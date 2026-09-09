from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest
from celery.exceptions import Retry

from backend.routers import season as season_router
from backend.services import season_api_analysis_service, season_trend_jobs
from backend.worker import tasks as worker_tasks


@pytest.fixture(autouse=True)
def clear_season_job_registry():
    with season_trend_jobs._JOBS_LOCK:
        season_trend_jobs._JOBS.clear()
        season_trend_jobs._LATEST_JOB_IDS.clear()
    yield
    with season_trend_jobs._JOBS_LOCK:
        season_trend_jobs._JOBS.clear()
        season_trend_jobs._LATEST_JOB_IDS.clear()


def test_account_and_entity_scopes_keep_independent_latest_jobs() -> None:
    admin_pl_first = season_trend_jobs.create_season_trend_job({}, "adminmaster__PL")
    eu_manager_pl = season_trend_jobs.create_season_trend_job({}, "eu_manager__PL")
    admin_hq = season_trend_jobs.create_season_trend_job({}, "adminmaster__HQ")
    admin_pl_second = season_trend_jobs.create_season_trend_job({}, "adminmaster__PL")

    assert not season_trend_jobs.is_latest_season_trend_job(admin_pl_first)
    assert season_trend_jobs.is_latest_season_trend_job(admin_pl_second)
    assert season_trend_jobs.is_latest_season_trend_job(eu_manager_pl)
    assert season_trend_jobs.is_latest_season_trend_job(admin_hq)

    season_trend_jobs.supersede_running_season_trend_jobs("adminmaster__PL")

    assert not season_trend_jobs.is_latest_season_trend_job(admin_pl_second)
    assert season_trend_jobs.is_latest_season_trend_job(eu_manager_pl)
    assert season_trend_jobs.is_latest_season_trend_job(admin_hq)


def test_concurrent_account_and_entity_jobs_each_publish_to_their_own_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scopes = ("adminmaster__PL", "eu_manager__PL", "adminmaster__HQ")
    jobs = {
        scope: season_trend_jobs.create_season_trend_job(
            {"security_scope": scope, "entity_code": scope.rsplit("__", 1)[1]},
            scope,
        )
        for scope in scopes
    }
    published: list[tuple[str, str]] = []

    def fake_analysis(
        analysis_options: dict[str, object],
        *,
        save_result: bool = True,
    ) -> dict[str, object]:
        raise AssertionError("analysis must be dispatched through run_in_threadpool")

    def fake_save(result: dict[str, object], security_scope: str = "default") -> None:
        published.append((security_scope, str(result["security_scope"])))

    async def exercise_concurrent_jobs() -> None:
        started_scopes: set[str] = set()
        all_started = asyncio.Event()

        async def fake_run_in_threadpool(function, *args, **kwargs):
            if function is fake_analysis:
                assert kwargs == {"save_result": False}
                analysis_options = args[0]
                security_scope = str(analysis_options["security_scope"])
                started_scopes.add(security_scope)
                if started_scopes == set(scopes):
                    all_started.set()
                await all_started.wait()
                return {"security_scope": security_scope}
            if function is fake_save:
                function(*args, **kwargs)
                return None
            raise AssertionError(f"unexpected threadpool function: {function}")

        monkeypatch.setattr(season_api_analysis_service, "run_api_analysis_with_options", fake_analysis)
        monkeypatch.setattr(season_api_analysis_service, "save_latest_season_trend_result", fake_save)
        monkeypatch.setattr(season_api_analysis_service, "run_in_threadpool", fake_run_in_threadpool)
        monkeypatch.setattr(season_api_analysis_service, "write_audit_event", lambda *args, **kwargs: None)

        await asyncio.gather(
            *(
                season_api_analysis_service.run_api_analysis_job(
                    jobs[scope],
                    {"security_scope": scope, "entity_code": scope.rsplit("__", 1)[1]},
                )
                for scope in scopes
            )
        )

    asyncio.run(exercise_concurrent_jobs())

    assert set(published) == {(scope, scope) for scope in scopes}
    for job_id in jobs.values():
        assert season_trend_jobs.get_season_trend_job(job_id)["status"] == "succeeded"


def test_cached_and_synchronous_requests_supersede_only_their_security_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    security_scope = "eu_manager__PL"
    superseded_scopes: list[str] = []
    cached_payload = {
        "status": "success",
        "analysis_options": {"average_eur_krw_rate": 1.0},
    }

    monkeypatch.setattr(season_router, "_api_analysis_options_from_body", lambda body: {})
    monkeypatch.setattr(
        season_router,
        "_scope_analysis_options",
        lambda request, options: (security_scope, {"security_scope": security_scope}),
    )
    monkeypatch.setattr(
        season_router,
        "_latest_api_analysis_matches",
        lambda options, scope: cached_payload,
    )
    monkeypatch.setattr(
        season_router,
        "supersede_running_season_trend_jobs",
        superseded_scopes.append,
    )
    monkeypatch.setattr(season_router, "write_audit_event", lambda *args, **kwargs: None)

    async def exercise_cached_paths() -> None:
        await season_router.start_season_trend_api_job(object(), object())
        await season_router.analyze_season_trend_from_api(object(), object())

    asyncio.run(exercise_cached_paths())

    assert superseded_scopes == [security_scope, security_scope]


def test_queued_api_job_does_not_reserve_execution_slot_before_worker_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued: list[tuple[str, dict[str, object], str]] = []

    monkeypatch.setattr(season_router, "_api_analysis_options_for_request", lambda request, body: {})
    monkeypatch.setattr(
        season_router,
        "_scope_analysis_options",
        lambda request, options: ("adminmaster__PL", {"security_scope": "adminmaster__PL"}),
    )
    monkeypatch.setattr(season_router, "_latest_api_analysis_matches", lambda options, scope: None)
    monkeypatch.setattr(season_router, "client_id_from_request", lambda request: "client-a")
    monkeypatch.setattr(season_router, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(season_router.task_queue, "enabled", lambda: True)
    monkeypatch.setattr(
        season_router.task_queue,
        "enqueue_season",
        lambda job_id, options, client_id: queued.append((job_id, options, client_id)),
    )

    async def must_not_acquire(_request):
        raise AssertionError("queued web request must not reserve an execution slot")

    monkeypatch.setattr(season_router, "_acquire_season_analysis_slot", must_not_acquire)

    response = asyncio.run(season_router.start_season_trend_api_job(object(), object()))

    assert response.status == "queued"
    assert response.job_id
    assert queued == [
        (response.job_id, {"security_scope": "adminmaster__PL"}, "client-a")
    ]


def test_season_worker_acquires_and_releases_slot_around_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = season_trend_jobs.create_season_trend_job({}, "adminmaster__PL")
    events: list[str] = []

    async def acquire(client_id: str) -> bool:
        events.append(f"acquire:{client_id}")
        return True

    async def run(job: str, options: dict[str, object]) -> None:
        events.append(f"run:{job}")
        season_trend_jobs.update_season_trend_job(job, status="succeeded", result={})

    async def release(client_id: str) -> None:
        events.append(f"release:{client_id}")

    import backend.services.concurrency as concurrency

    monkeypatch.setattr(concurrency, "acquire_analysis_slot", acquire)
    monkeypatch.setattr(concurrency, "release_analysis_slot", release)
    monkeypatch.setattr(season_api_analysis_service, "run_api_analysis_job", run)

    worker_tasks.run_season_analysis_task.run(job_id, {}, "client-a")

    assert events == [f"acquire:client-a", f"run:{job_id}", "release:client-a"]


def test_season_worker_requeues_when_all_execution_slots_are_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = season_trend_jobs.create_season_trend_job({}, "adminmaster__PL")
    executed: list[str] = []

    async def no_slot(_client_id: str) -> bool:
        return False

    async def run(job: str, _options: dict[str, object]) -> None:
        executed.append(job)

    import backend.services.concurrency as concurrency

    monkeypatch.setattr(concurrency, "acquire_analysis_slot", no_slot)
    monkeypatch.setattr(season_api_analysis_service, "run_api_analysis_job", run)

    with pytest.raises(Retry):
        worker_tasks.run_season_analysis_task.run(job_id, {}, "client-a")

    assert executed == []
    assert season_trend_jobs.get_season_trend_job(job_id)["status"] == "queued"


def test_duplicate_worker_delivery_does_not_run_an_already_claimed_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = season_trend_jobs.create_season_trend_job({}, "adminmaster__PL")
    assert season_trend_jobs.claim_season_trend_job(job_id) is True
    assert season_trend_jobs.claim_season_trend_job(job_id) is False
    monkeypatch.setattr(
        season_api_analysis_service,
        "run_api_analysis_with_options",
        lambda *args, **kwargs: pytest.fail("duplicate delivery must not execute"),
    )

    asyncio.run(
        season_api_analysis_service.run_api_analysis_job(
            job_id,
            {"security_scope": "adminmaster__PL"},
        )
    )

    assert season_trend_jobs.get_season_trend_job(job_id)["status"] == "running"


def test_polling_expires_an_orphaned_running_job(monkeypatch: pytest.MonkeyPatch) -> None:
    job_id = season_trend_jobs.create_season_trend_job({}, "adminmaster__PL")
    assert season_trend_jobs.claim_season_trend_job(job_id) is True
    monkeypatch.setattr(season_trend_jobs, "ANALYSIS_JOB_STALE_SECONDS", 60)
    with season_trend_jobs._JOBS_LOCK:
        season_trend_jobs._JOBS[job_id]["updated_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=61)
        ).isoformat()

    job = season_trend_jobs.get_season_trend_job(job_id)

    assert job is not None
    assert job["status"] == "failed"
    assert job["status_code"] == 504


def test_api_job_marks_timeout_but_waits_for_the_worker_to_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = season_trend_jobs.create_season_trend_job({}, "adminmaster__PL")

    def slow_analysis(
        analysis_options: dict[str, object],
        *,
        save_result: bool = True,
    ) -> dict[str, object]:
        del analysis_options, save_result
        time.sleep(0.03)
        return {"source_meta": {}, "analysis_options": {}}

    monkeypatch.setattr(season_api_analysis_service, "SEASON_ANALYSIS_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(season_api_analysis_service, "run_api_analysis_with_options", slow_analysis)
    monkeypatch.setattr(season_api_analysis_service, "write_audit_event", lambda *args, **kwargs: None)

    asyncio.run(season_api_analysis_service.run_api_analysis_job(job_id, {"security_scope": "adminmaster__PL"}))

    job = season_trend_jobs.get_season_trend_job(job_id)
    assert job is not None
    assert job["status"] == "failed"
    assert job["status_code"] == 504


@pytest.mark.parametrize("failure_stage", ["snapshot", "job_result"])
def test_result_storage_failure_finishes_job_instead_of_leaving_it_running(
    monkeypatch: pytest.MonkeyPatch, failure_stage: str,
) -> None:
    scope = "synthetic-storage-test"
    job_id = season_trend_jobs.create_season_trend_job({}, scope)
    audit_events: list[tuple[str, dict[str, object]]] = []
    original_finish = season_api_analysis_service.finish_season_trend_job

    def fail_storage(*args, **kwargs):
        raise RuntimeError("synthetic storage error with private payload")

    def finish(job, **patch):
        if patch.get("status") == "succeeded":
            fail_storage()
        return original_finish(job, **patch)

    monkeypatch.setattr(season_api_analysis_service, "run_api_analysis_with_options", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        season_api_analysis_service, "save_latest_season_trend_result",
        fail_storage if failure_stage == "snapshot" else lambda *args, **kwargs: None,
    )
    if failure_stage == "job_result":
        monkeypatch.setattr(season_api_analysis_service, "finish_season_trend_job", finish)
    monkeypatch.setattr(
        season_api_analysis_service, "write_audit_event",
        lambda event, request, **kwargs: audit_events.append((event, kwargs)),
    )

    asyncio.run(season_api_analysis_service.run_api_analysis_job(job_id, {"security_scope": scope}))

    job = season_trend_jobs.get_season_trend_job(job_id)
    assert job["status"] == "failed"
    assert job["status_code"] == 500
    assert "저장" in job["error"]
    assert "private payload" not in str(job)
    assert "private payload" not in str(audit_events)
    assert audit_events[-1][0] == "season_trend_api_analysis_job_failed"
    assert audit_events[-1][1]["phase"] == "result_persistence"


def test_result_storage_failure_does_not_overwrite_user_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    scope = "synthetic-cancel-test"
    job_id = season_trend_jobs.create_season_trend_job({}, scope)

    def cancel_during_save(*args, **kwargs):
        season_trend_jobs.cancel_season_trend_job(job_id)
        raise RuntimeError("synthetic storage error")

    monkeypatch.setattr(season_api_analysis_service, "run_api_analysis_with_options", lambda *args, **kwargs: {})
    monkeypatch.setattr(season_api_analysis_service, "save_latest_season_trend_result", cancel_during_save)
    monkeypatch.setattr(season_api_analysis_service, "write_audit_event", lambda *args, **kwargs: None)

    asyncio.run(season_api_analysis_service.run_api_analysis_job(job_id, {"security_scope": scope}))

    assert season_trend_jobs.get_season_trend_job(job_id)["status"] == "cancelled"
