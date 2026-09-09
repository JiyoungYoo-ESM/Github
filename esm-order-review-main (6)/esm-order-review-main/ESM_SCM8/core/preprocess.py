from __future__ import annotations

import re

import numpy as np
import pandas as pd

from core.common import (
    EU_LOCAL_STOCK_UNIT_PRICE_CURRENCY,
    NON_PRODUCT_SKU_TOKENS,
    PA_CA_SALES_CANDIDATES,
)
from core import kpi as kpi_mod

def clean_identifier_series(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    return text.str.replace(r"\.0$", "", regex=True).replace({"nan": "", "NaN": "", "None": ""})


def sku_group_key_series(series: pd.Series) -> pd.Series:
    text = clean_identifier_series(series)
    compact_upper = text.str.replace(r"\s+", "", regex=True).str.upper()
    exception_keys = {
        "RLSM04-SCEU": "RLSM04-SCEU",
        "DRAS01-CASREU": "DRAS01-CASREU",
    }
    return compact_upper.map(exception_keys).fillna(text)


def representative_sku_by_key(series: pd.Series) -> pd.Series:
    work = pd.DataFrame(
        {
            "_sku": clean_identifier_series(series),
            "_sku_key": sku_group_key_series(series),
        }
    )
    work = work[work["_sku"].ne("") & work["_sku_key"].ne("")]
    if work.empty:
        return pd.Series([], index=pd.Index([], name="_sku_key"), dtype=object, name="_sku")
    counts = work.groupby(["_sku_key", "_sku"], sort=False).size().rename("_count").reset_index()
    counts["_order"] = counts.groupby("_sku_key", sort=False).cumcount()
    reps = counts.sort_values(["_sku_key", "_count", "_order"], ascending=[True, False, True]).drop_duplicates("_sku_key")
    return reps.set_index("_sku_key")["_sku"]


def product_sku_mask(series: pd.Series) -> pd.Series:
    text = clean_identifier_series(series)
    compact = text.str.replace(r"[\s_\-()/]+", "", regex=True).str.lower()
    return text.astype(str).str.strip().ne("") & ~compact.isin(NON_PRODUCT_SKU_TOKENS)


def detect_pa_ca_sales_column(df: pd.DataFrame) -> str | None:
    """재고 파일에 포함된 최근 3개월 PA+CA 판매수량 컬럼을 자동 탐지한다."""
    return kpi_mod.find_column(df, PA_CA_SALES_CANDIDATES)


def prepare_eu_stock(
    eu_stock_df: pd.DataFrame,
    pa_ca_sales_col: str | None = None,
    currency_code: str | None = None,
) -> pd.DataFrame:
    df = eu_stock_df.copy()
    sku_col = kpi_mod.find_column(df, ["상품코드", "SKU", "품목코드", "아이템코드", "itemcode"])
    if sku_col is not None and sku_col != "상품코드":
        df = df.rename(columns={sku_col: "상품코드"})
    barcode_col = kpi_mod.find_column(df, ["바코드", "barcode", "ean", "jan"])
    if barcode_col is not None and barcode_col != "바코드":
        df = df.rename(columns={barcode_col: "바코드"})
    stock_col = kpi_mod.find_column(df, ["재고수량", "재고 수량", "stock qty", "stock quantity"])
    hold_col = kpi_mod.find_column(df, ["Hold수량", "Hold 수량", "홀드수량", "hold qty", "hold quantity"])
    available_col = kpi_mod.find_column(
        df,
        ["EU 현지 가용수량", "가용수량", "가용 수량", "available qty", "available quantity"],
    )
    stock_qty = (
        kpi_mod.to_number_series(df[stock_col])
        if stock_col is not None
        else pd.Series([0] * len(df), index=df.index)
    )
    hold_qty = (
        kpi_mod.to_number_series(df[hold_col])
        if hold_col is not None
        else pd.Series([0] * len(df), index=df.index)
    )
    if available_col is not None:
        df["EU 현지 가용수량"] = kpi_mod.to_number_series(df[available_col])
    elif "EU 현지 가용수량" not in df.columns:
        df["EU 현지 가용수량"] = (stock_qty - hold_qty).clip(lower=0)
    if "검토 운송수단" not in df.columns:
        df["검토 운송수단"] = "해운"
    pa_ca_col = pa_ca_sales_col if pa_ca_sales_col in df.columns else detect_pa_ca_sales_column(df)
    if pa_ca_sales_col is not None and pa_ca_sales_col in df.columns:
        df["최근 3개월 판매수량"] = kpi_mod.to_number_series(df[pa_ca_sales_col])
    elif "최근 3개월 판매수량" not in df.columns and pa_ca_col is not None:
        df = df.rename(columns={pa_ca_col: "최근 3개월 판매수량"})
    if "최근 3개월 판매수량" not in df.columns:
        df["최근 3개월 판매수량"] = 0
    if "재고수량" not in df.columns:
        df["재고수량"] = 0
    if "Hold수량" not in df.columns:
        df["Hold수량"] = 0
    df["PA+CA 판매수량"] = kpi_mod.to_number_series(df["최근 3개월 판매수량"])
    df["재고수량"] = stock_qty
    df["Hold수량"] = hold_qty
    df["EU 현지 가용수량"] = kpi_mod.to_number_series(df["EU 현지 가용수량"]).clip(lower=0)
    unit_price_col = kpi_mod.find_column(
        df,
        ["현지 입고단가", "EU 입고단가", "평균단가", "평균 단가", "평균 단가 ( )", "unit price", "average price"],
    )
    if unit_price_col is not None:
        df["현지 입고단가"] = kpi_mod.to_unit_price_number_series(df[unit_price_col])
    elif "현지 입고단가" not in df.columns and "EU 입고단가" not in df.columns:
        df["현지 입고단가"] = 0
    elif "현지 입고단가" in df.columns:
        df["현지 입고단가"] = kpi_mod.to_unit_price_number_series(df["현지 입고단가"])
    else:
        df["현지 입고단가"] = kpi_mod.to_unit_price_number_series(df["EU 입고단가"])
    df["EU 입고단가"] = df["현지 입고단가"]
    if "EU 입고단가 원본컬럼" not in df.columns:
        df["EU 입고단가 원본컬럼"] = unit_price_col or "현지 입고단가"
    requested_currency = str(currency_code or "").strip().upper()
    if requested_currency not in {"EUR", "USD"}:
        requested_currency = ""
    source_currency = None
    for currency_column in ("현지 입고단가 통화", "EU 입고단가 통화"):
        if currency_column in df.columns:
            source_currency = df[currency_column].astype(str).str.strip().str.upper()
            break
    if source_currency is None:
        source_currency = pd.Series(
            requested_currency or EU_LOCAL_STOCK_UNIT_PRICE_CURRENCY,
            index=df.index,
            dtype=object,
        )
    valid_source_currency = source_currency.isin({"EUR", "USD", "KRW"})
    normalized_currency = source_currency.where(
        valid_source_currency,
        requested_currency or EU_LOCAL_STOCK_UNIT_PRICE_CURRENCY,
    )
    df["현지 입고단가 통화"] = normalized_currency
    df["EU 입고단가 통화"] = normalized_currency
    if "브랜드" not in df.columns:
        df["브랜드"] = "-"
    if "상품명" not in df.columns:
        df["상품명"] = "-"
    status_col = kpi_mod.find_column(df, ["제품상태", "제품 상태", "상품상태", "product status"])
    if status_col is not None and status_col != "제품상태":
        df["제품상태"] = df[status_col]
    if "제품상태" not in df.columns:
        df["제품상태"] = ""
    if "바코드" not in df.columns:
        df["바코드"] = "-"
    if "상품코드" not in df.columns:
        df["상품코드"] = ""
    df["상품코드"] = clean_identifier_series(df["상품코드"])
    df["바코드"] = clean_identifier_series(df["바코드"])
    df["재고파일 존재여부"] = np.where(product_sku_mask(df["상품코드"]), "Y", "")
    df["SKU등록상태"] = np.where(df["재고파일 존재여부"].eq("Y"), "정상등록", "상품코드 확인필요")
    return df


def prepare_hq_eu_stock(hq_eu_stock_df: pd.DataFrame) -> pd.DataFrame:
    df = hq_eu_stock_df.copy()
    sku_col = kpi_mod.find_column(df, ["상품코드", "SKU", "품목코드", "아이템코드", "itemcode"])
    if sku_col is not None and sku_col != "상품코드":
        df = df.rename(columns={sku_col: "상품코드"})
    stock_col = kpi_mod.find_column(df, ["재고수량", "재고 수량", "stock qty", "stock quantity"])
    hold_col = kpi_mod.find_column(df, ["Hold수량", "Hold 수량", "홀드수량", "hold qty", "hold quantity"])
    available_col = kpi_mod.find_column(
        df,
        ["본사 EU창고 가용수량", "가용수량", "가용 수량", "available qty", "available quantity"],
    )
    stock_qty = (
        kpi_mod.to_number_series(df[stock_col])
        if stock_col is not None
        else pd.Series([0] * len(df), index=df.index)
    )
    hold_qty = (
        kpi_mod.to_number_series(df[hold_col])
        if hold_col is not None
        else pd.Series([0] * len(df), index=df.index)
    )
    if available_col is not None:
        df["본사 EU창고 가용수량"] = kpi_mod.to_number_series(df[available_col])
    elif "본사 EU창고 가용수량" not in df.columns:
        df["본사 EU창고 가용수량"] = (stock_qty - hold_qty).clip(lower=0)
    if "상품코드" not in df.columns:
        df["상품코드"] = ""
    df["상품코드"] = clean_identifier_series(df["상품코드"])
    df = df[product_sku_mask(df["상품코드"])].copy()
    return df.groupby("상품코드", as_index=False)["본사 EU창고 가용수량"].sum()

