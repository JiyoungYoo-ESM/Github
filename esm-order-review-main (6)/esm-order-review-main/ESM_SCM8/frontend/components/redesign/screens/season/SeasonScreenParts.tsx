"use client";

import { cn, formatNumber } from "@/lib/utils";
import type { SeasonCalendarRow } from "@/lib/season-calendar";
import { krwEokFromEur, wonEok } from "../../lib/currency-format";
import { useUserPermissions } from "@/lib/use-user-permissions";

export function SeasonMetricCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-[12px] border border-border bg-surface px-[18px] py-[18px] shadow-soft">
      <p className="text-[12px] font-semibold text-ink3">{label}</p>
      <p className="mt-[8px] text-[24px] font-black leading-none text-ink">{value}</p>
      <p className="mt-[9px] text-[12px] font-semibold text-muted2">{sub}</p>
    </div>
  );
}

export function SeasonDemandCell({
  value,
  raw,
  peakRaw,
  month,
  metricKind,
  averaged = false,
  eurKrwRate,
  peak = false
}: {
  value: number;
  raw: number;
  peakRaw: number;
  month: number;
  metricKind: SeasonCalendarRow["metricKind"];
  averaged?: boolean;
  eurKrwRate?: number | null;
  peak?: boolean;
}) {
  const { canViewAmountData } = useUserPermissions();
  const opacity =
    value >= 10 ? "bg-brand" : value >= 8 ? "bg-brand/80" : value >= 6 ? "bg-brand/60" : "bg-brand/35";
  const pctOfPeak = peakRaw > 0 && raw > 0 ? (raw / peakRaw) * 100 : 0;
  const headLabel = peak
    ? `${month}월 · 피크월`
    : raw > 0
      ? `${month}월 · 피크월 대비 ${formatNumber(pctOfPeak, pctOfPeak >= 10 ? 0 : 1)}%`
      : `${month}월`;
  const krwLabel = canViewAmountData && metricKind === "amount" && raw > 0 ? krwEokFromEur(raw, eurKrwRate) : "";
  const metricName = metricKind === "amount" ? (averaged ? "월평균 매출" : "매출") : averaged ? "월평균 판매량" : "판매량";
  const rawLabel =
    raw <= 0
      ? "해당 월 실적 없음"
      : metricKind === "amount" && canViewAmountData
        ? `${metricName} ${wonEok(raw)}${krwLabel ? ` · ${krwLabel}` : ""}`
        : metricKind === "amount"
          ? `매출 비중 ${formatNumber(pctOfPeak, pctOfPeak >= 10 ? 0 : 1)}%`
          : `${metricName} ${formatNumber(raw, raw >= 100 ? 0 : 1)}`;

  return (
    <div
      className="group/cell relative outline-none"
      tabIndex={0}
      role="img"
      aria-label={`${headLabel} · ${rawLabel}`}
    >
      <div
        className={cn(
          "h-[34px] rounded-[6px] transition group-hover/cell:ring-2 group-hover/cell:ring-ink/25 group-focus-within/cell:ring-2 group-focus-within/cell:ring-ink/40",
          opacity,
          peak ? "border-[2px] border-ink shadow-card" : "border border-transparent"
        )}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-[6px] -translate-x-1/2 whitespace-nowrap rounded-[8px] bg-ink px-[10px] py-[7px] text-center opacity-0 shadow-panel transition group-hover/cell:opacity-100 group-focus-within/cell:opacity-100"
      >
        <p className="text-[11px] font-black leading-none text-white">{headLabel}</p>
        <p className="mt-[5px] text-[11px] font-semibold leading-none text-white/70">{rawLabel}</p>
      </div>
    </div>
  );
}
