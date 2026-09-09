import type {
  AnalyzeResponse,
  OrderReviewRow,
  SeasonTrendAnalyzeResponse
} from "@/types/api";
import { apiFetch, ApiRequestError, clientHeaders, FASTAPI_BASE_URL, parseApiError } from "./client";
import { orderReviewRowFromTable } from "./mappers";
import { normalizeSeasonTrendResponse } from "./season-normalize";
import {
  dispatchStorageEvent,
  idbDeleteItem,
  idbGetItem,
  idbSetItem,
  readRawItem,
  removeItem,
  writeRawItem
} from "@/lib/storage/adapter";
import { getActiveEntityCode } from "@/lib/entity-session";

export const LAST_RESULT_STORAGE_KEY = "esm_scm_last_result";
export const SEASON_TREND_RESULT_STORAGE_KEY = "esm_scm_season_trend_result";
export const ANALYSIS_RESULT_CHANGED_EVENT = "esm_scm_analysis_result_changed";
export const CURRENT_ANALYSIS_JOB_STORAGE_KEY = "esm_scm_current_analysis_job_id";
export const CURRENT_ANALYSIS_EXPLICIT_JOB_STORAGE_KEY = "esm_scm_current_analysis_explicit_job_id";
export const CURRENT_SEASON_TREND_READY_STORAGE_KEY = "esm_scm_current_season_trend_ready";
const ANALYSIS_STORAGE_VERSION_KEY = "esm_scm_analysis_storage_version";
// v3은 발주 계산이 바뀐 결과를 캐시에서 버린다. 저장된 숫자만 보고는 구버전인지 알 수 없어
// (특히 SKU 집중도 판매금액이 EUR이었는지 KRW인지) 변환할 수 없으므로, 잘못된 값을 계속
// 보여주는 대신 결과를 비우고 재분석을 유도한다.
const ANALYSIS_STORAGE_VERSION = "3";
const SEASON_TREND_STORAGE_VERSION_KEY = "esm_scm_season_trend_storage_version";
// v4 invalidates results whose boundary months were silently excluded.
const SEASON_TREND_STORAGE_VERSION = "6";
const ANALYSIS_DB_NAME = "esm_scm_analysis";
const ANALYSIS_DB_STORE = "results";
const ANALYSIS_DB_RESULT_KEY = "latest";
const SEASON_TREND_DB_NAME = "esm_scm_season_trend";
const SEASON_TREND_DB_STORE = "results";
const SEASON_TREND_DB_RESULT_KEY = "latest";
const MAX_PERSISTED_SEASON_ROWS = 40_000;
const SENSITIVE_LOCAL_STORAGE_KEYS = [
  "esm_scm_shared_lead_times",
  "esm_scm_order_workflow",
  "esm_scm_season_order_queue",
  "esm_scm_integrated_order_state",
  "esm_scm_recent_sku_searches"
] as const;
const SENSITIVE_SESSION_STORAGE_KEYS = ["esm_scm_season_analysis_draft"] as const;

let lastAnalysisResult: AnalyzeResponse | null = null;
let lastSeasonTrendResult: SeasonTrendAnalyzeResponse | null = null;
let seasonTrendStorageResetPromise: Promise<void> | null = null;

function resultEntityCode(result: unknown): string {
  if (!result || typeof result !== "object") return "";
  const record = result as Record<string, unknown>;
  if (typeof record.entity_code === "string") return record.entity_code;
  const settings = record.settings;
  if (!settings || typeof settings !== "object") return "";
  const entityCode = (settings as Record<string, unknown>).entity_code;
  return typeof entityCode === "string" ? entityCode : "";
}

function matchesActiveEntity(result: unknown): boolean {
  const activeEntity = getActiveEntityCode();
  return !activeEntity || resultEntityCode(result) === activeEntity;
}

function withActiveEntityScope<T extends object>(result: T): T {
  const activeEntity = getActiveEntityCode();
  if (!activeEntity) return result;
  const record = result as T & { entity_code?: string; settings?: Record<string, unknown> };
  if (record.settings) {
    return {
      ...result,
      settings: { ...record.settings, entity_code: activeEntity }
    };
  }
  return { ...result, entity_code: activeEntity };
}

function perfLog(message: string, fields: Record<string, unknown> = {}) {
  if (typeof window === "undefined") {
    return;
  }
  console.info(`[perf][analysis-storage] ${message}`, fields);
}

function emitAnalysisResultChanged() {
  dispatchStorageEvent(ANALYSIS_RESULT_CHANGED_EVENT);
}

function seasonTrendRowCount(result: SeasonTrendAnalyzeResponse): number {
  const season = result.season_analysis;
  const ingredient = result.ingredient_analysis;
  return (
    (season?.category1Monthly?.length ?? 0) +
    (season?.category2Monthly?.length ?? 0) +
    (season?.topSku?.length ?? 0) +
    (season?.skuMonthly?.length ?? 0) +
    (season?.countryCategoryMonthly?.length ?? 0) +
    (season?.countryCategory2Monthly?.length ?? 0) +
    (season?.countryTopSku?.length ?? 0) +
    (season?.countrySkuMonthly?.length ?? 0) +
    (season?.countryCustomerSummary?.length ?? 0) +
    (season?.countryCategoryCustomerSummary?.length ?? 0) +
    (season?.customerSalesSummary?.length ?? 0) +
    (ingredient?.summary?.length ?? 0) +
    (ingredient?.monthlyTrend?.length ?? 0) +
    (ingredient?.topSku?.length ?? 0)
  );
}

function shouldPersistSeasonTrendResult(result: SeasonTrendAnalyzeResponse): boolean {
  return seasonTrendRowCount(result) <= MAX_PERSISTED_SEASON_ROWS;
}

async function writeAnalysisResultToDb(result: AnalyzeResponse): Promise<void> {
  await idbSetItem(ANALYSIS_DB_NAME, ANALYSIS_DB_STORE, ANALYSIS_DB_RESULT_KEY, result);
}

/** 분석 결과는 sessionStorage 한도(약 5MB)를 넘기 쉬워서 IndexedDB를 durable 저장소로 쓴다. */
async function readAnalysisResultFromDb(): Promise<AnalyzeResponse | null> {
  if (typeof window === "undefined") {
    return null;
  }
  return new Promise((resolve) => {
    let settled = false;
    const finish = (result: AnalyzeResponse | null) => {
      if (settled) {
        return;
      }
      settled = true;
      window.clearTimeout(timer);
      resolve(result);
    };
    const timer = window.setTimeout(() => finish(null), 3000);
    idbGetItem<AnalyzeResponse>(ANALYSIS_DB_NAME, ANALYSIS_DB_STORE, ANALYSIS_DB_RESULT_KEY)
      .then(finish)
      .catch(() => finish(null));
  });
}

async function deleteAnalysisResultFromDb(): Promise<void> {
  await idbDeleteItem(ANALYSIS_DB_NAME, ANALYSIS_DB_STORE, ANALYSIS_DB_RESULT_KEY);
}

async function readSeasonTrendResultFromDb(): Promise<SeasonTrendAnalyzeResponse | null> {
  if (typeof window === "undefined") {
    return null;
  }
  // idbGetItem이 내부적으로 DB 열기 자체를 3초 안에 못 하면 null로 폴백하지만,
  // 여기서는 "열기+조회" 전체를 다시 3초로 감싸 느린 조회도 조기에 포기한다(원래 동작 유지).
  return new Promise((resolve) => {
    let settled = false;
    const finish = (result: SeasonTrendAnalyzeResponse | null) => {
      if (settled) {
        return;
      }
      settled = true;
      window.clearTimeout(timer);
      resolve(result);
    };
    const timer = window.setTimeout(() => finish(null), 3000);
    idbGetItem<SeasonTrendAnalyzeResponse>(SEASON_TREND_DB_NAME, SEASON_TREND_DB_STORE, SEASON_TREND_DB_RESULT_KEY)
      .then(finish)
      .catch(() => finish(null));
  });
}

async function writeSeasonTrendResultToDb(result: SeasonTrendAnalyzeResponse): Promise<void> {
  await idbSetItem(SEASON_TREND_DB_NAME, SEASON_TREND_DB_STORE, SEASON_TREND_DB_RESULT_KEY, result);
}

async function deleteSeasonTrendResultFromDb(): Promise<void> {
  await idbDeleteItem(SEASON_TREND_DB_NAME, SEASON_TREND_DB_STORE, SEASON_TREND_DB_RESULT_KEY);
}

export function getStoredAnalysisResult(): AnalyzeResponse | null {
  if (lastAnalysisResult) {
    if (matchesActiveEntity(lastAnalysisResult)) return lastAnalysisResult;
    lastAnalysisResult = null;
  }
  if (typeof window !== "undefined") {
    removeItem("local", LAST_RESULT_STORAGE_KEY);
    removeItem("local", CURRENT_ANALYSIS_JOB_STORAGE_KEY);
    if (readRawItem("session", ANALYSIS_STORAGE_VERSION_KEY) !== ANALYSIS_STORAGE_VERSION) {
      removeItem("session", LAST_RESULT_STORAGE_KEY);
      removeItem("session", CURRENT_ANALYSIS_JOB_STORAGE_KEY);
      removeItem("session", CURRENT_ANALYSIS_EXPLICIT_JOB_STORAGE_KEY);
      writeRawItem("session", ANALYSIS_STORAGE_VERSION_KEY, ANALYSIS_STORAGE_VERSION);
    }
    try {
      const stored = readRawItem("session", LAST_RESULT_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as AnalyzeResponse;
        const currentJobId = readRawItem("session", CURRENT_ANALYSIS_JOB_STORAGE_KEY);
        if (parsed.job_id && parsed.job_id === currentJobId && matchesActiveEntity(parsed)) {
          lastAnalysisResult = parsed;
          return lastAnalysisResult;
        }
        removeItem("session", LAST_RESULT_STORAGE_KEY);
      }
    } catch {
      removeItem("session", LAST_RESULT_STORAGE_KEY);
    }
  }
  return null;
}

export async function getStoredAnalysisResultAsync(): Promise<AnalyzeResponse | null> {
  const stored = getStoredAnalysisResult();
  if (stored) {
    return stored;
  }
  // sessionStorage에 담지 못한 큰 결과는 IndexedDB에 있다. 현재 세션/법인 조건은 그대로
  // 지키고(작은 job id 마커는 sessionStorage에 항상 들어간다), 통과하면 메모리에 올린다.
  const fromDb = await readAnalysisResultFromDb();
  if (!fromDb) {
    return null;
  }
  const currentJobId = getCurrentAnalysisJobId();
  if (!fromDb.job_id || fromDb.job_id !== currentJobId || !matchesActiveEntity(fromDb)) {
    await deleteAnalysisResultFromDb();
    return null;
  }
  lastAnalysisResult = fromDb;
  return fromDb;
}

export type LatestOrderReviewMeta = {
  jobId: string | null;
  savedAt: string | null;
  source: string | null;
  downloadUrl: string | null;
};

let latestOrderReviewMeta: LatestOrderReviewMeta | null = null;
let latestOrderReviewRawRows: Record<string, unknown>[] | null = null;
let latestOrderReviewEtaRows: Record<string, unknown>[] | null = null;

export function getLatestOrderReviewMeta(): LatestOrderReviewMeta | null {
  return latestOrderReviewMeta;
}

/**
 * 서버가 저장해 둔 발주검토 원본 행. 매핑된 OrderReviewRow에는 기준일·일평균 판매수량이
 * 없어서, 세션 복구 결과를 이 값으로 채워야 재고공백 화면이 분석 기준일 기준으로 소진일을
 * 계산한다(매핑된 행만 쓰면 오늘 날짜로 다시 계산된다).
 */
export function getLatestOrderReviewRawRows(): Record<string, unknown>[] | null {
  return latestOrderReviewRawRows;
}

/**
 * 서버가 저장해 둔 도착 캘린더 행. 발주검토 행에는 SKU별 '최초 ETA' 한 건만 있어서, 이
 * 표가 없으면 세션을 복구한 재고공백 화면이 ETA 상세와 타임라인 입고 지점을 그릴 수 없다.
 */
export function getLatestOrderReviewEtaRows(): Record<string, unknown>[] | null {
  return latestOrderReviewEtaRows;
}

export async function fetchLatestOrderReviewRows(): Promise<OrderReviewRow[]> {
  const startedAt = performance.now();
  const response = await apiFetch(`${FASTAPI_BASE_URL}/analysis/latest-order-review`, {
    headers: clientHeaders()
  });
  perfLog("latest_order_review_fetch_done", { seconds: Number(((performance.now() - startedAt) / 1000).toFixed(3)) });

  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }

  const parseStartedAt = performance.now();
  const payload = (await response.json()) as {
    rows?: Record<string, unknown>[];
    eta_rows?: Record<string, unknown>[];
    job_id?: string | null;
    saved_at?: string | null;
    source?: string | null;
    download_url?: string | null;
  };
  latestOrderReviewMeta = {
    jobId: typeof payload.job_id === "string" ? payload.job_id : null,
    savedAt: typeof payload.saved_at === "string" ? payload.saved_at : null,
    source: typeof payload.source === "string" ? payload.source : null,
    downloadUrl: typeof payload.download_url === "string" ? payload.download_url : null
  };
  const rawRows = payload.rows ?? [];
  const etaRows = payload.eta_rows ?? [];
  latestOrderReviewRawRows = rawRows.length > 0 ? rawRows : null;
  latestOrderReviewEtaRows = etaRows.length > 0 ? etaRows : null;
  const rows = rawRows.map(orderReviewRowFromTable);
  perfLog("latest_order_review_parse_done", {
    seconds: Number(((performance.now() - parseStartedAt) / 1000).toFixed(3)),
    rows: rows.length,
    etaRows: etaRows.length
  });
  return rows;
}

export async function getStoredSeasonTrendResult(): Promise<SeasonTrendAnalyzeResponse | null> {
  if (seasonTrendStorageResetPromise) {
    await seasonTrendStorageResetPromise;
  }
  if (typeof window !== "undefined" && readRawItem("session", SEASON_TREND_STORAGE_VERSION_KEY) !== SEASON_TREND_STORAGE_VERSION) {
    removeItem("session", SEASON_TREND_RESULT_STORAGE_KEY);
    writeRawItem("session", SEASON_TREND_STORAGE_VERSION_KEY, SEASON_TREND_STORAGE_VERSION);
    lastSeasonTrendResult = null;
    // Preserve the ready marker so the scoped backend snapshot can be fetched
    // once after this storage-only migration. The obsolete oversized
    // IndexedDB clone is removed before any read is attempted.
    const resetPromise = deleteSeasonTrendResultFromDb();
    seasonTrendStorageResetPromise = resetPromise;
    try {
      await resetPromise;
    } finally {
      if (seasonTrendStorageResetPromise === resetPromise) {
        seasonTrendStorageResetPromise = null;
      }
    }
    return null;
  }
  if (lastSeasonTrendResult) {
    const normalized = normalizeSeasonTrendResponse(lastSeasonTrendResult);
    if (!matchesActiveEntity(normalized) || isStaleSeasonTrendResult(normalized)) {
      clearSeasonTrendResult();
      return null;
    }
    lastSeasonTrendResult = normalized;
    return normalized;
  }
  if (typeof window !== "undefined") {
    try {
      const stored = readRawItem("session", SEASON_TREND_RESULT_STORAGE_KEY);
      if (stored) {
        const parsed = normalizeSeasonTrendResponse(JSON.parse(stored) as SeasonTrendAnalyzeResponse);
        if (!matchesActiveEntity(parsed) || isStaleSeasonTrendResult(parsed)) {
          removeItem("session", SEASON_TREND_RESULT_STORAGE_KEY);
          lastSeasonTrendResult = null;
          return null;
        }
        lastSeasonTrendResult = parsed;
        return lastSeasonTrendResult;
      }
    } catch {
      removeItem("session", SEASON_TREND_RESULT_STORAGE_KEY);
    }
  }
  const dbResult = await readSeasonTrendResultFromDb();
  if (dbResult) {
    const normalized = normalizeSeasonTrendResponse(dbResult);
    if (!matchesActiveEntity(normalized) || isStaleSeasonTrendResult(normalized)) {
      clearSeasonTrendResult();
      return null;
    }
    lastSeasonTrendResult = normalized;
    return normalized;
  }
  return null;
}

export function isStaleSeasonTrendResult(result: SeasonTrendAnalyzeResponse | AnalyzeResponse | null | undefined) {
  const season = result?.season_analysis;
  if (season && Number((result as SeasonTrendAnalyzeResponse).analysis_schema_version ?? 0) < 13) return true;
  const hasUploadedSeasonFiles = Boolean(result?.uploaded_files?.some((file) => file.role === "sales_history" || file.role === "prod_list"));
  const hasAnySeasonData = Boolean(
    (season?.category1Monthly?.length ?? 0) > 0 ||
      (season?.category2Monthly?.length ?? 0) > 0 ||
      (season?.topSku?.length ?? 0) > 0 ||
      (season?.skuMonthly?.length ?? 0) > 0 ||
      (season?.countryCategoryMonthly?.length ?? 0) > 0 ||
      (season?.countryCategory2Monthly?.length ?? 0) > 0 ||
      (season?.countryTopSku?.length ?? 0) > 0 ||
      (season?.countrySkuMonthly?.length ?? 0) > 0
  );
  return Boolean(season && hasUploadedSeasonFiles && !hasAnySeasonData);
}

export function getLastAnalysisResult(): AnalyzeResponse | null {
  return getStoredAnalysisResult();
}

export function getCurrentAnalysisJobId(): string {
  return readRawItem("session", CURRENT_ANALYSIS_JOB_STORAGE_KEY) ?? "";
}

export function hasExplicitCurrentAnalysisResult(
  result: Pick<AnalyzeResponse, "job_id"> | null | undefined
): boolean {
  if (!result?.job_id) return false;
  return readRawItem("session", CURRENT_ANALYSIS_EXPLICIT_JOB_STORAGE_KEY) === result.job_id;
}

export function hasCurrentSeasonTrendResult(): boolean {
  // Version migration is completed by getStoredSeasonTrendResult(). Keeping
  // this gate marker-only lets the getter discard an oversized legacy clone
  // and recover the scoped backend snapshot without forcing a new analysis.
  return readRawItem("session", CURRENT_SEASON_TREND_READY_STORAGE_KEY) === "1";
}

export function clearLastAnalysisResult(): void {
  lastAnalysisResult = null;
  if (typeof window !== "undefined") {
    removeItem("local", LAST_RESULT_STORAGE_KEY);
    removeItem("local", CURRENT_ANALYSIS_JOB_STORAGE_KEY);
    removeItem("session", LAST_RESULT_STORAGE_KEY);
    removeItem("session", CURRENT_ANALYSIS_JOB_STORAGE_KEY);
    removeItem("session", CURRENT_ANALYSIS_EXPLICIT_JOB_STORAGE_KEY);
  }
  void deleteAnalysisResultFromDb();
  emitAnalysisResultChanged();
}

export function clearCurrentAnalysisStatus(): void {
  if (typeof window !== "undefined") {
    removeItem("local", CURRENT_ANALYSIS_JOB_STORAGE_KEY);
    removeItem("session", CURRENT_ANALYSIS_JOB_STORAGE_KEY);
    removeItem("session", CURRENT_ANALYSIS_EXPLICIT_JOB_STORAGE_KEY);
  }
  emitAnalysisResultChanged();
}

type SaveLastAnalysisResultOptions = {
  markExecuted?: boolean;
};

export async function saveLastAnalysisResult(
  result: AnalyzeResponse,
  options: SaveLastAnalysisResultOptions = {}
): Promise<void> {
  const startedAt = performance.now();
  result = withActiveEntityScope(result);
  lastAnalysisResult = result;
  if (typeof window !== "undefined") {
    removeItem("local", LAST_RESULT_STORAGE_KEY);
    removeItem("local", CURRENT_ANALYSIS_JOB_STORAGE_KEY);
    writeRawItem("session", ANALYSIS_STORAGE_VERSION_KEY, ANALYSIS_STORAGE_VERSION);
    try {
      if (!writeRawItem("session", LAST_RESULT_STORAGE_KEY, JSON.stringify(result))) {
        removeItem("session", LAST_RESULT_STORAGE_KEY);
      }
    } catch {
      removeItem("session", LAST_RESULT_STORAGE_KEY);
    }
    try {
      // Result persistence can still succeed even if the lightweight status marker fails.
      writeRawItem("session", CURRENT_ANALYSIS_JOB_STORAGE_KEY, result.job_id);
      if (options.markExecuted) {
        writeRawItem("session", CURRENT_ANALYSIS_EXPLICIT_JOB_STORAGE_KEY, result.job_id);
      } else {
        const explicitJobId = readRawItem("session", CURRENT_ANALYSIS_EXPLICIT_JOB_STORAGE_KEY);
        if (explicitJobId && explicitJobId !== result.job_id) {
          removeItem("session", CURRENT_ANALYSIS_EXPLICIT_JOB_STORAGE_KEY);
        }
      }
    } catch {
      // ignore
    }
  }
  // 발주검토 결과는 sessionStorage 한도를 넘기 쉽다(원본 행 2,586건이면 7MB 이상). 위 쓰기가
  // 실패하면 새로고침 때 결과가 사라지므로 IndexedDB에도 남긴다.
  try {
    await writeAnalysisResultToDb(result);
  } catch {
    // 저장에 실패해도 메모리 결과로 현재 화면은 동작한다.
  }
  emitAnalysisResultChanged();
  perfLog("save_last_analysis_result_done", {
    seconds: Number(((performance.now() - startedAt) / 1000).toFixed(3)),
    jobId: result.job_id,
    tableRows: Object.fromEntries(Object.entries(result.tables ?? {}).map(([key, rows]) => [key, Array.isArray(rows) ? rows.length : 0]))
  });
}

export function clearSeasonTrendResult(): void {
  lastSeasonTrendResult = null;
  if (typeof window !== "undefined") {
    removeItem("session", SEASON_TREND_RESULT_STORAGE_KEY);
    removeItem("session", CURRENT_SEASON_TREND_READY_STORAGE_KEY);
    removeItem("session", SEASON_TREND_STORAGE_VERSION_KEY);
  }
  void deleteSeasonTrendResultFromDb();
  emitAnalysisResultChanged();
}

/** Account/entity switches must not retain rows, job ids or IndexedDB results
 * created in a previous authorization scope. */
export async function clearSensitiveAnalysisState(): Promise<void> {
  clearLastAnalysisResult();
  clearSeasonTrendResult();
  latestOrderReviewMeta = null;
  latestOrderReviewRawRows = null;
  latestOrderReviewEtaRows = null;
  if (typeof window !== "undefined") {
    SENSITIVE_LOCAL_STORAGE_KEYS.forEach((key) => removeItem("local", key));
    SENSITIVE_SESSION_STORAGE_KEYS.forEach((key) => removeItem("session", key));
  }
  await Promise.all([deleteAnalysisResultFromDb(), deleteSeasonTrendResultFromDb()]);
}

export async function saveSeasonTrendResult(result: SeasonTrendAnalyzeResponse): Promise<void> {
  result = withActiveEntityScope(result);
  result = normalizeSeasonTrendResponse(result);
  lastSeasonTrendResult = result;
  if (typeof window !== "undefined") {
    const persistResult = shouldPersistSeasonTrendResult(result);
    if (persistResult) {
      await writeSeasonTrendResultToDb(result);
    } else {
      // High-cardinality HQ/USA cubes can be hundreds of MB. IndexedDB's
      // structured clone and JSON serialization both block the browser main
      // thread long enough to trigger "page unresponsive". Keep those results
      // in memory for the active session; the backend remains the durable copy.
      await deleteSeasonTrendResultFromDb();
    }
    try {
      if (persistResult) {
        const serialized = JSON.stringify(result);
        if (serialized.length >= 4_000_000) {
          removeItem("session", SEASON_TREND_RESULT_STORAGE_KEY);
        } else if (!writeRawItem("session", SEASON_TREND_RESULT_STORAGE_KEY, serialized)) {
          throw new Error("season-trend-result-write-failed");
        }
      } else {
        removeItem("session", SEASON_TREND_RESULT_STORAGE_KEY);
      }
      if (!writeRawItem("session", SEASON_TREND_STORAGE_VERSION_KEY, SEASON_TREND_STORAGE_VERSION)) {
        throw new Error("season-trend-version-write-failed");
      }
      if (!writeRawItem("session", CURRENT_SEASON_TREND_READY_STORAGE_KEY, "1")) {
        throw new Error("season-trend-ready-write-failed");
      }
    } catch {
      removeItem("session", SEASON_TREND_RESULT_STORAGE_KEY);
      writeRawItem("session", SEASON_TREND_STORAGE_VERSION_KEY, SEASON_TREND_STORAGE_VERSION);
      writeRawItem("session", CURRENT_SEASON_TREND_READY_STORAGE_KEY, "1");
    }
    emitAnalysisResultChanged();
    return;
  }
  await writeSeasonTrendResultToDb(result);
  emitAnalysisResultChanged();
}
