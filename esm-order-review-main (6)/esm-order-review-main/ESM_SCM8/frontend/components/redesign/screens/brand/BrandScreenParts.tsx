"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { growthBadgeClass } from "../../lib/yoy-comparison";

export type SkuSearchOption = {
  value: string;
  name: string;
  code: string;
};

export function SkuSearchSelect({
  value,
  options,
  onChange,
  disabled = false
}: {
  value: string;
  options: SkuSearchOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const selectedOption = options.find((option) => option.value === value);
  const filteredOptions = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("ko");
    if (!normalizedQuery) return options;
    return options.filter((option) => `${option.name} ${option.code}`.toLocaleLowerCase("ko").includes(normalizedQuery));
  }, [options, query]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open]);

  const selectSku = (sku: string) => {
    onChange(sku);
    setQuery("");
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative min-w-0" onKeyDown={(event) => event.key === "Escape" && setOpen(false)}>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => {
          setQuery("");
          setOpen((current) => !current);
        }}
        className="inline-flex h-[42px] w-full min-w-0 items-center justify-between gap-2 rounded-[10px] border border-border bg-surface-soft px-3 text-left text-[13px] font-black text-ink outline-none transition hover:border-brand focus:border-brand disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span className="truncate">{disabled ? "선택 가능한 SKU가 없습니다" : selectedOption ? `${selectedOption.name} · ${selectedOption.code}` : "-"}</span>
        <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted transition", open && "rotate-180")} />
      </button>
      {open && !disabled ? (
        <div className="absolute left-0 right-0 top-11 z-40 overflow-hidden rounded-[12px] border border-border bg-surface shadow-soft">
          <div className="border-b border-divider p-2.5">
            <div className="flex h-9 items-center gap-2 rounded-[9px] border border-border bg-surface-soft px-3 focus-within:border-brand/40 focus-within:bg-surface">
              <Search className="h-4 w-4 shrink-0 text-muted2" />
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="상품명 또는 SKU 코드 검색"
                aria-label="SKU 검색"
                className="min-w-0 flex-1 bg-transparent text-[12.5px] font-bold text-ink outline-none placeholder:text-muted2"
              />
              {query ? (
                <button type="button" onClick={() => setQuery("")} aria-label="SKU 검색어 지우기" className="text-muted2 hover:text-ink">
                  <X className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </div>
          </div>
          <div role="listbox" aria-label="SKU 선택" className="max-h-[320px] overflow-y-auto py-1">
            {!query ? (
              <button
                type="button"
                role="option"
                aria-selected={!value}
                onClick={() => selectSku("")}
                className={cn(
                  "block w-full px-4 py-2.5 text-left text-[13px] font-black hover:bg-surface-soft",
                  !value ? "text-brand" : "text-ink"
                )}
              >
                -
              </button>
            ) : null}
            {filteredOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={value === option.value}
                onClick={() => selectSku(option.value)}
                className={cn(
                  "grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-2.5 text-left hover:bg-surface-soft",
                  value === option.value ? "text-brand" : "text-ink"
                )}
              >
                <span className="truncate text-[13px] font-black">{option.name}</span>
                <span className="text-[11.5px] font-bold text-muted2">{option.code}</span>
              </button>
            ))}
            {filteredOptions.length === 0 ? <p className="px-4 py-7 text-center text-[12.5px] font-bold text-muted">검색 결과가 없습니다.</p> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function BrandRankRow({
  rank,
  name,
  sales,
  salesSub,
  share,
  growth,
  growthLabel,
  secondaryGrowth,
  secondaryGrowthLabel,
  width,
  added = false,
  active = false,
  onAdd,
  onClick
}: {
  rank: string;
  name: string;
  sales: string;
  salesSub?: string;
  share?: string;
  growth?: string | null;
  growthLabel?: string;
  secondaryGrowth?: string | null;
  secondaryGrowthLabel?: string;
  width: string;
  added?: boolean;
  active?: boolean;
  onAdd?: () => void;
  onClick?: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onClick?.();
        }
      }}
      className={cn(
        "grid min-h-[56px] cursor-pointer items-center gap-3 border-b border-rowline px-[18px] last:border-b-0 hover:bg-surface-soft",
        onAdd ? "grid-cols-[34px_minmax(0,1fr)_150px_38px]" : "grid-cols-[34px_minmax(0,1fr)_150px]",
        active ? "border-l-[3px] border-l-brand bg-brand-50 pl-[15px]" : ""
      )}
    >
      <span className={cn("text-[13px] font-black", Number(rank) <= 3 ? "text-brand" : "text-muted2")}>{rank}</span>
      <div className="min-w-0">
        <p className="truncate text-[13px] font-black text-ink">{name}</p>
        <div className="mt-[9px] h-[5px] overflow-hidden rounded-full bg-row">
          <div className={cn("h-full rounded-full", active ? "bg-brand" : "bg-slatebar")} style={{ width }} />
        </div>
      </div>
      <div className="text-right">
        <p className="text-[13px] font-black text-ink">{sales}</p>
        {salesSub ? <p className="mt-[2px] text-[11px] font-black text-muted2">{salesSub}</p> : null}
        {share ? <p className="mt-[2px] text-[11px] font-black text-muted2">{share}</p> : null}
        {growth ? <p className={cn("mt-[2px] whitespace-nowrap text-[11px] font-black", growthBadgeClass(growth))}>{growthLabel ? `${growth} ${growthLabel}` : growth}</p> : null}
        {secondaryGrowth ? (
          <p className={cn("mt-[2px] whitespace-nowrap text-[11px] font-black", growthBadgeClass(secondaryGrowth))}>
            {secondaryGrowthLabel ? `${secondaryGrowth} ${secondaryGrowthLabel}` : secondaryGrowth}
          </p>
        ) : null}
      </div>
      {onAdd ? (
        <button
          type="button"
          aria-label={`${name} 리포트에 담기`}
          title={`${name} 리포트에 담기`}
          onClick={(event) => {
            event.stopPropagation();
            onAdd();
          }}
          className={cn(
            "ml-auto grid h-[30px] w-[30px] place-items-center rounded-[8px] border text-[16px] font-black leading-none transition",
            added ? "border-brand bg-brand text-white" : "border-border bg-surface text-brand hover:border-brand"
          )}
        >
          {added ? <Check className="h-4 w-4" /> : "+"}
        </button>
      ) : null}
    </div>
  );
}

export function BrandMetricBox({
  label,
  value,
  sub,
  subTone = "muted"
}: {
  label: string;
  value: string;
  sub?: string;
  subTone?: "brand" | "pos" | "muted";
}) {
  const subParts = splitMetricSubText(sub);
  return (
    <div className="min-w-0 overflow-hidden border-l border-divider px-[18px] py-[16px] first:border-l-0">
      <p className="text-[12px] font-semibold text-muted2">{label}</p>
      <p className="mt-[8px] whitespace-nowrap text-[18px] font-black leading-none text-ink">{value}</p>
      {subParts ? (
        <p
          className={cn(
            "mt-[6px] max-w-full text-[10.5px] font-black leading-[1.25]",
            subTone === "pos" ? "text-pos" : subTone === "brand" ? "text-brand" : "text-muted2"
          )}
        >
          <span className="block whitespace-nowrap">{subParts.value}</span>
          {subParts.context ? <span className="block whitespace-normal break-keep">{subParts.context}</span> : null}
        </p>
      ) : null}
    </div>
  );
}

function splitMetricSubText(sub?: string) {
  if (!sub) return null;
  const match = sub.match(/^([^\s(]+)\s*(\(.+\))$/);
  if (!match) return { value: sub, context: "" };
  return { value: match[1], context: match[2] };
}

export function BrandStatusPill({ label, tone }: { label: string; tone: "pos" | "muted" | "brand" }) {
  return (
    <span
      className={cn(
        "inline-flex h-[22px] items-center rounded-full px-[10px] text-[11px] font-black",
        tone === "pos" ? "bg-pos/10 text-pos" : tone === "brand" ? "bg-brand-50 text-brand" : "bg-row text-ink3"
      )}
    >
      {label}
    </span>
  );
}


