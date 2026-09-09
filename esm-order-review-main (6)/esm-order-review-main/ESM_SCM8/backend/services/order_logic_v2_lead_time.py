"""Validated packing-level lead-time aggregation for order-logic v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from statistics import fmean, stdev
from typing import Iterable, Mapping


MAX_LEAD_TIME_DAYS = 180
REQUIRED_MODES = ("AIR", "SEA")


@dataclass(frozen=True, slots=True)
class LeadTimeModeStats:
    sample_size: int
    mean_days: float
    stdev_days: float
    sigma_weeks: float


@dataclass(frozen=True, slots=True)
class LeadTimeAggregation:
    completion_date_from: date
    completion_date_to: date
    api_date_from: date
    api_date_to: date
    fetched_row_count: int
    completed_row_count: int
    packing_count: int
    excluded_missing_packing_rows: int
    excluded_invalid_rows: int
    excluded_conflicting_packings: int
    response_hash: str
    calculated_at: str
    modes: dict[str, LeadTimeModeStats]

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        for key in (
            "completion_date_from",
            "completion_date_to",
            "api_date_from",
            "api_date_to",
        ):
            value[key] = getattr(self, key).isoformat()
        return value


@dataclass(frozen=True, slots=True)
class HQLeadTimeAggregation:
    """HQ domestic lead time at normalized PO×SKU receipt grain."""

    completion_date_from: date
    completion_date_to: date
    fetched_row_count: int
    sample_size: int
    excluded_outside_window: int
    excluded_invalid_rows: int
    mean_days: float
    stdev_days: float
    response_hash: str
    calculated_at: str

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["completion_date_from"] = self.completion_date_from.isoformat()
        value["completion_date_to"] = self.completion_date_to.isoformat()
        return value


def subtract_calendar_months(value: date, months: int) -> date:
    if months < 0:
        raise ValueError("months must be non-negative")
    target_index = value.year * 12 + value.month - 1 - months
    year, month_index = divmod(target_index, 12)
    month = month_index + 1
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(value.day, last_day))


def lead_time_query_window(
    as_of: str | date,
    *,
    completion_months: int = 12,
) -> tuple[date, date, date]:
    resolved = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of))
    if completion_months <= 0:
        raise ValueError("completion_months must be positive")
    completion_from = subtract_calendar_months(resolved, completion_months)
    return completion_from, resolved, completion_from - timedelta(days=MAX_LEAD_TIME_DAYS)


def _parsed_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _mode(value: object) -> str | None:
    normalized = str(value or "").strip().upper().replace(" ", "")
    return {
        "AIR": "AIR",
        "항공": "AIR",
        "SEA": "SEA",
        "해운": "SEA",
        "RAIL": "RAIL",
        "철송": "RAIL",
    }.get(normalized)


def _duration(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not number.is_integer():
        return None
    days = int(number)
    return days if 1 <= days <= MAX_LEAD_TIME_DAYS else None


def aggregate_lead_time_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    as_of: str | date,
    required_modes: tuple[str, ...] = REQUIRED_MODES,
    completion_months: int = 12,
    minimum_sample_size: int = 2,
) -> LeadTimeAggregation:
    """Aggregate completed rows at packing grain using STDEV.S.

    ``required_modes`` selects which transport modes must resolve to a valid
    two-observation sample.  USA uses the default ``("AIR", "SEA")`` while the
    EU/PL policy also measures ``RAIL``.  Rows whose mode is outside the
    requested set are treated as invalid, mirroring the previous AIR/SEA-only
    behaviour.
    """

    materialized = [dict(row) for row in rows]
    if minimum_sample_size < 2:
        raise ValueError("minimum_sample_size must be at least two for STDEV.S")
    completion_from, completion_to, api_from = lead_time_query_window(
        as_of,
        completion_months=completion_months,
    )
    canonical_rows = sorted(
        json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        for row in materialized
    )
    response_hash = hashlib.sha256(
        "\n".join(canonical_rows).encode("utf-8")
    ).hexdigest()

    groups: dict[str, set[tuple[str, date, date, int]]] = {}
    completed_rows = 0
    missing_packing = 0
    invalid_rows = 0
    for row in materialized:
        completed = _parsed_date(row.get("iw_dt"))
        if completed is None or not completion_from <= completed <= completion_to:
            continue
        completed_rows += 1
        packing_no = str(row.get("pckg_no") or "").strip()
        if not packing_no:
            missing_packing += 1
            continue
        shipped = _parsed_date(row.get("ow_dt"))
        mode = _mode(row.get("transport_mode"))
        days = _duration(row.get("ow_to_iw_days"))
        if shipped is None or mode not in required_modes or days is None:
            invalid_rows += 1
            continue
        groups.setdefault(packing_no, set()).add((mode, shipped, completed, days))

    samples: dict[str, list[int]] = {mode: [] for mode in required_modes}
    conflicting_packings = 0
    accepted_packings = 0
    for values in groups.values():
        if len(values) != 1:
            conflicting_packings += 1
            continue
        mode, _shipped, _completed, days = next(iter(values))
        samples.setdefault(mode, []).append(days)
        accepted_packings += 1

    mode_stats: dict[str, LeadTimeModeStats] = {}
    for mode in required_modes:
        values = samples[mode]
        if len(values) < minimum_sample_size:
            raise ValueError(
                f"{mode} completed packing sample must contain at least "
                f"{minimum_sample_size} valid observations"
            )
        stdev_days = stdev(values)
        mode_stats[mode] = LeadTimeModeStats(
            sample_size=len(values),
            mean_days=fmean(values),
            stdev_days=stdev_days,
            sigma_weeks=stdev_days / 7.0,
        )

    return LeadTimeAggregation(
        completion_date_from=completion_from,
        completion_date_to=completion_to,
        api_date_from=api_from,
        api_date_to=completion_to,
        fetched_row_count=len(materialized),
        completed_row_count=completed_rows,
        packing_count=accepted_packings,
        excluded_missing_packing_rows=missing_packing,
        excluded_invalid_rows=invalid_rows,
        excluded_conflicting_packings=conflicting_packings,
        response_hash=response_hash,
        calculated_at=datetime.now(timezone.utc).isoformat(),
        modes=mode_stats,
    )


def aggregate_hq_po_sku_lead_time_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    as_of: str | date,
) -> HQLeadTimeAggregation:
    """Aggregate equal-weight HQ PO×SKU observations over the last 12 months.

    The future HQ API adapter must normalize each valid completed receipt to
    ``po_number``, ``sku_code``, ``po_created_at`` and ``actual_received_at``.
    This function intentionally knows nothing about an endpoint or raw field
    aliases, which remain unresolved in the source contract.
    """

    materialized = [dict(row) for row in rows]
    completion_from, completion_to, _api_from = lead_time_query_window(as_of)
    canonical_rows = sorted(
        json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        for row in materialized
    )
    response_hash = hashlib.sha256(
        "\n".join(canonical_rows).encode("utf-8")
    ).hexdigest()

    samples: list[int] = []
    outside_window = 0
    invalid_rows = 0
    seen: set[tuple[str, str, date, date]] = set()
    for row in materialized:
        po_number = str(row.get("po_number") or "").strip()
        sku_code = str(row.get("sku_code") or "").strip()
        created = _parsed_date(row.get("po_created_at"))
        received = _parsed_date(row.get("actual_received_at"))
        if not po_number or not sku_code or created is None or received is None:
            invalid_rows += 1
            continue
        if not completion_from <= received <= completion_to:
            outside_window += 1
            continue
        if received < created:
            invalid_rows += 1
            continue
        observation = (po_number, sku_code, created, received)
        if observation in seen:
            # Duplicate API rows do not become additional observations.
            continue
        seen.add(observation)
        samples.append((received - created).days)

    if len(samples) < 2:
        raise ValueError(
            "HQ completed PO×SKU sample must contain at least two valid observations"
        )
    return HQLeadTimeAggregation(
        completion_date_from=completion_from,
        completion_date_to=completion_to,
        fetched_row_count=len(materialized),
        sample_size=len(samples),
        excluded_outside_window=outside_window,
        excluded_invalid_rows=invalid_rows,
        mean_days=fmean(samples),
        stdev_days=stdev(samples),
        response_hash=response_hash,
        calculated_at=datetime.now(timezone.utc).isoformat(),
    )


__all__ = [
    "LeadTimeAggregation",
    "HQLeadTimeAggregation",
    "LeadTimeModeStats",
    "aggregate_lead_time_rows",
    "aggregate_hq_po_sku_lead_time_rows",
    "lead_time_query_window",
    "subtract_calendar_months",
]
