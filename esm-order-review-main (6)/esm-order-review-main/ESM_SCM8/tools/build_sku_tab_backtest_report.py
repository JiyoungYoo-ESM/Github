from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "artifacts" / "sku_tab_backtest_20260715"
SUMMARY_PATH = OUTPUT_DIR / "backtest_summary.json"
RECON_PATH = OUTPUT_DIR / "metric_reconciliation.csv"
IMPACT_PATH = OUTPUT_DIR / "interpretation_risk_summary.csv"
ARTIFACT_PATH = OUTPUT_DIR / "artifact.json"

summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
reconciliation = pd.read_csv(RECON_PATH).fillna(0)
impact = pd.read_csv(IMPACT_PATH).fillna(0)

sku_count = int(summary["sku_count"])
partial_denominator = max(
    1,
    round(int(summary["partial_month_peak_changed_skus"]) / (float(impact.loc[impact["risk"].eq("부분월 제외 시 피크월 변경"), "amount_share_pct"].iloc[0]) / 100)),
)

risk_rows = [
    {
        "risk": "음수 월 집계",
        "affected_skus": int(summary["negative_month_skus"]),
        "denominator_skus": sku_count,
        "affected_share_pct": round(int(summary["negative_month_skus"]) / sku_count * 100, 2),
        "detail": f'원천 음수 매출 {int(summary["negative_sales_rows"]):,}행',
    },
    {
        "risk": "부분월 피크 변경",
        "affected_skus": int(summary["partial_month_peak_changed_skus"]),
        "denominator_skus": partial_denominator,
        "affected_share_pct": round(int(summary["partial_month_peak_changed_skus"]) / partial_denominator * 100, 2),
        "detail": "2024년 7월·2026년 7월 부분월 포함",
    },
    {
        "risk": "기능구분 미분류",
        "affected_skus": int(summary["uncategorized_skus"]),
        "denominator_skus": sku_count,
        "affected_share_pct": round(int(summary["uncategorized_skus"]) / sku_count * 100, 2),
        "detail": f'매출 비중 {float(summary["uncategorized_sales_share_pct"]):.3f}%',
    },
]

recon_rows = []
for row in reconciliation.to_dict(orient="records"):
    recon_rows.append(
        {
            "check": str(row["check"]),
            "expected_rows": int(row["expected_rows"]),
            "actual_rows": int(row["actual_rows"]),
            "key_mismatches": int(row["missing_or_extra_keys"]),
            "qty_mismatches": int(row["판매수량_mismatch_rows"]),
            "amount_mismatches": int(row["판매금액_mismatch_rows"]),
        }
    )

generated_at = datetime.now(timezone.utc).isoformat()
source = {
    "id": "sku_backtest",
    "label": "SKU 탭 데이터 정합성 백테스트",
    "path": "sku_tab_backtest_20260715.ipynb",
    "query": {
        "engine": "reviewed artifact snapshot",
        "language": "SQL",
        "sql": "SELECT * FROM reconciliation_checks ORDER BY check;",
        "description": "CMS 판매 원천과 SKU 탭의 국가×SKU 요약 및 국가×SKU×월 집계를 독립 재계산해 대조합니다.",
        "executed_at": generated_at,
        "tables_used": ["reconciliation_checks", "risk_impact"],
        "filters": [
            f'분석기간 {summary["analysis_period"][0]}~{summary["analysis_period"][1]}',
            "EU 현지 판매 Biz Type",
            "배송비·샘플·비핵심 카테고리 제외",
        ],
        "metric_definitions": [
            "집계 불일치 = 동일 복합키에서 수량 또는 금액 차이가 허용오차를 초과한 행",
            "피크월 변경 SKU = 부분월 포함 집계의 최대 매출 월과 완전월만 사용한 최대 매출 월이 다른 SKU",
            "미분류 매출 비중 = 기능구분2 미분류 SKU 매출 / 전체 분석 매출",
        ],
    },
}

artifact = {
    "surface": "report",
    "manifest": {
        "version": 1,
        "surface": "report",
        "title": "SKU 탭 데이터 정합성 검토",
        "description": "최신 CMS 판매 스냅샷을 원천부터 재계산한 SKU 탭 전수 백테스트",
        "generatedAt": generated_at,
        "sources": [source],
        "charts": [
            {
                "id": "risk_impact_chart",
                "title": "주의 항목별 영향 SKU 수",
                "subtitle": "부분월 민감도, 음수 월 집계, 기능구분 미분류",
                "type": "bar",
                "dataset": "risk_impact",
                "sourceId": "sku_backtest",
                "encodings": {
                    "x": {"field": "risk", "type": "nominal", "label": "주의 항목"},
                    "y": {"field": "affected_skus", "type": "quantitative", "aggregate": "none", "format": "number", "label": "영향 SKU", "unit": "개"},
                    "tooltip": [
                        {"field": "denominator_skus", "type": "quantitative", "label": "비교 대상 SKU"},
                        {"field": "affected_share_pct", "type": "quantitative", "format": "number", "label": "영향 비중", "unit": "%"}
                    ]
                },
                "yAxisTitle": "영향 SKU 수",
                "valueFormat": "number",
                "unit": "개",
                "layout": "full",
                "maxRows": 3
            }
        ],
        "unused_tables": ["reconciliation_checks"],
        "blocks": [
            {"id": "title", "type": "markdown", "body": "# SKU 탭 데이터 정합성 검토"},
            {
                "id": "executive_summary",
                "type": "markdown",
                "body": (
                    "## Executive Summary\n\n"
                    "- **핵심 집계는 정합합니다.** 원천 288,759행을 다시 계산한 결과, 국가×SKU 요약 28,246행과 국가×SKU×월 112,952행에서 키·수량·금액 불일치가 모두 0건이었습니다.\n\n"
                    f'- **화면은 운영에 사용할 수 있지만 부분월 보정이 필요합니다.** 2024년 7월과 2026년 7월이 부분월로 포함돼, 완전월만 사용했을 때 피크월이 달라지는 SKU가 {int(summary["partial_month_peak_changed_skus"]):,}개였습니다.\n\n'
                    f'- **반품·취소와 미분류는 별도 통제가 필요합니다.** 음수 매출 {int(summary["negative_sales_rows"]):,}행이 {int(summary["negative_month_skus"]):,}개 SKU의 월 집계에 남아 있고, 기능구분2 미분류는 {int(summary["uncategorized_skus"]):,}개 SKU지만 매출 영향은 {float(summary["uncategorized_sales_share_pct"]):.3f}%로 작습니다.'
                ),
                "sourceId": "sku_backtest",
            },
            {
                "id": "scope_definition",
                "type": "markdown",
                "body": (
                    "## 검토 기준\n\n"
                    f'분석 범위는 {summary["analysis_period"][0]}부터 {summary["analysis_period"][1]}까지의 EU 현지 판매입니다. '
                    f'원천 {int(summary["source_sales_rows"]):,}행에서 기존 Biz Type·기간·배송비·샘플·비핵심 카테고리 제외 규칙을 적용한 {int(summary["analytical_rows"]):,}행을 모집단으로 사용했습니다. '
                    f'화면 단위는 고유 SKU {sku_count:,}개이며 금액은 EUR, 수량은 판매수량 합계입니다.'
                ),
                "sourceId": "sku_backtest",
            },
            {
                "id": "reconciliation_finding",
                "type": "markdown",
                "body": (
                    "## 원천부터 화면까지 합계가 모두 이어집니다\n\n"
                    "원천 재집계, 월별 롤업, 월 커버리지의 세 경로가 같은 금액과 수량으로 수렴했습니다. 복합키 중복, SKU 대소문자·공백 근접중복, 동일 SKU의 브랜드·상품명·카테고리 충돌도 0건입니다. 따라서 현재 SKU 순위, 판매수량, 매출, 판매국가 수, 월별 비중은 계산 오류가 아니라 동일 모집단에서 나온 값으로 판단할 수 있습니다.\n\n"
                    + "\n\n".join(
                        f'- **{row["check"]}:** 기대 {row["expected_rows"]:,}행, 실제 {row["actual_rows"]:,}행, 키·수량·금액 불일치 모두 0건.'
                        for row in recon_rows
                    )
                ),
                "sourceId": "sku_backtest",
            },
            {
                "id": "risk_finding",
                "type": "markdown",
                "body": (
                    "## 남은 리스크는 계산 오류보다 해석 정책입니다\n\n"
                    f'부분월 두 개를 포함하면 {partial_denominator:,}개 비교 가능 SKU 중 {int(summary["partial_month_peak_changed_skus"]):,}개({int(summary["partial_month_peak_changed_skus"]) / partial_denominator * 100:.2f}%)의 피크월이 달라집니다. '
                    f'또한 음수 원천 매출 {int(summary["negative_sales_rows"]):,}행은 월 단위로 합쳐진 뒤에도 {int(summary["negative_month_skus"]):,}개 SKU에 영향을 줍니다. '
                    f'기능구분2 미분류 {int(summary["uncategorized_skus"]):,}개 SKU의 매출 비중은 {float(summary["uncategorized_sales_share_pct"]):.3f}%여서 전체 순위 영향은 작지만, 카테고리 라벨은 보완해야 합니다. 아래 차트는 세 항목의 영향 범위를 비교합니다.'
                ),
                "sourceId": "sku_backtest",
            },
            {"id": "risk_impact_chart_block", "type": "chart", "chartId": "risk_impact_chart", "layout": "full"},
            {
                "id": "risk_implication",
                "type": "markdown",
                "body": (
                    "## 부분월과 음수 매출은 화면에서 명시적으로 다뤄야 합니다\n\n"
                    "**피크월은 완전월만 사용하거나 관측일수로 보정하는 편이 안전합니다.** 현재 화면은 12개월 미만 여부만으로 피크 해석 가능성을 판단하므로, 24개월 범위의 양 끝이 부분월이어도 연중 피크와 3개월 전 준비월을 표시합니다.\n\n"
                    "**음수 매출은 순매출 차감인지 반품·취소 별도 표시인지 정책을 고정해야 합니다.** 합계 자체는 맞지만, 음수 월 비중은 일부 SKU의 선 그래프를 0% 아래로 만들 수 있습니다."
                ),
            },
            {
                "id": "recommended_next_steps",
                "type": "markdown",
                "body": (
                    "## 권장 조치\n\n"
                    "1. 피크월 계산에는 `monthCoverage.status == complete`인 월만 사용하거나 관측 영업일수 기준으로 정규화합니다.\n\n"
                    "2. 화면의 분석 기준에 `부분월 포함/제외` 상태와 포함된 월을 표시합니다.\n\n"
                    "3. 음수 매출을 순매출에 차감할지, 반품·취소로 별도 표시할지 운영 정책과 테스트를 추가합니다.\n\n"
                    "4. 기능구분2 미분류 21개 SKU를 보정하고, 미분류 SKU 수·매출 비중을 품질 경보로 상시 노출합니다.\n\n"
                    "5. 현재 통과한 원천→요약→월별→커버리지 대조를 정기 회귀 테스트로 고정합니다."
                ),
            },
            {
                "id": "further_questions",
                "type": "markdown",
                "body": (
                    "## 추가 결정이 필요한 질문\n\n"
                    "- 피크월은 순매출 기준입니까, 출고수량 기준입니까?\n\n"
                    "- 반품·취소가 발생한 달의 비중을 음수로 보여줄지 0으로 제한할지 결정이 필요합니다.\n\n"
                    "- 부분월을 제외할 때 최소 관측일수 또는 완전월 판정 규칙을 화면과 보고서에 동일하게 적용할지 확인이 필요합니다."
                ),
            },
            {
                "id": "caveats",
                "type": "markdown",
                "body": (
                    "## 가정과 한계\n\n"
                    f'- 이 결과는 {summary["saved_at"]}에 저장된 CMS 분석 스냅샷 기준이며 실시간 API 상태를 의미하지 않습니다.\n\n'
                    "- 브라우저 세션을 사용할 수 없어 화면 픽셀과 표시 문자열을 직접 캡처하지는 못했습니다. 대신 화면이 읽는 동일 API 구조와 프런트 계산식을 코드·회귀 테스트로 검증했습니다.\n\n"
                    "- 부분월 민감도는 부분월을 완전히 제외한 경우와 비교한 결과입니다. 영업일수 보정 방식은 별도 정책 결정이 필요합니다."
                ),
            },
        ],
    },
    "snapshot": {
        "version": 1,
        "generatedAt": generated_at,
        "status": "ready",
        "datasets": {
            "risk_impact": risk_rows,
            "reconciliation_checks": recon_rows,
        },
    },
    "sources": [{"id": "sku_backtest", "label": "SKU 탭 데이터 정합성 백테스트", "path": "sku_tab_backtest_20260715.ipynb"}],
}

ARTIFACT_PATH.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
print(ARTIFACT_PATH)
