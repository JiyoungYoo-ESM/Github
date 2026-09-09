"""Cross-router API integration checks for the deployed application contract."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import backend.routers.auth as auth_router
import backend.services.auth as auth_service
import backend.auth.user_store as user_store_module
from backend.main import app
from tests.auth_helpers import TEST_ALLOWED_ENTITIES, TEST_PASSWORDS, TestUserStore


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(user_store_module, "_user_store", TestUserStore())
    auth_service.reset_sessions()
    auth_router._login_limiter.reset()
    return TestClient(app)


def test_health_auth_metadata_and_error_contract_share_one_http_stack(client: TestClient) -> None:
    request_id = "integration-flow-001"
    # X-Requested-With: 실제 프론트(apiFetch)가 항상 붙이는 CSRF 헤더 — 보호 라우트의
    # 상태 변경 요청에 필요하다.
    headers = {"X-Request-Id": request_id, "X-Requested-With": "fetch", "X-Entity-Code": "PL"}

    health_response = client.get("/api/health", headers=headers)
    assert health_response.status_code == 200
    assert health_response.headers["X-Request-Id"] == request_id
    assert float(health_response.headers["X-Response-Time-Ms"]) >= 0
    health = health_response.json()
    assert health["status"] in {"ok", "degraded"}
    assert health["service"] == "ESM SCM Backend"
    assert health["limits"]["max_upload_files"] > 0
    assert health["requests"]["scope"] == "process_local"
    assert health["requests"]["in_flight"] >= 1

    client_measure = client.post(
        "/api/health/client-performance",
        headers=headers,
        json={"name": "workspace.global-search.index", "duration_ms": 24.5, "screen": "/order-analysis"},
    )
    assert client_measure.status_code == 202
    assert client_measure.json() == {"status": "accepted"}
    assert client.post(
        "/api/health/client-performance",
        headers=headers,
        json={"name": "untrusted.metric", "duration_ms": 24.5},
    ).status_code == 422

    live_response = client.get("/api/health/live", headers=headers)
    assert live_response.status_code == 200
    assert live_response.json()["status"] == "ok"

    ready_response = client.get("/api/health/ready", headers=headers)
    assert ready_response.status_code == 503
    assert ready_response.json()["checks"]["database"] == "not_configured"

    login_response = client.post(
        "/api/auth/login",
        headers=headers,
        json={"id": "adminmaster", "password": TEST_PASSWORDS["adminmaster"]},
    )
    assert login_response.status_code == 200
    assert login_response.headers["X-Request-Id"] == request_id
    assert login_response.cookies.get("s2_session")

    me_response = client.get("/api/auth/me", headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "adminmaster"
    assert me_response.json()["allowed_entities"] == list(TEST_ALLOWED_ENTITIES["adminmaster"])

    options_response = client.get("/api/category-corrections/options", headers=headers)
    assert options_response.status_code == 200
    options = options_response.json()
    assert options["category1"]
    assert options["category2ByCategory1"]

    invalid_response = client.post(
        "/api/analyze/cms",
        headers=headers,
        json={"as_of": "not-a-date"},
    )
    assert invalid_response.status_code == 422
    assert invalid_response.headers["X-Request-Id"] == request_id
    error = invalid_response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["status"] == 422
    assert error["request_id"] == request_id
    assert error["details"]

    logout_response = client.post("/api/auth/logout", headers=headers)
    assert logout_response.status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401
