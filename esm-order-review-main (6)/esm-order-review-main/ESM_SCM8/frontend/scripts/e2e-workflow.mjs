/**
 * Browser-level critical-path test. Run against a deployed/staging stack so
 * authentication, proxying, cookies, and real API wiring are all exercised.
 * Required: E2E_LOGIN_ID, E2E_LOGIN_PASSWORD. Optional: E2E_BASE_URL.
 */
import { chromium } from "playwright";

const baseUrl = process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000";
const loginId = process.env.E2E_LOGIN_ID;
const loginPassword = process.env.E2E_LOGIN_PASSWORD;

if (!loginId || !loginPassword) {
  throw new Error("E2E_LOGIN_ID and E2E_LOGIN_PASSWORD must be configured for the browser E2E test.");
}

const browser = await chromium.launch({ headless: true });
try {
  const anonymous = await browser.newContext();
  const anonymousPage = await anonymous.newPage();
  await anonymousPage.goto(`${baseUrl}/order-analysis`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await anonymousPage.waitForURL(/\/login(?:\?|$)/, { timeout: 15_000 });
  await anonymous.close();

  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForSelector("#login-id", { state: "visible" });
  await page.fill("#login-id", loginId);
  await page.fill("#login-password", loginPassword);
  await page.click('button[type="submit"]');
  await page.waitForURL(`${baseUrl}/`, { waitUntil: "domcontentloaded", timeout: 30_000 });

  await page.goto(`${baseUrl}/order-analysis`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.getByRole("button", { name: "리포트 만들기" }).click();
  await page.getByRole("dialog").waitFor({ state: "visible", timeout: 10_000 });

  await page.goto(`${baseUrl}/insight/brand-report`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.getByRole("heading", { name: "브랜드 자동 리포트" }).waitFor({ state: "visible", timeout: 15_000 });
  await context.close();
  console.log("Critical browser E2E workflow passed.");
} finally {
  await browser.close();
}
