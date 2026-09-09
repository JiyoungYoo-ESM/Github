"use client";

import { useCallback, useEffect, useState } from "react";
import { getExchangeRate, isAbortError } from "@/lib/api";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import type { ExchangeRateResponse } from "@/types/api";

/** Owns exchange-rate loading state shared by the order and insight screens. */
export function useWorkspaceExchangeRate(loadOnMount = true) {
  const { selectedEntity } = useAuthSession();
  const currencyCode: "USD" | "EUR" = selectedEntity === "USA" ? "USD" : "EUR";
  const [exchangeRate, setExchangeRate] = useState<ExchangeRateResponse | null>(null);
  const [exchangeRateInput, setExchangeRateInput] = useState("");
  const [exchangeRateError, setExchangeRateError] = useState("");
  const [refreshingExchangeRate, setRefreshingExchangeRate] = useState(false);

  const refreshExchangeRate = useCallback(async () => {
    setRefreshingExchangeRate(true);
    setExchangeRateError("");
    try {
      const rate = await getExchangeRate(currencyCode);
      setExchangeRate(rate);
      setExchangeRateInput(String(rate.currency_krw_rate));
    } catch (error) {
      // 법인 전환·로그아웃에서 우리가 끊은 요청은 실패가 아니다. 로그도 남기지 않고
      // "환율 조회 실패"도 띄우지 않는다.
      if (isAbortError(error)) {
        return;
      }
      console.warn("환율 조회 실패:", error instanceof Error ? error.message : error);
      setExchangeRateError("환율 조회 실패");
    } finally {
      setRefreshingExchangeRate(false);
    }
  }, [currencyCode]);

  useEffect(() => {
    if (loadOnMount) void refreshExchangeRate();
  }, [loadOnMount, refreshExchangeRate]);

  return {
    exchangeRate,
    setExchangeRate,
    exchangeRateInput,
    setExchangeRateInput,
    exchangeRateError,
    setExchangeRateError,
    refreshingExchangeRate,
    setRefreshingExchangeRate,
    refreshExchangeRate,
    currencyCode
  } as const;
}
