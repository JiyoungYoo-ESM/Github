import { dispatchStorageEvent, readJsonItem, writeJsonItem } from "@/lib/storage/adapter";

export type SeasonOrderItem = {
  sku: string;
  productName: string;
  brand: string;
  category: string;
  peakMonth: number;
};

const QUEUE_KEY = "esm_scm_season_order_queue";
const CHANGE_EVENT = "esm_scm_season_queue_changed";

export function getSeasonOrderQueue(): SeasonOrderItem[] {
  return readJsonItem<SeasonOrderItem[]>("local", QUEUE_KEY, []);
}

export function addToSeasonOrderQueue(item: SeasonOrderItem): void {
  const queue = getSeasonOrderQueue();
  if (queue.some((i) => i.sku === item.sku)) return;
  queue.push(item);
  writeJsonItem("local", QUEUE_KEY, queue);
  dispatchStorageEvent(CHANGE_EVENT);
}

export function removeFromSeasonOrderQueue(sku: string): void {
  const queue = getSeasonOrderQueue().filter((i) => i.sku !== sku);
  writeJsonItem("local", QUEUE_KEY, queue);
  dispatchStorageEvent(CHANGE_EVENT);
}

export function isInSeasonOrderQueue(sku: string): boolean {
  return getSeasonOrderQueue().some((i) => i.sku === sku);
}

export { CHANGE_EVENT as SEASON_QUEUE_CHANGE_EVENT };
