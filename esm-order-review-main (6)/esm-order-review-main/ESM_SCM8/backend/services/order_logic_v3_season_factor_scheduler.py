"""Configurable monthly runner for V3 season-factor artifacts."""

from __future__ import annotations

import asyncio
from datetime import datetime
import traceback

from backend.config import (
    SCM_V3_SEASON_FACTOR_CHECK_INTERVAL_SECONDS,
    SCM_V3_SEASON_FACTOR_MONTHLY_DAY,
    SCM_V3_SEASON_FACTOR_MONTHLY_ENABLED,
    SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST,
)
from backend.services.audit import write_audit_event
from backend.services.order_logic_v3_ledger import LEDGER_POLICY
from backend.services.order_logic_v3_season_factor_service import (
    monthly_completed_window,
)
from backend.services.order_logic_v3_season_factor_jobs import queue_refresh
from backend.services.order_logic_v3_season_factor_store import (
    load_latest_candidate,
)
from core.common import korea_now


def _is_schedule_reached(now: datetime) -> bool:
    day = SCM_V3_SEASON_FACTOR_MONTHLY_DAY
    hour = SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST
    if day is None or hour is None:
        return False
    return now.day > day or (now.day == day and now.hour >= hour)


def refresh_due_for_entity(now: datetime, entity_code: str) -> bool:
    """Return true once per completed-month target after the configured gate."""

    if not _is_schedule_reached(now):
        return False
    _start, target_end, _months = monthly_completed_window(now.date())
    latest_candidate = load_latest_candidate(entity_code)
    return not (
        latest_candidate
        and str(latest_candidate.get("window_end") or "") == target_end.isoformat()
        and (latest_candidate.get("source_request") or {}).get("demand_policy") == LEDGER_POLICY
    )


def refresh_due_season_factors_once(now: datetime | None = None) -> dict[str, object]:
    current = now or korea_now()
    results: dict[str, object] = {}
    for entity_code in ("HQ", "PL", "USA"):
        if not refresh_due_for_entity(current, entity_code):
            results[entity_code] = {"status": "skipped", "reason": "not_due"}
            continue
        try:
            latest = load_latest_candidate(entity_code)
            # A source migration resumes already verified monthly ledger caches.
            # Routine refreshes after migration still reload historical corrections.
            force_refresh = bool(latest and (latest.get("source_request") or {}).get("demand_policy") == LEDGER_POLICY)
            job = queue_refresh(
                as_of=current.date().isoformat(),
                entity_code=entity_code,
                force_refresh=force_refresh,
                trigger="scheduled",
            )
            results[entity_code] = {
                "status": job["status"],
                "job_id": job["job_id"],
            }
            write_audit_event(
                "order_logic_v3_season_factor_monthly_queued",
                None,
                entity_code=entity_code,
                **results[entity_code],
            )
        except Exception as exc:  # noqa: BLE001 - keep other entities running
            traceback.print_exc()
            results[entity_code] = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            write_audit_event(
                "order_logic_v3_season_factor_monthly_failed",
                None,
                entity_code=entity_code,
                error_type=type(exc).__name__,
                error=str(exc),
            )
    return {"now_kst": current.isoformat(), "entities": results}


async def season_factor_monthly_loop() -> None:
    interval_seconds = max(SCM_V3_SEASON_FACTOR_CHECK_INTERVAL_SECONDS, 1)
    while True:
        try:
            await asyncio.to_thread(refresh_due_season_factors_once)
        except Exception as exc:  # noqa: BLE001 - background loop must survive
            traceback.print_exc()
            write_audit_event(
                "order_logic_v3_season_factor_scheduler_failed",
                None,
                error_type=type(exc).__name__,
                error=str(exc),
            )
        await asyncio.sleep(interval_seconds)


def start_season_factor_monthly_task() -> asyncio.Task[None] | None:
    if not SCM_V3_SEASON_FACTOR_MONTHLY_ENABLED:
        return None
    return asyncio.create_task(
        season_factor_monthly_loop(),
        name="order-v3-season-factor-monthly",
    )


__all__ = [
    "refresh_due_for_entity",
    "refresh_due_season_factors_once",
    "start_season_factor_monthly_task",
]
