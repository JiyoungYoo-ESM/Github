"""CMS source adapter for the textbook V3 calculation.

The adapter keeps source work separate from ``core.order_logic_v3``: stock-ledger
sales (including online) supply SKU x calendar-day quantities, the sales-history
API supplies revenue grades, matching monthly artifacts supply seasonal factors,
and the existing inventory snapshot supplies IP operands. Web demand covers only
13 completed weeks; it cannot establish a product's lifetime first sale.
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from time import perf_counter
from typing import Mapping, Sequence

import pandas as pd

from backend.cms_client import fetch_cms_lead_time
from backend.services.order_logic_v3_ledger import (
    LEDGER_POLICY, SALE_TYPES, fetch_v3_ledger_sales,
)
from backend.services.order_logic_v3_shipping import build_shipping_reference_source
from backend.services.order_logic_v3_product_identity import (
    PRODUCT_IDENTITY_REASON,
    ProductIdentityResolver,
    inventory_identity_sources,
)
from backend.season_trend_api_client import fetch_cached_season_trend_source_data
from backend.services.cms_source import (
    fetch_cached_cms_inventory_raw_data,
)
from backend.services.order_logic_v3_hq_fetch import fetch_cached_hq_opo_raw_data
from backend.services.order_logic_v3_unreceived_window import (
    unreceived_po_window_audit,
)
from backend.services.order_logic_v2_hq_source import (
    build_hq_order_logic_source,
    is_hq_demand_row,
)
from backend.services.order_logic_v2_lead_time import (
    aggregate_lead_time_rows,
    lead_time_query_window,
)
from backend.services.order_logic_v2_source import (
    build_order_logic_inventory_position_source,
)
from core.order_logic_v3 import (
    PERIOD_DAYS,
    REQUIRED_COMPLETED_PERIODS,
    SALES_GRADE_CORE,
    SALES_GRADE_GENERAL,
    SeasonalProfile,
    V3ReplenishmentBaseInput,
    V3ReplenishmentPolicy,
    apply_textbook_seasonal_shrinkage,
    calculate_candidate_monthly_factors,
)
from core.season_calendar import (
    AMOUNT_COL,
    BRAND_COL,
    CATEGORY1_COL,
    CATEGORY2_COL,
    DATE_COL,
    MASTER_BRAND_COL,
    MASTER_PRODUCT_NAME_COL,
    PRODUCT_CODE_COL,
    PRODUCT_NAME_COL,
    QTY_COL,
    UNMAPPED,
    _standard_prod_df,
    merge_sales_with_product_master,
    normalize_product_code,
)


SEASON_FACTOR_VERSION = "v3.8-stock-in-out-sale-online"
SOURCE_DATE_BASIS = "SOURCE_CALENDAR_DATE"
GRADE_CUTOFF = 0.90
FUNCTION_CLASS_1_AGGREGATE = "__FUNCTION_CLASS_1__"
SEASON_FACTOR_SCOPE_CLASS_1_AND_2 = "FUNCTION_CLASS_1_AND_2"
SEASON_FACTOR_SCOPE_CLASS_1 = "FUNCTION_CLASS_1"
CLASS2_MISSING_USE_CLASS1_FACTOR = "FUNCTION_CLASS2_MISSING_USE_CLASS1_FACTOR"

_V2_SCENARIO_MODES = {
    # 2026-09-08 user decision: PL uses RAIL for both order scenarios.
    "PL": {"CASH": "RAIL", "SHORTAGE": "RAIL"},
    "USA": {"CASH": "AIR", "SHORTAGE": "SEA"},
}
# Modes measured from completed packings. PL still measures SEA because the
# V2-parity ETA resolver needs the measured SEA mean for sea shipments in
# transit, even though both PL order scenarios now use RAIL.
_V3_MEASURED_LEAD_TIME_MODES = {
    "PL": ("RAIL", "SEA"),
    "USA": ("AIR", "SEA"),
}
_V3_SAFETY_STOCK_FENCE_PERIODS = {
    "PL": (2.0, 10.0),
    "USA": (2.0, 8.0),
    "HQ": (1.0, 2.0),
}
_V3_LEAD_TIME_COMPLETION_MONTHS = 6
_V3_LEAD_TIME_MINIMUM_SAMPLE_SIZE = 10
_V3_INVENTORY_POSITION_POLICY = (
    "V2 adapter values: PL/USA=local_available_qty+eu_available_qty+transit_qty+incoming_qty; "
    "HQ=local_available_qty+incoming_qty (eu_available_qty=transit_qty=0); "
    "PL/USA trust V2 avbl_qty without an extra V3 TROUBLE/trbl_yn filter; "
    "HQ excludes stock_status=trouble in its V2 adapter; "
    "incoming=open+PNFM confirmed+inbound progress; completed receipts excluded; "
    "V3 limits only the ① open-PO quantity to the last 30 calendar days of PO "
    "registration (PL/USA via a second open-po query, HQ by zeroing stale rows); "
    "② PNFM confirmed and ③ inbound progress keep the full window because those "
    "goods are already inbound"
)
# User-approved V3 scope exceptions (2026-08-31), not a product-name rule.
# These identifiers are policy configuration; no CMS payload is stored here.
_V3_EXCLUDED_SKUS_BY_ENTITY = {
    "USA": frozenset({"IUS04-CEU", "JSMS01-SgEU", "MECUS08-TPREU"}),
}
_V3_SKU_SCOPE_VERSION = "v3-sku-scope-2026-08-31"


def _analysis_sku_scope(
    candidates: set[str],
    *,
    entity_code: str,
    identity_source_codes: Mapping[str, Sequence[str]],
) -> tuple[list[str], dict[str, object]]:
    """Exclude only explicit entity/SKU exceptions after validated identity mapping."""
    excluded = _V3_EXCLUDED_SKUS_BY_ENTITY.get(entity_code, frozenset())
    kept = [
        sku for sku in sorted(candidates)
        if sku not in excluded
        and excluded.isdisjoint(identity_source_codes.get(sku, ()))
    ]
    # Record counts and a policy fingerprint, never source names or transactions.
    return kept, {
        "version": _V3_SKU_SCOPE_VERSION,
        "reason_code": "USER_APPROVED_ENTITY_SKU_EXCLUSION",
        "configured_sku_count": len(excluded),
        "configuration_sha256": hashlib.sha256(
            json.dumps(sorted(excluded), ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "candidate_sku_count": len(candidates),
        "excluded_sku_count": len(candidates) - len(kept),
        "included_sku_count": len(kept),
    }


def last_completed_sunday(as_of: date) -> date:
    return as_of - timedelta(days=as_of.weekday() + 1)


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _shift_month(value: date, months: int) -> date:
    absolute = value.year * 12 + value.month - 1 + months
    return date(absolute // 12, absolute % 12 + 1, 1)


def completed_month_window(sales_cutoff: date) -> tuple[date, date, tuple[date, ...]]:
    """Return 24 whole months ending before the completed-sales cutoff month."""

    end = _month_start(sales_cutoff) - timedelta(days=1)
    start = _shift_month(_month_start(end), -23)
    months = tuple(_shift_month(start, offset) for offset in range(24))
    return start, end, months


def _number(value: object) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        parsed = float(str(value).replace(",", "").strip() or "0")
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _text(value: object) -> str:
    return str(value or "").strip()


def _paid_demand(
    sales_rows: Sequence[Mapping[str, object]],
    product_rows: Sequence[Mapping[str, object]],
    *,
    entity_code: str,
    identity_resolver: ProductIdentityResolver | None = None,
) -> pd.DataFrame:
    resolver = identity_resolver or ProductIdentityResolver.build(product_rows, [sales_rows])
    # Warehouse/biz filters do not inspect product codes. Apply them before
    # allocating rewritten rows, while the resolver still sees ALL identity
    # evidence (including conflicts in excluded source rows).
    eligible_rows = (
        [row for row in sales_rows if is_hq_demand_row(row)]
        if entity_code == "HQ" else sales_rows
    )
    rows = resolver.rewrite_rows(eligible_rows)
    merged = merge_sales_with_product_master(
        pd.DataFrame(rows),
        pd.DataFrame(resolver.rewrite_products(product_rows)),
        eu_local=entity_code == "PL",
        entity_code=entity_code,
        preserve_product_code_suffix=True,
    )
    if merged.empty:
        return merged
    # Retain the previous paid-sales population for revenue-based grades only.
    # Quantity demand now comes exclusively from _ledger_demand.
    return merged.loc[
        pd.to_numeric(merged[QTY_COL], errors="coerce").fillna(0).gt(0)
        & pd.to_numeric(merged[AMOUNT_COL], errors="coerce").fillna(0).gt(0)
    ].copy()


def _ledger_demand(
    sales_rows: Sequence[Mapping[str, object]],
    product_rows: Sequence[Mapping[str, object]],
    *,
    entity_code: str,
    identity_resolver: ProductIdentityResolver | None = None,
) -> pd.DataFrame:
    """Quantity-only demand. Do not invent amounts or run invoice biz filters.

    Source scope, signs and completeness are validated before monthly caching.
    The same product-master and exact-name identity policy serves web and season.
    """
    resolver = identity_resolver or ProductIdentityResolver.build(product_rows, [sales_rows])
    master = _product_master_identities(resolver.rewrite_products(product_rows))
    columns = [PRODUCT_CODE_COL, PRODUCT_NAME_COL, BRAND_COL, CATEGORY1_COL,
               CATEGORY2_COL, DATE_COL, QTY_COL]
    records = []
    for row in resolver.rewrite_rows(sales_rows):
        if row.get("ledger_type_nm") not in SALE_TYPES:
            continue
        sku = _text(row.get("prod_cd"))
        qty = row.get("qty_out")
        if not sku or isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
            raise ValueError("수불 판매집계의 상품코드 또는 출고수량이 올바르지 않습니다.")
        day = date.fromisoformat(str(row.get("ledger_dt")))
        name, brand, class1, class2 = master.get(sku, ("", "", UNMAPPED, UNMAPPED))
        records.append({
            PRODUCT_CODE_COL: sku, PRODUCT_NAME_COL: _text(row.get("prod_nm")) or name,
            BRAND_COL: _text(row.get("brand_nm")) or brand,
            CATEGORY1_COL: class1, CATEGORY2_COL: class2,
            DATE_COL: pd.Timestamp(day), QTY_COL: qty,
        })
    return pd.DataFrame(records, columns=columns)


def _monthly_totals(
    frame: pd.DataFrame,
    months: Sequence[date],
    *,
    category2: bool,
) -> dict[tuple[str, ...], dict[date, float]]:
    start, end = pd.Timestamp(months[0]), pd.Timestamp(_shift_month(months[-1], 1))
    scoped = frame.loc[(frame[DATE_COL] >= start) & (frame[DATE_COL] < end)].copy()
    keys = [CATEGORY1_COL, CATEGORY2_COL] if category2 else [CATEGORY1_COL]
    result: dict[tuple[str, ...], dict[date, float]] = {}
    if scoped.empty:
        return result
    scoped["_month"] = scoped[DATE_COL].dt.to_period("M").dt.to_timestamp()
    grouped = scoped.groupby(keys + ["_month"], dropna=False)[QTY_COL].sum()
    for index, value in grouped.items():
        parts = index if isinstance(index, tuple) else (index,)
        group_key = tuple(_text(part) or UNMAPPED for part in parts[:-1])
        month_key = pd.Timestamp(parts[-1]).date()
        result.setdefault(group_key, {month: 0.0 for month in months})[month_key] = float(value)
    return result


@dataclass(frozen=True, slots=True)
class _SeasonalProfileCatalog:
    by_class_1_and_2: Mapping[tuple[str, str], SeasonalProfile]
    by_class_1: Mapping[str, SeasonalProfile]
    class_1_and_2_errors: Mapping[tuple[str, str], str]
    class_1_errors: Mapping[str, str]
    identities: Mapping[str, tuple[str, str, str, str]]
    artifact_error_code: str | None = None
    artifact_error_message: str | None = None
    artifact_version: str | None = None
    application_metadata: Mapping[tuple[str, str, str], Mapping[str, str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _SeasonalProfileSelection:
    profile: SeasonalProfile
    source_function_class_1_code: str
    source_function_class_2_code: str
    scope: str
    application_reason_code: str | None = None
    blocking_reason_code: str | None = None
    blocking_message: str | None = None
    original_reason_code: str | None = None
    original_message: str | None = None


def _selected_profile(
    catalog: _SeasonalProfileCatalog,
    profile: SeasonalProfile,
    *,
    class1: str,
    class2: str,
    scope: str,
    application_reason_code: str | None = None,
) -> _SeasonalProfileSelection:
    metadata = catalog.application_metadata.get(
        (scope, profile.function_class_1_code, profile.function_class_2_code), {}
    )
    return _SeasonalProfileSelection(
        profile=profile,
        source_function_class_1_code=class1,
        source_function_class_2_code=class2,
        scope=scope,
        application_reason_code=metadata.get("reason_code") or application_reason_code,
        original_reason_code=metadata.get("original_reason_code"),
        original_message=metadata.get("original_message"),
    )


def _placeholder_seasonal_profile(
    *,
    entity_code: str,
    function_class_1_code: str,
    function_class_2_code: str,
    version: str = SEASON_FACTOR_VERSION,
) -> SeasonalProfile:
    """Carry a valid profile object only until the service emits a blocked SKU row.

    The caller must set a blocking reason and the V3 engine must never receive
    this placeholder as a calculable input.
    """

    return SeasonalProfile(
        version=version,
        entity_code=entity_code,
        function_class_1_code=function_class_1_code,
        function_class_2_code=function_class_2_code,
        factors_by_month={month: 1.0 for month in range(1, 13)},
    )


def _candidate_factors(totals: Mapping[date, float]) -> dict[int, float]:
    factors = calculate_candidate_monthly_factors(totals)
    if any(value <= 0 for value in factors.values()):
        raise ValueError("zero monthly factor")
    return factors


def _identities(demand: pd.DataFrame) -> dict[str, tuple[str, str, str, str]]:
    # Same last physical row per SKU, without allocating one DataFrame per
    # group. Do not use groupby.last(): it skips nulls column by column.
    columns = [PRODUCT_CODE_COL, PRODUCT_NAME_COL, BRAND_COL, CATEGORY1_COL, CATEGORY2_COL]
    last_rows = demand.loc[demand[PRODUCT_CODE_COL].notna()].drop_duplicates(
        subset=[PRODUCT_CODE_COL], keep="last",
    )
    return {
        _text(sku): (_text(name), _text(brand), _text(class1) or UNMAPPED, _text(class2) or UNMAPPED)
        for sku, name, brand, class1, class2 in last_rows.reindex(columns=columns).itertuples(index=False, name=None)
    }


def _product_master_metadata(
    product_rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, tuple[str, str, str, str]], dict[str, str]]:
    """Resolve classification even when a SKU has no eligible paid sales.

    Use the same normalization and duplicate handling as the sales/master
    join. This lookup does not add master-only SKUs to the order population
    or change the sales-based sample counts used by monthly factor generation.
    The barcode is display metadata and fills inventory/source gaps only.
    """

    master = _standard_prod_df(pd.DataFrame(product_rows), preserve_product_code_suffix=True)
    if master.empty:
        return {}, {}
    columns = [
        PRODUCT_CODE_COL, MASTER_PRODUCT_NAME_COL, MASTER_BRAND_COL,
        CATEGORY1_COL, CATEGORY2_COL, "바코드",
    ]
    identities: dict[str, tuple[str, str, str, str]] = {}
    barcodes: dict[str, str] = {}
    for sku, name, brand, class1, class2, barcode in (
        master[columns].fillna("").itertuples(index=False, name=None)
    ):
        code = _text(sku)
        identities[code] = (
            _text(name), _text(brand), _text(class1) or UNMAPPED,
            _text(class2) or UNMAPPED,
        )
        value = _text(barcode)
        if value:
            barcodes[code] = value
    return identities, barcodes


def _product_master_identities(
    product_rows: Sequence[Mapping[str, object]],
) -> dict[str, tuple[str, str, str, str]]:
    identities, _barcodes = _product_master_metadata(product_rows)
    return identities


def _pack_quantity_or_none(value: object) -> float | None:
    """CMS unified unset inbox/outbox to null; treat 0/negative/non-numeric the same."""

    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0.0:
        return None
    return parsed


def _product_pack_quantities(
    product_rows: Sequence[Mapping[str, object]],
    *,
    entity_code: str,
) -> dict[str, tuple[float | None, float | None]]:
    """Map each master SKU to its (inbox, outbox) order-unit source values.

    Uses the same code normalization and last-row-wins duplicate handling as
    the master identity lookup, and never adds SKUs to the order population.

    User decision (2026-09-08): USA orders read the US-specific master pack
    (`inbox_cnt_usa`) only. A missing USA value falls through to the 10-unit
    ladder fallback; the company-wide `inbox_cnt` is not a USA substitute
    because real USA packs differ in both directions (e.g. 1->6, 50->5).
    `outbox_cnt` has no regional variant and stays shared.
    """

    inbox_field = "inbox_cnt_usa" if entity_code == "USA" else "inbox_cnt"
    packs: dict[str, tuple[float | None, float | None]] = {}
    for row in product_rows:
        code = normalize_product_code(
            row.get("prod_cd") or row.get(PRODUCT_CODE_COL), preserve_suffix=True,
        )
        if not code:
            continue
        packs[code] = (
            _pack_quantity_or_none(row.get(inbox_field)),
            _pack_quantity_or_none(row.get("outbox_cnt")),
        )
    return packs


def _profiles(
    demand: pd.DataFrame,
    months: Sequence[date],
    *,
    entity_code: str,
) -> _SeasonalProfileCatalog:
    identities = _identities(demand)
    combo_totals = _monthly_totals(demand, months, category2=True)
    parent_totals = _monthly_totals(demand, months, category2=False)
    sku_counts: dict[tuple[str, str], int] = defaultdict(int)
    for _sku, (_name, _brand, class1, class2) in identities.items():
        sku_counts[(class1, class2)] += 1

    parent_profiles: dict[str, SeasonalProfile] = {}
    parent_errors: dict[str, str] = {}
    for (class1,), totals in parent_totals.items():
        try:
            factors = _candidate_factors(totals)
        except ValueError as exc:
            parent_errors[class1] = str(exc)
            continue
        parent_profiles[class1] = SeasonalProfile(
            version=SEASON_FACTOR_VERSION,
            entity_code=entity_code,
            function_class_1_code=class1,
            function_class_2_code=FUNCTION_CLASS_1_AGGREGATE,
            factors_by_month=factors,
        )

    profiles: dict[tuple[str, str], SeasonalProfile] = {}
    profile_errors: dict[tuple[str, str], str] = {}
    for key, totals in combo_totals.items():
        class1, class2 = key
        # A missing function class 2 is intentionally resolved with the
        # explicit class-1 policy below, not a pseudo "미분류" class-2 profile.
        if class2 == UNMAPPED:
            continue
        try:
            combo = _candidate_factors(totals)
            parent = parent_profiles[class1].factors_by_month
            factors = apply_textbook_seasonal_shrinkage(
                combo,
                parent,
                sku_count=sku_counts[key],
                # The textbook gives no separate hypothesis-test equation;
                # a complete calculable 24-month category series is therefore
                # the literal calculable profile. Invalid/zero profiles are
                # retained as SKU-level blocking reasons below.
                seasonality_confirmed=True,
            )
            if any(value <= 0 for value in factors.values()):
                raise ValueError("zero monthly factor")
        except (KeyError, ValueError) as exc:
            profile_errors[key] = str(exc)
            continue
        profiles[key] = SeasonalProfile(
            version=SEASON_FACTOR_VERSION,
            entity_code=entity_code,
            function_class_1_code=class1,
            function_class_2_code=class2,
            factors_by_month=factors,
        )
    return _SeasonalProfileCatalog(
        by_class_1_and_2=profiles,
        by_class_1=parent_profiles,
        class_1_and_2_errors=profile_errors,
        class_1_errors=parent_errors,
        identities=identities,
    )


def _select_seasonal_profile(
    catalog: _SeasonalProfileCatalog,
    *,
    entity_code: str,
    function_class_1_code: str,
    function_class_2_code: str,
) -> _SeasonalProfileSelection:
    """Choose the approved factor scope without hiding unmapped/error states."""

    placeholder = _placeholder_seasonal_profile(
        entity_code=entity_code,
        function_class_1_code=function_class_1_code,
        function_class_2_code=function_class_2_code,
        version=catalog.artifact_version or SEASON_FACTOR_VERSION,
    )
    if catalog.artifact_error_code:
        return _SeasonalProfileSelection(
            profile=placeholder,
            source_function_class_1_code=function_class_1_code,
            source_function_class_2_code=function_class_2_code,
            scope=SEASON_FACTOR_SCOPE_CLASS_1_AND_2,
            blocking_reason_code=catalog.artifact_error_code,
            blocking_message=(
                catalog.artifact_error_message
                or "활성 시즌팩터 artifact를 사용할 수 없습니다."
            ),
        )
    if function_class_1_code == UNMAPPED:
        return _SeasonalProfileSelection(
            profile=placeholder,
            source_function_class_1_code=function_class_1_code,
            source_function_class_2_code=function_class_2_code,
            scope=SEASON_FACTOR_SCOPE_CLASS_1_AND_2,
            blocking_reason_code="SEASON_FACTOR_MAPPING_MISSING",
            blocking_message="기능구분1이 미분류라 계절지수를 적용할 수 없습니다.",
        )

    if function_class_2_code == UNMAPPED:
        profile = catalog.by_class_1.get(function_class_1_code)
        if profile is not None:
            return _selected_profile(
                catalog, profile,
                class1=function_class_1_code,
                class2=function_class_2_code,
                scope=SEASON_FACTOR_SCOPE_CLASS_1,
                application_reason_code=CLASS2_MISSING_USE_CLASS1_FACTOR,
            )
        error = catalog.class_1_errors.get(function_class_1_code)
        return _SeasonalProfileSelection(
            profile=placeholder,
            source_function_class_1_code=function_class_1_code,
            source_function_class_2_code=function_class_2_code,
            scope=SEASON_FACTOR_SCOPE_CLASS_1,
            blocking_reason_code=(
                "SEASON_FACTOR_CALC_FAILED" if error else "SEASON_FACTOR_MISSING"
            ),
            blocking_message=(
                f"기능구분2가 미분류여 기능구분1 팩터를 적용할 수 없습니다: {error}"
                if error
                else "기능구분2가 미분류이며 적용 가능한 동일 법인 기능구분1 팩터가 없습니다."
            ),
        )

    profile = catalog.by_class_1_and_2.get(
        (function_class_1_code, function_class_2_code)
    )
    if profile is not None:
        return _selected_profile(
            catalog, profile,
            class1=function_class_1_code,
            class2=function_class_2_code,
            scope=SEASON_FACTOR_SCOPE_CLASS_1_AND_2,
        )
    error = catalog.class_1_and_2_errors.get(
        (function_class_1_code, function_class_2_code)
    )
    return _SeasonalProfileSelection(
        profile=placeholder,
        source_function_class_1_code=function_class_1_code,
        source_function_class_2_code=function_class_2_code,
        scope=SEASON_FACTOR_SCOPE_CLASS_1_AND_2,
        blocking_reason_code="SEASON_FACTOR_CALC_FAILED" if error else "SEASON_FACTOR_MISSING",
        blocking_message=(
            f"기능구분1·2 시즌팩터 계산에 실패했습니다: {error}"
            if error
            else "적용 가능한 동일 법인 기능구분1·2 시즌팩터가 없습니다."
        ),
    )


def _load_active_profile_catalog(
    entity_code: str,
) -> tuple[_SeasonalProfileCatalog, dict[str, object]]:
    """Keep artifact imports lazy so monthly generation can reuse this module."""

    from backend.services.order_logic_v3_season_factor_service import (
        load_active_season_factor_catalog,
    )
    from backend.services.order_logic_v3_season_factor_store import (
        SeasonFactorArtifactError,
    )

    try:
        catalog, meta = load_active_season_factor_catalog(entity_code)
        if meta.get("source_policy") != LEDGER_POLICY:
            raise SeasonFactorArtifactError(
                "SEASON_FACTOR_SOURCE_MISMATCH",
                "수불 판매 기준의 계절지수 갱신이 필요합니다. 계절지수 관리에서 새로 계산해 주세요.",
            )
        return catalog, meta
    except SeasonFactorArtifactError as exc:
        return (
            _SeasonalProfileCatalog(
                by_class_1_and_2={},
                by_class_1={},
                class_1_and_2_errors={},
                class_1_errors={},
                identities={},
                artifact_error_code=exc.reason_code,
                artifact_error_message=str(exc),
            ),
            {
                "status": "unavailable",
                "reason_code": exc.reason_code,
                "message": str(exc),
            },
        )


def _daily_sales(demand: pd.DataFrame, *, period_end: date) -> dict[str, dict[date, float]]:
    period_start = period_end - timedelta(
        days=REQUIRED_COMPLETED_PERIODS * PERIOD_DAYS - 1
    )
    scoped = demand.loc[
        (demand[DATE_COL].dt.date >= period_start)
        & (demand[DATE_COL].dt.date <= period_end)
    ]
    result: dict[str, dict[date, float]] = defaultdict(dict)
    grouped = scoped.groupby([PRODUCT_CODE_COL, scoped[DATE_COL].dt.date])[QTY_COL].sum()
    for (sku, day), qty in grouped.items():
        result[_text(sku)][day] = float(qty)
    return dict(result)


def _first_paid_sale_dates(demand: pd.DataFrame) -> dict[str, date]:
    """Return the earliest valid paid-sale date supplied by the V3 API snapshot."""

    if demand.empty:
        return {}
    earliest = demand.groupby(PRODUCT_CODE_COL, dropna=False)[DATE_COL].min()
    return {
        _text(sku): pd.Timestamp(value).date()
        for sku, value in earliest.items()
        if pd.notna(value)
    }


def _grades(demand: pd.DataFrame, *, period_end: date) -> dict[str, str]:
    period_start = period_end - timedelta(
        days=REQUIRED_COMPLETED_PERIODS * PERIOD_DAYS - 1
    )
    scoped = demand.loc[
        (demand[DATE_COL].dt.date >= period_start)
        & (demand[DATE_COL].dt.date <= period_end)
    ]
    revenue = scoped.groupby(PRODUCT_CODE_COL)[AMOUNT_COL].sum().sort_values(ascending=False)
    total = float(revenue.clip(lower=0).sum())
    if total <= 0:
        return {str(sku): SALES_GRADE_GENERAL for sku in revenue.index}
    cumulative_before = revenue.clip(lower=0).cumsum().shift(fill_value=0) / total
    return {
        _text(sku): SALES_GRADE_CORE if float(cumulative_before.loc[sku]) < GRADE_CUTOFF else SALES_GRADE_GENERAL
        for sku in revenue.index
    }


_V2_INVENTORY_WARNING_FIELDS = (
    "INCOMING_QTY", "PNFM_QTY", "INBOUND_PROGRESS_QTY", "INBOUND_COMPLETED_QTY",
    "INBOUND_CONFIRMED_QTY", "EU_AVAILABLE_QTY", "LOCAL_AVAILABLE_QTY",
    "OPO_AVAILABLE_QTY", "TRANSIT_QTY",
)


def _inventory_validation_state(
    row: Mapping[str, object], *, entity_code: str,
) -> tuple[str | None, tuple[str, ...]]:
    """Carry V2 inventory validation, without importing HQ's V2 demand policy."""
    raw_warnings = row.get("warnings") or ()
    if isinstance(raw_warnings, str):
        raw_warnings = (raw_warnings,)
    warnings = tuple(dict.fromkeys(str(value) for value in raw_warnings))
    error = str(row["validation_error"]) if row.get("validation_error") else None
    if entity_code == "HQ":
        # HQ's adapter also prepares V2 sales. Only its inventory diagnostics
        # belong to V3's inventory contract; V3 owns its separate demand window.
        warnings = tuple(value for value in warnings if value.startswith(
            tuple(f"{field}_" for field in _V2_INVENTORY_WARNING_FIELDS)
        ) or value == "OPO_STOCK_MISSING")
        if not any(value.endswith("_NEGATIVE") for value in warnings):
            error = None
    return error, warnings


def _inventory_rows(
    raw: Mapping[str, object],
    *,
    as_of: str,
    entity_code: str,
) -> tuple[dict[str, Mapping[str, object]], dict[str, int], dict[str, object] | None]:
    if entity_code == "HQ":
        prepared = build_hq_order_logic_source(raw, as_of=as_of)
        lead_time = dict(prepared.lead_time)
    else:
        prepared = build_order_logic_inventory_position_source(
            dict(raw),  # type: ignore[arg-type]
            entity_code=entity_code,
        )
        lead_time = None
    return (
        {_text(row.get("sku_code")): row for row in prepared.rows},
        dict(prepared.source_counts),
        lead_time,
    )


def _measured_replenishment_policies(
    *,
    as_of: date,
    entity_code: str,
    hq_lead_time: Mapping[str, object] | None,
) -> tuple[V3ReplenishmentPolicy, V3ReplenishmentPolicy, dict[str, object]]:
    """Convert the guide's six-month measured lead time to weekly V3 units."""

    review_days = 28.0
    floor_periods, cap_periods = _V3_SAFETY_STOCK_FENCE_PERIODS[entity_code]
    if entity_code == "HQ":
        if hq_lead_time is None:
            raise ValueError("HQ 실측 리드타임 원천이 누락되었습니다.")
        mean_days = _number(hq_lead_time.get("mean_days"))
        stdev_days = _number(hq_lead_time.get("stdev_days"))
        sample_size = int(_number(hq_lead_time.get("sample_size")))
        if sample_size < _V3_LEAD_TIME_MINIMUM_SAMPLE_SIZE:
            raise ValueError(
                "HQ 직전 6개월 리드타임 유효 표본이 10건 미만이라 계산을 차단했습니다."
            )
        if mean_days <= 0 or stdev_days < 0:
            raise ValueError("HQ 실측 리드타임 평균 또는 표준편차가 유효하지 않습니다.")
        policy = V3ReplenishmentPolicy(
            lead_time_days=mean_days,
            review_days=review_days,
            sigma_lead_time_periods=stdev_days / PERIOD_DAYS,
            safety_stock_floor_periods=floor_periods,
            safety_stock_cap_periods=cap_periods,
        )
        return policy, policy, {
            "basis": "해설서 기준 HQ 직전 6개월 완료 PO×SKU 실측",
            "source": {
                **dict(hq_lead_time),
                "observation_months": _V3_LEAD_TIME_COMPLETION_MONTHS,
                "minimum_sample_size": _V3_LEAD_TIME_MINIMUM_SAMPLE_SIZE,
            },
            "scenarios": {
                scenario: {
                    "transport_mode": "DOMESTIC_COMMON",
                    "lead_time_days": policy.lead_time_days,
                    "lead_time_periods": policy.lead_time_days / PERIOD_DAYS,
                    "review_days": policy.review_days,
                    "review_periods": policy.review_days / PERIOD_DAYS,
                    "sigma_lead_time_periods": policy.sigma_lead_time_periods,
                    "safety_stock_floor_periods": policy.safety_stock_floor_periods,
                    "safety_stock_cap_periods": policy.safety_stock_cap_periods,
                }
                for scenario in ("CASH", "SHORTAGE")
            },
        }

    required_modes = _V3_MEASURED_LEAD_TIME_MODES[entity_code]
    _completion_from, completion_to, api_from = lead_time_query_window(
        as_of,
        completion_months=_V3_LEAD_TIME_COMPLETION_MONTHS,
    )
    raw_rows = fetch_cms_lead_time(
        entity_code,
        date_from=api_from.isoformat(),
        date_to=completion_to.isoformat(),
        include_in_transit=False,
    )
    aggregation = aggregate_lead_time_rows(
        raw_rows,
        as_of=as_of,
        required_modes=required_modes,
        completion_months=_V3_LEAD_TIME_COMPLETION_MONTHS,
        minimum_sample_size=_V3_LEAD_TIME_MINIMUM_SAMPLE_SIZE,
    )

    policies: dict[str, V3ReplenishmentPolicy] = {}
    scenario_audit: dict[str, dict[str, object]] = {}
    for scenario, mode in _V2_SCENARIO_MODES[entity_code].items():
        stats = aggregation.modes[mode]
        policy = V3ReplenishmentPolicy(
            lead_time_days=stats.mean_days,
            review_days=review_days,
            sigma_lead_time_periods=stats.stdev_days / PERIOD_DAYS,
            safety_stock_floor_periods=floor_periods,
            safety_stock_cap_periods=cap_periods,
        )
        policies[scenario] = policy
        scenario_audit[scenario] = {
            "transport_mode": mode,
            "sample_size": stats.sample_size,
            "lead_time_days": policy.lead_time_days,
            "lead_time_periods": policy.lead_time_days / PERIOD_DAYS,
            "review_days": policy.review_days,
            "review_periods": policy.review_days / PERIOD_DAYS,
            "sigma_lead_time_days": stats.stdev_days,
            "sigma_lead_time_periods": policy.sigma_lead_time_periods,
            "safety_stock_floor_periods": policy.safety_stock_floor_periods,
            "safety_stock_cap_periods": policy.safety_stock_cap_periods,
        }
    return policies["CASH"], policies["SHORTAGE"], {
        "basis": "해설서 기준 직전 6개월 완료 Packing No 실측(모드별 최소 10건)",
        "source": {
            **aggregation.as_dict(),
            "completion_months": _V3_LEAD_TIME_COMPLETION_MONTHS,
            "minimum_sample_size": _V3_LEAD_TIME_MINIMUM_SAMPLE_SIZE,
        },
        "scenarios": scenario_audit,
    }


def _scenario_transport_mode(
    lead_time_audit: Mapping[str, object], scenario: str,
) -> str:
    scenarios = lead_time_audit.get("scenarios")
    scenario_audit = scenarios.get(scenario) if isinstance(scenarios, Mapping) else None
    mode = _text(scenario_audit.get("transport_mode")) if isinstance(scenario_audit, Mapping) else ""
    if not mode:
        raise ValueError(f"{scenario} 시나리오의 운송수단 감사정보가 누락되었습니다.")
    return mode


def build_order_logic_v3_source(
    *,
    as_of: str,
    entity_code: str,
    force_refresh: bool = False,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Fetch CMS sources and return explicit textbook operands per SKU."""

    started = phase_started = perf_counter()
    timings: dict[str, float] = {}

    def mark(stage: str) -> None:
        nonlocal phase_started
        now = perf_counter()
        timings[stage] = round(now - phase_started, 3)
        phase_started = now
        print(f"[perf][order_logic_v3] entity={entity_code} stage={stage} seconds={timings[stage]}", flush=True)

    parsed_as_of = date.fromisoformat(as_of)
    code = _text(entity_code).upper()
    if code not in {"HQ", "PL", "USA"}:
        raise ValueError(f"V3 적용 대상이 아닌 법인입니다: {code or '(empty)'}")
    period_end = last_completed_sunday(parsed_as_of)
    demand_start = period_end - timedelta(
        days=REQUIRED_COMPLETED_PERIODS * PERIOD_DAYS - 1
    )
    fetch_end = period_end
    # ① 미입고 수량만 PO 등록일 최근 30 달력일로 좁힌 창. 실제 적용은 법인별
    # fetch에서 같은 helper로 계산하므로 감사값과 조회 범위는 어긋날 수 없다.
    unreceived_window = unreceived_po_window_audit(parsed_as_of)

    if code == "HQ":
        inventory_raw, inventory_meta = fetch_cached_hq_opo_raw_data(
            as_of=as_of,
            date_from=demand_start.isoformat(),
            date_to=fetch_end.isoformat(),
            force_refresh=force_refresh,
        )
        sales_rows = inventory_raw.get("sales_history") or []
        product_rows = list(inventory_raw.get("products") or [])
        season_meta: Mapping[str, object] = inventory_meta
    else:
        # Inventory/IP and the 13-completed-week V3 demand do not depend on one another.
        # Fetch them together so a cold V3 run waits for the slower source,
        # rather than their combined latency.
        with ThreadPoolExecutor(max_workers=2) as pool:
            inventory_future = pool.submit(
                fetch_cached_cms_inventory_raw_data,
                as_of=as_of,
                date_from=demand_start.isoformat(),
                force_refresh=force_refresh,
                entity_code=code,
            )
            season_future = pool.submit(
                fetch_cached_season_trend_source_data,
                date_from=demand_start.isoformat(),
                date_to=fetch_end.isoformat(),
                # V3 also classifies inventory/PO-only SKUs. The EU-sold
                # subset (even with sales-code supplements) omits them.
                # Keep sales entity-scoped; the full master adds no SKU
                # to the inventory/recent-sales population by itself.
                eu_sold_only=False,
                force_refresh=force_refresh,
                entity_code=code,
            )
            inventory_raw, inventory_meta, _dates = inventory_future.result()
            season_raw, season_meta = season_future.result()
        sales_rows = list(season_raw.get("sales_history") or [])
        product_rows = list(season_raw.get("prod_list") or [])

    mark("revenue_and_inventory_fetch")
    ledger_rows, ledger_meta = fetch_v3_ledger_sales(
        entity_code=code, date_from=demand_start.isoformat(),
        date_to=fetch_end.isoformat(), force_refresh=force_refresh,
    )
    mark("ledger_fetch")
    identity_resolver = ProductIdentityResolver.build(product_rows, [
        sales_rows, ledger_rows,
        # HQ's sales_history is already sales_rows. Visiting the exact same
        # rows twice adds no name/code evidence to the resolver's sets.
        *(rows for rows in inventory_identity_sources(inventory_raw) if rows is not sales_rows),
    ])
    # Only a V3-owned copy changes. Existing/V2 callers and CMS cache rows
    # retain their original case-sensitive codes and quantity contracts.
    inventory_raw = identity_resolver.rewrite_payload(inventory_raw)
    identity_source_codes = identity_resolver.source_codes_by_target()
    mark("product_identity")
    revenue_demand = _paid_demand(
        sales_rows, product_rows, entity_code=code, identity_resolver=identity_resolver,
    )
    demand = _ledger_demand(
        ledger_rows, product_rows, entity_code=code, identity_resolver=identity_resolver,
    )
    mark("ledger_demand_and_revenue")
    profile_catalog, season_factor_artifact = _load_active_profile_catalog(code)
    rewritten_product_rows = identity_resolver.rewrite_products(product_rows)
    product_identities, product_barcodes = _product_master_metadata(rewritten_product_rows)
    product_pack_quantities = _product_pack_quantities(rewritten_product_rows, entity_code=code)
    identities = _identities(demand) if not demand.empty else {}
    sales_by_sku = _daily_sales(demand, period_end=period_end) if not demand.empty else {}
    # The interactive source is intentionally only the approved 13 completed
    # weeks.  Its earliest row is not a trustworthy lifetime first-sale date,
    # so do not mislabel it. New-SKU status is trace-only and HOLT always uses
    # the approved fixed phi=0.90, therefore this changes no forecast operand.
    first_paid_sale_dates: dict[str, date] = {}
    grades = _grades(revenue_demand, period_end=period_end) if not revenue_demand.empty else {}
    mark("sales_and_factor_mapping")
    inventory, source_counts, hq_lead_time = _inventory_rows(
        inventory_raw,
        as_of=as_of,
        entity_code=code,
    )
    cash_policy, shortage_policy, lead_time_audit = _measured_replenishment_policies(
        as_of=parsed_as_of,
        entity_code=code,
        hq_lead_time=hq_lead_time,
    )
    cash_transport_mode = _scenario_transport_mode(lead_time_audit, "CASH")
    shortage_transport_mode = _scenario_transport_mode(lead_time_audit, "SHORTAGE")
    shipping_details, invalid_shipping_skus, shipping_status = build_shipping_reference_source(
        inventory_raw, entity_code=code, lead_time_audit=lead_time_audit,
    )
    mark("inventory_mapping")

    # Apply the scope exception after preparing demand/grades. Other SKUs keep
    # their original inputs and Pareto grades; shared CMS/V2 sources stay intact.
    scoped_skus, sku_scope_audit = _analysis_sku_scope(
        set(sales_by_sku) | set(inventory),
        entity_code=code,
        identity_source_codes=identity_source_codes,
    )
    rows: list[dict[str, object]] = []
    for sku in scoped_skus:
        current = inventory.get(sku, {})
        inventory_error, inventory_warnings = _inventory_validation_state(current, entity_code=code)
        master_identity = product_identities.get(sku, ("", "", UNMAPPED, UNMAPPED))
        identity = identities.get(sku, master_identity)
        name = identity[0] or master_identity[0] or _text(current.get("product_name"))
        brand = identity[1] or master_identity[1] or _text(current.get("brand"))
        class1, class2 = master_identity[2:]
        profile_selection = _select_seasonal_profile(
            profile_catalog,
            entity_code=code,
            function_class_1_code=class1,
            function_class_2_code=class2,
        )
        profile = profile_selection.profile
        # V3 inherits V2's approved IP adapter.  These availability fields
        # already contain V2's source-specific policy: HQ excludes
        # stock_status=trouble, while PL/USA trust V2 avbl_qty without adding a
        # V3 TROUBLE/trbl_yn filter. V3 must not recalculate raw stock/hold rows.
        on_hand = _number(current.get("local_available_qty"))
        upstream_available = _number(current.get("eu_available_qty"))
        inbox_quantity, outbox_quantity = product_pack_quantities.get(sku, (None, None))
        rows.append(
            {
                "sku_code": sku,
                "product_name": name,
                "brand": brand,
                "barcode": _text(current.get("barcode")) or product_barcodes.get(sku, ""),
                "inbox_quantity": inbox_quantity,
                "outbox_quantity": outbox_quantity,
                "product_identity_source_codes": identity_source_codes.get(sku, [sku]),
                "product_identity_reason_code": PRODUCT_IDENTITY_REASON if sku in identity_source_codes else None,
                "daily_sales": sales_by_sku.get(sku, {}),
                "first_sale_date": first_paid_sale_dates.get(sku),
                "cash_transport_mode": cash_transport_mode,
                "shortage_transport_mode": shortage_transport_mode,
                "shipping_eta_details": shipping_details.get(sku, []),
                "shipping_source_status": "INVALID_SOURCE" if sku in invalid_shipping_skus else shipping_status,
                "seasonal_profile": profile,
                "source_function_class_1_code": profile_selection.source_function_class_1_code,
                "source_function_class_2_code": profile_selection.source_function_class_2_code,
                "season_factor_scope": profile_selection.scope,
                "season_factor_application_reason_code": profile_selection.application_reason_code,
                "season_factor_original_reason_code": profile_selection.original_reason_code,
                "season_factor_original_message": profile_selection.original_message,
                "season_factor_blocking_reason_code": profile_selection.blocking_reason_code,
                "season_factor_blocking_message": profile_selection.blocking_message,
                "sales_grade": grades.get(sku, SALES_GRADE_GENERAL),
                "unit_price_krw": (
                    _number(current.get("unit_price_krw"))
                    if current.get("unit_price_krw") is not None
                    else None
                ),
                "unit_price_local": (
                    _number(current.get("unit_price_local"))
                    if current.get("unit_price_local") is not None else None
                ),
                "inventory_validation_error": inventory_error,
                "inventory_warnings": inventory_warnings,
                # Sales-only SKUs have no inventory/source row. Never infer
                # absence from a zero or a missing individual quantity field.
                "inbound_status_source_present": (
                    current.get("inbound_status_source_present") if current else False
                ),
                # Display the four existing source buckets separately. Do not
                # relabel the combined incoming operand as bucket ① alone.
                "inventory_breakdown": {
                    target: (_number(current[key]) if current.get(key) is not None else None)
                    for target, key in (
                        ("open_po_qty", "open_qty"), ("pnfm_qty", "pnfm_qty"),
                        ("inbound_progress_qty", "inbound_progress_qty"),
                        ("inbound_completed_qty", "inbound_completed_qty"),
                    )
                },
                "replenishment": V3ReplenishmentBaseInput(
                    order_date=parsed_as_of,
                    cash_policy=cash_policy,
                    shortage_policy=shortage_policy,
                    on_hand_qty=max(0.0, on_hand),
                    upstream_available_qty=max(0.0, upstream_available),
                    in_transit_qty=max(0.0, _number(current.get("transit_qty"))),
                    unreceived_qty=max(0.0, _number(current.get("incoming_qty"))),
                    holding_qty=0.0,
                ),
            }
        )

    mark("sku_inputs")
    timings["total"] = round(perf_counter() - started, 3)
    digest_payload = {
        "entity": code,
        "as_of": as_of,
        "date_basis": SOURCE_DATE_BASIS,
        "classification_basis": "CURRENT_PRODUCT_MASTER_INDEPENDENT_OF_PAID_SALES",
        "classification_master_scope": "FULL_PRODUCT_MASTER",
        "demand_window": {
            "date_from": demand_start.isoformat(),
            "date_to": fetch_end.isoformat(),
            "completed_periods": REQUIRED_COMPLETED_PERIODS,
            "period_days": PERIOD_DAYS,
            "calendar_days": REQUIRED_COMPLETED_PERIODS * PERIOD_DAYS,
        },
        "unreceived_window": unreceived_window,
        "product_identity": identity_resolver.audit(),
        "sku_scope": sku_scope_audit,
        "season_factor_artifact": {
            "version": season_factor_artifact.get("version"),
            "checksum": season_factor_artifact.get("checksum"),
            "status": season_factor_artifact.get("status"),
        },
        "counts": source_counts,
        "sales_rows": len(sales_rows),
        "demand_source_policy": LEDGER_POLICY,
        "ledger_sales_sha256": ledger_meta["sha256"],
        "product_rows": len(product_rows),
        "lead_time_audit": {
            **lead_time_audit,
            "source": {
                key: value
                for key, value in dict(lead_time_audit["source"]).items()
                if key != "calculated_at"
            },
        },
        "inventory_position_policy": _V3_INVENTORY_POSITION_POLICY,
    }
    snapshot_id = "v3_" + hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return rows, {
        "snapshot_id": snapshot_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "performance_seconds": timings,
        "date_basis": SOURCE_DATE_BASIS,
        "classification_basis": "CURRENT_PRODUCT_MASTER_INDEPENDENT_OF_PAID_SALES",
        "classification_master_scope": "FULL_PRODUCT_MASTER",
        "demand_window": {
            "date_from": demand_start.isoformat(),
            "date_to": fetch_end.isoformat(),
            "completed_periods": REQUIRED_COMPLETED_PERIODS,
            "period_days": PERIOD_DAYS,
            "calendar_days": REQUIRED_COMPLETED_PERIODS * PERIOD_DAYS,
        },
        "unreceived_window": unreceived_window,
        "product_identity": identity_resolver.audit(),
        "sku_scope": sku_scope_audit,
        "source_counts": {**source_counts, "ledger_daily_sales": len(ledger_rows),
                          "revenue_sales": len(sales_rows), "products": len(product_rows)},
        "demand_source": ledger_meta,
        "revenue_source": dict(season_meta),
        "revenue_unmatched_demand_sku_count": len(set(sales_by_sku) - set(grades)),
        "season_factor_artifact": season_factor_artifact,
        "inventory_source": dict(inventory_meta),
        "inventory_position_policy": _V3_INVENTORY_POSITION_POLICY,
        "lead_time_audit": lead_time_audit,
        "demand_filter": "stock-in-out: OUT-SALE and OUT-SALE (ONLINE); qty_out > 0; other ledger types excluded",
        "new_sku_rule": (
            "lifetime first paid sale is unavailable from the 91-day web demand window; "
            "trace is omitted and HOLT uses phi=0.90 for every SKU"
        ),
        "recent_demand_guard": "no undocumented recent-sales hold or Croston recent-demand cap",
        "season_factor_weighting": (
            "rolling 24 completed calendar months ending at the latest completed month; "
            "earlier 12 months weight=1, latest 12 months weight=2"
        ),
        "grade_rule": (
            f"13-week revenue Pareto {GRADE_CUTOFF:.0%} (CORE/GENERAL)"
        ),
    }


__all__ = [
    "SEASON_FACTOR_VERSION",
    "SOURCE_DATE_BASIS",
    "build_order_logic_v3_source",
    "completed_month_window",
    "last_completed_sunday",
]
