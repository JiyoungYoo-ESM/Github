"""Country, SKU, and customer detail tables for season analysis."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from backend.services.season_analysis_common import filter_rows_by_values, top_rows_per_group
from core.season_calendar import (
    AMOUNT_COL,
    BRAND_COL,
    CATEGORY1_COL,
    CATEGORY2_COL,
    COUNTRY_COL,
    DATE_COL,
    DIAGNOSTIC_EDITABLE_COL,
    DIAGNOSTIC_REASON_COL,
    PRODUCT_CODE_COL,
    PRODUCT_NAME_COL,
    QTY_COL,
    UNMAPPED,
    build_country_category_customer_summary,
    build_country_customer_summary,
    build_customer_sales_summary,
    build_top_sku_by_category,
)


@dataclass(frozen=True)
class SeasonDetailTables:
    top_sku: pd.DataFrame
    sku_monthly: pd.DataFrame
    uncategorized_sku: pd.DataFrame
    country_top_sku: pd.DataFrame
    country_sku_summary: pd.DataFrame
    country_sku_monthly: pd.DataFrame
    country_customer_summary: pd.DataFrame
    country_category_customer_summary: pd.DataFrame
    customer_sales_summary: pd.DataFrame


def _normalized_country_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or COUNTRY_COL not in frame.columns:
        return frame
    return frame.assign(
        **{
            COUNTRY_COL: frame[COUNTRY_COL]
            .astype(str)
            .str.strip()
            .replace({"": "미상", "nan": "미상", "None": "미상"})
        }
    )


def _build_country_sku_tables(merged: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if merged.empty or COUNTRY_COL not in merged.columns:
        return pd.DataFrame(), pd.DataFrame()
    normalized = _normalized_country_frame(merged)
    country_top_sku = build_top_sku_by_category(normalized, group_columns=[COUNTRY_COL])
    if not country_top_sku.empty:
        country_top_sku = top_rows_per_group(
            country_top_sku,
            [COUNTRY_COL, CATEGORY1_COL, CATEGORY2_COL],
            [QTY_COL, AMOUNT_COL],
            80,
        )
    country_sku_summary = (
        normalized.groupby(
            [COUNTRY_COL, CATEGORY1_COL, CATEGORY2_COL, PRODUCT_CODE_COL, BRAND_COL, PRODUCT_NAME_COL],
            dropna=False,
        )
        .agg(**{QTY_COL: (QTY_COL, "sum"), AMOUNT_COL: (AMOUNT_COL, "sum")})
        .reset_index()
        .sort_values([COUNTRY_COL, CATEGORY1_COL, CATEGORY2_COL, PRODUCT_CODE_COL])
    )
    return country_top_sku, country_sku_summary


def _add_month_dimensions(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["year"] = result[DATE_COL].dt.year.astype("Int64")
    result["month"] = result[DATE_COL].dt.month.astype("Int64")
    result["year_month"] = result[DATE_COL].dt.to_period("M").astype(str)
    return result


def _build_sku_monthly_tables(
    merged: pd.DataFrame,
    response_sku_codes: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if merged.empty:
        return pd.DataFrame(), pd.DataFrame()

    sku_base = (
        filter_rows_by_values(merged, PRODUCT_CODE_COL, response_sku_codes)
        if response_sku_codes
        else merged.head(0).copy()
    )
    sku_base = _add_month_dimensions(sku_base)
    sku_monthly = (
        sku_base.groupby(
            [
                "year",
                "month",
                "year_month",
                CATEGORY1_COL,
                CATEGORY2_COL,
                PRODUCT_CODE_COL,
                BRAND_COL,
                PRODUCT_NAME_COL,
            ],
            dropna=False,
        )
        .agg(**{QTY_COL: (QTY_COL, "sum"), AMOUNT_COL: (AMOUNT_COL, "sum")})
        .reset_index()
        .sort_values(["year_month", CATEGORY1_COL, CATEGORY2_COL, PRODUCT_CODE_COL])
    )

    # Cross-analysis requires the complete country/brand/SKU population. Only
    # the compact skuMonthly response is limited to the selected top SKUs.
    country_sku_base = _add_month_dimensions(merged)
    country_sku_monthly = pd.DataFrame()
    if COUNTRY_COL in country_sku_base.columns:
        country_sku_monthly = (
            _normalized_country_frame(country_sku_base)
            .groupby(
                [
                    COUNTRY_COL,
                    "year",
                    "month",
                    "year_month",
                    CATEGORY1_COL,
                    CATEGORY2_COL,
                    PRODUCT_CODE_COL,
                    BRAND_COL,
                    PRODUCT_NAME_COL,
                ],
                dropna=False,
            )
            .agg(**{QTY_COL: (QTY_COL, "sum"), AMOUNT_COL: (AMOUNT_COL, "sum")})
            .reset_index()
            .sort_values([COUNTRY_COL, "year_month", CATEGORY1_COL, CATEGORY2_COL, PRODUCT_CODE_COL])
        )
    return sku_monthly, country_sku_monthly


def _build_uncategorized_sku(merged: pd.DataFrame) -> pd.DataFrame:
    if merged.empty:
        return pd.DataFrame()
    if DIAGNOSTIC_REASON_COL in merged.columns:
        uncategorized_base = merged[merged[DIAGNOSTIC_REASON_COL].astype(str).str.strip().ne("")].copy()
    else:
        uncategorized_base = merged[
            merged[CATEGORY1_COL].astype(str).eq(UNMAPPED) | merged[CATEGORY2_COL].astype(str).eq(UNMAPPED)
        ].copy()
    if uncategorized_base.empty:
        return pd.DataFrame()
    group_columns = [CATEGORY1_COL, CATEGORY2_COL, PRODUCT_CODE_COL, BRAND_COL, PRODUCT_NAME_COL]
    for column in (DIAGNOSTIC_REASON_COL, DIAGNOSTIC_EDITABLE_COL):
        if column in uncategorized_base.columns:
            group_columns.append(column)
    return (
        uncategorized_base.groupby(
            group_columns,
            dropna=False,
        )
        .agg(
            **{
                QTY_COL: (QTY_COL, "sum"),
                AMOUNT_COL: (AMOUNT_COL, "sum"),
                "판매월수": (DATE_COL, lambda values: values.dt.to_period("M").nunique()),
                "판매행수": (PRODUCT_CODE_COL, "size"),
            }
        )
        .reset_index()
        .sort_values([QTY_COL, AMOUNT_COL], ascending=[False, False])
    )


def build_season_detail_tables(
    merged: pd.DataFrame,
    *,
    diagnostic_source: pd.DataFrame | None = None,
) -> SeasonDetailTables:
    """Build bounded response tables plus the complete cross-analysis cube."""
    top_sku = top_rows_per_group(
        build_top_sku_by_category(merged),
        [CATEGORY1_COL, CATEGORY2_COL],
        [QTY_COL, AMOUNT_COL],
        80,
    )
    response_sku_codes = (
        set(top_sku[PRODUCT_CODE_COL].dropna().astype(str))
        if not top_sku.empty and PRODUCT_CODE_COL in top_sku.columns
        else set()
    )
    country_top_sku, country_sku_summary = _build_country_sku_tables(merged)
    sku_monthly, country_sku_monthly = _build_sku_monthly_tables(merged, response_sku_codes)

    return SeasonDetailTables(
        top_sku=top_sku,
        sku_monthly=sku_monthly,
        uncategorized_sku=_build_uncategorized_sku(
            diagnostic_source if diagnostic_source is not None else merged
        ),
        country_top_sku=country_top_sku,
        country_sku_summary=country_sku_summary,
        country_sku_monthly=country_sku_monthly,
        country_customer_summary=build_country_customer_summary(merged).head(500),
        country_category_customer_summary=top_rows_per_group(
            build_country_category_customer_summary(merged),
            [COUNTRY_COL, CATEGORY1_COL, CATEGORY2_COL],
            [QTY_COL, AMOUNT_COL],
            30,
        ),
        customer_sales_summary=build_customer_sales_summary(merged).head(500),
    )


__all__ = ["SeasonDetailTables", "build_season_detail_tables"]
