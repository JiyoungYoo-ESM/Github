import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const path = "lib/api/order-logic-v3.ts";
const source = readFileSync(path, "utf8");
const ast = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
const code = ts.transpileModule(ast.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(ast)).join("\n"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
}).outputText;
class ApiRequestError extends Error { constructor(message, status) { super(message); this.status = status; } }
const result = {
  job_id: "synthetic", entity_code: "HQ", source_snapshot_id: "snapshot", status: "success",
  rows: [{ sku_code: "A", qty: 0 }, { sku_code: "B", qty: null }],
  scenarios: { CASH: { rows: [{ qty: 1 }, { qty: 2 }, { qty: 3 }] }, SHORTAGE: { rows: [{ qty: 9 }] } },
  summary: { preserve: true }
};
function page(offset) {
  const next = offset === 0 ? 2 : 3;
  return {
    job_id: "synthetic", entity_code: "HQ", snapshot_id: "snapshot", offset, next_offset: next < 3 ? next : null,
    total: 3, counts: { rows: 2, CASH: 3, SHORTAGE: 1 }, rows: result.rows.slice(offset, next),
    scenarios: { CASH: { rows: result.scenarios.CASH.rows.slice(offset, next) }, SHORTAGE: { rows: result.scenarios.SHORTAGE.rows.slice(offset, next) } },
    ...(offset === 0 ? { result: { ...result, rows: [], scenarios: { CASH: { rows: [] }, SHORTAGE: { rows: [] } } } } : {})
  };
}
function harness(intercept = () => undefined) {
  const calls = [], progress = [], statuses = [], controller = new AbortController();
  const context = {
    exports: {}, DOMException, AbortController, ApiRequestError, setTimeout, clearTimeout,
    isAbortError: error => error?.name === "AbortError", FASTAPI_BASE_URL: "/api",
    clientHeaders: () => ({}), getActiveEntityCode: () => "HQ", wait: async () => {},
    parseApiError: async response => response.status === 403 ? "forbidden" : "temporary",
    apiFetch: async (url, init) => {
      calls.push({ url, init });
      const overridden = await intercept(url, init, calls, controller);
      if (overridden) return overridden;
      const value = init.method === "POST" ? { job_id: "synthetic" }
        : init.method === "DELETE" ? { job_id: "synthetic", status: "cancelled" }
        : url.includes("/result?") ? page(Number(new URL(url, "http://synthetic").searchParams.get("offset")))
        : { job_id: "synthetic", status: "succeeded", result_delivery: "paged-v1" };
      return { ok: true, json: async () => structuredClone(value) };
    }
  };
  vm.createContext(context); vm.runInContext(code, context);
  return { calls, progress, statuses, controller, context,
    run: resumeJobId => context.exports.runOrderLogicV3("2026-08-31", {
      entityCode: "HQ", signal: controller.signal, resumeJobId,
      onStatusChange: status => statuses.push(status),
      onReceiveProgress: (received, total) => progress.push([received, total])
    }) };
}
let brokenBodies = 0;
const recovering = harness(url => url.endsWith("offset=2") && brokenBodies++ === 0
  ? { ok: true, json: async () => { throw new TypeError("connection reset while reading body"); } } : undefined);
assert.equal(JSON.stringify(await recovering.run()), JSON.stringify(result));
assert.equal(recovering.calls.filter(call => call.init.method === "POST").length, 1);
assert.equal(recovering.calls.filter(call => call.url.endsWith("offset=0")).length, 1);
assert.equal(recovering.calls.filter(call => call.url.endsWith("offset=2")).length, 2);
assert.deepEqual(recovering.progress, [[2, 3], [3, 3]]);
assert.deepEqual(recovering.statuses, ["queued"], "The UI is told that an accepted job is waiting for a worker.");

const aliased = harness(url => {
  if (!url.includes("/result?")) return;
  const value = structuredClone(page(Number(new URL(url, "http://synthetic").searchParams.get("offset"))));
  value.row_alias = "SHORTAGE"; value.rows = []; value.counts.rows = 1;
  return { ok: true, json: async () => value };
});
const aliasResult = await aliased.run();
assert.equal(aliasResult.rows, aliasResult.scenarios.SHORTAGE.rows);
assert.deepEqual(aliasResult.rows, result.scenarios.SHORTAGE.rows);

let unavailable = true;
const reconnect = harness((url, init) => init.method !== "POST" && unavailable ? { ok: false, status: 503 } : undefined);
await assert.rejects(reconnect.run(), error => error.name === "OrderLogicV3ConnectionError" && error.jobId === "synthetic");
unavailable = false;
assert.equal(JSON.stringify(await reconnect.run("synthetic")), JSON.stringify(result));
assert.equal(reconnect.calls.filter(call => call.init.method === "POST").length, 1, "Reconnecting never restarts the calculation.");

const forbidden = harness((url, init) => init.method !== "POST" ? { ok: false, status: 403 } : undefined);
await assert.rejects(forbidden.run(), error => error.status === 403);

const busyMessage = "이미 V3 분석이 실행 중이거나 중단 처리를 마무리하고 있습니다. 처리가 끝난 뒤 다시 실행해 주세요.";
const busy = harness((url, init) => init.method === "POST"
  ? { ok: false, status: 409, json: async () => ({ detail: busyMessage }) } : undefined);
busy.context.parseApiError = async response => (await response.json()).detail;
await assert.rejects(busy.run(), error => error.status === 409 && error.message === busyMessage);
assert.equal(busy.calls.length, 1, "A busy server never creates/retries/polls another analysis.");

const memoryMessage = "서버 메모리가 부족하여 V3 분석을 완료하지 못했습니다. 메모리 사용량을 줄인 뒤 다시 실행해 주세요.";
const outOfMemory = harness((url, init) => init.method !== "POST"
  ? { ok: true, json: async () => ({ job_id: "synthetic", status: "failed", status_code: 503, error: memoryMessage }) } : undefined);
await assert.rejects(outOfMemory.run(), error => error.status === 503 && error.message === memoryMessage);
assert.equal(outOfMemory.calls.length, 2, "A recorded memory failure is not a transient connection retry.");
assert.equal(forbidden.calls.length, 2);
for (const corrupt of [
  value => { value.snapshot_id = "different"; },
  value => { value.next_offset = 0; },
  value => { value.rows = []; },
  value => { value.entity_code = "PL"; }
]) {
  const bad = harness(url => {
    if (!url.includes("/result?")) return;
    const value = structuredClone(page(0)); corrupt(value);
    return { ok: true, json: async () => value };
  });
  await assert.rejects(bad.run(), error => error.status === 409);
}
const stopping = harness((url, init, calls, controller) => {
  if (url.endsWith("offset=2")) { controller.abort(); throw new DOMException("stopped", "AbortError"); }
});
await assert.rejects(stopping.run(), error => error.name === "AbortError");
assert.equal(stopping.calls.filter(call => call.init.method === "DELETE").length, 1);
assert.equal(stopping.calls.filter(call => call.url.endsWith("offset=2")).length, 1);
console.log("V3 delivery passed: exact page assembly, interrupted bodies, reconnect without recalculation, permissions, corrupt pages and cancellation.");
