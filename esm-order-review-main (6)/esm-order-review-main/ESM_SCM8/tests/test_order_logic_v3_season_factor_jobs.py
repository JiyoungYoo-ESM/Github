from types import SimpleNamespace
import threading
import time

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from backend.services import order_logic_v3_season_factor_jobs as jobs
from backend.services import order_logic_v3_season_factor_scheduler as scheduler
from backend.services import order_logic_v3_ledger as ledger


@pytest.fixture
def queued(monkeypatch):
    work = []
    monkeypatch.setattr(jobs, "_JOBS", {})
    monkeypatch.setattr(jobs, "_POOL", SimpleNamespace(submit=lambda *args: work.append(args)))
    monkeypatch.setattr(jobs, "write_audit_event", lambda *_, **__: None)
    return work


def test_repeated_and_scheduled_requests_share_one_unfinished_job(queued):
    first = jobs.queue_refresh(entity_code="PL", as_of="2026-09-07", trigger="scheduled")
    second = jobs.queue_refresh(entity_code="PL", as_of="2026-09-07")
    assert first["job_id"] == second["job_id"]
    assert len(queued) == 1
    jobs.queue_refresh(entity_code="USA", as_of="2026-09-07")
    assert len(queued) == 2
    jobs._update("PL", first["job_id"], status="running")
    assert jobs.refresh_status("USA")["waiting_for_entity"] == "PL"
    assert jobs.refresh_status("HQ") == {"entity_code": "HQ", "status": "idle"}


def test_progress_completion_and_failure_are_visible_without_raw_data(queued, monkeypatch):
    def refresh(**kwargs):
        kwargs["progress"]({"stage": "fetching", "month": "2024-09", "completed_months": 0, "total_months": 24})
        assert jobs.refresh_status("PL")["month"] == "2024-09"
        return {"status": "active", "version": "synthetic", "validation": {"passed": True}, "window_end": "2026-08-31"}
    monkeypatch.setattr(jobs, "refresh_order_logic_v3_season_factors", refresh)
    first = jobs.queue_refresh(entity_code="PL", as_of="2026-09-07")
    function, *args = queued.pop()
    function(*args)
    assert jobs.refresh_status("PL")["status"] == "succeeded"
    second = jobs.queue_refresh(entity_code="PL", as_of="2026-09-07")
    assert second["job_id"] != first["job_id"]
    def failed(**kwargs):
        raise ValueError("Synthetic internal detail")
    monkeypatch.setattr(jobs, "refresh_order_logic_v3_season_factors", failed)
    function, *args = queued.pop()
    function(*args)
    status = jobs.refresh_status("PL")
    assert status["status"] == "failed"
    assert "Synthetic internal detail" not in status["error"]
    assert "ValueError" in status["error"]


def test_http_refresh_returns_202_before_work_and_scopes_status_to_entity(queued, monkeypatch):
    from backend.routers import order_logic_v3 as routes
    monkeypatch.setattr(routes, "write_audit_event", lambda *_, **__: None)
    admin = True
    entity = "PL"
    app = FastAPI()
    @app.middleware("http")
    async def state(request: Request, call_next):
        request.state.entity_code = entity
        request.state.current_user = SimpleNamespace(is_admin=admin)
        return await call_next(request)
    app.include_router(routes.router)
    with TestClient(app) as client:
        response = client.post("/api/order-logic-v3/season-factors/refresh")
        assert response.status_code == 202
        assert response.json()["status"] == "queued"
        assert len(queued) == 1
        assert client.get("/api/order-logic-v3/season-factors/refresh/status").json()["job_id"] == response.json()["job_id"]
        entity = "HQ"
        assert client.get("/api/order-logic-v3/season-factors/refresh/status").json()["status"] == "idle"
        admin = False
        assert client.post("/api/order-logic-v3/season-factors/refresh").status_code == 403
        assert len(queued) == 1


def test_ledger_validation_failure_reports_safe_reason_and_month(queued, monkeypatch):
    reason = "수불 API의 페이지 건수와 전체 건수가 맞지 않습니다. 다시 조회해 주세요."

    def failed(**kwargs):
        kwargs["progress"]({"stage": "fetching", "month": "2024-09"})
        raise ledger.LedgerSourceError(reason)

    monkeypatch.setattr(jobs, "refresh_order_logic_v3_season_factors", failed)
    jobs.queue_refresh(entity_code="USA", as_of="2026-09-08")
    function, *args = queued.pop()
    function(*args)
    status = jobs.refresh_status("USA")
    assert status["status"] == "failed"
    assert "2024-09" in status["error"]
    assert reason in status["error"]
    assert "기존 버전은 유지" in status["error"]
    assert "LedgerSourceError" not in status["error"]
    assert jobs.refresh_status("PL")["status"] == "idle"


def test_scheduler_resumes_migration_cache_and_queues_without_waiting(queued, monkeypatch):
    monkeypatch.setattr(scheduler, "refresh_due_for_entity", lambda *_: True)
    monkeypatch.setattr(scheduler, "write_audit_event", lambda *_, **__: None)
    monkeypatch.setattr(scheduler, "load_latest_candidate", lambda entity: {
        "source_request": {"demand_policy": ledger.LEDGER_POLICY if entity == "USA" else None}
    })
    result = scheduler.refresh_due_season_factors_once()
    assert {value["status"] for value in result["entities"].values()} == {"queued"}
    assert [args[-1] for args in queued] == [False, False, True]
    scheduler.refresh_due_season_factors_once()
    assert len(queued) == 3


def test_real_worker_does_not_block_status_requests(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    started, release = threading.Event(), threading.Event()
    pool = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(jobs, "_POOL", pool)
    monkeypatch.setattr(jobs, "_JOBS", {})
    monkeypatch.setattr(jobs, "write_audit_event", lambda *_, **__: None)
    def slow(**kwargs):
        started.set()
        assert release.wait(timeout=5)
        return {"status": "active", "validation": {"passed": True}, "version": "synthetic"}
    monkeypatch.setattr(jobs, "refresh_order_logic_v3_season_factors", slow)
    try:
        first = jobs.queue_refresh(entity_code="PL", as_of="2026-09-07")
        assert started.wait(timeout=2)
        before = time.monotonic()
        assert jobs.refresh_status("PL")["status"] == "running"
        assert jobs.queue_refresh(entity_code="PL", as_of="2026-09-07")["job_id"] == first["job_id"]
        assert time.monotonic() - before < 1
    finally:
        release.set()
        pool.shutdown(wait=True)
    assert jobs.refresh_status("PL")["status"] == "succeeded"
