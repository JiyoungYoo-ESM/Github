import assert from "node:assert/strict";
import { allowedEntityOptions, ENTITY_OPTIONS } from "../lib/entities.ts";

const matrix = {
  adminmaster: ["HQ", "PL", "UK", "USA", "ME", "MX", "MY", "VN"],
  eu_manager: ["HQ", "PL", "UK"],
  bm1: ["HQ", "PL", "UK", "USA", "ME"],
  bm2: ["HQ", "PL", "UK", "USA", "ME"],
  bm3: ["HQ", "PL", "UK", "USA", "ME"],
  hnb_team: ["HQ", "PL", "USA"],
  ia: ["HQ", "PL", "UK", "USA", "ME", "MX", "MY", "VN"],
  my_team: ["HQ", "MY"],
  sales_team: ["HQ", "PL"],
  vn_team: ["HQ", "VN"]
};

assert.deepEqual(ENTITY_OPTIONS.map((entity) => entity.code), matrix.adminmaster);
const headquarters = ENTITY_OPTIONS.find((entity) => entity.code === "HQ");
assert.equal(headquarters?.integrated, true);
assert.equal(headquarters?.orderIntegrated, false);
assert.equal(headquarters?.insightIntegrated, true);
for (const [username, allowed] of Object.entries(matrix)) {
  assert.deepEqual(
    allowedEntityOptions(allowed).map((entity) => entity.code),
    allowed,
    username
  );
}
assert.equal(allowedEntityOptions(matrix.eu_manager).some((entity) => entity.code === "USA"), false);
assert.equal(allowedEntityOptions(matrix.my_team).some((entity) => entity.code === "PL"), false);
assert.equal(allowedEntityOptions(matrix.vn_team).some((entity) => entity.code === "MY"), false);
assert.equal(allowedEntityOptions(matrix.hnb_team).some((entity) => entity.code === "UK"), false);
assert.equal(allowedEntityOptions(matrix.sales_team).some((entity) => entity.code === "USA"), false);
assert.deepEqual(allowedEntityOptions(matrix.ia).map((entity) => entity.code), matrix.adminmaster);

console.log("entity permission UI matrix: ok");
