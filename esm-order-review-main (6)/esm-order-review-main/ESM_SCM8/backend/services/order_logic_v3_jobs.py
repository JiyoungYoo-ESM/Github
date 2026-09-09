"""Transient/persistent job registry for V3 preview runs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from backend.config import (
    ANALYSIS_JOB_STALE_SECONDS,
    JOB_MAX_RETAINED,
    JOB_RETENTION_HOURS,
    STORAGE_ROOT,
)
from backend.services import persistent_state
from backend.services.job_retention import parse_job_time, prune_jobs


JOB_KIND = "order_logic_v3"
_JOBS: dict[str, dict[str, object]] = {}
_JOBS_LOCK = Lock()
LOCAL_COMPLETED_JOB_ROOT = STORAGE_ROOT / "runtime" / "order-v3-completed-jobs"
_PAGED_RESULT_MARKER = "_order_logic_v3_paged_result"
_STALE_JOB_ERROR = (
    "V3 분석 작업이 실행 제한 시간을 초과했거나 작업자가 중단되어 종료되었습니다. "
    "다시 분석해 주세요."
)


def _local_job_path(job_id: str):
    if not job_id.startswith("order3_") or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for character in job_id
    ):
        raise ValueError("Unsafe V3 job id.")
    return LOCAL_COMPLETED_JOB_ROOT / f"{job_id}.json"


def _persist_completed_job(job: dict[str, object]) -> None:
    """Persist only a small page manifest, never the full SKU result arrays."""
    result = job.get("result")
    if job.get("status") != "succeeded" or not isinstance(result, dict) or _PAGED_RESULT_MARKER not in result:
        return
    path = _local_job_path(str(job.get("job_id") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".json.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(job, ensure_ascii=False, separators=(",", ":"), default=str),
        encoding="utf-8",
    )
    temporary.replace(path)
    _prune_completed_job_files()


def _load_completed_job(job_id: str) -> dict[str, object] | None:
    try:
        path = _local_job_path(job_id)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict) or value.get("job_id") != job_id or value.get("status") != "succeeded":
        return None
    updated_at = parse_job_time(value.get("updated_at") or value.get("created_at"))
    if updated_at is None or (datetime.now(timezone.utc) - updated_at).total_seconds() > max(JOB_RETENTION_HOURS, 0) * 3600:
        _delete_completed_job_file(job_id)
        return None
    return value


def _delete_completed_job_file(job_id: str) -> None:
    try:
        path = _local_job_path(job_id)
        path.unlink(missing_ok=True)
        from backend.services.order_logic_v3_result_store import delete_local_result
        delete_local_result(job_id)
    except (OSError, ValueError):
        pass


def _prune_completed_job_files() -> None:
    try:
        files = sorted(
            LOCAL_COMPLETED_JOB_ROOT.glob("order3_*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    cutoff = datetime.now(timezone.utc).timestamp() - max(JOB_RETENTION_HOURS, 0) * 3600
    for index, path in enumerate(files):
        try:
            expired = path.stat().st_mtime < cutoff
        except OSError:
            continue
        if expired or index >= max(JOB_MAX_RETAINED, 0):
            _delete_completed_job_file(path.stem)


def order_logic_v3_entity_scope(client_id: str, entity_code: object) -> str:
    resolved_entity = str(entity_code or "").strip().upper()
    return f"{client_id}::{resolved_entity}"


def create_order_logic_v3_job(
    client_id: str,
    request_body: dict[str, object],
) -> str:
    job_id = f"order3_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    entity_scope = order_logic_v3_entity_scope(
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
            is_latest=False,
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
            "security_scope": entity_scope,
            "analysis_options": request_body,
            "is_latest": False,
        }
    return job_id


def update_order_logic_v3_job(job_id: str, **patch: object) -> None:
    if persistent_state.enabled():
        persistent_state.update_job(job_id, **patch)
        return
    now = datetime.now(timezone.utc).isoformat()
    persisted: dict[str, object] | None = None
    with _JOBS_LOCK:
        current = _JOBS.get(job_id)
        if current is None:
            return
        if current.get("status") == "cancelled":
            return
        current.update(patch)
        current["updated_at"] = now
        prune_jobs(_JOBS)
        if current.get("status") == "succeeded":
            persisted = dict(current)
    if persisted is not None:
        _persist_completed_job(persisted)


def claim_order_logic_v3_job(job_id: str) -> bool:
    """Atomically reserve a queued V3 job for one worker delivery."""

    if persistent_state.enabled():
        return persistent_state.claim_job(job_id, JOB_KIND)
    with _JOBS_LOCK:
        prune_jobs(_JOBS)
        current = _JOBS.get(job_id)
        if current is None or current.get("status") != "queued":
            return False
        current.update(
            status="running",
            status_code=None,
            error=None,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        return True


def finish_order_logic_v3_job(job_id: str, **patch: object) -> bool:
    """Persist a terminal outcome only if V3 is still actively running."""

    if patch.get("status") not in {"succeeded", "failed", "cancelled"}:
        raise ValueError("finish_order_logic_v3_job requires a terminal status.")
    if persistent_state.enabled():
        return persistent_state.finish_running_job(job_id, JOB_KIND, **patch)
    persisted: dict[str, object] | None = None
    with _JOBS_LOCK:
        current = _JOBS.get(job_id)
        if current is None or current.get("status") != "running":
            return False
        current.update(patch)
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        prune_jobs(_JOBS)
        if current.get("status") == "succeeded":
            persisted = dict(current)
    if persisted is not None:
        _persist_completed_job(persisted)
    return True


def _expire_stale_running_job_locked(job_id: str) -> None:
    current = _JOBS.get(job_id)
    if current is None or current.get("status") != "running":
        return
    updated_at = parse_job_time(current.get("updated_at"))
    if updated_at is None:
        return
    age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
    if age_seconds <= ANALYSIS_JOB_STALE_SECONDS:
        return
    current.update(
        status="failed",
        status_code=504,
        error=_STALE_JOB_ERROR,
        is_latest=False,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def cancel_order_logic_v3_job_record(job_id: str) -> dict[str, object] | None:
    """Atomically cancel active work; completed results remain intact."""
    if persistent_state.enabled():
        return persistent_state.cancel_job(job_id)
    with _JOBS_LOCK:
        current = _JOBS.get(job_id)
        if current is None:
            return None
        if current.get("status") in {"queued", "running"}:
            current.update(
                status="cancelled",
                status_code=499,
                error="사용자가 분석을 중단했습니다.",
                is_latest=False,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
        return dict(current)


def get_order_logic_v3_job(job_id: str) -> dict[str, object] | None:
    if persistent_state.enabled():
        persistent_state.fail_stale_running_job(
            job_id,
            JOB_KIND,
            stale_after_seconds=ANALYSIS_JOB_STALE_SECONDS,
            error=_STALE_JOB_ERROR,
        )
        return persistent_state.get_job(job_id)
    with _JOBS_LOCK:
        prune_jobs(_JOBS)
        _expire_stale_running_job_locked(job_id)
        current = _JOBS.get(job_id)
        if current:
            return dict(current)
    restored = _load_completed_job(job_id)
    if restored is None:
        return None
    with _JOBS_LOCK:
        _JOBS[job_id] = restored
    return dict(restored)


def get_order_logic_v3_job_metadata(job_id: str) -> dict[str, object] | None:
    """Poll without loading/copying a potentially hundreds-of-MB result."""
    if persistent_state.enabled():
        from sqlalchemy import select
        from sqlalchemy.orm import defer
        from backend import database
        from backend.models.persistence import AnalysisJob

        persistent_state.fail_stale_running_job(
            job_id,
            JOB_KIND,
            stale_after_seconds=ANALYSIS_JOB_STALE_SECONDS,
            error=_STALE_JOB_ERROR,
        )
        with database.get_session_factory()() as session:
            row = session.scalar(select(AnalysisJob).where(
                AnalysisJob.job_id == job_id, AnalysisJob.kind == JOB_KIND,
            ).options(defer(AnalysisJob.result_payload, raiseload=True)))
            if row is None:
                return None
            return {
                "job_id": row.job_id, "status": row.status,
                "client_id": row.client_id, "analysis_options": row.request_payload,
                "status_code": row.status_code, "error": row.error,
            }
    with _JOBS_LOCK:
        prune_jobs(_JOBS)
        _expire_stale_running_job_locked(job_id)
        current = _JOBS.get(job_id)
        if current:
            return {key: value for key, value in current.items() if key != "result"}
    restored = _load_completed_job(job_id)
    if restored is None:
        return None
    with _JOBS_LOCK:
        _JOBS[job_id] = restored
    return {key: value for key, value in restored.items() if key != "result"}


__all__ = [
    "cancel_order_logic_v3_job_record",
    "claim_order_logic_v3_job",
    "create_order_logic_v3_job",
    "finish_order_logic_v3_job",
    "get_order_logic_v3_job",
    "get_order_logic_v3_job_metadata",
    "order_logic_v3_entity_scope",
    "update_order_logic_v3_job",
]
