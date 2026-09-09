"""Case-only aliases require literal names, preserve suffixes and conserve quantities."""

from copy import deepcopy
from datetime import date, timedelta

import pandas as pd
import pytest

from backend.services import order_logic_v3_source as source
from backend.services.order_logic_v3_product_identity import (
    PRODUCT_IDENTITY_POLICY,
    PRODUCT_IDENTITY_REASON,
    ProductIdentityResolver,
)
from backend.services.order_logic_v3_service import (
    LOGIC_VERSION,
    OrderLogicV3SkuCalculationInput,
    build_order_logic_v3_calculation_result,
)
from core.order_logic_v3 import SeasonalProfile, V3ReplenishmentPolicy, textbook_candidate_parameters
from core.season_calendar import merge_sales_with_product_master


NAME = "[시험] 수분 크림 (신형) 50ml"
MASTER = {"prod_cd": "Test-A", "prod_nm": NAME, "brand_nm": "TEST", "class1_nm": "스킨케어", "class2_nm": "패치"}


@pytest.mark.parametrize("name", [
    None, "", "   ", " " + NAME, NAME + " ", NAME.replace("수분 크림", "수분  크림"),
    NAME.replace("수분 크림", "수분크림"), NAME.replace("(신형)", "신형"),
    NAME.replace("50ml", "50 ml"), NAME.replace("50ml", "50mL"),
    NAME.replace("50ml", "0.05L"), NAME.replace("50ml", "100ml"),
    NAME.replace("[시험]", "시험"), NAME.replace("(신형)", "（신형）"),
    NAME.replace(" ", "\u00a0"), NAME + ".", NAME.replace(" ", "\t"),
])
def test_case_alias_rejects_any_name_difference_or_missing_name(name):
    row = {"prod_cd": "TEST-A", "prod_nm": name}
    resolver = ProductIdentityResolver.build([MASTER], [[row]])
    assert resolver.aliases == {}
    assert "TEST-A" in resolver.rejected
    assert resolver.rewrite_rows([row]) == [row]


def test_verified_alias_is_copied_without_changing_rows_or_inventing_deduplication():
    rows = [{"prod_cd": "TEST-A", "prod_nm": NAME, "qty": 5}] * 2
    nameless = {"prod_cd": "TEST-A", "qty": 7}
    payload = {"shipping": rows, "open_po": [nameless], "products": [MASTER]}
    original = deepcopy(payload)
    resolver = ProductIdentityResolver.build([MASTER], [rows, [nameless]])
    result = resolver.rewrite_payload(payload)
    assert resolver.aliases == {"TEST-A": "Test-A"}
    assert [r["prod_cd"] for r in result["shipping"]] == ["Test-A", "Test-A"]
    assert sum(r["qty"] for r in result["shipping"]) == 10
    assert result["open_po"][0] == {"prod_cd": "Test-A", "qty": 7}
    assert result["products"] == [MASTER]
    assert payload == original
    assert resolver.source_codes_by_target() == {"Test-A": ["TEST-A"]}


def test_different_codes_and_dot_zero_suffix_are_not_case_aliases():
    products = [MASTER, {"prod_cd": "Test2.0", "prod_nm": NAME}]
    rows = [{"prod_cd": c, "prod_nm": NAME} for c in ("TEST-B", "Test2", "TEST-A")]
    resolver = ProductIdentityResolver.build(products, [rows])
    assert resolver.aliases == {"TEST-A": "Test-A"}
    assert [r["prod_cd"] for r in resolver.rewrite_rows(rows)] == ["TEST-B", "Test2", "Test-A"]


def test_ambiguous_master_or_conflicting_names_across_sources_never_merge():
    row = {"prod_cd": "TEST-A", "prod_nm": NAME}
    ambiguous = ProductIdentityResolver.build([MASTER, {**MASTER, "prod_cd": "test-a"}], [[row]])
    assert not ambiguous.aliases
    assert ambiguous.rejected["TEST-A"] == "AMBIGUOUS_MASTER_CODE"
    assert ProductIdentityResolver.build([MASTER, MASTER], [[row]]).aliases
    conflicting = ProductIdentityResolver.build([MASTER, {**MASTER, "prod_nm": NAME + " "}], [[row]])
    assert not conflicting.aliases
    assert conflicting.rejected["TEST-A"] == "MISSING_OR_CONFLICTING_MASTER_NAME"
    source_conflict = ProductIdentityResolver.build([MASTER], [[row], [{**row, "prod_nm": NAME + " "}]])
    assert not source_conflict.aliases
    assert source_conflict.rejected["TEST-A"] == "SOURCE_NAME_MISMATCH_OR_CONFLICT"
    products = [MASTER, {**MASTER, "prod_cd": "test-a", "class1_nm": "바디"}]
    classification_conflict = ProductIdentityResolver.build(products, [[row]])
    assert not classification_conflict.aliases
    assert classification_conflict.rewrite_products(products) == products
    sales = [{**row, "qty": 10, "amount": 100, "ship_dt": "2026-08-30", "biz_type": "US-DOMESTIC"}]
    demand = source._paid_demand(sales, products, entity_code="USA")
    assert len(demand) == 1 and demand.iloc[0][source.QTY_COL] == 10
    assert demand.iloc[0][source.CATEGORY1_COL] == source.UNMAPPED


def test_exact_master_code_preserves_existing_contract_even_with_a_different_name():
    row = {"prod_cd": "Test-A", "prod_nm": "이전 상품명"}
    resolver = ProductIdentityResolver.build([MASTER], [[row]])
    assert not resolver.aliases and not resolver.rejected
    assert resolver.rewrite_rows([row]) == [row]


def test_common_sales_mapping_stays_case_sensitive_but_v3_joins_named_aliases():
    rows = [{"prod_cd": "TEST-A", "prod_nm": NAME, "qty": 10, "amount": 100,
             "ship_dt": "2026-08-30", "biz_type": "US-DOMESTIC"}]
    legacy = merge_sales_with_product_master(pd.DataFrame(rows), pd.DataFrame([MASTER]), entity_code="USA")
    assert legacy.iloc[0][source.PRODUCT_CODE_COL] == "TEST-A"
    assert legacy.iloc[0][source.CATEGORY1_COL] == source.UNMAPPED
    v3 = source._paid_demand(rows, [MASTER], entity_code="USA")
    assert v3.iloc[0][source.PRODUCT_CODE_COL] == "Test-A"
    assert v3.iloc[0][source.CATEGORY1_COL] == "스킨케어"
    assert rows[0]["prod_cd"] == "TEST-A"


@pytest.mark.parametrize("entity", ["PL", "USA"])
@pytest.mark.parametrize("suffix", ["", "2.0"])
def test_real_inventory_sales_eta_and_api_share_one_canonical_product(monkeypatch, entity, suffix):
    sales = [
        {"prod_cd": code, "prod_nm": NAME, "qty": qty, "amount": qty * 100,
         "amount_krw_actual": qty * 100,
         "ship_dt": (date(2026, 6, 1) + timedelta(days=7 * i)).isoformat(),
         "biz_type": "EU-PL" if entity == "PL" else "US-DOMESTIC"}
        for i in range(13) for code, qty in (("TEST-A", 10), ("test-a", 5))
    ]
    stock = lambda code, qty: {"prod_cd": code, "prod_nm": NAME, "avbl_qty": qty,
                              "unit_cost_krw": 100, "bar_code": "000001", "brand_nm": "TEST"}
    raw = {
        "stock_local": [stock("TEST-A", 20), stock("test-a", 30)],
        "stock_hq": [stock("Test-A", 10)],
        "shipping": [{"prod_cd": code, "prod_nm": NAME, "qty": qty,
                      "cust_nm": "SKO Sp. z o.o." if entity == "PL" else "Stylekorean Inc.",
                      "eta_dt": "2026-09-03", "ship_dt": "2026-08-24", "remark": "SEA"}
                     for code, qty in (("TEST-A", 7), ("Test-A", 3))],
        "open_po": [{"prod_cd": code, "prod_nm": NAME, "open_qty": qty,
                     "pnfm_confirmed_qty": pnfm, "inbound_in_progress_qty": progress,
                     "completed_qty": 9}
                    for code, qty, pnfm, progress in (("TEST-A", 4, 1, 2), ("test-a", 6, 3, 4))],
        "sales_local": [], "sales_hq": [],
    }
    master = {**MASTER, "prod_cd": MASTER["prod_cd"] + suffix}
    canonical = master["prod_cd"]
    variants = sorted([canonical.upper(), canonical, canonical.lower()])
    for records in [sales, *raw.values()]:
        for record in records:
            record["prod_cd"] += suffix
    originals = deepcopy((raw, sales))
    baseline, _, _ = source._inventory_rows(raw, as_of="2026-08-31", entity_code=entity)
    assert set(variants) == set(baseline)
    policy = V3ReplenishmentPolicy(lead_time_days=28, review_days=28, sigma_lead_time_periods=0.1,
                                 safety_stock_floor_periods=0.5, safety_stock_cap_periods=2)
    profile = SeasonalProfile(version="synthetic", entity_code=entity, function_class_1_code="스킨케어",
                              function_class_2_code="패치", factors_by_month={m: 1 for m in range(1, 13)})
    catalog = source._SeasonalProfileCatalog(by_class_1_and_2={("스킨케어", "패치"): profile},
                                           by_class_1={}, class_1_and_2_errors={}, class_1_errors={}, identities={})
    monkeypatch.setattr(source, "fetch_cached_cms_inventory_raw_data", lambda **_: (raw, {}, ()))
    monkeypatch.setattr(source, "fetch_cached_season_trend_source_data", lambda **_: ({"sales_history": sales, "prod_list": [master]}, {}))
    monkeypatch.setattr(source, "fetch_v3_ledger_sales", lambda **_: ([
        {**row, "ledger_dt": row["ship_dt"], "qty_out": row["qty"], "ledger_type_nm": "OUT-SALE"}
        for row in sales
    ], {"sha256": "synthetic-ledger"}))
    monkeypatch.setattr(source, "_load_active_profile_catalog", lambda _: (catalog, {"version": "synthetic"}))
    # Keep the synthetic measured-mode audit consistent with the policy
    # operands, as the real loader does. Missing audit must not be defaulted.
    lead_time_audit = {"source": {}, "scenarios": {
        "CASH": {"transport_mode": "RAIL" if entity == "PL" else "AIR", "lead_time_days": policy.lead_time_days},
        "SHORTAGE": {"transport_mode": "SEA", "lead_time_days": policy.lead_time_days},
    }}
    monkeypatch.setattr(source, "_measured_replenishment_policies", lambda **_: (policy, policy, lead_time_audit))
    rows, meta = source.build_order_logic_v3_source(as_of="2026-08-31", entity_code=entity)
    assert len(rows) == 1
    row = rows[0]
    assert row["sku_code"] == canonical
    assert list(row["daily_sales"].values()) == [15] * 13
    # The 91-day web window cannot prove a lifetime first sale.  Keep this
    # trace unavailable rather than mislabeling the earliest fetched row.
    assert row["first_sale_date"] is None
    assert row["replenishment"].on_hand_qty == 50
    assert row["replenishment"].upstream_available_qty == 10
    assert row["replenishment"].in_transit_qty == 10
    assert row["replenishment"].unreceived_qty == 20
    assert row["inventory_breakdown"] == {"open_po_qty": 10, "pnfm_qty": 4,
                                          "inbound_progress_qty": 6, "inbound_completed_qty": 18}
    assert sum(r["qty"] for r in row["shipping_eta_details"]) == 10
    assert [(r["eta"], r["qty"]) for r in row["shipping_eta_details"]] == [
        ("2026-09-03", 7), ("2026-09-03", 3),
    ]
    assert row["season_factor_blocking_reason_code"] is None
    assert meta["product_identity"]["matched_alias_count"] == 2
    assert (raw, sales) == originals
    result = build_order_logic_v3_calculation_result(
        job_id="synthetic", as_of="2026-08-31", entity_code=entity,
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
        sku_inputs=[OrderLogicV3SkuCalculationInput(**row)],
        source_snapshot_id=meta["snapshot_id"], source_fetched_at=meta["fetched_at"],
    )
    for scenario in ("CASH", "SHORTAGE"):
        calculated = result["scenarios"][scenario]["rows"][0]
        assert calculated["calculable"] is True
        assert calculated["original_period_sales"] == [15] * 13
        assert calculated["inventory_position"] == 90
        assert calculated["product_identity_source_codes"] == variants
        assert calculated["product_identity_reason_code"] == PRODUCT_IDENTITY_REASON
        assert calculated["eta_reference_status"] == "AVAILABLE"
        assert calculated["next_eta"] == "2026-09-03"
        assert calculated["eta_bucket_quantities"] == [0, 10] + [0] * 13
        assert calculated["eta_missing_qty"] == 0


@pytest.mark.parametrize("suffix", ["", "2.0"])
@pytest.mark.parametrize("name_suffix", ["", " "])
def test_monthly_candidate_uses_same_alias_contract_and_stores_no_sku_audit(monkeypatch, suffix, name_suffix):
    from backend.services import order_logic_v3_season_factor_service as service

    sales = [{"prod_cd": code, "prod_nm": NAME, "qty": 10, "amount": 100,
              "ship_dt": f"{year}-{month:02}-15", "biz_type": "US-DOMESTIC"}
             for year in (2024, 2025) for month in range(1, 13) for code in ("TEST-A", "Test-A")]
    master = {**MASTER, "prod_cd": MASTER["prod_cd"] + suffix}
    for row in sales:
        row["prod_cd"] += suffix
        if row["prod_cd"] == "TEST-A" + suffix:
            row["prod_nm"] += name_suffix
    monkeypatch.setattr(service, "fetch_v3_ledger_sales", lambda **_: ([
        {**row, "ledger_dt": row["ship_dt"], "qty_out": row["qty"], "ledger_type_nm": "OUT-SALE"}
        for row in sales
    ], {"sha256": "synthetic-ledger", "scope": {}, "included_types": sorted(source.SALE_TYPES)}))
    monkeypatch.setattr(service, "_fetch_cached_product_master", lambda **_: ([master], {}))
    real_profiles = service._profiles

    def check_profiles(demand, *args, **kwargs):
        expected = {master["prod_cd"], "TEST-A" + suffix} if name_suffix else {master["prod_cd"]}
        assert set(demand[source.PRODUCT_CODE_COL]) == expected
        assert len(demand) == 48
        assert demand[source.QTY_COL].sum() == 480
        return real_profiles(demand, *args, **kwargs)

    monkeypatch.setattr(service, "_profiles", check_profiles)
    monkeypatch.setattr(service, "save_candidate_and_auto_activate", lambda candidate: candidate)
    result = service.refresh_order_logic_v3_season_factors(as_of="2026-01-31", entity_code="USA")
    assert result["source_request"]["product_identity"] == {
        "policy": PRODUCT_IDENTITY_POLICY,
        "matched_alias_count": 0 if name_suffix else 1,
        "rejected_alias_count": 1 if name_suffix else 0,
    }
    assert "Test-A" not in str(result["source_request"])


def test_literal_suffix_does_not_merge_distinct_text_or_numeric_product_codes():
    codes = ("Test2", "Test2.0", "123", "123.0")
    products = [{**MASTER, "prod_cd": code} for code in codes]
    sales = [{"prod_cd": code.upper(), "prod_nm": NAME, "qty": qty, "amount": 100,
              "ship_dt": "2026-08-30", "biz_type": "US-DOMESTIC"}
             for qty, code in enumerate(codes, 1)]
    v3 = source._paid_demand(sales, products, entity_code="USA")
    assert dict(zip(v3[source.PRODUCT_CODE_COL], v3[source.QTY_COL])) == dict(zip(codes, (1, 2, 3, 4)))
    master = source._product_master_identities(products)
    assert set(master) == set(codes)
    legacy = merge_sales_with_product_master(pd.DataFrame(sales), pd.DataFrame(products), entity_code="USA")
    assert set(legacy[source.PRODUCT_CODE_COL]) == {"TEST2", "123"}


def test_master_missing_codes_remain_separate_without_verified_name_match():
    sales = [{"prod_cd": code, "qty": 5, "amount": 100,
              "ship_dt": "2026-08-30", "biz_type": "US-DOMESTIC"}
             for code in ("New2.0", "NEW2.0", "new2.0")]
    demand = source._paid_demand(sales, [], entity_code="USA")
    assert set(demand[source.PRODUCT_CODE_COL]) == {"NEW2.0", "New2.0", "new2.0"}
    assert demand[source.QTY_COL].sum() == 15
    assert set(demand[source.CATEGORY1_COL]) == {source.UNMAPPED}


@pytest.mark.parametrize("suffix", ["", "2.0"])
def test_one_space_difference_keeps_sales_and_inventory_separate(suffix):
    master = {**MASTER, "prod_cd": "Test-A" + suffix}
    canonical = master["prod_cd"]
    variant = canonical.upper()
    sales = [{"prod_cd": code, "prod_nm": name, "qty": qty, "amount": 100,
              "ship_dt": "2026-08-30", "biz_type": "US-DOMESTIC"}
             for code, name, qty in ((canonical, NAME, 10), (variant, NAME, 5))]
    raw = {"stock_local": [{"prod_cd": variant, "prod_nm": NAME + " ", "avbl_qty": 20}],
           "stock_hq": [], "shipping": [], "open_po": [], "sales_local": [], "sales_hq": []}
    resolver = ProductIdentityResolver.build([master], [sales, raw["stock_local"]])
    # Correct sales names cannot override a conflicting inventory name.
    assert not resolver.aliases
    assert resolver.rewrite_payload(raw) == raw
    demand = source._paid_demand(sales, [master], entity_code="USA", identity_resolver=resolver)
    assert dict(zip(demand[source.PRODUCT_CODE_COL], demand[source.QTY_COL])) == {canonical: 10, variant: 5}
    assert dict(zip(demand[source.PRODUCT_CODE_COL], demand[source.CATEGORY1_COL])) == {
        canonical: "스킨케어", variant: source.UNMAPPED,
    }


@pytest.mark.parametrize("master_name", [None, "", "   "])
def test_missing_master_name_cannot_validate_case_alias(master_name):
    resolver = ProductIdentityResolver.build([{**MASTER, "prod_nm": master_name}],
                                            [[{"prod_cd": "TEST-A", "prod_nm": NAME}]])
    assert not resolver.aliases
    assert resolver.rejected["TEST-A"] == "MISSING_OR_CONFLICTING_MASTER_NAME"


@pytest.mark.parametrize("suffix", ["", "2.0"])
@pytest.mark.parametrize("name_suffix", ["", " ", None])
def test_hq_native_sku_field_joins_inventory_po_and_inbound_only_after_exact_name_evidence(suffix, name_suffix):
    canonical = "Test-A" + suffix
    variant = canonical.upper()
    master = {**MASTER, "prod_cd": canonical}
    sales = [{"prod_cd": variant, "prod_nm": NAME + name_suffix if name_suffix is not None else None,
              "qty": 15, "amount_krw": 150, "ship_dt": "2026-08-30",
              "whouse_nm": "OPO", "biz_type": "KR-OVERSEAS"}]
    raw = {
        "products": [master], "sales_history": sales,
        "inventory": [{"sku": code, "available_qty": qty, "unit_cost": 10, "stock_status": "normal"}
                      for code, qty in ((variant, 20), (canonical, 30))],
        "open_po": [{"sku": variant, "remaining_qty": 2}],
        "inbound_confirmed": [{"sku": variant, "remaining_qty": 7, "pnfm_confirmed_qty": 3,
                               "inbound_in_progress_qty": 4, "completed_qty": 8}],
        "leadtime_stats": {"sample_count": 2, "avg_days": 10, "stddev_days": 2},
    }
    original = deepcopy(raw)
    resolver = ProductIdentityResolver.build([master], [sales, raw["inventory"], raw["open_po"], raw["inbound_confirmed"]])
    mapped = resolver.rewrite_payload(raw)
    inventory, _, _ = source._inventory_rows(mapped, as_of="2026-08-31", entity_code="HQ")
    if name_suffix == "":
        assert set(inventory) == {canonical}
        assert inventory[canonical]["local_available_qty"] == 50
        assert inventory[canonical]["incoming_qty"] == 9
        for feed in ("inventory", "open_po", "inbound_confirmed"):
            assert {row["sku"] for row in mapped[feed]} == {canonical}
    else:
        assert not resolver.aliases
        assert set(inventory) == {canonical, variant}
        assert inventory[variant]["local_available_qty"] == 20
        assert inventory[canonical]["local_available_qty"] == 30
    assert raw == original
