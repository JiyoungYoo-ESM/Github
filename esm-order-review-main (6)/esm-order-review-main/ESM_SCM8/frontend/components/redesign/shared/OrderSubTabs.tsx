import { cn } from "@/lib/utils";
import type { Screen } from "../lib/types";

export function OrderSubTabs({ active, onNavigate }: { active: "order" | "gap"; onNavigate: (screen: Screen) => void }) {
  const tabs = [
    { id: "order", label: "발주 추천 SKU" },
    { id: "gap", label: "재고 공백" }
  ] as const;

  return (
    <div className="mb-[18px] flex flex-wrap gap-[10px]">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onNavigate(tab.id)}
          className={cn(
            "h-[42px] flex-1 rounded-full border px-3 text-[13px] font-black shadow-soft transition sm:h-[40px] sm:flex-none sm:px-[21px]",
            active === tab.id
              ? "border-warn-border bg-warn-bg text-warn"
              : "border-border bg-surface text-ink hover:border-warn-border hover:text-warn"
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
