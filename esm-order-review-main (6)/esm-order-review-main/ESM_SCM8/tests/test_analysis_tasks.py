from __future__ import annotations

import asyncio

from backend.services import analysis_tasks, concurrency


def reset_slots() -> None:
    concurrency._active_analysis_total = 0
    concurrency._active_analysis_by_client.clear()


def test_timeout_keeps_slot_until_worker_really_finishes(monkeypatch):
    async def scenario() -> None:
        reset_slots()
        monkeypatch.setattr(concurrency, "MAX_CONCURRENT_ANALYSES", 1)
        worker_release = asyncio.Event()
        cleanup_calls: list[str] = []

        async def worker() -> str:
            await worker_release.wait()
            return "done"

        assert await concurrency.acquire_analysis_slot("client-a") is True
        task = analysis_tasks.create_analysis_task(worker())
        completed, result = await analysis_tasks.wait_without_cancelling(task, 0)
        assert completed is False
        assert result is None

        analysis_tasks.defer_slot_release(task, "client-a", lambda: cleanup_calls.append("cleaned"))
        await asyncio.sleep(0)
        assert concurrency.active_analysis_snapshot()["active_total"] == 1
        assert await concurrency.acquire_analysis_slot("client-b") is False

        worker_release.set()
        for _ in range(10):
            await asyncio.sleep(0)
            if analysis_tasks.pending_analysis_finalizers() == 0:
                break

        assert cleanup_calls == ["cleaned"]
        assert concurrency.active_analysis_snapshot()["active_total"] == 0
        assert await concurrency.acquire_analysis_slot("client-b") is True
        await concurrency.release_analysis_slot("client-b")
        reset_slots()

    asyncio.run(scenario())


def test_completed_worker_returns_result_without_background_finalizer():
    async def scenario() -> None:
        task = analysis_tasks.create_analysis_task(asyncio.sleep(0, result={"ok": True}))

        completed, result = await analysis_tasks.wait_without_cancelling(task, 1)

        assert completed is True
        assert result == {"ok": True}
        assert analysis_tasks.pending_analysis_finalizers() == 0

    asyncio.run(scenario())
