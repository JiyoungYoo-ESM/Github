from datetime import date, datetime, timedelta
from math import sqrt

import pytest

from core.order_logic_v3_reference import inventory_reference_metrics, sales_reference_metrics, shipping_reference_metrics


def test_reference_is_91_calendar_days_not_three_forecast_periods():
    values = {
        date(2026, 5, 31): 99999,  # immediately before the 91-day window
        date(2026, 6, 1): 600,    # inclusive first day
        date(2026, 8, 30): 700,   # inclusive completed Sunday
        date(2026, 8, 31): 99999, # incomplete week excluded
    }
    result = sales_reference_metrics(values, completed_sales_cutoff=date(2026, 8, 30))
    assert result["reference_sales_start"] == "2026-06-01"
    assert result["reference_sales_end"] == "2026-08-30"
    assert result["reference_sales_days"] == 91
    assert result["reference_sales_status"] == "AVAILABLE"
    assert result["reference_sales_13w"] == 1300
    assert result["reference_monthly_sales"] == 433
    assert result["reference_monthly_sales_raw"] == pytest.approx(1300 / 3)
    assert result["reference_monthly_sales"] != 1300 / 13 * 4
    assert result["reference_weekly_sales"] == 100
    assert len(values) == 4  # source stays unchanged


def test_successfully_loaded_empty_sales_are_zero_reference_sales():
    result = sales_reference_metrics({}, completed_sales_cutoff=date(2026, 8, 30))
    assert result["reference_sales_status"] == "AVAILABLE"
    assert result["reference_sales_13w"] == 0
    assert result["reference_monthly_sales"] == 0
    assert result["reference_weekly_sales"] == 0


@pytest.mark.parametrize("invalid", [-1, float("nan"), float("inf"), None])
def test_invalid_sales_are_not_silently_converted_to_zero(invalid):
    result = sales_reference_metrics({date(2026, 8, 30): invalid}, completed_sales_cutoff=date(2026, 8, 30))
    assert result["reference_sales_status"] == "INVALID_SOURCE"
    assert result["reference_sales_13w"] is None
    assert result["reference_monthly_sales"] is None
    assert result["reference_weekly_sales"] is None


def test_template_timing_example_uses_actual_weekly_sigma_and_unrounded_dates():
    weeks = [50, 150] * 6 + [100]
    sales = {date(2026, 6, 1) + timedelta(weeks=i): qty for i, qty in enumerate(weeks)}
    source = sales_reference_metrics(sales, completed_sales_cutoff=date(2026, 8, 30))
    assert source["reference_weekly_sales_history"] == weeks
    assert source["reference_weekly_sigma"] == 50
    row = {**source, "on_hand_qty": 500, "in_transit_qty": 100,
           "calculable": True, "inventory_position": 600, "reorder_point": 400,
           "z_value": 1.28, "forecast_sigma": 99999}
    result = inventory_reference_metrics(row, as_of=date(2026, 8, 31))
    conservative = ((sqrt((1.28 * 50) ** 2 + 4 * 100 * 200) - 1.28 * 50) / (2 * 100)) ** 2
    assert result["reference_moi"] == result["reference_logistics_moi"] == 1.4
    assert result["reference_depletion_weeks"] == 6
    assert result["reference_order_slack_weeks"] == 2
    assert result["reference_conservative_slack_weeks"] == 1.3
    assert result["reference_order_at"] == "2026-09-14T00:00:00"
    expected_date = datetime(2026, 8, 31) + timedelta(days=conservative * 7)
    assert datetime.fromisoformat(result["reference_early_warning_at"]) == expected_date
    assert expected_date.date() == date(2026, 9, 8)  # rounding 1.3*7 would incorrectly give Sep 9
    row["forecast_sigma"] = 0
    assert inventory_reference_metrics(row, as_of=date(2026, 8, 31)) == result


@pytest.mark.parametrize("gap,sigma,expected", [(0, 0, 0), (-10, 50, 0), (105, 0, 1.1), (155, 0, 1.6), (175, 0, 1.8), (205, 0, 2.1)])
def test_timing_zero_and_excel_halfway_rounding(gap, sigma, expected):
    row = {"calculable": True, "inventory_position": 400 + gap, "reorder_point": 400,
           "z_value": 1.28, "reference_sales_status": "AVAILABLE",
           "reference_weekly_sales": 100, "reference_weekly_sigma": sigma}
    result = inventory_reference_metrics(row, as_of=date(2026, 8, 31))
    assert result["reference_order_slack_weeks"] == expected
    assert result["reference_conservative_slack_weeks"] == expected


def test_moi_uses_rounded_monthly_denominator_and_main_ip_guard():
    row = {"reference_sales_status": "AVAILABLE", "reference_monthly_sales": 1,
           "reference_monthly_sales_raw": 4 / 3, "reference_weekly_sales": 4 / 13,
           "on_hand_qty": 3, "in_transit_qty": 0, "calculable": False}
    result = inventory_reference_metrics(row, as_of=date(2026, 8, 31))
    assert result["reference_moi"] is None
    assert result["reference_logistics_moi"] == 3  # not 2.3 from raw /3
    assert result["reference_order_at"] is None
    row.update(reference_monthly_sales=0, reference_weekly_sales=0)
    assert all(value is None for value in inventory_reference_metrics(row, as_of=date(2026, 8, 31)).values())


def test_eta_matches_sumifs_boundaries_and_reconciles_unknown_quantities():
    details = [{"eta": eta, "qty": qty} for eta, qty in [
        ("2026-08-30", 1), ("2026-08-31", 2), ("2026-09-06", 3),
        ("2026-09-07", 4), ("2026-11-29", 5), ("2026-11-30", 6), (None, 7)]]
    result = shipping_reference_metrics(details, as_of=date(2026, 9, 2), source_status="AVAILABLE", in_transit_qty=28)
    assert result["eta_week_start"] == "2026-08-31"
    assert result["eta_reference_status"] == "PARTIAL"
    assert result["eta_bucket_quantities"] == [1, 5, 4] + [0] * 10 + [5, 6]
    assert result["eta_missing_qty"] == 7
    assert sum(result["eta_bucket_quantities"]) + result["eta_missing_qty"] == 28
    assert result["next_eta"] == "2026-08-30"  # template minimum includes overdue
    mismatched = shipping_reference_metrics(details, as_of=date(2026, 8, 31), source_status="AVAILABLE", in_transit_qty=29)
    assert mismatched["eta_reference_status"] == "SOURCE_MISMATCH"
    assert mismatched["eta_bucket_quantities"] is None


@pytest.mark.parametrize("status", ["UNAVAILABLE", "NOT_APPLICABLE", "INVALID_SOURCE"])
def test_unknown_or_excluded_shipping_is_not_zero(status):
    result = shipping_reference_metrics([], as_of=date(2027, 1, 1), source_status=status, in_transit_qty=0)
    assert result["eta_reference_status"] == status
    assert result["eta_bucket_quantities"] is None
    assert result["eta_missing_qty"] is None


def test_successful_empty_shipping_is_zero():
    result = shipping_reference_metrics([], as_of=date(2027, 1, 1), source_status="AVAILABLE", in_transit_qty=0)
    assert result["eta_week_start"] == "2026-12-28"
    assert result["eta_bucket_quantities"] == [0] * 15
    assert result["eta_missing_qty"] == 0
