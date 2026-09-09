import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import ExcelJS from "exceljs";
import { populateV3Excel, V3_DETAIL_COLUMNS, V3_EXCEL_HEADER_ROW } from "../components/redesign/screens/order-v3/excelExport.ts";
import { attentionExportRows, filterReviewRows, reviewExportRows } from "../components/redesign/screens/order-v3/reviewList.ts";
import { createExcelStream } from "../lib/server/order-v3-excel.ts";

// Synthetic source values only. IP=100 < ROP=105; S=110.25 -> Q=10.25.
// Pack rounding: outbox 12 ceils 10.25 to 12; the API amount is
// 12 * 1234 = 14808, not the reviewed 11 * 1234.
const base = {
  sku_code: "TEST-NEEDED", barcode: "0001234567890", product_name: "검산용 상품 · 긴 상품명도 구분해서 표시", brand: "테스트 브랜드",
  calculable: true, data_status: "CALCULATED", order_signal: "즉시 발주",
  pattern: "STABLE", engine: "SES", adi: 1, cv2: 0.25, trend_signal: 0.1,
  demand_per_period: 20.5, forecast_rmse: 3.2, forecast_sigma: 3.2,
  alpha: 0.2, beta: null, phi: null, z_value: 1.28, z_policy: "SHORTAGE",
  transport_mode: "SEA", lead_time_days: 70, review_days: 28, lead_time_periods: 10, review_periods: 4,
  sigma_lead_time_periods: 0.4, safety_stock_floor_periods: 2, safety_stock_cap_periods: 13,
  layer1: 85, layer2_raw: 20, safety_stock_floor: 10.25, safety_stock_cap: 66.625,
  layer2: 20, layer3: 5.25, reorder_point: 105, target_stock: 110.25,
  on_hand_qty: 60, upstream_available_qty: 10, in_transit_qty: 10, unreceived_qty: 20, holding_qty: 0,
  inventory_position: 100, raw_order_quantity: 10.25, order_amount_krw: 14808, order_amount_local: 9.1875,
  inbox_quantity: 6, outbox_quantity: 12, order_unit_quantity: 12, order_unit_source: "OUTBOX",
  unit_price_krw: 1234, unit_price_local: 0.75, local_currency: "EUR",
  inbound_status_source_present: true,
  open_po_qty: 5, pnfm_qty: 8, inbound_progress_qty: 7, inbound_completed_qty: 99,
  reference_sales_start: "2026-06-01", reference_sales_end: "2026-08-30", reference_sales_days: 91,
  reference_sales_status: "AVAILABLE", reference_sales_13w: 1300, reference_monthly_sales: 433, reference_monthly_sales_raw: 1300 / 3, reference_weekly_sales: 100,
  reference_weekly_sales_history: [50, 150, 50, 150, 50, 150, 50, 150, 50, 150, 50, 150, 100], reference_weekly_sigma: 50,
  reference_moi: 0.2, reference_logistics_moi: 0.2, reference_depletion_weeks: 0.7,
  reference_order_slack_weeks: 0, reference_conservative_slack_weeks: 0,
  reference_early_warning_at: "2026-08-31T00:00:00", reference_order_at: "2026-08-31T00:00:00",
  eta_reference_status: "PARTIAL", eta_week_start: "2026-08-31", eta_missing_qty: 4,
  eta_bucket_quantities: [1, 2, 3, ...Array(12).fill(0)], next_eta: "2026-08-30",
  shipping_eta_details: [
    { eta: "2026-08-30", qty: 1, eta_status: "원천 ETA", ship_date: "2026-08-01", transport_mode: "SEA", lead_time_days: null },
    { eta: "2026-08-31", qty: 2, eta_status: "원천 ETA", ship_date: "2026-08-01", transport_mode: "SEA", lead_time_days: null },
    { eta: "2026-09-07", qty: 3, eta_status: "출고일 추정 ETA", ship_date: "2026-08-24", transport_mode: "RAIL", lead_time_days: 14 },
    { eta: null, qty: 4, eta_status: "ETA 미확인", ship_date: null, transport_mode: null, lead_time_days: null }
  ],
  final_order_quantity: 12, seasonal_applied: true, season_factor_available: true,
  season_factor_version: "SYNTHETIC-SF", function_class_1_code: "TEST-CLASS1", function_class_2_code: "TEST-CLASS2",
  season_factor_scope: "FUNCTION_CLASS_1_AND_2", season_factor_function_class_1_code: "TEST-CLASS1",
  season_factor_function_class_2_code: "TEST-CLASS2", seasonal_f1: 0.81234567890123, seasonal_f2: 1.2, seasonal_f_lr: 1.02,
  season_factors_by_month: Object.fromEntries(Array.from({ length: 12 }, (_, i) => [String(i + 1), 0.7 + i * 0.05])),
  season_factor_window_start: "2024-08-01", season_factor_window_end: "2026-07-31",
  first_sale_date: "2025-08-01", analysis_sales_cutoff: "2026-08-30", calendar_days_since_first_sale: 394,
  lead_time_source: "synthetic-only", lead_time_sample_size: 50, lead_time_completion_from: "2025-08-31", lead_time_completion_to: "2026-08-30",
  original_period_sales: Array.from({ length: 13 }, (_, i) => i * 10),
  adjusted_period_sales: Array.from({ length: 13 }, (_, i) => i * 10.125),
  adjusted_forecast: [999, 888] // Must never be exported as historical adjusted sales.
};
const cash = { ...base, raw_order_quantity: 2.5, final_order_quantity: 12, order_amount_krw: 14808, order_amount_local: 9.1875, transport_mode: "RAIL", z_policy: "CASH", layer1: 81, layer3: 1.5, reorder_point: 101, target_stock: 102.5 };
const noOrder = { ...base, sku_code: "TEST-NO-ORDER", order_signal: "발주 제외", inventory_position: 105, raw_order_quantity: 0, final_order_quantity: 0, order_amount_krw: 0, order_amount_local: 0 };
const missingAmount = { ...base, sku_code: "TEST-NO-PRICE", order_amount_krw: null, order_amount_local: null, unit_price_local: null };
const held = {
  sku_code: "TEST-HELD", barcode: "0000000123", product_name: "수요이력 부족 테스트", brand: "테스트",
  calculable: false, data_status: "BLOCKED", order_signal: "계산 차단", reason_code: "DEMAND_HISTORY_INSUFFICIENT", validation_error: "완료 13주 수요이력이 부족함",
  raw_order_quantity: null, final_order_quantity: null, order_unit_quantity: null, order_unit_source: null,
  order_amount_krw: null, order_amount_local: null, seasonal_applied: false, season_factor_available: true,
  reference_sales_start: "2026-06-01", reference_sales_end: "2026-08-30", reference_sales_days: 91,
  reference_sales_status: "AVAILABLE", reference_sales_13w: 0, reference_monthly_sales: 0, reference_weekly_sales: 0,
  reference_weekly_sigma: 0, reference_moi: null, reference_logistics_moi: null, reference_depletion_weeks: null,
  reference_order_slack_weeks: null, reference_conservative_slack_weeks: null, reference_early_warning_at: null, reference_order_at: null,
  season_factor_version: "SYNTHETIC-DEFAULT", function_class_1_code: "TEST-CLASS1", function_class_2_code: "TEST-CLASS2",
  season_factor_application_reason_code: "SEASON_FACTOR_CALC_FAILED_USE_DEFAULT_1",
  season_factor_original_reason_code: "SEASON_FACTOR_CALC_FAILED", season_factor_original_message: "synthetic failure",
  season_factors_by_month: Object.fromEntries(Array.from({ length: 12 }, (_, i) => [String(i + 1), 1]))
};
const blocked = { ...held, sku_code: "TEST-BLOCKED", reason_code: "SEASON_FACTOR_MAPPING_MISSING", data_status: "BLOCKED", order_signal: "계산 차단", validation_error: "분류 연결 필요", season_factor_available: false, season_factors_by_month: { 1: 999 } };
const crostonBlocked = { ...blocked, sku_code: "TEST-CROSTON-BLOCKED", validation_error: "Croston requires at least two non-zero sales periods" };
const manualHold = { ...base, sku_code: "TEST-MANUAL-HOLD" };
const maintained = { ...base, sku_code: "TEST-MAINTAINED" };
const allRows = [base, noOrder, missingAmount, held, blocked, manualHold, maintained];
const result = {
  status: "success", job_id: "SYNTHETIC-RUN", entity_code: "PL", as_of: "2026-08-31", calculated_at: "2026-08-31T01:00:00Z",
  logic_version: "synthetic-v3", result_schema_version: 24, preview: true,
  period_start: "2026-06-01", period_end: "2026-08-30", period_count: 13, period_days: 7,
  source_snapshot_id: "SYNTHETIC-SNAPSHOT", source_fetched_at: "2026-08-31T00:59:00Z", order_constraint_status: "ORDER_CONSTRAINTS_PENDING", warnings: [],
  rows: allRows,
  scenarios: { SHORTAGE: { rows: allRows }, CASH: { rows: [noOrder, cash] } }
};
const decisions = {
  "TEST-NEEDED": { decision: "수량 수정", finalQty: 11 },
  "TEST-NO-ORDER": { decision: "수량 수정", finalQty: 999 }, // stale review state cannot turn Q=0 into an order
  "TEST-HELD": { decision: "수량 수정", finalQty: 999 },
  "TEST-MANUAL-HOLD": { decision: "발주 보류", finalQty: 0 },
  "TEST-MAINTAINED": { decision: "권고 유지", finalQty: 10.25 }
};
const options = { result, scenario: "SHORTAGE", skus: allRows.map(row => row.sku_code), decisions, canViewAmountData: true, viewTitle: "합성 검산 데이터" };
const inputBefore = JSON.stringify(options);
const create = overrides => {
  const workbook = new ExcelJS.Workbook();
  populateV3Excel(workbook, { ...options, ...overrides });
  return workbook;
};
const output = create();
const bytes = await output.xlsx.writeBuffer();
const reloaded = new ExcelJS.Workbook();
await reloaded.xlsx.load(bytes);
assert.equal(JSON.stringify(options), inputBefore, "Never mutate API or review state.");
assert.deepEqual(reloaded.worksheets.map(sheet => [sheet.name, sheet.state]), [
  ["발주제안", "visible"], ["물류전망", "visible"], ["확인필요", "visible"], ["_계산기준", "hidden"], ["_운송원천", "hidden"]
]);
const proposal = reloaded.getWorksheet("발주제안");
const logistics = reloaded.getWorksheet("물류전망");
const check = reloaded.getWorksheet("확인필요");
const detail = reloaded.getWorksheet("_계산기준");
assert.ok(detail.getCell("B10").value.includes("소급 변경하지 않음"), "Legacy snapshots must not claim ledger sales.");
const ledgerBook = create({ result: { ...result, source_audit: {
  demand_source: { policy: "V3_STOCK_IN_OUT_SALE_AND_ONLINE_V1" }
} } });
assert.ok(ledgerBook.getWorksheet("_계산기준").getCell("B10").value.includes("OUT-SALE (ONLINE)"));
assert.ok(ledgerBook.getWorksheet("_계산기준").getCell("B10").value.includes("재고조정·이동·입고·반품 제외"));
const headers = (sheet, row = 7) => sheet.getRow(row).values.slice(1);
const headerColumn = (sheet, label, row = 7) => {
  const column = headers(sheet, row).indexOf(label) + 1;
  assert.ok(column > 0, `${sheet.name}에 '${label}' 열이 있어야 합니다.`);
  return column;
};
const cellByHeader = (sheet, label, row = 8) => sheet.getCell(row, headerColumn(sheet, label));
const valueByHeader = (sheet, label, row = 8) => cellByHeader(sheet, label, row).value;
const proposalValue = (label, row = 8) => valueByHeader(proposal, label, row);
const proposalCell = (label, row = 8) => cellByHeader(proposal, label, row);
const auditValue = (label, row = 21) => detail.getCell(row, headers(detail, 20).indexOf(label) + 1).value;
const aliasSource = { ...base, product_identity_source_codes: ["TEST-NEEDED", "test-needed"], product_identity_reason_code: "CASE_ONLY_CODE_EXACT_PRODUCT_NAME" };
const aliasBook = create({ result: { ...result, scenarios: { SHORTAGE: { rows: [aliasSource] } } }, skus: [base.sku_code] });
const aliasDetail = aliasBook.getWorksheet("_계산기준");
assert.equal(aliasDetail.getCell(21, headers(aliasDetail, 20).indexOf("동일 제품 원천 상품코드") + 1).value, "TEST-NEEDED / test-needed");
assert.equal(aliasDetail.getCell(21, headers(aliasDetail, 20).indexOf("동일 제품 연결 사유") + 1).value, "CASE_ONLY_CODE_EXACT_PRODUCT_NAME");
assert.equal(proposal.columnCount, 41);
assert.equal(V3_EXCEL_HEADER_ROW, 7);
assert.equal(proposalValue("상품코드"), base.sku_code);
assert.equal(proposalValue("바코드"), base.barcode);
assert.equal(proposalCell("바코드").numFmt, "@");
assert.equal(proposalValue("판매량\n(13주)"), 1300);
assert.equal(proposalValue("월평균\n판매량(/3)\n참고지표"), 433);
assert.notEqual(proposalValue("월평균\n판매량(/3)\n참고지표"), 400, "/3 is not a four-week average.");
assert.equal(proposalValue("주평균\n판매량"), 100);
assert.equal(proposalValue("향후 4주(28일)\n예상 수요"), base.demand_per_period * 4,
  "발주제안의 향후 예상 수요는 1기(7일) 기초수요를 4기로 환산한 값입니다.");
assert.equal(proposalValue("최종분류"), "안정형");
assert.equal(proposalValue("추세판정"), "–");
assert.equal(proposalValue("적용엔진"), "SES");
assert.equal(proposalValue("계절보정\n유무"), "o");
assert.ok(!headers(proposal).includes("운송수단"), "발주제안 sheet drops the transport mode column for every entity (2026-09-08 사용자 요청).");
assert.equal(proposalValue("리드타임\n(달력일)"), base.lead_time_days);
assert.equal(proposalValue("발주주기\n(달력일)"), base.review_days);
for (const [label, key] of Object.entries({
  "리드타임 수요\n(Layer 1)": "layer1", "안전재고\n(Layer 2)": "layer2",
  "발주주기 수요\n(Layer 3)": "layer3", "참고 ROP\n(L1+L2·미사용)": "reorder_point",
  "목표재고\n(S=L1+L2+L3)": "target_stock", "현지 가용재고": "on_hand_qty",
  "본사 창고\n가용재고": "upstream_available_qty", "운송중": "in_transit_qty",
  "입고예정 합계\n(①+②+③)": "unreceived_qty", "확보 물량\n(IP)": "inventory_position",
  "① 미입고\n수량": "open_po_qty", "② PNFM확정\n수량": "pnfm_qty",
  "③ 입고진행중\n수량": "inbound_progress_qty", "④ 입고완료\n수량": "inbound_completed_qty",
  "(hidden)\nZ-score": "z_value"
})) assert.equal(proposalValue(label), base[key], key);
assert.notEqual(proposalValue("① 미입고\n수량"), base.unreceived_qty, "Bucket ① is not combined incoming ①+②+③.");
for (const [label, key] of Object.entries({
  "재고보유\n개월수(MOI)": "reference_moi", "고갈주수\n(현지+운송)": "reference_depletion_weeks",
  "(hidden)\n주간수요σ": "reference_weekly_sigma"
})) assert.equal(proposalValue(label), base[key]);
assert.equal(proposalValue("다음 입고예정\n(운송중 최소 ETA)").toISOString(), "2026-08-30T00:00:00.000Z");
assert.ok(!headers(proposal).includes("조기경보일\n(CV·서비스수준)"), "발주제안 sheet drops the order-timing columns.");
assert.ok(!headers(proposal).includes("예상 발주일\n(평균)"));
assert.ok(!headers(proposal).includes("발주까지 여유\n(주, 평균)"));
assert.ok(!headers(proposal).includes("보수적 발주\n여유(주)"));
assert.equal(auditValue("발주까지 여유\n(주, 평균)"), base.reference_order_slack_weeks, "Order-timing metrics stay traceable in the hidden _계산기준 sheet.");
assert.equal(auditValue("보수적 발주\n여유(주)"), base.reference_conservative_slack_weeks);
assert.equal(auditValue("조기경보일\n(CV·서비스수준)").toISOString(), "2026-08-31T00:00:00.000Z");
assert.equal(auditValue("예상 발주일\n(평균)").toISOString(), "2026-08-31T00:00:00.000Z");
assert.equal(proposalValue("발주 판단\n(IP<S)"), "🔴발주필요");
assert.equal(proposalValue("발주필요수량\n(원시)"), 10.25, "Keep raw precision, not manual 11 or ceil 11.");
assert.equal(proposalValue("단가\n(KRW)"), 1234);
assert.equal(proposalValue("발주필요금액\n(KRW)"), 14808);
assert.equal(proposalValue("단가\n(EUR)"), 0.75);
assert.equal(proposalValue("발주필요금액\n(EUR)"), 9.1875, "Use the server amount, not displayed 10 or reviewed 11 times EUR 0.75.");
assert.equal(proposalCell("발주필요금액\n(EUR)").numFmt, "#,##0.00");
assert.match(proposal.getCell(7, headerColumn(proposal, "발주필요금액\n(EUR)")).note, /order_amount_local/);
assert.match(proposal.getCell(7, headerColumn(proposal, "월평균\n판매량(/3)\n참고지표")).note, /예측엔진 산출값과는 구분/);
assert.match(proposal.getCell("A4").value, /max\(0,S−IP\)/);
assert.match(proposal.getCell("A4").value, /91일/);
assert.equal(proposalValue("발주필요수량\n(원시)", 9), 0);
assert.equal(proposalValue("발주필요금액\n(KRW)", 9), 0);
assert.equal(proposalValue("발주필요금액\n(EUR)", 9), 0);
assert.equal(proposalValue("발주필요금액\n(KRW)", 10), "미확인");
assert.equal(proposalValue("발주필요금액\n(EUR)", 10), "미확인");
assert.equal(proposalValue("발주필요수량\n(원시)", 11), "미산출");
assert.equal(proposalValue("발주필요금액\n(KRW)", 11), "미산출");
assert.equal(proposalValue("발주필요금액\n(EUR)", 11), "미산출");
assert.equal(proposalValue("발주필요금액\n(EUR)", 12), "미산출");
assert.equal(proposalValue("발주필요금액\n(EUR)", 13), 9.1875, "Manual hold does not rewrite the V3 proposal amount.");
assert.equal(proposalValue("월평균\n판매량(/3)\n참고지표", 11), 0, "A held SKU can still have valid zero sales reference.");
assert.equal(check.getCell("A6").value, held.sku_code);
assert.equal(check.getCell("G6").value, held.validation_error);
assert.equal(check.getCell("A7").value, blocked.sku_code);
assert.equal(check.getCell("G7").value, blocked.validation_error);
const crostonCheck = create({ skus: [], attentionSkus: [crostonBlocked.sku_code], result: { ...result, scenarios: { SHORTAGE: { rows: [crostonBlocked] } } } }).getWorksheet("확인필요");
assert.equal(crostonCheck.getCell("G6").value, "Croston 예측을 하려면 판매가 발생한 완료 주가 최소 2개 필요합니다.");
assert.equal(logistics.getCell("C7").value, "0001234567890");
assert.equal(logistics.getCell("C7").numFmt, "@");
assert.equal(logistics.getCell("D7").value, 1300);
assert.equal(logistics.getCell("E7").value, proposalValue("월평균\n판매량(/3)\n참고지표"));
assert.equal(logistics.getCell("F7").value, 100);
assert.equal(logistics.getCell("G7").value, base.on_hand_qty);
assert.equal(logistics.getCell("H7").value, base.in_transit_qty);
assert.equal(logistics.getCell("I7").value, 0.2);
assert.equal(logistics.columnCount, 9);
assert.ok(!headers(logistics, 6).includes("안전재고\n(상하한 적용)"), "물류전망 sheet drops the safety stock column (2026-09-08 사용자 요청).");
assert.deepEqual(headers(logistics, 6), [
  "상품코드", "상품명", "바코드", "판매량\n(13주)", "월평균\n판매량(/3)\n참고지표", "주평균\n판매량",
  "현재고\n(현지가용)", "운송중\n합계", "재고보유\n개월수(MOI)"
]);
assert.match(logistics.getCell("A2").value, /숨김 _운송원천 시트/);
assert.ok(!logistics.model.merges.includes("K4:Y4"));
assert.ok(logistics.model.merges.includes("A5:C5"));
assert.ok(logistics.model.merges.includes("D5:F5"));
assert.ok(logistics.model.merges.includes("G5:I5"));
assert.equal(proposalValue("재고보유\n개월수(MOI)", 11), "–");
assert.equal(auditValue("조기경보일\n(CV·서비스수준)", 24), "–");
assert.equal(auditValue("담당자 검토수량"), 11);
assert.equal(auditValue("담당자 검토수량", 22), null);
assert.equal(auditValue("담당자 검토수량", 24), null);
assert.equal(auditValue("담당자 검토수량", 26), 0);
assert.equal(auditValue("계절지수 적용 상태", 24), "기본값 1.0 연결 · 발주 계산 미완료");
assert.equal(auditValue("1월 연결 계절지수", 24), 1);
assert.equal(auditValue("1월 연결 계절지수", 25), null);
assert.equal(auditValue("계절지수 f1"), base.seasonal_f1);
assert.equal(auditValue("예측 σ(EA/주)"), base.forecast_sigma);
assert.equal(auditValue("계절제거 13주(EA)"), base.adjusted_period_sales[12]);
V3_DETAIL_COLUMNS.forEach((column, index) => {
  if (Object.hasOwn(base, column.key)) assert.equal(detail.getCell(21, index + 1).value,
    column.key === "season_factor_available" ? "연결 완료" : base[column.key], column.key);
  assert.ok(detail.getCell(20, index + 1).note, column.key);
});
for (const label of ["발주필요수량\n(원시)", "발주필요금액\n(KRW)", "판매량\n(13주)", "월평균\n판매량(/3)\n참고지표"]) assert.equal(proposalCell(label).numFmt, "#,##0");
assert.equal(proposalCell("단가\n(KRW)").numFmt, "#,##0.00");
assert.equal(proposalCell("주평균\n판매량").numFmt, "#,##0.0");
assert.equal(proposal.getColumn(headerColumn(proposal, "(hidden)\n주간수요σ")).hidden, true);
assert.equal(proposal.getColumn(headerColumn(proposal, "(hidden)\nZ-score")).hidden, true);
assert.equal(proposal.views[0].xSplit, 3);
assert.equal(proposal.views[0].ySplit, 7);
assert.equal(proposal.views[0].showGridLines, true);
assert.equal(proposal.getCell("A7").fill.fgColor.argb, "FF12324F");
assert.equal(proposalCell("발주필요수량\n(원시)").font.color.argb, "FF7A1F1F");
assert.equal(proposal.getCell("A8").border.bottom.color.argb, "FFC7CDD6");
for (const merge of ["A6:D6", "E6:L6", "M6:N6", "O6:S6", "T6:AE6", "AF6:AM6"]) assert.ok(proposal.model.merges.includes(merge), merge);
assert.ok(proposal.conditionalFormattings.length);
assert.equal(check.views[0].showGridLines, false);

const cashOutput = create({ scenario: "CASH", skus: [base.sku_code, noOrder.sku_code], decisions: {} });
const cashProposal = cashOutput.getWorksheet("발주제안");
assert.equal(valueByHeader(cashProposal, "발주필요수량\n(원시)"), 2.5);
assert.equal(valueByHeader(cashProposal, "발주필요금액\n(KRW)"), 14808);
assert.equal(valueByHeader(cashProposal, "발주필요금액\n(EUR)"), 9.1875);
assert.equal(valueByHeader(cashProposal, "월평균\n판매량(/3)\n참고지표"), 433);
const subset = create({ skus: [manualHold.sku_code, base.sku_code] });
assert.equal(subset.getWorksheet("발주제안").getCell("A8").value, manualHold.sku_code);
assert.equal(subset.getWorksheet("발주제안").rowCount, 9);
assert.equal(subset.getWorksheet("물류전망").columnCount, 9);
assert.equal(subset.getWorksheet("_운송원천").rowCount, 9);
assert.equal(subset.getWorksheet("_운송원천").getCell("H2").value, "sku-1");
assert.equal(subset.getWorksheet("_운송원천").getCell("H6").value, "sku-2");
const hidden = create({ canViewAmountData: false });
// Reproduce the actual UI path: proposals exclude blocked SKUs, companion sheet does not.
const uiRows = allRows.map(row => ({ sku: row.sku_code, signal: row.order_signal, calculable: row.calculable,
  productName: row.product_name, brand: row.brand, orderAmountKrw: row.order_amount_krw ?? 0 }));
const proposalScope = reviewExportRows(filterReviewRows(uiRows, { view: "needed" }, {}), new Set([base.sku_code]));
const checkScope = attentionExportRows(uiRows, { view: "needed" }, new Set([base.sku_code]));
const companionOptions = { skus: proposalScope.map(row => row.sku), attentionSkus: checkScope.map(row => row.sku),
  attentionScope: "브랜드·검색 조건의 전체 보류·차단 상품" };
const companion = new ExcelJS.Workbook();
await companion.xlsx.load(await create(companionOptions).xlsx.writeBuffer());
assert.equal(companion.getWorksheet("발주제안").rowCount, 8);
assert.equal(valueByHeader(companion.getWorksheet("발주제안"), "발주필요수량\n(원시)"), base.raw_order_quantity);
assert.equal(companion.getWorksheet("물류전망").rowCount, 7);
assert.equal(companion.getWorksheet("물류전망").columnCount, 9);
assert.deepEqual([6, 7].map(row => companion.getWorksheet("확인필요").getCell(`A${row}`).value), [held.sku_code, blocked.sku_code]);
assert.equal(companion.getWorksheet("확인필요").getCell("G6").value, held.validation_error);
assert.equal(companion.getWorksheet("확인필요").getCell("G7").value, blocked.validation_error);
assert.equal(companion.getWorksheet("확인필요").getCell("D6").value, 0);
assert.equal(companion.getWorksheet("확인필요").getCell("E6").value, "미확인");
assert.match(companion.getWorksheet("확인필요").getCell("A3").value, /확인필요 2개.*브랜드·검색/);
const companionAudit = companion.getWorksheet("_계산기준");
const skuColumn = headers(companionAudit, 20).indexOf("상품코드") + 1;
assert.deepEqual([21, 22, 23].map(row => companionAudit.getCell(row, skuColumn).value), [base.sku_code, held.sku_code, blocked.sku_code]);
const reasonColumn = headers(companionAudit, 20).indexOf("보류·차단 사유") + 1;
assert.equal(companionAudit.getCell(23, reasonColumn).value, blocked.validation_error);
assert.equal(create({ ...companionOptions, skus: allRows.map(row => row.sku_code) }).getWorksheet("_계산기준").rowCount, 27, "Do not duplicate overlapping audit rows.");
const onlyCheck = create({ skus: [], attentionSkus: [blocked.sku_code] });
assert.equal(onlyCheck.getWorksheet("발주제안").rowCount, 7);
assert.equal(onlyCheck.getWorksheet("확인필요").getCell("A6").value, blocked.sku_code);
assert.equal(onlyCheck.getWorksheet("_계산기준").getCell(21, skuColumn).value, blocked.sku_code);
assert.match(create({ skus: [base.sku_code], attentionSkus: [] }).getWorksheet("확인필요").getCell("A6").value, /상품이 없습니다/);
const cashBlocked = { ...blocked, validation_error: "현금 시나리오 차단 사유", reference_sales_13w: 17 };
const scenarioBook = create({ scenario: "CASH", skus: [base.sku_code], attentionSkus: [blocked.sku_code],
  result: { ...result, scenarios: { ...result.scenarios, CASH: { rows: [cash, cashBlocked] } } } });
assert.equal(scenarioBook.getWorksheet("확인필요").getCell("G6").value, cashBlocked.validation_error);
assert.equal(scenarioBook.getWorksheet("확인필요").getCell("D6").value, 17);
assert.throws(() => create({ ...companionOptions, scenario: "CASH" }), /일치하지/);
assert.throws(() => create({ attentionSkus: ["MISSING"] }), /일치하지/);
assert.throws(() => create({ attentionSkus: [base.sku_code] }), /일치하지/);
assert.throws(() => create({ attentionSkus: [held.sku_code, held.sku_code] }), /중복/);
const noAmountCompanion = create({ ...companionOptions, canViewAmountData: false });
assert.ok(!JSON.stringify(noAmountCompanion.model).includes("14808"));
assert.equal(noAmountCompanion.getWorksheet("확인필요").getCell("G7").value, blocked.validation_error);
const hiddenReloaded = new ExcelJS.Workbook();
await hiddenReloaded.xlsx.load(await hidden.xlsx.writeBuffer());
const hiddenProposal = hiddenReloaded.getWorksheet("발주제안");
for (const label of ["단가\n(KRW)", "발주필요금액\n(KRW)", "단가\n(EUR)", "발주필요금액\n(EUR)"]) assert.equal(valueByHeader(hiddenProposal, label), null);
assert.ok(!JSON.stringify(hiddenReloaded.model).includes("14808"), "No money leakage through hidden metadata.");
assert.ok(!JSON.stringify(hiddenReloaded.model).includes("9.1875"), "No local amount leakage through hidden metadata.");
assert.equal(valueByHeader(hiddenProposal, "판매량\n(13주)"), 1300, "Permissions do not shift columns.");
const usa = create({ result: { ...result, entity_code: "USA" } }).getWorksheet("발주제안");
assert.equal(valueByHeader(usa, "단가\n(USD)"), "미확인", "Never relabel an EUR source value as USD.");
assert.equal(valueByHeader(usa, "발주필요금액\n(USD)"), "미확인", "Never relabel an EUR amount as USD.");
const usdSource = { ...base, local_currency: "USD", unit_price_local: 3, order_amount_local: 30.75 };
const usd = create({ result: { ...result, entity_code: "USA", scenarios: { SHORTAGE: { rows: [usdSource] } } }, skus: [base.sku_code] });
assert.equal(valueByHeader(usd.getWorksheet("발주제안"), "발주필요금액\n(USD)"), 30.75);
for (const amount of [undefined, null, Infinity]) {
  const noLocal = create({ result: { ...result, scenarios: { SHORTAGE: { rows: [{ ...base, order_amount_local: amount }] } } }, skus: [base.sku_code] });
  assert.equal(valueByHeader(noLocal.getWorksheet("발주제안"), "발주필요금액\n(EUR)"), "미확인", "Do not calculate a missing server amount in Excel.");
}
const serverValue = create({ result: { ...result, scenarios: { SHORTAGE: { rows: [{ ...base, order_amount_local: 42.1234 }] } } }, skus: [base.sku_code] });
assert.equal(valueByHeader(serverValue.getWorksheet("발주제안"), "발주필요금액\n(EUR)"), 42.1234, "Export the exact server value, never rederive it.");
const hqOutput = create({ result: { ...result, entity_code: "HQ" } });
const hq = hqOutput.getWorksheet("발주제안");
const hqCheck = hqOutput.getWorksheet("확인필요");
const hqAudit = hqOutput.getWorksheet("_계산기준");
assert.equal(hq.columnCount, 36);
assert.ok(!headers(hq).includes("운송수단"), "HQ export drops the transport mode column.");
assert.ok(!headers(proposal).includes("운송수단"), "PL/USA proposal exports drop the transport mode column too (2026-09-08 사용자 요청).");
assert.ok(!headers(hq).includes("다음 입고예정\n(운송중 최소 ETA)"), "HQ export drops the next-ETA column (not applicable for HQ international transport).");
assert.ok(headers(proposal).includes("다음 입고예정\n(운송중 최소 ETA)"), "PL/USA proposal exports keep the next-ETA column.");
assert.ok(!headers(hq).includes("본사 창고\n가용재고"));
assert.ok(headers(hq).includes("본사 가용재고"));
assert.ok(!headers(hq).includes("운송중"));
assert.ok(!headers(hq).includes("단가\n(EUR)"));
assert.equal(valueByHeader(hq, "단가\n(KRW)"), base.unit_price_krw);
assert.equal(valueByHeader(hq, "발주필요금액\n(KRW)"), base.order_amount_krw, "HQ retains one authoritative KRW proposal amount.");
for (const merge of ["A6:D6", "E6:L6", "M6:N6", "O6:S6", "T6:AB6", "AC6:AH6"]) assert.ok(hq.model.merges.includes(merge), merge);
assert.equal(hq.getColumn(headerColumn(hq, "(hidden)\n주간수요σ")).hidden, true);
assert.equal(hq.getColumn(headerColumn(hq, "(hidden)\nZ-score")).hidden, true);
assert.equal(hqOutput.getWorksheet("물류전망"), undefined, "HQ export drops the logistics forecast sheet entirely.");
assert.deepEqual(hqOutput.worksheets.map(sheet => sheet.name), ["발주제안", "확인필요", "_계산기준", "_운송원천"]);
assert.equal(hqCheck.columnCount, 6);
assert.ok(!headers(hqCheck, 5).includes("운송중 수량"));
assert.ok(headers(hqAudit, 20).includes("운송중(EA)"), "Hidden calculation evidence keeps HQ transit_qty=0 for audit.");
assert.ok(headers(proposal).includes("운송중"), "PL/USA proposal exports keep the real transit operand.");
assert.ok(headers(logistics, 6).includes("운송중\n합계"), "PL/USA logistics exports keep transit totals.");
assert.ok(headers(check, 5).includes("운송중 수량"), "PL/USA attention exports keep transit quantities.");
const oldSource = { ...base, reference_sales_status: undefined, reference_sales_days: undefined };
const old = create({ result: { ...result, scenarios: { SHORTAGE: { rows: [oldSource] } } }, skus: [base.sku_code] });
assert.equal(valueByHeader(old.getWorksheet("발주제안"), "월평균\n판매량(/3)\n참고지표"), "미확인", "Never approximate 91 days from 28-day forecast periods.");
const hqEta = create({ result: { ...result, entity_code: "HQ", scenarios: { SHORTAGE: { rows: [{ ...base, eta_reference_status: "NOT_APPLICABLE", eta_bucket_quantities: null, next_eta: null }] } } }, skus: [base.sku_code] });
assert.equal(hqEta.getWorksheet("물류전망"), undefined, "HQ export drops the logistics forecast sheet entirely.");
assert.ok(!headers(hqEta.getWorksheet("발주제안")).includes("다음 입고예정\n(운송중 최소 ETA)"), "HQ export drops the next-ETA column even when the source row carries ETA fields.");
for (const sheet of reloaded.worksheets) sheet.eachRow(row => row.eachCell(cell => {
  assert.notEqual(cell.type, ExcelJS.ValueType.Formula, `${sheet.name}!${cell.address} must be values only`);
}));
assert.throws(() => create({ skus: ["MISSING"] }), /일치하지/);
assert.throws(() => create({ skus: [base.sku_code, base.sku_code] }), /중복/);
assert.throws(() => create({ result: { ...result, scenarios: { CASH: result.scenarios.CASH } } }), /시나리오/);
assert.throws(() => create({ result: { ...result, scenarios: { ...result.scenarios, SHORTAGE: { rows: [base, base] } } } }), /중복/);
assert.throws(() => create({ result: { ...result, as_of: "2026-02-31" } }), /기준일/);
assert.throws(() => create({ result: { ...result, result_schema_version: 13 } }), /다시 분석/);
assert.throws(() => create({ result: { ...result, result_schema_version: 17 } }), /재고 오류·경고.*다시 분석/);
assert.throws(() => create({ result: { ...result, result_schema_version: 18 } }), /외화 제안금액.*다시 분석/);
assert.throws(() => create({ result: { ...result, result_schema_version: 19 } }), /미입고 원천 행 존재 여부.*다시 분석/);
for (const entity of ["PL", "USA"]) {
  assert.throws(() => create({ result: { ...result, entity_code: entity, result_schema_version: 20 } }), /V2 동일 ETA.*다시 분석/);
}
assert.throws(() => create({ result: { ...result, entity_code: "HQ", result_schema_version: 20 } }), /운송수단.*다시 분석/);
assert.throws(() => create({ result: { ...result, result_schema_version: 21 } }), /운송수단.*다시 분석/);
assert.throws(() => create({ result: { ...result, result_schema_version: 22 } }), /순수 정기발주.*다시 분석/);
assert.throws(() => create({ result: { ...result, result_schema_version: 23 } }), /13주 수요창.*다시 분석/);
assert.equal(create({ skus: [] }).getWorksheet("발주제안").rowCount, 7);
const literal = create({ result: { ...result, scenarios: { SHORTAGE: { rows: [{ ...base, product_name: '=HYPERLINK("https://invalid.example")', order_amount_krw: Infinity }] } } }, skus: [base.sku_code] });
assert.equal(literal.getWorksheet("발주제안").getCell("B8").type, ExcelJS.ValueType.String);
assert.equal(valueByHeader(literal.getWorksheet("발주제안"), "발주필요금액\n(KRW)"), "미확인");

// V2 inventory nulls remain calculable with a visible warning, not a silent 0.
const inventoryWarning = "① 미입고 수량이 비어 있어 V2 기준으로 0을 적용했습니다. 원천 수량을 확인하세요.";
const nullInventory = { ...base, open_po_qty: 0, pnfm_qty: 20, inbound_progress_qty: 30, unreceived_qty: 50,
  inventory_warnings: ["INCOMING_QTY_NULL_AS_ZERO"], inventory_warning_messages: [inventoryWarning] };
const warningBook = create({ result: { ...result, scenarios: { SHORTAGE: { rows: [nullInventory] } } }, skus: [base.sku_code] });
const warningSheet = warningBook.getWorksheet("발주제안");
assert.equal(valueByHeader(warningSheet, "① 미입고\n수량"), 0);
assert.equal(valueByHeader(warningSheet, "② PNFM확정\n수량"), 20);
assert.equal(valueByHeader(warningSheet, "③ 입고진행중\n수량"), 30);
assert.equal(valueByHeader(warningSheet, "발주 판단\n(IP<S)"), "⚠확인후발주");
assert.ok(cellByHeader(warningSheet, "발주 판단\n(IP<S)").note.includes(inventoryWarning));
assert.equal(valueByHeader(warningSheet, "발주필요수량\n(원시)"), base.raw_order_quantity);
const warningAudit = warningBook.getWorksheet("_계산기준");
assert.equal(warningAudit.getCell(21, headers(warningAudit, 20).indexOf("V2 재고 경고 코드") + 1).value, "INCOMING_QTY_NULL_AS_ZERO");

// No source row and a missing individual field both display as 0 (not yet
// reached that stage / not tracked); reported zeros stay numeric either way.
for (const entity of ["PL", "USA", "HQ"]) {
  for (const scenario of ["CASH", "SHORTAGE"]) {
    const cases = [
      { ...base, sku_code: "ABSENT", inbound_status_source_present: false,
        open_po_qty: 0, pnfm_qty: null, inbound_progress_qty: null, inbound_completed_qty: null },
      { ...base, sku_code: "ZERO", open_po_qty: 0, pnfm_qty: 0, inbound_progress_qty: 0, inbound_completed_qty: 0 },
      { ...base, sku_code: "PARTIAL", pnfm_qty: null },
      { ...base, sku_code: "UNKNOWN", inbound_status_source_present: null, pnfm_qty: null },
      { ...held, sku_code: "HELD-ABSENT", inbound_status_source_present: false },
    ];
    const before = JSON.stringify(cases);
    const book = create({ scenario, skus: cases.map(row => row.sku_code),
      result: { ...result, entity_code: entity, scenarios: { [scenario]: { rows: cases } } } });
    const roundTrip = new ExcelJS.Workbook();
    await roundTrip.xlsx.load(await book.xlsx.writeBuffer());
    const sheet = roundTrip.getWorksheet("발주제안");
    const proposalHeaders = headers(sheet);
    const inboundColumn = (label) => proposalHeaders.indexOf(label) + 1;
    const inboundHeaders = ["① 미입고\n수량", "② PNFM확정\n수량", "③ 입고진행중\n수량", "④ 입고완료\n수량"];
    for (const label of inboundHeaders) {
      const col = inboundColumn(label);
      assert.equal(sheet.getCell(8, col).value, 0);
      assert.equal(sheet.getCell(9, col).value, 0);
      assert.equal(sheet.getCell(12, col).value, 0);
      assert.match(sheet.getCell(7, col).note, /원천 행이 없거나/);
    }
    assert.deepEqual(inboundHeaders.map(label => sheet.getCell(10, inboundColumn(label)).value), [5, 0, 7, 99]);
    assert.equal(sheet.getCell(11, inboundColumn("② PNFM확정\n수량")).value, 0);
    assert.equal(valueByHeader(sheet, "발주필요수량\n(원시)"), base.raw_order_quantity);
    assert.equal(valueByHeader(sheet, "확보 물량\n(IP)"), base.inventory_position);
    assert.equal(valueByHeader(sheet, "발주필요수량\n(원시)", 12), "미산출");
    const audit = roundTrip.getWorksheet("_계산기준");
    const presenceCol = headers(audit, 20).indexOf("미입고/입고 원천 행 존재") + 1;
    assert.equal(audit.getCell(21, presenceCol).value, false);
    assert.equal(audit.getCell(22, presenceCol).value, true);
    assert.equal(JSON.stringify(cases), before);
  }
}

// A V2 error must not export even a stale positive quantity/amount as a result.
const invalidInventory = { ...nullInventory, calculable: false, data_status: "BLOCKED", order_signal: "계산 차단",
  reason_code: "V2_INVENTORY_INVALID", validation_error: "Synthetic negative inventory",
  inventory_validation_error: "Synthetic negative inventory", inventory_warnings: ["INCOMING_QTY_NEGATIVE"],
  inventory_warning_messages: ["① 미입고 수량에 음수가 있어 V2 기준으로 발주 계산을 차단했습니다."] };
const invalidBook = create({ result: { ...result, scenarios: { SHORTAGE: { rows: [invalidInventory] } } }, skus: [base.sku_code] });
const invalidSheet = invalidBook.getWorksheet("발주제안");
assert.equal(valueByHeader(invalidSheet, "발주 판단\n(IP<S)"), "⚠계산차단");
assert.equal(valueByHeader(invalidSheet, "발주필요수량\n(원시)"), "미산출");
assert.equal(valueByHeader(invalidSheet, "발주필요금액\n(KRW)"), "미산출");
assert.equal(valueByHeader(invalidSheet, "발주필요금액\n(EUR)"), "미산출");
assert.equal(invalidBook.getWorksheet("확인필요").getCell("G6").value, "Synthetic negative inventory");

// Optional local reference comparison. Neither the supplied data nor its path is checked into fixtures.
if (process.env.V3_EXCEL_TEMPLATE_PATH) {
  const template = new ExcelJS.Workbook();
  await template.xlsx.readFile(process.env.V3_EXCEL_TEMPLATE_PATH);
  for (const name of ["확인필요"]) {
    const actual = reloaded.getWorksheet(name);
    const expected = template.getWorksheet(name);
    const count = 7;
    for (let col = 1; col <= count; col++) assert.equal(actual.getColumn(col).width ?? actual.properties.defaultColWidth, expected.getColumn(col).width, `${name} column ${col}`);
    for (const merge of expected.model.merges) assert.ok(actual.model.merges.includes(merge), `${name} merge ${merge}`);
    assert.equal(actual.views[0].ySplit, expected.views[0].ySplit);
    assert.equal(actual.views[0].xSplit, expected.views[0].xSplit);
    assert.deepEqual(actual.getCell("A1").fill, expected.getCell("A1").fill);
    assert.deepEqual(actual.getCell("A1").font, expected.getCell("A1").font);
  }
  const expectedProposal = template.getWorksheet("발주제안");
  assert.equal(proposal.views[0].ySplit, expectedProposal.views[0].ySplit);
  assert.equal(proposal.views[0].xSplit, expectedProposal.views[0].xSplit);
  assert.deepEqual(proposal.getCell("A1").fill, expectedProposal.getCell("A1").fill);
  assert.deepEqual(proposal.getCell("A1").font, expectedProposal.getCell("A1").font);
  for (const label of ["상품코드", "상품명", "브랜드"]) {
    assert.equal(proposal.getColumn(headerColumn(proposal, label)).width, expectedProposal.getColumn(headerColumn(expectedProposal, label)).width, `${label} width`);
  }
  if (process.env.V3_EXCEL_QA_DIR) {
    const formulas = Object.fromEntries(Object.entries({
      "발주제안": ["O8", "AC8", "AE8", "AF8", "AG8", "AH8"]
    }).map(([name, cells]) => [name, Object.fromEntries(cells.map(cell => [cell, template.getWorksheet(name).getCell(cell).formula]))]));
    await mkdir(resolve(process.env.V3_EXCEL_QA_DIR), { recursive: true });
    await writeFile(resolve(process.env.V3_EXCEL_QA_DIR, "reference-formulas-only.json"), JSON.stringify(formulas));
  }
}
if (process.env.V3_EXCEL_QA_DIR) {
  const directory = resolve(process.env.V3_EXCEL_QA_DIR);
  await mkdir(directory, { recursive: true });
  await writeFile(resolve(directory, "v3-excel-synthetic.xlsx"), bytes);
  await writeFile(resolve(directory, "v3-excel-hq-synthetic.xlsx"), await hqOutput.xlsx.writeBuffer());
}
console.log("V3 Excel checks passed: reference template, raw calculations, 13-week /3 reference, null/zero, scenarios, permissions, identity and formatting.");

// Same mapping, streamed row-by-row: compare decoded XLSX cells (not source code)
// against the document writer, including every hidden-sheet cell and all notes.
for (const overrides of [{}, { canViewAmountData: false }, companionOptions, { skus: [], attentionSkus: [blocked.sku_code] },
  { scenario: "CASH", skus: [base.sku_code], attentionSkus: [] }, { result: { ...result, entity_code: "HQ" } }]) {
  const expected = new ExcelJS.Workbook();
  await expected.xlsx.load(await create(overrides).xlsx.writeBuffer());
  const { stream, done } = createExcelStream({ ...options, ...overrides }, new AbortController().signal);
  const chunks = [];
  const consumed = (async () => { for await (const chunk of stream) chunks.push(chunk); })();
  await Promise.all([done, consumed]);
  const actual = new ExcelJS.Workbook();
  await actual.xlsx.load(Buffer.concat(chunks));
  assert.deepEqual(actual.worksheets.map(sheet => [sheet.name, sheet.state]), expected.worksheets.map(sheet => [sheet.name, sheet.state]));
  for (const wanted of expected.worksheets) {
    const got = actual.getWorksheet(wanted.name);
    assert.equal(got.rowCount, wanted.rowCount, wanted.name);
    assert.deepEqual(got.views, wanted.views, `${wanted.name} views`);
    assert.deepEqual(got.model.merges, wanted.model.merges, `${wanted.name} merges`);
    for (const key of ["orientation", "fitToPage", "fitToWidth", "fitToHeight", "printTitlesRow"]) {
      assert.equal(got.pageSetup[key], wanted.pageSetup[key], `${wanted.name} ${key}`);
    }
    for (let column = 1; column <= wanted.columnCount; column++) {
      assert.equal(got.getColumn(column).width, wanted.getColumn(column).width, `${wanted.name} width ${column}`);
      assert.equal(Boolean(got.getColumn(column).hidden), Boolean(wanted.getColumn(column).hidden), `${wanted.name} hidden ${column}`);
    }
    for (let row = 1; row <= wanted.rowCount; row++) {
      assert.equal(got.getRow(row).height, wanted.getRow(row).height, `${wanted.name} height ${row}`);
      for (let column = 1; column <= wanted.columnCount; column++) {
        const actualCell = got.getCell(row, column), expectedCell = wanted.getCell(row, column);
        for (const key of ["value", "style", "note"]) assert.deepEqual(actualCell[key], expectedCell[key], `${wanted.name} ${actualCell.address} ${key}`);
      }
    }
    assert.deepEqual(got.conditionalFormattings, wanted.conditionalFormattings, `${wanted.name} conditional formatting`);
    assert.deepEqual(got.autoFilter, wanted.autoFilter, `${wanted.name} filter`);
  }
}
console.log("V3 streaming XLSX matches all document-writer values, styles, notes, views and scopes.");
