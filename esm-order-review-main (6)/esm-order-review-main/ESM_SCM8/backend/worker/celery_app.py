"""Celery application for durable analysis execution."""

from __future__ import annotations

from backend.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND, CELERY_TASK_TIME_LIMIT_SECONDS

try:
    from celery import Celery
except ImportError as exc:  # pragma: no cover - dependency is installed in worker deployments
    raise RuntimeError("celery must be installed to run the analysis worker.") from exc

celery_app = Celery(
    "esm_scm",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND or None,
    include=["backend.worker.tasks"],
)
celery_app.conf.update(
    task_default_queue="analysis",
    task_acks_late=True,
    task_acks_on_failure_or_timeout=False,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=CELERY_TASK_TIME_LIMIT_SECONDS,
    task_track_started=True,
    task_publish_retry=True,
    # Redis only redelivers an unacknowledged task after this lease. Keep it
    # comfortably beyond the hard task limit to avoid concurrent redelivery.
    broker_transport_options={"visibility_timeout": CELERY_TASK_TIME_LIMIT_SECONDS * 2},
    broker_connection_retry_on_startup=True,
)
