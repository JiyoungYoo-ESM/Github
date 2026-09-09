import assert from "node:assert/strict";

import { allocateCrossMatrixShares } from "../lib/cross-analysis-share.ts";

const ukExample = [[61.06128991, 12.4500161, 9.37421815, 0.00799805, 3.26019567, 5.65449932, 0.77980763, 6.7112505, 0.70072468]];
const ukAllocation = allocateCrossMatrixShares(ukExample);
assert.equal(ukAllocation.values.flat().reduce((sum, value) => sum + (value ?? 0), 0), 100);
assert.deepEqual(ukAllocation.rowTotals, [100]);
assert.equal(ukAllocation.calculable, true);

const multiCountry = allocateCrossMatrixShares([
  [60, 20],
  [15, 5]
]);
assert.deepEqual(multiCountry.values, [
  [60, 20],
  [15, 5]
]);
assert.deepEqual(multiCountry.rowTotals, [80, 20]);
assert.equal(multiCountry.rowTotals.reduce((sum, value) => sum + value, 0), 100);

const roundingStress = allocateCrossMatrixShares([[...Array(40).fill(2.051), 17.96]]);
assert.equal(Number(roundingStress.values.flat().reduce((sum, value) => sum + (value ?? 0), 0).toFixed(1)), 100);
assert.deepEqual(roundingStress.rowTotals, [100]);

const empty = allocateCrossMatrixShares([[null, 0]]);
assert.deepEqual(empty.values, [[null, 0]]);
assert.deepEqual(empty.rowTotals, [0]);
assert.equal(empty.calculable, false);

const returnsIncluded = allocateCrossMatrixShares([[80, 40, -20]], 1, [["a", "b", "c"]]);
assert.deepEqual(returnsIncluded.values, [[80, 40, -20]]);
assert.equal(returnsIncluded.values.flat().reduce((sum, value) => sum + (value ?? 0), 0), 100);
assert.equal(returnsIncluded.calculable, true);

const offsettingReturns = allocateCrossMatrixShares([[100, -100]]);
assert.equal(offsettingReturns.calculable, false);
assert.deepEqual(offsettingReturns.values, [[0, 0]]);
assert.deepEqual(offsettingReturns.rowTotals, [0]);

console.log("Cross-analysis share checks passed.");
