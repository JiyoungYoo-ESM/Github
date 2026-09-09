"""Pure candidate V3 calculation engine for offline backtests.

This module deliberately has no CMS, database, clock, web, Excel, or V2
dependency.  It implements the documented V3 calculation flow when each
source operand is supplied explicitly by the caller:

    completed daily sales -> 13 completed weeks -> deseasonalise
    -> classify -> SES/HOLT/Croston -> future seasonalise -> Layers -> raw Q

It is *not* an operational order API.  Pack-size, MOQ, pallet and automatic
order-release constraints are intentionally excluded while V3-012 remains in
its raw-quantity phase.  Missing factors or policies fail closed; this module
never silently substitutes a factor of 1.0, a zero lead time, or an inventory
component.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
import math
from numbers import Real
from statistics import fmean, pstdev, stdev
from typing import Mapping, Sequence


REQUIRED_COMPLETED_PERIODS = 13
PERIOD_DAYS = 7

PATTERN_STABLE = "STABLE"
PATTERN_TREND_UP = "TREND_UP"
PATTERN_TREND_DOWN = "TREND_DOWN"
PATTERN_INTERMITTENT = "INTERMITTENT"
PATTERN_SHORT_HISTORY = "SHORT_HISTORY"

ENGINE_SES = "SES"
ENGINE_HOLT_DAMPED = "HOLT_DAMPED"
ENGINE_CROSTON_SBA = "CROSTON_SBA"
ENGINE_MOVING_AVERAGE = "MOVING_AVERAGE"

CONSTRAINT_STATUS_PENDING = "ORDER_CONSTRAINTS_PENDING"
CONSTRAINT_STATUS_PACK_ROUNDED = "PACK_ROUNDING_APPLIED"

# Approved order-unit rounding ladder (2026-09-08): outbox pack first,
# then inbox pack, then a fixed 10-unit fallback when neither is set.
ORDER_UNIT_SOURCE_OUTBOX = "OUTBOX"
ORDER_UNIT_SOURCE_INBOX = "INBOX"
ORDER_UNIT_SOURCE_FALLBACK_10 = "FALLBACK_10"
ORDER_UNIT_FALLBACK_QUANTITY = 10.0

INVENTORY_POLICY_SHORTAGE = "SHORTAGE"
INVENTORY_POLICY_CASH = "CASH"
SALES_GRADE_CORE = "CORE"
SALES_GRADE_GENERAL = "GENERAL"

TEXTBOOK_SEASONAL_SHRINKAGE_CONSTANT = 30.0
SEASONAL_OLDER_12_MONTH_WEIGHT = 1.0
SEASONAL_RECENT_12_MONTH_WEIGHT = 2.0
TEXTBOOK_NEW_SKU_MAX_CALENDAR_DAYS = 168
TEXTBOOK_NEW_SKU_PHI = 0.90

TEXTBOOK_Z_MATRIX = {
    (INVENTORY_POLICY_SHORTAGE, SALES_GRADE_CORE): 1.68,
    (INVENTORY_POLICY_SHORTAGE, SALES_GRADE_GENERAL): 1.28,
    (INVENTORY_POLICY_CASH, SALES_GRADE_CORE): 1.28,
    (INVENTORY_POLICY_CASH, SALES_GRADE_GENERAL): 1.08,
}


class V3CalculationError(ValueError):
    """Raised when candidate V3 inputs are invalid or insufficient."""


class V3PolicyRequiredError(V3CalculationError):
    """Raised instead of inventing an unapproved V3 policy or fallback."""


def _finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise V3CalculationError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise V3CalculationError(f"{name} must be a finite number")
    return result


def _nonnegative(name: str, value: object) -> float:
    result = _finite(name, value)
    if result < 0:
        raise V3CalculationError(f"{name} must be non-negative")
    return result


def _positive(name: str, value: object) -> float:
    result = _finite(name, value)
    if result <= 0:
        raise V3CalculationError(f"{name} must be greater than zero")
    return result


def _validated_sales(values: Sequence[float], *, name: str = "period_sales") -> tuple[float, ...]:
    result = tuple(_nonnegative(f"{name}[{index}]", value) for index, value in enumerate(values))
    if len(result) != REQUIRED_COMPLETED_PERIODS:
        raise V3CalculationError(
            f"{name} must contain exactly {REQUIRED_COMPLETED_PERIODS} completed weeks"
        )
    return result


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


@dataclass(frozen=True, slots=True)
class V3CandidateParameters:
    """Explicit parameters for one named backtest candidate.

    This class intentionally has no defaults.  Calling code must attach a
    parameter/version snapshot to every backtest run instead of turning the
    teaching material into a hidden operational default.
    """

    calculation_logic_version: str
    adi_threshold: float
    cv2_threshold: float
    trend_threshold: float
    alpha: float
    beta: float
    phi: float
    new_sku_max_calendar_days: int
    new_sku_phi: float
    holt_initialization: str
    croston_initialization: str
    layer2_seasonality_mode: str

    def __post_init__(self) -> None:
        if not self.calculation_logic_version.strip():
            raise V3CalculationError("calculation_logic_version is required")
        _positive("adi_threshold", self.adi_threshold)
        _nonnegative("cv2_threshold", self.cv2_threshold)
        _nonnegative("trend_threshold", self.trend_threshold)
        for name in ("alpha", "beta", "phi"):
            value = _finite(name, getattr(self, name))
            if not 0 < value <= 1:
                raise V3CalculationError(f"{name} must be greater than zero and at most one")
        if isinstance(self.new_sku_max_calendar_days, bool) or not isinstance(
            self.new_sku_max_calendar_days, int
        ):
            raise V3CalculationError("new_sku_max_calendar_days must be a positive integer")
        if self.new_sku_max_calendar_days <= 0:
            raise V3CalculationError("new_sku_max_calendar_days must be a positive integer")
        new_sku_phi = _finite("new_sku_phi", self.new_sku_phi)
        if not 0 < new_sku_phi <= 1:
            raise V3CalculationError("new_sku_phi must be greater than zero and at most one")
        if self.holt_initialization != "SIX_WEEK_REGRESSION":
            raise V3PolicyRequiredError(
                "holt_initialization must explicitly select SIX_WEEK_REGRESSION"
            )
        if self.croston_initialization != "FIRST_INTERVAL_FIRST_DEMAND":
            raise V3PolicyRequiredError(
                "croston_initialization must explicitly select FIRST_INTERVAL_FIRST_DEMAND"
            )
        if self.layer2_seasonality_mode != "SCALE_MEAN_AND_SIGMA_BY_FLR":
            raise V3PolicyRequiredError(
                "layer2_seasonality_mode must explicitly select SCALE_MEAN_AND_SIGMA_BY_FLR"
            )

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def textbook_candidate_parameters(*, logic_version: str) -> V3CandidateParameters:
    """Return the teaching-material values as a *named backtest candidate*.

    The guide marks CV² above 0.49 for stronger sigma treatment, but does not
    define a multiplier or formula. The unresolved adjustment is therefore
    not invented here; the selected engine's own RMSE/variance remains visible
    together with ``high_cv2`` until that formula is approved.
    """

    return V3CandidateParameters(
        calculation_logic_version=logic_version,
        adi_threshold=1.32,
        cv2_threshold=0.49,
        trend_threshold=0.20,
        alpha=0.20,
        beta=0.10,
        phi=0.90,
        new_sku_max_calendar_days=TEXTBOOK_NEW_SKU_MAX_CALENDAR_DAYS,
        new_sku_phi=TEXTBOOK_NEW_SKU_PHI,
        holt_initialization="SIX_WEEK_REGRESSION",
        croston_initialization="FIRST_INTERVAL_FIRST_DEMAND",
        layer2_seasonality_mode="SCALE_MEAN_AND_SIGMA_BY_FLR",
    )


def textbook_z_value(
    *,
    inventory_policy: str,
    sales_grade: str,
    z_matrix: Mapping[tuple[str, str], float] | None = None,
) -> float:
    """Return an explicitly selected policy/grade Z value.

    The matrix is intentionally separate from demand-pattern classification:
    ``CORE``/``GENERAL`` is a sales grade, while SES/HOLT/Croston is selected
    from the sales pattern.  An entity-specific matrix must be passed by the
    policy boundary; omitting it retains the documented textbook matrix.
    """

    key = (inventory_policy, sales_grade)
    try:
        matrix = TEXTBOOK_Z_MATRIX if z_matrix is None else z_matrix
        return _nonnegative("z_value", matrix[key])
    except KeyError as exc:
        raise V3CalculationError(
            "inventory_policy and sales_grade must select an approved Z-matrix entry"
        ) from exc


@dataclass(frozen=True, slots=True)
class SeasonalProfile:
    """Approved/candidate month factors for one explicit entity/class scope."""

    version: str
    entity_code: str
    function_class_1_code: str
    function_class_2_code: str
    factors_by_month: Mapping[int, float]

    def __post_init__(self) -> None:
        for name, value in (
            ("version", self.version),
            ("entity_code", self.entity_code),
            ("function_class_1_code", self.function_class_1_code),
            ("function_class_2_code", self.function_class_2_code),
        ):
            if not isinstance(value, str) or not value.strip():
                raise V3CalculationError(f"{name} is required")
        keys = set(self.factors_by_month)
        if keys != set(range(1, 13)):
            raise V3CalculationError("factors_by_month must contain each calendar month 1 through 12")
        for month, factor in self.factors_by_month.items():
            _positive(f"factors_by_month[{month}]", factor)

    def factor_for(self, value: date) -> float:
        return _positive(f"factor[{value.month}]", self.factors_by_month[value.month])


def calculate_candidate_monthly_factors(
    completed_month_totals: Mapping[date, float],
) -> dict[int, float]:
    """Calculate a rolling 24-month, recent-year-weighted seasonal profile.

    The caller must provide exactly 24 consecutive completed calendar months,
    keyed by the first day of each month.  The earlier 12 months carry weight
    1 and the latest 12 months carry weight 2, regardless of their absolute
    calendar years.  Missing collection is therefore not indistinguishable
    from a real zero-sale month in this pure layer.
    """

    if len(completed_month_totals) != 24:
        raise V3CalculationError("completed_month_totals must contain exactly 24 completed months")
    ordered = sorted(completed_month_totals)
    if any(key.day != 1 for key in ordered):
        raise V3CalculationError("completed_month_totals keys must be calendar-month start dates")
    for previous, current in zip(ordered, ordered[1:]):
        if _next_month(previous) != current:
            raise V3CalculationError("completed_month_totals must be consecutive without a missing month")
    totals = {key: _nonnegative(f"completed_month_totals[{key.isoformat()}]", value) for key, value in completed_month_totals.items()}
    weights = {
        key: (
            SEASONAL_OLDER_12_MONTH_WEIGHT
            if index < 12
            else SEASONAL_RECENT_12_MONTH_WEIGHT
        )
        for index, key in enumerate(ordered)
    }
    total_weight = sum(weights.values())
    overall_monthly_mean = sum(totals[key] * weights[key] for key in ordered) / total_weight
    if overall_monthly_mean == 0:
        raise V3PolicyRequiredError("cannot calculate a seasonal profile from 24 all-zero months")
    return {
        month: (
            sum(totals[key] * weights[key] for key in ordered if key.month == month)
            / sum(weights[key] for key in ordered if key.month == month)
        )
        / overall_monthly_mean
        for month in range(1, 13)
    }


def apply_textbook_seasonal_shrinkage(
    combination_factors: Mapping[int, float],
    parent_factors: Mapping[int, float],
    *,
    sku_count: int,
    seasonality_confirmed: bool,
) -> dict[int, float]:
    """Apply the textbook's explicit low-sample shrinkage rule.

    ``w = n / (n + 30)`` and
    ``final = w * combination + (1 - w) * parent``.

    A caller must explicitly distinguish a statistically unconfirmed group
    (which the textbook assigns 1.0) from a missing or failed profile.  Missing
    months and invalid counts therefore still fail instead of becoming 1.0.
    The exact source population used to produce ``sku_count`` belongs to the
    upstream data contract and is not inferred here.
    """

    if isinstance(sku_count, bool) or not isinstance(sku_count, int) or sku_count < 0:
        raise V3CalculationError("sku_count must be a non-negative integer")
    if not isinstance(seasonality_confirmed, bool):
        raise V3CalculationError("seasonality_confirmed must be a boolean")
    expected_months = set(range(1, 13))
    if set(combination_factors) != expected_months:
        raise V3CalculationError("combination_factors must contain each calendar month 1 through 12")
    if set(parent_factors) != expected_months:
        raise V3CalculationError("parent_factors must contain each calendar month 1 through 12")
    combination = {
        month: _nonnegative(f"combination_factors[{month}]", combination_factors[month])
        for month in range(1, 13)
    }
    parent = {
        month: _nonnegative(f"parent_factors[{month}]", parent_factors[month])
        for month in range(1, 13)
    }
    if not seasonality_confirmed:
        return {month: 1.0 for month in range(1, 13)}
    weight = sku_count / (sku_count + TEXTBOOK_SEASONAL_SHRINKAGE_CONSTANT)
    return {
        month: weight * combination[month] + (1 - weight) * parent[month]
        for month in range(1, 13)
    }


def _calendar_datetime(value: date | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.combine(value, time.min)


def weighted_month_factor(
    profile: SeasonalProfile,
    start: date | datetime,
    end: date | datetime,
) -> float:
    """Return the calendar-duration-weighted factor for ``[start, end)``.

    The V3 forecast grain is one week, while actual lead times may contain a
    fraction of a day.  A fractional final day remains in the month where it
    occurs; it is never rounded to a different calendar boundary.
    """

    start_at = _calendar_datetime(start)
    end_at = _calendar_datetime(end)
    if end_at <= start_at:
        raise V3CalculationError("seasonal factor range must have a positive duration")
    total_weighted_factor = 0.0
    cursor = start_at
    while cursor < end_at:
        next_month = _next_month(cursor.date())
        month_end = datetime.combine(next_month, time.min)
        segment_end = min(month_end, end_at)
        duration_days = (segment_end - cursor).total_seconds() / timedelta(days=1).total_seconds()
        total_weighted_factor += duration_days * profile.factor_for(cursor.date())
        cursor = segment_end
    total_days = (end_at - start_at).total_seconds() / timedelta(days=1).total_seconds()
    return total_weighted_factor / total_days


def deseasonalized_completed_4week_sales(
    daily_sales: Mapping[date, float],
    *,
    profile: SeasonalProfile,
    last_completed_sunday: date,
) -> tuple[float, ...]:
    """Build 13 completed Monday-Sunday weeks from daily demand.

    Sales are divided by their own calendar month's factor *before* summing the
    7-day period, so a week crossing a month boundary does not use a
    representative-month shortcut.

    The historical function name is retained for compatibility with existing
    callers; its calculation grain is weekly.
    """

    if last_completed_sunday.weekday() != 6:
        raise V3CalculationError("last_completed_sunday must be a Sunday")
    normalized_daily_sales = {
        key: _nonnegative(f"daily_sales[{key.isoformat()}]", value)
        for key, value in daily_sales.items()
    }
    oldest_start = last_completed_sunday - timedelta(days=(REQUIRED_COMPLETED_PERIODS * PERIOD_DAYS) - 1)
    latest_end = last_completed_sunday
    if any(key > latest_end for key in normalized_daily_sales):
        raise V3CalculationError("daily_sales contains a date after the completed observation window")
    periods: list[float] = []
    for period_index in range(REQUIRED_COMPLETED_PERIODS):
        start = oldest_start + timedelta(days=period_index * PERIOD_DAYS)
        adjusted_total = 0.0
        for offset in range(PERIOD_DAYS):
            current = start + timedelta(days=offset)
            adjusted_total += normalized_daily_sales.get(current, 0.0) / profile.factor_for(current)
        periods.append(adjusted_total)
    return tuple(periods)


def completed_4week_sales(
    daily_sales: Mapping[date, float],
    *,
    last_completed_sunday: date,
) -> tuple[float, ...]:
    """Build the original 13 completed weekly totals for traceability.

    This uses the same half-open observation window as the deseasonalised
    series but performs no seasonal adjustment.  Keeping both series lets the
    API and screen prove that seasonality was removed before classification.

    The historical function name is retained for compatibility with existing
    callers; its calculation grain is weekly.
    """

    if last_completed_sunday.weekday() != 6:
        raise V3CalculationError("last_completed_sunday must be a Sunday")
    normalized_daily_sales = {
        key: _nonnegative(f"daily_sales[{key.isoformat()}]", value)
        for key, value in daily_sales.items()
    }
    oldest_start = last_completed_sunday - timedelta(
        days=(REQUIRED_COMPLETED_PERIODS * PERIOD_DAYS) - 1
    )
    if any(key > last_completed_sunday for key in normalized_daily_sales):
        raise V3CalculationError(
            "daily_sales contains a date after the completed observation window"
        )
    return tuple(
        sum(
            normalized_daily_sales.get(
                oldest_start + timedelta(days=(period_index * PERIOD_DAYS) + offset),
                0.0,
            )
            for offset in range(PERIOD_DAYS)
        )
        for period_index in range(REQUIRED_COMPLETED_PERIODS)
    )


@dataclass(frozen=True, slots=True)
class V3Classification:
    pattern: str
    engine: str
    adi: float
    cv2: float
    trend_signal: float | None
    high_cv2: bool


def classify_v3_demand(
    adjusted_period_sales: Sequence[float],
    *,
    parameters: V3CandidateParameters,
) -> V3Classification:
    """Classify 13 adjusted weekly sales values in the guide's stated order."""

    values = _validated_sales(adjusted_period_sales, name="adjusted_period_sales")
    positive_count = sum(value > 0 for value in values)
    if positive_count == 0:
        raise V3PolicyRequiredError("all-zero sales require an approved V3 new/no-sales policy")
    adi = len(values) / positive_count
    mean = fmean(values)
    # The textbook's Cream A fixture reports CV²=0.0160, which is the
    # population variance across all 13 observed periods.  The sample formula
    # would yield 0.0174 and can change classifications near the 0.49 boundary.
    sigma = pstdev(values) if len(values) > 1 else 0.0
    cv2 = (sigma / mean) ** 2 if mean > 0 else math.inf
    high_cv2 = cv2 > parameters.cv2_threshold
    # Approved 2026-09-08: a SKU whose first observed sale week starts after
    # the beginning of the 13-completed-week window has fewer than 13 weeks of
    # in-window history.  The 91-day web source cannot prove a lifetime first
    # sale, so this judgement intentionally uses in-window evidence only.  Such
    # short-history SKUs skip the SES/HOLT/Croston gates and use the simple
    # moving average of the weeks since their first in-window sale week.  ADI
    # and CV² stay full-window audit values and are not used as a gate here.
    first_positive_index = next(index for index, value in enumerate(values) if value > 0)
    if first_positive_index > 0:
        return V3Classification(
            pattern=PATTERN_SHORT_HISTORY,
            engine=ENGINE_MOVING_AVERAGE,
            adi=adi,
            cv2=cv2,
            trend_signal=None,
            high_cv2=high_cv2,
        )
    # Approved 2026-09-02 (확정 로직표 B): the intermittent gate is conjunctive
    # and inclusive.  A SKU is Croston + SBA only when ``ADI >= 1.32`` AND
    # ``CV² >= 0.49`` both hold; if either fails the row is not intermittent and
    # continues to the trend test.  ``high_cv2`` stays a strict ``>`` audit flag
    # for the still-unresolved sigma reinforcement and is intentionally separate
    # from this classification gate.
    if adi >= parameters.adi_threshold and cv2 >= parameters.cv2_threshold:
        return V3Classification(
            pattern=PATTERN_INTERMITTENT,
            engine=ENGINE_CROSTON_SBA,
            adi=adi,
            cv2=cv2,
            trend_signal=None,
            high_cv2=high_cv2,
        )

    # Compare periods 1-6 with periods 8-13 and exclude the middle (7th)
    # period exactly as specified in the textbook.
    previous_six = sum(values[:6])
    recent_six = sum(values[-6:])
    if previous_six == 0:
        raise V3PolicyRequiredError("trend signal is undefined because the preceding six periods sum to zero")
    trend_signal = (recent_six - previous_six) / previous_six
    if trend_signal > parameters.trend_threshold:
        pattern, engine = PATTERN_TREND_UP, ENGINE_HOLT_DAMPED
    elif trend_signal < -parameters.trend_threshold:
        pattern, engine = PATTERN_TREND_DOWN, ENGINE_HOLT_DAMPED
    else:
        pattern, engine = PATTERN_STABLE, ENGINE_SES
    return V3Classification(
        pattern=pattern,
        engine=engine,
        adi=adi,
        cv2=cv2,
        trend_signal=trend_signal,
        high_cv2=high_cv2,
    )


@dataclass(frozen=True, slots=True)
class V3Forecast:
    engine: str
    damping_phi: float | None
    demand_per_period: float
    sigma_per_period: float
    variance_per_period: float
    next_period_forecast: float
    second_period_forecast: float | None
    rmse: float | None
    level: float | None
    trend: float | None
    croston_interval: float | None
    croston_size: float | None
    croston_forecast_cap_per_period: float | None
    croston_forecast_was_capped: bool


@dataclass(frozen=True, slots=True)
class V3NewSkuStatus:
    """Calendar-day lifecycle status retained as non-calculating audit data."""

    first_sale_date: date
    analysis_date: date
    elapsed_calendar_days: int
    is_new_sku: bool


def calculate_v3_new_sku_status(
    *,
    first_sale_date: date,
    analysis_date: date,
    parameters: V3CandidateParameters,
) -> V3NewSkuStatus:
    """Classify a SKU from its first paid sale through the sales cutoff.

    V3 uses calendar days, including weekends and holidays.  The date span is
    a date subtraction rather than a count of sales rows or weekly buckets;
    exactly 168 elapsed days remains a new SKU.
    """

    if first_sale_date > analysis_date:
        raise V3CalculationError("first_sale_date cannot be after the analysis sales cutoff")
    elapsed_calendar_days = (analysis_date - first_sale_date).days
    return V3NewSkuStatus(
        first_sale_date=first_sale_date,
        analysis_date=analysis_date,
        elapsed_calendar_days=elapsed_calendar_days,
        is_new_sku=elapsed_calendar_days <= parameters.new_sku_max_calendar_days,
    )


def _rmse(errors: Sequence[float]) -> float:
    if not errors:
        raise V3CalculationError("at least one forecast error is required for RMSE")
    return math.sqrt(fmean(error * error for error in errors))


def calculate_ses_forecast(
    adjusted_period_sales: Sequence[float],
    *,
    alpha: float,
) -> V3Forecast:
    values = _validated_sales(adjusted_period_sales, name="adjusted_period_sales")
    alpha_value = _positive("alpha", alpha)
    if alpha_value > 1:
        raise V3CalculationError("alpha must be at most one")
    level = values[0]
    errors: list[float] = []
    for observed in values[1:]:
        prediction = level
        errors.append(observed - prediction)
        level = level + alpha_value * (observed - level)
    rmse = _rmse(errors)
    return V3Forecast(
        engine=ENGINE_SES,
        damping_phi=None,
        demand_per_period=level,
        sigma_per_period=rmse,
        variance_per_period=rmse**2,
        next_period_forecast=level,
        second_period_forecast=level,
        rmse=rmse,
        level=level,
        trend=None,
        croston_interval=None,
        croston_size=None,
        croston_forecast_cap_per_period=None,
        croston_forecast_was_capped=False,
    )


def calculate_holt_damped_forecast(
    adjusted_period_sales: Sequence[float],
    *,
    alpha: float,
    beta: float,
    phi: float,
    initialization: str,
) -> V3Forecast:
    values = _validated_sales(adjusted_period_sales, name="adjusted_period_sales")
    if initialization != "SIX_WEEK_REGRESSION":
        raise V3PolicyRequiredError("HOLT initialization policy is required")
    alpha_value = _positive("alpha", alpha)
    beta_value = _positive("beta", beta)
    phi_value = _positive("phi", phi)
    if any(value > 1 for value in (alpha_value, beta_value, phi_value)):
        raise V3CalculationError("alpha, beta and phi must each be at most one")
    # Approved 2026-09-08 (초기추세오류 오답노트): the two-point difference
    # ``b0 = week2 - week1`` enters the recursion unsmoothed, so one launch
    # spike poisons the whole horizon.  b0 is now the least-squares slope of
    # the first six weeks (the same window the trend gate already uses) and
    # l0 is that regression line evaluated at week 6: with t = 1..6 the
    # integer-weight form is ``(-5*Y1 - 3*Y2 - Y3 + Y4 + 3*Y5 + 5*Y6) / 35``
    # and ``l0 = mean(Y1..Y6) + b0 * 2.5``.  The recursion then consumes the
    # remaining weeks 7..13 so no observation is double-counted.
    trend = (
        -5.0 * values[0]
        - 3.0 * values[1]
        - values[2]
        + values[3]
        + 3.0 * values[4]
        + 5.0 * values[5]
    ) / 35.0
    level = fmean(values[:6]) + trend * 2.5
    errors: list[float] = []
    for observed in values[6:]:
        prediction = level + phi_value * trend
        errors.append(observed - prediction)
        previous_level = level
        level = prediction + alpha_value * (observed - prediction)
        trend = beta_value * (level - previous_level) + (1 - beta_value) * phi_value * trend
    rmse = _rmse(errors)
    next_period = level + trend * phi_value
    second_period = level + trend * (phi_value + phi_value**2)
    return V3Forecast(
        engine=ENGINE_HOLT_DAMPED,
        damping_phi=phi_value,
        demand_per_period=next_period,
        sigma_per_period=rmse,
        variance_per_period=rmse**2,
        next_period_forecast=next_period,
        second_period_forecast=second_period,
        rmse=rmse,
        level=level,
        trend=trend,
        croston_interval=None,
        croston_size=None,
        croston_forecast_cap_per_period=None,
        croston_forecast_was_capped=False,
    )


def calculate_croston_sba_forecast(
    adjusted_period_sales: Sequence[float],
    *,
    alpha: float,
    initialization: str,
) -> V3Forecast:
    values = _validated_sales(adjusted_period_sales, name="adjusted_period_sales")
    if initialization != "FIRST_INTERVAL_FIRST_DEMAND":
        raise V3PolicyRequiredError("Croston initialization policy is required")
    alpha_value = _positive("alpha", alpha)
    if alpha_value > 1:
        raise V3CalculationError("alpha must be at most one")
    nonzero = [(index, value) for index, value in enumerate(values) if value > 0]
    if len(nonzero) < 2:
        raise V3PolicyRequiredError("Croston requires at least two non-zero sales periods")
    intervals = [current[0] - previous[0] for previous, current in zip(nonzero, nonzero[1:])]
    interval = float(intervals[0])
    size = nonzero[0][1]
    for observed_interval, (_, observed_size) in zip(intervals, nonzero[1:]):
        interval = interval + alpha_value * (observed_interval - interval)
        size = size + alpha_value * (observed_size - size)
    if interval <= 0:
        raise V3CalculationError("Croston interval must be greater than zero")
    size_sigma = stdev(value for _, value in nonzero)
    demand = (size / interval) * (1 - alpha_value / 2)
    variance = (size_sigma**2 / interval) + (size**2 * (1 / interval) * (1 - 1 / interval))
    return V3Forecast(
        engine=ENGINE_CROSTON_SBA,
        damping_phi=None,
        demand_per_period=demand,
        sigma_per_period=math.sqrt(variance),
        variance_per_period=variance,
        next_period_forecast=demand,
        second_period_forecast=demand,
        rmse=None,
        level=None,
        trend=None,
        croston_interval=interval,
        croston_size=size,
        croston_forecast_cap_per_period=None,
        croston_forecast_was_capped=False,
    )


def calculate_moving_average_forecast(
    adjusted_period_sales: Sequence[float],
) -> V3Forecast:
    """Simple moving average for short-history SKUs (approved 2026-09-08).

    Uses every completed week from the first in-window sale week through the
    latest completed week, including intermediate zero-sales weeks.  ``d_bar``
    is the plain mean and sigma is the sample standard deviation (STDEV.S) of
    those same weeks.  Hand check: first sale in week 9 with adjusted sales
    ``10, 20, 30, 20, 20`` gives ``d_bar = 100 / 5 = 20`` and
    ``sigma = STDEV.S(...) ~= 7.07``.
    """

    values = _validated_sales(adjusted_period_sales, name="adjusted_period_sales")
    first_positive_index = next(
        (index for index, value in enumerate(values) if value > 0), None
    )
    if first_positive_index is None:
        raise V3PolicyRequiredError("all-zero sales require an approved V3 new/no-sales policy")
    if first_positive_index == 0:
        raise V3CalculationError(
            "moving average applies only to short-history SKUs whose first sale week starts after the window"
        )
    observed = values[first_positive_index:]
    if len(observed) < 2:
        raise V3PolicyRequiredError(
            "moving average sigma (STDEV.S) requires at least two completed weeks since the first in-window sale"
        )
    demand = fmean(observed)
    sigma = stdev(observed)
    return V3Forecast(
        engine=ENGINE_MOVING_AVERAGE,
        damping_phi=None,
        demand_per_period=demand,
        sigma_per_period=sigma,
        variance_per_period=sigma**2,
        next_period_forecast=demand,
        second_period_forecast=demand,
        rmse=None,
        level=None,
        trend=None,
        croston_interval=None,
        croston_size=None,
        croston_forecast_cap_per_period=None,
        croston_forecast_was_capped=False,
    )


def forecast_v3_demand(
    adjusted_period_sales: Sequence[float],
    *,
    classification: V3Classification,
    parameters: V3CandidateParameters,
    holt_phi: float | None = None,
) -> V3Forecast:
    if classification.engine == ENGINE_SES:
        return calculate_ses_forecast(adjusted_period_sales, alpha=parameters.alpha)
    if classification.engine == ENGINE_HOLT_DAMPED:
        return calculate_holt_damped_forecast(
            adjusted_period_sales,
            alpha=parameters.alpha,
            beta=parameters.beta,
            phi=parameters.phi if holt_phi is None else holt_phi,
            initialization=parameters.holt_initialization,
        )
    if classification.engine == ENGINE_CROSTON_SBA:
        return calculate_croston_sba_forecast(
            adjusted_period_sales,
            alpha=parameters.alpha,
            initialization=parameters.croston_initialization,
        )
    if classification.engine == ENGINE_MOVING_AVERAGE:
        return calculate_moving_average_forecast(adjusted_period_sales)
    raise V3CalculationError(f"unsupported V3 engine: {classification.engine}")


@dataclass(frozen=True, slots=True)
class V3ReplenishmentInput:
    """Explicit policy and inventory inputs for one SKU backtest snapshot.

    Demand is measured per completed calendar week. Lead/review fields remain in
    calendar days so seasonal factors can be weighted by actual dates.
    """

    order_date: date
    lead_time_days: float
    review_days: float
    sigma_lead_time_periods: float
    safety_stock_floor_periods: float
    safety_stock_cap_periods: float
    z_value: float
    on_hand_qty: float
    upstream_available_qty: float
    in_transit_qty: float
    unreceived_qty: float
    holding_qty: float

    def __post_init__(self) -> None:
        _positive("lead_time_days", self.lead_time_days)
        _positive("review_days", self.review_days)
        _nonnegative("sigma_lead_time_periods", self.sigma_lead_time_periods)
        _nonnegative("safety_stock_floor_periods", self.safety_stock_floor_periods)
        _positive("safety_stock_cap_periods", self.safety_stock_cap_periods)
        if self.safety_stock_cap_periods < self.safety_stock_floor_periods:
            raise V3CalculationError("safety_stock_cap_periods must be at least safety_stock_floor_periods")
        _nonnegative("z_value", self.z_value)
        for name in (
            "on_hand_qty",
            "upstream_available_qty",
            "in_transit_qty",
            "unreceived_qty",
            "holding_qty",
        ):
            _nonnegative(name, getattr(self, name))

    @property
    def lead_time_periods(self) -> float:
        return float(self.lead_time_days) / PERIOD_DAYS

    @property
    def review_periods(self) -> float:
        return float(self.review_days) / PERIOD_DAYS

    @property
    def inventory_position(self) -> float:
        return (
            float(self.on_hand_qty)
            + float(self.upstream_available_qty)
            + float(self.in_transit_qty)
            + float(self.unreceived_qty)
            - float(self.holding_qty)
        )


@dataclass(frozen=True, slots=True)
class V3ReplenishmentPolicy:
    """One scenario's measured lead-time and safety-stock policy in V3 units."""

    lead_time_days: float
    review_days: float
    sigma_lead_time_periods: float
    safety_stock_floor_periods: float
    safety_stock_cap_periods: float

    def __post_init__(self) -> None:
        _positive("lead_time_days", self.lead_time_days)
        _positive("review_days", self.review_days)
        _nonnegative("sigma_lead_time_periods", self.sigma_lead_time_periods)
        _nonnegative("safety_stock_floor_periods", self.safety_stock_floor_periods)
        _positive("safety_stock_cap_periods", self.safety_stock_cap_periods)
        if self.safety_stock_cap_periods < self.safety_stock_floor_periods:
            raise V3CalculationError("safety_stock_cap_periods must be at least safety_stock_floor_periods")


@dataclass(frozen=True, slots=True)
class V3ReplenishmentBaseInput:
    """Shared inventory plus both scenario-specific V3 replenishment policies."""

    order_date: date
    cash_policy: V3ReplenishmentPolicy
    shortage_policy: V3ReplenishmentPolicy
    on_hand_qty: float
    upstream_available_qty: float
    in_transit_qty: float
    unreceived_qty: float
    holding_qty: float

    def __post_init__(self) -> None:
        for name in (
            "on_hand_qty",
            "upstream_available_qty",
            "in_transit_qty",
            "unreceived_qty",
            "holding_qty",
        ):
            _nonnegative(name, getattr(self, name))

    def for_policy(self, inventory_policy: str, z_value: float) -> V3ReplenishmentInput:
        if inventory_policy == INVENTORY_POLICY_CASH:
            policy = self.cash_policy
        elif inventory_policy == INVENTORY_POLICY_SHORTAGE:
            policy = self.shortage_policy
        else:
            raise V3CalculationError(f"unsupported inventory policy: {inventory_policy}")
        return V3ReplenishmentInput(
            order_date=self.order_date,
            lead_time_days=policy.lead_time_days,
            review_days=policy.review_days,
            sigma_lead_time_periods=policy.sigma_lead_time_periods,
            safety_stock_floor_periods=policy.safety_stock_floor_periods,
            safety_stock_cap_periods=policy.safety_stock_cap_periods,
            z_value=z_value,
            on_hand_qty=self.on_hand_qty,
            upstream_available_qty=self.upstream_available_qty,
            in_transit_qty=self.in_transit_qty,
            unreceived_qty=self.unreceived_qty,
            holding_qty=self.holding_qty,
        )


@dataclass(frozen=True, slots=True)
class V3FutureSeasonality:
    f1: float
    f2: float
    f_lr: float

    def __post_init__(self) -> None:
        _positive("f1", self.f1)
        _positive("f2", self.f2)
        _positive("f_lr", self.f_lr)


def calculate_future_seasonality(
    profile: SeasonalProfile,
    *,
    order_date: date,
    lead_time_days: float,
    review_days: float,
) -> V3FutureSeasonality:
    """Calculate the SF-002 candidate factors from actual calendar dates."""

    lead_days = _positive("lead_time_days", lead_time_days)
    review_days_value = _positive("review_days", review_days)
    order_at = datetime.combine(order_date, time.min)
    lead_end = order_at + timedelta(days=lead_days)
    review_end = lead_end + timedelta(days=review_days_value)
    return V3FutureSeasonality(
        f1=weighted_month_factor(profile, order_at, lead_end),
        f2=weighted_month_factor(profile, lead_end, review_end),
        f_lr=weighted_month_factor(profile, order_at, review_end),
    )


@dataclass(frozen=True, slots=True)
class V3RawOrderResult:
    classification: V3Classification
    new_sku_status: V3NewSkuStatus | None
    forecast: V3Forecast
    seasonal_factors: V3FutureSeasonality
    z_value: float
    inventory_position: float
    layer1: float
    layer2_raw: float
    layer2: float
    safety_stock_floor: float
    safety_stock_cap: float
    layer3: float
    reorder_point: float
    target_stock: float
    need_order: bool
    raw_order_quantity: float
    final_order_quantity: None
    order_constraint_status: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _holt_period_forecast(
    forecast: V3Forecast,
    *,
    phi: float,
    horizon: int,
) -> float:
    """Return the demand forecast for one future week at ``horizon``."""

    if horizon < 1 or forecast.level is None or forecast.trend is None:
        raise V3CalculationError("HOLT future-period forecast requires level, trend and a positive horizon")
    phi_value = _positive("phi", phi)
    if math.isclose(phi_value, 1.0):
        damped_sum = float(horizon)
    else:
        damped_sum = phi_value * (1 - phi_value**horizon) / (1 - phi_value)
    return forecast.level + forecast.trend * damped_sum


def _holt_interval_demand(
    forecast: V3Forecast,
    *,
    phi: float,
    start_period: float,
    end_period: float,
) -> float:
    """Integrate weekly HOLT forecasts over an exact fractional-week range."""

    start = _nonnegative("start_period", start_period)
    end = _positive("end_period", end_period)
    if end <= start:
        raise V3CalculationError("HOLT interval must have a positive duration")
    total = 0.0
    cursor = start
    while cursor < end:
        period_index = math.floor(cursor)
        segment_end = min(end, period_index + 1.0)
        total += _holt_period_forecast(
            forecast,
            phi=phi,
            horizon=period_index + 1,
        ) * (segment_end - cursor)
        cursor = segment_end
    return total


def _pack_quantity(value: object) -> float | None:
    """Accept only a finite pack size greater than zero; anything else is unset."""

    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0.0:
        return None
    return parsed


@dataclass(frozen=True, slots=True)
class V3OrderUnitRounding:
    """One SKU's approved order-unit ceiling applied to a raw quantity."""

    final_order_quantity: float
    order_unit_quantity: float
    order_unit_source: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def round_v3_order_quantity(
    raw_order_quantity: float,
    *,
    outbox_quantity: object = None,
    inbox_quantity: object = None,
) -> V3OrderUnitRounding:
    """Ceil a positive raw quantity to the approved order unit ladder.

    The ladder is outbox pack, then inbox pack, then a fixed 10-unit
    fallback. A raw quantity of zero stays zero: pack rounding must not
    create an order for a SKU that needs none.
    """

    raw = _nonnegative("raw_order_quantity", raw_order_quantity)
    outbox = _pack_quantity(outbox_quantity)
    inbox = _pack_quantity(inbox_quantity)
    if outbox is not None:
        unit, source = outbox, ORDER_UNIT_SOURCE_OUTBOX
    elif inbox is not None:
        unit, source = inbox, ORDER_UNIT_SOURCE_INBOX
    else:
        unit, source = ORDER_UNIT_FALLBACK_QUANTITY, ORDER_UNIT_SOURCE_FALLBACK_10
    final = 0.0 if raw == 0.0 else math.ceil(raw / unit) * unit
    return V3OrderUnitRounding(
        final_order_quantity=float(final),
        order_unit_quantity=float(unit),
        order_unit_source=source,
    )


def calculate_v3_raw_order(
    adjusted_period_sales: Sequence[float],
    *,
    parameters: V3CandidateParameters,
    replenishment: V3ReplenishmentInput,
    seasonal_factors: V3FutureSeasonality,
    first_sale_date: date | None = None,
    analysis_date: date | None = None,
) -> V3RawOrderResult:
    """Calculate V3 through raw quantity, deliberately excluding order constraints."""

    values = _validated_sales(adjusted_period_sales, name="adjusted_period_sales")
    classification = classify_v3_demand(values, parameters=parameters)
    new_sku_status = (
        calculate_v3_new_sku_status(
            first_sale_date=first_sale_date,
            analysis_date=analysis_date or replenishment.order_date,
            parameters=parameters,
        )
        if first_sale_date is not None
        else None
    )
    forecast = forecast_v3_demand(
        values,
        classification=classification,
        parameters=parameters,
        holt_phi=parameters.phi if classification.engine == ENGINE_HOLT_DAMPED else None,
    )
    lead_periods = replenishment.lead_time_periods
    review_periods = replenishment.review_periods
    if forecast.engine == ENGINE_HOLT_DAMPED:
        if forecast.damping_phi is None:
            raise V3CalculationError("HOLT forecast must retain its applied damping phi")
        layer1 = _holt_interval_demand(
            forecast,
            phi=forecast.damping_phi,
            start_period=0.0,
            end_period=lead_periods,
        ) * seasonal_factors.f1
        layer3 = _holt_interval_demand(
            forecast,
            phi=forecast.damping_phi,
            start_period=lead_periods,
            end_period=lead_periods + review_periods,
        ) * seasonal_factors.f2
        layer2_demand = (
            _holt_interval_demand(
                forecast,
                phi=forecast.damping_phi,
                start_period=0.0,
                end_period=lead_periods + review_periods,
            )
            / (lead_periods + review_periods)
        ) * seasonal_factors.f_lr
    else:
        layer1 = forecast.demand_per_period * lead_periods * seasonal_factors.f1
        layer3 = forecast.demand_per_period * review_periods * seasonal_factors.f2
        layer2_demand = forecast.demand_per_period * seasonal_factors.f_lr

    layer2_sigma = forecast.sigma_per_period * seasonal_factors.f_lr
    layer2_raw = replenishment.z_value * math.sqrt(
        (lead_periods + review_periods) * (layer2_sigma**2)
        + (layer2_demand**2) * (replenishment.sigma_lead_time_periods**2)
    )
    safety_stock_floor = layer2_demand * replenishment.safety_stock_floor_periods
    safety_stock_cap = layer2_demand * replenishment.safety_stock_cap_periods
    layer2 = min(max(layer2_raw, safety_stock_floor), safety_stock_cap)
    # Pure periodic-review (R,S): every analysis compares inventory position
    # directly with the target stock.  ROP remains in the result only as an
    # inspectable Layer 1 + Layer 2 reference; it is not an order gate.
    reorder_point = layer1 + layer2
    target_stock = reorder_point + layer3
    ip = replenishment.inventory_position
    raw_order_quantity = max(0.0, target_stock - ip)
    need_order = raw_order_quantity > 0.0
    return V3RawOrderResult(
        classification=classification,
        new_sku_status=new_sku_status,
        forecast=forecast,
        seasonal_factors=seasonal_factors,
        z_value=replenishment.z_value,
        inventory_position=ip,
        layer1=layer1,
        layer2_raw=layer2_raw,
        layer2=layer2,
        safety_stock_floor=safety_stock_floor,
        safety_stock_cap=safety_stock_cap,
        layer3=layer3,
        reorder_point=reorder_point,
        target_stock=target_stock,
        need_order=need_order,
        raw_order_quantity=raw_order_quantity,
        final_order_quantity=None,
        order_constraint_status=CONSTRAINT_STATUS_PENDING,
    )


@dataclass(frozen=True, slots=True)
class V3TextbookScenarioResult:
    """One SKU calculated once from one snapshot under both Z scenarios."""

    original_period_sales: tuple[float, ...]
    adjusted_period_sales: tuple[float, ...]
    shortage: V3RawOrderResult
    cash: V3RawOrderResult


def calculate_v3_textbook_scenarios(
    daily_sales: Mapping[date, float],
    *,
    first_sale_date: date | None = None,
    profile: SeasonalProfile,
    last_completed_sunday: date,
    parameters: V3CandidateParameters,
    replenishment: V3ReplenishmentBaseInput,
    sales_grade: str,
    z_matrix: Mapping[tuple[str, str], float] | None = None,
) -> V3TextbookScenarioResult:
    """Run the approved textbook flow once and return both policy scenarios.

    Both scenarios share the exact same daily-sales window, seasonal profile,
    demand classification, forecast and inventory snapshot. Every engine uses
    the Z entry selected by its scenario and sales grade.
    """

    original_period_sales = completed_4week_sales(
        daily_sales,
        last_completed_sunday=last_completed_sunday,
    )
    adjusted_period_sales = deseasonalized_completed_4week_sales(
        daily_sales,
        profile=profile,
        last_completed_sunday=last_completed_sunday,
    )
    classification = classify_v3_demand(adjusted_period_sales, parameters=parameters)
    shortage_replenishment = replenishment.for_policy(
        INVENTORY_POLICY_SHORTAGE,
        textbook_z_value(
            inventory_policy=INVENTORY_POLICY_SHORTAGE,
            sales_grade=sales_grade,
            z_matrix=z_matrix,
        ),
    )
    shortage_factors = calculate_future_seasonality(
        profile,
        order_date=shortage_replenishment.order_date,
        lead_time_days=shortage_replenishment.lead_time_days,
        review_days=shortage_replenishment.review_days,
    )
    shortage = calculate_v3_raw_order(
        adjusted_period_sales,
        parameters=parameters,
        replenishment=shortage_replenishment,
        seasonal_factors=shortage_factors,
        first_sale_date=first_sale_date,
        analysis_date=last_completed_sunday,
    )
    cash_replenishment = replenishment.for_policy(
        INVENTORY_POLICY_CASH,
        textbook_z_value(
            inventory_policy=INVENTORY_POLICY_CASH,
            sales_grade=sales_grade,
            z_matrix=z_matrix,
        ),
    )
    cash_factors = calculate_future_seasonality(
        profile,
        order_date=cash_replenishment.order_date,
        lead_time_days=cash_replenishment.lead_time_days,
        review_days=cash_replenishment.review_days,
    )
    cash = calculate_v3_raw_order(
        adjusted_period_sales,
        parameters=parameters,
        replenishment=cash_replenishment,
        seasonal_factors=cash_factors,
        first_sale_date=first_sale_date,
        analysis_date=last_completed_sunday,
    )
    return V3TextbookScenarioResult(
        original_period_sales=original_period_sales,
        adjusted_period_sales=adjusted_period_sales,
        shortage=shortage,
        cash=cash,
    )


@dataclass(frozen=True, slots=True)
class V3BacktestPoint:
    origin_index: int
    engine: str
    forecast: float
    actual: float
    signed_error: float
    absolute_error: float


@dataclass(frozen=True, slots=True)
class V3BacktestBlockedPoint:
    """One rolling origin that could not use an unapproved candidate policy."""

    origin_index: int
    reason: str


@dataclass(frozen=True, slots=True)
class V3BacktestResult:
    points: tuple[V3BacktestPoint, ...]
    blocked_points: tuple[V3BacktestBlockedPoint, ...]
    mean_signed_error: float | None
    mean_absolute_error: float | None


def run_v3_rolling_origin_backtest(
    adjusted_period_sales: Sequence[float],
    *,
    parameters: V3CandidateParameters,
) -> V3BacktestResult:
    """Evaluate one-period-ahead V3 candidate forecasts without V2 comparison.

    The caller supplies already deseasonalised completed weekly demand. Each
    origin uses the immediately preceding 13 periods and compares its next
    period forecast with the then-future actual period.  Inventory, pack and
    MOQ are intentionally outside this first forecast-only backtest.
    """

    values = tuple(_nonnegative(f"adjusted_period_sales[{index}]", value) for index, value in enumerate(adjusted_period_sales))
    if len(values) <= REQUIRED_COMPLETED_PERIODS:
        raise V3CalculationError(
            "rolling-origin backtest requires more than 13 adjusted weekly periods"
        )
    points: list[V3BacktestPoint] = []
    blocked_points: list[V3BacktestBlockedPoint] = []
    for origin_index in range(REQUIRED_COMPLETED_PERIODS, len(values)):
        history = values[origin_index - REQUIRED_COMPLETED_PERIODS:origin_index]
        try:
            classification = classify_v3_demand(history, parameters=parameters)
            forecast = forecast_v3_demand(history, classification=classification, parameters=parameters)
        except V3PolicyRequiredError as exc:
            blocked_points.append(V3BacktestBlockedPoint(origin_index=origin_index, reason=str(exc)))
            continue
        actual = values[origin_index]
        signed_error = forecast.next_period_forecast - actual
        points.append(
            V3BacktestPoint(
                origin_index=origin_index,
                engine=forecast.engine,
                forecast=forecast.next_period_forecast,
                actual=actual,
                signed_error=signed_error,
                absolute_error=abs(signed_error),
            )
        )
    return V3BacktestResult(
        points=tuple(points),
        blocked_points=tuple(blocked_points),
        mean_signed_error=fmean(point.signed_error for point in points) if points else None,
        mean_absolute_error=fmean(point.absolute_error for point in points) if points else None,
    )
