// Synthetic HQ-scale export benchmark for the page -> disk spool -> child worker path.
import { performance } from "node:perf_hooks";
import { cleanupExcelSpool, prepareExcelSpool, runExcelSpoolWorker, validateExportRequest } from "../lib/server/order-v3-excel.ts";

const count = Number(process.env.V3_BENCH_ROWS || 1000);
const codes = Array.from({ length: count }, (_, index) => `SYNTHETIC-${index}`);
const row = index => ({
  sku_code: codes[index], barcode: `000${index}`, product_name: `검증용 상품 ${index}`, brand: `모의 브랜드 ${index % 20}`,
  calculable: false, data_status: "ON_HOLD", order_signal: "발주 보류",
  reason_code: "DEMAND_HISTORY_INSUFFICIENT", validation_error: "완료 13주 수요이력 부족",
  inbound_status_source_present: false, seasonal_applied: false, season_factor_available: true,
  season_factor_version: "SYNTHETIC", season_factors_by_month: Object.fromEntries(Array.from({ length: 12 }, (_, month) => [month + 1, 1])),
  original_period_sales: Array(13).fill(0), adjusted_period_sales: [], reference_sales_status: "AVAILABLE",
  reference_sales_days: 91, reference_sales_13w: 0, reference_monthly_sales: 0, reference_weekly_sales: 0,
  reference_weekly_sales_history: Array(13).fill(0), on_hand_qty: index, in_transit_qty: 0, unreceived_qty: 0,
  eta_reference_status: "NOT_APPLICABLE",
});
const result = {
  entity_code: "HQ", job_id: "synthetic", source_snapshot_id: "synthetic", result_schema_version: 24,
  as_of: "2026-09-01", calculated_at: "2026-09-01T00:00:00Z", period_count: 13, period_days: 7,
  period_start: "2025-09-01", period_end: "2026-08-30", logic_version: "synthetic",
  rows: [], scenarios: { CASH: { rows: [] }, SHORTAGE: { rows: [] } },
};
const body = validateExportRequest({
  jobId: "synthetic", entityCode: "HQ", snapshotId: "synthetic", scenario: "SHORTAGE",
  skus: [], attentionSkus: codes, decisions: {}, viewTitle: "전체 브랜드", attentionScope: "전체 브랜드",
  brandScope: null,
});
const readJson = async path => {
  if (path === "/auth/me") return { permissions: { canViewAmountData: true } };
  const offset = Number(new URL(path, "http://synthetic").searchParams.get("offset"));
  const end = Math.min(offset + 250, count);
  const rows = Array.from({ length: end - offset }, (_, local) => row(offset + local));
  return {
    job_id: "synthetic", entity_code: "HQ", snapshot_id: "synthetic", offset,
    next_offset: end < count ? end : null, total: count,
    counts: { rows: count, CASH: count, SHORTAGE: count },
    scenarios: { CASH: { rows }, SHORTAGE: { rows } }, ...(offset === 0 ? { result } : {}),
  };
};

let peakHeap = 0, peakRss = 0;
const sample = () => {
  const memory = process.memoryUsage();
  peakHeap = Math.max(peakHeap, memory.heapUsed);
  peakRss = Math.max(peakRss, memory.rss);
};
const timer = setInterval(sample, 25);
const started = performance.now();
let spool;
try {
  spool = await prepareExcelSpool(body, readJson, new AbortController().signal);
  const prepared = performance.now();
  await runExcelSpoolWorker(spool, new AbortController().signal);
  sample();
  const { size } = await import("node:fs/promises").then(module => module.stat(spool.outputPath));
  console.log(JSON.stringify({ count, spoolSeconds: (prepared - started) / 1000, totalSeconds: (performance.now() - started) / 1000,
    bytes: size, parentPeakHeapMB: peakHeap / 1e6, parentPeakRssMB: peakRss / 1e6 }));
} finally {
  clearInterval(timer);
  await cleanupExcelSpool(spool);
}
