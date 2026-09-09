"use client";

import { ChevronDown, ChevronUp } from "lucide-react";

export function FieldBox({
  label,
  value,
  caption,
  onChange,
  step = 1,
  min = 0
}: {
  label: string;
  value: string;
  caption?: string;
  onChange?: (value: string) => void;
  step?: number;
  min?: number;
}) {
  const editable = Boolean(onChange);
  const adjustValue = (direction: 1 | -1) => {
    if (!onChange) return;
    const currentValue = Number(value);
    const baseValue = Number.isFinite(currentValue) ? currentValue : min;
    const decimalPlaces = String(step).split(".")[1]?.length ?? 0;
    const nextValue = Math.max(min, baseValue + direction * step);
    onChange(String(Number(nextValue.toFixed(decimalPlaces))));
  };

  return (
    <div className="block">
      <span className="mb-2 block text-[12px] font-black text-ink3">{label}</span>
      <div className="relative">
        <input
          aria-label={label}
          type={editable ? "number" : "text"}
          value={value}
          readOnly={!editable}
          aria-readonly={!editable}
          onChange={(event) => onChange?.(event.target.value)}
          inputMode={editable ? "decimal" : undefined}
          step={editable ? step : undefined}
          min={editable ? min : undefined}
          className={`h-[43px] w-full rounded-[10px] border px-[14px] text-[15px] font-black outline-none ${
            editable
              ? "appearance-none border-border bg-surface pr-10 text-ink focus:border-brand [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
              : "cursor-not-allowed border-border bg-slate-100 text-muted"
          }`}
        />
        {editable ? (
          <div className="absolute bottom-px right-px top-px flex w-7 flex-col overflow-hidden rounded-r-[9px] border-l border-border bg-slate-50">
            <button
              type="button"
              aria-label={`${label} 증가`}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => adjustValue(1)}
              className="flex flex-1 items-center justify-center border-b border-border text-muted transition-colors hover:bg-brand-50 hover:text-brand focus-visible:bg-brand-50 focus-visible:text-brand focus-visible:outline-none"
            >
              <ChevronUp className="h-2.5 w-2.5" strokeWidth={2.25} />
            </button>
            <button
              type="button"
              aria-label={`${label} 감소`}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => adjustValue(-1)}
              disabled={Number(value) <= min}
              className="flex flex-1 items-center justify-center text-muted transition-colors hover:bg-brand-50 hover:text-brand focus-visible:bg-brand-50 focus-visible:text-brand focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-35"
            >
              <ChevronDown className="h-2.5 w-2.5" strokeWidth={2.25} />
            </button>
          </div>
        ) : null}
      </div>
      {caption ? <span className="mt-2 block text-[11.5px] font-semibold text-muted2">{caption}</span> : null}
    </div>
  );
}
