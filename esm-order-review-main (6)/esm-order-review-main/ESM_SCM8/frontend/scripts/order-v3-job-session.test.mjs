import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const path = "lib/order-v3-job-session.ts";
const source = readFileSync(path, "utf8");
const ast = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
const code = ts.transpileModule(
  ast.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(ast)).join("\n"),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }
).outputText;

const storage = new Map();
const context = {
  exports: {},
  readRawItem: (_area, key) => storage.get(key) ?? null,
  writeRawItem: (_area, key, value) => { storage.set(key, value); return true; },
  removeItem: (_area, key) => { storage.delete(key); }
};
vm.createContext(context);
vm.runInContext(code, context);

const jobId = "order3_20260901_010203_abcdef12";
context.exports.saveOrderV3ActiveJob("adminmaster", "HQ", jobId);
assert.equal(context.exports.loadOrderV3ActiveJob("adminmaster", "HQ"), jobId);
assert.ok([...storage.keys()].some(key => key.startsWith("esm_scm_order_v3_running_job:")));
assert.equal(context.exports.loadOrderV3ActiveJob("other-user", "HQ"), null);
assert.equal(context.exports.loadOrderV3ActiveJob("adminmaster", "PL"), null);

context.exports.clearOrderV3ActiveJob("adminmaster", "HQ");
assert.equal(context.exports.loadOrderV3ActiveJob("adminmaster", "HQ"), null);

context.exports.saveOrderV3ActiveJob("adminmaster", "HQ", "../../another-job");
assert.equal(context.exports.loadOrderV3ActiveJob("adminmaster", "HQ"), null);

const legacyKey = `esm_scm_order_v3_active_job:${encodeURIComponent("legacy-user")}:HQ`;
storage.set(legacyKey, jobId);
assert.equal(context.exports.loadOrderV3ActiveJob("legacy-user", "HQ"), null);
assert.equal(storage.has(legacyKey), false, "Completed-job legacy keys are removed during migration.");

console.log("V3 job session passed: running-job isolation, restore, terminal clear and legacy-key cleanup.");
