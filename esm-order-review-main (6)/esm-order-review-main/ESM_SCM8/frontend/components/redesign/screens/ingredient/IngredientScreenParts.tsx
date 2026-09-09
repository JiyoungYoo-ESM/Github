"use client";

import { cn } from "@/lib/utils";

export function IngredientMetricCard({
  label,
  value,
  sub,
  tone = "default"
}: {
  label: string;
  value: string;
  sub: string;
  tone?: "default" | "warn" | "pos";
}) {
  return (
    <div
      className={cn(
        "rounded-[12px] border px-[20px] py-[18px] shadow-soft",
        tone === "warn"
          ? "border-warn-border bg-warn-bg"
          : tone === "pos"
            ? "border-pos/20 bg-pos-bg"
            : "border-border bg-surface"
      )}
    >
      <p className="text-[12px] font-semibold text-ink3">{label}</p>
      <p className={cn("mt-[9px] text-[25px] font-black leading-none", tone === "warn" ? "text-warn" : tone === "pos" ? "text-pos" : "text-ink")}>
        {value}
      </p>
      <p className="mt-[9px] text-[12px] font-semibold text-muted2">{sub}</p>
    </div>
  );
}

export function IngredientTabButton({
  label,
  active,
  onClick
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "h-[40px] rounded-full border px-[20px] text-[13px] font-black shadow-soft",
        active ? "border-brand bg-surface text-brand" : "border-border bg-surface text-ink3"
      )}
    >
      {label}
    </button>
  );
}
