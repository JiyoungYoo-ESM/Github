"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { getStockGapItems } from "@/lib/api";
import {
  computeStockGapItem,
  formatDate,
  startOfDay,
  type StockGapComputedItem
} from "@/lib/stock-gap";
import {
  numberText,
  stockGapActionText,
  stockGapNarrative,
  stockGapStatusMeta,
  stockoutLabel
} from "@/lib/stock-gap-view";
import { routes } from "@/lib/routes";
import { cn, formatNumber } from "@/lib/utils";

function Metric({
  label,
  value,
  sub,
  danger = false
}: {
  label: string;
  value: string;
  sub?: string;
  danger?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border p-3",
        danger ? "border-red-100 bg-red-50" : "border-slate-200 bg-white"
      )}
    >
      <p className="text-xs font-bold text-slate-500">{label}</p>
      <p
        className={cn(
          "mt-1.5 text-base font-black tabular-nums",
          danger ? "text-brand-700" : "text-ink"
        )}
      >
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs font-semibold text-slate-400">{sub}</p>}
    </div>
  );
}

export function SkuStockGapDrawer({
  sku,
  onClose
}: {
  sku: string | null;
  onClose: () => void;
}) {
  const [item, setItem] = useState<StockGapComputedItem | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback((targetSku: string) => {
    setLoading(true);
    setItem(null);
    const baseDate = startOfDay(new Date());
    getStockGapItems()
      .then((items) => {
        const raw = items.find((i) => i.sku === targetSku);
        setItem(raw ? computeStockGapItem(raw, baseDate) : null);
      })
      .catch(() => setItem(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (sku) {
      load(sku);
    } else {
      setItem(null);
    }
  }, [sku, load]);

  useEffect(() => {
    if (!sku) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [sku, onClose]);

  const open = sku !== null;
  const isRisk =
    item?.status === "urgent_replenishment" || item?.status === "stock_gap";

  return (
    <>
      <div
        aria-hidden="true"
        className={cn(
          "fixed inset-0 z-40 bg-black/20 transition-opacity duration-200",
          open ? "opacity-100" : "pointer-events-none opacity-0"
        )}
        onClick={onClose}
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${sku ?? ""} 재고공백 상세`}
        className={cn(
          "fixed right-0 top-0 z-50 flex h-full w-full max-w-[500px] flex-col border-l border-line bg-white shadow-panel transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full"
        )}
      >
        {/* Header */}
        <div className="flex shrink-0 items-start justify-between border-b border-line px-5 py-4">
          {item ? (
            <div className="min-w-0 pr-4">
              <p className="font-mono text-sm font-black text-brand-700">{item.sku}</p>
              <h2 className="mt-0.5 text-base font-black leading-snug text-ink">
                {item.productName}
              </h2>
              <p className="mt-0.5 text-sm font-semibold text-slate-500">{item.brand}</p>
            </div>
          ) : (
            <div className="min-w-0 pr-4">
              <p className="font-mono text-sm font-black text-brand-700">{sku}</p>
              <p className="mt-0.5 text-sm font-semibold text-slate-400">
                {loading ? "불러오는 중…" : "데이터 없음"}
              </p>
            </div>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line text-slate-400 hover:bg-slate-25 hover:text-ink"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          {loading && (
            <div className="grid grid-cols-2 gap-3">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="h-20 animate-pulse rounded-xl bg-slate-100" />
              ))}
            </div>
          )}

          {!loading && item && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                {(() => {
                  const meta = stockGapStatusMeta[item.status];
                  return (
                    <Badge className={cn("gap-1.5 text-sm font-bold", meta.badge)}>
                      <span className={cn("h-2 w-2 rounded-full", meta.dot)} />
                      {meta.label}
                    </Badge>
                  );
                })()}
                <span
                  className={cn(
                    "text-sm font-bold",
                    isRisk ? "text-brand-700" : "text-slate-600"
                  )}
                >
                  {stockGapActionText(item)}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <Metric
                  label="현재 가용재고"
                  value={`${numberText(item.availableQty)}개`}
                />
                <Metric
                  label="일평균 판매"
                  value={`${numberText(item.dailySalesQty, 1)}개`}
                  sub="최근 3개월"
                />
                <Metric
                  label="재고 소진"
                  value={formatDate(item.stockoutDate)}
                  sub={stockoutLabel(item)}
                  danger={!!isRisk}
                />
                <Metric
                  label="가장 빠른 ETA"
                  value={formatDate(item.earliestEtaDate)}
                  sub={item.earliestEta?.transportMode ?? "입고 없음"}
                />
                <Metric
                  label="재고 공백일"
                  value={item.gapDays === null ? "-" : `${formatNumber(item.gapDays)}일`}
                  sub={
                    item.gapTiming === "active"
                      ? "이미 진행 중"
                      : item.gapTiming === "future"
                        ? "발생 예정"
                        : "공백 없음"
                  }
                  danger={(item.gapDays ?? 0) > 0}
                />
                <Metric label="발주 권장" value={stockGapActionText(item)} />
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="mb-1.5 text-xs font-bold text-slate-500">판단 근거</p>
                <p className="text-sm font-semibold leading-6 text-slate-700">
                  {stockGapNarrative(item)}
                </p>
              </div>
            </>
          )}

          {!loading && !item && sku && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <p className="text-sm font-semibold text-slate-500">
                재고공백 데이터가 없습니다.
              </p>
              <p className="mt-1 text-xs text-slate-400">
                재고공백 분석이 실행되지 않았거나 해당 SKU가 없을 수 있습니다.
              </p>
            </div>
          )}
        </div>

        {item && (
          <div className="shrink-0 border-t border-line px-5 py-4">
            <Link
              href={`${routes.stockGap}?sku=${encodeURIComponent(item.sku)}`}
              onClick={onClose}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-ink py-2.5 text-sm font-bold text-white transition hover:bg-slate-700"
            >
              재고공백 전체 보기
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        )}
      </aside>
    </>
  );
}
