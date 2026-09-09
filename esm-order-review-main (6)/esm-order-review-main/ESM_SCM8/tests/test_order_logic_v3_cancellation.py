"""V3 stop lifecycle, using synthetic jobs and isolated memory/SQLite stores."""

from __future__ import annotations

import asyncio
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import database
from backend.routers import order_logic_v3 as routes
from backend.services import order_logic_v3_jobs as jobs
from backend.services import order_logic_v3_service as service
from backend.services import persistent_state
from core.order_logic_v3 import textbook_candidate_parameters


@pytest.fixture(params=["memory", "sqlite"])
def registry(request, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "_JOBS", {})
    monkeypatch.setattr(service, "_CANCEL_SIGNALS", {})
    monkeypatch.setattr(service, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, "write_audit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(persistent_state, "enabled", lambda: request.param == "sqlite")
    engine = None
    if request.param == "sqlite":
        engine = create_engine(f"sqlite:///{tmp_path / 'v3-stop.sqlite'}", connect_args={"check_same_thread": False})
        database.Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    yield
    if engine is not None:
        engine.dispose()


def create_job(client="synthetic-client", entity="PL"):
    body = {"entity_code": entity, "as_of": "2026-08-31", "preview": True}
    return jobs.create_order_logic_v3_job(client, body), body


@pytest.mark.parametrize("status", ["queued", "running"])
def test_stop_is_idempotent_and_rejects_late_completion(registry, status):
    job_id, _ = create_job()
    jobs.update_order_logic_v3_job(job_id, status=status)
    stopped = service.cancel_order_logic_v3_job(job_id, "synthetic-client", "PL")
    assert stopped["status"] == "cancelled"
    assert stopped["status_code"] == 499
    assert service.cancel_order_logic_v3_job(job_id, "synthetic-client", "PL") == stopped
    for late_status in ["running", "succeeded", "failed"]:
        jobs.update_order_logic_v3_job(job_id, status=late_status, result={"synthetic": True}, error="late failure")
        assert jobs.get_order_logic_v3_job(job_id) == stopped
    assert "result" not in stopped


@pytest.mark.parametrize("status", ["succeeded", "failed"])
def test_stop_preserves_already_finished_jobs(registry, status):
    job_id, _ = create_job()
    jobs.update_order_logic_v3_job(job_id, status=status, result={"synthetic": True})
    original = jobs.get_order_logic_v3_job(job_id)
    assert service.cancel_order_logic_v3_job(job_id, "synthetic-client", "PL") == original


def test_stop_checks_owner_entity_and_missing_job(registry):
    job_id, _ = create_job()
    for client, entity in [("someone-else", "PL"), ("synthetic-client", "HQ")]:
        with pytest.raises(HTTPException) as caught:
            service.cancel_order_logic_v3_job(job_id, client, entity)
        assert caught.value.status_code == 403
        assert jobs.get_order_logic_v3_job(job_id)["status"] == "queued"
    with pytest.raises(HTTPException) as caught:
        service.cancel_order_logic_v3_job("missing", "synthetic-client", "PL")
    assert caught.value.status_code == 404


def test_only_one_worker_can_claim_a_v3_job(registry):
    job_id, _ = create_job()

    assert jobs.claim_order_logic_v3_job(job_id) is True
    assert jobs.claim_order_logic_v3_job(job_id) is False
    assert jobs.get_order_logic_v3_job(job_id)["status"] == "running"


def test_polling_expires_an_orphaned_v3_job(registry, monkeypatch):
    job_id, _ = create_job()
    jobs.update_order_logic_v3_job(job_id, status="running")
    monkeypatch.setattr(jobs, "ANALYSIS_JOB_STALE_SECONDS", -1)

    job = jobs.get_order_logic_v3_job(job_id)

    assert job["status"] == "failed"
    assert job["status_code"] == 504


def test_stop_before_worker_start_skips_source(registry, monkeypatch):
    job_id, body = create_job()
    service.cancel_order_logic_v3_job(job_id, "synthetic-client", "PL")
    monkeypatch.setattr(service, "build_order_logic_v3_source", lambda **kwargs: pytest.fail("Cancelled work must not fetch CMS."))
    asyncio.run(service.run_order_logic_v3_job(job_id, "synthetic-client", body))
    assert jobs.get_order_logic_v3_job(job_id)["status"] == "cancelled"


def test_stop_during_source_prevents_calculation_and_late_failure(registry, monkeypatch):
    job_id, body = create_job()
    started, release = Event(), Event()

    def source(**kwargs):
        started.set()
        assert release.wait(5)
        return [], {"snapshot_id": "synthetic", "fetched_at": "2026-08-31T00:00:00Z"}

    monkeypatch.setattr(service, "build_order_logic_v3_source", source)
    monkeypatch.setattr(service, "build_order_logic_v3_calculation_result", lambda **kwargs: pytest.fail("Cancelled source must not begin calculation."))

    async def scenario():
        task = asyncio.create_task(service.run_order_logic_v3_job(job_id, "synthetic-client", body))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            stopped = await asyncio.to_thread(service.cancel_order_logic_v3_job, job_id, "synthetic-client", "PL")
            assert stopped["status"] == "cancelled"
        finally:
            release.set()
        await asyncio.wait_for(task, 5)

    asyncio.run(scenario())
    assert jobs.get_order_logic_v3_job(job_id)["status"] == "cancelled"
    assert "result" not in jobs.get_order_logic_v3_job(job_id)
    assert job_id not in service._CANCEL_SIGNALS


@pytest.mark.parametrize("other_worker", [False, True])
def test_stop_during_calculation_keeps_event_loop_responsive(registry, monkeypatch, other_worker):
    job_id, body = create_job()
    started = Event()
    monkeypatch.setattr(service, "build_order_logic_v3_source", lambda **kwargs: ([], {"snapshot_id": "synthetic", "fetched_at": "2026-08-31T00:00:00Z"}))

    def calculate(*, check_cancelled, **kwargs):
        started.set()
        deadline = monotonic() + 5
        while monotonic() < deadline:
            check_cancelled()
            sleep(0.005)
        pytest.fail("The worker did not observe cancellation.")

    monkeypatch.setattr(service, "build_order_logic_v3_calculation_result", calculate)

    async def scenario():
        task = asyncio.create_task(service.run_order_logic_v3_job(job_id, "synthetic-client", body))
        assert await asyncio.to_thread(started.wait, 5)
        if other_worker:
            # The endpoint process cannot access the original worker's Event.
            service._CANCEL_SIGNALS.pop(job_id, None)
        stopped = await asyncio.to_thread(service.cancel_order_logic_v3_job, job_id, "synthetic-client", "PL")
        assert stopped["status"] == "cancelled"
        await asyncio.wait_for(task, 5)

    asyncio.run(scenario())
    job = jobs.get_order_logic_v3_job(job_id)
    assert job["status"] == "cancelled"
    assert "result" not in job


@pytest.mark.parametrize("inventory_error", [None, "Synthetic inventory error"])
def test_calculation_loop_checks_stop_between_skus(monkeypatch, inventory_error):
    processed = []
    checks = 0
    source = SimpleNamespace(
        sku_code="SYNTHETIC", season_factor_blocking_reason_code="TEST",
        season_factor_blocking_message="Synthetic test",
        inventory_validation_error=inventory_error, inventory_warnings=(),
        cash_transport_mode="RAIL", shortage_transport_mode="SEA",
    )

    def check():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise service._OrderLogicV3JobCancelled()

    def blocked(row, **kwargs):
        processed.append(row.sku_code)
        return {"calculable": False}

    monkeypatch.setattr(service, "_blocked_row", blocked)
    with pytest.raises(service._OrderLogicV3JobCancelled):
        service.build_order_logic_v3_calculation_result(
            job_id="synthetic", as_of="2026-08-31", entity_code="PL",
            parameters=textbook_candidate_parameters(logic_version=service.LOGIC_VERSION),
            sku_inputs=[source, source], source_snapshot_id="synthetic",
            source_fetched_at="2026-08-31T00:00:00Z", check_cancelled=check,
        )
    assert processed == ["SYNTHETIC"]


def test_delete_endpoint_returns_only_job_identity_and_status(registry):
    app = FastAPI()

    @app.middleware("http")
    async def synthetic_auth(request: Request, call_next):
        request.state.current_user = SimpleNamespace(username=request.headers.get("x-test-user", "synthetic-user"))
        request.state.entity_code = request.headers.get("x-entity-code", "PL")
        return await call_next(request)

    app.include_router(routes.router)
    job_id, _ = create_job(client="synthetic-user__PL__synthetic-browser")
    headers = {"X-Client-Id": "synthetic-browser", "X-Entity-Code": "PL"}
    with TestClient(app) as client:
        assert client.delete(f"/api/order-logic-v3/jobs/{job_id}", headers={**headers, "X-Test-User": "someone-else"}).status_code == 403
        assert client.delete(f"/api/order-logic-v3/jobs/{job_id}", headers={**headers, "X-Entity-Code": "HQ"}).status_code == 403
        response = client.delete(f"/api/order-logic-v3/jobs/{job_id}", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"job_id": job_id, "status": "cancelled"}
        assert client.get(f"/api/order-logic-v3/jobs/{job_id}", headers=headers).json()["status"] == "cancelled"
