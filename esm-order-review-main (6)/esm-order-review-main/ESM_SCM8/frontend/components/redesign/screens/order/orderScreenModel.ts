import { isOrderExcludedRow } from "@/lib/api/mappers";
import { formatNumber } from "@/lib/utils";
import type { OrderReviewRow } from "@/types/api";

export type InboundScenario = "before" | "after";
export type OrderSortKey = "stock" | "sales" | "moi" | "qty" | "amount" | "inbound" | "shipping";
export type SortDirection = "desc" | "asc";
export type OrderTableColumnKey =
  | "productCode"
  | "sku"
  | "brand"
  | "stock"
  | "sales"
  | "moi"
  | "qty"
  | "amount"
  | "inbound"
  | "shipping"
  | "reason"
  | "status";

export const orderTableColumns: Array<{
  key: OrderTableColumnKey;
  label: string;
  defaultWidth: number;
  minWidth: number;
  align?: "left" | "center";
}> = [
  { key: "productCode", label: "상품코드", defaultWidth: 150, minWidth: 120, align: "left" },
  { key: "sku", label: "SKU", defaultWidth: 330, minWidth: 220, align: "left" },
  { key: "brand", label: "브랜드", defaultWidth: 160, minWidth: 120, align: "center" },
  { key: "stock", label: "현지 재고", defaultWidth: 120, minWidth: 100, align: "center" },
  { key: "sales", label: "3개월 판매량", defaultWidth: 140, minWidth: 110, align: "center" },
  { key: "moi", label: "현지 MOI (커버기간)", defaultWidth: 170, minWidth: 150, align: "center" },
  { key: "qty", label: "발주필요수량", defaultWidth: 150, minWidth: 122, align: "center" },
  { key: "amount", label: "발주필요금액", defaultWidth: 150, minWidth: 130, align: "center" },
  { key: "inbound", label: "미입고 수량", defaultWidth: 130, minWidth: 104, align: "center" },
  { key: "shipping", label: "운송중 수량", defaultWidth: 130, minWidth: 104, align: "center" },
  { key: "reason", label: "판단 근거", defaultWidth: 440, minWidth: 260, align: "left" },
  { key: "status", label: "발주 상태", defaultWidth: 100, minWidth: 84, align: "center" }
];

export const sortableOrderColumns: Partial<Record<OrderTableColumnKey, OrderSortKey>> = {
  stock: "stock",
  sales: "sales",
  moi: "moi",
  qty: "qty",
  amount: "amount",
  inbound: "inbound",
  shipping: "shipping"
};

export const orderSortLabels: Record<OrderSortKey, string> = {
  stock: "현지 재고",
  sales: "3개월 판매량",
  moi: "현지 MOI",
  qty: "발주필요수량",
  amount: "발주필요금액",
  inbound: "미입고 수량",
  shipping: "운송중 수량"
};

export function orderMoi(row: OrderReviewRow, scenario: InboundScenario = "before") {
  if (row.monthlyDemand <= 0) {
    return Number.POSITIVE_INFINITY;
  }
  return scenarioStockQty(row, scenario) / row.monthlyDemand;
}

export function formatMoiDisplay(moi: number, stockQty?: number) {
  if (!Number.isFinite(moi)) {
    return stockQty !== undefined && stockQty <= 0 ? "재고 없음" : "판매 없음";
  }

  if (stockQty !== undefined && stockQty <= 0) {
    return `재고 없음 (${formatNumber(moi, 2)}개월)`;
  }

  const coverageDays = moi * 30;
  if (coverageDays < 1) {
    return `<1일 (${formatNumber(moi, 2)}개월)`;
  }
  if (coverageDays < 30) {
    return `${Math.max(1, Math.round(coverageDays))}일 (${formatNumber(moi, 2)}개월)`;
  }
  return `${formatNumber(moi, 1)}개월 (${Math.round(coverageDays)}일)`;
}

// 제외 행은 표시·합계·정렬·엑셀 내보내기가 모두 adjustedOrderQty를 거치므로 여기서 한 번만 막는다.
export const isOrderExcluded = isOrderExcludedRow;

export function adjustedOrderQty(row: OrderReviewRow, scenario: InboundScenario) {
  if (isOrderExcluded(row)) {
    return 0;
  }
  if (scenario === "before") {
    return row.requiredOrderQty;
  }
  return Math.max(row.requiredOrderQty - row.inboundQty, 0);
}

export function displayedInboundQty(row: OrderReviewRow, scenario: InboundScenario) {
  return scenario === "after" ? 0 : row.inboundQty;
}

export function scenarioStockQty(row: OrderReviewRow, scenario: InboundScenario) {
  return scenario === "after" ? row.euAvailableStock + row.inboundQty : row.euAvailableStock;
}

export function orderUnitAmount(row: OrderReviewRow) {
  if (row.requiredOrderQty > 0 && row.requiredOrderAmount > 0) {
    return row.requiredOrderAmount / row.requiredOrderQty;
  }
  return row.unitPrice ?? 0;
}

export function adjustedOrderAmount(row: OrderReviewRow, scenario: InboundScenario) {
  return adjustedOrderQty(row, scenario) * orderUnitAmount(row);
}

export function meaningfulOrderText(value: string | null | undefined) {
  const text = (value ?? "").trim();
  return !text || text === "-" || text === "0" || text === "0.0" || text.toLowerCase() === "nan" ? "" : text;
}

export function compactKrw(value: number) {
  if (value >= 100000000) {
    return "₩ " + formatNumber(value / 100000000, 1) + "억";
  }
  if (value >= 10000) {
    return "₩ " + formatNumber(value / 10000, 0) + "만";
  }
  return "₩ " + formatNumber(value, 0);
}

export function orderStatus(row: OrderReviewRow, scenario: InboundScenario = "before") {
  const moi = orderMoi(row, scenario);
  if (isOrderExcluded(row)) {
    return (row.backendStatus ?? "").trim() === "확인필요" ? "확인필요" : "제외";
  }
  if (adjustedOrderQty(row, scenario) <= 0) {
    return "충분";
  }
  if (moi < 1.5 || row.priorityAction.includes("긴급")) {
    return "긴급";
  }
  return "발주필요";
}

export function orderReason(row: OrderReviewRow, scenario: InboundScenario) {
  if (orderStatus(row, scenario) === "충분") {
    return "";
  }

  const explicitReason = meaningfulOrderText(row.riskReason);
  if (explicitReason) {
    return explicitReason;
  }

  const reasons: string[] = [];
  const moi = orderMoi(row, scenario);
  const orderQty = adjustedOrderQty(row, scenario);
  const stockQty = scenarioStockQty(row, scenario);

  if (stockQty <= 0) {
    reasons.push("현재고 없음");
  }
  if (Number.isFinite(moi)) {
    if (moi < 1.5) {
      reasons.push(`MOI ${formatMoiDisplay(moi, stockQty)}`);
    } else if (moi < 2) {
      reasons.push(`MOI ${formatMoiDisplay(moi, stockQty)} 주의`);
    }
  }
  if (orderQty > 0) {
    reasons.push(`발주 ${formatNumber(orderQty)}개 필요`);
  }
  if (row.recentSalesQty > 0) {
    reasons.push(`3개월 판매 ${formatNumber(row.recentSalesQty)}개`);
  }

  return reasons.slice(0, 3).join(" · ") || orderStatus(row, scenario);
}

export function orderReasonDisplay(row: OrderReviewRow, scenario: InboundScenario) {
  if (orderStatus(row, scenario) === "충분") {
    return { headline: "", detail: "" };
  }

  const source = `${meaningfulOrderText(row.riskReason)} ${meaningfulOrderText(row.priorityAction)}`;
  const moi = orderMoi(row, scenario);
  const orderQty = adjustedOrderQty(row, scenario);
  const stockQty = scenarioStockQty(row, scenario);

  // 제외 행은 재고가 목표에 못 미쳐도 발주 대상이 아니므로 보충 문구 대신 제외 사유를 보여준다.
  if (isOrderExcluded(row)) {
    return {
      headline: meaningfulOrderText(row.riskReason) || "발주 검토 제외",
      detail: Number.isFinite(moi) ? `MOI ${formatMoiDisplay(moi, stockQty)}` : ""
    };
  }
  const lowStockSignal = /OOS|가용재고\s*부족|현재고\s*없음|현지\s*재고\s*부족|현지재고\s*부족/.test(source);
  const targetShortageSignal = /안전재고|목표\s*재고/.test(source) || orderQty > 0;
  const headline =
    stockQty <= 0
      ? "현지 가용재고가 없어 즉시 보충 필요"
      : lowStockSignal || moi < 1.5
        ? "현지 재고가 목표 대비 부족"
        : moi < 2
          ? "현지 MOI가 주의 구간"
          : targetShortageSignal
            ? "목표 재고 대비 부족분 발생"
            : source.split(/[·,]/).map((part) => part.trim()).filter(Boolean)[0] || orderStatus(row, scenario);

  const details: string[] = [];
  if (Number.isFinite(moi)) {
    details.push(`MOI ${formatMoiDisplay(moi, stockQty)}`);
  }
  if (orderQty > 0) {
    details.push(`발주 ${formatNumber(orderQty)}개 필요`);
  }
  if (row.shippingQty > 0) {
    details.push(`운송중 ${formatNumber(row.shippingQty)}개`);
  }
  const inboundQty = displayedInboundQty(row, scenario);
  if (inboundQty > 0) {
    // 미입고 물량의 도착일을 모르면 발주량을 확정하기 어렵다. 수량만 보여주면 곧 들어올
    // 물량으로 오해할 수 있어 도착일 미확인 사실을 함께 붙인다.
    details.push(`미입고 ${formatNumber(inboundQty)}개${row.openPoEtaUnknown ? " (도착일 미확인)" : ""}`);
  }

  return { headline, detail: details.slice(0, 3).join(" · ") };
}

export function orderSortValue(row: OrderReviewRow, scenario: InboundScenario, sortKey: OrderSortKey): number {
  if (sortKey === "stock") return scenarioStockQty(row, scenario);
  if (sortKey === "sales") return row.recentSalesQty;
  if (sortKey === "moi") return orderMoi(row, scenario);
  if (sortKey === "qty") return adjustedOrderQty(row, scenario);
  if (sortKey === "amount") return adjustedOrderAmount(row, scenario);
  if (sortKey === "inbound") return displayedInboundQty(row, scenario);
  return row.shippingQty;
}

export function compareOrderRows(
  a: OrderReviewRow,
  b: OrderReviewRow,
  scenario: InboundScenario,
  sortKey: OrderSortKey,
  direction: SortDirection
): number {
  const aValue = orderSortValue(a, scenario, sortKey);
  const bValue = orderSortValue(b, scenario, sortKey);
  if (aValue !== bValue) {
    return direction === "desc" ? (aValue < bValue ? 1 : -1) : aValue < bValue ? -1 : 1;
  }
  return (
    adjustedOrderAmount(b, scenario) - adjustedOrderAmount(a, scenario) ||
    adjustedOrderQty(b, scenario) - adjustedOrderQty(a, scenario) ||
    a.sku.localeCompare(b.sku, "ko")
  );
}

export function productDisplayName(row: OrderReviewRow) {
  const name = row.productName.trim();
  if (!name || name === "-" || name.includes("상품명 미확인")) {
    return row.sku;
  }
  return name;
}
