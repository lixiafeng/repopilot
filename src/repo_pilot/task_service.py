from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from repo_pilot.db.models import RepairAttempt, RepairTask, TraceEvent
from repo_pilot.db.session import SessionLocal
from repo_pilot.event_sink import reset_trace_sink, set_trace_sink
from repo_pilot.runtime import create_workflow, resolve_repo_path


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_task(
    db: Session,
    *,
    repo_path: str,
    issue: str,
    test_command: str,
    provider: str,
    model: str,
    max_iterations: int,
    apply_patch: bool,
    command_timeout_sec: int,
) -> RepairTask:
    task = RepairTask(
        repo_path=repo_path,
        issue=issue,
        test_command=test_command,
        provider=provider,
        model=model,
        max_iterations=max_iterations,
        apply_patch=apply_patch,
        command_timeout_sec=command_timeout_sec,
        status="PENDING",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int) -> RepairTask | None:
    return db.get(RepairTask, task_id)


def list_tasks(db: Session, limit: int = 50) -> list[RepairTask]:
    stmt = select(RepairTask).order_by(RepairTask.id.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def list_attempts(db: Session, task_id: int) -> list[RepairAttempt]:
    stmt = (
        select(RepairAttempt)
        .where(RepairAttempt.task_id == task_id)
        .order_by(RepairAttempt.attempt_no.asc())
    )
    return list(db.scalars(stmt).all())


def list_trace_events(db: Session, task_id: int) -> list[TraceEvent]:
    stmt = (
        select(TraceEvent)
        .where(TraceEvent.task_id == task_id)
        .order_by(TraceEvent.id.asc())
    )
    return list(db.scalars(stmt).all())


def _find_attempt(db: Session, task_id: int, attempt_no: int) -> RepairAttempt | None:
    stmt = select(RepairAttempt).where(
        RepairAttempt.task_id == task_id,
        RepairAttempt.attempt_no == attempt_no,
    )
    return db.scalar(stmt)


def _ensure_attempt(db: Session, task: RepairTask, attempt_no: int) -> RepairAttempt:
    attempt = _find_attempt(db, task.id, attempt_no)
    if attempt is not None:
        return attempt

    attempt = RepairAttempt(
        task_id=task.id,
        attempt_no=attempt_no,
        status="RUNNING",
        stage="iteration_started",
    )
    db.add(attempt)
    db.flush()
    return attempt


def _event_stage(event_type: str, payload: dict[str, Any]) -> str:
    explicit = payload.get("stage")
    if explicit:
        return str(explicit)

    mapping = {
        "workflow_started": "starting",
        "repo_scanned": "repo_scan",
        "symbols_indexed": "symbol_index",
        "initial_test_finished": "initial_test",
        "failure_analyzed": "failure_analysis",
        "iteration_started": "iteration",
        "context_built": "context_build",
        "plan_created": "repair_plan",
        "patch_created": "patch_generation",
        "patch_reviewed": "patch_review",
        "patch_applied": "patch_apply",
        "verification_finished": "verification",
        "snapshot_restored": "rollback",
        "workflow_error": "error",
        "workflow_finished": "finished",
        "cost_summary": "cost",
    }
    return mapping.get(event_type, event_type)


def _task_status_for_event(event_type: str, payload: dict[str, Any]) -> str | None:
    if event_type in {"repo_scanned", "symbols_indexed", "initial_test_finished", "failure_analyzed", "context_built"}:
        return "ANALYZING"
    if event_type == "plan_created":
        return "PLANNING"
    if event_type in {"patch_created", "patch_reviewed", "patch_applied"}:
        return "PATCHING"
    if event_type == "verification_finished":
        return "TESTING"
    if event_type == "snapshot_restored":
        return "RETRYING"
    if event_type == "workflow_error":
        return "FAILED"
    return None


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(v) for v in value]
    return str(value)


def _make_trace_sink(db: Session, task: RepairTask):
    current_attempt_id: int | None = None

    def sink(event_type: str, payload: dict[str, Any]) -> None:
        nonlocal current_attempt_id

        iteration_raw = payload.get("iteration")
        iteration = int(iteration_raw) if iteration_raw is not None else 0

        if event_type == "iteration_started" and iteration > 0:
            previous = None
            if iteration > 1:
                previous = _find_attempt(db, task.id, iteration - 1)
            if previous is not None and previous.status == "RUNNING":
                previous.status = "FAILED"
                previous.finished_at = utcnow()

            attempt = _ensure_attempt(db, task, iteration)
            current_attempt_id = attempt.id
            task.current_iteration = iteration
            task.status = "RETRYING" if iteration > 1 else "RUNNING"

        attempt: RepairAttempt | None = None
        if iteration > 0:
            attempt = _ensure_attempt(db, task, iteration)
            current_attempt_id = attempt.id
        elif current_attempt_id is not None:
            attempt = db.get(RepairAttempt, current_attempt_id)

        stage = _event_stage(event_type, payload)
        task.current_stage = stage

        mapped_status = _task_status_for_event(event_type, payload)
        if mapped_status is not None:
            task.status = mapped_status

        if attempt is not None:
            attempt.stage = stage

            if event_type == "plan_created":
                attempt.plan = _json_value(payload.get("plan"))
            elif event_type == "patch_created":
                attempt.patch = _json_value(payload.get("patch"))
            elif event_type == "patch_applied":
                attempt.diff = str(payload.get("diff") or "")
            elif event_type == "patch_reviewed" and not bool(payload.get("approved", True)):
                attempt.status = "FAILED"
                attempt.error_type = "PATCH_REVIEW_FAILED"
                attempt.error_message = str(payload.get("issues") or "")
                attempt.finished_at = utcnow()
            elif event_type == "verification_finished":
                if bool(payload.get("success")):
                    attempt.status = "SUCCEEDED"
                else:
                    attempt.status = "FAILED"
                    attempt.error_type = str(payload.get("stage") or "TEST_FAILED")
                attempt.finished_at = utcnow()

        safe_payload = {
            str(k): _json_value(v)
            for k, v in payload.items()
        }
        db.add(
            TraceEvent(
                task_id=task.id,
                attempt_id=attempt.id if attempt is not None else None,
                stage=stage,
                event_type=event_type,
                payload=safe_payload,
            )
        )
        db.commit()

    return sink


def run_persisted_task(task_id: int) -> None:
    db = SessionLocal()
    token = None
    try:
        task = db.get(RepairTask, task_id)
        if task is None:
            raise ValueError(f"RepairTask {task_id} does not exist")

        task.status = "RUNNING"
        task.current_stage = "starting"
        task.started_at = task.started_at or utcnow()
        task.finished_at = None
        task.success = None
        task.error_type = None
        task.error_message = None
        db.commit()

        sink = _make_trace_sink(db, task)
        token = set_trace_sink(sink)

        repo = resolve_repo_path(task.repo_path)
        workflow = create_workflow(
            provider=task.provider,
            model=task.model,
            max_iterations=task.max_iterations,
            apply_patch=task.apply_patch,
            command_timeout_sec=task.command_timeout_sec,
        )
        result = workflow.run(
            repo=repo,
            issue=task.issue,
            test_command=task.test_command,
        )

        task.success = result.success
        task.message = result.message
        task.current_iteration = result.iteration
        task.final_diff = result.diff or ""
        task.test_output = result.test_output or ""
        task.status = "SUCCEEDED" if result.success else "FAILED"
        task.current_stage = "finished"
        task.finished_at = utcnow()

        if result.iteration > 0:
            attempt = _ensure_attempt(db, task, result.iteration)
            attempt.diff = result.diff or attempt.diff
            attempt.test_output = result.test_output or ""
            attempt.status = "SUCCEEDED" if result.success else "FAILED"
            attempt.finished_at = attempt.finished_at or utcnow()

        db.commit()

    except Exception as exc:
        db.rollback()
        task = db.get(RepairTask, task_id)
        if task is not None:
            task.status = "FAILED"
            task.success = False
            task.current_stage = "error"
            task.error_type = type(exc).__name__
            task.error_message = str(exc)
            task.message = f"Task failed: {type(exc).__name__}: {exc}"
            task.finished_at = utcnow()
            db.commit()
        raise
    finally:
        if token is not None:
            reset_trace_sink(token)
        db.close()


def dispatch_task(task_id: int) -> None:
    mode = os.getenv("REPOPILOT_TASK_MODE", "inline").strip().lower()

    if mode == "inline":
        run_persisted_task(task_id)
        return

    if mode == "celery":
        db = SessionLocal()
        try:
            task = db.get(RepairTask, task_id)
            if task is None:
                raise ValueError(f"RepairTask {task_id} does not exist")
            task.status = "QUEUED"
            task.current_stage = "queued"
            db.commit()
        finally:
            db.close()

        from repo_pilot.worker.tasks import execute_repair_task

        execute_repair_task.delay(task_id)
        return

    raise ValueError(
        "REPOPILOT_TASK_MODE must be 'inline' or 'celery', "
        f"got: {mode!r}"
    )
