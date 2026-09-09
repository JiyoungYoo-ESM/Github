"""In-memory job state for long-running CMS order analyses."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from backend.services.job_retention import prune_jobs
from backend.services import persistent_state


_JOBS: dict[str, dict[str, object]] = {}
_JOBS_LOCK = Lock()


def create_cms_analysis_job(client_id: str, request_body: dict[str, object]) -> str:
    job_id = f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    if persistent_state.enabled():
        persistent_state.create_job(
            job_id=job_id,
            kind="cms",
            client_id=client_id,
            request_payload=request_body,
        )
        return job_id
    now = datetime.now(timezone.utc).isoformat()
    with _JOBS_LOCK:
        prune_jobs(_JOBS)
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "client_id": client_id,
            "request_body": request_body,
        }
    return job_id


def update_cms_analysis_job(job_id: str, **patch: object) -> None:
    if persistent_state.enabled():
        persistent_state.update_job(job_id, **patch)
        return
    now = datetime.now(timezone.utc).isoformat()
    with _JOBS_LOCK:
        current = _JOBS.get(job_id)
        if not current:
            return
        if current.get("status") == "cancelled" and patch.get("status") != "cancelled":
            return
        current.update(patch)
        current["updated_at"] = now
        prune_jobs(_JOBS)


def get_cms_analysis_job(job_id: str) -> dict[str, object] | None:
    if persistent_state.enabled():
        return persistent_state.get_job(job_id)
    with _JOBS_LOCK:
        prune_jobs(_JOBS)
        current = _JOBS.get(job_id)
        return dict(current) if current else None


def cancel_cms_analysis_job(job_id: str) -> dict[str, object] | None:
    if persistent_state.enabled():
        return persistent_state.cancel_job(job_id)
    now = datetime.now(timezone.utc).isoformat()
    with _JOBS_LOCK:
        current = _JOBS.get(job_id)
        if current is None:
            return None
        if current.get("status") in {"queued", "running"}:
            current.update(
                {
                    "status": "cancelled",
                    "status_code": 499,
                    "error": "사용자가 분석을 중단했습니다.",
                    "updated_at": now,
                }
            )
        return dict(current)


def prune_cms_analysis_jobs() -> int:
    if persistent_state.enabled():
        from backend.config import JOB_MAX_RETAINED, JOB_RETENTION_HOURS

        return persistent_state.prune_jobs(
            "cms", retention_hours=JOB_RETENTION_HOURS, max_retained=JOB_MAX_RETAINED
        )
    with _JOBS_LOCK:
        return len(prune_jobs(_JOBS))
