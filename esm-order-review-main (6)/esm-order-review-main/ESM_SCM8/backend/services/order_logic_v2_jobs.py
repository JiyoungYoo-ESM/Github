"""Transient/background job registry for the BETA order-logic screen."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from backend.services import persistent_state
from backend.services.job_retention import prune_jobs


JOB_KIND = "order_logic_v2"
_JOBS: dict[str, dict[str, object]] = {}
_JOBS_LOCK = Lock()


def order_logic_v2_entity_scope(client_id: str, entity_code: object) -> str:
    """Return the latest-job scope for one browser client and legal entity."""

    resolved_entity = str(entity_code or "PL").strip().upper() or "PL"
    return f"{client_id}::{resolved_entity}"


def create_order_logic_v2_job(
    client_id: str,
    request_body: dict[str, object],
    *,
    is_latest: bool = True,
) -> str:
    job_id = f"order2_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    entity_scope = order_logic_v2_entity_scope(
        client_id,
        request_body.get("entity_code"),
    )
    if persistent_state.enabled():
        persistent_state.create_job(
            job_id=job_id,
            kind=JOB_KIND,
            client_id=client_id,
            security_scope=entity_scope,
            request_payload=request_body,
            is_latest=is_latest,
        )
        return job_id

    now = datetime.now(timezone.utc).isoformat()
    with _JOBS_LOCK:
        prune_jobs(_JOBS)
        if is_latest:
            for job in _JOBS.values():
                if job.get("security_scope") == entity_scope:
                    job["is_latest"] = False
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "client_id": client_id,
            "security_scope": entity_scope,
            "analysis_options": request_body,
            "is_latest": is_latest,
        }
    return job_id


def update_order_logic_v2_job(job_id: str, **patch: object) -> None:
    if persistent_state.enabled():
        persistent_state.update_job(job_id, **patch)
        return
    now = datetime.now(timezone.utc).isoformat()
    with _JOBS_LOCK:
        current = _JOBS.get(job_id)
        if current is None:
            return
        current.update(patch)
        current["updated_at"] = now
        prune_jobs(_JOBS)


def get_order_logic_v2_job(job_id: str) -> dict[str, object] | None:
    if persistent_state.enabled():
        return persistent_state.get_job(job_id)
    with _JOBS_LOCK:
        prune_jobs(_JOBS)
        current = _JOBS.get(job_id)
        return dict(current) if current else None


def prune_order_logic_v2_jobs() -> int:
    if persistent_state.enabled():
        from backend.config import JOB_MAX_RETAINED, JOB_RETENTION_HOURS

        return persistent_state.prune_jobs(
            JOB_KIND,
            retention_hours=JOB_RETENTION_HOURS,
            max_retained=JOB_MAX_RETAINED,
        )
    with _JOBS_LOCK:
        return len(prune_jobs(_JOBS))


__all__ = [
    "create_order_logic_v2_job",
    "get_order_logic_v2_job",
    "order_logic_v2_entity_scope",
    "prune_order_logic_v2_jobs",
    "update_order_logic_v2_job",
]
