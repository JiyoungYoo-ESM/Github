"""Ingredient-specific aggregation pipeline for season analysis."""

from __future__ import annotations

import pandas as pd

from backend.services.dataframe_utils import dataframe_records
from backend.services.season_analysis_common import empty_season_ingredient_analysis
from core.season_calendar import (
    AMOUNT_COL,
    BRAND_COL,
    COUNTRY_COL,
    DATE_COL,
    PRODUCT_CODE_COL,
    PRODUCT_NAME_COL,
    QTY_COL,
)


def _normalized_dimension(series: pd.Series, missing_value: str) -> pd.Series:
    return series.astype(str).str.strip().replace({"": missing_value, "nan": missing_value, "None": missing_value})


def _country_coverage_records(merged: pd.DataFrame, matched_sku_codes: set[str]) -> list[dict[str, object]]:
    if merged.empty or COUNTRY_COL not in merged.columns or PRODUCT_CODE_COL not in merged.columns:
        return []
    records: list[dict[str, object]] = []
    for country, country_group in merged.groupby(COUNTRY_COL, dropna=False):
        country_skus = set(country_group[PRODUCT_CODE_COL].dropna().astype(str))
        country_total = len(country_skus)
        country_matched = len(country_skus & matched_sku_codes)
        records.append(
            {
                COUNTRY_COL: country,
                "totalSkuCount": country_total,
                "matchedSkuCount": country_matched,
                "unmatchedSkuCount": max(0, country_total - country_matched),
                "coveragePct": (country_matched / country_total * 100) if country_total else 0,
            }
        )
    return records


def _ingredient_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "ingredient" not in frame.columns:
        return pd.DataFrame(columns=["ingredient", QTY_COL, AMOUNT_COL, "SKU수", "브랜드수"])
    aggregations: dict[str, tuple[str, str]] = {
        QTY_COL: (QTY_COL, "sum"),
        AMOUNT_COL: (AMOUNT_COL, "sum"),
    }
    if PRODUCT_CODE_COL in frame.columns:
        aggregations["SKU수"] = (PRODUCT_CODE_COL, "nunique")
    if BRAND_COL in frame.columns:
        aggregations["브랜드수"] = (BRAND_COL, "nunique")
    return (
        frame.groupby("ingredient", dropna=False)
        .agg(**aggregations)
        .reset_index()
        .sort_values([QTY_COL, AMOUNT_COL], ascending=[False, False])
    )


def _country_summary_records(sales_keyword_df: pd.DataFrame) -> list[dict[str, object]]:
    if sales_keyword_df.empty or COUNTRY_COL not in sales_keyword_df.columns or "ingredient" not in sales_keyword_df.columns:
        return []
    base = sales_keyword_df.assign(**{COUNTRY_COL: _normalized_dimension(sales_keyword_df[COUNTRY_COL], "미상")})
    aggregations: dict[str, tuple[str, str]] = {
        QTY_COL: (QTY_COL, "sum"),
        AMOUNT_COL: (AMOUNT_COL, "sum"),
    }
    if PRODUCT_CODE_COL in base.columns:
        aggregations["SKU수"] = (PRODUCT_CODE_COL, "nunique")
    if BRAND_COL in base.columns:
        aggregations["브랜드수"] = (BRAND_COL, "nunique")
    result = (
        base.groupby([COUNTRY_COL, "ingredient"], dropna=False)
        .agg(**aggregations)
        .reset_index()
        .sort_values([COUNTRY_COL, QTY_COL, AMOUNT_COL], ascending=[True, False, False])
    )
    return dataframe_records(result)


def _country_monthly_trend_records(sales_keyword_df: pd.DataFrame) -> list[dict[str, object]]:
    required = {COUNTRY_COL, DATE_COL, "ingredient", QTY_COL, AMOUNT_COL}
    if sales_keyword_df.empty or not required.issubset(sales_keyword_df.columns):
        return []
    base = sales_keyword_df.copy()
    base[DATE_COL] = pd.to_datetime(base[DATE_COL], errors="coerce")
    base = base[base[DATE_COL].notna()].copy()
    if base.empty:
        return []
    base[COUNTRY_COL] = _normalized_dimension(base[COUNTRY_COL], "미상")
    base["year"] = base[DATE_COL].dt.year.astype("Int64")
    base["month"] = base[DATE_COL].dt.month.astype("Int64")
    base["year_month"] = base[DATE_COL].dt.to_period("M").astype(str)
    aggregations: dict[str, tuple[str, str]] = {
        QTY_COL: (QTY_COL, "sum"),
        AMOUNT_COL: (AMOUNT_COL, "sum"),
    }
    if PRODUCT_CODE_COL in base.columns:
        aggregations["SKU수"] = (PRODUCT_CODE_COL, "nunique")
    if BRAND_COL in base.columns:
        aggregations["브랜드수"] = (BRAND_COL, "nunique")
    result = (
        base.groupby([COUNTRY_COL, "ingredient", "year", "month", "year_month"], dropna=False)
        .agg(**aggregations)
        .reset_index()
        .sort_values([COUNTRY_COL, "ingredient", "year_month"])
    )
    return dataframe_records(result)


def _ingredient_monthly_records(
    sales_keyword_df: pd.DataFrame,
    group_columns: list[str],
) -> list[dict[str, object]]:
    required = {"ingredient", QTY_COL, AMOUNT_COL, *group_columns}
    if sales_keyword_df.empty or not required.issubset(sales_keyword_df.columns):
        return []
    base = sales_keyword_df.copy()
    if DATE_COL in base.columns:
        base[DATE_COL] = pd.to_datetime(base[DATE_COL], errors="coerce")
        base = base[base[DATE_COL].notna()].copy()
        base["year"] = base[DATE_COL].dt.year.astype("Int64")
        base["month"] = base[DATE_COL].dt.month.astype("Int64")
        base["year_month"] = base[DATE_COL].dt.to_period("M").astype(str)
    elif {"year", "month"}.issubset(base.columns):
        base["year"] = pd.to_numeric(base["year"], errors="coerce").astype("Int64")
        base["month"] = pd.to_numeric(base["month"], errors="coerce").astype("Int64")
        base = base[base["year"].notna() & base["month"].notna()].copy()
        if "year_month" not in base.columns:
            base["year_month"] = base["year"].astype(str) + "-" + base["month"].astype(str).str.zfill(2)
    else:
        return []
    if base.empty:
        return []
    for column in group_columns:
        base[column] = _normalized_dimension(base[column], "-")
    group_by = ["ingredient", *group_columns, "year", "month", "year_month"]
    result = (
        base.groupby(group_by, dropna=False)
        .agg(**{QTY_COL: (QTY_COL, "sum"), AMOUNT_COL: (AMOUNT_COL, "sum")})
        .reset_index()
        .sort_values(["ingredient", *group_columns, "year_month"])
    )
    return dataframe_records(result)


def build_ingredient_analysis(
    merged: pd.DataFrame,
    sku_df: pd.DataFrame,
) -> dict[str, list[dict[str, object]]]:
    """Build all ingredient tables while isolating optional ingredient failures."""
    empty = empty_season_ingredient_analysis()["ingredient_analysis"]
    try:
        from core.ingredient_trend import (
            INGREDIENT_KEYWORDS,
            build_ingredient_monthly_trend,
            build_ingredient_top_brand,
            build_ingredient_top_sku,
            build_sales_keyword_table,
            tag_ingredient_keywords,
        )

        sku_keyword_df = tag_ingredient_keywords(sku_df)
        sales_keyword_df = build_sales_keyword_table(merged, sku_keyword_df)
        tagged_sku_codes = sku_keyword_df.get(PRODUCT_CODE_COL, pd.Series(dtype=str))
        unmatched_sku_df = (
            sku_df[~sku_df[PRODUCT_CODE_COL].isin(tagged_sku_codes)].copy()
            if not sku_df.empty and PRODUCT_CODE_COL in sku_df.columns
            else pd.DataFrame()
        )
        matched_sku_codes = (
            set(sku_keyword_df[PRODUCT_CODE_COL].dropna().astype(str))
            if not sku_keyword_df.empty and PRODUCT_CODE_COL in sku_keyword_df.columns
            else set()
        )
        all_sku_codes = (
            set(sku_df[PRODUCT_CODE_COL].dropna().astype(str))
            if not sku_df.empty and PRODUCT_CODE_COL in sku_df.columns
            else set()
        )
        total_sku_count = len(all_sku_codes)
        matched_sku_count = len(all_sku_codes & matched_sku_codes)
        coverage_records = [
            {
                "totalSkuCount": total_sku_count,
                "matchedSkuCount": matched_sku_count,
                "unmatchedSkuCount": max(0, total_sku_count - matched_sku_count),
                "coveragePct": (matched_sku_count / total_sku_count * 100) if total_sku_count else 0,
            }
        ]

        return {
            "keywordMap": [{"ingredient": key, "keywords": value} for key, value in INGREDIENT_KEYWORDS.items()],
            "skuTags": dataframe_records(sku_keyword_df),
            "monthlyTrend": dataframe_records(build_ingredient_monthly_trend(sales_keyword_df)),
            "summary": dataframe_records(_ingredient_summary(sales_keyword_df)),
            "growth3m": [],
            "ytdComparison": [],
            "topSku": dataframe_records(build_ingredient_top_sku(sales_keyword_df)),
            "topBrand": dataframe_records(build_ingredient_top_brand(sales_keyword_df)),
            "brandMonthlyTrend": _ingredient_monthly_records(sales_keyword_df, [BRAND_COL]),
            "skuMonthlyTrend": _ingredient_monthly_records(
                sales_keyword_df,
                [PRODUCT_CODE_COL, BRAND_COL, PRODUCT_NAME_COL],
            ),
            "unmatchedSku": dataframe_records(unmatched_sku_df),
            "coverage": coverage_records,
            "countryCoverage": _country_coverage_records(merged, matched_sku_codes),
            "countryMonthlyTrend": _country_monthly_trend_records(sales_keyword_df),
            "countrySummary": _country_summary_records(sales_keyword_df),
            "countryGrowth3m": [],
            "countryYtdComparison": [],
            "countryTopSku": [],
            "countryTopBrand": [],
        }
    except Exception as exc:  # noqa: BLE001
        print(f"[ingredient tables skipped] {exc}", flush=True)
        return empty


__all__ = ["build_ingredient_analysis"]
