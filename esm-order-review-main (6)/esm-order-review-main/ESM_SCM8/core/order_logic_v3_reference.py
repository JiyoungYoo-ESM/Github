"""Descriptive sales metrics only; never inputs to the V3 order engine."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import fsum, isclose, isfinite, sqrt
from statistics import stdev
from typing import Mapping, Sequence


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) else None


def _round(value: float, digits: int) -> float:
    """Excel ROUND: halfway values go away from zero, not bankers' rounding."""
    # Excel numeric precision is 15 significant digits. Remove binary sqrt /
    # division noise (e.g. 1.0499999999999998) before rounding a halfway value.
    return float(Decimal(format(value, ".15g")).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def sales_reference_metrics(
    daily_sales: Mapping[date, float], *, completed_sales_cutoff: date,
) -> dict[str, object]:
    """91 completed days ending at V3's cutoff, monthly /3 and weekly /13.

    The source has already applied V3's paid-demand filters. Missing sale days
    in a successfully loaded source are zero sales, not missing API results.
    Invalid in-window values remain unavailable instead of being coerced to 0.
    No season adjustment or annual-period averaging. The template rounds the
    monthly /3 result BEFORE using it as the MOI denominator; keep raw /3 too.
    """
    start = completed_sales_cutoff - timedelta(days=90)
    values = [value for day, value in daily_sales.items() if start <= day <= completed_sales_cutoff]
    valid = all(_number(value) is not None and value >= 0 for value in values)
    total = fsum(values) if valid else None
    weeks = [fsum(daily_sales.get(start + timedelta(days=i * 7 + j), 0) for j in range(7)) for i in range(13)] if valid else None
    return {
        "reference_sales_start": start.isoformat(),
        "reference_sales_end": completed_sales_cutoff.isoformat(),
        "reference_sales_days": 91,
        "reference_sales_status": "AVAILABLE" if valid else "INVALID_SOURCE",
        "reference_sales_13w": total,
        "reference_monthly_sales_raw": total / 3 if total is not None else None,
        "reference_monthly_sales": _round(total / 3, 0) if total is not None else None,
        "reference_weekly_sales": total / 13 if total is not None else None,
        "reference_weekly_sales_history": weeks,
        "reference_weekly_sigma": stdev(weeks) if weeks is not None else None,
    }


def inventory_reference_metrics(row: Mapping[str, object], *, as_of: date) -> dict[str, object]:
    """Approved template AC:AI outputs, NOT inputs to V3 Q/ROP/SS.

    Units: actual demand EA/week, sigma STDEV.S of 13 weeks, IP/ROP EA.
    Dates retain unrounded fractional days, just as Excel's serial date does.
    """
    result: dict[str, object] = dict.fromkeys((
        "reference_moi", "reference_logistics_moi", "reference_depletion_weeks",
        "reference_order_slack_weeks", "reference_conservative_slack_weeks",
        "reference_early_warning_at", "reference_order_at",
    ))
    valid_sales = row.get("reference_sales_status") == "AVAILABLE"
    monthly = _number(row.get("reference_monthly_sales")) if valid_sales else None
    weekly = _number(row.get("reference_weekly_sales")) if valid_sales else None
    sigma = _number(row.get("reference_weekly_sigma")) if valid_sales else None
    local, transit = _number(row.get("on_hand_qty")), _number(row.get("in_transit_qty"))
    ip = _number(row.get("inventory_position")) if row.get("calculable") is True else None
    rop = _number(row.get("reorder_point")) if row.get("calculable") is True else None
    z = _number(row.get("z_value")) if row.get("calculable") is True else None
    if local is not None and transit is not None:
        if monthly is not None and monthly > 0:
            result["reference_logistics_moi"] = _round((local + transit) / monthly, 1)
            # The main sheet additionally guards against a blank IP.
            if ip is not None:
                result["reference_moi"] = result["reference_logistics_moi"]
        if weekly is not None and weekly > 0:
            result["reference_depletion_weeks"] = (local + transit) / weekly
    if weekly is None or weekly <= 0 or ip is None or rop is None:
        return result
    gap = max(0.0, ip - rop)
    mean_weeks = gap / weekly
    result["reference_order_slack_weeks"] = max(0.0, _round((ip - rop) / weekly, 1))
    def timestamp(weeks: float) -> str | None:
        try:
            return (datetime.combine(as_of, time()) + timedelta(days=weeks * 7)).isoformat()
        except (OverflowError, ValueError):
            return None  # Never manufacture a date outside the supported calendar.
    result["reference_order_at"] = timestamp(mean_weeks)
    if sigma is not None and sigma >= 0 and z is not None and z >= 0:
        # Algebraically identical to ((sqrt(a²+4*d*gap)-a)/(2*d))²,
        # rationalized to avoid cancellation when gap is small.
        a = z * sigma
        denominator = sqrt(a * a + 4 * weekly * gap) + a
        conservative = (2 * gap / denominator) ** 2 if denominator else 0.0
        result["reference_conservative_slack_weeks"] = max(0.0, _round(conservative, 1))
        result["reference_early_warning_at"] = timestamp(conservative)
    return result


def shipping_reference_metrics(
    details: Sequence[Mapping[str, object]] | None, *, as_of: date,
    source_status: str, in_transit_qty: float,
) -> dict[str, object]:
    """SUMIFS-equivalent buckets: overdue, 13 Monday weeks, >= Monday+91.

    Unknown ETA quantities are retained separately, never dated or discarded.
    The source adapter owns filtering; no new deduplication is introduced.
    """
    monday = as_of - timedelta(days=as_of.weekday())
    result: dict[str, object] = {
        "eta_reference_status": source_status, "eta_week_start": monday.isoformat(),
        "eta_bucket_quantities": None, "eta_missing_qty": None,
        "next_eta": None, "shipping_eta_details": list(details or []),
    }
    if source_status != "AVAILABLE" or details is None:
        return result
    quantities = [_number(item.get("qty")) for item in details]
    if any(qty is None or qty < 0 for qty in quantities):
        result["eta_reference_status"] = "INVALID_SOURCE"
        return result
    if not isclose(fsum(quantities), in_transit_qty, rel_tol=1e-9, abs_tol=1e-6):
        result["eta_reference_status"] = "SOURCE_MISMATCH"
        return result
    buckets: list[list[float]] = [[] for _ in range(15)]
    missing: list[float] = []
    dates: list[str] = []
    for item, qty in zip(details, quantities, strict=True):
        if qty == 0:
            continue
        try:
            eta = date.fromisoformat(str(item.get("eta")))
        except (TypeError, ValueError):
            missing.append(qty)
            continue
        offset = (eta - monday).days
        bucket = 0 if offset < 0 else min(14, offset // 7 + 1)
        buckets[bucket].append(qty)
        dates.append(eta.isoformat())
    result.update({
        "eta_reference_status": "PARTIAL" if missing else "AVAILABLE",
        "eta_bucket_quantities": [fsum(bucket) for bucket in buckets],
        "eta_missing_qty": fsum(missing), "next_eta": min(dates) if dates else None,
    })
    return result
