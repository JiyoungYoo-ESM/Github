"""Queued V3 execution and out-of-memory behavior; synthetic inputs only."""

from __future__ import annotations

import asyncio
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from backend.routers import order_logic_v3 as routes
from backend.services import order_logic_v3_jobs as jobs
from backend.services import order_logic_v3_service as service
from backend.services import analysis_cancel, persistent_state, task_queue


BODY = {"entity_code": "HQ", "as_of": "2026-08-31", "preview": True}
SOURCE = ([], {"snapshot_id": "synthetic", "fetched_at": "2026-08-31T00:00:00Z"})


@pytest.fixture
def isolated(monkeypatch):
    monkeypatch.setattr(persistent_state, "enabled", lambda: False)
    monkeypatch.setattr(task_queue, "enabled", lambda: False)
    monkeypatch.setattr(jobs, "_JOBS", {})
    monkeypatch.setattr(service, "_RUNNING_TASKS", set())
    monkeypatch.setattr(service, "_CANCEL_SIGNALS", {})
    monkeypatch.setattr(service, "_LOCAL_EXECUTION_LIMIT", asyncio.Semaphore(1))
    audits = []
    monkeypatch.setattr(service, "write_audit_event", lambda *args, **kwargs: audits.append(kwargs))
    monkeypatch.setattr(routes, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "build_order_logic_v3_source", lambda **kwargs: SOURCE)
    monkeypatch.setattr(service, "build_order_logic_v3_calculation_result", lambda **kwargs: {
        "entity_code": kwargs["entity_code"], "status": "success", "blocking_contracts": [],
        "rows": [{"sku_code": "SYNTHETIC", "raw_order_quantity": 10.25}],
    })
    return audits


def queued(client="synthetic-client", body=BODY):
    job_id = service.queue_order_logic_v3_job(client, body)
    task = next(task for task in service._RUNNING_TASKS if task.get_name().endswith(job_id))
    return job_id, task


def test_local_requests_wait_instead_of_returning_busy(isolated, monkeypatch):
    started, release = Event(), Event()

    def source(**kwargs):
        started.set()
        assert release.wait(5)
        return SOURCE

    monkeypatch.setattr(service, "build_order_logic_v3_source", source)

    async def scenario():
        first_id, first_task = queued()
        assert await asyncio.to_thread(started.wait, 5)
        second_id, second_task = queued("other-client", {**BODY, "entity_code": "PL"})
        await asyncio.sleep(0)
        assert jobs.get_order_logic_v3_job(first_id)["status"] == "running"
        assert jobs.get_order_logic_v3_job(second_id)["status"] == "queued"
        assert first_id != second_id
        release.set()
        await asyncio.gather(first_task, second_task)
        assert jobs.get_order_logic_v3_job(first_id)["status"] == "succeeded"
        assert jobs.get_order_logic_v3_job(second_id)["status"] == "succeeded"

    asyncio.run(scenario())


@pytest.mark.parametrize("stage", ["source", "input_conversion", "calculation", "result_storage"])
def test_memory_error_is_explicit_audited(isolated, monkeypatch, stage):
    def fail(*args, **kwargs):
        raise MemoryError("Synthetic private data must not be returned")

    if stage == "source":
        monkeypatch.setattr(service, "build_order_logic_v3_source", fail)
    elif stage == "input_conversion":
        monkeypatch.setattr(service, "build_order_logic_v3_source", lambda **kwargs: ([{
            "sku_code": "SYNTHETIC", "daily_sales": {}, "seasonal_profile": None,
            "replenishment": None, "sales_grade": "GENERAL",
        }], SOURCE[1]))
        monkeypatch.setattr(service, "OrderLogicV3SkuCalculationInput", fail)
    elif stage == "calculation":
        monkeypatch.setattr(service, "build_order_logic_v3_calculation_result", fail)
    else:
        original = service.finish_order_logic_v3_job

        def finish(job_id, **patch):
            if patch.get("status") == "succeeded":
                fail()
            return original(job_id, **patch)

        monkeypatch.setattr(service, "finish_order_logic_v3_job", finish)

    async def scenario():
        job_id, task = queued()
        await task
        job = jobs.get_order_logic_v3_job(job_id)
        assert job["status"] == "failed"
        assert job["status_code"] == 503
        assert "메모리가 부족" in job["error"]
        assert "private data" not in job["error"]
        assert isolated[-1]["error_type"] == "MemoryError"
        assert isolated[-1]["stage"] == stage

    asyncio.run(scenario())


@pytest.mark.parametrize("exception,status", [(ValueError, 422), (RuntimeError, 500)])
def test_other_failures_are_recorded(isolated, monkeypatch, exception, status):
    def fail(**kwargs):
        raise exception("Synthetic failure")

    monkeypatch.setattr(service, "build_order_logic_v3_source", fail)

    async def scenario():
        job_id, task = queued()
        await task
        assert jobs.get_order_logic_v3_job(job_id)["status_code"] == status

    asyncio.run(scenario())


def test_v3_timeout_is_persisted_before_the_source_thread_exits(isolated, monkeypatch):
    calculated: list[bool] = []

    def slow_source(**kwargs):
        del kwargs
        import time

        time.sleep(0.03)
        return SOURCE

    monkeypatch.setattr(service, "ORDER_LOGIC_V3_ANALYSIS_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(service, "bounded_worker_timeout_seconds", lambda value: value)
    monkeypatch.setattr(service, "build_order_logic_v3_source", slow_source)
    monkeypatch.setattr(
        service,
        "build_order_logic_v3_calculation_result",
        lambda **kwargs: calculated.append(True),
    )

    async def scenario():
        job_id, task = queued()
        await task
        job = jobs.get_order_logic_v3_job(job_id)
        assert job["status"] == "failed"
        assert job["status_code"] == 504

    asyncio.run(scenario())
    assert calculated == []
    assert analysis_cancel.active_token_count() == 0


@pytest.mark.parametrize("task_cancel", [False, True])
def test_cancel_keeps_local_capacity_until_source_thread_exits(isolated, monkeypatch, task_cancel):
    started, release = Event(), Event()

    def source(**kwargs):
        started.set()
        assert release.wait(5)
        return SOURCE

    monkeypatch.setattr(service, "build_order_logic_v3_source", source)
    monkeypatch.setattr(
        service,
        "build_order_logic_v3_calculation_result",
        lambda **kwargs: pytest.fail("Cancelled job must not calculate"),
    )

    async def scenario():
        job_id, running_task = queued()
        assert await asyncio.to_thread(started.wait, 5)
        if task_cancel:
            running_task.cancel()
            await asyncio.sleep(0)
            running_task.cancel()
        else:
            service.cancel_order_logic_v3_job(job_id, "synthetic-client", "HQ")
        waiting_id, waiting_task = queued("waiting-client", {**BODY, "entity_code": "PL"})
        await asyncio.sleep(0)
        assert jobs.get_order_logic_v3_job(waiting_id)["status"] == "queued"
        assert not waiting_task.done()
        service.cancel_order_logic_v3_job(waiting_id, "waiting-client", "PL")
        release.set()
        if task_cancel:
            with pytest.raises(asyncio.CancelledError):
                await running_task
        else:
            await running_task
        await waiting_task
        assert jobs.get_order_logic_v3_job(job_id)["status"] == "cancelled"

    asyncio.run(scenario())


def test_cancel_before_start_never_fetches(isolated, monkeypatch):
    monkeypatch.setattr(service, "build_order_logic_v3_source", lambda **kwargs: pytest.fail("Must not fetch"))

    async def scenario():
        job_id, task = queued()
        service.cancel_order_logic_v3_job(job_id, "synthetic-client", "HQ")
        await task
        assert jobs.get_order_logic_v3_job(job_id)["status"] == "cancelled"

    asyncio.run(scenario())


def test_job_creation_failure_creates_no_task(isolated, monkeypatch):
    def fail(*args):
        raise RuntimeError("Synthetic store unavailable")

    monkeypatch.setattr(service, "create_order_logic_v3_job", fail)
    with pytest.raises(RuntimeError):
        service.queue_order_logic_v3_job("synthetic-client", BODY)
    assert not service._RUNNING_TASKS


def test_concurrent_posts_are_both_accepted_and_owned(isolated, monkeypatch):
    started, release = Event(), Event()

    def source(**kwargs):
        started.set()
        assert release.wait(5)
        return SOURCE

    monkeypatch.setattr(service, "build_order_logic_v3_source", source)
    app = FastAPI()

    @app.middleware("http")
    async def auth(request: Request, call_next):
        request.state.current_user = SimpleNamespace(username="synthetic-user")
        request.state.entity_code = request.headers.get("x-entity-code", "HQ")
        return await call_next(request)

    app.include_router(routes.router)
    with TestClient(app) as client:
        try:
            first = client.post(
                "/api/order-logic-v3/jobs", json={"as_of": "2026-08-31"},
                headers={"X-Client-Id": "synthetic-browser"},
            )
            assert first.status_code == 202
            assert started.wait(5)
            second = client.post(
                "/api/order-logic-v3/jobs", json={"as_of": "2026-08-31"},
                headers={"X-Client-Id": "other-browser", "X-Entity-Code": "PL"},
            )
            assert second.status_code == 202
            assert second.json()["job_id"] != first.json()["job_id"]
            assert len(jobs._JOBS) == 2
            assert jobs.get_order_logic_v3_job(second.json()["job_id"])["status"] == "queued"
        finally:
            for job in list(jobs._JOBS.values()):
                service.cancel_order_logic_v3_job(
                    str(job["job_id"]), str(job["client_id"]),
                    str((job["analysis_options"] or {})["entity_code"]),
                )
            release.set()


def test_task_creation_failure_marks_job_failed(isolated, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic task creation failure")

    monkeypatch.setattr(service.asyncio, "create_task", fail)
    with pytest.raises(RuntimeError):
        service.queue_order_logic_v3_job("synthetic-client", BODY)
    assert next(iter(jobs._JOBS.values()))["status"] == "failed"


def test_distributed_queue_requires_persistent_job_store(isolated, monkeypatch):
    monkeypatch.setattr(task_queue, "enabled", lambda: True)
    with pytest.raises(HTTPException) as caught:
        service.queue_order_logic_v3_job("synthetic-client", BODY)
    assert caught.value.status_code == 503
    assert next(iter(jobs._JOBS.values()))["status"] == "failed"


def test_production_never_falls_back_to_process_local_execution(isolated, monkeypatch):
    monkeypatch.setattr(service, "IS_PRODUCTION", True)
    with pytest.raises(HTTPException) as caught:
        service.queue_order_logic_v3_job("synthetic-client", BODY)
    assert caught.value.status_code == 503
    assert not jobs._JOBS
