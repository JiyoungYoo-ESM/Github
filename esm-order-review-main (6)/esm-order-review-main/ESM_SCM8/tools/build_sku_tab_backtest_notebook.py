from __future__ import annotations

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "sku_tab_backtest_20260715"
NOTEBOOK_PATH = OUTPUT_DIR / "sku_tab_backtest_20260715.ipynb"


def code(source: str):
    return nbf.v4.new_code_cell(source.strip())


def markdown(source: str):
    return nbf.v4.new_markdown_cell(source.strip())


notebook = nbf.v4.new_notebook()
notebook["metadata"]["kernelspec"] = {
    "display_name": "Python 3 (ESM SCM)",
    "language": "python",
    "name": "python3",
}
notebook["metadata"]["language_info"] = {"name": "python", "version": "3.11"}

notebook["cells"] = [
    markdown(
        """
# SKU 탭 전체 데이터 정합성 백테스트

## tl;dr

이 노트북은 최신 메인 `SKU` 탭이 사용하는 `countrySkuSummary`와 `countrySkuMonthly`를 원천 CMS 캐시에서 재구성해 전수 대조한다. 핵심 판정과 수치는 마지막 셀의 실행 결과로 갱신된다.
"""
    ),
    markdown(
        """
## Context & Methods

- 대상 화면: `SiliconAnalyticsWorkspace.tsx`의 `SkuScreenExact`
- 화면 데이터: `/api/season-trend/latest` 응답의 국가×SKU 요약 및 국가×SKU×월 집계
- 백테스트 기준: 원천 CMS 판매 1행을 출발점으로 운영 필터·상품 마스터 결합·카테고리 제외를 적용한 뒤 독립 `groupby`로 재집계
- 합격 기준: 키 집합 동일, 합계 오차 `max(0.01, |기준값|×1e-9)` 이내, 요약·월별·월 커버리지 합계 일치

### Key Assumptions

- `판매금액`은 응답 메타데이터 정의에 따라 EUR이다.
- 2024-04은 `exclude_partial_months=false`로 포함된 부분월이며, 합계 일치와 별개로 시즌성 해석에는 주의가 필요하다.
"""
    ),
    markdown("## Data\n\n### 1. 최신 분석 스냅샷과 원천 캐시를 로드한다"),
    code(
        r'''
from pathlib import Path
import json
import math
import unicodedata

import numpy as np
import pandas as pd

ROOT = Path.cwd()
if not (ROOT / "backend").exists():
    ROOT = ROOT.parent
OUTPUT_DIR = ROOT / "artifacts" / "sku_tab_backtest_20260715"
LATEST_PATH = ROOT / "backend" / "storage" / "latest_season_trend" / "latest.json"

latest = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
latest_saved_at = latest["saved_at"]
options = latest["analysis_options"]
from backend.services.cms_fetch_cache import _cache_key, _cache_path
cache_key = _cache_key(
    as_of=str(options["end_date"]),
    date_from=str(options["start_date"]),
    date_to=str(options["end_date"]),
    logistics_date_from="season_trend_source_api_v2:eu_sold_only=true",
)
CACHE_PATH = _cache_path(cache_key)
cache_payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
raw = cache_payload["raw"]
sales_raw = pd.DataFrame(raw["sales_history"])
products_raw = pd.DataFrame(raw["prod_list"])
season = latest["season_analysis"]
source_meta = latest["source_meta"]

summary_actual = pd.DataFrame(season["countrySkuSummary"])
monthly_actual = pd.DataFrame(season["countrySkuMonthly"])
coverage_actual = pd.DataFrame(season["monthCoverage"])

profile = pd.DataFrame([
    {"dataset": "CMS 판매 원천", "rows": len(sales_raw), "columns": len(sales_raw.columns)},
    {"dataset": "CMS 상품 마스터", "rows": len(products_raw), "columns": len(products_raw.columns)},
    {"dataset": "SKU 탭 국가×SKU 요약", "rows": len(summary_actual), "columns": len(summary_actual.columns)},
    {"dataset": "SKU 탭 국가×SKU×월", "rows": len(monthly_actual), "columns": len(monthly_actual.columns)},
])
print("분석 기간:", options["start_date"], "~", options["end_date"])
print("저장 시각:", latest["saved_at"])
print("원천 캐시:", CACHE_PATH.name)
display(profile)
'''
    ),
    markdown("### 2. 운영 화면과 같은 분석 모집단을 원천에서 재구성한다"),
    code(
        r'''
from backend.services.category_corrections import apply_category_corrections_to_merged, merge_default_category_corrections
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
)

start_date = pd.Timestamp(options["start_date"])
end_date = pd.Timestamp(options["end_date"]) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)

merged_before_exclusions = merge_sales_with_product_master(
    sales_raw,
    products_raw,
    start_date=start_date,
    end_date=end_date,
    eu_local=bool(options.get("eu_local", True)),
)
corrections = merge_default_category_corrections(pd.DataFrame())
merged_corrected = apply_category_corrections_to_merged(
    merged_before_exclusions,
    corrections,
    PRODUCT_CODE_COL,
    CATEGORY1_COL,
    CATEGORY2_COL,
)
merged = exclude_season_category1_values(merged_corrected)

country_norm = merged[COUNTRY_COL].fillna("").astype(str).str.normalize("NFKC").str.strip().str.casefold()
missing_country = country_norm.isin({"", "-", "미상", "unknown", "nan", "none", "n/a", "<na>"})
amount_numeric = pd.to_numeric(merged[AMOUNT_COL], errors="coerce").fillna(0)
non_revenue_unknown_country = missing_country & amount_numeric.le(0)
merged = merged.loc[~non_revenue_unknown_country].copy()

population_steps = pd.DataFrame([
    {"stage": "raw CMS rows", "rows": len(sales_raw)},
    {"stage": "date/biz/delivery filters + product join", "rows": len(merged_before_exclusions)},
    {"stage": "category exclusions", "rows": len(exclude_season_category1_values(merged_corrected))},
    {"stage": "final SKU-tab analytical population", "rows": len(merged)},
])
display(population_steps)
'''
    ),
    markdown("## Results\n\n### 3. 원천 재집계와 API 집계를 키·값 단위로 전수 대조한다"),
    code(
        r'''
COUNTRY_KEYS = [COUNTRY_COL, CATEGORY1_COL, CATEGORY2_COL, PRODUCT_CODE_COL, BRAND_COL, PRODUCT_NAME_COL]
MONTHLY_KEYS = [COUNTRY_COL, "year", "month", "year_month", CATEGORY1_COL, CATEGORY2_COL, PRODUCT_CODE_COL, BRAND_COL, PRODUCT_NAME_COL]
MEASURES = [QTY_COL, AMOUNT_COL]

independent = merged.copy()
independent[COUNTRY_COL] = independent[COUNTRY_COL].astype(str).str.strip().replace({"": "미상", "nan": "미상", "None": "미상"})

summary_expected = (
    independent.groupby(COUNTRY_KEYS, dropna=False)
    .agg(**{QTY_COL: (QTY_COL, "sum"), AMOUNT_COL: (AMOUNT_COL, "sum")})
    .reset_index()
)
monthly_source = independent.copy()
monthly_source["year"] = monthly_source[DATE_COL].dt.year.astype("Int64")
monthly_source["month"] = monthly_source[DATE_COL].dt.month.astype("Int64")
monthly_source["year_month"] = monthly_source[DATE_COL].dt.to_period("M").astype(str)
monthly_expected = (
    monthly_source.groupby(MONTHLY_KEYS, dropna=False)
    .agg(**{QTY_COL: (QTY_COL, "sum"), AMOUNT_COL: (AMOUNT_COL, "sum")})
    .reset_index()
)

def compare_frames(expected, actual, keys, label):
    left = expected.copy()
    right = actual.copy()
    for key in keys:
        left[key] = left[key].astype(str)
        right[key] = right[key].astype(str)
    joined = left.merge(right, on=keys, how="outer", suffixes=("_expected", "_actual"), indicator=True)
    result = {"check": label, "expected_rows": len(left), "actual_rows": len(right), "missing_or_extra_keys": int((joined["_merge"] != "both").sum())}
    for measure in MEASURES:
        exp = pd.to_numeric(joined[f"{measure}_expected"], errors="coerce").fillna(0)
        act = pd.to_numeric(joined[f"{measure}_actual"], errors="coerce").fillna(0)
        diff = (act - exp).abs()
        tol = np.maximum(0.01, exp.abs() * 1e-9)
        result[f"{measure}_mismatch_rows"] = int((diff > tol).sum())
        result[f"{measure}_max_abs_diff"] = float(diff.max()) if len(diff) else 0.0
    return result, joined

summary_check, summary_joined = compare_frames(summary_expected, summary_actual, COUNTRY_KEYS, "원천→국가×SKU 요약")
monthly_check, monthly_joined = compare_frames(monthly_expected, monthly_actual, MONTHLY_KEYS, "원천→국가×SKU×월")

monthly_rollup = monthly_actual.groupby(COUNTRY_KEYS, dropna=False)[MEASURES].sum().reset_index()
rollup_check, rollup_joined = compare_frames(summary_actual, monthly_rollup, COUNTRY_KEYS, "월별→요약 롤업")

reconciliation = pd.DataFrame([summary_check, monthly_check, rollup_check])
display(reconciliation)
'''
    ),
    markdown("### 4. 월 커버리지, 화면 합계, 월별 비중을 교차 검산한다"),
    code(
        r'''
coverage_monthly = monthly_actual.groupby("year_month", dropna=False)[MEASURES].sum().reset_index()
coverage_compare = coverage_actual[["month", "status", "rowCount", "totalAmount", "totalQty"]].merge(
    coverage_monthly,
    left_on="month",
    right_on="year_month",
    how="outer",
)
coverage_compare["amount_diff"] = coverage_compare["totalAmount"] - coverage_compare[AMOUNT_COL]
coverage_compare["qty_diff"] = coverage_compare["totalQty"] - coverage_compare[QTY_COL]

frontend_summary = (
    summary_actual.groupby(PRODUCT_CODE_COL, dropna=False)
    .agg(
        amount=(AMOUNT_COL, "sum"),
        qty=(QTY_COL, "sum"),
        countries=(COUNTRY_COL, lambda values: len({str(v).strip() for v in values if str(v).strip() not in {"", "미상"}})),
        brands=(BRAND_COL, "nunique"),
        names=(PRODUCT_NAME_COL, "nunique"),
        category1=(CATEGORY1_COL, "nunique"),
        category2=(CATEGORY2_COL, "nunique"),
    )
    .reset_index()
    .sort_values(["amount", "qty"], ascending=False)
)
monthly_frontend = monthly_actual.groupby(PRODUCT_CODE_COL, dropna=False)[MEASURES].sum().reset_index()
frontend_rollup = frontend_summary.merge(monthly_frontend, on=PRODUCT_CODE_COL, how="outer")
frontend_rollup["amount_diff"] = frontend_rollup["amount"] - frontend_rollup[AMOUNT_COL]
frontend_rollup["qty_diff"] = frontend_rollup["qty"] - frontend_rollup[QTY_COL]

month_share = monthly_actual.groupby([PRODUCT_CODE_COL, "month"], dropna=False)[MEASURES].sum().reset_index()
sku_amount_total = month_share.groupby(PRODUCT_CODE_COL)[AMOUNT_COL].transform("sum")
sku_qty_total = month_share.groupby(PRODUCT_CODE_COL)[QTY_COL].transform("sum")
month_share["metric"] = np.where(sku_amount_total > 0, month_share[AMOUNT_COL], month_share[QTY_COL])
month_share["metric_total"] = np.where(sku_amount_total > 0, sku_amount_total, sku_qty_total)
month_share["share_pct"] = np.where(month_share["metric_total"] != 0, month_share["metric"] / month_share["metric_total"] * 100, 0)
share_sums = month_share.groupby(PRODUCT_CODE_COL)["share_pct"].sum()

print("화면 SKU 수:", len(frontend_summary))
print("요약↔월별 SKU 합계 불일치:", int(((frontend_rollup["amount_diff"].abs() > 0.01) | (frontend_rollup["qty_diff"].abs() > 0.01)).sum()))
print("월별 비중 합계가 100%에서 벗어난 SKU:", int(((share_sums - 100).abs() > 1e-7).sum()))
display(coverage_compare)
display(frontend_summary.head(10))
'''
    ),
    markdown("### 5. 키 유일성, 누락, 중복·표기 충돌, 음수값을 점검한다"),
    code(
        r'''
def norm_sku(value):
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return "".join(text.split()).casefold()

summary_duplicate_keys = int(summary_actual.duplicated(COUNTRY_KEYS, keep=False).sum())
monthly_duplicate_keys = int(monthly_actual.duplicated(MONTHLY_KEYS, keep=False).sum())
product_key_duplicates = int(products_raw.assign(_sku=products_raw["prod_cd"].map(norm_sku)).duplicated("_sku", keep=False).sum())

sku_spellings = pd.DataFrame({"sku": pd.concat([sales_raw["prod_cd"], products_raw["prod_cd"]], ignore_index=True).astype(str)})
sku_spellings["normalized"] = sku_spellings["sku"].map(norm_sku)
near_duplicate_groups = (
    sku_spellings.drop_duplicates()
    .groupby("normalized")["sku"]
    .agg(lambda values: sorted(set(values)))
)
near_duplicate_groups = near_duplicate_groups[near_duplicate_groups.map(len) > 1]

identity_anomalies = frontend_summary[
    (frontend_summary["brands"] > 1)
    | (frontend_summary["names"] > 1)
    | (frontend_summary["category1"] > 1)
    | (frontend_summary["category2"] > 1)
].copy()

missing_checks = pd.DataFrame([
    {"field": PRODUCT_CODE_COL, "rows": int(summary_actual[PRODUCT_CODE_COL].fillna("").astype(str).str.strip().isin({"", "-", "nan", "None"}).sum())},
    {"field": PRODUCT_NAME_COL, "rows": int(summary_actual[PRODUCT_NAME_COL].fillna("").astype(str).str.strip().isin({"", "-", "nan", "None"}).sum())},
    {"field": BRAND_COL, "rows": int(summary_actual[BRAND_COL].fillna("").astype(str).str.strip().isin({"", "-", "nan", "None"}).sum())},
    {"field": CATEGORY1_COL, "rows": int(summary_actual[CATEGORY1_COL].fillna("").astype(str).str.strip().eq(UNMAPPED).sum())},
    {"field": CATEGORY2_COL, "rows": int(summary_actual[CATEGORY2_COL].fillna("").astype(str).str.strip().eq(UNMAPPED).sum())},
])

negative_raw = pd.DataFrame([
    {"measure": QTY_COL, "negative_rows": int((merged[QTY_COL] < 0).sum()), "negative_total": float(merged.loc[merged[QTY_COL] < 0, QTY_COL].sum())},
    {"measure": AMOUNT_COL, "negative_rows": int((merged[AMOUNT_COL] < 0).sum()), "negative_total": float(merged.loc[merged[AMOUNT_COL] < 0, AMOUNT_COL].sum())},
])
negative_sku = frontend_summary[(frontend_summary["amount"] < 0) | (frontend_summary["qty"] < 0)].copy()

quality_checks = pd.DataFrame([
    {"check": "요약 복합키 중복 행", "count": summary_duplicate_keys},
    {"check": "월별 복합키 중복 행", "count": monthly_duplicate_keys},
    {"check": "상품 마스터 정규화 SKU 중복 행", "count": product_key_duplicates},
    {"check": "대소문자/공백/.0 근접중복 SKU 그룹", "count": len(near_duplicate_groups)},
    {"check": "SKU별 브랜드/상품명/카테고리 충돌", "count": len(identity_anomalies)},
    {"check": "음수 합계 SKU", "count": len(negative_sku)},
])
display(quality_checks)
display(missing_checks)
display(negative_raw)
display(identity_anomalies.head(20))
'''
    ),
    markdown("### 6. 부분월·음수 매출·미상 국가가 화면 해석에 미치는 영향을 측정한다"),
    code(
        r'''
total_amount = float(summary_actual[AMOUNT_COL].sum())
total_qty = float(summary_actual[QTY_COL].sum())

unknown_country_mask = summary_actual[COUNTRY_COL].fillna("").astype(str).str.strip().isin({"", "미상", "nan", "None"})
unknown_country_rows = summary_actual.loc[unknown_country_mask].copy()
unknown_country_skus = int(unknown_country_rows[PRODUCT_CODE_COL].nunique())
unknown_country_amount = float(unknown_country_rows[AMOUNT_COL].sum())
unknown_country_qty = float(unknown_country_rows[QTY_COL].sum())

uncategorized_mask = summary_actual[CATEGORY2_COL].fillna("").astype(str).str.strip().eq(UNMAPPED)
uncategorized_rows = summary_actual.loc[uncategorized_mask].copy()
uncategorized_skus = int(uncategorized_rows[PRODUCT_CODE_COL].nunique())
uncategorized_amount = float(uncategorized_rows[AMOUNT_COL].sum())
uncategorized_qty = float(uncategorized_rows[QTY_COL].sum())

negative_month_rows = monthly_actual[pd.to_numeric(monthly_actual[AMOUNT_COL], errors="coerce").fillna(0) < 0].copy()
negative_month_skus = int(negative_month_rows[PRODUCT_CODE_COL].nunique())

complete_month_keys = set(coverage_actual.loc[coverage_actual["status"].eq("complete"), "month"].astype(str))
seasonal_all = monthly_actual.groupby([PRODUCT_CODE_COL, "month"], dropna=False)[AMOUNT_COL].sum().reset_index()
seasonal_complete = (
    monthly_actual[monthly_actual["year_month"].astype(str).isin(complete_month_keys)]
    .groupby([PRODUCT_CODE_COL, "month"], dropna=False)[AMOUNT_COL].sum()
    .reset_index()
)
peak_all = seasonal_all.sort_values([PRODUCT_CODE_COL, AMOUNT_COL], ascending=[True, False]).drop_duplicates(PRODUCT_CODE_COL)[[PRODUCT_CODE_COL, "month"]]
peak_complete = seasonal_complete.sort_values([PRODUCT_CODE_COL, AMOUNT_COL], ascending=[True, False]).drop_duplicates(PRODUCT_CODE_COL)[[PRODUCT_CODE_COL, "month"]]
peak_sensitivity = peak_all.merge(peak_complete, on=PRODUCT_CODE_COL, how="inner", suffixes=("_with_partial", "_complete_only"))
peak_changed = peak_sensitivity["month_with_partial"].ne(peak_sensitivity["month_complete_only"])

month_period_counts = (
    monthly_actual[["year_month", "month"]]
    .drop_duplicates()
    .groupby("month")
    .size()
    .rename("period_count")
    .reset_index()
)

impact_summary = pd.DataFrame([
    {"risk": "미상 국가", "rows": len(unknown_country_rows), "skus": unknown_country_skus, "amount_eur": unknown_country_amount, "amount_share_pct": unknown_country_amount / total_amount * 100 if total_amount else 0, "qty": unknown_country_qty},
    {"risk": "기능구분2 미분류", "rows": len(uncategorized_rows), "skus": uncategorized_skus, "amount_eur": uncategorized_amount, "amount_share_pct": uncategorized_amount / total_amount * 100 if total_amount else 0, "qty": uncategorized_qty},
    {"risk": "음수 월 집계", "rows": len(negative_month_rows), "skus": negative_month_skus, "amount_eur": float(negative_month_rows[AMOUNT_COL].sum()), "amount_share_pct": float(negative_month_rows[AMOUNT_COL].sum()) / total_amount * 100 if total_amount else 0, "qty": float(negative_month_rows[QTY_COL].sum())},
    {"risk": "부분월 제외 시 피크월 변경", "rows": int(peak_changed.sum()), "skus": int(peak_changed.sum()), "amount_eur": np.nan, "amount_share_pct": int(peak_changed.sum()) / len(peak_sensitivity) * 100 if len(peak_sensitivity) else 0, "qty": np.nan},
])
display(impact_summary)
display(month_period_counts)
display(peak_sensitivity.loc[peak_changed].head(20))
'''
    ),
    markdown("### 7. 해석 리스크와 최종 판정을 산출한다"),
    code(
        r'''
recon_failures = int(
    reconciliation["missing_or_extra_keys"].sum()
    + reconciliation["판매수량_mismatch_rows"].sum()
    + reconciliation["판매금액_mismatch_rows"].sum()
)
coverage_failures = int(((coverage_compare["amount_diff"].abs() > 0.01) | (coverage_compare["qty_diff"].abs() > 0.01)).sum())
partial_months = coverage_actual.loc[coverage_actual["status"] != "complete", "month"].astype(str).tolist()

issues = []
if recon_failures or coverage_failures:
    issues.append({"severity": "Critical", "issue": "원천·요약·월별 집계 불일치", "count": recon_failures + coverage_failures})
if len(identity_anomalies):
    issues.append({"severity": "High", "issue": "동일 SKU의 표시 속성 충돌", "count": len(identity_anomalies)})
if partial_months:
    issues.append({"severity": "Medium", "issue": "부분월이 시즌 비중에 포함됨", "count": len(partial_months), "affected_peak_skus": int(peak_changed.sum())})
if int(negative_raw["negative_rows"].sum()):
    issues.append({"severity": "Medium", "issue": "반품/취소 추정 음수 판매행 포함", "count": int(negative_raw["negative_rows"].sum()), "affected_skus": negative_month_skus})
if missing_checks["rows"].sum():
    issues.append({"severity": "Medium", "issue": "기능구분2 미분류", "count": int(missing_checks["rows"].sum()), "affected_skus": uncategorized_skus})
if unknown_country_skus:
    issues.append({"severity": "Medium", "issue": "국가 미상 판매가 국가 분포에서 제외됨", "count": len(unknown_country_rows), "affected_skus": unknown_country_skus})

overall = "Ready to share" if not issues else ("Needs revision" if any(i["severity"] in {"Critical", "High"} for i in issues) else "Share with caveats")
result_summary = {
    "overall_assessment": overall,
    "analysis_period": [options["start_date"], options["end_date"]],
    "saved_at": latest["saved_at"],
    "source_sales_rows": len(sales_raw),
    "analytical_rows": len(merged),
    "sku_count": len(frontend_summary),
    "country_sku_summary_rows": len(summary_actual),
    "country_sku_monthly_rows": len(monthly_actual),
    "reconciliation_failures": recon_failures,
    "coverage_failures": coverage_failures,
    "partial_months": partial_months,
    "identity_conflict_skus": len(identity_anomalies),
    "near_duplicate_sku_groups": len(near_duplicate_groups),
    "negative_sales_rows": int(negative_raw["negative_rows"].sum()),
    "missing_field_rows": int(missing_checks["rows"].sum()),
    "total_sales_amount_eur": total_amount,
    "total_sales_qty": total_qty,
    "partial_month_peak_changed_skus": int(peak_changed.sum()),
    "negative_month_skus": negative_month_skus,
    "uncategorized_skus": uncategorized_skus,
    "uncategorized_sales_amount_eur": uncategorized_amount,
    "uncategorized_sales_share_pct": uncategorized_amount / total_amount * 100 if total_amount else 0,
    "unknown_country_skus": unknown_country_skus,
    "unknown_country_sales_amount_eur": unknown_country_amount,
    "unknown_country_sales_share_pct": unknown_country_amount / total_amount * 100 if total_amount else 0,
    "issues": issues,
}
print(json.dumps(result_summary, ensure_ascii=False, indent=2))
'''
    ),
    markdown("## Takeaways\n\n실행 결과의 `overall_assessment`와 `issues`가 최종 판정이다. 상세 불일치 행은 아래 저장 파일에서 추적할 수 있다."),
    code(
        r'''
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
latest_at_end = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
assert latest_at_end.get("saved_at") == latest_saved_at, "백테스트 도중 최신 분석 스냅샷이 변경되었습니다. 다시 실행하세요."
(OUTPUT_DIR / "backtest_summary.json").write_text(json.dumps(result_summary, ensure_ascii=False, indent=2), encoding="utf-8")
reconciliation.to_csv(OUTPUT_DIR / "metric_reconciliation.csv", index=False, encoding="utf-8-sig")
coverage_compare.to_csv(OUTPUT_DIR / "month_coverage_reconciliation.csv", index=False, encoding="utf-8-sig")
frontend_summary.head(50).to_csv(OUTPUT_DIR / "top50_sku.csv", index=False, encoding="utf-8-sig")
identity_anomalies.to_csv(OUTPUT_DIR / "identity_anomalies.csv", index=False, encoding="utf-8-sig")
missing_checks.to_csv(OUTPUT_DIR / "missing_fields.csv", index=False, encoding="utf-8-sig")
negative_raw.to_csv(OUTPUT_DIR / "negative_rows_summary.csv", index=False, encoding="utf-8-sig")
impact_summary.to_csv(OUTPUT_DIR / "interpretation_risk_summary.csv", index=False, encoding="utf-8-sig")
peak_sensitivity.loc[peak_changed].to_csv(OUTPUT_DIR / "partial_month_peak_changes.csv", index=False, encoding="utf-8-sig")
pd.DataFrame([{"normalized": key, "spellings": " | ".join(values)} for key, values in near_duplicate_groups.items()]).to_csv(
    OUTPUT_DIR / "near_duplicate_skus.csv", index=False, encoding="utf-8-sig"
)
print("Saved evidence to", OUTPUT_DIR)
'''
    ),
]

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
nbf.write(notebook, NOTEBOOK_PATH)
print(NOTEBOOK_PATH)
