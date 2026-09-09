"""V3 web workflow boundary backed by the CMS textbook source adapter."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from contextvars import copy_context
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import partial
from threading import Event
from time import monotonic
from typing import Callable, Mapping, Sequence

from fastapi import HTTPException

from backend.auth.models import UserAccount
from backend.config import (
    IS_PRODUCTION,
    ORDER_LOGIC_V3_ANALYSIS_TIMEOUT_SECONDS,
    V3_LOCAL_WORKER_CONCURRENCY,
    bounded_worker_timeout_seconds,
)
from backend.services import analysis_cancel, persistent_state, task_queue
from backend.services.audit import write_audit_event
from backend.services.task_queue import TaskQueueUnavailable
from backend.services.object_storage import ObjectStorageUnavailable
from backend.services.order_logic_v3_jobs import (
    cancel_order_logic_v3_job_record,
    claim_order_logic_v3_job,
    create_order_logic_v3_job,
    finish_order_logic_v3_job,
    get_order_logic_v3_job,
    update_order_logic_v3_job,
)
from backend.services.order_logic_v3_result_store import store_result
from backend.services.order_logic_v3_source import (
    SOURCE_DATE_BASIS,
    build_order_logic_v3_source,
)
from core.order_logic_v3 import (
    PERIOD_DAYS,
    REQUIRED_COMPLETED_PERIODS,
    CONSTRAINT_STATUS_PACK_ROUNDED,
    INVENTORY_POLICY_CASH,
    INVENTORY_POLICY_SHORTAGE,
    SALES_GRADE_CORE,
    SALES_GRADE_GENERAL,
    SeasonalProfile,
    V3CalculationError,
    V3CandidateParameters,
    V3PolicyRequiredError,
    V3RawOrderResult,
    V3ReplenishmentBaseInput,
    V3TextbookScenarioResult,
    calculate_v3_textbook_scenarios,
    round_v3_order_quantity,
    textbook_candidate_parameters,
)
from core.order_logic_v3_amount import calculate_v3_local_order_amount
from core.order_logic_v3_reference import inventory_reference_metrics, sales_reference_metrics, shipping_reference_metrics


LOGIC_VERSION = "v3.33-usa-inbox-cnt-usa-pack"
RESULT_SCHEMA_VERSION = 25
_RUNNING_TASKS: set[asyncio.Task[None]] = set()
_CANCEL_SIGNALS: dict[str, Event] = {}
_LOCAL_EXECUTION_LIMIT = asyncio.Semaphore(V3_LOCAL_WORKER_CONCURRENCY)
# Cross-worker cancellation refresh, not a calculation parameter.
_CANCEL_CHECK_INTERVAL_SECONDS = 0.25
_CALENDAR_WEEK_DAYS = 7.0

# Approved 2026-09-02 HQ/OPO policy. Values are the standard-normal Z scores
# for the stated service levels; only CASH/GENERAL deliberately uses zero.
_HQ_FIXED_Z_MATRIX = {
    (INVENTORY_POLICY_SHORTAGE, SALES_GRADE_CORE): 0.8416212335729143,
    (INVENTORY_POLICY_SHORTAGE, SALES_GRADE_GENERAL): 0.5244005127080409,
    (INVENTORY_POLICY_CASH, SALES_GRADE_CORE): 0.2533471031357998,
    (INVENTORY_POLICY_CASH, SALES_GRADE_GENERAL): 0.0,
}

# Approved 2026-09-02 PL/USA policy. Values are the standard-normal Z scores
# for service levels 90/80 (SHORTAGE) and 70/60 (CASH).
_PL_USA_FIXED_Z_MATRIX = {
    (INVENTORY_POLICY_SHORTAGE, SALES_GRADE_CORE): 1.2815515655446008,
    (INVENTORY_POLICY_SHORTAGE, SALES_GRADE_GENERAL): 0.8416212335729143,
    (INVENTORY_POLICY_CASH, SALES_GRADE_CORE): 0.5244005127080409,
    (INVENTORY_POLICY_CASH, SALES_GRADE_GENERAL): 0.2533471031357998,
}

_PL_USA_FIXED_Z_ENTITIES = frozenset({"PL", "USA"})


def _z_matrix_for_entity(entity_code: str) -> Mapping[tuple[str, str], float] | None:
    """Return an explicitly approved entity override, never a cross-entity fallback."""

    if entity_code == "HQ":
        return _HQ_FIXED_Z_MATRIX
    if entity_code in _PL_USA_FIXED_Z_ENTITIES:
        return _PL_USA_FIXED_Z_MATRIX
    return None


def _z_policy_audit(entity_code: str) -> dict[str, object]:
    if entity_code in _PL_USA_FIXED_Z_ENTITIES:
        return {
            "policy_version": "PL_USA_FIXED_SERVICE_LEVELS_90_80_70_60",
            "scope": entity_code,
            "override_applied": True,
            "service_levels": {
                "SHORTAGE": {"CORE": 0.90, "GENERAL": 0.80},
                "CASH": {"CORE": 0.70, "GENERAL": 0.60},
            },
            "z_values": {
                "SHORTAGE": {
                    "CORE": 1.2815515655446008,
                    "GENERAL": 0.8416212335729143,
                },
                "CASH": {
                    "CORE": 0.5244005127080409,
                    "GENERAL": 0.2533471031357998,
                },
            },
        }
    if entity_code != "HQ":
        return {
            "policy_version": "TEXTBOOK_Z_MATRIX",
            "scope": entity_code,
            "override_applied": False,
        }
    return {
        "policy_version": "HQ_FIXED_SERVICE_LEVELS_80_70_60_50",
        "scope": "HQ_ONLY",
        "override_applied": True,
        "service_levels": {
            "SHORTAGE": {"CORE": 0.80, "GENERAL": 0.70},
            "CASH": {"CORE": 0.60, "GENERAL": 0.50},
        },
        "z_values": {
            "SHORTAGE": {"CORE": 0.8416212335729143, "GENERAL": 0.5244005127080409},
            "CASH": {"CORE": 0.2533471031357998, "GENERAL": 0.0},
        },
        "zero_z_rule": "CASH/GENERAL Z=0; SS_raw=0, then existing HQ 1-week fence floor applies.",
    }


class _OrderLogicV3JobCancelled(Exception):
    """Cooperative job termination; never a SKU calculation failure."""


@dataclass(frozen=True, slots=True)
class OrderLogicV3SkuCalculationInput:
    """Explicit, source-owned operands for one V3 textbook calculation."""

    sku_code: str
    product_name: str
    brand: str
    daily_sales: Mapping[date, float]
    first_sale_date: date | None
    seasonal_profile: SeasonalProfile
    replenishment: V3ReplenishmentBaseInput
    sales_grade: str
    unit_price_krw: float | None = None
    source_function_class_1_code: str | None = None
    source_function_class_2_code: str | None = None
    season_factor_scope: str = "FUNCTION_CLASS_1_AND_2"
    season_factor_application_reason_code: str | None = None
    season_factor_blocking_reason_code: str | None = None
    season_factor_blocking_message: str | None = None
    season_factor_original_reason_code: str | None = None
    season_factor_original_message: str | None = None
    barcode: str = ""
    # CMS /eu/products inbox_cnt / outbox_cnt; null when unset in the master.
    inbox_quantity: float | None = None
    outbox_quantity: float | None = None
    product_identity_source_codes: Sequence[str] = ()
    product_identity_reason_code: str | None = None
    # Display-only source buckets, independent of forecast/replenishment inputs.
    inventory_breakdown: Mapping[str, float | None] = field(default_factory=dict)
    inbound_status_source_present: bool | None = None
    # V2 inventory errors gate calculation; warnings alone do not alter quantities.
    inventory_validation_error: str | None = None
    inventory_warnings: Sequence[str] = ()
    # Local price values the raw proposal only; never an input to quantity calculation.
    unit_price_local: float | None = None
    shipping_eta_details: Sequence[Mapping[str, object]] | None = None
    shipping_source_status: str = "UNAVAILABLE"
    cash_transport_mode: str | None = None
    shortage_transport_mode: str | None = None

    def __post_init__(self) -> None:
        if not self.sku_code.strip():
            raise ValueError("sku_code is required")


def _last_completed_sunday(as_of: date) -> date:
    """Use the Sunday immediately before the current incomplete week."""

    current_week_monday = as_of - timedelta(days=as_of.weekday())
    return current_week_monday - timedelta(days=1)


def _blocking_contracts() -> list[dict[str, str]]:
    return [
        {
            "code": "SEASON_FACTOR_ARTIFACT_NOT_ACTIVE",
            "area": "시즌팩터",
            "message": (
                "검증을 통과해 자동 활성화된 24개 완료월 시즌팩터 artifact가 필요합니다. "
                "활성 artifact가 없으면 누락 팩터를 1.0으로 대체하지 않습니다."
            ),
        },
        {
            "code": "SALES_GRADE_SOURCE_PENDING",
            "area": "판매등급",
            "message": "Z 행렬은 확정됐지만 SKU별 주력/일반 등급 원천과 판정 규칙이 미확정입니다.",
        },
    ]


def build_order_logic_v3_readiness_result(
    *,
    job_id: str,
    as_of: str,
    entity_code: str,
) -> dict[str, object]:
    """Build the audit-safe web result for the currently approved scope."""

    resolved_entity = str(entity_code or "").strip().upper()
    if resolved_entity not in {"HQ", "PL", "USA"}:
        raise ValueError(f"V3 적용 대상이 아닌 법인입니다: {resolved_entity or '(empty)'}")
    parsed_as_of = date.fromisoformat(as_of)
    period_end = _last_completed_sunday(parsed_as_of)
    period_start = period_end - timedelta(
        days=(REQUIRED_COMPLETED_PERIODS * PERIOD_DAYS) - 1
    )
    blockers = _blocking_contracts()
    return {
        "status": "blocked",
        "job_id": job_id,
        "logic_version": LOGIC_VERSION,
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "preview": True,
        "entity_code": resolved_entity,
        "date_basis": SOURCE_DATE_BASIS,
        "as_of": parsed_as_of.isoformat(),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "period_count": REQUIRED_COMPLETED_PERIODS,
        "period_days": PERIOD_DAYS,
        "duration_unit": "CALENDAR_DAY",
        "observation_window_days": REQUIRED_COMPLETED_PERIODS * PERIOD_DAYS,
        "demand_grain": "WEEK_7D",
        "demand_grain_days": PERIOD_DAYS,
        "source_snapshot_id": None,
        "source_fetched_at": None,
        "order_constraint_status": "ORDER_CONSTRAINTS_PENDING",
        "rows": [],
        "scenarios": {"CASH": {"rows": []}, "SHORTAGE": {"rows": []}},
        "summary": {
            "total_sku_count": 0,
            "calculable_sku_count": 0,
            "blocked_sku_count": 0,
            "raw_order_quantity": 0,
            "final_order_quantity": None,
        },
        "blocking_contracts": blockers,
        "warnings": [item["message"] for item in blockers],
        "analysis_ledger": {
            "business_question": "현재 확정된 V3 계약만으로 법인별 원시 발주 필요량을 재현 가능하게 계산할 수 있는가?",
            "population": (
                "수불 OUT-SALE·OUT-SALE (ONLINE)의 양수 출고수량; "
                "재고조정·이동·입고·반품 등 나머지 수불구분 제외"
            ),
            "period": f"{period_start.isoformat()}~{period_end.isoformat()}, 7일×13 완료주",
            "deduplication": "안정적인 고유키 확정 전 자동 삭제하지 않고 감사만 수행",
            "result": "필수 운영 계약 미확정으로 수량 계산 차단",
        },
    }


def _inventory_warning_messages(codes: Sequence[str]) -> list[str]:
    labels = {
        "INCOMING_QTY": "① 미입고 수량", "PNFM_QTY": "② PNFM확정 수량",
        "INBOUND_PROGRESS_QTY": "③ 입고진행중 수량", "INBOUND_COMPLETED_QTY": "④ 입고완료 수량",
        "INBOUND_CONFIRMED_QTY": "확정 입고 잔량", "EU_AVAILABLE_QTY": "본사 법인창고 가용수량",
        "LOCAL_AVAILABLE_QTY": "현지 가용수량", "OPO_AVAILABLE_QTY": "오포 가용수량",
        "TRANSIT_QTY": "운송중 수량",
    }
    messages = []
    for code in dict.fromkeys(codes):
        if code.endswith("_NULL_AS_ZERO"):
            label = labels.get(code.removesuffix("_NULL_AS_ZERO"), code)
            messages.append(f"{label}이 비어 있어 V2 기준으로 0을 적용했습니다. 원천 수량을 확인하세요.")
        elif code.endswith("_NEGATIVE"):
            label = labels.get(code.removesuffix("_NEGATIVE"), code)
            messages.append(f"{label}에 음수가 있어 V2 기준으로 발주 계산을 차단했습니다.")
        else:
            messages.append(code)
    return messages


def _sku_reason_code(exc: V3CalculationError) -> str:
    message = str(exc).casefold()
    if (
        "all-zero" in message
        or "at least two non-zero" in message
        or "moving average sigma" in message
    ):
        return "DEMAND_HISTORY_INSUFFICIENT"
    if "season" in message or "factor" in message:
        return "SEASON_FACTOR_CALC_FAILED"
    if "holt" in message:
        return "HOLT_POLICY_PENDING"
    if "croston" in message:
        return "CROSTON_POLICY_PENDING"
    return "V3_INPUT_OR_POLICY_INVALID"


def _season_factor_audit_fields(
    source: OrderLogicV3SkuCalculationInput, *, available: bool,
) -> dict[str, object]:
    """Keep the SKU's source classification separate from its factor scope."""

    return {
        "season_factor_available": available,
        "season_factors_by_month": (
            {str(month): float(factor) for month, factor in source.seasonal_profile.factors_by_month.items()}
            if available else None
        ),
        "function_class_1_code": (
            source.source_function_class_1_code
            or source.seasonal_profile.function_class_1_code
        ),
        "function_class_2_code": (
            source.source_function_class_2_code
            or source.seasonal_profile.function_class_2_code
        ),
        "season_factor_scope": source.season_factor_scope,
        "season_factor_application_reason_code": source.season_factor_application_reason_code,
        "season_factor_original_reason_code": source.season_factor_original_reason_code,
        "season_factor_original_message": source.season_factor_original_message,
        "season_factor_function_class_1_code": source.seasonal_profile.function_class_1_code,
        "season_factor_function_class_2_code": source.seasonal_profile.function_class_2_code,
    }


def _calculated_row(
    source: OrderLogicV3SkuCalculationInput,
    result: V3RawOrderResult,
    trace: V3TextbookScenarioResult,
    parameters: V3CandidateParameters,
    inventory_policy: str,
) -> dict[str, object]:
    forecast = result.forecast
    classification = result.classification
    new_sku_status = result.new_sku_status
    replenishment = source.replenishment
    policy = (
        replenishment.cash_policy
        if inventory_policy == INVENTORY_POLICY_CASH
        else replenishment.shortage_policy
    )
    # Approved 2026-09-08 order-unit ladder: outbox pack, then inbox pack,
    # then 10-unit fallback. Zero raw quantity stays zero.
    rounding = round_v3_order_quantity(
        result.raw_order_quantity,
        outbox_quantity=source.outbox_quantity,
        inbox_quantity=source.inbox_quantity,
    )
    return {
        "sku_code": source.sku_code,
        "product_name": source.product_name,
        "brand": source.brand,
        "barcode": source.barcode,
        "calculable": True,
        "reason_code": None,
        "validation_error": None,
        "data_status": "CALCULATED",
        "pattern": classification.pattern,
        "engine": classification.engine,
        "seasonal_applied": True,
        "season_factor_version": source.seasonal_profile.version,
        **_season_factor_audit_fields(source, available=True),
        "seasonal_f1": result.seasonal_factors.f1,
        "seasonal_f2": result.seasonal_factors.f2,
        "seasonal_f_lr": result.seasonal_factors.f_lr,
        "original_period_sales": list(trace.original_period_sales),
        "adjusted_period_sales": list(trace.adjusted_period_sales),
        "adjusted_forecast": [
            forecast.next_period_forecast,
            forecast.second_period_forecast
            if forecast.second_period_forecast is not None
            else forecast.next_period_forecast,
        ],
        "demand_per_period": forecast.demand_per_period,
        "forecast_rmse": forecast.rmse,
        "forecast_sigma": forecast.sigma_per_period,
        "croston_forecast_cap_per_period": forecast.croston_forecast_cap_per_period,
        "croston_forecast_was_capped": forecast.croston_forecast_was_capped,
        "inventory_position": result.inventory_position,
        "reorder_point": result.reorder_point,
        "target_stock": result.target_stock,
        "raw_order_quantity": result.raw_order_quantity,
        "inbox_quantity": source.inbox_quantity,
        "outbox_quantity": source.outbox_quantity,
        "order_unit_quantity": rounding.order_unit_quantity,
        "order_unit_source": rounding.order_unit_source,
        "final_order_quantity": rounding.final_order_quantity,
        "order_amount_krw": (
            rounding.final_order_quantity * source.unit_price_krw
            if source.unit_price_krw is not None
            else None
        ),
        "order_signal": "즉시 발주" if result.need_order else "발주 제외",
        "adi": classification.adi,
        "cv2": classification.cv2,
        "trend_signal": classification.trend_signal,
        "first_sale_date": (
            new_sku_status.first_sale_date.isoformat()
            if new_sku_status is not None
            else None
        ),
        "analysis_sales_cutoff": (
            new_sku_status.analysis_date.isoformat()
            if new_sku_status is not None
            else None
        ),
        "calendar_days_since_first_sale": (
            new_sku_status.elapsed_calendar_days
            if new_sku_status is not None
            else None
        ),
        "is_new_sku": (
            new_sku_status.is_new_sku
            if new_sku_status is not None
            else None
        ),
        "layer1": result.layer1,
        "z_value": result.z_value,
        "z_policy": inventory_policy,
        "layer2_raw": result.layer2_raw,
        "layer2": result.layer2,
        "safety_stock_floor": result.safety_stock_floor,
        "safety_stock_cap": result.safety_stock_cap,
        "layer3": result.layer3,
        "transport_mode": (
            source.cash_transport_mode
            if inventory_policy == INVENTORY_POLICY_CASH
            else source.shortage_transport_mode
        ),
        "lead_time_days": policy.lead_time_days,
        "lead_time_weeks": policy.lead_time_days / _CALENDAR_WEEK_DAYS,
        "lead_time_periods": policy.lead_time_days / PERIOD_DAYS,
        "review_days": policy.review_days,
        "review_weeks": policy.review_days / _CALENDAR_WEEK_DAYS,
        "review_periods": policy.review_days / PERIOD_DAYS,
        "sigma_lead_time_periods": policy.sigma_lead_time_periods,
        "sigma_lead_time_days": policy.sigma_lead_time_periods * PERIOD_DAYS,
        "sigma_lead_time_weeks": (
            policy.sigma_lead_time_periods * PERIOD_DAYS / _CALENDAR_WEEK_DAYS
        ),
        "safety_stock_floor_periods": policy.safety_stock_floor_periods,
        "safety_stock_floor_days": policy.safety_stock_floor_periods * PERIOD_DAYS,
        "safety_stock_floor_weeks": (
            policy.safety_stock_floor_periods * PERIOD_DAYS / _CALENDAR_WEEK_DAYS
        ),
        "safety_stock_cap_periods": policy.safety_stock_cap_periods,
        "safety_stock_cap_days": policy.safety_stock_cap_periods * PERIOD_DAYS,
        "safety_stock_cap_weeks": (
            policy.safety_stock_cap_periods * PERIOD_DAYS / _CALENDAR_WEEK_DAYS
        ),
        "on_hand_qty": replenishment.on_hand_qty,
        "upstream_available_qty": replenishment.upstream_available_qty,
        "in_transit_qty": replenishment.in_transit_qty,
        "unreceived_qty": replenishment.unreceived_qty,
        "holding_qty": replenishment.holding_qty,
        # Moving-average rows use a plain mean, so no smoothing coefficient
        # applies; SES/HOLT/Croston keep the approved alpha.
        "alpha": None if classification.engine == "MOVING_AVERAGE" else parameters.alpha,
        "beta": parameters.beta if classification.engine == "HOLT_DAMPED" else None,
        "phi": forecast.damping_phi,
    }


def _blocked_row(
    source: OrderLogicV3SkuCalculationInput,
    *,
    reason_code: str,
    message: str,
) -> dict[str, object]:
    return {
        "sku_code": source.sku_code,
        "product_name": source.product_name,
        "brand": source.brand,
        "barcode": source.barcode,
        "calculable": False,
        "reason_code": reason_code,
        "validation_error": message,
        "data_status": "BLOCKED",
        "pattern": None,
        "engine": None,
        "seasonal_applied": False,
        "season_factor_version": (
            None
            if reason_code.startswith("SEASON_FACTOR_ARTIFACT_") or reason_code == "SEASON_FACTOR_SOURCE_MISMATCH"
            else source.seasonal_profile.version
        ),
        **_season_factor_audit_fields(
            source,
            available=not reason_code.startswith("SEASON_FACTOR_")
            and not source.season_factor_blocking_reason_code,
        ),
        "original_period_sales": [],
        "adjusted_period_sales": [],
        "croston_forecast_cap_per_period": None,
        "croston_forecast_was_capped": None,
        "raw_order_quantity": None,
        "inbox_quantity": source.inbox_quantity,
        "outbox_quantity": source.outbox_quantity,
        "order_unit_quantity": None,
        "order_unit_source": None,
        "order_amount_krw": None,
        "final_order_quantity": None,
        "order_signal": "계산 차단",
    }


def _blocked_scenario_rows(
    source: OrderLogicV3SkuCalculationInput,
    *,
    reason_code: str,
    message: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Attach each selected scenario's supply mode without changing the block reason."""

    base = _blocked_row(source, reason_code=reason_code, message=message)
    cash = {**deepcopy(base), "transport_mode": source.cash_transport_mode}
    shortage = {**base, "transport_mode": source.shortage_transport_mode}
    return cash, shortage


def build_order_logic_v3_calculation_result(
    *,
    job_id: str,
    as_of: str,
    entity_code: str,
    parameters: V3CandidateParameters,
    sku_inputs: Sequence[OrderLogicV3SkuCalculationInput],
    source_snapshot_id: str,
    source_fetched_at: str,
    check_cancelled: Callable[[], None] | None = None,
) -> dict[str, object]:
    """Calculate supplied, validated SKU inputs through the textbook engine.

    Source adapters must build the explicit input contract first.  This
    function never substitutes missing factors, lead time, grade or inventory
    components and keeps policy errors visible on their SKU rows.
    """

    resolved_entity = str(entity_code or "").strip().upper()
    if resolved_entity not in {"HQ", "PL", "USA"}:
        raise ValueError(f"V3 적용 대상이 아닌 법인입니다: {resolved_entity or '(empty)'}")
    if not source_snapshot_id.strip() or not source_fetched_at.strip():
        raise ValueError("source snapshot metadata is required")
    parsed_as_of = date.fromisoformat(as_of)
    period_end = _last_completed_sunday(parsed_as_of)
    period_start = period_end - timedelta(
        days=(REQUIRED_COMPLETED_PERIODS * PERIOD_DAYS) - 1
    )
    z_matrix = _z_matrix_for_entity(resolved_entity)
    z_policy = _z_policy_audit(resolved_entity)
    shortage_rows: list[dict[str, object]] = []
    cash_rows: list[dict[str, object]] = []
    warnings: list[str] = []
    for source in sku_inputs:
        if check_cancelled is not None:
            check_cancelled()
        warnings.extend(
            f"{source.sku_code}: {message}"
            for message in _inventory_warning_messages(source.inventory_warnings)
        )
        if source.inventory_validation_error:
            message = source.inventory_validation_error
            cash_blocked, shortage_blocked = _blocked_scenario_rows(
                source, reason_code="V2_INVENTORY_INVALID", message=message,
            )
            shortage_rows.append(shortage_blocked)
            cash_rows.append(cash_blocked)
            warnings.append(f"{source.sku_code}: {message}")
            continue
        if source.season_factor_blocking_reason_code:
            message = source.season_factor_blocking_message or "시즌팩터 적용 조건을 충족하지 못했습니다."
            cash_blocked, shortage_blocked = _blocked_scenario_rows(
                source,
                reason_code=source.season_factor_blocking_reason_code,
                message=message,
            )
            shortage_rows.append(shortage_blocked)
            cash_rows.append(cash_blocked)
            warnings.append(f"{source.sku_code}: {message}")
            continue
        if source.seasonal_profile.entity_code.strip().upper() != resolved_entity:
            message = "해당 법인의 승인 시즌팩터가 아닙니다. 타 법인 팩터로 대체하지 않습니다."
            cash_blocked, shortage_blocked = _blocked_scenario_rows(
                source,
                reason_code="SEASON_FACTOR_ENTITY_MISMATCH",
                message=message,
            )
            shortage_rows.append(shortage_blocked)
            cash_rows.append(cash_blocked)
            warnings.append(f"{source.sku_code}: {message}")
            continue
        try:
            trace = calculate_v3_textbook_scenarios(
                source.daily_sales,
                first_sale_date=source.first_sale_date,
                profile=source.seasonal_profile,
                last_completed_sunday=period_end,
                parameters=parameters,
                replenishment=source.replenishment,
                sales_grade=source.sales_grade,
                z_matrix=z_matrix,
            )
        except (V3PolicyRequiredError, V3CalculationError) as exc:
            message = str(exc)
            cash_blocked, shortage_blocked = _blocked_scenario_rows(
                source,
                reason_code=_sku_reason_code(exc),
                message=message,
            )
            shortage_rows.append(shortage_blocked)
            cash_rows.append(cash_blocked)
            warnings.append(f"{source.sku_code}: {message}")
            continue
        shortage_rows.append(
            _calculated_row(
                source,
                trace.shortage,
                trace,
                parameters,
                INVENTORY_POLICY_SHORTAGE,
            )
        )
        cash_rows.append(
            _calculated_row(
                source,
                trace.cash,
                trace,
                parameters,
                INVENTORY_POLICY_CASH,
            )
        )

    if check_cancelled is not None:
        check_cancelled()
    # One reference window per source SKU, shared across both scenarios and
    # retained on blocked rows. Never feed these averages back into V3.
    empty_sales_references: dict[str, object] | None = None
    for source, cash_row, shortage_row in zip(sku_inputs, cash_rows, shortage_rows, strict=True):
        if check_cancelled is not None:
            check_cancelled()
        if source.daily_sales:
            sales_references = sales_reference_metrics(source.daily_sales, completed_sales_cutoff=period_end)
        else:
            # Thousands of no-sales SKUs have exactly the same reference
            # calendar/zero history. Reuse the approved function's result,
            # giving each SKU its own mutable list (no formula or fallback).
            if empty_sales_references is None:
                empty_sales_references = sales_reference_metrics({}, completed_sales_cutoff=period_end)
            sales_references = deepcopy(empty_sales_references)
        references = {
            "inventory_validation_error": source.inventory_validation_error,
            "inventory_warnings": list(dict.fromkeys(source.inventory_warnings)),
            "inventory_warning_messages": _inventory_warning_messages(source.inventory_warnings),
            "product_identity_source_codes": list(source.product_identity_source_codes or (source.sku_code,)),
            "product_identity_reason_code": source.product_identity_reason_code,
            **sales_references,
            **shipping_reference_metrics(
                source.shipping_eta_details, as_of=parsed_as_of,
                source_status=source.shipping_source_status,
                in_transit_qty=source.replenishment.in_transit_qty,
            ),
            "unit_price_krw": source.unit_price_krw,
            "unit_price_local": source.unit_price_local,
            "local_currency": {"PL": "EUR", "USA": "USD", "HQ": "KRW"}[resolved_entity],
            "inbound_status_source_present": source.inbound_status_source_present,
            **{key: source.inventory_breakdown.get(key) for key in (
                "open_po_qty", "pnfm_qty", "inbound_progress_qty", "inbound_completed_qty",
            )},
            "on_hand_qty": source.replenishment.on_hand_qty,
            "upstream_available_qty": source.replenishment.upstream_available_qty,
            "in_transit_qty": source.replenishment.in_transit_qty,
            "unreceived_qty": source.replenishment.unreceived_qty,
            "holding_qty": source.replenishment.holding_qty,
        }
        for row in (cash_row, shortage_row):
            row.update(references)
            row["order_amount_local"] = (
                row["order_amount_krw"] if resolved_entity == "HQ"
                else calculate_v3_local_order_amount(row["final_order_quantity"], source.unit_price_local)
            )
            row.update(inventory_reference_metrics(row, as_of=parsed_as_of))
    calculable_count = sum(row["calculable"] is True for row in shortage_rows)
    raw_order_quantity = sum(
        float(row["raw_order_quantity"] or 0)
        for row in shortage_rows
        if row["calculable"] is True
    )
    final_order_quantity = sum(
        float(row["final_order_quantity"] or 0)
        for row in shortage_rows
        if row["calculable"] is True
    )
    factor_versions = sorted(
        {
            str(row["season_factor_version"])
            for row in shortage_rows
            if row.get("calculable") is True and row.get("season_factor_version")
        }
    )
    return {
        "status": "success" if calculable_count else "blocked",
        "job_id": job_id,
        "logic_version": parameters.calculation_logic_version,
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "preview": True,
        "entity_code": resolved_entity,
        "date_basis": SOURCE_DATE_BASIS,
        "as_of": parsed_as_of.isoformat(),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "period_count": REQUIRED_COMPLETED_PERIODS,
        "period_days": PERIOD_DAYS,
        "duration_unit": "CALENDAR_DAY",
        "observation_window_days": REQUIRED_COMPLETED_PERIODS * PERIOD_DAYS,
        "demand_grain": "WEEK_7D",
        "demand_grain_days": PERIOD_DAYS,
        "source_snapshot_id": source_snapshot_id,
        "source_fetched_at": source_fetched_at,
        "season_factor_versions": factor_versions,
        "calculation_parameters": parameters.as_dict(),
        "z_policy": z_policy,
        "order_constraint_status": CONSTRAINT_STATUS_PACK_ROUNDED,
        "order_unit_policy": {
            "ladder": ["OUTBOX", "INBOX", "FALLBACK_10"],
            "source_api": "GET /api/v1/eu/products (outbox_cnt; inbox_cnt, USA: inbox_cnt_usa)",
            # 2026-09-08 user decision: USA uses inbox_cnt_usa only; a missing
            # USA pack falls to the 10-unit step, never to shared inbox_cnt.
            "inbox_source_field": "inbox_cnt_usa" if resolved_entity == "USA" else "inbox_cnt",
            "fallback_unit": 10,
            "zero_raw_stays_zero": True,
        },
        "rows": shortage_rows,
        "scenarios": {
            "CASH": {"rows": cash_rows},
            "SHORTAGE": {"rows": shortage_rows},
        },
        "summary": {
            "total_sku_count": len(shortage_rows),
            "calculable_sku_count": calculable_count,
            "blocked_sku_count": len(shortage_rows) - calculable_count,
            "raw_order_quantity": raw_order_quantity,
            "final_order_quantity": final_order_quantity,
        },
        "blocking_contracts": [],
        "warnings": warnings,
        "analysis_ledger": {
            "business_question": "승인된 명시 입력으로 교과서 V3 원시 필요량을 재현 가능하게 계산할 수 있는가?",
            "population": f"입력 SKU {len(shortage_rows)}건; 계산 가능 {calculable_count}건",
            "period": f"{period_start.isoformat()}~{period_end.isoformat()}, 7일×13 완료주",
            "source_snapshot_id": source_snapshot_id,
            "season_factor_versions": factor_versions,
            "formula": (
                "일별 계절 제거→13주 분류→SES/HOLT/Croston, 창 내 판매 13주 미만은 이동평균→미래 계절 재적용→"
                "L1+L2+L3→S; 순수 정기보충 Q_raw=max(0,S-IP), ROP는 참고값; "
                "최종수량=Q_raw>0일 때 아웃박스→인박스→10단위 올림"
            ),
            "result": "최종 주문수량은 박스 올림(아웃박스→인박스→10단위)만 적용한 값이며 MOQ·팔레트 제약은 미적용",
        },
    }


async def _run_v3_thread(cancel_signal: Event, function: Callable, **kwargs):
    """Keep admission reserved until an interrupted thread has really exited."""
    context = copy_context()
    worker = asyncio.get_running_loop().run_in_executor(
        None, partial(context.run, function, **kwargs),
    )
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancel_signal.set()
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not worker.cancelled():
            worker.exception()  # Consume a late failure without leaking source data.
        raise


async def _fail_v3_job_on_timeout(
    job_id: str,
    client_id: str,
    cancel_signal: Event,
    timeout_seconds: float,
) -> None:
    """Publish a terminal timeout while an uninterruptible source thread exits."""

    await asyncio.sleep(timeout_seconds)
    changed = finish_order_logic_v3_job(
        job_id,
        status="failed",
        status_code=504,
        error=f"V3 analysis exceeded {timeout_seconds:g} seconds.",
    )
    if not changed:
        return
    cancel_signal.set()
    analysis_cancel.cancel(job_id)
    write_audit_event(
        "order_logic_v3_job_failed",
        None,
        job_id=job_id,
        client_id=client_id,
        error_type="timeout",
        duration_seconds=timeout_seconds,
    )


async def run_order_logic_v3_job(
    job_id: str,
    client_id: str,
    request_body: Mapping[str, object],
) -> None:
    if not claim_order_logic_v3_job(job_id):
        return
    cancel_signal = Event()
    _CANCEL_SIGNALS[job_id] = cancel_signal
    analysis_cancel.register(job_id)
    timeout_seconds = bounded_worker_timeout_seconds(
        ORDER_LOGIC_V3_ANALYSIS_TIMEOUT_SECONDS
    )
    timeout_task = asyncio.create_task(
        _fail_v3_job_on_timeout(
            job_id,
            client_id,
            cancel_signal,
            timeout_seconds,
        ),
        name=f"order-logic-v3-timeout:{job_id}",
    )
    last_cancel_check = float("-inf")

    def check_cancelled(*, force: bool = False) -> None:
        nonlocal last_cancel_check
        now = monotonic()
        if force or now - last_cancel_check >= _CANCEL_CHECK_INTERVAL_SECONDS:
            last_cancel_check = now
            if (get_order_logic_v3_job(job_id) or {}).get("status") == "cancelled":
                cancel_signal.set()
        if cancel_signal.is_set():
            analysis_cancel.cancel(job_id)
            raise _OrderLogicV3JobCancelled()

    stage_started = monotonic()
    stage = "source"
    performance: dict[str, float] = {}
    try:
        check_cancelled(force=True)
        source_rows, source_meta = await _run_v3_thread(
            cancel_signal,
            build_order_logic_v3_source,
            as_of=str(request_body.get("as_of") or ""),
            entity_code=str(request_body.get("entity_code") or ""),
            force_refresh=bool(request_body.get("force_refresh", False)),
        )
        performance["source"] = round(monotonic() - stage_started, 3)
        print(f"[perf][order_logic_v3] stage=source_ready seconds={performance['source']} skus={len(source_rows)}", flush=True)
        check_cancelled(force=True)
        stage_started = monotonic()
        stage = "input_conversion"
        sku_inputs = [
            OrderLogicV3SkuCalculationInput(
                sku_code=str(row["sku_code"]),
                product_name=str(row.get("product_name") or ""),
                brand=str(row.get("brand") or ""),
                barcode=str(row.get("barcode") or ""),
                inbox_quantity=(
                    float(row["inbox_quantity"])
                    if row.get("inbox_quantity") is not None else None
                ),
                outbox_quantity=(
                    float(row["outbox_quantity"])
                    if row.get("outbox_quantity") is not None else None
                ),
                product_identity_source_codes=row.get("product_identity_source_codes") or (),
                product_identity_reason_code=row.get("product_identity_reason_code"),
                daily_sales=row["daily_sales"],  # type: ignore[arg-type]
                first_sale_date=row.get("first_sale_date"),  # type: ignore[arg-type]
                seasonal_profile=row["seasonal_profile"],  # type: ignore[arg-type]
                replenishment=row["replenishment"],  # type: ignore[arg-type]
                sales_grade=str(row["sales_grade"]),
                unit_price_krw=(
                    float(row["unit_price_krw"])
                    if row.get("unit_price_krw") is not None
                    else None
                ),
                unit_price_local=row.get("unit_price_local"),
                inventory_breakdown=row.get("inventory_breakdown") or {},
                inbound_status_source_present=row.get("inbound_status_source_present"),
                inventory_validation_error=row.get("inventory_validation_error"),
                inventory_warnings=tuple(row.get("inventory_warnings") or ()),
                shipping_eta_details=row.get("shipping_eta_details"),
                shipping_source_status=str(row.get("shipping_source_status") or "UNAVAILABLE"),
                cash_transport_mode=(
                    str(row["cash_transport_mode"])
                    if row.get("cash_transport_mode") is not None else None
                ),
                shortage_transport_mode=(
                    str(row["shortage_transport_mode"])
                    if row.get("shortage_transport_mode") is not None else None
                ),
                source_function_class_1_code=(
                    str(row["source_function_class_1_code"])
                    if row.get("source_function_class_1_code") is not None
                    else None
                ),
                source_function_class_2_code=(
                    str(row["source_function_class_2_code"])
                    if row.get("source_function_class_2_code") is not None
                    else None
                ),
                season_factor_scope=str(
                    row.get("season_factor_scope") or "FUNCTION_CLASS_1_AND_2"
                ),
                season_factor_application_reason_code=(
                    str(row["season_factor_application_reason_code"])
                    if row.get("season_factor_application_reason_code") is not None
                    else None
                ),
                season_factor_blocking_reason_code=(
                    str(row["season_factor_blocking_reason_code"])
                    if row.get("season_factor_blocking_reason_code") is not None
                    else None
                ),
                season_factor_original_reason_code=row.get("season_factor_original_reason_code"),
                season_factor_original_message=row.get("season_factor_original_message"),
                season_factor_blocking_message=(
                    str(row["season_factor_blocking_message"])
                    if row.get("season_factor_blocking_message") is not None
                    else None
                ),
            )
            for row in source_rows
        ]
        parameters = textbook_candidate_parameters(logic_version=LOGIC_VERSION)
        performance["input_conversion"] = round(monotonic() - stage_started, 3)
        stage_started = monotonic()
        stage = "calculation"
        # Keep the event loop responsive to stop requests during CPU-heavy runs.
        result = await _run_v3_thread(
            cancel_signal,
            build_order_logic_v3_calculation_result,
            job_id=job_id,
            as_of=str(request_body.get("as_of") or ""),
            entity_code=str(request_body.get("entity_code") or ""),
            parameters=parameters,
            sku_inputs=sku_inputs,
            source_snapshot_id=str(source_meta["snapshot_id"]),
            source_fetched_at=str(source_meta["fetched_at"]),
            check_cancelled=check_cancelled,
        )
        performance["calculation"] = round(monotonic() - stage_started, 3)
        print(f"[perf][order_logic_v3] stage=calculation_ready seconds={performance['calculation']} skus={len(sku_inputs)}", flush=True)
        check_cancelled(force=True)
        result["source_audit"] = source_meta
        result["calculation_parameters"] = parameters.as_dict()
        result["performance_seconds"] = performance
        stage = "result_storage"
        stored_result = await _run_v3_thread(
            cancel_signal,
            store_result,
            job_id=job_id,
            result=result,
        )
        check_cancelled(force=True)
        if not finish_order_logic_v3_job(
            job_id, status="succeeded", status_code=200, result=stored_result,
        ):
            return
    except (_OrderLogicV3JobCancelled, analysis_cancel.AnalysisCancelled):
        return
    except asyncio.CancelledError:
        cancel_order_logic_v3_job_record(job_id)
        raise
    except MemoryError:
        if not finish_order_logic_v3_job(
            job_id,
            status="failed",
            status_code=503,
            error="서버 메모리가 부족하여 V3 분석을 완료하지 못했습니다. 메모리 사용량을 줄인 뒤 다시 실행해 주세요.",
        ):
            return
        write_audit_event(
            "order_logic_v3_job_failed", None, job_id=job_id,
            client_id=client_id, error_type="MemoryError", stage=stage,
        )
        return
    except ObjectStorageUnavailable as exc:
        if not finish_order_logic_v3_job(
            job_id,
            status="failed",
            status_code=503,
            error="V3 분석 결과 저장소에 연결하지 못했습니다. 잠시 후 다시 실행해 주세요.",
        ):
            return
        write_audit_event(
            "order_logic_v3_job_failed", None, job_id=job_id,
            client_id=client_id, error_type=type(exc).__name__, stage=stage,
        )
        return
    except (TypeError, ValueError) as exc:
        finish_order_logic_v3_job(
            job_id,
            status="failed",
            status_code=422,
            error=str(exc),
        )
        return
    except Exception as exc:  # noqa: BLE001 - background task must terminate
        if not finish_order_logic_v3_job(
            job_id,
            status="failed",
            status_code=500,
            error="V3 CMS 원천 조회 또는 계산 중 서버 오류가 발생했습니다.",
        ):
            return
        write_audit_event(
            "order_logic_v3_job_failed",
            None,
            job_id=job_id,
            client_id=client_id,
            error_type=type(exc).__name__,
            stage=stage,
        )
        return
    finally:
        timeout_task.cancel()
        with suppress(asyncio.CancelledError):
            await timeout_task
        analysis_cancel.unregister(job_id)
        _CANCEL_SIGNALS.pop(job_id, None)
    if (get_order_logic_v3_job(job_id) or {}).get("status") != "succeeded":
        return
    write_audit_event(
        "order_logic_v3_job_succeeded",
        None,
        job_id=job_id,
        client_id=client_id,
        entity_code=result["entity_code"],
        result_status=result["status"],
        blocker_count=len(result["blocking_contracts"]),
    )


async def _run_local_order_logic_v3_job(
    job_id: str,
    client_id: str,
    request_body: Mapping[str, object],
) -> None:
    """Bound the development fallback while preserving FIFO-style waiting.

    Production publishes to Celery and scales with isolated worker processes.
    The in-process fallback deliberately keeps a small configurable limit so a
    developer laptop accepts concurrent users without starting unbounded
    memory-heavy V3 calculations.
    """
    async with _LOCAL_EXECUTION_LIMIT:
        await run_order_logic_v3_job(job_id, client_id, request_body)


def queue_order_logic_v3_job(
    client_id: str,
    request_body: Mapping[str, object],
) -> str:
    """Accept every valid request, then dispatch it to durable or local workers."""
    if IS_PRODUCTION and not task_queue.enabled():
        raise HTTPException(
            status_code=503,
            detail="운영 V3 분석 대기열이 설정되지 않았습니다. 관리자에게 문의해 주세요.",
        )
    payload = dict(request_body)
    job_id = create_order_logic_v3_job(client_id, payload)

    if task_queue.enabled():
        if not persistent_state.enabled():
            update_order_logic_v3_job(
                job_id, status="failed", status_code=503,
                error="분산 작업 저장소가 설정되지 않아 V3 분석을 시작하지 못했습니다.",
            )
            raise HTTPException(
                status_code=503,
                detail="V3 작업 저장소 설정을 확인해 주세요.",
            )
        try:
            task_queue.enqueue_order_logic_v3(job_id, payload, client_id)
        except TaskQueueUnavailable as exc:
            update_order_logic_v3_job(
                job_id, status="failed", status_code=503,
                error="V3 분석 대기열에 연결하지 못했습니다. 잠시 후 다시 실행해 주세요.",
            )
            raise HTTPException(
                status_code=503,
                detail="V3 분석 대기열에 연결하지 못했습니다. 잠시 후 다시 실행해 주세요.",
            ) from exc
        return job_id

    # Development fallback: accept immediately and wait behind the bounded
    # local semaphore instead of rejecting another browser with HTTP 409.
    coroutine = _run_local_order_logic_v3_job(job_id, client_id, payload)
    try:
        task = asyncio.create_task(coroutine, name=f"order-logic-v3:{job_id}")
    except BaseException:
        coroutine.close()
        update_order_logic_v3_job(
            job_id, status="failed", status_code=500,
            error="V3 분석 작업을 시작하지 못했습니다. 다시 실행해 주세요.",
        )
        raise

    def finished(completed: asyncio.Task[None]) -> None:
        _RUNNING_TASKS.discard(completed)
        if completed.cancelled():
            cancel_order_logic_v3_job_record(job_id)

    _RUNNING_TASKS.add(task)
    task.add_done_callback(finished)
    return job_id


def owned_order_logic_v3_job(job_id: str, client_id: str) -> dict[str, object]:
    job = get_order_logic_v3_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="V3 계산 작업을 찾을 수 없습니다.")
    if job.get("client_id") != client_id:
        raise HTTPException(status_code=403, detail="다른 사용자의 V3 계산 작업에는 접근할 수 없습니다.")
    return deepcopy(job)


def cancel_order_logic_v3_job(
    job_id: str, client_id: str, entity_code: str,
) -> dict[str, object]:
    job = owned_order_logic_v3_job(job_id, client_id)
    options = job.get("analysis_options") or {}
    if not isinstance(options, dict) or options.get("entity_code") != entity_code:
        raise HTTPException(status_code=403, detail="다른 법인의 V3 계산 작업은 중단할 수 없습니다.")
    cancelled = cancel_order_logic_v3_job_record(job_id)
    if cancelled is None:
        raise HTTPException(status_code=404, detail="V3 계산 작업을 찾을 수 없습니다.")
    if cancelled.get("status") == "cancelled":
        analysis_cancel.cancel(job_id)
        signal = _CANCEL_SIGNALS.get(job_id)
        if signal is not None:
            signal.set()
        if task_queue.enabled():
            try:
                task_queue.cancel_order_logic_v3(job_id)
            except TaskQueueUnavailable:
                # The database cancellation flag is authoritative. A worker
                # that later receives the message exits before fetching CMS.
                pass
    return deepcopy(cancelled)


def payload_visible_to_user(
    payload: Mapping[str, object],
    user: UserAccount,
    *,
    already_isolated: bool = False,
) -> dict[str, object]:
    # The order-analysis workspace is the approved exception to the global
    # insight/report amount restriction, matching V2. Authentication, entity
    # authorization and job ownership are enforced by the router before this
    # function is called. Keep the argument in the signature for that boundary
    # and avoid copying a completed paged result twice on the status route.
    _ = user
    return dict(payload) if already_isolated else deepcopy(dict(payload))


__all__ = [
    "LOGIC_VERSION",
    "OrderLogicV3SkuCalculationInput",
    "RESULT_SCHEMA_VERSION",
    "build_order_logic_v3_calculation_result",
    "build_order_logic_v3_readiness_result",
    "cancel_order_logic_v3_job",
    "owned_order_logic_v3_job",
    "payload_visible_to_user",
    "queue_order_logic_v3_job",
]
