/**
 * Backwards-compatible API facade. URL selection, request identity, and HTTP
 * transport live in focused modules so feature clients do not duplicate auth
 * or browser-state rules.
 */

import type { UploadRole } from "@/types/api";
import {
  LOCAL_SERVER_API_BASE,
  normalizeApiBase,
  resolveBrowserApiBase,
  resolveServerApiBase,
  SAME_ORIGIN_API_BASE
} from "./base-url";

export const localServerApiBase = LOCAL_SERVER_API_BASE;
export const sameOriginApiBase = SAME_ORIGIN_API_BASE;
export { normalizeApiBase };

export const publicApiBase = normalizeApiBase(process.env.NEXT_PUBLIC_FASTAPI_BASE_URL);
export const internalApiBase = process.env.FASTAPI_INTERNAL_BASE_URL?.replace(/\/$/, "");

export function defaultApiBase(): string {
  return typeof window !== "undefined"
    ? SAME_ORIGIN_API_BASE
    : resolveServerApiBase(internalApiBase);
}

export const FASTAPI_BASE_URL = typeof window !== "undefined"
  ? resolveBrowserApiBase(process.env.NEXT_PUBLIC_FASTAPI_BASE_URL)
  : resolveServerApiBase(process.env.FASTAPI_INTERNAL_BASE_URL);
export const FASTAPI_UPLOAD_BASE_URL = FASTAPI_BASE_URL;

export const MAX_UPLOAD_FILE_BYTES = 100 * 1024 * 1024;
export const MAX_UPLOAD_TOTAL_BYTES = 300 * 1024 * 1024;
export const MAX_UPLOAD_FILES = 10;

export { CLIENT_ID_STORAGE_KEY, clientHeaders, getClientId, randomClientId } from "./request-context";
export { abortActiveApiRequests, apiFetch, ApiRequestError, isAbortError, parseApiError, wait } from "./transport";

export const ROLE_ORDER: UploadRole[] = [
  "eu_stock",
  "hq_eu_stock",
  "sales_detail",
  "hq_to_eu_sales_detail",
  "shipping",
  "inbound"
];
