from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from repo_pilot.db.models import RepairAttempt, RepairTask, TraceEvent
from repo_pilot.db.session import get_db
from repo_pilot.result import WorkflowResult
from repo_pilot.runtime import create_workflow, resolve_repo_path
from repo_pilot.task_service import (
    create_task,
    dispatch_task,
    get_task,
    list_attempts,
    list_tasks,
    list_trace_events,
)


class HealthResponse(BaseModel):
    status: str


class RepairRequest(BaseModel):
    repo: str = Field(min_length=1)
    issue: str = Field(min_length=1)
    test_command: str = Field(default="python -m pytest -q", min_length=1)
    provider: str = Field(default="fake", min_length=1)
    model: str = Field(default="fake-model", min_length=1)
    max_iterations: int = Field(default=2, ge=1, le=10)
    apply_patch: bool = True
    command_timeout_sec: int = Field(default=120, ge=1, le=3600)


class RepairResponse(BaseModel):
    success: bool
    message: str
    iteration: int
    diff: str
    test_output: str


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repo_path: str
    issue: str
    test_command: str
    provider: str
    model: str
    max_iterations: int
    apply_patch: bool
    command_timeout_sec: int
    status: str
    current_stage: str | None
    current_iteration: int
    success: bool | None
    message: str | None
    final_diff: str | None
    test_output: str | None
    error_type: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    attempt_no: int
    status: str
    stage: str | None
    plan: Any | None
    patch: Any | None
    diff: str | None
    test_output: str | None
    error_type: str | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


class TraceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    attempt_id: int | None
    stage: str | None
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


app = FastAPI(
    title="RepoPilot API",
    description="RepoPilot repository repair agent with persistent repair tasks.",
    version="0.2.0",
)

repair_lock = Lock()


def _resolve_repo_http(repo_text: str):
    try:
        return resolve_repo_path(repo_text)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def to_repair_response(result: WorkflowResult) -> RepairResponse:
    return RepairResponse(
        success=result.success,
        message=result.message,
        iteration=result.iteration,
        diff=result.diff or "",
        test_output=result.test_output or "",
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/repair", response_model=RepairResponse)
def repair(request: RepairRequest) -> RepairResponse:
    repo = _resolve_repo_http(request.repo)

    try:
        with repair_lock:
            workflow = create_workflow(
                provider=request.provider,
                model=request.model,
                max_iterations=request.max_iterations,
                apply_patch=request.apply_patch,
                command_timeout_sec=request.command_timeout_sec,
            )
            result = workflow.run(
                repo=repo,
                issue=request.issue,
                test_command=request.test_command,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start repair workflow: {type(exc).__name__}: {exc}",
        ) from exc

    return to_repair_response(result)


@app.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_repair_task(
    request: RepairRequest,
    db: Session = Depends(get_db),
) -> RepairTask:
    _resolve_repo_http(request.repo)

    task = create_task(
        db,
        repo_path=request.repo,
        issue=request.issue,
        test_command=request.test_command,
        provider=request.provider,
        model=request.model,
        max_iterations=request.max_iterations,
        apply_patch=request.apply_patch,
        command_timeout_sec=request.command_timeout_sec,
    )

    try:
        dispatch_task(task.id)
    except Exception as exc:
        task = get_task(db, task.id)
        if task is not None:
            task.status = "FAILED"
            task.error_type = type(exc).__name__
            task.error_message = str(exc)
            db.commit()
            db.refresh(task)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to dispatch task: {type(exc).__name__}: {exc}",
        ) from exc

    task = get_task(db, task.id)
    assert task is not None
    db.refresh(task)
    return task


@app.get("/tasks", response_model=list[TaskRead])
def get_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[RepairTask]:
    return list_tasks(db, limit=limit)


@app.get("/tasks/{task_id}", response_model=TaskRead)
def get_repair_task(
    task_id: int,
    db: Session = Depends(get_db),
) -> RepairTask:
    task = get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Repair task not found")
    return task


@app.get("/tasks/{task_id}/attempts", response_model=list[AttemptRead])
def get_repair_attempts(
    task_id: int,
    db: Session = Depends(get_db),
) -> list[RepairAttempt]:
    if get_task(db, task_id) is None:
        raise HTTPException(status_code=404, detail="Repair task not found")
    return list_attempts(db, task_id)


@app.get("/tasks/{task_id}/trace", response_model=list[TraceRead])
def get_repair_trace(
    task_id: int,
    db: Session = Depends(get_db),
) -> list[TraceEvent]:
    if get_task(db, task_id) is None:
        raise HTTPException(status_code=404, detail="Repair task not found")
    return list_trace_events(db, task_id)
