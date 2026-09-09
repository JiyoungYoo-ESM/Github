import type { OrderV3DecisionState, OrderV3Row } from "./types";

export type OrderV3ReviewView = "needed" | "not-needed" | "excluded" | "unknown";

// Use the API's original result, not the quantity edited during review.
// This only selects a display list; it does not calculate order quantities.
export function reviewViewOf(row: Pick<OrderV3Row, "calculable" | "signal">): OrderV3ReviewView {
  if (row.calculable === false) return "excluded";
  if (row.signal === "발주 제외") return "not-needed";
  if (row.signal === "즉시 발주") return "needed";
  return "unknown";
}

export function reviewActionLabel(row: OrderV3Row, decision?: OrderV3DecisionState): string {
  const view = reviewViewOf(row);
  if (view === "excluded") return "사유보기";
  if (row.inventoryWarnings?.length && (!decision || decision.decision === "미검토")) return "재고확인";
  if (view === "not-needed") return "검토하기";
  if (view !== "needed") return "상세보기";
  return !decision || decision.decision === "미검토" ? "검토하기" : decision.decision;
}

export function reviewProgress(rows: OrderV3Row[], decisions: Record<string, OrderV3DecisionState>) {
  const neededRows = rows.filter((row) => reviewViewOf(row) === "needed");
  return {
    total: neededRows.length,
    completed: neededRows.filter((row) => {
      const decision = decisions[row.sku]?.decision;
      return decision !== undefined && decision !== "미검토";
    }).length
  };
}

export function displayOrderQuantity(row: OrderV3Row, decision?: OrderV3DecisionState): number {
  return reviewViewOf(row) === "needed" ? decision?.finalQty ?? row.finalOrderQty : row.finalOrderQty;
}

export function exclusionReasonKey(row: Pick<OrderV3Row, "dataStatus" | "validationCode" | "validationError">) {
  // Missing class-1 fallback and missing class-1/2 profiles share an API code,
  // but their explanations must remain separate in the reason filter.
  const key = [row.dataStatus, row.validationCode || row.validationError || "unknown"];
  if (row.validationCode === "SEASON_FACTOR_MISSING") key.push(row.validationError || "");
  return JSON.stringify(key);
}

export function filterReviewRows(
  rows: OrderV3Row[],
  options: {
    view: OrderV3ReviewView;
    brand?: string;
    query?: string;
    reviewDecision?: string;
    exclusionReason?: string;
  },
  decisions: Record<string, OrderV3DecisionState>
): OrderV3Row[] {
  const { view, brand = "all", query = "", reviewDecision = "all", exclusionReason = "all" } = options;
  const normalizedQuery = query.trim().toLowerCase();
  return rows.filter((row) => {
    if (reviewViewOf(row) !== view) return false;
    if (view === "excluded" && exclusionReason !== "all" && exclusionReasonKey(row) !== exclusionReason) return false;
    if (brand !== "all" && row.brand !== brand) return false;
    if (view === "needed" && reviewDecision !== "all" && (decisions[row.sku]?.decision ?? "미검토") !== reviewDecision) return false;
    return !normalizedQuery || `${row.sku} ${row.productName} ${row.brand}`.toLowerCase().includes(normalizedQuery);
  }).sort((left, right) => right.orderAmountKrw - left.orderAmountKrw);
}

export function reviewExportRows(rows: OrderV3Row[], selectedSkus: Set<string>): OrderV3Row[] {
  return rows.filter((row) => row.calculable !== false && (!selectedSkus.size || selectedSkus.has(row.sku)));
}

// The companion sheet follows brand/search, not the calculable-only review list.
// Selection and reason filters apply when exporting the exclusions view itself.
export function attentionExportRows(
  rows: OrderV3Row[],
  options: { view: OrderV3ReviewView; brand?: string; query?: string; exclusionReason?: string },
  selectedSkus: Set<string>
): OrderV3Row[] {
  return filterReviewRows(rows, {
    view: "excluded", brand: options.brand, query: options.query,
    exclusionReason: options.view === "excluded" ? options.exclusionReason : "all"
  }, {}).filter(row => options.view !== "excluded" || !selectedSkus.size || selectedSkus.has(row.sku));
}
