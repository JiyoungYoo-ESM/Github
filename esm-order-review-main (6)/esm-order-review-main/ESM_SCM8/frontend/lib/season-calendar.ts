import {
  amountOf,
  category1Of,
  category2Of,
  monthKeyOf,
  numberValue,
  qtyOf
} from "./global-demand-view-model.ts";

export type SeasonMetricKind = "amount" | "qty";

export type SeasonCalendarRow = {
  group: string;
  parentGroup: string;
  level: "기능1" | "기능2";
  values: number[];
  rawValues: number[];
  metricKind: SeasonMetricKind;
  metricAveraged: boolean;
  peak: string;
  peakMonth: number;
  peakStrength: number;
  skuCount: number;
};

function monthNumberOf(row: Record<string, unknown>) {
  const fromKey = monthKeyOf(row);
  const match = fromKey.match(/(?:^|-)(\d{2})$/);
  if (match) return Number(match[1]);
  const direct = numberValue(row.month ?? row["월"]);
  return direct >= 1 && direct <= 12 ? Math.trunc(direct) : 0;
}

function skuCountOf(row: Record<string, unknown>) {
  return numberValue(row["SKU수"] ?? row.skuCount ?? row.sku_count);
}

function groupParts(row: Record<string, unknown>, level: SeasonCalendarRow["level"]) {
  const category1 = category1Of(row);
  const category2 = category2Of(row);
  if (!category1 || category1 === "미분류") return null;
  return level === "기능2"
    ? { group: category2 || "미분류", parentGroup: category1 }
    : { group: category1, parentGroup: category1 };
}

export function completeSeasonMonthKeys(
  coverage: Array<{ month?: string; status?: string }> | undefined
): Set<string> {
  return new Set(
    (coverage ?? [])
      .filter((item) => item.status === "complete" && /^\d{4}-\d{2}$/.test(String(item.month ?? "")))
      .map((item) => String(item.month))
  );
}

export function seasonPeakDistance(peakMonth: number, currentMonth: number) {
  if (peakMonth < 1 || peakMonth > 12 || currentMonth < 1 || currentMonth > 12) return 0;
  return (peakMonth - currentMonth + 12) % 12;
}

export function daysUntilSeasonMonth(month: number, now = new Date()) {
  if (month < 1 || month > 12) return 0;
  const currentMonth = now.getMonth() + 1;
  if (month === currentMonth) return 0;
  const targetYear = month > currentMonth ? now.getFullYear() : now.getFullYear() + 1;
  const target = new Date(targetYear, month - 1, 1);
  return Math.max(0, Math.ceil((target.getTime() - now.getTime()) / 86_400_000));
}

export function buildSeasonCalendarRows(
  rows: Array<Record<string, unknown>>,
  level: SeasonCalendarRow["level"],
  metricKind: SeasonMetricKind,
  eligibleMonthKeys?: ReadonlySet<string>
): SeasonCalendarRow[] {
  const grouped = new Map<string, { monthly: number[]; skuCounts: number[] }>();
  const observedMonthKeys = new Set<string>();
  const hasEligibilityGate = Boolean(eligibleMonthKeys?.size);

  rows.forEach((row) => {
    const parts = groupParts(row, level);
    const monthKey = monthKeyOf(row);
    const month = monthNumberOf(row);
    if (!parts || month < 1 || month > 12 || (hasEligibilityGate && !eligibleMonthKeys?.has(monthKey))) return;

    if (monthKey) observedMonthKeys.add(monthKey);
    const value = Math.max(0, metricKind === "amount" ? amountOf(row) : qtyOf(row));
    const key = `${parts.parentGroup}\u0000${parts.group}`;
    const current = grouped.get(key) ?? { monthly: Array<number>(12).fill(0), skuCounts: [] as number[] };
    current.monthly[month - 1] += value;
    current.skuCounts.push(skuCountOf(row));
    grouped.set(key, current);
  });

  const denominatorKeys = hasEligibilityGate ? Array.from(eligibleMonthKeys ?? []) : Array.from(observedMonthKeys);
  const coverageByMonth = Array<number>(12).fill(0);
  denominatorKeys.forEach((key) => {
    const match = key.match(/(?:^|-)(\d{2})$/);
    const month = match ? Number(match[1]) : 0;
    if (month >= 1 && month <= 12) coverageByMonth[month - 1] += 1;
  });
  const metricAveraged = coverageByMonth.some((count) => count > 1);

  return Array.from(grouped.entries())
    .map(([key, item]) => {
      const [parentGroup, group] = key.split("\u0000");
      const monthly = item.monthly.map((value, index) =>
        coverageByMonth[index] > 0 ? value / coverageByMonth[index] : 0
      );
      const max = Math.max(...monthly, 0);
      const coveredValues = monthly.filter((_, index) => coverageByMonth[index] > 0);
      const average = coveredValues.length
        ? coveredValues.reduce((sum, value) => sum + value, 0) / coveredValues.length
        : 0;
      const peakIndex = monthly.findIndex((value) => value === max);
      const peakMonth = peakIndex >= 0 ? peakIndex + 1 : 1;
      const peakStrength = average > 0 ? max / average : 1;
      const values = monthly.map((value) => {
        if (max <= 0 || value <= 0) return 2;
        return Math.max(2, Math.min(11, Math.round((value / max) * 10) + 1));
      });
      return {
        group,
        parentGroup,
        level,
        values,
        rawValues: monthly,
        metricKind,
        metricAveraged,
        peak: `${peakMonth}월`,
        peakMonth,
        peakStrength,
        skuCount: Math.max(...item.skuCounts, 0)
      };
    })
    .filter((row) => row.values.some((value) => value > 2))
    .sort((a, b) => b.peakStrength - a.peakStrength);
}
