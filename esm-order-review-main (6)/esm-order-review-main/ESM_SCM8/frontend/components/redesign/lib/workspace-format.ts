import { useEffect, useState } from "react";
import { displayBrandName } from "../../../lib/brand-display.ts";

export function normalizedBrandIdentity(value: string) {
  return displayBrandName(value).normalize("NFKC").trim().toLowerCase();
}

export function reportBrandRole(value: string): "self" | "competitor" {
  const normalized = normalizedBrandIdentity(value);
  return normalized === "아누아" || normalized === "anua" ? "self" : "competitor";
}

export function koreaDateString(date = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(date);
}

export function addMonthsForDate(date: Date, months: number) {
  const next = new Date(date);
  const day = next.getDate();
  next.setDate(1);
  next.setMonth(next.getMonth() + months);
  next.setDate(Math.min(day, new Date(next.getFullYear(), next.getMonth() + 1, 0).getDate()));
  return next;
}

export function analysisRangeMonthCount(startDate: unknown, endDate: unknown) {
  const start = String(startDate ?? "");
  const end = String(endDate ?? "");
  const startYear = Number(start.slice(0, 4));
  const startMonth = Number(start.slice(5, 7));
  const endYear = Number(end.slice(0, 4));
  const endMonth = Number(end.slice(5, 7));
  if (
    startYear <= 0 ||
    endYear <= 0 ||
    startMonth < 1 ||
    startMonth > 12 ||
    endMonth < 1 ||
    endMonth > 12
  ) {
    return 0;
  }
  return (endYear - startYear) * 12 + endMonth - startMonth + 1;
}

export function analysisPeriodLabel(options: Record<string, unknown> | null | undefined) {
  const start = String(options?.start_date ?? "").trim();
  const end = String(options?.end_date ?? "").trim();
  if (!start || !end) return "분석 기간 미설정";
  return `${start} ~ ${end}`;
}

export function longKoreanDateLabel(value: unknown) {
  const text = String(value ?? "").trim();
  const matched = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!matched) return text || "날짜 미설정";
  return `${Number(matched[1])}년 ${Number(matched[2])}월 ${Number(matched[3])}일`;
}

export function analysisPeriodSentenceLabel(options: Record<string, unknown> | null | undefined) {
  const start = String(options?.start_date ?? "").trim();
  const end = String(options?.end_date ?? "").trim();
  if (!start || !end) return "분석 기간 미설정";
  return `${longKoreanDateLabel(start)} ~ ${longKoreanDateLabel(end)}`;
}

export function analysisPeriodCompactLabel(options: Record<string, unknown> | null | undefined) {
  const start = String(options?.start_date ?? "").trim();
  const end = String(options?.end_date ?? "").trim();
  if (!start || !end) return "기간 미설정";
  return `${start} ~ ${end}`;
}

export function reportAnalysisPeriodParams(options: Record<string, unknown> | null | undefined) {
  const start = String(options?.start_date ?? "").trim();
  const end = String(options?.end_date ?? "").trim();
  if (!start || !end) return {};
  return {
    analysis_start_date: start,
    analysis_end_date: end,
    analysis_period_label: analysisPeriodCompactLabel(options)
  };
}

export function useLoadingDots(active: boolean) {
  const [dotCount, setDotCount] = useState(1);

  useEffect(() => {
    if (!active) {
      setDotCount(1);
      return;
    }
    const interval = window.setInterval(() => {
      setDotCount((count) => (count >= 3 ? 1 : count + 1));
    }, 450);
    return () => window.clearInterval(interval);
  }, [active]);

  return ".".repeat(dotCount);
}

// CMS /eu/sales/local(현지판매) 실데이터는 2024-04-11부터 존재한다(CMS팀 확인).
export const DEMAND_DATA_MIN_DATE = "2024-04-01";
export const MAX_DEMAND_DIRECT_RANGE_MONTHS = 24;
export const MAX_LONG_HISTORY_DIRECT_RANGE_MONTHS = 24;
// 보고서 export 백엔드(ReportExportRequest.blocks max_length=30)와 반드시 일치시킨다.
export const MAX_REPORT_BLOCKS = 30;
export const MAX_REPORT_EXPORT_ID_LENGTH = 160;

export function demandRange(months: number) {
  const end = new Date();
  end.setDate(end.getDate() - 1);
  return {
    startDate: koreaDateString(addMonthsForDate(end, -months)),
    endDate: koreaDateString(end)
  };
}

export function demandYearRange(year: number, minimumDate: string | null = DEMAND_DATA_MIN_DATE) {
  const today = new Date();
  const end = year === today.getFullYear() ? today : new Date(year, 11, 31);
  const start = `${year}-01-01`;
  return {
    startDate: minimumDate && start < minimumDate ? minimumDate : start,
    endDate: koreaDateString(end)
  };
}

export const todayKst = koreaDateString();

export function compactReportExportId(id: string, index: number) {
  if (id.length <= MAX_REPORT_EXPORT_ID_LENGTH) return id;
  let hash = 2166136261;
  for (let i = 0; i < id.length; i += 1) {
    hash ^= id.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  const suffix = Math.abs(hash >>> 0).toString(36);
  return `${id.slice(0, 124)}:${suffix}:${index + 1}`;
}

export function stableShortHash(value: string) {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

export function seasonOptionsFromDates(dates: { startDate: string; endDate: string }) {
  return {
    startDate: dates.startDate,
    endDate: dates.endDate,
    metric: "qty" as const,
    groupBy: "month" as const,
    includeIngredient: false,
    // Keep boundary months in the analytical payload for coverage diagnostics and
    // non-season views. The season calendar itself uses monthCoverage=complete only.
    excludePartialMonths: false
  };
}
