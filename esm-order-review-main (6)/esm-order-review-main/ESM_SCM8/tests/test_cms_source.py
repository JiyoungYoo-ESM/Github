from __future__ import annotations

import pytest

from backend.services import cms_fetch_cache
from backend.services.cms_source import (
    fetch_cached_cms_inventory_raw_data,
    fetch_cached_cms_raw_data,
    resolve_cms_effective_dates,
)
from backend.services.order_logic_v3_unreceived_window import (
    unreceived_cache_scope,
    unreceived_po_window,
)


def test_default_cms_effective_dates_use_logistics_window_start():
    dates = resolve_cms_effective_dates("2026-07-02")

    assert dates.date_from == "2026-01-01"
    assert dates.logistics_date_from == "2026-01-01"
    assert dates.date_to == "2026-07-02"


def test_prefetch_and_default_router_cache_key_fields_match():
    as_of = "2026-07-02"
    router_dates = resolve_cms_effective_dates(as_of, None)
    prefetch_dates = resolve_cms_effective_dates(as_of, None)

    router_key = cms_fetch_cache._cache_key(as_of=as_of, **router_dates.cache_fields())
    prefetch_key = cms_fetch_cache._cache_key(as_of=as_of, **prefetch_dates.cache_fields())

    assert router_dates == prefetch_dates
    assert router_key == prefetch_key


def test_fetch_cached_cms_raw_data_uses_router_fetch_arguments(tmp_path, monkeypatch):
    captured: dict[str, object] = {}

    def fake_fetch_cms_data(as_of: str, **kwargs: object) -> dict[str, object]:
        captured["as_of"] = as_of
        captured.update(kwargs)
        return {"sales_local": [{"prod_cd": "SKU-1"}]}

    monkeypatch.setattr(cms_fetch_cache, "CMS_FETCH_CACHE_DIR", tmp_path)
    cms_fetch_cache._MEMORY_CACHE.clear()
    cms_fetch_cache._KEY_LOCKS.clear()
    monkeypatch.setattr("backend.services.cms_source.fetch_cms_data", fake_fetch_cms_data)

    raw, cache_info, dates = fetch_cached_cms_raw_data(as_of="2026-07-02", date_from=None)

    assert raw == {"sales_local": [{"prod_cd": "SKU-1"}]}
    assert cache_info["source"] == "cms_api"
    assert dates.date_from == "2026-01-01"
    assert captured == {
        "as_of": "2026-07-02",
        "date_from": "2026-01-01",
        "date_to": "2026-07-02",
        "shipping_date_from": "2026-01-01",
        "open_po_date_from": "2026-01-01",
        "include_sales_detail": True,
        "entity_code": "PL",
    }


def test_fetch_cached_cms_raw_data_scopes_us_fetch_and_cache(tmp_path, monkeypatch):
    captured: dict[str, object] = {}

    def fake_fetch_cms_data(as_of: str, **kwargs: object) -> dict[str, object]:
        captured["as_of"] = as_of
        captured.update(kwargs)
        return {"sales_local": []}

    monkeypatch.setattr(cms_fetch_cache, "CMS_FETCH_CACHE_DIR", tmp_path)
    cms_fetch_cache._MEMORY_CACHE.clear()
    cms_fetch_cache._KEY_LOCKS.clear()
    monkeypatch.setattr("backend.services.cms_source.fetch_cms_data", fake_fetch_cms_data)

    fetch_cached_cms_raw_data(
        as_of="2026-07-28",
        entity_code="USA",
    )

    assert captured["entity_code"] == "USA"


def test_v3_inventory_snapshot_skips_v2_sales_and_eta_sources(tmp_path, monkeypatch):
    captured: dict[str, object] = {}

    def fake_fetch_cms_data(as_of: str, **kwargs: object) -> dict[str, object]:
        captured["as_of"] = as_of
        captured.update(kwargs)
        return {"stock_local": [], "stock_hq": [], "shipping": [], "open_po": []}

    monkeypatch.setattr(cms_fetch_cache, "CMS_FETCH_CACHE_DIR", tmp_path)
    cms_fetch_cache._MEMORY_CACHE.clear()
    cms_fetch_cache._KEY_LOCKS.clear()
    monkeypatch.setattr("backend.services.cms_source.fetch_cms_data", fake_fetch_cms_data)

    fetch_cached_cms_inventory_raw_data(
        as_of="2026-07-28",
        entity_code="USA",
    )

    assert captured["entity_code"] == "USA"
    assert captured["include_sales_detail"] is False
    assert captured["include_lead_time_detail"] is False
    dates = resolve_cms_effective_dates("2026-07-28")
    assert cms_fetch_cache._cache_key(
        as_of="2026-07-28",
        entity_code="USA",
        cache_scope=unreceived_cache_scope(),
        **dates.cache_fields(),
    ) != cms_fetch_cache._cache_key(
        as_of="2026-07-28",
        entity_code="USA",
        **dates.cache_fields(),
    )


@pytest.mark.parametrize("entity_code", ["PL", "USA"])
def test_v3_inventory_snapshot_narrows_only_the_unreceived_quantity(
    tmp_path, monkeypatch, entity_code
):
    """① 미입고만 30일 창으로 바꾸고, ②③과 운송중 창은 전체 기간을 유지한다."""

    captured: dict[str, object] = {}
    open_po_calls: list[dict[str, object]] = []

    def fake_fetch_cms_data(as_of: str, **kwargs: object) -> dict[str, object]:
        captured["as_of"] = as_of
        captured.update(kwargs)
        return {
            "stock_local": [], "stock_hq": [], "shipping": [],
            "open_po": [{
                "prod_cd": "SKU-STALE", "prod_nm": "Stale", "open_qty": 900,
                "po_qty": 1000, "pnfm_qty": 100, "open_amt": 9000.0,
                "pnfm_confirmed_qty": 60, "inbound_in_progress_qty": 40,
                "completed_qty": 25,
            }],
        }

    def fake_fetch_cms_open_po(entity: str, **kwargs: object) -> list[dict[str, object]]:
        open_po_calls.append({"entity": entity, **kwargs})
        return []

    monkeypatch.setattr(cms_fetch_cache, "CMS_FETCH_CACHE_DIR", tmp_path)
    cms_fetch_cache._MEMORY_CACHE.clear()
    cms_fetch_cache._KEY_LOCKS.clear()
    monkeypatch.setattr("backend.services.cms_source.fetch_cms_data", fake_fetch_cms_data)
    monkeypatch.setattr("backend.services.cms_source.fetch_cms_open_po", fake_fetch_cms_open_po)

    raw, _cache_info, _dates = fetch_cached_cms_inventory_raw_data(
        as_of="2026-09-04", entity_code=entity_code,
    )

    window_start, window_end = unreceived_po_window("2026-09-04")
    assert window_start.isoformat() == "2026-08-06"
    # 두 번째 조회만 30일 창을 쓰고, 첫 조회는 기존 전체 창을 그대로 쓴다.
    assert open_po_calls == [{
        "entity": entity_code,
        "date_from": window_start.isoformat(),
        "date_to": window_end.isoformat(),
    }]
    assert captured["open_po_date_from"] == "2026-01-01"
    # 운송중·재고·리드타임 창은 이번 결정의 범위가 아니다.
    assert captured["shipping_date_from"] == "2026-01-01"

    row = raw["open_po"][0]
    # ① 미입고 수량·금액만 30일 창 값으로 바뀐다.
    assert row["open_qty"] == 0 and row["open_amt"] == 0
    # 확실히 들어올 물량, PO 단위 총계, 식별 정보는 전체 창 값을 유지한다.
    assert row["pnfm_confirmed_qty"] == 60
    assert row["inbound_in_progress_qty"] == 40
    assert row["completed_qty"] == 25
    assert row["po_qty"] == 1000 and row["pnfm_qty"] == 100
    assert row["po_qty"] >= row["completed_qty"]
    assert row["prod_nm"] == "Stale"
    assert raw["open_po_unreceived_window"]["changed_rows"] == 1


def test_v2_snapshot_keeps_the_year_to_date_open_po_window(tmp_path, monkeypatch):
    """V2는 같은 결정의 대상이 아니므로 1월 1일 미입고 창을 유지한다."""

    captured: dict[str, object] = {}

    def fake_fetch_cms_data(as_of: str, **kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"sales_local": [], "stock_local": [], "shipping": [], "open_po": []}

    monkeypatch.setattr(cms_fetch_cache, "CMS_FETCH_CACHE_DIR", tmp_path)
    cms_fetch_cache._MEMORY_CACHE.clear()
    cms_fetch_cache._KEY_LOCKS.clear()
    monkeypatch.setattr("backend.services.cms_source.fetch_cms_data", fake_fetch_cms_data)

    fetch_cached_cms_raw_data(as_of="2026-09-04", entity_code="PL")

    assert captured["open_po_date_from"] == "2026-01-01"
