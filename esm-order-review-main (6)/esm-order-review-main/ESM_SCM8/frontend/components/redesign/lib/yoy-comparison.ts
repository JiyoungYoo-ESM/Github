import { amountOf, monthKeyOf } from "../../../lib/global-demand-view-model.ts";
import { lowBaseAmount } from "../../../lib/low-base.ts";
import { formatNumber } from "../../../lib/utils.ts";
import type { ComparableYearWindow, ComparisonBasis } from "./types.ts";

function comparisonMonthKeyOf(row: Record<string, unknown>) {
  const direct = String(row.month_key ?? row.monthKey ?? row.period ?? row.month ?? "").trim();
  return /^\d{4}-\d{2}$/.test(direct) ? direct : monthKeyOf(row);
}

function yearOfRow(row: Record<string, unknown>): number | null {
  const directYear = Number(row.year ?? row["연도"] ?? row.YEAR);
  if (Number.isFinite(directYear) && directYear >= 1900) return directYear;
  const monthKey = comparisonMonthKeyOf(row);
  const match = monthKey.match(/^(\d{4})-/);
  if (!match) return null;
  const year = Number(match[1]);
  return Number.isFinite(year) ? year : null;
}

export function pickComparableYearWindow(monthsByYear: Map<number, Set<number>>): ComparableYearWindow | null {
  const years = Array.from(monthsByYear.keys()).sort((a, b) => b - a);
  if (years.length < 2) return null;
  const latestYear = years[0];
  const previousYear = latestYear - 1;
  if (!years.includes(previousYear)) return null;
  const latestMonths = monthsByYear.get(latestYear) ?? new Set<number>();
  const previousMonths = monthsByYear.get(previousYear) ?? new Set<number>();
  if (latestMonths.size > 0 && previousMonths.size > 0) {
    const commonMonths = new Set(Array.from(latestMonths).filter((month) => previousMonths.has(month)));
    if (commonMonths.size === 0) return null;
    return { latestYear, previousYear, months: commonMonths };
  }
  return { latestYear, previousYear, months: null };
}

export function comparableYearWindow(rows: Array<Record<string, unknown>>): ComparableYearWindow | null {
  const monthsByYear = new Map<number, Set<number>>();
  rows.forEach((row) => {
    const year = yearOfRow(row);
    if (year === null) return;
    const months = monthsByYear.get(year) ?? new Set<number>();
    const monthMatch = comparisonMonthKeyOf(row).match(/^\d{4}-(\d{2})$/);
    if (monthMatch) {
      const month = Number(monthMatch[1]);
      if (month >= 1 && month <= 12) months.add(month);
    }
    monthsByYear.set(year, months);
  });
  return pickComparableYearWindow(monthsByYear);
}

/**
 * 완료월 기준 YTD 비교 창.
 *
 * 최신 연도와 직전 연도에 1월부터 연속으로 모두 존재하는 월까지만 사용한다.
 * 완료월 목록이 전달되면 partial/missing 월은 관측 행이 있어도 비교에서 제외한다.
 */
export function completedYtdComparableYearWindow(
  rows: Array<Record<string, unknown>>,
  completedMonthKeys?: ReadonlySet<string>
): ComparableYearWindow | null {
  const monthsByYear = new Map<number, Set<number>>();
  const observedYears = new Set<number>();
  rows.forEach((row) => {
    const monthKey = comparisonMonthKeyOf(row);
    const matched = monthKey.match(/^(\d{4})-(\d{2})$/);
    if (!matched) return;
    const year = Number(matched[1]);
    const month = Number(matched[2]);
    if (!Number.isFinite(year) || month < 1 || month > 12) return;
    observedYears.add(year);
    if (completedMonthKeys && !completedMonthKeys.has(monthKey)) return;
    const months = monthsByYear.get(year) ?? new Set<number>();
    months.add(month);
    monthsByYear.set(year, months);
  });

  const years = Array.from(observedYears).sort((left, right) => right - left);
  if (years.length < 2) return null;
  const latestYear = years[0];
  const previousYear = latestYear - 1;
  const latestMonths = monthsByYear.get(latestYear);
  const previousMonths = monthsByYear.get(previousYear);
  if (!latestMonths || !previousMonths) return null;

  let latestCompleteMonth = 0;
  for (let month = 1; month <= 12; month += 1) {
    if (!latestMonths.has(month) || !previousMonths.has(month)) break;
    latestCompleteMonth = month;
  }
  if (latestCompleteMonth === 0) return null;
  return {
    latestYear,
    previousYear,
    months: new Set(Array.from({ length: latestCompleteMonth }, (_, index) => index + 1))
  };
}

export function latestComparableYears(rows: Array<Record<string, unknown>>): [number, number] | null {
  const window = comparableYearWindow(rows);
  return window ? [window.latestYear, window.previousYear] : null;
}

export function yoyBucketOf(row: Record<string, unknown>, window: ComparableYearWindow): "current" | "previous" | null {
  const year = yearOfRow(row);
  if (year !== window.latestYear && year !== window.previousYear) return null;
  if (!window.months) return year === window.latestYear ? "current" : "previous";
  const monthMatch = comparisonMonthKeyOf(row).match(/^\d{4}-(\d{2})$/);
  if (!monthMatch) return null;
  if (!window.months.has(Number(monthMatch[1]))) return null;
  return year === window.latestYear ? "current" : "previous";
}

export function yoyWindowRangeLabel(window: ComparableYearWindow) {
  if (!window.months || window.months.size >= 12) return "";
  const months = Array.from(window.months).sort((a, b) => a - b);
  const first = months[0];
  const last = months[months.length - 1];
  return first === last ? ` ${first}월` : ` ${first}~${last}월`;
}

export function compactYoyPeriodLabel(window: ComparableYearWindow, year: number) {
  if (!window.months || window.months.size >= 12) return String(year);
  const months = Array.from(window.months).sort((a, b) => a - b);
  const first = String(months[0]).padStart(2, "0");
  const last = String(months[months.length - 1]).padStart(2, "0");
  return first === last ? `${year}.${first}` : `${year}.${first}~${last}`;
}

export function latestComparableMonths(rows: Array<Record<string, unknown>>): [string, string] | null {
  const months = Array.from(new Set(rows.map(monthKeyOf).filter((month) => /^\d{4}-\d{2}$/.test(month)))).sort().reverse();
  if (months.length < 2) return null;
  return [months[0], months[1]];
}

export function comparisonBasisFromValue(value: unknown): ComparisonBasis {
  return value === "yoy" || value === "mom" || value === "none" ? value : "yoy";
}

export function availableComparisonBasis(
  preferred: ComparisonBasis,
  rows: Array<Record<string, unknown>>,
  fallbackRows: Array<Record<string, unknown>> = []
): ComparisonBasis {
  if (preferred === "none") return "none";
  const combinedRows = fallbackRows.length > 0 ? [...rows, ...fallbackRows] : rows;
  if (preferred === "mom" && latestComparableMonths(combinedRows)) return "mom";
  if (preferred === "yoy" && latestComparableYears(rows)) return "yoy";
  if (latestComparableMonths(combinedRows)) return "mom";
  if (latestComparableYears(rows)) return "yoy";
  return "none";
}

export function monthsBetweenInclusive(startDate: string, endDate: string) {
  const [startYear, startMonth] = startDate.slice(0, 7).split("-").map(Number);
  const [endYear, endMonth] = endDate.slice(0, 7).split("-").map(Number);
  if (![startYear, startMonth, endYear, endMonth].every(Number.isFinite)) return 0;
  return (endYear - startYear) * 12 + endMonth - startMonth + 1;
}

export function automaticComparisonBasis(startDate: string, endDate: string): ComparisonBasis {
  if (!startDate || !endDate) return "none";
  if (monthsBetweenInclusive(startDate, endDate) >= 13) return "yoy";
  if (monthsBetweenInclusive(startDate, endDate) >= 2) return "mom";
  return "none";
}

export function previousMonthKey(monthKey: string) {
  const [year, month] = monthKey.split("-").map(Number);
  if (!Number.isFinite(year) || !Number.isFinite(month)) return "";
  const previous = new Date(year, month - 2, 1);
  return `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, "0")}`;
}

export function previousYearMonthKey(monthKey: string) {
  const matched = monthKey.match(/^(\d{4})-(\d{2})$/);
  if (!matched) return "";
  return `${Number(matched[1]) - 1}-${matched[2]}`;
}

export function automaticGrowthTargetMonths(months: string[], comparisonMonthOf: (month: string) => string) {
  const monthSet = new Set(months);
  return months.filter((month) => monthSet.has(comparisonMonthOf(month)));
}

export function growthLabelsForMonthPair(
  rows: Array<Record<string, unknown>>,
  targetMonth: string,
  comparisonMonth: string,
  labelOf: (row: Record<string, unknown>) => string
) {
  const targetAmounts = new Map<string, number>();
  const comparisonAmounts = new Map<string, number>();
  if (!targetMonth || !comparisonMonth || targetMonth === comparisonMonth) return new Map<string, string>();
  rows.forEach((row) => {
    const label = labelOf(row);
    if (!label) return;
    const period = monthKeyOf(row);
    if (period === targetMonth) targetAmounts.set(label, (targetAmounts.get(label) ?? 0) + amountOf(row));
    else if (period === comparisonMonth) comparisonAmounts.set(label, (comparisonAmounts.get(label) ?? 0) + amountOf(row));
  });
  const labels = new Set([...targetAmounts.keys(), ...comparisonAmounts.keys()]);
  const growthByLabel = new Map<string, string>();
  labels.forEach((label) => {
    const currentAmount = targetAmounts.get(label) ?? 0;
    const previousAmount = comparisonAmounts.get(label) ?? 0;
    if (previousAmount <= 0) {
      if (currentAmount > 0) growthByLabel.set(label, "신규");
      return;
    }
    const growth = growthDisplayLabel(currentAmount, previousAmount);
    if (growth) growthByLabel.set(label, growth);
  });
  return growthByLabel;
}

export type YtdAmountComparison = {
  currentAmount: number;
  previousAmount: number;
  deltaAmount: number;
  value: number | null;
  growth: string;
  lowBase: boolean;
  comparisonNoSales: boolean;
};

/**
 * 비가산 지표인 성장률을 행별로 평균하지 않고, 완료월 YTD 금액을 먼저 합한 뒤 계산한다.
 */
export function ytdAmountComparisonsByLabel(
  rows: Array<Record<string, unknown>>,
  window: ComparableYearWindow | null,
  labelOf: (row: Record<string, unknown>) => string,
  lowBaseThreshold = lowBaseAmount()
) {
  const amounts = new Map<string, { current: number; previous: number }>();
  if (!window) return new Map<string, YtdAmountComparison>();

  rows.forEach((row) => {
    const label = labelOf(row);
    if (!label) return;
    const bucket = yoyBucketOf(row, window);
    if (!bucket) return;
    const current = amounts.get(label) ?? { current: 0, previous: 0 };
    current[bucket] += amountOf(row);
    amounts.set(label, current);
  });

  const result = new Map<string, YtdAmountComparison>();
  amounts.forEach(({ current, previous }, label) => {
    if (current <= 0 && previous <= 0) return;
    const comparisonNoSales = previous <= 0 && current > 0;
    const value = previous > 0 ? ((current - previous) / previous) * 100 : null;
    result.set(label, {
      currentAmount: current,
      previousAmount: previous,
      deltaAmount: current - previous,
      value,
      growth: comparisonNoSales ? "신규" : growthDisplayLabel(current, previous, lowBaseThreshold) ?? "-",
      lowBase: previous > 0 && previous < lowBaseThreshold,
      comparisonNoSales
    });
  });
  return result;
}

export function completedYtdPeriodLabel(window: ComparableYearWindow | null) {
  if (!window?.months?.size) return "완료월 YTD 비교 데이터 없음";
  const lastMonth = Math.max(...window.months);
  const monthRange = lastMonth === 1 ? "1월" : `1~${lastMonth}월`;
  return `YTD · ${window.latestYear}년 ${monthRange} vs ${window.previousYear}년 ${monthRange}`;
}

export function shortMonthKeyLabel(monthKey: string, compareWith?: string) {
  const match = monthKey.match(/^(\d{4})-(\d{2})$/);
  if (!match) return monthKey;
  const compareYear = compareWith?.slice(0, 4);
  return compareYear && compareYear !== match[1] ? `${match[1]}-${match[2]}` : `${Number(match[2])}월`;
}

// 비교 두 달이 달력상 인접하지 않을 때, 건너뛴 달 구간 라벨(예: "5월", "4~5월")을 만든다.
export function missingMonthRangeLabel(periods: [string, string]) {
  const [current, previous] = periods;
  const gaps: string[] = [];
  let cursor = previousMonthKey(current);
  while (cursor && cursor !== previous && gaps.length < 24) {
    gaps.push(cursor);
    cursor = previousMonthKey(cursor);
  }
  if (gaps.length === 0 || gaps.length >= 24) return "";
  const newest = shortMonthKeyLabel(gaps[0], current);
  const oldest = shortMonthKeyLabel(gaps[gaps.length - 1], current);
  return gaps.length === 1 ? newest : `${oldest}~${newest}`;
}

export function isAdjacentMonthPair(periods: [string, string] | null) {
  return Boolean(periods && previousMonthKey(periods[0]) === periods[1]);
}

export function shortMonthPairLabel(periods: [string, string] | null) {
  if (!periods) return "MoM";
  const pairText = `${shortMonthKeyLabel(periods[0], periods[1])} vs ${shortMonthKeyLabel(periods[1], periods[0])}`;
  if (isAdjacentMonthPair(periods)) return `MoM · ${pairText}`;
  const missing = missingMonthRangeLabel(periods);
  return `월 비교 · ${pairText}${missing ? ` (${missing} 데이터 없음)` : ""}`;
}

// 성장률 표시 정책: 기저(비교 대상 값)가 임계 미만이면 %가 소음이 되므로 "기저 미미"로,
// 임계 이상이라도 +999%를 넘으면 사용자가 바로 이해할 수 있도록 배수 표현으로 표시한다.
// 원시 계산과 순위 기준은 바꾸지 않는다.
export const LOW_BASE_AMOUNT_EUR = 500;
export const LOW_BASE_QTY = 10;
export const GROWTH_DISPLAY_CAP = 999;

export function growthDisplayLabel(current: number, previous: number, lowBaseThreshold = lowBaseAmount()): string | null {
  if (previous <= 0) return null;
  if (previous < lowBaseThreshold) return "기저 미미";
  const growth = ((current - previous) / previous) * 100;
  if (growth > GROWTH_DISPLAY_CAP) return "10배 이상 증가";
  return `${growth >= 0 ? "+" : ""}${formatNumber(growth, 1)}%`;
}

// "+12.3%" / ">-..." 형태가 아닌 상태 라벨(신규/기저 미미/-)은 증감 색이 아니라 중립색으로 다룬다.
export function isGrowthStatusLabel(value: string) {
  return value === "신규" || value === "기저 미미" || value === "-" || value === "";
}

export function growthBadgeClass(value: string) {
  if (isGrowthStatusLabel(value)) return "text-muted2";
  return value.startsWith("-") ? "text-brand" : "text-pos";
}

export function comparisonPeriodLabel(
  basis: ComparisonBasis,
  rows: Array<Record<string, unknown>>,
  fallbackEndDate?: string,
  requestedBasis?: ComparisonBasis
) {
  if (basis === "none") return "카드 증감 기준: 표시 안 함";
  // 사용자가 YoY를 원했지만 비교 가능한 전년 창이 없어 MoM으로 대체된 경우 사유를 명시한다.
  const fallbackPrefix = requestedBasis === "yoy" && basis === "mom" ? "YoY 불가(전년 동일 월 없음) · " : "";
  if (basis === "mom") {
    const months = latestComparableMonths(rows);
    if (months) {
      if (isAdjacentMonthPair(months)) return `카드 증감 기준: ${fallbackPrefix}MoM · ${months[0]} vs ${months[1]}`;
      const missing = missingMonthRangeLabel(months);
      return `카드 증감 기준: ${fallbackPrefix}월 비교 · ${months[0]} vs ${months[1]}${missing ? ` (${missing} 데이터 없음)` : ""}`;
    }
    const endMonth = fallbackEndDate?.slice(0, 7);
    return endMonth ? `카드 증감 기준: ${fallbackPrefix}MoM · ${endMonth} vs ${previousMonthKey(endMonth)}` : `카드 증감 기준: ${fallbackPrefix}MoM`;
  }
  const window = comparableYearWindow(rows);
  if (window) {
    const rangeLabel = yoyWindowRangeLabel(window);
    return `카드 증감 기준: YTD YoY · ${window.latestYear}년${rangeLabel} vs ${window.previousYear}년${rangeLabel}`;
  }
  const endYear = fallbackEndDate?.slice(0, 4);
  return endYear ? `카드 증감 기준: YTD YoY · ${endYear}년 vs ${Number(endYear) - 1}년` : "카드 증감 기준: 전년 대비";
}
