import type {
  CrossAxis,
  CrossMatrixData,
  CrossMetric,
  CrossScale
} from "../../../../lib/cross-analysis-matrix.ts";
import type { CrossMomStatus } from "../../../../lib/cross-analysis-mom.ts";
import type { CrossShareAllocation } from "../../../../lib/cross-analysis-share.ts";
import { formatNumber } from "../../../../lib/utils.ts";
import type { ReportBlock } from "../../lib/types.ts";
import { krwEokFromEur, formatCrossAmountK } from "../../lib/currency-format.ts";
import {
  reportAnalysisPeriodParams,
  reportBrandRole,
  stableShortHash
} from "../../lib/workspace-format.ts";

export type CrossAnalysisReportModelOptions = {
  axis: CrossAxis;
  flipped: boolean;
  metric: CrossMetric;
  scale: CrossScale;
  monthComparisonMode: "mom";
  momCurrentMonth: string;
  momComparisonMonth: string;
  yoyComparisonMode: "ytd";
  yoyMonthRange: [number, number] | null;
  selectedRows: string[];
  selectedColumns: string[];
  selectedAxisLabel: string;
  growthBasisLabel: string;
  momHasMissingMonth: boolean;
  momHasPartialMonth: boolean;
  momHasCoverageIssue: boolean;
  momCoverageWarningMessage: string;
  yoyCoverageWarningMessage: string;
  dataScopeWarning: string;
  averageEurKrwRate: number | null;
  analysisOptions: Record<string, unknown> | null;
  matrix: CrossMatrixData;
  shareAllocation: CrossShareAllocation;
};

function crossCellStatusLabel(status: CrossMomStatus | null) {
  switch (status) {
    case "ok":
      return "정상";
    case "same_period":
      return "동일 기간 선택";
    case "current_month_missing":
      return "기준 기간 데이터 없음";
    case "comparison_month_missing":
      return "비교 기간 데이터 없음";
    case "current_month_partial":
      return "기준 기간 부분 적재 의심";
    case "comparison_month_partial":
      return "비교 기간 부분 적재 의심";
    case "zero_base":
      return "비교월 실적 0";
    case "low_base":
      return "비교 기준 미달";
    default:
      return "";
  }
}

function buildCrossSnapshotRows({
  metric,
  scale,
  averageEurKrwRate,
  matrix,
  shareAllocation
}: Pick<
  CrossAnalysisReportModelOptions,
  "metric" | "scale" | "averageEurKrwRate" | "matrix" | "shareAllocation"
>) {
  return matrix.rows.flatMap((rowLabel, rowIndex) => {
    const rowValues = matrix.values[rowIndex] ?? [];
    return matrix.columns.map((columnLabel, columnIndex) => {
      const value = rowValues[columnIndex];
      const allocatedShare = shareAllocation.values[rowIndex]?.[columnIndex];
      const shareValue =
        metric !== "yoy" &&
        metric !== "mom" &&
        shareAllocation.calculable &&
        typeof allocatedShare === "number"
          ? allocatedShare
          : null;
      const displayedValue =
        value === null || value === undefined
          ? "-"
          : metric === "yoy" || metric === "mom"
            ? `${value > 0 ? "+" : ""}${value}%`
            : scale === "share"
              ? shareValue !== null
                ? `${formatNumber(shareValue, 1)}%`
                : "-"
              : metric === "quantity"
                ? `${formatNumber(value, 1)}만`
                : formatCrossAmountK(value);
      const krwDisplay =
        metric === "sales" && scale !== "share" && typeof value === "number" && value > 0
          ? krwEokFromEur(value * 1_000, averageEurKrwRate)
          : "";

      return {
        [matrix.rowLabel]: rowLabel,
        [matrix.columnLabel]: columnLabel,
        값: value,
        표시값: displayedValue,
        원화표시: krwDisplay,
        점유율: shareValue !== null ? `${formatNumber(shareValue, 1)}%` : "",
        상태:
          metric === "mom" || metric === "yoy"
            ? crossCellStatusLabel(matrix.cellStatuses[rowIndex]?.[columnIndex] ?? null)
            : "",
        metric,
        scale,
        brand_role:
          matrix.rowLabel === "브랜드"
            ? reportBrandRole(rowLabel)
            : matrix.columnLabel === "브랜드"
              ? reportBrandRole(columnLabel)
              : undefined
      };
    });
  });
}

export function buildCrossAnalysisReportModel(options: CrossAnalysisReportModelOptions) {
  const {
    axis,
    flipped,
    metric,
    scale,
    monthComparisonMode,
    momCurrentMonth,
    momComparisonMonth,
    yoyComparisonMode,
    yoyMonthRange,
    selectedRows,
    selectedColumns,
    selectedAxisLabel,
    growthBasisLabel,
    momHasMissingMonth,
    momHasPartialMonth,
    momHasCoverageIssue,
    momCoverageWarningMessage,
    yoyCoverageWarningMessage,
    dataScopeWarning,
    averageEurKrwRate,
    analysisOptions,
    matrix,
    shareAllocation
  } = options;
  const signature = JSON.stringify({
    axis,
    flipped,
    metric,
    scale,
    monthComparisonMode: metric === "mom" ? monthComparisonMode : "",
    momCurrentMonth: metric === "mom" ? momCurrentMonth : "",
    momComparisonMonth: metric === "mom" ? momComparisonMonth : "",
    yoyComparisonMode: metric === "yoy" ? yoyComparisonMode : "",
    yoyMonthRange: metric === "yoy" ? yoyMonthRange : null,
    rows: selectedRows,
    columns: selectedColumns
  });
  const id = `cross:${axis}:${flipped ? "flip" : "norm"}:${metric}:${scale}:${stableShortHash(signature)}`;
  const metricLabel =
    metric === "sales"
      ? "매출액"
      : metric === "quantity"
        ? "판매량"
        : metric === "mom"
          ? "MoM 성장률"
          : "완료월 누계 (YTD YoY)";
  const block: ReportBlock = {
    id,
    title: `${selectedAxisLabel} 교차분석`,
    subtitle: `${selectedRows.join(", ")} × ${selectedColumns.join(", ")}`,
    meta: `${metricLabel}${growthBasisLabel ? ` (${growthBasisLabel})` : ""} · ${
      scale === "share" && metric !== "yoy" && metric !== "mom" ? "비중" : "금액"
    }`,
    type: "cross_matrix",
    kind: "matrix",
    section: "cross",
    size: "full",
    params: {
      axis,
      metric,
      scale,
      mom_current_month: metric === "mom" ? momCurrentMonth : undefined,
      mom_comparison_month: metric === "mom" ? momComparisonMonth : undefined,
      month_comparison_mode: metric === "mom" ? monthComparisonMode : undefined,
      yoy_comparison_mode: metric === "yoy" ? yoyComparisonMode : undefined,
      mom_month_status:
        metric === "mom"
          ? momHasMissingMonth
            ? "month_missing"
            : momHasPartialMonth
              ? "month_partial"
              : "ok"
          : undefined,
      mom_month_warning:
        metric === "mom" && momHasCoverageIssue ? momCoverageWarningMessage : undefined,
      growth_period_warning:
        metric === "yoy" ? yoyCoverageWarningMessage || undefined : undefined,
      data_scope_warning: dataScopeWarning || undefined,
      eur_krw_rate: averageEurKrwRate,
      ...reportAnalysisPeriodParams(analysisOptions),
      rowLabel: matrix.rowLabel,
      columnLabel: matrix.columnLabel
    },
    snapshot: {
      columns: [matrix.rowLabel, matrix.columnLabel, "표시값", "원화표시", "점유율", "상태"],
      rows: buildCrossSnapshotRows(options)
    }
  };

  return {
    block,
    ready:
      selectedRows.length > 0 &&
      selectedColumns.length > 0 &&
      matrix.rows.length > 0 &&
      matrix.columns.length > 0
  };
}

export { buildCrossSnapshotRows, crossCellStatusLabel };
