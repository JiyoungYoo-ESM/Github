import assert from "node:assert/strict";

import { buildCrossAnalysisReportHtml } from "../components/redesign/screens/cross/crossAnalysisReportDocument.ts";

const matrix = {
  rowLabel: "국가<script>",
  columnLabel: "브랜드&",
  totalLabel: "합계",
  columns: ["A&B"],
  rows: ["<KR>"],
  rowOptions: ["<KR>"],
  columnOptions: ["A&B"],
  filteredRowOptions: ["<KR>"],
  filteredColumnOptions: ["A&B"],
  values: [[1200]],
  cellPresence: [[true]],
  cellStatuses: [[null]],
  growthRowTotals: [null],
  growthRowTotalStatuses: [null],
  shareTieBreakKeys: [["row-column"]]
};
const shareAllocation = {
  values: [[100]],
  rowTotals: [100],
  total: 1200,
  calculable: true
};

const shareHtml = buildCrossAnalysisReportHtml({
  generatedAt: "2026. 07. 22. 10:00",
  fileDate: "2026-07-22",
  selectedAxisLabel: "국가 < 브랜드",
  metric: "sales",
  scale: "share",
  matrix,
  shareAllocation,
  momHasCoverageIssue: false,
  momCoverageWarningMessage: "",
  yoyCoverageWarningMessage: "",
  dataScopeWarning: "<scope> & warning"
});

assert.match(shareHtml, /<!doctype html>/);
assert.match(shareHtml, /국가 &lt; 브랜드/);
assert.match(shareHtml, /국가&lt;script&gt;/);
assert.match(shareHtml, /A&amp;B/);
assert.match(shareHtml, /100\.0%/);
assert.match(shareHtml, /&lt;scope&gt; &amp; warning/);
assert.doesNotMatch(shareHtml, /<script>.*국가/s);

const zeroDenominatorHtml = buildCrossAnalysisReportHtml({
  generatedAt: "2026. 07. 22. 10:00",
  fileDate: "2026-07-22",
  selectedAxisLabel: "국가 × 브랜드",
  metric: "sales",
  scale: "share",
  matrix: {
    ...matrix,
    values: [[0]],
    cellPresence: [[true]]
  },
  shareAllocation: {
    values: [[0]],
    rowTotals: [0],
    total: 0,
    calculable: false
  },
  momHasCoverageIssue: false,
  momCoverageWarningMessage: "",
  yoyCoverageWarningMessage: "",
  dataScopeWarning: ""
});
assert.doesNotMatch(zeroDenominatorHtml, /0\.0%/);
assert.match(zeroDenominatorHtml, />-<\/td>/);

const growthHtml = buildCrossAnalysisReportHtml({
  generatedAt: "2026. 07. 22. 10:00",
  fileDate: "2026-07-22",
  selectedAxisLabel: "국가 × 브랜드",
  metric: "yoy",
  scale: "amount",
  matrix: {
    ...matrix,
    rowLabel: "국가",
    columnLabel: "브랜드",
    rows: ["KR"],
    columns: ["A"],
    values: [[1500]],
    cellStatuses: [["ok"]],
    growthRowTotals: [1500]
  },
  shareAllocation,
  momHasCoverageIssue: false,
  momCoverageWarningMessage: "",
  yoyCoverageWarningMessage: "YoY 경고",
  dataScopeWarning: ""
});

assert.match(growthHtml, /&gt;\+999%/);
assert.match(growthHtml, /rgba\(22, 163, 74/);
assert.match(growthHtml, /YoY 경고/);
assert.match(growthHtml, /가장 많이 증가/);
assert.match(growthHtml, /가장 많이 감소/);
assert.match(growthHtml, /증가한 조합/);
assert.match(growthHtml, /비교 가능한 조합/);
assert.match(growthHtml, /window\.print\(\)/);

console.log("Cross-analysis report document checks passed.");
