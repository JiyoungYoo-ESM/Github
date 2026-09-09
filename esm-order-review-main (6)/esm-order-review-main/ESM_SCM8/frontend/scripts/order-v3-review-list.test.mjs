import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { formatCalendarDuration } from "../lib/format-calendar-duration.ts";
import { attentionExportRows, displayOrderQuantity, exclusionReasonKey, filterReviewRows, reviewActionLabel, reviewExportRows, reviewProgress, reviewViewOf } from "../components/redesign/screens/order-v3/reviewList.ts";

// Synthetic rows only. No CMS or user data.
const makeRow = (sku, signal, extra = {}) => ({
  sku, signal, calculable: true, productName: `테스트 상품 ${sku}`, brand: "테스트 브랜드",
  suggestedQty: 10, finalOrderQty: 10, orderAmountKrw: 100, dataStatus: "정상",
  salesHistory: [], adjustedForecast: [], inventoryPosition: 30, reorderPoint: 35, targetStock: 40,
  targetLayers: { leadTimeDemand: 20, safetyStock: 10, reviewDemand: 10 },
  inventoryParts: { localAvailable: 30, hqAvailable: 0, inTransit: 0, incoming: 0 },
  coefficients: {}, averageDemand: 10, leadTimeDays: 28, reviewDays: 28, leadTimeSigmaDays: 0,
  ...extra
});
const rows = [
  makeRow("NEED-A", "즉시 발주"),
  makeRow("NEED-B", "즉시 발주", { orderAmountKrw: 200, brand: "다른 브랜드" }),
  makeRow("NONE", "발주 제외", { suggestedQty: 0, finalOrderQty: 0, orderAmountKrw: 0, reorderPoint: 30 }),
  makeRow("HELD", "계산 차단", { calculable: false, dataStatus: "계산차단", validationCode: "DEMAND_HISTORY_INSUFFICIENT" }),
  makeRow("BLOCKED", "계산 차단", { calculable: false, dataStatus: "계산차단", validationCode: "SEASON_FACTOR_MAPPING_MISSING" }),
  makeRow("UNKNOWN", "확인 후 발주")
];
const ids = values => values.map(row => row.sku);
const select = (options, decisions = {}) => filterReviewRows(rows, options, decisions);
const baseline = JSON.stringify(rows);
assert.deepEqual(ids(select({ view: "needed" })), ["NEED-B", "NEED-A"]);
assert.deepEqual(ids(select({ view: "not-needed" })), ["NONE"]);
assert.deepEqual(ids(select({ view: "excluded" })), ["HELD", "BLOCKED"]);
assert.deepEqual(ids(select({ view: "unknown" })), ["UNKNOWN"]);
const allLists = ["needed", "not-needed", "excluded", "unknown"].flatMap(view => ids(select({ view })));
assert.equal(new Set(allLists).size, rows.length);
assert.equal(allLists.length, rows.length);
assert.equal(reviewViewOf({ calculable: false, signal: "즉시 발주" }), "excluded");
assert.equal(reviewViewOf({ calculable: true, signal: undefined }), "unknown");
assert.deepEqual(ids(select({ view: "needed", query: " need-a " })), ["NEED-A"]);
assert.deepEqual(ids(select({ view: "needed", brand: "다른 브랜드" })), ["NEED-B"]);
assert.deepEqual(ids(select({ view: "needed", query: "NONE" })), []);
assert.deepEqual(filterReviewRows(rows.filter(row => row.signal !== "즉시 발주"), { view: "needed" }, {}), []);
const decisions = { "NEED-A": { decision: "발주 보류", finalQty: 0 }, NONE: { decision: "수량 수정", finalQty: 50 } };
assert.deepEqual(ids(select({ view: "needed" }, decisions)), ["NEED-B", "NEED-A"]);
assert.deepEqual(ids(select({ view: "not-needed" }, decisions)), ["NONE"]);
assert.deepEqual(ids(select({ view: "needed", reviewDecision: "발주 보류" }, decisions)), ["NEED-A"]);
assert.deepEqual(ids(select({ view: "needed", reviewDecision: "미검토" }, decisions)), ["NEED-B"]);
assert.deepEqual(ids(select({ view: "not-needed", reviewDecision: "미검토" }, decisions)), ["NONE"]);
assert.deepEqual(ids(select({ view: "unknown", reviewDecision: "권고 유지" }, decisions)), ["UNKNOWN"]);
assert.deepEqual(ids(select({ view: "excluded", exclusionReason: exclusionReasonKey(rows[3]), reviewDecision: "권고 유지" })), ["HELD"]);
assert.deepEqual(reviewProgress(rows, {}), { total: 2, completed: 0 });
assert.deepEqual(reviewProgress(rows, decisions), { total: 2, completed: 1 });
assert.deepEqual(reviewProgress(rows, {
  ...decisions,
  "NEED-B": { decision: "수량 수정", finalQty: 0 },
  HELD: { decision: "권고 유지", finalQty: 10 },
  BLOCKED: { decision: "수량 수정", finalQty: 25 },
  UNKNOWN: { decision: "권고 유지", finalQty: 10 }
}), { total: 2, completed: 2 }, "Only originally order-needed rows count, including reviewed zero quantities.");
assert.deepEqual(reviewProgress(rows.slice(2), decisions), { total: 0, completed: 0 });
assert.equal(reviewActionLabel(rows[0]), "검토하기");
assert.equal(reviewActionLabel(rows[0], decisions["NEED-A"]), "발주 보류");
assert.equal(reviewActionLabel(rows[2], decisions.NONE), "검토하기");
assert.equal(reviewActionLabel(rows[3]), "사유보기");
assert.equal(reviewActionLabel(rows[4]), "사유보기");
assert.equal(reviewActionLabel(rows[5]), "상세보기");
assert.equal(displayOrderQuantity(rows[0], decisions["NEED-A"]), 0);
assert.equal(displayOrderQuantity(rows[1]), 10);
assert.equal(displayOrderQuantity(rows[2], decisions.NONE), 0, "Legacy review decisions cannot change a read-only result.");
assert.equal(JSON.stringify(rows), baseline, "List filtering must not alter any source quantity or row.");
assert.deepEqual(ids(reviewExportRows(select({ view: "needed" }), new Set())), ["NEED-B", "NEED-A"]);
assert.deepEqual(ids(reviewExportRows(select({ view: "needed" }), new Set(["NONE", "NEED-A"]))), ["NEED-A"]);
assert.deepEqual(reviewExportRows(select({ view: "needed" }), new Set(["NONE"])), []);
assert.deepEqual(ids(reviewExportRows(select({ view: "not-needed" }), new Set())), ["NONE"]);
assert.deepEqual(reviewExportRows(select({ view: "excluded" }), new Set()), []);
const attention = (options, selected = []) => ids(attentionExportRows(rows, options, new Set(selected)));
assert.deepEqual(attention({ view: "needed" }), ["HELD", "BLOCKED"]);
assert.deepEqual(attention({ view: "needed" }, ["NEED-A"]), ["HELD", "BLOCKED"], "Companion exceptions are independent of proposal selection.");
assert.deepEqual(attention({ view: "not-needed" }), ["HELD", "BLOCKED"]);
assert.deepEqual(attention({ view: "needed", brand: "다른 브랜드" }), []);
assert.deepEqual(attention({ view: "needed", query: " held " }), ["HELD"]);
assert.deepEqual(attention({ view: "needed", exclusionReason: exclusionReasonKey(rows[3]) }), ["HELD", "BLOCKED"], "Ignore stale reason filters outside the exclusions view.");
assert.deepEqual(attention({ view: "excluded", exclusionReason: exclusionReasonKey(rows[3]) }), ["HELD"]);
assert.deepEqual(attention({ view: "excluded" }, ["BLOCKED", "NEED-A"]), ["BLOCKED"]);
assert.deepEqual(attention({ view: "excluded", query: "HELD" }, ["BLOCKED"]), []);
assert.equal(JSON.stringify(rows), baseline);
const otherScenario = rows.map(row => row.sku === "NEED-A" ? { ...row, signal: "발주 제외", suggestedQty: 0 } : row);
assert.deepEqual(ids(filterReviewRows(otherScenario, { view: "needed" }, decisions)), ["NEED-B"]);
assert.deepEqual(reviewProgress(otherScenario, decisions), { total: 1, completed: 0 });

// Render the actual table component without calling the analysis API.
const screenFile = "components/redesign/screens/order-v3/OrderV3Screen.tsx";
const source = readFileSync(screenFile, "utf8").replace(/\r\n/g, "\n");
const ast = ts.createSourceFile(screenFile, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const functionNames = ["TriageProposalTable", "DecisionBadge", "ExclusionStatusBadge", "riskLabel", "ReviewSummary", "mapApiRow", "patternLabel", "engineLabel"];
const functions = ast.statements.filter(node => ts.isFunctionDeclaration(node) && functionNames.includes(node.name?.text));
assert.equal(functions.length, functionNames.length);
const compiled = ts.transpileModule(functions.map(node => node.getText(ast)).join("\n"), {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
}).outputText;
const context = {
  require: createRequire(import.meta.url), exports: {}, reviewViewOf, reviewActionLabel, displayOrderQuantity,
  cn: (...values) => values.filter(Boolean).join(" "),
  formatInteger: value => String(value), formatKrw: value => `₩${value}`,
  formatKrwInEok: value => `₩${value}`, useState: React.useState,
  exclusionReasonLabel: row => row.validationCode,
  Search: () => null, Info: () => null,
  ChevronDown: () => React.createElement("span", { "data-icon": "chevron-down" }),
  TrendSparkline: () => React.createElement("span", null, "테스트 추세")
};
vm.createContext(context);
vm.runInContext(compiled, context);
const progress = reviewProgress(rows, decisions);
const summaryMarkup = renderToStaticMarkup(React.createElement(context.ReviewSummary, {
  rows, reviewedCount: progress.completed, reviewTotalCount: progress.total,
  canViewAmountData: true, exclusionsOpen: false, onToggleExclusions() {}
}));
const summaryValues = [...summaryMarkup.matchAll(/<strong\b[^>]*>(.*?)<\/strong>/g)].map(match => match[1]);
assert.equal(summaryValues[0], "2건", "The needed card and review denominator use the same original result set.");
assert.equal(summaryValues.at(-1), "1 / 2건");
assert.equal(summaryValues[3], "2건", "The blocked count remains visible without the redundant arrow.");
assert.ok(!summaryMarkup.includes('data-icon="chevron-down"'));
assert.ok(summaryMarkup.includes('aria-expanded="false" aria-controls="order-v3-exclusion-reasons"'));
const selectedBrandRows = rows.filter(row => row.brand === "테스트 브랜드");
const selectedBrandProgress = reviewProgress(selectedBrandRows, decisions);
const selectedBrandSummaryMarkup = renderToStaticMarkup(React.createElement(context.ReviewSummary, {
  rows: selectedBrandRows,
  reviewedCount: selectedBrandProgress.completed,
  reviewTotalCount: selectedBrandProgress.total,
  canViewAmountData: true,
  exclusionsOpen: false,
  onToggleExclusions() {}
}));
const selectedBrandSummaryValues = [...selectedBrandSummaryMarkup.matchAll(/<strong\b[^>]*>(.*?)<\/strong>/g)].map(match => match[1]);
assert.deepEqual(selectedBrandSummaryValues, ["1건", "20 EA", "₩200", "2건", "1 / 1건"], "Summary cards must use only the selected brand's V3 result rows.");
const expandedSummaryMarkup = renderToStaticMarkup(React.createElement(context.ReviewSummary, {
  rows, reviewedCount: progress.completed, reviewTotalCount: progress.total,
  canViewAmountData: true, exclusionsOpen: true, onToggleExclusions() {}
}));
assert.ok(!expandedSummaryMarkup.includes('data-icon="chevron-down"'), "The active summary card must also omit the arrow.");
assert.ok(expandedSummaryMarkup.includes('aria-expanded="true" aria-controls="order-v3-exclusion-reasons"'));
const renderTable = (tableRows, extra = {}) => renderToStaticMarkup(React.createElement(context.TriageProposalTable, {
  rows: tableRows, hasResult: true, showExclusionReasons: false, decisions: {},
  selectedSku: null, selectedSkus: new Set(), canViewAmountData: true,
  onToggle() {}, onToggleAll() {}, onOpen() {},
  emptyMessage: "발주가 필요한 상품이 없습니다.", emptyDescription: "다른 목록을 확인하세요.", ...extra
}));
const neededMarkup = renderTable(select({ view: "needed" }));
assert.ok(!neededMarkup.includes("발주 상태"));
assert.ok(!neededMarkup.includes("발주 필요"));
assert.ok(!neededMarkup.includes("h-8 w-1"), "Do not repeat a red status stripe for every needed row.");
assert.equal((neededMarkup.match(/<th\b/g) || []).length, 6);
assert.ok(neededMarkup.includes("NEED-A") && neededMarkup.includes("NEED-B"));
assert.ok(!neededMarkup.includes("HELD"));
assert.ok(neededMarkup.includes("검토하기"));
assert.ok(!neededMarkup.includes("빠른승인"));
const notNeededMarkup = renderTable(select({ view: "not-needed" }), { decisions });
assert.equal((notNeededMarkup.match(/검토하기/g) || []).length, 2, "Desktop and mobile use the review label while keeping details read-only.");
assert.ok(!notNeededMarkup.includes("수량 수정") && !notNeededMarkup.includes("빠른승인") && !notNeededMarkup.includes("상세보기"));
assert.ok(!notNeededMarkup.includes(">50<") && !notNeededMarkup.includes(">50 EA<"));
const hiddenAmounts = renderTable(select({ view: "needed" }), { canViewAmountData: false });
assert.ok(!hiddenAmounts.includes("₩"));
const cellTexts = (markup, tag) => [...markup.matchAll(new RegExp(`<${tag}\\b[^>]*>([\\s\\S]*?)</${tag}>`, "g"))]
  .map(match => match[1].replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim());
const barcodeRow = { ...rows[2], barcode: "0001234567890" };
const barcodeMarkup = renderTable([barcodeRow]);
assert.deepEqual(cellTexts(barcodeMarkup, "th"), ["", "바코드", "상품", "추세 (91일 / 13주)", "제안수량 · 금액", "검토"]);
assert.equal(cellTexts(barcodeMarkup, "td")[1], "0001234567890", "The first data column shows the barcode without dropping leading zeros.");
assert.ok(cellTexts(barcodeMarkup, "td")[2].includes("NONE"), "Product identifiers remain in the next column.");
assert.ok(barcodeMarkup.includes("바코드 0001234567890"), "Mobile cards also show the barcode before the product information.");
assert.equal(cellTexts(renderTable([barcodeRow], { canViewAmountData: false }), "td")[1], "0001234567890");
for (const barcode of [undefined, null, ""]) {
  assert.equal(cellTexts(renderTable([{ ...barcodeRow, barcode }]), "td")[1], "미확인");
}
const excludedMarkup = renderTable(select({ view: "excluded" }), { showExclusionReasons: true });
const excludedCheckboxes = [...excludedMarkup.matchAll(/<input\b[^>]*type="checkbox"[^>]*>/g)].map(match => match[0]);
assert.equal(excludedCheckboxes.length, 5, "Desktop select-all plus desktop/mobile row selections.");
assert.ok(excludedCheckboxes.every(input => !input.includes("disabled=")), "Blocked rows are selectable for Excel, not for order review.");
assert.equal(cellTexts(excludedMarkup, "th")[1], "바코드", "All lists that use the same table keep a consistent column order.");
assert.ok(excludedMarkup.includes("계산 차단"));
assert.ok(excludedMarkup.includes("보류·차단 사유"));
assert.ok(excludedMarkup.includes("DEMAND_HISTORY_INSUFFICIENT"));
assert.ok(!excludedMarkup.includes("₩"));
assert.equal((excludedMarkup.match(/사유보기/g) || []).length, 4);
assert.ok(renderTable([]).includes("발주가 필요한 상품이 없습니다."));
assert.ok(renderTable([], { hasResult: false }).includes("분석을 실행하면 발주 검토 목록이 표시됩니다."));
assert.ok(source.includes('const changeReviewView = (nextView: OrderV3ReviewView) => {\n    setReviewView(nextView);\n    resetFilters();'));
assert.ok(source.includes('setSelectedSkus(new Set()); setSelectedSku(null); setDrawerOpen(false);'));

// Render the actual drawer to ensure read-only lists cannot expose review actions.
const drawerFile = "components/redesign/screens/order-v3/OrderV3EvidenceDrawer.tsx";
const drawerSource = readFileSync(drawerFile, "utf8");
const drawerAst = ts.createSourceFile(drawerFile, drawerSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const drawerFunctionNames = ["orderUnitDescription", "StepTitle", "MetricBox", "OrderV3CalculationDetails", "OrderV3EvidenceDrawer"];
const drawerFunctions = drawerAst.statements.filter(node => ts.isFunctionDeclaration(node) && drawerFunctionNames.includes(node.name?.text));
assert.equal(drawerFunctions.length, drawerFunctionNames.length);
const drawerCompiled = ts.transpileModule(drawerFunctions.map(node => node.getText(drawerAst)).join("\n"), {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
}).outputText;
const drawerContext = {
  ...context, exports: {},
  useEffect: React.useEffect, useMemo: React.useMemo, useRef: React.useRef, useState: React.useState,
  PERIOD_LABELS: Array.from({ length: 13 }, (_, index) => `P${index + 1}`),
  formatCalendarDuration, chartColors: {},
  ...Object.fromEntries([
    "Check", "ChevronDown", "ChevronLeft", "ChevronRight", "PauseCircle", "PencilLine", "X",
    "Bar", "CartesianGrid", "ComposedChart", "Line", "ResponsiveContainer", "Tooltip", "XAxis", "YAxis"
  ].map(name => [name, () => null]))
};
vm.createContext(drawerContext);
vm.runInContext(drawerCompiled, drawerContext);
const renderDrawer = (row, decision = null) => renderToStaticMarkup(React.createElement(drawerContext.OrderV3EvidenceDrawer, {
  open: true, row, decision, overallPosition: 0, overallTotal: 2, priorityPosition: 0, priorityTotal: 0,
  scenarioLabel: "테스트 시나리오", canViewAmountData: true,
  onClose() {}, onPrevious() {}, onNext() {}, onKeep() {}, onSaveQuantity() {}, onHold() {}
}));
const buttonTexts = markup => [...markup.matchAll(/<button\b[^>]*>([\s\S]*?)<\/button>/g)]
  .map(match => match[1].replace(/<[^>]*>/g, "").trim());
const reviewButtons = ["권고 유지", "수량 수정", "발주 보류"];
const neededDrawer = renderDrawer(rows[0]);
assert.ok(reviewButtons.every(label => buttonTexts(neededDrawer).includes(label)));
assert.equal(neededDrawer.match(/<p\b[^>]*>(.*?)<\/p>/)?.[1], "테스트 시나리오");
assert.ok(neededDrawer.includes("최종 주문수량 (박스 올림)") && neededDrawer.includes("발주반영 총재고 (IP)"));
assert.ok(neededDrawer.includes("목표재고(S) 40") && neededDrawer.includes("발주필요수량 10개"));
assert.ok(neededDrawer.includes("최종 주문수량 10개"), "The drawer explains the pack-rounded final quantity.");
assert.ok(neededDrawer.includes("참고 ROP(미사용)"));
assert.ok(neededDrawer.indexOf("향후 수요 예측") < neededDrawer.indexOf("목표재고·정기발주"));
assert.ok(neededDrawer.indexOf("목표재고·정기발주") < neededDrawer.indexOf("91일 판매"));
assert.ok(neededDrawer.indexOf("91일 판매") < neededDrawer.indexOf("자동 분류 근거"));
for (const row of rows.slice(2)) {
  const markup = renderDrawer(row, decisions.NONE);
  const labels = buttonTexts(markup);
  assert.ok(reviewButtons.every(label => !labels.includes(label)), `${row.sku} must not expose review actions.`);
  assert.ok(labels.includes("닫기"));
  assert.ok(!markup.includes("검토 순서") && !markup.includes("미검토"));
}
const notNeededDrawer = renderDrawer(rows[2], decisions.NONE);
assert.ok(notNeededDrawer.includes("이번에는 발주가 필요하지 않습니다."));
assert.ok(notNeededDrawer.includes("목표재고(S) 40"));
assert.ok(notNeededDrawer.includes("0 EA") && !notNeededDrawer.includes("50 EA"));
assert.ok(renderDrawer(rows[3]).includes("보류·차단 사유"));

// Factor availability is independent of whether demand/order calculation succeeded.
const heldApiRow = {
  sku_code: "CLASSIFIED-NO-SALES", calculable: false,
  reason_code: "DEMAND_HISTORY_INSUFFICIENT",
  validation_error: "완료 13주 수요이력이 부족해 계산을 차단했습니다.",
  function_class_1_code: "스킨케어", function_class_2_code: "패치",
  season_factor_available: true, season_factor_scope: "FUNCTION_CLASS_1_AND_2",
  season_factor_version: "synthetic-active", seasonal_applied: false,
  season_factors_by_month: Object.fromEntries(Array.from({ length: 12 }, (_, index) => [index + 1, 1.2])),
};
const heldMapped = context.mapApiRow(heldApiRow);
assert.equal(heldMapped.functionClass1, "스킨케어");
assert.equal(heldMapped.functionClass2, "패치");
assert.equal(heldMapped.seasonFactorAvailable, true);
assert.equal(heldMapped.seasonalApplied, false);
assert.equal(reviewViewOf(heldMapped), "excluded");
const heldMarkup = renderDrawer(heldMapped);
assert.ok(heldMarkup.includes("스킨케어 / 패치") && heldMarkup.includes("계산된 지수 연결 완료"));
assert.ok(heldMarkup.includes("발주 계산은 위 사유로 완료되지 않았습니다."));
assert.equal((heldMarkup.match(/<dt\b/g) || []).length, 12);
assert.equal((heldMarkup.match(/>1.20<\/dd>/g) || []).length, 12);
assert.ok(heldMarkup.includes("synthetic-active") && !heldMarkup.includes("후보지수"));
assert.ok(!heldMarkup.includes("0 EA"), "A held order must not masquerade as a completed zero-quantity result.");
const unavailable = renderDrawer(context.mapApiRow({
  ...heldApiRow, season_factor_available: false, season_factors_by_month: null,
  reason_code: "SEASON_FACTOR_MISSING", validation_error: "적용 가능한 동일 법인 계절지수가 없습니다.",
}));
assert.ok(unavailable.includes("연결 불가") && !unavailable.includes("연결 완료"));
assert.equal((unavailable.match(/<dt\b/g) || []).length, 0);
const parentOnly = renderDrawer(context.mapApiRow({
  ...heldApiRow, function_class_2_code: "미분류", season_factor_scope: "FUNCTION_CLASS_1",
  season_factor_application_reason_code: "SEASON_FACTOR_CALC_FAILED_USE_DEFAULT_1",
}));
assert.ok(parentOnly.includes("기능구분1 기준") && parentOnly.includes("기본값 1.0 연결 완료"));

// Detail explanations must use the calculation response, not fixture-only policy fields.
const evidenceApiRow = {
  sku_code: "DETAIL-TEST", calculable: true, order_signal: "즉시 발주",
  engine: "HOLT_DAMPED", pattern: "TREND_UP", inventory_position: 190,
  on_hand_qty: 100, upstream_available_qty: 40, in_transit_qty: 30, unreceived_qty: 20, holding_qty: 0,
  lead_time_days: 72.9, review_days: 28, sigma_lead_time_days: 0,
  demand_per_period: 75, forecast_rmse: 12,
  layer1: 170, layer2_raw: 35, layer2: 40, safety_stock_floor: 40, safety_stock_cap: 160, layer3: 90,
  reorder_point: 210, target_stock: 300, raw_order_quantity: 110, alpha: 0.2, beta: 0.1, phi: 0.90,
  first_sale_date: "2025-01-01", analysis_sales_cutoff: "2025-07-01",
  calendar_days_since_first_sale: 181, is_new_sku: false
};
const evidenceApiBefore = JSON.stringify(evidenceApiRow);
const evidenceRow = context.mapApiRow(evidenceApiRow);
const renderDetails = row => renderToStaticMarkup(React.createElement(drawerContext.OrderV3CalculationDetails, { row }));
const detailMarkup = renderDetails(evidenceRow);
assert.equal(evidenceRow.inventoryParts.hqAvailable, 40);
assert.equal(evidenceRow.inventoryPosition, 190);
assert.equal(evidenceRow.reorderPoint, 210);
assert.equal(evidenceRow.suggestedQty, 110);
assert.ok(detailMarkup.includes("+ 40개") && detailMarkup.includes("190개"));
assert.ok(detailMarkup.includes("72.9일 (10.41기)") && detailMarkup.includes("28일 (4기)") && detailMarkup.includes("0일 (0기)"));
assert.ok(!detailMarkup.includes("확인 필요"), "Applied durations must not depend on an unmapped leadTimePolicy object.");
assert.ok(detailMarkup.includes("0.90"), "HOLT uses the guide's common damping coefficient.");
assert.ok(!detailMarkup.includes("V2") && !detailMarkup.includes("Calendar Days") && !detailMarkup.includes("추가 차감 수량"));
assert.ok(detailMarkup.includes("<details ") && !detailMarkup.includes("<details open"));
assert.ok(detailMarkup.includes("박스 단위와 최소 주문수량 조건이 아직 반영되지 않았습니다."));
const missingDurationMarkup = renderDetails({ ...evidenceRow, leadTimeDays: null, reviewDays: null, leadTimeSigmaDays: null });
assert.equal((missingDurationMarkup.match(/확인 필요/g) || []).length, 3, "Missing duration values must remain explicit instead of becoming zero.");
assert.equal(JSON.stringify(evidenceApiRow), evidenceApiBefore);

// V2 inventory warnings remain visible without changing the V3 order/review queue.
const inventoryMessage = "① 미입고 수량이 비어 있어 V2 기준으로 0을 적용했습니다. 원천 수량을 확인하세요.";
const inventoryWarningRow = context.mapApiRow({
  ...evidenceApiRow,
  inventory_warnings: ["INCOMING_QTY_NULL_AS_ZERO"],
  inventory_warning_messages: [inventoryMessage],
});
assert.equal(inventoryWarningRow.inventoryWarnings[0], inventoryMessage);
assert.equal(inventoryWarningRow.suggestedQty, evidenceRow.suggestedQty);
assert.equal(reviewViewOf(inventoryWarningRow), "needed");
assert.equal(reviewActionLabel(inventoryWarningRow), "재고확인");
assert.equal(reviewActionLabel(inventoryWarningRow, { decision: "미검토" }), "재고확인");
assert.equal(reviewActionLabel(inventoryWarningRow, { decision: "권고 유지", finalQty: 110 }), "권고 유지");
const inventoryWarningDrawer = renderDrawer(inventoryWarningRow);
assert.ok(inventoryWarningDrawer.includes('aria-label="재고 원천 확인"'));
assert.ok(inventoryWarningDrawer.includes(inventoryMessage));
assert.ok(reviewButtons.every(label => buttonTexts(inventoryWarningDrawer).includes(label)));
assert.equal((renderTable([inventoryWarningRow]).match(/재고확인/g) || []).length, 2, "Both desktop and mobile show the inventory warning action.");
assert.ok(!renderDrawer(evidenceRow).includes('aria-label="재고 원천 확인"'), "Normal rows must not acquire an inventory warning.");

const inventoryError = "재고·미입고 수량에 음수가 있어 계산할 수 없습니다.";
const inventoryBlockedRow = context.mapApiRow({
  ...evidenceApiRow, calculable: false, order_signal: "계산 차단",
  reason_code: "V2_INVENTORY_INVALID", validation_error: inventoryError,
  raw_order_quantity: null, order_amount_krw: null,
  inventory_validation_error: inventoryError,
  inventory_warnings: ["INCOMING_QTY_NEGATIVE"],
  inventory_warning_messages: ["① 미입고 수량에 음수가 있어 V2 기준으로 발주 계산을 차단했습니다."],
});
assert.equal(reviewViewOf(inventoryBlockedRow), "excluded");
assert.equal(reviewActionLabel(inventoryBlockedRow), "사유보기");
const inventoryBlockedDrawer = renderDrawer(inventoryBlockedRow);
assert.ok(inventoryBlockedDrawer.includes(inventoryError));
assert.ok(reviewButtons.every(label => !buttonTexts(inventoryBlockedDrawer).includes(label)));
assert.ok(!inventoryBlockedDrawer.includes("0 EA"), "A blocked inventory row must not look like a calculated zero order.");
assert.equal(JSON.stringify(rows), baseline);
console.log("V3 review workflow checks passed: list partitions, review-only counts/actions, legacy decisions, scenario changes, export scope, desktop/mobile rendering, read-only drawers, inventory warnings/blocks and empty states.");
