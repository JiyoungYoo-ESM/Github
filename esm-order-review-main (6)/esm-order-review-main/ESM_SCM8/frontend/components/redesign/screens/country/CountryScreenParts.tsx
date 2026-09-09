"use client";

import { cn } from "@/lib/utils";
import { growthBadgeClass } from "../../lib/yoy-comparison";

export function ShareCard({
  region,
  percent,
  amount,
  countries,
  selected = false,
  onSelect
}: {
  region: string;
  percent: string;
  amount?: string;
  countries: string;
  selected?: boolean;
  onSelect?: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect?.();
        }
      }}
      className={cn(
        "relative min-w-[260px] cursor-pointer rounded-[12px] border bg-surface px-4 py-[15px] text-left transition",
        selected ? "border-brand shadow-card" : "border-border hover:border-brand/40"
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] font-black text-ink">{region}</p>
        <p className="text-[18px] font-black leading-none text-brand">{percent}</p>
      </div>
      <div className="mt-[12px] h-[6px] overflow-hidden rounded-full bg-row">
        <div className="h-full rounded-full bg-brand" style={{ width: percent }} />
      </div>
      <div className="mt-[10px] flex items-center justify-between text-[12px] font-semibold text-muted2">
        {amount ? <span>{amount}</span> : <span>점유율 기준</span>}
        <span>{countries}</span>
      </div>
    </div>
  );
}

export function CountryRankRow({
  rank,
  country,
  region,
  share,
  amount,
  growth,
  growthLabel,
  secondaryGrowth,
  secondaryGrowthLabel,
  width,
  active,
  onSelect
}: {
  rank: number;
  country: string;
  region: string;
  share: string;
  amount?: string;
  growth?: string | null;
  growthLabel?: string;
  secondaryGrowth?: string | null;
  secondaryGrowthLabel?: string;
  width: string;
  active?: boolean;
  onSelect?: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect?.();
        }
      }}
      className={cn(
        "grid w-full cursor-pointer grid-cols-[34px_minmax(0,1fr)_122px] items-center gap-3 border-b border-rowline px-4 py-[13px] text-left last:border-b-0 hover:bg-surface-soft",
        active && "border-l-[3px] border-l-brand bg-brand-50/60"
      )}
    >
      <div className={cn("text-[13px] font-black", active ? "text-brand" : "text-muted2")}>{rank}</div>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <p className="min-w-[72px] text-[14px] font-black text-ink">{country}</p>
          <span className="rounded-[6px] border border-border bg-surface px-2 py-[1px] text-[11px] font-bold text-muted2">{region}</span>
        </div>
        <div className="mt-[9px] h-[5px] overflow-hidden rounded-full bg-row">
          <div className="h-full rounded-full bg-brand" style={{ width }} />
        </div>
      </div>
      <div className="text-right">
        <p className="text-[14px] font-black leading-none text-ink">{share}</p>
        {amount ? <p className="mt-[3px] whitespace-nowrap text-[12px] font-bold text-muted2">{amount}</p> : null}
        {growth ? <p className={cn("mt-[3px] whitespace-nowrap text-[12px] font-black", growthBadgeClass(growth))}>{growthLabel ? `${growth} ${growthLabel}` : growth}</p> : null}
        {secondaryGrowth ? (
          <p className={cn("mt-[2px] whitespace-nowrap text-[11px] font-black", growthBadgeClass(secondaryGrowth))}>
            {secondaryGrowthLabel ? `${secondaryGrowth} ${secondaryGrowthLabel}` : secondaryGrowth}
          </p>
        ) : null}
      </div>
    </div>
  );
}
