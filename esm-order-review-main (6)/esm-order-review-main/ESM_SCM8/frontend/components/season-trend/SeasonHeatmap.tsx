import { monthValue } from "@/lib/data-fields";

export { findKey, monthValue, numberValue, textValue, yearValue } from "@/lib/data-fields";

export type HeatmapRow = {
  category: string;
  months: number[];
  monthCounts: number[];
  total: number;
  rawTotal: number;
  peakMonth: number;
  riseMonth: number;
};

export const MONTHS = Array.from({ length: 12 }, (_, index) => index + 1);

export function monthLabel(month: number) {
  return `${month}월`;
}

export function buildHeatmapRows(
  rows: Array<Record<string, unknown>>,
  {
    getCategory,
    getValue,
    sortRank
  }: {
    getCategory: (row: Record<string, unknown>) => string | null;
    getValue: (row: Record<string, unknown>) => number;
    sortRank?: (category: string) => number;
  }
): HeatmapRow[] {
  const buckets = new Map<string, number[]>();
  const counts = new Map<string, number[]>();

  rows.forEach((row) => {
    const category = getCategory(row);
    if (category === null) {
      return;
    }
    const month = monthValue(row);
    if (!month || month < 1 || month > 12) {
      return;
    }
    const months = buckets.get(category) ?? Array(12).fill(0);
    const monthCounts = counts.get(category) ?? Array(12).fill(0);
    months[month - 1] += getValue(row);
    monthCounts[month - 1] += 1;
    buckets.set(category, months);
    counts.set(category, monthCounts);
  });

  return Array.from(buckets.entries())
    .map(([category, months]) => {
      const monthCounts = counts.get(category) ?? Array(12).fill(0);
      const rawTotal = months.reduce((sum, value) => sum + value, 0);
      const averageMonths = months.map((value, index) => (monthCounts[index] > 0 ? value / monthCounts[index] : 0));
      const activeAverageMonths = averageMonths.filter((_, index) => monthCounts[index] > 0);
      const displayTotal = averageMonths.reduce((sum, value) => sum + value, 0);
      const peakValue = Math.max(...averageMonths);
      const peakMonth = averageMonths.findIndex((value) => value === peakValue) + 1;
      const average =
        activeAverageMonths.length > 0 ? activeAverageMonths.reduce((sum, value) => sum + value, 0) / activeAverageMonths.length : 0;
      const riseIndex = averageMonths.findIndex((value, index) => monthCounts[index] > 0 && average > 0 && value >= average * 1.1);
      return {
        category,
        months: averageMonths,
        monthCounts,
        total: displayTotal,
        rawTotal,
        peakMonth,
        riseMonth: riseIndex >= 0 ? riseIndex + 1 : peakMonth
      };
    })
    .filter((row) => row.rawTotal > 0)
    .sort((a, b) => (sortRank ? sortRank(a.category) - sortRank(b.category) : 0) || b.rawTotal - a.rawTotal);
}
