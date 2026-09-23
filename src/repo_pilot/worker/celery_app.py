from __future__ import annotations

import os

from celery import Celery


redis_url = os.getenv("REPOPILOT_REDIS_URL", "redis://127.0.0.1:6379/0")

celery_app = Celery(
    "repopilot",
    broker=redis_url,
    backend=redis_url,
)

celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
