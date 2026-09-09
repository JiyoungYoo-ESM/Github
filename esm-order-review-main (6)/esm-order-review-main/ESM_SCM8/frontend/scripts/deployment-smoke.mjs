import assert from "node:assert/strict";

const origin = (process.argv[2] ?? process.env.DEPLOYMENT_ORIGIN ?? "").replace(/\/$/, "");
const timeoutSeconds = Number(process.env.DEPLOYMENT_SMOKE_TIMEOUT_SECONDS ?? "300");
const retryDelayMs = Number(process.env.DEPLOYMENT_SMOKE_RETRY_DELAY_MS ?? "10000");

if (!/^https?:\/\/[^/]+$/i.test(origin)) {
  throw new Error(
    "Usage: node scripts/deployment-smoke.mjs https://your-frontend.example.com"
  );
}
if (!Number.isFinite(timeoutSeconds) || timeoutSeconds <= 0) {
  throw new Error("DEPLOYMENT_SMOKE_TIMEOUT_SECONDS must be a positive number.");
}

async function request(path) {
  const response = await fetch(`${origin}${path}`, {
    redirect: "manual",
    headers: { "X-Requested-With": "deployment-smoke" }
  });
  return response;
}

async function verifyDeployment() {
  const login = await request("/login");
  assert.equal(login.status, 200, `frontend /login returned ${login.status}`);

  for (const path of ["/backend-api/health/live", "/backend-api/health/ready"]) {
    const response = await request(path);
    assert.equal(response.status, 200, `frontend-to-backend proxy ${path} returned ${response.status}`);
  }

  const health = await request("/backend-api/health");
  assert.equal(health.status, 200, `frontend-to-backend proxy /backend-api/health returned ${health.status}`);
  assert.match(health.headers.get("content-type") ?? "", /application\/json/i, "backend health response is not JSON");
  const healthBody = await health.json();
  assert.ok(healthBody && typeof healthBody === "object" && healthBody.status, "backend health response has no status field");

  const anonymousMe = await request("/backend-api/auth/me");
  assert.equal(anonymousMe.status, 401, `anonymous /backend-api/auth/me must return 401, got ${anonymousMe.status}`);

  for (const path of ["/docs/esm-scm-detail-guide-v10.html", "/reports/anua_global_market_report_revised.pdf"]) {
    const response = await request(path);
    assert.ok([301, 302, 303, 307, 308].includes(response.status), `anonymous ${path} must redirect to login, got ${response.status}`);
    const location = response.headers.get("location");
    assert.ok(location, `anonymous ${path} redirect has no location header`);
    assert.equal(new URL(location, origin).pathname, "/login", `anonymous ${path} must redirect to /login, got ${location}`);
  }
}

const deadline = Date.now() + timeoutSeconds * 1000;
let lastError;
while (Date.now() < deadline) {
  try {
    await verifyDeployment();
    lastError = undefined;
    break;
  } catch (error) {
    lastError = error;
    console.warn(`Deployment not ready yet: ${error.message}. Retrying in ${retryDelayMs}ms.`);
    await new Promise((resolve) => setTimeout(resolve, retryDelayMs));
  }
}
if (lastError) {
  throw new Error(`Deployment smoke timed out after ${timeoutSeconds}s: ${lastError.message}`);
}

console.log(`Deployment smoke passed: ${origin}`);
