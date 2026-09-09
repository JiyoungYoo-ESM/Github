"""Application service for the BETA EU order-logic v2 API."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from backend.auth.models import UserAccount
from backend.cms_client import fetch_cms_lead_time
from backend.services.audit import write_audit_event
from backend.services.cms_source import (
    fetch_cached_cms_raw_data,
    fetch_cached_hq_opo_raw_data,
)
from backend.services.order_logic_v2_excel import generate_order_logic_v2_excel
from backend.services.order_logic_v2_jobs import (
    create_order_logic_v2_job,
    get_order_logic_v2_job,
    order_logic_v2_entity_scope,
    update_order_logic_v2_job,
)
from backend.services.order_logic_v2_lead_time import (
    aggregate_lead_time_rows,
    lead_time_query_window,
)
from backend.services.order_logic_v2_hq_source import (
    COMPLETED_DAY_COUNT as HQ_COMPLETED_DAY_COUNT,
    HQ_CURRENCY_CODE,
    HQ_TIMEZONE,
    HQ_WAREHOUSE_CODE,
    PreparedHQOrderLogicSource,
    build_hq_order_logic_source,
    completed_day_window,
)
from backend.services.order_logic_v2_source import (
    COMPLETED_WEEK_COUNT,
    PreparedOrderLogicSource,
    build_order_logic_v2_source,
    completed_week_window,
)
from backend.services.order_logic_v2_store import (
    load_latest_order_logic_v2_result,
    save_latest_order_logic_v2_result,
)
from backend.services import persistent_state
from core.order_logic_v2 import (
    DEFAULT_CONFIG,
    GRADE_MAJOR,
    GRADE_MINOR,
    HQOrderLogicConfig,
    POLICY_CASH,
    POLICY_SHORTAGE,
    SALES_STATUS_NO_SALES,
    TRANSPORT_HQ_DOMESTIC,
    OrderLogicConfig,
    OrderLogicResult,
    OrderLogicValidationError,
    SKUOrderInput,
    assign_pareto_grades,
    calculate_hq_sku_order,
    calculate_sku_order,
)


LOGIC_VERSION = "2.1.0-rs.5"
RESULT_SCHEMA_VERSION = 10
MAX_SOURCE_AGE_SECONDS = 24 * 60 * 60
SUPPORTED_MODES = (POLICY_CASH, POLICY_SHORTAGE)
_CALENDAR_WEEK_DAYS = 7.0

# Maps a measured transport mode to the OrderLogicConfig fields it overrides.
_LEAD_TIME_CONFIG_FIELDS: dict[str, tuple[str, str]] = {
    "AIR": ("lt_air_days", "sigma_l_air_weeks"),
    "RAIL": ("lt_rail_days", "sigma_l_rail_weeks"),
    "SEA": ("lt_sea_days", "sigma_l_sea_weeks"),
}

# Per-entity measured-lead-time integration. Only entities listed here pull
# live lead-time samples; others keep the reviewed fixed policy values.
# USA ships air/sea only; EU/PL policy uses rail for cash and sea for shortage.
_ENTITY_LEAD_TIME_PLANS: dict[str, dict[str, object]] = {
    "USA": {
        "required_modes": ("AIR", "SEA"),
        "cash_transport_mode": "AIR",
        "shortage_transport_mode": "SEA",
        "error_message": "미주 운송 리드타임 원천을 검증할 수 없어 발주 계산을 차단했습니다.",
    },
    "PL": {
        "required_modes": ("RAIL", "SEA"),
        "cash_transport_mode": "RAIL",
        "shortage_transport_mode": "SEA",
        "error_message": "EU 운송 리드타임 원천을 검증할 수 없어 발주 계산을 차단했습니다.",
    },
}

_RUNNING_TASKS: set[asyncio.Task[None]] = set()
_RUNNING_TASKS_BY_JOB: dict[str, asyncio.Task[None]] = {}


class OrderLogicV2SourceUnavailable(RuntimeError):
    """The calculation is blocked because its CMS snapshot is unavailable."""


class OrderLogicV2DecisionError(ValueError):
    """A reviewer override violates the export decision contract."""


def _policy_mode(value: object) -> str:
    if value not in SUPPORTED_MODES:
        raise ValueError("applied_mode must be CASH or SHORTAGE")
    return str(value)


def _config_from_settings(
    settings: Mapping[str, object] | None,
) -> OrderLogicConfig:
    if settings is None:
        return DEFAULT_CONFIG
    if not isinstance(settings, Mapping):
        raise ValueError("settings must be an object")
    try:
        return OrderLogicConfig(**dict(settings))  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(f"invalid order-logic settings: {exc}") from exc


def _config_with_entity_lead_times(
    config: OrderLogicConfig,
    *,
    entity_code: str,
    as_of: str,
) -> tuple[OrderLogicConfig, dict[str, object] | None]:
    """Resolve server-managed policy transports and measured lead-time values."""

    code = str(entity_code or "").strip().upper()
    # Entity policy values are server-managed.  Request settings remain in the
    # schema for backward compatibility, but cannot silently change R or the
    # approved safety-stock fences.
    policy_overrides: dict[str, object] = {
        "cover_weeks": 4.0,
        "ss_floor_weeks": 2.0,
        "ss_cap_weeks": 8.0 if code == "USA" else 13.0,
    }
    config = replace(config, **policy_overrides)
    plan = _ENTITY_LEAD_TIME_PLANS.get(code)
    if plan is None:
        raise OrderLogicV2SourceUnavailable(
            f"{code or 'UNKNOWN'} 법인의 리드타임 원천 어댑터가 없어 계산을 차단했습니다."
        )

    _completion_from, completion_to, api_from = lead_time_query_window(as_of)
    try:
        rows = fetch_cms_lead_time(
            code,
            date_from=api_from.isoformat(),
            date_to=completion_to.isoformat(),
            include_in_transit=False,
        )
        aggregation = aggregate_lead_time_rows(
            rows,
            as_of=as_of,
            required_modes=plan["required_modes"],
        )
    except Exception as exc:  # noqa: BLE001 - upstream errors are normalized
        raise OrderLogicV2SourceUnavailable(
            plan["error_message"]
        ) from exc

    # Override only the lead-time fields that this entity measures, so an
    # unmeasured mode keeps its reviewed fixed value (for example EU AIR).
    overrides: dict[str, object] = {
        "cash_transport_mode": plan["cash_transport_mode"],
        "shortage_transport_mode": plan["shortage_transport_mode"],
    }
    for mode in plan["required_modes"]:
        stats = aggregation.modes[mode]
        lt_field, sigma_field = _LEAD_TIME_CONFIG_FIELDS[mode]
        overrides[lt_field] = stats.mean_days
        overrides[sigma_field] = stats.sigma_weeks
    resolved = replace(config, **overrides)

    audit = aggregation.as_dict()
    audit["entity_code"] = code
    audit["policy_transport_modes"] = {
        POLICY_CASH: plan["cash_transport_mode"],
        POLICY_SHORTAGE: plan["shortage_transport_mode"],
    }
    return resolved, audit


def resolve_order_logic_v2_entity_lead_times(
    config: OrderLogicConfig,
    *,
    entity_code: str,
    as_of: str,
) -> tuple[OrderLogicConfig, dict[str, object] | None]:
    """Publicly expose the validated V2 measured lead-time policy snapshot."""

    return _config_with_entity_lead_times(
        config,
        entity_code=entity_code,
        as_of=as_of,
    )


def _source_age_seconds(cache_info: Mapping[str, object]) -> float:
    value = cache_info.get("age_seconds")
    if isinstance(value, bool):
        raise OrderLogicV2SourceUnavailable(
            "CMS 원천 데이터의 최신성을 확인할 수 없어 계산을 차단했습니다."
        )
    try:
        age_seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise OrderLogicV2SourceUnavailable(
            "CMS 원천 데이터의 최신성을 확인할 수 없어 계산을 차단했습니다."
        ) from exc
    if not math.isfinite(age_seconds) or age_seconds < 0:
        raise OrderLogicV2SourceUnavailable(
            "CMS 원천 데이터의 최신성을 확인할 수 없어 계산을 차단했습니다."
        )
    return age_seconds


def _fetch_fresh_cms_source(
    as_of: str,
    entity_code: str = "PL",
) -> tuple[dict[str, object], dict[str, object]]:
    """Fetch one CMS snapshot and refuse to calculate from data older than 24h."""

    date_from = completed_week_window(as_of).period_start.isoformat()
    try:
        raw, cache_info, _dates = fetch_cached_cms_raw_data(
            as_of=as_of,
            date_from=date_from,
            entity_code=entity_code,
        )
    except Exception as exc:  # noqa: BLE001 - upstream errors are normalized
        raise OrderLogicV2SourceUnavailable(
            "CMS 원천 데이터를 조회하지 못해 발주 계산을 차단했습니다."
        ) from exc

    if _source_age_seconds(cache_info) > MAX_SOURCE_AGE_SECONDS:
        try:
            raw, cache_info, _dates = fetch_cached_cms_raw_data(
                as_of=as_of,
                date_from=date_from,
                force_refresh=True,
                entity_code=entity_code,
            )
        except Exception as exc:  # noqa: BLE001 - upstream errors are normalized
            raise OrderLogicV2SourceUnavailable(
                "CMS 원천 데이터가 24시간을 초과했고 재조회도 실패해 계산을 차단했습니다."
            ) from exc

    if _source_age_seconds(cache_info) > MAX_SOURCE_AGE_SECONDS:
        raise OrderLogicV2SourceUnavailable(
            "CMS 원천 데이터가 24시간을 초과해 발주 계산을 차단했습니다."
        )
    if not isinstance(raw, dict):
        raise OrderLogicV2SourceUnavailable(
            "CMS 원천 데이터 형식이 올바르지 않아 발주 계산을 차단했습니다."
        )
    return raw, dict(cache_info)


def _source_snapshot_id(
    prepared: PreparedOrderLogicSource | PreparedHQOrderLogicSource,
    cache_info: Mapping[str, object],
    lead_time_audit: Mapping[str, object] | None = None,
) -> str:
    lead_time_digest = dict(lead_time_audit or {})
    # The calculation timestamp is useful for audit display, but it is not part
    # of the source data.  Excluding it keeps an identical CMS snapshot and
    # lead-time response reproducible across reruns.
    lead_time_digest.pop("calculated_at", None)
    digest_payload = {
        "created_at": cache_info.get("created_at"),
        "period_start": prepared.period_start.isoformat(),
        "period_end": prepared.period_end.isoformat(),
        "rows": prepared.rows,
        "source_audit": prepared.source_audit,
        "lead_time_audit": lead_time_digest,
    }
    serialized = json.dumps(
        digest_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _source_warnings(row: Mapping[str, object]) -> tuple[str, ...]:
    value = row.get("warnings")
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if item not in (None, ""))
    return (str(value),)


def _sku_input(row: Mapping[str, object]) -> SKUOrderInput:
    return SKUOrderInput(
        sku_code=str(row.get("sku_code") or ""),
        weekly_sales=row.get("weekly_sales"),  # type: ignore[arg-type]
        revenue_amt=row.get("revenue", 0.0),  # type: ignore[arg-type]
        qty_incoming=row.get("incoming_qty"),  # type: ignore[arg-type]
        qty_eu_available=row.get("eu_available_qty"),  # type: ignore[arg-type]
        qty_in_transit=row.get("transit_qty"),  # type: ignore[arg-type]
        qty_local_available=row.get("local_available_qty"),  # type: ignore[arg-type]
    )


def _split_calculable_rows(
    prepared: PreparedOrderLogicSource | PreparedHQOrderLogicSource,
    *,
    config: OrderLogicConfig | HQOrderLogicConfig,
) -> tuple[
    list[tuple[dict[str, object], SKUOrderInput]],
    dict[str, str],
]:
    valid: list[tuple[dict[str, object], SKUOrderInput]] = []
    invalid: dict[str, str] = {}
    seen: set[str] = set()

    for source_value in prepared.rows:
        source_row = dict(source_value)
        sku_code = str(source_row.get("sku_code") or "")
        source_error = source_row.get("validation_error")
        if not sku_code:
            continue
        if sku_code in seen:
            invalid[sku_code] = "중복 SKU 코드가 있어 계산할 수 없습니다."
            continue
        seen.add(sku_code)
        if source_error:
            invalid[sku_code] = str(source_error)
            continue
        if source_row.get("check_required") is True:
            invalid[sku_code] = str(
                source_row.get("check_required_reason")
                or "재고 마스터 등록 여부를 확인해야 해 발주수량을 계산하지 않습니다."
            )
            continue

        item = _sku_input(source_row)
        try:
            # Validate the complete per-SKU input without duplicating core rules.
            if isinstance(config, HQOrderLogicConfig):
                calculate_hq_sku_order(
                    item,
                    grade=GRADE_MINOR,
                    policy_mode=POLICY_CASH,
                    config=config,
                )
            else:
                calculate_sku_order(
                    item,
                    grade=GRADE_MINOR,
                    policy_mode=POLICY_CASH,
                    config=config,
                )
        except OrderLogicValidationError as exc:
            invalid[sku_code] = str(exc)
            continue
        valid.append((source_row, item))
    return valid, invalid


def _unit_price(row: Mapping[str, object]) -> float | None:
    value = row.get("unit_price_local", row.get("unit_price_eur"))
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _unit_price_krw(row: Mapping[str, object]) -> float | None:
    value = row.get("unit_price_krw")
    if value is None:
        # HQ/OPO의 unit_price_local은 이미 KRW다.
        value = row.get("unit_price_local") if row.get("entity_code") == "HQ" else None
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _row_from_calculation(
    source_row: Mapping[str, object],
    calculation: OrderLogicResult,
) -> dict[str, object]:
    d_bar = calculation.d_bar
    sigma = calculation.sigma
    suggested_qty = calculation.suggested_qty
    unit_price = _unit_price(source_row)
    unit_price_krw = _unit_price_krw(source_row)
    suggested_amount = (
        float(suggested_qty) * unit_price
        if suggested_qty is not None and unit_price is not None
        else None
    )
    suggested_amount_krw = (
        float(suggested_qty) * unit_price_krw
        if suggested_qty is not None and unit_price_krw is not None
        else None
    )
    is_calculable = not calculation.is_data_insufficient
    warnings = tuple(
        dict.fromkeys(
            (*_source_warnings(source_row), *calculation.warnings)
        )
    )
    if not is_calculable or calculation.sales_status == SALES_STATUS_NO_SALES:
        order_signal = "-"
    elif calculation.need_order:
        order_signal = (
            "확인후발주"
            if calculation.sales_status.startswith("⚠") or warnings
            else "발주"
        )
    else:
        order_signal = "충분"

    depletion_weeks = (
        (calculation.qty_local_available + calculation.qty_in_transit) / d_bar
        if d_bar is not None and d_bar > 0
        else None
    )
    demand_grain_days = (
        1.0
        if calculation.transport_mode == TRANSPORT_HQ_DOMESTIC
        else _CALENDAR_WEEK_DAYS
    )
    protection_days = calculation.p_weeks * demand_grain_days
    return {
        "sku_code": calculation.sku_code,
        "product_name": str(source_row.get("product_name") or ""),
        "brand": str(source_row.get("brand") or ""),
        "barcode": str(source_row.get("barcode") or ""),
        "sales_13w_qty": _nonnegative_source_number(
            source_row.get("sales_13w_qty")
        ),
        "calculable": is_calculable,
        "validation_error": (
            None
            if is_calculable
            else (
                f"최근 {HQ_COMPLETED_DAY_COUNT}개 완료일 판매이력이 부족합니다."
                if calculation.transport_mode == TRANSPORT_HQ_DOMESTIC
                else f"최근 {COMPLETED_WEEK_COUNT}개 완료 주 판매이력이 부족합니다."
            )
        ),
        "data_status": calculation.sales_status,
        "grade": calculation.grade,
        "grade_label": "주력" if calculation.grade == GRADE_MAJOR else "일반",
        "policy_mode": calculation.policy_mode,
        "inbound_status_source_present": bool(
            source_row.get("inbound_status_source_present")
        ),
        "weeks_with_sales": calculation.weeks_with_sales,
        "is_no_sales": calculation.is_no_sales,
        "is_intermittent": calculation.is_intermittent,
        "has_bulk_week": calculation.has_bulk_week,
        "demand_avg": d_bar,
        "demand_sigma": sigma,
        "cv": (
            sigma / d_bar
            if d_bar is not None and d_bar > 0 and sigma is not None
            else None
        ),
        "z_applied": calculation.z_applied,
        "transport_mode": calculation.transport_mode,
        # Calendar days are the canonical duration contract.  The legacy
        # *_weeks fields below intentionally keep their historical grain:
        # HQ uses day-grain demand while PL/USA use week-grain demand.
        "lead_time_days": calculation.lt_days,
        "lead_time_weeks": calculation.lt_days / _CALENDAR_WEEK_DAYS,
        "protection_weeks": calculation.p_weeks,
        "protection_days": protection_days,
        "review_days": protection_days - calculation.lt_days,
        "lead_time_sigma_weeks": calculation.sigma_l_weeks,
        "lead_time_sigma_days": calculation.sigma_l_weeks * demand_grain_days,
        "layer1": calculation.layer1,
        "raw_safety_stock": calculation.layer2_ss_raw,
        "safety_stock_floor": calculation.ss_floor,
        "safety_stock_cap": calculation.ss_cap,
        "safety_stock": calculation.layer2_ss,
        "safety_stock_clamp": calculation.ss_clamp,
        "layer3": calculation.layer3,
        "reorder_point": calculation.reorder_point_s,
        "target_stock": calculation.target_stock_s,
        "open_qty": source_row.get("open_qty"),
        "incoming_qty": calculation.qty_incoming,
        "pnfm_qty": source_row.get("pnfm_qty"),
        "inbound_progress_qty": source_row.get("inbound_progress_qty"),
        "inbound_completed_qty": source_row.get("inbound_completed_qty"),
        "eu_available_qty": calculation.qty_eu_available,
        "transit_qty": calculation.qty_in_transit,
        "next_eta": source_row.get("next_eta"),
        "next_eta_status": source_row.get("next_eta_status"),
        "shipping_schedule": deepcopy(source_row.get("shipping_schedule") or []),
        "shipping_eta_details": deepcopy(
            source_row.get("shipping_eta_details") or []
        ),
        "eta_actual_qty": _nonnegative_source_number(
            source_row.get("eta_actual_qty")
        ),
        "eta_estimated_qty": _nonnegative_source_number(
            source_row.get("eta_estimated_qty")
        ),
        "eta_missing_qty": _nonnegative_source_number(
            source_row.get("eta_missing_qty")
        ),
        "local_available_qty": calculation.qty_local_available,
        "inventory_position": calculation.ip_total,
        "need_order": calculation.need_order,
        "raw_order_qty": calculation.raw_order_qty,
        "suggested_qty": suggested_qty,
        "inventory_position_without_incoming": calculation.ip_without_incoming,
        "need_upper_order": calculation.need_upper_order,
        "raw_upper_order_qty": calculation.raw_upper_order_qty,
        "upper_suggested_qty": calculation.upper_suggested_qty,
        "depletion_weeks": depletion_weeks,
        # Export-only operational fields are calculated as auditable Excel
        # formulas.  Keep the JSON row contract explicit without duplicating
        # those formulas in the approved order-calculation service.
        "transport_recommendation": None,
        "order_slack_weeks": None,
        "expected_order_date": None,
        "conservative_slack_weeks": None,
        "early_warning_date": None,
        "order_signal": order_signal,
        "confirmed_qty": suggested_qty,
        "memo": None,
        "unit_price_local": unit_price,
        "unit_price_krw": unit_price_krw,
        "suggested_amount_local": suggested_amount,
        "confirmed_amount_local": suggested_amount,
        "suggested_amount_krw": suggested_amount_krw,
        "confirmed_amount_krw": suggested_amount_krw,
        # 기존 프론트/Excel 저장 결과 호환용 별칭. 실제 통화는 결과의
        # currency_code(PL=EUR, USA=USD)를 따른다.
        "unit_price_eur": unit_price,
        "suggested_amount_eur": suggested_amount,
        "confirmed_amount_eur": suggested_amount,
        "check_required": bool(source_row.get("check_required")),
        "check_required_reason": source_row.get("check_required_reason"),
        "warnings": list(warnings),
    }


def _nonnegative_source_number(value: object) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) and number >= 0 else 0.0


def _row_for_invalid_sku(
    source_row: Mapping[str, object],
    *,
    policy_mode: str,
    validation_error: str,
    grade: str,
    config: OrderLogicConfig | HQOrderLogicConfig,
) -> dict[str, object]:
    check_required = bool(source_row.get("check_required"))
    incoming = _nonnegative_source_number(source_row.get("incoming_qty"))
    eu_available = _nonnegative_source_number(source_row.get("eu_available_qty"))
    transit = _nonnegative_source_number(source_row.get("transit_qty"))
    local_available = _nonnegative_source_number(source_row.get("local_available_qty"))
    warnings = list(
        dict.fromkeys(
            (*_source_warnings(source_row), "CALCULATION_BLOCKED")
        )
    )
    return {
        "sku_code": str(source_row.get("sku_code") or ""),
        "product_name": str(source_row.get("product_name") or ""),
        "brand": str(source_row.get("brand") or ""),
        "barcode": str(source_row.get("barcode") or ""),
        "sales_13w_qty": _nonnegative_source_number(
            source_row.get("sales_13w_qty")
        ),
        "calculable": False,
        "validation_error": validation_error,
        "data_status": "확인필요" if check_required else "계산불가",
        "grade": grade,
        "grade_label": "주력" if grade == GRADE_MAJOR else "일반",
        "policy_mode": policy_mode,
        "inbound_status_source_present": bool(
            source_row.get("inbound_status_source_present")
        ),
        "weeks_with_sales": None,
        "is_no_sales": False,
        "is_intermittent": False,
        "has_bulk_week": False,
        "demand_avg": None,
        "demand_sigma": None,
        "cv": None,
        "z_applied": None,
        "transport_mode": (
            TRANSPORT_HQ_DOMESTIC
            if isinstance(config, HQOrderLogicConfig)
            else (
                config.cash_transport_mode
                if policy_mode == POLICY_CASH
                else config.shortage_transport_mode
            )
        ),
        "lead_time_days": None,
        "lead_time_weeks": None,
        "protection_weeks": None,
        "protection_days": None,
        "review_days": None,
        "lead_time_sigma_weeks": None,
        "lead_time_sigma_days": None,
        "layer1": None,
        "raw_safety_stock": None,
        "safety_stock_floor": None,
        "safety_stock_cap": None,
        "safety_stock": None,
        "safety_stock_clamp": None,
        "layer3": None,
        "reorder_point": None,
        "target_stock": None,
        "open_qty": source_row.get("open_qty"),
        "incoming_qty": incoming,
        "pnfm_qty": source_row.get("pnfm_qty"),
        "inbound_progress_qty": source_row.get("inbound_progress_qty"),
        "inbound_completed_qty": source_row.get("inbound_completed_qty"),
        "eu_available_qty": eu_available,
        "transit_qty": transit,
        "next_eta": source_row.get("next_eta"),
        "next_eta_status": source_row.get("next_eta_status"),
        "shipping_schedule": deepcopy(source_row.get("shipping_schedule") or []),
        "shipping_eta_details": deepcopy(
            source_row.get("shipping_eta_details") or []
        ),
        "eta_actual_qty": _nonnegative_source_number(
            source_row.get("eta_actual_qty")
        ),
        "eta_estimated_qty": _nonnegative_source_number(
            source_row.get("eta_estimated_qty")
        ),
        "eta_missing_qty": _nonnegative_source_number(
            source_row.get("eta_missing_qty")
        ),
        "local_available_qty": local_available,
        "inventory_position": incoming + eu_available + transit + local_available,
        "need_order": None,
        "raw_order_qty": None,
        "suggested_qty": None,
        "inventory_position_without_incoming": (
            eu_available + transit + local_available
        ),
        "need_upper_order": None,
        "raw_upper_order_qty": None,
        "upper_suggested_qty": None,
        "depletion_weeks": None,
        "transport_recommendation": None,
        "order_slack_weeks": None,
        "expected_order_date": None,
        "conservative_slack_weeks": None,
        "early_warning_date": None,
        "order_signal": "-",
        "confirmed_qty": None,
        "memo": None,
        "unit_price_local": _unit_price(source_row),
        "unit_price_krw": _unit_price_krw(source_row),
        "suggested_amount_local": None,
        "confirmed_amount_local": None,
        "suggested_amount_krw": None,
        "confirmed_amount_krw": None,
        "unit_price_eur": _unit_price(source_row),
        "suggested_amount_eur": None,
        "confirmed_amount_eur": None,
        "check_required": check_required,
        "check_required_reason": source_row.get("check_required_reason"),
        "warnings": warnings,
    }


def _scenario_summary(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    materialized = list(rows)
    calculable = [row for row in materialized if row.get("calculable") is True]
    order_rows = [row for row in calculable if row.get("need_order") is True]
    check_required_rows = [
        row for row in materialized if row.get("check_required") is True
    ]
    return {
        "total_skus": len(materialized),
        "calculable_skus": len(calculable),
        "invalid_skus": len(materialized) - len(calculable),
        "order_skus": len(order_rows),
        "check_required_skus": len(check_required_rows),
        "suggested_qty_total": sum(
            float(row.get("suggested_qty") or 0.0) for row in order_rows
        ),
        "upper_suggested_qty_total": sum(
            float(row.get("upper_suggested_qty") or 0.0) for row in calculable
        ),
        "suggested_amount_eur_total": sum(
            float(row.get("suggested_amount_eur") or 0.0) for row in order_rows
        ),
        "suggested_amount_krw_total": sum(
            float(row.get("suggested_amount_krw") or 0.0) for row in order_rows
        ),
    }


def build_order_logic_v2_result(
    prepared: PreparedOrderLogicSource,
    *,
    cache_info: Mapping[str, object],
    applied_mode: str,
    job_id: str,
    as_of: str,
    config: OrderLogicConfig = DEFAULT_CONFIG,
    preview: bool = False,
    entity_code: str = "PL",
    lead_time_audit: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Calculate both modes from one immutable prepared CMS snapshot."""

    resolved_entity = str(entity_code or "").strip().upper()
    if resolved_entity not in {"PL", "USA"}:
        raise OrderLogicV2SourceUnavailable(
            f"{resolved_entity or 'UNKNOWN'} 법인의 결과 원천·통화 계약이 없어 계산을 차단했습니다."
        )
    resolved_mode = _policy_mode(applied_mode)
    valid, invalid = _split_calculable_rows(prepared, config=config)
    population_inputs = tuple(
        _sku_input(dict(source_row))
        for source_row in prepared.rows
        if str(dict(source_row).get("sku_code") or "")
    )
    try:
        grades = assign_pareto_grades(population_inputs, config=config)
    except OrderLogicValidationError as exc:
        raise OrderLogicV2SourceUnavailable(
            "Pareto 모집단 매출을 검증할 수 없어 발주 계산을 차단했습니다."
        ) from exc
    valid_inputs = tuple(item for _source_row, item in valid)
    result_by_mode = {
        mode: {
            item.sku_code: calculate_sku_order(
                item,
                grade=grades[item.sku_code],
                policy_mode=mode,
                config=config,
            )
            for item in valid_inputs
        }
        for mode in SUPPORTED_MODES
    }

    snapshot_id = _source_snapshot_id(prepared, cache_info, lead_time_audit)
    scenarios: dict[str, dict[str, object]] = {}
    for mode in SUPPORTED_MODES:
        mode_rows: list[dict[str, object]] = []
        for source_value in prepared.rows:
            source_row = dict(source_value)
            sku_code = str(source_row.get("sku_code") or "")
            if not sku_code:
                continue
            calculation = result_by_mode[mode].get(sku_code)
            if calculation is None:
                mode_rows.append(
                    _row_for_invalid_sku(
                        source_row,
                        policy_mode=mode,
                        validation_error=invalid.get(
                            sku_code,
                            "입력값 검증에 실패해 계산할 수 없습니다.",
                        ),
                        grade=grades[sku_code],
                        config=config,
                    )
                )
            else:
                mode_rows.append(_row_from_calculation(source_row, calculation))
        scenarios[mode] = {
            "source_snapshot_id": snapshot_id,
            "summary": _scenario_summary(mode_rows),
            "rows": mode_rows,
        }

    official = scenarios[resolved_mode]
    calculated_at = datetime.now(timezone.utc).isoformat()
    return {
        "status": "success",
        "job_id": job_id,
        "logic_version": LOGIC_VERSION,
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "as_of": as_of,
        "entity_code": resolved_entity,
        "currency_code": "USD" if resolved_entity == "USA" else "EUR",
        "duration_unit": "CALENDAR_DAY",
        "period_unit": "week",
        "demand_period_count": COMPLETED_WEEK_COUNT,
        "observation_window_days": int(COMPLETED_WEEK_COUNT * _CALENDAR_WEEK_DAYS),
        "demand_grain": "WEEK_7D",
        "demand_grain_days": int(_CALENDAR_WEEK_DAYS),
        "preview": preview,
        "applied_mode": resolved_mode,
        # Existing Excel metadata consumes policy_mode.
        "policy_mode": resolved_mode,
        "calculated_at": calculated_at,
        "period_start": prepared.period_start.isoformat(),
        "period_end": prepared.period_end.isoformat(),
        "source_fetched_at": cache_info.get("created_at"),
        "source_age_seconds": _source_age_seconds(cache_info),
        "source_snapshot_id": snapshot_id,
        "source_counts": dict(prepared.source_counts),
        "source_audit": deepcopy(prepared.source_audit),
        "lead_time_audit": deepcopy(dict(lead_time_audit or {})) or None,
        "settings": config.as_dict(),
        "warnings": list(prepared.warnings),
        "summary": deepcopy(official["summary"]),
        "rows": deepcopy(official["rows"]),
        "scenarios": scenarios,
    }


def build_hq_order_logic_v2_result(
    prepared: PreparedHQOrderLogicSource,
    *,
    cache_info: Mapping[str, object],
    applied_mode: str,
    job_id: str,
    as_of: str,
    config: HQOrderLogicConfig,
    preview: bool = False,
) -> dict[str, object]:
    """Calculate both HQ scenarios in day units from one immutable snapshot."""

    resolved_mode = _policy_mode(applied_mode)
    valid, invalid = _split_calculable_rows(prepared, config=config)
    population_inputs = tuple(
        _sku_input(dict(source_row))
        for source_row in prepared.rows
        if str(dict(source_row).get("sku_code") or "")
    )
    try:
        grades = assign_pareto_grades(population_inputs, config=config)
    except OrderLogicValidationError as exc:
        raise OrderLogicV2SourceUnavailable(
            "Pareto 모집단 매출을 검증할 수 없어 발주 계산을 차단했습니다."
        ) from exc

    lead_time_audit = deepcopy(prepared.lead_time)
    lead_time_audit["policy_scenarios"] = {
        POLICY_CASH: TRANSPORT_HQ_DOMESTIC,
        POLICY_SHORTAGE: TRANSPORT_HQ_DOMESTIC,
    }
    snapshot_id = _source_snapshot_id(prepared, cache_info, lead_time_audit)

    valid_inputs = tuple(item for _source_row, item in valid)
    result_by_mode = {
        mode: {
            item.sku_code: calculate_hq_sku_order(
                item,
                grade=grades[item.sku_code],
                policy_mode=mode,
                config=config,
            )
            for item in valid_inputs
        }
        for mode in SUPPORTED_MODES
    }

    scenarios: dict[str, dict[str, object]] = {}
    for mode in SUPPORTED_MODES:
        mode_rows: list[dict[str, object]] = []
        for source_value in prepared.rows:
            source_row = dict(source_value)
            sku_code = str(source_row.get("sku_code") or "")
            if not sku_code:
                continue
            calculation = result_by_mode[mode].get(sku_code)
            if calculation is None:
                mode_rows.append(
                    _row_for_invalid_sku(
                        source_row,
                        policy_mode=mode,
                        validation_error=invalid.get(
                            sku_code,
                            "입력값 검증에 실패해 계산할 수 없습니다.",
                        ),
                        grade=grades[sku_code],
                        config=config,
                    )
                )
            else:
                mode_rows.append(_row_from_calculation(source_row, calculation))
        scenarios[mode] = {
            "source_snapshot_id": snapshot_id,
            "summary": _scenario_summary(mode_rows),
            "rows": mode_rows,
        }

    official = scenarios[resolved_mode]
    return {
        "status": "success",
        "job_id": job_id,
        "logic_version": LOGIC_VERSION,
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "as_of": as_of,
        "entity_code": "HQ",
        "warehouse_code": HQ_WAREHOUSE_CODE,
        "timezone": str(HQ_TIMEZONE),
        "currency_code": HQ_CURRENCY_CODE,
        # HQ amounts are already KRW, so no exchange rate is applied.
        "exchange_rate_krw": None,
        "duration_unit": "CALENDAR_DAY",
        "period_unit": "day",
        "demand_period_count": HQ_COMPLETED_DAY_COUNT,
        "observation_window_days": HQ_COMPLETED_DAY_COUNT,
        "demand_grain": "DAY_1D",
        "demand_grain_days": 1,
        "preview": preview,
        "applied_mode": resolved_mode,
        "policy_mode": resolved_mode,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "period_start": prepared.period_start.isoformat(),
        "period_end": prepared.period_end.isoformat(),
        "source_fetched_at": cache_info.get("created_at"),
        "source_age_seconds": _source_age_seconds(cache_info),
        "source_snapshot_id": snapshot_id,
        "source_counts": dict(prepared.source_counts),
        "source_audit": deepcopy(prepared.source_audit),
        "lead_time_audit": lead_time_audit,
        "settings": config.as_dict(),
        "warnings": list(prepared.warnings),
        "summary": deepcopy(official["summary"]),
        "rows": deepcopy(official["rows"]),
        "scenarios": scenarios,
    }


def calculate_hq_order_logic_v2_from_cms(
    *,
    as_of: str,
    applied_mode: str,
    job_id: str,
    settings: Mapping[str, object] | None = None,
    preview: bool = False,
) -> dict[str, object]:
    """Run one HQ/OPO calculation from the live CMS sources.

    HQ policy values are server-managed: ``R``, the safety-stock fences and the
    measured domestic lead time cannot be overridden by a request, so only the
    reviewed Pareto cutoff and service levels come from settings.
    """

    resolved_mode = _policy_mode(applied_mode)
    window = completed_day_window(as_of)
    try:
        raw, cache_info = fetch_cached_hq_opo_raw_data(
            as_of=as_of,
            date_from=window.period_start.isoformat(),
            date_to=window.period_end.isoformat(),
        )
    except Exception as exc:  # noqa: BLE001 - upstream errors are normalized
        raise OrderLogicV2SourceUnavailable(
            "본사 오포창고 원천 데이터를 조회하지 못해 발주 계산을 차단했습니다."
        ) from exc

    if _source_age_seconds(cache_info) > MAX_SOURCE_AGE_SECONDS:
        try:
            raw, cache_info = fetch_cached_hq_opo_raw_data(
                as_of=as_of,
                date_from=window.period_start.isoformat(),
                date_to=window.period_end.isoformat(),
                force_refresh=True,
            )
        except Exception as exc:  # noqa: BLE001 - upstream errors are normalized
            raise OrderLogicV2SourceUnavailable(
                "본사 오포창고 원천 데이터를 갱신하지 못해 발주 계산을 차단했습니다."
            ) from exc
        if _source_age_seconds(cache_info) > MAX_SOURCE_AGE_SECONDS:
            raise OrderLogicV2SourceUnavailable(
                "본사 오포창고 원천 데이터가 24시간을 초과해 발주 계산을 차단했습니다."
            )

    try:
        prepared = build_hq_order_logic_source(raw, as_of=as_of)
    except Exception as exc:  # noqa: BLE001 - malformed upstream data is blocked
        raise OrderLogicV2SourceUnavailable(
            f"본사 오포창고 원천이 발주 계산 요건을 충족하지 못했습니다: {exc}"
        ) from exc

    requested = dict(settings or {})
    try:
        config = HQOrderLogicConfig(
            grade_cutoff=float(requested.get("grade_cutoff", 0.80)),
            z_cash_major=float(requested.get("z_cash_major", 1.28)),
            z_cash_minor=float(requested.get("z_cash_minor", 1.08)),
            z_shortage_major=float(requested.get("z_shortage_major", 1.68)),
            z_shortage_minor=float(requested.get("z_shortage_minor", 1.28)),
            lt_days=float(prepared.lead_time["mean_days"]),
            sigma_l_days=float(prepared.lead_time["stdev_days"]),
        )
    except (OrderLogicValidationError, TypeError, ValueError) as exc:
        raise OrderLogicV2SourceUnavailable(
            f"본사 발주 정책값을 검증할 수 없어 계산을 차단했습니다: {exc}"
        ) from exc

    return build_hq_order_logic_v2_result(
        prepared,
        cache_info=cache_info,
        applied_mode=resolved_mode,
        job_id=job_id,
        as_of=as_of,
        config=config,
        preview=preview,
    )


def calculate_order_logic_v2_from_cms(
    *,
    as_of: str,
    applied_mode: str,
    job_id: str,
    settings: Mapping[str, object] | None = None,
    preview: bool = False,
    entity_code: str = "PL",
) -> dict[str, object]:
    resolved_mode = _policy_mode(applied_mode)
    if str(entity_code or "").strip().upper() == "HQ":
        return calculate_hq_order_logic_v2_from_cms(
            as_of=as_of,
            applied_mode=resolved_mode,
            job_id=job_id,
            settings=settings,
            preview=preview,
        )
    config, lead_time_audit = _config_with_entity_lead_times(
        _config_from_settings(settings),
        entity_code=entity_code,
        as_of=as_of,
    )
    raw, cache_info = _fetch_fresh_cms_source(as_of, entity_code=entity_code)
    try:
        prepared = build_order_logic_v2_source(
            raw,
            as_of=as_of,
            config=config,
            entity_code=entity_code,
        )  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001 - malformed upstream data is blocked
        raise OrderLogicV2SourceUnavailable(
            "CMS 원천 데이터가 발주 계산 요건을 충족하지 못해 계산을 차단했습니다."
        ) from exc
    return build_order_logic_v2_result(
        prepared,
        cache_info=cache_info,
        applied_mode=resolved_mode,
        job_id=job_id,
        as_of=as_of,
        config=config,
        preview=preview,
        entity_code=entity_code,
        lead_time_audit=lead_time_audit,
    )


def _is_latest_order_logic_v2_job(
    job_id: str,
    client_id: str,
    entity_code: str,
) -> bool:
    """Prevent an older, slower job from overwriting the official latest run."""

    entity_scope = order_logic_v2_entity_scope(client_id, entity_code)
    if persistent_state.enabled():
        return persistent_state.job_is_latest(job_id, entity_scope)
    current = get_order_logic_v2_job(job_id)
    return bool(
        current
        and current.get("client_id") == client_id
        and current.get("security_scope") == entity_scope
        and current.get("is_latest") is True
    )


async def run_order_logic_v2_job(
    job_id: str,
    client_id: str,
    request_body: Mapping[str, object],
) -> None:
    """Execute one queued job and publish only a successful result."""

    entity_code = str(request_body.get("entity_code") or "PL").strip().upper() or "PL"
    if (get_order_logic_v2_job(job_id) or {}).get("status") == "cancelled":
        return
    update_order_logic_v2_job(job_id, status="running")
    write_audit_event(
        "order_logic_v2_job_started",
        None,
        job_id=job_id,
        client_id=client_id,
        as_of=request_body.get("as_of"),
        applied_mode=request_body.get("applied_mode"),
        preview=bool(request_body.get("preview", False)),
        settings=request_body.get("settings"),
    )
    try:
        result = await run_in_threadpool(
            calculate_order_logic_v2_from_cms,
            as_of=str(request_body.get("as_of") or ""),
            applied_mode=str(request_body.get("applied_mode") or ""),
            job_id=job_id,
            settings=(
                request_body.get("settings")
                if isinstance(request_body.get("settings"), Mapping)
                else None
            ),
            preview=bool(request_body.get("preview", False)),
            entity_code=entity_code,
        )
    except OrderLogicV2SourceUnavailable as exc:
        update_order_logic_v2_job(
            job_id,
            status="failed",
            status_code=503,
            error=str(exc),
        )
        write_audit_event(
            "order_logic_v2_job_failed",
            None,
            job_id=job_id,
            client_id=client_id,
            status_code=503,
            error_type=type(exc).__name__,
        )
        return
    except (ValueError, OrderLogicValidationError) as exc:
        update_order_logic_v2_job(
            job_id,
            status="failed",
            status_code=422,
            error=str(exc),
        )
        write_audit_event(
            "order_logic_v2_job_failed",
            None,
            job_id=job_id,
            client_id=client_id,
            status_code=422,
            error_type=type(exc).__name__,
        )
        return
    except Exception as exc:  # noqa: BLE001 - background task must end terminally
        update_order_logic_v2_job(
            job_id,
            status="failed",
            status_code=502,
            error="발주 계산 중 서버 오류가 발생했습니다.",
        )
        write_audit_event(
            "order_logic_v2_job_failed",
            None,
            job_id=job_id,
            client_id=client_id,
            status_code=502,
            error_type=type(exc).__name__,
        )
        return

    if (get_order_logic_v2_job(job_id) or {}).get("status") == "cancelled":
        return
    update_order_logic_v2_job(
        job_id,
        status="succeeded",
        status_code=200,
        result=result,
    )
    if (
        not bool(result.get("preview"))
        and _is_latest_order_logic_v2_job(job_id, client_id, entity_code)
    ):
        save_latest_order_logic_v2_result(client_id, entity_code, result)
    write_audit_event(
        "order_logic_v2_job_succeeded",
        None,
        job_id=job_id,
        client_id=client_id,
        applied_mode=result.get("applied_mode"),
        preview=result.get("preview"),
        source_snapshot_id=result.get("source_snapshot_id"),
        row_count=len(result.get("rows", [])),
    )


def queue_order_logic_v2_job(
    client_id: str,
    request_body: Mapping[str, object],
) -> str:
    """Create a transient/durable job record and dispatch it on the event loop."""

    payload = dict(request_body)
    _policy_mode(payload.get("applied_mode"))
    job_id = create_order_logic_v2_job(
        client_id,
        payload,
        is_latest=not bool(payload.get("preview", False)),
    )
    task = asyncio.create_task(
        run_order_logic_v2_job(job_id, client_id, payload),
        name=f"order-logic-v2:{job_id}",
    )
    _RUNNING_TASKS.add(task)
    _RUNNING_TASKS_BY_JOB[job_id] = task
    task.add_done_callback(lambda _task, job_id=job_id: _RUNNING_TASKS_BY_JOB.pop(job_id, None))
    task.add_done_callback(_RUNNING_TASKS.discard)
    return job_id


def cancel_order_logic_v2_job(job_id: str, client_id: str) -> dict[str, object]:
    job = get_order_logic_v2_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="발주 계산 작업을 찾을 수 없습니다.")
    if job.get("client_id") != client_id:
        raise HTTPException(status_code=403, detail="다른 사용자의 발주 계산 작업에는 접근할 수 없습니다.")
    if job.get("status") in {"succeeded", "failed", "cancelled"}:
        return deepcopy(job)
    update_order_logic_v2_job(job_id, status="cancelled", status_code=499, error="사용자가 분석을 중단했습니다.")
    task = _RUNNING_TASKS_BY_JOB.get(job_id)
    if task is not None:
        task.cancel()
    return get_order_logic_v2_job(job_id) or {"job_id": job_id, "status": "cancelled"}


def owned_order_logic_v2_job(
    job_id: str,
    client_id: str,
) -> dict[str, object]:
    job = get_order_logic_v2_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="발주 계산 작업을 찾을 수 없습니다.")
    if job.get("client_id") != client_id:
        raise HTTPException(
            status_code=403,
            detail="다른 사용자의 발주 계산 작업에는 접근할 수 없습니다.",
        )
    return deepcopy(job)


def latest_order_logic_v2_result(
    client_id: str,
    entity_code: str,
) -> dict[str, object] | None:
    resolved_entity = str(entity_code or "").strip().upper()
    if not resolved_entity:
        return None
    payload = load_latest_order_logic_v2_result(client_id, resolved_entity)
    if not isinstance(payload, dict):
        return None
    if payload.get("result_schema_version") != RESULT_SCHEMA_VERSION:
        # Stored results are immutable snapshots.  Do not silently export an
        # older snapshot through a newer workbook contract because fields such
        # as shipment-level ETA details cannot be reconstructed faithfully.
        return None
    if str(payload.get("entity_code") or "").strip().upper() != resolved_entity:
        return None
    return deepcopy(payload)


def payload_visible_to_user(
    payload: Mapping[str, object],
    user: UserAccount,
) -> dict[str, object]:
    # The order-analysis workspace is the approved exception to the global
    # insight/report amount restriction. Authentication and job ownership are
    # still enforced by the router before this function is called.
    _ = user
    return deepcopy(dict(payload))


def _finite_nonnegative_decision_value(name: str, value: object) -> float:
    if isinstance(value, bool):
        raise OrderLogicV2DecisionError(f"{name}은 0 이상의 숫자여야 합니다.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OrderLogicV2DecisionError(
            f"{name}은 0 이상의 숫자여야 합니다."
        ) from exc
    if not math.isfinite(number) or number < 0:
        raise OrderLogicV2DecisionError(f"{name}은 0 이상의 숫자여야 합니다.")
    return number


def apply_order_decision_overrides(
    result: Mapping[str, object],
    overrides: Iterable[Mapping[str, object]],
    *,
    row_ids: Iterable[object] | None = None,
) -> dict[str, object]:
    """Apply reviewer quantities and select export rows without changing the result."""

    payload = deepcopy(dict(result))
    rows_value = payload.get("rows")
    if not isinstance(rows_value, list) or any(
        not isinstance(row, dict) for row in rows_value
    ):
        raise OrderLogicV2DecisionError("내보낼 발주 결과 행이 없습니다.")
    rows: list[dict[str, object]] = rows_value
    rows_by_sku = {
        str(row.get("sku_code") or ""): row
        for row in rows
        if row.get("sku_code")
    }
    selected_ids: list[str] | None = None
    selected_id_set: set[str] | None = None
    if row_ids is not None:
        selected_ids = []
        selected_id_set = set()
        for value in row_ids:
            sku_code = str(value or "").strip()
            if not sku_code or sku_code not in rows_by_sku:
                raise OrderLogicV2DecisionError(
                    f"결과에 없는 SKU는 내보낼 수 없습니다: {sku_code or '(blank)'}"
                )
            if sku_code in selected_id_set:
                raise OrderLogicV2DecisionError(
                    f"같은 SKU가 내보내기 행에 중복되었습니다: {sku_code}"
                )
            selected_ids.append(sku_code)
            selected_id_set.add(sku_code)

    seen: set[str] = set()
    override_count = 0
    for override in overrides:
        sku_code = str(override.get("sku_code") or "").strip()
        if not sku_code or sku_code not in rows_by_sku:
            raise OrderLogicV2DecisionError(
                f"결과에 없는 SKU는 수정할 수 없습니다: {sku_code or '(blank)'}"
            )
        if sku_code in seen:
            raise OrderLogicV2DecisionError(
                f"같은 SKU의 확정수량이 중복 제출되었습니다: {sku_code}"
            )
        if selected_id_set is not None and sku_code not in selected_id_set:
            raise OrderLogicV2DecisionError(
                f"선택되지 않은 SKU의 확정수량은 제출할 수 없습니다: {sku_code}"
            )
        seen.add(sku_code)
        row = rows_by_sku[sku_code]
        if row.get("calculable") is not True or row.get("suggested_qty") is None:
            raise OrderLogicV2DecisionError(
                f"계산불가 SKU의 확정수량은 수정할 수 없습니다: {sku_code}"
            )

        confirmed_qty = _finite_nonnegative_decision_value(
            f"{sku_code}.confirmed_qty",
            override.get("confirmed_qty"),
        )
        if not math.isclose(
            confirmed_qty,
            round(confirmed_qty),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise OrderLogicV2DecisionError(
                f"{sku_code} 확정수량은 낱개 단위의 정수여야 합니다."
            )

        suggested_qty = float(row["suggested_qty"])
        changed = not math.isclose(
            confirmed_qty,
            suggested_qty,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        memo = str(override.get("memo") or "").strip()
        if changed and not memo:
            raise OrderLogicV2DecisionError(
                f"{sku_code} 제안수량을 변경하려면 메모가 필요합니다."
            )

        row["confirmed_qty"] = confirmed_qty
        row["memo"] = memo or None
        unit_price = _unit_price(row)
        unit_price_krw = _unit_price_krw(row)
        row["confirmed_amount_local"] = (
            confirmed_qty * unit_price if unit_price is not None else None
        )
        row["confirmed_amount_eur"] = (
            confirmed_qty * unit_price if unit_price is not None else None
        )
        row["confirmed_amount_krw"] = (
            confirmed_qty * unit_price_krw if unit_price_krw is not None else None
        )
        if changed:
            override_count += 1

    if selected_ids is not None:
        rows = [rows_by_sku[sku_code] for sku_code in selected_ids]
        payload["rows"] = rows

    payload["exported_at"] = datetime.now(timezone.utc).isoformat()
    payload["decision_override_count"] = override_count
    payload["export_filter_applied"] = selected_ids is not None
    payload["export_row_count"] = len(rows)
    summary_value = _scenario_summary(rows)
    summary_value["confirmed_qty_total"] = sum(
        float(row.get("confirmed_qty") or 0.0) for row in rows
    )
    summary_value["confirmed_amount_eur_total"] = sum(
        float(row.get("confirmed_amount_eur") or 0.0) for row in rows
    )
    summary_value["confirmed_amount_krw_total"] = sum(
        float(row.get("confirmed_amount_krw") or 0.0) for row in rows
    )
    payload["summary"] = summary_value
    return payload


def build_order_logic_v2_export(
    *,
    job_id: str,
    client_id: str,
    user: UserAccount,
    overrides: Iterable[Mapping[str, object]],
    export_mode: str,
    row_ids: Iterable[object] | None = None,
    entity_code: str = "PL",
) -> tuple[bytes, str]:
    try:
        job = owned_order_logic_v2_job(job_id, client_id)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        latest = latest_order_logic_v2_result(client_id, entity_code)
        if (
            latest is None
            or latest.get("job_id") != job_id
            or latest.get("status") != "success"
            or latest.get("preview") is True
        ):
            raise
        result = latest
    else:
        if job.get("status") != "succeeded":
            raise HTTPException(
                status_code=409,
                detail="완료된 발주 계산만 엑셀로 내보낼 수 있습니다.",
            )
        result = job.get("result")
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=409,
            detail="완료된 발주 계산만 엑셀로 내보낼 수 있습니다.",
        )
    if result.get("result_schema_version") != RESULT_SCHEMA_VERSION:
        raise HTTPException(
            status_code=409,
            detail=(
                "현재 13주/91일 수요기간 계약이 포함되지 않은 이전 분석 결과입니다. "
                "분석 실행을 다시 눌러 새로 계산해 주세요."
            ),
        )
    resolved_entity = str(entity_code).strip().upper()
    result_entity = str(result.get("entity_code") or "").strip().upper()
    if not result_entity or result_entity != resolved_entity:
        raise HTTPException(
            status_code=409,
            detail="선택한 법인과 다른 분석 결과입니다. 현재 법인에서 분석 실행을 다시 해 주세요.",
        )
    resolved_export_mode = _policy_mode(export_mode)
    scenarios = result.get("scenarios")
    scenario = scenarios.get(resolved_export_mode) if isinstance(scenarios, dict) else None
    if not isinstance(scenario, dict):
        raise OrderLogicV2DecisionError(
            f"선택한 시나리오 결과가 없습니다: {resolved_export_mode}"
        )
    if scenario.get("source_snapshot_id") != result.get("source_snapshot_id"):
        raise OrderLogicV2DecisionError(
            "선택한 시나리오가 공식 결과와 동일한 원천 snapshot이 아닙니다."
        )
    scenario_rows = scenario.get("rows")
    scenario_summary = scenario.get("summary")
    if not isinstance(scenario_rows, list) or not isinstance(scenario_summary, dict):
        raise OrderLogicV2DecisionError("선택한 시나리오 결과 형식이 올바르지 않습니다.")
    selected_result = deepcopy(result)
    selected_result["official_applied_mode"] = result.get("applied_mode")
    selected_result["export_mode"] = resolved_export_mode
    selected_result["applied_mode"] = resolved_export_mode
    selected_result["policy_mode"] = resolved_export_mode
    selected_result["rows"] = deepcopy(scenario_rows)
    selected_result["summary"] = deepcopy(scenario_summary)
    export_payload = apply_order_decision_overrides(
        selected_result,
        overrides,
        row_ids=row_ids,
    )
    # Order analysis workbooks are operational outputs. Amounts are visible to
    # ordinary order-analysis accounts even when insight/report amounts are restricted.
    include_amounts = True
    if resolved_entity == "HQ":
        currency_code = HQ_CURRENCY_CODE
    elif resolved_entity == "USA":
        currency_code = "USD"
    else:
        currency_code = "EUR"
    export_payload["currency_code"] = currency_code
    export_payload["exchange_rate_source"] = (
        "BASE_KRW" if currency_code == HQ_CURRENCY_CODE else "CMS_STOCK_DAILY_RATE"
    )
    content = generate_order_logic_v2_excel(
        export_payload,
        include_amounts=include_amounts,
        entity_code=entity_code,
    )
    safe_job_id = re.sub(r"[^A-Za-z0-9._-]+", "_", job_id)[:100]
    safe_entity = re.sub(r"[^A-Za-z0-9_-]+", "_", str(entity_code or "PL").upper())[:16] or "PL"
    return content, f"{safe_entity}_order_logic_v2_{resolved_export_mode.lower()}_{safe_job_id}.xlsx"


__all__ = [
    "LOGIC_VERSION",
    "MAX_SOURCE_AGE_SECONDS",
    "RESULT_SCHEMA_VERSION",
    "OrderLogicV2DecisionError",
    "OrderLogicV2SourceUnavailable",
    "apply_order_decision_overrides",
    "build_order_logic_v2_export",
    "build_order_logic_v2_result",
    "build_hq_order_logic_v2_result",
    "calculate_order_logic_v2_from_cms",
    "calculate_hq_order_logic_v2_from_cms",
    "latest_order_logic_v2_result",
    "owned_order_logic_v2_job",
    "cancel_order_logic_v2_job",
    "payload_visible_to_user",
    "queue_order_logic_v2_job",
    "resolve_order_logic_v2_entity_lead_times",
    "run_order_logic_v2_job",
]
