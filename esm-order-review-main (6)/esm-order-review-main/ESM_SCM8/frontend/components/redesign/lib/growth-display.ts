import { GROWTH_DISPLAY_CAP } from "./yoy-comparison";

export function growthPercentValue(value: string): number | null {
  if (value === "10배 이상 증가") return GROWTH_DISPLAY_CAP + 1;
  const match = value.replace(/,/g, "").match(/[+-]?\d+(?:\.\d+)?/);
  if (!match) return null;
  const numeric = Number(match[0]);
  return Number.isFinite(numeric) ? numeric : null;
}
