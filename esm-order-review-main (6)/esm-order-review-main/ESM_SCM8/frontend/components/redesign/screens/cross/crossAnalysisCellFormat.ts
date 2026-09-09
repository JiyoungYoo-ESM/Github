import { formatNumber } from "../../../../lib/utils.ts";
import type { CrossMetric, CrossScale } from "../../../../lib/cross-analysis-matrix.ts";
import { GROWTH_DISPLAY_CAP } from "../../lib/yoy-comparison.ts";
import { krwEokFromEur, formatCrossAmountK } from "../../lib/currency-format.ts";

export function isCrossGrowthMetric(metric: CrossMetric) {
  return metric === "yoy" || metric === "mom";
}

export function formatCrossCellValue(value: number, metric: CrossMetric, scale: CrossScale) {
  if (isCrossGrowthMetric(metric)) {
    return value > GROWTH_DISPLAY_CAP
      ? `>+${formatNumber(GROWTH_DISPLAY_CAP)}%`
      : `${value > 0 ? "+" : ""}${value}%`;
  }
  if (scale === "share") return `${value.toFixed(1)}%`;
  return metric === "quantity" ? `${value.toFixed(1)}만` : formatCrossAmountK(value);
}

// scale이 "share"이거나 metric이 매출액이 아니면 원화 참고값을 만들지 않는다(마스킹 계정이 amount 값을 우회 노출받지 않도록).
export function formatCrossCellKrw(value: number, metric: CrossMetric, scale: CrossScale, eurKrwRate?: number | null) {
  if (isCrossGrowthMetric(metric)) return "";
  if (scale !== "amount" || metric !== "sales") return "";
  return krwEokFromEur(value * 1_000, eurKrwRate);
}
