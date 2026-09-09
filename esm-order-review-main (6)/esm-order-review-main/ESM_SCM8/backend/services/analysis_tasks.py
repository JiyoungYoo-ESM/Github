"""Track timed-out analysis threads until their real work has finished."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from backend.services.concurrency import release_analysis_slot

T = TypeVar("T")

_background_finalizers: set[asyncio.Task[None]] = set()


def create_analysis_task(awaitable: Awaitable[T]) -> asyncio.Task[T]:
    """Create a task that is not implicitly cancelled by an HTTP timeout."""

    return asyncio.create_task(awaitable)


async def wait_without_cancelling(task: asyncio.Task[T], timeout_seconds: float) -> tuple[bool, T | None]:
    """Wait up to ``timeout_seconds`` while leaving unfinished thread work alive."""

    done, _ = await asyncio.wait({task}, timeout=timeout_seconds)
    if not done:
        return False, None
    return True, task.result()


def defer_slot_release(
    task: asyncio.Task[object],
    client_id: str,
    cleanup: Callable[[], None],
) -> None:
    """Release resources only after an abandoned worker has actually stopped."""

    async def finalize() -> None:
        try:
            await task
        except BaseException:
            # The request already returned its error; consume the worker outcome.
            pass
        finally:
            try:
                cleanup()
            finally:
                await release_analysis_slot(client_id)

    finalizer = asyncio.create_task(finalize())
    _background_finalizers.add(finalizer)
    finalizer.add_done_callback(_background_finalizers.discard)


def pending_analysis_finalizers() -> int:
    return len(_background_finalizers)
