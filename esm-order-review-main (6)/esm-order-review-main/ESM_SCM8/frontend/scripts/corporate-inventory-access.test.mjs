import assert from "node:assert/strict";
import {
  canAccessCorporateInventory,
  canAccessCorporateInventoryForEntity,
  isCorporateInventoryPath,
  isCorporateInventoryScreen
} from "../lib/corporate-inventory-access.ts";

assert.equal(canAccessCorporateInventory("adminmaster"), true);
assert.equal(canAccessCorporateInventory({ username: " ADMINMASTER " }), true);
assert.equal(canAccessCorporateInventory("ia"), false);
assert.equal(canAccessCorporateInventory({ username: "eu_manager" }), false);
assert.equal(canAccessCorporateInventoryForEntity("HQ"), true);
assert.equal(canAccessCorporateInventoryForEntity("PL"), false);
assert.equal(canAccessCorporateInventoryForEntity(null), false);
assert.equal(isCorporateInventoryPath("/overview/inventory"), true);
assert.equal(isCorporateInventoryPath("/insight/input"), false);
assert.equal(isCorporateInventoryScreen("overview"), true);
assert.equal(isCorporateInventoryScreen("order"), false);

console.log("corporate inventory access policy: ok");
