from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import math

import pytest

from core.order_logic_v3 import (
    CONSTRAINT_STATUS_PENDING,
    ENGINE_CROSTON_SBA,
    ENGINE_HOLT_DAMPED,
    ENGINE_MOVING_AVERAGE,
    ENGINE_SES,
    INVENTORY_POLICY_CASH,
    INVENTORY_POLICY_SHORTAGE,
    ORDER_UNIT_SOURCE_FALLBACK_10,
    ORDER_UNIT_SOURCE_INBOX,
    ORDER_UNIT_SOURCE_OUTBOX,
    PATTERN_SHORT_HISTORY,
    SALES_GRADE_CORE,
    SALES_GRADE_GENERAL,
    SeasonalProfile,
    V3FutureSeasonality,
    V3PolicyRequiredError,
    V3ReplenishmentBaseInput,
    V3ReplenishmentInput,
    V3ReplenishmentPolicy,
    apply_textbook_seasonal_shrinkage,
    calculate_candidate_monthly_factors,
    calculate_croston_sba_forecast,
    calculate_future_seasonality,
    calculate_holt_damped_forecast,
    calculate_v3_raw_order,
    calculate_v3_textbook_scenarios,
    classify_v3_demand,
    deseasonalized_completed_4week_sales,
    forecast_v3_demand,
    round_v3_order_quantity,
    run_v3_rolling_origin_backtest,
    textbook_candidate_parameters,
    textbook_z_value,
)


TEXTBOOK_CREAM_SALES = [440, 460, 340, 340, 400, 320, 440, 360, 380, 400, 480, 340, 420]


def test_order_unit_rounding_prefers_outbox_then_inbox_then_ten() -> None:
    # Approved hand checks (2026-09-08): 205.3 with outbox 160 -> 320,
    # inbox 20 -> 220, neither -> 210.
    outbox = round_v3_order_quantity(205.3, outbox_quantity=160, inbox_quantity=20)
    assert outbox.final_order_quantity == 320.0
    assert outbox.order_unit_quantity == 160.0
    assert outbox.order_unit_source == ORDER_UNIT_SOURCE_OUTBOX

    inbox = round_v3_order_quantity(205.3, outbox_quantity=None, inbox_quantity=20)
    assert inbox.final_order_quantity == 220.0
    assert inbox.order_unit_quantity == 20.0
    assert inbox.order_unit_source == ORDER_UNIT_SOURCE_INBOX

    fallback = round_v3_order_quantity(205.3)
    assert fallback.final_order_quantity == 210.0
    assert fallback.order_unit_quantity == 10.0
    assert fallback.order_unit_source == ORDER_UNIT_SOURCE_FALLBACK_10


def test_order_unit_rounding_keeps_zero_raw_at_zero() -> None:
    result = round_v3_order_quantity(0.0, outbox_quantity=160, inbox_quantity=20)
    assert result.final_order_quantity == 0.0
    assert result.order_unit_source == ORDER_UNIT_SOURCE_OUTBOX


def test_order_unit_rounding_treats_invalid_packs_as_unset() -> None:
    # CMS unified unset values to null; 0, negatives and non-numeric text
    # must also fall through the ladder instead of dividing by them.
    for bad in (None, 0, -3, float("nan"), float("inf"), "abc", True):
        result = round_v3_order_quantity(11.0, outbox_quantity=bad, inbox_quantity=bad)
        assert result.order_unit_source == ORDER_UNIT_SOURCE_FALLBACK_10
        assert result.final_order_quantity == 20.0


def test_order_unit_rounding_does_not_round_up_exact_multiples() -> None:
    exact = round_v3_order_quantity(320.0, outbox_quantity=160)
    assert exact.final_order_quantity == 320.0


def test_order_unit_rounding_rejects_negative_raw_quantity() -> None:
    with pytest.raises(Exception):
        round_v3_order_quantity(-1.0)


def _parameters():
    return textbook_candidate_parameters(logic_version="v3-backtest-candidate-test")


def _policy(
    *,
    lead_time_days: float = 28.0,
    sigma_lead_time_periods: float = 0.1,
    floor_periods: float = 2.0,
    cap_periods: float = 13.0,
) -> V3ReplenishmentPolicy:
    return V3ReplenishmentPolicy(
        lead_time_days=lead_time_days,
        review_days=28.0,
        sigma_lead_time_periods=sigma_lead_time_periods,
        safety_stock_floor_periods=floor_periods,
        safety_stock_cap_periods=cap_periods,
    )


def _profile(*, october: float = 1.0, november: float = 1.0, december: float = 1.0) -> SeasonalProfile:
    factors = {month: 1.0 for month in range(1, 13)}
    factors.update({10: october, 11: november, 12: december})
    return SeasonalProfile(
        version="season-test-v1",
        entity_code="PL",
        function_class_1_code="SUN",
        function_class_2_code="UV",
        factors_by_month=factors,
    )


def test_ses_textbook_example_calculates_raw_quantity_without_order_constraints() -> None:
    result = calculate_v3_raw_order(
        TEXTBOOK_CREAM_SALES,
        parameters=_parameters(),
        replenishment=V3ReplenishmentInput(
            order_date=date(2026, 8, 31),
            lead_time_days=28,
            review_days=28,
            sigma_lead_time_periods=0.1,
            safety_stock_floor_periods=2.0,
            safety_stock_cap_periods=13.0,
            z_value=1.68,
            on_hand_qty=320,
            upstream_available_qty=0,
            in_transit_qty=150,
            unreceived_qty=60,
            holding_qty=30,
        ),
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
    )

    # V3-009 applies the PL safety-stock fence before raw need is calculated.
    assert result.forecast.demand_per_period == pytest.approx(400.0, abs=0.01)
    assert result.forecast.sigma_per_period == pytest.approx(60.0, abs=0.05)
    assert result.inventory_position == 500
    assert result.layer1 == pytest.approx(1_600.0, abs=0.01)
    assert result.layer2_raw == pytest.approx(292.75, abs=0.02)
    assert result.safety_stock_floor == pytest.approx(800.0, abs=0.01)
    assert result.safety_stock_cap == pytest.approx(5_200.0, abs=0.05)
    assert result.layer2 == pytest.approx(800.0, abs=0.01)
    assert result.layer3 == pytest.approx(1_600.0, abs=0.01)
    assert result.reorder_point == pytest.approx(2_400.0, abs=0.05)
    assert result.target_stock == pytest.approx(4_000.0, abs=0.05)
    assert result.need_order is True
    assert result.raw_order_quantity == pytest.approx(3_500.0, abs=0.05)
    assert result.final_order_quantity is None
    assert result.order_constraint_status == CONSTRAINT_STATUS_PENDING


def test_textbook_sku_flow_uses_one_snapshot_for_both_policy_scenarios() -> None:
    last_completed_sunday = date(2026, 8, 23)
    oldest_start = date(2026, 5, 25)
    daily_sales = {
        oldest_start + timedelta(days=index * 7): float(value)
        for index, value in enumerate(TEXTBOOK_CREAM_SALES)
    }

    result = calculate_v3_textbook_scenarios(
        daily_sales,
        profile=_profile(),
        last_completed_sunday=last_completed_sunday,
        parameters=_parameters(),
        replenishment=V3ReplenishmentBaseInput(
            order_date=date(2026, 8, 31),
            cash_policy=_policy(),
            shortage_policy=_policy(),
            on_hand_qty=320,
            upstream_available_qty=0,
            in_transit_qty=150,
            unreceived_qty=60,
            holding_qty=30,
        ),
        sales_grade=SALES_GRADE_CORE,
    )

    assert result.original_period_sales == pytest.approx(TEXTBOOK_CREAM_SALES)
    assert result.adjusted_period_sales == pytest.approx(TEXTBOOK_CREAM_SALES)
    assert result.shortage.forecast == result.cash.forecast
    assert result.shortage.inventory_position == result.cash.inventory_position == 500
    assert result.shortage.raw_order_quantity == pytest.approx(3_500.0, abs=0.05)
    assert result.cash.raw_order_quantity == pytest.approx(result.shortage.raw_order_quantity)


def test_recent_three_zero_weeks_do_not_add_an_undocumented_sales_hold() -> None:
    last_completed_sunday = date(2026, 8, 23)
    oldest_start = date(2026, 5, 25)
    sales_with_recent_gap = TEXTBOOK_CREAM_SALES[:-3] + [0, 0, 0]

    result = calculate_v3_textbook_scenarios(
        {
            oldest_start + timedelta(days=index * 7): float(value)
            for index, value in enumerate(sales_with_recent_gap)
        },
        profile=_profile(),
        last_completed_sunday=last_completed_sunday,
        parameters=_parameters(),
        replenishment=V3ReplenishmentBaseInput(
            order_date=date(2026, 8, 31),
            cash_policy=_policy(),
            shortage_policy=_policy(),
            on_hand_qty=0,
            upstream_available_qty=0,
            in_transit_qty=0,
            unreceived_qty=0,
            holding_qty=0,
        ),
        sales_grade=SALES_GRADE_GENERAL,
    )

    assert result.shortage.classification.engine == ENGINE_HOLT_DAMPED
    assert result.shortage.raw_order_quantity > 0


def test_raw_order_path_does_not_hold_for_latest_three_zero_weeks() -> None:
    sales_with_recent_gap = TEXTBOOK_CREAM_SALES[:-3] + [0, 0, 0]

    result = calculate_v3_raw_order(
        sales_with_recent_gap,
        parameters=_parameters(),
        replenishment=V3ReplenishmentInput(
            order_date=date(2026, 8, 31),
            lead_time_days=28,
            review_days=28,
            sigma_lead_time_periods=0.1,
            safety_stock_floor_periods=2.0,
            safety_stock_cap_periods=13.0,
            z_value=1.08,
            on_hand_qty=0,
            upstream_available_qty=0,
            in_transit_qty=0,
            unreceived_qty=0,
            holding_qty=0,
        ),
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
    )

    assert result.forecast.engine == ENGINE_HOLT_DAMPED
    assert result.raw_order_quantity > 0


def test_croston_forecast_is_not_capped_by_an_undocumented_recent_demand_rule() -> None:
    intermittent_sales = [1000, 0, 0, 1000, 0, 0, 1000, 0, 0, 0, 10, 20, 30]
    parameters = _parameters()
    classification = classify_v3_demand(intermittent_sales, parameters=parameters)
    uncapped = calculate_croston_sba_forecast(
        intermittent_sales,
        alpha=parameters.alpha,
        initialization=parameters.croston_initialization,
    )
    forecast = forecast_v3_demand(
        intermittent_sales,
        classification=classification,
        parameters=parameters,
    )
    result = calculate_v3_raw_order(
        intermittent_sales,
        parameters=parameters,
        replenishment=V3ReplenishmentInput(
            order_date=date(2026, 8, 31),
            lead_time_days=28,
            review_days=28,
            sigma_lead_time_periods=0.1,
            safety_stock_floor_periods=2.0,
            safety_stock_cap_periods=13.0,
            z_value=1.08,
            on_hand_qty=0,
            upstream_available_qty=0,
            in_transit_qty=0,
            unreceived_qty=0,
            holding_qty=0,
        ),
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
    )

    assert classification.engine == ENGINE_CROSTON_SBA
    assert uncapped.demand_per_period > 40
    assert forecast.croston_forecast_cap_per_period is None
    assert forecast.croston_forecast_was_capped is False
    assert forecast.demand_per_period == pytest.approx(uncapped.demand_per_period)
    assert forecast.next_period_forecast == pytest.approx(uncapped.next_period_forecast)
    assert forecast.second_period_forecast == pytest.approx(uncapped.second_period_forecast)
    assert forecast.sigma_per_period == pytest.approx(uncapped.sigma_per_period)
    assert result.layer1 == pytest.approx(uncapped.demand_per_period * 4)
    assert result.layer3 == pytest.approx(uncapped.demand_per_period * 4)


def test_ip_equal_to_reorder_point_orders_the_review_period_demand() -> None:
    base_replenishment = V3ReplenishmentInput(
        order_date=date(2026, 8, 31),
        lead_time_days=28,
        review_days=28,
        sigma_lead_time_periods=0.1,
        safety_stock_floor_periods=0.5,
        safety_stock_cap_periods=3.25,
        z_value=1.68,
        on_hand_qty=0,
        upstream_available_qty=0,
        in_transit_qty=0,
        unreceived_qty=0,
        holding_qty=0,
    )
    initial = calculate_v3_raw_order(
        TEXTBOOK_CREAM_SALES,
        parameters=_parameters(),
        replenishment=base_replenishment,
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
    )
    boundary = calculate_v3_raw_order(
        TEXTBOOK_CREAM_SALES,
        parameters=_parameters(),
        replenishment=V3ReplenishmentInput(
            order_date=base_replenishment.order_date,
            lead_time_days=base_replenishment.lead_time_days,
            review_days=base_replenishment.review_days,
            sigma_lead_time_periods=base_replenishment.sigma_lead_time_periods,
            safety_stock_floor_periods=base_replenishment.safety_stock_floor_periods,
            safety_stock_cap_periods=base_replenishment.safety_stock_cap_periods,
            z_value=base_replenishment.z_value,
            on_hand_qty=initial.reorder_point,
            upstream_available_qty=0,
            in_transit_qty=0,
            unreceived_qty=0,
            holding_qty=0,
        ),
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
    )

    assert boundary.inventory_position == pytest.approx(boundary.reorder_point)
    assert boundary.need_order is True
    assert boundary.raw_order_quantity == pytest.approx(boundary.layer3)


def test_inventory_between_reorder_point_and_target_stock_orders_to_target() -> None:
    base_replenishment = V3ReplenishmentInput(
        order_date=date(2026, 8, 31),
        lead_time_days=28,
        review_days=28,
        sigma_lead_time_periods=0.1,
        safety_stock_floor_periods=0.5,
        safety_stock_cap_periods=3.25,
        z_value=1.68,
        on_hand_qty=0,
        upstream_available_qty=0,
        in_transit_qty=0,
        unreceived_qty=0,
        holding_qty=0,
    )
    initial = calculate_v3_raw_order(
        TEXTBOOK_CREAM_SALES,
        parameters=_parameters(),
        replenishment=base_replenishment,
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
    )
    inventory_between = (initial.reorder_point + initial.target_stock) / 2
    result = calculate_v3_raw_order(
        TEXTBOOK_CREAM_SALES,
        parameters=_parameters(),
        replenishment=replace(base_replenishment, on_hand_qty=inventory_between),
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
    )

    assert result.inventory_position == pytest.approx(inventory_between)
    assert result.inventory_position < result.target_stock
    assert result.inventory_position > result.reorder_point
    assert result.need_order is True
    assert result.raw_order_quantity == pytest.approx(result.target_stock - inventory_between)


def test_inventory_equal_to_target_stock_does_not_order() -> None:
    base_replenishment = V3ReplenishmentInput(
        order_date=date(2026, 8, 31),
        lead_time_days=28,
        review_days=28,
        sigma_lead_time_periods=0.1,
        safety_stock_floor_periods=0.5,
        safety_stock_cap_periods=3.25,
        z_value=1.68,
        on_hand_qty=0,
        upstream_available_qty=0,
        in_transit_qty=0,
        unreceived_qty=0,
        holding_qty=0,
    )
    initial = calculate_v3_raw_order(
        TEXTBOOK_CREAM_SALES,
        parameters=_parameters(),
        replenishment=base_replenishment,
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
    )
    boundary = calculate_v3_raw_order(
        TEXTBOOK_CREAM_SALES,
        parameters=_parameters(),
        replenishment=replace(base_replenishment, on_hand_qty=initial.target_stock),
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
    )

    assert boundary.inventory_position == pytest.approx(boundary.target_stock)
    assert boundary.need_order is False
    assert boundary.raw_order_quantity == 0


def test_inventory_position_keeps_v2_available_inventory_components_separate() -> None:
    replenishment = V3ReplenishmentInput(
        order_date=date(2026, 8, 31),
        lead_time_days=28,
        review_days=28,
        sigma_lead_time_periods=0.1,
        safety_stock_floor_periods=0.5,
        safety_stock_cap_periods=3.25,
        z_value=1.68,
        on_hand_qty=55,
        upstream_available_qty=20,
        in_transit_qty=15,
        unreceived_qty=10,
        holding_qty=0,
    )

    # V2 owns availability (including holds/statuses). V3 only sums those
    # approved components and must not subtract hold quantities a second time.
    assert replenishment.inventory_position == pytest.approx(100)


def test_future_factor_is_weighted_by_actual_calendar_days() -> None:
    profile = _profile(october=0.8, november=1.0, december=1.4)

    factors = calculate_future_seasonality(
        profile,
        order_date=date(2026, 10, 1),
        lead_time_days=61,
        review_days=28,
    )

    assert factors.f1 == pytest.approx((31 * 0.8 + 30 * 1.0) / 61)
    assert factors.f2 == pytest.approx(1.4)
    assert factors.f_lr == pytest.approx((31 * 0.8 + 30 * 1.0 + 28 * 1.4) / 89)


def test_future_factor_preserves_a_fractional_actual_lead_time() -> None:
    profile = _profile(october=0.8, november=1.0, december=1.4)

    factors = calculate_future_seasonality(
        profile,
        order_date=date(2026, 10, 1),
        lead_time_days=61.5,
        review_days=28,
    )

    assert factors.f1 == pytest.approx((31 * 0.8 + 30 * 1.0 + 0.5 * 1.4) / 61.5)
    assert factors.f2 == pytest.approx(1.4)
    assert factors.f_lr == pytest.approx((31 * 0.8 + 30 * 1.0 + 28.5 * 1.4) / 89.5)


def test_candidate_monthly_factor_requires_24_consecutive_completed_months() -> None:
    totals = {}
    current = date(2024, 1, 1)
    for _ in range(24):
        totals[current] = 220.0 if current.month == 6 else 100.0
        current = date(current.year + (current.month == 12), (current.month % 12) + 1, 1)

    factors = calculate_candidate_monthly_factors(totals)

    assert factors[6] == pytest.approx(2.0)
    assert sum(factors.values()) / 12 == pytest.approx(1.0)


def test_candidate_monthly_factor_weights_the_latest_completed_12_months_twice() -> None:
    totals = {}
    current = date(2024, 8, 1)
    for index in range(24):
        # January in the most recent completed 12-month block is three times
        # the ordinary month total. The older block keeps the baseline 100.
        totals[current] = 300.0 if index == 17 else 100.0
        current = date(current.year + (current.month == 12), (current.month % 12) + 1, 1)

    factors = calculate_candidate_monthly_factors(totals)

    # January: (100×1 + 300×2) / (1+2) = 233.33.
    # Weighted 24-month mean: (1,200 + 2×1,400) / 36 = 111.11.
    assert factors[1] == pytest.approx(2.1)
    assert factors[2] == pytest.approx(0.9)
    assert sum(factors.values()) / 12 == pytest.approx(1.0)


def test_textbook_seasonal_shrinkage_and_explicit_unconfirmed_one() -> None:
    combination = {
        month: (2.0 if month == 6 else 0.0 if month == 12 else 1.0)
        for month in range(1, 13)
    }
    parent = {month: 1.0 for month in range(1, 13)}

    shrunk = apply_textbook_seasonal_shrinkage(
        combination,
        parent,
        sku_count=30,
        seasonality_confirmed=True,
    )
    unconfirmed = apply_textbook_seasonal_shrinkage(
        combination,
        parent,
        sku_count=30,
        seasonality_confirmed=False,
    )

    assert shrunk[6] == pytest.approx(1.5)
    assert shrunk[12] == pytest.approx(0.5)
    assert unconfirmed == {month: 1.0 for month in range(1, 13)}


def test_textbook_z_matrix_is_independent_of_demand_pattern() -> None:
    assert textbook_z_value(
        inventory_policy=INVENTORY_POLICY_SHORTAGE,
        sales_grade=SALES_GRADE_CORE,
    ) == pytest.approx(1.68)
    assert textbook_z_value(
        inventory_policy=INVENTORY_POLICY_SHORTAGE,
        sales_grade=SALES_GRADE_GENERAL,
    ) == pytest.approx(1.28)
    assert textbook_z_value(
        inventory_policy=INVENTORY_POLICY_CASH,
        sales_grade=SALES_GRADE_CORE,
    ) == pytest.approx(1.28)
    assert textbook_z_value(
        inventory_policy=INVENTORY_POLICY_CASH,
        sales_grade=SALES_GRADE_GENERAL,
    ) == pytest.approx(1.08)


def test_explicit_z_matrix_allows_zero_and_keeps_the_safety_stock_floor() -> None:
    last_completed_sunday = date(2026, 8, 23)
    oldest_start = last_completed_sunday - timedelta(days=(13 * 7) - 1)
    result = calculate_v3_textbook_scenarios(
        {
            oldest_start + timedelta(days=index * 7): float(value)
            for index, value in enumerate(TEXTBOOK_CREAM_SALES)
        },
        profile=_profile(),
        last_completed_sunday=last_completed_sunday,
        parameters=_parameters(),
        replenishment=V3ReplenishmentBaseInput(
            order_date=date(2026, 8, 28),
            cash_policy=_policy(floor_periods=1.0, cap_periods=2.0),
            shortage_policy=_policy(floor_periods=1.0, cap_periods=2.0),
            on_hand_qty=0,
            upstream_available_qty=0,
            in_transit_qty=0,
            unreceived_qty=0,
            holding_qty=0,
        ),
        sales_grade=SALES_GRADE_GENERAL,
        z_matrix={
            (INVENTORY_POLICY_SHORTAGE, SALES_GRADE_GENERAL): 0.5244005127080409,
            (INVENTORY_POLICY_CASH, SALES_GRADE_GENERAL): 0.0,
        },
    )

    assert result.cash.z_value == 0.0
    assert result.cash.layer2_raw == 0.0
    assert result.cash.layer2 == pytest.approx(result.cash.safety_stock_floor)
    assert result.shortage.z_value == pytest.approx(0.5244005127080409)


def test_croston_uses_each_scenarios_grade_z() -> None:
    last_completed_sunday = date(2026, 8, 23)
    # Starts with an observed sale so the full 13-week history applies; a
    # leading-zero series is now the approved short-history moving-average path.
    intermittent_sales = [300, 0, 0, 0, 300, 0, 0, 0, 200, 0, 0, 0, 400]
    oldest_start = last_completed_sunday - timedelta(days=(13 * 7) - 1)
    result = calculate_v3_textbook_scenarios(
        {
            oldest_start + timedelta(days=index * 7): float(value)
            for index, value in enumerate(intermittent_sales)
        },
        profile=_profile(),
        last_completed_sunday=last_completed_sunday,
        parameters=_parameters(),
        replenishment=V3ReplenishmentBaseInput(
            order_date=date(2026, 8, 28),
            cash_policy=_policy(),
            shortage_policy=_policy(),
            on_hand_qty=0,
            upstream_available_qty=0,
            in_transit_qty=0,
            unreceived_qty=0,
            holding_qty=0,
        ),
        sales_grade=SALES_GRADE_GENERAL,
    )

    assert result.shortage.classification.engine == ENGINE_CROSTON_SBA
    assert result.shortage.z_value == pytest.approx(1.28)
    assert result.cash.z_value == pytest.approx(1.08)
    assert result.shortage.layer2_raw > result.cash.layer2_raw


def test_completed_4week_observation_includes_weekend_sales_and_deseasonalizes_by_day() -> None:
    profile = _profile()
    profile = SeasonalProfile(
        version=profile.version,
        entity_code=profile.entity_code,
        function_class_1_code=profile.function_class_1_code,
        function_class_2_code=profile.function_class_2_code,
        factors_by_month={**profile.factors_by_month, 3: 2.0},
    )
    periods = deseasonalized_completed_4week_sales(
        {
            date(2026, 3, 28): 100.0,  # Saturday
            date(2026, 3, 29): 110.0,  # Sunday
        },
        profile=profile,
        last_completed_sunday=date(2026, 3, 29),
    )

    assert len(periods) == 13
    assert periods[-1] == pytest.approx(105.0)


def test_holt_and_croston_candidate_engines_are_selected_from_their_patterns() -> None:
    parameters = _parameters()
    trend_sales = [280, 300, 330, 350, 350, 370, 390, 400, 420, 430, 440, 450, 480]
    # First week sells, so this is full-window intermittent demand and not the
    # approved short-history moving-average path.
    intermittent_sales = [300, 0, 0, 0, 300, 0, 0, 0, 200, 0, 0, 0, 400]

    trend_classification = classify_v3_demand(trend_sales, parameters=parameters)
    intermittent_classification = classify_v3_demand(intermittent_sales, parameters=parameters)
    holt = calculate_holt_damped_forecast(
        trend_sales,
        alpha=parameters.alpha,
        beta=parameters.beta,
        phi=parameters.phi,
        initialization=parameters.holt_initialization,
    )
    croston = calculate_croston_sba_forecast(
        intermittent_sales,
        alpha=parameters.alpha,
        initialization=parameters.croston_initialization,
    )

    assert trend_classification.engine == ENGINE_HOLT_DAMPED
    assert intermittent_classification.engine == ENGINE_CROSTON_SBA
    assert holt.second_period_forecast is not None
    # SIX_WEEK_REGRESSION init: b0 = (-5*280 - 3*300 - 330 + 350 + 3*350 + 5*370)/35
    # = 17.714286, l0 = mean(280..370) + b0*2.5 = 374.285714; recursion runs
    # over weeks 7..13.
    assert holt.next_period_forecast == pytest.approx(470.2, abs=0.1)
    assert holt.second_period_forecast == pytest.approx(477.5, abs=0.1)
    assert croston.demand_per_period == pytest.approx(68.4)
    # sizes (300, 300, 200, 400): STDEV.S² = 6_666.67, interval 4 →
    # 6_666.67 / 4 + 304² × (1/4) × (3/4) = 18_994.67
    assert croston.variance_per_period == pytest.approx(18_994.67, abs=0.01)


def test_intermittent_classification_requires_both_adi_and_cv2() -> None:
    parameters = _parameters()
    # ADI=13/9 exceeds 1.32, but equal nonzero quantities keep CV² below 0.49.
    #확정 로직표 B: the intermittent gate is conjunctive, so a high ADI alone is
    # not enough — CV² below 0.49 falls through to the trend test instead of
    # Croston + SBA.
    sparse_but_low_variability = [100.0] * 9 + [0.0] * 4

    classification = classify_v3_demand(sparse_but_low_variability, parameters=parameters)

    assert classification.adi >= parameters.adi_threshold
    assert classification.cv2 < parameters.cv2_threshold
    assert classification.engine != ENGINE_CROSTON_SBA


def test_intermittent_gate_is_inclusive_while_high_cv2_flag_stays_strict() -> None:
    values = [100.0] * 9 + [0.0] * 4
    observed = classify_v3_demand(values, parameters=_parameters())
    boundary_parameters = replace(
        _parameters(),
        adi_threshold=observed.adi,
        cv2_threshold=observed.cv2,
    )

    classification = classify_v3_demand(values, parameters=boundary_parameters)

    # 확정 로직표 B: the Croston gate is inclusive (``ADI >= 1.32`` and
    # ``CV² >= 0.49``), so both conditions sitting exactly on the boundary select
    # Croston + SBA.  ``high_cv2`` remains a strict ``>`` audit flag and is False
    # on the boundary.
    assert classification.adi == boundary_parameters.adi_threshold
    assert classification.cv2 == boundary_parameters.cv2_threshold
    assert classification.high_cv2 is False
    assert classification.engine == ENGINE_CROSTON_SBA


def test_trend_classification_uses_strict_twenty_percent_boundaries() -> None:
    parameters = _parameters()
    rising = [100.0] * 7 + [120.0] * 6
    falling = [100.0] * 7 + [80.0] * 6

    rising_classification = classify_v3_demand(rising, parameters=parameters)
    falling_classification = classify_v3_demand(falling, parameters=parameters)

    assert rising_classification.trend_signal == pytest.approx(0.20)
    assert rising_classification.engine == ENGINE_SES
    assert falling_classification.trend_signal == pytest.approx(-0.20)
    assert falling_classification.engine == ENGINE_SES


def test_short_history_sku_uses_the_approved_moving_average_hand_check() -> None:
    # Approved 2026-09-08 hand check: first in-window sale in week 9 with
    # adjusted sales 10, 20, 30, 20, 20 → d_bar = 100/5 = 20, σ = STDEV.S ≈ 7.07.
    parameters = _parameters()
    short_history_sales = [0.0] * 8 + [10.0, 20.0, 30.0, 20.0, 20.0]

    classification = classify_v3_demand(short_history_sales, parameters=parameters)
    forecast = forecast_v3_demand(
        short_history_sales, classification=classification, parameters=parameters
    )

    assert classification.pattern == PATTERN_SHORT_HISTORY
    assert classification.engine == ENGINE_MOVING_AVERAGE
    assert classification.trend_signal is None
    assert forecast.engine == ENGINE_MOVING_AVERAGE
    assert forecast.demand_per_period == pytest.approx(20.0)
    assert forecast.sigma_per_period == pytest.approx(7.0710678, abs=1e-6)
    assert forecast.next_period_forecast == pytest.approx(20.0)
    assert forecast.second_period_forecast == pytest.approx(20.0)


def test_short_history_moving_average_includes_intermediate_zero_weeks() -> None:
    # Weeks after the first in-window sale count even when they sold zero.
    parameters = _parameters()
    values = [0.0] * 9 + [40.0, 0.0, 0.0, 20.0]

    classification = classify_v3_demand(values, parameters=parameters)
    forecast = forecast_v3_demand(values, classification=classification, parameters=parameters)

    assert classification.engine == ENGINE_MOVING_AVERAGE
    assert forecast.demand_per_period == pytest.approx(60.0 / 4.0)


def test_short_history_with_a_single_observed_week_stays_blocked() -> None:
    # One in-window sale week cannot produce a STDEV.S sigma; this row keeps
    # failing closed instead of inventing a zero-sigma safety stock.
    parameters = _parameters()
    values = [0.0] * 12 + [50.0]

    classification = classify_v3_demand(values, parameters=parameters)
    assert classification.engine == ENGINE_MOVING_AVERAGE
    with pytest.raises(V3PolicyRequiredError):
        forecast_v3_demand(values, classification=classification, parameters=parameters)


def test_full_window_history_never_selects_the_moving_average_engine() -> None:
    # A SKU selling in week 1 keeps the approved SES/HOLT/Croston gates even
    # with later zero weeks; the short-history path needs leading zero weeks.
    parameters = _parameters()
    trailing_zero_sales = [100.0] * 9 + [0.0] * 4

    classification = classify_v3_demand(trailing_zero_sales, parameters=parameters)

    assert classification.pattern != PATTERN_SHORT_HISTORY
    assert classification.engine != ENGINE_MOVING_AVERAGE


def test_short_history_moving_average_flows_through_layers_and_raw_quantity() -> None:
    parameters = _parameters()
    short_history_sales = [0.0] * 8 + [10.0, 20.0, 30.0, 20.0, 20.0]
    result = calculate_v3_raw_order(
        short_history_sales,
        parameters=parameters,
        replenishment=V3ReplenishmentInput(
            order_date=date(2026, 8, 31),
            lead_time_days=28,
            review_days=28,
            sigma_lead_time_periods=0.1,
            safety_stock_floor_periods=2.0,
            safety_stock_cap_periods=13.0,
            z_value=1.68,
            on_hand_qty=0,
            upstream_available_qty=0,
            in_transit_qty=0,
            unreceived_qty=0,
            holding_qty=0,
        ),
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
    )

    # d_bar=20/week over L=R=4 weeks: Layer1 = Layer3 = 80; the existing
    # fence, Z and pure periodic Q_raw = max(0, S - IP) formulas are unchanged.
    assert result.forecast.engine == ENGINE_MOVING_AVERAGE
    assert result.layer1 == pytest.approx(80.0)
    assert result.layer3 == pytest.approx(80.0)
    expected_layer2_raw = 1.68 * math.sqrt(8 * 7.0710678**2 + 20.0**2 * 0.1**2)
    assert result.layer2_raw == pytest.approx(expected_layer2_raw, abs=1e-4)
    assert result.safety_stock_floor == pytest.approx(40.0)
    assert result.layer2 == pytest.approx(min(max(expected_layer2_raw, 40.0), 260.0), abs=1e-4)
    assert result.raw_order_quantity == pytest.approx(
        result.target_stock - result.inventory_position
    )


def test_high_cv2_trend_keeps_holt_while_sigma_multiplier_is_unresolved() -> None:
    parameters = _parameters()
    high_variability_rising_sales = [1.0] * 7 + [100.0] * 6

    classification = classify_v3_demand(high_variability_rising_sales, parameters=parameters)

    assert classification.adi < parameters.adi_threshold
    assert classification.trend_signal is not None
    assert classification.trend_signal >= parameters.trend_threshold
    assert classification.high_cv2 is True
    assert classification.engine == ENGINE_HOLT_DAMPED


def test_holt_six_week_regression_init_is_not_poisoned_by_a_launch_spike() -> None:
    """Approved 2026-09-08: a week-2 one-off bulk sale must not turn a falling
    SKU into a growth forecast (PL cases MNC10-OCDeep200 / ALSC01-FbrEU /
    MNS02-T).  The old two-point init produced b0 = 1492 - 195 = +1297/week
    here; the six-week regression slope must be negative instead."""

    parameters = _parameters()
    spike_sales = [195, 1492, 954, 34, 10, 94, 282, 44, 43, 99, 110, 71, 12]

    classification = classify_v3_demand(spike_sales, parameters=parameters)
    forecast = calculate_holt_damped_forecast(
        spike_sales,
        alpha=parameters.alpha,
        beta=parameters.beta,
        phi=parameters.phi,
        initialization=parameters.holt_initialization,
    )

    assert classification.pattern == "TREND_DOWN"
    # b0 = (-5*195 - 3*1492 - 954 + 34 + 3*10 + 5*94) / 35 = -167.742857
    # l0 = mean(first six weeks) + b0 * 2.5 = 43.809524
    assert forecast.trend is not None
    assert forecast.next_period_forecast == pytest.approx(-240.121360, abs=1e-4)
    assert forecast.rmse is not None
    # The mis-initialised engine reported sigma around 2,261 for this shape;
    # the regression init keeps the fit honest.
    assert forecast.rmse == pytest.approx(324.240548, abs=1e-4)


def test_holt_integrates_forecasts_over_measured_fractional_lead_time() -> None:
    trend_sales = [280, 300, 330, 350, 350, 370, 390, 400, 420, 430, 440, 450, 480]
    parameters = _parameters()
    result = calculate_v3_raw_order(
        trend_sales,
        parameters=parameters,
        replenishment=V3ReplenishmentInput(
            order_date=date(2026, 8, 31),
            lead_time_days=72.9,
            review_days=28,
            sigma_lead_time_periods=2.18,
            safety_stock_floor_periods=2.0,
            safety_stock_cap_periods=13.0,
            z_value=1.68,
            on_hand_qty=0,
            upstream_available_qty=0,
            in_transit_qty=0,
            unreceived_qty=0,
            holding_qty=0,
        ),
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
        first_sale_date=date(2025, 8, 23),
        analysis_date=date(2026, 8, 23),
    )

    assert result.forecast.engine == ENGINE_HOLT_DAMPED
    assert result.forecast.level is not None
    assert result.forecast.trend is not None
    lead_periods = 72.9 / 7
    whole_lead_periods = int(lead_periods)
    lead_fraction = lead_periods - whole_lead_periods
    forecast_at = lambda horizon: result.forecast.level + result.forecast.trend * sum(
        parameters.phi**step for step in range(1, horizon + 1)
    )
    assert result.layer1 == pytest.approx(
        sum(forecast_at(horizon) for horizon in range(1, whole_lead_periods + 1))
        + lead_fraction * forecast_at(whole_lead_periods + 1)
    )
    assert result.layer3 == pytest.approx(
        (1 - lead_fraction) * forecast_at(whole_lead_periods + 1)
        + sum(forecast_at(horizon) for horizon in range(whole_lead_periods + 2, whole_lead_periods + 5))
        + lead_fraction * forecast_at(whole_lead_periods + 5)
    )


def test_new_sku_holt_damping_uses_elapsed_calendar_days_from_first_sale() -> None:
    trend_sales = [280, 300, 330, 350, 350, 370, 390, 400, 420, 430, 440, 450, 480]
    parameters = _parameters()
    analysis_date = date(2026, 8, 23)
    replenishment = V3ReplenishmentInput(
        order_date=date(2026, 8, 28),
        lead_time_days=28,
        review_days=28,
        sigma_lead_time_periods=0.1,
        safety_stock_floor_periods=0.5,
        safety_stock_cap_periods=3.25,
        z_value=1.68,
        on_hand_qty=0,
        upstream_available_qty=0,
        in_transit_qty=0,
        unreceived_qty=0,
        holding_qty=0,
    )
    new_sku = calculate_v3_raw_order(
        trend_sales,
        parameters=parameters,
        replenishment=replenishment,
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
        first_sale_date=analysis_date - timedelta(days=168),
        analysis_date=analysis_date,
    )
    existing_sku = calculate_v3_raw_order(
        trend_sales,
        parameters=parameters,
        replenishment=replenishment,
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
        first_sale_date=analysis_date - timedelta(days=169),
        analysis_date=analysis_date,
    )

    assert new_sku.classification.engine == ENGINE_HOLT_DAMPED
    assert new_sku.new_sku_status is not None
    assert new_sku.new_sku_status.elapsed_calendar_days == 168
    assert new_sku.new_sku_status.is_new_sku is True
    assert new_sku.forecast.damping_phi == pytest.approx(0.90)
    assert existing_sku.new_sku_status is not None
    assert existing_sku.new_sku_status.elapsed_calendar_days == 169
    assert existing_sku.new_sku_status.is_new_sku is False
    assert existing_sku.forecast.damping_phi == pytest.approx(0.90)
    assert new_sku.forecast.next_period_forecast == pytest.approx(
        existing_sku.forecast.next_period_forecast
    )


def test_textbook_classification_uses_population_cv2_and_excludes_middle_period_for_trend() -> None:
    classification = classify_v3_demand(TEXTBOOK_CREAM_SALES, parameters=_parameters())

    assert classification.cv2 == pytest.approx(0.0160217, abs=1e-7)
    assert classification.trend_signal == pytest.approx(0.0347826, abs=1e-7)


def test_textbook_high_cv2_flag_keeps_engine_variance_without_inventing_a_coefficient() -> None:
    high_variability_sales = [100, 1, 100, 1, 100, 1, 100, 1, 100, 1, 100, 1, 100]
    result = calculate_v3_raw_order(
        high_variability_sales,
        parameters=_parameters(),
        replenishment=V3ReplenishmentInput(
            order_date=date(2026, 8, 31),
            lead_time_days=28,
            review_days=28,
            sigma_lead_time_periods=0.1,
            safety_stock_floor_periods=0.5,
            safety_stock_cap_periods=3.25,
            z_value=1.68,
            on_hand_qty=0,
            upstream_available_qty=0,
            in_transit_qty=0,
            unreceived_qty=0,
            holding_qty=0,
        ),
        seasonal_factors=V3FutureSeasonality(f1=1.0, f2=1.0, f_lr=1.0),
    )

    assert result.classification.high_cv2 is True
    expected_layer2_raw = 1.68 * (
        8.0 * (result.forecast.sigma_per_period**2)
        + (result.forecast.demand_per_period**2) * (0.1**2)
    ) ** 0.5
    assert result.layer2_raw == pytest.approx(expected_layer2_raw)
    assert result.layer2 > 0


def test_rolling_origin_backtest_reports_v3_result_values_without_v2_baseline() -> None:
    result = run_v3_rolling_origin_backtest([100.0] * 16, parameters=_parameters())

    assert len(result.points) == 3
    assert result.blocked_points == ()
    assert result.mean_signed_error == pytest.approx(0.0)
    assert result.mean_absolute_error == pytest.approx(0.0)


def test_rolling_origin_backtest_calculates_high_cv2_origins_with_textbook_baseline() -> None:
    high_variability_sales = [100.0, 1.0] * 8

    result = run_v3_rolling_origin_backtest(high_variability_sales, parameters=_parameters())

    assert len(result.points) == 3
    assert result.blocked_points == ()
    assert result.mean_signed_error is not None
    assert result.mean_absolute_error is not None
