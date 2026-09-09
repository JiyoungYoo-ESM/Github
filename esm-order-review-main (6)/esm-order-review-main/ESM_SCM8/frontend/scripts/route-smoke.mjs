// 라우트 스모크 테스트 (IMPROVEMENT_PLAN.md 5단계 보완책 2, 7단계 행동 검증 보강).
//
// 실제 브라우저(Playwright)로 앱의 모든 라우트를 순회하며 콘솔 에러 0건·본문 비어있지
// 않음을 확인하고, 전체 페이지 스크린샷을 저장한다. 5단계(워크스페이스 해체) 커밋마다
// 이 스크립트를 다시 돌려서 방금 뗀 화면이 이전 스크린샷과 시각적으로 같은지 대조한다.
//
// 라우트 순회 뒤에는 행동 검증 2건을 추가로 돈다(behaviorChecks):
//   - 세션 쿠키 없이 보호된 라우트 직접 접근 → /login 리다이렉트(권한 없는 접근 검증)
//   - 새로고침·뒤로가기 후에도 화면이 비지 않고 URL이 일치하는지(딥링크·뒤로가기 검증)
//
// 사용법:
//   1. 백엔드(8002)와 프론트 dev 서버(3000)를 먼저 띄운다.
//   2. SMOKE_LOGIN_ID / SMOKE_LOGIN_PASSWORD 환경변수를 테스트 계정 값으로 설정한다.
//      (비밀번호를 이 스크립트에 하드코딩하지 않는다 — IMPROVEMENT_PLAN.md 4번 참고)
//   3. node scripts/route-smoke.mjs
//   4. scripts/route-smoke-screenshots/ 안의 PNG를 이전 실행 결과와 육안으로 대조한다.
//      (baseline/ 폴더에 첫 실행 결과를 보관해두고, 이후 실행은 latest/에 저장한다)
//
// 스크린샷 자체는 gitignore 대상 — 커밋하지 않는다.

import { chromium } from "playwright";
import { mkdirSync, existsSync, cpSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const BASE_URL = process.env.SMOKE_BASE_URL ?? "http://127.0.0.1:3000";
const LOGIN_ID = process.env.SMOKE_LOGIN_ID;
const LOGIN_PASSWORD = process.env.SMOKE_LOGIN_PASSWORD;
const OUT_DIR = join(__dirname, "route-smoke-screenshots");
const LATEST_DIR = join(OUT_DIR, "latest");
const BASELINE_DIR = join(OUT_DIR, "baseline");

// app/ 아래 page.tsx 35개 (find app -name "page.tsx" 기준, 2026-07-20 확정 목록).
// 화면이 추가/삭제되면 이 목록도 같이 갱신한다.
const DEFAULT_ROUTES = [
  "/",
  "/about",
  "/dashboard",
  "/detail-guide",
  "/esm",
  "/ingredient-trend",
  "/insight/brand",
  "/insight/brand-report",
  "/insight/country",
  "/insight/cross",
  "/insight/ingredient",
  "/insight/input",
  "/insight/sku",
  "/integrated-order-review",
  "/login",
  "/manual",
  "/mapping-check",
  "/order-analysis",
  "/order-analysis/final",
  "/order-analysis/order-review",
  "/order-analysis/sku-concentration",
  "/order-analysis/stock-gap",
  "/order-review",
  "/season-calendar",
  "/season-trend",
  "/season-trend/category-top-sku",
  "/season-trend/country-insight",
  "/season-trend/global-demand",
  "/season-trend/ingredient-top",
  "/season-trend/ingredient-trend",
  "/season-trend/mapping-check",
  "/season-trend/season-calendar",
  "/season-trend/sku-season",
  "/sku-concentration",
  "/stock-gap",
  "/upload"
];

const ROUTES = process.env.SMOKE_ROUTES
  ? process.env.SMOKE_ROUTES.split(",").map((route) => route.trim()).filter(Boolean)
  : DEFAULT_ROUTES;

function routeToFilename(route) {
  const slug = route === "/" ? "root" : route.replace(/^\//, "").replace(/\//g, "-");
  return `${slug}.png`;
}

async function login(page) {
  if (!LOGIN_ID || !LOGIN_PASSWORD) {
    throw new Error(
      "SMOKE_LOGIN_ID / SMOKE_LOGIN_PASSWORD 환경변수가 없습니다. 테스트 계정 값을 셸에 설정한 뒤 다시 실행하세요."
    );
  }
  await page.goto(`${BASE_URL}/login`, { waitUntil: "domcontentloaded" });
  // Next 개발 서버에서는 DOMContentLoaded 직후에도 로그인 폼의 React 이벤트 핸들러가
  // 아직 hydrate되지 않을 수 있다. 이때 fill하면 DOM 값만 바뀌고 state는 빈 값으로 남는다.
  await page.waitForTimeout(1500);
  await page.fill("#login-id", LOGIN_ID);
  await page.fill("#login-password", LOGIN_PASSWORD);
  await page.click('button[type="submit"]');
  // 첫 루트 진입은 개발 서버의 초기 컴파일로 load 이벤트가 늦을 수 있다.
  // 인증 성공 후 주소 전환과 DOM 준비까지만 확인하면 라우트 순회 전에 충분하다.
  await page.waitForURL(`${BASE_URL}/`, { waitUntil: "domcontentloaded", timeout: 20000 });
}

/**
 * 인증 가드 검증: 세션 쿠키가 전혀 없는 새 브라우저 컨텍스트로 보호된 라우트에
 * 직접 접근하면 AuthGuard(components/auth/AuthGuard.tsx)가 /api/auth/me 401을 보고
 * /login으로 리다이렉트해야 한다. 백엔드 401 자체는 tests/test_auth.py가 이미
 * 커버하므로, 여기서는 "그 401을 프론트가 실제로 로그인 화면으로 넘기는가"를
 * 실제 브라우저로 확인한다.
 */
async function testUnauthenticatedRedirect(browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const targetRoute = "/upload";
  let ok = false;
  let detail = "";
  try {
    await page.goto(`${BASE_URL}${targetRoute}`, { waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForURL(`${BASE_URL}/login`, { timeout: 10000 });
    ok = true;
  } catch (error) {
    detail = error instanceof Error ? error.message : String(error);
  }
  const finalUrl = page.url();
  await context.close();
  return {
    name: `미인증 접근 시 /login 리다이렉트 (${targetRoute})`,
    ok: ok && finalUrl.endsWith("/login"),
    detail: ok ? "" : detail || `최종 URL이 /login이 아님: ${finalUrl}`
  };
}

async function testProtectedStaticDocument(browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const protectedPath = "/docs/esm-scm-detail-guide-v10.html";
  let ok = false;
  let detail = "";
  try {
    await page.goto(`${BASE_URL}${protectedPath}`, { waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForURL(/\/login(?:\?|$)/, { timeout: 10000 });
    ok = true;
  } catch (error) {
    detail = error instanceof Error ? error.message : String(error);
  }
  const finalUrl = page.url();
  await context.close();
  return {
    name: `익명 정적 문서 접근 차단 (${protectedPath})`,
    ok: ok && new URL(finalUrl).pathname === "/login",
    detail: ok ? "" : detail || `최종 URL이 /login이 아님: ${finalUrl}`
  };
}

async function testLoginKeyboardAccessibility(browser) {
  const context = await browser.newContext();
  const page = await context.newPage();
  let ok = false;
  let detail = "";
  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: "domcontentloaded", timeout: 20000 });
    const idInput = page.locator("#login-id");
    const passwordInput = page.locator("#login-password");
    const labels = await Promise.all([
      idInput.evaluate((input) => input.labels?.length ?? 0),
      passwordInput.evaluate((input) => input.labels?.length ?? 0)
    ]);
    await idInput.focus();
    await page.keyboard.press("Tab");
    const focusedId = await page.evaluate(() => document.activeElement?.id ?? "");
    ok = labels.every((count) => count > 0) && focusedId === "login-password";
    if (!ok) detail = `labels=${labels.join(",")}, focused=${focusedId}`;
  } catch (error) {
    detail = error instanceof Error ? error.message : String(error);
  }
  await context.close();
  return { name: "로그인 폼 label·키보드 포커스", ok, detail };
}

/**
 * 새로고침·뒤로가기·딥링크 안정성: 이 워크스페이스는 화면 전환이 URL 변경 없는
 * in-memory state인 라우트가 있어(SiliconAnalyticsWorkspace), 새로고침/뒤로가기 시
 * 화면이 완전히 빈 채로 죽지 않는지가 실질적인 회귀 포인트다.
 */
async function testReloadAndBackNavigation(page) {
  const first = "/order-analysis/order-review";
  const second = "/order-analysis/stock-gap";
  try {
    await page.goto(`${BASE_URL}${first}`, { waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForTimeout(800);

    // 새로고침(딥링크 재진입과 동일한 경로)
    await page.reload({ waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForTimeout(800);
    const afterReload = (await page.textContent("body"))?.trim().length ?? 0;
    if (afterReload === 0) {
      return { name: "새로고침·뒤로가기 안정성", ok: false, detail: "새로고침 후 본문이 비어 있음" };
    }

    // 다른 라우트로 이동 후 뒤로가기
    await page.goto(`${BASE_URL}${second}`, { waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForTimeout(800);
    await page.goBack({ waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForTimeout(800);
    const afterBack = (await page.textContent("body"))?.trim().length ?? 0;
    const urlAfterBack = page.url();
    if (afterBack === 0 || !urlAfterBack.endsWith(first)) {
      return {
        name: "새로고침·뒤로가기 안정성",
        ok: false,
        detail: `뒤로가기 후 상태 불일치 (url=${urlAfterBack}, bodyLength=${afterBack})`
      };
    }
    return { name: "새로고침·뒤로가기 안정성", ok: true, detail: "" };
  } catch (error) {
    return {
      name: "새로고침·뒤로가기 안정성",
      ok: false,
      detail: error instanceof Error ? error.message : String(error)
    };
  }
}

async function main() {
  mkdirSync(LATEST_DIR, { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage();
  await login(page);

  const behaviorChecks = [
    await testUnauthenticatedRedirect(browser),
    await testProtectedStaticDocument(browser),
    await testLoginKeyboardAccessibility(browser),
    await testReloadAndBackNavigation(page)
  ];

  const results = [];

  for (const route of ROUTES) {
    const consoleErrors = [];
    const pageErrors = [];
    const listener = (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    };
    const pageErrorListener = (error) => pageErrors.push(error.message);
    page.on("console", listener);
    page.on("pageerror", pageErrorListener);

    let bodyLength = 0;
    let navError = null;
    try {
      // networkidle은 Next dev의 HMR 연결·애널리틱스 등 백그라운드 활동 때문에 SPA에서
      // 잘 안 settle되는 경우가 있다(관찰됨: "/", "/login" 재방문 시 20s 타임아웃). 대신
      // domcontentloaded로 받고 클라이언트 렌더/리다이렉트가 끝날 시간을 명시적으로 준다.
      await page.goto(`${BASE_URL}${route}`, { waitUntil: "domcontentloaded", timeout: 20000 });
      await page.waitForLoadState("load", { timeout: 5000 }).catch(() => {});
      // 각 라우트는 SiliconAnalyticsWorkspace 루트를 새로 마운트하며 환율 API를 1회
      // 호출한다(실제 외부 API 왕복). 다음 라우트로 너무 빨리 넘어가면 이 fetch가
      // 페이지 이동으로 중간에 abort되어 "Failed to fetch" 콘솔 에러로 잘못 보인다
      // (실사용자는 SPA 내부 이동만 하므로 이 문제를 겪지 않음 — 스모크 스크립트가
      // 매번 풀 네비게이션을 하기 때문에 생기는 테스트 한정 타이밍 이슈).
      await page.waitForTimeout(1500);
      const bodyText = await page.textContent("body");
      bodyLength = bodyText?.trim().length ?? 0;
      await page.screenshot({ path: join(LATEST_DIR, routeToFilename(route)), fullPage: true });
    } catch (error) {
      navError = error instanceof Error ? error.message : String(error);
    }

    page.off("console", listener);
    page.off("pageerror", pageErrorListener);

    results.push({
      route,
      ok: !navError && bodyLength > 0 && consoleErrors.length === 0 && pageErrors.length === 0,
      bodyLength,
      consoleErrors,
      pageErrors,
      navError
    });
  }

  await browser.close();

  console.log(`\n${"route".padEnd(38)}  상태   본문길이  콘솔에러`);
  console.log("-".repeat(70));
  let failed = 0;
  for (const result of results) {
    const status = result.ok ? "OK" : "FAIL";
    if (!result.ok) failed += 1;
    console.log(`${result.route.padEnd(38)}  ${status.padEnd(5)} ${String(result.bodyLength).padEnd(8)}  ${result.consoleErrors.length + result.pageErrors.length}`);
    if (result.navError) console.log(`  ⨯ 탐색 오류: ${result.navError}`);
    for (const err of result.consoleErrors) console.log(`  ⨯ 콘솔 에러: ${err}`);
    for (const err of result.pageErrors) console.log(`  ⨯ 런타임 에러: ${err}`);
  }
  console.log("-".repeat(70));
  console.log(`${results.length - failed}/${results.length} 통과, 스크린샷: ${LATEST_DIR}`);

  console.log(`\n${"행동 검증".padEnd(38)}  상태`);
  console.log("-".repeat(70));
  let behaviorFailed = 0;
  for (const check of behaviorChecks) {
    const status = check.ok ? "OK" : "FAIL";
    if (!check.ok) behaviorFailed += 1;
    console.log(`${check.name.padEnd(38)}  ${status}`);
    if (check.detail) console.log(`  ⨯ ${check.detail}`);
  }
  console.log("-".repeat(70));
  console.log(`${behaviorChecks.length - behaviorFailed}/${behaviorChecks.length} 통과`);
  failed += behaviorFailed;

  if (!existsSync(BASELINE_DIR)) {
    cpSync(LATEST_DIR, BASELINE_DIR, { recursive: true });
    console.log(`baseline/ 없어서 이번 결과로 새로 생성했습니다. 다음 실행부터 baseline/과 latest/를 육안으로 대조하세요.`);
  } else {
    console.log(`baseline/과 latest/ 스크린샷을 육안으로 대조하세요. baseline을 갱신하려면 --update-baseline로 다시 실행하세요.`);
  }

  if (process.argv.includes("--update-baseline")) {
    rmSync(BASELINE_DIR, { recursive: true, force: true });
    cpSync(LATEST_DIR, BASELINE_DIR, { recursive: true });
    console.log("baseline/을 갱신했습니다.");
  }

  if (failed > 0) {
    process.exitCode = 1;
  }
}

main();
