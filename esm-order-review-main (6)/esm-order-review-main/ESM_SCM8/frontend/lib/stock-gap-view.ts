import {
  dayDiff,
  formatDate,
  parseDate,
  startOfDay,
  type StockGapComputedItem
} from "@/lib/stock-gap";
import { formatNumber } from "@/lib/utils";
import type { StockGapStatus } from "@/types/api";

export const stockGapStatusMeta: Record<StockGapStatus, { dot: string; badge: string; order: number; label: string }> = {
  urgent_replenishment: {
    dot: "bg-brand",
    badge: "border-red-100 bg-red-50 text-brand",
    order: 0,
    label: "긴급"
  },
  stock_gap: {
    dot: "bg-orange-500",
    badge: "border-orange-100 bg-orange-50 text-orange-700",
    order: 1,
    label: "주의"
  },
  stockout_no_inbound: {
    dot: "bg-orange-500",
    badge: "border-orange-100 bg-orange-50 text-orange-700",
    order: 1,
    label: "입고예정 없음"
  },
  waiting_eta: {
    dot: "bg-orange-500",
    badge: "border-orange-100 bg-orange-50 text-orange-700",
    order: 1,
    label: "주의"
  },
  needs_check: {
    dot: "bg-slate-400",
    badge: "border-slate-200 bg-slate-100 text-slate-700",
    order: 2,
    label: "확인"
  },
  sufficient: {
    dot: "bg-emerald-500",
    badge: "border-emerald-100 bg-emerald-50 text-emerald-700",
    order: 3,
    label: "정상"
  }
};

export function numberText(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-";
  }
  return formatNumber(value, digits);
}

export function stockGapBadgeText(item: StockGapComputedItem) {
  if (item.gapDays !== null && item.gapDays > 0) {
    if (item.gapTiming === "active") return `현재 공백 ${item.gapDays}일`;
    if (item.gapTiming === "future") return `예정 공백 ${item.gapDays}일`;
    return `공백 ${item.gapDays}일`;
  }
  if (!item.stockoutDate && item.dailySalesQty !== null && item.dailySalesQty <= 0) {
    return "판매 없음";
  }
  if (!item.stockoutDate) {
    return "계산 불가";
  }
  if (!item.earliestEtaDate && item.stockoutDate) {
    const baseDate = parseDate(item.baseDate) ?? startOfDay(new Date());
    const diff = dayDiff(baseDate, item.stockoutDate);
    if (diff < 0) {
      return `${Math.abs(diff)}일 전 소진됨`;
    }
    if (diff === 0) {
      return "오늘 소진";
    }
    const days = Math.max(diff, 0);
    return `소진 ${days}일`;
  }
  return "공백 없음";
}

export function stockGapBadgeClass(item: StockGapComputedItem) {
  if (item.gapDays !== null && item.gapDays > 0) {
    if (item.gapTiming === "active") return "border-black bg-black text-white";
    if (item.gapTiming === "future") return "border-red-100 bg-red-50 text-brand";
  }
  return stockGapStatusMeta[item.status].badge;
}

export function stockGapDotClass(item: StockGapComputedItem) {
  if (item.gapDays !== null && item.gapDays > 0 && item.gapTiming === "active") {
    return "bg-black";
  }
  return stockGapStatusMeta[item.status].dot;
}

export function stockoutLabel(item: StockGapComputedItem) {
  if (!item.stockoutDate) {
    return "-";
  }
  const baseDate = parseDate(item.baseDate) ?? startOfDay(new Date());
  const diff = dayDiff(baseDate, item.stockoutDate);
  if (diff < 0) {
    return `${Math.abs(diff)}일 전 소진됨`;
  }
  if (diff === 0) {
    return "오늘 소진";
  }
  return `${diff}일 후 소진 예정`;
}

export function stockGapNarrative(item: StockGapComputedItem) {
  if (!item.stockoutDate || !item.earliestEtaDate) {
    return "소진일 또는 ETA가 없어 재고 공백 여부를 확정할 수 없습니다.";
  }
  const baseDate = parseDate(item.baseDate) ?? startOfDay(new Date());
  const stockout = formatDate(item.stockoutDate);
  const eta = formatDate(item.earliestEtaDate);

  if (item.gapTiming === "active") {
    return `기준일 ${formatDate(baseDate)} 현재 이미 재고가 소진된 상태이며, 가장 빠른 ETA ${eta}까지 ${item.gapDays ?? 0}일의 재고 공백이 진행 중입니다.`;
  }
  if (item.gapTiming === "future") {
    return `현재 판매 속도 기준 ${stockout}에 재고가 소진될 예정이고, 가장 빠른 ETA가 ${eta}라서 ${item.gapDays ?? 0}일의 재고 공백이 발생 예정입니다.`;
  }
  if (item.gapTiming === "ended") {
    return `재고 공백은 ${stockout}부터 ${eta}까지 발생했으며 기준일 현재는 종료된 구간입니다.`;
  }
  if (item.gapTiming === "none") {
    return `가장 빠른 ETA ${eta}가 소진일 ${stockout}보다 빠르거나 같아 재고 공백은 없습니다.`;
  }
  return "재고 공백 상태를 계산하려면 일평균 판매량과 ETA가 필요합니다.";
}

export function stockGapStatusCounts(items: StockGapComputedItem[]) {
  return {
    urgent: items.filter((item) => item.status === "urgent_replenishment").length,
    warning: items.filter(
      (item) => item.status === "stock_gap" || item.status === "waiting_eta" || item.status === "stockout_no_inbound"
    ).length,
    normal: items.filter((item) => item.status === "sufficient").length,
    avgGap:
      items.length === 0
        ? 0
        : Math.round(
            items.reduce((sum, item) => sum + Math.max(item.gapDays ?? 0, 0), 0) /
              Math.max(items.filter((item) => (item.gapDays ?? 0) > 0).length, 1)
          )
  };
}

export function sortStockGapRiskItems(items: StockGapComputedItem[]) {
  return [...items].sort((a, b) => {
    const statusOrder = stockGapStatusMeta[a.status].order - stockGapStatusMeta[b.status].order;
    if (statusOrder !== 0) {
      return statusOrder;
    }
    return Math.max(b.gapDays ?? 0, 0) - Math.max(a.gapDays ?? 0, 0) || a.sku.localeCompare(b.sku);
  });
}

export function stockGapActionText(item: StockGapComputedItem) {
  const source = `${item.urgentAction ?? ""} ${item.priorityAction ?? ""}`.replace(/\s+/g, " ").trim();

  if (item.status === "urgent_replenishment") {
    if (source.includes("항공") || source.includes("앞당") || source.includes("전환") || (item.gapDays && item.gapDays > 0)) {
      return "입고 필요";
    }
    return "긴급 발주";
  }
  if (item.status === "stock_gap") {
    return "입고 필요";
  }
  if (item.status === "stockout_no_inbound") {
    // 소진됐는데 들어올 물량이 없다 - ETA를 확인할 대상이 아니라 발주를 잡을 대상이다.
    return "발주 필요";
  }
  if (item.status === "waiting_eta") {
    return "ETA 확인";
  }

  if (source.includes("발주 불필요") || source.includes("불필요")) {
    return "발주 불필요";
  }
  if (source.includes("본사")) {
    return "본사 이동";
  }
  if (source.includes("항공") || source.includes("앞당") || source.includes("전환")) {
    return "입고 필요";
  }
  if (source.toUpperCase().includes("ETA")) {
    return "ETA 확인";
  }
  if (source.includes("발주 필요") || source.includes("발주")) {
    return "발주 필요";
  }

  switch (item.status) {
    case "needs_check":
      return "확인 필요";
    case "sufficient":
    default:
      return "발주 불필요";
  }
}
