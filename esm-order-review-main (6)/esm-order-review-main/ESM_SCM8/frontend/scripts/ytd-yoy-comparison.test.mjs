import assert from "node:assert/strict";

import {
  automaticComparisonBasis,
  completedYtdComparableYearWindow,
  completedYtdPeriodLabel,
  ytdAmountComparisonsByLabel
} from "../components/redesign/lib/yoy-comparison.ts";

assert.equal(automaticComparisonBasis("2025-07-01", "2026-07-01"), "yoy");
assert.equal(automaticComparisonBasis("2026-01-01", "2026-12-01"), "mom");

const rows = [
  { month: "2025-01", brand: "A", amount: 100 },
  { month: "2025-02", brand: "A", amount: 200 },
  { month: "2025-03", brand: "A", amount: 9_999 },
  { month: "2026-01", brand: "A", amount: 150 },
  { month: "2026-02", brand: "A", amount: 300 },
  { month: "2026-03", brand: "A", amount: 50_000 },
  { month: "2025-01", brand: "NEW", amount: 0 },
  { month: "2025-02", brand: "NEW", amount: 0 },
  { month: "2026-01", brand: "NEW", amount: 40 },
  { month: "2026-02", brand: "NEW", amount: 60 }
];
const completeMonths = new Set([
  "2025-01",
  "2025-02",
  "2025-03",
  "2026-01",
  "2026-02"
]);

const window = completedYtdComparableYearWindow(rows, completeMonths);
assert.ok(window);
assert.equal(window.latestYear, 2026);
assert.equal(window.previousYear, 2025);
assert.deepEqual([...window.months], [1, 2], "부분 적재된 3월은 완료월 YTD에서 제외해야 합니다.");
assert.equal(completedYtdPeriodLabel(window), "YTD · 2026년 1~2월 vs 2025년 1~2월");

const comparisons = ytdAmountComparisonsByLabel(rows, window, (row) => String(row.brand), 50);
assert.equal(comparisons.get("A")?.currentAmount, 450);
assert.equal(comparisons.get("A")?.previousAmount, 300);
assert.equal(comparisons.get("A")?.growth, "+50%");
assert.equal(comparisons.get("NEW")?.growth, "신규");

const missingJanuary = completedYtdComparableYearWindow(
  rows.filter((row) => row.month !== "2026-01"),
  new Set(["2025-01", "2025-02", "2026-02"])
);
assert.equal(missingJanuary, null, "1월부터 연속되지 않은 기간을 YTD로 표시하면 안 됩니다.");

const latestYearOnlyPartial = completedYtdComparableYearWindow(
  [
    { month: "2024-01", amount: 100 },
    { month: "2025-01", amount: 120 },
    { month: "2026-01", amount: 140 }
  ],
  new Set(["2024-01", "2025-01"])
);
assert.equal(latestYearOnlyPartial, null, "최신 연도가 미완료이면 과거 두 해를 최신 YTD처럼 표시하면 안 됩니다.");

console.log("Completed-month YTD YoY checks passed.");
