from copy import deepcopy
from dataclasses import replace
from datetime import date

import pytest

from backend.cms_mapping import _shipping_frame
from backend.services.order_logic_v2_source import _shipping_rows_for_entity, _shipping_schedule_by_sku
from backend.services.order_logic_v3_shipping import build_shipping_reference_source
from core.order_logic_v2 import DEFAULT_CONFIG
from core.order_logic_v3_reference import shipping_reference_metrics


def _audit(entity):
    if entity == "PL":
        # PL orders both scenarios by RAIL (2026-09-08); the measured SEA mean
        # only survives in the aggregation source for the ETA resolver.
        return {
            "scenarios": {
                "CASH": {"transport_mode": "RAIL", "lead_time_days": 7.5},
                "SHORTAGE": {"transport_mode": "RAIL", "lead_time_days": 7.5},
            },
            "source": {"modes": {"SEA": {"mean_days": 14, "sample_size": 10}}},
        }
    return {"scenarios": {
        "CASH": {"transport_mode": "AIR", "lead_time_days": 7.5},
        "SHORTAGE": {"transport_mode": "SEA", "lead_time_days": 14},
    }}


def _build(rows, entity="PL"):
    return build_shipping_reference_source({"shipping": rows}, entity_code=entity, lead_time_audit=_audit(entity))


def test_eta_source_wins_and_pl_unmeasured_air_uses_v2_default():
    base = {"cust_nm": "SKO Sp. z o.o.", "prod_cd": "Case", "qty": 10, "ship_dt": "2026-08-24"}
    rows = [{**base, "eta_dt": "2026-09-03", "remark": "RAIL"},
            {**base, "remark": "RAIL"}, {**base, "remark": "AIR"},
            {**base, "prod_cd": "case", "remark": "SEA"},
            {**base, "cust_nm": "OTHER", "qty": 999}]
    details, invalid, status = _build(rows)
    assert status == "AVAILABLE" and not invalid
    assert len(details["Case"]) == 3 and len(details["case"]) == 1
    assert details["Case"][0]["eta"] == "2026-09-03"
    assert details["Case"][0]["lead_time_days"] is None
    assert details["Case"][1]["eta"] == "2026-08-31"
    assert details["Case"][1]["lead_time_days"] == 7.5
    assert details["Case"][2]["eta"] == "2026-09-09"
    assert details["Case"][2]["lead_time_days"] == DEFAULT_CONFIG.lt_air_days
    assert details["case"][0]["eta"] == "2026-09-07"


def test_missing_invalid_and_hq_shipping_stay_distinct():
    assert build_shipping_reference_source({}, entity_code="PL", lead_time_audit={})[2] == "UNAVAILABLE"
    assert _build([])[2] == "AVAILABLE"
    assert _build([], entity="HQ")[2] == "NOT_APPLICABLE"
    details, invalid, _ = _build([{"prod_cd": "BAD", "qty": None}], entity="USA")
    assert invalid == {"BAD"} and not details


@pytest.mark.parametrize("entity", ["PL", "USA"])
def test_v3_eta_details_and_week_buckets_match_v2_without_mutating_source(entity):
    base = {"cust_nm": "SKO Sp. z o.o.", "prod_cd": "Case.0", "qty": 10, "ship_dt": "2026-08-24"}
    rows = [{**base, "eta_dt": eta, "qty": qty, "remark": "SEA"} for eta, qty in [
        ("2026-08-30", 1), ("2026-08-31", 2), ("2026-09-06", 3),
        ("2026-09-07", 4), ("2026-11-29", 5), ("2026-11-30", 6),
    ]]
    rows += [
        {**base, "qty": 7, "ship_dt": None},
        {**base, "prod_cd": "case.0", "remark": "AIR"},
        {**base, "prod_cd": "RAIL-ONLY", "remark": "RAIL"},
        {**base, "prod_cd": "REMARK-ETA", "remark": "AIR ETA 9/7"},
        {**base, "prod_cd": "OTHER", "cust_nm": "OTHER CUSTOMER", "remark": "SEA"},
        {**base, "qty": 0, "eta_dt": "2020-01-01"},
    ]
    raw = {"shipping": rows}
    before = deepcopy(raw)
    config = replace(DEFAULT_CONFIG, lt_sea_days=14, **{
        "lt_rail_days" if entity == "PL" else "lt_air_days": 7.5,
    })
    selected = _shipping_rows_for_entity(rows, entity_code=entity)
    v2 = _shipping_schedule_by_sku(_shipping_frame(selected, entity_code=entity), config=config, entity_code=entity)
    v3, invalid, status = build_shipping_reference_source(raw, entity_code=entity, lead_time_audit=_audit(entity))
    assert raw == before
    assert status == "AVAILABLE" and not invalid
    assert v3.keys() == v2.details.keys()
    for sku, details in v3.items():
        assert details == [{key: item[key] for key in details[0]} for item in v2.details[sku]]
    assert "Case.0" in v3 and "case.0" in v3 and "Case" not in v3
    assert ("OTHER" in v3) is (entity == "USA")
    assert v3["RAIL-ONLY"][0]["lead_time_days"] == config.lt_rail_days
    assert v3["REMARK-ETA"][0]["eta"] == ("2026-09-07" if entity == "USA" else "2026-09-09")
    metrics = shipping_reference_metrics(v3["Case.0"], as_of=date(2026, 9, 2), source_status=status, in_transit_qty=28)
    assert metrics["eta_bucket_quantities"] == [1, 5, 4] + [0] * 10 + [5, 6]
    assert metrics["eta_missing_qty"] == v2.review_qty["Case.0"] == 7
    assert metrics["next_eta"] == v2.schedules["Case.0"][0]["eta"] == "2026-08-30"


@pytest.mark.parametrize("entity", ["PL", "USA"])
def test_v3_uses_v2_remark_mode_even_when_transport_enrichment_disagrees(entity):
    raw = {
        "shipping": [{"cust_nm": "SKO Sp. z o.o.", "prod_cd": "TEST", "qty": 100,
                      "ship_dt": "2026-08-24", "remark": "AIR", "pckg_no": "TEST-PACK"}],
        "lead_time": [{"pckg_no": "TEST-PACK", "ship_via": "SYNTHETIC", "transport_mode": "해운"}],
    }
    details, _, status = build_shipping_reference_source(raw, entity_code=entity, lead_time_audit=_audit(entity))
    assert status == "AVAILABLE"
    assert details["TEST"][0]["transport_mode"] == "AIR"
    assert details["TEST"][0]["eta"] == ("2026-09-09" if entity == "PL" else "2026-08-31")


def test_usa_does_not_invent_eta_from_numbered_voyage_without_a_v2_remark_mode():
    details, _, _ = _build([{"prod_cd": "TEST", "qty": 5, "ship_dt": "2026-08-24",
                            "remark": "ME 12th"}], entity="USA")
    assert details["TEST"][0]["eta"] is None
    assert details["TEST"][0]["eta_status"] == "ETA 미확인"


@pytest.mark.parametrize("entity", ["PL", "USA"])
def test_missing_required_measurements_never_fall_back_to_v2_fixed_lead_times(entity):
    raw = {"shipping": [{"cust_nm": "SKO Sp. z o.o.", "prod_cd": "TEST", "qty": 5,
                         "ship_dt": "2026-08-24", "remark": "SEA"}]}
    details, invalid, status = build_shipping_reference_source(raw, entity_code=entity, lead_time_audit={})
    assert status == "UNAVAILABLE" and not details and not invalid


def test_invalid_quantities_keep_sku_guard_and_valid_duplicates_are_not_deduplicated():
    base = {"cust_nm": "SKO Sp. z o.o.", "prod_cd": "GOOD", "qty": 10,
            "ship_dt": "2026-08-24", "remark": "SEA"}
    details, invalid, status = _build([base, dict(base), {**base, "prod_cd": "BAD", "qty": -1}])
    assert status == "AVAILABLE" and invalid == {"BAD"}
    assert len(details["GOOD"]) == 2
    assert sum(item["qty"] for item in details["GOOD"]) == 20
