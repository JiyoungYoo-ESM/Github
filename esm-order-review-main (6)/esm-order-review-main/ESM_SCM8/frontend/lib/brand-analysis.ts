export type BrandMonthCoverage = {
  month: string;
  status: string;
};

export type SkuConcentrationInput = {
  sku: string;
  name: string;
  category: string;
  amount: number;
  qty: number;
};

export type SkuConcentrationRow<T extends SkuConcentrationInput = SkuConcentrationInput> = T & {
  sharePct: number;
  barWidthPct: number;
};

export type CalendarMonthAveragePoint = {
  month: number;
  amount: number;
  observationCount: number;
};

export type CalendarMonthSharePoint = CalendarMonthAveragePoint & {
  share: number | null;
};

const YEAR_MONTH_PATTERN = /^\d{4}-\d{2}$/;

export function buildTopSkuConcentration<T extends SkuConcentrationInput>(
  items: T[],
  limit = 5,
  wholeBrandAmount?: number
) {
  const sorted = [...items].sort((a, b) => b.amount - a.amount || a.sku.localeCompare(b.sku));
  const itemTotalAmount = sorted.reduce((sum, row) => sum + row.amount, 0);
  const totalAmount = Number.isFinite(wholeBrandAmount) && Number(wholeBrandAmount) >= itemTotalAmount
    ? Number(wholeBrandAmount)
    : itemTotalAmount;
  const topRows = sorted.slice(0, Math.max(0, limit));
  const maxAmount = Math.max(...topRows.map((row) => row.amount), 0);

  const rows: Array<SkuConcentrationRow<T>> = topRows.map((row) => ({
    ...row,
    sharePct: totalAmount > 0 ? (row.amount / totalAmount) * 100 : 0,
    barWidthPct: maxAmount > 0 ? (row.amount / maxAmount) * 100 : 0
  }));

  return {
    totalAmount,
    itemTotalAmount,
    topAmount: rows.reduce((sum, row) => sum + row.amount, 0),
    rows
  };
}

export function completeSeasonalityMonthKeys(
  coverage: BrandMonthCoverage[],
  observedMonthKeys: Iterable<string>
) {
  const complete = new Set(
    coverage
      .filter((item) => item.status === "complete" && YEAR_MONTH_PATTERN.test(item.month))
      .map((item) => item.month)
  );
  if (complete.size > 0) return complete;
  return new Set(Array.from(observedMonthKeys).filter((month) => YEAR_MONTH_PATTERN.test(month)));
}

export function buildCalendarMonthAverageProfile<T>({
  rows,
  calendarMonths,
  eligibleMonthKeys,
  monthKey,
  amount
}: {
  rows: T[];
  calendarMonths: number[];
  eligibleMonthKeys: Iterable<string>;
  monthKey: (row: T) => string;
  amount: (row: T) => number;
}): CalendarMonthAveragePoint[] {
  const eligible = new Set(Array.from(eligibleMonthKeys).filter((key) => YEAR_MONTH_PATTERN.test(key)));
  const coverageByCalendarMonth = new Map<number, number>();
  eligible.forEach((key) => {
    const calendarMonth = Number(key.slice(5, 7));
    if (calendarMonth >= 1 && calendarMonth <= 12) {
      coverageByCalendarMonth.set(calendarMonth, (coverageByCalendarMonth.get(calendarMonth) ?? 0) + 1);
    }
  });

  const amountByCalendarMonth = new Map<number, number>();
  rows.forEach((row) => {
    const key = monthKey(row);
    if (!eligible.has(key)) return;
    const calendarMonth = Number(key.slice(5, 7));
    if (calendarMonth < 1 || calendarMonth > 12) return;
    amountByCalendarMonth.set(calendarMonth, (amountByCalendarMonth.get(calendarMonth) ?? 0) + amount(row));
  });

  return calendarMonths.map((calendarMonth) => {
    const observationCount = coverageByCalendarMonth.get(calendarMonth) ?? 0;
    return {
      month: calendarMonth,
      amount: observationCount > 0 ? (amountByCalendarMonth.get(calendarMonth) ?? 0) / observationCount : 0,
      observationCount
    };
  });
}

export function buildCalendarMonthShareProfile(
  profile: CalendarMonthAveragePoint[]
): CalendarMonthSharePoint[] {
  const observed = profile.filter((row) => row.observationCount > 0);
  const totalAmount = observed.reduce((sum, row) => sum + row.amount, 0);
  return profile.map((row) => ({
    ...row,
    share: row.observationCount > 0 && totalAmount > 0
      ? (row.amount / totalAmount) * 100
      : null
  }));
}
