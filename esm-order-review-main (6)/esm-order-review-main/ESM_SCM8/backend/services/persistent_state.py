"""Small database repository for runtime state.

Development can run without a database and keeps the previous in-memory/file
behaviour. Production already requires ``DATABASE_URL`` and therefore uses
this repository exclusively for the state represented here.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select, update

from backend import database
from backend.models.persistence import AnalysisJob, LatestAnalysisSnapshot
from backend.models.persistence import AuthSession


def enabled() -> bool:
    return bool(database.DATABASE_URL)


def _json_value(value: dict[str, object] | None) -> dict[str, object] | None:
    if value is None:
        return None
    # Result payloads may contain Decimal/Timestamp values from analysis code.
    # Normalising once gives PostgreSQL and SQLite identical JSON semantics.
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def create_job(
    *,
    job_id: str,
    kind: str,
    client_id: str | None = None,
    security_scope: str | None = None,
    request_payload: dict[str, object] | None = None,
    is_latest: bool = False,
) -> None:
    with database.get_session_factory()() as session:
        if is_latest and security_scope:
            session.execute(
                update(AnalysisJob)
                .where(AnalysisJob.kind == kind, AnalysisJob.security_scope == security_scope)
                .values(is_latest=False)
            )
        session.add(
            AnalysisJob(
                job_id=job_id,
                kind=kind,
                status="queued",
                client_id=client_id,
                security_scope=security_scope,
                is_latest=is_latest,
                request_payload=_json_value(request_payload),
            )
        )
        session.commit()


def update_job(job_id: str, **patch: object) -> None:
    allowed = {"status", "status_code", "error", "result", "is_latest"}
    values: dict[str, object] = {
        key: value for key, value in patch.items() if key in allowed
    }
    if "result" in values:
        values["result_payload"] = _json_value(values.pop("result"))  # type: ignore[arg-type]
    if not values:
        return
    values["updated_at"] = datetime.now(timezone.utc)
    with database.get_session_factory()() as session:
        statement = update(AnalysisJob).where(AnalysisJob.job_id == job_id)
        if values.get("status") != "cancelled":
            statement = statement.where(AnalysisJob.status != "cancelled")
        session.execute(statement.values(**values))
        session.commit()


def claim_job(job_id: str, kind: str) -> bool:
    """Atomically move one queued job to running.

    Celery may redeliver a message when a worker is lost.  A compare-and-set
    transition ensures that only the first delivery executes the expensive
    CMS analysis.
    """

    now = datetime.now(timezone.utc)
    with database.get_session_factory()() as session:
        result = session.execute(
            update(AnalysisJob)
            .where(
                AnalysisJob.job_id == job_id,
                AnalysisJob.kind == kind,
                AnalysisJob.status == "queued",
            )
            .values(
                status="running",
                status_code=None,
                error=None,
                updated_at=now,
            )
        )
        session.commit()
        return bool(result.rowcount)


def finish_running_job(job_id: str, kind: str, **patch: object) -> bool:
    """Persist a terminal outcome only while the job is still running."""

    status = patch.get("status")
    if status not in {"succeeded", "failed", "cancelled"}:
        raise ValueError("finish_running_job requires a terminal status.")
    allowed = {"status", "status_code", "error", "result", "is_latest"}
    values: dict[str, object] = {
        key: value for key, value in patch.items() if key in allowed
    }
    if "result" in values:
        values["result_payload"] = _json_value(values.pop("result"))  # type: ignore[arg-type]
    values["updated_at"] = datetime.now(timezone.utc)
    with database.get_session_factory()() as session:
        result = session.execute(
            update(AnalysisJob)
            .where(
                AnalysisJob.job_id == job_id,
                AnalysisJob.kind == kind,
                AnalysisJob.status == "running",
            )
            .values(**values)
        )
        session.commit()
        return bool(result.rowcount)


def fail_stale_running_job(
    job_id: str,
    kind: str,
    *,
    stale_after_seconds: int,
    error: str,
) -> bool:
    """Fail an orphaned running record left behind by a terminated worker."""

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=max(stale_after_seconds, 0))
    with database.get_session_factory()() as session:
        result = session.execute(
            update(AnalysisJob)
            .where(
                AnalysisJob.job_id == job_id,
                AnalysisJob.kind == kind,
                AnalysisJob.status == "running",
                AnalysisJob.updated_at <= cutoff,
            )
            .values(
                status="failed",
                status_code=504,
                error=error,
                is_latest=False,
                updated_at=now,
            )
        )
        session.commit()
        return bool(result.rowcount)


def get_job(job_id: str) -> dict[str, object] | None:
    with database.get_session_factory()() as session:
        row = session.get(AnalysisJob, job_id)
        return _job_dict(row) if row else None


def cancel_job(job_id: str) -> dict[str, object] | None:
    now = datetime.now(timezone.utc)
    with database.get_session_factory()() as session:
        session.execute(
            update(AnalysisJob)
            .where(
                AnalysisJob.job_id == job_id,
                AnalysisJob.status.in_({"queued", "running"}),
            )
            .values(
                status="cancelled",
                status_code=499,
                error="사용자가 분석을 중단했습니다.",
                is_latest=False,
                updated_at=now,
            )
        )
        session.commit()
        row = session.get(AnalysisJob, job_id)
        return _job_dict(row) if row else None


def job_is_latest(job_id: str, security_scope: str | None = None) -> bool:
    with database.get_session_factory()() as session:
        row = session.get(AnalysisJob, job_id)
        return bool(
            row
            and row.is_latest
            and (security_scope is None or row.security_scope == security_scope)
        )


def supersede_jobs(kind: str, security_scope: str) -> None:
    with database.get_session_factory()() as session:
        session.execute(
            update(AnalysisJob)
            .where(AnalysisJob.kind == kind, AnalysisJob.security_scope == security_scope)
            .values(is_latest=False, updated_at=datetime.now(timezone.utc))
        )
        session.commit()


def prune_jobs(kind: str, *, retention_hours: int, max_retained: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(retention_hours, 0))
    with database.get_session_factory()() as session:
        rows = list(
            session.scalars(
                select(AnalysisJob).where(AnalysisJob.kind == kind).order_by(AnalysisJob.updated_at.desc())
            )
        )
        removable = [
            row.job_id
            for row in rows
            if _as_utc(row.updated_at) < cutoff
        ]
        terminal = [
            row
            for row in rows
            if row.status in {"succeeded", "failed", "cancelled"} and row.job_id not in removable
        ]
        removable.extend(row.job_id for row in terminal[max(max_retained, 0):])
        if removable:
            session.execute(delete(AnalysisJob).where(AnalysisJob.job_id.in_(set(removable))))
            session.commit()
        return len(set(removable))


def save_snapshot(snapshot_key: str, kind: str, payload: dict[str, object]) -> None:
    normalized = _json_value(payload)
    assert normalized is not None
    now = datetime.now(timezone.utc)
    with database.get_session_factory()() as session:
        row = session.get(LatestAnalysisSnapshot, snapshot_key)
        if row is None:
            session.add(LatestAnalysisSnapshot(snapshot_key=snapshot_key, kind=kind, payload=normalized))
        else:
            row.kind = kind
            row.payload = normalized
            row.updated_at = now
        session.commit()


def load_snapshot(snapshot_key: str) -> dict[str, object] | None:
    with database.get_session_factory()() as session:
        row = session.get(LatestAnalysisSnapshot, snapshot_key)
        return dict(row.payload) if row else None


def delete_snapshot(snapshot_key: str) -> None:
    with database.get_session_factory()() as session:
        session.execute(delete(LatestAnalysisSnapshot).where(LatestAnalysisSnapshot.snapshot_key == snapshot_key))
        session.commit()


def prune_expired_sessions() -> int:
    """Remove expired server-side sessions without waiting for a browser retry."""
    with database.get_session_factory()() as session:
        result = session.execute(
            delete(AuthSession).where(AuthSession.expires_at < datetime.now(timezone.utc))
        )
        session.commit()
        return int(result.rowcount or 0)


def newest_snapshot(kind: str) -> tuple[str, dict[str, object]] | None:
    with database.get_session_factory()() as session:
        row = session.scalar(
            select(LatestAnalysisSnapshot)
            .where(LatestAnalysisSnapshot.kind == kind)
            .order_by(LatestAnalysisSnapshot.updated_at.desc())
        )
        return (row.snapshot_key, dict(row.payload)) if row else None


def _job_dict(row: AnalysisJob) -> dict[str, object]:
    result: dict[str, object] = {
        "job_id": row.job_id,
        "status": row.status,
        "created_at": _as_utc(row.created_at).isoformat(),
        "updated_at": _as_utc(row.updated_at).isoformat(),
    }
    if row.client_id is not None:
        result["client_id"] = row.client_id
    if row.security_scope is not None:
        result["security_scope"] = row.security_scope
    if row.request_payload is not None:
        result["request_body" if row.kind == "cms" else "analysis_options"] = dict(row.request_payload)
    if row.result_payload is not None:
        result["result"] = dict(row.result_payload)
    if row.status_code is not None:
        result["status_code"] = row.status_code
    if row.error is not None:
        result["error"] = row.error
    return result


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
