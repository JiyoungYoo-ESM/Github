"""Orchestrate season and ingredient analysis without owning table algorithms."""

from __future__ import annotations

import time

import pandas as pd

from backend.services.category_corrections import (
    apply_category_corrections_to_merged,
    append_default_category_correction_products,
    merge_default_category_corrections,
    read_default_category_corrections,
)
from backend.services.dataframe_utils import dataframe_records, date_range_label as _date_range_label
from backend.services.ingredient_analysis_pipeline import build_ingredient_analysis
from backend.services.season_analysis_common import (
    build_month_coverage,
    empty_season_ingredient_analysis,
    exclude_non_revenue_unknown_country_rows,
    parse_season_analysis_options,
)
from backend.services.season_detail_pipeline import build_season_detail_tables
from backend.services.brand_report_summary import build_brand_report_summaries
from backend.services.season_data_quality import build_source_data_quality
from core.season_calendar import (
    AMOUNT_COL,
    CATEGORY1_COL,
    CATEGORY2_COL,
    COUNTRY_COL,
    DATE_COL,
    PRODUCT_MASTER_CATEGORY1_COL,
    PRODUCT_MASTER_CATEGORY2_COL,
    PRODUCT_CODE_COL,
    QTY_COL,
    build_category1_share,
    build_category2_share,
    build_mapping_quality_report,
    build_monthly_category1_summary,
    build_monthly_category2_summary,
    build_monthly_country_category2_summary,
    build_monthly_country_category_summary,
    build_ytd_comparison,
    exclude_season_category1_values,
    merge_sales_with_product_master,
    split_cosmetic_product_scope,
)


class CosmeticScopeValidationError(ValueError):
    """Raised when strict season analysis cannot establish a Cosmetic population."""


def _log_stage(stage: str, started_at: float) -> float:
    now = time.perf_counter()
    print(f"[season_analysis] {stage}: {now - started_at:.2f}s", flush=True)
    return now


def _build_sku_frame(merged: pd.DataFrame) -> pd.DataFrame:
    sku_columns = [
        column
        for column in ["상품코드", "브랜드", "상품명", "브랜드_마스터", "상품명_마스터"]
        if column in merged.columns
    ]
    if merged.empty or PRODUCT_CODE_COL not in merged.columns or not sku_columns:
        return pd.DataFrame()
    return merged[sku_columns].drop_duplicates(subset=[PRODUCT_CODE_COL])


def build_season_ingredient_analysis(
    uploaded_data: dict[str, pd.DataFrame],
    options: dict[str, object] | None = None,
) -> dict[str, dict[str, object]]:
    """Build API season tables by coordinating focused analysis pipelines."""
    empty = empty_season_ingredient_analysis()
    sales_history_df = pd.DataFrame(uploaded_data.get("sales_history", pd.DataFrame()))
    if sales_history_df.empty:
        return empty

    prod_df = pd.DataFrame(uploaded_data.get("prod_list", pd.DataFrame()))
    strict_cosmetic_scope = bool((options or {}).get("strict_cosmetic_scope"))
    default_correction_df = read_default_category_corrections()
    correction_df = merge_default_category_corrections(
        pd.DataFrame(uploaded_data.get("category_correction", pd.DataFrame()))
    )

    try:
        analysis_options = parse_season_analysis_options(options)
        stage_started = time.perf_counter()
        source_data_quality = build_source_data_quality(
            sales_history_df,
            start_date=analysis_options.effective_start_date,
            end_date=analysis_options.effective_end_date,
            eu_local=analysis_options.eu_local,
            entity_code=analysis_options.entity_code,
        )
        prod_df = append_default_category_correction_products(prod_df, default_correction_df)
        merged = merge_sales_with_product_master(
            sales_history_df,
            prod_df,
            start_date=analysis_options.effective_start_date,
            end_date=analysis_options.effective_end_date,
            eu_local=analysis_options.eu_local,
            entity_code=analysis_options.entity_code,
        )
        stage_started = _log_stage(f"standardize/filter/merge rows={len(merged)}", stage_started)
        if merged.empty:
            selected_range = (
                f"{analysis_options.start_date_value or '전체'} ~ {analysis_options.end_date_value or '전체'}"
            )
            source_range = _date_range_label(
                sales_history_df,
                ["출고일", "출고 일자", "일자", "date", "Date"],
            )
            raise ValueError(
                "선택한 분석 기간에 해당하는 판매내역이 없습니다. "
                f"선택 기간: {selected_range}. 파일 내 출고일 범위: {source_range}. "
                "분석 시작일/종료일을 파일 기간에 맞춰 다시 선택해 주세요."
            )

        # Season scope must start from explicit product-master categories.
        # Product-name inference remains available to other legacy consumers
        # but cannot admit a SKU into Cosmetic calendar calculations.
        if PRODUCT_MASTER_CATEGORY1_COL in merged.columns:
            merged[CATEGORY1_COL] = merged[PRODUCT_MASTER_CATEGORY1_COL]
        if PRODUCT_MASTER_CATEGORY2_COL in merged.columns:
            merged[CATEGORY2_COL] = merged[PRODUCT_MASTER_CATEGORY2_COL]
        merged = apply_category_corrections_to_merged(
            merged,
            correction_df,
            PRODUCT_CODE_COL,
            CATEGORY1_COL,
            CATEGORY2_COL,
        )
        merged, product_scope_diagnostics = split_cosmetic_product_scope(merged)
        if strict_cosmetic_scope and merged.empty:
            diagnostic_sku_count = (
                int(product_scope_diagnostics[PRODUCT_CODE_COL].nunique())
                if PRODUCT_CODE_COL in product_scope_diagnostics.columns
                else 0
            )
            raise CosmeticScopeValidationError(
                "상품마스터에서 집계 가능한 Cosmetic SKU가 0건입니다. "
                f"데이터 진단 대상 {diagnostic_sku_count}개 SKU와 상품마스터 class1/class2를 확인해 주세요."
            )
        merged = exclude_season_category1_values(merged)
        merged, excluded_count = exclude_non_revenue_unknown_country_rows(merged, COUNTRY_COL, AMOUNT_COL)
        if strict_cosmetic_scope and merged.empty:
            raise CosmeticScopeValidationError(
                "상품마스터 Cosmetic SKU 중 시즌 캘린더 집계 조건을 충족한 판매가 0건입니다. "
                "샘플·무상·제외상품 조건과 데이터 진단 항목을 확인해 주세요."
            )
        if excluded_count:
            print(
                f"[season_analysis] excluded non-revenue unknown-country rows={excluded_count}",
                flush=True,
            )

        # Coverage and countrySkuMonthly intentionally use the same filtered
        # population so their amount and quantity totals always reconcile.
        month_coverage = build_month_coverage(
            merged,
            DATE_COL,
            start_date=analysis_options.effective_start_date,
            end_date=analysis_options.effective_end_date,
            amount_col=AMOUNT_COL,
            qty_col=QTY_COL,
        )
        stage_started = _log_stage(f"category corrections rows={len(merged)}", stage_started)
        category1_monthly = build_monthly_category1_summary(merged)
        category2_monthly = build_monthly_category2_summary(merged)
        stage_started = _log_stage("monthly category summaries", stage_started)

        ingredient_result = empty["ingredient_analysis"]
        if analysis_options.include_ingredient:
            ingredient_result = build_ingredient_analysis(merged, _build_sku_frame(merged))
            stage_started = _log_stage("ingredient summaries", stage_started)

        details = build_season_detail_tables(merged, diagnostic_source=product_scope_diagnostics)
        stage_started = _log_stage("country/sku/customer summaries", stage_started)
        country_sku_summary_records = dataframe_records(details.country_sku_summary)
        country_sku_monthly_records = dataframe_records(details.country_sku_monthly)
        complete_months = {
            str(item.get("month"))
            for item in month_coverage
            if item.get("status") == "complete" and item.get("month")
        }
        result: dict[str, dict[str, object]] = {
            "season_analysis": {
                # Consumers that need whole-brand totals must never replace this
                # cube with the bounded top-SKU response tables.
                "crossAnalysisComplete": True,
                "sourceDataQuality": source_data_quality,
                "category1Monthly": dataframe_records(category1_monthly),
                "category2Monthly": dataframe_records(category2_monthly),
                "category1Share": dataframe_records(build_category1_share(category1_monthly, merged)),
                "category2Share": dataframe_records(build_category2_share(category2_monthly, merged)),
                "ytdComparison": dataframe_records(build_ytd_comparison(merged, complete_months)),
                "topSku": dataframe_records(details.top_sku),
                "skuMonthly": dataframe_records(details.sku_monthly),
                "mappingQuality": dataframe_records(
                    build_mapping_quality_report(sales_history_df, merged, prod_df.empty)
                ),
                "uncategorizedSku": dataframe_records(details.uncategorized_sku),
                "countryCategoryMonthly": dataframe_records(build_monthly_country_category_summary(merged)),
                "countryCategory2Monthly": dataframe_records(build_monthly_country_category2_summary(merged)),
                "countryTopSku": dataframe_records(details.country_top_sku),
                "countrySkuSummary": country_sku_summary_records,
                "countrySkuMonthly": country_sku_monthly_records,
                "brandReports": build_brand_report_summaries({
                    "countrySkuSummary": country_sku_summary_records,
                    "countrySkuMonthly": country_sku_monthly_records,
                }),
                "dataMonths": sorted(
                    str(value)
                    for value in merged[DATE_COL].dropna().dt.to_period("M").astype(str).unique().tolist()
                ),
                "monthCoverage": month_coverage,
                "countryCustomerSummary": dataframe_records(details.country_customer_summary),
                "countryCategoryCustomerSummary": dataframe_records(details.country_category_customer_summary),
                "customerSalesSummary": dataframe_records(details.customer_sales_summary),
            },
            "ingredient_analysis": ingredient_result,
        }
        _log_stage("json records", stage_started)
        return result
    except CosmeticScopeValidationError:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"[season/ingredient tables skipped] {exc}", flush=True)
        return empty


__all__ = [
    "CosmeticScopeValidationError",
    "build_month_coverage",
    "build_season_ingredient_analysis",
]
