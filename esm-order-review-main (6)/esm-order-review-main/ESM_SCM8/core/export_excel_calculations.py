from __future__ import annotations

import numpy as np
import pandas as pd

from core.common import _DEFAULT_EUR_KRW_RATE, ORDER_EXCLUDED_REVIEW_STATUSES
from core import order_review as order_review_mod


def _numeric_series(df: pd.DataFrame, candidates: list[str], default: object = 0) -> pd.Series:
    return pd.to_numeric(order_review_mod.report_col(df, candidates, default), errors="coerce")


def order_review_excluded_mask(df: pd.DataFrame) -> pd.Series:
    """Rows the review already dropped from 발주 검토 (0단가/무상, 저판매, 데이터 오류 등).

    상태 컬럼이 없는 호출자(참조 워크북 레이아웃 테스트, 부분 프레임)는 전부 검토
    대상으로 본다.
    """
    status = order_review_mod.report_col(df, ["상태"], "정상").astype(str).str.strip()
    return status.isin(ORDER_EXCLUDED_REVIEW_STATUSES)


def _excel_round_qty(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0).astype(float)
    rounded = np.where(numeric >= 0, np.floor(numeric + 0.5), np.ceil(numeric - 0.5))
    return pd.Series(rounded, index=values.index)


def _month_setting(
    df: pd.DataFrame,
    settings: dict | None,
    setting_key: str,
    candidates: list[str],
    default: float,
) -> pd.Series:
    if settings is not None and setting_key in settings:
        value = float(settings.get(setting_key, default))
        return pd.Series(value, index=df.index, dtype=float)
    existing = _numeric_series(df, candidates, np.nan)
    return existing.fillna(default).astype(float)


def template_order_metrics(df: pd.DataFrame, settings: dict | None = None) -> pd.DataFrame:
    """Replicate the reference workbook's order quantity and amount basis.

    Canonical quantity formula:
    =IF(monthly_sales=0, 0, MAX(0, monthly_sales * safety_months - (eu_stock + shipping_stock)))
    """

    base = pd.DataFrame(df).copy()
    if base.empty:
        return pd.DataFrame(
            {
                "월평균_계산": pd.Series(dtype=float),
                "유럽재고_계산": pd.Series(dtype=float),
                "운송재고_계산": pd.Series(dtype=float),
                "유럽운송합산_계산": pd.Series(dtype=float),
                "안전재고_계산": pd.Series(dtype=float),
                "발주필요수량_계산": pd.Series(dtype=float),
                "발주금액_EUR_계산": pd.Series(dtype=float),
                "발주금액_KRW_계산": pd.Series(dtype=float),
                "미입고해소후_발주필요수량_계산": pd.Series(dtype=float),
                "미입고해소후_발주금액_EUR_계산": pd.Series(dtype=float),
                "미입고해소후_발주금액_KRW_계산": pd.Series(dtype=float),
                "적용단가_EUR_계산": pd.Series(dtype=float),
            }
        )

    settings = settings or {}
    currency_code = str(settings.get("currency_code") or "EUR").strip().upper()
    if currency_code not in {"EUR", "USD"}:
        currency_code = "EUR"
    eur_rate = float(settings.get("currency_krw_rate", settings.get("eur_krw_rate", _DEFAULT_EUR_KRW_RATE)))
    recent_sales = _numeric_series(
        base,
        ["3개월 판매량", "최근 3개월 판매수량", "기준_3M_판매수량", "최근 3개월 수요", "PA+CA 판매수량"],
        0,
    ).fillna(0)
    monthly_raw = _numeric_series(base, ["월평균 판매량", "월평균 판매수량", "월평균"], np.nan)
    monthly = _excel_round_qty(monthly_raw.fillna(recent_sales / 3))
    eu_stock = _excel_round_qty(
        _numeric_series(
            base,
            ["1. 현지 재고", "1. 유럽 재고", "EU 현지 재고", "유럽 가용재고", "EU 가용재고", "EU 현지 가용수량", "유럽현지재고", "현지재고"],
            0,
        ).fillna(0)
    )
    shipping_stock = _excel_round_qty(
        _numeric_series(base, ["2. 운송 재고", "운송중", "운송중 수량", "운송재고"], 0).fillna(0)
    )
    combined_stock = eu_stock + shipping_stock
    safety_months = _month_setting(
        base,
        settings,
        "safety_months",
        ["안전재고 개월 수", "안전재고(M)"],
        3.0,
    )
    safety_stock = monthly * safety_months
    order_qty = (safety_stock - combined_stock).clip(lower=0)
    order_qty = order_qty.where(monthly.gt(0), 0)
    # 발주제외/확인필요 행은 리뷰 단계에서 이미 수량을 0으로 확정했다. canonical 재계산이
    # 이를 되살리면 "발주 불필요 + 발주필요수량 > 0" 행이 생기고 화면·요약 KPI의 SKU 수와
    # 수량 기준이 서로 달라진다.
    order_qty = order_qty.where(~order_review_excluded_mask(base), 0)

    open_po = _numeric_series(base, ["미입고 현황", "미입고\n현황", "미입고 수량", "미입고수량", "미입고"], 0).fillna(0)
    source_order_qty = _numeric_series(
        base,
        ["발주 필요 수량", "추가 발주 필요 수량", "발주필요수량", "발주총\n필요수량", "최종 부족수량", "부족수량", "1차 부족수량"],
        0,
    ).fillna(0)
    unit_price_eur = _numeric_series(
        base,
        [
            f"현지 입고단가({currency_code})",
            f"현지 입고단가_{currency_code}",
            "현지 입고단가",
            "EU 입고단가(EUR)",
            "EU 입고단가",
            f"적용 단가_{currency_code}",
            "적용 단가_EUR",
        ],
        np.nan,
    )
    source_amount_eur = _numeric_series(
        base,
        [
            f"부족금액_{currency_code}",
            "부족금액_EUR",
            f"=발주 금액({currency_code})",
            f"발주 금액({currency_code})",
        ],
        np.nan,
    )
    source_amount_krw = _numeric_series(
        base,
        ["부족금액_KRW", "추가 발주 필요 금액", "발주필요금액", "발주필요금액_KRW", "발주 필요 금액"],
        np.nan,
    )
    fallback_unit_from_eur = source_amount_eur / source_order_qty.replace(0, np.nan)
    fallback_unit_from_krw = (source_amount_krw / eur_rate) / source_order_qty.replace(0, np.nan)
    effective_unit_price = (
        unit_price_eur.where(unit_price_eur.gt(0))
        .fillna(fallback_unit_from_eur)
        .fillna(fallback_unit_from_krw)
        .fillna(0)
    )

    order_amount_eur = order_qty * effective_unit_price
    order_amount_krw = order_amount_eur * eur_rate
    order_with_open_qty = (order_qty - open_po).clip(lower=0)
    order_with_open_eur = order_with_open_qty * effective_unit_price
    order_with_open_krw = order_with_open_eur * eur_rate

    return pd.DataFrame(
        {
            "월평균_계산": monthly,
            "유럽재고_계산": eu_stock,
            "운송재고_계산": shipping_stock,
            "유럽운송합산_계산": combined_stock,
            "안전재고_계산": safety_stock,
            "발주필요수량_계산": order_qty,
            "발주금액_EUR_계산": order_amount_eur,
            "발주금액_KRW_계산": order_amount_krw,
            "미입고해소후_발주필요수량_계산": order_with_open_qty,
            "미입고해소후_발주금액_EUR_계산": order_with_open_eur,
            "미입고해소후_발주금액_KRW_계산": order_with_open_krw,
            "적용단가_EUR_계산": effective_unit_price,
        },
        index=base.index,
    )
