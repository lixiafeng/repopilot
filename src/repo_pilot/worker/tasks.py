from __future__ import annotations

from repo_pilot.task_service import run_persisted_task
from repo_pilot.worker.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="repo_pilot.execute_repair_task",
    autoretry_for=(),
)
def execute_repair_task(self, task_id: int) -> None:
    run_persisted_task(task_id)
