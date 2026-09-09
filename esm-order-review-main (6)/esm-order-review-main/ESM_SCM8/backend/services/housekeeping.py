"""Periodic cleanup for retained files, caches and completed jobs."""

from __future__ import annotations

import asyncio

from backend.config import STORAGE_CLEANUP_INTERVAL_SECONDS
from backend.services.cms_analysis_jobs import prune_cms_analysis_jobs
from backend.services.cms_fetch_cache import prune_disk_cache
from backend.services.season_trend_jobs import prune_season_trend_jobs
from backend.services import persistent_state
from backend.services.storage import ensure_storage_dirs


def run_storage_housekeeping() -> dict[str, object]:
    ensure_storage_dirs()
    result = {
        "cms_cache": prune_disk_cache(),
        "cms_jobs_removed": prune_cms_analysis_jobs(),
        "season_jobs_removed": prune_season_trend_jobs(),
    }
    if persistent_state.enabled():
        result["expired_sessions_removed"] = persistent_state.prune_expired_sessions()
    return result


async def storage_housekeeping_loop() -> None:
    interval = max(STORAGE_CLEANUP_INTERVAL_SECONDS, 60)
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(run_storage_housekeeping)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[storage housekeeping failed] {type(exc).__name__}: {exc}", flush=True)
