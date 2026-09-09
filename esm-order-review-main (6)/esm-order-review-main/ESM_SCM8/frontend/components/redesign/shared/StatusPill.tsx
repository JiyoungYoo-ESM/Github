import { cn } from "@/lib/utils";

export function StatusPill({ status }: { status: string }) {
  const style =
    status === "긴급" || status === "재고공백"
      ? "bg-brand/10 text-brand"
      : status === "주의" ||
          status === "발주필요" ||
          status === "ETA 없음" ||
          status === "ETA 경과" ||
          status === "입고예정 없음" ||
          status === "임박"
        ? "bg-warn-bg text-warn"
        : status === "정상" || status === "안전"
          ? "bg-pos-bg text-pos"
          : "bg-row text-muted";
  return (
    <span className={cn("inline-flex h-[22px] items-center rounded-[7px] px-2 text-[12px] font-black", style)}>
      {status}
    </span>
  );
}
