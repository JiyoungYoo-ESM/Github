"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getExchangeRate } from "@/lib/api";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import type { ExchangeRateResponse } from "@/types/api";
import { exchangeRateSourceText, formatExchangeRate } from "./upload-utils";

type ExchangeRateFieldProps = {
  exchangeRate: ExchangeRateResponse | null;
  exchangeRateError: string;
  exchangeRateInput: string;
  onExchangeRateInputChange: (value: string) => void;
};

function exchangeRateMetaText(rate: ExchangeRateResponse) {
  const sourceText = exchangeRateSourceText(rate.rate_source);
  if (rate.rate_source === "default") {
    return rate.fallback_rate_as_of && rate.fallback_rate_as_of !== "unknown"
      ? `${sourceText} · ${rate.fallback_rate_as_of}`
      : sourceText;
  }
  return `${sourceText}${rate.rate_date ? ` · ${rate.rate_date}` : ""}`;
}

export function ExchangeRateField({
  exchangeRate,
  exchangeRateError,
  exchangeRateInput,
  onExchangeRateInputChange
}: ExchangeRateFieldProps) {
  const { selectedEntity } = useAuthSession();
  const currencyCode = selectedEntity === "USA" ? "USD" : "EUR";
  const [currentRate, setCurrentRate] = useState<ExchangeRateResponse | null>(exchangeRate);
  const [currentError, setCurrentError] = useState(exchangeRateError);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    setCurrentRate(exchangeRate);
    setCurrentError(exchangeRateError);
  }, [exchangeRate, exchangeRateError]);

  const refreshExchangeRate = async () => {
    setRefreshing(true);
    try {
      const response = await getExchangeRate(currencyCode);
      setCurrentRate(response);
      setCurrentError("");
      onExchangeRateInputChange(String(response.eur_krw_rate));
    } catch (caught) {
      setCurrentRate(null);
      setCurrentError(caught instanceof Error ? caught.message : "환율 조회 실패");
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <label>
        <span className="text-sm font-semibold text-slate-700">적용 환율({currencyCode}/KRW)</span>
        <Input
          className="mt-2"
          type="number"
          value={exchangeRateInput}
          onChange={(event) => onExchangeRateInputChange(event.target.value)}
          inputMode="decimal"
          min="0.01"
          step="0.01"
          placeholder="예: 1500"
        />
        <span className="mt-1 block text-xs text-slate-500">
          {currentError ? "자동 조회 실패 시 현재 환율을 직접 입력하세요." : "자동 조회값을 수정하면 수동 환율로 분석됩니다."}
        </span>
      </label>

      <div className="rounded-2xl border border-brand-100 bg-brand-50 px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold text-brand-800">{currencyCode}/KRW 환율</p>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="h-7 px-2 text-xs"
            onClick={refreshExchangeRate}
            disabled={refreshing}
          >
            {refreshing ? "조회 중" : "재조회"}
          </Button>
        </div>
        <p className="mt-2 text-lg font-bold text-brand-900">
          {currentRate ? formatExchangeRate(currentRate.eur_krw_rate) : currentError ? "조회 실패" : "조회 중"}
        </p>
        <p className="mt-1 text-xs text-brand">
          {currentRate ? exchangeRateMetaText(currentRate) : currentError || "환율 자동 조회"}
        </p>
      </div>
    </div>
  );
}
