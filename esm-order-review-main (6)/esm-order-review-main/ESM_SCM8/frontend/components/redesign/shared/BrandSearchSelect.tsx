"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

export function BrandSearchSelect({
  value,
  options,
  allValue,
  onChange,
  allLabel = "전체",
  getOptionLabel = (option) => option,
  fullWidth = false,
  responsiveFullWidth = false,
  dropdownAlign = "right",
  disabled = false,
  buttonLabel,
  buttonClassName,
  searchPlaceholder = "브랜드 검색",
  testId
}: {
  value: string;
  options: string[];
  allValue?: string;
  onChange: (value: string) => void;
  allLabel?: string;
  getOptionLabel?: (option: string) => string;
  fullWidth?: boolean;
  responsiveFullWidth?: boolean;
  dropdownAlign?: "left" | "right" | "responsive";
  disabled?: boolean;
  buttonLabel?: string;
  buttonClassName?: string;
  searchPlaceholder?: string;
  testId?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const filteredOptions = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("ko");
    if (!normalizedQuery) return options;
    return options.filter((brand) =>
      `${getOptionLabel(brand)} ${brand}`.toLocaleLowerCase("ko").includes(normalizedQuery)
    );
  }, [getOptionLabel, options, query]);

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open]);

  const selectBrand = (brand: string) => {
    onChange(brand);
    setQuery("");
    setOpen(false);
  };

  return (
    <div ref={rootRef} className={cn("relative", responsiveFullWidth && "w-full sm:w-auto")} onKeyDown={(event) => event.key === "Escape" && setOpen(false)}>
      <button
        type="button"
        data-testid={testId}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => {
          setQuery("");
          setOpen((current) => !current);
        }}
        className={cn(
          "inline-flex items-center justify-between gap-2 rounded-[10px] border border-border px-4 text-[13px] font-black text-ink disabled:cursor-not-allowed disabled:opacity-50",
          fullWidth ? "h-[42px] w-full bg-surface-soft" : "h-[38px] min-w-[120px] max-w-[210px] bg-surface",
          responsiveFullWidth && "w-full sm:w-auto",
          buttonClassName
        )}
      >
        <span className="truncate">{buttonLabel ?? (allValue !== undefined && value === allValue ? allLabel : getOptionLabel(value))}</span>
        <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted transition", open && "rotate-180")} />
      </button>
      {open ? (
        <div className={cn(
          "absolute top-11 z-40 w-[280px] overflow-hidden rounded-[12px] border border-border bg-surface shadow-soft",
          responsiveFullWidth && "w-full sm:w-[280px]",
          dropdownAlign === "responsive" ? "left-0 lg:left-auto lg:right-0" : dropdownAlign === "left" ? "left-0" : "right-0"
        )}>
          <div className="border-b border-divider p-2.5">
            <div className="flex h-9 items-center gap-2 rounded-[9px] border border-border bg-surface-soft px-3 focus-within:border-brand/40 focus-within:bg-surface">
              <Search className="h-4 w-4 shrink-0 text-muted2" />
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={searchPlaceholder}
                aria-label={searchPlaceholder}
                className="min-w-0 flex-1 bg-transparent text-[12.5px] font-bold text-ink outline-none placeholder:text-muted2"
              />
              {query ? (
                <button type="button" onClick={() => setQuery("")} aria-label="브랜드 검색어 지우기" className="text-muted2 hover:text-ink">
                  <X className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </div>
          </div>
          <div role="listbox" aria-label="브랜드 선택" className="max-h-[260px] overflow-y-auto py-1">
            {!query && allValue !== undefined ? (
              <button
                type="button"
                role="option"
                aria-selected={value === allValue}
                onClick={() => selectBrand(allValue)}
                className={cn(
                  "block w-full px-4 py-2.5 text-left text-[13px] font-black hover:bg-surface-soft",
                  value === allValue ? "text-brand" : "text-ink"
                )}
              >
                {allLabel}
              </button>
            ) : null}
            {filteredOptions.map((brand) => (
              <button
                key={brand}
                type="button"
                role="option"
                aria-selected={value === brand}
                onClick={() => selectBrand(brand)}
                className={cn(
                  "block w-full px-4 py-2.5 text-left text-[13px] font-black hover:bg-surface-soft",
                  value === brand ? "text-brand" : "text-ink"
                )}
              >
                {getOptionLabel(brand)}
              </button>
            ))}
            {filteredOptions.length === 0 ? (
              <p className="px-4 py-6 text-center text-[12.5px] font-bold text-muted">검색 결과가 없습니다.</p>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
