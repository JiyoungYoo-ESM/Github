export type CrossMomStatus =
  | "ok"
  | "same_period"
  | "current_month_missing"
  | "comparison_month_missing"
  | "current_month_partial"
  | "comparison_month_partial"
  | "zero_base"
  | "low_base";

export type CrossMomGrowth = {
  value: number | null;
  status: CrossMomStatus;
};

export const CROSS_GROWTH_AXES = [
  "country-brand",
  "country-sku",
  "brand-sku",
  "ingredient-country",
  "ingredient-brand",
  "ingredient-sku"
] as const;

export type CrossGrowthAxis = (typeof CROSS_GROWTH_AXES)[number];
export type CrossGrowthDimension = "country" | "brand" | "sku" | "ingredient";

export type CrossGrowthSourceRow = Record<CrossGrowthDimension, string> & {
  month: string;
  value: number;
};

export type CrossGrowthPeriodValues = {
  current: number;
  comparison: number;
};

export type CrossGrowthAggregate = CrossGrowthPeriodValues & CrossMomGrowth;

export type CrossGrowthMatrix = {
  rowDimension: CrossGrowthDimension;
  columnDimension: CrossGrowthDimension;
  rows: string[];
  columns: string[];
  cells: Array<CrossGrowthAggregate & { row: string; column: string }>;
  rowTotals: Array<CrossGrowthAggregate & { row: string }>;
  columnTotals: Array<CrossGrowthAggregate & { column: string }>;
  grandTotal: CrossGrowthAggregate;
};

type CrossGrowthCoverage = {
  currentMonthAvailable: boolean;
  comparisonMonthAvailable: boolean;
  currentMonthPartial?: boolean;
  comparisonMonthPartial?: boolean;
  lowBaseThreshold: number;
};

const CROSS_GROWTH_DIMENSIONS: Record<
  CrossGrowthAxis,
  { row: CrossGrowthDimension; column: CrossGrowthDimension }
> = {
  "country-brand": { row: "country", column: "brand" },
  "country-sku": { row: "country", column: "sku" },
  "brand-sku": { row: "brand", column: "sku" },
  "ingredient-country": { row: "ingredient", column: "country" },
  "ingredient-brand": { row: "ingredient", column: "brand" },
  "ingredient-sku": { row: "ingredient", column: "sku" }
};

type DateParts = {
  year: number;
  month: number;
  day: number;
};

function parseDateParts(value: string): DateParts | null {
  const matched = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!matched) return null;
  const year = Number(matched[1]);
  const month = Number(matched[2]);
  const day = Number(matched[3]);
  if (![year, month, day].every(Number.isFinite) || month < 1 || month > 12 || day < 1 || day > 31) return null;
  return { year, month, day };
}

function monthIndex(year: number, month: number) {
  return year * 12 + month - 1;
}

function monthKeyIndex(value: string) {
  const matched = value.match(/^(\d{4})-(\d{2})$/);
  if (!matched) return null;
  const year = Number(matched[1]);
  const month = Number(matched[2]);
  if (!Number.isFinite(year) || month < 1 || month > 12) return null;
  return monthIndex(year, month);
}

function monthKeyFromIndex(index: number) {
  const year = Math.floor(index / 12);
  const month = (index % 12) + 1;
  return `${year}-${String(month).padStart(2, "0")}`;
}

/** 분석 기간의 달을 오름차순으로 반환한다. 부분 월 제외 옵션도 백엔드와 동일하게 반영한다. */
export function analysisMonthKeys(startDate: string, endDate: string, excludePartialMonths = true) {
  const start = parseDateParts(startDate);
  const end = parseDateParts(endDate);
  if (!start || !end) return [];

  let startIndex = monthIndex(start.year, start.month);
  let endIndex = monthIndex(end.year, end.month);
  if (excludePartialMonths && start.day !== 1) startIndex += 1;
  const endMonthLastDay = new Date(Date.UTC(end.year, end.month, 0)).getUTCDate();
  if (excludePartialMonths && end.day !== endMonthLastDay) endIndex -= 1;
  if (startIndex > endIndex) return [];

  const keys: string[] = [];
  for (let index = startIndex; index <= endIndex; index += 1) keys.push(monthKeyFromIndex(index));
  return keys;
}

export function formatAnalysisMonthLabel(monthKey: string) {
  const matched = monthKey.match(/^(\d{4})-(\d{2})$/);
  return matched ? `${matched[1]}년 ${Number(matched[2])}월` : monthKey;
}

export function nearestAvailableMonth(targetMonth: string, availableMonths: string[], excludedMonth = "") {
  const target = targetMonth.match(/^(\d{4})-(\d{2})$/);
  if (!target) return "";
  const targetIndex = monthIndex(Number(target[1]), Number(target[2]));
  return (
    availableMonths
      .filter((month) => month !== excludedMonth && /^\d{4}-\d{2}$/.test(month))
      .map((month) => {
        const [year, monthNumber] = month.split("-").map(Number);
        const index = monthIndex(year, monthNumber);
        return { month, distance: Math.abs(index - targetIndex), isFuture: index > targetIndex };
      })
      .sort((left, right) => left.distance - right.distance || Number(left.isFuture) - Number(right.isFuture) || right.month.localeCompare(left.month))[0]?.month ?? ""
  );
}

/** 같은 달은 제외하고 입력된 모든 월의 순서 있는 쌍을 만든다. */
export function orderedDistinctMonthPairs(months: string[]) {
  const uniqueMonths = Array.from(new Set(months.filter((month) => monthKeyIndex(month) !== null)));
  return uniqueMonths.flatMap((currentMonth) =>
    uniqueMonths
      .filter((comparisonMonth) => comparisonMonth !== currentMonth)
      .map((comparisonMonth) => ({ currentMonth, comparisonMonth }))
  );
}

/**
 * 기준월이 비교월의 바로 다음 달일 때만 MoM이다.
 * 비인접 쌍과 역순 쌍은 계산은 가능하지만 일반 월 비교로 분류한다.
 */
export function classifyCrossMonthPair(currentMonth: string, comparisonMonth: string) {
  const currentIndex = monthKeyIndex(currentMonth);
  const comparisonIndex = monthKeyIndex(comparisonMonth);
  if (currentIndex === null || comparisonIndex === null || currentIndex === comparisonIndex) {
    return { valid: false, distance: null, reverse: false, adjacent: false, kind: "invalid" as const };
  }
  const distance = currentIndex - comparisonIndex;
  return {
    valid: true,
    distance,
    reverse: distance < 0,
    adjacent: distance === 1,
    kind: distance === 1 ? ("mom" as const) : ("month_comparison" as const)
  };
}

export function calculateCrossMomGrowth({
  current,
  comparison,
  currentMonthAvailable,
  comparisonMonthAvailable,
  currentMonthPartial = false,
  comparisonMonthPartial = false,
  samePeriod = false,
  lowBaseThreshold
}: {
  current: number;
  comparison: number;
  currentMonthAvailable: boolean;
  comparisonMonthAvailable: boolean;
  currentMonthPartial?: boolean;
  comparisonMonthPartial?: boolean;
  samePeriod?: boolean;
  lowBaseThreshold: number;
}): CrossMomGrowth {
  if (samePeriod) return { value: null, status: "same_period" };
  if (!currentMonthAvailable) return { value: null, status: "current_month_missing" };
  if (!comparisonMonthAvailable) return { value: null, status: "comparison_month_missing" };
  if (currentMonthPartial) return { value: null, status: "current_month_partial" };
  if (comparisonMonthPartial) return { value: null, status: "comparison_month_partial" };
  if (!Number.isFinite(comparison) || comparison <= 0) return { value: null, status: "zero_base" };
  if (comparison < lowBaseThreshold) return { value: null, status: "low_base" };
  const safeCurrent = Number.isFinite(current) ? current : 0;
  return { value: Math.round(((safeCurrent - comparison) / comparison) * 100), status: "ok" };
}

/** 셀 성장률을 평균하지 않고 기간 값을 먼저 합산한 뒤 성장률을 한 번 계산한다. */
export function calculateAggregateCrossGrowth(
  periodValues: CrossGrowthPeriodValues[],
  coverage: CrossGrowthCoverage
): CrossGrowthAggregate {
  const totals = periodValues.reduce(
    (sum, values) => ({
      current: sum.current + (Number.isFinite(values.current) ? values.current : 0),
      comparison: sum.comparison + (Number.isFinite(values.comparison) ? values.comparison : 0)
    }),
    { current: 0, comparison: 0 }
  );
  return { ...totals, ...calculateCrossMomGrowth({ ...totals, ...coverage }) };
}

export function crossGrowthDimensions(axis: CrossGrowthAxis, flipped = false) {
  const dimensions = CROSS_GROWTH_DIMENSIONS[axis];
  return flipped
    ? { row: dimensions.column, column: dimensions.row }
    : { row: dimensions.row, column: dimensions.column };
}

function crossPairKey(row: string, column: string) {
  return `${row}\u0000${column}`;
}

/**
 * 교차축과 월 쌍에 대해 셀/행/열/전체 값을 먼저 집계하고 동일한 상태 정책으로 성장률을 계산한다.
 * MoM뿐 아니라 명시적인 전년 동월 쌍을 넘기면 YoY 공식 감사에도 사용할 수 있다.
 */
export function buildCrossGrowthMatrix({
  sourceRows,
  axis,
  flipped = false,
  currentMonth,
  comparisonMonth,
  availableMonths,
  partialMonths = new Set<string>(),
  lowBaseThreshold
}: {
  sourceRows: CrossGrowthSourceRow[];
  axis: CrossGrowthAxis;
  flipped?: boolean;
  currentMonth: string;
  comparisonMonth: string;
  availableMonths?: Set<string>;
  partialMonths?: Set<string>;
  lowBaseThreshold: number;
}): CrossGrowthMatrix {
  const pair = classifyCrossMonthPair(currentMonth, comparisonMonth);
  if (!pair.valid) throw new Error("교차 성장률의 기준월과 비교월은 서로 다른 YYYY-MM 형식이어야 합니다.");

  const dimensions = crossGrowthDimensions(axis, flipped);
  const observedMonths = new Set<string>();
  const rowLabels = new Set<string>();
  const columnLabels = new Set<string>();
  const periodValues = new Map<string, CrossGrowthPeriodValues>();

  sourceRows.forEach((sourceRow) => {
    const row = String(sourceRow[dimensions.row] ?? "").trim();
    const column = String(sourceRow[dimensions.column] ?? "").trim();
    if (!row || !column || monthKeyIndex(sourceRow.month) === null) return;
    observedMonths.add(sourceRow.month);
    rowLabels.add(row);
    columnLabels.add(column);
    if (sourceRow.month !== currentMonth && sourceRow.month !== comparisonMonth) return;

    const key = crossPairKey(row, column);
    const current = periodValues.get(key) ?? { current: 0, comparison: 0 };
    const value = Number.isFinite(sourceRow.value) ? sourceRow.value : 0;
    if (sourceRow.month === currentMonth) current.current += value;
    if (sourceRow.month === comparisonMonth) current.comparison += value;
    periodValues.set(key, current);
  });

  const availability = availableMonths ?? observedMonths;
  const coverage: CrossGrowthCoverage = {
    currentMonthAvailable: availability.has(currentMonth),
    comparisonMonthAvailable: availability.has(comparisonMonth),
    currentMonthPartial: partialMonths.has(currentMonth),
    comparisonMonthPartial: partialMonths.has(comparisonMonth),
    lowBaseThreshold
  };
  const rows = Array.from(rowLabels).sort();
  const columns = Array.from(columnLabels).sort();
  const cells = rows.flatMap((row) =>
    columns.map((column) => {
      const values = periodValues.get(crossPairKey(row, column)) ?? { current: 0, comparison: 0 };
      return { row, column, ...calculateAggregateCrossGrowth([values], coverage) };
    })
  );
  const rowTotals = rows.map((row) => ({
    row,
    ...calculateAggregateCrossGrowth(
      columns.map((column) => periodValues.get(crossPairKey(row, column)) ?? { current: 0, comparison: 0 }),
      coverage
    )
  }));
  const columnTotals = columns.map((column) => ({
    column,
    ...calculateAggregateCrossGrowth(
      rows.map((row) => periodValues.get(crossPairKey(row, column)) ?? { current: 0, comparison: 0 }),
      coverage
    )
  }));
  const grandTotal = calculateAggregateCrossGrowth(Array.from(periodValues.values()), coverage);

  return {
    rowDimension: dimensions.row,
    columnDimension: dimensions.column,
    rows,
    columns,
    cells,
    rowTotals,
    columnTotals,
    grandTotal
  };
}
