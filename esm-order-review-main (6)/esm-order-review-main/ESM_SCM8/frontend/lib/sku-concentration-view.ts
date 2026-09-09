import {
  defaultSkuConcentrationThresholds,
  normalizeSkuConcentrationThresholds,
  type BrandDependencyResult,
  type ConcentrationJudgement,
  type SkuConcentrationThresholds
} from "@/lib/sku-concentration";
import { formatNumber } from "@/lib/utils";

export const allSkuConcentrationBrands = "전체";
export const defaultSkuConcentrationPageSize = 10;

export const skuConcentrationStatusOptions: Array<{ value: "all" | ConcentrationJudgement; label: string }> = [
  { value: "all", label: "전체" },
  { value: "shortage_risk", label: "재고 부족" },
  { value: "overstock", label: "과잉 재고" },
  { value: "balanced", label: "적정" },
  { value: "needs_check", label: "확인 필요" }
];

export const skuConcentrationSortOptions = [
  { value: "salesShare", label: "판매 비중 높은 순" },
  { value: "diff", label: "불균형 큰 순" },
  { value: "stockShare", label: "재고 비중 높은 순" },
  { value: "grade", label: "등급" }
] as const;

export type SkuConcentrationSortKey = (typeof skuConcentrationSortOptions)[number]["value"];

export const judgementBadgeClass: Record<ConcentrationJudgement, string> = {
  shortage_risk: "border-red-100 bg-red-50 text-brand",
  overstock: "border-orange-100 bg-orange-50 text-orange-700",
  balanced: "border-slate-200 bg-slate-100 text-slate-700",
  needs_check: "border-slate-200 bg-slate-100 text-slate-500"
};

export const diffToneClass: Record<ConcentrationJudgement, string> = {
  shortage_risk: "text-brand",
  overstock: "text-orange-700",
  balanced: "text-slate-500",
  needs_check: "text-slate-400"
};

export const gradeBadgeClass: Record<string, string> = {
  A: "border-emerald-100 bg-emerald-50 text-emerald-700",
  B: "border-blue-100 bg-blue-50 text-blue-700",
  C: "border-slate-200 bg-slate-100 text-slate-600"
};

export const concentrationLevelLabel: Record<BrandDependencyResult["risk"], string> = {
  high: "높음",
  medium: "보통",
  low: "낮음"
};

export const concentrationLevelClass: Record<BrandDependencyResult["risk"], string> = {
  high: "border-red-100 bg-red-50 text-brand",
  medium: "border-orange-100 bg-orange-50 text-orange-700",
  low: "border-emerald-100 bg-emerald-50 text-emerald-700"
};

export const concentrationFillClass: Record<BrandDependencyResult["risk"], string> = {
  high: "bg-red-100",
  medium: "bg-orange-100",
  low: "bg-emerald-100"
};

export const concentrationTopClass: Record<BrandDependencyResult["risk"], string> = {
  high: "bg-brand",
  medium: "bg-orange-500",
  low: "bg-emerald-500"
};

export function percent(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-";
  }
  const rounded = Math.abs(value) >= 99.95 ? formatNumber(value, 0) : formatNumber(value, digits);
  return `${rounded}%`;
}

export function diffPercent(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-";
  }
  return `${value > 0 ? "+" : ""}${formatNumber(value, 1)}%p`;
}

export function amount(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-";
  }
  return `₩${formatNumber(value, 0)}`;
}

export function compactAmount(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-";
  }
  if (Math.abs(value) >= 100_000_000) {
    return `${formatNumber(value / 100_000_000, 0)}억`;
  }
  if (Math.abs(value) >= 10_000) {
    return `${formatNumber(value / 10_000, 0)}만`;
  }
  return formatNumber(value);
}

export function readSkuConcentrationThresholds(settings: unknown): SkuConcentrationThresholds {
  const source = settings as {
    sku_shortage_threshold_pct?: unknown;
    sku_overstock_threshold_pct?: unknown;
  } | null;
  return normalizeSkuConcentrationThresholds({
    shortagePct:
      typeof source?.sku_shortage_threshold_pct === "number"
        ? source.sku_shortage_threshold_pct
        : defaultSkuConcentrationThresholds.shortagePct,
    overstockPct:
      typeof source?.sku_overstock_threshold_pct === "number"
        ? source.sku_overstock_threshold_pct
        : defaultSkuConcentrationThresholds.overstockPct
  });
}
