"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, X } from "lucide-react";
import { getOrderReviewRows } from "@/lib/api";
import { routes } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import { canAccessOrderAnalysis } from "@/lib/order-access";
import { addRecentSkuSearch, getRecentSkuSearches } from "@/lib/storage/repositories/recent-sku-search";
import type { OrderReviewRow } from "@/types/api";

export function GlobalSkuSearch() {
  const router = useRouter();
  const { user } = useAuthSession();
  const orderAnalysisAllowed = canAccessOrderAnalysis(user);
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<OrderReviewRow[]>([]);
  const [open, setOpen] = useState(false);
  const [recent, setRecent] = useState<string[]>([]);

  useEffect(() => {
    setRecent(getRecentSkuSearches());
  }, []);

  useEffect(() => {
    if (!orderAnalysisAllowed) {
      setRows([]);
      return;
    }
    let active = true;
    getOrderReviewRows()
      .then((nextRows) => {
        if (active) setRows(nextRows);
      })
      .catch(() => {
        if (active) setRows([]);
      });
    return () => {
      active = false;
    };
  }, [orderAnalysisAllowed]);

  const results = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return rows.filter((row) => recent.includes(row.sku)).slice(0, 5);
    }
    return rows
      .filter((row) =>
        [row.sku, row.productName, row.brand].some((value) => value.toLowerCase().includes(normalized))
      )
      .slice(0, 7);
  }, [query, recent, rows]);

  const selectSku = useCallback(
    (sku: string, target: "stockGap" | "orderReview" | "skuConcentration" = "stockGap") => {
      addRecentSkuSearch(sku);
      setRecent(getRecentSkuSearches());
      setQuery("");
      setOpen(false);
      const href =
        target === "orderReview"
          ? `${routes.orderAnalysis}?sku=${encodeURIComponent(sku)}`
          : target === "skuConcentration"
            ? `${routes.skuConcentration}?q=${encodeURIComponent(sku)}`
            : `${routes.stockGap}?sku=${encodeURIComponent(sku)}`;
      router.push(href);
    },
    [router]
  );

  if (!orderAnalysisAllowed) return null;

  return (
    <div className="relative w-full max-w-[420px]">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder="SKU · 상품명 · 브랜드 전역 검색"
        className="h-10 w-full rounded-xl border border-line bg-white pl-9 pr-9 text-sm font-semibold text-ink shadow-sm outline-none transition placeholder:text-slate-400 focus:border-slate-400"
      />
      {query ? (
        <button type="button" onClick={() => setQuery("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400">
          <X className="h-4 w-4" />
        </button>
      ) : null}
      {open && (query || recent.length > 0) ? (
        <div className="absolute right-0 top-12 z-30 w-full overflow-hidden rounded-xl border border-line bg-white shadow-xl">
          <div className="border-b border-line px-3 py-2 text-xs font-bold text-slate-400">
            {query ? "검색 결과" : "최근 검색"}
          </div>
          {results.length > 0 ? (
            results.map((row) => (
              <div
                key={row.sku}
                className="grid gap-2 border-b border-line px-3 py-2.5 last:border-b-0"
              >
                <button
                  type="button"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => selectSku(row.sku)}
                  className="grid text-left"
                >
                  <span className="font-mono text-sm font-black text-brand-700">{row.sku}</span>
                  <span className="truncate text-sm font-bold text-ink">{row.productName}</span>
                  <span className="truncate text-xs font-semibold text-slate-500">{row.brand}</span>
                </button>
                <div className="flex flex-wrap gap-1">
                  <button type="button" onClick={() => selectSku(row.sku, "stockGap")} className="rounded-full bg-brand-50 px-2 py-1 text-xs font-bold text-brand-700">
                    재고공백
                  </button>
                  <button type="button" onClick={() => selectSku(row.sku, "orderReview")} className="rounded-full bg-slate-100 px-2 py-1 text-xs font-bold text-slate-700">
                    발주검토
                  </button>
                  <button type="button" onClick={() => selectSku(row.sku, "skuConcentration")} className="rounded-full bg-slate-100 px-2 py-1 text-xs font-bold text-slate-700">
                    SKU 집중도
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="px-3 py-6 text-center text-sm font-semibold text-slate-500">검색 결과가 없습니다.</div>
          )}
          <button
            type="button"
            onClick={() => setOpen(false)}
            className={cn("w-full border-t border-line px-3 py-2 text-xs font-bold text-slate-500 hover:bg-slate-25")}
          >
            닫기
          </button>
        </div>
      ) : null}
    </div>
  );
}
