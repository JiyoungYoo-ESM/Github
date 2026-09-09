"""HTTP-level contract tests for POST /api/analyze.

Unit tests for core/backend logic already cover calculation correctness, but the
2026-07-22 large-upload incident (server unresponsive for 13+ minutes, see
OPERATIONS.md 3-3) went undetected by all 241 of them because none of them exercise
the actual HTTP upload path. These tests pin the observable contract of that path
(status codes for the documented limits in OPERATIONS.md 3-1, plus one genuine
end-to-end success) so a regression in request handling shows up in CI instead of
in production.
"""

from __future__ import annotations

from io import BytesIO

import openpyxl
import pytest
from fastapi.testclient import TestClient

import backend.routers.auth as auth_router
import backend.services.auth as auth_service
import backend.auth.user_store as user_store_module
import backend.services.concurrency as concurrency_module
import backend.services.upload_storage as upload_storage_module
from backend.main import app
from core import loaders as loaders_mod
from tests.auth_helpers import TEST_PASSWORDS, TestUserStore

HEADERS = {"X-Requested-With": "fetch", "X-Entity-Code": "PL"}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(user_store_module, "_user_store", TestUserStore())
    auth_service.reset_sessions()
    auth_router._login_limiter.reset()
    test_client = TestClient(app)
    login = test_client.post(
        "/api/auth/login",
        headers=HEADERS,
        json={"id": "adminmaster", "password": TEST_PASSWORDS["adminmaster"]},
    )
    assert login.status_code == 200
    return test_client


def _eu_stock_xlsx_bytes() -> bytes:
    df = loaders_mod.sample_eu_stock()
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(list(df.columns))
    for row in df.itertuples(index=False):
        sheet.append(list(row))
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_analyze_rejects_when_no_files(client: TestClient) -> None:
    response = client.post("/api/analyze", headers=HEADERS, files=[])
    assert response.status_code in (400, 422)


def test_analyze_rejects_invalid_excel_signature(client: TestClient) -> None:
    files = [("files", ("fake.xlsx", b"this is not a real xlsx file", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    response = client.post("/api/analyze", headers=HEADERS, files=files)
    assert response.status_code == 400
    assert "형식" in response.json()["detail"]


def test_analyze_rejects_duplicate_roles(client: TestClient) -> None:
    payload = _eu_stock_xlsx_bytes()
    files = [
        ("files", ("a.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
        ("files", ("b.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
    ]
    response = client.post("/api/analyze", headers=HEADERS, files=files, data={"roles": ["eu_stock", "eu_stock"]})
    assert response.status_code == 400
    assert "중복" in response.json()["detail"]


def test_analyze_rejects_file_over_size_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # 실제 100MB 파일을 만들지 않고 한도를 낮춰서 같은 코드 경로(413)를 재현한다.
    monkeypatch.setattr(upload_storage_module, "MAX_UPLOAD_FILE_BYTES", 100)
    payload = _eu_stock_xlsx_bytes()
    assert len(payload) > 100
    files = [("files", ("big.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    response = client.post("/api/analyze", headers=HEADERS, files=files, data={"roles": ["eu_stock"]})
    assert response.status_code == 413


def test_analyze_rejects_when_concurrency_limit_reached(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(concurrency_module, "MAX_CONCURRENT_ANALYSES", 0)
    payload = _eu_stock_xlsx_bytes()
    files = [("files", ("eu_stock.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    response = client.post("/api/analyze", headers=HEADERS, files=files, data={"roles": ["eu_stock"]})
    assert response.status_code == 429
    assert "동시 분석" in response.json()["detail"]


def test_analyze_succeeds_with_single_role_file(client: TestClient) -> None:
    payload = _eu_stock_xlsx_bytes()
    files = [("files", ("eu_stock.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))]
    response = client.post("/api/analyze", headers=HEADERS, files=files, data={"roles": ["eu_stock"]})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["job_id"]
    assert body["download_url"].startswith(f"/api/download/{body['job_id']}")
    assert "tables" in body
    assert body["file_mapping"]
