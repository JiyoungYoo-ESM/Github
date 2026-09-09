import { skuCodeOf, numberValue } from "@/lib/global-demand-view-model";
import { formatNumber } from "@/lib/utils";
import type { IngredientAnalysis } from "@/types/api";

export function uniqueValueCount(rows: Array<Record<string, unknown>>, getter: (row: Record<string, unknown>) => string) {
  return new Set(rows.map(getter).filter((value) => value && value !== "-" && !value.includes("미분류"))).size;
}

export function ingredientCoverageStats(ingredient: IngredientAnalysis | null) {
  const coverage = ingredient?.coverage?.[0];
  const totalSkuCount = numberValue(coverage?.totalSkuCount);
  const matchedSkuCount = numberValue(coverage?.matchedSkuCount);
  const unmatchedSkuCount = numberValue(coverage?.unmatchedSkuCount);
  const taggedSkuFallback = uniqueValueCount(ingredient?.skuTags ?? [], skuCodeOf);
  return {
    matchedSkuCount: matchedSkuCount || taggedSkuFallback,
    unmatchedSkuCount: unmatchedSkuCount || (ingredient?.unmatchedSku?.length ?? 0),
    totalSkuCount: totalSkuCount || matchedSkuCount + unmatchedSkuCount
  };
}



export function ingredientCrossScopeNote(ingredient: IngredientAnalysis | null) {
  const coverage = ingredientCoverageStats(ingredient);
  const coveragePct = coverage.totalSkuCount > 0 ? (coverage.matchedSkuCount / coverage.totalSkuCount) * 100 : 0;
  const tagsBySku = new Map<string, number>();
  (ingredient?.skuTags ?? []).forEach((row) => {
    const sku = skuCodeOf(row);
    if (!sku || sku === "-") return;
    tagsBySku.set(sku, (tagsBySku.get(sku) ?? 0) + 1);
  });
  const multiTaggedSkuCount = Array.from(tagsBySku.values()).filter((count) => count > 1).length;
  return `상품명 키워드로 성분이 매칭된 SKU ${formatNumber(coverage.matchedSkuCount)}/${formatNumber(coverage.totalSkuCount)}개(${formatNumber(coveragePct, 1)}%) 범위입니다. 미매칭 SKU는 제외되며${multiTaggedSkuCount > 0 ? `, 복수 성분 태그 SKU ${formatNumber(multiTaggedSkuCount)}개는 각 성분에 중복 귀속되어` : ""} 성분별 합은 전체 매출 합과 일치하지 않을 수 있습니다.`;
}

