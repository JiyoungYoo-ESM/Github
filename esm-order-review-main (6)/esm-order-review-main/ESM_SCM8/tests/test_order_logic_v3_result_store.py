from __future__ import annotations

import json

import pytest

from backend.services import object_storage
from backend.services import order_logic_v3_result_store as result_store
from backend.services.order_logic_v3_result_store import (
    OrderLogicV3ResultUnavailable,
    is_paged_result,
    result_page,
    store_result,
)


@pytest.fixture
def fake_objects(monkeypatch):
    objects: dict[str, bytes] = {}
    monkeypatch.setattr(object_storage, "enabled", lambda: True)
    monkeypatch.setattr(
        object_storage,
        "put_bytes",
        lambda value, name, **kwargs: objects.__setitem__(name, value) or name,
    )
    monkeypatch.setattr(object_storage, "get_bytes", lambda name: objects.get(name))
    return objects


def test_large_result_is_compressed_paged_and_reassembled_exactly(fake_objects):
    shortage_rows = [{"sku_code": f"S-{index}", "qty": index} for index in range(275)]
    cash_rows = [{"sku_code": f"C-{index}", "qty": index / 10} for index in range(503)]
    result = {
        "job_id": "order3_synthetic",
        "entity_code": "HQ",
        "source_snapshot_id": "snapshot-1",
        "status": "success",
        "summary": {"preserved": True},
        "rows": shortage_rows,
        "scenarios": {
            "CASH": {"policy": "cash", "rows": cash_rows},
            "SHORTAGE": {"policy": "shortage", "rows": shortage_rows},
        },
    }

    stored = store_result("order3_synthetic", result)

    assert is_paged_result(stored)
    assert len(fake_objects) == 3
    assert len(json.dumps(stored)) < 2_000

    pages = [
        result_page("order3_synthetic", stored, offset=0, limit=250),
        result_page("order3_synthetic", stored, offset=250, limit=250),
        result_page("order3_synthetic", stored, offset=500, limit=250),
    ]
    base = pages[0]["result"]
    assert base["summary"] == {"preserved": True}
    assert base["scenarios"]["CASH"]["policy"] == "cash"
    assert pages[0]["row_alias"] == "SHORTAGE"
    assert all(page["rows"] == [] for page in pages)
    assert [
        row for page in pages for row in page["scenarios"]["SHORTAGE"]["rows"]
    ] == shortage_rows
    assert [
        row for page in pages for row in page["scenarios"]["CASH"]["rows"]
    ] == cash_rows
    assert pages[-1]["next_offset"] is None


def test_missing_object_page_is_reported_without_partial_result(fake_objects):
    result = {
        "entity_code": "PL",
        "source_snapshot_id": "snapshot-2",
        "rows": [{"sku_code": str(index)} for index in range(251)],
        "scenarios": {"CASH": {"rows": []}, "SHORTAGE": {"rows": []}},
    }
    stored = store_result("order3_missing", result)
    fake_objects.clear()

    with pytest.raises(OrderLogicV3ResultUnavailable):
        result_page("order3_missing", stored, offset=0, limit=250)


def test_development_without_object_storage_uses_local_paged_result(monkeypatch, tmp_path):
    monkeypatch.setattr(object_storage, "enabled", lambda: False)
    monkeypatch.setattr(result_store, "LOCAL_RESULT_ROOT", tmp_path / "order-v3")
    rows = [{"sku_code": f"LOCAL-{index}", "qty": index} for index in range(251)]
    result = {
        "entity_code": "USA", "source_snapshot_id": "local-snapshot",
        "rows": rows,
        "scenarios": {"CASH": {"rows": []}, "SHORTAGE": {"rows": rows}},
    }

    stored = store_result("order3_local", result)

    assert is_paged_result(stored)
    assert stored["_order_logic_v3_paged_result"]["storage"] == "local"
    assert len(list((tmp_path / "order-v3").rglob("*.json.gz"))) == 2
    first = result_page("order3_local", stored, offset=0, limit=250)
    second = result_page("order3_local", stored, offset=250, limit=250)
    assert first["scenarios"]["SHORTAGE"]["rows"] + second["scenarios"]["SHORTAGE"]["rows"] == rows
