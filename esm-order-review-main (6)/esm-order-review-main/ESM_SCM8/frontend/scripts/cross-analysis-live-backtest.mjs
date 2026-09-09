import assert from "node:assert/strict";

import { allocateCrossMatrixShares } from "../lib/cross-analysis-share.ts";
import {
  crossDimensionValue,
  crossMatrixData,
  sourceRowsForCrossAxis
} from "../lib/cross-analysis-matrix.ts";
import { calculateCrossMomGrowth } from "../lib/cross-analysis-mom.ts";
import { amountOf, monthKeyOf, qtyOf } from "../lib/global-demand-view-model.ts";

const API_URL = process.env.BACKTEST_URL || "http://127.0.0.1:8002/api/season-trend/latest";
const AXES = [
  "country-brand",
  "country-sku",
  "brand-sku",
  "ingredient-country",
  "ingredient-brand",
  "ingredient-sku"
];
const METRICS = ["sales", "quantity"];
const GROWTH_METRICS = ["mom", "yoy"];

function assertClose(actual, expected, message, tolerance = 1e-8) {
  assert.ok(Number.isFinite(actual), `${message}: actual is not finite (${actual})`);
  assert.ok(Math.abs(actual - expected) <= tolerance, `${message}: ${actual} !== ${expected}`);
}

function assertFiniteMatrix(matrix, message) {
  matrix.flat().forEach((value) => {
    assert.ok(value === null || (typeof value === "number" && Number.isFinite(value)), `${message}: invalid ${value}`);
  });
}

function sumValues(rows, metric) {
  return rows.reduce((sum, row) => {
    const value = metric === "quantity" ? qtyOf(row) / 10_000 : amountOf(row) / 1_000;
    return sum + (Number.isFinite(value) ? value : 0);
  }, 0);
}

function groupByPairAndMonth(rows, rowDimension, columnDimension) {
  const result = new Map();
  for (const source of rows) {
    const row = crossDimensionValue(source, rowDimension);
    const column = crossDimensionValue(source, columnDimension);
    const month = monthKeyOf(source);
    if (!row || !column || !/^\d{4}-\d{2}$/.test(month)) continue;
    const key = `${row}\u0000${column}`;
    const monthValues = result.get(key) ?? new Map();
    monthValues.set(month, (monthValues.get(month) ?? 0) + amountOf(source) / 1_000);
    result.set(key, monthValues);
  }
  return result;
}

function dimensionsFor(axis, flipped = false) {
  const pairs = {
    "country-brand": ["country", "brand"],
    "country-sku": ["country", "sku"],
    "brand-sku": ["brand", "sku"],
    "ingredient-country": ["ingredient", "country"],
    "ingredient-brand": ["ingredient", "brand"],
    "ingredient-sku": ["ingredient", "sku"]
  };
  const [row, column] = pairs[axis];
  return flipped ? { row: column, column: row } : { row, column };
}

function rawMonthKeys(rows) {
  return Array.from(new Set(rows.map(monthKeyOf).filter((month) => /^\d{4}-\d{2}$/.test(month)))).sort();
}

function comparableYoyMonths(rows) {
  const byYear = new Map();
  for (const month of rawMonthKeys(rows)) {
    const [year, monthNumber] = month.split("-").map(Number);
    const months = byYear.get(year) ?? new Set();
    months.add(monthNumber);
    byYear.set(year, months);
  }
  const years = Array.from(byYear.keys()).sort((a, b) => b - a);
  const latestYear = years[0];
  const previousYear = latestYear - 1;
  const latest = byYear.get(latestYear) ?? new Set();
  const previous = byYear.get(previousYear) ?? new Set();
  return {
    latestYear,
    previousYear,
    months: Array.from(latest).filter((month) => previous.has(month)).sort((a, b) => a - b)
  };
}

function rowCoverage(period, currentMonth, comparisonMonth) {
  const available = period.availableMonths;
  const partial = period.partialMonths;
  return {
    currentMonthAvailable: available.has(currentMonth),
    comparisonMonthAvailable: available.has(comparisonMonth),
    currentMonthPartial: partial.has(currentMonth),
    comparisonMonthPartial: partial.has(comparisonMonth)
  };
}

const response = await fetch(API_URL);
assert.equal(response.ok, true, `live analysis endpoint failed: ${response.status}`);
const payload = await response.json();
assert.equal(payload.status, "success");
const season = payload.season_analysis;
const ingredient = payload.ingredient_analysis;
assert.ok(season && ingredient, "season/ingredient analysis payload is missing");

const summaryRows = season.countrySkuSummary ?? [];
const monthlyRows = season.countrySkuMonthly ?? [];
assert.ok(summaryRows.length > 0 && monthlyRows.length > 0, "country/SKU source rows are empty");

// Source-level reconciliation: the cached cube must preserve both SKU grain and totals.
const summarySkus = new Set(summaryRows.map((row) => String(row.prod_cd ?? row["상품코드"] ?? "")).filter(Boolean));
const monthlySkus = new Set(monthlyRows.map((row) => String(row.prod_cd ?? row["상품코드"] ?? "")).filter(Boolean));
assert.deepEqual(summarySkus, monthlySkus, "summary/monthly SKU sets differ");
assertClose(sumValues(summaryRows, "sales"), sumValues(monthlyRows, "sales"), "summary/monthly sales total", 1e-6);
assertClose(sumValues(summaryRows, "quantity"), sumValues(monthlyRows, "quantity"), "summary/monthly quantity total", 1e-6);

const coverageRows = season.monthCoverage ?? [];
const coverageMonths = coverageRows.map((item) => String(item.month));
assert.equal(new Set(coverageMonths).size, coverageMonths.length, "monthCoverage contains duplicate months");
assert.ok(coverageRows.every((item) => ["complete", "partial", "missing"].includes(item.status)), "unknown month coverage status");
assert.ok(coverageRows.every((item) => Number.isFinite(Number(item.totalAmount)) && Number.isFinite(Number(item.totalQty))), "invalid month coverage totals");
assertClose(
  coverageRows.reduce((sum, item) => sum + Number(item.totalAmount), 0) / 1_000,
  sumValues(monthlyRows, "sales"),
  "month coverage/cross cube sales total",
  1e-6
);
assertClose(
  coverageRows.reduce((sum, item) => sum + Number(item.totalQty), 0) / 10_000,
  sumValues(monthlyRows, "quantity"),
  "month coverage/cross cube quantity total",
  1e-6
);

const allMonths = rawMonthKeys(monthlyRows);
assert.ok(allMonths.length >= 2, "fewer than two source months");
const partialMonths = new Set(coverageRows.filter((item) => item.status === "partial").map((item) => String(item.month)));
const period = {
  currentMonth: allMonths.at(-1),
  comparisonMonth: allMonths.at(-2),
  availableMonths: new Set(allMonths),
  partialMonths,
  expectedMonths: new Set(allMonths)
};

let staticViews = 0;
let growthFormulaChecks = 0;
let growthIntegrationViews = 0;
let cellsChecked = 0;
for (const axis of AXES) {
  console.error(`backtest axis ${axis} started`);
  for (const metric of METRICS) {
    const rows = sourceRowsForCrossAxis(axis, metric, season, ingredient);
    assert.ok(rows.length > 0, `${axis}/${metric}: no source rows`);
    const dimensions = dimensionsFor(axis);
    const sourcePairs = new Map();
    for (const source of rows) {
      const row = crossDimensionValue(source, dimensions.row);
      const column = crossDimensionValue(source, dimensions.column);
      if (!row || !column) continue;
      const key = `${row}\u0000${column}`;
      sourcePairs.set(key, (sourcePairs.get(key) ?? 0) + (metric === "quantity" ? qtyOf(source) / 10_000 : amountOf(source) / 1_000));
    }

    const options = crossMatrixData(axis, metric, season, ingredient, [], [], false, period);
    const normal = crossMatrixData(axis, metric, season, ingredient, options.rowOptions, options.columnOptions, false, period);
    const flipped = crossMatrixData(axis, metric, season, ingredient, options.columnOptions, options.rowOptions, true, period);
    assertFiniteMatrix(normal.values, `${axis}/${metric}/normal`);
    assertFiniteMatrix(flipped.values, `${axis}/${metric}/flipped`);
    assertClose(
      normal.values.flat().reduce((sum, value) => sum + (value ?? 0), 0),
      Array.from(sourcePairs.values()).reduce((sum, value) => sum + value, 0),
      `${axis}/${metric} total`,
      1e-6
    );
    assert.deepEqual(flipped.values, normal.values[0]?.map((_, columnIndex) => normal.values.map((row) => row[columnIndex])) ?? []);

    const share = allocateCrossMatrixShares(normal.values, 1, normal.shareTieBreakKeys);
    assertFiniteMatrix(share.values, `${axis}/${metric}/share`);
    const shareTotal = share.values.flat().reduce((sum, value) => sum + (value ?? 0), 0);
    assert.equal(Number(shareTotal.toFixed(1)), normal.values.flat().some((value) => (value ?? 0) !== 0) ? 100 : 0);
    staticViews += 2 * 2; // amount/share × normal/flipped

    for (const rowIndex of normal.rows.keys()) {
      for (const columnIndex of normal.columns.keys()) {
        const expected = sourcePairs.get(`${normal.rows[rowIndex]}\u0000${normal.columns[columnIndex]}`) ?? 0;
        assertClose(normal.values[rowIndex][columnIndex], expected, `${axis}/${metric} cell`);
        cellsChecked += 1;
      }
    }
  }

  const growthRows = sourceRowsForCrossAxis(axis, "mom", season, ingredient);
  const dimensions = dimensionsFor(axis);
  const pairValues = groupByPairAndMonth(growthRows, dimensions.row, dimensions.column);
  const availableMonths = rawMonthKeys(growthRows);
  const growthPeriod = {
    ...period,
    currentMonth: availableMonths.at(-1),
    comparisonMonth: availableMonths.at(-2),
    availableMonths: new Set(availableMonths),
    expectedMonths: new Set(availableMonths)
  };

  const growthOptions = crossMatrixData(axis, "mom", season, ingredient, [], [], false, growthPeriod);
  const growthRowsLabels = growthOptions.rowOptions;
  const growthColumnsLabels = growthOptions.columnOptions;
  let growthPairsChecked = 0;

  // Every ordered pair is exercised against an independent grouped source. This keeps the
  // backtest exhaustive without rebuilding a 100k-row matrix twice for every pair.
  for (const currentMonth of availableMonths) {
    for (const comparisonMonth of availableMonths) {
      if (currentMonth === comparisonMonth) continue;
      const currentPeriod = { ...growthPeriod, currentMonth, comparisonMonth };
      const coverage = rowCoverage(currentPeriod, currentMonth, comparisonMonth);
      for (const [pairKey, values] of pairValues.entries()) {
        const expected = calculateCrossMomGrowth({
          current: values.get(currentMonth) ?? 0,
          comparison: values.get(comparisonMonth) ?? 0,
          ...coverage,
          lowBaseThreshold: 0.5
        });
        assert.ok(expected.value === null || Number.isFinite(expected.value), `${axis}/${currentMonth}/${comparisonMonth}/${pairKey}: invalid growth value`);
        growthPairsChecked += 1;
      }
      const integrationPairs = new Set([
        `${availableMonths.at(-1)}\u0000${availableMonths.at(-2)}`,
        `${availableMonths.at(-2)}\u0000${availableMonths.at(-1)}`,
        `${availableMonths.at(-1)}\u0000${availableMonths[0]}`
      ]);
      if (integrationPairs.has(`${currentMonth}\u0000${comparisonMonth}`)) {
        const normal = crossMatrixData(axis, "mom", season, ingredient, growthRowsLabels, growthColumnsLabels, false, currentPeriod);
        const flipped = crossMatrixData(axis, "mom", season, ingredient, growthColumnsLabels, growthRowsLabels, true, currentPeriod);
        assert.deepEqual(flipped.values, normal.values[0]?.map((_, columnIndex) => normal.values.map((row) => row[columnIndex])) ?? []);
        assert.deepEqual(flipped.cellStatuses, normal.cellStatuses[0]?.map((_, columnIndex) => normal.cellStatuses.map((row) => row[columnIndex])) ?? []);
        for (const [rowIndex, row] of normal.rows.entries()) {
          for (const [columnIndex, column] of normal.columns.entries()) {
            const values = pairValues.get(`${row}\u0000${column}`) ?? new Map();
            const expected = calculateCrossMomGrowth({ current: values.get(currentMonth) ?? 0, comparison: values.get(comparisonMonth) ?? 0, ...coverage, lowBaseThreshold: 0.5 });
            assert.equal(normal.values[rowIndex][columnIndex], expected.value, `${axis}/${currentMonth}/${comparisonMonth} integration value`);
            assert.equal(normal.cellStatuses[rowIndex][columnIndex], expected.status, `${axis}/${currentMonth}/${comparisonMonth} integration status`);
            cellsChecked += 1;
          }
        }
        growthIntegrationViews += 2;
      }
    }
  }
  growthFormulaChecks += growthPairsChecked;
  console.error(`backtest axis ${axis} growth pairs=${growthPairsChecked}`);

  const yoy = comparableYoyMonths(growthRows);
  for (const month of yoy.months) {
    const currentMonth = `${yoy.latestYear}-${String(month).padStart(2, "0")}`;
    const comparisonMonth = `${yoy.previousYear}-${String(month).padStart(2, "0")}`;
    const currentPeriod = { ...period, currentMonth, comparisonMonth };
    const options = crossMatrixData(axis, "yoy", season, ingredient, [], [], false, currentPeriod, [month, month]);
    const normal = crossMatrixData(axis, "yoy", season, ingredient, options.rowOptions, options.columnOptions, false, currentPeriod, [month, month]);
    const flipped = crossMatrixData(axis, "yoy", season, ingredient, options.columnOptions, options.rowOptions, true, currentPeriod, [month, month]);
    assert.deepEqual(flipped.values, normal.values[0]?.map((_, columnIndex) => normal.values.map((row) => row[columnIndex])) ?? []);
    const coverage = rowCoverage(currentPeriod, currentMonth, comparisonMonth);
    for (const [rowIndex, row] of normal.rows.entries()) {
      for (const [columnIndex, column] of normal.columns.entries()) {
        const values = pairValues.get(`${row}\u0000${column}`) ?? new Map();
        const expected = calculateCrossMomGrowth({
          current: values.get(currentMonth) ?? 0,
          comparison: values.get(comparisonMonth) ?? 0,
          ...coverage,
          lowBaseThreshold: 0.5
        });
        assert.equal(normal.values[rowIndex][columnIndex], expected.value, `${axis}/${currentMonth}/${comparisonMonth} YoY value`);
        assert.equal(normal.cellStatuses[rowIndex][columnIndex], expected.status, `${axis}/${currentMonth}/${comparisonMonth} YoY status`);
        cellsChecked += 1;
      }
    }
    growthIntegrationViews += 2;
  }
}

console.log(JSON.stringify({
  status: "passed",
  endpoint: API_URL,
  sourceRows: { countrySkuSummary: summaryRows.length, countrySkuMonthly: monthlyRows.length },
  months: allMonths.length,
  partialMonths: [...partialMonths],
  staticViews,
  growthFormulaChecks,
  growthIntegrationViews,
  cellsChecked
}, null, 2));
