import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  canViewAmountData,
  getUserPermissions,
  isAmountField,
  sanitizeAmountData
} from "../lib/amount-permissions.ts";

assert.equal(canViewAmountData("adminmaster"), true);
assert.equal(canViewAmountData(" IA "), true);
for (const username of ["eu_manager", "bm1", "bm2", "bm3", "my_team", "vn_team", "hnb_team", "sales_team", "", undefined]) {
  assert.equal(canViewAmountData(username), false, username);
}

assert.deepEqual(getUserPermissions("bm1"), {
  canViewAmountData: false,
  canDownloadAmountData: false,
  canExportAmountReport: false
});
assert.equal(isAmountField("매출액"), true);
assert.equal(isAmountField("sales_amount"), true);
assert.equal(isAmountField("재고금액"), true);
assert.equal(isAmountField("매출 비중"), false);
assert.equal(isAmountField("sales_share"), false);
assert.equal(isAmountField("판매수량"), false);
assert.equal(isAmountField("순위"), false);

const sanitized = sanitizeAmountData({
  매출액: 123456,
  판매수량: 12,
  점유율: 20.5,
  metric: "판매금액",
  value: "₩123,456",
  htmlSnapshot: "<div>₩123,456</div>",
  rows: [{ sales_amount: 10, sales_share: 33.3, quantity: 4, rank: 1 }]
});

assert.deepEqual(sanitized, {
  판매수량: 12,
  점유율: 20.5,
  metric: "판매금액",
  htmlSnapshot: null,
  rows: [{ sales_share: 33.3, quantity: 4, rank: 1 }]
});

const orderScreenSource = readFileSync(
  new URL("../components/redesign/screens/order/OrderScreenExact.tsx", import.meta.url),
  "utf8"
);
const orderModelSource = readFileSync(
  new URL("../components/redesign/screens/order/useOrderScreenModel.tsx", import.meta.url),
  "utf8"
);
const crossScreenSource = readFileSync(
  new URL("../components/redesign/screens/cross/CrossAnalysisScreenExact.tsx", import.meta.url),
  "utf8"
);
const crossControlsSource = readFileSync(
  new URL("../components/redesign/screens/cross/CrossAnalysisControls.tsx", import.meta.url),
  "utf8"
);
const crossReportSource = readFileSync(
  new URL("../components/redesign/screens/cross/useCrossAnalysisReport.ts", import.meta.url),
  "utf8"
);
const brandReportPreviewSource = readFileSync(
  new URL("../components/redesign/screens/report/BrandReportPreview.tsx", import.meta.url),
  "utf8"
);
const brandReportPdfSource = readFileSync(
  new URL("../components/redesign/screens/report/reportPdfDocument.ts", import.meta.url),
  "utf8"
);
assert.match(orderScreenSource, /<OrderMetricCard label=\{"총 발주필요금액"\}/);
assert.match(orderScreenSource, /<dt className="text-muted">발주 필요금액<\/dt>/);
assert.doesNotMatch(orderScreenSource, /permissions\.canViewAmountData/);
assert.match(orderModelSource, /key: "amount"/);
assert.match(orderModelSource, /const visibleOrderTableColumns = orderTableColumns/);
assert.match(
  orderModelSource,
  /downloadOrderRowsXlsx\([\s\S]*?ESM_order_review_filtered_[\s\S]*?true\s*\)/,
  "발주 탭의 브랜드 데이터 내보내기는 일반 계정에도 발주금액을 포함해야 함"
);
assert.doesNotMatch(orderModelSource, /permissions\.canDownloadAmountData/);
assert.match(crossScreenSource, /canExportReport=\{canExportAmountReport\}/);
assert.match(crossControlsSource, /\{canExportReport \? <button[\s\S]*?cross-export-report/);
assert.match(crossReportSource, /if \(!canExportReport \|\| exportingCrossPdf\) return/);
assert.match(brandReportPreviewSource, /metricRows\.length === 3[\s\S]*?"sm:grid-cols-3"/);
assert.match(brandReportPdfSource, /grid-template-columns:repeat\(\$\{Math\.max\(metricRows\.length, 1\)\},1fr\)/);

console.log("amount permission policy tests passed");
