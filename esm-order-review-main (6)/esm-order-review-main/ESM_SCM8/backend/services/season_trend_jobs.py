"""In-memory job state for long-running season trend API analyses."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from backend.config import ANALYSIS_JOB_STALE_SECONDS
from backend.services.job_retention import parse_job_time, prune_jobs
from backend.services import persistent_state


_JOBS: dict[str, dict[str, object]] = {}
_JOBS_LOCK = Lock()
_LATEST_JOB_IDS: dict[str, str] = {}
_STALE_JOB_ERROR = (
    "분석 작업이 실행 제한 시간을 초과했거나 작업자가 중단되어 종료되었습니다. "
    "다시 분석해 주세요."
)


def _normalized_security_scope(security_scope: str) -> str:
    return str(security_scope or "default")


def create_season_trend_job(analysis_options: dict[str, object], security_scope: str = "default") -> str:
    security_scope = _normalized_security_scope(security_scope)
    job_id = uuid4().hex
    if persistent_state.enabled():
        persistent_state.create_job(
            job_id=job_id,
            kind="season",
            security_scope=security_scope,
            request_payload=analysis_options,
            is_latest=True,
        )
        return job_id
    now = datetime.now(timezone.utc).isoformat()
    with _JOBS_LOCK:
        _prune_locked()
        _LATEST_JOB_IDS[security_scope] = job_id
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "analysis_options": analysis_options,
            "security_scope": security_scope,
        }
    return job_id


def supersede_running_season_trend_jobs(security_scope: str = "default") -> None:
    """Prevent older jobs in one security scope from publishing a stale result."""
    security_scope = _normalized_security_scope(security_scope)
    if persistent_state.enabled():
        persistent_state.supersede_jobs("season", security_scope)
        return
    with _JOBS_LOCK:
        _LATEST_JOB_IDS.pop(security_scope, None)


def is_latest_season_trend_job(job_id: str, security_scope: str | None = None) -> bool:
    if persistent_state.enabled():
        return persistent_state.job_is_latest(job_id, security_scope)
    with _JOBS_LOCK:
        _prune_locked()
        current = _JOBS.get(job_id)
        if not current:
            return False
        job_security_scope = _normalized_security_scope(str(current.get("security_scope") or "default"))
        if security_scope is not None and _normalized_security_scope(security_scope) != job_security_scope:
            return False
        return _LATEST_JOB_IDS.get(job_security_scope) == job_id


def update_season_trend_job(job_id: str, **patch: object) -> None:
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
        _prune_locked()


def claim_season_trend_job(job_id: str) -> bool:
    """Atomically reserve a queued job for exactly one worker delivery."""

    if persistent_state.enabled():
        return persistent_state.claim_job(job_id, "season")
    now = datetime.now(timezone.utc).isoformat()
    with _JOBS_LOCK:
        _prune_locked()
        current = _JOBS.get(job_id)
        if current is None or current.get("status") != "queued":
            return False
        current.update(
            status="running",
            status_code=None,
            error=None,
            updated_at=now,
        )
        return True


def finish_season_trend_job(job_id: str, **patch: object) -> bool:
    """Write a terminal result without reviving a cancelled/timed-out job."""

    if patch.get("status") not in {"succeeded", "failed", "cancelled"}:
        raise ValueError("finish_season_trend_job requires a terminal status.")
    if persistent_state.enabled():
        return persistent_state.finish_running_job(job_id, "season", **patch)
    now = datetime.now(timezone.utc).isoformat()
    with _JOBS_LOCK:
        current = _JOBS.get(job_id)
        if current is None or current.get("status") != "running":
            return False
        current.update(patch)
        current["updated_at"] = now
        _prune_locked()
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


def get_season_trend_job(job_id: str) -> dict[str, object] | None:
    if persistent_state.enabled():
        persistent_state.fail_stale_running_job(
            job_id,
            "season",
            stale_after_seconds=ANALYSIS_JOB_STALE_SECONDS,
            error=_STALE_JOB_ERROR,
        )
        return persistent_state.get_job(job_id)
    with _JOBS_LOCK:
        _prune_locked()
        _expire_stale_running_job_locked(job_id)
        current = _JOBS.get(job_id)
        return dict(current) if current else None


def cancel_season_trend_job(job_id: str) -> dict[str, object] | None:
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
                    "is_latest": False,
                    "updated_at": now,
                }
            )
            security_scope = _normalized_security_scope(
                str(current.get("security_scope") or "default")
            )
            if _LATEST_JOB_IDS.get(security_scope) == job_id:
                _LATEST_JOB_IDS.pop(security_scope, None)
        return dict(current)


def _prune_locked() -> int:
    removed = prune_jobs(_JOBS)
    for security_scope, job_id in list(_LATEST_JOB_IDS.items()):
        if job_id in removed:
            del _LATEST_JOB_IDS[security_scope]
    return len(removed)


def prune_season_trend_jobs() -> int:
    if persistent_state.enabled():
        from backend.config import JOB_MAX_RETAINED, JOB_RETENTION_HOURS

        return persistent_state.prune_jobs(
            "season", retention_hours=JOB_RETENTION_HOURS, max_retained=JOB_MAX_RETAINED
        )
    with _JOBS_LOCK:
        return _prune_locked()
