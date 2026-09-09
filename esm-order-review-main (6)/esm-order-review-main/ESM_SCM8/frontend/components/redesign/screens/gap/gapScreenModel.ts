import {
  calculateStockGapShortageQty,
  computeStockGapItem,
  formatDate as formatStockGapDate,
  stockGapStatusOrder
} from "@/lib/stock-gap";
import { formatNumber } from "@/lib/utils";

export type SortDirection = "desc" | "asc";
export type StockGapComputed = ReturnType<typeof computeStockGapItem>;

export type GapSortKey = "stock" | "sales" | "stockout" | "eta" | "gap" | "shortage";
export type GapTableColumnKey =
  | "productCode"
  | "sku"
  | "brand"
  | "stock"
  | "sales"
  | "stockout"
  | "eta"
  | "gap"
  | "shortage"
  | "reason"
  | "status";

export const gapTableColumns: Array<{
  key: GapTableColumnKey;
  label: string;
  defaultWidth: number;
  minWidth: number;
  align?: "left" | "center";
}> = [
  { key: "productCode", label: "상품코드", defaultWidth: 150, minWidth: 120, align: "left" },
  { key: "sku", label: "SKU", defaultWidth: 390, minWidth: 240, align: "left" },
  { key: "brand", label: "브랜드", defaultWidth: 150, minWidth: 110, align: "center" },
  { key: "stock", label: "현재고", defaultWidth: 100, minWidth: 82, align: "center" },
  { key: "sales", label: "판매 속도", defaultWidth: 120, minWidth: 96, align: "center" },
  { key: "stockout", label: "소진 예정", defaultWidth: 110, minWidth: 94, align: "center" },
  { key: "eta", label: "최초 ETA", defaultWidth: 110, minWidth: 94, align: "center" },
  { key: "gap", label: "공백", defaultWidth: 90, minWidth: 76, align: "center" },
  { key: "shortage", label: "부족 수량", defaultWidth: 120, minWidth: 100, align: "center" },
  { key: "reason", label: "판단 사유", defaultWidth: 420, minWidth: 220, align: "left" },
  { key: "status", label: "상태", defaultWidth: 110, minWidth: 88, align: "center" }
];

export const sortableGapColumns: Partial<Record<GapTableColumnKey, GapSortKey>> = {
  stock: "stock",
  sales: "sales",
  stockout: "stockout",
  eta: "eta",
  gap: "gap",
  shortage: "shortage"
};

export const gapSortLabels: Record<GapSortKey, string> = {
  stock: "현재고",
  sales: "판매 속도",
  stockout: "소진 예정",
  eta: "최초 ETA",
  gap: "공백 일수",
  shortage: "부족 수량"
};

export function stockGapDisplayStatus(item: StockGapComputed) {
  if (item.status === "urgent_replenishment" || item.status === "stock_gap") {
    return "재고공백";
  }
  if (item.status === "stockout_no_inbound") {
    return "입고예정 없음";
  }
  if (item.status === "waiting_eta") {
    // ETA 자체가 없는 행(출고일·운송수단 결측)과 ETA가 지난 행(입고 대조 필요)은 원인이 다르다.
    return item.pastEtaDate ? "ETA 경과" : "ETA 없음";
  }
  if (item.status === "needs_check") {
    return "검토필요";
  }
  return "안전";
}

/** ETA를 만들지 못한 행. ETA가 지난 행은 데이터 결측이 아니라 입고 대조 대상이므로 뺀다. */
export function isEtaMissingRow(item: StockGapComputed) {
  return item.status === "waiting_eta" && item.pastEtaDate === null;
}

/**
 * ETA 열 표기. 지난 ETA는 공백 계산에서 빼지만 날짜 자체는 대조에 필요하므로 "(경과)"를 붙여
 * 같은 열에 남긴다. YYYY-MM-DD로 시작해 정렬 순서는 유지된다.
 */
export function stockGapEtaLabel(item: StockGapComputed) {
  if (item.earliestEtaDate) {
    return formatStockGapDate(item.earliestEtaDate);
  }
  if (item.pastEtaDate) {
    return `${formatStockGapDate(item.pastEtaDate)} (경과)`;
  }
  return "-";
}

export function stockGapShortageQty(item: StockGapComputed) {
  return calculateStockGapShortageQty(item);
}

function dateSortValue(value: Date | string | null | undefined, fallback: number) {
  const parsed = value instanceof Date ? value : value ? new Date(value) : null;
  const time = parsed?.getTime();
  return Number.isFinite(time) ? Number(time) : fallback;
}

export function stockGapSortValue(row: StockGapComputed, sortKey: GapSortKey): number | null {
  if (sortKey === "stock") return row.availableQty;
  if (sortKey === "sales") return row.dailySalesQty;
  if (sortKey === "stockout") {
    const value = dateSortValue(row.stockoutDate, Number.NaN);
    return Number.isFinite(value) ? value : null;
  }
  if (sortKey === "eta") {
    const value = dateSortValue(row.earliestEtaDate, Number.NaN);
    return Number.isFinite(value) ? value : null;
  }
  if (sortKey === "gap") return row.gapDays;
  return stockGapShortageQty(row);
}

export function compareStockGapRows(a: StockGapComputed, b: StockGapComputed, sortKey: GapSortKey, direction: SortDirection): number {
  const riskOrder =
    stockGapStatusOrder.indexOf(a.status) - stockGapStatusOrder.indexOf(b.status) ||
    (b.gapDays ?? -1) - (a.gapDays ?? -1) ||
    stockGapShortageQty(b) - stockGapShortageQty(a);

  const aValue = stockGapSortValue(a, sortKey);
  const bValue = stockGapSortValue(b, sortKey);
  if (aValue === null && bValue !== null) return 1;
  if (aValue !== null && bValue === null) return -1;
  if (aValue !== null && bValue !== null && aValue !== bValue) {
    return direction === "desc" ? (aValue < bValue ? 1 : -1) : aValue < bValue ? -1 : 1;
  }
  return riskOrder;
}

export function stockGapReason(item: StockGapComputed) {
  if (item.status === "sufficient") {
    return item.pastEtaDate ? `ETA ${formatStockGapDate(item.pastEtaDate)} 경과 · 입고 확인 필요` : "";
  }
  if (item.status === "waiting_eta") {
    // 과거 ETA만 있는 행은 "ETA 미확인"이 아니라 입고 완료 여부를 대조해야 하는 행이다.
    return item.pastEtaDate
      ? `ETA ${formatStockGapDate(item.pastEtaDate)} 경과 · 입고 확인 필요`
      : "ETA 미확인";
  }
  if (item.status === "stockout_no_inbound") {
    const parts = [`소진 ${formatStockGapDate(item.stockoutDate)}`, "입고 예정 없음"];
    if (item.pastEtaDate) {
      parts.push(`ETA ${formatStockGapDate(item.pastEtaDate)} 경과`);
    }
    parts.push("발주 검토 필요");
    return parts.join(" · ");
  }

  const parts: string[] = [];
  if (item.availableQty === 0) {
    parts.push("현재고 0");
  }
  if (item.stockoutDate) {
    parts.push(`소진 ${formatStockGapDate(item.stockoutDate)}`);
  }
  if (item.earliestEtaDate) {
    parts.push(`ETA ${formatStockGapDate(item.earliestEtaDate)}`);
  } else if (item.pastEtaDate) {
    parts.push(`ETA ${formatStockGapDate(item.pastEtaDate)} 경과`);
  }
  if ((item.gapDays ?? 0) > 0) {
    parts.push(`공백 ${formatNumber(item.gapDays ?? 0)}일`);
  }
  const shortageQty = stockGapShortageQty(item);
  if (shortageQty > 0) {
    parts.push(`부족 ${formatNumber(shortageQty)}개`);
  }

  return parts.slice(0, 4).join(" · ");
}
