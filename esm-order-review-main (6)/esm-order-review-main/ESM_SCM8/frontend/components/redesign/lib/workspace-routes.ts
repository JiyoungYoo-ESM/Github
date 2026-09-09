import type { Screen } from "./types";

export const WORKSPACE_SCREEN_PATHS = {
  overview: "/overview/inventory",
  prep: "/upload",
  diag: "/mapping-check",
  order: "/order-analysis/order-review",
  "order-v2": "/order-analysis/new-order-logic",
  "order-v3": "/order-analysis/order-v3",
  "season-factor": "/order-analysis/season-factors",
  gap: "/order-analysis/stock-gap",
  final: "/order-analysis/final",
  idata: "/insight/input",
  country: "/insight/country",
  brand: "/insight/brand",
  sku: "/insight/sku",
  category: "/insight/category",
  ingredient: "/insight/ingredient",
  season: "/season-calendar",
  cross: "/insight/cross",
  report: "/insight/brand-report",
  support: "/support"
} as const satisfies Record<Screen, string>;

const WORKSPACE_PATH_SCREENS = new Map<string, Screen>(
  Object.entries(WORKSPACE_SCREEN_PATHS).map(([screen, path]) => [path, screen as Screen])
);

const WORKSPACE_PATH_ALIASES: Record<string, Screen> = {
  "/order-analysis": "order",
  "/order-review": "order",
  "/stock-gap": "gap",
  "/season-trend/mapping-check": "diag",
  "/season-trend/season-calendar": "season"
};

function normalizePathname(pathname: string) {
  if (!pathname || pathname === "/") return pathname || "/";
  return pathname.replace(/\/+$/, "");
}

export function pathForWorkspaceScreen(screen: Screen) {
  return WORKSPACE_SCREEN_PATHS[screen];
}

export function workspaceScreenFromPathname(pathname: string): Screen | null {
  const normalizedPathname = normalizePathname(pathname);
  return WORKSPACE_PATH_SCREENS.get(normalizedPathname) ?? WORKSPACE_PATH_ALIASES[normalizedPathname] ?? null;
}
