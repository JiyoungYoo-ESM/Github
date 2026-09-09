"""Product classification must not depend on a SKU having eligible sales."""

from copy import deepcopy
from datetime import date, timedelta

import pytest

from backend.services import order_logic_v3_source as source
from backend.services.order_logic_v3_service import (
    LOGIC_VERSION,
    OrderLogicV3SkuCalculationInput,
    build_order_logic_v3_calculation_result,
)
from core.order_logic_v3 import SeasonalProfile, V3ReplenishmentPolicy, textbook_candidate_parameters


@pytest.fixture
def source_case(monkeypatch):
    def prepare(entity_code, *, with_sales=True, artifact_error=None):
        products = [
            {"prod_cd": "SOLD", "class1_nm": "스킨케어", "class2_nm": "패치"},
            {"prod_cd": "NO-SALES", "prod_nm": "마스터 상품명", "brand_nm": "TEST", "class1": "01", "class2_nm": "패치", "use_yn": "N"},
            {"prod_cd": "PARENT", "class1_nm": "스킨케어", "class2_nm": None},
            {"prod_cd": "FILTERED", "class1_nm": "스킨케어", "class2_nm": "패치"},
            {"prod_cd": "UNCLASSIFIED", "class1_nm": None, "class2_nm": None},
            {"prod_cd": "MASTER-ONLY", "class1_nm": "스킨케어", "class2_nm": "패치"},
        ]
        biz_type = {"PL": "EU-PL", "USA": "US-DOMESTIC", "HQ": "KR-DOMESTIC"}[entity_code]
        sales = [
            {
                "prod_cd": "SOLD", "qty": 20 + index, "amount": 100, "amount_krw_actual": 100,
                "ship_dt": (date(2026, 6, 1) + timedelta(days=index * 7)).isoformat(),
                "biz_type": biz_type, "whouse_nm": "OPO",
            }
            for index in range(13)
        ] if with_sales else []
        # A returned transaction is not necessarily an eligible paid sale.
        sales.append({
            "prod_cd": "FILTERED", "qty": 1, "amount": 0, "amount_krw_actual": 0,
            "ship_dt": "2026-08-23", "biz_type": "FREE SAMPLE", "whouse_nm": "OPO",
        })
        inventory = {
            sku: {"product_name": "재고 상품명", "brand": "", "barcode": "00012345", "local_available_qty": 10}
            for sku in ["SOLD", "NO-SALES", "PARENT", "FILTERED", "UNCLASSIFIED", "NO-MASTER"]
        }
        factor = {"HQ": 0.8, "PL": 1.1, "USA": 1.2}[entity_code]
        combo = SeasonalProfile(
            version="synthetic-active", entity_code=entity_code,
            function_class_1_code="스킨케어", function_class_2_code="패치",
            factors_by_month={month: factor for month in range(1, 13)},
        )
        parent = SeasonalProfile(
            version="synthetic-active", entity_code=entity_code,
            function_class_1_code="스킨케어", function_class_2_code=source.FUNCTION_CLASS_1_AGGREGATE,
            factors_by_month={month: 1.3 for month in range(1, 13)},
        )
        catalog = source._SeasonalProfileCatalog(
            by_class_1_and_2={("스킨케어", "패치"): combo}, by_class_1={"스킨케어": parent},
            class_1_and_2_errors={}, class_1_errors={}, identities={},
            artifact_error_code=artifact_error,
        )
        monkeypatch.setattr(source, "fetch_cached_cms_inventory_raw_data", lambda **_: ({}, {}, ()))
        monkeypatch.setattr(source, "fetch_v3_ledger_sales", lambda **_: ([
            {"prod_cd": row["prod_cd"], "prod_nm": row.get("prod_nm"),
             "ledger_dt": row["ship_dt"], "qty_out": row["qty"], "ledger_type_nm": "OUT-SALE"}
            for row in sales if row["prod_cd"] != "FILTERED"
        ], {"sha256": "synthetic-ledger"}))
        monkeypatch.setattr(source, "fetch_cached_season_trend_source_data", lambda **_: (
            {"sales_history": sales, "prod_list": products}, {},
        ))
        monkeypatch.setattr(source, "fetch_cached_hq_opo_raw_data", lambda **_: (
            {"sales_history": sales, "products": products}, {},
        ))
        monkeypatch.setattr(source, "_inventory_rows", lambda *_, **__: (inventory, {"inventory": len(inventory)}, None))
        policy = V3ReplenishmentPolicy(
            lead_time_days=28, review_days=28, sigma_lead_time_periods=0.1,
            safety_stock_floor_periods=0.5, safety_stock_cap_periods=1.25,
        )
        modes = {"PL": ("RAIL", "SEA"), "USA": ("AIR", "SEA"),
                 "HQ": ("DOMESTIC_COMMON", "DOMESTIC_COMMON")}[entity_code]
        # The real policy loader supplies both operands and their measured
        # mode audit; the V2-backed ETA adapter consumes that same audit.
        lead_time_audit = {"source": {}, "scenarios": {
            scenario: {"transport_mode": mode, "lead_time_days": policy.lead_time_days}
            for scenario, mode in zip(("CASH", "SHORTAGE"), modes)
        }}
        monkeypatch.setattr(source, "_measured_replenishment_policies", lambda **_: (policy, policy, lead_time_audit))
        monkeypatch.setattr(source, "_load_active_profile_catalog", lambda _: (catalog, {"version": combo.version}))
        monkeypatch.setattr(source, "_profiles", lambda *_, **__: pytest.fail("Web analysis must not regenerate monthly factors"))
        return products, sales, combo, parent
    return prepare


@pytest.mark.parametrize("entity_code", ["PL", "USA"])
def test_inventory_only_classification_fetches_full_master(source_case, monkeypatch, entity_code):
    products, sales, combo, parent = source_case(entity_code)
    calls = []

    def fetch(**kwargs):
        calls.append(kwargs)
        # The EU-sold list omits valid inventory-only products, even after
        # the shared season client supplements codes found in sales history.
        sold_codes = {row["prod_cd"] for row in sales}
        selected = (
            [row for row in products if row["prod_cd"] in sold_codes]
            if kwargs["eu_sold_only"] else products
        )
        return {"sales_history": sales, "prod_list": selected}, {"eu_sold_only": kwargs["eu_sold_only"]}

    monkeypatch.setattr(source, "fetch_cached_season_trend_source_data", fetch)
    rows, meta = source.build_order_logic_v3_source(
        as_of="2026-08-31", entity_code=entity_code, force_refresh=True,
    )
    by_sku = {row["sku_code"]: row for row in rows}
    assert by_sku["NO-SALES"]["source_function_class_1_code"] == "스킨케어"
    assert by_sku["NO-SALES"]["seasonal_profile"] == combo
    assert by_sku["PARENT"]["seasonal_profile"] == parent
    assert set(by_sku) == {"SOLD", "NO-SALES", "PARENT", "FILTERED", "UNCLASSIFIED", "NO-MASTER"}
    assert by_sku["SOLD"]["daily_sales"] == {
        date.fromisoformat(row["ship_dt"]): row["qty"] for row in sales if row["prod_cd"] == "SOLD"
    }
    assert all(row["replenishment"].on_hand_qty == 10 for row in rows)
    for sku in ("UNCLASSIFIED", "NO-MASTER"):
        assert by_sku[sku]["season_factor_blocking_reason_code"] == "SEASON_FACTOR_MAPPING_MISSING"
    assert calls == [{
        "date_from": "2026-06-01", "date_to": "2026-08-30", "eu_sold_only": False,
        "force_refresh": True, "entity_code": entity_code,
    }]
    assert meta["revenue_source"]["eu_sold_only"] is False
    assert meta["demand_window"] == {
        "date_from": "2026-06-01",
        "date_to": "2026-08-30",
        "completed_periods": 13,
        "period_days": 7,
        "calendar_days": 91,
    }
    assert meta["classification_master_scope"] == "FULL_PRODUCT_MASTER"


@pytest.mark.parametrize("entity_code", ["HQ", "PL", "USA"])
def test_ledger_drives_quantity_while_existing_sales_drive_revenue_grade(source_case, monkeypatch, entity_code):
    source_case(entity_code)
    calls = []

    def ledger_fetch(**kwargs):
        calls.append(kwargs)
        return [
            {"prod_cd": sku, "ledger_dt": "2026-08-23", "ledger_type_nm": kind, "qty_out": qty}
            for sku, kind, qty in [("SOLD", "OUT-SALE", 32), ("SOLD", "OUT-SALE (ONLINE)", 3),
                                   ("SOLD", "STOCK ADJUSTMENT (OUT)", 100), ("FILTERED", "OUT-SALE (ONLINE)", 7)]
        ], {"sha256": "synthetic-ledger"}

    monkeypatch.setattr(source, "fetch_v3_ledger_sales", ledger_fetch)
    rows, _ = source.build_order_logic_v3_source(as_of="2026-08-31", entity_code=entity_code)
    by_sku = {row["sku_code"]: row for row in rows}
    assert by_sku["SOLD"]["daily_sales"] == {date(2026, 8, 23): 35}
    assert by_sku["FILTERED"]["daily_sales"] == {date(2026, 8, 23): 7}
    assert by_sku["SOLD"]["sales_grade"] == "CORE"
    assert by_sku["FILTERED"]["sales_grade"] == "GENERAL"
    assert all(row["replenishment"].on_hand_qty == 10 for row in rows)
    assert calls == [{"entity_code": entity_code, "date_from": "2026-06-01", "date_to": "2026-08-30", "force_refresh": False}]


def test_hq_web_source_fetches_only_the_completed_91_day_window(
    source_case,
    monkeypatch,
):
    products, sales, _, _ = source_case("HQ")
    calls = []

    def fetch_hq(**kwargs):
        calls.append(kwargs)
        return {"sales_history": sales, "products": products}, {"source": "test"}

    monkeypatch.setattr(source, "fetch_cached_hq_opo_raw_data", fetch_hq)

    source.build_order_logic_v3_source(
        as_of="2026-08-31",
        entity_code="HQ",
        force_refresh=True,
    )

    assert calls == [{
        "as_of": "2026-08-31",
        "date_from": "2026-06-01",
        "date_to": "2026-08-30",
        "force_refresh": True,
    }]


@pytest.mark.parametrize("entity_code", ["HQ", "PL", "USA"])
def test_excel_reference_buckets_pass_through_without_changing_inventory(source_case, entity_code):
    source_case(entity_code)
    inventory, _, _ = source._inventory_rows()
    inventory["SOLD"].update({
        "open_qty": 3, "pnfm_qty": 0, "inbound_progress_qty": 5,
        "inbound_completed_qty": 999, "incoming_qty": 8,
        "unit_price_local": 0.75, "unit_price_krw": 1200,
    })
    rows, _ = source.build_order_logic_v3_source(as_of="2026-08-31", entity_code=entity_code)
    row = next(row for row in rows if row["sku_code"] == "SOLD")
    assert row["inventory_breakdown"] == {
        "open_po_qty": 3, "pnfm_qty": 0, "inbound_progress_qty": 5, "inbound_completed_qty": 999,
    }
    assert row["replenishment"].unreceived_qty == 8
    assert row["unit_price_local"] == 0.75
    assert row["unit_price_krw"] == 1200
    missing = next(row for row in rows if row["sku_code"] == "NO-SALES")
    assert missing["inventory_breakdown"]["pnfm_qty"] is None


def test_v3_source_connects_eta_from_same_inventory_snapshot(source_case, monkeypatch):
    source_case("PL")
    inventory, _, _ = source._inventory_rows()
    inventory["SOLD"]["transit_qty"] = 12
    monkeypatch.setattr(source, "fetch_cached_cms_inventory_raw_data", lambda **_: ({
        "shipping": [{"prod_cd": "SOLD", "qty": 12, "eta_dt": "2026-09-03", "cust_nm": "SKO Sp. z o.o."}],
    }, {}, ()))
    rows, _ = source.build_order_logic_v3_source(as_of="2026-08-31", entity_code="PL")
    row = next(row for row in rows if row["sku_code"] == "SOLD")
    assert row["shipping_source_status"] == "AVAILABLE"
    assert row["shipping_eta_details"][0]["eta"] == "2026-09-03"
    assert row["shipping_eta_details"][0]["qty"] == row["replenishment"].in_transit_qty == 12


@pytest.mark.parametrize("entity_code", ["HQ", "PL", "USA"])
@pytest.mark.parametrize("with_sales", [True, False])
def test_master_classification_survives_missing_or_filtered_sales(source_case, entity_code, with_sales):
    products, sales, combo, parent = source_case(entity_code, with_sales=with_sales)
    rows, meta = source.build_order_logic_v3_source(as_of="2026-08-31", entity_code=entity_code)
    by_sku = {row["sku_code"]: row for row in rows}

    assert set(by_sku) == {"SOLD", "NO-SALES", "PARENT", "FILTERED", "UNCLASSIFIED", "NO-MASTER"}
    assert "MASTER-ONLY" not in by_sku
    for sku in ("NO-SALES", "FILTERED"):
        row = by_sku[sku]
        assert row["source_function_class_1_code"] == "스킨케어"
        assert row["source_function_class_2_code"] == "패치"
        assert row["seasonal_profile"] == combo
        assert row["season_factor_blocking_reason_code"] is None
        assert row["daily_sales"] == {}
        assert row["first_sale_date"] is None
        assert row["barcode"] == "00012345"
    assert by_sku["NO-SALES"]["product_name"] == "마스터 상품명"
    assert by_sku["NO-SALES"]["brand"] == "TEST"
    assert by_sku["PARENT"]["source_function_class_2_code"] == source.UNMAPPED
    assert by_sku["PARENT"]["seasonal_profile"] == parent
    assert by_sku["PARENT"]["season_factor_application_reason_code"] == source.CLASS2_MISSING_USE_CLASS1_FACTOR
    for sku in ("UNCLASSIFIED", "NO-MASTER"):
        assert by_sku[sku]["season_factor_blocking_reason_code"] == "SEASON_FACTOR_MAPPING_MISSING"
    assert meta["classification_basis"] == "CURRENT_PRODUCT_MASTER_INDEPENDENT_OF_PAID_SALES"

    result = build_order_logic_v3_calculation_result(
        job_id="synthetic-classification", as_of="2026-08-31", entity_code=entity_code,
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
        sku_inputs=[OrderLogicV3SkuCalculationInput(**row) for row in rows],
        source_snapshot_id="synthetic", source_fetched_at="2026-08-31T00:00:00+00:00",
    )
    for scenario in ("CASH", "SHORTAGE"):
        result_rows = {row["sku_code"]: row for row in result["scenarios"][scenario]["rows"]}
        for sku in ("NO-SALES", "FILTERED", "PARENT"):
            row = result_rows[sku]
            assert row["reason_code"] == "DEMAND_HISTORY_INSUFFICIENT"
            assert row["data_status"] == "BLOCKED"
            assert row["function_class_1_code"] == "스킨케어"
            assert row["season_factor_available"] is True
            expected = parent if sku == "PARENT" else combo
            assert row["season_factors_by_month"] == {str(month): factor for month, factor in expected.factors_by_month.items()}
            assert row["seasonal_applied"] is False
            assert row["raw_order_quantity"] is None
            assert row["order_amount_krw"] is None
        for sku in ("UNCLASSIFIED", "NO-MASTER"):
            assert result_rows[sku]["season_factor_available"] is False
            assert result_rows[sku]["season_factors_by_month"] is None
        assert result_rows["SOLD"]["calculable"] is with_sales
        if with_sales:
            assert result_rows["SOLD"]["original_period_sales"] == list(range(20, 33))


@pytest.mark.parametrize("reason", ["SEASON_FACTOR_ARTIFACT_NOT_ACTIVE", "SEASON_FACTOR_ARTIFACT_INVALID", "SEASON_FACTOR_STALE", "SEASON_FACTOR_SOURCE_MISMATCH"])
def test_master_classification_does_not_override_artifact_failure(source_case, reason):
    source_case("USA", artifact_error=reason)
    rows, _ = source.build_order_logic_v3_source(as_of="2026-08-31", entity_code="USA")
    row = next(row for row in rows if row["sku_code"] == "NO-SALES")
    assert row["source_function_class_1_code"] == "스킨케어"
    assert row["source_function_class_2_code"] == "패치"
    assert row["season_factor_blocking_reason_code"] == reason
    if reason == "SEASON_FACTOR_SOURCE_MISMATCH":
        result = build_order_logic_v3_calculation_result(
            job_id="synthetic", as_of="2026-08-31", entity_code="USA",
            parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
            sku_inputs=[OrderLogicV3SkuCalculationInput(**row)],
            source_snapshot_id="synthetic", source_fetched_at="2026-08-31T00:00:00Z",
        )
        for scenario in ("CASH", "SHORTAGE"):
            blocked = result["scenarios"][scenario]["rows"][0]
            assert blocked["calculable"] is False
            assert blocked["reason_code"] == reason
            assert blocked["season_factor_version"] is None


def test_master_lookup_preserves_existing_normalization_and_duplicate_policy():
    products = [
        {"prod_cd": " SKU-A ", "prod_nm": None, "brand_nm": None, "class1": "01", "class1_nm": None, "class2_nm": "패치"},
        {"prod_cd": "SKU-A", "class1_nm": "네일", "class2_nm": None},
        {"prod_cd": "SKU-B", "class1_nm": None, "class2_nm": None},
    ]
    identities = source._product_master_identities(products)
    assert identities["SKU-A"] == ("", "", "스킨케어", "패치")
    assert identities["SKU-B"][2:] == (source.UNMAPPED, source.UNMAPPED)
    assert source._product_master_identities([]) == {}


@pytest.mark.parametrize("suffix", ["", "2.0"])
def test_hq_inventory_only_case_alias_reaches_adapter_and_hold_audit(source_case, monkeypatch, suffix):
    products, _sales, _combo, _parent = source_case("HQ", with_sales=False)
    canonical = "Named-Case" + suffix
    original = canonical.upper()
    products.append({"prod_cd": canonical, "prod_nm": "[시험] 50ml (신형)",
                     "class1_nm": "스킨케어", "class2_nm": "패치"})
    raw = {"products": products, "sales_history": [],
           "stock": [{"prod_cd": original, "prod_nm": "[시험] 50ml (신형)", "qty": 10}]}
    monkeypatch.setattr(source, "fetch_cached_hq_opo_raw_data", lambda **_: (raw, {}))

    def inventory_adapter(mapped, **kwargs):
        assert kwargs["entity_code"] == "HQ"
        assert mapped["stock"][0]["prod_cd"] == canonical
        assert raw["stock"][0]["prod_cd"] == original
        return {canonical: {"local_available_qty": 10}}, {}, {}

    monkeypatch.setattr(source, "_inventory_rows", inventory_adapter)
    rows, _meta = source.build_order_logic_v3_source(as_of="2026-08-31", entity_code="HQ")
    assert len(rows) == 1 and rows[0]["sku_code"] == canonical
    assert rows[0]["season_factor_blocking_reason_code"] is None
    result = build_order_logic_v3_calculation_result(
        job_id="synthetic", as_of="2026-08-31", entity_code="HQ",
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
        sku_inputs=[OrderLogicV3SkuCalculationInput(**rows[0])],
        source_snapshot_id="synthetic", source_fetched_at="2026-08-31T00:00:00Z",
    )
    for scenario in ("CASH", "SHORTAGE"):
        row = result["scenarios"][scenario]["rows"][0]
        assert row["reason_code"] == "DEMAND_HISTORY_INSUFFICIENT"
        assert row["product_identity_source_codes"] == [original]
        assert row["season_factor_available"] is True


@pytest.mark.parametrize("entity", ["USA", "PL", "HQ"])
def test_explicit_sku_scope_filters_source_and_both_scenarios_without_changing_other_rows(
    source_case, monkeypatch, entity,
):
    products, sales, _, _ = source_case(entity)
    # Cover a sales-only SKU as well as inventory-only candidates. Every value
    # is synthetic; operational identifiers belong only in policy configuration.
    sales.append({**sales[0], "prod_cd": "SALES-ONLY"})
    inventory, _, _ = source._inventory_rows()
    original = deepcopy((products, sales, inventory))
    baseline, baseline_meta = source.build_order_logic_v3_source(as_of="2026-08-31", entity_code=entity)
    excluded = frozenset({"NO-SALES", "PARENT", "SALES-ONLY"})
    monkeypatch.setattr(source, "_V3_EXCLUDED_SKUS_BY_ENTITY", {"USA": excluded})
    rows, meta = source.build_order_logic_v3_source(as_of="2026-08-31", entity_code=entity)
    expected = [row for row in baseline if entity != "USA" or row["sku_code"] not in excluded]
    assert rows == expected  # Includes grades, demand, inventory, price and profiles.
    assert (products, sales, inventory) == original
    assert meta["sku_scope"]["excluded_sku_count"] == (3 if entity == "USA" else 0)
    assert meta["source_counts"] == baseline_meta["source_counts"]
    if entity == "USA":
        assert meta["snapshot_id"] != baseline_meta["snapshot_id"]

    def calculate(inputs):
        return build_order_logic_v3_calculation_result(
            job_id="synthetic-sku-scope", as_of="2026-08-31", entity_code=entity,
            parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
            sku_inputs=[OrderLogicV3SkuCalculationInput(**row) for row in inputs],
            source_snapshot_id="synthetic", source_fetched_at="2026-08-31T00:00:00Z",
        )

    result, baseline_result = calculate(rows), calculate(baseline)
    for scenario in ("CASH", "SHORTAGE"):
        expected_results = [
            row for row in baseline_result["scenarios"][scenario]["rows"]
            if entity != "USA" or row["sku_code"] not in excluded
        ]
        assert result["scenarios"][scenario]["rows"] == expected_results
    assert result["rows"] == result["scenarios"]["SHORTAGE"]["rows"]
    assert result["summary"]["total_sku_count"] == len(expected)
