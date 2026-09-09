"""HQ/OPO source adapter for the order-logic v2 periodic-review calculation.

This module converts the HQ CMS sources into the neutral prepared-source
shape the calculation service consumes.  It only translates source meaning; the
approved formula lives in ``core.order_logic_v2`` and is never recomputed here
(see ``docs/HQ_ORDER_ANALYSIS_HANDOFF.md`` section 7).

Approved contracts implemented here:

- Demand is SKU x calendar day over the previous 91 completed days (RS-024).
- The population is the OPO warehouse of headquarters (HQ-001, HQ-010).
- Rows excluded by the reviewed sales filter (staff sales, free samples,
  returns, deferred offsets, TP adjustments, non-manufacturer accounting rows)
  leave both demand and Pareto revenue.
- ``IP`` is open-PO remainder + confirmed-inbound remainder + OPO available
  stock, three mutually exclusive pipeline stages (RS-008).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
import re
from zoneinfo import ZoneInfo


HQ_TIMEZONE = ZoneInfo("Asia/Seoul")
HQ_ENTITY_CODE = "HQ"
HQ_WAREHOUSE_CODE = "OPO"
HQ_CURRENCY_CODE = "KRW"
COMPLETED_DAY_COUNT = 91

# Reviewed HQ demand population.  The headquarters sales feed reports resolved
# biz-type names, so the allow list is stated positively and the exclusion
# patterns below stay as a second guard.
HQ_ALLOWED_BIZ_TYPES = frozenset(
    {"KR-OVERSEAS", "KR-DOMESTIC", "KR-DOMESTIC 0%"}
)
# Mirrors core.sales.filter_sales_by_biz_type for the HQ feed: staff sales,
# free samples, returns, deferred offsets, transfer-price adjustments and
# non-manufacturer accounting rows are not order demand.
HQ_EXCLUDED_BIZ_PATTERN = re.compile(
    r"STAFF|FREE\s*SAMPLE|SAMPLE|반품|추후상계|TP[\s_-]*ADJUST|ADVANCE[\s_-]*TO"
    r"|기타제조사|커미션|CUM|EXCS",
    re.IGNORECASE,
)

EXCLUDED_ORDER_ITEM_CODES = frozenset({"delivery charge"})


@dataclass(frozen=True, slots=True)
class CompletedDayWindow:
    """The previous 91 completed calendar days, excluding ``as_of`` itself."""

    period_start: date
    period_end: date
    days: tuple[date, ...]


@dataclass(slots=True)
class PreparedHQOrderLogicSource:
    """Immutable HQ snapshot handed to the calculation service."""

    as_of: date
    period_start: date
    period_end: date
    rows: tuple[dict[str, object], ...]
    source_counts: dict[str, int]
    warnings: tuple[str, ...]
    lead_time: dict[str, object]
    source_audit: dict[str, object]


def hq_today() -> date:
    return datetime.now(HQ_TIMEZONE).date()


def completed_day_window(as_of: str | date) -> CompletedDayWindow:
    """Return the 91 completed days before ``as_of``; the current day is out."""

    parsed = (
        datetime.strptime(as_of, "%Y-%m-%d").date()
        if isinstance(as_of, str)
        else as_of
    )
    period_end = parsed - timedelta(days=1)
    period_start = period_end - timedelta(days=COMPLETED_DAY_COUNT - 1)
    return CompletedDayWindow(
        period_start=period_start,
        period_end=period_end,
        days=tuple(
            period_start + timedelta(days=index)
            for index in range(COMPLETED_DAY_COUNT)
        ),
    )


def _clean_text(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _numeric(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
    return number if math.isfinite(number) else None


def _sum_optional_quantity_by_sku(
    rows: Sequence[Mapping[str, object]],
    *,
    sku_field: str,
    quantity_field: str,
    warning_code: str,
) -> tuple[dict[str, float], dict[str, list[str]], set[str]]:
    """Aggregate an optional status quantity without turning absence into zero."""

    if not any(quantity_field in row for row in rows):
        return {}, {}, set()
    return _sum_quantity_by_sku(
        rows,
        sku_field=sku_field,
        quantity_field=quantity_field,
        warning_code=warning_code,
    )


def _parsed_date(value: object) -> date | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _is_excluded_order_item(sku_code: str) -> bool:
    return sku_code.casefold() in EXCLUDED_ORDER_ITEM_CODES


def is_hq_demand_row(row: Mapping[str, object]) -> bool:
    """Return whether one headquarters sales line counts as OPO order demand."""

    if _clean_text(row.get("whouse_nm")).upper() != HQ_WAREHOUSE_CODE:
        return False
    biz_type = _clean_text(row.get("biz_type")).upper()
    if HQ_EXCLUDED_BIZ_PATTERN.search(biz_type):
        return False
    return biz_type in HQ_ALLOWED_BIZ_TYPES


def _validate_raw_source(raw: object) -> None:
    """Fail closed before any mapping fills a missing HQ field with a default."""

    if not isinstance(raw, Mapping):
        raise ValueError("HQ 원천은 객체 형식이어야 합니다.")

    required_list_fields: dict[str, set[str]] = {
        "sales_history": {"prod_cd", "qty", "ship_dt", "whouse_nm", "biz_type"},
        "products": {"prod_cd"},
        "inventory": {"sku", "available_qty", "unit_cost"},
        "open_po": {"sku", "remaining_qty"},
        "inbound_confirmed": {
            "sku",
            "remaining_qty",
            "pnfm_confirmed_qty",
            "inbound_in_progress_qty",
            "completed_qty",
        },
    }
    required_nonempty = {"sales_history", "products", "inventory"}
    for key, fields in required_list_fields.items():
        rows = raw.get(key)
        if not isinstance(rows, list):
            raise ValueError(f"HQ 원천 엔드포인트가 누락되었습니다: {key}")
        if key in required_nonempty and not rows:
            raise ValueError(f"HQ 원천 엔드포인트가 비어 있습니다: {key}")
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise ValueError(f"HQ 원천 행 형식이 올바르지 않습니다: {key}")
            missing = sorted(fields - set(row))
            if missing:
                raise ValueError(
                    f"HQ 원천 {key}[{index}]의 필수 필드가 누락되었습니다: "
                    f"{', '.join(missing)}"
                )
    stats = raw.get("leadtime_stats")
    if not isinstance(stats, Mapping):
        raise ValueError("HQ 리드타임 통계 원천이 누락되었습니다.")
    for field in ("sample_count", "avg_days", "stddev_days"):
        if field not in stats:
            raise ValueError(f"HQ 리드타임 통계에 {field}가 없습니다.")


def resolve_hq_lead_time(stats: Mapping[str, object]) -> dict[str, object]:
    """Validate the measured HQ domestic lead time without any fallback.

    The API derives one PO-to-actual-receipt statistic per warehouse over the
    last 12 months (RS-005, RS-006).  ``STDEV.S`` needs at least two samples, so
    a smaller population blocks the run instead of borrowing another entity's
    value (RS-007).
    """

    sample_count = _numeric(stats.get("sample_count"))
    mean_days = _numeric(stats.get("avg_days"))
    stdev_days = _numeric(stats.get("stddev_days"))
    if sample_count is None or sample_count < 2:
        raise ValueError(
            "HQ 리드타임 유효 표본이 2건 미만이라 표본표준편차를 계산할 수 없습니다."
        )
    if mean_days is None or mean_days <= 0:
        raise ValueError("HQ 평균 리드타임을 확인할 수 없어 계산을 차단했습니다.")
    if stdev_days is None or stdev_days < 0:
        raise ValueError("HQ 리드타임 표준편차를 확인할 수 없어 계산을 차단했습니다.")
    return {
        "entity_code": HQ_ENTITY_CODE,
        "warehouse_code": HQ_WAREHOUSE_CODE,
        "observation_months": 12,
        "sample_size": int(sample_count),
        "mean_days": mean_days,
        "stdev_days": stdev_days,
        "median_days": _numeric(stats.get("median_days")),
        "min_days": _numeric(stats.get("min_days")),
        "max_days": _numeric(stats.get("max_days")),
        "day_type": _clean_text(stats.get("day_type")) or None,
        "partial_shipment_handling": (
            _clean_text(stats.get("partial_shipment_handling")) or None
        ),
        "basis": "PO 생성일 → 실입고일, 실입고 이벤트 단위 동일가중",
    }


def _daily_demand_by_sku(
    sales_rows: Sequence[Mapping[str, object]],
    window: CompletedDayWindow,
) -> tuple[
    dict[str, list[float]],
    dict[str, float],
    dict[str, list[str]],
    set[str],
    dict[str, object],
]:
    day_index = {day: index for index, day in enumerate(window.days)}
    demand: dict[str, list[float]] = {}
    revenue: dict[str, float] = {}
    warnings: dict[str, list[str]] = {}
    invalid: set[str] = set()

    considered = 0
    excluded_warehouse = 0
    excluded_biz_type = 0
    excluded_outside_window = 0
    excluded_biz_distribution: dict[str, int] = {}
    accepted_rows = 0
    accepted_qty = 0.0
    excluded_negative_amount_positive_qty_rows = 0
    excluded_negative_amount_positive_qty = 0.0
    excluded_negative_amount_positive_revenue = 0.0
    excluded_negative_amount_positive_biz_distribution: dict[str, int] = {}

    for row in sales_rows:
        considered += 1
        warehouse = _clean_text(row.get("whouse_nm")).upper()
        if warehouse != HQ_WAREHOUSE_CODE:
            excluded_warehouse += 1
            continue
        biz_type = _clean_text(row.get("biz_type")).upper()
        if not is_hq_demand_row(row):
            excluded_biz_type += 1
            label = biz_type or "(blank)"
            excluded_biz_distribution[label] = (
                excluded_biz_distribution.get(label, 0) + 1
            )
            continue
        ship_date = _parsed_date(row.get("ship_dt"))
        if ship_date is None or ship_date not in day_index:
            excluded_outside_window += 1
            continue

        sku_code = _clean_text(row.get("prod_cd"))
        if not sku_code:
            excluded_outside_window += 1
            continue
        sku_warnings = warnings.setdefault(sku_code, [])

        quantity = _numeric(row.get("qty"))
        if quantity is None:
            quantity = 0.0
            if "SALES_QTY_NULL_AS_ZERO" not in sku_warnings:
                sku_warnings.append("SALES_QTY_NULL_AS_ZERO")

        amount = _numeric(row.get("amount_krw"))
        if amount is None:
            amount = 0.0
            if "SALES_AMOUNT_NULL_AS_ZERO" not in sku_warnings:
                sku_warnings.append("SALES_AMOUNT_NULL_AS_ZERO")

        if amount < 0 and quantity > 0:
            excluded_negative_amount_positive_qty_rows += 1
            excluded_negative_amount_positive_qty += quantity
            excluded_negative_amount_positive_revenue += amount
            excluded_negative_amount_positive_biz_distribution[biz_type] = (
                excluded_negative_amount_positive_biz_distribution.get(biz_type, 0) + 1
            )
            if "NEGATIVE_AMOUNT_POSITIVE_QTY_EXCLUDED" not in sku_warnings:
                sku_warnings.append("NEGATIVE_AMOUNT_POSITIVE_QTY_EXCLUDED")
            continue

        values = demand.setdefault(sku_code, [0.0] * COMPLETED_DAY_COUNT)
        if quantity < 0:
            # The approved HQ contract returns net order demand, so a negative
            # line has no reviewed handling rule and isolates the SKU.
            invalid.add(sku_code)
            if "SALES_QTY_NEGATIVE" not in sku_warnings:
                sku_warnings.append("SALES_QTY_NEGATIVE")
        else:
            values[day_index[ship_date]] += quantity
            accepted_qty += quantity

        revenue[sku_code] = revenue.get(sku_code, 0.0) + amount
        accepted_rows += 1

    for sku_code, amount in list(revenue.items()):
        if amount < 0:
            invalid.add(sku_code)
            warnings.setdefault(sku_code, []).append("SALES_REVENUE_NET_NEGATIVE")
            revenue[sku_code] = 0.0

    if not demand:
        raise ValueError(
            f"최근 {COMPLETED_DAY_COUNT}개 완료일에 해당하는 "
            "OPO 국내 B2B 판매 데이터가 없습니다."
        )

    audit = {
        "sales_rows_considered": considered,
        "sales_rows_accepted": accepted_rows,
        "sales_qty_accepted": accepted_qty,
        "sales_excluded_other_warehouse": excluded_warehouse,
        "sales_excluded_biz_type": excluded_biz_type,
        "sales_excluded_outside_window": excluded_outside_window,
        "sales_excluded_biz_type_distribution": excluded_biz_distribution,
        "sales_allowed_biz_types": sorted(HQ_ALLOWED_BIZ_TYPES),
        "sales_demand_excluded_rows": excluded_negative_amount_positive_qty_rows,
        "sales_demand_excluded_qty": excluded_negative_amount_positive_qty,
        "sales_demand_excluded_amount": excluded_negative_amount_positive_revenue,
        "sales_demand_excluded_biz_type_distribution": excluded_negative_amount_positive_biz_distribution,
    }
    return demand, revenue, warnings, invalid, audit


def _sum_quantity_by_sku(
    rows: Sequence[Mapping[str, object]],
    *,
    sku_field: str,
    quantity_field: str,
    warning_code: str,
) -> tuple[dict[str, float], dict[str, list[str]], set[str]]:
    totals: dict[str, float] = {}
    warnings: dict[str, list[str]] = {}
    invalid: set[str] = set()
    for row in rows:
        sku_code = _clean_text(row.get(sku_field))
        if not sku_code:
            continue
        quantity = _numeric(row.get(quantity_field))
        if quantity is None:
            warnings.setdefault(sku_code, []).append(f"{warning_code}_NULL_AS_ZERO")
            continue
        if quantity < 0:
            invalid.add(sku_code)
            warnings.setdefault(sku_code, []).append(f"{warning_code}_NEGATIVE")
            continue
        totals[sku_code] = totals.get(sku_code, 0.0) + quantity
    return totals, warnings, invalid


def _unit_prices(rows: Sequence[Mapping[str, object]]) -> dict[str, float]:
    """Use the CMS-equivalent OPO unit cost in KRW as the order price.

    ``avg_unit_cost`` is intentionally not used here. It is a current
    positive-cost-lot average and can be null when stock is zero (or when all
    remaining lots are uncosted). The OPO API's ``unit_cost`` is the CMS
    inventory-screen cost intended for order-amount calculation.
    """

    prices: dict[str, float] = {}
    for row in rows:
        sku_code = _clean_text(row.get("sku"))
        if not sku_code or sku_code in prices:
            continue
        price = _numeric(row.get("unit_cost"))
        if price is not None and price >= 0:
            prices[sku_code] = price
    return prices


def _merge_warning_maps(
    target: dict[str, list[str]],
    source: Mapping[str, list[str]],
) -> None:
    for sku_code, messages in source.items():
        target.setdefault(sku_code, []).extend(messages)


def build_hq_order_logic_source(
    raw: Mapping[str, object],
    *,
    as_of: str | date,
) -> PreparedHQOrderLogicSource:
    """Map one raw HQ/OPO snapshot into the neutral prepared-source shape."""

    _validate_raw_source(raw)
    parsed_as_of = (
        datetime.strptime(as_of, "%Y-%m-%d").date()
        if isinstance(as_of, str)
        else as_of
    )
    window = completed_day_window(parsed_as_of)
    lead_time = resolve_hq_lead_time(raw["leadtime_stats"])  # type: ignore[index]

    sales_rows: list[Mapping[str, object]] = list(raw["sales_history"])  # type: ignore[arg-type]
    product_rows: list[Mapping[str, object]] = list(raw["products"])  # type: ignore[arg-type]
    inventory_rows: list[Mapping[str, object]] = list(raw["inventory"])  # type: ignore[arg-type]
    open_po_rows: list[Mapping[str, object]] = list(raw["open_po"])  # type: ignore[arg-type]
    inbound_rows: list[Mapping[str, object]] = list(raw["inbound_confirmed"])  # type: ignore[arg-type]
    inbound_status_skus = {
        _clean_text(row.get("sku") or row.get("prod_cd"))
        for row in (*open_po_rows, *inbound_rows)
        if _clean_text(row.get("sku") or row.get("prod_cd"))
    }

    (
        demand,
        revenue,
        row_warnings,
        invalid_skus,
        sales_audit,
    ) = _daily_demand_by_sku(sales_rows, window)

    # RS-023: HQ uses ①+②+③ as one incoming operand and excludes shipping from
    # IP. ``incoming`` is raw ①; the two confirmed-inbound components are raw
    # ② and ③; ``available`` is already on hand and free of holds.
    incoming, warnings, invalid = _sum_quantity_by_sku(
        open_po_rows,
        sku_field="sku",
        quantity_field="remaining_qty",
        warning_code="INCOMING_QTY",
    )
    _merge_warning_maps(row_warnings, warnings)
    invalid_skus.update(invalid)

    inbound, warnings, invalid = _sum_quantity_by_sku(
        inbound_rows,
        sku_field="sku",
        quantity_field="remaining_qty",
        warning_code="INBOUND_CONFIRMED_QTY",
    )
    _merge_warning_maps(row_warnings, warnings)
    invalid_skus.update(invalid)

    pnfm, warnings, invalid = _sum_optional_quantity_by_sku(
        inbound_rows,
        sku_field="sku",
        quantity_field="pnfm_confirmed_qty",
        warning_code="PNFM_QTY",
    )
    _merge_warning_maps(row_warnings, warnings)
    invalid_skus.update(invalid)

    inbound_progress, warnings, invalid = _sum_optional_quantity_by_sku(
        inbound_rows,
        sku_field="sku",
        quantity_field="inbound_in_progress_qty",
        warning_code="INBOUND_PROGRESS_QTY",
    )
    _merge_warning_maps(row_warnings, warnings)
    invalid_skus.update(invalid)

    completed, warnings, invalid = _sum_optional_quantity_by_sku(
        inbound_rows,
        sku_field="sku",
        quantity_field="completed_qty",
        warning_code="INBOUND_COMPLETED_QTY",
    )
    _merge_warning_maps(row_warnings, warnings)
    invalid_skus.update(invalid)

    available, warnings, invalid = _sum_quantity_by_sku(
        [row for row in inventory_rows if _clean_text(row.get("stock_status")).lower() != "trouble"],
        sku_field="sku",
        quantity_field="available_qty",
        warning_code="OPO_AVAILABLE_QTY",
    )
    _merge_warning_maps(row_warnings, warnings)
    invalid_skus.update(invalid)

    identities: dict[str, tuple[str, str]] = {}
    # Data-deficient SKUs can be present only in inventory/PO/inbound feeds,
    # so sales history cannot be the sole product-master source.
    # The global COSMETIC product master is the authoritative identity source.
    # It enriches only SKUs already present in order sources and must never
    # expand the calculation population by itself.
    for source_rows in (
        product_rows,
        inventory_rows,
        open_po_rows,
        inbound_rows,
        sales_rows,
    ):
        for row in source_rows:
            sku_code = _clean_text(row.get("sku") or row.get("prod_cd"))
            if not sku_code:
                continue
            product_name = _clean_text(
                row.get("prod_nm") or row.get("product_name") or row.get("name")
            )
            brand = _clean_text(row.get("brand_nm") or row.get("brand"))
            previous_name, previous_brand = identities.get(sku_code, ("", ""))
            identities[sku_code] = (
                previous_name or product_name,
                previous_brand or brand,
            )
    prices = _unit_prices(inventory_rows)
    stock_registered = {
        _clean_text(row.get("sku")) for row in inventory_rows if _clean_text(row.get("sku"))
    }

    sku_codes = [
        sku_code
        for sku_code in sorted(
            set(demand) | set(incoming) | set(inbound) | set(available) | set(completed)
        )
        if sku_code and not _is_excluded_order_item(sku_code)
    ]

    rows: list[dict[str, object]] = []
    for sku_code in sku_codes:
        product_name, brand = identities.get(sku_code, ("", ""))
        daily_values = demand.get(sku_code)
        open_qty = incoming.get(sku_code, 0.0)
        pnfm_confirmed_qty = pnfm.get(sku_code, 0.0)
        inbound_progress_qty = inbound_progress.get(sku_code, 0.0)
        calculation_incoming_qty = (
            open_qty + pnfm_confirmed_qty + inbound_progress_qty
        )
        stock_missing = sku_code not in stock_registered
        if stock_missing:
            row_warnings.setdefault(sku_code, []).append("OPO_STOCK_MISSING")
            present_sources = []
            if sku_code in demand:
                present_sources.append("판매내역")
            if sku_code in incoming:
                present_sources.append("미입고 PO")
            if sku_code in inbound:
                present_sources.append("입고확정")
            source_phrase = (
                "·".join(present_sources) + " 내역에는 존재"
                if present_sources
                else "원천 데이터에는 존재"
            )
            check_required_reason = (
                f"오포창고 재고 마스터에 없는 SKU입니다({source_phrase}). "
                "신규 SKU이거나 재고 이력이 없는 상품일 수 있어 확인이 필요합니다."
            )
        else:
            check_required_reason = None

        rows.append(
            {
                "sku_code": sku_code,
                "product_name": product_name,
                "brand": brand,
                "barcode": "",
                # The neutral field name is shared with PL/USA; for HQ it holds
                # 91 completed daily values instead of 13 weekly values.
                "weekly_sales": daily_values,
                # API/Excel 호환 필드명은 유지하지만 HQ 값은 승인된 91일 합계다.
                "sales_13w_qty": float(sum(daily_values or ())),
                "revenue": revenue.get(sku_code, 0.0),
                "inbound_status_source_present": sku_code in inbound_status_skus,
                "open_qty": open_qty,
                "incoming_qty": calculation_incoming_qty,
                "pnfm_qty": pnfm.get(sku_code),
                # HQ/OPO has no shipping operand in IP. ② and ③ are already
                # included once in calculation_incoming_qty.
                "eu_available_qty": 0.0,
                "transit_qty": 0.0,
                "inbound_progress_qty": inbound_progress.get(sku_code),
                "inbound_completed_qty": completed.get(sku_code),
                "local_available_qty": available.get(sku_code, 0.0),
                "shipping_schedule": [],
                "shipping_eta_details": [],
                "eta_actual_qty": 0.0,
                "eta_estimated_qty": 0.0,
                "eta_missing_qty": 0.0,
                "next_eta": None,
                "next_eta_status": None,
                "unit_price_local": prices.get(sku_code),
                "unit_price_krw": prices.get(sku_code),
                "entity_code": "HQ",
                "unit_price_eur": prices.get(sku_code),
                "check_required": stock_missing,
                "check_required_reason": check_required_reason,
                "warnings": sorted(set(row_warnings.get(sku_code, ()))),
                "validation_error": (
                    "음수 판매·매출·재고 값은 기술명세서에 처리 규칙이 없어 계산하지 않습니다."
                    if sku_code in invalid_skus
                    else None
                ),
            }
        )

    source_counts = {
        key: len(value)
        for key, value in raw.items()
        if isinstance(value, list)
    }
    source_counts["demand_skus"] = len(demand)
    source_counts["order_skus"] = len(rows)
    source_counts["identity_missing_skus"] = sum(
        not _clean_text(row.get("product_name"))
        or not _clean_text(row.get("brand"))
        for row in rows
    )

    source_audit: dict[str, object] = {
        "entity_code": HQ_ENTITY_CODE,
        "warehouse_code": HQ_WAREHOUSE_CODE,
        "timezone": str(HQ_TIMEZONE),
        "currency_code": HQ_CURRENCY_CODE,
        "demand_grain": "sku_x_calendar_day",
        "demand_days": COMPLETED_DAY_COUNT,
        "inventory_position_stages": [
            "open_po_open_qty",
            "pnfm_confirmed_qty",
            "inbound_in_progress_qty",
            "opo_available",
        ],
        "inventory_position_exclusions": ["shipping_in_transit", "completed_qty"],
        "product_identity_source": "eu/products?eu_sold_only=false",
        **sales_audit,
    }

    limitations = (
        "HQ 발주 수요는 본사 판매이력에서 오포창고 행만 사용하며, "
        "임직원판매·무상샘플·반품·상계·회계조정 행은 제외한다.",
        "HQ 리드타임은 오포창고 PO 생성일에서 실입고일까지의 최근 12개월 통계이며 "
        "SKU·브랜드별로 나누지 않는다.",
    )

    return PreparedHQOrderLogicSource(
        as_of=parsed_as_of,
        period_start=window.period_start,
        period_end=window.period_end,
        rows=tuple(rows),
        source_counts=source_counts,
        warnings=limitations,
        lead_time=lead_time,
        source_audit=source_audit,
    )


__all__ = [
    "COMPLETED_DAY_COUNT",
    "CompletedDayWindow",
    "HQ_CURRENCY_CODE",
    "HQ_ENTITY_CODE",
    "HQ_TIMEZONE",
    "HQ_WAREHOUSE_CODE",
    "PreparedHQOrderLogicSource",
    "build_hq_order_logic_source",
    "completed_day_window",
    "hq_today",
    "is_hq_demand_row",
    "resolve_hq_lead_time",
]
