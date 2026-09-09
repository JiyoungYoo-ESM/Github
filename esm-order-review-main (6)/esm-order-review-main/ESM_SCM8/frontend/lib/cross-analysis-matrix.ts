import { displayBrandName } from "./brand-display.ts";
import { calculateCrossMomGrowth, type CrossMomStatus } from "./cross-analysis-mom.ts";
import { lowBaseAmount } from "./low-base.ts";
import {
  amountOf,
  brandOf,
  countryOf,
  ingredientOf,
  monthKeyOf,
  productNameOf,
  qtyOf,
  skuCodeOf
} from "./global-demand-view-model.ts";
import type { IngredientAnalysis, SeasonAnalysis } from "../types/api.ts";

export type CrossAxis =
  | "country-brand"
  | "country-sku"
  | "brand-sku"
  | "ingredient-country"
  | "ingredient-brand"
  | "ingredient-sku";
export type CrossMetric = "sales" | "quantity" | "yoy" | "mom";
export type CrossScale = "amount" | "share";
export type CrossDimension = "country" | "brand" | "sku" | "ingredient";

export type CrossMomPeriod = {
  currentMonth: string;
  comparisonMonth: string;
  availableMonths: Set<string>;
  partialMonths: Set<string>;
  expectedMonths?: Set<string>;
};

export type CrossMatrixData = {
  rowLabel: string;
  columnLabel: string;
  totalLabel: string;
  columns: string[];
  rows: string[];
  rowOptions: string[];
  columnOptions: string[];
  filteredRowOptions: string[];
  filteredColumnOptions: string[];
  values: Array<Array<number | null>>;
  cellPresence: boolean[][];
  cellStatuses: Array<Array<CrossMomStatus | null>>;
  growthRowTotals: Array<number | null>;
  growthRowTotalStatuses: Array<CrossMomStatus | null>;
  shareTieBreakKeys: string[][];
};

type ComparableYearWindow = { latestYear: number; previousYear: number; months: Set<number> | null };
type PeriodValues = { current: number; comparison: number };

const CROSS_AXIS_DIMENSIONS: Record<
  CrossAxis,
  { row: CrossDimension; column: CrossDimension; rowLabel: string; columnLabel: string }
> = {
  "country-brand": { row: "country", column: "brand", rowLabel: "국가", columnLabel: "브랜드" },
  "country-sku": { row: "country", column: "sku", rowLabel: "국가", columnLabel: "SKU" },
  "brand-sku": { row: "brand", column: "sku", rowLabel: "브랜드", columnLabel: "SKU" },
  "ingredient-country": { row: "ingredient", column: "country", rowLabel: "성분", columnLabel: "국가" },
  "ingredient-brand": { row: "ingredient", column: "brand", rowLabel: "성분", columnLabel: "브랜드" },
  "ingredient-sku": { row: "ingredient", column: "sku", rowLabel: "성분", columnLabel: "SKU" }
};

function firstNonEmptyRows(...candidates: Array<Array<Record<string, unknown>> | undefined>) {
  return candidates.find((rows) => rows && rows.length > 0) ?? [];
}

function validCrossLabel(value: string) {
  const normalized = value.normalize("NFKC").trim().toLowerCase();
  return Boolean(normalized) && !["-", "미상", "unknown", "n/a", "nan", "none"].includes(normalized) && !value.includes("미분류");
}

export function crossDimensionValue(row: Record<string, unknown>, dimension: CrossDimension) {
  if (dimension === "country") return countryOf(row);
  if (dimension === "brand") return displayBrandName(brandOf(row));
  if (dimension === "ingredient") return ingredientOf(row);
  const sku = skuCodeOf(row).trim();
  const name = productNameOf(row).trim();
  if (sku && sku !== "-" && name && name !== "-") return `${name} · ${sku}`;
  return sku && sku !== "-" ? sku : name;
}

function crossMetricValue(row: Record<string, unknown>, metric: Exclude<CrossMetric, "yoy" | "mom">) {
  return metric === "quantity" ? qtyOf(row) / 10_000 : amountOf(row) / 1_000;
}

function crossBaseValue(row: Record<string, unknown>) {
  return amountOf(row) / 1_000;
}

function rowColumnKey(row: string, column: string) {
  return `${row}\u0000${column}`;
}

function pickComparableYearWindow(monthsByYear: Map<number, Set<number>>): ComparableYearWindow | null {
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

function buildCrossYoyData(
  rows: Array<Record<string, unknown>>,
  rowDimension: CrossDimension,
  columnDimension: CrossDimension,
  coveragePeriod?: CrossMomPeriod,
  yoyMonthRange?: [number, number] | null
) {
  const grouped = new Map<string, Map<string, { year: number; month: number; value: number }>>();
  const monthsByYear = new Map<number, Set<number>>();
  const observedMonths = new Set<string>();

  rows.forEach((sourceRow) => {
    const row = crossDimensionValue(sourceRow, rowDimension);
    const column = crossDimensionValue(sourceRow, columnDimension);
    if (!validCrossLabel(row) || !validCrossLabel(column)) return;
    const monthKey = monthKeyOf(sourceRow);
    const matched = monthKey.match(/^(\d{4})-(\d{2})$/);
    if (!matched) return;
    const year = Number(matched[1]);
    const month = Number(matched[2]);
    observedMonths.add(monthKey);
    const key = rowColumnKey(row, column);
    const periods = grouped.get(key) ?? new Map<string, { year: number; month: number; value: number }>();
    const current = periods.get(monthKey) ?? { year, month, value: 0 };
    current.value += crossBaseValue(sourceRow);
    periods.set(monthKey, current);
    grouped.set(key, periods);
    const months = monthsByYear.get(year) ?? new Set<number>();
    months.add(month);
    monthsByYear.set(year, months);
  });

  const expectedMonthsByYear = new Map<number, Set<number>>();
  coveragePeriod?.expectedMonths?.forEach((monthKey) => {
    const matched = monthKey.match(/^(\d{4})-(\d{2})$/);
    if (!matched) return;
    const year = Number(matched[1]);
    const months = expectedMonthsByYear.get(year) ?? new Set<number>();
    months.add(Number(matched[2]));
    expectedMonthsByYear.set(year, months);
  });
  const window = pickComparableYearWindow(expectedMonthsByYear.size > 0 ? expectedMonthsByYear : monthsByYear);
  const periodValues = new Map<string, PeriodValues>();
  if (!window) {
    return {
      currentMonthAvailable: false,
      comparisonMonthAvailable: false,
      currentMonthPartial: false,
      comparisonMonthPartial: false,
      periodValues
    };
  }
  // 사용자가 YoY 비교 구간(시작월~종료월)을 지정하면 비교 가능한 창과 교집합으로 제한한다
  const rangeMonths = yoyMonthRange
    ? new Set(Array.from({ length: 12 }, (_, index) => index + 1).filter((month) => month >= yoyMonthRange[0] && month <= yoyMonthRange[1]))
    : null;
  const effectiveMonths = rangeMonths
    ? new Set(Array.from(window.months ?? rangeMonths).filter((month) => rangeMonths.has(month)))
    : window.months;
  grouped.forEach((periods, key) => {
    const totals = { current: 0, comparison: 0 };
    periods.forEach((item) => {
      if (effectiveMonths && !effectiveMonths.has(item.month)) return;
      if (item.year === window.latestYear) totals.current += item.value;
      if (item.year === window.previousYear) totals.comparison += item.value;
    });
    periodValues.set(key, totals);
  });
  const availability = coveragePeriod?.availableMonths ?? observedMonths;
  const partialMonths = coveragePeriod?.partialMonths ?? new Set<string>();
  const comparisonKeys = Array.from(effectiveMonths ?? []).map(
    (month) => `${window.previousYear}-${String(month).padStart(2, "0")}`
  );
  const currentKeys = Array.from(effectiveMonths ?? []).map(
    (month) => `${window.latestYear}-${String(month).padStart(2, "0")}`
  );
  return {
    currentMonthAvailable: currentKeys.every((month) => availability.has(month)),
    comparisonMonthAvailable: comparisonKeys.every((month) => availability.has(month)),
    currentMonthPartial: currentKeys.some((month) => partialMonths.has(month)),
    comparisonMonthPartial: comparisonKeys.some((month) => partialMonths.has(month)),
    periodValues
  };
}

function buildCrossMomData(
  rows: Array<Record<string, unknown>>,
  rowDimension: CrossDimension,
  columnDimension: CrossDimension,
  requestedPeriod?: CrossMomPeriod
) {
  const grouped = new Map<string, Map<string, number>>();
  const observedMonths = new Set<string>();
  rows.forEach((sourceRow) => {
    const row = crossDimensionValue(sourceRow, rowDimension);
    const column = crossDimensionValue(sourceRow, columnDimension);
    if (!validCrossLabel(row) || !validCrossLabel(column)) return;
    const monthKey = monthKeyOf(sourceRow);
    if (!/^\d{4}-\d{2}$/.test(monthKey)) return;
    observedMonths.add(monthKey);
    const key = rowColumnKey(row, column);
    const periods = grouped.get(key) ?? new Map<string, number>();
    periods.set(monthKey, (periods.get(monthKey) ?? 0) + crossBaseValue(sourceRow));
    grouped.set(key, periods);
  });

  const fallbackMonths = Array.from(observedMonths).sort().reverse();
  const currentMonth = requestedPeriod?.currentMonth || fallbackMonths[0] || "";
  const comparisonMonth = requestedPeriod?.comparisonMonth || fallbackMonths[1] || "";
  const availability = requestedPeriod?.availableMonths ?? observedMonths;
  const partialMonths = requestedPeriod?.partialMonths ?? new Set<string>();
  const periodValues = new Map<string, PeriodValues>();
  grouped.forEach((periods, key) => {
    periodValues.set(key, {
      current: periods.get(currentMonth) ?? 0,
      comparison: periods.get(comparisonMonth) ?? 0
    });
  });
  return {
    samePeriod: Boolean(currentMonth && currentMonth === comparisonMonth),
    currentMonthAvailable: Boolean(currentMonth && availability.has(currentMonth)),
    comparisonMonthAvailable: Boolean(comparisonMonth && availability.has(comparisonMonth)),
    currentMonthPartial: Boolean(currentMonth && partialMonths.has(currentMonth)),
    comparisonMonthPartial: Boolean(comparisonMonth && partialMonths.has(comparisonMonth)),
    periodValues
  };
}

function calculatePeriodGrowth(
  totals: PeriodValues,
  availability: {
    currentMonthAvailable: boolean;
    comparisonMonthAvailable: boolean;
    currentMonthPartial?: boolean;
    comparisonMonthPartial?: boolean;
    samePeriod?: boolean;
  }
) {
  return calculateCrossMomGrowth({
    ...totals,
    ...availability,
    // 교차 매트릭스 값은 천 단위(amount / 1000)라 임계값도 천 단위로 환산해 넣는다.
    lowBaseThreshold: lowBaseAmount() / 1_000
  });
}

export function buildCrossMatrix(
  sourceRows: Array<Record<string, unknown>>,
  rowDimension: CrossDimension,
  columnDimension: CrossDimension,
  metric: CrossMetric,
  rowLabel: string,
  columnLabel: string,
  selectedRows: string[],
  selectedColumns: string[],
  momPeriod?: CrossMomPeriod,
  yoyMonthRange?: [number, number] | null
): CrossMatrixData {
  const pairTotals = new Map<string, number>();
  const rowTotals = new Map<string, number>();
  const columnTotals = new Map<string, number>();
  const rowToColumns = new Map<string, Set<string>>();
  const columnToRows = new Map<string, Set<string>>();

  sourceRows.forEach((sourceRow) => {
    const row = crossDimensionValue(sourceRow, rowDimension);
    const column = crossDimensionValue(sourceRow, columnDimension);
    if (!validCrossLabel(row) || !validCrossLabel(column)) return;
    const value = metric === "yoy" || metric === "mom" ? crossBaseValue(sourceRow) : crossMetricValue(sourceRow, metric);
    if (!Number.isFinite(value)) return;
    const key = rowColumnKey(row, column);
    pairTotals.set(key, (pairTotals.get(key) ?? 0) + value);
    rowTotals.set(row, (rowTotals.get(row) ?? 0) + value);
    columnTotals.set(column, (columnTotals.get(column) ?? 0) + value);
    const columnsForRow = rowToColumns.get(row) ?? new Set<string>();
    columnsForRow.add(column);
    rowToColumns.set(row, columnsForRow);
    const rowsForColumn = columnToRows.get(column) ?? new Set<string>();
    rowsForColumn.add(row);
    columnToRows.set(column, rowsForColumn);
  });

  const rowOptions = Array.from(rowTotals.entries()).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([label]) => label);
  const columnOptions = Array.from(columnTotals.entries()).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([label]) => label);
  const rows = selectedRows.filter((row) => rowOptions.includes(row));
  const columns = selectedColumns.filter((column) => columnOptions.includes(column));
  const allowedColumns = selectedRows.length > 0 ? new Set(selectedRows.flatMap((row) => Array.from(rowToColumns.get(row) ?? []))) : null;
  const allowedRows = selectedColumns.length > 0 ? new Set(selectedColumns.flatMap((column) => Array.from(columnToRows.get(column) ?? []))) : null;
  const filteredColumnOptions = allowedColumns ? columnOptions.filter((column) => allowedColumns.has(column)) : columnOptions;
  const filteredRowOptions = allowedRows ? rowOptions.filter((row) => allowedRows.has(row)) : rowOptions;

  const yoyData = metric === "yoy" ? buildCrossYoyData(sourceRows, rowDimension, columnDimension, momPeriod, yoyMonthRange) : null;
  const momData = metric === "mom" ? buildCrossMomData(sourceRows, rowDimension, columnDimension, momPeriod) : null;
  const growthAvailability =
    metric === "yoy"
      ? {
          currentMonthAvailable: Boolean(yoyData?.currentMonthAvailable),
          comparisonMonthAvailable: Boolean(yoyData?.comparisonMonthAvailable),
          currentMonthPartial: Boolean(yoyData?.currentMonthPartial),
          comparisonMonthPartial: Boolean(yoyData?.comparisonMonthPartial)
        }
      : {
          currentMonthAvailable: Boolean(momData?.currentMonthAvailable),
          comparisonMonthAvailable: Boolean(momData?.comparisonMonthAvailable),
          currentMonthPartial: Boolean(momData?.currentMonthPartial),
          comparisonMonthPartial: Boolean(momData?.comparisonMonthPartial),
          samePeriod: Boolean(momData?.samePeriod)
        };
  const growthPeriods = metric === "yoy" ? yoyData?.periodValues : momData?.periodValues;
  const growthForKey = (key: string) =>
    calculatePeriodGrowth(growthPeriods?.get(key) ?? { current: 0, comparison: 0 }, growthAvailability);
  const growthRows = rows.map((row) => columns.map((column) => growthForKey(rowColumnKey(row, column))));

  const values = rows.map((row, rowIndex) =>
    columns.map((column, columnIndex) =>
      metric === "yoy" || metric === "mom"
        ? growthRows[rowIndex][columnIndex].value
        : pairTotals.get(rowColumnKey(row, column)) ?? 0
    )
  );
  const cellPresence = rows.map((row) =>
    columns.map((column) => pairTotals.has(rowColumnKey(row, column)))
  );
  const cellStatuses = rows.map((_, rowIndex) =>
    columns.map((_, columnIndex) => (metric === "yoy" || metric === "mom" ? growthRows[rowIndex][columnIndex].status : null))
  );
  const growthRowResults = rows.map((row) => {
    if (metric !== "yoy" && metric !== "mom") return null;
    const totals = columns.reduce(
      (sum, column) => {
        const periodValues = growthPeriods?.get(rowColumnKey(row, column));
        return {
          current: sum.current + (periodValues?.current ?? 0),
          comparison: sum.comparison + (periodValues?.comparison ?? 0)
        };
      },
      { current: 0, comparison: 0 }
    );
    return calculatePeriodGrowth(totals, growthAvailability);
  });

  return {
    rowLabel,
    columnLabel,
    totalLabel: metric === "yoy" || metric === "mom" ? "합계 성장률" : "합계",
    columns,
    rows,
    rowOptions,
    columnOptions,
    filteredRowOptions,
    filteredColumnOptions,
    values,
    cellPresence,
    cellStatuses,
    growthRowTotals: growthRowResults.map((result) => result?.value ?? null),
    growthRowTotalStatuses: growthRowResults.map((result) => result?.status ?? null),
    shareTieBreakKeys: []
  };
}

export function sourceRowsForCrossAxis(
  axis: CrossAxis,
  metric: CrossMetric,
  season: SeasonAnalysis | null,
  ingredient: IngredientAnalysis | null
) {
  const isGrowth = metric === "yoy" || metric === "mom";
  if (axis === "country-brand" || axis === "country-sku" || axis === "brand-sku") {
    return isGrowth ? season?.countrySkuMonthly ?? [] : season?.countrySkuSummary ?? [];
  }
  if (axis === "ingredient-country") {
    return isGrowth
      ? ingredient?.countryMonthlyTrend ?? []
      : firstNonEmptyRows(ingredient?.countryMonthlyTrend, ingredient?.countrySummary);
  }
  if (axis === "ingredient-brand") {
    return ingredient?.brandMonthlyTrend ?? [];
  }
  return ingredient?.skuMonthlyTrend ?? [];
}

export function crossMatrixData(
  axis: CrossAxis,
  metric: CrossMetric,
  season: SeasonAnalysis | null,
  ingredient: IngredientAnalysis | null,
  selectedRows: string[] = [],
  selectedColumns: string[] = [],
  flipped = false,
  momPeriod?: CrossMomPeriod,
  yoyMonthRange?: [number, number] | null
) {
  const rows = sourceRowsForCrossAxis(axis, metric, season, ingredient);
  const config = CROSS_AXIS_DIMENSIONS[axis];
  const result = flipped
    ? buildCrossMatrix(rows, config.column, config.row, metric, config.columnLabel, config.rowLabel, selectedRows, selectedColumns, momPeriod, yoyMonthRange)
    : buildCrossMatrix(rows, config.row, config.column, metric, config.rowLabel, config.columnLabel, selectedRows, selectedColumns, momPeriod, yoyMonthRange);
  return {
    ...result,
    shareTieBreakKeys: result.rows.map((row) =>
      result.columns.map((column) => `${axis}\u0000${flipped ? column : row}\u0000${flipped ? row : column}`)
    )
  };
}
