import assert from "node:assert/strict";

import {
  LOCAL_SERVER_API_BASE,
  resolveBrowserApiBase,
  resolveBrowserDirectApiBase,
  resolveServerApiBase,
  SAME_ORIGIN_API_BASE,
  SAME_ORIGIN_DIRECT_API_BASE
} from "../lib/api/base-url.ts";
import { normalizeBackendInternalBaseUrl } from "../next.config.mjs";

assert.equal(SAME_ORIGIN_API_BASE, "/backend-api");
assert.equal(resolveBrowserApiBase(), "/backend-api");
assert.equal(resolveBrowserApiBase("https://api.example.com"), "https://api.example.com/api");
assert.equal(resolveBrowserApiBase("https://api.example.com/api/"), "https://api.example.com/api");

assert.equal(SAME_ORIGIN_DIRECT_API_BASE, "/api");
assert.equal(
  resolveBrowserDirectApiBase(undefined, { protocol: "https:", hostname: "esm.pikicat.com" }, "production"),
  "/api"
);
assert.equal(
  resolveBrowserDirectApiBase(undefined, { protocol: "http:", hostname: "localhost" }, "development"),
  "http://localhost:8002/api"
);
assert.equal(
  resolveBrowserDirectApiBase(undefined, { protocol: "http:", hostname: "localhost" }, "production"),
  "http://localhost:8002/api"
);
assert.equal(
  resolveBrowserDirectApiBase(undefined, { protocol: "http:", hostname: "192.168.0.245" }, "development"),
  "http://192.168.0.245:8002/api"
);
assert.equal(
  resolveBrowserDirectApiBase("https://api.example.com", { protocol: "https:", hostname: "esm.example.com" }, "production"),
  "https://api.example.com/api"
);

assert.equal(resolveServerApiBase(), LOCAL_SERVER_API_BASE);
assert.equal(resolveServerApiBase("http://backend:8002"), "http://backend:8002/api");

assert.equal(normalizeBackendInternalBaseUrl("http://backend.railway.internal:8002/"), "http://backend.railway.internal:8002");
assert.throws(() => normalizeBackendInternalBaseUrl("backend:8002"), /absolute http\(s\) URL/);
assert.throws(() => normalizeBackendInternalBaseUrl("http://backend:8002/api"), /without an \/api path/);
assert.throws(() => normalizeBackendInternalBaseUrl("ftp://backend:8002"), /http or https/);

console.log("API base URL policy tests passed.");
