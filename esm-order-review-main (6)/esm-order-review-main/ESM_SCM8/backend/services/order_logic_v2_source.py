"""Prepare the CMS source data consumed by the BETA order-logic engine.

This module deliberately stops at a small, JSON-friendly input contract.  The
calculation formula lives in ``core.order_logic_v2`` so source mapping changes
cannot silently change the approved policy mathematics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from backend.cms_mapping import build_uploaded_data_from_cms
from core.order_logic_v2 import DEFAULT_CONFIG, OrderLogicConfig
from core.sales import (
    filter_sales_by_biz_type,
    negative_amount_positive_qty_mask,
)
from core.transport import normalize_transport_code


WARSAW_TIMEZONE = ZoneInfo("Europe/Warsaw")
COMPLETED_WEEK_COUNT = 13
PL_SHIPPING_CUSTOMER_NAME = "SKO Sp. z o.o."
EXCLUDED_ORDER_ITEM_CODES = frozenset({"delivery charge"})


@dataclass(frozen=True, slots=True)
class CompletedWeekWindow:
    period_start: date
    period_end: date
    week_starts: tuple[date, ...]


@dataclass(frozen=True, slots=True)
class PreparedOrderLogicSource:
    period_start: date
    period_end: date
    rows: tuple[dict[str, object], ...]
    source_counts: dict[str, int]
    warnings: tuple[str, ...]
    source_audit: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class PreparedInventoryPositionSource:
    """The V2-approved PL/USA inventory-position operands, without demand/ETA work."""

    rows: tuple[dict[str, object], ...]
    source_counts: dict[str, int]


@dataclass(slots=True)
class _InventoryPositionComponents:
    source_raw: dict[str, list[dict[str, object]]]
    local_stock: pd.DataFrame
    hq_stock: pd.DataFrame
    sales: pd.DataFrame
    shipping: pd.DataFrame
    open_po: pd.DataFrame
    inbound_status_skus: set[str]
    incoming: dict[str, float]
    pnfm: dict[str, float]
    inbound_progress: dict[str, float]
    completed: dict[str, float]
    eu_available: dict[str, float]
    transit: dict[str, float]
    local_available: dict[str, float]
    identities: dict[str, tuple[str, str]]
    barcodes: dict[str, str]
    prices: dict[str, float | None]
    prices_krw: dict[str, float | None]
    warnings: dict[str, list[str]]
    invalid_skus: set[str]


@dataclass(slots=True)
class _ShippingEtaSummary:
    schedules: dict[str, list[dict[str, object]]]
    details: dict[str, list[dict[str, object]]]
    actual_qty: dict[str, float]
    estimated_qty: dict[str, float]
    review_qty: dict[str, float]


def warsaw_today() -> date:
    return datetime.now(WARSAW_TIMEZONE).date()


def completed_week_window(as_of: str | date) -> CompletedWeekWindow:
    """Return the previous 13 Monday-Sunday weeks, excluding the current week."""

    parsed = (
        datetime.strptime(as_of, "%Y-%m-%d").date()
        if isinstance(as_of, str)
        else as_of
    )
    current_week_start = parsed - timedelta(days=parsed.weekday())
    period_start = current_week_start - timedelta(weeks=COMPLETED_WEEK_COUNT)
    period_end = current_week_start - timedelta(days=1)
    return CompletedWeekWindow(
        period_start=period_start,
        period_end=period_end,
        week_starts=tuple(
            period_start + timedelta(weeks=index)
            for index in range(COMPLETED_WEEK_COUNT)
        ),
    )


def _clean_text(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _is_excluded_order_item(sku_code: str) -> bool:
    return sku_code.casefold() in EXCLUDED_ORDER_ITEM_CODES


def _first_text(values: Iterable[object]) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _numeric(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _frame_rows(
    frame: pd.DataFrame,
    *,
    sku_column: str,
    quantity_column: str | None = None,
) -> Iterable[tuple[str, pd.Series, float | None]]:
    if frame.empty or sku_column not in frame.columns:
        return ()
    rows: list[tuple[str, pd.Series, float | None]] = []
    for _, row in frame.iterrows():
        sku_code = _clean_text(row.get(sku_column))
        if not sku_code:
            continue
        quantity = _numeric(row.get(quantity_column)) if quantity_column else None
        rows.append((sku_code, row, quantity))
    return rows


def _sum_quantity_by_sku(
    frame: pd.DataFrame,
    *,
    sku_column: str,
    quantity_column: str,
    warning_code: str,
) -> tuple[dict[str, float], dict[str, list[str]], set[str]]:
    totals: dict[str, float] = {}
    warnings: dict[str, list[str]] = {}
    invalid: set[str] = set()
    for sku_code, _row, quantity in _frame_rows(
        frame,
        sku_column=sku_column,
        quantity_column=quantity_column,
    ):
        if quantity is None:
            quantity = 0.0
            warnings.setdefault(sku_code, []).append(f"{warning_code}_NULL_AS_ZERO")
        elif quantity < 0:
            invalid.add(sku_code)
            warnings.setdefault(sku_code, []).append(f"{warning_code}_NEGATIVE")
            continue
        totals[sku_code] = totals.get(sku_code, 0.0) + quantity
    return totals, warnings, invalid


def _sum_optional_quantity_by_sku(
    frame: pd.DataFrame,
    *,
    sku_column: str,
    quantity_column: str,
    warning_code: str,
) -> tuple[dict[str, float], dict[str, list[str]], set[str]]:
    """Aggregate an optional CMS quantity only when the source provides it.

    Some test/legacy payloads contain only ``open_qty`` even though the CMS
    mapper exposes the optional PNFM column. Treating that absent field as an
    observed zero would make the Excel status breakdown look authoritative, so
    keep it unavailable until at least one numeric source value is present.
    """

    if quantity_column not in frame.columns:
        return {}, {}, set()
    numeric_values = frame[quantity_column].map(_numeric)
    if not numeric_values.notna().any():
        return {}, {}, set()
    return _sum_quantity_by_sku(
        frame,
        sku_column=sku_column,
        quantity_column=quantity_column,
        warning_code=warning_code,
    )


def _merge_warning_maps(
    destination: dict[str, list[str]],
    source: dict[str, list[str]],
) -> None:
    for sku_code, values in source.items():
        destination.setdefault(sku_code, []).extend(values)


def _identity_map(frames: Iterable[pd.DataFrame]) -> dict[str, tuple[str, str]]:
    identity: dict[str, tuple[str, str]] = {}
    for frame in frames:
        if frame.empty or "상품코드" not in frame.columns:
            continue
        for _, row in frame.iterrows():
            sku_code = _clean_text(row.get("상품코드"))
            if not sku_code:
                continue
            previous_name, previous_brand = identity.get(sku_code, ("", ""))
            identity[sku_code] = (
                previous_name or _clean_text(row.get("상품명")),
                previous_brand or _clean_text(row.get("브랜드")),
            )
    return identity


def _text_value_by_sku(
    frames: Iterable[pd.DataFrame],
    *,
    column: str,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for frame in frames:
        if frame.empty or "상품코드" not in frame.columns or column not in frame.columns:
            continue
        for _, row in frame.iterrows():
            sku_code = _clean_text(row.get("상품코드"))
            value = _clean_text(row.get(column))
            if sku_code and value and sku_code not in result:
                result[sku_code] = value
    return result


def _unit_prices(local_stock: pd.DataFrame) -> dict[str, float | None]:
    candidates: dict[str, list[float]] = {}
    if local_stock.empty:
        return {}
    for sku_code, row, _ in _frame_rows(local_stock, sku_column="상품코드"):
        price = _numeric(
            row.get("현지 입고단가")
            if _clean_text(row.get("현지 입고단가"))
            else row.get("EU 입고단가")
        )
        if price is not None and price >= 0:
            candidates.setdefault(sku_code, []).append(price)
    return {
        sku_code: next((value for value in values if value > 0), values[0] if values else None)
        for sku_code, values in candidates.items()
    }


def _shipping_schedule_by_sku(
    shipping: pd.DataFrame,
    *,
    config: OrderLogicConfig,
    entity_code: str,
) -> _ShippingEtaSummary:
    """Resolve each shipment's ETA without using the selected policy mode.

    Source ETA wins.  When it is absent, the shipment's actual transport mode
    is parsed from the CMS remark and connected to the V2 transport-specific
    mean lead time.  Lead-time sigma is deliberately not added to the date.
    """

    schedule_totals: dict[str, dict[str, float]] = {}
    details: dict[str, list[dict[str, object]]] = {}
    actual_qty: dict[str, float] = {}
    estimated_qty: dict[str, float] = {}
    review_qty: dict[str, float] = {}
    required = {"상품코드", "수량"}
    if shipping.empty or not required.issubset(shipping.columns):
        return _ShippingEtaSummary({}, {}, {}, {}, {})

    lead_time_by_code = {
        "AIR": ("AIR", "항공", float(config.lt_air_days)),
        "RAIL": ("RAIL", "철송", float(config.lt_rail_days)),
        "OCEAN": ("SEA", "해운", float(config.lt_sea_days)),
    }

    for sku_code, row, quantity in _frame_rows(
        shipping,
        sku_column="상품코드",
        quantity_column="수량",
    ):
        if quantity is None or quantity <= 0:
            continue

        source_eta = pd.to_datetime(row.get("ETA"), errors="coerce")
        ship_date = pd.to_datetime(row.get("출고일"), errors="coerce")
        remark = _clean_text(row.get("Invoice 비고"))
        parsed_code = normalize_transport_code(remark, entity_code)
        transport = lead_time_by_code.get(parsed_code)
        transport_code = transport[0] if transport else None
        transport_label = transport[1] if transport else None
        lead_time_days = transport[2] if transport else None

        eta_status = "ETA 미확인"
        resolved_eta = None
        applied_lead_time = None
        if pd.notna(source_eta):
            eta_status = "원천 ETA"
            resolved_eta = source_eta
            actual_qty[sku_code] = actual_qty.get(sku_code, 0.0) + quantity
        elif pd.notna(ship_date) and lead_time_days is not None:
            eta_status = "출고일 추정 ETA"
            applied_lead_time = lead_time_days
            resolved_eta = ship_date + pd.to_timedelta(lead_time_days, unit="D")
            estimated_qty[sku_code] = (
                estimated_qty.get(sku_code, 0.0) + quantity
            )
        else:
            review_qty[sku_code] = review_qty.get(sku_code, 0.0) + quantity

        eta_label = (
            resolved_eta.date().isoformat()
            if resolved_eta is not None and pd.notna(resolved_eta)
            else None
        )
        ship_date_label = (
            ship_date.date().isoformat() if pd.notna(ship_date) else None
        )
        details.setdefault(sku_code, []).append(
            {
                "eta": eta_label,
                "qty": quantity,
                "eta_status": eta_status,
                "ship_date": ship_date_label,
                "transport_mode": transport_code,
                "transport_label": transport_label,
                "lead_time_days": applied_lead_time,
            }
        )
        if eta_label is not None:
            sku_schedule = schedule_totals.setdefault(sku_code, {})
            sku_schedule[eta_label] = (
                sku_schedule.get(eta_label, 0.0) + quantity
            )

    schedules = {
        sku_code: [
            {"eta": eta_label, "qty": quantity}
            for eta_label, quantity in sorted(values.items())
        ]
        for sku_code, values in schedule_totals.items()
    }
    return _ShippingEtaSummary(
        schedules=schedules,
        details=details,
        actual_qty=actual_qty,
        estimated_qty=estimated_qty,
        review_qty=review_qty,
    )


def _sales_by_sku(
    sales: pd.DataFrame,
    window: CompletedWeekWindow,
    *,
    entity_code: str,
) -> tuple[
    dict[str, list[float]],
    dict[str, float],
    dict[str, list[str]],
    set[str],
    dict[str, object],
]:
    if sales.empty:
        raise ValueError(
            f"판매 데이터가 비어 있어 최근 {COMPLETED_WEEK_COUNT}개 완료 주를 계산할 수 없습니다."
        )
    required = {"상품코드", "수량", "출고일"}
    missing = sorted(required - set(sales.columns))
    if missing:
        raise ValueError(f"판매 데이터 필수 컬럼이 없습니다: {', '.join(missing)}")

    work = sales.copy()
    work["_sku"] = work["상품코드"].map(_clean_text)
    work["_date"] = pd.to_datetime(work["출고일"], errors="coerce")
    work["_qty"] = pd.to_numeric(
        work["수량"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    )
    amount_column = "환산금액" if "환산금액" in work.columns else "금액"
    if amount_column in work.columns:
        work["_revenue"] = pd.to_numeric(
            work[amount_column].astype(str).str.replace(",", "", regex=False),
            errors="coerce",
        )
    else:
        raise ValueError("판매 원천에 매출 필드가 없습니다.")

    valid_dates = work["_date"].dropna()
    if valid_dates.empty:
        raise ValueError("판매 데이터의 출고일을 날짜로 인식할 수 없습니다.")

    work = work[
        work["_date"].dt.date.between(window.period_start, window.period_end)
        & (work["_sku"] != "")
    ].copy()
    if work.empty:
        raise ValueError(
            f"최근 {COMPLETED_WEEK_COUNT}개 완료 주에 해당하는 판매 데이터가 없습니다."
        )

    # Cross-entity contract: a negative-amount, positive-quantity row is a
    # verified incident adjustment, not physical demand.  Its quantity leaves
    # the weekly demand vector and its signed amount also leaves the Pareto
    # revenue population, so an incident cannot lower a SKU's revenue grade.
    # CASH and SHORTAGE consume this same prepared frame.
    excluded_demand_mask = pd.Series(False, index=work.index)
    if str(entity_code or "").strip().upper() in {"PL", "USA"}:
        excluded_demand_mask = negative_amount_positive_qty_mask(
            work["_revenue"], work["_qty"]
        )
    work["_demand_qty"] = work["_qty"].mask(excluded_demand_mask, 0.0)
    work["_pareto_revenue"] = work["_revenue"].mask(excluded_demand_mask, 0.0)
    excluded_rows = work.loc[excluded_demand_mask]
    biz_distribution: dict[str, int] = {}
    if "Biz Type" in excluded_rows.columns:
        biz_distribution = {
            str(key or "(blank)"): int(value)
            for key, value in excluded_rows["Biz Type"].fillna("(blank)").value_counts().items()
        }
    exclusion_audit: dict[str, object] = {
        "sales_demand_excluded_rows": int(excluded_demand_mask.sum()),
        "sales_demand_excluded_skus": int(
            excluded_rows["_sku"].nunique()
        ),
        "sales_demand_excluded_qty": float(
            excluded_rows["_qty"].fillna(0.0).sum()
        ),
        "sales_demand_excluded_amount": float(
            excluded_rows["_revenue"].fillna(0.0).sum()
        ),
        "sales_demand_excluded_biz_type_distribution": biz_distribution,
    }

    work["_week_start"] = work["_date"].dt.date.map(
        lambda value: value - timedelta(days=value.weekday())
    )
    present_weeks = set(work["_week_start"].unique())
    missing_weeks = [week for week in window.week_starts if week not in present_weeks]
    if missing_weeks:
        labels = ", ".join(week.isoformat() for week in missing_weeks)
        raise ValueError(
            f"판매 원천이 {COMPLETED_WEEK_COUNT}주 전체를 덮지 못합니다. 누락 주: {labels}"
        )

    warnings: dict[str, list[str]] = {}
    invalid: set[str] = set()
    weekly: dict[str, list[float]] = {}
    revenue: dict[str, float] = {}
    week_index = {week: index for index, week in enumerate(window.week_starts)}

    for sku_code, group in work.groupby("_sku", sort=False):
        values = [0.0] * COMPLETED_WEEK_COUNT
        sku_warnings = warnings.setdefault(str(sku_code), [])
        if bool(excluded_demand_mask.loc[group.index].any()):
            sku_warnings.append("NEGATIVE_AMOUNT_POSITIVE_QTY_EXCLUDED")
        if group["_qty"].isna().any():
            sku_warnings.append("SALES_QTY_NULL_AS_ZERO")
        source_quantities = group["_qty"].fillna(0.0)
        quantities = group["_demand_qty"].fillna(0.0)
        if (source_quantities < 0).any():
            invalid.add(str(sku_code))
            sku_warnings.append("SALES_QTY_NEGATIVE")
        else:
            for week_start, week_group in group.assign(_qty=quantities).groupby(
                "_week_start",
                sort=False,
            ):
                index = week_index.get(week_start)
                if index is not None:
                    values[index] = float(week_group["_qty"].sum())
        weekly[str(sku_code)] = values

        revenue_values = group["_revenue"]
        if revenue_values.isna().any():
            raise ValueError(f"판매 원천의 매출 값이 누락되었습니다: {sku_code}")
        # V1 parity: within an allowed net-sales biz type, returns/adjustments
        # arrive as signed amount rows and net out when summed per SKU. A single
        # negative amount row therefore must not abort the whole snapshot. Only a
        # residual-negative SKU total cannot be graded or costed, so it is
        # isolated for review instead of blocking every other SKU.
        # Incident rows are already zeroed in `_pareto_revenue`, so a verified
        # incident no longer reduces the grade of an otherwise healthy SKU.
        revenue_sum = float(group["_pareto_revenue"].sum())
        if revenue_sum < 0:
            invalid.add(str(sku_code))
            sku_warnings.append("SALES_REVENUE_NET_NEGATIVE")
            revenue[str(sku_code)] = 0.0
        else:
            revenue[str(sku_code)] = revenue_sum

    return weekly, revenue, warnings, invalid, exclusion_audit


def _validate_inventory_position_raw_source(raw: object) -> None:
    """Validate the stock/IP contract independently from V2 sales detail."""

    if not isinstance(raw, dict):
        raise ValueError("V2 재고위치 CMS 원천은 객체 형식이어야 합니다.")

    required_fields: dict[str, set[str]] = {
        "stock_local": {"prod_cd", "avbl_qty"},
        "stock_hq": {"prod_cd", "avbl_qty"},
        "shipping": {"prod_cd", "qty"},
        "open_po": {"prod_cd", "open_qty"},
    }
    required_nonempty = {"stock_local", "stock_hq"}
    for key, fields in required_fields.items():
        rows = raw.get(key)
        if not isinstance(rows, list):
            raise ValueError(f"V2 재고위치 CMS 원천 엔드포인트가 누락되었습니다: {key}")
        if key in required_nonempty and not rows:
            raise ValueError(f"V2 재고위치 CMS 원천 엔드포인트가 비어 있습니다: {key}")
        if not rows:
            continue
        if any(not isinstance(row, dict) for row in rows):
            raise ValueError(f"V2 재고위치 CMS 원천 행 형식이 올바르지 않습니다: {key}")
        for index, row in enumerate(rows):
            missing = sorted(fields - set(row))
            if missing:
                raise ValueError(
                    f"V2 재고위치 CMS 원천 {key}[{index}]의 필수 필드가 누락되었습니다: "
                    f"{', '.join(missing)}"
                )

    open_po_rows = raw["open_po"]
    open_po_fields = {
        field for row in open_po_rows if isinstance(row, dict) for field in row
    }
    required_open_po_status_fields = {
        "pnfm_confirmed_qty",
        "inbound_in_progress_qty",
        "completed_qty",
    }
    missing_open_po_status_fields = sorted(
        required_open_po_status_fields - open_po_fields
    )
    if open_po_rows and missing_open_po_status_fields:
        raise ValueError(
            "최신 open-po 상태 필드가 없습니다: "
            + ", ".join(missing_open_po_status_fields)
        )


def _validate_raw_source(raw: object) -> None:
    """Fail closed before the permissive CMS mapper fills missing fields."""

    _validate_inventory_position_raw_source(raw)
    if not isinstance(raw, dict):
        raise AssertionError("inventory validation must reject non-object raw data")

    sales_rows = raw.get("sales_local")
    if not isinstance(sales_rows, list):
        raise ValueError("V2 CMS 원천 엔드포인트가 누락되었습니다: sales_local")
    if not sales_rows:
        raise ValueError("V2 CMS 원천 엔드포인트가 비어 있습니다: sales_local")
    for index, row in enumerate(sales_rows):
        if not isinstance(row, dict):
            raise ValueError("V2 CMS 원천 행 형식이 올바르지 않습니다: sales_local")
        missing = sorted({"prod_cd", "qty", "ship_dt"} - set(row))
        if missing:
            raise ValueError(
                f"V2 CMS 원천 sales_local[{index}]의 필수 필드가 누락되었습니다: "
                f"{', '.join(missing)}"
            )

    sales_fields = {
        field for row in sales_rows if isinstance(row, dict) for field in row
    }
    if "amount_krw_actual" not in sales_fields:
        raise ValueError("V2 CMS 판매 원천에 실제 원화 매출(amount_krw_actual)이 없습니다.")
    for index, row in enumerate(sales_rows):
        if not isinstance(row, dict):
            continue
        if _numeric(row.get("amount_krw_actual")) is None:
            raise ValueError(f"V2 CMS 판매 원천 sales_local[{index}]의 실제 원화 매출이 없습니다.")
        if _clean_text(row.get("xrate_source")).upper() == "UNRESOLVED":
            raise ValueError(f"V2 CMS 판매 원천 sales_local[{index}]의 환율을 확인할 수 없습니다.")

def _unit_prices_krw(local_stock: pd.DataFrame) -> dict[str, float | None]:
    candidates: dict[str, list[float]] = {}
    if local_stock.empty or "CMS 원화 입고단가" not in local_stock.columns:
        return {}
    for sku_code, row, _ in _frame_rows(local_stock, sku_column="상품코드"):
        price = _numeric(row.get("CMS 원화 입고단가"))
        if price is not None and price >= 0:
            candidates.setdefault(sku_code, []).append(price)
    return {
        sku_code: next(
            (value for value in values if value > 0),
            values[0] if values else None,
        )
        for sku_code, values in candidates.items()
    }


def _apply_biz_type_filter(
    sales: pd.DataFrame,
    *,
    entity_code: str,
) -> pd.DataFrame:
    """Apply the approved V1 biz-type population filter to the sales frame.

    V2 reuses ``core.sales.filter_sales_by_biz_type`` verbatim so the order
    logic shares one population definition with the legacy analysis: staff,
    free-sample, return, and accounting-adjustment rows drop out, while signed
    amount rows inside an allowed net-sales biz type are retained and net out
    when summed per SKU.  When the source carries no Biz Type values (for
    example synthetic fixtures) the rows cannot be classified, so the frame
    passes through unchanged, mirroring the legacy helper's behaviour when the
    biz column is absent.
    """

    if sales.empty or "Biz Type" not in sales.columns:
        return sales
    if not sales["Biz Type"].map(_clean_text).astype(bool).any():
        return sales
    return filter_sales_by_biz_type(sales, {"entity_code": entity_code})


def _shipping_rows_for_entity(
    rows: list[dict[str, object]],
    *,
    entity_code: str,
) -> list[dict[str, object]]:
    """Keep only shipments that belong to the entity's order population."""

    if str(entity_code or "").strip().upper() != "PL":
        return list(rows)
    return [
        row
        for row in rows
        if _clean_text(row.get("cust_nm")) == PL_SHIPPING_CUSTOMER_NAME
    ]


def _prepare_inventory_position_components(
    raw: dict[str, list[dict[str, object]]],
    *,
    entity_code: str,
) -> _InventoryPositionComponents:
    """Map the approved PL/USA IP inputs without preparing V2 demand or ETA."""

    _validate_inventory_position_raw_source(raw)
    source_raw = dict(raw)
    source_raw["shipping"] = _shipping_rows_for_entity(
        raw["shipping"],
        entity_code=entity_code,
    )
    uploaded = build_uploaded_data_from_cms(source_raw, entity_code=entity_code)
    local_stock = uploaded["eu_stock"]
    hq_stock = uploaded["hq_eu_stock"]
    sales = uploaded["sales_detail"]
    shipping = uploaded["shipping"]
    open_po = uploaded["open_po"]
    inbound_status_skus = (
        {
            _clean_text(value)
            for value in open_po["상품코드"].tolist()
            if _clean_text(value)
        }
        if "상품코드" in open_po.columns
        else set()
    )

    warnings_by_sku: dict[str, list[str]] = {}
    invalid_skus: set[str] = set()
    incoming, warnings, invalid = _sum_quantity_by_sku(
        open_po,
        sku_column="상품코드",
        quantity_column="미입고 수량",
        warning_code="INCOMING_QTY",
    )
    _merge_warning_maps(warnings_by_sku, warnings)
    invalid_skus.update(invalid)

    pnfm, warnings, invalid = _sum_optional_quantity_by_sku(
        open_po,
        sku_column="상품코드",
        quantity_column="PNFM확정 수량",
        warning_code="PNFM_QTY",
    )
    _merge_warning_maps(warnings_by_sku, warnings)
    invalid_skus.update(invalid)

    inbound_progress, warnings, invalid = _sum_optional_quantity_by_sku(
        open_po,
        sku_column="상품코드",
        quantity_column="입고진행중 수량",
        warning_code="INBOUND_PROGRESS_QTY",
    )
    _merge_warning_maps(warnings_by_sku, warnings)
    invalid_skus.update(invalid)

    completed, warnings, invalid = _sum_optional_quantity_by_sku(
        open_po,
        sku_column="상품코드",
        quantity_column="입고완료 수량",
        warning_code="INBOUND_COMPLETED_QTY",
    )
    _merge_warning_maps(warnings_by_sku, warnings)
    invalid_skus.update(invalid)

    eu_available, warnings, invalid = _sum_quantity_by_sku(
        hq_stock,
        sku_column="상품코드",
        quantity_column="본사 EU창고 가용수량",
        warning_code="EU_AVAILABLE_QTY",
    )
    _merge_warning_maps(warnings_by_sku, warnings)
    invalid_skus.update(invalid)

    transit, warnings, invalid = _sum_quantity_by_sku(
        shipping,
        sku_column="상품코드",
        quantity_column="수량",
        warning_code="TRANSIT_QTY",
    )
    _merge_warning_maps(warnings_by_sku, warnings)
    invalid_skus.update(invalid)

    local_available, warnings, invalid = _sum_quantity_by_sku(
        local_stock,
        sku_column="상품코드",
        quantity_column="EU 현지 가용수량",
        warning_code="LOCAL_AVAILABLE_QTY",
    )
    _merge_warning_maps(warnings_by_sku, warnings)
    invalid_skus.update(invalid)

    return _InventoryPositionComponents(
        source_raw=source_raw,
        local_stock=local_stock,
        hq_stock=hq_stock,
        sales=sales,
        shipping=shipping,
        open_po=open_po,
        inbound_status_skus=inbound_status_skus,
        incoming=incoming,
        pnfm=pnfm,
        inbound_progress=inbound_progress,
        completed=completed,
        eu_available=eu_available,
        transit=transit,
        local_available=local_available,
        identities=_identity_map((local_stock, hq_stock, shipping, open_po)),
        barcodes=_text_value_by_sku(
            (local_stock, hq_stock, open_po),
            column="바코드",
        ),
        prices=_unit_prices(local_stock),
        prices_krw=_unit_prices_krw(local_stock),
        warnings=warnings_by_sku,
        invalid_skus=invalid_skus,
    )


def build_order_logic_inventory_position_source(
    raw: dict[str, list[dict[str, object]]],
    *,
    entity_code: str = "PL",
) -> PreparedInventoryPositionSource:
    """Return the V2-approved PL/USA inventory position without V2 demand work.

    The result deliberately owns only `incoming + HQ available + transit +
    local available` and price/identity mappings.  V3 uses a separate daily
    24-month demand source, so it must not trigger V2's sales aggregation or
    shipment ETA calculation merely to obtain these operands.
    """

    components = _prepare_inventory_position_components(raw, entity_code=entity_code)
    sku_codes = [
        sku_code
        for sku_code in sorted(
            set(components.identities)
            | set(components.incoming)
            | set(components.eu_available)
            | set(components.transit)
            | set(components.local_available)
        )
        if not _is_excluded_order_item(sku_code)
    ]
    rows: list[dict[str, object]] = []
    for sku_code in sku_codes:
        open_qty = components.incoming.get(sku_code, 0.0)
        pnfm_confirmed_qty = components.pnfm.get(sku_code, 0.0)
        inbound_progress_qty = components.inbound_progress.get(sku_code, 0.0)
        rows.append(
            {
                "sku_code": sku_code,
                "product_name": components.identities.get(sku_code, ("", ""))[0],
                "brand": components.identities.get(sku_code, ("", ""))[1],
                "barcode": components.barcodes.get(sku_code, ""),
                # Preserve V2's display-only distinction between no row and zero.
                "inbound_status_source_present": sku_code in components.inbound_status_skus,
                "open_qty": open_qty,
                # RS-023: ① 미입고 + ② PNFM확정 + ③ 입고진행중 only.
                "incoming_qty": open_qty + pnfm_confirmed_qty + inbound_progress_qty,
                "pnfm_qty": components.pnfm.get(sku_code),
                "inbound_progress_qty": components.inbound_progress.get(sku_code),
                "inbound_completed_qty": components.completed.get(sku_code),
                "eu_available_qty": components.eu_available.get(sku_code, 0.0),
                "transit_qty": components.transit.get(sku_code, 0.0),
                "local_available_qty": components.local_available.get(sku_code, 0.0),
                "unit_price_local": components.prices.get(sku_code),
                "unit_price_krw": components.prices_krw.get(sku_code),
                "unit_price_eur": components.prices.get(sku_code),
                "warnings": sorted(set(components.warnings.get(sku_code, ()))),
                "validation_error": (
                    "음수 재고 값은 기술명세서에 처리 규칙이 없어 계산하지 않습니다."
                    if sku_code in components.invalid_skus
                    else None
                ),
            }
        )
    return PreparedInventoryPositionSource(
        rows=tuple(rows),
        source_counts={
            key: len(value)
            for key, value in components.source_raw.items()
            if isinstance(value, list)
        },
    )


def build_order_logic_v2_source(
    raw: dict[str, list[dict[str, object]]],
    *,
    as_of: str,
    config: OrderLogicConfig = DEFAULT_CONFIG,
    entity_code: str = "PL",
) -> PreparedOrderLogicSource:
    _validate_raw_source(raw)
    inventory = _prepare_inventory_position_components(raw, entity_code=entity_code)
    source_raw = inventory.source_raw
    local_stock = inventory.local_stock
    hq_stock = inventory.hq_stock
    sales = _apply_biz_type_filter(inventory.sales, entity_code=entity_code)
    shipping = inventory.shipping
    open_po = inventory.open_po

    window = completed_week_window(as_of)
    (
        weekly_sales,
        revenues,
        row_warnings,
        invalid_skus,
        sales_exclusion_audit,
    ) = _sales_by_sku(sales, window, entity_code=entity_code)
    _merge_warning_maps(row_warnings, inventory.warnings)
    invalid_skus.update(inventory.invalid_skus)

    incoming = inventory.incoming
    pnfm = inventory.pnfm
    inbound_progress = inventory.inbound_progress
    completed = inventory.completed
    eu_available = inventory.eu_available
    transit = inventory.transit
    local_available = inventory.local_available
    identities = _identity_map((local_stock, hq_stock, shipping, open_po, sales))
    barcodes = inventory.barcodes
    prices = inventory.prices
    prices_krw = inventory.prices_krw
    shipping_eta = _shipping_schedule_by_sku(
        shipping,
        config=config,
        entity_code=entity_code,
    )
    sku_codes = [
        sku_code
        for sku_code in sorted(
            set(identities)
            | set(weekly_sales)
            | set(incoming)
            | set(eu_available)
            | set(transit)
            | set(local_available)
        )
        if not _is_excluded_order_item(sku_code)
    ]

    rows: list[dict[str, object]] = []
    for sku_code in sku_codes:
        product_name, brand = identities.get(sku_code, ("", ""))
        weekly_values = weekly_sales.get(sku_code)
        open_qty = incoming.get(sku_code, 0.0)
        pnfm_confirmed_qty = pnfm.get(sku_code, 0.0)
        inbound_progress_qty = inbound_progress.get(sku_code, 0.0)
        # RS-023: PL and USA use the same inventory-position contract.
        # The calculation incoming quantity is the complete open-PO pipeline
        # ①+②+③, while the actual shipping feed remains a separate IP operand.
        calculation_incoming_qty = (
            open_qty + pnfm_confirmed_qty + inbound_progress_qty
        )
        hq_stock_missing = sku_code not in eu_available
        local_stock_missing = sku_code not in local_available
        if hq_stock_missing:
            row_warnings.setdefault(sku_code, []).append("HQ_STOCK_MISSING")
        if local_stock_missing:
            row_warnings.setdefault(sku_code, []).append("LOCAL_STOCK_MISSING")
        # A SKU that is absent from BOTH the local and HQ stock masters, yet
        # appears in a non-stock source (sales/shipping/open-PO), cannot be
        # costed or graded reliably. Mirroring the legacy analysis, it is routed
        # to the check-required list instead of the order suggestion.
        needs_master_review = hq_stock_missing and local_stock_missing
        if needs_master_review:
            present_sources = []
            if sku_code in weekly_sales:
                present_sources.append("판매내역")
            if sku_code in transit:
                present_sources.append("운송중")
            if sku_code in incoming:
                present_sources.append("미입고")
            source_phrase = (
                "·".join(present_sources) + " 내역에는 존재"
                if present_sources
                else "원천 데이터에는 존재"
            )
            check_required_reason = (
                f"현지·본사 재고 마스터 어디에도 없는 SKU입니다({source_phrase}). "
                "신규 SKU이거나 재고 이력이 없는 상품일 수 있어 확인이 필요합니다."
            )
            row_warnings.setdefault(sku_code, []).append("MASTER_STOCK_UNREGISTERED")
        else:
            check_required_reason = None
        schedule = shipping_eta.schedules.get(sku_code, [])
        eta_details = shipping_eta.details.get(sku_code, [])
        next_eta = schedule[0]["eta"] if schedule else None
        next_eta_statuses = {
            str(item.get("eta_status") or "")
            for item in eta_details
            if item.get("eta") == next_eta
        }
        if {"원천 ETA", "출고일 추정 ETA"} <= next_eta_statuses:
            next_eta_status = "원천·추정 ETA"
        elif "원천 ETA" in next_eta_statuses:
            next_eta_status = "원천 ETA"
        elif "출고일 추정 ETA" in next_eta_statuses:
            next_eta_status = "출고일 추정 ETA"
        elif shipping_eta.review_qty.get(sku_code, 0.0) > 0:
            next_eta_status = "ETA 미확인"
        else:
            next_eta_status = None
        rows.append(
            {
                "sku_code": sku_code,
                "product_name": product_name,
                "brand": brand,
                "barcode": barcodes.get(sku_code, ""),
                "weekly_sales": weekly_values,
                # API/Excel 호환 필드명은 유지하지만 값은 현재 승인된 13주 합계다.
                "sales_13w_qty": float(sum(weekly_values or ())),
                "revenue": revenues.get(sku_code, 0.0),
                "inbound_status_source_present": sku_code in inventory.inbound_status_skus,
                "open_qty": open_qty,
                "incoming_qty": calculation_incoming_qty,
                "pnfm_qty": pnfm.get(sku_code),
                # The existing shipping aggregate is the approved source for
                # material currently moving toward the destination warehouse.
                # Completed quantity is display-only and is not added to IP,
                # because completed receipts are already reflected in stock.
                "inbound_progress_qty": inbound_progress.get(sku_code),
                "inbound_completed_qty": completed.get(sku_code),
                "eu_available_qty": eu_available.get(sku_code, 0.0),
                # PL and USA both add actual shipping quantity separately from
                # the ①+②+③ open-PO pipeline.  ④ remains display-only.
                "transit_qty": transit.get(sku_code, 0.0),
                "local_available_qty": local_available.get(sku_code, 0.0),
                "shipping_schedule": schedule,
                "shipping_eta_details": eta_details,
                "eta_actual_qty": shipping_eta.actual_qty.get(sku_code, 0.0),
                "eta_estimated_qty": shipping_eta.estimated_qty.get(
                    sku_code, 0.0
                ),
                "eta_missing_qty": shipping_eta.review_qty.get(sku_code, 0.0),
                "next_eta": next_eta,
                "next_eta_status": next_eta_status,
                "unit_price_local": prices.get(sku_code),
                "unit_price_krw": prices_krw.get(sku_code),
                # result_schema_version=4 이전 소비자 호환용 별칭
                "unit_price_eur": prices.get(sku_code),
                "check_required": needs_master_review,
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
        for key, value in source_raw.items()
        if isinstance(value, list)
    }
    source_counts.update(
        {
            key: int(sales_exclusion_audit[key])
            for key in (
                "sales_demand_excluded_rows",
                "sales_demand_excluded_skus",
            )
        }
    )
    limitations = (
        "신상품은 판매 이력이 짧아 제안수량이 실제 수요보다 적을 수 있습니다.",
        "품절 이력이 반영되지 않아, 품절이 잦았던 SKU는 제안수량이 실제 수요보다 적을 수 있습니다.",
    )
    return PreparedOrderLogicSource(
        period_start=window.period_start,
        period_end=window.period_end,
        rows=tuple(rows),
        source_counts=source_counts,
        warnings=limitations,
        source_audit={"sales_demand_exclusion": sales_exclusion_audit},
    )


__all__ = [
    "COMPLETED_WEEK_COUNT",
    "CompletedWeekWindow",
    "PreparedInventoryPositionSource",
    "PreparedOrderLogicSource",
    "build_order_logic_inventory_position_source",
    "build_order_logic_v2_source",
    "completed_week_window",
    "warsaw_today",
]
