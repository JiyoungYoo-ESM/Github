"""Retention policy shared by in-memory asynchronous job registries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.config import JOB_MAX_RETAINED, JOB_RETENTION_HOURS

TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}


def prune_jobs(
    jobs: dict[str, dict[str, object]],
    *,
    now: datetime | None = None,
    retention_hours: int = JOB_RETENTION_HOURS,
    max_retained: int = JOB_MAX_RETAINED,
) -> set[str]:
    """Remove expired jobs and cap retained terminal results by recency.

    Non-terminal jobs are only removed when stale beyond the retention window,
    which also prevents abandoned queued/running entries from leaking forever.
    """

    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(hours=max(retention_hours, 0))
    removed: set[str] = set()
    dated: list[tuple[datetime, str, bool]] = []

    for job_id, job in jobs.items():
        updated_at = parse_job_time(job.get("updated_at") or job.get("created_at"))
        terminal = str(job.get("status") or "") in TERMINAL_JOB_STATUSES
        if updated_at is not None and updated_at < cutoff:
            removed.add(job_id)
            continue
        dated.append((updated_at or datetime.min.replace(tzinfo=timezone.utc), job_id, terminal))

    retained_terminal = sorted(
        (item for item in dated if item[2] and item[1] not in removed),
        reverse=True,
    )
    for _, job_id, _ in retained_terminal[max(max_retained, 0):]:
        removed.add(job_id)

    for job_id in removed:
        jobs.pop(job_id, None)
    return removed


def parse_job_time(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
