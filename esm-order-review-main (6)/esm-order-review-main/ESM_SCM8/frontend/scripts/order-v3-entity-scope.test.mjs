import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import ts from "typescript";
import ExcelJS from "exceljs";
import { populateV3Excel } from "../components/redesign/screens/order-v3/excelExport.ts";
import { renderToStaticMarkup } from "react-dom/server";
import { ENTITY_BY_CODE } from "../lib/entities.ts";
import * as reviewList from "../components/redesign/screens/order-v3/reviewList.ts";

// Compile production code, replacing only external boundaries. No CMS requests/data.
const compile = path => {
  const source = readFileSync(path, "utf8");
  const ast = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, path.endsWith("tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const statements = ast.statements.filter(node => !ts.isImportDeclaration(node));
  return {
    imports: ast.statements.filter(ts.isImportDeclaration),
    code: ts.transpileModule(statements.map(node => node.getText(ast)).join("\n"), {
      compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
    }).outputText
  };
};
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};
const payload = entity => {
  const row = { sku_code: `${entity}-TEST`, product_name: "테스트 상품", brand: "테스트 브랜드", calculable: true, order_signal: "즉시 발주", raw_order_quantity: 10, order_amount_krw: 100 };
  return {
    entity_code: entity, status: "success", as_of: "2026-08-31", calculated_at: "2026-08-31T01:00:00Z",
    job_id: "synthetic-job", logic_version: "synthetic-v3", result_schema_version: 24,
    period_start: "2026-06-01", period_end: "2026-08-30", period_count: 13, period_days: 7,
    order_constraint_status: "ORDER_CONSTRAINTS_PENDING", warnings: [],
    rows: [row], scenarios: { SHORTAGE: { rows: [row] }, CASH: { rows: [row] } }, summary: { blocked_sku_count: 0 }, blocking_contracts: []
  };
};
class ApiRequestError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

// Exercise POST, polling gaps, response decoding and mismatched-result rejection.
const apiModule = compile("lib/api/order-logic-v3.ts");
const makeApi = ({ entity = "PL", onWait, onFetch, onDecode, resultEntity = entity, jobStatus = "succeeded", cancelStatus = "cancelled", cancelFails = false } = {}) => {
  const calls = [];
  const controller = new AbortController();
  const state = { entity };
  const context = {
    exports: {}, DOMException, ApiRequestError, AbortController, setTimeout, clearTimeout,
    isAbortError: error => error?.name === "AbortError",
    FASTAPI_BASE_URL: "/synthetic-api", clientHeaders: () => ({}),
    getActiveEntityCode: () => state.entity,
    wait: async () => { await onWait?.(state, controller); },
    parseApiError: async () => "synthetic error",
    apiFetch: async (url, init) => {
      calls.push({ url, init, entity: state.entity });
      await onFetch?.(calls.length, state, controller);
      if (init.method === "DELETE") {
        if (cancelFails) throw new Error("synthetic cancel failure");
        return { ok: true, json: async () => ({ job_id: "synthetic-job", status: cancelStatus }) };
      }
      return { ok: true, json: async () => {
        await onDecode?.(calls.length, state, controller);
        return calls.length === 1 ? { job_id: "synthetic-job" } : { status: jobStatus, result: payload(resultEntity), error: "synthetic job failed", status_code: 422 };
      } };
    }
  };
  vm.createContext(context);
  vm.runInContext(apiModule.code, context);
  return { calls, controller, state, CancellationError: context.exports.OrderLogicV3CancellationError, ConnectionError: context.exports.OrderLogicV3ConnectionError, run: () => context.exports.runOrderLogicV3("2026-08-31", { entityCode: entity, signal: controller.signal }) };
};
for (const entity of ["PL", "HQ", "USA"]) {
  const api = makeApi({ entity });
  assert.equal((await api.run()).entity_code, entity);
  assert.equal(api.calls.length, 2);
  assert.ok(api.calls.every(call => call.entity === entity));
  assert.equal(api.calls[0].init.signal, undefined, "Keep creation alive until its job ID can be cancelled.");
  assert.ok(api.calls[1].init.signal instanceof AbortSignal);
  assert.ok(api.calls[1].url.endsWith("?include_result=false"));
  assert.deepEqual(JSON.parse(api.calls[0].init.body), { as_of: "2026-08-31", preview: true });
}
for (const options of [
  { onWait: state => { state.entity = "HQ"; } },
  { onFetch: (_index, state) => { state.entity = "HQ"; } },
  { onDecode: (_index, state) => { state.entity = "HQ"; } }
]) {
  const api = makeApi(options);
  await assert.rejects(api.run(), error => error.name === "AbortError");
  assert.equal(api.calls.length, 1, "Do not poll a previous entity's job, including switches between requests.");
}
for (const options of [
  { onWait: (_state, controller) => controller.abort() },
  { onFetch: (index, _state, controller) => { if (index === 1) controller.abort(); } },
  { onDecode: (index, _state, controller) => { if (index === 1) controller.abort(); } }
]) {
  const api = makeApi(options);
  await assert.rejects(api.run(), error => error.name === "AbortError" && error.message.includes("분석을 중단"));
  assert.equal(api.calls.length, 2, "An early stop still cancels the job once creation returns its ID.");
  assert.equal(api.calls[1].init.method, "DELETE");
  assert.equal(api.calls[1].init.signal, undefined, "Cancellation must not reuse the already-aborted polling signal.");
}
const stopFailure = makeApi({ onWait: (_state, controller) => controller.abort(), cancelFails: true });
await assert.rejects(stopFailure.run(), error => error instanceof stopFailure.CancellationError && error.jobId === "synthetic-job");
await assert.rejects(makeApi({ onWait: (_state, controller) => controller.abort(), cancelStatus: "running" }).run(), error => error.name === "OrderLogicV3CancellationError");
await assert.rejects(makeApi({ onWait: (_state, controller) => controller.abort(), cancelStatus: "succeeded" }).run(), error => error.name === "AbortError" && error.message.includes("이미 종료"));
await assert.rejects(makeApi({ jobStatus: "cancelled" }).run(), error => error.name === "AbortError");
for (const options of [
  { onFetch: (index, state) => { if (index === 2) state.entity = "HQ"; } },
  { onDecode: (index, _state, controller) => { if (index === 2) controller.abort(); } }
]) {
  await assert.rejects(makeApi(options).run(), error => error.name === "AbortError");
}
const alreadyAborted = makeApi();
alreadyAborted.controller.abort();
await assert.rejects(alreadyAborted.run(), error => error.name === "AbortError");
assert.equal(alreadyAborted.calls.length, 0);
const wrongStart = makeApi();
wrongStart.state.entity = "HQ";
await assert.rejects(wrongStart.run(), error => error.name === "AbortError");
assert.equal(wrongStart.calls.length, 0);
await assert.rejects(makeApi({ resultEntity: "HQ" }).run(), error => error.status === 409);
await assert.rejects(makeApi({ jobStatus: "failed" }).run(), error => error.status === 422);

// A small deterministic hook host tests state/cleanup and the real keyed boundary.
// Markup is rendered separately with React's server renderer.
const screenModule = compile("components/redesign/screens/order-v3/OrderV3Screen.tsx");
let session = { user: { username: "synthetic-user" }, selectedEntity: "PL" };
let activeHost;
let mounted;
const requests = [];
const stopRetries = [];
const workbookWrites = [];
const downloads = [];
const persistedJobs = new Map([['synthetic-user:PL', 'order3_saved_pl']]);
const persistedJobKey = (username, entity) => `${username}:${entity}`;
const context = {
  require: name => name === "exceljs" ? { Workbook: class extends ExcelJS.Workbook {
    get xlsx() { return { writeBuffer: () => { const pending = deferred(); workbookWrites.push({ ...pending, workbook: this }); return pending.promise; } }; }
  } } : createRequire(import.meta.url)(name),
  exports: {}, ...reviewList, ENTITY_BY_CODE, AbortController, Error,
  OrderLogicV3CancellationError: makeApi().CancellationError,
  OrderLogicV3ConnectionError: makeApi().ConnectionError,
  useAuthSession: () => session,
  getActiveEntityCode: () => session.selectedEntity,
  useUserPermissions: () => ({ canViewAmountData: true }),
  loadOrderV3ActiveJob: (username, entity) => persistedJobs.get(persistedJobKey(username, entity)) ?? null,
  saveOrderV3ActiveJob: (username, entity, jobId) => persistedJobs.set(persistedJobKey(username, entity), jobId),
  clearOrderV3ActiveJob: (username, entity) => persistedJobs.delete(persistedJobKey(username, entity)),
  isAbortError: error => error?.name === "AbortError",
  useMemo: factory => factory(),
  useRef: initial => {
    const index = activeHost.cursor++;
    return activeHost.hooks[index] ??= { current: initial };
  },
  useState: initial => {
    const host = activeHost;
    const index = host.cursor++;
    if (!(index in host.hooks)) host.hooks[index] = typeof initial === "function" ? initial() : initial;
    return [host.hooks[index], next => { host.hooks[index] = typeof next === "function" ? next(host.hooks[index]) : next; }];
  },
  useEffect: effect => {
    const index = activeHost.cursor++;
    if (!(index in activeHost.hooks)) {
      activeHost.hooks[index] = true;
      activeHost.effects.push(effect);
    }
  },
  cn: (...values) => values.filter(Boolean).join(" "),
  runOrderLogicV3: (_date, options) => {
    const pending = deferred();
    requests.push({ ...pending, options });
    options.onJobStarted?.(options.resumeJobId ?? `synthetic-job-${requests.length}`);
    return pending.promise;
  },
  cancelOrderLogicV3Job: (jobId, entity) => { const pending = deferred(); stopRetries.push({ ...pending, jobId, entity }); return pending.promise; },
  populateV3Excel,
  downloadOrderV3Excel: (options, signal) => {
    const workbook = new ExcelJS.Workbook();
    const pending = deferred();
    workbookWrites.push({ ...pending, options, workbook, signal });
    populateV3Excel(workbook, options);
    return pending.promise;
  },
  Blob, URL: { createObjectURL: () => "blob:synthetic", revokeObjectURL() {} },
  window: { setTimeout: callback => { callback(); return 1; }, clearTimeout() {} },
  document: { body: { appendChild() {} }, createElement: () => ({ click() { downloads.push("download"); }, remove() {} }) }
};
for (const declaration of screenModule.imports) {
  for (const item of declaration.importClause?.namedBindings?.elements ?? []) {
    if (!(item.name.text in context)) {
      context[item.name.text] = Object.defineProperty(() => null, "name", { value: item.name.text });
    }
  }
}
vm.createContext(context);
vm.runInContext(screenModule.code, context);
const render = () => {
  const boundary = context.exports.OrderV3Screen();
  if (!mounted || mounted.key !== boundary.key) {
    mounted?.cleanups.forEach(cleanup => cleanup?.());
    mounted = { key: boundary.key, hooks: [], cursor: 0, effects: [], cleanups: [] };
  }
  activeHost = mounted;
  activeHost.cursor = 0;
  const tree = typeof boundary.type === "function" ? boundary.type(boundary.props) : boundary;
  activeHost.effects.splice(0).forEach(effect => activeHost.cleanups.push(effect()));
  return tree;
};
const nodes = tree => Array.isArray(tree) ? tree.flatMap(nodes) : tree && typeof tree === "object" ? [tree, ...nodes(tree.props?.children)] : [];
const component = (tree, name) => nodes(tree).find(node => node.type?.name === name)?.props;
const header = tree => component(tree, "ExecutionStatusBar");
const table = tree => component(tree, "TriageProposalTable");
const textOf = tree => Array.isArray(tree) ? tree.map(textOf).join("") : tree && typeof tree === "object" ? textOf(tree.props?.children) : String(tree ?? "");
const headerMarkup = tree => renderToStaticMarkup(context.ExecutionStatusBar(header(tree)));
const finish = async (tree, entity, result = payload(entity)) => {
  const pending = header(tree).onRun();
  requests.at(-1).resolve(result);
  await pending;
  return render();
};
const flushMicrotasks = async () => {
  for (let index = 0; index < 5; index += 1) await Promise.resolve();
};
let tree = render();
assert.equal(header(tree).result, null);
assert.equal(requests.length, 1, "A persisted running job is recovered automatically when the entity screen mounts.");
assert.equal(requests[0].options.resumeJobId, "order3_saved_pl");
tree = render();
assert.equal(header(tree).running, true);
assert.ok(headerMarkup(tree).includes("분석 중…"));
assert.ok(!headerMarkup(tree).includes("분석 이어받기"));
requests[0].resolve(payload("PL"));
await flushMicrotasks();
tree = render();
assert.equal(header(tree).result.entity_code, "PL");
assert.equal(persistedJobs.has("synthetic-user:PL"), false, "A completed job is no longer retained as active.");
assert.ok(headerMarkup(tree).includes("새로 분석"));
assert.ok(headerMarkup(tree).includes("SKO Sp. z o.o.") && !headerMarkup(tree).includes("(PL)"));
assert.equal(header(tree).canExport, true);
tree = await finish(tree, "PL");
assert.equal(requests.at(-1).options.resumeJobId, undefined, "The primary action always starts a new analysis.");
assert.equal(table(tree).rows[0].sku, "PL-TEST");
table(tree).onToggle("PL-TEST");
table(tree).onOpen("PL-TEST");
tree = render();
component(tree, "OrderV3EvidenceDrawer").onHold();
nodes(tree).find(node => node.type === "input").props.onChange({ target: { value: "PL" } });
nodes(tree).find(node => node.type === "button" && textOf(node).includes("발주수량·금액 비교")).props.onClick();
tree = render();
assert.equal(component(tree, "OrderV3EvidenceDrawer").open, true);
assert.equal(component(tree, "ScenarioComparison").open, true);
assert.equal(table(tree).selectedSkus.size, 1);
assert.equal(table(tree).decisions["PL-TEST"].decision, "발주 보류");
session = { ...session, selectedEntity: "HQ" };
tree = render();
assert.equal(header(tree).entityCode, "HQ");
assert.equal(header(tree).result, null);
assert.equal(header(tree).lastCalculatedAt, "실행 전");
assert.equal(header(tree).running, false);
assert.equal(header(tree).canExport, false);
assert.equal(table(tree).rows.length, 0);
assert.equal(table(tree).selectedSkus.size, 0);
assert.equal(Object.keys(table(tree).decisions).length, 0);
assert.equal(component(tree, "OrderV3EvidenceDrawer").open, false);
assert.equal(component(tree, "ScenarioComparison").open, false);
assert.equal(nodes(tree).find(node => node.type === "input").props.value, "");
assert.ok(headerMarkup(tree).includes("Silicon2 Co., Ltd.") && !headerMarkup(tree).includes("계산 완료"));
tree = await finish(tree, "HQ");
assert.equal(table(tree).rows[0].sku, "HQ-TEST");

// Late success/error after HQ -> PL -> HQ cannot revive the earlier HQ session.
const oldRun = header(tree).onRun();
const oldRequest = requests.at(-1);
session = { ...session, selectedEntity: "PL" };
tree = render();
assert.equal(oldRequest.options.signal.aborted, true);
const oldFailure = header(tree).onRun();
const failedRequest = requests.at(-1);
session = { ...session, selectedEntity: "HQ" };
tree = render();
const newRun = header(tree).onRun();
tree = render();
assert.equal(header(tree).running, true);
oldRequest.resolve(payload("HQ"));
failedRequest.reject(new Error("old PL failure"));
await Promise.all([oldRun, oldFailure]);
tree = render();
assert.equal(header(tree).running, true, "Old completion must not stop the new request's progress state.");
assert.equal(header(tree).result, null);
assert.ok(!textOf(tree).includes("old PL failure"));
requests.at(-1).resolve(payload("HQ"));
await newRun;
tree = render();
assert.equal(header(tree).result.entity_code, "HQ");
assert.equal(header(tree).running, false);

// An Excel write already underway must not download after the entity changes.
assert.equal(header(tree).canExport, true);
assert.equal(header(tree).exporting, false);
assert.equal(header(tree).running, false);
const exporting = header(tree).onExport();
await Promise.resolve();
await Promise.resolve();
assert.equal(workbookWrites.length, 1);
session = { ...session, selectedEntity: "PL" };
tree = render();
assert.equal(workbookWrites[0].signal.aborted, true, "Entity change cancels the export request.");
workbookWrites[0].resolve(new Uint8Array());
await exporting;
assert.equal(downloads.length, 0);
assert.equal(header(tree).exporting, false);
tree = await finish(tree, "PL");
const normalExport = header(tree).onExport();
await Promise.resolve();
await Promise.resolve();
workbookWrites.at(-1).resolve(new Uint8Array());
await normalExport;
assert.equal(downloads.length, 1, "Export remains available in the same entity session.");

// Manual stop preserves the last completed result and permits a clean rerun.
tree = render();
const originalResult = header(tree).result;
assert.ok(!headerMarkup(tree).includes(">분석 중단</button>"));
const manualRun = header(tree).onRun();
const manualRequest = requests.at(-1);
tree = render();
assert.ok(headerMarkup(tree).includes("분석 중단</button>"));
await header(tree).onStop();
tree = render();
assert.equal(manualRequest.options.signal.aborted, true);
assert.equal(header(tree).stopping, true);
assert.equal(header(tree).running, true);
manualRequest.reject(new DOMException("분석을 중단했습니다.", "AbortError"));
await manualRun;
tree = render();
assert.equal(header(tree).running, false);
assert.equal(header(tree).stopped, true);
assert.equal(header(tree).result, originalResult);
assert.ok(textOf(tree).includes("이전 완료 결과는 유지됩니다."));
tree = await finish(tree, "PL");
assert.equal(header(tree).stopped, false);

// A failed server stop is not reported as completed, and can be retried safely.
const failingRun = header(tree).onRun();
tree = render();
await header(tree).onStop();
requests.at(-1).reject(new context.OrderLogicV3CancellationError("synthetic-failed-stop"));
await failingRun;
tree = render();
assert.equal(header(tree).running, true);
assert.equal(header(tree).stopFailed, true);
assert.equal(header(tree).stopping, false);
const failedRetry = header(tree).onStop();
stopRetries.at(-1).reject(new Error("still unavailable"));
await failedRetry;
tree = render();
assert.equal(header(tree).stopFailed, true);
const retry = header(tree).onStop();
assert.equal(stopRetries.at(-1).jobId, "synthetic-failed-stop");
assert.equal(stopRetries.at(-1).entity, "PL");
stopRetries.at(-1).resolve("cancelled");
await retry;
tree = render();
assert.equal(header(tree).running, false);
assert.equal(header(tree).stopped, true);
assert.equal(header(tree).stopFailed, false);
tree = await finish(tree, "PL");
assert.equal(header(tree).result.entity_code, "PL");

// A disconnected download preserves the previous result and reconnects in the
// background to the same job rather than asking the user or restarting it.
const resultBeforeDisconnect = header(tree).result;
const disconnectedRun = header(tree).onRun();
const disconnectedRequest = requests.at(-1);
disconnectedRequest.reject(new context.OrderLogicV3ConnectionError("synthetic-reconnect"));
await flushMicrotasks();
tree = render();
assert.equal(header(tree).running, true);
assert.equal(header(tree).result, resultBeforeDisconnect);
const reconnectRequest = requests.at(-1);
assert.notEqual(reconnectRequest, disconnectedRequest);
assert.equal(reconnectRequest.options.resumeJobId, "synthetic-reconnect");
assert.equal(persistedJobs.get("synthetic-user:PL"), "synthetic-reconnect");
assert.ok(headerMarkup(tree).includes("분석 중…"));
assert.ok(!headerMarkup(tree).includes("분석 이어받기"));
reconnectRequest.options.onReceiveProgress(250, 471);
tree = render();
assert.equal(header(tree).running, true);
assert.ok(textOf(tree).includes("분석 결과 받는 중 250 / 471 SKU"));
reconnectRequest.resolve(payload("PL"));
await disconnectedRun;
tree = render();
assert.equal(header(tree).running, false);
assert.equal(persistedJobs.has("synthetic-user:PL"), false);
assert.ok(headerMarkup(tree).includes("새로 분석"));
assert.ok(!textOf(tree).includes("분석 결과 받는 중"));

// Real screen -> scope selection -> Excel builder, including exceptions-only exports.
const mixedResult = payload("PL");
const heldRow = { sku_code: "PL-HELD", product_name: "테스트 보류", brand: "테스트 브랜드", calculable: false,
  data_status: "BLOCKED", order_signal: "계산 차단", reason_code: "DEMAND_HISTORY_INSUFFICIENT", validation_error: "13주 수요이력 부족" };
const blockedRow = { ...heldRow, sku_code: "PL-BLOCKED", data_status: "BLOCKED", reason_code: "V2_INVENTORY_INVALID", validation_error: "재고 오류" };
mixedResult.scenarios.SHORTAGE.rows.push(heldRow, blockedRow);
tree = await finish(tree, "PL", mixedResult);
table(tree).onToggle("PL-TEST");
tree = render();
assert.match(header(tree).exportDescription, /발주제안·물류전망 1개 \/ 확인필요 2개/);
const captureExport = async () => {
  const previousCount = workbookWrites.length;
  const pending = header(tree).onExport();
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(workbookWrites.length, previousCount + 1);
  const write = workbookWrites.at(-1);
  write.resolve(new Uint8Array());
  await pending;
  tree = render();
  return write.workbook;
};
const companionBook = await captureExport();
assert.equal(companionBook.getWorksheet("발주제안").getCell("A8").value, "PL-TEST");
assert.equal(companionBook.getWorksheet("발주제안").rowCount, 8);
assert.deepEqual([6, 7].map(row => companionBook.getWorksheet("확인필요").getCell(`A${row}`).value), ["PL-HELD", "PL-BLOCKED"]);
component(tree, "ReviewSummary").onToggleExclusions();
tree = render();
assert.equal(header(tree).canExport, true);
table(tree).onToggleAll();
tree = render();
assert.equal(table(tree).selectedSkus.size, 2, "Exceptions can be selected for export without becoming reviewable.");
table(tree).onToggle("PL-HELD");
tree = render();
const blockedBook = await captureExport();
assert.equal(blockedBook.getWorksheet("발주제안").rowCount, 7);
assert.equal(blockedBook.getWorksheet("확인필요").getCell("A6").value, "PL-BLOCKED");
assert.equal(blockedBook.getWorksheet("확인필요").getCell("G6").value, "재고 오류");
assert.equal(blockedBook.getWorksheet("확인필요").rowCount, 6);
assert.equal(table(tree).decisions["PL-BLOCKED"], undefined);
const onlyBlockedResult = payload("PL");
onlyBlockedResult.scenarios.SHORTAGE.rows = [blockedRow];
tree = await finish(tree, "PL", onlyBlockedResult);
assert.equal(table(tree).rows.length, 0);
assert.equal(header(tree).canExport, true, "Allow a companion-only export even when there are no order-needed rows.");
const onlyBlockedBook = await captureExport();
assert.equal(onlyBlockedBook.getWorksheet("확인필요").getCell("A6").value, "PL-BLOCKED");
session = { user: { username: "another-synthetic-user" }, selectedEntity: "PL" };
tree = render();
assert.equal(header(tree).result, null, "Changing accounts also resets the review session.");
session = { ...session, selectedEntity: null };
assert.ok(textOf(render()).includes("분석할 법인을 선택해 주세요."));
console.log("V3 entity-scope checks passed: reset, late responses, server stop before/after creation, stop retry, rerun and export isolation.");
