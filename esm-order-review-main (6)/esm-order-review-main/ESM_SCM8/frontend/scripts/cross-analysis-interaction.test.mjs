import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const frontendDirectory = join(scriptDirectory, "..");
const nextBin = join(frontendDirectory, "node_modules", "next", "dist", "bin", "next");

const emptySeason = {
  category1Monthly: [],
  category2Monthly: [],
  category1Share: [],
  category2Share: [],
  ytdComparison: [],
  topSku: [],
  skuMonthly: [],
  mappingQuality: [],
  uncategorizedSku: [],
  countryCategoryMonthly: [],
  countryCategory2Monthly: [],
  countryTopSku: [],
  countryCustomerSummary: [],
  countryCategoryCustomerSummary: [],
  customerSalesSummary: []
};

const emptyIngredient = {
  keywordMap: [],
  skuTags: [],
  monthlyTrend: [],
  summary: [],
  growth3m: [],
  ytdComparison: [],
  topSku: [],
  topBrand: [],
  brandMonthlyTrend: [],
  skuMonthlyTrend: [],
  unmatchedSku: [],
  coverage: [],
  countryCoverage: [],
  countryMonthlyTrend: [],
  countrySummary: [],
  countryGrowth3m: [],
  countryYtdComparison: [],
  countryTopSku: [],
  countryTopBrand: []
};

const summaryRows = [
  { country: "UK", brand: "Alpha", sku: "A1", product_name: "Serum", qty: 120_000, amount: 120_000 },
  { country: "UK", brand: "Beta", sku: "B1", product_name: "Cream", qty: 50_000, amount: 50_000 },
  { country: "FR", brand: "Alpha", sku: "A1", product_name: "Serum", qty: 80_000, amount: 80_000 }
];

const monthlyRows = [
  [2024, 1, "UK", "Alpha", "A1", "Serum", 100_000],
  [2024, 2, "UK", "Alpha", "A1", "Serum", 120_000],
  [2024, 1, "UK", "Beta", "B1", "Cream", 40_000],
  [2024, 2, "UK", "Beta", "B1", "Cream", 50_000],
  [2024, 1, "FR", "Alpha", "A1", "Serum", 70_000],
  [2024, 2, "FR", "Alpha", "A1", "Serum", 80_000],
  [2025, 1, "UK", "Alpha", "A1", "Serum", 150_000],
  [2025, 2, "UK", "Alpha", "A1", "Serum", 180_000],
  [2025, 1, "UK", "Beta", "B1", "Cream", 45_000],
  [2025, 2, "UK", "Beta", "B1", "Cream", 60_000],
  [2025, 1, "FR", "Alpha", "A1", "Serum", 75_000],
  [2025, 2, "FR", "Alpha", "A1", "Serum", 90_000]
].map(([year, month, country, brand, sku, product_name, amount]) => ({
  year,
  month,
  country,
  brand,
  sku,
  product_name,
  qty: amount,
  amount
}));

const analysisResult = {
  status: "success",
  analysis_schema_version: 3,
  entity_code: "PL",
  season_analysis: {
    ...emptySeason,
    category1Monthly: [{ year: 2025, month: 2, category1: "Skincare", qty: 330_000, amount: 330_000 }],
    countrySkuSummary: summaryRows,
    countrySkuMonthly: monthlyRows,
    dataMonths: ["2024-01", "2024-02", "2025-01", "2025-02"],
    monthCoverage: ["2024-01", "2024-02", "2025-01", "2025-02"].map((month) => ({
      month,
      status: "complete"
    }))
  },
  ingredient_analysis: emptyIngredient,
  uploaded_files: [],
  analysis_options: {
    start_date: "2024-01-01",
    end_date: "2025-02-28",
    average_eur_krw_rate: 1_500
  }
};

async function reservePort() {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close((error) => error ? reject(error) : resolve(port));
    });
  });
}

async function waitForServer(url, processOutput, timeoutMs = 45_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // The Next development server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Next server did not start within ${timeoutMs}ms.\n${processOutput()}`);
}

async function serverIsReachable(url) {
  try {
    const response = await fetch(url);
    return response.ok;
  } catch {
    return false;
  }
}

async function selectOption(page, selectorTestId, optionName) {
  await page.getByTestId(selectorTestId).click();
  await page.getByRole("option", { name: optionName, exact: true }).click();
}

async function run() {
  const testUser = {
    authenticated: true,
    username: "adminmaster",
    display_name: "Interaction Test",
    role: "TEST",
    account_type: "TEST",
    allowed_entities: ["PL"],
    entities: [
      {
        code: "PL",
        display_name: "폴란드",
        legal_name: "SKO Sp. z o.o.",
        integrated: true
      }
    ],
    is_admin: false
  };
  const authorizationScope = JSON.stringify({
    username: testUser.username,
    role: testUser.role,
    accountType: testUser.account_type,
    isAdmin: testUser.is_admin,
    allowedEntities: testUser.allowed_entities,
    entities: testUser.entities.map((entity) => [entity.code, entity.integrated])
  });
  const configuredBaseUrl = process.env.CROSS_INTERACTION_BASE_URL?.replace(/\/$/, "");
  const existingBaseUrl = configuredBaseUrl ?? "http://127.0.0.1:3000";
  const reuseExistingServer = await serverIsReachable(`${existingBaseUrl}/login`);
  const port = reuseExistingServer ? 0 : await reservePort();
  const baseUrl = reuseExistingServer ? existingBaseUrl : `http://127.0.0.1:${port}`;
  let output = "";
  const nextProcess = reuseExistingServer
    ? null
    : spawn(process.execPath, [nextBin, "dev", "-H", "127.0.0.1", "-p", String(port)], {
        cwd: frontendDirectory,
        env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
        stdio: ["ignore", "pipe", "pipe"]
      });
  nextProcess?.stdout.on("data", (chunk) => { output += chunk.toString(); });
  nextProcess?.stderr.on("data", (chunk) => { output += chunk.toString(); });

  let browser;
  try {
    if (nextProcess) await waitForServer(`${baseUrl}/login`, () => output);
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    await context.addInitScript(({ storedResult, authorizationScope }) => {
      sessionStorage.setItem("esm_scm_season_trend_storage_version", "5");
      sessionStorage.setItem("esm_scm_current_season_trend_ready", "1");
      sessionStorage.setItem("esm_scm_season_trend_result", JSON.stringify(storedResult));
      sessionStorage.setItem("esm_scm_authorization_scope", authorizationScope);
    }, { storedResult: analysisResult, authorizationScope });
    await context.route("**/backend-api/**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith("/auth/me")) {
        await route.fulfill({ json: testUser });
        return;
      }
      if (url.pathname.endsWith("/exchange-rate")) {
        await route.fulfill({ json: { eur_krw_rate: 1_500, rate_source: "test", rate_date: "2025-02-28" } });
        return;
      }
      if (url.pathname.endsWith("/analysis/latest-order-review")) {
        await route.fulfill({ json: { rows: [] } });
        return;
      }
      await route.fulfill({ status: 404, json: { detail: "not needed by cross-analysis interaction test" } });
    });

    const page = await context.newPage();
    const runtimeErrors = [];
    page.on("pageerror", (error) => runtimeErrors.push(error.message));
    await page.goto(`${baseUrl}/insight/cross`, { waitUntil: "domcontentloaded" });
    try {
      await page.getByTestId("cross-empty-state").waitFor({ state: "visible", timeout: 20_000 });
    } catch (error) {
      const bodyText = (await page.locator("body").innerText()).slice(0, 2_000);
      throw new Error(`Cross-analysis screen did not become ready (url=${page.url()}).\n${bodyText}`, { cause: error });
    }

    assert.equal(await page.getByTestId("cross-axis-country-brand").getAttribute("aria-pressed"), "true");
    assert.equal(await page.getByTestId("cross-metric-sales").getAttribute("aria-pressed"), "true");
    assert.equal(await page.getByTestId("cross-export-report").isDisabled(), true);

    await selectOption(page, "cross-row-select", "UK");
    await selectOption(page, "cross-column-select", "Alpha");
    await page.getByTestId("cross-heatmap").waitFor({ state: "visible" });
    assert.match(await page.getByTestId("cross-heatmap").innerText(), /UK/);
    assert.match(await page.getByTestId("cross-heatmap").innerText(), /Alpha/);
    assert.equal(await page.getByTestId("cross-export-report").isEnabled(), true);

    await page.getByTestId("cross-scale-share").click();
    assert.equal(await page.getByTestId("cross-scale-share").getAttribute("aria-pressed"), "true");
    assert.match(await page.getByTestId("cross-heatmap").innerText(), /100\.0%/);

    await page.getByTestId("cross-metric-mom").click();
    await page.getByTestId("cross-mom-current-month").waitFor({ state: "visible" });
    assert.equal(await page.getByTestId("cross-mom-current-month").inputValue(), "2025-02");
    assert.match(await page.getByTestId("cross-mom-comparison-month").innerText(), /2025.*1/);

    await page.getByTestId("cross-metric-yoy").click();
    await page.getByTestId("cross-yoy-base-month").selectOption("1");
    assert.match(await page.getByTestId("cross-yoy-comparison-month").innerText(), /2024.*1/);
    assert.match(await page.getByTestId("cross-heatmap").innerText(), /\+50%/);

    await page.getByTestId("cross-axis-country-sku").click();
    await page.getByTestId("cross-empty-state").waitFor({ state: "visible" });
    assert.equal(await page.getByTestId("cross-selection-chips").count(), 0);
    assert.equal(await page.getByTestId("cross-export-report").isDisabled(), true);
    assert.deepEqual(runtimeErrors, []);

    await context.close();
    console.log("Cross-analysis browser interaction checks passed.");
  } finally {
    await browser?.close();
    if (nextProcess && !nextProcess.killed) nextProcess.kill();
  }
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
