"use client";

import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export function DiagnosticMetricCard({
  label,
  value,
  sub,
  positive = false
}: {
  label: string;
  value: string;
  sub: string;
  positive?: boolean;
}) {
  return (
    <div className="rounded-[12px] border border-border bg-surface px-[20px] py-[19px] shadow-soft">
      <p className="text-[12px] font-semibold text-ink3">{label}</p>
      <p className="mt-[10px] text-[29px] font-black leading-none text-ink">{value}</p>
      <p className={cn("mt-[9px] text-[12px] font-black", positive ? "text-pos" : "text-warn")}>{sub}</p>
    </div>
  );
}

export function SelectPill({ label }: { label: string }) {
  return (
    <button
      type="button"
      className="inline-flex h-[30px] min-w-[72px] items-center justify-between gap-2 rounded-[7px] border border-border bg-surface px-[11px] text-[12px] font-black text-ink3"
    >
      {label}
      <ChevronDown className="h-3 w-3 text-muted2" />
    </button>
  );
}

export function CategorySelectPill({
  value,
  options,
  placeholder,
  onChange,
  disabled = false
}: {
  value: string;
  options: string[];
  placeholder: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <label className="inline-flex h-[30px] w-[160px] max-w-full items-center rounded-[7px] border border-border bg-surface px-[11px] text-[12px] font-black text-ink3">
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        className="w-full appearance-none bg-transparent pr-[18px] outline-none disabled:cursor-not-allowed disabled:text-muted2"
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      <ChevronDown className="-ml-[16px] h-3 w-3 pointer-events-none text-muted2" />
    </label>
  );
}
