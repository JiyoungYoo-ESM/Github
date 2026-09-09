import type { ExchangeRateResponse, HealthResponse } from "@/types/api";
import { ApiRequestError, FASTAPI_BASE_URL, parseApiError } from "./client";

// 백엔드가 연결은 받되 응답을 못 주는 상태(리로드 중, 워커 기동 실패)에서도
// fetch가 영원히 pending으로 남지 않도록 타임아웃을 강제한다.
const HEALTH_REQUEST_TIMEOUT_MS = 10_000;
const EXCHANGE_RATE_REQUEST_TIMEOUT_MS = 15_000;
const exchangeRateRequests = new Map<"EUR" | "USD", Promise<ExchangeRateResponse>>();

async function fetchWithTimeout(url: string, timeoutMs = HEALTH_REQUEST_TIMEOUT_MS): Promise<Response> {
  try {
    return await fetch(url, {
      method: "GET",
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs)
    });
  } catch (caught) {
    if (caught instanceof DOMException && caught.name === "TimeoutError") {
      throw new ApiRequestError("서버 응답이 지연되어 요청을 중단했습니다. 재조회를 눌러 다시 시도해 주세요.", 408);
    }
    throw caught;
  }
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetchWithTimeout(`${FASTAPI_BASE_URL}/health`);
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
  return response.json() as Promise<HealthResponse>;
}

async function fetchExchangeRate(currencyCode: "EUR" | "USD"): Promise<ExchangeRateResponse> {
  const query = new URLSearchParams({ currency: currencyCode });
  const response = await fetchWithTimeout(
    `${FASTAPI_BASE_URL}/exchange-rate?${query.toString()}`,
    EXCHANGE_RATE_REQUEST_TIMEOUT_MS
  );
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
  return response.json() as Promise<ExchangeRateResponse>;
}

export function getExchangeRate(currencyCode: "EUR" | "USD" = "EUR"): Promise<ExchangeRateResponse> {
  const existing = exchangeRateRequests.get(currencyCode);
  if (existing) return existing;

  const request = fetchExchangeRate(currencyCode).finally(() => {
    if (exchangeRateRequests.get(currencyCode) === request) {
      exchangeRateRequests.delete(currencyCode);
    }
  });
  exchangeRateRequests.set(currencyCode, request);
  return request;
}
