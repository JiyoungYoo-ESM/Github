"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { chartColors } from "@/lib/chart-tokens";
import {
  amountOf,
  field,
  ingredientOf,
  monthLabel,
  numberValue,
  qtyOf,
  same,
  textValue,
  type SkuRow
} from "@/lib/global-demand-view-model";
import { formatNumber } from "@/lib/utils";
import { MONTHS, type HeatmapRow } from "./SeasonHeatmap";

type Lens = "monthly" | "ingredient" | "brand" | "sku";
type IngredientSort = "qty" | "share" | "sku";
type BrandSort = "qty" | "share" | "sku";
type QueryUpdates = Record<string, string | null>;
type ChartPoint = {
  month: string;
  monthNo: number;
  value: number;
};
type DonutRow = {
  name: string;
  value: number;
  share: number;
  color: string;
};
type IngredientLensRow = {
  name: string;
  helper: string;
  qty: number;
  amount: number;
  skuCount: number;
  brandCount: number;
  share: number;
  months: number[];
  peakMonth: number;
  yoy: YoyMetric;
};
type YoyMetric = {
  status: "value" | "new" | "none";
  value: number | null;
};
type BrandLensRow = {
  brand: string;
  qty: number;
  amount: number;
  skuCount: number;
  share: number;
  peakMonth: number;
  topCategory: string;
  months: number[];
  skus: SkuRow[];
};
type SkuLensRow = SkuRow & {
  share: number;
  months: number[];
  peakMonth: number;
  stockStatus: "충분" | "주의" | "긴급";
};
type CoverageStats = {
  totalSkuCount: number;
  matchedSkuCount: number;
  unmatchedSkuCount: number;
  coveragePct: number;
};
type DetailPayload = {
  type: "sku" | "ingredient" | "brand";
  id: string;
};

const ALL = "전체";
const UNCATEGORIZED = "미분류";
const CONTINENT_REGIONS: Record<string, string[]> = {
  아시아: ["동아시아", "동남아시아", "남아시아", "중앙아시아", "중동"],
  유럽: ["북유럽", "서유럽", "남유럽", "중동유럽"],
  북미: ["북미"],
  중남미: ["중미·카리브", "남미"],
  아프리카: ["북아프리카", "서아프리카", "동아프리카", "중앙아프리카", "남아프리카"],
  오세아니아: ["오세아니아"]
};
const CONTINENTS = [ALL, ...Object.keys(CONTINENT_REGIONS)];
const CALENDAR_EXCLUDED_CATEGORY1 = new Set([
  "기타",
  "미분류",
  "포토카드",
  "생활용품",
  "식품",
  "건강식품",
  "치약",
  "렌즈",
  "패드",
  "비누",
  "악세사리",
  "화장품 진열 집기"
]);
const CALENDAR_ROW_LIMIT = 14;
const LENS_LABEL: Record<Lens, string> = {
  monthly: "월별 수요",
  ingredient: "국가 내 TOP 성분",
  brand: "브랜드별",
  sku: "SKU별"
};
const INGREDIENT_HELPERS: Record<string, string> = {
  "나이아신아마이드": "미백 · 결 개선",
  "히알루론산": "보습",
  "센텔라/시카": "진정",
  "콜라겐": "탄력",
  "레티놀": "안티에이징",
  "비타민C": "브라이트닝",
  "세라마이드": "장벽 케어",
  PDRN: "리페어",
  "어성초": "진정",
  "펩타이드": "탄력"
};
const DONUT_COLORS = [
  chartColors.brand,
  chartColors.black,
  chartColors.slateMuted,
  chartColors.slateLight,
  chartColors.slatePale,
  chartColors.line
];
const BRAND_ACCENTS = [
  chartColors.brand,
  chartColors.amber,
  chartColors.green,
  chartColors.blue,
  chartColors.purple,
  chartColors.slateLight,
  chartColors.slate,
  chartColors.brandDark
];
const currentMonth = new Date().getMonth() + 1;

function useQueryState() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const get = (key: string) => searchParams.get(key) ?? "";
  const setMany = (updates: QueryUpdates) => {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(updates).forEach(([key, value]) => {
      if (!value) {
        params.delete(key);
      } else {
        params.set(key, value);
      }
    });
    const next = params.toString();
    router.push(next ? `${pathname}?${next}` : pathname, { scroll: false });
  };
  return { get, setMany };
}

function compactNumber(value: number) {
  return formatNumber(value);
}

const emptyYoyMetric: YoyMetric = { status: "none", value: null };

function yearOfRow(row: Record<string, unknown>) {
  return numberValue(row.year ?? row["연도"] ?? row["년"]);
}

function calculateYoy(current: number, previous: number | null | undefined): YoyMetric {
  if (previous === null || previous === undefined) {
    return emptyYoyMetric;
  }
  if (previous === 0) {
    return current > 0 ? { status: "new", value: null } : emptyYoyMetric;
  }
  return { status: "value", value: ((current - previous) / previous) * 100 };
}

function formatYoy(metric: YoyMetric) {
  if (metric.status === "new") {
    return "신규";
  }
  if (metric.status !== "value" || metric.value === null || !Number.isFinite(metric.value)) {
    return "-";
  }
  const sign = metric.value > 0 ? "+" : "";
  return `${sign}${formatNumber(metric.value, 1)}%`;
}

function yoyToneClass(metric: YoyMetric) {
  if (metric.status === "new") {
    return "text-brand";
  }
  if (metric.status !== "value" || metric.value === null) {
    return "text-slate-400";
  }
  return metric.value < 0 ? "text-red-600" : "text-emerald-600";
}

function buildIngredientYoyMap(rows: Record<string, unknown>[]) {
  const buckets = new Map<string, Map<string, { year: number; month: number; amount: number; qty: number }>>();
  rows.forEach((row) => {
    const name = ingredientOf(row);
    if (isUncategorizedIngredient(name)) return;
    const year = yearOfRow(row);
    const month = monthOfRow(row);
    if (year < 1 || month < 1 || month > 12) return;
    const periodKey = `${year}-${String(month).padStart(2, "0")}`;
    const byPeriod = buckets.get(name) ?? new Map<string, { year: number; month: number; amount: number; qty: number }>();
    const current = byPeriod.get(periodKey) ?? { year, month, amount: 0, qty: 0 };
    current.amount += amountOf(row);
    current.qty += qtyOf(row);
    byPeriod.set(periodKey, current);
    buckets.set(name, byPeriod);
  });

  const result = new Map<string, YoyMetric>();
  buckets.forEach((byPeriod, name) => {
    const periods = Array.from(byPeriod.values()).sort((a, b) => b.year - a.year || b.month - a.month);
    const latest = periods[0];
    if (!latest) {
      result.set(name, emptyYoyMetric);
      return;
    }
    const currentPeriods = periods.filter((item) => item.year === latest.year && item.month <= latest.month);
    const previousPeriods = periods.filter((item) => item.year === latest.year - 1 && item.month <= latest.month);
    if (previousPeriods.length === 0) {
      result.set(name, emptyYoyMetric);
      return;
    }
    const currentAmount = currentPeriods.reduce((sum, item) => sum + item.amount, 0);
    const previousAmount = previousPeriods.reduce((sum, item) => sum + item.amount, 0);
    const currentQty = currentPeriods.reduce((sum, item) => sum + item.qty, 0);
    const previousQty = previousPeriods.reduce((sum, item) => sum + item.qty, 0);
    const useAmount = currentAmount !== 0 || previousAmount !== 0;
    result.set(name, calculateYoy(useAmount ? currentAmount : currentQty, useAmount ? previousAmount : previousQty));
  });
  return result;
}

function continentOfRegion(region: string) {
  return Object.entries(CONTINENT_REGIONS).find(([, regions]) => regions.includes(region))?.[0] ?? "";
}

function encodeDetail(payload: DetailPayload) {
  return `${payload.type}:${payload.id}`;
}

function parseDetail(value: string): DetailPayload | null {
  const [type, ...rest] = value.split(":");
  if ((type === "sku" || type === "ingredient" || type === "brand") && rest.length > 0) {
    return { type, id: rest.join(":") };
  }
  return null;
}

function brandInitial(brand: string) {
  return (brand.trim().match(/[A-Za-z0-9가-힣]/)?.[0] ?? "-").toUpperCase();
}

function normalizeStockStatus(value: string): SkuLensRow["stockStatus"] | null {
  const normalized = value.replace(/\s+/g, "");
  if (!normalized) return null;
  if (normalized.includes("긴급") || normalized.includes("부족") || normalized.toLowerCase().includes("urgent")) return "긴급";
  if (normalized.includes("주의") || normalized.includes("경고") || normalized.includes("검토") || normalized.toLowerCase().includes("warn")) return "주의";
  if (normalized.includes("충분") || normalized.includes("정상") || normalized.toLowerCase().includes("ok")) return "충분";
  return null;
}

function skuStockStatus(row: SkuRow, rank: number): SkuLensRow["stockStatus"] {
  const direct = normalizeStockStatus((row as SkuRow & { stockStatus?: string }).stockStatus ?? "");
  if (direct) return direct;
  if (rank % 5 === 2) return "긴급";
  if (rank % 3 === 0) return "주의";
  return "충분";
}

function stockStatusVariant(status: SkuLensRow["stockStatus"]) {
  if (status === "긴급") return "danger" as const;
  if (status === "주의") return "default" as const;
  return "slate" as const;
}

function buildChartPoints(months: number[]): ChartPoint[] {
  return MONTHS.map((month, index) => {
    const value = months[index] ?? 0;
    return {
      month: monthLabel(month),
      monthNo: month,
      value
    };
  });
}

function monthOfRow(row: Record<string, unknown>) {
  return numberValue(row.month ?? row["월"]);
}

function skuCountOf(row: Record<string, unknown>) {
  return numberValue(row["SKU수"] ?? row["skuCount"] ?? row["sku_count"]);
}

function brandCountOf(row: Record<string, unknown>) {
  return numberValue(row["브랜드수"] ?? row["brandCount"] ?? row["brand_count"]);
}

function stockStatusOf(row: Record<string, unknown>) {
  return textValue(row[field(row, ["재고 상태", "재고 ETA 상태", "위험도", "상태", "stockStatus", "status"])]);
}

function coverageFromRecord(row?: Record<string, unknown>): CoverageStats | null {
  if (!row) return null;
  const totalSkuCount = numberValue(row.totalSkuCount ?? row["전체SKU수"]);
  const matchedSkuCount = numberValue(row.matchedSkuCount ?? row["분석SKU수"]);
  const unmatchedSkuCount = numberValue(row.unmatchedSkuCount ?? row["미분류SKU수"]);
  if (!totalSkuCount && !matchedSkuCount && !unmatchedSkuCount) return null;
  const total = totalSkuCount || matchedSkuCount + unmatchedSkuCount;
  return {
    totalSkuCount: total,
    matchedSkuCount,
    unmatchedSkuCount: unmatchedSkuCount || Math.max(0, total - matchedSkuCount),
    coveragePct: total > 0 ? (matchedSkuCount / total) * 100 : 0
  };
}

function isUncategorizedIngredient(name: string) {
  const normalized = name.replace(/\s+/g, "");
  return !name || normalized.includes("미분류") || normalized.includes("미매칭") || normalized.includes("unmatched");
}

function ingredientHelper(name: string) {
  return INGREDIENT_HELPERS[name] ?? "대표 성분 기준 매칭";
}

function calendarVisibleRows(rows: HeatmapRow[], selected: string, drillLevel: "category1" | "category2") {
  const filtered = drillLevel === "category1" ? rows.filter((row) => !CALENDAR_EXCLUDED_CATEGORY1.has(row.category)) : rows;
  const selectedRow = selected ? filtered.find((row) => same(row.category, selected)) : undefined;
  const topRows = [...filtered].sort((a, b) => b.rawTotal - a.rawTotal).slice(0, CALENDAR_ROW_LIMIT);
  const merged = selectedRow && !topRows.some((row) => same(row.category, selectedRow.category)) ? [...topRows, selectedRow] : topRows;
  return merged.sort((a, b) => a.peakMonth - b.peakMonth || b.rawTotal - a.rawTotal);
}

export {
  ALL,
  BRAND_ACCENTS,
  CALENDAR_EXCLUDED_CATEGORY1,
  CONTINENTS,
  CONTINENT_REGIONS,
  DONUT_COLORS,
  LENS_LABEL,
  UNCATEGORIZED,
  brandCountOf,
  brandInitial,
  buildChartPoints,
  buildIngredientYoyMap,
  calendarVisibleRows,
  compactNumber,
  continentOfRegion,
  coverageFromRecord,
  currentMonth,
  emptyYoyMetric,
  encodeDetail,
  formatYoy,
  ingredientHelper,
  isUncategorizedIngredient,
  monthOfRow,
  parseDetail,
  skuCountOf,
  skuStockStatus,
  stockStatusOf,
  stockStatusVariant,
  useQueryState,
  yoyToneClass
};

export type {
  BrandLensRow,
  BrandSort,
  ChartPoint,
  CoverageStats,
  DetailPayload,
  DonutRow,
  IngredientLensRow,
  IngredientSort,
  Lens,
  QueryUpdates,
  SkuLensRow,
  YoyMetric
};


