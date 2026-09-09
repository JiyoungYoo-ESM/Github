export type CountryQuarterGrowthBasis = "yoy" | "qoq";

// 실제 국가별 분포 분석 전까지 기존 성장률 표시 정책과 동일한 임시 기준을 사용한다.
export const QUARTER_LOW_BASE_EUR = 500;
export const COUNTRY_QUARTER_LOW_BASE_EUR = QUARTER_LOW_BASE_EUR;

export function quarterKeyFromMonthKey(monthKey: string) {
  const match = /^(\d{4})-(\d{2})$/.exec(monthKey);
  if (!match) return "";
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (month < 1 || month > 12) return "";
  return `${year}-Q${Math.ceil(month / 3)}`;
}

export function monthsForQuarter(quarterKey: string) {
  const match = /^(\d{4})-Q([1-4])$/.exec(quarterKey);
  if (!match) return [];
  const year = Number(match[1]);
  const quarter = Number(match[2]);
  const firstMonth = (quarter - 1) * 3 + 1;
  return [0, 1, 2].map((offset) => `${year}-${String(firstMonth + offset).padStart(2, "0")}`);
}

export function previousQuarterKey(quarterKey: string) {
  const match = /^(\d{4})-Q([1-4])$/.exec(quarterKey);
  if (!match) return "";
  const year = Number(match[1]);
  const quarter = Number(match[2]);
  return quarter === 1 ? `${year - 1}-Q4` : `${year}-Q${quarter - 1}`;
}

export function previousYearQuarterKey(quarterKey: string) {
  const match = /^(\d{4})-Q([1-4])$/.exec(quarterKey);
  if (!match) return "";
  return `${Number(match[1]) - 1}-Q${match[2]}`;
}

export function formatQuarterLabel(quarterKey: string) {
  const match = /^(\d{4})-Q([1-4])$/.exec(quarterKey);
  return match ? `${match[1]}년 ${match[2]}분기` : "-";
}

export function completeQuarterKeys(completeMonthKeys: Iterable<string>) {
  const monthSet = new Set(completeMonthKeys);
  const candidates = new Set(Array.from(monthSet, quarterKeyFromMonthKey).filter(Boolean));
  return Array.from(candidates)
    .filter((quarter) => monthsForQuarter(quarter).every((month) => monthSet.has(month)))
    .sort();
}

export function comparableQuarterKeys(
  completeQuarters: string[],
  basis: CountryQuarterGrowthBasis
) {
  const quarterSet = new Set(completeQuarters);
  const baseline = basis === "yoy" ? previousYearQuarterKey : previousQuarterKey;
  return completeQuarters.filter((quarter) => quarterSet.has(baseline(quarter)));
}
