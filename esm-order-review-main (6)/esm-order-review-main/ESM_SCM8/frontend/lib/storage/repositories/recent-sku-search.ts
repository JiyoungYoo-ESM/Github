import { readJsonItem, writeJsonItem } from "@/lib/storage/adapter";

const RECENT_KEY = "esm_scm_recent_sku_searches";
const MAX_RECENT = 5;

export function getRecentSkuSearches(): string[] {
  const parsed = readJsonItem<unknown>("local", RECENT_KEY, []);
  return Array.isArray(parsed)
    ? parsed.filter((item): item is string => typeof item === "string").slice(0, MAX_RECENT)
    : [];
}

export function addRecentSkuSearch(sku: string): void {
  const next = [sku, ...getRecentSkuSearches().filter((item) => item !== sku)].slice(0, MAX_RECENT);
  writeJsonItem("local", RECENT_KEY, next);
}
