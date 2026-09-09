"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export function BrandCardAddButton({ added, ariaLabel, onClick }: { added: boolean; ariaLabel: string; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      title={ariaLabel}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-[8px] border px-3 text-[12px] font-black transition",
        added ? "border-brand bg-brand text-white" : "border-brand bg-surface text-brand hover:bg-brand-50"
      )}
    >
      {added ? <Check className="h-4 w-4" /> : "+"}
      담기
    </button>
  );
}


