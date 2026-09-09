"""Submission boundary between the web process and Celery workers."""

from __future__ import annotations

from backend.config import CELERY_BROKER_URL, CELERY_TASK_MAX_RETRIES, CELERY_TASK_RETRY_BACKOFF_SECONDS


class TaskQueueUnavailable(RuntimeError):
    pass


def _publish_retry_policy() -> dict[str, int]:
    return {
        "max_retries": CELERY_TASK_MAX_RETRIES,
        "interval_start": CELERY_TASK_RETRY_BACKOFF_SECONDS,
        "interval_step": CELERY_TASK_RETRY_BACKOFF_SECONDS,
        "interval_max": CELERY_TASK_RETRY_BACKOFF_SECONDS * 4,
    }


def enabled() -> bool:
    return bool(CELERY_BROKER_URL)


def enqueue_cms(job_id: str, body: dict[str, object], client_id: str, owner_username: str, entity_code: str) -> None:
    if not enabled():
        raise TaskQueueUnavailable("CELERY_BROKER_URL is not configured.")
    try:
        from backend.worker.tasks import run_cms_analysis_task

        run_cms_analysis_task.apply_async(
            args=[job_id, body, client_id, owner_username, entity_code],
            task_id=f"cms:{job_id}",
            queue="analysis",
            retry=True,
            retry_policy=_publish_retry_policy(),
        )
    except Exception as exc:  # noqa: BLE001
        raise TaskQueueUnavailable("Could not enqueue CMS analysis.") from exc


def enqueue_season(job_id: str, analysis_options: dict[str, object], client_id: str) -> None:
    if not enabled():
        raise TaskQueueUnavailable("CELERY_BROKER_URL is not configured.")
    try:
        from backend.worker.tasks import run_season_analysis_task

        run_season_analysis_task.apply_async(
            args=[job_id, analysis_options, client_id],
            task_id=f"season:{job_id}",
            queue="analysis",
            retry=True,
            retry_policy=_publish_retry_policy(),
        )
    except Exception as exc:  # noqa: BLE001
        raise TaskQueueUnavailable("Could not enqueue season analysis.") from exc


def enqueue_order_logic_v3(job_id: str, request_body: dict[str, object], client_id: str) -> None:
    """Publish one durable V3 job without putting source/result data on Redis."""
    if not enabled():
        raise TaskQueueUnavailable("CELERY_BROKER_URL is not configured.")
    try:
        from backend.worker.tasks import run_order_logic_v3_task

        run_order_logic_v3_task.apply_async(
            args=[job_id, request_body, client_id],
            task_id=f"order-v3:{job_id}",
            queue="order-v3",
            retry=True,
            retry_policy=_publish_retry_policy(),
        )
    except Exception as exc:  # noqa: BLE001
        raise TaskQueueUnavailable("Could not enqueue V3 analysis.") from exc


def cancel_cms(job_id: str) -> None:
    if not enabled():
        return
    try:
        from backend.worker.celery_app import celery_app

        celery_app.control.revoke(f"cms:{job_id}", terminate=False)
    except Exception as exc:  # noqa: BLE001
        raise TaskQueueUnavailable("Could not cancel CMS analysis.") from exc


def cancel_order_logic_v3(job_id: str) -> None:
    if not enabled():
        return
    try:
        from backend.worker.celery_app import celery_app

        # Running V3 work observes the database cancellation flag. A queued
        # message is revoked before execution; terminate=False avoids killing a
        # worker in the middle of shared CMS/cache cleanup.
        celery_app.control.revoke(f"order-v3:{job_id}", terminate=False)
    except Exception as exc:  # noqa: BLE001
        raise TaskQueueUnavailable("Could not cancel V3 analysis.") from exc
