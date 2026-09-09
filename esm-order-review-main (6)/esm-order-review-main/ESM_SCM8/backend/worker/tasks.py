"""Worker entry points; task arguments are JSON-safe durable job identifiers."""

from __future__ import annotations

import asyncio

from backend.config import CELERY_TASK_MAX_RETRIES, CELERY_TASK_RETRY_BACKOFF_SECONDS
from backend.worker.celery_app import celery_app


_RETRYABLE_STATUS_CODES = {502, 503}
_SLOT_WAIT_MAX_RETRIES = 70  # 35 minutes at the default 30-second backoff.


def _retry_if_transient(task, job: dict[str, object] | None, requeue) -> None:
    if not job or job.get("status") != "failed" or int(job.get("status_code") or 0) not in _RETRYABLE_STATUS_CODES:
        return
    if task.request.retries >= CELERY_TASK_MAX_RETRIES:
        return
    requeue()
    raise task.retry(countdown=CELERY_TASK_RETRY_BACKOFF_SECONDS * (2 ** task.request.retries))


@celery_app.task(name="analysis.cms", bind=True)
def run_cms_analysis_task(self, job_id: str, body: dict[str, object], client_id: str, owner_username: str, entity_code: str) -> None:
    from backend.services.cms_analysis_jobs import get_cms_analysis_job, update_cms_analysis_job
    from backend.schemas import CmsAnalyzeRequest
    from backend.services.cms_analysis_service import _run_cms_analysis_job

    asyncio.run(
        _run_cms_analysis_job(
            job_id,
            CmsAnalyzeRequest.model_validate(body),
            client_id,
            owner_username,
            entity_code,
        )
    )
    _retry_if_transient(self, get_cms_analysis_job(job_id), lambda: update_cms_analysis_job(job_id, status="queued", error=None, status_code=None))


@celery_app.task(name="analysis.season", bind=True)
def run_season_analysis_task(self, job_id: str, analysis_options: dict[str, object], client_id: str) -> None:
    from backend.services.concurrency import acquire_analysis_slot, release_analysis_slot
    from backend.services.season_api_analysis_service import run_api_analysis_job
    from backend.services.season_trend_jobs import get_season_trend_job, update_season_trend_job

    job = get_season_trend_job(job_id)
    # A late/redelivered message must never execute a job already claimed by
    # another worker.  ``run_api_analysis_job`` repeats this as an atomic CAS.
    if job is None or job.get("status") != "queued":
        return

    # Queue waiting is not active execution. Acquire the shared slot only after
    # Celery has delivered the task to a worker, so an unavailable worker cannot
    # leave the submitting browser stuck behind a stale Redis lease.
    acquired = asyncio.run(acquire_analysis_slot(client_id))
    if not acquired:
        if self.request.retries >= _SLOT_WAIT_MAX_RETRIES:
            update_season_trend_job(
                job_id,
                status="failed",
                status_code=503,
                error="분석 대기 시간이 길어 작업을 종료했습니다. 잠시 후 다시 시도해 주세요.",
            )
            return
        raise self.retry(
            countdown=CELERY_TASK_RETRY_BACKOFF_SECONDS,
            max_retries=_SLOT_WAIT_MAX_RETRIES,
        )

    try:
        asyncio.run(run_api_analysis_job(job_id, analysis_options))
        _retry_if_transient(self, get_season_trend_job(job_id), lambda: update_season_trend_job(job_id, status="queued", error=None, status_code=None))
    finally:
        asyncio.run(release_analysis_slot(client_id))


@celery_app.task(name="analysis.order_logic_v3", bind=True)
def run_order_logic_v3_task(
    self,
    job_id: str,
    request_body: dict[str, object],
    client_id: str,
) -> None:
    from backend.services.order_logic_v3_service import run_order_logic_v3_job

    asyncio.run(run_order_logic_v3_job(job_id, client_id, request_body))
