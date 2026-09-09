"""Reconcile CMS source rows to the persisted cross-analysis cubes.

This audit intentionally emits only aggregate quality evidence. It does not
write raw CMS records, invoice numbers, customer data, or credentials.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd

from backend.services.category_corrections import (
    apply_category_corrections_to_merged,
    merge_default_category_corrections,
)
from backend.services.season_analysis_common import (
    exclude_non_revenue_unknown_country_rows,
    parse_season_analysis_options,
)
from core.season_calendar import (
    AMOUNT_COL,
    BRAND_COL,
    CATEGORY1_COL,
    CATEGORY2_COL,
    COUNTRY_COL,
    DATE_COL,
    PRODUCT_CODE_COL,
    PRODUCT_MASTER_CATEGORY1_COL,
    PRODUCT_MASTER_CATEGORY2_COL,
    PRODUCT_NAME_COL,
    QTY_COL,
    exclude_season_category1_values,
    merge_sales_with_product_master,
    split_cosmetic_product_scope,
)


SUMMARY_KEYS = [
    COUNTRY_COL,
    CATEGORY1_COL,
    CATEGORY2_COL,
    PRODUCT_CODE_COL,
    BRAND_COL,
    PRODUCT_NAME_COL,
]
MONTHLY_KEYS = [
    COUNTRY_COL,
    "year",
    "month",
    "year_month",
    CATEGORY1_COL,
    CATEGORY2_COL,
    PRODUCT_CODE_COL,
    BRAND_COL,
    PRODUCT_NAME_COL,
]


@dataclass
class Reconciliation:
    key_mismatches: int
    amount_mismatches: int
    quantity_mismatches: int
    max_amount_delta: float
    max_quantity_delta: float


def _normalized_country(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.assign(
        **{
            COUNTRY_COL: frame[COUNTRY_COL]
            .astype(str)
            .str.strip()
            .replace({"": "미상", "nan": "미상", "None": "미상"})
        }
    )


def _reconcile(expected: pd.DataFrame, actual: pd.DataFrame, keys: list[str]) -> Reconciliation:
    joined = expected.merge(actual, on=keys, how="outer", suffixes=("_expected", "_actual"), indicator=True)
    amount_delta = (
        joined[f"{AMOUNT_COL}_expected"].fillna(0)
        - joined[f"{AMOUNT_COL}_actual"].fillna(0)
    )
    quantity_delta = (
        joined[f"{QTY_COL}_expected"].fillna(0)
        - joined[f"{QTY_COL}_actual"].fillna(0)
    )
    return Reconciliation(
        key_mismatches=int(joined["_merge"].ne("both").sum()),
        amount_mismatches=int(amount_delta.abs().gt(1e-7).sum()),
        quantity_mismatches=int(quantity_delta.abs().gt(1e-7).sum()),
        max_amount_delta=float(amount_delta.abs().max() if not joined.empty else 0),
        max_quantity_delta=float(quantity_delta.abs().max() if not joined.empty else 0),
    )


def _build_filtered_sales(
    raw_sales: pd.DataFrame,
    product_master: pd.DataFrame,
    analysis_options: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, int]]:
    options = parse_season_analysis_options(analysis_options)
    merged_initial = merge_sales_with_product_master(
        raw_sales,
        product_master,
        start_date=options.effective_start_date,
        end_date=options.effective_end_date,
        eu_local=options.eu_local,
        entity_code=options.entity_code,
    )
    if PRODUCT_MASTER_CATEGORY1_COL in merged_initial.columns:
        merged_initial[CATEGORY1_COL] = merged_initial[PRODUCT_MASTER_CATEGORY1_COL]
    if PRODUCT_MASTER_CATEGORY2_COL in merged_initial.columns:
        merged_initial[CATEGORY2_COL] = merged_initial[PRODUCT_MASTER_CATEGORY2_COL]
    corrected = apply_category_corrections_to_merged(
        merged_initial,
        merge_default_category_corrections(pd.DataFrame()),
        PRODUCT_CODE_COL,
        CATEGORY1_COL,
        CATEGORY2_COL,
    )
    cosmetic, diagnostics = split_cosmetic_product_scope(corrected)
    category_filtered = exclude_season_category1_values(cosmetic)
    final, unknown_country_excluded = exclude_non_revenue_unknown_country_rows(
        category_filtered,
        COUNTRY_COL,
        AMOUNT_COL,
    )
    return final, {
        "rawRows": int(len(raw_sales)),
        "postStandardizeMergeRows": int(len(merged_initial)),
        "cosmeticRows": int(len(cosmetic)),
        "diagnosticRows": int(len(diagnostics)),
        "finalRows": int(len(final)),
        "unknownCountryRowsExcluded": int(unknown_country_excluded),
    }


def _completed_ytd_month(payload: dict[str, Any]) -> int:
    coverage = payload["season_analysis"].get("monthCoverage", [])
    complete = {
        str(row.get("month"))
        for row in coverage
        if row.get("status") == "complete"
    }
    observed_years = sorted(
        {int(str(row.get("month"))[:4]) for row in coverage if str(row.get("month", ""))[:4].isdigit()},
        reverse=True,
    )
    if len(observed_years) < 2:
        return 0
    latest = observed_years[0]
    previous = latest - 1
    if previous not in observed_years:
        return 0
    completed = 0
    for month in range(1, 13):
        suffix = f"{month:02d}"
        if f"{latest}-{suffix}" not in complete or f"{previous}-{suffix}" not in complete:
            break
        completed = month
    return completed


def validate_snapshot(snapshot_path: Path, raw_cache_path: Path) -> dict[str, Any]:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    cache_payload = json.loads(raw_cache_path.read_text(encoding="utf-8"))
    raw = cache_payload["raw"]
    raw_sales = pd.DataFrame(raw.get("sales_history", []))
    product_master = pd.DataFrame(raw.get("prod_list", []))
    season = payload["season_analysis"]

    filtered, stages = _build_filtered_sales(raw_sales, product_master, payload["analysis_options"])
    normalized = _normalized_country(filtered)
    expected_summary = (
        normalized.groupby(SUMMARY_KEYS, dropna=False)[[QTY_COL, AMOUNT_COL]]
        .sum()
        .reset_index()
    )
    monthly_source = normalized.assign(
        year=normalized[DATE_COL].dt.year.astype("Int64"),
        month=normalized[DATE_COL].dt.month.astype("Int64"),
        year_month=normalized[DATE_COL].dt.to_period("M").astype(str),
    )
    expected_monthly = (
        monthly_source.groupby(MONTHLY_KEYS, dropna=False)[[QTY_COL, AMOUNT_COL]]
        .sum()
        .reset_index()
    )
    actual_summary = pd.DataFrame(season.get("countrySkuSummary", []))
    actual_monthly = pd.DataFrame(season.get("countrySkuMonthly", []))

    summary_reconciliation = _reconcile(expected_summary, actual_summary, SUMMARY_KEYS)
    monthly_reconciliation = _reconcile(expected_monthly, actual_monthly, MONTHLY_KEYS)
    coverage = pd.DataFrame(season.get("monthCoverage", []))

    required_columns = [
        DATE_COL,
        COUNTRY_COL,
        PRODUCT_CODE_COL,
        BRAND_COL,
        PRODUCT_NAME_COL,
        QTY_COL,
        AMOUNT_COL,
    ]
    nulls = {column: int(filtered[column].isna().sum()) for column in required_columns}
    blanks = {
        column: int(filtered[column].astype(str).str.strip().isin(["", "nan", "None"]).sum())
        for column in required_columns
    }
    sku_identity = filtered.groupby(PRODUCT_CODE_COL, dropna=False).agg(
        brands=(BRAND_COL, lambda values: values.astype(str).str.strip().nunique()),
        names=(PRODUCT_NAME_COL, lambda values: values.astype(str).str.strip().nunique()),
    )
    raw_exact_duplicate_mask = raw_sales.duplicated(keep=False)
    product_code_counts = (
        product_master[PRODUCT_CODE_COL].astype(str).str.strip().value_counts()
        if PRODUCT_CODE_COL in product_master.columns
        else pd.Series(dtype=int)
    )
    source_quality = season.get("sourceDataQuality", {})

    raw_amount_total = float(filtered[AMOUNT_COL].sum())
    raw_quantity_total = float(filtered[QTY_COL].sum())
    summary_amount_total = float(actual_summary[AMOUNT_COL].sum())
    summary_quantity_total = float(actual_summary[QTY_COL].sum())
    monthly_amount_total = float(actual_monthly[AMOUNT_COL].sum())
    monthly_quantity_total = float(actual_monthly[QTY_COL].sum())
    coverage_amount_total = float(pd.to_numeric(coverage.get("totalAmount"), errors="coerce").fillna(0).sum())
    coverage_quantity_total = float(pd.to_numeric(coverage.get("totalQty"), errors="coerce").fillna(0).sum())

    checks = {
        "crossAnalysisComplete": season.get("crossAnalysisComplete") is True,
        "summaryKeysMatch": summary_reconciliation.key_mismatches == 0,
        "summaryAmountsMatch": summary_reconciliation.amount_mismatches == 0,
        "summaryQuantitiesMatch": summary_reconciliation.quantity_mismatches == 0,
        "monthlyKeysMatch": monthly_reconciliation.key_mismatches == 0,
        "monthlyAmountsMatch": monthly_reconciliation.amount_mismatches == 0,
        "monthlyQuantitiesMatch": monthly_reconciliation.quantity_mismatches == 0,
        "rawSummaryAmountTotalMatch": abs(raw_amount_total - summary_amount_total) <= 1e-6,
        "rawSummaryQuantityTotalMatch": abs(raw_quantity_total - summary_quantity_total) <= 1e-6,
        "summaryMonthlyAmountTotalMatch": abs(summary_amount_total - monthly_amount_total) <= 1e-6,
        "summaryMonthlyQuantityTotalMatch": abs(summary_quantity_total - monthly_quantity_total) <= 1e-6,
        "coverageMonthlyAmountTotalMatch": abs(coverage_amount_total - monthly_amount_total) <= 1e-6,
        "coverageMonthlyQuantityTotalMatch": abs(coverage_quantity_total - monthly_quantity_total) <= 1e-6,
        "requiredFieldsComplete": sum(nulls.values()) == 0 and sum(blanks.values()) == 0,
        "skuBrandStable": int(sku_identity["brands"].gt(1).sum()) == 0,
        "skuNameStable": int(sku_identity["names"].gt(1).sum()) == 0,
    }

    return {
        "snapshot": str(snapshot_path.resolve()),
        "rawCache": str(raw_cache_path.resolve()),
        "savedAt": payload.get("saved_at"),
        "analysisRange": [
            payload["analysis_options"].get("start_date"),
            payload["analysis_options"].get("end_date"),
        ],
        "entityCode": payload["analysis_options"].get("entity_code"),
        "sourceRows": {
            "sales": int(len(raw_sales)),
            "productMaster": int(len(product_master)),
        },
        "pipelineStages": stages,
        "cubeRows": {
            "countrySkuSummary": int(len(actual_summary)),
            "countrySkuMonthly": int(len(actual_monthly)),
            "monthCoverage": int(len(coverage)),
        },
        "totals": {
            "rawFilteredAmount": raw_amount_total,
            "summaryAmount": summary_amount_total,
            "monthlyAmount": monthly_amount_total,
            "coverageAmount": coverage_amount_total,
            "rawFilteredQuantity": raw_quantity_total,
            "summaryQuantity": summary_quantity_total,
            "monthlyQuantity": monthly_quantity_total,
            "coverageQuantity": coverage_quantity_total,
        },
        "summaryReconciliation": asdict(summary_reconciliation),
        "monthlyReconciliation": asdict(monthly_reconciliation),
        "requiredFieldNulls": nulls,
        "requiredFieldBlanks": blanks,
        "dimensionIntegrity": {
            "skuCount": int(sku_identity.shape[0]),
            "skuCodesWithMultipleBrands": int(sku_identity["brands"].gt(1).sum()),
            "skuCodesWithMultipleNames": int(sku_identity["names"].gt(1).sum()),
            "productMasterDuplicateCodeRows": int(product_code_counts[product_code_counts.gt(1)].sum()),
            "productMasterDuplicateCodes": int(product_code_counts.gt(1).sum()),
        },
        "sourceDuplicateRisk": {
            "stableIdColumn": source_quality.get("stableIdColumn"),
            "exactDuplicateRowsObserved": int(raw_exact_duplicate_mask.sum()),
            "exactDuplicateGroupsObserved": int(raw_sales.loc[raw_exact_duplicate_mask].drop_duplicates().shape[0]),
            "candidateGroupsInAnalysisPopulation": int(source_quality.get("duplicateCandidateGroups") or 0),
            "candidateRowsInAnalysisPopulation": int(source_quality.get("duplicateCandidateRows") or 0),
            "candidateExcessRows": int(source_quality.get("duplicateCandidateExcessRows") or 0),
            "candidateAmount": float(source_quality.get("duplicateCandidateAmountEur") or 0),
            "candidateAmountSharePct": float(source_quality.get("duplicateCandidateAmountSharePct") or 0),
        },
        "measureEdgeCounts": {
            "summaryNegativeAmountCells": int(actual_summary[AMOUNT_COL].lt(0).sum()),
            "summaryZeroAmountCells": int(actual_summary[AMOUNT_COL].eq(0).sum()),
            "summaryNegativeQuantityCells": int(actual_summary[QTY_COL].lt(0).sum()),
            "summaryZeroQuantityCells": int(actual_summary[QTY_COL].eq(0).sum()),
            "monthlyNegativeAmountCells": int(actual_monthly[AMOUNT_COL].lt(0).sum()),
            "monthlyZeroAmountCells": int(actual_monthly[AMOUNT_COL].eq(0).sum()),
            "monthlyNegativeQuantityCells": int(actual_monthly[QTY_COL].lt(0).sum()),
            "monthlyZeroQuantityCells": int(actual_monthly[QTY_COL].eq(0).sum()),
        },
        "completedYtdBaseMonth": _completed_ytd_month(payload),
        "checks": checks,
        "allDeterministicChecksPassed": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", action="append", nargs=2, metavar=("SNAPSHOT", "RAW_CACHE"), required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    results = [
        validate_snapshot(Path(snapshot), Path(raw_cache))
        for snapshot, raw_cache in args.snapshot
    ]
    report = {
        "status": "passed" if all(item["allDeterministicChecksPassed"] for item in results) else "failed",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "snapshots": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
