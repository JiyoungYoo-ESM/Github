import type {
  CrossMatrixData,
  CrossMetric,
  CrossScale
} from "../../../../lib/cross-analysis-matrix.ts";
import type { CrossShareAllocation } from "../../../../lib/cross-analysis-share.ts";
import { formatNumber } from "../../../../lib/utils.ts";
import { escapeReportHtml, injectReportWatermark } from "../../lib/report-html.ts";
import { GROWTH_DISPLAY_CAP } from "../../lib/yoy-comparison.ts";
import { formatCrossAmountK } from "../../lib/currency-format.ts";
import { buildCrossSummaryCards } from "./crossAnalysisSummaryModel.ts";

type CrossAnalysisReportDocumentOptions = {
  generatedAt: string;
  fileDate: string;
  selectedAxisLabel: string;
  metric: CrossMetric;
  scale: CrossScale;
  matrix: CrossMatrixData;
  shareAllocation: CrossShareAllocation;
  eurKrwRate?: number | null;
  momHasCoverageIssue: boolean;
  momCoverageWarningMessage: string;
  yoyCoverageWarningMessage: string;
  dataScopeWarning: string;
};

// design-token-audit: report-template-start — standalone print document with its own embedded palette
export function buildCrossAnalysisReportHtml({
  generatedAt,
  fileDate,
  selectedAxisLabel,
  metric,
  scale,
  matrix: filterOptions,
  shareAllocation: crossShareAllocation,
  eurKrwRate,
  momHasCoverageIssue,
  momCoverageWarningMessage,
  yoyCoverageWarningMessage,
  dataScopeWarning: crossDataScopeWarning
}: CrossAnalysisReportDocumentOptions) {
  const crossMetricLabel =
    metric === "sales"
      ? "매출액"
      : metric === "quantity"
        ? "판매량"
        : metric === "mom"
          ? "MoM 성장률"
          : "완료월 누계 (YTD YoY)";
  const crossScaleLabel =
    scale === "share" && metric !== "yoy" && metric !== "mom" ? "비중" : "금액";
  const summaryCards = buildCrossSummaryCards({
    selected: filterOptions,
    metric,
    scale,
    shareAllocation: crossShareAllocation,
    eurKrwRate
  });

  const values = filterOptions.values;
  const isGrowthMetric = metric === "yoy" || metric === "mom";
  const numericValues = values.flat().filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const rowTotals = values.map((row, rowIndex) => {
    const numericRow = row.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
    if (isGrowthMetric) {
      return filterOptions.growthRowTotals[rowIndex] ?? null;
    }
    return numericRow.reduce((sum, value) => sum + value, 0);
  });
  const max = Math.max(...numericValues.map((value) => (isGrowthMetric ? Math.min(Math.abs(value), GROWTH_DISPLAY_CAP) : Math.abs(value))), 1);
  const displayValue = (value: number | null, shareValue: number | null = null) => {
    if (value === null) return "-";
    if (isGrowthMetric) {
      if (value > GROWTH_DISPLAY_CAP) return `>+${formatNumber(GROWTH_DISPLAY_CAP)}%`;
      return `${value > 0 ? "+" : ""}${value.toFixed(0)}%`;
    }
    if (scale === "share") {
      return crossShareAllocation.calculable && shareValue !== null
        ? `${shareValue.toFixed(1)}%`
        : "-";
    }
    return metric === "quantity" ? `${value.toFixed(1)}만` : formatCrossAmountK(value);
  };
  return injectReportWatermark(`<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>교차분석 리포트 ${escapeReportHtml(fileDate)}</title>
  <style>
    @page { size: A4 landscape; margin: 12mm; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #f3f4f6; color: #05060a; font-family: Arial, "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; }
    .page { padding: 24px; }
    .header { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; margin-bottom: 18px; }
    .eyebrow { font-size: 11px; font-weight: 900; color: #e90035; letter-spacing: .02em; }
    h1 { margin: 4px 0 8px; font-size: 24px; line-height: 1.15; }
    .desc, .muted { color: #69707f; font-weight: 700; }
    .desc { font-size: 12px; }
    .date { font-size: 11px; text-align: right; }
    .metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 14px; }
    .metric, .section { background: #fff; border: 1px solid #e2e4e8; border-radius: 14px; box-shadow: 0 6px 16px rgba(15, 23, 42, .06); }
    .metric { padding: 16px 18px; min-height: 82px; }
    .summary-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px; }
    .summary-card { min-height: 78px; padding: 12px 14px; background: #fff; border: 1px solid #e2e4e8; border-radius: 12px; box-shadow: 0 5px 14px rgba(15, 23, 42, .05); }
    .summary-label { color: #69707f; font-size: 10px; font-weight: 800; }
    .summary-value { margin-top: 7px; font-size: 17px; line-height: 1; font-weight: 950; }
    .summary-sub { margin-top: 7px; color: #69707f; font-size: 10px; line-height: 1.35; font-weight: 700; }
    .label { color: #69707f; font-size: 11px; font-weight: 800; }
    .value { margin-top: 10px; font-size: 22px; font-weight: 950; }
    .accent { color: #e90035; }
    .section { overflow: hidden; }
    .section-head { display: flex; justify-content: space-between; gap: 16px; padding: 16px 18px; border-bottom: 1px solid #edf0f3; }
    h2 { margin: 0; font-size: 15px; }
    table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 12px; }
    th, td { border-bottom: 1px solid #fff; padding: 10px 12px; text-align: right; font-weight: 900; }
    th { background: #f7f8fa; color: #69707f; }
    th:first-child, td:first-child { text-align: left; width: 190px; color: #05060a; background: #fff; }
    .total { background: #f7f8fa; color: #05060a; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; padding: 14px 18px; border-bottom: 1px solid #edf0f3; }
    .chip { border: 1px solid #e2e4e8; border-radius: 999px; padding: 5px 11px; font-size: 11px; font-weight: 900; background: #fff; }
    .print-note { margin-top: 16px; color: #69707f; font-size: 10px; font-weight: 700; text-align: right; }
    .warning { margin: 0 18px 14px; border: 1px solid rgb(244 196 204); border-radius: 10px; background: rgb(255 245 247); color: rgb(179 0 36); padding: 10px 12px; font-size: 11px; font-weight: 900; }
    @media print { body { background: #f3f4f6; } .page { padding: 0; } }
  </style>
</head>
<body>
  <main class="page">
    <header class="header">
      <div>
        <div class="eyebrow">분석 · INSIGHT</div>
        <h1>${escapeReportHtml(selectedAxisLabel)} 교차분석</h1>
        <div class="desc">선택한 ${escapeReportHtml(filterOptions.rowLabel)}와 ${escapeReportHtml(filterOptions.columnLabel)} 조합의 ${escapeReportHtml(crossMetricLabel)} 기준 교차표입니다.</div>
      </div>
      <div class="date muted">생성일<br />${escapeReportHtml(generatedAt)}</div>
    </header>
    <section class="metrics">
      <div class="metric"><div class="label">교차 축</div><div class="value accent">${escapeReportHtml(selectedAxisLabel)}</div></div>
      <div class="metric"><div class="label">${escapeReportHtml(filterOptions.rowLabel)}</div><div class="value">${escapeReportHtml(formatNumber(filterOptions.rows.length))}</div></div>
      <div class="metric"><div class="label">${escapeReportHtml(filterOptions.columnLabel)}</div><div class="value">${escapeReportHtml(formatNumber(filterOptions.columns.length))}</div></div>
      <div class="metric"><div class="label">분석 기준</div><div class="value">${escapeReportHtml(crossMetricLabel)}</div></div>
    </section>
    ${summaryCards ? `
    <section class="summary-cards" aria-label="교차분석 요약">
      ${summaryCards.map((card) => `
        <div class="summary-card">
          <div class="summary-label">${escapeReportHtml(card.label)}</div>
          <div class="summary-value">${escapeReportHtml(card.value)}</div>
          <div class="summary-sub">${escapeReportHtml(card.sub)}</div>
        </div>
      `).join("")}
    </section>` : ""}
    <section class="section">
      <div class="section-head"><h2>교차 매트릭스</h2><span class="muted">${escapeReportHtml(crossScaleLabel)} 기준</span></div>
      <div class="chips">
        ${filterOptions.rows.map((item) => `<span class="chip">${escapeReportHtml(filterOptions.rowLabel)} ${escapeReportHtml(item)}</span>`).join("")}
        ${filterOptions.columns.map((item) => `<span class="chip">${escapeReportHtml(filterOptions.columnLabel)} ${escapeReportHtml(item)}</span>`).join("")}
      </div>
      ${momHasCoverageIssue ? `<div class="warning">${escapeReportHtml(`${momCoverageWarningMessage}. 성장률을 계산하지 않고 ‘-’로 표시합니다.`)}</div>` : ""}
      ${yoyCoverageWarningMessage ? `<div class="warning">${escapeReportHtml(yoyCoverageWarningMessage)}</div>` : ""}
      ${crossDataScopeWarning ? `<div class="warning">${escapeReportHtml(crossDataScopeWarning)}</div>` : ""}
      <table>
        <thead>
          <tr>
            <th>${escapeReportHtml(filterOptions.rowLabel)} / ${escapeReportHtml(filterOptions.columnLabel)}</th>
            ${filterOptions.columns.map((column) => `<th>${escapeReportHtml(column)}</th>`).join("")}
            <th class="total">${escapeReportHtml(metric === "yoy" || metric === "mom" ? "합계 성장률" : scale === "share" ? "행 비중" : "합계")}</th>
          </tr>
        </thead>
        <tbody>
          ${filterOptions.rows
            .map((row, rowIndex) => {
              const rowTotal = rowTotals[rowIndex];
              const cells = (values[rowIndex] ?? [])
                .map((value, columnIndex) => {
                  if (value === null) {
                    return `<td style="background:#f7f8fa;color:#69707f">-</td>`;
                  }
                  const shareValue = crossShareAllocation.values[rowIndex]?.[columnIndex] ?? null;
                  const ratio = isGrowthMetric
                    ? Math.min(Math.min(Math.abs(value), GROWTH_DISPLAY_CAP) / max, 1)
                    : scale === "share"
                      ? crossShareAllocation.calculable
                        ? Math.min((shareValue ?? 0) / 100, 1)
                        : 0
                      : value / max;

                  const bg = isGrowthMetric
                    ? value < 0
                      ? `rgba(230, 0, 45, ${0.12 + ratio * 0.48})`
                      : `rgba(22, 163, 74, ${0.1 + ratio * 0.5})`
                    : `rgba(230, 0, 45, ${0.08 + ratio * 0.58})`;
                  return `<td style="background:${bg}">${escapeReportHtml(displayValue(value, shareValue))}</td>`;
                })
                .join("");
              const rowShareTotal = crossShareAllocation.calculable
                ? crossShareAllocation.rowTotals[rowIndex] ?? 0
                : null;
              return `<tr><td>${escapeReportHtml(row)}</td>${cells}<td class="total">${escapeReportHtml(displayValue(rowTotal, rowShareTotal))}</td></tr>`;
            })
            .join("")}
        </tbody>
      </table>
    </section>
    <div class="print-note">Silicon2 SCM · 교차분석 리포트</div>
  </main>
  <script>
    window.addEventListener("load", () => {
      document.title = "cross-analysis-report-${escapeReportHtml(fileDate)}";
      setTimeout(() => {
        window.focus();
        window.print();
      }, 250);
    });
  </script>
</body>
</html>`);
}
// design-token-audit: report-template-end
