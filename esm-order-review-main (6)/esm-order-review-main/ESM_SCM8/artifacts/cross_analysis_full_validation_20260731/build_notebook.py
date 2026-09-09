from __future__ import annotations

from pathlib import Path

import nbformat as nbf


OUTPUT = Path(__file__).with_name("cross_analysis_full_validation_20260731.ipynb")


def code(source: str):
    return nbf.v4.new_code_cell(source.strip())


def markdown(source: str):
    return nbf.v4.new_markdown_cell(source.strip())


notebook = nbf.v4.new_notebook()
notebook["metadata"]["kernelspec"] = {
    "display_name": "Python 3",
    "language": "python",
    "name": "python3",
}
notebook["metadata"]["language_info"] = {"name": "python", "version": "3"}
notebook["cells"] = [
    markdown(
        """
# 교차분석 완전 정합성 검증

## tl;dr

- H&B/PL 운영 스냅샷의 CMS 원천 24,995행에서 최종 분석 22,098행, `countrySkuSummary` 5,767행, `countrySkuMonthly` 13,039행까지 키·매출·수량 오차가 모두 0이다.
- 국가×브랜드, 국가×SKU, 브랜드×SKU의 정적·MoM·YTD 실제 셀 2,089,098개와 행 성장률 1,722개를 프런트엔드 함수와 독립 집계로 대사했으며 산식 불일치는 0건이다.
- 다만 원천에 안정적인 판매행 ID가 없어 H&B 범위의 중복 후보 63개 초과행, €61,599.03(매출의 0.169412%)이 진짜 중복인지 확정할 수 없다.
- 성장 카드의 최댓값·최솟값 계산은 맞지만, 선택값이 모두 음수 또는 모두 양수일 때 각각 `최대 성장`, `최대 감소`라는 명칭이 의미상 틀리다. 따라서 최종 판정은 **Needs revision**이다.
"""
    ),
    markdown(
        """
## Context & Methods

### Key Assumptions

- 사용자 화면과 일치하는 `hnb_team / PL`, 분석기간 2024-04-01~2024-12-31 운영 스냅샷을 정적 지표와 MoM의 주 검증 대상으로 사용한다.
- 해당 기간에는 전년도 1월부터의 비교창이 없으므로 YTD는 정상 비활성 상태다. YTD 실제 검증에는 같은 PL 원천의 2025년·2026년 완료월이 연속된 운영 스냅샷을 보조 사용한다.
- 비중은 선택 행×열의 순매출 또는 순수량 합계를 분모로 한다. 성장률은 매출액만 사용하며 비교금액 €500 미만은 low-base 처리한다.
- 원천 판매행 ID가 없으므로 완전 일치 행은 자동 삭제하지 않고 중복 후보로만 평가한다.
"""
    ),
    code(
        """
from pathlib import Path
import json
import os
import subprocess
import sys
import pandas as pd
from IPython.display import display

cwd = Path.cwd().resolve()
PROJECT_ROOT = next(
    candidate
    for candidate in [cwd, *cwd.parents]
    if (candidate / "frontend").is_dir() and (candidate / "backend").is_dir()
)
sys.path.insert(0, str(PROJECT_ROOT))
ARTIFACT_DIR = PROJECT_ROOT / "artifacts" / "cross_analysis_full_validation_20260731"
PRIMARY_SNAPSHOT = PROJECT_ROOT / "backend" / "storage" / "latest_season_trend" / "latest_hnb_team__PL.json"
PRIMARY_RAW = PROJECT_ROOT / "backend" / "storage" / "cms_fetch_cache" / "5324936ddbd3a8e212f456a723d3a08eb46df6017c0f74eef32c900b5877e00e.json"
YTD_SNAPSHOT = PROJECT_ROOT / "backend" / "storage" / "latest_season_trend" / "latest_bm3__PL.json"
YTD_RAW = PROJECT_ROOT / "backend" / "storage" / "cms_fetch_cache" / "e552812929b671d2bf424f9be8a9227497e0cdac3fa6dba0910d8313201e9ea8.json"
SOURCE_RESULTS = ARTIFACT_DIR / "source_cube_results.json"
MATRIX_RESULTS = ARTIFACT_DIR / "matrix_results.json"

for required in [PRIMARY_SNAPSHOT, PRIMARY_RAW, YTD_SNAPSHOT, YTD_RAW]:
    assert required.exists(), f"Missing validation input: {required}"
"""
    ),
    markdown("## Data\n\n### 1. 원천 → 집계 큐브 재실행 및 대사"),
    code(
        """
env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}
source_command = [
    str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"),
    str(ARTIFACT_DIR / "source_cube_validation.py"),
    "--snapshot", str(PRIMARY_SNAPSHOT), str(PRIMARY_RAW),
    "--snapshot", str(YTD_SNAPSHOT), str(YTD_RAW),
    "--output", str(SOURCE_RESULTS),
]
source_run = subprocess.run(
    source_command,
    cwd=PROJECT_ROOT,
    env=env,
    capture_output=True,
    text=True,
    check=False,
)
assert source_run.returncode == 0, source_run.stderr or source_run.stdout[-4000:]
source_report = json.loads(SOURCE_RESULTS.read_text(encoding="utf-8"))
assert source_report["status"] == "passed"

source_rows = []
for item in source_report["snapshots"]:
    source_rows.append({
        "기간": " ~ ".join(item["analysisRange"]),
        "원천 판매행": item["sourceRows"]["sales"],
        "최종 판매행": item["pipelineStages"]["finalRows"],
        "정적 큐브 행": item["cubeRows"]["countrySkuSummary"],
        "월 큐브 행": item["cubeRows"]["countrySkuMonthly"],
        "키 불일치": item["summaryReconciliation"]["key_mismatches"] + item["monthlyReconciliation"]["key_mismatches"],
        "매출 불일치": item["summaryReconciliation"]["amount_mismatches"] + item["monthlyReconciliation"]["amount_mismatches"],
        "수량 불일치": item["summaryReconciliation"]["quantity_mismatches"] + item["monthlyReconciliation"]["quantity_mismatches"],
        "중복 후보 매출 비중": item["sourceDuplicateRisk"]["candidateAmountSharePct"],
    })
display(pd.DataFrame(source_rows))
"""
    ),
    markdown("### 2. 세 탭의 프런트엔드 행렬·비중·MoM·YTD 셀 대사"),
    code(
        """
matrix_command = [
    "node",
    "--disable-warning=MODULE_TYPELESS_PACKAGE_JSON",
    "--experimental-strip-types",
    str(ARTIFACT_DIR / "matrix_snapshot_backtest.mjs"),
    str(PRIMARY_SNAPSHOT),
    str(YTD_SNAPSHOT),
    str(MATRIX_RESULTS),
]
matrix_run = subprocess.run(
    matrix_command,
    cwd=PROJECT_ROOT,
    capture_output=True,
    text=True,
    check=False,
)
assert matrix_run.returncode == 0, matrix_run.stderr or matrix_run.stdout[-4000:]
matrix_report = json.loads(MATRIX_RESULTS.read_text(encoding="utf-8"))
assert matrix_report["status"] == "passed"

matrix_summary = pd.DataFrame([
    {"검증": "정적 매출·수량·비중", "실제 셀": matrix_report["static"]["cellsChecked"], "행 합계": 0},
    {"검증": "전월 대비(MoM)", "실제 셀": matrix_report["mom"]["cellsChecked"], "행 합계": matrix_report["mom"]["rowTotalsChecked"]},
    {"검증": "완료월 누계(YTD YoY)", "실제 셀": matrix_report["ytd"]["cellsChecked"], "행 합계": matrix_report["ytd"]["rowTotalsChecked"]},
])
matrix_summary.loc["합계"] = {
    "검증": "합계",
    "실제 셀": int(matrix_summary["실제 셀"].sum()),
    "행 합계": int(matrix_summary["행 합계"].sum()),
}
display(matrix_summary)
"""
    ),
    markdown("### 3. 첨부 화면의 세 SKU를 CMS 집계값으로 역산"),
    code(
        """
from core.season_calendar import AMOUNT_COL, PRODUCT_CODE_COL, PRODUCT_NAME_COL

primary_payload = json.loads(PRIMARY_SNAPSHOT.read_text(encoding="utf-8"))
monthly = pd.DataFrame(primary_payload["season_analysis"]["countrySkuMonthly"])
selected_codes = ["JSMSM03-SREU", "JSMS01-SgEU", "JSMS01-TGEU"]
selected = monthly[
    monthly[PRODUCT_CODE_COL].astype(str).isin(selected_codes)
    & monthly["year_month"].isin(["2024-11", "2024-12"])
]
selected_grouped = (
    selected.groupby([PRODUCT_CODE_COL, PRODUCT_NAME_COL, "year_month"], dropna=False)[AMOUNT_COL]
    .sum()
    .unstack("year_month", fill_value=0)
    .reset_index()
)
selected_grouped["화면 성장률"] = selected_grouped.apply(
    lambda row: round((row["2024-12"] - row["2024-11"]) / row["2024-11"] * 100)
    if row["2024-11"] > 0 else None,
    axis=1,
)
display(selected_grouped)
assert sorted(selected_grouped["화면 성장률"].tolist()) == [-97, -25, 5]
"""
    ),
    markdown(
        """
## Results

### 결정적 정합성

- 두 운영 스냅샷 모두 원천 필터 결과와 정적 큐브·월 큐브의 키, 매출액, 판매량이 오차 0으로 일치했다.
- 월 커버리지 합계도 월 큐브 합계와 일치했다.
- 필수 차원 필드의 null/빈값은 0건이고, 최종 분석 범위에서 한 SKU가 여러 브랜드 또는 여러 상품명으로 분리된 사례는 0건이었다.
- 정적 비중은 양수 합계인 실제 화면에서 반올림 후 정확히 100.0%였다.
- MoM은 H&B 범위의 9개 기준월, YTD는 2026년 완료월 1~6월에 대해 모든 셀과 행 합계가 독립 계산과 일치했다.

### 남은 데이터 품질 위험

- H&B 범위에 완전 일치 중복 후보 63개 초과행, €61,599.03, 전체 분석매출의 0.169412%가 포함되어 있다.
- 25개월 YTD 보조 범위에는 중복 후보 1,234개 초과행, €555,492.00, 0.172363%가 포함되어 있다.
- 두 원천 모두 안정적인 판매행 ID가 없으므로 이 후보를 진짜 중복과 합법적인 동일 라인 반복으로 구분할 수 없다.

### UI 의미 오류

- 성장 카드가 부호를 필터링하지 않고 전체 유효값의 최대·최소를 사용한다.
- 실제 검증 view-cell 기준으로 양수 단일 선택 8,497건은 `최대 감소`에 양수를, 음수 단일 선택 20,621건은 `최대 성장`에 음수를 표시할 수 있다.
- 0% 단일 선택 110건은 두 카드 모두 0%를 표시할 수 있다.
- 이는 산식 오류가 아니라 라벨·상태 모델 오류지만, “모든 경우”의 화면 정합성 기준에서는 수정 대상이다.
"""
    ),
    markdown(
        """
## Takeaways

1. **원천에서 화면 숫자까지의 결정적 계산 경로는 통과**했다. 현재 첨부 화면의 `+5%, -97%, -25%, 33.3%, 100%`도 CMS 월 합계로 재현된다.
2. **완전 무결하다고 승인할 수는 없다.** 판매행 안정 ID 부재로 약 0.17%의 중복 후보를 확정할 수 없고, 성장/감소 카드의 부호 의미가 일부 선택에서 틀린다.
3. 배포 전 최소 수정은 성장 카드를 `양수 중 최대`, `음수 중 최소`로 계산하고 해당 부호가 없으면 `조합 없음`으로 표시하는 것이다.
4. 원천 품질의 완전 확정에는 CMS가 판매행 고유 ID 또는 인보이스 라인 번호를 제공해야 한다.
"""
    ),
]

nbf.write(notebook, OUTPUT)
print(OUTPUT)
