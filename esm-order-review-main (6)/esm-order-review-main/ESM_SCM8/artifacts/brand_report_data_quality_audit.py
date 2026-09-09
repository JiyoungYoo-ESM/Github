from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.brand_report_summary import (
    brand_report_summaries_match_source,
    build_brand_report_summaries,
)
from backend.services.category_corrections import (
    apply_category_corrections_to_merged,
    merge_default_category_corrections,
)
from backend.services.season_analysis_common import exclude_non_revenue_unknown_country_rows
from core.season_calendar import (
    AMOUNT_COL,
    BRAND_COL,
    CATEGORY1_COL,
    CATEGORY2_COL,
    COUNTRY_COL,
    DATE_COL,
    PRODUCT_CODE_COL,
    PRODUCT_NAME_COL,
    QTY_COL,
    UNMAPPED,
    exclude_season_category1_values,
    merge_sales_with_product_master,
    normalize_product_code,
)


SEASON_SNAPSHOT = (
    PROJECT_ROOT
    / "backend"
    / "storage"
    / "latest_season_trend"
    / "latest_adminmaster__PL.json"
)
ORDER_SNAPSHOT = (
    PROJECT_ROOT
    / "backend"
    / "storage"
    / "latest_order_review"
    / "adminmaster__PL__06ef365e-3b27-4980-b416-f4627440f520.json"
)


def _empty_mask(series: pd.Series) -> pd.Series:
    text = series.astype("string").fillna("").str.strip()
    return text.isin({"", "-", "nan", "None", "none", "N/A", "n/a", "<NA>"})


def _number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype("string").str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )


def _close(left: float, right: float) -> bool:
    tolerance = max(0.01, abs(left) * 1e-9)
    return abs(left - right) <= tolerance


def _find_source_cache(payload: dict[str, Any]) -> Path:
    uploads = {
        str(item.get("key")): int(item.get("rows") or 0)
        for item in payload.get("uploaded_files", [])
        if isinstance(item, dict)
    }
    candidates: list[tuple[float, Path]] = []
    cache_dir = PROJECT_ROOT / "backend" / "storage" / "cms_fetch_cache"
    for path in cache_dir.glob("*.json"):
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            raw = cached.get("raw")
            if not isinstance(raw, dict):
                continue
            if (
                len(raw.get("sales_history") or []) == uploads.get("sales_history")
                and len(raw.get("prod_list") or []) == uploads.get("prod_list")
            ):
                candidates.append((float(cached.get("created_at") or 0), path))
        except (OSError, ValueError, TypeError):
            continue
    if not candidates:
        raise FileNotFoundError("분석 스냅샷과 행 수가 일치하는 CMS 원천 캐시를 찾지 못했습니다.")
    return max(candidates, key=lambda item: item[0])[1]


def _brand_reconciliation(
    summary: pd.DataFrame,
    reports: list[dict[str, Any]],
) -> pd.DataFrame:
    expected = (
        summary.groupby(BRAND_COL, dropna=False)
        .agg(
            source_amount=(AMOUNT_COL, "sum"),
            source_qty=(QTY_COL, "sum"),
            source_skus=(PRODUCT_CODE_COL, "nunique"),
            source_countries=(COUNTRY_COL, "nunique"),
            source_categories=(CATEGORY1_COL, "nunique"),
        )
        .reset_index()
    )
    report_frame = pd.DataFrame(
        [
            {
                BRAND_COL: row.get("brand"),
                "report_amount": float(row.get("amount") or 0),
                "report_qty": float(row.get("qty") or 0),
                "report_skus": int(row.get("skuCount") or 0),
                "report_countries": int(row.get("countryCount") or 0),
                "report_categories": int(row.get("categoryCount") or 0),
                "monthly_amount": sum(float(item.get("amount") or 0) for item in row.get("monthly") or []),
                "top_sku_amount": sum(float(item.get("amount") or 0) for item in row.get("topSkus") or []),
            }
            for row in reports
        ]
    )
    merged = expected.merge(report_frame, on=BRAND_COL, how="outer", indicator=True)
    merged["amount_diff"] = merged["report_amount"] - merged["source_amount"]
    merged["qty_diff"] = merged["report_qty"] - merged["source_qty"]
    merged["monthly_diff"] = merged["monthly_amount"] - merged["source_amount"]
    merged["top5_share_pct"] = merged["top_sku_amount"] / merged["source_amount"].replace(0, pd.NA) * 100
    merged["counts_match"] = (
        merged["source_skus"].eq(merged["report_skus"])
        & merged["source_countries"].eq(merged["report_countries"])
        & merged["source_categories"].eq(merged["report_categories"])
    )
    return merged.sort_values("source_amount", ascending=False)


def _stock_profile(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], pd.DataFrame]:
    stock = pd.DataFrame(rows)
    numeric_columns = [
        "유럽 가용재고",
        "기준_3M_판매수량",
        "PA+CA 판매수량",
        "일평균 판매수량",
        "발주 필요 수량",
        "긴급 보충 필요 수량",
    ]
    for column in numeric_columns:
        if column in stock.columns:
            stock[column] = pd.to_numeric(stock[column], errors="coerce")

    expected_daily = stock["기준_3M_판매수량"] / 90
    daily_diff = (stock["일평균 판매수량"] - expected_daily).abs()
    sku_text = stock["상품코드"].astype("string").fillna("").str.strip()
    base_dates = stock["기준일"].astype("string").fillna("").str.strip()
    stock_brands = stock["브랜드"].astype("string").fillna("").str.strip()

    profile = {
        "rows": int(len(stock)),
        "distinct_skus": int(sku_text[sku_text.ne("")].nunique()),
        "duplicate_sku_rows": int(sku_text.duplicated(keep=False).sum()),
        "missing_sku_rows": int(sku_text.eq("").sum()),
        "missing_brand_rows": int(stock_brands.eq("").sum()),
        "base_dates": sorted(base_dates[base_dates.ne("")].unique().tolist()),
        "negative_available_rows": int(stock["유럽 가용재고"].lt(0).sum()),
        "negative_recent_sales_rows": int(stock["기준_3M_판매수량"].lt(0).sum()),
        "daily_sales_formula_mismatch_rows": int(daily_diff.gt(1e-9).sum()),
        "available_null_rows": int(stock["유럽 가용재고"].isna().sum()),
        "daily_sales_null_rows": int(stock["일평균 판매수량"].isna().sum()),
        "order_required_rows": int(stock["우선 액션"].astype(str).str.contains("발주 필요", na=False).sum()),
    }

    stock_by_brand = (
        stock.groupby("브랜드", dropna=False)
        .agg(
            stock_skus=("상품코드", "nunique"),
            available_qty=("유럽 가용재고", "sum"),
            daily_sales_qty=("일평균 판매수량", "sum"),
            risk_skus=("우선 액션", lambda values: values.astype(str).str.contains("발주 필요", na=False).sum()),
        )
        .reset_index()
    )
    stock_by_brand["moi"] = (
        stock_by_brand["available_qty"]
        / stock_by_brand["daily_sales_qty"].replace(0, pd.NA)
        / 30
    )
    return profile, stock_by_brand


def run_audit() -> dict[str, Any]:
    payload = json.loads(SEASON_SNAPSHOT.read_text(encoding="utf-8"))
    season = payload["season_analysis"]
    options = payload["analysis_options"]
    source_cache_path = _find_source_cache(payload)
    source_cache = json.loads(source_cache_path.read_text(encoding="utf-8"))
    raw = source_cache["raw"]
    sales = pd.DataFrame(raw["sales_history"])
    products = pd.DataFrame(raw["prod_list"])

    required_columns = [
        "invc_no",
        "prod_cd",
        "prod_nm",
        "brand_nm",
        "qty",
        "amount",
        "amount_krw",
        "curr",
        "ship_dt",
        "biz_type",
        "country",
    ]
    completeness_rows = []
    for column in required_columns:
        missing = int(_empty_mask(sales[column]).sum()) if column in sales else len(sales)
        completeness_rows.append(
            {
                "column": column,
                "missing_rows": missing,
                "missing_rate_pct": round(missing / len(sales) * 100, 4) if len(sales) else 0,
            }
        )
    completeness = pd.DataFrame(completeness_rows)

    ship_dates = pd.to_datetime(sales["ship_dt"], errors="coerce")
    qty = _number(sales["qty"])
    source_amount = _number(sales["amount"])
    normalized_amount = _number(sales["amount_krw"])
    currency = sales["curr"].astype("string").fillna("").str.upper().str.strip()
    comparable = source_amount.abs().gt(0) & normalized_amount.abs().gt(0)
    currency_ratio = (
        pd.DataFrame(
            {
                "currency": currency[comparable],
                "ratio": (normalized_amount[comparable].abs() / source_amount[comparable].abs()),
            }
        )
        .groupby("currency")
        .agg(rows=("ratio", "size"), median_ratio=("ratio", "median"))
        .reset_index()
        .sort_values("rows", ascending=False)
    )

    exact_duplicate_rows = int(sales.duplicated(keep=False).sum())
    duplicate_excess = sales[sales.duplicated(keep="first")].copy()
    duplicate_rows = sales.loc[sales.duplicated(keep=False)].copy()
    duplicate_rows["_source_position"] = duplicate_rows.index
    duplicate_group_positions = (
        duplicate_rows.groupby(list(sales.columns), dropna=False)["_source_position"]
        .apply(list)
        .tolist()
    )
    duplicate_group_pages = [
        sorted({int(position) // 2000 + 1 for position in positions})
        for positions in duplicate_group_positions
    ]
    duplicate_diagnostics = {
        "groups": len(duplicate_group_positions),
        "all_groups_are_pairs": all(len(positions) == 2 for positions in duplicate_group_positions),
        "same_page_groups": sum(len(pages) == 1 for pages in duplicate_group_pages),
        "cross_page_groups": sum(len(pages) > 1 for pages in duplicate_group_pages),
        "adjacent_position_groups": sum(
            len(positions) == 2 and abs(positions[1] - positions[0]) == 1
            for positions in duplicate_group_positions
        ),
        "maximum_position_gap": max(
            (max(positions) - min(positions) for positions in duplicate_group_positions),
            default=0,
        ),
        "cross_page_pairs": pd.Series(
            [
                f"{pages[0]}→{pages[-1]}"
                for pages in duplicate_group_pages
                if len(pages) > 1
            ],
            dtype="string",
        ).value_counts().to_dict(),
        "duplicate_months": (
            pd.to_datetime(duplicate_excess["ship_dt"], errors="coerce")
            .dt.to_period("M")
            .astype("string")
            .value_counts()
            .sort_index()
            .to_dict()
        ),
    }
    invoice_sku_duplicate_rows = int(
        sales.duplicated(["invc_no", "prod_cd"], keep=False).sum()
    )
    zero_amount_mask = qty.gt(0) & normalized_amount.fillna(0).eq(0)
    zero_amount_rows = sales.loc[zero_amount_mask].copy()
    negative_mask = qty.lt(0) | normalized_amount.lt(0)
    negative_rows = sales.loc[negative_mask].copy()
    duplicate_excess_qty = float(_number(duplicate_excess["qty"]).fillna(0).sum())
    duplicate_excess_amount = float(_number(duplicate_excess["amount_krw"]).fillna(0).sum())
    raw_total_qty = float(qty.fillna(0).sum())
    raw_total_amount = float(normalized_amount.fillna(0).sum())
    raw_profile = {
        "rows": int(len(sales)),
        "columns": int(len(sales.columns)),
        "date_min": ship_dates.min().date().isoformat() if ship_dates.notna().any() else None,
        "date_max": ship_dates.max().date().isoformat() if ship_dates.notna().any() else None,
        "invalid_date_rows": int(ship_dates.isna().sum()),
        "exact_duplicate_rows": exact_duplicate_rows,
        "invoice_sku_duplicate_rows": invoice_sku_duplicate_rows,
        "negative_qty_rows": int(qty.lt(0).sum()),
        "negative_source_amount_rows": int(source_amount.lt(0).sum()),
        "negative_normalized_amount_rows": int(normalized_amount.lt(0).sum()),
        "positive_qty_zero_normalized_amount_rows": int((qty.gt(0) & normalized_amount.fillna(0).eq(0)).sum()),
        "zero_qty_nonzero_normalized_amount_rows": int((qty.fillna(0).eq(0) & normalized_amount.fillna(0).ne(0)).sum()),
        "currency_counts": currency.value_counts(dropna=False).to_dict(),
    }
    anomaly_profile = {
        "duplicate_groups": int(
            sales.loc[sales.duplicated(keep=False)]
            .groupby(list(sales.columns), dropna=False)
            .ngroups
        ),
        "duplicate_excess_rows_if_keep_first": int(len(duplicate_excess)),
        "duplicate_excess_qty": duplicate_excess_qty,
        "duplicate_excess_qty_share_pct": round(
            duplicate_excess_qty / max(abs(raw_total_qty), 1) * 100,
            4,
        ),
        "duplicate_excess_amount": duplicate_excess_amount,
        "duplicate_excess_amount_share_pct": round(
            duplicate_excess_amount / max(abs(raw_total_amount), 1) * 100,
            4,
        ),
        "duplicate_top_brands": (
            duplicate_excess["brand_nm"]
            .astype("string")
            .fillna("")
            .value_counts()
            .head(5)
            .to_dict()
        ),
        "zero_amount_qty": float(_number(zero_amount_rows["qty"]).fillna(0).sum()),
        "zero_amount_qty_share_pct": round(
            float(_number(zero_amount_rows["qty"]).fillna(0).sum())
            / max(abs(raw_total_qty), 1)
            * 100,
            4,
        ),
        "zero_amount_distinct_skus": int(
            zero_amount_rows["prod_cd"].astype("string").fillna("").nunique()
        ),
        "zero_amount_top_brands": (
            zero_amount_rows["brand_nm"]
            .astype("string")
            .fillna("")
            .value_counts()
            .head(5)
            .to_dict()
        ),
        "zero_amount_biz_types": (
            zero_amount_rows["biz_type"]
            .astype("string")
            .fillna("")
            .value_counts()
            .to_dict()
        ),
        "negative_rows": int(len(negative_rows)),
        "negative_qty_and_amount_same_sign_rows": int(
            (
                _number(negative_rows["qty"]).lt(0)
                & _number(negative_rows["amount_krw"]).lt(0)
            ).sum()
        ),
        "negative_qty_sum": float(_number(negative_rows["qty"]).fillna(0).sum()),
        "negative_amount_sum": float(
            _number(negative_rows["amount_krw"]).fillna(0).sum()
        ),
    }

    merged = merge_sales_with_product_master(
        sales,
        products,
        start_date=pd.Timestamp(options["start_date"]),
        end_date=pd.Timestamp(options["end_date"]) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1),
        eu_local=bool(options.get("eu_local")),
    )
    rows_after_standardize = len(merged)
    correction_df = merge_default_category_corrections(pd.DataFrame())
    corrected = apply_category_corrections_to_merged(
        merged,
        correction_df,
        PRODUCT_CODE_COL,
        CATEGORY1_COL,
        CATEGORY2_COL,
    )
    category_filtered = exclude_season_category1_values(corrected)
    final_merged, unknown_country_excluded = exclude_non_revenue_unknown_country_rows(
        category_filtered,
        COUNTRY_COL,
        AMOUNT_COL,
    )
    final_zero_amount_mask = (
        pd.to_numeric(final_merged[QTY_COL], errors="coerce").fillna(0).gt(0)
        & pd.to_numeric(final_merged[AMOUNT_COL], errors="coerce").fillna(0).eq(0)
    )
    final_negative_mask = (
        pd.to_numeric(final_merged[QTY_COL], errors="coerce").fillna(0).lt(0)
        | pd.to_numeric(final_merged[AMOUNT_COL], errors="coerce").fillna(0).lt(0)
    )
    final_total_qty = float(
        pd.to_numeric(final_merged[QTY_COL], errors="coerce").fillna(0).sum()
    )
    final_total_amount = float(
        pd.to_numeric(final_merged[AMOUNT_COL], errors="coerce").fillna(0).sum()
    )
    anomaly_profile.update(
        {
            "final_zero_amount_rows": int(final_zero_amount_mask.sum()),
            "final_zero_amount_qty": float(
                pd.to_numeric(
                    final_merged.loc[final_zero_amount_mask, QTY_COL],
                    errors="coerce",
                ).fillna(0).sum()
            ),
            "final_zero_amount_qty_share_pct": round(
                float(
                    pd.to_numeric(
                        final_merged.loc[final_zero_amount_mask, QTY_COL],
                        errors="coerce",
                    ).fillna(0).sum()
                )
                / max(abs(final_total_qty), 1)
                * 100,
                4,
            ),
            "final_negative_rows": int(final_negative_mask.sum()),
            "final_negative_amount": float(
                pd.to_numeric(
                    final_merged.loc[final_negative_mask, AMOUNT_COL],
                    errors="coerce",
                ).fillna(0).sum()
            ),
            "final_negative_amount_share_pct": round(
                float(
                    pd.to_numeric(
                        final_merged.loc[final_negative_mask, AMOUNT_COL],
                        errors="coerce",
                    ).fillna(0).sum()
                )
                / max(abs(final_total_amount), 1)
                * 100,
                4,
            ),
        }
    )

    product_codes = {
        normalize_product_code(value)
        for value in products["prod_cd"].tolist()
        if str(value or "").strip()
    }
    merged_codes = final_merged[PRODUCT_CODE_COL].astype(str)
    unmatched_master = ~merged_codes.isin(product_codes)
    mapping_profile = {
        "product_rows": int(len(products)),
        "distinct_product_codes": int(len(product_codes)),
        "duplicate_product_code_rows": int(
            products["prod_cd"].map(normalize_product_code).duplicated(keep=False).sum()
        ),
        "final_sales_rows": int(len(final_merged)),
        "unmatched_master_rows": int(unmatched_master.sum()),
        "unmatched_master_qty_share_pct": round(
            float(final_merged.loc[unmatched_master, QTY_COL].sum())
            / max(float(final_merged[QTY_COL].sum()), 1)
            * 100,
            4,
        ),
        "unmatched_master_amount_share_pct": round(
            float(final_merged.loc[unmatched_master, AMOUNT_COL].sum())
            / max(float(final_merged[AMOUNT_COL].sum()), 1)
            * 100,
            4,
        ),
        "unmapped_category_rows": int(
            (
                final_merged[CATEGORY1_COL].astype(str).eq(UNMAPPED)
                | final_merged[CATEGORY2_COL].astype(str).eq(UNMAPPED)
            ).sum()
        ),
        "missing_brand_rows": int(_empty_mask(final_merged[BRAND_COL]).sum()),
        "missing_country_rows": int(_empty_mask(final_merged[COUNTRY_COL]).sum()),
    }

    summary = pd.DataFrame(season["countrySkuSummary"])
    monthly = pd.DataFrame(season["countrySkuMonthly"])
    coverage = pd.DataFrame(season["monthCoverage"])
    reports = season["brandReports"]
    rebuilt_reports = build_brand_report_summaries(season)
    brand_reconciliation = _brand_reconciliation(summary, reports)

    source_total_amount = float(final_merged[AMOUNT_COL].sum())
    source_total_qty = float(final_merged[QTY_COL].sum())
    summary_total_amount = float(pd.to_numeric(summary[AMOUNT_COL], errors="coerce").fillna(0).sum())
    summary_total_qty = float(pd.to_numeric(summary[QTY_COL], errors="coerce").fillna(0).sum())
    monthly_total_amount = float(pd.to_numeric(monthly[AMOUNT_COL], errors="coerce").fillna(0).sum())
    monthly_total_qty = float(pd.to_numeric(monthly[QTY_COL], errors="coerce").fillna(0).sum())
    coverage_total_amount = float(pd.to_numeric(coverage["totalAmount"], errors="coerce").fillna(0).sum())
    coverage_total_qty = float(pd.to_numeric(coverage["totalQty"], errors="coerce").fillna(0).sum())
    report_total_amount = sum(float(row.get("amount") or 0) for row in reports)
    report_total_qty = sum(float(row.get("qty") or 0) for row in reports)
    totals = pd.DataFrame(
        [
            {"layer": "reconstructed_source", "amount": source_total_amount, "qty": source_total_qty},
            {"layer": "countrySkuSummary", "amount": summary_total_amount, "qty": summary_total_qty},
            {"layer": "countrySkuMonthly", "amount": monthly_total_amount, "qty": monthly_total_qty},
            {"layer": "monthCoverage", "amount": coverage_total_amount, "qty": coverage_total_qty},
            {"layer": "brandReports", "amount": report_total_amount, "qty": report_total_qty},
        ]
    )
    totals["amount_diff_vs_source"] = totals["amount"] - source_total_amount
    totals["qty_diff_vs_source"] = totals["qty"] - source_total_qty

    report_checks = {
        "cached_reports_match_source_guard": bool(brand_report_summaries_match_source(season, reports)),
        "cached_reports_equal_rebuild": reports == rebuilt_reports,
        "source_summary_amount_match": _close(source_total_amount, summary_total_amount),
        "source_summary_qty_match": _close(source_total_qty, summary_total_qty),
        "summary_monthly_amount_match": _close(summary_total_amount, monthly_total_amount),
        "summary_monthly_qty_match": _close(summary_total_qty, monthly_total_qty),
        "monthly_coverage_amount_match": _close(monthly_total_amount, coverage_total_amount),
        "monthly_coverage_qty_match": _close(monthly_total_qty, coverage_total_qty),
        "summary_report_amount_match": _close(summary_total_amount, report_total_amount),
        "summary_report_qty_match": _close(summary_total_qty, report_total_qty),
        "brand_count": int(len(reports)),
        "brand_amount_mismatch_count": int(brand_reconciliation["amount_diff"].abs().gt(0.01).sum()),
        "brand_qty_mismatch_count": int(brand_reconciliation["qty_diff"].abs().gt(0.01).sum()),
        "brand_monthly_mismatch_count": int(brand_reconciliation["monthly_diff"].abs().gt(0.01).sum()),
        "brand_count_mismatch_count": int((~brand_reconciliation["counts_match"]).sum()),
        "positive_qty_zero_amount_brands": int(
            (
                brand_reconciliation["source_qty"].gt(0)
                & brand_reconciliation["source_amount"].le(0)
            ).sum()
        ),
        "top5_share_over_100_brands": int(brand_reconciliation["top5_share_pct"].gt(100.000001).sum()),
    }
    source_quality = season.get("sourceDataQuality") if isinstance(season, dict) else None
    if isinstance(source_quality, dict):
        report_checks.update(
            {
                "quality_duplicate_group_match": int(
                    source_quality.get("duplicateCandidateGroups") or 0
                )
                == int(anomaly_profile["duplicate_groups"]),
                "quality_duplicate_amount_match": _close(
                    float(source_quality.get("duplicateCandidateAmountEur") or 0),
                    float(anomaly_profile["duplicate_excess_amount"]),
                ),
                "quality_recommendation_not_blocked": source_quality.get(
                    "recommendationBlocked"
                )
                is False,
            }
        )

    month_profile = coverage[
        [
            "month",
            "status",
            "rowCount",
            "activeDays",
            "expectedBusinessDays",
            "activityRatio",
            "firstDate",
            "lastDate",
            "totalAmount",
            "totalQty",
        ]
    ].copy()
    partial_amount = float(
        pd.to_numeric(
            coverage.loc[coverage["status"].ne("complete"), "totalAmount"],
            errors="coerce",
        ).fillna(0).sum()
    )
    temporal_profile = {
        "months": int(len(coverage)),
        "complete_months": int(coverage["status"].eq("complete").sum()),
        "partial_months": coverage.loc[coverage["status"].ne("complete"), "month"].tolist(),
        "partial_month_amount_share_pct": round(
            partial_amount / max(coverage_total_amount, 1) * 100,
            4,
        ),
        "analysis_saved_at": payload.get("saved_at"),
        "analysis_start_date": options.get("start_date"),
        "analysis_end_date": options.get("end_date"),
    }

    order_payload = json.loads(ORDER_SNAPSHOT.read_text(encoding="utf-8"))
    stock_profile, stock_by_brand = _stock_profile(order_payload["rows"])
    sales_brands = set(summary[BRAND_COL].dropna().astype(str).str.strip())
    stock_brands = set(stock_by_brand["브랜드"].dropna().astype(str).str.strip())
    overlap = sales_brands & stock_brands
    stock_profile["sales_brand_count"] = len(sales_brands)
    stock_profile["sales_brands_with_stock_match"] = len(overlap)
    stock_profile["sales_brand_stock_match_rate_pct"] = round(
        len(overlap) / max(len(sales_brands), 1) * 100,
        2,
    )
    stock_profile["sales_brands_without_stock_match"] = sorted(sales_brands - stock_brands)
    stock_profile["saved_at"] = order_payload.get("saved_at")
    stock_profile["job_id"] = order_payload.get("job_id")

    focus_brand = "편강율"
    focus_sales = brand_reconciliation.loc[
        brand_reconciliation[BRAND_COL].eq(focus_brand)
    ]
    focus_stock = stock_by_brand.loc[stock_by_brand["브랜드"].eq(focus_brand)]
    focus = {
        "brand": focus_brand,
        "sales": focus_sales.to_dict(orient="records"),
        "stock": focus_stock.to_dict(orient="records"),
    }

    findings: list[dict[str, Any]] = []
    if not all(value for value in report_checks.values() if isinstance(value, bool)):
        findings.append(
            {
                "severity": "Critical",
                "finding": "원천·집계·리포트 합계 불일치",
                "evidence": report_checks,
            }
        )
    if exact_duplicate_rows:
        findings.append(
            {
                "severity": "Medium",
                "finding": "CMS 판매 원천의 완전 중복 후보",
                "evidence": {
                    "affected_rows": exact_duplicate_rows,
                    "duplicate_groups": anomaly_profile["duplicate_groups"],
                    "maximum_amount_overstatement_pct": anomaly_profile[
                        "duplicate_excess_amount_share_pct"
                    ],
                },
            }
        )
    if anomaly_profile["final_zero_amount_rows"]:
        findings.append(
            {
                "severity": "Medium",
                "finding": "리포트 모집단의 판매수량 양수·매출 0 행",
                "evidence": {
                    "affected_rows": anomaly_profile["final_zero_amount_rows"],
                    "quantity": anomaly_profile["final_zero_amount_qty"],
                    "quantity_share_pct": anomaly_profile[
                        "final_zero_amount_qty_share_pct"
                    ],
                },
            }
        )
    if raw_profile["negative_qty_rows"] or raw_profile["negative_normalized_amount_rows"]:
        findings.append(
            {
                "severity": "Low",
                "finding": "음수 판매수량 또는 매출 행",
                "evidence": {
                    "affected_rows": anomaly_profile["final_negative_rows"],
                    "net_amount": anomaly_profile["final_negative_amount"],
                    "amount_share_pct": anomaly_profile[
                        "final_negative_amount_share_pct"
                    ],
                },
            }
        )
    if mapping_profile["unmatched_master_amount_share_pct"] > 0.1:
        findings.append(
            {
                "severity": "High",
                "finding": "상품 마스터 미매칭 매출 비중",
                "evidence": mapping_profile,
            }
        )
    elif mapping_profile["unmatched_master_rows"]:
        findings.append(
            {
                "severity": "Low",
                "finding": "상품 마스터 미매칭 행",
                "evidence": mapping_profile,
            }
        )
    if temporal_profile["partial_months"]:
        findings.append(
            {
                "severity": "Medium",
                "finding": "부분 월이 총매출에 포함됨",
                "evidence": temporal_profile,
            }
        )
    exchange_date = str(options.get("exchange_rate_date") or "")
    if (
        options.get("exchange_rate_source") != "api"
        or not exchange_date
        or "현재 적용 환율" not in str(options.get("exchange_rate_basis") or "")
    ):
        findings.append(
            {
                "severity": "High",
                "finding": "현재 적용 환율 조회 또는 기준 표기 확인 필요",
                "evidence": {
                    "exchange_rate": options.get("average_eur_krw_rate"),
                    "exchange_rate_date": exchange_date,
                    "exchange_rate_source": options.get("exchange_rate_source"),
                    "exchange_rate_checked_date": options.get("exchange_rate_checked_date"),
                    "exchange_rate_basis": options.get("exchange_rate_basis"),
                },
            }
        )
    if stock_profile["daily_sales_formula_mismatch_rows"]:
        findings.append(
            {
                "severity": "High",
                "finding": "MOI 판매속도 공식 불일치",
                "evidence": stock_profile,
            }
        )
    if stock_profile["sales_brand_stock_match_rate_pct"] < 100:
        findings.append(
            {
                "severity": "Medium",
                "finding": "판매 브랜드와 재고 브랜드 결합 누락",
                "evidence": {
                    "match_rate_pct": stock_profile["sales_brand_stock_match_rate_pct"],
                    "missing_brands": stock_profile["sales_brands_without_stock_match"],
                },
            }
        )

    return {
        "source_path": str(source_cache_path.relative_to(PROJECT_ROOT)),
        "season_snapshot": str(SEASON_SNAPSHOT.relative_to(PROJECT_ROOT)),
        "order_snapshot": str(ORDER_SNAPSHOT.relative_to(PROJECT_ROOT)),
        "analysis_options": options,
        "source_meta": raw.get("__source_meta", {}),
        "raw_profile": raw_profile,
        "anomaly_profile": anomaly_profile,
        "duplicate_diagnostics": duplicate_diagnostics,
        "completeness": completeness,
        "currency_ratio": currency_ratio,
        "row_flow": {
            "raw_rows": len(sales),
            "after_standardize_filter_merge": rows_after_standardize,
            "after_category_exclusions": len(category_filtered),
            "unknown_country_non_revenue_excluded": int(unknown_country_excluded),
            "final_rows": len(final_merged),
        },
        "mapping_profile": mapping_profile,
        "totals": totals,
        "report_checks": report_checks,
        "brand_reconciliation": brand_reconciliation,
        "month_profile": month_profile,
        "temporal_profile": temporal_profile,
        "stock_profile": stock_profile,
        "stock_by_brand": stock_by_brand,
        "focus": focus,
        "findings": findings,
    }


def _json_ready(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value) if not isinstance(value, (str, bytes)) else False:
        return None
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    if hasattr(value, "item"):
        return value.item()
    return str(value)


if __name__ == "__main__":
    audit = run_audit()
    summary = {
        "source_path": audit["source_path"],
        "raw_profile": audit["raw_profile"],
        "anomaly_profile": audit["anomaly_profile"],
        "duplicate_diagnostics": audit["duplicate_diagnostics"],
        "row_flow": audit["row_flow"],
        "mapping_profile": audit["mapping_profile"],
        "report_checks": audit["report_checks"],
        "temporal_profile": audit["temporal_profile"],
        "stock_profile": audit["stock_profile"],
        "focus": audit["focus"],
        "findings": audit["findings"],
    }
    print(json.dumps(_json_ready(summary), ensure_ascii=False, indent=2))
