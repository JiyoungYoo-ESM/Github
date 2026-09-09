from __future__ import annotations

import numpy as np
import pandas as pd
from core import inbound as inbound_mod, kpi as kpi_mod, preprocess as preprocess_mod


def _is_missing_identity_text(value: object) -> bool:
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "-"} or "상품명 미확인" in text


def _first_non_empty_series(values: pd.Series) -> str:
    if not len(values):
        return ""
    for value in values:
        if not _is_missing_identity_text(value):
            return str(value).strip()
    return ""


def _missing_identity_mask(text: pd.Series) -> pd.Series:
    lowered = text.str.lower()
    return text.eq("") | lowered.isin({"nan", "none", "-"}) | text.str.contains("상품명 미확인", regex=False, na=False)


def _first_non_empty_by_group(df: pd.DataFrame, group_col: str, value_col: str, result_col: str | None = None) -> pd.DataFrame:
    result_col = result_col or value_col
    text = df[value_col].astype(str).str.strip()
    valid = ~_missing_identity_mask(text)
    grouped = (
        pd.DataFrame({group_col: df[group_col], result_col: text.where(valid)})
        .groupby(group_col, sort=True, as_index=False)[result_col]
        .first()
    )
    grouped[result_col] = grouped[result_col].fillna("")
    return grouped


def _first_positive(values: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0)
    positive = numeric[numeric > 0]
    return float(positive.iloc[0]) if not positive.empty else float(numeric.iloc[0]) if not numeric.empty else 0.0


def _first_positive_by_group(df: pd.DataFrame, group_col: str, value_col: str, result_col: str | None = None) -> pd.DataFrame:
    result_col = result_col or value_col
    numeric = pd.to_numeric(df[value_col], errors="coerce").fillna(0)
    work = pd.DataFrame({group_col: df[group_col], result_col: numeric})
    fallback = work.groupby(group_col, sort=True)[result_col].first()
    positive = work.assign(**{result_col: work[result_col].where(work[result_col] > 0)})
    first_positive = positive.groupby(group_col, sort=True)[result_col].first()
    grouped = first_positive.combine_first(fallback).fillna(0).astype(float).rename(result_col).reset_index()
    return grouped


def aggregate_eu_stock_for_order(eu_stock_df: pd.DataFrame) -> pd.DataFrame:
    if eu_stock_df.empty:
        return pd.DataFrame(
            columns=[
                "상품코드", "브랜드", "상품명", "제품상태", "바코드", "재고수량", "Hold수량",
                "EU 현지 가용수량", "현지 입고단가", "현지 입고단가 통화", "EU 입고단가",
                "CMS 원화 입고단가", "CMS 재고금액(KRW)", "적용 환율", "환율 기준일", "환율 출처",
                "PA+CA 판매수량", "최근 3개월 판매수량", "EU 입고단가 원본컬럼",
                "EU 입고단가 통화", "재고파일 존재여부", "SKU등록상태",
            ]
        )
    df = eu_stock_df[preprocess_mod.product_sku_mask(eu_stock_df["상품코드"])].copy()
    if df.empty:
        return pd.DataFrame(columns=eu_stock_df.columns)
    if "현지 입고단가" not in df.columns:
        df["현지 입고단가"] = df.get("EU 입고단가", 0)
    if "현지 입고단가 통화" not in df.columns:
        df["현지 입고단가 통화"] = df.get("EU 입고단가 통화", "EUR")
    df["_sku_key"] = preprocess_mod.sku_group_key_series(df["상품코드"])
    sku_rep = preprocess_mod.representative_sku_by_key(df["상품코드"]).rename("상품코드").reset_index()
    grouped = df.groupby("_sku_key", sort=True, as_index=False).agg(
        재고수량=("재고수량", "sum"),
        Hold수량=("Hold수량", "sum"),
        **{"EU 현지 가용수량": ("EU 현지 가용수량", "sum")},
    )
    grouped = grouped.merge(sku_rep, on="_sku_key", how="left")
    for col in ["브랜드", "상품명", "제품상태", "바코드", "EU 입고단가 원본컬럼", "현지 입고단가 통화", "EU 입고단가 통화", "환율 기준일", "환율 출처"]:
        if col not in df.columns:
            df[col] = ""
        grouped = grouped.merge(_first_non_empty_by_group(df, "_sku_key", col), on="_sku_key", how="left")
    for col in ["현지 입고단가", "EU 입고단가", "CMS 원화 입고단가", "적용 환율", "PA+CA 판매수량", "최근 3개월 판매수량"]:
        if col not in df.columns:
            df[col] = 0
        grouped = grouped.merge(_first_positive_by_group(df, "_sku_key", col), on="_sku_key", how="left")
    if "CMS 재고금액(KRW)" not in df.columns:
        df["CMS 재고금액(KRW)"] = 0
    stock_amount = pd.DataFrame(
        {
            "_sku_key": df["_sku_key"],
            "CMS 재고금액(KRW)": pd.to_numeric(df["CMS 재고금액(KRW)"], errors="coerce").fillna(0),
        }
    ).groupby("_sku_key", as_index=False)["CMS 재고금액(KRW)"].sum()
    grouped = grouped.merge(stock_amount, on="_sku_key", how="left")
    grouped["재고파일 존재여부"] = "Y"
    grouped["SKU등록상태"] = "정상등록"
    return grouped[
        [
            "상품코드",
            "브랜드",
            "상품명",
            "제품상태",
            "바코드",
            "재고수량",
            "Hold수량",
            "EU 현지 가용수량",
            "현지 입고단가",
            "현지 입고단가 통화",
            "CMS 원화 입고단가",
            "CMS 재고금액(KRW)",
            "적용 환율",
            "환율 기준일",
            "환율 출처",
            "EU 입고단가",
            "PA+CA 판매수량",
            "최근 3개월 판매수량",
            "EU 입고단가 원본컬럼",
            "EU 입고단가 통화",
            "재고파일 존재여부",
            "SKU등록상태",
        ]
    ]


def source_identity_df(df: pd.DataFrame, sku_col: str, brand_col: str | None = None, name_col: str | None = None) -> pd.DataFrame:
    if df is None or df.empty or sku_col not in df.columns:
        return pd.DataFrame(columns=["상품코드", "브랜드", "상품명"])
    out = pd.DataFrame({"상품코드": preprocess_mod.clean_identifier_series(df[sku_col])})
    out["브랜드"] = df[brand_col].astype(str) if brand_col and brand_col in df.columns else ""
    out["상품명"] = df[name_col].astype(str) if name_col and name_col in df.columns else ""
    out = out[preprocess_mod.product_sku_mask(out["상품코드"])]
    if out.empty:
        return pd.DataFrame(columns=["상품코드", "브랜드", "상품명"])
    out["_sku_key"] = preprocess_mod.sku_group_key_series(out["상품코드"])
    sku_rep = preprocess_mod.representative_sku_by_key(out["상품코드"]).rename("상품코드").reset_index()
    grouped = sku_rep.merge(
        _first_non_empty_by_group(out, "_sku_key", "브랜드"),
        on="_sku_key",
        how="left",
    ).merge(
        _first_non_empty_by_group(out, "_sku_key", "상품명"),
        on="_sku_key",
        how="left",
    )
    return grouped[["상품코드", "브랜드", "상품명"]]


def sku_unit_price_from_amount_qty(
    df: pd.DataFrame,
    sku_candidates: list[str],
    qty_candidates: list[str],
    amount_candidates: list[str],
    price_col: str,
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["SKU", price_col])
    sku_col = kpi_mod.find_column(df, sku_candidates)
    qty_col = kpi_mod.find_column(df, qty_candidates)
    amount_col = kpi_mod.find_column(df, amount_candidates)
    if sku_col is None or qty_col is None or amount_col is None:
        return pd.DataFrame(columns=["SKU", price_col])
    out = pd.DataFrame(
        {
            "SKU": preprocess_mod.clean_identifier_series(df[sku_col]),
            "수량": kpi_mod.to_number_series(df[qty_col]),
            "금액": kpi_mod.to_number_series(df[amount_col]),
        }
    )
    out = out[preprocess_mod.product_sku_mask(out["SKU"]) & out["수량"].gt(0) & out["금액"].gt(0)]
    if out.empty:
        return pd.DataFrame(columns=["SKU", price_col])
    out["_sku_key"] = preprocess_mod.sku_group_key_series(out["SKU"])
    sku_rep = preprocess_mod.representative_sku_by_key(out["SKU"]).rename("SKU").reset_index()
    grouped = out.groupby("_sku_key", as_index=False).agg(수량=("수량", "sum"), 금액=("금액", "sum")).merge(sku_rep, on="_sku_key", how="left")
    grouped[price_col] = grouped["금액"] / grouped["수량"]
    return grouped[["SKU", price_col]]


def hq_stock_unit_price_eur_df(raw_hq_stock: pd.DataFrame, eur_krw_rate: float) -> pd.DataFrame:
    if raw_hq_stock is None or raw_hq_stock.empty or float(eur_krw_rate) <= 0:
        return pd.DataFrame(columns=["SKU", "본사창고 단가_EUR"])
    sku_col = kpi_mod.find_column(raw_hq_stock, ["상품코드", "SKU", "품목코드", "아이템코드", "itemcode"])
    price_col = kpi_mod.find_column(raw_hq_stock, ["평균단가", "입고단가", "단가", "Unit Price", "평균단가(KRW)", "단가(KRW)"])
    if sku_col is None or price_col is None:
        return pd.DataFrame(columns=["SKU", "본사창고 단가_EUR"])
    out = pd.DataFrame(
        {
            "SKU": preprocess_mod.clean_identifier_series(raw_hq_stock[sku_col]),
            "본사창고 단가_EUR": kpi_mod.to_number_series(raw_hq_stock[price_col]) / float(eur_krw_rate),
        }
    )
    out = out[preprocess_mod.product_sku_mask(out["SKU"]) & out["본사창고 단가_EUR"].gt(0)]
    if out.empty:
        return pd.DataFrame(columns=["SKU", "본사창고 단가_EUR"])
    out["_sku_key"] = preprocess_mod.sku_group_key_series(out["SKU"])
    sku_rep = preprocess_mod.representative_sku_by_key(out["SKU"]).rename("SKU").reset_index()
    return sku_rep.merge(_first_positive_by_group(out, "_sku_key", "본사창고 단가_EUR"), on="_sku_key", how="left")[["SKU", "본사창고 단가_EUR"]]


def fill_blank_text_from_maps(df: pd.DataFrame, target_col: str, maps: list[dict[str, str]], fallback: str = "") -> pd.Series:
    out = df[target_col].astype(str) if target_col in df.columns else pd.Series([""] * len(df), index=df.index)
    for mapping in maps:
        if not mapping:
            continue
        missing = out.map(_is_missing_identity_text)
        candidates = df["상품코드"].astype(str).str.strip().map(mapping).fillna("").astype(str)
        usable = ~candidates.map(_is_missing_identity_text)
        out = out.mask(missing & usable, candidates)
    if fallback:
        missing = out.map(_is_missing_identity_text)
        out = out.mask(missing, fallback)
    return out


def build_order_master_skus(
    eu_stock_df: pd.DataFrame,
    hq_eu_stock_df: pd.DataFrame,
    shipping_df: pd.DataFrame,
    open_po_df: pd.DataFrame,
    sales_validation_df: pd.DataFrame,
    sales_detail_df: pd.DataFrame,
) -> pd.DataFrame:
    sources = [
        source_identity_df(eu_stock_df, "상품코드", "브랜드", "상품명"),
        source_identity_df(hq_eu_stock_df, "상품코드"),
        source_identity_df(shipping_df, "SKU", "브랜드", "상품명"),
        source_identity_df(open_po_df, "SKU"),
        source_identity_df(sales_validation_df, "SKU"),
        source_identity_df(sales_detail_df, "SKU", "브랜드", "상품명"),
    ]
    combined = pd.concat(sources, ignore_index=True)
    combined = combined[preprocess_mod.product_sku_mask(combined["상품코드"])]
    if combined.empty:
        return pd.DataFrame(columns=["상품코드", "브랜드", "상품명"])
    combined["_sku_key"] = preprocess_mod.sku_group_key_series(combined["상품코드"])
    sku_rep = preprocess_mod.representative_sku_by_key(combined["상품코드"]).rename("상품코드").reset_index()
    grouped = sku_rep.merge(
        _first_non_empty_by_group(combined, "_sku_key", "브랜드"),
        on="_sku_key",
        how="left",
    ).merge(
        _first_non_empty_by_group(combined, "_sku_key", "상품명"),
        on="_sku_key",
        how="left",
    )
    return grouped[["상품코드", "브랜드", "상품명"]]
