import assert from "node:assert/strict";

import {
  comparableQuarterKeys,
  completeQuarterKeys,
  formatQuarterLabel,
  monthsForQuarter,
  previousQuarterKey,
  previousYearQuarterKey,
  quarterKeyFromMonthKey
} from "../components/redesign/screens/country/country-quarter-growth.ts";

assert.equal(quarterKeyFromMonthKey("2024-01"), "2024-Q1");
assert.equal(quarterKeyFromMonthKey("2024-12"), "2024-Q4");
assert.equal(quarterKeyFromMonthKey("2024-13"), "");
assert.deepEqual(monthsForQuarter("2024-Q4"), ["2024-10", "2024-11", "2024-12"]);
assert.equal(previousQuarterKey("2024-Q1"), "2023-Q4");
assert.equal(previousQuarterKey("2024-Q4"), "2024-Q3");
assert.equal(previousYearQuarterKey("2024-Q4"), "2023-Q4");
assert.equal(formatQuarterLabel("2024-Q4"), "2024년 4분기");

const completeMonths = [
  "2023-10", "2023-11", "2023-12",
  "2024-01", "2024-02", "2024-03",
  "2024-04", "2024-05", "2024-06",
  "2024-07", "2024-08", "2024-09",
  "2024-10", "2024-11"
];
const quarters = completeQuarterKeys(completeMonths);
assert.deepEqual(quarters, ["2023-Q4", "2024-Q1", "2024-Q2", "2024-Q3"], "부분 분기인 2024-Q4는 제외해야 함");
assert.deepEqual(
  comparableQuarterKeys(quarters, "qoq"),
  ["2024-Q1", "2024-Q2", "2024-Q3"],
  "직전 완료 분기가 있는 분기만 QoQ 대상이어야 함"
);
assert.deepEqual(
  comparableQuarterKeys(quarters, "yoy"),
  [],
  "전년 동일 분기가 없으면 YoY 대상이 없어야 함"
);

const yoyQuarters = completeQuarterKeys([
  ...completeMonths,
  "2022-10", "2022-11", "2022-12"
]);
assert.deepEqual(
  comparableQuarterKeys(yoyQuarters, "yoy"),
  ["2023-Q4"],
  "전년 동일 분기가 있는 분기만 YoY 대상이어야 함"
);

console.log("Country quarter growth checks passed.");
