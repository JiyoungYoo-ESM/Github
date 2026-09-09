import {
  analysisMonthKeys,
  formatAnalysisMonthLabel,
  nearestAvailableMonth,
  type CrossMomStatus
} from "../../../../lib/cross-analysis-mom.ts";
import { sourceRowsForCrossAxis, type CrossAxis, type CrossMetric } from "../../../../lib/cross-analysis-matrix.ts";
import { monthKeyOf } from "../../../../lib/global-demand-view-model.ts";
import type { IngredientAnalysis, MonthCoverage, SeasonAnalysis } from "../../../../types/api.ts";
import {
  comparableYearWindow,
  latestComparableMonths,
  previousMonthKey,
  shortMonthKeyLabel
} from "../../lib/yoy-comparison.ts";

type AnalysisOptions = Record<string, unknown> | null;

function firstNonEmptyRows(...candidates: Array<Array<Record<string, unknown>> | undefined>) {
  return candidates.find((rows) => rows && rows.length > 0) ?? [];
}

function buildCrossMonthCoverageModel({
  axis,
  season,
  ingredient,
  analysisOptions
}: {
  axis: CrossAxis;
  season: SeasonAnalysis | null;
  ingredient: IngredientAnalysis | null;
  analysisOptions: AnalysisOptions;
}) {
  const coverageEntries = (season?.monthCoverage ?? []).filter(
    (item): item is MonthCoverage => /^\d{4}-\d{2}$/.test(item.month)
  );
  const monthCoverageByKey = new Map(coverageEntries.map((item) => [item.month, item]));

  let observedMonthKeys: string[];
  if (monthCoverageByKey.size > 0) {
    observedMonthKeys = Array.from(monthCoverageByKey.values())
      .filter((item) => item.status !== "missing")
      .map((item) => item.month)
      .sort();
  } else {
    const explicitMonths = (season?.dataMonths ?? []).filter((month) => /^\d{4}-\d{2}$/.test(month));
    if (explicitMonths.length > 0) {
      observedMonthKeys = Array.from(new Set(explicitMonths)).sort();
    } else {
      const fallbackRows = firstNonEmptyRows(
        season?.countrySkuMonthly,
        sourceRowsForCrossAxis(axis, "mom", season, ingredient)
      );
      observedMonthKeys = Array.from(
        new Set(fallbackRows.map(monthKeyOf).filter((month) => /^\d{4}-\d{2}$/.test(month)))
      ).sort();
    }
  }

  const observedMonthSet = new Set(observedMonthKeys);
  const partialMonthSet = new Set(
    coverageEntries.filter((item) => item.status === "partial").map((item) => item.month)
  );
  const completeMonthKeys = monthCoverageByKey.size > 0
    ? coverageEntries.filter((item) => item.status === "complete").map((item) => item.month).sort()
    : observedMonthKeys;
  const expectedMonths = analysisMonthKeys(
    String(analysisOptions?.start_date ?? ""),
    String(analysisOptions?.end_date ?? ""),
    analysisOptions?.exclude_partial_months !== false
  );
  const momMonthOptions = expectedMonths.length > 0 ? expectedMonths : observedMonthKeys;

  return {
    monthCoverageByKey,
    observedMonthKeys,
    observedMonthSet,
    partialMonthSet,
    completeMonthKeys,
    momMonthOptions
  };
}

function resolveMomPeriodDefaults({
  currentMonth,
  monthOptions,
  completeMonths
}: {
  currentMonth: string;
  monthOptions: string[];
  completeMonths: string[];
}) {
  if (monthOptions.length === 0) return { currentMonth: "", comparisonMonth: "" };

  const availableInRange = completeMonths.filter((month) => monthOptions.includes(month));
  const defaultCurrent = availableInRange.at(-1) ?? monthOptions.at(-1) ?? "";
  const resolvedCurrent = currentMonth && monthOptions.includes(currentMonth) ? currentMonth : defaultCurrent;
  const calendarPrevious = previousMonthKey(resolvedCurrent);
  const fallbackComparison =
    (monthOptions.includes(calendarPrevious) ? calendarPrevious : "") ||
    [...availableInRange].reverse().find((month) => month !== resolvedCurrent) ||
    [...monthOptions].reverse().find((month) => month !== resolvedCurrent) ||
    "";

  return {
    currentMonth: resolvedCurrent,
    comparisonMonth: calendarPrevious || fallbackComparison
  };
}

function buildMomCoverageModel({
  metric,
  currentMonth,
  comparisonMonth,
  observedMonths,
  partialMonths,
  completeMonths,
  coverageByMonth
}: {
  metric: CrossMetric;
  currentMonth: string;
  comparisonMonth: string;
  observedMonths: ReadonlySet<string>;
  partialMonths: ReadonlySet<string>;
  completeMonths: string[];
  coverageByMonth: ReadonlyMap<string, MonthCoverage>;
}) {
  const periodReady = Boolean(currentMonth && comparisonMonth);
  const currentMonthAvailable = Boolean(currentMonth && observedMonths.has(currentMonth));
  const comparisonMonthAvailable = Boolean(comparisonMonth && observedMonths.has(comparisonMonth));
  const currentMonthPartial = Boolean(currentMonth && partialMonths.has(currentMonth));
  const comparisonMonthPartial = Boolean(comparisonMonth && partialMonths.has(comparisonMonth));
  const hasMissingMonth =
    metric === "mom" && periodReady && (!currentMonthAvailable || !comparisonMonthAvailable);
  const hasPartialMonth =
    metric === "mom" && periodReady && (currentMonthPartial || comparisonMonthPartial);

  const missingMonthLabels = [
    !currentMonthAvailable && currentMonth ? formatAnalysisMonthLabel(currentMonth) : "",
    !comparisonMonthAvailable && comparisonMonth ? formatAnalysisMonthLabel(comparisonMonth) : ""
  ].filter(Boolean);
  const partialMonthDetails = [currentMonthPartial ? currentMonth : "", comparisonMonthPartial ? comparisonMonth : ""]
    .filter(Boolean)
    .map((month) => {
      const coverage = coverageByMonth.get(month);
      if (!coverage) return formatAnalysisMonthLabel(month);
      const activity =
        typeof coverage.activeDays === "number" && typeof coverage.expectedBusinessDays === "number"
          ? `활동일 ${coverage.activeDays}/${coverage.expectedBusinessDays}일`
          : "";
      return `${formatAnalysisMonthLabel(month)}${coverage.reason ? ` · ${coverage.reason}` : ""}${activity ? ` · ${activity}` : ""}`;
    });
  const warningMessage = [
    missingMonthLabels.length > 0 ? `${missingMonthLabels.join(", ")} 데이터 없음` : "",
    partialMonthDetails.length > 0 ? `${partialMonthDetails.join(" / ")} (부분 적재 의심)` : ""
  ]
    .filter(Boolean)
    .join(" · ");

  const currentMonthUsable = currentMonthAvailable && !currentMonthPartial;
  const comparisonMonthUsable = comparisonMonthAvailable && !comparisonMonthPartial;
  const nearestCurrentMonth = !currentMonthUsable
    ? nearestAvailableMonth(currentMonth, completeMonths, comparisonMonth)
    : currentMonth;
  const nearestComparisonMonth = !comparisonMonthUsable
    ? nearestAvailableMonth(comparisonMonth, completeMonths, nearestCurrentMonth)
    : comparisonMonth;

  return {
    periodReady,
    hasMissingMonth,
    hasPartialMonth,
    hasCoverageIssue: hasMissingMonth || hasPartialMonth,
    warningMessage,
    currentMonthUsable,
    comparisonMonthUsable,
    nearestCurrentMonth,
    nearestComparisonMonth,
    nearestUsableMonth: !currentMonthUsable
      ? nearestCurrentMonth
      : !comparisonMonthUsable
        ? nearestComparisonMonth
        : ""
  };
}

function buildYoyCoverageWarning(metric: CrossMetric, statuses: Array<Array<CrossMomStatus | null>>) {
  if (metric !== "yoy") return "";
  const statusSet = new Set(statuses.flat().filter(Boolean));
  if (statusSet.has("current_month_missing") || statusSet.has("comparison_month_missing")) {
    return "YTD 기준 연도 또는 비교 연도의 누계 월 데이터가 누락되어 성장률을 계산하지 않습니다.";
  }
  if (statusSet.has("current_month_partial") || statusSet.has("comparison_month_partial")) {
    return "YTD 기준 연도 또는 비교 연도에 부분 적재 의심 월이 있어 성장률을 계산하지 않습니다.";
  }
  return "";
}

function buildCrossGrowthBasisLabel({
  metric,
  sourceRows,
  momCurrentMonth,
  momComparisonMonth,
  yoyMonthRange
}: {
  metric: CrossMetric;
  sourceRows: Array<Record<string, unknown>>;
  momCurrentMonth: string;
  momComparisonMonth: string;
  yoyMonthRange: [number, number] | null;
}) {
  if (metric !== "yoy" && metric !== "mom") return "";
  if (metric === "mom") {
    const months: [string, string] | null = momCurrentMonth && momComparisonMonth
      ? [momCurrentMonth, momComparisonMonth]
      : latestComparableMonths(sourceRows);
    if (!months) return "";
    return `${shortMonthKeyLabel(months[0], months[1])} vs ${shortMonthKeyLabel(months[1], months[0])}`;
  }

  const window = comparableYearWindow(sourceRows);
  if (!window) return "";
  const selectedMonths = yoyMonthRange
    ? Array.from({ length: yoyMonthRange[1] - yoyMonthRange[0] + 1 }, (_, index) => yoyMonthRange[0] + index)
    : Array.from(window.months ?? []).sort((left, right) => left - right);
  const firstMonth = selectedMonths[0];
  const lastMonth = selectedMonths.at(-1);
  const monthLabel = firstMonth && lastMonth
    ? firstMonth === lastMonth
      ? `${firstMonth}월`
      : `${firstMonth}~${lastMonth}월`
    : "";
  return `${window.latestYear}년 ${monthLabel} vs ${window.previousYear}년 ${monthLabel}`.trim();
}

export {
  buildCrossGrowthBasisLabel,
  buildCrossMonthCoverageModel,
  buildMomCoverageModel,
  buildYoyCoverageWarning,
  resolveMomPeriodDefaults
};
