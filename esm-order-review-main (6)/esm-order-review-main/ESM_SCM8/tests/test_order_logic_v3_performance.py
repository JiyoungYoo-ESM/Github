"""Performance boundaries must preserve source policy and all calculated values."""

from copy import deepcopy
from datetime import date
from threading import Barrier

import pandas as pd
import pytest

from backend.services import cms_fetch_cache, order_logic_v3_hq_fetch as fetch
from backend.services import order_logic_v3_service as service, order_logic_v3_source as source
from core.order_logic_v3 import SeasonalProfile, V3ReplenishmentBaseInput, V3ReplenishmentPolicy


def test_hq_inventory_fetch_uses_only_the_original_opo_endpoints(monkeypatch):
    calls = []
    monkeypatch.setattr(fetch, "_fetch_paged", lambda *args: calls.append(args) or [])
    monkeypatch.setattr(fetch, "_get_json", lambda *args: calls.append(args) or {"sample": 2})
    raw = fetch._fetch_inventory()
    assert set(raw) == {"inventory", "open_po", "inbound_confirmed", "leadtime_stats"}
    assert sorted(calls, key=lambda x: x[0]) == [
        ("/opo/inbound/confirmed", None, None, {"warehouse": "OPO"}),
        ("/opo/inventory", None, None, {"warehouse": "OPO"}),
        ("/opo/leadtime/stats", {"warehouse": "OPO", "months": 6}),
        ("/opo/po/open", None, None, {"warehouse": "OPO"}),
    ]


def test_hq_inventory_cache_is_independent_of_history_and_separate_from_v2(tmp_path, monkeypatch):
    monkeypatch.setattr(cms_fetch_cache, "CMS_FETCH_CACHE_DIR", tmp_path)
    from collections import OrderedDict
    monkeypatch.setattr(cms_fetch_cache, "_MEMORY_CACHE", OrderedDict())
    calls = []
    monkeypatch.setattr(fetch, "_fetch_inventory", lambda: calls.append(True) or {"inventory": []})
    a, info_a = fetch._cached_inventory(as_of="2026-08-31", force_refresh=False)
    b, info_b = fetch._cached_inventory(as_of="2026-08-31", force_refresh=False)
    assert a == b and len(calls) == 1 and not info_a["hit"] and info_b["hit"]
    common = dict(as_of="2026-08-31", date_from=None, date_to=None, logistics_date_from=None, entity_code="HQ")
    assert cms_fetch_cache._cache_key(**common) != cms_fetch_cache._cache_key(
        **common, cache_scope="v3_hq_inventory_position_v1",
    )


def test_components_are_parallel_keep_window_and_restore_invoice_order(monkeypatch):
    barrier = Barrier(2)
    captured = {}
    rows = [
        {"invc_no": "IN-02", "ship_dt": "2024-08-20", "qty": 3},
        {"invc_no": "IN-01", "ship_dt": "2025-01-02", "qty": 5},
    ]
    original = deepcopy(rows)

    def inventory(**kwargs):
        barrier.wait(timeout=3)
        captured["inventory"] = kwargs
        return {"inventory": [], "open_po": [], "inbound_confirmed": [], "leadtime_stats": {}}, {"hit": True}

    def history(**kwargs):
        barrier.wait(timeout=3)
        captured["history"] = kwargs
        return {"sales_history": rows, "prod_list": []}, {"cache": {"hit": True}}

    monkeypatch.setattr(fetch, "_cached_inventory", inventory)
    monkeypatch.setattr(fetch, "fetch_cached_season_trend_source_data", history)
    raw, meta = fetch.fetch_cached_hq_opo_raw_data(
        as_of="2026-08-31", date_from="2024-08-01", date_to="2026-08-30", force_refresh=True,
    )
    assert captured["history"] == dict(
        date_from="2024-08-01", date_to="2026-08-30", eu_sold_only=False, entity_code="HQ", force_refresh=True,
    )
    assert captured["inventory"] == dict(as_of="2026-08-31", force_refresh=True)
    assert raw["sales_history"] == [rows[1], rows[0]]
    assert rows == original
    assert meta["warehouse_code"] == "OPO"


@pytest.mark.parametrize("rows", [
    [{"ship_dt": "2026-01-01"}],
    [{"invc_no": "A", "ship_dt": "2026-01-01"}, {"invc_no": "A", "ship_dt": "2026-02-01"}],
    [{"invc_no": "B", "ship_dt": "2026-01-01"}, {"invc_no": "A", "ship_dt": "2026-01-02"}],
])
def test_ambiguous_month_order_uses_original_query_not_inferred_order(monkeypatch, rows):
    monkeypatch.setattr(fetch, "_cached_inventory", lambda **kw: ({"inventory": []}, {}))
    monkeypatch.setattr(fetch, "fetch_cached_season_trend_source_data", lambda **kw: (
        {"sales_history": rows, "prod_list": []}, {},
    ))
    calls = []
    monkeypatch.setattr(fetch, "_fetch_paged", lambda *args: calls.append(args) or rows)
    raw, meta = fetch.fetch_cached_hq_opo_raw_data(as_of="2026-08-31", date_from="2024-08-01", date_to="2026-08-30")
    assert calls == [("/us/sales/history", "2024-08-01", "2026-08-30")]
    assert raw["sales_history"] is rows
    assert meta["history"]["sales_order_source"] == "original_full_range_query"


def test_failed_history_never_becomes_partial_snapshot(monkeypatch):
    monkeypatch.setattr(fetch, "_cached_inventory", lambda **kw: ({}, {}))
    def fail(**kw):
        raise RuntimeError("synthetic source unavailable")
    monkeypatch.setattr(fetch, "fetch_cached_season_trend_source_data", fail)
    with pytest.raises(RuntimeError, match="synthetic"):
        fetch.fetch_cached_hq_opo_raw_data(as_of="2026-08-31", date_from="2024-08-01", date_to="2026-08-30")


def test_invalid_dates_dropped_by_month_client_preserve_original_identity_evidence(monkeypatch):
    monkeypatch.setattr(fetch, "_cached_inventory", lambda **kw: ({"inventory": []}, {}))
    monkeypatch.setattr(fetch, "fetch_cached_season_trend_source_data", lambda **kw: (
        {"sales_history": [], "prod_list": []},
        {"sales_history": {"date_chunks": [{"invalid_date_rows": 1}]}},
    ))
    original_rows = [{"invc_no": "A", "ship_dt": "invalid", "prod_cd": "abc", "prod_nm": "Name evidence"}]
    monkeypatch.setattr(fetch, "_fetch_paged", lambda *args: original_rows)
    raw, meta = fetch.fetch_cached_hq_opo_raw_data(as_of="2026-08-31", date_from="2024-08-01", date_to="2026-08-30")
    assert raw["sales_history"] is original_rows
    assert meta["history"]["full_range_reason"] == "invalid_month_dates"


def test_invoice_sort_preserves_duplicate_lines_and_does_not_mutate_cache():
    rows = [
        {"invc_no": "B", "ship_dt": "2026-01-02", "qty": 1},
        {"invc_no": "B", "ship_dt": "2026-01-02", "qty": 1},
        {"invc_no": "B", "ship_dt": "2026-01-02", "qty": 2},
        {"invc_no": "A", "ship_dt": "2026-02-02", "qty": 3},
    ]
    original = deepcopy(rows)
    assert fetch._legacy_order_from_months(rows) == [rows[3], *rows[:3]]
    assert rows == original


def test_last_identity_keeps_physical_row_and_null_behavior():
    frame = pd.DataFrame([
        {source.PRODUCT_CODE_COL: "A", source.PRODUCT_NAME_COL: "First", source.BRAND_COL: "Brand"},
        {source.PRODUCT_CODE_COL: "B", source.PRODUCT_NAME_COL: "B", source.BRAND_COL: "Brand"},
        {source.PRODUCT_CODE_COL: "A", source.PRODUCT_NAME_COL: None, source.BRAND_COL: None},
    ])
    frame[source.CATEGORY1_COL] = None
    frame[source.CATEGORY2_COL] = None
    expected = {}
    for sku, group in frame.groupby(source.PRODUCT_CODE_COL, sort=False):
        row = group.iloc[-1]
        expected[source._text(sku)] = (
            source._text(row.get(source.PRODUCT_NAME_COL)), source._text(row.get(source.BRAND_COL)),
            source._text(row.get(source.CATEGORY1_COL)) or source.UNMAPPED,
            source._text(row.get(source.CATEGORY2_COL)) or source.UNMAPPED,
        )
    assert source._identities(frame) == expected
    assert expected["A"][0] != "First"


def test_early_opo_filter_preserves_alias_conflicts_in_other_warehouses():
    from backend.services.order_logic_v3_product_identity import ProductIdentityResolver
    products = [{"prod_cd": "ABC.0", "prod_nm": "Exact", "class1_nm": "스킨케어", "class2_nm": "패치"}]
    rows = [
        {"prod_cd": "abc.0", "prod_nm": "Exact", "qty": 3, "amount_krw": 100,
         "whouse_nm": "OPO", "biz_type": "KR-DOMESTIC", "ship_dt": "2026-08-20"},
        {"prod_cd": "abc.0", "prod_nm": "Different", "qty": 8, "amount_krw": 100,
         "whouse_nm": "BR-EU", "biz_type": "KR-DOMESTIC", "ship_dt": "2026-08-20"},
    ]
    original = deepcopy(rows)
    resolver = ProductIdentityResolver.build(products, [rows])
    demand = source._paid_demand(rows, products, entity_code="HQ", identity_resolver=resolver)
    assert "abc.0" in resolver.rejected
    assert demand[source.PRODUCT_CODE_COL].tolist() == ["abc.0"]
    assert demand[source.QTY_COL].sum() == 3
    assert rows == original


def test_empty_sales_reference_reuse_is_exact_and_per_sku_lists_are_independent(monkeypatch):
    profile = SeasonalProfile(version="synthetic", entity_code="HQ", function_class_1_code="C1",
                              function_class_2_code="C2", factors_by_month={i: 1.0 for i in range(1, 13)})
    policy = V3ReplenishmentPolicy(lead_time_days=28, review_days=28, sigma_lead_time_periods=0.1,
                                  safety_stock_floor_periods=0.5, safety_stock_cap_periods=1.25)
    replenishment = V3ReplenishmentBaseInput(order_date=date(2026, 8, 31), cash_policy=policy,
                                           shortage_policy=policy, on_hand_qty=0, in_transit_qty=0,
                                           unreceived_qty=0, holding_qty=0, upstream_available_qty=0)
    inputs = [service.OrderLogicV3SkuCalculationInput(sku_code=str(i), product_name="Synthetic", brand="B",
              daily_sales={}, first_sale_date=None, seasonal_profile=profile, replenishment=replenishment,
              sales_grade="GENERAL") for i in range(3)]
    calls = []
    original = service.sales_reference_metrics
    def recorded(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(service, "sales_reference_metrics", recorded)
    result = service.build_order_logic_v3_calculation_result(
        job_id="synthetic", as_of="2026-08-31", entity_code="HQ",
        parameters=service.textbook_candidate_parameters(logic_version=service.LOGIC_VERSION),
        sku_inputs=inputs, source_snapshot_id="synthetic", source_fetched_at="synthetic",
    )
    assert len(calls) == 1
    expected = original({}, completed_sales_cutoff=date(2026, 8, 30))
    for row in result["rows"]:
        assert {k: row[k] for k in expected} == expected
        assert row["reason_code"] == "DEMAND_HISTORY_INSUFFICIENT"
    result["rows"][0]["reference_weekly_sales_history"][0] = 999
    assert result["rows"][1]["reference_weekly_sales_history"][0] == 0
