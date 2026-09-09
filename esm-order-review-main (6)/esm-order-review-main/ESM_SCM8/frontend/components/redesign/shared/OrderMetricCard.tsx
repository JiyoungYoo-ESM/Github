import { cn } from "@/lib/utils";

export function OrderMetricCard({
  label,
  value,
  accent,
  sub,
  subTone = "brand"
}: {
  label: string;
  value: string;
  accent?: boolean;
  sub?: string;
  subTone?: "brand" | "pos" | "muted";
}) {
  return (
    <div className="rounded-[14px] border border-border bg-surface px-5 py-[18px] shadow-card">
      <p className="text-[12.5px] font-semibold text-muted">{label}</p>
      <p className={cn("mt-[10px] text-[28px] font-black leading-none tracking-normal", accent ? "text-brand" : "text-ink")}>
        {value}
      </p>
      {sub ? <p className={cn("mt-[8px] text-[12px] font-black", subTone === "pos" ? "text-pos" : subTone === "muted" ? "text-muted2" : "text-brand")}>{sub}</p> : null}
    </div>
  );
}
