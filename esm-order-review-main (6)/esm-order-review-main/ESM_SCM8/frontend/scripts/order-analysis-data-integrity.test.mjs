import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  calculateStockGapShortageQty,
  computeStockGapItem,
  formatDate,
  isDormantStockGapItem,
  stockGapStatusOrder
} from "../lib/stock-gap.ts";
import {
  isOrderExcludedRow,
  isRequiredOrderReviewRow,
  orderReviewRowFromTable,
  stockGapItemFromOrderReview
} from "../lib/api/mappers.ts";

const historical = computeStockGapItem(
  {
    sku: "HISTORICAL-001",
    productCode: "HISTORICAL-001",
    productName: "Historical test",
    brand: "Test",
    baseDate: "2026-01-01",
    availableQty: 1000,
    recent3mSalesQty: 900,
    avgDailySalesQty: 10,
    stockoutDate: null,
    earliestEtaDate: null,
    etaItems: []
  },
  new Date(2026, 6, 15)
);

assert.equal(historical.status, "sufficient", "과거 분석 결과가 실행일 시계에 의존합니다.");
assert.equal(historical.baseDate, "2026-01-01");
assert.equal(formatDate(historical.stockoutDate), "2026-04-11");

// 기준일보다 이른 ETA는 이미 입고됐거나 지연된 건이므로 미래 입고로 쓰면 안 된다.
const pastEta = computeStockGapItem(
  {
    sku: "PAST-ETA-001",
    productCode: "PAST-ETA-001",
    productName: "Past ETA test",
    brand: "Test",
    baseDate: "2026-07-24",
    availableQty: 300,
    recent3mSalesQty: 900,
    avgDailySalesQty: 10,
    stockoutDate: null,
    earliestEtaDate: "2026-06-12",
    etaItems: []
  },
  new Date(2026, 6, 24)
);

assert.equal(pastEta.earliestEtaDate, null, "기준일 이전 ETA가 가장 빠른 ETA로 쓰이고 있습니다.");
assert.equal(formatDate(pastEta.pastEtaDate), "2026-06-12", "과거 ETA는 확인용으로 남아야 합니다.");
assert.equal(pastEta.gapDays, null, "과거 ETA로 공백 일수를 계산하면 안 됩니다.");
assert.equal(pastEta.gapTiming, "unknown");
assert.notEqual(pastEta.status, "sufficient", "과거 ETA를 미래 입고로 보고 안전 판정하면 안 됩니다.");

const futureEta = computeStockGapItem(
  {
    sku: "FUTURE-ETA-001",
    productCode: "FUTURE-ETA-001",
    productName: "Future ETA test",
    brand: "Test",
    baseDate: "2026-07-24",
    availableQty: 300,
    recent3mSalesQty: 900,
    avgDailySalesQty: 10,
    stockoutDate: null,
    earliestEtaDate: "2026-09-30",
    etaItems: []
  },
  new Date(2026, 6, 24)
);
assert.equal(formatDate(futureEta.earliestEtaDate), "2026-09-30", "미래 ETA는 그대로 써야 합니다.");
assert.equal(futureEta.pastEtaDate, null);
assert.equal(futureEta.gapDays, 38, "공백 일수는 소진일과 미래 ETA 사이의 일수입니다.");

// 이미 소진 + 예정 입고 없음은 '검토필요'(판매 이력 없는 행과 같은 버킷)로 묻히면 안 된다.
const gapRow = (overrides) =>
  computeStockGapItem(
    {
      sku: "GAP-001",
      productCode: "GAP-001",
      productName: "Gap status test",
      brand: "Test",
      baseDate: "2026-07-24",
      availableQty: 0,
      recent3mSalesQty: 900,
      avgDailySalesQty: 10,
      stockoutDate: null,
      earliestEtaDate: null,
      etaItems: [],
      ...overrides
    },
    new Date(2026, 6, 24)
  );

assert.equal(gapRow({}).status, "stockout_no_inbound", "소진 + 입고예정 없음은 별도 상태여야 합니다.");
assert.equal(gapRow({ availableQty: 5 }).status, "stockout_no_inbound", "하루치 미만 재고도 소진 당일로 봅니다.");
assert.equal(gapRow({ availableQty: 300 }).status, "waiting_eta", "아직 소진 전이면 ETA 대기 상태를 유지해야 합니다.");
assert.equal(gapRow({ availableQty: 3000 }).status, "sufficient", "90일 이상 여유는 정상 판정을 유지해야 합니다.");
assert.equal(gapRow({ recent3mSalesQty: 0, avgDailySalesQty: 0 }).status, "needs_check", "판매 이력이 없으면 확인필요로 남습니다.");
// 미래 ETA가 있으면 공백 구간을 계산할 수 있으므로 기존 재고공백(긴급) 집계가 그대로 유지된다.
assert.equal(gapRow({ earliestEtaDate: "2026-08-20" }).status, "urgent_replenishment");
assert.equal(stockGapStatusOrder.indexOf("stockout_no_inbound") < stockGapStatusOrder.indexOf("waiting_eta"), true,
  "입고예정 없는 소진 행은 ETA 대기보다 위에 정렬되어야 합니다.");

// 판매·재고·운송·미입고가 전부 없는 행만 기본 목록에서 숨긴다. 하나라도 있으면 남겨야 한다.
assert.equal(isDormantStockGapItem({ availableQty: 0, recent3mSalesQty: 0, avgDailySalesQty: 0, inTransitQty: 0, openPoQty: 0 }), true);
assert.equal(isDormantStockGapItem({ availableQty: null, recent3mSalesQty: null }), true, "값이 없는 행도 빈 행입니다.");
assert.equal(isDormantStockGapItem({ availableQty: 5, recent3mSalesQty: 0, inTransitQty: 0, openPoQty: 0 }), false, "재고가 있으면 남겨야 합니다.");
assert.equal(isDormantStockGapItem({ availableQty: 0, recent3mSalesQty: 90, inTransitQty: 0, openPoQty: 0 }), false, "판매 이력이 있으면 남겨야 합니다.");
assert.equal(isDormantStockGapItem({ availableQty: 0, recent3mSalesQty: 0, inTransitQty: 10, openPoQty: 0 }), false, "운송중 물량이 있으면 남겨야 합니다.");
assert.equal(isDormantStockGapItem({ availableQty: 0, recent3mSalesQty: 0, inTransitQty: 0, openPoQty: 10 }), false, "미입고 물량이 있으면 남겨야 합니다.");
// 원본 행과 세션 복구용 camelCase 행 모두에서 운송중·미입고를 읽어야 판정이 흔들리지 않는다.
const rawDormant = stockGapItemFromOrderReview(
  { 상품코드: "DORMANT-1", "EU 현지 재고": 0, 기준_3M_판매수량: 0, 운송중: 0, "미입고 수량": 0, "일평균 판매수량": 0 },
  []
);
assert.equal(isDormantStockGapItem(rawDormant), true);
const rawActive = stockGapItemFromOrderReview(
  { 상품코드: "ACTIVE-1", "EU 현지 재고": 0, 기준_3M_판매수량: 0, 운송중: 250, "미입고 수량": 0, "일평균 판매수량": 0 },
  []
);
assert.equal(rawActive.inTransitQty, 250);
assert.equal(isDormantStockGapItem(rawActive), false);
const camelActive = stockGapItemFromOrderReview(
  orderReviewRowFromTable({ 상품코드: "ACTIVE-2", "EU 현지 재고": 0, 기준_3M_판매수량: 0, 운송중: 0, "미입고 수량": 40 }),
  []
);
assert.equal(camelActive.openPoQty, 40, "세션 복구 행에서도 미입고 수량을 읽어야 합니다.");
assert.equal(isDormantStockGapItem(camelActive), false);

assert.equal(
  calculateStockGapShortageQty({
    gapDays: 5,
    dailySalesQty: 10,
    urgentReplenishmentQty: 999,
    shortageQty: 888
  }),
  50,
  "부족수량은 공백일수 × 일평균 판매량 계약을 따라야 합니다."
);
assert.equal(calculateStockGapShortageQty({ gapDays: 2, dailySalesQty: 2.2 }), 5);
assert.equal(calculateStockGapShortageQty({ gapDays: null, dailySalesQty: 10 }), 0);
assert.equal(formatDate("2027-01-02"), "2027-01-02", "날짜에서 연도를 제거하면 안 됩니다.");

const workspaceSource = await readFile(new URL("../components/redesign/SiliconAnalyticsWorkspace.tsx", import.meta.url), "utf8");
const gapScreenModuleFiles = [
  "../components/redesign/screens/gap/GapScreenExact.tsx",
  "../components/redesign/screens/gap/useGapScreenModel.tsx",
  "../components/redesign/screens/gap/useGapScreenData.ts",
  "../components/redesign/screens/gap/gapScreenModel.ts",
  "../components/redesign/screens/gap/gapExportXlsx.ts"
];
const gapScreenSource = (
  await Promise.all(gapScreenModuleFiles.map((path) => readFile(new URL(path, import.meta.url), "utf8")))
).join("\n");
const orderScreenModuleFiles = [
  "../components/redesign/screens/order/OrderScreenExact.tsx",
  "../components/redesign/screens/order/useOrderScreenModel.tsx",
  "../components/redesign/screens/order/useOrderScreenData.ts",
  "../components/redesign/screens/order/orderScreenModel.ts",
  "../components/redesign/screens/order/orderExportXlsx.ts"
];
const orderScreenSource = (
  await Promise.all(orderScreenModuleFiles.map((path) => readFile(new URL(path, import.meta.url), "utf8")))
).join("\n");
const orderReviewSharedSource = await readFile(new URL("../components/redesign/shared/order-review-shared.ts", import.meta.url), "utf8");
assert.match(orderScreenSource, /errorStyle:\s*"stop"/);
assert.doesNotMatch(orderScreenSource, /errorStyle:\s*"error"/);
assert.doesNotMatch(workspaceSource, /function\s+shortDate\s*\(/);
assert.match(gapScreenSource, /calculateStockGapShortageQty\(item\)/);
assert.match(orderReviewSharedSource, /async function resolveFullOrderReviewDownload/);
assert.match(orderReviewSharedSource, /await getOrderReviewRows\(\{ includeLatestFallback: true \}\)/);
assert.match(orderScreenSource, /전체 ESM_order 다중 시트 파일/g);
assert.doesNotMatch(workspaceSource, /fullOrderDownloadAvailable|fullGapAnalysisDownloadAvailable/);

// 발주제외 행은 예전에 저장된 결과에 수량이 남아 있어도 발주 대상으로 집계되지 않는다.
const excludedRow = orderReviewRowFromTable({
  상품코드: "SKU-ZERO-PRICE",
  상품명: "FOC sample",
  브랜드: "Brand",
  상태: "발주제외",
  "우선 액션": "발주 불필요",
  "판단 사유": "입고단가 0, 무상제공/FOC성 SKU로 발주 검토 제외",
  발주필요수량: 15147,
  발주필요금액_KRW: 0,
  "월평균": 5000,
  "EU 현지 재고": 0
});
assert.equal(isOrderExcludedRow(excludedRow), true, "상태 발주제외는 발주 대상에서 빠져야 합니다.");
assert.equal(isRequiredOrderReviewRow(excludedRow), false, "발주제외 행이 발주 필요 SKU로 집계됩니다.");
const normalRow = orderReviewRowFromTable({
  상품코드: "SKU-NORMAL",
  상태: "정상",
  "우선 액션": "발주 필요",
  발주필요수량: 300
});
assert.equal(isOrderExcludedRow(normalRow), false);
assert.equal(isRequiredOrderReviewRow(normalRow), true);

// 미입고 물량의 도착일을 모르는 행은 화면에서도 그 사실이 보여야 한다.
const openPoUnknownRow = orderReviewRowFromTable({
  상품코드: "SKU-PO-NO-ETA",
  상태: "정상",
  "우선 액션": "발주 필요 없음",
  "미입고 수량": 100,
  ETA미확인: "Y"
});
assert.equal(openPoUnknownRow.openPoEtaUnknown, true, "ETA미확인 플래그를 읽어야 합니다.");
assert.equal(openPoUnknownRow.inboundQty, 100);
assert.equal(orderReviewRowFromTable({ 상품코드: "SKU-PO-OK", "미입고 수량": 100, ETA미확인: "N" }).openPoEtaUnknown, false);
assert.match(
  orderScreenSource,
  /미입고 \$\{formatNumber\(inboundQty\)\}개\$\{row\.openPoEtaUnknown \? " \(도착일 미확인\)" : ""\}/,
  "미입고 수량 옆에 도착일 미확인 여부를 함께 표시해야 합니다."
);
assert.match(
  orderScreenSource,
  /export function adjustedOrderQty[\s\S]{0,160}isOrderExcluded\(row\)[\s\S]{0,40}return 0;/,
  "발주 수량·금액·정렬·내보내기는 adjustedOrderQty에서 제외 행을 막아야 합니다."
);
assert.match(orderScreenSource, /isOrderExcluded\(row\)[\s\S]{0,120}"확인필요"[\s\S]{0,20}"제외"/, "제외 행은 '충분'이 아니라 제외 상태로 표시되어야 합니다.");

// ExcelJS는 수식 캐시 결과가 0이면 생략한다. 미입고 해소 전/후 값이 같은 셀은 리터럴로 써야
// 수식을 계산하지 않는 도구에서도 0이 읽힌다.
assert.match(orderScreenSource, /const scenarioCell = \(/, "발주검토 내보내기는 시나리오 값이 같은 셀을 리터럴로 써야 합니다.");
assert.match(orderScreenSource, /if \(beforeValue === afterValue\) \{\s*return beforeValue;/);
assert.equal((orderScreenSource.match(/scenarioCell\(/g) ?? []).length, 6, "6개 시나리오 열이 모두 scenarioCell을 거쳐야 합니다.");

// 세션 복구 결과는 서버 원본 행을 담아야 한다. 매핑된 행에는 기준일·일평균이 없어서
// 재고공백 계산이 분석 기준일 대신 화면을 연 날짜를 쓰게 된다.
const storageSource = await readFile(new URL("../lib/api/storage.ts", import.meta.url), "utf8");
const prepModelSource = await readFile(new URL("../components/redesign/screens/prep/prepScreenModel.ts", import.meta.url), "utf8");
const prepScreenHookSource = await readFile(new URL("../components/redesign/screens/prep/usePrepScreenModel.tsx", import.meta.url), "utf8");
const workspaceSessionSource = await readFile(new URL("../components/redesign/workspace/useWorkspaceAnalysisSession.ts", import.meta.url), "utf8");
assert.match(storageSource, /export function getLatestOrderReviewRawRows/);
assert.match(storageSource, /latestOrderReviewRawRows = rawRows\.length > 0 \? rawRows : null/);
assert.match(
  storageSource,
  /clearSensitiveAnalysisState[\s\S]{0,400}latestOrderReviewRawRows = null/,
  "계정·법인 전환 시 서버 원본 행 캐시도 비워야 합니다."
);
assert.match(prepModelSource, /const rowRecords = recoveredOrderReviewRecords\(rows\)/);
assert.doesNotMatch(prepModelSource, /const rowRecords = rows as unknown/);

// 로그인·새로고침·법인 전환에서는 과거 성공 결과를 자동 복구하지 않는다.
// 이번 세션에서 사용자가 분석 시작을 눌러 성공한 결과만 발주 화면을 연다.
assert.doesNotMatch(
  workspaceSessionSource,
  /getOrderReviewRows|buildRecoveredOrderAnalysisResult|includeLatestFallback:\s*true/,
  "워크스페이스 진입 시 과거 발주 결과를 자동 복구하면 안 됩니다."
);
assert.doesNotMatch(
  prepScreenHookSource,
  /getOrderReviewRows|buildRecoveredOrderAnalysisResult|includeLatestFallback:\s*true/,
  "새 분석이 실패했을 때 과거 성공 결과를 현재 실행 결과처럼 표시하면 안 됩니다."
);

// ETA 상세(도착 캘린더)도 서버에 저장해 세션 복구 시 타임라인 입고 지점을 되살린다.
assert.match(storageSource, /export function getLatestOrderReviewEtaRows/);
assert.match(storageSource, /latestOrderReviewEtaRows = etaRows\.length > 0 \? etaRows : null/);
assert.match(
  storageSource,
  /clearSensitiveAnalysisState[\s\S]{0,400}latestOrderReviewEtaRows = null/,
  "계정·법인 전환 시 ETA 캐시도 비워야 합니다."
);
assert.match(prepModelSource, /stock_gap_eta: etaRecords/, "복구 결과에 도착 캘린더를 담아야 합니다.");
// 발주 계산이 바뀐 뒤에도 예전 캐시를 그대로 보여주면 안 된다.
assert.match(storageSource, /const ANALYSIS_STORAGE_VERSION = "3"/);

// 같은 원본 행 배열을 두 키에 담으면 직렬화 크기가 두 배가 되고 sessionStorage 한도를 넘긴다.
assert.match(
  prepModelSource,
  /order_review: rowRecords\.slice\(0, RECOVERED_PREVIEW_ROWS\)/,
  "복구 결과의 order_review는 미리보기여야 합니다(전체 행을 두 번 담으면 저장에 실패합니다)."
);
assert.doesNotMatch(prepModelSource, /^\s*order_review: rowRecords,$/m);
// sessionStorage 한도를 넘는 결과는 IndexedDB에 남겨 새로고침 후에도 살아남아야 한다.
assert.match(storageSource, /await writeAnalysisResultToDb\(result\)/, "분석 결과를 durable 저장소에 남겨야 합니다.");
assert.match(
  storageSource,
  /getStoredAnalysisResultAsync[\s\S]{0,700}await readAnalysisResultFromDb\(\)/,
  "sessionStorage에 없으면 IndexedDB에서 복구해야 합니다."
);
assert.match(
  storageSource,
  /readAnalysisResultFromDb\(\)[\s\S]{0,400}fromDb\.job_id !== currentJobId \|\| !matchesActiveEntity\(fromDb\)/,
  "IndexedDB 복구도 현재 세션·법인 조건을 지켜야 합니다."
);
assert.match(storageSource, /CURRENT_ANALYSIS_EXPLICIT_JOB_STORAGE_KEY/, "직접 실행한 발주분석 job을 복구 결과와 구분해야 합니다.");
assert.match(storageSource, /options\.markExecuted/, "직접 실행한 결과만 명시적 실행 상태로 저장해야 합니다.");
assert.match(prepScreenHookSource, /saveLastAnalysisResult\(result, \{ markExecuted: true \}\)/, "사용자가 실행한 V1 결과는 명시적 실행 상태로 저장해야 합니다.");
assert.doesNotMatch(
  workspaceSessionSource,
  /saveLastAnalysisResult\(recoveredResult, \{ markExecuted: true \}\)/,
  "자동 복구한 과거 V1 결과를 사용자가 실행한 결과로 표시하면 안 됩니다."
);
const recoveredPayloadBytes = (rows, etaRows) =>
  Buffer.byteLength(
    JSON.stringify({
      tables: {
        order_review: rows.slice(0, 300),
        check_required: [],
        stock_eta: [],
        stock_gap_order_review: rows,
        stock_gap_eta: etaRows
      }
    })
  );
const wideRow = Object.fromEntries(Array.from({ length: 84 }, (_, index) => [`컬럼${index}`, "값".repeat(6)]));
const duplicatedBytes = Buffer.byteLength(
  JSON.stringify({ tables: { order_review: Array(2586).fill(wideRow), stock_gap_order_review: Array(2586).fill(wideRow) } })
);
assert.equal(
  recoveredPayloadBytes(Array(2586).fill(wideRow), []) < duplicatedBytes * 0.6,
  true,
  "미리보기 적용 후 직렬화 크기가 크게 줄어야 합니다(전체 행을 두 번 담으면 두 배가 됩니다)."
);

console.log("order analysis data-integrity regression: 76 assertions passed");
