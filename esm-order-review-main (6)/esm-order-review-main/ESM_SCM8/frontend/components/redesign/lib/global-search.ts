import { displayBrandName } from "@/lib/brand-display";
import { amountOf, brandOf, countryOf, numberValue, productNameOf, qtyOf, skuCodeOf } from "@/lib/global-demand-view-model";
import { validCrossLabel } from "./cross-label";
import type { GlobalSearchResult, GlobalSearchSource, GlobalSearchTarget } from "./types";

function normalizedSearchText(value: string) {
  return value.normalize("NFKC").replace(/\s+/g, "").toLowerCase();
}

function searchSkuOf(row: Record<string, unknown>) {
  const sku = skuCodeOf(row);
  return sku && sku !== "-" ? sku : String(row.sku ?? row.SKU ?? "-").trim() || "-";
}

function searchProductNameOf(row: Record<string, unknown>) {
  const productName = productNameOf(row);
  return productName && productName !== "-" ? productName : String(row.productName ?? row.product_name ?? row.name ?? "-").trim() || "-";
}

function searchBrandOf(row: Record<string, unknown>) {
  const brand = brandOf(row);
  return brand && brand !== "-" ? brand : String(row.brand ?? "-").trim() || "-";
}

function searchAmountOf(row: Record<string, unknown>) {
  return amountOf(row) || numberValue(row.salesAmount) || numberValue(row.requiredOrderAmount) || numberValue(row.stockAmount);
}

function searchQtyOf(row: Record<string, unknown>) {
  return qtyOf(row) || numberValue(row.recentSalesQty) || numberValue(row.requiredOrderQty) || numberValue(row.availableQty);
}

function addSearchTab(current: GlobalSearchResult, tab: GlobalSearchSource["tabs"][number]) {
  if (!current.tabs.includes(tab.label)) {
    current.tabs.push(tab.label);
  }
  if (!current.tabScreens.includes(tab.screen)) {
    current.tabScreens.push(tab.screen);
  }
}

function addGlobalSearchCandidate(
  map: Map<string, GlobalSearchResult>,
  searchTermsByKey: Map<string, Set<string>>,
  target: GlobalSearchTarget,
  label: string,
  source: GlobalSearchSource,
  description: string,
  searchTerms: string[]
) {
  if (!validCrossLabel(label)) return;
  const row = source.row;
  const key = `${target}:${normalizedSearchText(label)}`;
  const current =
    map.get(key) ??
    ({
      id: key,
      target,
      label,
      description,
      amount: 0,
      qty: 0,
      screen: source.tabs[0]?.screen ?? target,
      searchText: "",
      tabs: [],
      tabScreens: []
    } satisfies GlobalSearchResult);
  current.amount += searchAmountOf(row);
  current.qty += searchQtyOf(row);
  current.description = description;
  const terms = searchTermsByKey.get(key) ?? new Set<string>();
  [label, description, ...searchTerms, ...source.tabs.map((tab) => tab.label)]
    .filter(Boolean)
    .forEach((term) => terms.add(term));
  searchTermsByKey.set(key, terms);
  source.tabs.forEach((tab) => addSearchTab(current, tab));
  if (current.tabScreens.includes(target)) {
    current.screen = target;
  }
  map.set(key, current);
}

export function buildGlobalSearchIndex(sources: GlobalSearchSource[]): GlobalSearchResult[] {
  const candidates = new Map<string, GlobalSearchResult>();
  const searchTermsByKey = new Map<string, Set<string>>();
  sources.forEach((source) => {
    const row = source.row;
    const country = countryOf(row);
    const brand = searchBrandOf(row);
    const displayBrand = displayBrandName(brand);
    const sku = searchSkuOf(row);
    const productName = searchProductNameOf(row);
    const skuLabel = productName && productName !== "-" ? productName : sku;
    addGlobalSearchCandidate(candidates, searchTermsByKey, "country", country, source, "국가 인사이트로 이동", [country]);
    addGlobalSearchCandidate(candidates, searchTermsByKey, "brand", displayBrand, source, "브랜드 인사이트로 이동", [displayBrand, brand]);
    addGlobalSearchCandidate(
      candidates,
      searchTermsByKey,
      "sku",
      skuLabel,
      source,
      [sku, displayBrand].filter((value) => value && value !== "-").join(" · ") || "SKU 인사이트로 이동",
      [country, displayBrand, brand, sku, productName]
    );
  });

  return Array.from(candidates.values())
    .map((item) => ({
      ...item,
      searchText: normalizedSearchText(Array.from(searchTermsByKey.get(item.id) ?? []).join(" "))
    }))
    .sort((a, b) => b.amount - a.amount || b.qty - a.qty || a.label.localeCompare(b.label));
}

export function searchGlobalSearchIndex(index: GlobalSearchResult[], query: string): GlobalSearchResult[] {
  const normalizedQuery = normalizedSearchText(query);
  if (normalizedQuery.length < 1) return [];

  return index
    .filter((item) => item.searchText.includes(normalizedQuery))
    .slice(0, 18);
}

export function buildGlobalSearchResults(sources: GlobalSearchSource[], query: string): GlobalSearchResult[] {
  return searchGlobalSearchIndex(buildGlobalSearchIndex(sources), query);
}
