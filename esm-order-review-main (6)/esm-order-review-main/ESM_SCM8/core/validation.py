from __future__ import annotations

import re
from datetime import timedelta

import numpy as np
import pandas as pd
from core.session import SessionContext, ensure_session_context

from core.common import (
    _DEFAULT_EUR_KRW_RATE,
    DATA_SPECS,
    DEFAULT_LEAD_TIME_DAYS,
    DISCONTINUED_SKU_PATTERN,
    korea_today,
    ORDER_REVIEW_EXCLUDED_BRANDS,
    SAMPLE_SKU_PATTERN,
    STANDARD_TRANSPORT_MODES,
    TRANSPORT_MODES,
)
from core.lead_times import analysis_lead_time_settings
from core import inventory as inventory_mod, kpi as kpi_mod, loaders as loaders_mod, order_review as order_review_mod, preprocess as preprocess_mod, sales as sales_mod, transport as transport_mod

def selected_transport_modes(settings: dict | None) -> list[str]:
    modes = list((settings or {}).get("modes", TRANSPORT_MODES))
    selected = [mode for mode in modes if mode in TRANSPORT_MODES]
    return selected or TRANSPORT_MODES.copy()


def all_transport_modes_selected(settings: dict | None) -> bool:
    return set(selected_transport_modes(settings)) == set(TRANSPORT_MODES)


def _business_excluded_brand_mask(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().isin(ORDER_REVIEW_EXCLUDED_BRANDS)


def apply_business_brand_exclusion(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    out = df.copy()
    brand_col = kpi_mod.find_column(out, ["브랜드", "브랜드명", "Brand", "brand", "brandname"])
    if brand_col is None:
        return out
    return out[~_business_excluded_brand_mask(out[brand_col])].copy()


def apply_common_filters(
    df: pd.DataFrame,
    settings: dict,
    include_brand: bool = True,
    include_transport: bool = True,
) -> pd.DataFrame:
    out = apply_business_brand_exclusion(df)
    if include_brand and settings.get("brand", "전체") != "전체" and "브랜드" in out.columns:
        selected_brand = str(settings.get("brand", "전체")).strip()
        out = out[out["브랜드"].astype(str).str.strip().eq(selected_brand)]
    if include_transport and "운송수단" in out.columns:
        out = out[out["운송수단"].isin(selected_transport_modes(settings))]
    return out


def _brand_options_from_series(series: pd.Series) -> list[str]:
    if series is None:
        return []
    cleaned = series.dropna().astype(str).str.strip()
    cleaned = cleaned[cleaned.ne("") & cleaned.ne("-") & cleaned.str.lower().ne("nan")]
    cleaned = cleaned[~cleaned.isin(ORDER_REVIEW_EXCLUDED_BRANDS)]
    return sorted(cleaned.drop_duplicates().tolist())


def brand_options_from_df(df: pd.DataFrame) -> list[str]:
    if df is None or df.empty:
        return []
    brand_col = kpi_mod.find_column(df, ["브랜드", "브랜드명", "Brand", "brand", "brandname"])
    if brand_col is None:
        return []
    return _brand_options_from_series(df[brand_col])


def raw_brand_filter_options(context: SessionContext | None = None) -> list[str]:
    context = ensure_session_context(context)
    sig = loaders_mod.uploaded_data_signature(context)
    cache = context.brand_options_cache
    if sig in cache:
        return cache[sig]
    options: set[str] = set()
    sources = [
        lambda: preprocess_mod.prepare_eu_stock(inventory_mod.get_eu_stock(context)),
        lambda: inventory_mod.get_hq_eu_stock(context),
        lambda: sales_mod.get_sales_detail(context),
        lambda: transport_mod.get_shipping(context=context),
    ]
    for load_source in sources:
        try:
            options.update(brand_options_from_df(load_source()))
        except Exception:
            continue
    result = sorted(options)
    cache[sig] = result
    return result


def brand_filter_options(settings: dict, context: SessionContext | None = None) -> list[str]:
    options = raw_brand_filter_options(context)
    return ["전체"] + options


def apply_brand_filter(df: pd.DataFrame, settings: dict) -> pd.DataFrame:
    selected_brand = str(settings.get("brand", "전체")).strip()
    out = apply_business_brand_exclusion(df)
    if selected_brand == "전체" or out.empty or "브랜드" not in out.columns:
        return out
    return out[out["브랜드"].astype(str).str.strip().eq(selected_brand)]


def _transport_mode_match_mask(series: pd.Series, modes: list[str]) -> pd.Series:
    text = series.fillna("").astype(str)
    mask = pd.Series(False, index=series.index)
    for mode in modes:
        if mode == "트럭":
            mask = mask | text.str.contains("트럭|트럭킹", na=False)
        else:
            mask = mask | text.str.contains(mode, na=False)
    return mask


def apply_transport_filter(df: pd.DataFrame, settings: dict) -> pd.DataFrame:
    if df is None or df.empty or all_transport_modes_selected(settings):
        return df.copy()
    out = df.copy()
    modes = selected_transport_modes(settings)
    recommendation_col = order_review_mod.first_existing_col(out, ["운송수단 검토안", "운송 검토안", "추천 운송수단", "권장 대응 / 운송 검토안"])
    if recommendation_col is not None:
        return out[_transport_mode_match_mask(out[recommendation_col], modes)]
    if "운송수단" in out.columns:
        return out[out["운송수단"].isin(modes)]
    return out


def apply_order_review_filters(df: pd.DataFrame, settings: dict) -> pd.DataFrame:
    return apply_transport_filter(apply_brand_filter(df, settings), settings)


def apply_raw_brand_filter(df: pd.DataFrame, settings: dict | None) -> pd.DataFrame:
    selected_brand = str((settings or {}).get("brand", "전체")).strip()
    out = apply_business_brand_exclusion(df)
    if selected_brand == "전체" or out.empty:
        return out
    brand_col = kpi_mod.find_column(df, ["브랜드", "브랜드명", "Brand", "brand", "brandname"])
    if brand_col is None:
        return out
    return out[out[brand_col].astype(str).str.strip().eq(selected_brand)]


def apply_raw_transport_filter(df: pd.DataFrame, settings: dict | None) -> pd.DataFrame:
    if df is None or df.empty or all_transport_modes_selected(settings):
        return df.copy()
    modes = selected_transport_modes(settings)
    parsed_modes = df.apply(transport_mod.parse_transport_mode_from_row, axis=1)
    return df[parsed_modes.isin(modes)].copy()


def add_sku_exclusion_flags(df: pd.DataFrame, settings: dict) -> pd.DataFrame:
    out = df.copy()
    name = out["상품명"].astype(str) if "상품명" in out.columns else pd.Series([""] * len(out), index=out.index)
    status_col = kpi_mod.find_column(out, ["제품상태", "상품상태", "상태", "판매상태", "사용여부", "status"])
    status = out[status_col].astype(str) if status_col is not None else pd.Series([""] * len(out), index=out.index)

    use_name_based_exclusion = bool(settings.get("allow_name_based_sku_exclusion", False))
    sample_mask = (
        name.str.contains(SAMPLE_SKU_PATTERN, case=False, regex=True, na=False)
        if use_name_based_exclusion
        else pd.Series([False] * len(out), index=out.index)
    )
    discontinued_mask = (
        status.str.contains(DISCONTINUED_SKU_PATTERN, case=False, regex=True, na=False)
        | (
            name.str.contains(DISCONTINUED_SKU_PATTERN, case=False, regex=True, na=False)
            if use_name_based_exclusion
            else pd.Series([False] * len(out), index=out.index)
        )
    )

    out["제품상태"] = status
    out["샘플 SKU"] = sample_mask
    out["단종 SKU"] = discontinued_mask
    out["제외 SKU"] = (
        (settings.get("exclude_sample", True) & out["샘플 SKU"])
        | (settings.get("exclude_discontinued", True) & out["단종 SKU"])
    )
    out["제외유형"] = np.select(
        [out["샘플 SKU"] & out["단종 SKU"], out["샘플 SKU"], out["단종 SKU"]],
        ["샘플/FOC/무상/단종", "샘플/FOC/무상", "단종"],
        default="",
    )
    out["제외사유"] = np.where(
        out["제외 SKU"],
        "상품코드 기준 계산에서 제외 플래그가 지정된 SKU는 제외",
        "",
    )
    return out


def apply_sku_exclusion_filters(df: pd.DataFrame, settings: dict) -> pd.DataFrame:
    out = add_sku_exclusion_flags(df, settings)
    if settings.get("exclude_sample", True) or settings.get("exclude_discontinued", True):
        out = out[~out["제외 SKU"]]
    return out


def validation_df(context: SessionContext | None = None) -> pd.DataFrame:
    rows = []
    sample_map = {
        "eu_stock": loaders_mod.sample_eu_stock,
        "hq_eu_stock": loaders_mod.sample_hq_eu_stock,
        "sales_detail": loaders_mod.sample_sales_detail,
        "hq_to_eu_sales_detail": loaders_mod.sample_hq_to_eu_sales_detail,
        "open_po": loaders_mod.sample_open_po,
        "shipping": loaders_mod.sample_shipping,
        "past_sales": loaders_mod.sample_past_sales,
    }
    for key, spec in DATA_SPECS.items():
        df = loaders_mod.get_data_or_sample(key, sample_map[key], context)
        missing = [col for col in spec["required_columns"] if col not in df.columns]
        rows.append(
            {
                "데이터명": spec["name"],
                "필수 컬럼": "정상" if not missing else ", ".join(missing),
                "날짜 컬럼 인식": "있음" if any("일" in str(col) or "ETA" in str(col) for col in df.columns) else "없음",
                "숫자 컬럼 인식": len(df.select_dtypes(include="number").columns),
                "행 수": len(df),
            }
        )

    review = order_review_mod.order_review_df(default_settings_for_validation(), context=context)
    rows.append(
        {
            "데이터명": "발주 검토 계산",
            "필수 컬럼": "정상",
            "날짜 컬럼 인식": "고갈 예상일 계산",
            "숫자 컬럼 인식": len(review.select_dtypes(include="number").columns),
            "행 수": len(review),
        }
    )
    return pd.DataFrame(rows)


def default_settings_for_validation(entity_code: str = "PL") -> dict:
    normalized_entity_code = str(entity_code or "PL").strip().upper()
    default_base_date = korea_today()
    default_period = (default_base_date - timedelta(days=91), default_base_date - timedelta(days=1))
    entity_lead_times = analysis_lead_time_settings(normalized_entity_code)
    return {
        "entity_code": normalized_entity_code,
        "currency_code": "USD" if normalized_entity_code == "USA" else "EUR",
        "base_date": default_base_date,
        "period_start": default_period[0],
        "period_end": default_period[1],
        "recent_days": 30,
        "safety_months": 3.0,
        "sku_shortage_threshold_pct": 2.5,
        "sku_overstock_threshold_pct": 3.0,
        "demand_source": "재고파일 PA+CA 판매수량 기준",
        "brand": "전체",
        "modes": list(entity_lead_times["modes"]),
        "include_eu_pl_sales": True,
        "include_etc_sales": False,
        "exclude_sample": True,
        "exclude_discontinued": True,
        "allow_name_based_sku_exclusion": False,
        "include_inbound_po_in_coverage": False,
        "include_hq_eu_in_order_coverage": False,
        **entity_lead_times,
        "applied_lead_times": transport_mod.applied_lead_times(entity_lead_times),
        "surge_threshold": 0.5,
        "drop_threshold": -0.5,
        "dead_threshold": -0.7,
        "min_sales_qty": 30,
        "min_monthly_sales_for_order_review": 1.0,
        "stock_increase_threshold": 0.3,
        "stock_adjustment_factor": 1.15,
        "eur_krw_rate": _DEFAULT_EUR_KRW_RATE,
    }

