"""HTTP delivery must preserve all rows, ownership and monetary permissions."""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.routers import order_logic_v3 as routes
from backend.services import order_logic_v3_jobs as jobs, persistent_state
from backend.services import object_storage, order_logic_v3_result_store as result_store


@pytest.fixture
def delivery(monkeypatch):
    monkeypatch.setattr(persistent_state, "enabled", lambda: False)
    monkeypatch.setattr(jobs, "_JOBS", {})
    app = FastAPI()

    @app.middleware("http")
    async def auth(request: Request, call_next):
        request.state.current_user = SimpleNamespace(username=request.headers.get("x-test-user", "adminmaster"))
        request.state.entity_code = request.headers.get("x-entity-code", "HQ")
        return await call_next(request)

    app.include_router(routes.router)
    with TestClient(app) as client:
        yield client


def completed_job(username="adminmaster", count=537):
    job_id = jobs.create_order_logic_v3_job(f"{username}__HQ__delivery", {"entity_code": "HQ"})
    def rows(size, factor):
        return [{"sku_code": f"SYNTHETIC-{index}", "raw_order_quantity": index * factor,
                 "order_amount_krw": index * factor * 10, "unit_price_krw": 10,
                 "nullable": None, "history": [0, index]} for index in range(size)]
    result = {
        "job_id": job_id, "entity_code": "HQ", "status": "success", "source_snapshot_id": "synthetic",
        "rows": rows(count, 1), "scenarios": {
            "CASH": {"policy": "keep-scenario-metadata", "rows": rows(max(count - 1, 0), 2)},
            "SHORTAGE": {"rows": rows(count, 3)},
        }, "summary": {"total_sku_count": count}, "audit": {"preserve": [1, 2, 3]},
    }
    jobs.update_order_logic_v3_job(job_id, status="succeeded", result=result)
    return job_id, result


HEADERS = {"X-Client-Id": "delivery", "X-Entity-Code": "HQ"}


@pytest.mark.parametrize("username", ["adminmaster", "eu_manager"])
@pytest.mark.parametrize("count", [0, 537])
def test_pages_reconstruct_every_field_and_preserve_permissions(delivery, username, count):
    job_id, result = completed_job(username, count)
    original = deepcopy(result)
    headers = {**HEADERS, "X-Test-User": username}
    status = delivery.get(f"/api/order-logic-v3/jobs/{job_id}?include_result=false", headers=headers)
    assert status.status_code == 200 and len(status.content) < 500
    assert "result" not in status.json() and status.json()["result_delivery"] == "paged-v1"
    offset = 0
    received = None
    while True:
        response = delivery.get(f"/api/order-logic-v3/jobs/{job_id}/result?offset={offset}", headers=headers)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        page = response.json()
        assert page["offset"] == offset and len(page["rows"]) <= 250
        if received is None:
            received = page["result"]
        else:
            assert "result" not in page
        received["rows"].extend(page["rows"])
        for scenario in ("CASH", "SHORTAGE"):
            received["scenarios"][scenario]["rows"].extend(page["scenarios"][scenario]["rows"])
        if page["next_offset"] is None:
            break
        offset = page["next_offset"]
    assert received == original
    assert result == original


def test_status_does_not_touch_result_and_page_rejects_other_scopes(delivery):
    job_id, _ = completed_job()
    for suffix in ("?include_result=false", "/result"):
        for changed in ({"X-Test-User": "another"}, {"X-Client-Id": "another"}, {"X-Entity-Code": "PL"}):
            assert delivery.get(f"/api/order-logic-v3/jobs/{job_id}{suffix}", headers={**HEADERS, **changed}).status_code == 403
    class Uncopyable:
        def __deepcopy__(self, memo):
            raise AssertionError("Status polling must never copy the result")
    jobs.update_order_logic_v3_job(job_id, result=Uncopyable())
    assert delivery.get(f"/api/order-logic-v3/jobs/{job_id}?include_result=false", headers=HEADERS).status_code == 200


def test_page_bounds_and_unfinished_jobs(delivery):
    job_id, _ = completed_job()
    for query in ("offset=-1", "offset=9999", "limit=0", "limit=251"):
        assert delivery.get(f"/api/order-logic-v3/jobs/{job_id}/result?{query}", headers=HEADERS).status_code == 422
    jobs.update_order_logic_v3_job(job_id, status="running")
    assert delivery.get(f"/api/order-logic-v3/jobs/{job_id}/result", headers=HEADERS).status_code == 409
    assert delivery.get("/api/order-logic-v3/jobs/missing?include_result=false", headers=HEADERS).status_code == 404


def test_identical_primary_array_is_sent_only_once(delivery):
    job_id, result = completed_job()
    result["rows"] = result["scenarios"]["SHORTAGE"]["rows"]
    page = delivery.get(f"/api/order-logic-v3/jobs/{job_id}/result", headers=HEADERS).json()
    assert page["row_alias"] == "SHORTAGE" and page["rows"] == []
    assert page["counts"]["rows"] == page["counts"]["SHORTAGE"] == 537
    assert page["scenarios"]["SHORTAGE"]["rows"] == result["rows"][:250]


def test_database_metadata_query_excludes_result(monkeypatch):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from backend import database
    from backend.models.persistence import AnalysisJob
    engine = create_engine("sqlite://")
    AnalysisJob.__table__.create(engine)
    factory = sessionmaker(engine)
    with factory() as session:
        session.add(AnalysisJob(job_id="synthetic", kind=jobs.JOB_KIND, status="succeeded", client_id="c",
                                request_payload={"entity_code": "HQ"}, result_payload={"secret": "not-read"}))
        session.commit()
    queries = []
    event.listen(engine, "before_cursor_execute", lambda conn, cursor, statement, *args: queries.append(statement))
    monkeypatch.setattr(persistent_state, "enabled", lambda: True)
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    metadata = jobs.get_order_logic_v3_job_metadata("synthetic")
    assert metadata["status"] == "succeeded" and "result" not in metadata
    assert all("result_payload" not in statement for statement in queries)
    engine.dispose()


def test_local_completed_job_and_paged_result_survive_worker_restart(monkeypatch, tmp_path):
    monkeypatch.setattr(persistent_state, "enabled", lambda: False)
    monkeypatch.setattr(object_storage, "enabled", lambda: False)
    monkeypatch.setattr(jobs, "LOCAL_COMPLETED_JOB_ROOT", tmp_path / "completed-jobs")
    monkeypatch.setattr(result_store, "LOCAL_RESULT_ROOT", tmp_path / "results")
    monkeypatch.setattr(jobs, "_JOBS", {})
    job_id = jobs.create_order_logic_v3_job("browser__HQ__restart", {"entity_code": "HQ"})
    rows = [{"sku_code": f"RESTORE-{index}", "raw_order_quantity": index} for index in range(501)]
    result = {
        "job_id": job_id, "entity_code": "HQ", "status": "success",
        "source_snapshot_id": "restart-snapshot", "rows": rows,
        "scenarios": {"CASH": {"rows": rows}, "SHORTAGE": {"rows": rows}},
    }
    stored = result_store.store_result(job_id, result)
    jobs.update_order_logic_v3_job(job_id, status="succeeded", status_code=200, result=stored)

    monkeypatch.setattr(jobs, "_JOBS", {})  # simulate the uvicorn worker process restarting
    restored = jobs.get_order_logic_v3_job(job_id)

    assert restored is not None and restored["status"] == "succeeded"
    assert result_store.is_paged_result(restored["result"])
    first_page = result_store.result_page(job_id, restored["result"], offset=0, limit=250)
    assert first_page["scenarios"]["SHORTAGE"]["rows"] == rows[:250]
