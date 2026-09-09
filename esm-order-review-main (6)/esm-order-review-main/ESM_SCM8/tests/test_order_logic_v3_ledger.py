"""Synthetic ledger contracts: sales population, complete pages, cache boundaries."""

from datetime import date
import json

import pytest

from backend.services import analysis_cancel
from backend.services import order_logic_v3_ledger as ledger
from backend.services import order_logic_v3_source as source


def row(kind="OUT-SALE", qty=3, **fields):
    return {
        "ledger_dt": "2026-08-31", "prod_cd": "TEST.0", "prod_nm": "Synthetic",
        "brand_nm": "TEST", "biz_gbn": "COSMETIC", "comp_cd": "CO000007",
        "whouse_cd": "TEST-WH", "ledger_type_nm": kind,
        "qty": -qty, "qty_in": max(0, -qty), "qty_out": max(0, qty),
        "origin_no": "SAME-DOCUMENT", "cust_nm": "SYNTHETIC PRIVATE CUSTOMER",
        "remk": "SYNTHETIC PRIVATE REMARK", **fields,
    }


def fake_api(monkeypatch, rows, *, page_size=2, change=None):
    calls = []
    monkeypatch.setattr(ledger, "PAGE_SIZE", page_size)

    def get(path, params):
        calls.append((path, params))
        page = params["page"]
        payload = {"items": rows[(page - 1) * page_size:page * page_size],
                   "page": page, "page_size": page_size,
                   "total": len(rows) if params["include_total"] == "true" else None}
        return change(page, payload) if change else payload

    monkeypatch.setattr(ledger, "_get_json", get)
    return calls


def fetch_month(entity="USA"):
    return ledger._fetch_month(entity_code=entity, start=date(2026, 8, 1), end=date(2026, 8, 31))


def test_all_pages_include_online_keep_identical_lines_and_strip_private_fields(monkeypatch):
    rows = [row(qty=32), row("OUT-SALE (ONLINE)", 3), row("STOCK ADJUSTMENT (OUT)", 100),
            row("PURCHASE", -50), row("OUT-SALE (ONLINE)", 3), row("RETURN - IN", -2),
            row("STOCK MOVEMENT (OUT)", 70)]
    calls = fake_api(monkeypatch, rows)
    raw = fetch_month()
    assert sum(item["qty_out"] for item in raw["daily_sales"]) == 38
    assert raw["audit"]["raw_row_count"] == 7
    assert raw["audit"]["pages"] == 4
    assert raw["audit"]["sales_row_count"] == 3
    assert raw["audit"]["out_qty_by_type"]["STOCK ADJUSTMENT (OUT)"] == 100
    assert sorted(params["page"] for _, params in calls) == [1, 2, 3, 4]
    assert all(path == "/esm/stock-in-out" for path, _ in calls)
    assert all(params["comp_cd"] == "CO000007" and "whouse_cd" not in params for _, params in calls)
    assert all(params["include_total"] == ("true" if params["page"] == 1 else "false") for _, params in calls)
    for forbidden in ("origin_no", "cust_nm", "remk", "PRIVATE"):
        assert forbidden not in json.dumps(raw)


@pytest.mark.parametrize("entity,company,warehouse", [
    ("HQ", "CO000001", "WH000028"), ("PL", "CO000016", None), ("USA", "CO000007", None),
])
def test_entity_and_warehouse_scopes(monkeypatch, entity, company, warehouse):
    calls = fake_api(monkeypatch, [row(comp_cd=company, whouse_cd=warehouse or "TEST-WH")])
    assert fetch_month(entity)["audit"]["sales_quantity"] == 3
    assert calls[0][1]["comp_cd"] == company
    assert calls[0][1].get("whouse_cd") == warehouse


@pytest.mark.parametrize("fields", [
    {"comp_cd": "WRONG"}, {"whouse_cd": None}, {"biz_gbn": "FOOD"},
    {"ledger_dt": "2026-07-31"}, {"ledger_dt": "2026-08-31T00:00:00Z"},
    {"qty_out": -3}, {"qty": 3}, {"qty_in": 1}, {"qty_out": None},
    {"qty": -3.5}, {"qty_out": True}, {"prod_cd": ""}, {"ledger_type_nm": None},
    {"prod_nm": 12}, {"qty": 3, "qty_in": 2, "qty_out": 0},
])
def test_malformed_rows_fail_instead_of_becoming_zero_sales(monkeypatch, fields):
    fake_api(monkeypatch, [{**row(), **fields}])
    with pytest.raises(ledger.LedgerSourceError):
        fetch_month()


@pytest.mark.parametrize("change", [
    lambda page, data: {**data, "total": None},
    lambda page, data: {**data, "page": page + 1},
    lambda page, data: {**data, "page_size": 1},
    lambda page, data: {**data, "items": []} if page == 2 else data,
    lambda page, data: {**data, "total": 4} if page == 2 else data,
])
def test_missing_truncated_or_changing_pages_fail(monkeypatch, change):
    fake_api(monkeypatch, [row(), row(), row()], change=change)
    with pytest.raises(ledger.LedgerSourceError):
        fetch_month()


def test_empty_complete_month_is_valid(monkeypatch):
    fake_api(monkeypatch, [])
    raw = fetch_month()
    assert raw["daily_sales"] == []
    assert raw["audit"]["raw_row_count"] == 0


def test_zero_quantity_sale_has_no_effect_on_demand(monkeypatch):
    fake_api(monkeypatch, [row(qty=0)])
    raw = fetch_month()
    assert raw["daily_sales"] == []
    assert raw["audit"]["sales_quantity"] == 0


@pytest.mark.parametrize("kind", sorted(ledger.SALE_TYPES))
def test_inbound_only_sale_label_contributes_zero_without_subtracting_sales(monkeypatch, kind):
    fake_api(monkeypatch, [row(qty=32), row("OUT-SALE (ONLINE)", 3), row(kind, -5)])
    raw = fetch_month()
    assert raw["audit"]["raw_row_count"] == 3
    assert raw["audit"]["pages"] == 2
    assert raw["audit"]["sales_inbound_only_row_count"] == 1
    assert raw["audit"]["sales_quantity"] == 35
    assert sum(item["qty_out"] for item in raw["daily_sales"]) == 35


def test_page_progress_reaches_total_only_after_validation(monkeypatch):
    fake_api(monkeypatch, [row(), row(), row()])
    progress = []
    ledger._fetch_month(entity_code="USA", start=date(2026, 8, 1), end=date(2026, 8, 31), progress=progress.append)
    assert progress == [{"completed_pages": 1, "total_pages": 2}, {"completed_pages": 2, "total_pages": 2}]


def test_cancelled_fetch_never_requests_pages(monkeypatch):
    token = analysis_cancel.CancelToken()
    token.cancel()
    monkeypatch.setattr(ledger, "_get_json", lambda *_: pytest.fail("Cancelled request"))
    with pytest.raises(analysis_cancel.AnalysisCancelled):
        ledger._fetch_month(entity_code="USA", start=date(2026, 8, 1), end=date(2026, 8, 31), token=token)


def test_monthly_cache_is_shared_by_demand_and_season_and_trims_exact_window(monkeypatch):
    monkeypatch.setattr(ledger, "korea_today", lambda: date(2026, 9, 7))
    cache, requests, fetches = {}, [], []

    def month(**kwargs):
        fetches.append(kwargs)
        return {"daily_sales": [row(ledger_dt=kwargs["start"].isoformat()),
                                row(ledger_dt=kwargs["end"].isoformat())], "audit": {}}

    def cached(**kwargs):
        requests.append(kwargs)
        key = (kwargs["entity_code"], kwargs["date_from"], kwargs["date_to"], kwargs["cache_scope"])
        if key not in cache or kwargs["force_refresh"]:
            cache[key] = kwargs["fetcher"]()
        return cache[key], {"hit": True}

    monkeypatch.setattr(ledger, "_fetch_month", month)
    monkeypatch.setattr(ledger, "get_or_fetch_cms_raw_data", cached)
    rows, meta = ledger.fetch_v3_ledger_sales(entity_code="USA", date_from="2024-09-01", date_to="2026-08-31")
    assert len(fetches) == 24
    assert len(rows) == 48
    assert all((r["end"] - r["start"]).days < 31 for r in fetches)
    assert meta["policy"] == ledger.LEDGER_POLICY
    rows, _ = ledger.fetch_v3_ledger_sales(entity_code="USA", date_from="2026-06-08", date_to="2026-09-06")
    assert len(fetches) == 25
    assert [r["ledger_dt"] for r in rows] == ["2026-06-30", "2026-07-01", "2026-07-31", "2026-08-01", "2026-08-31", "2026-09-01"]
    assert requests[-1]["as_of"] == "2026-09-07"
    ledger.fetch_v3_ledger_sales(entity_code="USA", date_from="2026-08-01", date_to="2026-08-31", force_refresh=True)
    assert len(fetches) == 26


def test_partial_fetch_failure_does_not_write_a_cache_entry(tmp_path, monkeypatch):
    from backend.services import cms_fetch_cache
    monkeypatch.setattr(cms_fetch_cache, "CMS_FETCH_CACHE_DIR", tmp_path)
    monkeypatch.setattr(ledger, "korea_today", lambda: date(2026, 9, 7))
    fake_api(monkeypatch, [row(), row(), row()], change=lambda p, data: {**data, "items": []} if p == 2 else data)
    with pytest.raises(ledger.LedgerSourceError):
        ledger.fetch_v3_ledger_sales(entity_code="USA", date_from="2026-08-01", date_to="2026-08-31", force_refresh=True)
    assert list(tmp_path.glob("*.json")) == []


def test_ledger_demand_requires_no_amount_and_uses_source_calendar_date():
    rows = [row(qty=32), row("OUT-SALE (ONLINE)", 3), row("STOCK ADJUSTMENT (OUT)", 100)]
    master = [{"prod_cd": "TEST.0", "prod_nm": "Synthetic", "class1_nm": "스킨케어", "class2_nm": "패치"}]
    demand = source._ledger_demand(rows, master, entity_code="USA")
    assert source.AMOUNT_COL not in demand
    assert source._daily_sales(demand, period_end=date(2026, 9, 6)) == {"TEST.0": {date(2026, 8, 31): 35.0}}
    assert set(demand[source.CATEGORY2_COL]) == {"패치"}


def test_legacy_season_factor_is_blocked_until_recalculated(monkeypatch):
    from backend.services import order_logic_v3_season_factor_service as service
    monkeypatch.setattr(service, "load_active_season_factor_catalog", lambda _: (None, {"source_policy": None}))
    catalog, meta = source._load_active_profile_catalog("USA")
    assert catalog.artifact_error_code == "SEASON_FACTOR_SOURCE_MISMATCH"
    assert meta["status"] == "unavailable"
    assert "계절지수" in meta["message"]


def test_new_season_factor_source_policy_is_accepted(monkeypatch):
    from backend.services import order_logic_v3_season_factor_service as service
    sentinel = object()
    monkeypatch.setattr(service, "load_active_season_factor_catalog", lambda _: (sentinel, {"source_policy": ledger.LEDGER_POLICY}))
    assert source._load_active_profile_catalog("USA")[0] is sentinel
