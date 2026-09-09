const ORDER_ANALYSIS_BLOCKED_USERNAMES = new Set(["sales_team"]);

const ORDER_ANALYSIS_PATH_PREFIXES = [
  "/dashboard",
  "/integrated-order-review",
  "/order-analysis",
  "/order-review",
  "/stock-gap",
  "/upload"
] as const;

const ORDER_ANALYSIS_SCREEN_IDS = new Set(["prep", "order", "order-v2", "order-v3", "season-factor", "gap", "final"]);

type UsernameSource = string | { username: string } | null | undefined;

export function canAccessOrderAnalysis(user: UsernameSource): boolean {
  const username = typeof user === "string" ? user : user?.username;
  return !ORDER_ANALYSIS_BLOCKED_USERNAMES.has((username ?? "").trim().toLowerCase());
}

export function isOrderAnalysisPath(pathname: string): boolean {
  return ORDER_ANALYSIS_PATH_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}

export function isOrderAnalysisScreen(screen: string): boolean {
  return ORDER_ANALYSIS_SCREEN_IDS.has(screen);
}

export function isOrderAnalysisBlockedForEntity(
  entityCode: string | null | undefined,
  screen: string
): boolean {
  const code = String(entityCode ?? "").trim().toUpperCase();
  // HQ는 기존 발주분석의 원천 계약이 없으므로 데이터 입력과 레거시
  // 발주분석만 막는다. V2 탭 자체는 열어 두되, HQ 정책 미확정에 따른
  // 실제 계산 차단은 백엔드가 담당한다.
  return code === "HQ" && (screen === "prep" || screen === "order");
}
