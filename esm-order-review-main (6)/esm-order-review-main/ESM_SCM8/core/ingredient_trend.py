from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from core.common import PROJECT_ROOT
from core.export_excel_util import append_df, autosize_columns
from core.season_calendar import (
    AMOUNT_COL,
    BRAND_COL,
    DATE_COL,
    MASTER_BRAND_COL,
    MASTER_PRODUCT_NAME_COL,
    PRODUCT_CODE_COL,
    PRODUCT_NAME_COL,
    QTY_COL,
    _first_text,
    _growth,
    _unique_sheet_name,
    merge_sales_with_product_master,
)


DEFAULT_INGREDIENT_MAP_PATH = PROJECT_ROOT / "data" / "ingredient_maps" / "default_ingredient_map.json"


def load_ingredient_keywords(path: str | Path | None = None) -> dict[str, list[str]]:
    map_path = Path(path) if path is not None else DEFAULT_INGREDIENT_MAP_PATH
    with map_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    keywords: dict[str, list[str]] = {}
    for ingredient, values in raw.items():
        clean_ingredient = str(ingredient).strip()
        if not clean_ingredient or not isinstance(values, list):
            continue
        clean_keywords = []
        for value in values:
            keyword = str(value).strip()
            if keyword and keyword not in clean_keywords:
                clean_keywords.append(keyword)
        if clean_keywords:
            keywords[clean_ingredient] = clean_keywords
    return keywords


INGREDIENT_KEYWORDS = load_ingredient_keywords()


def _contains_keyword(text: str, keyword: str) -> bool:
    return re.search(re.escape(keyword), text, flags=re.IGNORECASE) is not None


def tag_ingredient_keywords(
    sku_df: pd.DataFrame,
    name_col: str = PRODUCT_NAME_COL,
    master_name_col: str = MASTER_PRODUCT_NAME_COL,
    ingredient_keywords: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    df = pd.DataFrame(sku_df).copy()
    if df.empty:
        return pd.DataFrame(columns=[PRODUCT_CODE_COL, "ingredient", "matched_keywords", "keyword_count"])

    keyword_map = ingredient_keywords or INGREDIENT_KEYWORDS
    rows = []
    for _, row in df.iterrows():
        text = " ".join(
            str(row.get(col, "") or "")
            for col in (name_col, master_name_col)
            if col in df.columns
        )
        for ingredient, keywords in keyword_map.items():
            matched = [keyword for keyword in keywords if _contains_keyword(text, keyword)]
            if matched:
                next_row = row.to_dict()
                next_row["ingredient"] = ingredient
                next_row["matched_keywords"] = matched
                next_row["keyword_count"] = len(matched)
                rows.append(next_row)
    return pd.DataFrame(rows)


def build_sales_keyword_table(merged_df: pd.DataFrame, sku_keyword_df: pd.DataFrame) -> pd.DataFrame:
    merged = pd.DataFrame(merged_df).copy()
    keyword_df = pd.DataFrame(sku_keyword_df).copy()
    if merged.empty or keyword_df.empty or PRODUCT_CODE_COL not in keyword_df.columns:
        return pd.DataFrame(columns=list(merged.columns) + ["ingredient", "matched_keywords", "keyword_count"])
    cols = [PRODUCT_CODE_COL, "ingredient", "matched_keywords", "keyword_count"]
    keyword_df = keyword_df[cols].drop_duplicates(subset=[PRODUCT_CODE_COL, "ingredient"])
    return merged.merge(keyword_df, on=PRODUCT_CODE_COL, how="inner")


def _with_month_parts(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(df).copy()
    out["year"] = out[DATE_COL].dt.year.astype("Int64")
    out["month"] = out[DATE_COL].dt.month.astype("Int64")
    out["year_month"] = out[DATE_COL].dt.to_period("M").astype(str)
    out["period"] = out[DATE_COL].dt.to_period("M")
    return out


def build_ingredient_monthly_trend(sales_kw_df: pd.DataFrame) -> pd.DataFrame:
    if pd.DataFrame(sales_kw_df).empty:
        return pd.DataFrame(columns=["ingredient", "year", "month", "year_month", QTY_COL, AMOUNT_COL, "SKU수", "브랜드수", "MoM_수량(%)", "MoM_금액(%)", "YoY_수량(%)", "YoY_금액(%)"])
    base = _with_month_parts(sales_kw_df)
    out = (
        base.groupby(["ingredient", "year", "month", "year_month"], dropna=False)
        .agg(**{QTY_COL: (QTY_COL, "sum"), AMOUNT_COL: (AMOUNT_COL, "sum"), "SKU수": (PRODUCT_CODE_COL, "nunique"), "브랜드수": (BRAND_COL, "nunique")})
        .reset_index()
        .sort_values(["ingredient", "year", "month"])
    )
    out["MoM_수량(%)"] = out.groupby("ingredient")[QTY_COL].pct_change() * 100
    out["MoM_금액(%)"] = out.groupby("ingredient")[AMOUNT_COL].pct_change() * 100
    out["YoY_수량(%)"] = out.groupby(["ingredient", "month"])[QTY_COL].pct_change() * 100
    out["YoY_금액(%)"] = out.groupby(["ingredient", "month"])[AMOUNT_COL].pct_change() * 100
    return out


def build_ingredient_growth_metrics(sales_kw_df: pd.DataFrame) -> pd.DataFrame:
    if pd.DataFrame(sales_kw_df).empty:
        return pd.DataFrame(columns=["ingredient", "최근3M_수량", "직전3M_수량", "3M_수량_성장률(%)", "최근3M_금액", "직전3M_금액", "3M_금액_성장률(%)"])
    base = _with_month_parts(sales_kw_df)
    latest = base["period"].max()
    rows = []
    for ingredient, group in base.groupby("ingredient", dropna=False):
        recent = group[(group["period"] >= latest - 2) & (group["period"] <= latest)]
        previous = group[(group["period"] >= latest - 5) & (group["period"] <= latest - 3)]
        recent_qty = float(recent[QTY_COL].sum())
        prev_qty = float(previous[QTY_COL].sum())
        recent_amount = float(recent[AMOUNT_COL].sum())
        prev_amount = float(previous[AMOUNT_COL].sum())
        rows.append(
            {
                "ingredient": ingredient,
                "최근3M_수량": recent_qty,
                "직전3M_수량": prev_qty,
                "3M_수량_성장률(%)": _growth(prev_qty, recent_qty),
                "최근3M_금액": recent_amount,
                "직전3M_금액": prev_amount,
                "3M_금액_성장률(%)": _growth(prev_amount, recent_amount),
            }
        )
    return pd.DataFrame(rows).sort_values("최근3M_수량", ascending=False)


def build_ingredient_summary(sales_kw_df: pd.DataFrame, growth_df: pd.DataFrame) -> pd.DataFrame:
    if pd.DataFrame(sales_kw_df).empty:
        return pd.DataFrame(columns=["ingredient", QTY_COL, AMOUNT_COL, "SKU수", "브랜드수"])
    base = pd.DataFrame(sales_kw_df)
    summary = (
        base.groupby("ingredient", dropna=False)
        .agg(**{QTY_COL: (QTY_COL, "sum"), AMOUNT_COL: (AMOUNT_COL, "sum"), "SKU수": (PRODUCT_CODE_COL, "nunique"), "브랜드수": (BRAND_COL, "nunique")})
        .reset_index()
    )
    return summary.merge(pd.DataFrame(growth_df), on="ingredient", how="left").sort_values(QTY_COL, ascending=False)


def build_ingredient_ytd_comparison(sales_kw_df: pd.DataFrame, latest_month: int | None = None) -> pd.DataFrame:
    if pd.DataFrame(sales_kw_df).empty:
        return pd.DataFrame(columns=["ingredient"])
    base = _with_month_parts(sales_kw_df)
    latest_month = latest_month or int(base["month"].max())
    base = base[base["month"] <= latest_month].copy()
    years = sorted(int(year) for year in base["year"].dropna().unique())
    grouped = base.groupby(["ingredient", "year"], dropna=False).agg(**{QTY_COL: (QTY_COL, "sum"), AMOUNT_COL: (AMOUNT_COL, "sum")}).reset_index()
    rows = []
    for ingredient, group in grouped.groupby("ingredient", dropna=False):
        row = {"ingredient": ingredient}
        by_year = {int(item["year"]): item for _, item in group.iterrows()}
        for year in years:
            item = by_year.get(year)
            row[f"YTD_수량_{year}"] = float(item[QTY_COL]) if item is not None else 0
            row[f"YTD_금액_{year}"] = float(item[AMOUNT_COL]) if item is not None else 0
        for prev, cur in zip(years, years[1:]):
            row[f"수량YTD성장률_{prev}_to_{cur}(%)"] = _growth(row[f"YTD_수량_{prev}"], row[f"YTD_수량_{cur}"])
            row[f"금액YTD성장률_{prev}_to_{cur}(%)"] = _growth(row[f"YTD_금액_{prev}"], row[f"YTD_금액_{cur}"])
        rows.append(row)
    return pd.DataFrame(rows)


def build_ingredient_top_sku(sales_kw_df: pd.DataFrame) -> pd.DataFrame:
    return _top_table(sales_kw_df, [PRODUCT_CODE_COL], PRODUCT_NAME_COL)


def build_ingredient_top_brand(sales_kw_df: pd.DataFrame) -> pd.DataFrame:
    return _top_table(sales_kw_df, [BRAND_COL], BRAND_COL)


def _top_table(sales_kw_df: pd.DataFrame, keys: list[str], label_col: str) -> pd.DataFrame:
    if pd.DataFrame(sales_kw_df).empty:
        return pd.DataFrame(columns=["ingredient", *keys, QTY_COL, AMOUNT_COL, "판매월수", "최근3M_수량", "최근6M_수량"])
    base = _with_month_parts(sales_kw_df)
    latest = base["period"].max()
    rows = []
    for group_keys, group in base.groupby(["ingredient", *keys], dropna=False):
        if not isinstance(group_keys, tuple):
            group_keys = (group_keys,)
        row = {"ingredient": group_keys[0]}
        for idx, key in enumerate(keys, start=1):
            row[key] = group_keys[idx]
        if PRODUCT_CODE_COL in keys:
            row[BRAND_COL] = _first_text(group[BRAND_COL])
            row[PRODUCT_NAME_COL] = _first_text(group[PRODUCT_NAME_COL])
        row[QTY_COL] = float(group[QTY_COL].sum())
        row[AMOUNT_COL] = float(group[AMOUNT_COL].sum())
        row["판매월수"] = int(group["period"].nunique())
        row["최근3M_수량"] = float(group[group["period"] >= latest - 2][QTY_COL].sum())
        row["최근6M_수량"] = float(group[group["period"] >= latest - 5][QTY_COL].sum())
        rows.append(row)
    out = pd.DataFrame(rows).sort_values(["ingredient", QTY_COL], ascending=[True, False])
    return out.groupby("ingredient", dropna=False).head(10).reset_index(drop=True)


def _write_df_sheet(wb, name: str, df: pd.DataFrame) -> None:
    ws = wb.create_sheet(_unique_sheet_name(wb, name))
    append_df(ws, pd.DataFrame(df))
    autosize_columns(ws)
    ws.freeze_panes = "A2"


def append_ingredient_sheets(wb, sales_history_df: pd.DataFrame, prod_df: pd.DataFrame, settings: dict) -> None:
    merged = merge_sales_with_product_master(sales_history_df, prod_df)
    sku_cols = [col for col in [PRODUCT_CODE_COL, BRAND_COL, PRODUCT_NAME_COL, MASTER_BRAND_COL, MASTER_PRODUCT_NAME_COL] if col in merged.columns]
    sku_df = merged[sku_cols].drop_duplicates(subset=[PRODUCT_CODE_COL]) if not merged.empty and PRODUCT_CODE_COL in merged.columns else pd.DataFrame()
    sku_keyword_df = tag_ingredient_keywords(sku_df)
    sales_kw_df = build_sales_keyword_table(merged, sku_keyword_df)
    growth = build_ingredient_growth_metrics(sales_kw_df)

    guide = pd.DataFrame(
        {
            "안내": [
                "본 성분 키워드 분석은 상품명 텍스트 기반 파일명 분석입니다.",
                "상품명에 성분명이 없는 경우 태깅되지 않을 수 있으며, 하나의 상품이 여러 성분에 중복 태깅될 수 있습니다.",
                "성분별 판매 합계는 전체 판매액과 일치하지 않습니다.",
            ]
        }
    )
    unmatched = sku_df[~sku_df[PRODUCT_CODE_COL].isin(sku_keyword_df.get(PRODUCT_CODE_COL, pd.Series(dtype=str)))].copy() if not sku_df.empty else pd.DataFrame()
    _write_df_sheet(wb, "성분_키워드판매집계표", guide)
    _write_df_sheet(wb, "성분_SKU태깅결과", sku_keyword_df)
    _write_df_sheet(wb, "성분_월별트렌드", build_ingredient_monthly_trend(sales_kw_df))
    _write_df_sheet(wb, "성분_요약방향성", build_ingredient_summary(sales_kw_df, growth))
    _write_df_sheet(wb, "성분_3M성장률", growth)
    latest_month = int(_with_month_parts(sales_kw_df)["month"].max()) if not sales_kw_df.empty else None
    _write_df_sheet(wb, "성분_YTD비교", build_ingredient_ytd_comparison(sales_kw_df, latest_month))
    _write_df_sheet(wb, "성분_Top_SKU", build_ingredient_top_sku(sales_kw_df))
    _write_df_sheet(wb, "성분_Top_브랜드", build_ingredient_top_brand(sales_kw_df))
    _write_df_sheet(wb, "성분_미매칭SKU", unmatched)
