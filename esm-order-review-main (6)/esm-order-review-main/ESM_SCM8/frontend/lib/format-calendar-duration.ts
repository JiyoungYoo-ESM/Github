export const CALENDAR_WEEK_DAYS = 7;
export const V3_PERIOD_DAYS = 7;

type CalendarDurationOptions = {
  showWeeks?: boolean;
  showV3Periods?: boolean;
  maximumFractionDigits?: number;
};

function formatNumber(value: number, maximumFractionDigits: number) {
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits }).format(value);
}

/**
 * Calendar-day is the display base.  Week and V3 period values are derived
 * annotations only; callers must keep their demand-statistics grain intact.
 */
export function formatCalendarDuration(
  days: number | null | undefined,
  {
    showWeeks = false,
    showV3Periods = false,
    maximumFractionDigits = 2
  }: CalendarDurationOptions = {}
) {
  if (days == null || !Number.isFinite(days)) return "확인 필요";

  const details: string[] = [];
  if (showWeeks) {
    details.push(`${formatNumber(days / CALENDAR_WEEK_DAYS, maximumFractionDigits)}주`);
  }
  if (showV3Periods) {
    details.push(`${formatNumber(days / V3_PERIOD_DAYS, maximumFractionDigits)}기`);
  }

  const primary = `${formatNumber(days, maximumFractionDigits)}일`;
  return details.length ? `${primary} (${details.join(" / ")})` : primary;
}
