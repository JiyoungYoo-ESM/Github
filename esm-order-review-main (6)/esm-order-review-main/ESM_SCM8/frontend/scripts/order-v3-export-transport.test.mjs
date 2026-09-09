import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import ExcelJS from "exceljs";
import { createExcelStream, prepareExcelOptions, validateExportRequest } from "../lib/server/order-v3-excel.ts";
import { POST } from "../app/api/order-v3-excel/route.ts";

const rows = [
  { sku_code: "A", product_name: "검증", calculable: true, order_signal: "즉시 발주", raw_order_quantity: 10.25,
    brand: "BRAND-A",
    unit_price_krw: 1234, order_amount_krw: 12648.5, eta_reference_status: "NOT_APPLICABLE",
    transport_mode: "DOMESTIC_COMMON", lead_time_days: 30.5, review_days: 28 },
  { sku_code: "B", brand: "BRAND-B", calculable: false, reason_code: "DEMAND_HISTORY_INSUFFICIENT", validation_error: "모의 차단" },
  { sku_code: "C", brand: "BRAND-C", calculable: false, reason_code: "SYNTHETIC_BLOCK", validation_error: "모의 차단", reference_sales_status: "AVAILABLE", reference_sales_days: 91, reference_sales_13w: 0 },
];
const result = { job_id: "synthetic", source_snapshot_id: "synthetic-snapshot", entity_code: "HQ", as_of: "2026-08-31",
  result_schema_version: 24, calculated_at: "2026-08-31T00:00:00Z", logic_version: "synthetic", period_count: 13,
  period_days: 7, period_start: "2026-06-01", period_end: "2026-08-30", rows: [], scenarios: { CASH: { rows: [] }, SHORTAGE: { rows: [] } } };
const body = { jobId: "synthetic", entityCode: "HQ", snapshotId: "synthetic-snapshot", scenario: "SHORTAGE",
  skus: ["A"], attentionSkus: ["C"], decisions: { A: { decision: "수량 수정", finalQty: 11 } }, viewTitle: "모의 선택", attentionScope: "모의 차단", brandScope: null };
function page(offset) {
  const end = Math.min(offset + 2, rows.length);
  return { job_id: body.jobId, entity_code: "HQ", snapshot_id: body.snapshotId, offset, next_offset: end === rows.length ? null : end,
    total: rows.length, counts: { rows: rows.length, CASH: rows.length, SHORTAGE: rows.length },
    scenarios: { SHORTAGE: { rows: rows.slice(offset, end) }, CASH: { rows: rows.slice(offset, end).map(row => ({ ...row, raw_order_quantity: 2.5 })) } },
    ...(offset === 0 ? { result } : {}) };
}
const reader = (allowed = true, alter = value => value) => async path => {
  if (path === "/auth/me") return { permissions: { canViewAmountData: allowed } };
  return alter(structuredClone(page(Number(new URL(path, "http://test").searchParams.get("offset")))));
};
const signal = new AbortController().signal;
const before = JSON.stringify({ rows, result, body });
const options = await prepareExcelOptions(validateExportRequest(body), reader(), signal);
assert.deepEqual(options.result.scenarios.SHORTAGE.rows.map(row => row.sku_code), ["A", "C"]);
assert.equal(options.result.scenarios.SHORTAGE.rows[0].order_amount_krw, 12648.5);
// 발주분석 V3 엑셀은 계정 권한과 무관하게 금액 컬럼을 노출한다(2026-09-02 사용자 요청).
assert.equal((await prepareExcelOptions({ ...body }, reader(false), signal)).canViewAmountData, true);
assert.equal((await prepareExcelOptions({ ...body, scenario: "CASH" }, reader(), signal)).result.scenarios.CASH.rows[0].raw_order_quantity, 2.5);
for (const alter of [
  value => ({ ...value, snapshot_id: "other" }), value => ({ ...value, entity_code: "PL" }),
  value => ({ ...value, next_offset: 0 }), value => ({ ...value, total: 4 }),
  value => ({ ...value, scenarios: { ...value.scenarios, SHORTAGE: { rows: [] } } })
]) await assert.rejects(prepareExcelOptions(body, reader(true, alter), signal), /일치하지/);
await assert.rejects(prepareExcelOptions({ ...body, skus: ["absent"] }, reader(), signal), /일치하지/);
await assert.rejects(prepareExcelOptions({ ...body, attentionSkus: [], brandScope: "BRAND-C" }, reader(), signal), /브랜드/);
assert.equal((await prepareExcelOptions({ ...body, attentionSkus: [], brandScope: "BRAND-A" }, reader(), signal)).result.scenarios.SHORTAGE.rows[0].brand, "BRAND-A");
await assert.rejects(prepareExcelOptions(body, async () => { throw new Error("forbidden"); }, signal), /forbidden/);
assert.throws(() => validateExportRequest({ ...body, attentionSkus: ["C", "C"] }), /중복/);
assert.equal(JSON.stringify({ rows, result, body }), before);

// Real Next handler: auth context forwarding, backend failures, scopes and XLSX.
const nativeFetch = globalThis.fetch;
const calls = [];
let allowed = true, backendStatus = 200;
globalThis.fetch = async (url, init) => {
  calls.push({ url, init });
  assert.equal(init.headers.get("cookie"), "session=synthetic-only");
  assert.equal(init.headers.get("x-client-id"), "synthetic-browser");
  assert.equal(init.headers.get("x-entity-code"), "HQ");
  if (backendStatus !== 200) return Response.json({ detail: "denied" }, { status: backendStatus });
  return Response.json(await reader(allowed)(new URL(url).pathname.replace(/^\/api/, "") + new URL(url).search));
};
const request = (data = body, headers = {}) => new Request("http://localhost:3000/api/order-v3-excel", {
  method: "POST", headers: { "content-type": "application/json", "x-requested-with": "fetch", "origin": "http://localhost:3000",
    "cookie": "session=synthetic-only", "x-client-id": "synthetic-browser", "x-entity-code": "HQ", ...headers }, body: JSON.stringify(data)
});
try {
  for (const amountAllowed of [true, false]) {
    allowed = amountAllowed;
    const response = await POST(request({ ...body, canViewAmountData: true }));
    assert.equal(response.status, 200);
    const file = new ExcelJS.Workbook();
    await file.xlsx.load(Buffer.from(await response.arrayBuffer()));
    const proposal = file.getWorksheet("발주제안");
    const proposalHeaders = proposal.getRow(7).values.slice(1);
    const proposalValue = label => proposal.getCell(8, proposalHeaders.indexOf(label) + 1).value;
    assert.ok(!proposalHeaders.includes("운송수단"), "HQ export drops the transport mode column.");
    assert.equal(proposalValue("리드타임\n(달력일)"), 30.5);
    assert.equal(proposalValue("발주필요수량\n(원시)"), 10.25);
    // 계정 권한과 무관하게 금액 컬럼이 항상 채워진다.
    assert.equal(proposalValue("발주필요금액\n(KRW)"), 12648.5);
    assert.equal(file.getWorksheet("확인필요").getCell("A6").value, "C");
    assert.equal(file.getWorksheet("확인필요").getCell("D6").value, 0);
    assert.equal(file.getWorksheet("_계산기준").rowCount, 22);
  }
  allowed = true;
  const brandResponse = await POST(request({ ...body, attentionSkus: [], brandScope: "BRAND-A", viewTitle: "BRAND-A" }));
  assert.equal(brandResponse.status, 200);
  const brandFile = new ExcelJS.Workbook();
  await brandFile.xlsx.load(Buffer.from(await brandResponse.arrayBuffer()));
  assert.equal(brandFile.getWorksheet("발주제안").getCell("A8").value, "A");
  assert.match(String(brandFile.getWorksheet("발주제안").getCell("A2").value), /BRAND-A/);
  assert.equal((await POST(request({ ...body, attentionSkus: [], brandScope: "BRAND-C" }))).status, 409);
  assert.ok(calls.every(call => call.init.method === undefined), "Export never creates/recalculates a job.");
  const previousCalls = calls.length;
  assert.equal((await POST(request(body, { origin: "https://other.example" }))).status, 403);
  assert.equal((await POST(request(body, { origin: "https://evil.example", "x-forwarded-host": "evil.example", "x-forwarded-proto": "https", "sec-fetch-site": "cross-site" }))).status, 403);
  assert.equal((await POST(request(body, { "x-entity-code": "PL" }))).status, 403);
  assert.equal(calls.length, previousCalls);
  for (const proxyHeaders of [
    { origin: "http://192.168.0.245:3000", host: "192.168.0.245:3000", "sec-fetch-site": "same-origin" },
    { origin: "https://esm.example.com", host: "frontend.railway.internal:3000", "x-forwarded-host": "esm.example.com", "x-forwarded-proto": "https", "sec-fetch-site": "same-origin" }
  ]) {
    const response = await POST(request(body, proxyHeaders));
    assert.equal(response.status, 200);
    await response.arrayBuffer();
  }
  for (const status of [401, 403, 404]) {
    backendStatus = status;
    assert.equal((await POST(request())).status, status);
  }
} finally { globalThis.fetch = nativeFetch; }

const controller = new AbortController();
const manyRows = Array.from({ length: 501 }, (_, index) => ({ ...rows[2], sku_code: `SYNTHETIC-${index}` }));
let highestProgress = 0;
const stopping = createExcelStream({ ...options, skus: [], attentionSkus: manyRows.map(row => row.sku_code),
  result: { ...result, scenarios: { SHORTAGE: { rows: manyRows } } } }, controller.signal,
  progress => { highestProgress = Math.max(highestProgress, progress.completed); if (progress.completed === 250) controller.abort(); });
stopping.stream.resume();
await assert.rejects(stopping.done, error => error.name === "AbortError");
assert.equal(highestProgress, 250);

// Browser transport sends only selection/decisions, cancels body consumption.
const path = "lib/api/order-v3-excel.ts";
const ast = ts.createSourceFile(path, readFileSync(path, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
const code = ts.transpileModule(ast.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(ast)).join("\n"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
}).outputText;
let payload, cancelCalled = false;
const browserController = new AbortController();
const context = { exports: {}, DOMException, Blob, getActiveEntityCode: () => "HQ", ApiRequestError: Error,
  parseApiError: async () => "error", apiFetch: async (url, init) => {
    assert.equal(url, "/api/order-v3-excel"); payload = JSON.parse(init.body);
    return new Response(new ReadableStream({ pull(stream) { stream.enqueue(new Uint8Array([1, 2, 3])); }, cancel() { cancelCalled = true; } }));
  }
};
vm.createContext(context); vm.runInContext(code, context);
await assert.rejects(context.exports.downloadOrderV3Excel(options, browserController.signal, () => browserController.abort()), error => error.name === "AbortError");
assert.equal(cancelCalled, true);
assert.equal(payload.jobId, "synthetic");
assert.equal(payload.result, undefined);
assert.equal(payload.canViewAmountData, undefined);
assert.ok(!JSON.stringify(payload).includes("12648.5"));
console.log("V3 export transport passed: all/specific-brand scopes, exact scenario, authoritative permissions, cancellation, no recalculation and isolated XLSX worker.");
