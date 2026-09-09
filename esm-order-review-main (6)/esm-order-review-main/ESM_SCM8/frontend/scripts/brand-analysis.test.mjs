import assert from "node:assert/strict";

import {
  buildCalendarMonthAverageProfile,
  buildCalendarMonthShareProfile,
  buildTopSkuConcentration,
  completeSeasonalityMonthKeys
} from "../lib/brand-analysis.ts";

const skuResult = buildTopSkuConcentration([
  { sku: "A", name: "A", category: "Skin", amount: 200, qty: 2 },
  { sku: "B", name: "B", category: "Skin", amount: 150, qty: 2 },
  { sku: "C", name: "C", category: "Skin", amount: 100, qty: 2 },
  { sku: "D", name: "D", category: "Skin", amount: 30, qty: 2 },
  { sku: "E", name: "E", category: "Skin", amount: 20, qty: 2 },
  { sku: "F", name: "F", category: "Skin", amount: 500, qty: 2 }
]);

assert.equal(skuResult.totalAmount, 1_000, "SKU concentration denominator must include every brand SKU");
assert.equal(skuResult.topAmount, 980);
assert.equal(skuResult.rows[0].sku, "F");
assert.equal(skuResult.rows[0].sharePct, 50);
assert.equal(skuResult.rows.reduce((sum, row) => sum + row.sharePct, 0), 98);

const wholeBrandResult = buildTopSkuConcentration(skuResult.rows, 5, 1_100);
assert.equal(wholeBrandResult.totalAmount, 1_100, "Unmapped SKU sales must remain in the whole-brand denominator");
assert.ok(Math.abs(wholeBrandResult.rows.reduce((sum, row) => sum + row.sharePct, 0) - (980 / 1_100) * 100) < 1e-10);

const coverage = [
  { month: "2024-07", status: "complete" },
  { month: "2025-07", status: "complete" },
  { month: "2024-08", status: "complete" },
  { month: "2025-08", status: "partial" }
];
const eligible = completeSeasonalityMonthKeys(coverage, ["2024-07", "2025-07", "2024-08", "2025-08"]);
assert.deepEqual([...eligible].sort(), ["2024-07", "2024-08", "2025-07"]);

const profile = buildCalendarMonthAverageProfile({
  rows: [
    { month: "2024-07", amount: 100 },
    { month: "2025-07", amount: 300 },
    { month: "2024-08", amount: 50 },
    { month: "2025-08", amount: 5_000 }
  ],
  calendarMonths: [7, 8],
  eligibleMonthKeys: eligible,
  monthKey: (row) => row.month,
  amount: (row) => row.amount
});

assert.deepEqual(profile, [
  { month: 7, amount: 200, observationCount: 2 },
  { month: 8, amount: 50, observationCount: 1 }
]);

const zeroFilledProfile = buildCalendarMonthAverageProfile({
  rows: [{ month: "2024-07", amount: 100 }],
  calendarMonths: [7],
  eligibleMonthKeys: eligible,
  monthKey: (row) => row.month,
  amount: (row) => row.amount
});
assert.deepEqual(zeroFilledProfile, [{ month: 7, amount: 50, observationCount: 2 }]);

const missingMonthProfile = buildCalendarMonthAverageProfile({
  rows: [{ month: "2024-07", amount: 100 }],
  calendarMonths: [7, 8],
  eligibleMonthKeys: ["2024-07"],
  monthKey: (row) => row.month,
  amount: (row) => row.amount
});
assert.deepEqual(missingMonthProfile, [
  { month: 7, amount: 100, observationCount: 1 },
  { month: 8, amount: 0, observationCount: 0 }
]);

const shareProfile = buildCalendarMonthShareProfile([
  ...missingMonthProfile,
  { month: 9, amount: 0, observationCount: 1 }
]);
assert.equal(shareProfile[0].share, 100);
assert.equal(shareProfile[1].share, null, "Missing months must not become 0% shares");
assert.equal(shareProfile[2].share, 0, "Observed zero-sales months remain 0% shares");

console.log("Brand analysis regression tests passed: SKU whole-brand denominator and complete-month calendar averages.");
