from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import fields, replace
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.schemas_order_logic_v3 import OrderLogicV3JobRequest
from backend.services.order_logic_v3_service import (
    LOGIC_VERSION,
    OrderLogicV3SkuCalculationInput,
    build_order_logic_v3_calculation_result,
    build_order_logic_v3_readiness_result,
)
from core.order_logic_v3 import (
    SALES_GRADE_CORE,
    SALES_GRADE_GENERAL,
    SeasonalProfile,
    V3ReplenishmentBaseInput,
    V3ReplenishmentPolicy,
    textbook_candidate_parameters,
)


TEXTBOOK_CREAM_SALES = [440, 460, 340, 340, 400, 320, 440, 360, 380, 400, 480, 340, 420]


@pytest.mark.parametrize("entity", ["PL", "USA"])
@pytest.mark.parametrize("open_qty,expected_qty,warning,invalid", [
    (None, 50, "INCOMING_QTY_NULL_AS_ZERO", False),
    (-5, 50, "INCOMING_QTY_NEGATIVE", True),
    (0, 50, None, False),
    (10, 60, None, False),
])
def test_v3_inherits_real_v2_inventory_validation(entity, open_qty, expected_qty, warning, invalid):
    from backend.services.order_logic_v3_source import _inventory_rows, _inventory_validation_state

    raw = {
        "stock_local": [{"prod_cd": "TEXTBOOK-CREAM-A", "avbl_qty": 100}],
        "stock_hq": [{"prod_cd": "TEXTBOOK-CREAM-A", "avbl_qty": 0}],
        "shipping": [], "sales_local": [], "sales_hq": [],
        "open_po": [{"prod_cd": "TEXTBOOK-CREAM-A", "open_qty": open_qty,
                     "pnfm_confirmed_qty": 20, "inbound_in_progress_qty": 30, "completed_qty": 99}],
    }
    original = deepcopy(raw)
    inventory, _, _ = _inventory_rows(raw, as_of="2026-08-31", entity_code=entity)
    current = inventory["TEXTBOOK-CREAM-A"]
    error, warnings = _inventory_validation_state(current, entity_code=entity)
    assert raw == original
    assert current["incoming_qty"] == expected_qty
    assert bool(error) is invalid
    assert (warning in warnings) if warning else not warnings
    source = _calculation_input(entity_code=entity)
    source = replace(source, unit_price_krw=1000,
                     replenishment=replace(source.replenishment, on_hand_qty=100, upstream_available_qty=0,
                                           in_transit_qty=0, unreceived_qty=current["incoming_qty"], holding_qty=0),
                     inventory_validation_error=error, inventory_warnings=warnings,
                     inbound_status_source_present=current["inbound_status_source_present"],
                     inventory_breakdown={"open_po_qty": current["open_qty"], "pnfm_qty": current["pnfm_qty"],
                                          "inbound_progress_qty": current["inbound_progress_qty"],
                                          "inbound_completed_qty": current["inbound_completed_qty"]})
    options = dict(job_id="synthetic-inventory", as_of="2026-08-31", entity_code=entity,
                   parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
                   source_snapshot_id="synthetic", source_fetched_at="2026-08-31T00:00:00Z")
    result = build_order_logic_v3_calculation_result(**options, sku_inputs=[source])
    baseline = None if invalid else build_order_logic_v3_calculation_result(
        **options, sku_inputs=[replace(source, inventory_warnings=())])
    for mode in ("CASH", "SHORTAGE"):
        row = result["scenarios"][mode]["rows"][0]
        assert row["inventory_warnings"] == list(warnings)
        assert row["inbound_status_source_present"] is True
        assert row["unreceived_qty"] == expected_qty
        assert row["inbound_completed_qty"] == 99  # display only
        if invalid:
            assert row["calculable"] is False
            assert row["data_status"] == "BLOCKED"
            assert row["reason_code"] == "V2_INVENTORY_INVALID"
            assert row["validation_error"] == error
            assert row["raw_order_quantity"] is None
            assert row["order_amount_krw"] is None
            assert row.get("inventory_position") is None
        else:
            assert row["calculable"] is True
            assert row["inventory_position"] == 100 + expected_qty
            assert row["raw_order_quantity"] == baseline["scenarios"][mode]["rows"][0]["raw_order_quantity"]
            assert row["order_amount_krw"] == row["final_order_quantity"] * 1000
        if open_qty is None:
            assert "0을 적용" in row["inventory_warning_messages"][0]
            assert sum("0을 적용" in value for value in result["warnings"]) == 1


@pytest.mark.parametrize("entity", ["HQ", "PL", "USA"])
def test_v3_inventory_error_blocks_only_affected_sku_before_forecast(monkeypatch, entity):
    from backend.services import order_logic_v3_service as service

    source = _calculation_input(entity_code=entity)
    invalid = replace(source, sku_code="SYNTHETIC-INVALID", inventory_validation_error="Synthetic V2 error",
                      inventory_warnings=("INCOMING_QTY_NEGATIVE",))
    original = service.calculate_v3_textbook_scenarios
    calls = []
    def calculate(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(service, "calculate_v3_textbook_scenarios", calculate)
    result = build_order_logic_v3_calculation_result(
        job_id="synthetic", as_of="2026-08-31", entity_code=entity,
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION), sku_inputs=[invalid, source],
        source_snapshot_id="synthetic", source_fetched_at="2026-08-31T00:00:00Z")
    assert len(calls) == 1
    for mode in ("CASH", "SHORTAGE"):
        bad, good = result["scenarios"][mode]["rows"]
        assert bad["calculable"] is False
        assert bad["raw_order_quantity"] is bad["order_amount_krw"] is None
        assert good["calculable"] is True
    assert result["summary"]["calculable_sku_count"] == 1


def test_v3_worker_passes_inventory_error_and_warning_to_result(monkeypatch):
    from backend.services import order_logic_v3_service as service, order_logic_v3_jobs as jobs, persistent_state
    from backend.services.order_logic_v3_result_store import is_paged_result, result_page

    monkeypatch.setattr(persistent_state, "enabled", lambda: False)
    monkeypatch.setattr(jobs, "_JOBS", {})
    monkeypatch.setattr(service, "_CANCEL_SIGNALS", {})
    monkeypatch.setattr(service, "write_audit_event", lambda *args, **kwargs: None)
    source = replace(
        _calculation_input(),
        cash_transport_mode="RAIL",
        shortage_transport_mode="SEA",
    )
    bad = replace(source, sku_code="SYNTHETIC-INVALID", inventory_validation_error="Synthetic V2 error",
                  inventory_warnings=("INCOMING_QTY_NEGATIVE",), inbound_status_source_present=False)
    warn = replace(source, inventory_warnings=("INCOMING_QTY_NULL_AS_ZERO",), inbound_status_source_present=True)
    source_rows = [{field.name: getattr(item, field.name) for field in fields(item)} for item in (bad, warn)]
    monkeypatch.setattr(service, "build_order_logic_v3_source", lambda **kwargs: (
        source_rows, {"snapshot_id": "synthetic", "fetched_at": "2026-08-31T00:00:00Z"}))
    body = {"entity_code": "PL", "as_of": "2026-08-31", "preview": True}
    job_id = jobs.create_order_logic_v3_job("synthetic-client", body)
    asyncio.run(service.run_order_logic_v3_job(job_id, "synthetic-client", body))
    job = jobs.get_order_logic_v3_job(job_id)
    assert job["status"] == "succeeded"
    delivered = (
        result_page(job_id, job["result"], offset=0, limit=250)
        if is_paged_result(job["result"])
        else job["result"]
    )
    for mode in ("CASH", "SHORTAGE"):
        invalid_row, warning_row = delivered["scenarios"][mode]["rows"]
        expected_transport_mode = "RAIL" if mode == "CASH" else "SEA"
        assert invalid_row["transport_mode"] == expected_transport_mode
        assert warning_row["transport_mode"] == expected_transport_mode
        assert invalid_row["reason_code"] == "V2_INVENTORY_INVALID"
        assert invalid_row["raw_order_quantity"] is invalid_row["order_amount_krw"] is None
        assert warning_row["calculable"] is True
        assert warning_row["inventory_warnings"] == ["INCOMING_QTY_NULL_AS_ZERO"]
        assert invalid_row["inbound_status_source_present"] is False
        assert warning_row["inbound_status_source_present"] is True


@pytest.mark.parametrize("entity", ["PL", "USA", "HQ"])
@pytest.mark.parametrize("present", [True, False, None])
def test_inbound_presence_is_display_metadata_only(entity, present):
    source = _calculation_input(entity_code=entity)
    source = replace(source, replenishment=replace(source.replenishment, unreceived_qty=0))
    options = dict(job_id="synthetic-presence", as_of="2026-08-31", entity_code=entity,
                   parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
                   source_snapshot_id="synthetic", source_fetched_at="2026-08-31T00:00:00Z")
    baseline = build_order_logic_v3_calculation_result(**options, sku_inputs=[source])
    result = build_order_logic_v3_calculation_result(
        **options, sku_inputs=[replace(source, inbound_status_source_present=present)])
    for mode in ("CASH", "SHORTAGE"):
        actual = dict(result["scenarios"][mode]["rows"][0])
        expected = dict(baseline["scenarios"][mode]["rows"][0])
        assert actual.pop("inbound_status_source_present") is present
        expected.pop("inbound_status_source_present")
        assert actual == expected


@pytest.mark.parametrize("entity,currency", [("PL", "EUR"), ("USA", "USD"), ("HQ", "KRW")])
def test_reference_metrics_and_source_buckets_do_not_change_v3_orders(entity, currency):
    source = _calculation_input(entity_code=entity)
    options = dict(
        job_id="reference-test", as_of="2026-08-31", entity_code=entity,
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
        source_snapshot_id="synthetic", source_fetched_at="2026-08-31T00:00:00Z",
    )
    baseline = build_order_logic_v3_calculation_result(**options, sku_inputs=[source])
    extended = replace(source, unit_price_krw=1200, unit_price_local=0.75,
                       shipping_source_status="AVAILABLE", shipping_eta_details=[
                           {"eta": "2026-09-01", "qty": 100}, {"eta": None, "qty": 50},
                       ],
                       inventory_breakdown={"open_po_qty": 10, "pnfm_qty": 20,
                                            "inbound_progress_qty": 30, "inbound_completed_qty": 40})
    result = build_order_logic_v3_calculation_result(**options, sku_inputs=[extended])
    expected_sales = sum(value for day, value in source.daily_sales.items() if date(2026, 6, 1) <= day <= date(2026, 8, 30))
    assert result["result_schema_version"] == 25
    for mode in ("CASH", "SHORTAGE"):
        row = result["scenarios"][mode]["rows"][0]
        original = baseline["scenarios"][mode]["rows"][0]
        for key in ("raw_order_quantity", "demand_per_period", "reorder_point", "target_stock", "inventory_position", "layer2"):
            assert row[key] == original[key]
        assert row["reference_sales_13w"] == expected_sales
        assert row["reference_monthly_sales_raw"] == expected_sales / 3
        assert row["reference_monthly_sales"] == round(expected_sales / 3)
        assert row["reference_weekly_sales"] == expected_sales / 13
        assert row["reference_weekly_sigma"] != row["forecast_sigma"]
        assert row["reference_logistics_moi"] is not None
        assert row["eta_reference_status"] == "PARTIAL"
        assert row["eta_bucket_quantities"] == [0, 100] + [0] * 13
        assert row["eta_missing_qty"] == 50
        assert row["next_eta"] == "2026-09-01"
        assert row["reference_order_slack_weeks"] == round(max(0, row["inventory_position"] - row["reorder_point"]) / row["reference_weekly_sales"], 1)
        assert row["open_po_qty"] == 10
        assert row["pnfm_qty"] == 20
        assert row["inbound_progress_qty"] == 30
        assert row["inbound_completed_qty"] == 40
        assert row["unreceived_qty"] == 60  # not bucket ①, and no double count of ④
        assert row["unit_price_krw"] == 1200
        assert row["unit_price_local"] == 0.75
        assert row["local_currency"] == currency
        assert row["order_amount_krw"] == row["final_order_quantity"] * 1200
        assert row["order_amount_local"] == row["final_order_quantity"] * (1200 if entity == "HQ" else 0.75)
    held = build_order_logic_v3_calculation_result(**options, sku_inputs=[replace(extended, daily_sales={})])["rows"][0]
    assert held["calculable"] is False
    assert held["raw_order_quantity"] is None
    assert held["order_amount_local"] is None
    assert held["reference_sales_13w"] == 0
    assert held["reference_monthly_sales"] == 0
    assert held["on_hand_qty"] == 320
    assert held["pnfm_qty"] == 20
    assert held["reference_order_at"] is None
    assert held["reference_early_warning_at"] is None
    assert held["eta_bucket_quantities"] == [0, 100] + [0] * 13


@pytest.mark.parametrize("entity", ["PL", "USA"])
def test_v2_resolved_eta_reaches_both_v3_scenarios_without_changing_orders(entity):
    from backend.services.order_logic_v3_shipping import build_shipping_reference_source

    source = _calculation_input(entity_code=entity)
    raw = {"shipping": [
        {"cust_nm": "SKO Sp. z o.o.", "prod_cd": source.sku_code, "qty": 100,
         "ship_dt": "2026-08-24", "remark": "SEA", "eta_dt": "2026-09-07"},
        {"cust_nm": "SKO Sp. z o.o.", "prod_cd": source.sku_code, "qty": 50,
         "ship_dt": "2026-08-24", "remark": "AIR"},
    ]}
    if entity == "PL":
        # PL orders both scenarios by RAIL (2026-09-08); SEA stays in the
        # measured aggregation source for the ETA resolver.
        audit = {
            "scenarios": {
                "CASH": {"transport_mode": "RAIL", "lead_time_days": 7.5},
                "SHORTAGE": {"transport_mode": "RAIL", "lead_time_days": 7.5},
            },
            "source": {"modes": {"SEA": {"mean_days": 14, "sample_size": 10}}},
        }
    else:
        audit = {"scenarios": {
            "CASH": {"transport_mode": "AIR", "lead_time_days": 7.5},
            "SHORTAGE": {"transport_mode": "SEA", "lead_time_days": 14},
        }}
    details, invalid, status = build_shipping_reference_source(raw, entity_code=entity, lead_time_audit=audit)
    assert not invalid
    options = dict(job_id="synthetic-v2-eta", as_of="2026-08-31", entity_code=entity,
                   parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
                   source_snapshot_id="synthetic", source_fetched_at="2026-08-31T00:00:00Z")
    source = replace(source, replenishment=replace(source.replenishment, in_transit_qty=150))
    baseline = build_order_logic_v3_calculation_result(**options, sku_inputs=[source])
    result = build_order_logic_v3_calculation_result(**options, sku_inputs=[
        replace(source, shipping_eta_details=details[source.sku_code], shipping_source_status=status),
    ])
    for mode in ("CASH", "SHORTAGE"):
        row = result["scenarios"][mode]["rows"][0]
        original = baseline["scenarios"][mode]["rows"][0]
        for key in ("raw_order_quantity", "demand_per_period", "reorder_point", "target_stock", "inventory_position", "layer2"):
            assert row[key] == original[key]
        assert row["eta_reference_status"] == "AVAILABLE"
        assert row["shipping_eta_details"] == details[source.sku_code]
        assert row["eta_bucket_quantities"] == ([0, 0, 150] if entity == "PL" else [0, 50, 100]) + [0] * 12
        assert row["eta_missing_qty"] == 0
        assert row["next_eta"] == ("2026-09-07" if entity == "PL" else "2026-08-31")


@pytest.mark.parametrize("entity", ["PL", "USA"])
def test_local_amount_scenarios_null_zero_and_authorization(entity):
    from backend.auth.amount_permissions import is_amount_field, sanitize_amount_data

    source = replace(_calculation_input(entity_code=entity), unit_price_krw=1200, unit_price_local=6.10)
    inputs = [
        source,
        replace(source, sku_code="MISSING-PRICE", unit_price_local=None),
        replace(source, sku_code="NO-ORDER", replenishment=replace(source.replenishment, on_hand_qty=100000)),
        replace(source, sku_code="ZERO-PRICE", unit_price_local=0),
        replace(source, sku_code="BLOCKED", inventory_validation_error="Synthetic inventory error"),
        replace(source, sku_code="LOCAL-ONLY", unit_price_krw=None),
    ]
    result = build_order_logic_v3_calculation_result(
        job_id="local-amount", as_of="2026-08-31", entity_code=entity,
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION), sku_inputs=inputs,
        source_snapshot_id="synthetic", source_fetched_at="2026-08-31T00:00:00Z",
    )
    original = deepcopy(result)
    assert is_amount_field("order_amount_local")
    sanitized = sanitize_amount_data(result)
    assert result == original
    for mode in ("CASH", "SHORTAGE"):
        normal, missing, no_order, free, blocked, local_only = result["scenarios"][mode]["rows"]
        assert normal["order_amount_local"] == normal["final_order_quantity"] * 6.10
        assert normal["order_amount_krw"] == normal["final_order_quantity"] * 1200
        assert missing["calculable"] is True
        assert missing["order_amount_local"] is None
        assert missing["raw_order_quantity"] == normal["raw_order_quantity"]
        assert no_order["raw_order_quantity"] == no_order["final_order_quantity"] == no_order["order_amount_local"] == 0
        assert free["order_amount_local"] == 0
        assert blocked["raw_order_quantity"] is blocked["order_amount_local"] is None
        assert local_only["order_amount_krw"] is None
        assert local_only["order_amount_local"] == normal["order_amount_local"]
        for row in sanitized["scenarios"][mode]["rows"]:
            assert "order_amount_local" not in row
            assert "unit_price_local" not in row
        assert sanitized["scenarios"][mode]["rows"][0]["raw_order_quantity"] == normal["raw_order_quantity"]
    assert all("order_amount_local" not in row for row in sanitized["rows"])
    assert result["scenarios"]["CASH"]["rows"][0]["z_value"] == pytest.approx(0.5244005127080409)
    assert result["scenarios"]["SHORTAGE"]["rows"][0]["z_value"] == pytest.approx(1.2815515655446008)


def test_entity_fixed_service_level_z_policies_stay_separated() -> None:
    options = dict(
        job_id="hq-fixed-z", as_of="2026-08-31",
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
        source_snapshot_id="synthetic", source_fetched_at="2026-08-31T00:00:00Z",
    )
    hq_source = _calculation_input(entity_code="HQ")
    hq_general = replace(hq_source, sku_code="HQ-GENERAL", sales_grade=SALES_GRADE_GENERAL)
    hq = build_order_logic_v3_calculation_result(
        **options, entity_code="HQ", sku_inputs=[hq_source, hq_general],
    )
    hq_cash = hq["scenarios"]["CASH"]["rows"]
    hq_shortage = hq["scenarios"]["SHORTAGE"]["rows"]
    assert [row["z_value"] for row in hq_shortage] == pytest.approx([0.8416212335729143, 0.5244005127080409])
    assert [row["z_value"] for row in hq_cash] == pytest.approx([0.2533471031357998, 0.0])
    assert hq_cash[1]["layer2_raw"] == 0.0
    assert hq_cash[1]["layer2"] == pytest.approx(hq_cash[1]["safety_stock_floor"])
    assert hq["z_policy"]["scope"] == "HQ_ONLY"
    assert hq["z_policy"]["zero_z_rule"].startswith("CASH/GENERAL Z=0")

    for entity in ("PL", "USA"):
        core = _calculation_input(entity_code=entity)
        general = replace(core, sku_code=f"{entity}-GENERAL", sales_grade=SALES_GRADE_GENERAL)
        result = build_order_logic_v3_calculation_result(
            **options, entity_code=entity, sku_inputs=[core, general],
        )
        shortage = [row["z_value"] for row in result["scenarios"]["SHORTAGE"]["rows"]]
        cash = [row["z_value"] for row in result["scenarios"]["CASH"]["rows"]]
        assert shortage == pytest.approx([1.2815515655446008, 0.8416212335729143])
        assert cash == pytest.approx([0.5244005127080409, 0.2533471031357998])
        assert result["z_policy"]["override_applied"] is True
        assert result["z_policy"]["policy_version"] == "PL_USA_FIXED_SERVICE_LEVELS_90_80_70_60"
        assert result["z_policy"]["service_levels"] == {
            "SHORTAGE": {"CORE": 0.90, "GENERAL": 0.80},
            "CASH": {"CORE": 0.70, "GENERAL": 0.60},
        }
        # HQ keeps its own approved levels; no cross-entity leakage.
        assert "zero_z_rule" not in result["z_policy"]


@pytest.mark.parametrize("username", ["adminmaster", "ia", "eu_manager", "bm1"])
def test_v3_job_response_exposes_amounts_to_order_analysis_accounts(username):
    from backend.auth.models import UserAccount
    from backend.services.order_logic_v3_service import payload_visible_to_user

    user = UserAccount(username=username, password_hash="synthetic", role="synthetic",
                       allowed_entities=("PL",), is_active=True, display_name="Synthetic", account_type="synthetic")
    row = {"sku_code": "TEST", "raw_order_quantity": 100, "order_amount_local": 610,
           "order_amount_krw": 100000, "unit_price_local": 6.10, "unit_price_krw": 1000}
    payload = {"status": "succeeded", "result": {"rows": [row], "scenarios": {
        "CASH": {"rows": [row]}, "SHORTAGE": {"rows": [row]},
    }}}
    original = deepcopy(payload)
    visible = payload_visible_to_user(payload, user)
    for rows in (visible["result"]["rows"], *(value["rows"] for value in visible["result"]["scenarios"].values())):
        assert rows[0]["raw_order_quantity"] == 100
        for key in ("order_amount_local", "order_amount_krw", "unit_price_local", "unit_price_krw"):
            assert key in rows[0]
    assert visible == payload
    visible["result"]["rows"][0]["raw_order_quantity"] = 999
    assert payload == original  # never redact or rewrite the cached source result


def _calculation_input(*, entity_code: str = "PL") -> OrderLogicV3SkuCalculationInput:
    oldest_start = date(2026, 5, 25)
    return OrderLogicV3SkuCalculationInput(
        sku_code="TEXTBOOK-CREAM-A",
        product_name="교과서 크림 A",
        brand="TEXTBOOK",
        barcode="0012345678905",
        daily_sales={
            oldest_start + timedelta(days=index * 7): float(value)
            for index, value in enumerate(TEXTBOOK_CREAM_SALES)
        },
        first_sale_date=oldest_start,
        seasonal_profile=SeasonalProfile(
            version="season-approved-test-v1",
            entity_code=entity_code,
            function_class_1_code="SKIN",
            function_class_2_code="CREAM",
            factors_by_month={month: 1.0 for month in range(1, 13)},
        ),
        replenishment=V3ReplenishmentBaseInput(
            order_date=date(2026, 8, 31),
            cash_policy=V3ReplenishmentPolicy(
                lead_time_days=28,
                review_days=28,
                sigma_lead_time_periods=0.1,
                safety_stock_floor_periods=2.0,
                safety_stock_cap_periods=13.0,
            ),
            shortage_policy=V3ReplenishmentPolicy(
                lead_time_days=28,
                review_days=28,
                sigma_lead_time_periods=0.1,
                safety_stock_floor_periods=2.0,
                safety_stock_cap_periods=13.0,
            ),
            on_hand_qty=320,
            upstream_available_qty=0,
            in_transit_qty=150,
            unreceived_qty=60,
            holding_qty=30,
        ),
        sales_grade=SALES_GRADE_CORE,
    )


def test_v3_web_result_uses_13_completed_calendar_periods_and_blocks_quantities():
    result = build_order_logic_v3_readiness_result(
        job_id="order3_test",
        as_of="2026-08-27",  # Thursday; latest completed Sunday is Aug 23.
        entity_code="PL",
    )

    assert result["status"] == "blocked"
    assert result["logic_version"] == LOGIC_VERSION
    assert result["period_start"] == "2026-05-25"
    assert result["period_end"] == "2026-08-23"
    assert result["period_count"] == 13
    assert result["period_days"] == 7
    assert result["duration_unit"] == "CALENDAR_DAY"
    assert result["observation_window_days"] == 91
    assert result["demand_grain"] == "WEEK_7D"
    assert result["demand_grain_days"] == 7
    assert result["date_basis"] == "SOURCE_CALENDAR_DATE"
    assert "timezone" not in result
    assert result["rows"] == []
    assert result["summary"]["final_order_quantity"] is None
    assert result["source_snapshot_id"] is None
    assert {item["code"] for item in result["blocking_contracts"]} >= {
        "SEASON_FACTOR_ARTIFACT_NOT_ACTIVE",
        "SALES_GRADE_SOURCE_PENDING",
    }
    assert "HIGH_CV2_SIGMA_POLICY_PENDING" not in {
        item["code"] for item in result["blocking_contracts"]
    }
    assert "INVENTORY_SOURCE_CONTRACT_PENDING" not in {
        item["code"] for item in result["blocking_contracts"]
    }


def test_usa_result_uses_source_calendar_date_without_timezone_blocker():
    result = build_order_logic_v3_readiness_result(
        job_id="order3_usa",
        as_of="2026-08-27",
        entity_code="USA",
    )

    assert result["date_basis"] == "SOURCE_CALENDAR_DATE"
    assert "timezone" not in result
    assert "USA_WAREHOUSE_TIMEZONE_PENDING" not in {
        item["code"] for item in result["blocking_contracts"]
    }


def test_v3_job_request_cannot_be_promoted_out_of_preview():
    assert OrderLogicV3JobRequest(as_of=date(2026, 8, 27)).preview is True
    with pytest.raises(ValidationError):
        OrderLogicV3JobRequest(as_of=date(2026, 8, 27), preview=False)


def test_v3_web_result_rejects_cross_entity_fallback():
    with pytest.raises(ValueError, match="적용 대상이 아닌 법인"):
        build_order_logic_v3_readiness_result(
            job_id="order3_invalid",
            as_of="2026-08-27",
            entity_code="JP",
        )


def test_v3_calculation_result_serializes_the_textbook_engine_for_both_scenarios():
    result = build_order_logic_v3_calculation_result(
        job_id="order3_calculated",
        as_of="2026-08-27",
        entity_code="PL",
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
        sku_inputs=[_calculation_input()],
        source_snapshot_id="snapshot-test-v1",
        source_fetched_at="2026-08-27T00:00:00+00:00",
    )

    shortage_row = result["scenarios"]["SHORTAGE"]["rows"][0]
    cash_row = result["scenarios"]["CASH"]["rows"][0]
    assert shortage_row["barcode"] == cash_row["barcode"] == "0012345678905"
    assert result["status"] == "success"
    assert result["duration_unit"] == "CALENDAR_DAY"
    assert result["date_basis"] == "SOURCE_CALENDAR_DATE"
    assert "timezone" not in result
    assert result["observation_window_days"] == 91
    assert result["demand_grain"] == "WEEK_7D"
    assert result["demand_grain_days"] == 7
    assert result["summary"] == {
        "total_sku_count": 1,
        "calculable_sku_count": 1,
        "blocked_sku_count": 0,
        "raw_order_quantity": pytest.approx(3_500.0, abs=0.05),
        # raw is fractionally above 3,500, so the 10-unit fallback ceils to 3,510.
        "final_order_quantity": pytest.approx(3_510.0),
    }
    assert shortage_row["original_period_sales"] == pytest.approx(TEXTBOOK_CREAM_SALES)
    assert shortage_row["adjusted_period_sales"] == pytest.approx(TEXTBOOK_CREAM_SALES)
    assert shortage_row["raw_order_quantity"] == pytest.approx(3_500.0, abs=0.05)
    assert cash_row["raw_order_quantity"] == pytest.approx(shortage_row["raw_order_quantity"])
    # PL/USA SHORTAGE x CORE uses the approved 90% service level (Z=1.2815515655).
    assert shortage_row["layer2_raw"] == pytest.approx(223.32, abs=0.02)
    assert shortage_row["layer2"] == pytest.approx(800.0, abs=0.01)
    assert shortage_row["safety_stock_floor_periods"] == pytest.approx(2.0)
    assert shortage_row["lead_time_days"] == pytest.approx(28)
    assert shortage_row["lead_time_weeks"] == pytest.approx(4)
    assert shortage_row["lead_time_periods"] == pytest.approx(4)
    assert shortage_row["review_days"] == pytest.approx(28)
    assert shortage_row["review_weeks"] == pytest.approx(4)
    assert shortage_row["review_periods"] == pytest.approx(4)
    assert shortage_row["sigma_lead_time_days"] == pytest.approx(0.7)
    assert shortage_row["sigma_lead_time_weeks"] == pytest.approx(0.1)
    assert shortage_row["safety_stock_floor_days"] == pytest.approx(14)
    assert shortage_row["safety_stock_floor_weeks"] == pytest.approx(2)
    assert shortage_row["upstream_available_qty"] == 0
    assert shortage_row["season_factor_version"] == "season-approved-test-v1"
    assert shortage_row["first_sale_date"] == "2026-05-25"
    assert shortage_row["analysis_sales_cutoff"] == "2026-08-23"
    assert shortage_row["calendar_days_since_first_sale"] == 90
    assert shortage_row["is_new_sku"] is True
    # No inbox/outbox pack on this fixture: the approved ladder falls back to
    # 10-unit ceiling. 3,500 is already a multiple of 10.
    assert shortage_row["order_unit_source"] == "FALLBACK_10"
    assert shortage_row["order_unit_quantity"] == pytest.approx(10.0)
    assert shortage_row["final_order_quantity"] == pytest.approx(3_510.0)


def test_v3_api_row_serializes_new_sku_holt_damping_from_calendar_days() -> None:
    period_end = date(2026, 8, 23)
    oldest_start = date(2026, 5, 25)
    trend_sales = [280, 300, 330, 350, 350, 370, 390, 400, 420, 430, 440, 450, 480]
    source = replace(
        _calculation_input(),
        daily_sales={
            oldest_start + timedelta(days=index * 7): float(value)
            for index, value in enumerate(trend_sales)
        },
        first_sale_date=period_end - timedelta(days=168),
    )

    result = build_order_logic_v3_calculation_result(
        job_id="order3_new_sku_holt",
        as_of="2026-08-27",
        entity_code="PL",
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
        sku_inputs=[source],
        source_snapshot_id="snapshot-test-v1",
        source_fetched_at="2026-08-27T00:00:00+00:00",
    )

    row = result["rows"][0]
    assert row["engine"] == "HOLT_DAMPED"
    assert row["first_sale_date"] == "2026-03-08"
    assert row["analysis_sales_cutoff"] == "2026-08-23"
    assert row["calendar_days_since_first_sale"] == 168
    assert row["is_new_sku"] is True
    assert row["phi"] == pytest.approx(0.90)


def test_v3_calculation_keeps_cross_entity_factor_failure_on_the_sku_row():
    result = build_order_logic_v3_calculation_result(
        job_id="order3_factor_blocked",
        as_of="2026-08-27",
        entity_code="PL",
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
        sku_inputs=[_calculation_input(entity_code="HQ")],
        source_snapshot_id="snapshot-test-v1",
        source_fetched_at="2026-08-27T00:00:00+00:00",
    )

    row = result["rows"][0]
    assert result["status"] == "blocked"
    assert result["summary"]["total_sku_count"] == 1
    assert result["summary"]["blocked_sku_count"] == 1
    assert row["calculable"] is False
    assert row["reason_code"] == "SEASON_FACTOR_ENTITY_MISMATCH"
    assert row["season_factor_available"] is False
    assert row["season_factors_by_month"] is None
    assert row["barcode"] == "0012345678905"
    assert row["raw_order_quantity"] is None


def test_v3_calculation_blocks_failed_class_1_factor_for_missing_class_2() -> None:
    source = replace(
        _calculation_input(),
        source_function_class_1_code="선케어",
        source_function_class_2_code="미분류",
        season_factor_scope="FUNCTION_CLASS_1",
        season_factor_blocking_reason_code="SEASON_FACTOR_CALC_FAILED",
        season_factor_blocking_message="기능구분1 시즌팩터 계산에 실패했습니다.",
    )

    result = build_order_logic_v3_calculation_result(
        job_id="order3_class1_factor_blocked",
        as_of="2026-08-27",
        entity_code="PL",
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
        sku_inputs=[source],
        source_snapshot_id="snapshot-test-v1",
        source_fetched_at="2026-08-27T00:00:00+00:00",
    )

    row = result["rows"][0]
    assert result["status"] == "blocked"
    assert row["calculable"] is False
    assert row["reason_code"] == "SEASON_FACTOR_CALC_FAILED"
    assert row["season_factor_available"] is False
    assert row["season_factors_by_month"] is None
    assert row["function_class_1_code"] == "선케어"
    assert row["function_class_2_code"] == "미분류"
    assert row["season_factor_scope"] == "FUNCTION_CLASS_1"


def test_v3_calculation_audits_class_1_factor_applied_for_missing_class_2() -> None:
    source = replace(
        _calculation_input(),
        source_function_class_1_code="선케어",
        source_function_class_2_code="미분류",
        season_factor_scope="FUNCTION_CLASS_1",
        season_factor_application_reason_code="FUNCTION_CLASS2_MISSING_USE_CLASS1_FACTOR",
    )

    result = build_order_logic_v3_calculation_result(
        job_id="order3_class1_factor_applied",
        as_of="2026-08-27",
        entity_code="PL",
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
        sku_inputs=[source],
        source_snapshot_id="snapshot-test-v1",
        source_fetched_at="2026-08-27T00:00:00+00:00",
    )

    row = result["rows"][0]
    assert row["calculable"] is True
    assert row["function_class_1_code"] == "선케어"
    assert row["function_class_2_code"] == "미분류"
    assert row["season_factor_scope"] == "FUNCTION_CLASS_1"
    assert (
        row["season_factor_application_reason_code"]
        == "FUNCTION_CLASS2_MISSING_USE_CLASS1_FACTOR"
    )
    assert row["season_factor_function_class_1_code"] == "SKIN"
    assert row["season_factor_function_class_2_code"] == "CREAM"


@pytest.mark.parametrize("no_recent_sales", [False, True])
def test_default_one_preserves_sales_and_audit_without_removing_other_holds(no_recent_sales):
    source = _calculation_input()
    if no_recent_sales:
        source = replace(source, daily_sales={
            day: qty for day, qty in source.daily_sales.items() if day < date(2026, 6, 1)
        })
    source = replace(
        source,
        season_factor_application_reason_code="SEASON_FACTOR_CALC_FAILED_USE_DEFAULT_1",
        season_factor_original_reason_code="SEASON_FACTOR_CALC_FAILED",
        season_factor_original_message="zero monthly factor",
    )
    result = build_order_logic_v3_calculation_result(
        job_id="neutral-default-test", as_of="2026-08-27", entity_code="PL",
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
        sku_inputs=[source], source_snapshot_id="test", source_fetched_at="2026-08-27T00:00:00+00:00",
    )
    for scenario in ("CASH", "SHORTAGE"):
        row = result["scenarios"][scenario]["rows"][0]
        assert row["season_factor_original_message"] == "zero monthly factor"
        assert row["season_factor_application_reason_code"] == "SEASON_FACTOR_CALC_FAILED_USE_DEFAULT_1"
        assert row["season_factor_version"] == "season-approved-test-v1"
        assert row["season_factor_available"] is True
        assert row["season_factors_by_month"] == {str(month): 1.0 for month in range(1, 13)}
        if no_recent_sales:
            assert row["reason_code"] == "DEMAND_HISTORY_INSUFFICIENT"
            assert row["raw_order_quantity"] is None
        else:
            assert row["calculable"] is True
            assert row["adjusted_period_sales"] == row["original_period_sales"] == TEXTBOOK_CREAM_SALES
            assert row["seasonal_f1"] == row["seasonal_f2"] == row["seasonal_f_lr"] == 1.0
            assert row["raw_order_quantity"] is not None


def test_v3_api_does_not_hold_a_sku_only_for_three_recent_zero_weeks() -> None:
    oldest_start = date(2026, 5, 25)
    source = replace(
        _calculation_input(),
        daily_sales={
            oldest_start + timedelta(days=index * 7): float(value)
            for index, value in enumerate(TEXTBOOK_CREAM_SALES[:-3] + [0, 0, 0])
        },
    )

    result = build_order_logic_v3_calculation_result(
        job_id="order3_recent_sales_hold",
        as_of="2026-08-27",
        entity_code="PL",
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
        sku_inputs=[source],
        source_snapshot_id="snapshot-test-v1",
        source_fetched_at="2026-08-27T00:00:00+00:00",
    )

    row = result["rows"][0]
    assert result["status"] == "success"
    assert row["calculable"] is True
    assert row["reason_code"] is None
    assert row["engine"] == "HOLT_DAMPED"
    assert row["raw_order_quantity"] > 0


def test_v3_api_serializes_uncapped_croston_forecast() -> None:
    oldest_start = date(2026, 5, 25)
    intermittent_sales = [1000, 0, 0, 1000, 0, 0, 1000, 0, 0, 0, 10, 20, 30]
    source = replace(
        _calculation_input(),
        daily_sales={
            oldest_start + timedelta(days=index * 7): float(value)
            for index, value in enumerate(intermittent_sales)
        },
    )

    result = build_order_logic_v3_calculation_result(
        job_id="order3_croston_cap",
        as_of="2026-08-27",
        entity_code="PL",
        parameters=textbook_candidate_parameters(logic_version=LOGIC_VERSION),
        sku_inputs=[source],
        source_snapshot_id="snapshot-test-v1",
        source_fetched_at="2026-08-27T00:00:00+00:00",
    )

    row = result["rows"][0]
    assert row["engine"] == "CROSTON_SBA"
    assert row["demand_per_period"] > 40
    assert row["croston_forecast_cap_per_period"] is None
    assert row["croston_forecast_was_capped"] is False
