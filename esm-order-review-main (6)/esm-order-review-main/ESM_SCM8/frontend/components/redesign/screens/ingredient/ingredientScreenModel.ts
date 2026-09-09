import { amountOf, brandOf, countryOf, ingredientOf, numberValue, qtyOf, skuCodeOf } from "@/lib/global-demand-view-model";
import { displayBrandName } from "@/lib/brand-display";
import { lowBaseAmount } from "@/lib/low-base";
import type { IngredientAnalysis, MonthCoverage } from "@/types/api";
import type { ComparisonBasis } from "../../lib/types";
import {
  growthBadgeClass,
  completedYtdComparableYearWindow,
  growthDisplayLabel,
  latestComparableMonths,
  LOW_BASE_QTY,
  ytdAmountComparisonsByLabel
} from "../../lib/yoy-comparison";

export function ingredientYoyClass(yoy: string) {
  if (yoy === "신규") return "text-pos";
  return growthBadgeClass(yoy);
}

export type IngredientRankRow = {
  ingredient: string;
  amount: number;
  qty: number;
  yoy: string;
  mom: string;
  country: string;
  brand: string;
  width: string;
};

export function topLabelFromMap(map: Map<string, number>) {
  return Array.from(map.entries()).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "-";
}

export function buildIngredientBrandMap(rows: Array<Record<string, unknown>>) {
  const result = new Map<string, Map<string, number>>();
  rows.forEach((row) => {
    const ingredient = ingredientOf(row);
    const brand = displayBrandName(brandOf(row));
    if (!ingredient || ingredient.includes("미분류") || !brand || brand.includes("미분류")) return;
    const current = result.get(ingredient) ?? new Map<string, number>();
    current.set(brand, (current.get(brand) ?? 0) + (amountOf(row) || qtyOf(row)));
    result.set(ingredient, current);
  });
  return result;
}

export function mergeIngredientBrandMaps(...maps: Array<Map<string, Map<string, number>>>) {
  const result = new Map<string, Map<string, number>>();
  maps.forEach((map) => {
    map.forEach((brandValues, ingredient) => {
      const current = result.get(ingredient) ?? new Map<string, number>();
      brandValues.forEach((value, brand) => {
        current.set(brand, (current.get(brand) ?? 0) + value);
      });
      result.set(ingredient, current);
    });
  });
  return result;
}

export function buildIngredientCountryMap(rows: Array<Record<string, unknown>>) {
  const result = new Map<string, Map<string, number>>();
  rows.forEach((row) => {
    const ingredient = ingredientOf(row);
    const country = countryOf(row);
    if (!ingredient || ingredient.includes("미분류") || !country || country === "미상") return;
    const current = result.get(ingredient) ?? new Map<string, number>();
    current.set(country, (current.get(country) ?? 0) + (amountOf(row) || qtyOf(row)));
    result.set(ingredient, current);
  });
  return result;
}

export function buildIngredientGrowthLabels(
  rows: Array<Record<string, unknown>>,
  comparisonBasis: ComparisonBasis,
  completedMonthKeys?: ReadonlySet<string>
) {
  const byIngredient = new Map<string, Map<string, { year: number; month: number; amount: number; qty: number }>>();
  rows.forEach((row) => {
    const ingredient = ingredientOf(row);
    const year = numberValue(row.year ?? row["연도"] ?? row["년"]);
    const month = numberValue(row.month ?? row["월"]);
    if (!ingredient || ingredient.includes("미분류") || year < 1 || month < 1 || month > 12) return;
    const periodKey = `${year}-${String(month).padStart(2, "0")}`;
    const periods = byIngredient.get(ingredient) ?? new Map<string, { year: number; month: number; amount: number; qty: number }>();
    const current = periods.get(periodKey) ?? { year, month, amount: 0, qty: 0 };
    current.amount += amountOf(row);
    current.qty += qtyOf(row);
    periods.set(periodKey, current);
    byIngredient.set(ingredient, periods);
  });

  const result = new Map<string, string>();
  if (comparisonBasis === "none") {
    byIngredient.forEach((_, ingredient) => result.set(ingredient, "-"));
    return result;
  }
  if (comparisonBasis === "mom") {
    const comparableMonths = latestComparableMonths(rows);
    if (!comparableMonths) {
      byIngredient.forEach((_, ingredient) => result.set(ingredient, "-"));
      return result;
    }
    const [latestMonth, previousMonth] = comparableMonths;
    byIngredient.forEach((periods, ingredient) => {
      const latest = periods.get(latestMonth);
      const previous = periods.get(previousMonth);
      const currentAmount = latest?.amount ?? 0;
      const previousAmount = previous?.amount ?? 0;
      const currentQty = latest?.qty ?? 0;
      const previousQty = previous?.qty ?? 0;
      const useAmount = currentAmount !== 0 || previousAmount !== 0;
      const current = useAmount ? currentAmount : currentQty;
      const previousValue = useAmount ? previousAmount : previousQty;
      if (previousValue === 0) {
        result.set(ingredient, current > 0 ? "신규" : "-");
        return;
      }
      result.set(ingredient, growthDisplayLabel(current, previousValue, useAmount ? lowBaseAmount() : LOW_BASE_QTY) ?? "-");
    });
    return result;
  }

  const window = completedYtdComparableYearWindow(rows, completedMonthKeys);
  if (!window) {
    byIngredient.forEach((_, ingredient) => result.set(ingredient, "-"));
    return result;
  }
  ytdAmountComparisonsByLabel(rows, window, ingredientOf).forEach((comparison, ingredient) => {
    result.set(ingredient, comparison.growth);
  });
  return result;
}

export function buildIngredientRankRows(
  ingredient: IngredientAnalysis | null,
  comparisonBasis: ComparisonBasis,
  monthCoverage: MonthCoverage[] = []
): IngredientRankRow[] {
  const summaryRows = ingredient?.summary ?? [];
  const brandMap = mergeIngredientBrandMaps(
    buildIngredientBrandMap(ingredient?.topBrand ?? []),
    buildIngredientBrandMap(ingredient?.skuTags ?? [])
  );
  const countryMap = buildIngredientCountryMap(ingredient?.countrySummary ?? []);
  const completeMonthKeys = monthCoverage.length > 0
    ? new Set(monthCoverage.filter((item) => item.status === "complete").map((item) => item.month))
    : undefined;
  const yoyMap = buildIngredientGrowthLabels(ingredient?.monthlyTrend ?? [], "yoy", completeMonthKeys);
  const momMap = buildIngredientGrowthLabels(ingredient?.monthlyTrend ?? [], "mom");
  const maxAmount = Math.max(...summaryRows.map((row) => amountOf(row)), 1);
  return summaryRows
    .map((row) => {
      const name = ingredientOf(row);
      return {
        ingredient: name,
        amount: amountOf(row),
        qty: qtyOf(row),
        yoy: yoyMap.get(name) ?? "-",
        mom: momMap.get(name) ?? "-",
        country: topLabelFromMap(countryMap.get(name) ?? new Map<string, number>()),
        brand: topLabelFromMap(brandMap.get(name) ?? new Map<string, number>()),
        width: `${Math.max(4, (amountOf(row) / maxAmount) * 100)}%`
      };
    })
    .filter((row) => row.ingredient && !row.ingredient.includes("미분류"))
    .sort((a, b) => b.amount - a.amount || b.qty - a.qty);
}

export function keywordListOf(row: Record<string, unknown>) {
  const raw = row.keywords;
  return Array.isArray(raw) ? raw.map(String).filter(Boolean) : [];
}

export function matchedKeywordListOf(row: Record<string, unknown>) {
  const raw = row.matched_keywords ?? row.matchedKeywords ?? row.keywords;
  return Array.isArray(raw) ? raw.map(String).filter(Boolean) : [];
}

// keyword/standard 그룹 키 구분자로 공백 대신 NUL 문자를 쓴다 - 둘 중 하나에 공백이
// 섞여도(예: 키워드가 "센텔라 추출물"처럼 공백 포함) 그룹 키가 충돌하지 않는다.
const KEYWORD_STANDARD_KEY_SEPARATOR = String.fromCharCode(0);

export function buildDetectedIngredientKeywordRows(ingredient: IngredientAnalysis | null) {
  const grouped = new Map<string, { keyword: string; standard: string; skuCodes: Set<string> }>();
  (ingredient?.skuTags ?? []).forEach((row) => {
    const standard = ingredientOf(row);
    const sku = skuCodeOf(row);
    matchedKeywordListOf(row).forEach((keyword) => {
      const key = `${keyword}${KEYWORD_STANDARD_KEY_SEPARATOR}${standard}`;
      const current = grouped.get(key) ?? { keyword, standard, skuCodes: new Set<string>() };
      if (sku && sku !== "-") {
        current.skuCodes.add(sku);
      }
      grouped.set(key, current);
    });
  });
  return Array.from(grouped.values()).sort((a, b) => b.skuCodes.size - a.skuCodes.size || a.keyword.localeCompare(b.keyword, "ko"));
}
