import { formatNumber } from "../../../lib/utils.ts";
import { getActiveEntityCode } from "../../../lib/entity-session.ts";
import { getAnalysisAmountCurrencyCode } from "../../../lib/analysis-amount-currency.ts";

function activeCurrencyCode() {
  const entityCode = getActiveEntityCode();
  if (entityCode === "HQ") return "KRW";
  return entityCode === "USA" ? "USD" : "EUR";
}

let currentKrwExchangeRate: {
  currencyCode: "EUR" | "USD";
  value: number;
  date: string;
  source: "api" | "default" | string;
} | null = null;

export function setCurrentKrwExchangeRate(rate: {
  currencyCode?: string | null;
  value?: number | null;
  date?: string | null;
  source?: string | null;
} | null) {
  const currencyCode = String(rate?.currencyCode ?? "").toUpperCase();
  const value = Number(rate?.value);
  currentKrwExchangeRate = currencyCode === "EUR" || currencyCode === "USD"
    ? Number.isFinite(value) && value > 0
      ? {
          currencyCode,
          value,
          date: String(rate?.date ?? "").trim(),
          source: String(rate?.source ?? "").trim() || "api"
        }
      : null
    : null;
}

export function activeCurrencySymbol() {
  const currencyCode = activeCurrencyCode();
  if (currencyCode === "KRW") return "₩";
  return currencyCode === "USD" ? "$" : "€";
}

export function wonEok(value: number) {
  const currencyCode = getAnalysisAmountCurrencyCode() || activeCurrencyCode();
  const currentRate = currentKrwExchangeRate?.currencyCode === currencyCode
    ? currentKrwExchangeRate.value
    : null;
  const krwValue = currencyCode === "KRW" ? value : currentRate ? value * currentRate : null;
  if (krwValue !== null) return formatKrwAmount(krwValue);

  const symbol = activeCurrencySymbol();
  if (Math.abs(value) >= 1_000_000) return `${symbol}${formatNumber(value / 1_000_000, Math.abs(value) >= 10_000_000 ? 1 : 2)}M`;
  if (Math.abs(value) >= 1_000) return `${symbol}${formatNumber(value / 1_000, 1)}K`;
  return `${symbol}${formatNumber(value, 0)}`;
}

function formatKrwAmount(value: number) {
  const absValue = Math.abs(value);
  if (absValue >= 1_000_000_000_000) {
    return `₩${formatNumber(value / 1_000_000_000_000, absValue >= 10_000_000_000_000 ? 1 : 2)}조`;
  }
  if (absValue >= 100_000_000) {
    return `₩${formatNumber(value / 100_000_000, absValue >= 1_000_000_000 ? 1 : 2)}억`;
  }
  if (absValue >= 10_000) {
    return `₩${formatNumber(value / 10_000, absValue >= 1_000_000 ? 0 : 1)}만원`;
  }
  return `₩${formatNumber(value, 0)}원`;
}

// 교차분석 셀은 값을 "천 단위(K)"로 넘겨받는다. KRW는 원 단위가 작아 K 표기가
// 읽기 어려우므로(예: ₩6073628.4K) 다른 화면과 같은 억/만원 표기로 통일하고,
// EUR/USD는 천 단위 구분자를 넣은 K 표기를 유지한다.
export function formatCrossAmountK(valueInThousands: number) {
  return wonEok(valueInThousands * 1_000);
}

export function signedEur(value: number) {
  if (value > 0) return `+${wonEok(value)}`;
  if (value < 0) return `-${wonEok(Math.abs(value))}`;
  return wonEok(0);
}

export function krwEokValueFromEur(value: number, eurKrwRate?: number | null) {
  if (getAnalysisAmountCurrencyCode() === "KRW") return "";
  // HQ amount values are already KRW (`amount_krw`), so a second reference
  // conversion line would duplicate the same amount.
  if (activeCurrencyCode() === "KRW") return "";
  // `wonEok` already uses the live API rate for the active entity. Do not render
  // a second, duplicate reference amount beside it.
  if (currentKrwExchangeRate?.currencyCode === activeCurrencyCode()) return "";
  const currentRate = currentKrwExchangeRate?.currencyCode === activeCurrencyCode()
    ? currentKrwExchangeRate.value
    : null;
  const rate = currentRate ?? Number(eurKrwRate);
  if (!Number.isFinite(rate) || rate <= 0) return "";
  return formatKrwAmount(value * rate);
}

export function krwEokFromEur(value: number, eurKrwRate?: number | null) {
  const formatted = krwEokValueFromEur(value, eurKrwRate);
  return formatted ? `약 ${formatted}` : "";
}

export function signedKrwEokFromEur(value: number, eurKrwRate?: number | null) {
  const formatted = krwEokValueFromEur(Math.abs(value), eurKrwRate);
  if (!formatted) return "";
  if (value > 0) return `약 +${formatted}`;
  if (value < 0) return `약 -${formatted}`;
  return `약 ${formatted}`;
}

export function exchangeRateText(rate?: number | null, currencyCode = activeCurrencyCode()) {
  if (currencyCode === "KRW") return "원화(KRW) 기준";
  const numericRate = currentKrwExchangeRate?.currencyCode === currencyCode
    ? currentKrwExchangeRate.value
    : Number(rate);
  if (!Number.isFinite(numericRate) || numericRate <= 0) return "";
  return `${currencyCode}/KRW ${formatNumber(numericRate, 2)}`;
}

export function exchangeRateBasisLabel(options: Record<string, unknown> | null | undefined, rate?: number | null) {
  const currencyCode = String(options?.currency_code ?? activeCurrencyCode()).toUpperCase();
  const currentRate = currentKrwExchangeRate?.currencyCode === currencyCode ? currentKrwExchangeRate : null;
  const rateText = exchangeRateText(currentRate?.value ?? rate, currencyCode);
  if (!rateText) return "";
  if (currentRate) return `현재 환율 · ${rateText}${currentRate.date ? ` · ${currentRate.date}` : ""}`;
  if (currencyCode === "KRW") return rateText;
  const explicitBasis = String(options?.exchange_rate_basis ?? "").trim();
  const basis = explicitBasis || "원화 금액은 현재 적용 환율 기준의 참고 환산값입니다.";
  const rateDate = String(options?.exchange_rate_date ?? "").trim();
  return `${basis} · ${rateText}${rateDate ? ` · ${rateDate}` : ""}`;
}
