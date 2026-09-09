import assert from "node:assert/strict";

import {
  buildCrossAnalysisReportModel,
  crossCellStatusLabel
} from "../components/redesign/screens/cross/crossAnalysisReportModel.ts";

const matrix = {
  rowLabel: "국가",
  columnLabel: "브랜드",
  totalLabel: "합계",
  columns: ["ANUA"],
  rows: ["KR"],
  rowOptions: ["KR"],
  columnOptions: ["ANUA"],
  filteredRowOptions: ["KR"],
  filteredColumnOptions: ["ANUA"],
  values: [[2.5]],
  cellPresence: [[true]],
  cellStatuses: [[null]],
  growthRowTotals: [null],
  growthRowTotalStatuses: [null],
  shareTieBreakKeys: [["KR-ANUA"]]
};
const baseOptions = {
  axis: "country-brand",
  flipped: false,
  metric: "sales",
  scale: "amount",
  monthComparisonMode: "mom",
  momCurrentMonth: "2025-03",
  momComparisonMonth: "2025-02",
  yoyComparisonMode: "ytd",
  yoyMonthRange: null,
  selectedRows: ["KR"],
  selectedColumns: ["ANUA"],
  selectedAxisLabel: "국가 × 브랜드",
  growthBasisLabel: "",
  momHasMissingMonth: false,
  momHasPartialMonth: false,
  momHasCoverageIssue: false,
  momCoverageWarningMessage: "",
  yoyCoverageWarningMessage: "",
  dataScopeWarning: "",
  averageEurKrwRate: 1500,
  analysisOptions: {
    start_date: "2025-01-01",
    end_date: "2025-03-31"
  },
  matrix,
  shareAllocation: {
    values: [[100]],
    rowTotals: [100],
    total: 2.5,
    calculable: true
  }
};

const first = buildCrossAnalysisReportModel(baseOptions);
const second = buildCrossAnalysisReportModel({ ...baseOptions });
assert.equal(first.block.id, second.block.id);
assert.equal(first.ready, true);
assert.equal(first.block.type, "cross_matrix");
assert.equal(first.block.params.analysis_start_date, "2025-01-01");
assert.equal(first.block.params.analysis_end_date, "2025-03-31");
assert.equal(first.block.snapshot.rows[0]["표시값"], "€2.5K");
assert.equal(first.block.snapshot.rows[0]["원화표시"], "약 ₩375만원");
assert.equal(first.block.snapshot.rows[0].brand_role, "self");

const changedSelection = buildCrossAnalysisReportModel({
  ...baseOptions,
  selectedColumns: ["ANUA", "COSRX"]
});
assert.notEqual(first.block.id, changedSelection.block.id);

const emptySelection = buildCrossAnalysisReportModel({
  ...baseOptions,
  selectedRows: []
});
assert.equal(emptySelection.ready, false);

const zeroDenominatorShare = buildCrossAnalysisReportModel({
  ...baseOptions,
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
  }
});
assert.equal(zeroDenominatorShare.block.snapshot.rows[0]["표시값"], "-");
assert.equal(zeroDenominatorShare.block.snapshot.rows[0]["점유율"], "");

assert.equal(crossCellStatusLabel("ok"), "정상");
assert.equal(crossCellStatusLabel("current_month_partial"), "기준 기간 부분 적재 의심");
assert.equal(crossCellStatusLabel("zero_base"), "비교월 실적 0");
assert.equal(crossCellStatusLabel(null), "");

console.log("Cross-analysis report model checks passed.");
