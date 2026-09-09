import type { OrderReviewRow } from "@/types/api";
import { dispatchStorageEvent, readJsonItem, writeJsonItem } from "@/lib/storage/adapter";

export type ReviewDisposition = "open" | "reviewed" | "held";

export type ReviewWorkflowState = {
  queuedSkus: string[];
  dispositions: Record<string, ReviewDisposition>;
  comments: Record<string, string>;
};

export const ORDER_WORKFLOW_STORAGE_KEY = "esm_scm_order_workflow";
export const ORDER_WORKFLOW_CHANGED_EVENT = "esm_scm_order_workflow_changed";

function emitChanged() {
  dispatchStorageEvent(ORDER_WORKFLOW_CHANGED_EVENT);
}

export function getOrderWorkflowState(): ReviewWorkflowState {
  const parsed = readJsonItem<Partial<ReviewWorkflowState>>("local", ORDER_WORKFLOW_STORAGE_KEY, {});
  return {
    queuedSkus: Array.isArray(parsed.queuedSkus) ? parsed.queuedSkus.filter((sku): sku is string => typeof sku === "string") : [],
    dispositions: parsed.dispositions ?? {},
    comments: parsed.comments ?? {}
  };
}

export function saveOrderWorkflowState(next: ReviewWorkflowState) {
  writeJsonItem("local", ORDER_WORKFLOW_STORAGE_KEY, next);
  emitChanged();
}

export function updateOrderWorkflowState(updater: (state: ReviewWorkflowState) => ReviewWorkflowState) {
  saveOrderWorkflowState(updater(getOrderWorkflowState()));
}

export function addRowsToIntegratedQueue(rows: OrderReviewRow[]) {
  updateOrderWorkflowState((state) => {
    const queued = new Set(state.queuedSkus);
    rows.forEach((row) => queued.add(row.sku));
    return { ...state, queuedSkus: Array.from(queued) };
  });
}

export function setReviewDisposition(skus: string[], disposition: ReviewDisposition) {
  updateOrderWorkflowState((state) => {
    const dispositions = { ...state.dispositions };
    skus.forEach((sku) => {
      dispositions[sku] = disposition;
    });
    return { ...state, dispositions };
  });
}

export function setReviewComment(sku: string, comment: string) {
  updateOrderWorkflowState((state) => ({
    ...state,
    comments: {
      ...state.comments,
      [sku]: comment
    }
  }));
}
