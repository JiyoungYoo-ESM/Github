from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "artifacts" / "brand_backtest_20260715.json"
REPORT_DIR = ROOT / "artifacts" / "brand_backtest_report_20260715"
ARTIFACT_PATH = REPORT_DIR / "artifact.json"
NOTEBOOK_PATH = ROOT / "artifacts" / "brand_backtest_audit_20260715.ipynb"


def find_finding(result: dict, finding_id: str) -> dict:
    return next(item for item in result["findings"] if item["id"] == finding_id)


def rounded(value: float, digits: int = 1) -> float:
    return round(float(value), digits)


def materialize_via_sql(rows: list[dict], table_name: str, query: str) -> list[dict]:
    if not rows:
        return []
    columns = list(rows[0])
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        definitions = []
        for column in columns:
            sample = next((row.get(column) for row in rows if row.get(column) is not None), None)
            sql_type = "REAL" if isinstance(sample, (int, float)) and not isinstance(sample, bool) else "TEXT"
            definitions.append(f'"{column}" {sql_type}')
        connection.execute(f'CREATE TABLE "{table_name}" ({", ".join(definitions)})')
        placeholders = ", ".join("?" for _ in columns)
        connection.executemany(
            f'INSERT INTO "{table_name}" ({", ".join(f"{chr(34)}{column}{chr(34)}" for column in columns)}) VALUES ({placeholders})',
            [[row.get(column) for column in columns] for row in rows],
        )
        return [dict(row) for row in connection.execute(query).fetchall()]
    finally:
        connection.close()


def build_notebook(result: dict) -> None:
    source = result["source"]
    summary = result["checkSummary"]
    finding_summary = result["findingSummary"]
    sku_finding = find_finding(result, "sku_concentration_top5_denominator")
    season_finding = find_finding(result, "seasonality_year_aggregation")

    notebook = nbf.v4.new_notebook()
    notebook["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3"},
    }
    notebook["cells"] = [
        nbf.v4.new_markdown_cell(
            "## tl;dr\n\n"
            f"- 라이브 브랜드 탭 백테스트는 **{summary['passed']}/{summary['total']}개 검증을 통과**했습니다.\n"
            f"- **High {finding_summary['high']}건**: SKU 집중도 분모 오류와 다년 월별 비교의 달력월 합산 왜곡이 확인됐습니다.\n"
            f"- SKU 집중도 오류는 **{sku_finding['evidence']['affectedBrands']}/{source['brandCount']}개 브랜드**에 영향을 줍니다.\n"
            f"- 다년 월 합산 때문에 최고월이 달라지는 브랜드는 **{season_finding['evidence']['brandsWithDifferentPeakMonth']}개**입니다."
        ),
        nbf.v4.new_markdown_cell(
            "## Context & Methods\n\n"
            "브랜드 탭의 브랜드 순위, 매출·수량·SKU·국가 KPI, MoM/YoY 성장, SKU 집중도, 국가/제품군 분포, 월별 비교를 최신 분석 API 결과에서 독립 재계산했습니다.\n\n"
            "### Key Assumptions\n\n"
            "- 브랜드 탭의 정본은 `countrySkuSummary`, 월별 정본은 `countrySkuMonthly`입니다.\n"
            "- 성장률은 `monthCoverage.status == complete`인 월만 비교합니다.\n"
            "- SKU 집중도는 브랜드 전체 매출을 분모로 해석합니다.\n"
            "- 다년 시즌성은 완료월만 사용하고 달력월별 관측 연도 수로 평균해야 비교 가능합니다."
        ),
        nbf.v4.new_markdown_cell("## Data"),
        nbf.v4.new_code_cell(
            "from pathlib import Path\n"
            "import json\n"
            "import pandas as pd\n\n"
            "result_path = Path('artifacts/brand_backtest_20260715.json')\n"
            "result = json.loads(result_path.read_text(encoding='utf-8'))\n"
            "source_summary = pd.DataFrame([{\n"
            "    '기간': f\"{result['source']['analysisOptions']['start_date']} ~ {result['source']['analysisOptions']['end_date']}\",\n"
            "    '브랜드': result['source']['brandCount'],\n"
            "    '요약행': result['source']['summaryRows'],\n"
            "    '월별행': result['source']['monthlyRows'],\n"
            "    '전체월': result['source']['monthCount'],\n"
            "    '완료월': result['source']['completeMonthCount'],\n"
            "}])\n"
            "source_summary"
        ),
        nbf.v4.new_markdown_cell("## Results"),
        nbf.v4.new_code_cell(
            "checks = pd.DataFrame([{\n"
            "    '검증': item['id'],\n"
            "    '결과': 'PASS' if item['passed'] else 'FAIL',\n"
            "} for item in result['checks']])\n"
            "checks"
        ),
        nbf.v4.new_code_cell(
            "findings = pd.DataFrame([{\n"
            "    '심각도': item['severity'].upper(),\n"
            "    '이슈': item['title'],\n"
            "    '영향': item['impact'],\n"
            "    '조치': item['recommendation'],\n"
            "} for item in result['findings']])\n"
            "findings"
        ),
        nbf.v4.new_code_cell(
            "sku_issue = next(item for item in result['findings'] if item['id'] == 'sku_concentration_top5_denominator')\n"
            "sku_examples = pd.DataFrame(sku_issue['evidence']['worstExamples'])\n"
            "sku_examples[['brand', 'skuCount', 'trueTopFiveSharePct', 'uiTopFiveSharePct', 'trueTopOneSharePct', 'uiTopOneSharePct', 'topOneOverstatementPp']]"
        ),
        nbf.v4.new_code_cell(
            "season_issue = next(item for item in result['findings'] if item['id'] == 'seasonality_year_aggregation')\n"
            "peak_examples = pd.DataFrame(season_issue['evidence']['samples'])\n"
            "peak_examples"
        ),
        nbf.v4.new_markdown_cell(
            "## Takeaways\n\n"
            "1. SKU 집중도 분모를 브랜드 전체 SKU 매출 합계로 수정해야 합니다.\n"
            "2. 월별 비교는 `year_month` 추이와 달력월 시즌성을 분리해야 합니다. 시즌성은 완료월·연평균 기준이 안전합니다.\n"
            "3. 부분월 포함 범위와 성장률 완료월 범위를 화면에 명확히 표시해야 합니다.\n"
            "4. 미분류 카테고리 매출 비중을 상시 품질 지표로 모니터링하는 것이 좋습니다."
        ),
    ]

    client = NotebookClient(
        notebook,
        timeout=120,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    executed = client.execute()
    nbf.write(executed, NOTEBOOK_PATH)


def build_report_artifact(result: dict) -> None:
    source = result["source"]
    metrics = result["metrics"]
    check_summary = result["checkSummary"]
    finding_summary = result["findingSummary"]
    sku_finding = find_finding(result, "sku_concentration_top5_denominator")
    season_finding = find_finding(result, "seasonality_year_aggregation")
    partial_finding = find_finding(result, "partial_month_scope_difference")
    mapping_finding = find_finding(result, "unmapped_dimensions")

    sku_examples = sku_finding["evidence"]["worstExamples"]
    peak_examples = season_finding["evidence"]["samples"]
    source_id = "brand_backtest_result"
    source_entry = {
        "id": source_id,
        "label": "브랜드 탭 라이브 백테스트 결과",
        "path": "artifacts/brand_backtest_20260715.json",
    }

    sku_share_chart = []
    for row in sku_examples:
        common = {
            "brand": row["brand"],
            "sku_count": row["skuCount"],
            "true_top1_share_pct": rounded(row["trueTopOneSharePct"]),
            "ui_top1_share_pct": rounded(row["uiTopOneSharePct"]),
        }
        sku_share_chart.append({**common, "series": "화면 표시", "share_pct": 100.0})
        sku_share_chart.append({**common, "series": "실제 Top 5 비중", "share_pct": rounded(row["trueTopFiveSharePct"])})

    issue_rows = [
        {
            "severity": "High",
            "severity_rank": 3,
            "issue": "SKU 집중도 Top 5 분모 오류",
            "affected": f"{sku_finding['evidence']['affectedBrands']}/{source['brandCount']}개 브랜드",
            "affected_pct": rounded(sku_finding["evidence"]["affectedSharePct"]),
            "impact": sku_finding["impact"],
            "recommendation": sku_finding["recommendation"],
        },
        {
            "severity": "High",
            "severity_rank": 3,
            "issue": "다년 달력월 합산으로 최고월 왜곡",
            "affected": f"{season_finding['evidence']['brandsWithDifferentPeakMonth']}/{source['brandCount']}개 브랜드",
            "affected_pct": rounded(season_finding["evidence"]["affectedSharePct"]),
            "impact": season_finding["impact"],
            "recommendation": season_finding["recommendation"],
        },
        {
            "severity": "Medium",
            "severity_rank": 2,
            "issue": "부분월과 성장률의 반영 범위 차이",
            "affected": f"부분월 {len(partial_finding['evidence']['partialMonths'])}/{source['monthCount']}개월",
            "affected_pct": rounded(100 * len(partial_finding["evidence"]["partialMonths"]) / source["monthCount"]),
            "impact": partial_finding["impact"],
            "recommendation": partial_finding["recommendation"],
        },
        {
            "severity": "Medium",
            "severity_rank": 2,
            "issue": "미분류 카테고리 잔존",
            "affected": f"{mapping_finding['evidence']['uncategorizedRows']}/{source['summaryRows']}행",
            "affected_pct": rounded(100 * mapping_finding["evidence"]["uncategorizedRows"] / source["summaryRows"]),
            "impact": mapping_finding["impact"],
            "recommendation": mapping_finding["recommendation"],
        },
    ]

    check_rows = []
    for item in result["checks"]:
        check_rows.append(
            {
                "check": item["id"],
                "status": "PASS" if item["passed"] else "FAIL",
                "status_rank": 1 if item["passed"] else 2,
                "evidence": json.dumps(item["evidence"], ensure_ascii=False, separators=(",", ":"))[:280],
            }
        )

    sql_queries = {
        "issues_sql": "SELECT severity, severity_rank, issue, affected, affected_pct, impact, recommendation FROM issues ORDER BY severity_rank DESC, affected_pct DESC",
        "sku_share_sql": "SELECT brand, series, share_pct, sku_count, true_top1_share_pct, ui_top1_share_pct FROM sku_share_chart ORDER BY rowid",
        "sku_examples_sql": "SELECT brand, skuCount, brandAmount, topFiveAmount, trueTopFiveSharePct, uiTopFiveSharePct, trueTopOneSharePct, uiTopOneSharePct, topOneOverstatementPp FROM sku_examples ORDER BY topOneOverstatementPp DESC",
        "peak_examples_sql": "SELECT brand, uiPeakMonth, uiPeakAmount, normalizedPeakMonth, normalizedPeakAverageAmount FROM peak_examples ORDER BY uiPeakAmount DESC",
        "checks_sql": "SELECT status, status_rank, [check], evidence FROM checks ORDER BY status_rank DESC, [check] ASC",
    }
    issue_rows = materialize_via_sql(issue_rows, "issues", sql_queries["issues_sql"])
    sku_share_chart = materialize_via_sql(sku_share_chart, "sku_share_chart", sql_queries["sku_share_sql"])
    sku_examples = materialize_via_sql(sku_examples, "sku_examples", sql_queries["sku_examples_sql"])
    peak_examples = materialize_via_sql(peak_examples, "peak_examples", sql_queries["peak_examples_sql"])
    check_rows = materialize_via_sql(check_rows, "checks", sql_queries["checks_sql"])

    sql_source_specs = {
        "issues_sql": ("정합성 이슈 요약 SQL", "issues", "검증 이슈를 심각도와 영향률 순으로 조회합니다."),
        "sku_share_sql": ("SKU 집중도 비교 SQL", "sku_share_chart", "화면 표시 비중과 브랜드 전체 기준 실제 Top 5 비중을 조회합니다."),
        "sku_examples_sql": ("SKU 집중도 사례 SQL", "sku_examples", "Top 1 과대 표시 폭이 큰 브랜드를 조회합니다."),
        "peak_examples_sql": ("최고월 왜곡 사례 SQL", "peak_examples", "다년 달력월 합산과 완료월 연평균의 최고월이 다른 브랜드를 조회합니다."),
        "checks_sql": ("전체 검증 결과 SQL", "checks", "전체 백테스트 검증 결과를 실패 우선으로 조회합니다."),
    }
    sql_sources = [
        {
            "id": source_key,
            "label": label,
            "query": {
                "engine": "sqlite",
                "language": "sql",
                "sql": sql_queries[source_key],
                "description": description,
                "executed_at": result["generatedAt"],
                "tables_used": [table_name],
                "filters": [f"분석 기간: {source['analysisOptions']['start_date']} ~ {source['analysisOptions']['end_date']}"],
                "metric_definitions": ["비중은 매출액 기준이며 percentage-point 값으로 저장됩니다."],
            },
        }
        for source_key, (label, table_name, description) in sql_source_specs.items()
    ]

    report_metrics = [
        {
            "brand_count": source["brandCount"],
            "checks_passed": check_summary["passed"],
            "checks_total": check_summary["total"],
            "high_findings": finding_summary["high"],
            "medium_findings": finding_summary["medium"],
            "summary_rows": source["summaryRows"],
            "monthly_rows": source["monthlyRows"],
            "period_months": source["monthCount"],
            "complete_months": source["completeMonthCount"],
        }
    ]

    generated_at = result["generatedAt"]
    title = "브랜드 탭 데이터 정합성 백테스트"
    period = f"{source['analysisOptions']['start_date']} ~ {source['analysisOptions']['end_date']}"
    partial_amount_pct = rounded(partial_finding["evidence"]["partialAmountSharePct"], 2)
    unmapped_amount_pct = rounded(100 * mapping_finding["evidence"]["uncategorizedAmount"] / metrics["summaryAmount"], 3)

    manifest = {
        "version": 1,
        "surface": "report",
        "title": title,
        "description": "브랜드 탭 전체 지표의 원천 큐브 대조, 산식 재계산, 범위·매핑 품질 검토 결과입니다.",
        "generatedAt": generated_at,
        "cards": [],
        "charts": [
            {
                "id": "sku_share_gap_chart",
                "title": "SKU 집중도: 화면 표시와 실제 Top 5 비중",
                "subtitle": "오차가 큰 대표 10개 브랜드 · 선택 기간 매출 기준, 단위 %",
                "type": "bar",
                "dataset": "sku_share_chart",
                "sourceId": "sku_share_sql",
                "valueFormat": "number",
                "encodings": {
                    "x": {"field": "brand", "type": "nominal", "label": "브랜드"},
                    "y": {"field": "share_pct", "type": "quantitative", "label": "매출 비중 (%)"},
                    "color": {"field": "series", "type": "nominal", "label": "산식"},
                    "tooltip": [
                        {"field": "sku_count", "type": "quantitative", "label": "SKU 수"},
                        {"field": "true_top1_share_pct", "type": "quantitative", "label": "실제 Top 1 비중"},
                        {"field": "ui_top1_share_pct", "type": "quantitative", "label": "화면 Top 1 비중"},
                    ],
                },
                "options": {"grouping": "grouped", "legend": {"show": True}},
            }
        ],
        "tables": [
            {
                "id": "issues_table",
                "title": "정합성 이슈 요약",
                "subtitle": "영향도와 조치 우선순위 기준",
                "dataset": "issues",
                "sourceId": "issues_sql",
                "defaultSort": {"field": "affected_pct", "direction": "desc"},
                "columns": [
                    {"field": "severity", "label": "심각도", "type": "text"},
                    {"field": "issue", "label": "이슈", "type": "text"},
                    {"field": "affected", "label": "영향 범위", "type": "text"},
                    {"field": "affected_pct", "label": "영향 비율", "format": "number", "unit": "%"},
                ],
            },
            {
                "id": "sku_examples_table",
                "title": "SKU 집중도 과대 표시 사례",
                "subtitle": "Top 1 비중 오차가 큰 10개 브랜드, 단위 %·%p",
                "dataset": "sku_examples",
                "sourceId": "sku_examples_sql",
                "defaultSort": {"field": "topOneOverstatementPp", "direction": "desc"},
                "columns": [
                    {"field": "brand", "label": "브랜드", "type": "text"},
                    {"field": "skuCount", "label": "SKU 수", "format": "number"},
                    {"field": "trueTopFiveSharePct", "label": "실제 Top 5 비중", "format": "number", "unit": "%"},
                    {"field": "trueTopOneSharePct", "label": "실제 Top 1", "format": "number", "unit": "%"},
                    {"field": "uiTopOneSharePct", "label": "화면 Top 1", "format": "number", "unit": "%"},
                    {"field": "topOneOverstatementPp", "label": "Top 1 과대 표시", "format": "number", "unit": "%p"},
                ],
            },
            {
                "id": "peak_examples_table",
                "title": "다년 합산으로 최고월이 달라지는 브랜드",
                "subtitle": "현재 화면 합산값과 완료월 연평균 기준 비교",
                "dataset": "peak_examples",
                "sourceId": "peak_examples_sql",
                "defaultSort": {"field": "uiPeakAmount", "direction": "desc"},
                "columns": [
                    {"field": "brand", "label": "브랜드", "type": "text"},
                    {"field": "uiPeakMonth", "label": "화면 최고월", "format": "number", "unit": "월"},
                    {"field": "uiPeakAmount", "label": "화면 합산 매출", "format": "number", "unit": "EUR"},
                    {"field": "normalizedPeakMonth", "label": "완료월 평균 최고월", "format": "number", "unit": "월"},
                    {"field": "normalizedPeakAverageAmount", "label": "완료월 평균 매출", "format": "number", "unit": "EUR"},
                ],
            },
            {
                "id": "checks_table",
                "title": "전체 검증 결과",
                "subtitle": "원천 합계·키 유일성·브랜드별 대조·분모·성장월 검증",
                "dataset": "checks",
                "sourceId": "checks_sql",
                "defaultSort": {"field": "check", "direction": "asc"},
                "columns": [
                    {"field": "status", "label": "결과", "type": "text"},
                    {"field": "check", "label": "검증 항목", "type": "text"},
                ],
            },
        ],
        "sources": [source_entry, *sql_sources],
        "blocks": [
            {"id": "title", "type": "markdown", "body": f"# {title}"},
            {
                "id": "executive_summary",
                "type": "markdown",
                "sourceId": source_id,
                "body": (
                    "## Executive Summary\n\n"
                    f"- **원천 판매 큐브는 일치합니다.** {source['summaryRows']:,}개 요약행과 {source['monthlyRows']:,}개 월별행의 매출·수량 합계, 브랜드별 합계, SKU 집합, 월 커버리지, 키 유일성이 모두 대조됐습니다.\n"
                    f"- **SKU 집중도는 수정 전 의사결정에 사용하면 안 됩니다.** {sku_finding['evidence']['affectedBrands']}/{source['brandCount']}개 브랜드({rounded(sku_finding['evidence']['affectedSharePct'])}%)에서 상위 5개 합계를 분모로 사용해 집중도를 과대 표시합니다.\n"
                    f"- **월별 추이 비교도 장기 범위에서 보정이 필요합니다.** 서로 다른 연도의 같은 달을 합산하고 부분월까지 포함해 {season_finding['evidence']['brandsWithDifferentPeakMonth']}개 브랜드의 최고월이 완료월 연평균 기준과 달랐습니다.\n"
                    f"- **운영 가능하되 두 High 이슈를 먼저 수정해야 합니다.** 그 외 부분월 범위 차이와 미분류 카테고리는 Medium 이슈로 관리할 수 있습니다."
                ),
            },
            {
                "id": "high_findings_intro",
                "type": "markdown",
                "sourceId": source_id,
                "body": "## 두 가지 High 이슈가 브랜드 집중도와 최고월 해석을 왜곡합니다\n\n산식 자체의 오류는 SKU 집중도에 집중되어 있고, 장기 월별 비교는 데이터 범위 정규화가 빠져 있습니다. 아래 표는 영향 범위와 우선 조치를 함께 정리합니다.",
            },
            {"id": "issues", "type": "table", "tableId": "issues_table"},
            {
                "id": "sku_denominator_explanation",
                "type": "markdown",
                "sourceId": source_id,
                "body": (
                    "## SKU 집중도는 상위 5개끼리의 구성비로 계산되고 있습니다\n\n"
                    "현재 화면은 먼저 상위 5개 SKU만 남긴 뒤 그 5개의 매출 합계를 분모로 씁니다. 따라서 상위 5개 막대는 항상 약 100%가 되며, 브랜드의 나머지 SKU 매출이 분모에서 사라집니다. "
                    f"예를 들어 조선미녀의 실제 Top 5 비중은 {rounded(next(row for row in sku_examples if row['brand'] == '조선미녀')['trueTopFiveSharePct'])}%지만 화면 합계는 100%입니다. 집중 리스크 판단에는 브랜드 전체 매출을 분모로 써야 합니다."
                ),
            },
            {"id": "sku_share_chart_block", "type": "chart", "chartId": "sku_share_gap_chart"},
            {"id": "sku_examples_block", "type": "table", "tableId": "sku_examples_table"},
            {
                "id": "seasonality_explanation",
                "type": "markdown",
                "sourceId": source_id,
                "body": (
                    "## 장기 월별 비교는 달력월별 관측 횟수 차이를 보정해야 합니다\n\n"
                    f"분석 범위는 {period}의 {source['monthCount']}개월이며 완료월은 {source['completeMonthCount']}개월입니다. 7월은 완료월 관측이 1회인 반면 다른 달은 2회씩 있어 단순 합산 비교가 동등하지 않습니다. "
                    f"완료월만 사용해 달력월별 연평균으로 다시 계산하면 {season_finding['evidence']['brandsWithDifferentPeakMonth']}개 브랜드의 최고월이 바뀝니다."
                ),
            },
            {"id": "peak_examples_block", "type": "table", "tableId": "peak_examples_table"},
            {
                "id": "passed_checks",
                "type": "markdown",
                "sourceId": source_id,
                "body": (
                    "## 원천 합계와 주요 분포 산식은 안정적으로 일치합니다\n\n"
                    f"매출 합계는 {metrics['summaryAmount']:,.2f} EUR, 판매수량은 {metrics['summaryQty']:,}개로 요약·월별 큐브가 일치했습니다. "
                    "브랜드별 매출·수량·SKU 집합, 국가 분포 분모, 제품군 구성비 분모, 점유율 합계, 완료월 성장 비교도 모두 통과했습니다."
                ),
            },
            {"id": "checks_block", "type": "table", "tableId": "checks_table"},
            {
                "id": "medium_findings",
                "type": "markdown",
                "sourceId": source_id,
                "body": (
                    "## 부분월과 미분류 항목은 범위 표시와 모니터링으로 통제할 수 있습니다\n\n"
                    f"부분월은 {len(partial_finding['evidence']['partialMonths'])}개월이며 전체 매출의 {partial_amount_pct}%입니다. 순위·KPI에는 포함되지만 성장률에는 제외되므로 카드와 성장 표의 기준 범위를 분리 표기해야 합니다. "
                    f"미분류 카테고리는 {mapping_finding['evidence']['uncategorizedRows']}행, {mapping_finding['evidence']['uncategorizedAmount']:,.2f} EUR로 전체 매출의 {unmapped_amount_pct}%입니다. 금액 영향은 작지만 매핑률 지표로 계속 감시하는 편이 안전합니다."
                ),
            },
            {
                "id": "recommendations",
                "type": "markdown",
                "sourceId": source_id,
                "body": (
                    "## 권장 수정 순서\n\n"
                    "1. **SKU 집중도 분모 수정:** `selectedSkuRows`가 아니라 선택 브랜드 전체 SKU 매출 합계를 분모로 사용합니다. Top 1·Top 3·Top 5 비중 회귀 테스트를 추가합니다.\n"
                    "2. **월별 비교 의미 분리:** 시계열 추이는 `year_month`를 유지하고, 시즌성은 완료월만 사용한 달력월별 연평균으로 계산합니다.\n"
                    "3. **범위 라벨 명시:** 순위/KPI의 전체 선택 기간과 성장률의 완료월 비교 기간을 각각 표시합니다.\n"
                    "4. **매핑 품질 자동화:** 브랜드·SKU not-null, 국가 매핑, 미분류 카테고리 매출 비중을 배포 전 테스트로 고정합니다."
                ),
            },
            {
                "id": "further_questions",
                "type": "markdown",
                "body": "## Further Questions\n\n- 월별 비교의 제품 의도는 연속 시계열 추이인가요, 반복 시즌성인가요?\n- 부분월을 브랜드 순위와 점유율에 포함하는 것이 운영 기준과 일치하나요?\n- 미분류 카테고리 허용 임계치를 행 기준과 매출 기준 중 어느 쪽으로 관리할까요?",
            },
            {
                "id": "caveats",
                "type": "markdown",
                "sourceId": source_id,
                "body": (
                    "## Caveats and Assumptions\n\n"
                    "- 결과는 로컬 최신 분석 API의 저장 스냅샷을 기준으로 하며 실시간 원천 DB 직접 조회는 아닙니다.\n"
                    "- 브랜드 표시명 충돌, 음수 매출/수량, 중복 집계 키, 미상 국가는 이번 스냅샷에서 발견되지 않았습니다.\n"
                    "- 환율은 화면 표시용이며 본 검증의 집계·비중 산식에는 영향을 주지 않습니다."
                ),
            },
        ],
    }

    artifact = {
        "surface": "report",
        "manifest": manifest,
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "ready",
            "datasets": {
                "report_metrics": report_metrics,
                "issues": issue_rows,
                "sku_share_chart": sku_share_chart,
                "sku_examples": sku_examples,
                "peak_examples": peak_examples,
                "checks": check_rows,
            },
        },
        "sources": [source_entry, *sql_sources],
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    build_notebook(result)
    build_report_artifact(result)
    print(json.dumps({"artifact": str(ARTIFACT_PATH), "notebook": str(NOTEBOOK_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
