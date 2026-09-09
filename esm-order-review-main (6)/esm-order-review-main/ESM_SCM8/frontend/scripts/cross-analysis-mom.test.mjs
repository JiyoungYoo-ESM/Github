import assert from "node:assert/strict";

import {
  CROSS_GROWTH_AXES,
  analysisMonthKeys,
  buildCrossGrowthMatrix,
  calculateAggregateCrossGrowth,
  calculateCrossMomGrowth,
  classifyCrossMonthPair,
  crossGrowthDimensions,
  orderedDistinctMonthPairs,
  nearestAvailableMonth
} from "../lib/cross-analysis-mom.ts";

assert.deepEqual(analysisMonthKeys("2025-01-01", "2025-05-31", true), [
  "2025-01",
  "2025-02",
  "2025-03",
  "2025-04",
  "2025-05"
]);
assert.deepEqual(analysisMonthKeys("2025-01-15", "2025-05-10", true), ["2025-02", "2025-03", "2025-04"]);

assert.deepEqual(
  calculateCrossMomGrowth({
    current: 0,
    comparison: 100,
    currentMonthAvailable: false,
    comparisonMonthAvailable: true,
    lowBaseThreshold: 0.5
  }),
  { value: null, status: "current_month_missing" }
);
assert.deepEqual(
  calculateCrossMomGrowth({
    current: 0,
    comparison: 100,
    currentMonthAvailable: true,
    comparisonMonthAvailable: true,
    lowBaseThreshold: 0.5
  }),
  { value: -100, status: "ok" }
);
assert.deepEqual(
  calculateCrossMomGrowth({
    current: 100,
    comparison: 90,
    currentMonthAvailable: true,
    comparisonMonthAvailable: true,
    currentMonthPartial: true,
    lowBaseThreshold: 0.5
  }),
  { value: null, status: "current_month_partial" }
);
assert.deepEqual(
  calculateCrossMomGrowth({
    current: 100,
    comparison: 90,
    currentMonthAvailable: true,
    comparisonMonthAvailable: true,
    comparisonMonthPartial: true,
    lowBaseThreshold: 0.5
  }),
  { value: null, status: "comparison_month_partial" }
);
assert.deepEqual(
  calculateCrossMomGrowth({
    current: 100,
    comparison: 0,
    currentMonthAvailable: true,
    comparisonMonthAvailable: true,
    lowBaseThreshold: 0.5
  }),
  { value: null, status: "zero_base" }
);
assert.equal(nearestAvailableMonth("2025-05", ["2025-04", "2025-06"]), "2025-04");

// 상태는 전역 기간 상태를 먼저, 셀의 기저 상태를 나중에 판정한다.
// current missing > comparison missing > current partial > comparison partial > zero > low-base > ok
const expectedStatus = ({
  currentMonthAvailable,
  comparisonMonthAvailable,
  currentMonthPartial,
  comparisonMonthPartial,
  comparison,
  lowBaseThreshold
}) => {
  if (!currentMonthAvailable) return "current_month_missing";
  if (!comparisonMonthAvailable) return "comparison_month_missing";
  if (currentMonthPartial) return "current_month_partial";
  if (comparisonMonthPartial) return "comparison_month_partial";
  if (!Number.isFinite(comparison) || comparison <= 0) return "zero_base";
  if (comparison < lowBaseThreshold) return "low_base";
  return "ok";
};

for (const currentMonthAvailable of [false, true]) {
  for (const comparisonMonthAvailable of [false, true]) {
    for (const currentMonthPartial of [false, true]) {
      for (const comparisonMonthPartial of [false, true]) {
        for (const comparison of [Number.NaN, -1, 0, 0.25, 0.5, 2]) {
          const input = {
            current: 3,
            comparison,
            currentMonthAvailable,
            comparisonMonthAvailable,
            currentMonthPartial,
            comparisonMonthPartial,
            lowBaseThreshold: 0.5
          };
          const result = calculateCrossMomGrowth(input);
          assert.equal(result.status, expectedStatus(input));
          if (result.status === "ok") {
            assert.equal(result.value, Math.round(((input.current - comparison) / comparison) * 100));
          } else {
            assert.equal(result.value, null);
          }
        }
      }
    }
  }
}

// 모든 서로 다른 월 쌍은 순서를 보존한다. 역순은 별도 비교이며 같은 달은 허용하지 않는다.
const months = ["2024-12", "2025-01", "2025-03", "2025-06", "2025-09"];
const orderedPairs = orderedDistinctMonthPairs([...months, "2025-03", "invalid"]);
assert.equal(orderedPairs.length, months.length * (months.length - 1));
assert.equal(new Set(orderedPairs.map(({ currentMonth, comparisonMonth }) => `${currentMonth}|${comparisonMonth}`)).size, orderedPairs.length);
assert.ok(orderedPairs.every(({ currentMonth, comparisonMonth }) => currentMonth !== comparisonMonth));
assert.deepEqual(classifyCrossMonthPair("2025-01", "2024-12"), {
  valid: true,
  distance: 1,
  reverse: false,
  adjacent: true,
  kind: "mom"
});
assert.deepEqual(classifyCrossMonthPair("2025-03", "2025-01"), {
  valid: true,
  distance: 2,
  reverse: false,
  adjacent: false,
  kind: "month_comparison"
});
assert.deepEqual(classifyCrossMonthPair("2025-01", "2025-03"), {
  valid: true,
  distance: -2,
  reverse: true,
  adjacent: false,
  kind: "month_comparison"
});
assert.equal(classifyCrossMonthPair("2025-03", "2025-03").valid, false);

// 월 쌍을 임의 순서로 선택해도 이전 선택 상태가 계산에 섞이지 않아야 한다.
function seededShuffle(items, seed = 0x51f15e) {
  const shuffled = [...items];
  let state = seed >>> 0;
  const random = () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 2 ** 32;
  };
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const target = Math.floor(random() * (index + 1));
    [shuffled[index], shuffled[target]] = [shuffled[target], shuffled[index]];
  }
  return shuffled;
}

const randomizedPairs = seededShuffle(orderedPairs);
assert.notDeepEqual(randomizedPairs, orderedPairs);
assert.deepEqual(
  [...randomizedPairs].map((pair) => `${pair.currentMonth}|${pair.comparisonMonth}`).sort(),
  [...orderedPairs].map((pair) => `${pair.currentMonth}|${pair.comparisonMonth}`).sort()
);

const dimensionRows = [
  { country: "C1", brand: "B1", sku: "S1", ingredient: "I1", factor: 1 },
  { country: "C1", brand: "B2", sku: "S2", ingredient: "I2", factor: 2 },
  { country: "C2", brand: "B1", sku: "S2", ingredient: "I2", factor: 3 },
  { country: "C2", brand: "B2", sku: "S1", ingredient: "I1", factor: 4 }
];
const sourceRows = months.flatMap((month, monthIndex) =>
  dimensionRows.map(({ factor, ...dimensions }) => ({
    ...dimensions,
    month,
    value: factor * 100 + monthIndex * (factor * factor * 7)
  }))
);
const availableMonths = new Set(months);
const sourceTotal = (dimension, label, month, otherDimension, otherLabel) =>
  sourceRows
    .filter(
      (row) =>
        row.month === month &&
        row[dimension] === label &&
        row[otherDimension] === otherLabel
    )
    .reduce((sum, row) => sum + row.value, 0);

let auditedMatrixCount = 0;
for (const { currentMonth, comparisonMonth } of randomizedPairs) {
  for (const axis of CROSS_GROWTH_AXES) {
    const normal = buildCrossGrowthMatrix({
      sourceRows,
      axis,
      currentMonth,
      comparisonMonth,
      availableMonths,
      lowBaseThreshold: 0.5
    });
    const flipped = buildCrossGrowthMatrix({
      sourceRows,
      axis,
      flipped: true,
      currentMonth,
      comparisonMonth,
      availableMonths,
      lowBaseThreshold: 0.5
    });
    const dimensions = crossGrowthDimensions(axis);

    for (const cell of normal.cells) {
      const current = sourceTotal(dimensions.row, cell.row, currentMonth, dimensions.column, cell.column);
      const comparison = sourceTotal(dimensions.row, cell.row, comparisonMonth, dimensions.column, cell.column);
      assert.equal(cell.current, current);
      assert.equal(cell.comparison, comparison);
      assert.equal(cell.status, comparison > 0 ? "ok" : "zero_base");
      assert.equal(cell.value, comparison > 0 ? Math.round(((current - comparison) / comparison) * 100) : null);

      const transposed = flipped.cells.find((candidate) => candidate.row === cell.column && candidate.column === cell.row);
      assert.ok(transposed, `${axis} 전환 후 ${cell.column} × ${cell.row} 셀이 없습니다.`);
      assert.deepEqual(
        { current: transposed.current, comparison: transposed.comparison, value: transposed.value, status: transposed.status },
        { current: cell.current, comparison: cell.comparison, value: cell.value, status: cell.status }
      );
    }
    auditedMatrixCount += 2;
  }
}
assert.equal(auditedMatrixCount, orderedPairs.length * CROSS_GROWTH_AXES.length * 2);

const singleDimensionRows = (currentValue, comparisonValue) => [
  { country: "C", brand: "B", sku: "S", ingredient: "I", month: "2025-06", value: currentValue },
  { country: "C", brand: "B", sku: "S", ingredient: "I", month: "2025-03", value: comparisonValue }
];
const coverageCases = [
  { availableMonths: new Set(["2025-03"]), partialMonths: new Set(), current: 1, comparison: 1, expected: "current_month_missing" },
  { availableMonths: new Set(["2025-06"]), partialMonths: new Set(), current: 1, comparison: 1, expected: "comparison_month_missing" },
  { availableMonths: new Set(["2025-06", "2025-03"]), partialMonths: new Set(["2025-06"]), current: 1, comparison: 1, expected: "current_month_partial" },
  { availableMonths: new Set(["2025-06", "2025-03"]), partialMonths: new Set(["2025-03"]), current: 1, comparison: 1, expected: "comparison_month_partial" },
  { availableMonths: new Set(["2025-06", "2025-03"]), partialMonths: new Set(), current: 1, comparison: 0, expected: "zero_base" },
  { availableMonths: new Set(["2025-06", "2025-03"]), partialMonths: new Set(), current: 1, comparison: 0.25, expected: "low_base" },
  { availableMonths: new Set(["2025-06", "2025-03"]), partialMonths: new Set(), current: 1, comparison: 0.5, expected: "ok" }
];

for (const axis of CROSS_GROWTH_AXES) {
  for (const flipped of [false, true]) {
    for (const coverageCase of coverageCases) {
      const matrix = buildCrossGrowthMatrix({
        sourceRows: singleDimensionRows(coverageCase.current, coverageCase.comparison),
        axis,
        flipped,
        currentMonth: "2025-06",
        comparisonMonth: "2025-03",
        availableMonths: coverageCase.availableMonths,
        partialMonths: coverageCase.partialMonths,
        lowBaseThreshold: 0.5
      });
      assert.equal(matrix.cells[0].status, coverageCase.expected);
      assert.equal(matrix.rowTotals[0].status, coverageCase.expected);
      assert.equal(matrix.columnTotals[0].status, coverageCase.expected);
      assert.equal(matrix.grandTotal.status, coverageCase.expected);
    }
  }
}

// 역순은 부호만 바꾸는 계산이 아니다: +100%의 역비교는 -50%다.
assert.equal(
  calculateCrossMomGrowth({ current: 200, comparison: 100, currentMonthAvailable: true, comparisonMonthAvailable: true, lowBaseThreshold: 0.5 }).value,
  100
);
assert.equal(
  calculateCrossMomGrowth({ current: 100, comparison: 200, currentMonthAvailable: true, comparisonMonthAvailable: true, lowBaseThreshold: 0.5 }).value,
  -50
);

// 행/열 합계는 셀 성장률 평균이 아니라 금액을 합친 뒤 한 번 계산해야 한다.
const aggregate = calculateAggregateCrossGrowth(
  [
    { current: 20, comparison: 10 },
    { current: 500, comparison: 1000 }
  ],
  { currentMonthAvailable: true, comparisonMonthAvailable: true, lowBaseThreshold: 0.5 }
);
assert.deepEqual(aggregate, { current: 520, comparison: 1010, value: -49, status: "ok" });
assert.notEqual(aggregate.value, Math.round((100 + -50) / 2));
assert.deepEqual(
  calculateAggregateCrossGrowth(
    [
      { current: 100, comparison: 100 },
      { current: -20, comparison: -10 }
    ],
    { currentMonthAvailable: true, comparisonMonthAvailable: true, lowBaseThreshold: 0.5 }
  ),
  { current: 80, comparison: 90, value: -11, status: "ok" }
);
assert.deepEqual(
  calculateAggregateCrossGrowth(
    [
      { current: 0.6, comparison: 0.3 },
      { current: 0.6, comparison: 0.3 }
    ],
    { currentMonthAvailable: true, comparisonMonthAvailable: true, lowBaseThreshold: 0.5 }
  ),
  { current: 1.2, comparison: 0.6, value: 100, status: "ok" }
);

for (const axis of CROSS_GROWTH_AXES) {
  for (const flipped of [false, true]) {
    const dimensions = crossGrowthDimensions(axis, flipped);
    const aggregateRows = [];
    for (const [column, current, comparison] of [
      ["A", 20, 10],
      ["B", 500, 1000]
    ]) {
      const base = { country: "fixed-country", brand: "fixed-brand", sku: "fixed-sku", ingredient: "fixed-ingredient" };
      base[dimensions.row] = "R";
      base[dimensions.column] = column;
      aggregateRows.push({ ...base, month: "2025-03", value: current });
      aggregateRows.push({ ...base, month: "2024-03", value: comparison });
    }
    const matrix = buildCrossGrowthMatrix({
      sourceRows: aggregateRows,
      axis,
      flipped,
      currentMonth: "2025-03",
      comparisonMonth: "2024-03",
      availableMonths: new Set(["2025-03", "2024-03"]),
      lowBaseThreshold: 0.5
    });
    assert.deepEqual(
      { current: matrix.rowTotals[0].current, comparison: matrix.rowTotals[0].comparison, value: matrix.rowTotals[0].value, status: matrix.rowTotals[0].status },
      { current: 520, comparison: 1010, value: -49, status: "ok" }
    );
    assert.equal(matrix.cells.reduce((sum, cell) => sum + cell.value, 0) / matrix.cells.length, 25);
  }
}

assert.throws(
  () =>
    buildCrossGrowthMatrix({
      sourceRows,
      axis: "country-brand",
      currentMonth: "2025-03",
      comparisonMonth: "2025-03",
      lowBaseThreshold: 0.5
    }),
  /서로 다른/
);

console.log(`Cross-analysis YoY/MoM checks passed (${auditedMatrixCount} axis/pair/orientation matrices).`);
