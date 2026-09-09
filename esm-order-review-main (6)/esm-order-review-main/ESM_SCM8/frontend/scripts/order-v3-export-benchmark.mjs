// Synthetic data only. Run document mode at a bounded size before streaming.
import ExcelJS from "exceljs";
import { performance } from "node:perf_hooks";
import { createHash } from "node:crypto";
import { Writable } from "node:stream";
import { createWriteStream } from "node:fs";
import { finished } from "node:stream/promises";
import { populateV3Excel } from "../components/redesign/screens/order-v3/excelExport.ts";
import { createExcelStream } from "../lib/server/order-v3-excel.ts";

const count = Number(process.env.V3_BENCH_ROWS || 1000);
const rows = Array.from({ length: count }, (_, index) => ({
  sku_code: `SYNTHETIC-${index}`, barcode: `000${index}`, product_name: `검증용 상품 ${index}`, brand: "모의 브랜드",
  calculable: false, data_status: "ON_HOLD", order_signal: "발주 보류",
  reason_code: "DEMAND_HISTORY_INSUFFICIENT", validation_error: "완료 13주 수요이력 부족",
  inbound_status_source_present: false, seasonal_applied: false, season_factor_available: true,
  season_factor_version: "SYNTHETIC", season_factors_by_month: Object.fromEntries(Array.from({ length: 12 }, (_, i) => [i + 1, 1])),
  original_period_sales: Array(13).fill(0), adjusted_period_sales: [],
  reference_sales_status: "AVAILABLE", reference_sales_days: 91, reference_sales_13w: 0,
  reference_monthly_sales: 0, reference_weekly_sales: 0, reference_weekly_sales_history: Array(13).fill(0),
  on_hand_qty: index, in_transit_qty: 0, unreceived_qty: 0, eta_reference_status: "NOT_APPLICABLE",
}));
const options = {
  result: { entity_code: "HQ", job_id: "synthetic", result_schema_version: 21, as_of: "2026-08-31", calculated_at: "2026-08-31T00:00:00Z",
    period_count: 13, period_days: 7, logic_version: "synthetic", scenarios: { SHORTAGE: { rows } } },
  scenario: "SHORTAGE", skus: [], attentionSkus: rows.map(row => row.sku_code), decisions: {}, canViewAmountData: true, viewTitle: "모의 보류 목록",
};
let peakHeap = 0, peakRss = 0;
const memory = () => { const m = process.memoryUsage(); peakHeap = Math.max(peakHeap, m.heapUsed); peakRss = Math.max(peakRss, m.rss); };
const started = performance.now();
if (process.env.V3_BENCH_MODE === "stream") {
  let bytes = 0;
  const hash = createHash("sha256");
  const sink = new Writable({ write(chunk, _encoding, next) { bytes += chunk.length; hash.update(chunk); memory(); next(); } });
  const { stream, done } = createExcelStream(options, new AbortController().signal, memory);
  stream.pipe(sink);
  const output = process.env.V3_BENCH_OUTPUT ? createWriteStream(process.env.V3_BENCH_OUTPUT) : null;
  if (output) stream.pipe(output);
  await done;
  await finished(sink);
  if (output) await finished(output);
  memory();
  console.log(JSON.stringify({ mode: "stream", count, totalSeconds: (performance.now() - started) / 1000,
    bytes, peakHeapMB: peakHeap / 1e6, peakRssMB: peakRss / 1e6, sha256: hash.digest("hex") }));
} else {
const workbook = new ExcelJS.Workbook();
populateV3Excel(workbook, options);
memory();
const built = performance.now();
console.log(JSON.stringify({ stage: "populated", count, buildSeconds: (built - started) / 1000, heapMB: peakHeap / 1e6 }),);
const timer = setInterval(memory, 25);
const bytes = await workbook.xlsx.writeBuffer();
clearInterval(timer); memory();
console.log(JSON.stringify({ mode: "document", count, buildSeconds: (built - started) / 1000,
  totalSeconds: (performance.now() - started) / 1000, bytes: bytes.length, peakHeapMB: peakHeap / 1e6, peakRssMB: peakRss / 1e6,
  sha256: createHash("sha256").update(bytes).digest("hex") }));
}
