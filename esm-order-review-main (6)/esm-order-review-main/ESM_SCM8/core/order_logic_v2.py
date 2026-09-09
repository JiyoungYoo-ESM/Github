"""Pure calculation engine for the HQ/PL/USA order-logic v2 specification.

The module deliberately has no pandas, database, clock, or web dependencies.
Callers provide one value for each of the latest 13 *completed* sales weeks (or
91 completed calendar days for HQ) and an inventory snapshot.  Results retain
every material intermediate value so a batch can be reproduced and audited by
the integration layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from numbers import Real
from statistics import fmean, stdev
from typing import Iterable, Sequence


POLICY_CASH = "CASH"
POLICY_SHORTAGE = "SHORTAGE"
SUPPORTED_POLICY_MODES = (POLICY_CASH, POLICY_SHORTAGE)

TRANSPORT_AIR = "AIR"
TRANSPORT_RAIL = "RAIL"
TRANSPORT_SEA = "SEA"
SUPPORTED_TRANSPORT_MODES = (TRANSPORT_AIR, TRANSPORT_RAIL, TRANSPORT_SEA)

GRADE_MAJOR = "MAJOR"
GRADE_MINOR = "MINOR"
SUPPORTED_GRADES = (GRADE_MAJOR, GRADE_MINOR)

SALES_STATUS_NORMAL = "정상"
SALES_STATUS_NO_SALES = "판매없음"
SALES_STATUS_INTERMITTENT = "⚠확인(간헐)"
SALES_STATUS_BULK_INCLUDED = "⚠대량포함"
SALES_STATUS_INSUFFICIENT = "데이터부족"

SS_CLAMP_NONE = "NONE"
SS_CLAMP_FLOOR = "FLOOR"
SS_CLAMP_CAP = "CAP"

REQUIRED_SALES_WEEKS = 13
# HQ/OPO demand grain is SKU x calendar day over the last completed 91 days.
REQUIRED_HQ_SALES_DAYS = 91

TRANSPORT_HQ_DOMESTIC = "HQ_DOMESTIC"

WARNING_QTY_INCOMING_DEFAULTED = "QTY_INCOMING_DEFAULTED_TO_ZERO"
WARNING_QTY_EU_AVAILABLE_DEFAULTED = "QTY_EU_AVAILABLE_DEFAULTED_TO_ZERO"
WARNING_QTY_TRANSIT_DEFAULTED = "QTY_TRANSIT_DEFAULTED_TO_ZERO"
WARNING_QTY_LOCAL_AVAILABLE_DEFAULTED = "QTY_LOCAL_AVAILABLE_DEFAULTED_TO_ZERO"


class OrderLogicValidationError(ValueError):
    """Raised when an input cannot be used without silently changing its meaning."""


def _finite_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise OrderLogicValidationError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise OrderLogicValidationError(f"{name} must be a finite number")
    return result


def _nonnegative_number(name: str, value: object) -> float:
    result = _finite_number(name, value)
    if result < 0:
        raise OrderLogicValidationError(f"{name} must be non-negative")
    return result


def _positive_number(name: str, value: object) -> float:
    result = _finite_number(name, value)
    if result <= 0:
        raise OrderLogicValidationError(f"{name} must be greater than zero")
    return result


@dataclass(frozen=True, slots=True)
class OrderLogicConfig:
    """Reviewed v2 policy parameters.

    Defaults are the fixed values in the web implementation specification.
    A config is immutable so a caller can safely attach its serialized value to
    a calculation-run audit record.
    """

    grade_cutoff: float = 0.80
    # Periodic-review interval R.  The legacy field name is retained in the
    # request/result snapshot for API compatibility; it is no longer an
    # additional buffer on top of a one-week review period.
    cover_weeks: float = 4.0
    ss_floor_weeks: float = 2.0
    ss_cap_weeks: float = 13.0

    lt_air_days: float = 16.4
    lt_rail_days: float = 36.6
    lt_sea_days: float = 72.9
    sigma_l_air_weeks: float = 0.68
    sigma_l_rail_weeks: float = 1.15
    sigma_l_sea_weeks: float = 2.18

    cash_transport_mode: str = TRANSPORT_RAIL
    shortage_transport_mode: str = TRANSPORT_SEA

    z_cash_major: float = 1.28
    z_cash_minor: float = 1.08
    z_shortage_major: float = 1.68
    z_shortage_minor: float = 1.28

    def __post_init__(self) -> None:
        cutoff = _finite_number("grade_cutoff", self.grade_cutoff)
        if not 0 <= cutoff <= 1:
            raise OrderLogicValidationError("grade_cutoff must be between zero and one")

        _nonnegative_number("cover_weeks", self.cover_weeks)
        floor = _nonnegative_number("ss_floor_weeks", self.ss_floor_weeks)
        cap = _nonnegative_number("ss_cap_weeks", self.ss_cap_weeks)
        if cap < floor:
            raise OrderLogicValidationError(
                "ss_cap_weeks must be greater than or equal to ss_floor_weeks"
            )

        _positive_number("lt_air_days", self.lt_air_days)
        _positive_number("lt_rail_days", self.lt_rail_days)
        _positive_number("lt_sea_days", self.lt_sea_days)
        _nonnegative_number("sigma_l_air_weeks", self.sigma_l_air_weeks)
        _nonnegative_number("sigma_l_rail_weeks", self.sigma_l_rail_weeks)
        _nonnegative_number("sigma_l_sea_weeks", self.sigma_l_sea_weeks)

        if self.cash_transport_mode not in SUPPORTED_TRANSPORT_MODES:
            raise OrderLogicValidationError(
                "cash_transport_mode must be AIR, RAIL, or SEA"
            )
        if self.shortage_transport_mode not in SUPPORTED_TRANSPORT_MODES:
            raise OrderLogicValidationError(
                "shortage_transport_mode must be AIR, RAIL, or SEA"
            )

        _positive_number("z_cash_major", self.z_cash_major)
        _positive_number("z_cash_minor", self.z_cash_minor)
        _positive_number("z_shortage_major", self.z_shortage_major)
        _positive_number("z_shortage_minor", self.z_shortage_minor)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


DEFAULT_CONFIG = OrderLogicConfig()


@dataclass(frozen=True, slots=True)
class HQOrderLogicConfig:
    """Reviewed HQ/OPO policy parameters in day units.

    HQ replenishes from domestic suppliers into one warehouse, so a single
    measured lead time applies to both scenarios and only ``Z`` changes
    (RS-004, RS-006).  Every period field is a calendar day (RS-011).
    """

    grade_cutoff: float = 0.80
    review_days: float = 28.0
    ss_floor_days: float = 14.0
    ss_cap_days: float = 35.0

    lt_days: float = 0.0
    sigma_l_days: float = 0.0

    z_cash_major: float = 1.28
    z_cash_minor: float = 1.08
    z_shortage_major: float = 1.68
    z_shortage_minor: float = 1.28

    def __post_init__(self) -> None:
        cutoff = _finite_number("grade_cutoff", self.grade_cutoff)
        if not 0 <= cutoff <= 1:
            raise OrderLogicValidationError("grade_cutoff must be between zero and one")
        _positive_number("review_days", self.review_days)
        floor = _nonnegative_number("ss_floor_days", self.ss_floor_days)
        cap = _nonnegative_number("ss_cap_days", self.ss_cap_days)
        if cap < floor:
            raise OrderLogicValidationError(
                "ss_cap_days must be greater than or equal to ss_floor_days"
            )
        # A measured HQ lead time is required; the source adapter must fail
        # closed instead of sending a placeholder (RS-006, RS-007).
        _positive_number("lt_days", self.lt_days)
        _nonnegative_number("sigma_l_days", self.sigma_l_days)
        _positive_number("z_cash_major", self.z_cash_major)
        _positive_number("z_cash_minor", self.z_cash_minor)
        _positive_number("z_shortage_major", self.z_shortage_major)
        _positive_number("z_shortage_minor", self.z_shortage_minor)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SKUOrderInput:
    """One SKU's sales history and inventory snapshot."""

    sku_code: str
    weekly_sales: Sequence[float] | None
    revenue_amt: float
    qty_incoming: float | None = 0.0
    qty_eu_available: float | None = 0.0
    qty_in_transit: float | None = 0.0
    qty_local_available: float | None = 0.0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OrderLogicResult:
    """One auditable SKU result.

    Numerical calculation fields are ``None`` when the input does not contain
    exactly 12 completed weeks.  Such a row is retained with ``데이터부족`` so
    the caller can show it separately instead of silently dropping the SKU.
    """

    sku_code: str
    grade: str
    policy_mode: str
    sales_status: str
    sales_history_count: int
    weeks_with_sales: int
    is_data_insufficient: bool
    is_no_sales: bool
    is_intermittent: bool
    has_bulk_week: bool

    d_bar: float | None
    sigma: float | None
    z_applied: float
    transport_mode: str
    lt_days: float
    p_weeks: float
    sigma_l_weeks: float

    layer1: float | None
    layer2_ss_raw: float | None
    ss_floor: float | None
    ss_cap: float | None
    layer2_ss: float | None
    ss_clamp: str | None
    layer3: float | None
    reorder_point_s: float | None
    target_stock_s: float | None

    qty_incoming: float
    qty_eu_available: float
    qty_in_transit: float
    qty_local_available: float
    ip_total: float
    need_order: bool | None
    raw_order_qty: float | None
    suggested_qty: float | None
    ip_without_incoming: float
    need_upper_order: bool | None
    raw_upper_order_qty: float | None
    upper_suggested_qty: float | None
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PeriodicRSCalculation:
    """Unit-agnostic pure periodic-review calculation.

    Demand, lead time, review period and lead-time deviation must all use the
    same period unit.  HQ therefore calls this in days, while PL/USA call it in
    weeks.  No reorder point, MOQ or pack multiple is applied.
    """

    protection_periods: float
    layer1: float
    safety_stock_raw: float
    safety_stock_floor: float
    safety_stock_cap: float
    safety_stock: float
    safety_stock_clamp: str
    layer3: float
    target_stock: float
    inventory_position: float
    raw_order_qty: float
    suggested_qty: float


def calculate_periodic_rs(
    *,
    demand_mean: float,
    demand_stdev: float,
    lead_time_periods: float,
    lead_time_stdev_periods: float,
    review_periods: float,
    z_value: float,
    safety_stock_floor_periods: float,
    safety_stock_cap_periods: float,
    inventory_position: float,
) -> PeriodicRSCalculation:
    """Calculate ``S`` and ``ceil(max(0, S-IP))`` in one explicit unit."""

    d_bar = _nonnegative_number("demand_mean", demand_mean)
    sigma_d = _nonnegative_number("demand_stdev", demand_stdev)
    lead_time = _nonnegative_number("lead_time_periods", lead_time_periods)
    sigma_l = _nonnegative_number(
        "lead_time_stdev_periods", lead_time_stdev_periods
    )
    review = _nonnegative_number("review_periods", review_periods)
    z_applied = _positive_number("z_value", z_value)
    floor_periods = _nonnegative_number(
        "safety_stock_floor_periods", safety_stock_floor_periods
    )
    cap_periods = _nonnegative_number(
        "safety_stock_cap_periods", safety_stock_cap_periods
    )
    if cap_periods < floor_periods:
        raise OrderLogicValidationError(
            "safety_stock_cap_periods must be greater than or equal to "
            "safety_stock_floor_periods"
        )
    ip = _nonnegative_number("inventory_position", inventory_position)

    protection = lead_time + review
    layer1 = d_bar * lead_time
    ss_raw = z_applied * math.sqrt(
        protection * sigma_d**2 + d_bar**2 * sigma_l**2
    )
    ss_floor = d_bar * floor_periods
    ss_cap = d_bar * cap_periods
    if ss_raw < ss_floor:
        safety_stock = ss_floor
        clamp = SS_CLAMP_FLOOR
    elif ss_raw > ss_cap:
        safety_stock = ss_cap
        clamp = SS_CLAMP_CAP
    else:
        safety_stock = ss_raw
        clamp = SS_CLAMP_NONE
    layer3 = d_bar * review
    target_stock = layer1 + safety_stock + layer3
    raw_order_qty = max(0.0, target_stock - ip)
    return PeriodicRSCalculation(
        protection_periods=protection,
        layer1=layer1,
        safety_stock_raw=ss_raw,
        safety_stock_floor=ss_floor,
        safety_stock_cap=ss_cap,
        safety_stock=safety_stock,
        safety_stock_clamp=clamp,
        layer3=layer3,
        target_stock=target_stock,
        inventory_position=ip,
        raw_order_qty=raw_order_qty,
        suggested_qty=float(math.ceil(raw_order_qty)),
    )


def _validated_sku_code(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OrderLogicValidationError("sku_code must be a non-empty string")
    return value


def _validated_policy_mode(value: object) -> str:
    if value not in SUPPORTED_POLICY_MODES:
        allowed = ", ".join(SUPPORTED_POLICY_MODES)
        raise OrderLogicValidationError(f"policy_mode must be one of: {allowed}")
    return str(value)


def _validated_grade(value: object) -> str:
    if value not in SUPPORTED_GRADES:
        allowed = ", ".join(SUPPORTED_GRADES)
        raise OrderLogicValidationError(f"grade must be one of: {allowed}")
    return str(value)


def _validated_sales_history(
    weekly_sales: Sequence[float] | None,
) -> tuple[float, ...]:
    if weekly_sales is None:
        return ()
    if isinstance(weekly_sales, (str, bytes)) or not isinstance(weekly_sales, Sequence):
        raise OrderLogicValidationError("weekly_sales must be a sequence of numbers")
    return tuple(
        _nonnegative_number(f"weekly_sales[{index}]", value)
        for index, value in enumerate(weekly_sales)
    )


def _resolve_quantity(
    name: str,
    value: object,
    warning_code: str,
    warnings: list[str],
) -> float:
    if value is None:
        warnings.append(warning_code)
        return 0.0
    return _nonnegative_number(name, value)


def _resolve_inventory(
    item: SKUOrderInput,
) -> tuple[float, float, float, float, tuple[str, ...]]:
    warnings: list[str] = []
    qty_incoming = _resolve_quantity(
        "qty_incoming",
        item.qty_incoming,
        WARNING_QTY_INCOMING_DEFAULTED,
        warnings,
    )
    qty_eu_available = _resolve_quantity(
        "qty_eu_available",
        item.qty_eu_available,
        WARNING_QTY_EU_AVAILABLE_DEFAULTED,
        warnings,
    )
    qty_in_transit = _resolve_quantity(
        "qty_in_transit",
        item.qty_in_transit,
        WARNING_QTY_TRANSIT_DEFAULTED,
        warnings,
    )
    qty_local_available = _resolve_quantity(
        "qty_local_available",
        item.qty_local_available,
        WARNING_QTY_LOCAL_AVAILABLE_DEFAULTED,
        warnings,
    )

    return (
        qty_incoming,
        qty_eu_available,
        qty_in_transit,
        qty_local_available,
        tuple(warnings),
    )


def resolve_policy_lead_time(
    policy_mode: str,
    config: OrderLogicConfig = DEFAULT_CONFIG,
) -> tuple[str, float, float]:
    """Return the V2 transport, measured mean days and sigma weeks.

    This public helper lets adjacent preview calculations consume the exact
    server-resolved V2 lead-time policy without copying its scenario mapping.
    """

    resolved_policy_mode = _validated_policy_mode(policy_mode)
    transport_mode = (
        config.cash_transport_mode
        if resolved_policy_mode == POLICY_CASH
        else config.shortage_transport_mode
    )
    lead_time_by_mode = {
        TRANSPORT_AIR: float(config.lt_air_days),
        TRANSPORT_RAIL: float(config.lt_rail_days),
        TRANSPORT_SEA: float(config.lt_sea_days),
    }
    sigma_by_mode = {
        TRANSPORT_AIR: float(config.sigma_l_air_weeks),
        TRANSPORT_RAIL: float(config.sigma_l_rail_weeks),
        TRANSPORT_SEA: float(config.sigma_l_sea_weeks),
    }
    return (
        transport_mode,
        lead_time_by_mode[transport_mode],
        sigma_by_mode[transport_mode],
    )


def _policy_parameters(
    policy_mode: str,
    grade: str,
    config: OrderLogicConfig,
) -> tuple[str, float, float, float, float]:
    if policy_mode == POLICY_CASH:
        transport_mode = config.cash_transport_mode
        z_applied = (
            float(config.z_cash_major)
            if grade == GRADE_MAJOR
            else float(config.z_cash_minor)
        )
    else:
        transport_mode = config.shortage_transport_mode
        z_applied = (
            float(config.z_shortage_major)
            if grade == GRADE_MAJOR
            else float(config.z_shortage_minor)
        )
    transport_mode, lt_days, sigma_l_weeks = resolve_policy_lead_time(
        policy_mode,
        config,
    )
    p_weeks = (lt_days / 7.0) + float(config.cover_weeks)
    return transport_mode, lt_days, p_weeks, sigma_l_weeks, z_applied


def assign_pareto_grades(
    items: Iterable[SKUOrderInput],
    *,
    config: OrderLogicConfig = DEFAULT_CONFIG,
) -> dict[str, str]:
    """Assign deterministic revenue grades.

    Rows are ordered by ``revenue_amt`` descending and then ``sku_code``
    ascending.  Per the technical specification, a row is MAJOR when the
    cumulative revenue *before* that row is strictly below ``grade_cutoff``.
    This means the row that crosses 80% remains MAJOR and the next row becomes
    MINOR.  A zero-revenue population is entirely MINOR.
    """

    materialized = tuple(items)
    revenue_by_sku: dict[str, float] = {}
    for item in materialized:
        sku_code = _validated_sku_code(item.sku_code)
        if sku_code in revenue_by_sku:
            raise OrderLogicValidationError(f"duplicate sku_code: {sku_code}")
        revenue_by_sku[sku_code] = _nonnegative_number(
            f"revenue_amt[{sku_code}]",
            item.revenue_amt,
        )

    total_revenue = sum(revenue_by_sku.values())
    if total_revenue == 0:
        return {sku_code: GRADE_MINOR for sku_code in revenue_by_sku}

    ordered = sorted(
        revenue_by_sku.items(),
        key=lambda pair: (-pair[1], pair[0]),
    )
    cumulative_revenue = 0.0
    grades: dict[str, str] = {}
    cutoff = float(config.grade_cutoff)
    for sku_code, revenue in ordered:
        cumulative_ratio_before = cumulative_revenue / total_revenue
        grades[sku_code] = (
            GRADE_MAJOR if cumulative_ratio_before < cutoff else GRADE_MINOR
        )
        cumulative_revenue += revenue
    return grades


def _order_quantity(
    *,
    inventory_position: float,
    target_stock: float,
) -> tuple[bool, float, float]:
    """Return pure periodic-review (R,S) quantity without an ``IP < s`` gate."""

    raw_order_qty = max(0.0, target_stock - inventory_position)
    return raw_order_qty > 0.0, raw_order_qty, float(math.ceil(raw_order_qty))


def calculate_sku_order(
    item: SKUOrderInput,
    *,
    grade: str,
    policy_mode: str,
    config: OrderLogicConfig = DEFAULT_CONFIG,
) -> OrderLogicResult:
    """Calculate one SKU after its Pareto grade has been assigned."""

    sku_code = _validated_sku_code(item.sku_code)
    resolved_grade = _validated_grade(grade)
    resolved_policy_mode = _validated_policy_mode(policy_mode)
    _nonnegative_number("revenue_amt", item.revenue_amt)
    sales_history = _validated_sales_history(item.weekly_sales)

    (
        qty_incoming,
        qty_eu_available,
        qty_in_transit,
        qty_local_available,
        warnings,
    ) = _resolve_inventory(item)
    ip_total = (
        qty_incoming
        + qty_eu_available
        + qty_in_transit
        + qty_local_available
    )
    ip_without_incoming = ip_total - qty_incoming

    (
        transport_mode,
        lt_days,
        p_weeks,
        sigma_l_weeks,
        z_applied,
    ) = _policy_parameters(
        resolved_policy_mode,
        resolved_grade,
        config,
    )

    history_count = len(sales_history)
    weeks_with_sales = sum(value > 0 for value in sales_history)
    if history_count != REQUIRED_SALES_WEEKS:
        return OrderLogicResult(
            sku_code=sku_code,
            grade=resolved_grade,
            policy_mode=resolved_policy_mode,
            sales_status=SALES_STATUS_INSUFFICIENT,
            sales_history_count=history_count,
            weeks_with_sales=weeks_with_sales,
            is_data_insufficient=True,
            is_no_sales=False,
            is_intermittent=False,
            has_bulk_week=False,
            d_bar=None,
            sigma=None,
            z_applied=z_applied,
            transport_mode=transport_mode,
            lt_days=lt_days,
            p_weeks=p_weeks,
            sigma_l_weeks=sigma_l_weeks,
            layer1=None,
            layer2_ss_raw=None,
            ss_floor=None,
            ss_cap=None,
            layer2_ss=None,
            ss_clamp=None,
            layer3=None,
            reorder_point_s=None,
            target_stock_s=None,
            qty_incoming=qty_incoming,
            qty_eu_available=qty_eu_available,
            qty_in_transit=qty_in_transit,
            qty_local_available=qty_local_available,
            ip_total=ip_total,
            need_order=None,
            raw_order_qty=None,
            suggested_qty=None,
            ip_without_incoming=ip_without_incoming,
            need_upper_order=None,
            raw_upper_order_qty=None,
            upper_suggested_qty=None,
            warnings=warnings,
        )

    d_bar = fmean(sales_history)
    sigma = stdev(sales_history)
    is_no_sales = d_bar == 0
    is_intermittent = not is_no_sales and weeks_with_sales < 7
    # 대량포함은 판매가 있었던 주들 사이에서 유독 튀는 주를 찾는 신호다.
    # 무판매 주를 포함한 13주 평균과 비교하면, 판매 주가 5주 미만인 SKU는
    # 수치와 무관하게 항상 3배를 넘는다(최대값 >= 총량/k, 평균 = 총량/13이므로
    # 비율이 13/k 이상으로 강제된다). 판정 의미를 세 법인에서 같게 유지하려고
    # HQ와 동일하게 실제 판매 기간 평균과 비교한다(RS-017).
    mean_on_selling_weeks = (
        (d_bar * float(history_count)) / float(weeks_with_sales)
        if weeks_with_sales
        else 0.0
    )
    has_bulk_week = (
        not is_no_sales and max(sales_history) > 3.0 * mean_on_selling_weeks
    )

    if is_no_sales:
        sales_status = SALES_STATUS_NO_SALES
    elif is_intermittent:
        sales_status = SALES_STATUS_INTERMITTENT
    elif has_bulk_week:
        sales_status = SALES_STATUS_BULK_INCLUDED
    else:
        sales_status = SALES_STATUS_NORMAL

    rs = calculate_periodic_rs(
        demand_mean=d_bar,
        demand_stdev=sigma,
        lead_time_periods=lt_days / 7.0,
        lead_time_stdev_periods=sigma_l_weeks,
        review_periods=float(config.cover_weeks),
        z_value=z_applied,
        safety_stock_floor_periods=float(config.ss_floor_weeks),
        safety_stock_cap_periods=float(config.ss_cap_weeks),
        inventory_position=ip_total,
    )
    layer1 = rs.layer1
    layer2_ss_raw = rs.safety_stock_raw
    ss_floor = rs.safety_stock_floor
    ss_cap = rs.safety_stock_cap
    layer2_ss = rs.safety_stock
    ss_clamp = rs.safety_stock_clamp
    layer3 = rs.layer3
    # Pure periodic-review (R,S): S covers lead time, the review interval and
    # safety stock.  ``reorder_point_s`` remains null as a deprecated response
    # field so older clients do not mistake a derived value for an order gate.
    reorder_point_s = None
    target_stock_s = rs.target_stock

    need_order = rs.raw_order_qty > 0.0
    raw_order_qty = rs.raw_order_qty
    suggested_qty = rs.suggested_qty
    (
        need_upper_order,
        raw_upper_order_qty,
        upper_suggested_qty,
    ) = _order_quantity(
        inventory_position=ip_without_incoming,
        target_stock=target_stock_s,
    )

    return OrderLogicResult(
        sku_code=sku_code,
        grade=resolved_grade,
        policy_mode=resolved_policy_mode,
        sales_status=sales_status,
        sales_history_count=history_count,
        weeks_with_sales=weeks_with_sales,
        is_data_insufficient=False,
        is_no_sales=is_no_sales,
        is_intermittent=is_intermittent,
        has_bulk_week=has_bulk_week,
        d_bar=d_bar,
        sigma=sigma,
        z_applied=z_applied,
        transport_mode=transport_mode,
        lt_days=lt_days,
        p_weeks=p_weeks,
        sigma_l_weeks=sigma_l_weeks,
        layer1=layer1,
        layer2_ss_raw=layer2_ss_raw,
        ss_floor=ss_floor,
        ss_cap=ss_cap,
        layer2_ss=layer2_ss,
        ss_clamp=ss_clamp,
        layer3=layer3,
        reorder_point_s=reorder_point_s,
        target_stock_s=target_stock_s,
        qty_incoming=qty_incoming,
        qty_eu_available=qty_eu_available,
        qty_in_transit=qty_in_transit,
        qty_local_available=qty_local_available,
        ip_total=ip_total,
        need_order=need_order,
        raw_order_qty=raw_order_qty,
        suggested_qty=suggested_qty,
        ip_without_incoming=ip_without_incoming,
        need_upper_order=need_upper_order,
        raw_upper_order_qty=raw_upper_order_qty,
        upper_suggested_qty=upper_suggested_qty,
        warnings=warnings,
    )


def calculate_hq_sku_order(
    item: SKUOrderInput,
    *,
    grade: str,
    policy_mode: str,
    config: HQOrderLogicConfig,
) -> OrderLogicResult:
    """Calculate one HQ/OPO SKU in day units.

    ``item.weekly_sales`` carries the 84 completed daily demand values for HQ.
    The field name is retained so the result contract, Pareto population and
    integration layer stay identical across entities; only the period unit
    differs.  Both scenarios share one measured domestic lead time and differ
    only by ``Z`` (RS-004).
    """

    sku_code = _validated_sku_code(item.sku_code)
    resolved_grade = _validated_grade(grade)
    resolved_policy_mode = _validated_policy_mode(policy_mode)
    _nonnegative_number("revenue_amt", item.revenue_amt)
    daily_sales = _validated_sales_history(item.weekly_sales)

    (
        qty_incoming,
        qty_eu_available,
        qty_in_transit,
        qty_local_available,
        warnings,
    ) = _resolve_inventory(item)
    ip_total = (
        qty_incoming
        + qty_eu_available
        + qty_in_transit
        + qty_local_available
    )
    ip_without_incoming = ip_total - qty_incoming

    if resolved_policy_mode == POLICY_CASH:
        z_applied = (
            float(config.z_cash_major)
            if resolved_grade == GRADE_MAJOR
            else float(config.z_cash_minor)
        )
    else:
        z_applied = (
            float(config.z_shortage_major)
            if resolved_grade == GRADE_MAJOR
            else float(config.z_shortage_minor)
        )
    lt_days = float(config.lt_days)
    sigma_l_days = float(config.sigma_l_days)
    protection_days = lt_days + float(config.review_days)

    history_count = len(daily_sales)
    days_with_sales = sum(value > 0 for value in daily_sales)
    if history_count != REQUIRED_HQ_SALES_DAYS:
        return OrderLogicResult(
            sku_code=sku_code,
            grade=resolved_grade,
            policy_mode=resolved_policy_mode,
            sales_status=SALES_STATUS_INSUFFICIENT,
            sales_history_count=history_count,
            weeks_with_sales=days_with_sales,
            is_data_insufficient=True,
            is_no_sales=False,
            is_intermittent=False,
            has_bulk_week=False,
            d_bar=None,
            sigma=None,
            z_applied=z_applied,
            transport_mode=TRANSPORT_HQ_DOMESTIC,
            lt_days=lt_days,
            p_weeks=protection_days,
            sigma_l_weeks=sigma_l_days,
            layer1=None,
            layer2_ss_raw=None,
            ss_floor=None,
            ss_cap=None,
            layer2_ss=None,
            ss_clamp=None,
            layer3=None,
            reorder_point_s=None,
            target_stock_s=None,
            qty_incoming=qty_incoming,
            qty_eu_available=qty_eu_available,
            qty_in_transit=qty_in_transit,
            qty_local_available=qty_local_available,
            ip_total=ip_total,
            need_order=None,
            raw_order_qty=None,
            suggested_qty=None,
            ip_without_incoming=ip_without_incoming,
            need_upper_order=None,
            raw_upper_order_qty=None,
            upper_suggested_qty=None,
            warnings=warnings,
        )

    d_bar = fmean(daily_sales)
    sigma = stdev(daily_sales)
    is_no_sales = d_bar == 0
    # HQ는 간헐 판정을 적용하지 않는다(RS-018).
    #
    # PL/USA는 13주 표본에서 7주 판매 기준을 유지한다. 이를 일 단위 비율로
    # 옮긴 `91일 중 49일`은 주말·공휴일이 처음부터 0으로 고정되어 HQ 정상
    # 조달 패턴을 과도하게 간헐로 분류한다. 사용자 결정에 따라 HQ에는 이
    # 판정을 적용하지 않는다(RS-018, RS-024).
    is_intermittent = False
    # 대량포함은 판매가 있었던 날들 사이에서 유독 튀는 날을 찾는 신호다.
    # 무판매일을 포함한 91일 평균과 비교하면, 판매일이 31일 미만인 SKU는
    # 실제 수치와 무관하게 항상 3배를 넘는다(최대값 >= 총량/k, 평균 =
    # 총량/91이므로 비율이 91/k 이상으로 강제된다). 본사 국내조달은 물량이
    # 며칠에 몰려 들어오는 정상 패턴이라 이 구조적 확정 위반이 전건에 걸렸다.
    # 그래서 비교 기준을 실제 판매일 평균으로 바꾼다.
    mean_on_selling_days = (
        (d_bar * float(history_count)) / float(days_with_sales)
        if days_with_sales
        else 0.0
    )
    has_bulk_day = (
        not is_no_sales and max(daily_sales) > 3.0 * mean_on_selling_days
    )

    if is_no_sales:
        sales_status = SALES_STATUS_NO_SALES
    elif has_bulk_day:
        sales_status = SALES_STATUS_BULK_INCLUDED
    else:
        sales_status = SALES_STATUS_NORMAL

    rs = calculate_periodic_rs(
        demand_mean=d_bar,
        demand_stdev=sigma,
        lead_time_periods=lt_days,
        lead_time_stdev_periods=sigma_l_days,
        review_periods=float(config.review_days),
        z_value=z_applied,
        safety_stock_floor_periods=float(config.ss_floor_days),
        safety_stock_cap_periods=float(config.ss_cap_days),
        inventory_position=ip_total,
    )
    (
        need_upper_order,
        raw_upper_order_qty,
        upper_suggested_qty,
    ) = _order_quantity(
        inventory_position=ip_without_incoming,
        target_stock=rs.target_stock,
    )
    return OrderLogicResult(
        sku_code=sku_code,
        grade=resolved_grade,
        policy_mode=resolved_policy_mode,
        sales_status=sales_status,
        sales_history_count=history_count,
        weeks_with_sales=days_with_sales,
        is_data_insufficient=False,
        is_no_sales=is_no_sales,
        is_intermittent=is_intermittent,
        has_bulk_week=has_bulk_day,
        d_bar=d_bar,
        sigma=sigma,
        z_applied=z_applied,
        transport_mode=TRANSPORT_HQ_DOMESTIC,
        lt_days=lt_days,
        p_weeks=rs.protection_periods,
        sigma_l_weeks=sigma_l_days,
        layer1=rs.layer1,
        layer2_ss_raw=rs.safety_stock_raw,
        ss_floor=rs.safety_stock_floor,
        ss_cap=rs.safety_stock_cap,
        layer2_ss=rs.safety_stock,
        ss_clamp=rs.safety_stock_clamp,
        layer3=rs.layer3,
        reorder_point_s=None,
        target_stock_s=rs.target_stock,
        qty_incoming=qty_incoming,
        qty_eu_available=qty_eu_available,
        qty_in_transit=qty_in_transit,
        qty_local_available=qty_local_available,
        ip_total=ip_total,
        need_order=rs.raw_order_qty > 0.0,
        raw_order_qty=rs.raw_order_qty,
        suggested_qty=rs.suggested_qty,
        ip_without_incoming=ip_without_incoming,
        need_upper_order=need_upper_order,
        raw_upper_order_qty=raw_upper_order_qty,
        upper_suggested_qty=upper_suggested_qty,
        warnings=warnings,
    )


def calculate_order_batch(
    items: Iterable[SKUOrderInput],
    *,
    policy_mode: str,
    config: OrderLogicConfig = DEFAULT_CONFIG,
) -> list[OrderLogicResult]:
    """Assign Pareto grades and calculate one result per input SKU."""

    materialized = tuple(items)
    resolved_policy_mode = _validated_policy_mode(policy_mode)
    grades = assign_pareto_grades(materialized, config=config)
    return [
        calculate_sku_order(
            item,
            grade=grades[item.sku_code],
            policy_mode=resolved_policy_mode,
            config=config,
        )
        for item in materialized
    ]


def calculate_both_policy_modes(
    items: Iterable[SKUOrderInput],
    *,
    config: OrderLogicConfig = DEFAULT_CONFIG,
) -> dict[str, list[OrderLogicResult]]:
    """Calculate the same immutable input snapshot under both policy modes."""

    materialized = tuple(items)
    return {
        POLICY_CASH: calculate_order_batch(
            materialized,
            policy_mode=POLICY_CASH,
            config=config,
        ),
        POLICY_SHORTAGE: calculate_order_batch(
            materialized,
            policy_mode=POLICY_SHORTAGE,
            config=config,
        ),
    }


__all__ = [
    "DEFAULT_CONFIG",
    "GRADE_MAJOR",
    "GRADE_MINOR",
    "HQOrderLogicConfig",
    "OrderLogicConfig",
    "PeriodicRSCalculation",
    "OrderLogicResult",
    "OrderLogicValidationError",
    "POLICY_CASH",
    "POLICY_SHORTAGE",
    "REQUIRED_SALES_WEEKS",
    "REQUIRED_HQ_SALES_DAYS",
    "SALES_STATUS_BULK_INCLUDED",
    "SALES_STATUS_INSUFFICIENT",
    "SALES_STATUS_INTERMITTENT",
    "SALES_STATUS_NORMAL",
    "SALES_STATUS_NO_SALES",
    "SKUOrderInput",
    "SS_CLAMP_CAP",
    "SS_CLAMP_FLOOR",
    "SS_CLAMP_NONE",
    "TRANSPORT_HQ_DOMESTIC",
    "WARNING_QTY_EU_AVAILABLE_DEFAULTED",
    "WARNING_QTY_INCOMING_DEFAULTED",
    "WARNING_QTY_LOCAL_AVAILABLE_DEFAULTED",
    "WARNING_QTY_TRANSIT_DEFAULTED",
    "assign_pareto_grades",
    "calculate_both_policy_modes",
    "calculate_hq_sku_order",
    "calculate_order_batch",
    "calculate_periodic_rs",
    "calculate_sku_order",
    "resolve_policy_lead_time",
]
