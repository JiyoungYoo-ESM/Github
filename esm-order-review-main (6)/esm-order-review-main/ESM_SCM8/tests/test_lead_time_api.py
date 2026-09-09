from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi.testclient import TestClient

import backend.auth.user_store as user_store_module
import backend.routers.auth as auth_router
import backend.services.auth as auth_service
from backend.entities import ENTITY_CODES
from backend.main import app
from tests.auth_helpers import TEST_ALLOWED_ENTITIES, TEST_PASSWORDS, TestUserStore
from tests.test_lead_times import EXPECTED_LEAD_TIMES


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(user_store_module, "_user_store", TestUserStore())
    auth_service.reset_sessions()
    auth_router._login_limiter.reset()
    return TestClient(app)


def _login(client: TestClient, username: str = "adminmaster"):
    return client.post(
        "/api/auth/login",
        json={"id": username, "password": TEST_PASSWORDS[username]},
    )


def _field(value: Mapping[str, object], *names: str) -> object | None:
    for name in names:
        if name in value:
            return value[name]
    return None


def _reference_payload(response) -> Mapping[str, object]:
    payload = response.json()
    for _ in range(2):
        assert isinstance(payload, Mapping), payload
        if _field(
            payload,
            "methods",
            "lead_times",
            "leadTimes",
            "transport_methods",
            "transportMethods",
        ) is not None:
            return payload
        wrapped = _field(payload, "data", "result")
        if not isinstance(wrapped, Mapping):
            break
        payload = wrapped
    assert isinstance(payload, Mapping)
    return payload


def _normalize_api_methods(payload: Mapping[str, object], entity_code: str) -> dict[str, int]:
    raw = _field(
        payload,
        "methods",
        "lead_times",
        "leadTimes",
        "transport_methods",
        "transportMethods",
    )
    assert raw is not None, payload

    if isinstance(raw, Mapping):
        entries = [(str(code), method) for code, method in raw.items()]
    else:
        assert isinstance(raw, list), raw
        entries = [(None, method) for method in raw]

    normalized: dict[str, int] = {}
    for fallback_code, method in entries:
        if isinstance(method, int) and not isinstance(method, bool):
            code = fallback_code
            days = method
        else:
            assert isinstance(method, Mapping), method
            code = _field(method, "code", "transport_code", "transportCode")
            days = _field(method, "lead_time_days", "leadTimeDays", "days")
            if code is None:
                code = fallback_code

        assert isinstance(code, str) and code, f"Missing transport code in {method!r}"
        assert type(days) is int, f"{entity_code}/{code} days must be a JSON integer"
        assert code not in normalized, f"Duplicate transport code for {entity_code}: {code}"
        normalized[code] = days

    return normalized


@pytest.mark.parametrize(
    "entity_code,expected",
    [
        pytest.param(entity_code, expected, id=entity_code)
        for entity_code, expected in EXPECTED_LEAD_TIMES.items()
    ],
)
def test_reference_api_returns_exact_lead_times_for_every_entity(
    client: TestClient,
    entity_code: str,
    expected: dict[str, int],
):
    assert _login(client).status_code == 200

    response = client.get(
        "/api/reference/lead-times",
        params={"entity_code": entity_code},
    )

    assert response.status_code == 200, response.text
    payload = _reference_payload(response)
    assert _field(payload, "entity_code", "entityCode") == entity_code
    assert _field(payload, "effective_date", "effectiveDate") == "2026-07-23"
    assert _normalize_api_methods(payload, entity_code) == expected


@pytest.mark.parametrize(
    "username,entity_code,expected",
    [
        pytest.param(
            username,
            entity_code,
            200 if entity_code in allowed_entities else 403,
            id=f"{username}-{entity_code}",
        )
        for username, allowed_entities in TEST_ALLOWED_ENTITIES.items()
        for entity_code in ENTITY_CODES
    ],
)
def test_reference_api_enforces_full_account_entity_permission_matrix(
    client: TestClient,
    username: str,
    entity_code: str,
    expected: int,
):
    assert _login(client, username).status_code == 200

    response = client.get(
        "/api/reference/lead-times",
        params={"entity_code": entity_code},
    )

    assert response.status_code == expected, response.text


@pytest.mark.parametrize(
    "username,entity_code",
    [
        ("my_team", "MY"),
        ("vn_team", "VN"),
    ],
)
def test_allowed_entity_returns_lead_time_config_even_without_entity_data_integration(
    client: TestClient,
    username: str,
    entity_code: str,
):
    assert _login(client, username).status_code == 200

    response = client.get(
        "/api/reference/lead-times",
        params={"entity_code": entity_code},
    )

    assert response.status_code == 200, response.text
    payload = _reference_payload(response)
    assert _normalize_api_methods(payload, entity_code) == EXPECTED_LEAD_TIMES[entity_code]


def test_reference_api_requires_authentication(client: TestClient):
    response = client.get(
        "/api/reference/lead-times",
        params={"entity_code": "PL"},
    )

    assert response.status_code == 401
