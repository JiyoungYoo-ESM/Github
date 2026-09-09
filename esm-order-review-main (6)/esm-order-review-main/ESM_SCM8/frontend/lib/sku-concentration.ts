import type { SkuConcentrationSource } from "@/types/api";

export type ConcentrationJudgement = "shortage_risk" | "overstock" | "balanced" | "needs_check";
export type ConcentrationStatus = ConcentrationJudgement;
export type ConcentrationScope = "global" | "brand";

export type SkuConcentrationThresholds = {
  shortagePct: number;
  overstockPct: number;
};

export type SkuConcentrationResult = SkuConcentrationSource & {
  salesAmount: number | null;
  stockAmount: number | null;
  salesSharePct: number;
  stockSharePct: number;
  shareDiffPct: number | null;
  judgement: ConcentrationJudgement;
  status: ConcentrationStatus;
  grade: string;
  missingProductName: boolean;
};

export type BrandDependencyResult = {
  brand: string;
  skuCount: number;
  activeSkuCount: number;
  top1SharePct: number;
  top3SharePct: number;
  risk: "high" | "medium" | "low";
};

export const defaultSkuConcentrationThresholds: SkuConcentrationThresholds = {
  shortagePct: 2.5,
  overstockPct: 3
};

export const concentrationStatusLabels: Record<ConcentrationJudgement, string> = {
  shortage_risk: "재고 부족",
  overstock: "과잉 재고",
  balanced: "적정",
  needs_check: "확인 필요"
};

export function normalizeSkuConcentrationThresholds(
  thresholds?: Partial<SkuConcentrationThresholds> | null
): SkuConcentrationThresholds {
  const shortagePct =
    typeof thresholds?.shortagePct === "number" && Number.isFinite(thresholds.shortagePct)
      ? Math.abs(thresholds.shortagePct)
      : defaultSkuConcentrationThresholds.shortagePct;
  const overstockPct =
    typeof thresholds?.overstockPct === "number" && Number.isFinite(thresholds.overstockPct)
      ? Math.abs(thresholds.overstockPct)
      : defaultSkuConcentrationThresholds.overstockPct;

  return { shortagePct, overstockPct };
}

export function determineConcentrationJudgement(
  salesAmount: number | null,
  stockAmount: number | null,
  salesSharePct: number,
  stockSharePct: number,
  thresholds?: Partial<SkuConcentrationThresholds> | null
): ConcentrationJudgement {
  const resolvedThresholds = normalizeSkuConcentrationThresholds(thresholds);

  if (salesAmount === null || stockAmount === null || !Number.isFinite(salesSharePct) || !Number.isFinite(stockSharePct)) {
    return "needs_check";
  }
  if (salesAmount === 0 && stockAmount === 0) {
    return "needs_check";
  }

  const diff = stockSharePct - salesSharePct;
  if (diff <= -resolvedThresholds.shortagePct) {
    return "shortage_risk";
  }
  if (diff >= resolvedThresholds.overstockPct) {
    return "overstock";
  }
  return "balanced";
}

export const determineConcentrationStatus = determineConcentrationJudgement;

function safeAmount(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? Math.max(value, 0) : null;
}

function gradeBySalesShare(sharePct: number) {
  if (sharePct >= 8) {
    return "A";
  }
  if (sharePct >= 3) {
    return "B";
  }
  return "C";
}

function isMissingProductName(value: string | null | undefined) {
  const normalized = String(value ?? "").trim();
  return !normalized || normalized === "-" || normalized.includes("상품명 미확인");
}

export function calculateSkuConcentration(
  skus: SkuConcentrationSource[],
  scope: ConcentrationScope,
  brandFilter?: string,
  thresholds?: Partial<SkuConcentrationThresholds> | null
): SkuConcentrationResult[] {
  const scoped =
    scope === "brand" && brandFilter ? skus.filter((sku) => sku.brand === brandFilter) : skus;
  const totalSales = scoped.reduce((sum, sku) => sum + (safeAmount(sku.salesAmount) ?? 0), 0);
  const totalStock = scoped.reduce((sum, sku) => sum + (safeAmount(sku.stockAmount) ?? 0), 0);

  const globalSalesTotal = skus.reduce((sum, sku) => sum + (safeAmount(sku.salesAmount) ?? 0), 0);

  return scoped.map((sku) => {
    const salesAmount = safeAmount(sku.salesAmount);
    const stockAmount = safeAmount(sku.stockAmount);
    const salesSharePct = totalSales > 0 && salesAmount !== null ? (salesAmount / totalSales) * 100 : 0;
    const stockSharePct = totalStock > 0 && stockAmount !== null ? (stockAmount / totalStock) * 100 : 0;
    const shareDiffPct = salesAmount === null || stockAmount === null ? null : stockSharePct - salesSharePct;
    const globalSalesSharePct = globalSalesTotal > 0 && salesAmount !== null ? (salesAmount / globalSalesTotal) * 100 : 0;
    const judgement = determineConcentrationJudgement(salesAmount, stockAmount, salesSharePct, stockSharePct, thresholds);

    return {
      ...sku,
      salesAmount,
      stockAmount,
      salesSharePct,
      stockSharePct,
      shareDiffPct,
      judgement,
      status: judgement,
      grade: sku.abcGrade || gradeBySalesShare(globalSalesSharePct),
      missingProductName: isMissingProductName(sku.productName)
    };
  });
}

export function calculateBrandDependency(skus: SkuConcentrationSource[]): BrandDependencyResult[] {
  const brands = Array.from(new Set(skus.map((sku) => sku.brand).filter(Boolean))).sort((a, b) => a.localeCompare(b));
  const riskOrder: Record<BrandDependencyResult["risk"], number> = {
    high: 3,
    medium: 2,
    low: 1
  };

  return brands
    .map((brand) => {
      const rows = skus
        .filter((sku) => sku.brand === brand)
        .map((sku) => ({ ...sku, salesAmount: safeAmount(sku.salesAmount) ?? 0 }))
        .sort((a, b) => b.salesAmount - a.salesAmount);
      const totalSales = rows.reduce((sum, sku) => sum + sku.salesAmount, 0);
      const activeSkuCount = rows.filter((sku) => sku.salesAmount > 0).length;
      const top1SharePct = totalSales > 0 ? ((rows[0]?.salesAmount ?? 0) / totalSales) * 100 : 0;
      const top3SharePct =
        totalSales > 0 ? (rows.slice(0, 3).reduce((sum, sku) => sum + sku.salesAmount, 0) / totalSales) * 100 : 0;
      const risk: BrandDependencyResult["risk"] =
        top3SharePct >= 80 ? "high" : top3SharePct >= 50 ? "medium" : "low";

      return {
        brand,
        skuCount: rows.length,
        activeSkuCount,
        top1SharePct,
        top3SharePct,
        risk
      };
    })
    .sort(
      (a, b) =>
        riskOrder[b.risk] - riskOrder[a.risk] ||
        b.top3SharePct - a.top3SharePct ||
        b.top1SharePct - a.top1SharePct ||
        b.skuCount - a.skuCount ||
        a.brand.localeCompare(b.brand)
    );
}
