"""In-process resource guard for report generation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from backend.config import MAX_CONCURRENT_REPORT_EXPORTS
from backend.services.storage import remove_path

_lock = asyncio.Lock()
_active_exports = 0
_background_finalizers: set[asyncio.Task[None]] = set()


async def acquire_report_slot() -> bool:
    global _active_exports
    async with _lock:
        if _active_exports >= MAX_CONCURRENT_REPORT_EXPORTS:
            return False
        _active_exports += 1
        return True


async def release_report_slot() -> None:
    global _active_exports
    async with _lock:
        _active_exports = max(0, _active_exports - 1)


def defer_report_release(task: asyncio.Task[Path]) -> None:
    """Keep the slot while a timed-out worker thread is still generating."""

    async def finalize() -> None:
        try:
            output_path = await task
        except BaseException:
            output_path = None
        try:
            if output_path is not None:
                remove_path(output_path.parent)
        finally:
            await release_report_slot()

    finalizer = asyncio.create_task(finalize())
    _background_finalizers.add(finalizer)
    finalizer.add_done_callback(_background_finalizers.discard)


def report_resource_snapshot() -> dict[str, int]:
    return {
        "active_exports": _active_exports,
        "max_concurrent_exports": MAX_CONCURRENT_REPORT_EXPORTS,
        "timed_out_workers": len(_background_finalizers),
    }
