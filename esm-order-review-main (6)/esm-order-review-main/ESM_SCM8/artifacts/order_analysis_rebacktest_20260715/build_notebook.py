from __future__ import annotations

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "order_analysis_postfix_backtest.ipynb"


notebook = nbf.v4.new_notebook()
notebook["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.11"},
}
notebook["cells"] = [
    nbf.v4.new_markdown_cell(
        """# 발주분석 수정 후 재백테스트

## tl;dr

- **판정: 조건부 공유 가능(Share with caveat).** 수정 대상 14개 수용 조건은 모두 통과했고 전체 회귀검사도 통과했습니다.
- 저장된 최신 발주결과 **2,571행**을 현행 TypeScript 계산 경로로 다시 산출한 결과, 부족수량 계약 불일치와 연도 없는 날짜는 각각 **0건**이었습니다.
- 이전 실데이터 내보내기의 부족수량 불일치 **30건(+170,930개)**은 새 단일 산식 계약을 적용하면 **0건**이 됩니다.
- Python 전체 테스트는 **168 passed, 1 skipped**, 프런트 발주분석 11개 단언·타입검사·프로덕션 빌드가 통과했습니다.
- 단, 수정 후 UI에서 새로 내려받은 Excel은 아직 없고, 저장 결과 중 **303행은 ETA가 분석 기준일보다 과거**입니다. 이 중 250행이 `sufficient`이므로 실제 입고 완료 여부와 대조가 필요합니다.
"""
    ),
    nbf.v4.new_markdown_cell(
        """## Context & Methods

검증 범위는 발주검토, 재고공백, SKU 집중도, Excel 내보내기 계약입니다. 기존 실제 Excel 두 개를 기준선으로 보존하고, 최신 저장 발주결과를 현재 코드에 다시 통과시켰습니다. 합성 경계값으로 분석 기준일, 기간 시작·종료일, 결측 식별자와 OOXML 유효성 검사를 확인했습니다.

### 핵심 가정

- 부족수량의 화면 계약은 `ceil(공백일수 × 일평균 판매량)`입니다.
- 최근 3개월 집계는 설정된 시작일과 종료일을 모두 포함합니다.
- 과거 ETA는 입고 완료일 수도 있으므로, 입고 상태가 없으면 데이터 신선도 경고로 분류합니다.
- 새 UI 생성 Excel이 없으므로 Excel 수정은 코드 검사와 표준 파서 스모크 테스트로 검증합니다.
"""
    ),
    nbf.v4.new_code_cell(
        """import json
from pathlib import Path
import pandas as pd

HERE = Path.cwd()
results = json.loads((HERE / "postfix_results.json").read_text(encoding="utf-8"))
results["as_of"]
"""
    ),
    nbf.v4.new_markdown_cell("## Results"),
    nbf.v4.new_code_cell(
        """acceptance = results["postfix_acceptance_checks"]
pd.DataFrame([{
    "overall_assessment": results["assessment"],
    "acceptance_passed": acceptance["passed"],
    "acceptance_total": acceptance["total"],
    "all_regression_runs_passed": results["all_executed_tests_passed"],
    "fresh_postfix_ui_workbook": results["residual_risks"]["postfix_ui_workbook_available"],
}])
"""
    ),
    nbf.v4.new_code_cell(
        """baseline = results["baseline_exports"]["stock_gap_export"]
live = results["saved_result_current_code"]
boundary = live["boundary_checks"]
python_checks = results["python_boundary_checks"]
excel = results["excel_validation_smoke"]

issue_closure = pd.DataFrame([
    {"check": "부족수량 산식 불일치", "before": baseline["shortage_reconciliation_exceptions"], "after": live["stock_gap"]["canonical_shortage_mismatches"], "evidence": "저장 2,571행 현행 계산"},
    {"check": "연도 없는 날짜", "before": baseline["gap_date_ambiguous_rows"], "after": live["stock_gap"]["full_year_date_failures"], "evidence": f'{live["stock_gap"]["date_values_checked"]:,}개 날짜 검사'},
    {"check": "과거 기준일 비결정성", "before": 1, "after": 0 if boundary["historical_fallback_independent"] else 1, "evidence": boundary["historical_base_date_status"]},
    {"check": "기간 밖 판매 포함", "before": 1, "after": 0 if python_checks["period_filter_passed"] else 1, "evidence": f'{python_checks["inclusive_observed_qty"]:.0f}개·{python_checks["concentration_observed_amount_krw"]:.0f}원'},
    {"check": "결측 식별자 nan", "before": 1, "after": 0 if python_checks["missing_identity_passed"] else 1, "evidence": f'{python_checks["product_name"]}/{python_checks["brand"]}'},
    {"check": "비표준 Excel errorStyle", "before": 1, "after": 0 if excel["passed"] else 1, "evidence": "openpyxl 재로드 성공"},
])
issue_closure
"""
    ),
    nbf.v4.new_code_cell(
        """stock = live["stock_gap"]
pd.DataFrame([{
    "input_rows": live["population"]["input_rows"],
    "computed_rows": live["population"]["computed_rows"],
    "risk_rows": stock["risk_rows"],
    "long_gap_rows": stock["long_gap_rows"],
    "canonical_shortage_qty": stock["total_canonical_shortage_qty"],
    "shortage_mismatches": stock["canonical_shortage_mismatches"],
    "date_failures": stock["full_year_date_failures"],
}])
"""
    ),
    nbf.v4.new_code_cell(
        """eta = stock["eta_before_base_detail"]
pd.DataFrame([{
    "eta_before_base_rows": eta["rows"],
    "sufficient": eta["status_counts"].get("sufficient", 0),
    "needs_check": eta["status_counts"].get("needs_check", 0),
    "eta_delay_flag_rows": eta["eta_delay_flag_rows"],
    "risk_status_rows": eta["risk_status_rows"],
    "interpretation": results["residual_risks"]["eta_interpretation"],
}])
"""
    ),
    nbf.v4.new_code_cell(
        """pd.DataFrame([
    {"test": item["name"], "passed": item["passed"], "duration_seconds": item["duration_seconds"]}
    for item in results["test_runs"]
])
"""
    ),
    nbf.v4.new_code_cell(
        """assert acceptance == {"passed": 14, "total": 14, "all_passed": True}
assert results["all_executed_tests_passed"]
assert live["population"]["input_rows"] == live["population"]["computed_rows"] == 2571
assert stock["canonical_shortage_mismatches"] == 0
assert stock["full_year_date_failures"] == 0
assert boundary["historical_base_date_status"] == "sufficient"
assert python_checks["period_filter_passed"] and python_checks["missing_identity_passed"]
assert excel["passed"]
print("All post-fix acceptance assertions passed.")
"""
    ),
    nbf.v4.new_markdown_cell(
        """## Takeaways

1. 기존에 수정한 6개 결함은 코드·경계값·저장 실데이터 규모 재산출에서 모두 닫혔습니다.
2. 발주검토 산술 기준선은 계속 일치합니다.
3. 부족수량은 단일 계산 함수로 통합되어 화면·요약·내보내기 계약이 일치합니다.
4. ETA가 기준일보다 과거인 303행은 계산 결함으로 단정할 수 없지만, 입고 완료 상태 없이 현재 ETA로 해석하면 안 됩니다.
5. 완전한 종료 판정에는 수정 후 UI에서 새 Excel을 한 번 내려받아 같은 스크립트로 직접 재로드하는 절차가 남아 있습니다.
"""
    ),
]

client = NotebookClient(
    notebook,
    timeout=180,
    kernel_name="python3",
    resources={"metadata": {"path": str(HERE)}},
)
client.execute()
nbf.write(notebook, OUTPUT)
print(OUTPUT)
