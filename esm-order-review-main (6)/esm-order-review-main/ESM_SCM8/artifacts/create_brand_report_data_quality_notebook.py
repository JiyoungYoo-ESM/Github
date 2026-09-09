from __future__ import annotations

from pathlib import Path

import nbformat as nbf


ARTIFACT_DIR = Path(__file__).resolve().parent
NOTEBOOK_PATH = ARTIFACT_DIR / "brand_report_data_quality_audit.ipynb"


cells = [
    nbf.v4.new_markdown_cell(
        """# 브랜드 자동 리포트 데이터 정합성 감사

## tl;dr

- 원천 재구성 합계, 국가·SKU 요약, 월별 큐브, 월 커버리지, 브랜드 리포트의 **매출 €36,197,522.84와 유상 판매수량 5,743,900개가 전부 일치**한다.
- 편강율 화면값도 원천 집계와 일치한다: **매출 €41,361.75, 판매수량 8,072개, 판매 SKU 13개, 최고월 2024-09 €14,358.84**.
- 현재 재고 스냅샷은 2,586개 SKU가 모두 유일하고, 기준일은 2026-07-23 하나이며, 일평균 판매량은 `최근 3개월 판매수량 ÷ 90`과 전 행 일치한다.
- 원화 환산은 **현재 적용 환율 EUR/KRW 1,689.48(고시일 2026-07-23)**을 사용하고, 화면에도 현재 환율임을 명시한다.
- 판매금액 0·수량 양수인 무상증정 467행, 33,742개는 판매 집계에서 제외했다.
- 원천에는 완전 중복 후보 63쌍(분석 대상 기준 최대 매출 0.1694% 영향)과 부분 월 2024-04이 존재한다.
"""
    ),
    nbf.v4.new_markdown_cell(
        """## Context & Methods

### 감사 범위

- 판매 분석: PL 법인, 2024-04-01~2024-12-31, CMS `/eu/sales/local`
- 판매 원천 단위: 송장·SKU 출고행
- 브랜드 리포트 단위: 브랜드 합계와 브랜드별 국가·SKU·카테고리·월 집계
- 재고 단위: 2026-07-23 기준 SKU별 발주분석 스냅샷

### Key Assumptions

- `amount_krw` 필드는 현재 API에서 EUR 정규화 금액으로 사용된다는 애플리케이션 정의를 따른다.
- 원천에 행 식별자가 없어 완전 중복 후보가 실제 중복인지 동일 송장의 합법적인 반복 라인인지는 별도 소스 확인이 필요하다.
- 매출 0 출고를 판매수량에 포함할지는 업무 정의가 필요하므로 오류로 단정하지 않고 정책 이슈로 분류한다.
"""
    ),
    nbf.v4.new_markdown_cell("## Data"),
    nbf.v4.new_code_cell(
        """from pathlib import Path
import sys
import pandas as pd
from IPython.display import display

project_root = Path.cwd()
sys.path.insert(0, str(project_root / "artifacts"))
from brand_report_data_quality_audit import run_audit

audit = run_audit()
print("판매 원천:", audit["source_path"])
print("시즌 스냅샷:", audit["season_snapshot"])
print("재고 스냅샷:", audit["order_snapshot"])
print("분석 옵션:", {
    key: audit["analysis_options"].get(key)
    for key in ("start_date", "end_date", "entity_code", "average_eur_krw_rate", "exchange_rate_date")
})"""
    ),
    nbf.v4.new_code_cell(
        """source_summary = pd.DataFrame([
    {"항목": "판매 원천 행", "값": audit["raw_profile"]["rows"]},
    {"항목": "최종 리포트 모집단 행", "값": audit["row_flow"]["final_rows"]},
    {"항목": "브랜드 수", "값": audit["report_checks"]["brand_count"]},
    {"항목": "재고 SKU 수", "값": audit["stock_profile"]["rows"]},
    {"항목": "완료 월", "값": audit["temporal_profile"]["complete_months"]},
    {"항목": "부분 월", "값": ", ".join(audit["temporal_profile"]["partial_months"])},
])
display(source_summary)"""
    ),
    nbf.v4.new_markdown_cell("## Results"),
    nbf.v4.new_markdown_cell("### 1. 필수 필드 완전성"),
    nbf.v4.new_code_cell(
        """display(audit["completeness"].sort_values("missing_rate_pct", ascending=False))
print("상품 마스터 결합:", audit["mapping_profile"])"""
    ),
    nbf.v4.new_markdown_cell("### 2. 원천→집계→리포트 합계 대사"),
    nbf.v4.new_code_cell(
        """display(audit["totals"].round(6))
checks = pd.DataFrame([
    {"검사": key, "통과": value}
    for key, value in audit["report_checks"].items()
])
display(checks)"""
    ),
    nbf.v4.new_markdown_cell("### 3. 편강율 화면값 대사"),
    nbf.v4.new_code_cell(
        """focus_sales = pd.DataFrame(audit["focus"]["sales"])
focus_stock = pd.DataFrame(audit["focus"]["stock"])
display(focus_sales[[
    "브랜드", "source_amount", "report_amount", "amount_diff",
    "source_qty", "report_qty", "qty_diff", "source_skus", "report_skus",
    "monthly_diff", "top5_share_pct"
]])
display(focus_stock)"""
    ),
    nbf.v4.new_markdown_cell("### 4. 월 커버리지와 부분 월"),
    nbf.v4.new_code_cell(
        """display(audit["month_profile"])
print("부분 월 매출 비중(%):", audit["temporal_profile"]["partial_month_amount_share_pct"])"""
    ),
    nbf.v4.new_markdown_cell("### 5. 재고·MOI 결합 품질"),
    nbf.v4.new_code_cell(
        """stock_keys = [
    "rows", "distinct_skus", "duplicate_sku_rows", "missing_sku_rows",
    "missing_brand_rows", "base_dates", "negative_available_rows",
    "negative_recent_sales_rows", "daily_sales_formula_mismatch_rows",
    "sales_brand_stock_match_rate_pct", "order_required_rows",
]
display(pd.DataFrame([
    {"검사": key, "결과": audit["stock_profile"][key]}
    for key in stock_keys
]))"""
    ),
    nbf.v4.new_markdown_cell("### 6. 원천 이상치와 표시 기준"),
    nbf.v4.new_code_cell(
        """anomaly_keys = [
    "duplicate_groups", "duplicate_excess_rows_if_keep_first",
    "duplicate_excess_amount_share_pct", "final_zero_amount_rows",
    "final_zero_amount_qty", "final_zero_amount_qty_share_pct",
    "final_negative_rows", "final_negative_amount_share_pct",
]
display(pd.DataFrame([
    {"검사": key, "결과": audit["anomaly_profile"][key]}
    for key in anomaly_keys
]))
display(audit["currency_ratio"])"""
    ),
    nbf.v4.new_code_cell(
        """findings = pd.DataFrame([
    {
        "심각도": item["severity"],
        "발견사항": item["finding"],
        "근거": str(item["evidence"]),
    }
    for item in audit["findings"]
])
display(findings)"""
    ),
    nbf.v4.new_markdown_cell(
        """## Takeaways

1. **집계 로직 정합성은 통과**다. 화면 수치가 집계 과정에서 틀어지는 문제는 현재 스냅샷에서 발견되지 않았다.
2. **원화 환산은 현재 적용 환율로 명확히 표시한다.** 환율 API를 일 1회 갱신하고, 성공 시 고시일을 함께 표시하며 실패 시에는 기본값임을 명시한다.
3. **완전 중복 후보는 CMS 원천에 존재한다.** 63쌍의 최대 영향은 분석 대상 매출의 0.1694%이며, CMS 행 ID가 없어 자동 삭제하지 않는다. 영향이 0.5% 이상이면 자동 발주 추천을 차단한다.
4. **무상증정은 판매수량에서 제외했다.** 판매금액 0·수량 양수인 467행, 33,742개를 판매 집계 모집단에서 제거했다.
5. **2024-04은 부분 월**이다. 전체 매출에는 포함되지만 YoY·추세 비교에서는 완료월만 사용해야 한다. 현재 YoY 로직은 완료월만 사용한다.
"""
    ),
]


notebook = nbf.v4.new_notebook(
    cells=cells,
    metadata={
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3"},
    },
)
nbf.write(notebook, NOTEBOOK_PATH)
print(NOTEBOOK_PATH)
