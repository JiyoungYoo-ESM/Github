"""Account, session, CSRF and entity-authorization integration tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import backend.auth.user_store as user_store_module
import backend.routers.auth as auth_router
import backend.services.auth as auth_service
from backend.main import app
from backend.entities import ENTITY_CODES
from tests.auth_helpers import TEST_ALLOWED_ENTITIES, TEST_PASSWORDS, TestUserStore


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(user_store_module, "_user_store", TestUserStore())
    auth_service.reset_sessions()
    auth_router._login_limiter.reset()
    return TestClient(app)


def login(client: TestClient, username: str = "adminmaster"):
    return client.post(
        "/api/auth/login",
        json={"id": username, "password": TEST_PASSWORDS[username]},
    )


def test_login_rejects_wrong_or_unknown_credentials(client: TestClient):
    assert client.post("/api/auth/login", json={"id": "adminmaster", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"id": "missing", "password": "wrong"}).status_code == 401


def test_login_rejects_empty_credentials(client: TestClient):
    assert client.post("/api/auth/login", json={"id": "", "password": ""}).status_code == 401


def test_cross_site_login_and_authenticated_writes_are_rejected(client: TestClient):
    blocked = {
        "Origin": "https://attacker.example",
        "Sec-Fetch-Site": "cross-site",
        "X-Requested-With": "fetch",
    }
    assert client.post(
        "/api/auth/login",
        headers=blocked,
        json={"id": "adminmaster", "password": TEST_PASSWORDS["adminmaster"]},
    ).status_code == 403

    assert login(client).status_code == 200
    response = client.post("/api/category-corrections", headers={**blocked, "X-Entity-Code": "PL"}, json={})
    assert response.status_code == 403


def test_cors_does_not_allow_unlisted_lan_origins(client: TestClient):
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://192.168.50.50:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 400


def test_me_without_cookie_is_unauthenticated(client: TestClient):
    assert client.get("/api/auth/me").status_code == 401


def test_each_account_logs_in_and_me_returns_only_its_permissions(client: TestClient):
    for username, expected_entities in TEST_ALLOWED_ENTITIES.items():
        auth_service.reset_sessions()
        response = login(client, username)
        assert response.status_code == 200, username
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        payload = me.json()
        assert payload["authenticated"] is True
        assert payload["username"] == username
        assert tuple(payload["allowed_entities"]) == expected_entities
        assert {entity["code"] for entity in payload["entities"]} == set(expected_entities)
        amount_allowed = username in {"adminmaster", "ia"}
        assert payload["permissions"] == {
            "canViewAmountData": amount_allowed,
            "canDownloadAmountData": amount_allowed,
            "canExportAmountReport": amount_allowed,
        }
        assert "password_hash" not in payload


def test_logout_invalidates_session(client: TestClient):
    login(client)
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/category-corrections/options", headers={"X-Entity-Code": "PL"}).status_code == 401


def test_successful_login_rotates_existing_browser_session(client: TestClient):
    assert login(client).status_code == 200
    old_token = client.cookies.get("s2_session")
    assert old_token

    assert login(client).status_code == 200
    assert client.cookies.get("s2_session") != old_token
    client.cookies.set("s2_session", old_token)
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    assert login(client).status_code == 200
    # Far beyond the 30-day session TTL, while remaining a valid gzip timestamp.
    monkeypatch.setattr(auth_service.time, "time", lambda: 4_000_000_000)
    assert client.get("/api/auth/me").status_code == 401


def test_login_trims_id_whitespace(client: TestClient):
    response = client.post(
        "/api/auth/login",
        json={"id": "  adminmaster  ", "password": TEST_PASSWORDS["adminmaster"]},
    )
    assert response.status_code == 200


def test_unknown_session_token_is_rejected(client: TestClient):
    client.cookies.set("s2_session", "not-a-real-token")
    assert client.get("/api/auth/me").status_code == 401


def test_inactive_account_cannot_login(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(user_store_module, "_user_store", TestUserStore(inactive={"bm1"}))
    assert login(client, "bm1").status_code == 401


def test_public_routes_need_no_auth(client: TestClient):
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/health").status_code == 200


def test_data_route_rejects_anonymous_request(client: TestClient):
    response = client.get("/api/category-corrections/options", headers={"X-Entity-Code": "PL"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "username,entity,expected",
    [
        (
            username,
            entity,
            200 if entity in {"HQ", "PL", "USA"} and entity in allowed else 409 if entity in allowed else 403,
        )
        for username, allowed in TEST_ALLOWED_ENTITIES.items()
        for entity in ENTITY_CODES
    ],
)
def test_entity_permission_matrix(client: TestClient, username: str, entity: str, expected: int):
    auth_service.reset_sessions()
    assert login(client, username).status_code == 200
    response = client.get("/api/category-corrections/options", headers={"X-Entity-Code": entity})
    assert response.status_code == expected


def test_invalid_or_missing_entity_is_400(client: TestClient):
    login(client)
    assert client.get("/api/category-corrections/options").status_code == 400
    assert client.get("/api/category-corrections/options", headers={"X-Entity-Code": "INVALID"}).status_code == 400


def test_hq_allows_insight_data_but_blocks_cms_order_analysis(client: TestClient):
    assert login(client).status_code == 200
    response = client.post(
        "/api/analyze/cms/jobs",
        headers={"X-Entity-Code": "HQ", "X-Requested-With": "fetch"},
        json={"as_of": "2026-07-28"},
    )

    assert response.status_code == 409
    assert "판매 분석 API만 연동" in response.json()["error"]["message"]


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/analysis/latest-order-review"),
        ("get", "/api/analyze/cms/jobs/not-a-real-job"),
        ("get", "/api/order-logic-v2/latest"),
    ],
)
def test_sales_team_cannot_access_order_analysis_apis(
    client: TestClient,
    method: str,
    path: str,
):
    assert login(client, "sales_team").status_code == 200

    response = getattr(client, method)(path, headers={"X-Entity-Code": "PL"})

    assert response.status_code == 403
    assert response.json()["error"]["message"] == "발주 분석 접근 권한이 없습니다."


def test_sales_team_keeps_insight_api_access(client: TestClient):
    assert login(client, "sales_team").status_code == 200

    response = client.get(
        "/api/category-corrections/options",
        headers={"X-Entity-Code": "PL"},
    )

    assert response.status_code == 200


def test_download_style_entity_query_is_authorized(client: TestClient):
    login(client, "eu_manager")
    assert client.get("/api/category-corrections/options?entity=PL").status_code == 200
    assert client.get("/api/category-corrections/options?entity=USA").status_code == 403


def test_authenticated_post_without_csrf_header_is_forbidden(client: TestClient):
    login(client)
    headers = {"X-Entity-Code": "PL"}
    assert client.get("/api/category-corrections/options", headers=headers).status_code == 200
    assert client.post("/api/category-corrections", headers=headers, json={}).status_code == 403


def test_login_is_rate_limited(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth_router, "_login_limiter", auth_router.SlidingWindowRateLimiter(max_events=3, window_seconds=300))
    for _ in range(3):
        assert client.post("/api/auth/login", json={"id": "adminmaster", "password": "wrong"}).status_code == 401
    assert login(client).status_code == 429


def test_successful_login_does_not_consume_rate_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth_router, "_login_limiter", auth_router.SlidingWindowRateLimiter(max_events=1, window_seconds=300))

    assert login(client, "adminmaster").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert login(client, "adminmaster").status_code == 200


def test_login_rate_limit_is_scoped_by_account(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth_router, "_login_limiter", auth_router.SlidingWindowRateLimiter(max_events=1, window_seconds=300))

    assert client.post(
        "/api/auth/login",
        json={"id": "adminmaster", "password": "wrong"},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"id": "eu_manager", "password": "wrong"},
    ).status_code == 401
