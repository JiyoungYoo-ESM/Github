from __future__ import annotations

from dataclasses import replace
import json
import math

import pytest

from core.order_logic_v2 import (
    GRADE_MAJOR,
    GRADE_MINOR,
    POLICY_CASH,
    POLICY_SHORTAGE,
    REQUIRED_SALES_WEEKS,
    SALES_STATUS_BULK_INCLUDED,
    SALES_STATUS_INSUFFICIENT,
    SALES_STATUS_INTERMITTENT,
    SALES_STATUS_NORMAL,
    SALES_STATUS_NO_SALES,
    SKUOrderInput,
    SS_CLAMP_CAP,
    SS_CLAMP_FLOOR,
    SS_CLAMP_NONE,
    WARNING_QTY_EU_AVAILABLE_DEFAULTED,
    WARNING_QTY_INCOMING_DEFAULTED,
    WARNING_QTY_LOCAL_AVAILABLE_DEFAULTED,
    WARNING_QTY_TRANSIT_DEFAULTED,
    OrderLogicValidationError,
    assign_pareto_grades,
    calculate_both_policy_modes,
    calculate_order_batch,
    calculate_periodic_rs,
    calculate_sku_order,
    OrderLogicConfig,
)


# Mean = 100 and sample standard deviation (STDEV.S) = 45 exactly over the
# approved 13 completed weeks: six symmetric pairs plus the mean itself.
FIXED_VECTOR_DELTA = 45.0
FIXED_VECTOR_HISTORY = (
    (100.0 - FIXED_VECTOR_DELTA, 100.0 + FIXED_VECTOR_DELTA) * 6 + (100.0,)
)


@pytest.mark.parametrize(
    (
        "demand_mean",
        "demand_stdev",
        "lead_time",
        "lead_time_stdev",
        "review",
        "floor",
        "cap",
        "inventory_position",
        "expected_qty",
    ),
    [
        # HQ/OPO: daily demand and daily lead time.
        (15.0, 9.0, 12.0, 6.0, 28.0, 14.0, 35.0, 150.0, 660.0),
        # USA and PL: weekly demand and weekly lead time.
        (80.0, 50.0, 8.0, 1.2, 4.0, 2.0, 8.0, 650.0, 643.0),
        (60.0, 40.0, 9.14, 1.5, 4.0, 2.0, 13.0, 410.0, 666.0),
    ],
)
def test_approved_entity_periodic_rs_vectors(
    demand_mean,
    demand_stdev,
    lead_time,
    lead_time_stdev,
    review,
    floor,
    cap,
    inventory_position,
    expected_qty,
):
    result = calculate_periodic_rs(
        demand_mean=demand_mean,
        demand_stdev=demand_stdev,
        lead_time_periods=lead_time,
        lead_time_stdev_periods=lead_time_stdev,
        review_periods=review,
        z_value=1.68,
        safety_stock_floor_periods=floor,
        safety_stock_cap_periods=cap,
        inventory_position=inventory_position,
    )

    assert result.suggested_qty == expected_qty


def _item(
    sku_code: str = "SKU_MAIN",
    *,
    weekly_sales=FIXED_VECTOR_HISTORY,
    revenue_amt: float = 80.0,
    qty_incoming: float | None = 0.0,
    qty_eu_available: float | None = 0.0,
    qty_in_transit: float | None = 0.0,
    qty_local_available: float | None = 0.0,
) -> SKUOrderInput:
    return SKUOrderInput(
        sku_code=sku_code,
        weekly_sales=weekly_sales,
        revenue_amt=revenue_amt,
        qty_incoming=qty_incoming,
        qty_eu_available=qty_eu_available,
        qty_in_transit=qty_in_transit,
        qty_local_available=qty_local_available,
    )


def _major_batch(main: SKUOrderInput) -> tuple[SKUOrderInput, SKUOrderInput]:
    # Main lands exactly on the 80% cumulative boundary and is therefore MAJOR.
    return main, _item(
        "SKU_TAIL", weekly_sales=(0.0,) * REQUIRED_SALES_WEEKS, revenue_amt=20.0
    )


def _by_sku(results):
    return {result.sku_code: result for result in results}


def test_pareto_grades_use_revenue_desc_then_sku_asc_and_pre_row_cutoff():
    # Input order deliberately differs from the deterministic grade order.
    items = (
        _item("SKU_B", revenue_amt=40),
        _item("SKU_C", revenue_amt=20),
        _item("SKU_A", revenue_amt=40),
    )

    grades = assign_pareto_grades(items)

    # Sorted order is A(40), B(40), C(20); cumulative ratios are .4, .8, 1.
    assert grades == {
        "SKU_A": GRADE_MAJOR,
        "SKU_B": GRADE_MAJOR,
        "SKU_C": GRADE_MINOR,
    }


def test_pareto_row_that_crosses_cutoff_remains_major():
    items = (
        _item("SKU_A", revenue_amt=70),
        _item("SKU_B", revenue_amt=20),
        _item("SKU_C", revenue_amt=10),
    )

    assert assign_pareto_grades(items) == {
        "SKU_A": GRADE_MAJOR,
        "SKU_B": GRADE_MAJOR,
        "SKU_C": GRADE_MINOR,
    }


def test_pareto_total_revenue_zero_assigns_every_sku_minor():
    items = (
        _item("SKU_A", revenue_amt=0),
        _item("SKU_B", revenue_amt=0),
    )

    assert assign_pareto_grades(items) == {
        "SKU_A": GRADE_MINOR,
        "SKU_B": GRADE_MINOR,
    }


def test_fixed_specification_vectors_match_for_both_policy_modes_without_rounding():
    inputs = _major_batch(_item())

    both_modes = calculate_both_policy_modes(inputs)
    cash = _by_sku(both_modes[POLICY_CASH])["SKU_MAIN"]
    shortage = _by_sku(both_modes[POLICY_SHORTAGE])["SKU_MAIN"]

    assert cash.grade == shortage.grade == GRADE_MAJOR
    assert cash.d_bar == pytest.approx(100.0)
    assert cash.sigma == pytest.approx(45.0)

    assert cash.transport_mode == "RAIL"
    assert cash.z_applied == pytest.approx(1.28)
    assert cash.lt_days == pytest.approx(36.6)
    assert cash.p_weeks == pytest.approx(9.22857142857143)
    assert cash.sigma_l_weeks == pytest.approx(1.15)
    assert cash.layer1 == pytest.approx(522.857142857143)
    assert cash.layer2_ss_raw == pytest.approx(228.661376587427)
    assert cash.layer2_ss == pytest.approx(228.661376587427)
    assert cash.ss_clamp == SS_CLAMP_NONE
    assert cash.reorder_point_s is None
    assert cash.layer3 == pytest.approx(400.0)
    assert cash.target_stock_s == pytest.approx(1151.51851944457)
    assert cash.suggested_qty == pytest.approx(1152.0)
    assert cash.ip_without_incoming == 0
    assert cash.upper_suggested_qty == pytest.approx(1152.0)

    assert shortage.transport_mode == "SEA"
    assert shortage.z_applied == pytest.approx(1.68)
    assert shortage.lt_days == pytest.approx(72.9)
    assert shortage.p_weeks == pytest.approx(14.4142857142857)
    assert shortage.sigma_l_weeks == pytest.approx(2.18)
    assert shortage.layer1 == pytest.approx(1041.42857142857)
    assert shortage.layer2_ss_raw == pytest.approx(465.311260985590)
    assert shortage.layer2_ss == pytest.approx(465.311260985590)
    assert shortage.ss_clamp == SS_CLAMP_NONE
    assert shortage.reorder_point_s is None
    assert shortage.layer3 == pytest.approx(400.0)
    assert shortage.target_stock_s == pytest.approx(1906.73983241416)
    assert shortage.suggested_qty == pytest.approx(1907.0)
    assert shortage.upper_suggested_qty == pytest.approx(1907.0)

    # Public result payloads contain only JSON-friendly values.
    json.dumps(cash.as_dict(), ensure_ascii=False)


def test_entity_policy_transport_mapping_can_use_air_for_cash() -> None:
    config = OrderLogicConfig(
        cash_transport_mode="AIR",
        shortage_transport_mode="SEA",
        lt_air_days=6.0,
        sigma_l_air_weeks=0.5,
        lt_sea_days=28.0,
        sigma_l_sea_weeks=1.0,
    )

    cash = calculate_sku_order(
        _item(), grade=GRADE_MAJOR, policy_mode=POLICY_CASH, config=config
    )
    shortage = calculate_sku_order(
        _item(), grade=GRADE_MAJOR, policy_mode=POLICY_SHORTAGE, config=config
    )

    assert (cash.transport_mode, cash.lt_days, cash.sigma_l_weeks) == (
        "AIR",
        6.0,
        0.5,
    )
    assert (shortage.transport_mode, shortage.lt_days, shortage.sigma_l_weeks) == (
        "SEA",
        28.0,
        1.0,
    )


def test_safety_stock_is_clamped_before_target_stock():
    floor_result = calculate_sku_order(
        _item(weekly_sales=(100.0,) * REQUIRED_SALES_WEEKS),
        grade=GRADE_MAJOR,
        policy_mode=POLICY_CASH,
    )
    assert floor_result.sigma == 0
    assert floor_result.layer2_ss_raw == pytest.approx(147.2)
    assert floor_result.ss_floor == pytest.approx(200.0)
    assert floor_result.layer2_ss == pytest.approx(200.0)
    assert floor_result.ss_clamp == SS_CLAMP_FLOOR
    assert floor_result.reorder_point_s is None
    assert floor_result.target_stock_s == pytest.approx(
        floor_result.layer1 + floor_result.layer2_ss + floor_result.layer3
    )

    cap_result = calculate_sku_order(
        _item(weekly_sales=(1300.0,) + (0.0,) * (REQUIRED_SALES_WEEKS - 1)),
        grade=GRADE_MAJOR,
        policy_mode=POLICY_SHORTAGE,
    )
    assert cap_result.d_bar == pytest.approx(100.0)
    assert cap_result.layer2_ss_raw > 1300.0
    assert cap_result.ss_cap == pytest.approx(1300.0)
    assert cap_result.layer2_ss == pytest.approx(1300.0)
    assert cap_result.ss_clamp == SS_CLAMP_CAP


def test_ip_equal_to_target_does_not_order_and_quantity_rounds_up():
    base = calculate_sku_order(
        _item(),
        grade=GRADE_MAJOR,
        policy_mode=POLICY_CASH,
    )
    assert base.reorder_point_s is None
    assert base.target_stock_s is not None

    exact_boundary = calculate_sku_order(
        replace(_item(), qty_local_available=base.target_stock_s),
        grade=GRADE_MAJOR,
        policy_mode=POLICY_CASH,
    )
    assert exact_boundary.ip_total == exact_boundary.target_stock_s
    assert exact_boundary.need_order is False
    assert exact_boundary.raw_order_qty == 0
    assert exact_boundary.suggested_qty == 0

    # Pure (R,S): an IP 0.1 below S orders one unit after ceiling.
    rounded_quantity = calculate_sku_order(
        replace(
            _item(),
            qty_local_available=base.target_stock_s - 0.1,
        ),
        grade=GRADE_MAJOR,
        policy_mode=POLICY_CASH,
    )
    assert rounded_quantity.need_order is True
    assert rounded_quantity.raw_order_qty == pytest.approx(0.1)
    assert rounded_quantity.suggested_qty == pytest.approx(1.0)


def test_upper_quantity_excludes_incoming_and_can_trigger_without_base_order():
    base = calculate_sku_order(
        _item(),
        grade=GRADE_MAJOR,
        policy_mode=POLICY_CASH,
    )
    assert base.reorder_point_s is None
    assert base.target_stock_s is not None

    incoming = 300.0
    result = calculate_sku_order(
        _item(
            qty_incoming=incoming,
            qty_local_available=base.target_stock_s - 100.0,
        ),
        grade=GRADE_MAJOR,
        policy_mode=POLICY_CASH,
    )

    assert result.need_order is False
    assert result.suggested_qty == 0
    assert result.ip_without_incoming == pytest.approx(
        base.target_stock_s - 100.0
    )
    assert result.need_upper_order is True
    assert result.raw_upper_order_qty == pytest.approx(
        base.target_stock_s - (base.target_stock_s - 100.0)
    )
    assert result.upper_suggested_qty == pytest.approx(100.0)


def test_none_quantities_use_auditable_defaults():
    result = calculate_sku_order(
        _item(
            qty_incoming=None,
            qty_eu_available=None,
            qty_in_transit=None,
            qty_local_available=None,
        ),
        grade=GRADE_MAJOR,
        policy_mode=POLICY_CASH,
    )

    assert result.qty_incoming == 0
    assert result.qty_eu_available == 0
    assert result.qty_in_transit == 0
    assert result.qty_local_available == 0
    assert result.ip_total == 0
    assert set(result.warnings) == {
        WARNING_QTY_INCOMING_DEFAULTED,
        WARNING_QTY_EU_AVAILABLE_DEFAULTED,
        WARNING_QTY_TRANSIT_DEFAULTED,
        WARNING_QTY_LOCAL_AVAILABLE_DEFAULTED,
    }


@pytest.mark.parametrize(
    ("weekly_sales", "expected_status", "expected_flag"),
    [
        (
            (0.0,) * REQUIRED_SALES_WEEKS,
            SALES_STATUS_NO_SALES,
            "is_no_sales",
        ),
        (
            (10.0,) * 6 + (0.0,) * (REQUIRED_SALES_WEEKS - 6),
            SALES_STATUS_INTERMITTENT,
            "is_intermittent",
        ),
        (
            (1.0,) * (REQUIRED_SALES_WEEKS - 1) + (50.0,),
            SALES_STATUS_BULK_INCLUDED,
            "has_bulk_week",
        ),
    ],
)
def test_sales_quality_flags(weekly_sales, expected_status, expected_flag):
    result = calculate_sku_order(
        _item(weekly_sales=weekly_sales),
        grade=GRADE_MAJOR,
        policy_mode=POLICY_CASH,
    )

    assert result.sales_status == expected_status
    assert getattr(result, expected_flag) is True


def _bulk_case(weekly_sales):
    return calculate_sku_order(
        _item(weekly_sales=tuple(weekly_sales)),
        grade=GRADE_MAJOR,
        policy_mode=POLICY_CASH,
    )


def test_bulk_screen_compares_against_the_selling_week_mean():
    """대량포함은 실제 판매 주 평균과 비교한다(RS-017).

    무판매 주를 포함한 13주 평균과 비교하면 판매 주가 5주 미만인 SKU는
    수치와 무관하게 항상 3배를 넘는다(최대값 >= 총량/k, 평균 = 총량/13).
    PL 실측에서 계산대상의 46%가 이 구조적 확정 위반이었고, HQ는 일 단위라
    같은 왜곡이 88%까지 커졌다. 세 법인에서 판정 의미를 같게 맞춘다.
    """

    # 3주에 100개씩 균등: 판매된 주들 사이 편차가 없으므로 대량포함이 아니다.
    even = _bulk_case((100.0,) * 3 + (0.0,) * 10)
    assert even.weeks_with_sales == 3
    assert even.has_bulk_week is False

    # 판매 주가 간헐 기준을 넘고 균등하면 정상이다.
    steady = _bulk_case((20.0,) * 8 + (0.0,) * 5)
    assert steady.has_bulk_week is False
    assert steady.sales_status == SALES_STATUS_NORMAL

    # 매주 팔리는데 한 주만 폭증하면 계속 대량포함으로 잡는다.
    spike = _bulk_case((10.0,) * 12 + (400.0,))
    assert spike.has_bulk_week is True
    assert spike.sales_status == SALES_STATUS_BULK_INCLUDED


def test_order_quantity_still_uses_the_full_window_mean():
    """판정 기준만 바뀌고 발주량 산식의 d_bar는 13주 평균을 유지한다."""

    result = _bulk_case((100.0,) * 3 + (0.0,) * 10)
    assert result.d_bar == pytest.approx(300.0 / REQUIRED_SALES_WEEKS)


@pytest.mark.parametrize("weekly_sales", [(1.0,) * 12, (1.0,) * 14, None])
def test_non_13_week_history_is_flagged_and_not_calculated(weekly_sales):
    result = calculate_sku_order(
        _item(weekly_sales=weekly_sales),
        grade=GRADE_MAJOR,
        policy_mode=POLICY_CASH,
    )

    assert result.sales_status == SALES_STATUS_INSUFFICIENT
    assert result.is_data_insufficient is True
    assert result.d_bar is None
    assert result.sigma is None
    assert result.reorder_point_s is None
    assert result.need_order is None
    assert result.suggested_qty is None
    assert result.need_upper_order is None
    assert result.upper_suggested_qty is None


@pytest.mark.parametrize(
    "item",
    [
        _item(weekly_sales=(-1.0,) + (0.0,) * (REQUIRED_SALES_WEEKS - 1)),
        _item(weekly_sales=(math.nan,) + (0.0,) * (REQUIRED_SALES_WEEKS - 1)),
        _item(weekly_sales=(math.inf,) + (0.0,) * (REQUIRED_SALES_WEEKS - 1)),
        _item(revenue_amt=-1),
        _item(revenue_amt=math.nan),
        _item(qty_incoming=-1),
        _item(qty_eu_available=math.inf),
    ],
)
def test_negative_or_nonfinite_business_values_raise_validation_error(item):
    with pytest.raises(OrderLogicValidationError):
        calculate_sku_order(
            item,
            grade=GRADE_MAJOR,
            policy_mode=POLICY_CASH,
        )


def test_invalid_policy_and_duplicate_sku_fail_explicitly():
    with pytest.raises(OrderLogicValidationError, match="policy_mode"):
        calculate_order_batch((_item(),), policy_mode="UNKNOWN")

    with pytest.raises(OrderLogicValidationError, match="duplicate sku_code"):
        calculate_order_batch(
            (_item("DUPLICATE"), _item("DUPLICATE")),
            policy_mode=POLICY_CASH,
        )
