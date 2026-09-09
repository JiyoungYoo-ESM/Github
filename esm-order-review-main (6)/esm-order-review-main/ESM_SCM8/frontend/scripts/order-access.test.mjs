import assert from "node:assert/strict";
import {
  canAccessOrderAnalysis,
  isOrderAnalysisBlockedForEntity,
  isOrderAnalysisPath,
  isOrderAnalysisScreen
} from "../lib/order-access.ts";

assert.equal(canAccessOrderAnalysis("sales_team"), false);
assert.equal(canAccessOrderAnalysis({ username: "sales_team" }), false);
assert.equal(canAccessOrderAnalysis("eu_manager"), true);

for (const pathname of [
  "/upload",
  "/order-analysis/order-review",
  "/order-analysis/new-order-logic",
  "/order-analysis/order-v3",
  "/order-analysis/season-factors",
  "/integrated-order-review",
  "/dashboard"
]) {
  assert.equal(isOrderAnalysisPath(pathname), true, pathname);
}
assert.equal(isOrderAnalysisPath("/insight/input"), false);
assert.equal(isOrderAnalysisPath("/season-trend/mapping-check"), false);

for (const screen of ["prep", "order", "order-v2", "order-v3", "season-factor", "gap", "final"]) {
  assert.equal(isOrderAnalysisScreen(screen), true, screen);
}
assert.equal(isOrderAnalysisScreen("diag"), false);
assert.equal(isOrderAnalysisScreen("idata"), false);

assert.equal(isOrderAnalysisBlockedForEntity("USA", "order"), false);
assert.equal(isOrderAnalysisBlockedForEntity("usa", "order-v2"), false);
assert.equal(isOrderAnalysisBlockedForEntity("USA", "prep"), false);
assert.equal(isOrderAnalysisBlockedForEntity("PL", "order"), false);
assert.equal(isOrderAnalysisBlockedForEntity("HQ", "prep"), true);
assert.equal(isOrderAnalysisBlockedForEntity("hq", "order"), true);
assert.equal(isOrderAnalysisBlockedForEntity("HQ", "order-v2"), false);
assert.equal(isOrderAnalysisBlockedForEntity("HQ", "order-v3"), false);

console.log("order access policy: ok");
