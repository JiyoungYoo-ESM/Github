from __future__ import annotations

import ast
import calendar
import re
from datetime import timedelta

import numpy as np
import pandas as pd
from core.session import SessionContext, ensure_session_context

from core.common import (
    _DEFAULT_EUR_KRW_RATE,
    _RAW_TRANSPORT_CANDIDATES,
    _SEA_CONTAINER_EUR_CANDIDATES,
    DEFAULT_LEAD_TIME_DAYS,
    STANDARD_TRANSPORT_MODES,
    TRACKED_SHIPPING_DEBUG_SKUS,
    TRANSPORT_MODES,
    TRANSPORT_REVIEW_REQUIRED,
)
from core.preprocess import product_sku_mask
from core.lead_times import (
    TRANSPORT_GROUP_DISPLAY_NAMES,
    lead_time_method,
    resolve_lead_time,
)
from datetime import datetime
from pathlib import Path
from core import inbound as inbound_mod, kpi as kpi_mod, loaders as loaders_mod, order_review as order_review_mod, preprocess as preprocess_mod, validation as validation_mod

def normalize_transport_code(value: object, entity_code: str = "PL") -> str:
    """Normalize a raw label to a stable transport code.

    UK air must include an explicit DIR/direct or T/S/transshipment marker.
    Generic UK ``AIR`` remains ``AIR`` and is rejected by the exact entity
    method lookup instead of silently receiving the PL air default.
    """

    text = str(value).strip()
    if not text:
        return ""
    upper = text.upper().replace("-", "_")
    compact = re.sub(r"[\s./·()]+", "_", upper).strip("_")

    if entity_code.strip().upper() == "UK":
        air_label = "AIR" in compact or "항공" in text
        if (
            compact in {"AIR_DIR", "AIR_DIRECT", "DIR", "DIRECT"}
            or "직항" in text
            or (
                air_label
                and (
                    re.search(r"(^|_)DIR($|_)", compact) is not None
                    or "DIRECT" in compact
                )
            )
        ):
            return "AIR_DIR"
        if (
            compact in {"AIR_TS", "AIR_T_S", "TS", "T_S", "TRANSSHIPMENT"}
            or "환적" in text
            or (
                air_label
                and (
                    re.search(r"(^|_)(TS|T_S)($|_)", compact) is not None
                    or "TRANSSHIP" in compact
                )
            )
        ):
            return "AIR_TS"

    if re.search(r"(해운|헤운|헤은)", text) or re.search(r"(?<![A-Z])(OCEAN|SEA)(?![A-Z])", upper):
        return "OCEAN"
    if re.search(r"(트럭|트럭킹)", text) or re.search(r"(?<![A-Z])(TRUCKING|TRUCK)(?![A-Z])", upper):
        return "TRUCKING"
    if "철송" in text or re.search(r"(?<![A-Z])RAIL(?![A-Z])", upper):
        return "RAIL"
    if "항공" in text or re.search(r"(?<![A-Z])AIR(?![A-Z])", upper):
        return "AIR"
    return ""


def normalize_transport_mode(value: object) -> str:
    text = str(value).strip()
    if text in STANDARD_TRANSPORT_MODES:
        return text
    code = normalize_transport_code(text)
    method = lead_time_method("PL", code)
    if method is not None:
        return TRANSPORT_GROUP_DISPLAY_NAMES[method.transport_group]
    match = re.search(r"(해운|헤운|헤은|항공|철송|트럭)", text)
    if not match:
        return ""
    mode = match.group(1)
    return "해운" if mode in {"헤운", "헤은"} else mode


def raw_transport_mode_from_row(row: pd.Series) -> str:
    for col in _RAW_TRANSPORT_CANDIDATES:
        if col in row.index:
            text = str(row[col]).strip()
            if text:
                return text
    return ""


def _extract_raw_transport_series(df: pd.DataFrame) -> pd.Series:
    result = pd.Series("", index=df.index, dtype=str)
    for col in _RAW_TRANSPORT_CANDIDATES:
        if col in df.columns:
            col_values = df[col].astype(str).str.strip()
            keep = result.ne("") | col_values.eq("")
            result = result.where(keep, col_values)
    return result


def parse_transport_mode_from_row(row: pd.Series) -> str:
    mode = normalize_transport_mode(raw_transport_mode_from_row(row))
    return mode if mode in STANDARD_TRANSPORT_MODES else TRANSPORT_REVIEW_REQUIRED


def recognized_transport_mask(df: pd.DataFrame) -> pd.Series:
    if "운송수단" not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    return df["운송수단"].astype(str).isin(STANDARD_TRANSPORT_MODES)


def _resolved_lead_times_by_code(
    settings: dict | None,
    entity_code: str,
) -> dict[str, int]:
    settings = settings or {}
    configured_by_code = settings.get("lead_times_by_code")
    if isinstance(configured_by_code, dict):
        return {
            str(code).strip().upper(): int(days)
            for code, days in configured_by_code.items()
            if lead_time_method(entity_code, code) is not None
        }

    overrides = settings.get("lead_time_overrides")
    overrides = overrides if isinstance(overrides, dict) else {}
    methods = [
        method
        for method in (
            lead_time_method(entity_code, code)
            for code in ("OCEAN", "TRUCKING", "RAIL", "AIR", "AIR_DIR", "AIR_TS")
        )
        if method is not None
    ]
    methods_per_group: dict[str, int] = {}
    for method in methods:
        methods_per_group[method.transport_group] = methods_per_group.get(method.transport_group, 0) + 1

    legacy = settings.get("lead_times")
    legacy = legacy if isinstance(legacy, dict) else {}
    result: dict[str, int] = {}
    for method in methods:
        override = overrides.get(method.transport_code)
        if override is not None:
            result[method.transport_code] = int(override)
            continue
        legacy_mode = TRANSPORT_GROUP_DISPLAY_NAMES[method.transport_group]
        if methods_per_group[method.transport_group] == 1 and legacy_mode in legacy:
            result[method.transport_code] = int(legacy[legacy_mode])
            continue
        resolved = resolve_lead_time(entity_code, method.transport_code)
        if resolved is not None:
            result[method.transport_code] = resolved
    return result


def prepare_shipping(
    shipping_df: pd.DataFrame,
    settings: dict | None = None,
    context: SessionContext | None = None,
) -> pd.DataFrame:
    df = shipping_df.copy()
    raw_eur_amount_col = kpi_mod.find_column(df, _SEA_CONTAINER_EUR_CANDIDATES)
    raw_eur_amount = df[raw_eur_amount_col].copy() if raw_eur_amount_col is not None else None

    rename_candidates = {
        "SKU": ["SKU", "상품코드", "품목코드", "아이템코드", "itemcode"],
        "바코드": ["바코드", "barcode", "ean", "jan"],
        "수량": ["수량", "운송수량", "출고수량", "입고수량", "qty"],
        "입고가(KRW)": ["입고가(KRW)", "입고가"],
        "출고일": ["출고일", "출고 일자", "선적일", "발송일", "shipdate"],
        "리드타임": ["리드타임", "적용 리드타임", "leadtime"],
        "ETA": ["ETA", "예상도착일", "입고예정일", "도착예정일"],
        # Only explicit actual-date labels are accepted.  A generic "입고일"
        # can mean a plan date in legacy workbooks and is deliberately omitted.
        "실제 도착일": ["실제 도착일", "실제 입고일"],
        "운송수단": ["운송수단", "운송 수단", "배송수단", "mode"],
        "Invoice 비고": ["Invoice 비고", "INVOICE 비고", "Invoice비고", "인보이스 비고", "비고", "remark", "remarks"],
        "브랜드": ["브랜드", "brand"],
        "상품명": ["상품명", "제품명", "품목명", "itemname"],
        "위험도": ["위험도", "리스크", "상태", "risk"],
        "목적지": ["목적지", "도착지", "destination"],
        "컨테이너번호": ["컨테이너번호", "컨테이너 번호", "container", "containerno"],
    }

    rename_map = {}
    for target, candidates in rename_candidates.items():
        if target not in df.columns:
            source = kpi_mod.find_column(df, candidates)
            if source is not None:
                rename_map[source] = target
    if rename_map:
        df = df.rename(columns=rename_map)
    if raw_eur_amount is not None:
        df["금액"] = kpi_mod.to_number_series(raw_eur_amount)

    required_defaults = {
        "SKU": "",
        "바코드": "",
        "수량": 0,
        "입고가(KRW)": 0,
        "출고일": "",
        "리드타임": 0,
        "ETA": "",
        "ETA 출처": "",
        "실제 도착일": "",
        "운송수단": "",
        "운송수단 출처": "",
        "Invoice 비고": "",
        "브랜드": "-",
        "상품명": "-",
        "위험도": "안정",
        "목적지": "",
        "컨테이너번호": "",
    }
    for col, default in required_defaults.items():
        if col not in df.columns:
            df[col] = default

    df["원본 운송수단"] = _extract_raw_transport_series(df)
    df["SKU"] = preprocess_mod.clean_identifier_series(df["SKU"])
    df["바코드"] = preprocess_mod.clean_identifier_series(df["바코드"])
    entity_code = str((settings or {}).get("entity_code") or "PL").strip().upper()
    df["운송수단 코드"] = df["원본 운송수단"].map(
        lambda value: normalize_transport_code(value, entity_code)
    )
    method_by_code = {
        code: lead_time_method(entity_code, code)
        for code in df["운송수단 코드"].astype(str).unique()
    }
    df["운송수단"] = df["운송수단 코드"].map(
        lambda code: (
            TRANSPORT_GROUP_DISPLAY_NAMES[method.transport_group]
            if (method := method_by_code.get(str(code))) is not None
            else ""
        )
    )
    recognized_mode = df["운송수단 코드"].map(
        lambda code: method_by_code.get(str(code)) is not None
    ).fillna(False).astype(bool)
    df.loc[~recognized_mode, "운송수단"] = TRANSPORT_REVIEW_REQUIRED
    df["운송수단 처리상태"] = np.where(recognized_mode, "정상", TRANSPORT_REVIEW_REQUIRED)
    transport_source = df["운송수단 출처"].fillna("").astype(str).str.strip()
    inferred_source = np.where(
        df["원본 운송수단"].fillna("").astype(str).str.strip().ne(""),
        "원본/Invoice 비고",
        "",
    )
    df["운송수단 출처"] = transport_source.where(
        transport_source.ne(""),
        pd.Series(inferred_source, index=df.index),
    )
    source_name = ensure_session_context(context).uploaded_files.get("shipping", "sample_shipping")
    df["원본 파일명"] = source_name
    df["수량"] = kpi_mod.to_number_series(df["수량"])
    df["입고가(KRW)"] = kpi_mod.to_number_series(df["입고가(KRW)"])
    df["리드타임"] = kpi_mod.to_number_series(df["리드타임"])
    parsed_ship_date = kpi_mod.parse_date_series(df["출고일"])
    parsed_original_eta = kpi_mod.parse_date_series(df["ETA"])
    parsed_actual_arrival = kpi_mod.parse_date_series(df["실제 도착일"])
    lead_times_by_code = _resolved_lead_times_by_code(settings, entity_code)
    transport_lead_days = pd.to_numeric(
        df["운송수단 코드"].map(lead_times_by_code),
        errors="coerce",
    )
    estimated_eta = parsed_ship_date + pd.to_timedelta(transport_lead_days, unit="D")
    # Confirmed source ETA wins even if a transport label needs manual review.
    # Lead-time calculation is only allowed for an exact supported method.
    final_eta = parsed_actual_arrival.where(
        parsed_actual_arrival.notna(),
        parsed_original_eta.where(
            parsed_original_eta.notna(),
            estimated_eta.where(recognized_mode),
        ),
    )
    df["운송 L/T"] = transport_lead_days.astype("Int64")
    df["리드타임"] = transport_lead_days.astype("Int64")
    source_eta_label = df["ETA 출처"].fillna("").astype(str).str.strip().replace("", "원본ETA")
    df["ETA 구분"] = np.select(
        [
            parsed_actual_arrival.notna(),
            parsed_original_eta.notna(),
            recognized_mode & estimated_eta.notna(),
        ],
        ["실제입고일", source_eta_label, "적용LT계산ETA"],
        default=TRANSPORT_REVIEW_REQUIRED,
    )
    df["ETA 출처"] = np.select(
        [
            parsed_actual_arrival.notna(),
            parsed_original_eta.notna(),
            recognized_mode & estimated_eta.notna(),
        ],
        ["실제 도착일", source_eta_label, "출고일+사용자입력L/T"],
        default=TRANSPORT_REVIEW_REQUIRED,
    )
    df["ETA"] = final_eta.dt.strftime("%Y-%m-%d").fillna("")
    df["실제 도착일"] = parsed_actual_arrival.dt.strftime("%Y-%m-%d").fillna("")
    df["출고일"] = parsed_ship_date.dt.strftime("%Y-%m-%d").fillna(df["출고일"].astype(str))
    return df


def get_shipping(settings: dict | None = None, context: SessionContext | None = None) -> pd.DataFrame:
    return prepare_shipping(loaders_mod.get_data_or_sample("shipping", loaders_mod.sample_shipping, context), settings=settings, context=context)


def unrecognized_transport_report_df(settings: dict | None = None, context: SessionContext | None = None) -> pd.DataFrame:
    shipping = get_shipping(settings, context)
    columns = [
        "원본값", "상품코드", "상품명", "브랜드", "수량", "출고일", "예상 입고일",
        "운송수단 코드", "표준 운송수단", "운송수단 출처", "ETA 구분", "ETA 출처",
        "적용 리드타임", "원본 파일명", "처리상태", "확인필요 사유",
        "권장 확인 액션", "처리 기준",
    ]
    if shipping.empty or "운송수단 처리상태" not in shipping.columns:
        return pd.DataFrame(columns=columns)
    invalid = shipping[
        shipping["운송수단 처리상태"].astype(str).eq(TRANSPORT_REVIEW_REQUIRED)
        & product_sku_mask(shipping.get("SKU", pd.Series("", index=shipping.index)))
    ].copy()
    if invalid.empty:
        return pd.DataFrame(columns=columns)
    eta_text = invalid.get("ETA", pd.Series("", index=invalid.index)).fillna("").astype(str).str.strip()
    has_eta = pd.to_datetime(eta_text, errors="coerce").notna()
    configured_methods = list((settings or {}).get("lead_time_methods") or [])
    method_labels = [
        str(method.get("display_name") or method.get("label") or "").strip()
        for method in configured_methods
        if str(method.get("display_name") or method.get("label") or "").strip()
    ]
    allowed_label = "/".join(dict.fromkeys(method_labels)) or "선택 법인 표준 운송수단"
    api_raw = invalid.get(
        "운송수단 API 원본값",
        pd.Series("", index=invalid.index, dtype=object),
    ).fillna("").astype(str).str.strip()
    original_raw = invalid.get(
        "원본 운송수단",
        pd.Series("", index=invalid.index, dtype=object),
    )
    review_raw = api_raw.where(api_raw.ne(""), original_raw)
    out = pd.DataFrame(
        {
            "원본값": review_raw,
            "상품코드": invalid.get("SKU", ""),
            "상품명": invalid.get("상품명", ""),
            "브랜드": invalid.get("브랜드", ""),
            "수량": pd.to_numeric(invalid.get("수량", 0), errors="coerce").fillna(0),
            "출고일": invalid.get("출고일", ""),
            "예상 입고일": eta_text,
            "운송수단 코드": invalid.get("운송수단 코드", ""),
            "표준 운송수단": "확인필요",
            "운송수단 출처": invalid.get("운송수단 출처", ""),
            "ETA 구분": invalid.get("ETA 구분", ""),
            "ETA 출처": invalid.get("ETA 출처", ""),
            "적용 리드타임": pd.to_numeric(invalid.get("리드타임", 0), errors="coerce"),
            "원본 파일명": invalid.get("원본 파일명", ""),
            "처리상태": TRANSPORT_REVIEW_REQUIRED,
            "확인필요 사유": np.where(
                has_eta,
                "입고 예정일은 확인되었으나 운송수단을 분류할 수 없습니다.",
                "운송수단과 입고 예정일을 모두 확인할 수 없습니다.",
            ),
            "권장 확인 액션": f"법인 표준 운송수단({allowed_label}) 확인",
            "처리 기준": np.where(
                has_eta,
                "입고예정 합계에는 확인필요로 반영하고 운송수단별 집계에서는 분리",
                "입고 예정일이 없어 입고예정 집계에서 제외",
            ),
        }
    )
    return out[columns].reset_index(drop=True)


def applied_lead_times(settings: dict | None) -> dict[str, int]:
    lead_times = DEFAULT_LEAD_TIME_DAYS if settings is None else (settings.get("lead_times") or {})
    return {
        mode: int(lead_times[mode])
        for mode in TRANSPORT_MODES
        if mode in lead_times
    }


def lead_time_summary(settings: dict) -> str:
    lead_times = settings.get("lead_times") or {}
    parts = []
    for mode in TRANSPORT_MODES:
        if mode not in lead_times:
            continue
        lead_days = int(lead_times[mode])
        parts.append(f"{mode} {lead_days}일")
    return " / ".join(parts) if parts else "적용 가능한 해외 운송 리드타임 없음"


def transport_recommendation_by_depletion_days(
    depletion_days: object,
    lead_times: dict | None,
    *,
    order_needed: bool = True,
    lead_times_by_code: dict[str, int] | None = None,
    entity_code: str | None = None,
) -> tuple[str, int, str]:
    if not order_needed:
        return "● 발주불필요", 0, "안전재고 충족"

    days = pd.to_numeric(depletion_days, errors="coerce")
    if pd.isna(days):
        return "판단불가", 0, "고갈일 확인 필요"
    days = float(days)

    # Preserve the established PL thresholds and labels, but require all three
    # supported values instead of filling a missing entity method from PL.
    legacy = DEFAULT_LEAD_TIME_DAYS if lead_times is None else lead_times
    if lead_times_by_code is not None and (entity_code or "").upper() == "PL":
        legacy = {
            "항공": lead_times_by_code.get("AIR"),
            "철송": lead_times_by_code.get("RAIL"),
            "해운": lead_times_by_code.get("OCEAN"),
        }
    if all(legacy.get(mode) is not None for mode in ("항공", "철송", "해운")):
        air_days = int(legacy["항공"])
        rail_days = int(legacy["철송"])
        sea_days = int(legacy["해운"])
        if days <= air_days:
            return "① 항공 긴급", air_days, "고갈까지 ≤ 항공 L/T일"
        if days <= rail_days:
            return "② 항공", air_days, "항공 L/T < 고갈까지 ≤ 철송 L/T"
        if days <= sea_days:
            return "③ 철송", rail_days, "철송 L/T < 고갈까지 ≤ 해운 L/T"
        return "④ 해운 가능", sea_days, "해운 L/T < 고갈까지"

    candidates: list[tuple[str, str, int]] = []
    if lead_times_by_code is not None:
        canonical_entity = str(entity_code or "").strip().upper()
        for transport_code in ("AIR_DIR", "AIR_TS", "AIR", "RAIL", "OCEAN"):
            if transport_code not in lead_times_by_code:
                continue
            method = lead_time_method(canonical_entity, transport_code)
            if method is None:
                continue
            candidates.append(
                (
                    transport_code,
                    method.display_name,
                    int(lead_times_by_code[transport_code]),
                )
            )
    else:
        for transport_code, display_name, legacy_mode in (
            ("AIR", "항공", "항공"),
            ("RAIL", "철송", "철송"),
            ("OCEAN", "해운", "해운"),
        ):
            if legacy_mode in legacy:
                candidates.append(
                    (transport_code, display_name, int(legacy[legacy_mode]))
                )

    candidates.sort(key=lambda item: (item[2], ("AIR_DIR", "AIR_TS", "AIR", "RAIL", "OCEAN").index(item[0])))
    if not candidates:
        return "판단불가", 0, "선택 법인에 지원되는 운송수단 없음"

    fastest = candidates[0]
    if days <= fastest[2]:
        return f"① {fastest[1]} 긴급", fastest[2], f"고갈까지 ≤ {fastest[1]} L/T일"

    feasible = [candidate for candidate in candidates if candidate[2] < days]
    selected = feasible[-1] if feasible else fastest
    selected_index = candidates.index(selected)
    number_labels = ("②", "③", "④", "⑤", "⑥")
    number = number_labels[min(selected_index, len(number_labels) - 1)]
    suffix = " 가능" if selected == candidates[-1] else ""
    return (
        f"{number} {selected[1]}{suffix}",
        selected[2],
        f"{selected[1]} L/T < 고갈까지",
    )


def get_past_sales(context: SessionContext | None = None) -> pd.DataFrame:
    return loaders_mod.get_data_or_sample("past_sales", loaders_mod.sample_past_sales, context)


def _shipping_debug_qty_info(df: pd.DataFrame) -> dict[str, object]:
    qty_col = kpi_mod.find_column(df, ["수량", "운송수량", "출고수량", "입고수량", "qty", "QTY"])
    if qty_col is None:
        return {"수량 추정 컬럼": "없음", "수량 합계": "-", "숫자 변환 실패 행 수": "-"}
    raw_qty = df[qty_col]
    numeric_qty = kpi_mod.to_number_series(raw_qty)
    return {
        "수량 추정 컬럼": qty_col,
        "수량 합계": f"{numeric_qty.sum():,.0f}",
        "숫자 변환 실패 행 수": f"{kpi_mod.number_conversion_failure_count(raw_qty):,}",
    }


def _standardize_shipping_for_debug(shipping_df: pd.DataFrame) -> pd.DataFrame:
    df = shipping_df.copy()
    raw_eur_amount_col = kpi_mod.find_column(df, _SEA_CONTAINER_EUR_CANDIDATES)
    raw_eur_amount = df[raw_eur_amount_col].copy() if raw_eur_amount_col is not None else None
    rename_candidates = {
        "SKU": ["SKU", "상품코드", "품목코드", "아이템코드", "itemcode"],
        "바코드": ["바코드", "barcode", "ean", "jan"],
        "수량": ["수량", "운송수량", "출고수량", "입고수량", "qty"],
        "입고가(KRW)": ["입고가(KRW)", "입고가"],
        "출고일": ["출고일", "출고 일자", "선적일", "발송일", "shipdate"],
        "리드타임": ["리드타임", "적용 리드타임", "leadtime"],
        "ETA": ["ETA", "예상도착일", "입고예정일", "도착예정일"],
        "운송수단": ["운송수단", "운송 수단", "배송수단", "mode"],
        "Invoice 비고": ["Invoice 비고", "INVOICE 비고", "Invoice비고", "인보이스 비고", "비고", "remark", "remarks"],
        "브랜드": ["브랜드", "brand"],
        "상품명": ["상품명", "제품명", "품목명", "itemname"],
        "위험도": ["위험도", "리스크", "상태", "risk"],
        "목적지": ["목적지", "도착지", "destination"],
        "컨테이너번호": ["컨테이너번호", "컨테이너 번호", "container", "containerno"],
    }
    rename_map = {}
    for target, candidates in rename_candidates.items():
        if target not in df.columns:
            source = kpi_mod.find_column(df, candidates)
            if source is not None:
                rename_map[source] = target
    if rename_map:
        df = df.rename(columns=rename_map)
    if raw_eur_amount is not None:
        df["금액"] = kpi_mod.to_number_series(raw_eur_amount)
    required_defaults = {
        "SKU": "",
        "바코드": "",
        "수량": 0,
        "입고가(KRW)": 0,
        "출고일": "",
        "리드타임": 0,
        "ETA": "",
        "운송수단": "",
        "Invoice 비고": "",
        "브랜드": "-",
        "상품명": "-",
        "위험도": "안정",
        "목적지": "",
        "컨테이너번호": "",
    }
    for col, default in required_defaults.items():
        if col not in df.columns:
            df[col] = default
    return df


def _shipping_debug_sku_key(value: object) -> str:
    return str(value).strip()


def _shipping_debug_sku_keys(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _shape_text(shape: object) -> str:
    if isinstance(shape, tuple) and len(shape) >= 2:
        return f"({shape[0]:,}, {shape[1]:,})"
    return str(shape or "-")


def _fmt_debug_number(value: object) -> str:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return "-"
    return f"{float(parsed):,.0f}"


def _value_counts_table(series: pd.Series, value_col: str, count_col: str = "행 수", top: int | None = None) -> pd.DataFrame:
    counts = series.value_counts(dropna=False)
    if top is not None:
        counts = counts.head(top)
    out = counts.reset_index()
    out.columns = [value_col, count_col]
    return out


def session_cache_inventory_df() -> pd.DataFrame:
    cache = ensure_session_context(None).order_review_cache
    brand_cache = ensure_session_context(None).brand_options_cache
    return pd.DataFrame(
        [
            {
                "캐시": "_order_review_cache",
                "대상": "발주검토 DataFrame",
                "현재 건수": len(cache) if isinstance(cache, dict) else 0,
                "키 구성": "order_review_settings_signature(settings, excluded_only) + uploaded_data_signature() + logic version",
                "TTL": "세션 유지",
                "클리어 조건": "파일 재업로드, 디버그 버튼, 로직 버전 변경",
            },
            {
                "캐시": "order_review_manager_xlsx",
                "대상": "다운로드용 Excel bytes",
                "현재 건수": 0,
                "키 구성": "_ORDER_REVIEW_EXPORT_VERSION + order_review_settings_signature(settings)",
                "TTL": "세션 유지",
                "클리어 조건": "파일 재업로드, 디버그 버튼, export version 변경",
            },
            {
                "캐시": "_brand_options_cache",
                "대상": "브랜드 필터 옵션",
                "현재 건수": len(brand_cache) if isinstance(brand_cache, dict) else 0,
                "키 구성": "uploaded_data_signature()",
                "TTL": "세션 유지",
                "클리어 조건": "디버그 버튼 또는 파일 재업로드 후 자연 갱신",
            },
        ]
    )


def _shipping_debug_qty_series(df: pd.DataFrame, qty_col: str | None, *, robust: bool) -> pd.Series:
    if qty_col is None or qty_col not in df.columns:
        return pd.Series([0.0] * len(df), index=df.index)
    if robust:
        return kpi_mod.to_number_series(df[qty_col])
    return pd.to_numeric(df[qty_col], errors="coerce").fillna(0)


def _shipping_debug_tracking_df(df: pd.DataFrame, sku_col: str | None, qty: pd.Series, stage: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if sku_col is None or sku_col not in df.columns:
        return pd.DataFrame(
            [
                {"추적 SKU": sku, "단계": stage, "행 수": 0, "수량 합계": 0}
                for sku in TRACKED_SHIPPING_DEBUG_SKUS
            ]
        )
    sku_keys = _shipping_debug_sku_keys(df[sku_col])
    qty = pd.to_numeric(qty, errors="coerce").fillna(0)
    for sku in TRACKED_SHIPPING_DEBUG_SKUS:
        mask = sku_keys.eq(_shipping_debug_sku_key(sku))
        rows.append(
            {
                "추적 SKU": sku,
                "단계": stage,
                "행 수": int(mask.sum()),
                "수량 합계": float(qty.loc[mask].sum()),
            }
        )
    return pd.DataFrame(rows)


def _shipping_debug_sku_normalization_tracking(df: pd.DataFrame, sku_col: str | None) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if sku_col is None or sku_col not in df.columns:
        return pd.DataFrame(
            [
                {"추적 SKU": sku, "정규화 전 매칭 행": 0, "strip 후 매칭 행": 0, "매칭 변화": "SKU 컬럼 없음"}
                for sku in TRACKED_SHIPPING_DEBUG_SKUS
            ]
        )
    raw_text = df[sku_col].fillna("").astype(str)
    stripped_text = raw_text.str.strip()
    normalized = _shipping_debug_sku_keys(df[sku_col])
    for sku in TRACKED_SHIPPING_DEBUG_SKUS:
        exact_rows = int(stripped_text.eq(sku).sum())
        normalized_rows = int(normalized.eq(_shipping_debug_sku_key(sku)).sum())
        rows.append(
            {
                "추적 SKU": sku,
                "정규화 전 매칭 행": exact_rows,
                "strip 후 매칭 행": normalized_rows,
                "매칭 변화": "변화 있음" if exact_rows != normalized_rows else "동일",
            }
        )
    return pd.DataFrame(rows)


def _shipping_debug_filter_rows(
    before_df: pd.DataFrame,
    after_df: pd.DataFrame,
    before_qty: pd.Series,
    after_qty: pd.Series,
    filter_name: str,
    condition: str,
    tracked_removed: dict[str, object] | None = None,
) -> pd.DataFrame:
    before_total = float(pd.to_numeric(before_qty, errors="coerce").fillna(0).sum())
    after_total = float(pd.to_numeric(after_qty, errors="coerce").fillna(0).sum())
    return pd.DataFrame(
        [
            {
                "필터명": filter_name,
                "필터 조건": condition,
                "필터 전 행 수": len(before_df),
                "필터 전 수량 합": before_total,
                "필터 후 행 수": len(after_df),
                "필터 후 수량 합": after_total,
                "제거된 행 수": len(before_df) - len(after_df),
                "제거된 수량 합": before_total - after_total,
                "제거된 추적 SKU": ", ".join(str(k) for k, v in (tracked_removed or {}).items() if v) or "없음",
            }
        ]
    )


def _shipping_debug_compare_raw_vs_esm(
    raw_df: pd.DataFrame,
    raw_sku_col: str | None,
    raw_qty: pd.Series,
    settings: dict | None,
    esm_review: pd.DataFrame | None = None,
    context: SessionContext | None = None,
) -> dict[str, pd.DataFrame]:
    empty = pd.DataFrame(columns=["상품코드", "raw_운송중_합", "ESM_운송중수량", "차이", "차이율", "브랜드", "상품명"])
    if raw_sku_col is None or raw_sku_col not in raw_df.columns:
        return {"top_diff": empty, "raw_only": empty, "esm_only": empty}

    raw_keys = _shipping_debug_sku_keys(raw_df[raw_sku_col])
    raw_work = pd.DataFrame(
        {
            "_sku_key": raw_keys,
            "raw_운송중_합": pd.to_numeric(raw_qty, errors="coerce").fillna(0),
        }
    )
    raw_work = raw_work[raw_work["_sku_key"].ne("")]
    if raw_work.empty:
        return {"top_diff": empty, "raw_only": empty, "esm_only": empty}
    raw_sum = raw_work.groupby("_sku_key", as_index=False)["raw_운송중_합"].sum()

    raw_name_col = kpi_mod.find_column(raw_df, ["상품명", "제품명", "품목명", "itemname"])
    raw_brand_col = kpi_mod.find_column(raw_df, ["브랜드", "브랜드명", "brand"])
    raw_names = pd.DataFrame(
        {
            "_sku_key": raw_keys,
            "상품코드_raw": raw_df[raw_sku_col].astype(str),
            "상품명_raw": raw_df[raw_name_col].astype(str) if raw_name_col else "",
            "브랜드_raw": raw_df[raw_brand_col].astype(str) if raw_brand_col else "",
        }
    )
    raw_names = raw_names[raw_names["_sku_key"].ne("")]
    raw_names = raw_names.groupby("_sku_key", as_index=False).agg(
        상품코드_raw=("상품코드_raw", inbound_mod.first_non_empty),
        상품명_raw=("상품명_raw", inbound_mod.first_non_empty),
        브랜드_raw=("브랜드_raw", inbound_mod.first_non_empty),
    )
    raw_sum = raw_sum.merge(raw_names, on="_sku_key", how="left")

    esm = esm_review.copy() if isinstance(esm_review, pd.DataFrame) else pd.DataFrame()
    if esm.empty:
        try:
            esm = loaders_mod.cached_order_review_df(settings or validation_mod.default_settings_for_validation(), context=context)
        except Exception:
            try:
                esm = order_review_mod.order_review_df(settings or validation_mod.default_settings_for_validation())
            except Exception:
                esm = pd.DataFrame()
    if esm.empty or "상품코드" not in esm.columns:
        compare = raw_sum.rename(columns={"상품코드_raw": "상품코드", "상품명_raw": "상품명", "브랜드_raw": "브랜드"})
        compare["ESM_운송중수량"] = 0
    else:
        esm_work = pd.DataFrame(
            {
                "_sku_key": _shipping_debug_sku_keys(esm["상품코드"]),
                "상품코드_esm": esm["상품코드"].astype(str),
                "ESM_운송중수량": pd.to_numeric(order_review_mod.report_col(esm, ["운송중 수량"], 0), errors="coerce").fillna(0),
                "상품명_esm": order_review_mod.report_col(esm, ["상품명"], ""),
                "브랜드_esm": order_review_mod.report_col(esm, ["브랜드"], ""),
            }
        )
        esm_work = esm_work.groupby("_sku_key", as_index=False).agg(
            상품코드_esm=("상품코드_esm", inbound_mod.first_non_empty),
            ESM_운송중수량=("ESM_운송중수량", "sum"),
            상품명_esm=("상품명_esm", inbound_mod.first_non_empty),
            브랜드_esm=("브랜드_esm", inbound_mod.first_non_empty),
        )
        compare = raw_sum.merge(esm_work, on="_sku_key", how="outer").fillna(0)
        compare["상품코드"] = np.where(compare.get("상품코드_esm", "").astype(str).ne("0"), compare.get("상품코드_esm", ""), compare.get("상품코드_raw", ""))
        compare["상품명"] = np.where(compare.get("상품명_esm", "").astype(str).ne("0"), compare.get("상품명_esm", ""), compare.get("상품명_raw", ""))
        compare["브랜드"] = np.where(compare.get("브랜드_esm", "").astype(str).ne("0"), compare.get("브랜드_esm", ""), compare.get("브랜드_raw", ""))
    compare["raw_운송중_합"] = pd.to_numeric(compare.get("raw_운송중_합", 0), errors="coerce").fillna(0)
    compare["ESM_운송중수량"] = pd.to_numeric(compare.get("ESM_운송중수량", 0), errors="coerce").fillna(0)
    compare["차이"] = compare["raw_운송중_합"] - compare["ESM_운송중수량"]
    compare["차이율"] = np.where(compare["raw_운송중_합"] > 0, compare["차이"] / compare["raw_운송중_합"], np.nan)
    columns = ["상품코드", "브랜드", "상품명", "raw_운송중_합", "ESM_운송중수량", "차이", "차이율"]
    compare = compare[columns]
    return {
        "top_diff": compare.sort_values("차이", ascending=False).head(30).reset_index(drop=True),
        "raw_only": compare[(compare["raw_운송중_합"] > 0) & (compare["ESM_운송중수량"] <= 0)].sort_values("raw_운송중_합", ascending=False).head(30).reset_index(drop=True),
        "esm_only": compare[(compare["ESM_운송중수량"] > 0) & (compare["raw_운송중_합"] <= 0)].sort_values("ESM_운송중수량", ascending=False).head(30).reset_index(drop=True),
    }


def _shipping_debug_summary_text(debug: dict[str, object]) -> str:
    stage = debug.get("stage_metrics", {})
    tracked = debug.get("tracked_wide", pd.DataFrame())
    top_diff = debug.get("compare_top_diff", pd.DataFrame())
    read_debug = debug.get("read_debug", {})
    lines = [
        f"[운송중 디버그 요약 - {datetime.now():%Y-%m-%d %H:%M}]",
        f"파일: {read_debug.get('file_name', '-')}",
        "",
        f"Stage 0: {read_debug.get('read_method', '-')}, candidates={read_debug.get('candidate_count', '-')}, selected={read_debug.get('selected_table_index', '-')}, shape={_shape_text(read_debug.get('selected_raw_shape') or read_debug.get('selected_cleaned_shape'))}",
        f"         MultiIndex: {'Yes' if read_debug.get('selected_raw_is_multiindex') else 'No'}",
        "",
        f"Stage 1 raw: {stage.get('stage1_rows', 0):,}행 / {_fmt_debug_number(stage.get('stage1_qty', 0))}개",
        f"Stage 2 표준화: {stage.get('stage2_rows', 0):,}행 / {_fmt_debug_number(stage.get('stage2_qty', 0))}개 (Δ {stage.get('stage2_rows', 0) - stage.get('stage1_rows', 0):,}행 / Δ {_fmt_debug_number(stage.get('stage2_qty', 0) - stage.get('stage1_qty', 0))}개)",
        f"         SKU unique: 정규화 전 {stage.get('stage2_sku_unique_before', 0):,} → 후 {stage.get('stage2_sku_unique_after', 0):,}",
        "",
        "Stage 2-1 필터:",
        "- Stage 1~2 사이 적용 필터 없음",
        "",
        f"Stage 3 정규화: {stage.get('stage3_rows', 0):,}행 / {_fmt_debug_number(stage.get('stage3_qty', 0))}개 (Δ {stage.get('stage3_rows', 0) - stage.get('stage2_rows', 0):,}행 / Δ {_fmt_debug_number(stage.get('stage3_qty', 0) - stage.get('stage2_qty', 0))}개)",
        f"         정규화 실패: {stage.get('stage3_fail_rows', 0):,}행 / {_fmt_debug_number(stage.get('stage3_fail_qty', 0))}개",
        f"         실패 Top: {debug.get('failure_top_text', '-')}",
        "",
        f"Stage 4 groupby: {stage.get('stage4_sku_count', 0):,} SKU / {_fmt_debug_number(stage.get('stage4_qty', 0))}개",
        "",
        "추적 SKU:",
    ]
    if isinstance(tracked, pd.DataFrame) and not tracked.empty:
        for _, row in tracked.iterrows():
            lines.append(
                f"- {row.get('추적 SKU')}: raw {int(row.get('Stage1_raw_행', 0))}건/{_fmt_debug_number(row.get('Stage1_raw_수량', 0))} "
                f"→ Stage2 {int(row.get('Stage2_행', 0))}건/{_fmt_debug_number(row.get('Stage2_수량', 0))} "
                f"→ Stage3 {int(row.get('Stage3_행', 0))}건/{_fmt_debug_number(row.get('Stage3_수량', 0))} "
                f"→ Stage4 {_fmt_debug_number(row.get('Stage4_groupby_수량', 0))}"
            )
    lines.append("")
    lines.append("raw vs ESM 차이 Top:")
    if isinstance(top_diff, pd.DataFrame) and not top_diff.empty:
        for idx, row in top_diff.head(5).iterrows():
            lines.append(
                f"{idx + 1}. {row.get('상품코드', '-')}: raw {_fmt_debug_number(row.get('raw_운송중_합', 0))} / "
                f"ESM {_fmt_debug_number(row.get('ESM_운송중수량', 0))} / 차이 {_fmt_debug_number(row.get('차이', 0))}"
            )
    else:
        lines.append("- 비교 데이터 없음")
    return "\n".join(lines)


def shipping_pipeline_debug(
    settings: dict | None = None,
    target_sku: str = "BODP04-MEU",
    esm_review: pd.DataFrame | None = None,
    context: SessionContext | None = None,
) -> dict[str, object]:
    context = ensure_session_context(context)
    uploaded = context.uploaded_data.get("shipping")
    if uploaded is None:
        uploaded = loaders_mod.sample_shipping()
    read_debug = context.shipping_read_debug
    raw_df = context.shipping_read_raw_df
    if raw_df is None or not isinstance(raw_df, pd.DataFrame):
        raw_df = uploaded.copy()

    raw_sku_col = kpi_mod.find_column(raw_df, ["SKU", "상품코드", "품목코드", "아이템코드", "itemcode"])
    raw_qty_col = kpi_mod.find_column(raw_df, ["수량", "운송수량", "출고수량", "입고수량", "qty", "QTY"])
    raw_qty = _shipping_debug_qty_series(raw_df, raw_qty_col, robust=True)
    raw_qty_app = _shipping_debug_qty_series(raw_df, raw_qty_col, robust=False)
    raw_tracking = _shipping_debug_tracking_df(raw_df, raw_sku_col, raw_qty, "Stage1 raw")

    standardized = _standardize_shipping_for_debug(uploaded)
    stage2_sku_col = "SKU" if "SKU" in standardized.columns else kpi_mod.find_column(standardized, ["SKU", "상품코드", "품목코드"])
    stage2_qty_col = "수량" if "수량" in standardized.columns else kpi_mod.find_column(standardized, ["수량", "운송수량", "qty"])
    stage2_qty = _shipping_debug_qty_series(standardized, stage2_qty_col, robust=True)
    stage2_qty_app = _shipping_debug_qty_series(standardized, stage2_qty_col, robust=False)
    stage2_tracking = _shipping_debug_tracking_df(standardized, stage2_sku_col, stage2_qty, "Stage2 표준화")
    stage2_sku_normalization_tracking = _shipping_debug_sku_normalization_tracking(standardized, stage2_sku_col)
    stage2_sku_text = standardized[stage2_sku_col].fillna("").astype(str).str.strip() if stage2_sku_col else pd.Series(dtype=str)
    stage2_sku_keys = _shipping_debug_sku_keys(standardized[stage2_sku_col]) if stage2_sku_col else pd.Series(dtype=str)

    filters_21 = _shipping_debug_filter_rows(
        raw_df,
        standardized,
        raw_qty,
        stage2_qty,
        "Stage 1~2 사이 적용 필터 없음",
        "파일 read 후 헤더/빈행 클린업 및 컬럼 표준화만 수행. 출고일/ETA/운송수단/SKU/수량 기준 제외 없음",
    )

    before_transport = _extract_raw_transport_series(standardized)
    normalized_transport = before_transport.map(normalize_transport_mode)
    prepared = prepare_shipping(uploaded, settings=settings, context=context)
    stage3_qty = pd.to_numeric(prepared.get("수량", pd.Series([0] * len(prepared), index=prepared.index)), errors="coerce").fillna(0)
    recognized = prepared.get("운송수단", pd.Series([""] * len(prepared), index=prepared.index)).astype(str).isin(STANDARD_TRANSPORT_MODES)
    stage3_tracking = _shipping_debug_tracking_df(prepared, "SKU" if "SKU" in prepared.columns else None, stage3_qty, "Stage3 정규화")

    recognized_prepared = prepared[recognized].copy()
    stage4_qty = pd.to_numeric(recognized_prepared.get("수량", pd.Series(dtype=float)), errors="coerce").fillna(0)
    grouped = recognized_prepared.groupby("SKU", dropna=False)["수량"].sum().reset_index().sort_values("수량", ascending=False) if "SKU" in recognized_prepared.columns else pd.DataFrame(columns=["SKU", "수량"])
    stage4_tracking = _shipping_debug_tracking_df(grouped, "SKU" if "SKU" in grouped.columns else None, pd.to_numeric(grouped.get("수량", 0), errors="coerce").fillna(0), "Stage4 groupby")

    tracked_wide = pd.DataFrame({"추적 SKU": TRACKED_SHIPPING_DEBUG_SKUS})
    for label, tracking in [
        ("Stage1_raw", raw_tracking),
        ("Stage2", stage2_tracking),
        ("Stage3", stage3_tracking),
    ]:
        tracking_map = tracking.set_index("추적 SKU") if not tracking.empty else pd.DataFrame()
        tracked_wide[f"{label}_행"] = tracked_wide["추적 SKU"].map(tracking_map["행 수"] if "행 수" in tracking_map else {})
        tracked_wide[f"{label}_수량"] = tracked_wide["추적 SKU"].map(tracking_map["수량 합계"] if "수량 합계" in tracking_map else {})
    stage4_map = stage4_tracking.set_index("추적 SKU") if not stage4_tracking.empty else pd.DataFrame()
    tracked_wide["Stage4_groupby_수량"] = tracked_wide["추적 SKU"].map(stage4_map["수량 합계"] if "수량 합계" in stage4_map else {}).fillna(0)
    tracked_wide = tracked_wide.fillna(0)

    failure_values = before_transport[~normalized_transport.isin(STANDARD_TRANSPORT_MODES)].astype(str).str.strip().replace("", "(빈값)")
    failure_counts = _value_counts_table(failure_values, "인식 실패 원본값", top=20)
    failure_top_text = ", ".join(f"{row['인식 실패 원본값']}({row['행 수']})" for _, row in failure_counts.head(5).iterrows()) if not failure_counts.empty else "없음"

    mode_rows = []
    prepared_modes = prepared.get("운송수단", pd.Series([""] * len(prepared), index=prepared.index)).astype(str)
    for mode in ["해운", "항공", "철송", "트럭", TRANSPORT_REVIEW_REQUIRED]:
        mask = prepared_modes.eq(mode)
        mode_rows.append({"운송수단": "기타/미인식" if mode == TRANSPORT_REVIEW_REQUIRED else mode, "행 수": int(mask.sum()), "수량 합계": float(stage3_qty.loc[mask].sum())})
    mode_summary = pd.DataFrame(mode_rows)

    compare = _shipping_debug_compare_raw_vs_esm(raw_df, raw_sku_col, raw_qty, settings, esm_review=esm_review, context=context)

    stage_metrics = {
        "stage1_rows": len(raw_df),
        "stage1_qty": float(raw_qty.sum()),
        "stage1_qty_app": float(raw_qty_app.sum()),
        "stage2_rows": len(standardized),
        "stage2_qty": float(stage2_qty.sum()),
        "stage2_qty_app": float(stage2_qty_app.sum()),
        "stage2_sku_unique_before": int(stage2_sku_text[stage2_sku_text.ne("")].nunique()) if not stage2_sku_text.empty else 0,
        "stage2_sku_unique_after": int(stage2_sku_keys[stage2_sku_keys.ne("")].nunique()) if not stage2_sku_keys.empty else 0,
        "stage3_rows": len(prepared),
        "stage3_qty": float(stage3_qty.sum()),
        "stage3_fail_rows": int((~recognized).sum()),
        "stage3_fail_qty": float(stage3_qty.loc[~recognized].sum()),
        "stage4_rows": len(recognized_prepared),
        "stage4_sku_count": int(grouped["SKU"].nunique()) if "SKU" in grouped.columns else 0,
        "stage4_qty": float(pd.to_numeric(grouped.get("수량", 0), errors="coerce").fillna(0).sum()),
    }

    stage0_summary = pd.DataFrame(
        [
            {"항목": "업로드 파일명", "값": read_debug.get("file_name", context.uploaded_files.get("shipping", "sample_shipping"))},
            {"항목": "파일 크기", "값": f"{int(read_debug.get('file_size_bytes', 0)):,.0f} bytes" if read_debug.get("file_size_bytes") else "-"},
            {"항목": "파일 확장자", "값": read_debug.get("suffix", "-")},
            {"항목": "실제 read 방식", "값": read_debug.get("read_method", "sample/unknown")},
            {"항목": "fallback/실패 사유", "값": " / ".join(str(item.get("error", "")) for item in read_debug.get("attempts", []) if item.get("error")) or "-"},
            {"항목": "MultiIndex 여부", "값": "Yes" if read_debug.get("selected_raw_is_multiindex") else "No"},
            {"항목": "read_html table/candidate 수", "값": read_debug.get("candidate_count", "-")},
            {"항목": "선택 table/candidate index", "값": read_debug.get("selected_table_index", "-")},
            {"항목": "선택 shape", "값": _shape_text(read_debug.get("selected_raw_shape") or read_debug.get("selected_cleaned_shape"))},
            {"항목": "table 선택 기준", "값": read_debug.get("selection_basis", "-")},
            {"항목": "Excel sheet 수", "값": read_debug.get("sheet_count", "-")},
            {"항목": "선택 sheet명", "값": (read_debug.get("selected_candidate_metadata") or {}).get("sheet_name", "-")},
        ]
    )
    stage1_summary = pd.DataFrame(
        [
            {"항목": "raw 행 수", "값": f"{len(raw_df):,}"},
            {"항목": "raw 컬럼 수", "값": f"{len(raw_df.columns):,}"},
            {"항목": "SKU 후보 컬럼명", "값": raw_sku_col or "없음"},
            {"항목": "수량 후보 컬럼명", "값": raw_qty_col or "없음"},
            {"항목": "수량 컬럼 dtype", "값": str(raw_df[raw_qty_col].dtype) if raw_qty_col else "없음"},
            {"항목": "수량 후보 컬럼 합계(쉼표 제거)", "값": f"{raw_qty.sum():,.0f}"},
            {"항목": "수량 후보 컬럼 합계(앱 numeric)", "값": f"{raw_qty_app.sum():,.0f}"},
        ]
    )
    required_status = {
        "SKU 또는 상품코드": "Y" if stage2_sku_col else "N",
        "수량": "Y" if stage2_qty_col else "N",
        "운송수단 또는 Invoice 비고": "Y" if ("운송수단" in standardized.columns or "Invoice 비고" in standardized.columns) else "N",
        "출고일/ETA": "Y" if ("출고일" in standardized.columns or "ETA" in standardized.columns) else "N",
    }
    stage2_summary = pd.DataFrame(
        [
            {"항목": "표준화 후 행 수", "값": f"{len(standardized):,}"},
            {"항목": "표준화 후 컬럼 수", "값": f"{len(standardized.columns):,}"},
            {"항목": "필수 컬럼 존재 여부", "값": ", ".join(f"{k}={v}" for k, v in required_status.items())},
            {"항목": "SKU 결측 행 수", "값": f"{stage2_sku_text.eq('').sum():,}" if not stage2_sku_text.empty else "-"},
            {"항목": "수량 결측 행 수", "값": f"{standardized[stage2_qty_col].isna().sum():,}" if stage2_qty_col else "-"},
            {"항목": "수량 숫자 변환 실패 행 수", "값": f"{kpi_mod.number_conversion_failure_count(standardized[stage2_qty_col]):,}" if stage2_qty_col else "-"},
            {"항목": "수량 합계(쉼표 제거)", "값": f"{stage2_qty.sum():,.0f}"},
            {"항목": "수량 합계(앱 numeric)", "값": f"{stage2_qty_app.sum():,.0f}"},
            {"항목": "Stage 1 대비 행 수 delta", "값": f"{len(standardized) - len(raw_df):,}"},
            {"항목": "Stage 1 대비 수량 delta", "값": f"{stage2_qty.sum() - raw_qty.sum():,.0f}"},
            {"항목": "SKU unique 정규화 전", "값": f"{stage_metrics['stage2_sku_unique_before']:,}"},
            {"항목": "SKU unique 정규화 후(strip)", "값": f"{stage_metrics['stage2_sku_unique_after']:,}"},
            {"항목": "정규화 전후 안내", "값": "unique 수 차이 있음: 앞뒤 공백 차이 가능" if stage_metrics["stage2_sku_unique_before"] != stage_metrics["stage2_sku_unique_after"] else "unique 수 동일"},
        ]
    )
    stage3_summary = pd.DataFrame(
        [
            {"항목": "정규화 후 행 수", "값": f"{len(prepared):,}"},
            {"항목": "정규화 후 수량 합계(앱 numeric)", "값": f"{stage3_qty.sum():,.0f}"},
            {"항목": "Stage 2 대비 행 수 delta", "값": f"{len(prepared) - len(standardized):,}"},
            {"항목": "Stage 2 대비 수량 delta", "값": f"{stage3_qty.sum() - stage2_qty.sum():,.0f}"},
            {"항목": "인식 성공 행 수", "값": f"{recognized.sum():,}"},
            {"항목": "인식 실패 행 수", "값": f"{(~recognized).sum():,}"},
            {"항목": "인식 성공 수량 합계", "값": f"{stage3_qty.loc[recognized].sum():,.0f}"},
            {"항목": "인식 실패 수량 합계", "값": f"{stage3_qty.loc[~recognized].sum():,.0f}"},
        ]
    )
    stage4_summary = pd.DataFrame(
        [
            {"항목": "groupby 전 행 수(운송수단 인식 성공)", "값": f"{len(recognized_prepared):,}"},
            {"항목": "groupby 후 SKU 수", "값": f"{stage_metrics['stage4_sku_count']:,}"},
            {"항목": "groupby 후 수량 합계", "값": f"{stage_metrics['stage4_qty']:,.0f}"},
            {"항목": "Stage 3 대비 행 수 delta", "값": f"{len(recognized_prepared) - len(prepared):,}"},
            {"항목": "Stage 3 대비 수량 delta", "값": f"{stage_metrics['stage4_qty'] - stage3_qty.sum():,.0f}"},
            {"항목": "Stage 3 대비 SKU 수 delta", "값": f"{stage_metrics['stage4_sku_count'] - (prepared['SKU'].nunique() if 'SKU' in prepared.columns else 0):,}"},
            {"항목": "merge/groupby SKU 키 기준", "값": "SKU 앞뒤 공백 제거 후 완전 일치 기준으로 Stage 5 비교"},
        ]
    )
    debug = {
        "read_debug": read_debug,
        "stage_metrics": stage_metrics,
        "stage0_summary": stage0_summary,
        "multiindex_columns": read_debug.get("selected_raw_column_tuples", []),
        "read_attempts": pd.DataFrame(read_debug.get("attempts", [])),
        "candidate_shapes": pd.DataFrame(read_debug.get("candidate_shapes", [])),
        "stage1_summary": stage1_summary,
        "raw_columns": [str(col) for col in raw_df.columns],
        "raw_preview": raw_df.head(5).astype(str),
        "raw_tracking": raw_tracking,
        "stage2_summary": stage2_summary,
        "standardized_columns": [str(col) for col in standardized.columns],
        "stage2_tracking": stage2_tracking,
        "stage2_sku_normalization_tracking": stage2_sku_normalization_tracking,
        "stage2_filters": filters_21,
        "stage3_rules": pd.DataFrame(
            [
                {"항목": "표준 운송수단", "값": ", ".join(sorted(STANDARD_TRANSPORT_MODES))},
                {"항목": "정규식", "값": r"(해운|헤운|헤은|항공|철송|트럭)"},
                {"항목": "오타 보정", "값": "헤운, 헤은 → 해운"},
                {"항목": "원본 후보 컬럼", "값": ", ".join(_RAW_TRANSPORT_CANDIDATES)},
            ]
        ),
        "stage3_summary": stage3_summary,
        "transport_before_counts": _value_counts_table(before_transport.astype(str).str.strip().replace("", "(빈값)"), "정규화 전 원본값", top=20),
        "transport_after_counts": _value_counts_table(prepared.get("운송수단", pd.Series(dtype=str)).astype(str), "정규화 후 운송수단"),
        "transport_failure_counts": failure_counts,
        "transport_mode_summary": mode_summary,
        "stage3_tracking": stage3_tracking,
        "stage4_summary": stage4_summary,
        "top_skus": grouped.head(20).rename(columns={"수량": "groupby 수량"}),
        "stage4_tracking": stage4_tracking,
        "tracked_wide": tracked_wide,
        "compare_top_diff": compare["top_diff"],
        "compare_raw_only": compare["raw_only"],
        "compare_esm_only": compare["esm_only"],
        "failure_top_text": failure_top_text,
    }
    debug["summary_text"] = _shipping_debug_summary_text(debug)
    return debug



