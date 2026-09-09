"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Search, X } from "lucide-react";
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

export function SkuChoiceCard({
  title,
  sub,
  growth,
  rank,
  active = false,
  onClick
}: {
  title: string;
  sub: string;
  growth?: string;
  rank?: number;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex min-h-[72px] items-center gap-3 rounded-[12px] border px-4 py-2 text-left shadow-soft",
        active ? "border-brand bg-brand-50" : "border-border bg-surface"
      )}
    >
      {rank ? (
        <span
          className={cn(
            "grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-black",
            active ? "bg-brand text-white" : "bg-row text-muted"
          )}
        >
          {rank}
        </span>
      ) : null}
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-black text-ink">{title}</span>
        <span className="mt-[5px] block truncate text-[12px] font-semibold text-muted2">{sub}</span>
        {growth ? (
          <span className={cn("mt-[3px] block text-[10.5px] font-black", growthBadgeClass(growth))}>
            {growth} 금액 YTD
          </span>
        ) : null}
      </span>
    </button>
  );
}
