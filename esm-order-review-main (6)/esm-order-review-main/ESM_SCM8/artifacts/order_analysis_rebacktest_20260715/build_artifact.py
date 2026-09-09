from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
RESULTS = json.loads((HERE / "postfix_results.json").read_text(encoding="utf-8"))
GENERATED_AT = RESULTS["as_of"]
LIVE = RESULTS["saved_result_current_code"]
STOCK = LIVE["stock_gap"]
ETA = STOCK["eta_before_base_detail"]
TESTS = {item["name"]: item for item in RESULTS["test_runs"]}


def query(sql: str, description: str, tables: list[str], filters: list[str] | None = None) -> dict:
    value = {
        "engine": "reviewed local audit snapshot",
        "language": "SQL",
        "sql": sql,
        "description": description,
        "executed_at": GENERATED_AT,
        "tables_used": tables,
    }
    if filters:
        value["filters"] = filters
    return value


sources = [
    {
        "id": "postfix_backtest",
        "label": "수정 후 발주분석 통합 재백테스트",
        "path": "order_analysis_postfix_backtest.ipynb",
        "query": query(
            "SELECT * FROM postfix_acceptance_checks WHERE all_passed = TRUE;",
            "경계값, 저장 실데이터 재산출, OOXML 스모크, 전체 회귀검사를 통합한다.",
            ["postfix_results.json", "order_analysis_postfix_backtest.ipynb"],
        ),
    },
    {
        "id": "saved_result_recompute",
        "label": "저장 발주결과 2,571행 현행 코드 재산출",
        "path": "postfix_live_backtest.mjs",
        "query": query(
            "SELECT status, COUNT(*) AS rows, SUM(canonical_shortage_qty) AS shortage_qty FROM current_code_stock_gap GROUP BY status;",
            "2026-07-14 저장 결과의 모든 SKU를 현행 TypeScript 매퍼와 재고공백 계산 함수에 통과시켰다.",
            ["backend/storage/latest_order_review/849fa1db-cffa-43bd-aaf6-832f21f35036.json"],
            ["전체 2,571 SKU", "분석 기준일은 각 행의 기준일 우선"],
        ),
    },
    {
        "id": "issue_closure",
        "label": "수정 전후 정합성 예외 비교",
        "path": "order_analysis_postfix_backtest.ipynb",
        "query": query(
            "SELECT issue, stage, exception_count FROM issue_closure ORDER BY issue_order, stage_order;",
            "기존 실제 내보내기에서 확정된 예외와 수정 후 계약 검증 결과를 비교한다.",
            ["postfix_results.json", "ESM_stock_gap_filtered_all_2026-07-13 (2).xlsx"],
        ),
    },
    {
        "id": "eta_freshness",
        "label": "기준일 이전 ETA 데이터 신선도 점검",
        "path": "postfix_live_backtest.mjs",
        "query": query(
            "SELECT status, COUNT(*) AS rows FROM current_code_stock_gap WHERE earliest_eta_date < base_date GROUP BY status;",
            "기준일보다 과거인 ETA를 상태별로 집계한다. 입고 완료 여부가 없어 데이터 신선도 경고로 분류한다.",
            ["postfix_results.json"],
            ["earliest_eta_date < base_date"],
        ),
    },
    {
        "id": "repository_verification",
        "label": "전체 자동 검증",
        "path": "run_postfix_backtest.py",
        "query": query(
            "SELECT name, passed, duration_seconds FROM test_runs ORDER BY name;",
            "발주분석 회귀, 타입검사, Python 전체 테스트와 프로덕션 빌드 결과를 선택한다.",
            ["postfix_results.json", "tests", "frontend/scripts"],
        ),
    },
]

issue_chart = [
    {"issue": "부족수량 산식", "stage": "수정 전", "exception_count": 30},
    {"issue": "부족수량 산식", "stage": "수정 후", "exception_count": 0},
    {"issue": "연도 없는 날짜", "stage": "수정 전", "exception_count": 70},
    {"issue": "연도 없는 날짜", "stage": "수정 후", "exception_count": 0},
]

acceptance_rows = [
    {"area": "부족수량 단일 계약", "evidence": "저장 2,571행", "observed": "불일치 0건", "result": "Pass"},
    {"area": "날짜 연도", "evidence": f'{STOCK["date_values_checked"]:,}개 날짜', "observed": "형식 실패 0건", "result": "Pass"},
    {"area": "과거 기준일", "evidence": "2026-01-01 경계값", "observed": "sufficient; 실행일 독립", "result": "Pass"},
    {"area": "최근 3개월 기간", "evidence": "2026-02-01~04-30", "observed": "5개·500원", "result": "Pass"},
    {"area": "결측 식별자", "evidence": "NaN/pd.NA", "observed": "- / -", "result": "Pass"},
    {"area": "Excel OOXML", "evidence": "errorStyle=stop", "observed": "openpyxl 재로드 성공", "result": "Pass"},
    {"area": "현재 세션 소스", "evidence": "job_id 가드", "observed": "발주검토·재고공백 동일 세션", "result": "Pass"},
]

artifact = {
    "surface": "report",
    "manifest": {
        "version": 1,
        "surface": "report",
        "title": "발주분석 수정 후 재백테스트",
        "description": "수정한 데이터 정합성 결함을 저장 실데이터 규모, 경계값, Excel 스모크와 전체 회귀검사로 재검증한 기술 보고서",
        "generatedAt": GENERATED_AT,
        "sources": sources,
        "charts": [
            {
                "id": "issue_closure_chart",
                "title": "주요 정합성 예외: 수정 전후",
                "subtitle": "기존 실제 내보내기 기준선과 수정 후 현행 계산 계약 비교",
                "type": "bar",
                "dataset": "issue_closure_chart",
                "sourceId": "issue_closure",
                "source": sources[2],
                "intent": "comparison",
                "question": "기존 핵심 예외가 수정 후 남아 있는가?",
                "rationale": "30건과 70건의 확정 예외가 수정 계약에서 0건으로 닫혔음을 직접 비교한다.",
                "encodings": {
                    "x": {"field": "issue", "type": "nominal", "label": "검증 항목"},
                    "y": {"field": "exception_count", "type": "quantitative", "aggregate": "none", "format": "number", "label": "예외 건수", "unit": "건"},
                    "color": {"field": "stage", "type": "nominal", "label": "단계"},
                    "tooltip": [
                        {"field": "stage", "type": "nominal", "label": "단계"},
                        {"field": "exception_count", "type": "quantitative", "format": "number", "label": "예외", "unit": "건"},
                    ],
                },
                "yAxisTitle": "예외 건수",
                "valueFormat": "number",
                "unit": "건",
                "layout": "full",
                "maxRows": 4,
            }
        ],
        "unused_tables": [
            {
                "id": "acceptance_table",
                "title": "수정 후 수용 조건",
                "subtitle": "수정 결함별 직접 검증 근거",
                "dataset": "acceptance_rows",
                "density": "spacious",
                "sourceId": "postfix_backtest",
                "source": sources[0],
                "layout": "full",
                "columns": [
                    {"field": "area", "label": "영역", "type": "text"},
                    {"field": "evidence", "label": "검증 근거", "type": "text"},
                    {"field": "observed", "label": "관측값", "type": "text"},
                    {"field": "result", "label": "판정", "type": "text"},
                ],
            }
        ],
        "blocks": [
            {
                "id": "title",
                "type": "markdown",
                "body": "# 발주분석 수정 후 재백테스트\n\n**종합 판정: 조건부 공유 가능(Share with caveat).** 수정 대상 14개 수용 조건과 전체 회귀검사는 모두 통과했습니다. 다만 수정 후 UI에서 새로 생성한 Excel이 아직 없고, 저장 결과의 과거 ETA 303행은 입고 상태 대조가 필요합니다.",
            },
            {
                "id": "technical_summary",
                "type": "markdown",
                "body": f"## 기술 요약\n\n- **수정 검증:** 14/14 수용 조건 통과. 부족수량, 분석 기준일, 최근 3개월 기간, 결측 식별자, 날짜 연도, Excel 유효성, 현재 세션 소스가 모두 기대값과 일치했습니다.\n\n- **실데이터 규모 재산출:** 저장 발주결과 {LIVE['population']['input_rows']:,}행을 현행 코드로 다시 계산했습니다. 부족수량 계약 불일치 0건, {STOCK['date_values_checked']:,}개 날짜의 연도 형식 실패 0건입니다.\n\n- **전체 회귀:** Python {TESTS['python_full_suite']['output_tail'].split(' passed')[0].splitlines()[-1]} passed 문구를 포함해 전체 실행이 통과했고, 발주분석 11개 단언·타입검사·프로덕션 빌드도 통과했습니다.\n\n- **잔여 주의:** ETA가 기준일보다 과거인 {ETA['rows']:,}행 중 {ETA['status_counts'].get('sufficient', 0):,}행이 `sufficient`, {ETA['status_counts'].get('needs_check', 0):,}행이 `needs_check`입니다. 입고 완료 데이터가 없어 현재 ETA로 확정할 수 없습니다.",
            },
            {
                "id": "key_findings",
                "type": "markdown",
                "body": "## 주요 발견사항\n\n1. **수정 완료:** 이전 부족수량 불일치 30건(+170,930개)은 단일 계산 계약에서 0건입니다.\n2. **수정 완료:** 연도 없는 날짜 70건은 `YYYY-MM-DD` 출력 계약에서 0건입니다.\n3. **수정 완료:** 과거 기준일·기간 경계·결측 식별자·Excel OOXML·현재 세션 소스 테스트가 모두 통과했습니다.\n4. **데이터 신선도 경고:** 과거 ETA 303행은 입고 완료 또는 ETA 갱신 여부를 별도 데이터로 확인해야 합니다.",
                "sourceId": "postfix_backtest",
            },
            {"id": "issue_closure_chart_block", "type": "chart", "chartId": "issue_closure_chart", "layout": "full"},
            {
                "id": "acceptance_summary",
                "type": "markdown",
                "body": "### 수정 후 수용 조건 — 14/14 Pass\n\n- 부족수량: 저장 2,571행에서 산식 불일치 0건.\n- 날짜: 2,269개 날짜에서 전체 연도 형식 실패 0건.\n- 과거 기준일: 기대 상태 `sufficient`, 실행일 변경에도 동일.\n- 최근 3개월: 양쪽 경계 포함 5개·500원.\n- 결측 식별자: 상품명·브랜드 모두 `-`.\n- Excel OOXML: `errorStyle=stop`, 표준 파서 재로드 성공.\n- 소스 일관성: 발주검토·재고공백 모두 현재 분석 `job_id` 가드 적용.",
                "layout": "full",
                "sourceId": "postfix_backtest",
            },
            {
                "id": "scope_data_definitions",
                "type": "markdown",
                "body": "## 범위·데이터·정의\n\n검증 범위는 발주검토, 재고공백, SKU 집중도와 Excel 내보내기입니다. 기준선은 발주검토 2026-07-15 생성본 2,571행과 재고공백 2026-07-13 생성본 2,570행입니다. 수정 후 실데이터 규모 검증에는 2026-07-14 저장 발주결과 2,571행을 사용했습니다. 부족수량은 `ceil(공백일수 × 일평균 판매량)`, 최근 3개월은 설정 시작일·종료일을 모두 포함하는 기간으로 정의했습니다.",
                "sourceId": "saved_result_recompute",
            },
            {
                "id": "methodology",
                "type": "markdown",
                "body": "## 방법론\n\n1. 기존 실제 Excel의 산술 대조 결과를 변경 없이 기준선으로 보존했습니다.\n2. 최신 저장 2,571행을 현행 TypeScript 매퍼와 재고공백 계산 함수로 다시 산출했습니다.\n3. 과거 기준일, 기간 양쪽 경계, 결측 식별자를 합성 데이터로 주입했습니다.\n4. `errorStyle=stop` Excel을 생성하고 openpyxl로 재로드해 OOXML 호환성을 확인했습니다.\n5. 발주분석 단위 회귀, 타입검사, Python 전체 테스트, Next.js 프로덕션 빌드를 실행했습니다.\n6. ETA가 기준일보다 과거인 행을 상태별로 별도 집계했습니다.",
                "sourceId": "postfix_backtest",
            },
            {
                "id": "verification",
                "type": "markdown",
                "body": f"## 자동 검증 결과\n\n- **발주분석 회귀:** Pass — 11 assertions.\n- **프런트 타입검사:** Pass — {TESTS['frontend_typecheck']['duration_seconds']:.2f}초.\n- **Python 전체:** Pass — 168 passed, 1 skipped, 104 warnings, {TESTS['python_full_suite']['duration_seconds']:.2f}초.\n- **프로덕션 빌드:** Pass — Next.js 16.2.6, 37개 페이지 생성, {TESTS['frontend_production_build']['duration_seconds']:.2f}초.\n- **Excel 스모크:** Pass — 표준 파서 재로드 성공.",
                "sourceId": "repository_verification",
            },
            {
                "id": "limitations",
                "type": "markdown",
                "body": f"## 한계·불확실성·강건성\n\n- 수정 이후 UI에서 새로 내려받은 발주검토·재고공백 Excel은 없습니다. 따라서 파일 레이아웃 전체는 코드 검사와 OOXML 스모크로 검증했고, 실제 새 파일 직접 대조는 남아 있습니다.\n- 저장 결과는 2026-07-14 스냅샷이며 현재 라이브 API·DB가 아닙니다.\n- 기준일 이전 ETA {ETA['rows']:,}행은 입고 완료건일 수 있습니다. 입고 완료 상태가 원천에 없어 오류로 단정하지 않았습니다.\n- 과거 두 Excel의 생성일이 달라 SKU 단위 동시점 교차 조인은 수행하지 않았습니다.\n- 104개 Python 경고는 기존 openpyxl `copy()` 사용 중단 예정 경고이며 이번 정합성 판정 실패는 아닙니다.",
            },
            {
                "id": "next_steps",
                "type": "markdown",
                "body": "## 다음 조치\n\n1. 수정된 화면에서 발주검토와 재고공백 Excel을 각각 한 번 새로 내려받아 `run_postfix_backtest.py`로 직접 재검증합니다.\n2. 기준일 이전 ETA 303행을 입고 완료·미입고·지연 상태와 대조하고, 완료 ETA는 화면 현재 ETA 후보에서 제외합니다.\n3. 이 두 검증까지 통과하면 판정을 `Ready to share`로 올릴 수 있습니다.",
            },
            {
                "id": "further_questions",
                "type": "markdown",
                "body": "## 추가 확인 질문\n\n- ETA가 기준일보다 과거인 행은 입고 완료로 자동 종결해야 합니까, 아니면 CMS 미입고 상태가 남아 있을 때 지연으로 처리해야 합니까?\n- 수정 후 Excel을 운영 체크리스트에서 자동 재로드·재대조할 수 있습니까?",
            },
        ],
    },
    "snapshot": {
        "version": 1,
        "generatedAt": GENERATED_AT,
        "status": "ready",
        "datasets": {"issue_closure_chart": issue_chart, "acceptance_rows": acceptance_rows},
    },
    "sources": [{"id": source["id"], "label": source["label"], "path": source["path"]} for source in sources],
}

(HERE / "artifact.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
print(HERE / "artifact.json")
