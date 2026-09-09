"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getOrderReviewRows, getSeasonTrendAnalysis, getStockGapItems } from "@/lib/api";
import { amountOf, brandOf, countryOf, productNameOf, qtyOf, skuCodeOf } from "@/lib/global-demand-view-model";
import { measureClientWork } from "@/lib/performance";
import { buildGlobalSearchIndex } from "../lib/global-search";
import type { GlobalSearchSource } from "../lib/types";

const ORDER_TAB = { screen: "order", label: "발주분석 V1" } as const;
const GAP_TAB = { screen: "gap", label: "재고공백" } as const;

function compactSeasonSearchRows(rows: Record<string, unknown>[]) {
  const countries = new Map<string, Record<string, unknown>>();
  const skus = new Map<string, Record<string, unknown>>();
  rows.forEach((row) => {
    const amount = amountOf(row);
    const qty = qtyOf(row);
    const country = countryOf(row);
    if (country && country !== "-") {
      const current = countries.get(country) ?? { country, amount: 0, qty: 0 };
      current.amount = Number(current.amount) + amount;
      current.qty = Number(current.qty) + qty;
      countries.set(country, current);
    }

    const sku = skuCodeOf(row);
    if (!sku || sku === "-") return;
    const current = skus.get(sku) ?? {
      country: "-",
      sku,
      productName: productNameOf(row),
      brand: brandOf(row),
      amount: 0,
      qty: 0
    };
    current.amount = Number(current.amount) + amount;
    current.qty = Number(current.qty) + qty;
    skus.set(sku, current);
  });
  return [...countries.values(), ...skus.values()];
}

export function useWorkspaceGlobalSearch(
  onSeasonTrendDataLoaded: () => void,
  includeOrderData = true
) {
  const [sources, setSources] = useState<GlobalSearchSource[]>([]);
  const [refreshToken, setRefreshToken] = useState(0);
  const onSeasonTrendDataLoadedRef = useRef(onSeasonTrendDataLoaded);

  // This callback is supplied by the workspace and can legitimately receive a
  // new identity after a parent render. Keep the data-loading effect tied only
  // to an explicit refresh; otherwise its own state updates can retrigger it.
  useEffect(() => {
    onSeasonTrendDataLoadedRef.current = onSeasonTrendDataLoaded;
  }, [onSeasonTrendDataLoaded]);

  const refresh = useCallback(() => {
    setRefreshToken((current) => current + 1);
  }, []);

  const clear = useCallback(() => {
    setSources([]);
  }, []);

  useEffect(() => {
    let active = true;
    setSources([]);
    void Promise.all([
      includeOrderData
        ? getOrderReviewRows({ includeLatestFallback: true }).catch(() => [])
        : Promise.resolve([]),
      includeOrderData
        ? getStockGapItems({ requireCurrentSession: true }).catch(() => [])
        : Promise.resolve([]),
      getSeasonTrendAnalysis({ requireCurrentSession: true }).catch(() => null)
    ]).then(([orderRows, stockGapRows, result]) => {
        if (!active) return;
        const nextSources: GlobalSearchSource[] = [
          ...orderRows.map((row) => ({ row: row as unknown as Record<string, unknown>, tabs: [ORDER_TAB] })),
          ...stockGapRows.map((row) => ({ row: row as unknown as Record<string, unknown>, tabs: [GAP_TAB] }))
        ];
        if (!result) {
          setSources(nextSources);
          return;
        }
        if (result.hasSeasonTrendData) onSeasonTrendDataLoadedRef.current();
        const season = result.seasonAnalysis;
        const add = (rows: Record<string, unknown>[], tabs: GlobalSearchSource["tabs"]) => {
          rows.forEach((row) => nextSources.push({ row, tabs }));
        };
        const searchableSkuRows =
          season.countrySkuSummary?.length
            ? season.countrySkuSummary
            : season.countryTopSku?.length
              ? season.countryTopSku
              : season.topSku ?? [];
        add(compactSeasonSearchRows(searchableSkuRows), [
          { screen: "country", label: "국가 분석" },
          { screen: "brand", label: "브랜드 분석" },
          { screen: "sku", label: "SKU 분석" },
          { screen: "cross", label: "교차분석" },
          { screen: "report", label: "브랜드 자동 리포트" },
          { screen: "season", label: "시즌 캘린더" }
        ]);
        setSources(nextSources);
      });

    return () => {
      active = false;
    };
  }, [includeOrderData, refreshToken]);

  return {
    index: useMemo(() => measureClientWork("workspace.global-search.index", () => buildGlobalSearchIndex(sources), 12), [sources]),
    refresh,
    clear
  };
}
