import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

import { allocateCrossMatrixShares } from "../../frontend/lib/cross-analysis-share.ts";
import {
  crossDimensionValue,
  crossMatrixData,
  sourceRowsForCrossAxis
} from "../../frontend/lib/cross-analysis-matrix.ts";
import { calculateCrossMomGrowth } from "../../frontend/lib/cross-analysis-mom.ts";
import { amountOf, monthKeyOf, qtyOf } from "../../frontend/lib/global-demand-view-model.ts";

const [primarySnapshotArg, ytdSnapshotArg, outputArg] = process.argv.slice(2);
assert.ok(primarySnapshotArg && ytdSnapshotArg && outputArg, "usage: node matrix_snapshot_backtest.mjs PRIMARY YTD OUTPUT");

const primarySnapshotPath = path.resolve(primarySnapshotArg);
const ytdSnapshotPath = path.resolve(ytdSnapshotArg);
const outputPath = path.resolve(outputArg);
const primaryPayload = JSON.parse(fs.readFileSync(primarySnapshotPath, "utf8"));
const ytdPayload = JSON.parse(fs.readFileSync(ytdSnapshotPath, "utf8"));

const AXES = ["country-brand", "country-sku", "brand-sku"];
const STATIC_METRICS = ["sales", "quantity"];
const LOW_BASE_THOUSAND_EUR = 0.5;

function assertClose(actual, expected, message, tolerance = 1e-7) {
  assert.ok(Number.isFinite(actual), `${message}: actual is not finite (${actual})`);
  assert.ok(Math.abs(actual - expected) <= tolerance, `${message}: ${actual} !== ${expected}`);
}

function previousMonth(monthKey) {
  const [year, month] = monthKey.split("-").map(Number);
  const date = new Date(year, month - 2, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function monthsInclusive(startDate, endDate) {
  const [startYear, startMonth] = startDate.slice(0, 7).split("-").map(Number);
  const [endYear, endMonth] = endDate.slice(0, 7).split("-").map(Number);
  const result = [];
  let year = startYear;
  let month = startMonth;
  while (year < endYear || (year === endYear && month <= endMonth)) {
    result.push(`${year}-${String(month).padStart(2, "0")}`);
    month += 1;
    if (month === 13) {
      year += 1;
      month = 1;
    }
  }
  return result;
}

function dimensionsFor(axis) {
  return {
    "country-brand": ["country", "brand"],
    "country-sku": ["country", "sku"],
    "brand-sku": ["brand", "sku"]
  }[axis];
}

function sourcePairTotals(rows, axis, metric, allowedRows, allowedColumns) {
  const [rowDimension, columnDimension] = dimensionsFor(axis);
  const totals = new Map();
  for (const source of rows) {
    const row = crossDimensionValue(source, rowDimension);
    const column = crossDimensionValue(source, columnDimension);
    if (!allowedRows.has(row) || !allowedColumns.has(column)) continue;
    const value = metric === "quantity" ? qtyOf(source) / 10_000 : amountOf(source) / 1_000;
    const key = `${row}\u0000${column}`;
    totals.set(key, (totals.get(key) ?? 0) + value);
  }
  return totals;
}

function monthlyPairTotals(rows, axis, allowedRows, allowedColumns) {
  const [rowDimension, columnDimension] = dimensionsFor(axis);
  const totals = new Map();
  for (const source of rows) {
    const row = crossDimensionValue(source, rowDimension);
    const column = crossDimensionValue(source, columnDimension);
    const month = monthKeyOf(source);
    if (!allowedRows.has(row) || !allowedColumns.has(column) || !/^\d{4}-\d{2}$/.test(month)) continue;
    const key = `${row}\u0000${column}`;
    const periods = totals.get(key) ?? new Map();
    periods.set(month, (periods.get(month) ?? 0) + amountOf(source) / 1_000);
    totals.set(key, periods);
  }
  return totals;
}

function coverageModel(payload) {
  const season = payload.season_analysis;
  const coverageRows = season.monthCoverage ?? [];
  const observed = new Set((season.countrySkuMonthly ?? []).map(monthKeyOf).filter((value) => /^\d{4}-\d{2}$/.test(value)));
  const partial = new Set(coverageRows.filter((row) => row.status === "partial").map((row) => String(row.month)));
  const complete = new Set(coverageRows.filter((row) => row.status === "complete").map((row) => String(row.month)));
  const expected = new Set(monthsInclusive(payload.analysis_options.start_date, payload.analysis_options.end_date));
  return { coverageRows, observed, partial, complete, expected };
}

function assertMatrixCell(matrix, rowIndex, columnIndex, expected, message) {
  assert.equal(matrix.cellStatuses[rowIndex][columnIndex], expected.status, `${message}: status`);
  assert.equal(matrix.values[rowIndex][columnIndex], expected.value, `${message}: value`);
}

function growthCardRisk(values) {
  const valid = values.flat().filter((value) => typeof value === "number" && Number.isFinite(value));
  return {
    validCells: valid.length,
    positiveCells: valid.filter((value) => value > 0).length,
    negativeCells: valid.filter((value) => value < 0).length,
    zeroCells: valid.filter((value) => value === 0).length
  };
}

function addRisk(target, risk) {
  for (const key of Object.keys(risk)) target[key] += risk[key];
}

function validateStatic(payload) {
  const season = payload.season_analysis;
  const ingredient = payload.ingredient_analysis;
  const results = [];
  let cellsChecked = 0;
  for (const axis of AXES) {
    for (const metric of STATIC_METRICS) {
      const rows = sourceRowsForCrossAxis(axis, metric, season, ingredient);
      const options = crossMatrixData(axis, metric, season, ingredient);
      const matrix = crossMatrixData(
        axis,
        metric,
        season,
        ingredient,
        options.rowOptions,
        options.columnOptions
      );
      const rowSet = new Set(matrix.rows);
      const columnSet = new Set(matrix.columns);
      const expectedPairs = sourcePairTotals(rows, axis, metric, rowSet, columnSet);
      for (const [rowIndex, row] of matrix.rows.entries()) {
        for (const [columnIndex, column] of matrix.columns.entries()) {
          const expected = expectedPairs.get(`${row}\u0000${column}`) ?? 0;
          assertClose(matrix.values[rowIndex][columnIndex], expected, `${axis}/${metric}/${rowIndex}/${columnIndex}`);
          cellsChecked += 1;
        }
      }
      const matrixTotal = matrix.values.flat().reduce((sum, value) => sum + (value ?? 0), 0);
      const expectedTotal = Array.from(expectedPairs.values()).reduce((sum, value) => sum + value, 0);
      assertClose(matrixTotal, expectedTotal, `${axis}/${metric}/total`, 1e-6);

      const shares = allocateCrossMatrixShares(matrix.values, 1, matrix.shareTieBreakKeys);
      const shareTotal = shares.values.flat().reduce((sum, value) => sum + (value ?? 0), 0);
      assert.equal(Number(shareTotal.toFixed(1)), matrixTotal === 0 ? 0 : 100, `${axis}/${metric}/share-total`);
      const nonZeroCells = matrix.values.flat().filter((value) => typeof value === "number" && value !== 0).length;
      const zeroCells = matrix.values.flat().filter((value) => value === 0).length;
      const negativeCells = matrix.values.flat().filter((value) => typeof value === "number" && value < 0).length;
      results.push({
        axis,
        metric,
        rows: matrix.rows.length,
        columns: matrix.columns.length,
        cells: matrix.rows.length * matrix.columns.length,
        nonZeroCells,
        zeroCells,
        negativeCells,
        matrixTotal,
        shareTotal: Number(shareTotal.toFixed(1))
      });
    }
  }
  return { results, cellsChecked };
}

function validateMom(payload) {
  const season = payload.season_analysis;
  const ingredient = payload.ingredient_analysis;
  const coverage = coverageModel(payload);
  const result = [];
  const cardRisk = { validCells: 0, positiveCells: 0, negativeCells: 0, zeroCells: 0 };
  let cellsChecked = 0;
  let rowTotalsChecked = 0;
  for (const axis of AXES) {
    const sourceRows = sourceRowsForCrossAxis(axis, "mom", season, ingredient);
    const options = crossMatrixData(axis, "mom", season, ingredient);
    const allowedRows = new Set(options.rowOptions);
    const allowedColumns = new Set(options.columnOptions);
    const grouped = monthlyPairTotals(sourceRows, axis, allowedRows, allowedColumns);
    let axisViews = 0;
    let axisCells = 0;
    for (const currentMonth of coverage.expected) {
      const comparisonMonth = previousMonth(currentMonth);
      const period = {
        currentMonth,
        comparisonMonth,
        availableMonths: coverage.observed,
        partialMonths: coverage.partial,
        expectedMonths: coverage.expected
      };
      const matrix = crossMatrixData(
        axis,
        "mom",
        season,
        ingredient,
        options.rowOptions,
        options.columnOptions,
        false,
        period
      );
      const availability = {
        currentMonthAvailable: coverage.observed.has(currentMonth),
        comparisonMonthAvailable: coverage.observed.has(comparisonMonth),
        currentMonthPartial: coverage.partial.has(currentMonth),
        comparisonMonthPartial: coverage.partial.has(comparisonMonth),
        lowBaseThreshold: LOW_BASE_THOUSAND_EUR
      };
      for (const [rowIndex, row] of matrix.rows.entries()) {
        let rowCurrent = 0;
        let rowComparison = 0;
        for (const [columnIndex, column] of matrix.columns.entries()) {
          const periods = grouped.get(`${row}\u0000${column}`) ?? new Map();
          const current = periods.get(currentMonth) ?? 0;
          const comparison = periods.get(comparisonMonth) ?? 0;
          const expected = calculateCrossMomGrowth({ current, comparison, ...availability });
          assertMatrixCell(matrix, rowIndex, columnIndex, expected, `${axis}/mom/${currentMonth}/${rowIndex}/${columnIndex}`);
          rowCurrent += current;
          rowComparison += comparison;
          cellsChecked += 1;
          axisCells += 1;
        }
        const expectedRow = calculateCrossMomGrowth({
          current: rowCurrent,
          comparison: rowComparison,
          ...availability
        });
        assert.equal(matrix.growthRowTotals[rowIndex], expectedRow.value, `${axis}/mom/${currentMonth}/row-total/${rowIndex}`);
        assert.equal(matrix.growthRowTotalStatuses[rowIndex], expectedRow.status, `${axis}/mom/${currentMonth}/row-status/${rowIndex}`);
        rowTotalsChecked += 1;
      }
      addRisk(cardRisk, growthCardRisk(matrix.values));
      axisViews += 1;
    }
    result.push({ axis, monthViews: axisViews, cellsChecked: axisCells });
  }
  return { result, cellsChecked, rowTotalsChecked, cardRisk };
}

function completedYtdWindow(payload) {
  const coverage = coverageModel(payload);
  const years = Array.from(new Set(Array.from(coverage.observed).map((month) => Number(month.slice(0, 4))))).sort((a, b) => b - a);
  const latestYear = years[0];
  const previousYear = latestYear - 1;
  let latestCompleteMonth = 0;
  for (let month = 1; month <= 12; month += 1) {
    const suffix = String(month).padStart(2, "0");
    if (!coverage.complete.has(`${latestYear}-${suffix}`) || !coverage.complete.has(`${previousYear}-${suffix}`)) break;
    latestCompleteMonth = month;
  }
  return { ...coverage, latestYear, previousYear, latestCompleteMonth };
}

function validateYtd(payload) {
  const season = payload.season_analysis;
  const ingredient = payload.ingredient_analysis;
  const window = completedYtdWindow(payload);
  assert.ok(window.latestCompleteMonth > 0, "YTD snapshot has no completed comparable month");
  const result = [];
  const cardRisk = { validCells: 0, positiveCells: 0, negativeCells: 0, zeroCells: 0 };
  let cellsChecked = 0;
  let rowTotalsChecked = 0;
  for (const axis of AXES) {
    const sourceRows = sourceRowsForCrossAxis(axis, "yoy", season, ingredient);
    const options = crossMatrixData(axis, "yoy", season, ingredient);
    const allowedRows = new Set(options.rowOptions);
    const allowedColumns = new Set(options.columnOptions);
    const grouped = monthlyPairTotals(sourceRows, axis, allowedRows, allowedColumns);
    let axisCells = 0;
    for (let baseMonth = 1; baseMonth <= window.latestCompleteMonth; baseMonth += 1) {
      const period = {
        currentMonth: `${window.latestYear}-${String(baseMonth).padStart(2, "0")}`,
        comparisonMonth: `${window.previousYear}-${String(baseMonth).padStart(2, "0")}`,
        availableMonths: window.observed,
        partialMonths: window.partial,
        expectedMonths: window.expected
      };
      const matrix = crossMatrixData(
        axis,
        "yoy",
        season,
        ingredient,
        options.rowOptions,
        options.columnOptions,
        false,
        period,
        [1, baseMonth]
      );
      const selectedMonths = Array.from({ length: baseMonth }, (_, index) => index + 1);
      const availability = {
        currentMonthAvailable: selectedMonths.every((month) => window.observed.has(`${window.latestYear}-${String(month).padStart(2, "0")}`)),
        comparisonMonthAvailable: selectedMonths.every((month) => window.observed.has(`${window.previousYear}-${String(month).padStart(2, "0")}`)),
        currentMonthPartial: selectedMonths.some((month) => window.partial.has(`${window.latestYear}-${String(month).padStart(2, "0")}`)),
        comparisonMonthPartial: selectedMonths.some((month) => window.partial.has(`${window.previousYear}-${String(month).padStart(2, "0")}`)),
        lowBaseThreshold: LOW_BASE_THOUSAND_EUR
      };
      for (const [rowIndex, row] of matrix.rows.entries()) {
        let rowCurrent = 0;
        let rowComparison = 0;
        for (const [columnIndex, column] of matrix.columns.entries()) {
          const periods = grouped.get(`${row}\u0000${column}`) ?? new Map();
          const current = selectedMonths.reduce(
            (sum, month) => sum + (periods.get(`${window.latestYear}-${String(month).padStart(2, "0")}`) ?? 0),
            0
          );
          const comparison = selectedMonths.reduce(
            (sum, month) => sum + (periods.get(`${window.previousYear}-${String(month).padStart(2, "0")}`) ?? 0),
            0
          );
          const expected = calculateCrossMomGrowth({ current, comparison, ...availability });
          assertMatrixCell(matrix, rowIndex, columnIndex, expected, `${axis}/ytd/${baseMonth}/${rowIndex}/${columnIndex}`);
          rowCurrent += current;
          rowComparison += comparison;
          cellsChecked += 1;
          axisCells += 1;
        }
        const expectedRow = calculateCrossMomGrowth({
          current: rowCurrent,
          comparison: rowComparison,
          ...availability
        });
        assert.equal(matrix.growthRowTotals[rowIndex], expectedRow.value, `${axis}/ytd/${baseMonth}/row-total/${rowIndex}`);
        assert.equal(matrix.growthRowTotalStatuses[rowIndex], expectedRow.status, `${axis}/ytd/${baseMonth}/row-status/${rowIndex}`);
        rowTotalsChecked += 1;
      }
      addRisk(cardRisk, growthCardRisk(matrix.values));
    }
    result.push({
      axis,
      baseMonthViews: window.latestCompleteMonth,
      cellsChecked: axisCells
    });
  }
  return {
    latestYear: window.latestYear,
    previousYear: window.previousYear,
    latestCompleteMonth: window.latestCompleteMonth,
    result,
    cellsChecked,
    rowTotalsChecked,
    cardRisk
  };
}

const primaryStatic = validateStatic(primaryPayload);
const primaryMom = validateMom(primaryPayload);
const actualYtd = validateYtd(ytdPayload);
const report = {
  status: "passed",
  generatedAt: new Date().toISOString(),
  primarySnapshot: {
    path: primarySnapshotPath,
    savedAt: primaryPayload.saved_at,
    range: [primaryPayload.analysis_options.start_date, primaryPayload.analysis_options.end_date],
    sourceRows: primaryPayload.uploaded_files
  },
  ytdSnapshot: {
    path: ytdSnapshotPath,
    savedAt: ytdPayload.saved_at,
    range: [ytdPayload.analysis_options.start_date, ytdPayload.analysis_options.end_date],
    sourceRows: ytdPayload.uploaded_files
  },
  static: primaryStatic,
  mom: primaryMom,
  ytd: actualYtd,
  summaryRegressionCoverage: {
    positiveOnlySelections: primaryMom.cardRisk.positiveCells + actualYtd.cardRisk.positiveCells,
    negativeOnlySelections: primaryMom.cardRisk.negativeCells + actualYtd.cardRisk.negativeCells,
    zeroOnlySelections: primaryMom.cardRisk.zeroCells + actualYtd.cardRisk.zeroCells,
    expectedBehavior: "positive-only has no maximum decline; negative-only has no maximum growth; zero-only has neither"
  }
};

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify(report, null, 2));
