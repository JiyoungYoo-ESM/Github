"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { SkuConcentrationClient } from "@/components/sku-concentration/SkuConcentrationClient";
import { StockGapClient } from "@/components/stock-gap/StockGapClient";
import { getOrderReviewRows, getStockGapItems } from "@/lib/api";
import { computeStockGapItem, startOfDay } from "@/lib/stock-gap";
import { cn } from "@/lib/utils";

export type OrderAnalysisTab = "order-review" | "stock-gap" | "sku-concentration";

const tabs: Array<{
  key: OrderAnalysisTab;
  href: string;
  label: string;
}> = [
  { key: "order-review", href: "/order-analysis/order-review", label: "발주검토" },
  { key: "stock-gap", href: "/order-analysis/stock-gap", label: "재고공백" },
  { key: "sku-concentration", href: "/order-analysis/sku-concentration", label: "SKU 집중도" }
];

const tabDescriptions: Record<OrderAnalysisTab, string> = {
  "order-review": "발주 필요 SKU의 권장 수량 · 금액 · 판단 사유를 확인합니다.",
  "stock-gap": "현재 재고와 ETA 사이의 공백 및 긴급 보충 리스크를 위험 순으로 점검합니다.",
  "sku-concentration": "판매 비중과 재고 비중을 비교해 SKU·브랜드 편중도와 판매–재고 불균형을 점검합니다."
};

function ActiveTabContent({ tab }: { tab: OrderAnalysisTab }) {
  if (tab === "stock-gap") {
    return <StockGapClient />;
  }
  if (tab === "sku-concentration") {
    return <SkuConcentrationClient />;
  }
  // "order-review" 탭은 이 shell이 아니라 /order-analysis/order-review 라우트의
  // SiliconAnalyticsWorkspace(initialScreen="order")가 담당한다. 이 shell은
  // sku-concentration 페이지에서만 마운트되므로 이 분기에는 도달하지 않는다.
  return null;
}

type OrderAnalysisClientProps = {
  tab?: OrderAnalysisTab;
};

export function OrderAnalysisClient({ tab = "order-review" }: OrderAnalysisClientProps) {
  const [counts, setCounts] = useState<Partial<Record<OrderAnalysisTab, number>>>({});
  const [countError, setCountError] = useState(false);
  const searchParams = useSearchParams();
  const baseDate = useMemo(() => startOfDay(new Date()), []);

  useEffect(() => {
    let active = true;
    setCountError(false);
    Promise.all([getOrderReviewRows(), getStockGapItems()])
      .then(([orderRows, stockGapRows]) => {
        if (!active) return;
        const computedStockGapRows = stockGapRows.map((item) => computeStockGapItem(item, baseDate));
        setCounts({
          "order-review": orderRows.filter((row) => row.requiredOrderQty > 0).length,
          "stock-gap": computedStockGapRows.filter((item) => item.status === "urgent_replenishment").length
        });
      })
      .catch(() => {
        if (active) setCountError(true);
      });
    return () => {
      active = false;
    };
  }, [baseDate]);

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-line bg-white p-2 shadow-sm">
        <div className="grid rounded-xl bg-slate-75 p-1.5 md:grid-cols-3">
          {tabs.map((item) => {
            const active = item.key === tab;
            const query = searchParams.toString();
            const href = query ? `${item.href}?${query}` : item.href;

            return (
              <Link
                key={item.key}
                href={href}
                className={cn(
                  "flex h-11 items-center justify-center gap-2 rounded-lg text-base font-bold transition",
                  active
                    ? "bg-white text-black shadow-soft ring-1 ring-line"
                    : "text-slate-500 hover:text-black"
                )}
              >
                {item.label}
                {item.key === tab && typeof counts[item.key] === "number" ? (
                  <span className="grid h-6 min-w-6 place-items-center rounded-full bg-slate-200 px-1.5 text-sm font-bold text-slate-700">
                    {counts[item.key]}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </div>
        <p className="px-3 pb-2 pt-3 text-base font-semibold text-slate-500">
          {tabDescriptions[tab]}
          {countError && (
            <span className="ml-2 text-sm font-bold text-brand-700">
              · 건수 조회 실패 — 새로고침해 주세요
            </span>
          )}
        </p>
      </section>

      <ActiveTabContent tab={tab} />
    </div>
  );
}
