from __future__ import annotations

import asyncio

import pytest

from backend.services import (
    cms_analysis_jobs,
    persistent_state,
    season_api_analysis_service,
    season_trend_jobs,
)


@pytest.fixture(autouse=True)
def in_memory_job_stores(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(persistent_state, "enabled", lambda: False)
    with cms_analysis_jobs._JOBS_LOCK:
        cms_analysis_jobs._JOBS.clear()
    with season_trend_jobs._JOBS_LOCK:
        season_trend_jobs._JOBS.clear()
        season_trend_jobs._LATEST_JOB_IDS.clear()
    yield
    with cms_analysis_jobs._JOBS_LOCK:
        cms_analysis_jobs._JOBS.clear()
    with season_trend_jobs._JOBS_LOCK:
        season_trend_jobs._JOBS.clear()
        season_trend_jobs._LATEST_JOB_IDS.clear()


def test_cancelled_cms_job_cannot_be_overwritten_by_late_success() -> None:
    job_id = cms_analysis_jobs.create_cms_analysis_job("user__PL", {"as_of": "2026-07-29"})

    cancelled = cms_analysis_jobs.cancel_cms_analysis_job(job_id)
    cms_analysis_jobs.update_cms_analysis_job(job_id, status="succeeded", result={"late": True})

    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
    assert cms_analysis_jobs.get_cms_analysis_job(job_id)["status"] == "cancelled"
    assert "result" not in cms_analysis_jobs.get_cms_analysis_job(job_id)


def test_cancelled_season_job_is_no_longer_latest() -> None:
    job_id = season_trend_jobs.create_season_trend_job({}, "user__PL")
    assert season_trend_jobs.is_latest_season_trend_job(job_id, "user__PL")

    cancelled = season_trend_jobs.cancel_season_trend_job(job_id)
    season_trend_jobs.update_season_trend_job(job_id, status="succeeded", result={"late": True})

    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
    assert not season_trend_jobs.is_latest_season_trend_job(job_id, "user__PL")
    assert season_trend_jobs.get_season_trend_job(job_id)["status"] == "cancelled"


def test_cancelled_running_season_job_does_not_publish_late_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = season_trend_jobs.create_season_trend_job({}, "user__PL")
    published: list[dict[str, object]] = []

    async def exercise() -> None:
        analysis_started = asyncio.Event()
        allow_analysis_to_finish = asyncio.Event()

        async def fake_run_in_threadpool(function, *args, **kwargs):
            if function is season_api_analysis_service.run_api_analysis_with_options:
                analysis_started.set()
                await allow_analysis_to_finish.wait()
                return {"source_meta": {}, "analysis_options": {}}
            if function is season_api_analysis_service.save_latest_season_trend_result:
                published.append(args[0])
                return None
            raise AssertionError(f"unexpected threadpool function: {function}")

        monkeypatch.setattr(
            season_api_analysis_service,
            "run_in_threadpool",
            fake_run_in_threadpool,
        )
        monkeypatch.setattr(
            season_api_analysis_service,
            "write_audit_event",
            lambda *args, **kwargs: None,
        )

        running = asyncio.create_task(
            season_api_analysis_service.run_api_analysis_job(
                job_id,
                {"security_scope": "user__PL"},
            )
        )
        await analysis_started.wait()
        season_trend_jobs.cancel_season_trend_job(job_id)
        running.cancel()
        allow_analysis_to_finish.set()
        await running

    asyncio.run(exercise())

    assert published == []
    assert season_trend_jobs.get_season_trend_job(job_id)["status"] == "cancelled"


def test_cancelling_season_job_returns_without_waiting_for_background_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling must not block on the still-running CMS fetch.

    Otherwise the caller's concurrency slot (released in the caller's
    ``finally``) stays held until the abandoned fetch finishes, and a
    just-cancelled user immediately hits "another analysis is already
    running" when starting a new one.
    """
    job_id = season_trend_jobs.create_season_trend_job({}, "user__PL")

    async def exercise() -> bool:
        analysis_started = asyncio.Event()
        allow_analysis_to_finish = asyncio.Event()

        async def fake_run_in_threadpool(function, *args, **kwargs):
            if function is season_api_analysis_service.run_api_analysis_with_options:
                analysis_started.set()
                await allow_analysis_to_finish.wait()
                return {"source_meta": {}, "analysis_options": {}}
            raise AssertionError(f"unexpected threadpool function: {function}")

        monkeypatch.setattr(
            season_api_analysis_service,
            "run_in_threadpool",
            fake_run_in_threadpool,
        )
        monkeypatch.setattr(
            season_api_analysis_service,
            "write_audit_event",
            lambda *args, **kwargs: None,
        )

        running = asyncio.create_task(
            season_api_analysis_service.run_api_analysis_job(
                job_id,
                {"security_scope": "user__PL"},
            )
        )
        await analysis_started.wait()
        season_trend_jobs.cancel_season_trend_job(job_id)
        running.cancel()

        try:
            await asyncio.wait_for(running, timeout=1.0)
            returned_promptly = True
        except asyncio.TimeoutError:
            returned_promptly = False

        allow_analysis_to_finish.set()
        return returned_promptly

    assert asyncio.run(exercise())
