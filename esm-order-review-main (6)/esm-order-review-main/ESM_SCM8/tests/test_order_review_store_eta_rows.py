"""세션 복구용으로 저장하는 발주검토 스냅샷이 도착 캘린더까지 함께 보관하는지 검증."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.services import order_review_store, persistent_state


ORDER_ROWS = [{"상품코드": "SKU-A", "미입고 수량": 100}, {"상품코드": "SKU-B", "미입고 수량": 0}]
ETA_ROWS = [
    {"상품코드": "SKU-A", "도착일": "2026-08-01", "수량": 500, "운송수단": "해운", "B/L": "BL-1"},
    {"상품코드": "SKU-A", "도착일": "2026-08-20", "수량": 300, "운송수단": "항공", "B/L": "BL-2"},
]


@pytest.fixture()
def file_backed_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(persistent_state, "enabled", lambda: False)
    monkeypatch.setattr(order_review_store, "LATEST_ORDER_REVIEW_DIR", tmp_path)
    return tmp_path


def test_saved_snapshot_keeps_arrival_calendar_rows(file_backed_store):
    """발주검토 행에는 SKU별 최초 ETA 한 건만 남아서, 이 표가 없으면 세션을 복구한
    재고공백 화면이 ETA 상세와 타임라인 입고 지점을 그릴 수 없다."""
    result = {
        "tables": {
            "stock_gap_order_review": ORDER_ROWS,
            "stock_gap_eta": ETA_ROWS,
        }
    }

    order_review_store.save_latest_order_review_result("acct__PL", "job-1", result, "cms_api")
    payload = order_review_store.load_latest_order_review_result("acct__PL")

    assert payload is not None
    assert payload["rows"] == ORDER_ROWS
    assert payload["row_count"] == 2
    assert payload["eta_rows"] == ETA_ROWS
    assert payload["eta_row_count"] == 2


def test_snapshot_without_arrival_calendar_stays_loadable(file_backed_store):
    """엑셀 복구 등 도착 캘린더가 없는 경로도 빈 목록으로 정상 저장돼야 한다."""
    order_review_store.save_latest_order_review_result(
        "acct__PL", "job-2", {"tables": {"order_review": ORDER_ROWS}}, "latest_output_excel"
    )
    payload = order_review_store.load_latest_order_review_result("acct__PL")

    assert payload is not None
    assert payload["rows"] == ORDER_ROWS
    assert payload["eta_rows"] == []
    assert payload["eta_row_count"] == 0


def test_eta_rows_extraction_ignores_malformed_tables():
    assert order_review_store.order_review_eta_rows_from_result({}) == []
    assert order_review_store.order_review_eta_rows_from_result({"tables": None}) == []
    assert order_review_store.order_review_eta_rows_from_result({"tables": {"stock_gap_eta": "not-a-list"}}) == []
    assert order_review_store.order_review_eta_rows_from_result({"tables": {"stock_gap_eta": ETA_ROWS}}) == ETA_ROWS
