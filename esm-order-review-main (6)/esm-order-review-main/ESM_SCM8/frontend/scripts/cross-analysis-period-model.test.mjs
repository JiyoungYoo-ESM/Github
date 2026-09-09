import assert from "node:assert/strict";

import {
  buildCrossGrowthBasisLabel,
  buildCrossMonthCoverageModel,
  buildMomCoverageModel,
  buildYoyCoverageWarning,
  resolveMomPeriodDefaults
} from "../components/redesign/screens/cross/crossAnalysisPeriodModel.ts";

const coverage = [
  { month: "2025-01", status: "complete" },
  {
    month: "2025-02",
    status: "partial",
    reason: "월말 적재 대기",
    activeDays: 10,
    expectedBusinessDays: 20
  },
  { month: "2025-03", status: "missing" }
];

const monthModel = buildCrossMonthCoverageModel({
  axis: "country-brand",
  season: { monthCoverage: coverage, dataMonths: ["2024-12", "invalid"] },
  ingredient: null,
  analysisOptions: {
    start_date: "2025-01-01",
    end_date: "2025-03-31",
    exclude_partial_months: false
  }
});

assert.deepEqual(monthModel.observedMonthKeys, ["2025-01", "2025-02"]);
assert.deepEqual(monthModel.completeMonthKeys, ["2025-01"]);
assert.deepEqual([...monthModel.partialMonthSet], ["2025-02"]);
assert.deepEqual(monthModel.momMonthOptions, ["2025-01", "2025-02", "2025-03"]);

assert.deepEqual(
  resolveMomPeriodDefaults({
    currentMonth: "2025-02",
    monthOptions: monthModel.momMonthOptions,
    completeMonths: ["2025-01", "2025-02"]
  }),
  { currentMonth: "2025-02", comparisonMonth: "2025-01" }
);
assert.deepEqual(
  resolveMomPeriodDefaults({
    currentMonth: "2024-12",
    monthOptions: monthModel.momMonthOptions,
    completeMonths: ["2025-01", "2025-02"]
  }),
  { currentMonth: "2025-02", comparisonMonth: "2025-01" }
);

const partialStatus = buildMomCoverageModel({
  metric: "mom",
  currentMonth: "2025-02",
  comparisonMonth: "2025-01",
  observedMonths: monthModel.observedMonthSet,
  partialMonths: monthModel.partialMonthSet,
  completeMonths: monthModel.completeMonthKeys,
  coverageByMonth: monthModel.monthCoverageByKey
});
assert.equal(partialStatus.hasCoverageIssue, true);
assert.equal(partialStatus.hasPartialMonth, true);
assert.match(partialStatus.warningMessage, /2025년 2월/);
assert.match(partialStatus.warningMessage, /활동일 10\/20일/);

const missingStatus = buildMomCoverageModel({
  metric: "mom",
  currentMonth: "2025-03",
  comparisonMonth: "2025-02",
  observedMonths: monthModel.observedMonthSet,
  partialMonths: monthModel.partialMonthSet,
  completeMonths: monthModel.completeMonthKeys,
  coverageByMonth: monthModel.monthCoverageByKey
});
assert.equal(missingStatus.hasMissingMonth, true);
assert.equal(missingStatus.nearestUsableMonth, "2025-01");

assert.equal(
  buildYoyCoverageWarning("yoy", [["comparison_month_partial"]]),
  "YTD 기준 연도 또는 비교 연도에 부분 적재 의심 월이 있어 성장률을 계산하지 않습니다."
);
assert.equal(
  buildYoyCoverageWarning("yoy", [["current_month_partial", "comparison_month_missing"]]),
  "YTD 기준 연도 또는 비교 연도의 누계 월 데이터가 누락되어 성장률을 계산하지 않습니다."
);
assert.equal(buildYoyCoverageWarning("sales", [["comparison_month_missing"]]), "");

assert.equal(
  buildCrossGrowthBasisLabel({
    metric: "mom",
    sourceRows: [],
    momCurrentMonth: "2025-03",
    momComparisonMonth: "2025-02",
    yoyMonthRange: null
  }),
  "3월 vs 2월"
);

console.log("Cross-analysis period model checks passed.");
