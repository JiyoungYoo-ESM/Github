import assert from "node:assert/strict";

import { buildCrossSummaryCards } from "../components/redesign/screens/cross/crossAnalysisSummaryModel.ts";
import { allocateCrossMatrixShares } from "../lib/cross-analysis-share.ts";

function matrix(values, cellPresence = values.map((row) => row.map((value) => value !== null))) {
  const rows = values.map((_, index) => `R${index + 1}`);
  const columns = values[0].map((_, index) => `C${index + 1}`);
  return {
    rowLabel: "행",
    columnLabel: "열",
    totalLabel: "합계",
    columns,
    rows,
    rowOptions: rows,
    columnOptions: columns,
    filteredRowOptions: rows,
    filteredColumnOptions: columns,
    values,
    cellPresence,
    cellStatuses: values.map((row) => row.map(() => null)),
    growthRowTotals: rows.map(() => null),
    growthRowTotalStatuses: rows.map(() => null),
    shareTieBreakKeys: values.map((row, rowIndex) =>
      row.map((_, columnIndex) => `${rowIndex}-${columnIndex}`)
    )
  };
}

function cards(selected, metric, scale = "amount") {
  return buildCrossSummaryCards({
    selected,
    metric,
    scale,
    shareAllocation: allocateCrossMatrixShares(
      selected.values,
      1,
      selected.shareTieBreakKeys
    )
  });
}

const allDecline = cards(matrix([[-5, -20]]), "mom");
assert.equal(allDecline[0].value, "-");
assert.equal(allDecline[0].sub, "성장 조합 없음");
assert.equal(allDecline[1].value, "-20%");
assert.match(allDecline[1].sub, /C2$/);

const allGrowth = cards(matrix([[5, 20]]), "mom");
assert.equal(allGrowth[0].value, "+20%");
assert.match(allGrowth[0].sub, /C2$/);
assert.equal(allGrowth[1].value, "-");
assert.equal(allGrowth[1].sub, "감소 조합 없음");

const screenshotCase = cards(matrix([[5, -97, -25]]), "mom");
assert.equal(screenshotCase[0].value, "+5%");
assert.equal(screenshotCase[1].value, "-97%");
assert.equal(screenshotCase[0].label, "가장 많이 증가");
assert.equal(screenshotCase[1].label, "가장 많이 감소");
assert.equal(screenshotCase[2].label, "증가한 조합");
assert.equal(screenshotCase[2].value, "1개");
assert.equal(screenshotCase[2].sub, "비교 가능한 3개 중 1개 증가 (33.3%)");
assert.equal(screenshotCase[3].label, "비교 가능한 조합");
assert.equal(screenshotCase[3].value, "3개 / 3개");
assert.equal(screenshotCase[3].sub, "전체 3개 조합 중 3개 비교 가능 (100%)");

const realZeroAndMissing = cards(
  matrix([[0, 0]], [[true, false]]),
  "sales"
);
assert.notEqual(realZeroAndMissing[2].value, "-");
assert.equal(realZeroAndMissing[3].value, "1개 / 2개");

const offsetting = matrix([[100, -100]], [[true, true]]);
const offsettingShare = cards(offsetting, "sales", "share");
assert.equal(offsettingShare[0].value, "-");
assert.match(offsettingShare[0].sub, /비중 계산 불가/);
assert.equal(offsettingShare[1].value, "-");
assert.match(offsettingShare[1].sub, /계산 불가/);
assert.equal(offsettingShare[3].value, "2개 / 2개");

const negativeTotal = cards(matrix([[-10]], [[true]]), "sales");
assert.notEqual(negativeTotal[2].value, "-");
assert.equal(negativeTotal[3].value, "1개 / 1개");

console.log("Cross-analysis summary checks passed.");
