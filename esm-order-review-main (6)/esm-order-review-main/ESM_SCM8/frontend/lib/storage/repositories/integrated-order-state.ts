import { readJsonItem, writeJsonItem } from "@/lib/storage/adapter";

const INTEGRATED_STATE_KEY = "esm_scm_integrated_order_state";

export type IntegratedOrderState<TStatus extends string> = {
  statusMap: Record<string, TStatus>;
  finalQtyMap: Record<string, number>;
};

export function readIntegratedOrderState<TStatus extends string>(): IntegratedOrderState<TStatus> {
  const parsed = readJsonItem<Partial<IntegratedOrderState<TStatus>>>("local", INTEGRATED_STATE_KEY, {});
  return {
    statusMap: parsed.statusMap ?? {},
    finalQtyMap: parsed.finalQtyMap ?? {}
  };
}

export function writeIntegratedOrderState<TStatus extends string>(state: IntegratedOrderState<TStatus>): void {
  writeJsonItem("local", INTEGRATED_STATE_KEY, state);
}
