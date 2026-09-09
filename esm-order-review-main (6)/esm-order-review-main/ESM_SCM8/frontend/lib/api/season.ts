import type { BrandReportAggregate, SeasonTrendAnalyzeResponse } from "@/types/api";
import { getActiveEntityCode } from "@/lib/entity-session";
import { cachedSeasonResultIsCurrent, koreaTodayString } from "@/lib/season-cache-validity";
import { apiFetch, ApiRequestError, clientHeaders, FASTAPI_BASE_URL, parseApiError } from "./client";
import { requestContextHeaders } from "./request-context";
import { normalizeSeasonTrendResponse } from "./season-normalize";
import { getStoredSeasonTrendResult, saveSeasonTrendResult } from "./storage";

const API_ANALYSIS_JOB_POLL_INTERVAL_MS = 1500;
const API_ANALYSIS_JOB_TIMEOUT_MS = 35 * 60 * 1000;
const API_ANALYSIS_SCHEMA_VERSION = 13;
const ANALYSIS_DELAYED_MESSAGE = "서버 응답이 지연되었습니다. 잠시 후 다시 분석을 눌러주세요.";

const API_CACHE_OPTION_KEYS = [
  "start_date",
  "end_date",
  "metric",
  "group_by",
  "eu_local",
  "include_ingredient",
  "exclude_partial_months",
  "warehouse"
] as const;

function apiAnalysisOptions(options: {
  startDate: string;
  endDate: string;
  metric?: "qty" | "amount";
  groupBy?: "month" | "quarter" | "year";
  includeIngredient?: boolean;
  excludePartialMonths?: boolean;
  warehouse?: string | null;
}) {
  return {
    start_date: options.startDate,
    end_date: options.endDate,
    metric: options.metric ?? "qty",
    group_by: options.groupBy ?? "month",
    eu_local: true,
    include_ingredient: options.includeIngredient ?? true,
    exclude_partial_months: options.excludePartialMonths ?? true,
    warehouse: options.warehouse?.trim().toUpperCase() || null
  };
}

function matchesApiAnalysisOptions(result: SeasonTrendAnalyzeResponse | null, expected: ReturnType<typeof apiAnalysisOptions>) {
  const actual = result?.analysis_options as Record<string, unknown> | undefined;
  const dataSource = (result as (SeasonTrendAnalyzeResponse & { data_source?: string }) | null)?.data_source;
  if (
    !actual ||
    dataSource !== "source_api" ||
    Number(result?.analysis_schema_version ?? 0) < API_ANALYSIS_SCHEMA_VERSION
  ) return false;
  // 기간이 오늘을 포함한 채 계산된 결과는 마지막 하루가 미완성이므로 날짜가
  // 바뀌면 재사용하지 않는다. 이 층은 백엔드를 호출하지 않으므로 여기서도
  // 서버와 같은 규칙을 적용해야 한다.
  if (
    !cachedSeasonResultIsCurrent({
      computedDate: (result as (SeasonTrendAnalyzeResponse & { computed_date?: string }) | null)?.computed_date,
      endDate: String(actual.end_date ?? "") || null,
      today: koreaTodayString()
    })
  ) {
    return false;
  }
  return API_CACHE_OPTION_KEYS.every((key) => {
    if (key === "eu_local" && actual[key] === undefined) {
      return expected[key] === true;
    }
    if ((key === "start_date" || key === "end_date") && actual.exclude_partial_months === true && expected.exclude_partial_months === true) {
      return String(actual[key] ?? "").slice(0, 7) === String(expected[key] ?? "").slice(0, 7);
    }
    return actual[key] === expected[key];
  });
}

export async function analyzeSeasonTrendFiles(filesByRole: {
  sales_history?: File;
  prod_list?: File;
  category_correction?: File;
}, options: {
  startDate?: string;
  endDate?: string;
  metric?: "qty" | "amount";
  groupBy?: "month" | "quarter" | "year";
  includeIngredient?: boolean;
  excludePartialMonths?: boolean;
  onUploadProgress?: (progress: { loaded: number; total?: number; percent?: number }) => void;
} = {}): Promise<SeasonTrendAnalyzeResponse> {
  const formData = new FormData();

  if (filesByRole.sales_history) {
    formData.append("files", filesByRole.sales_history);
    formData.append("roles", "sales_history");
  }
  if (filesByRole.prod_list) {
    formData.append("files", filesByRole.prod_list);
    formData.append("roles", "prod_list");
  }
  if (filesByRole.category_correction) {
    formData.append("files", filesByRole.category_correction);
    formData.append("roles", "category_correction");
  }
  if (options.startDate) {
    formData.append("start_date", options.startDate);
  }
  if (options.endDate) {
    formData.append("end_date", options.endDate);
  }
  if (options.metric) {
    formData.append("metric", options.metric);
  }
  if (options.groupBy) {
    formData.append("group_by", options.groupBy);
  }
  if (typeof options.includeIngredient === "boolean") {
    formData.append("include_ingredient", String(options.includeIngredient));
  }
  formData.append("exclude_partial_months", String(options.excludePartialMonths ?? true));

  const result = normalizeSeasonTrendResponse(await postSeasonTrendFormData(formData, options.onUploadProgress));
  await saveSeasonTrendResult(result);
  return result;
}

export async function analyzeSeasonTrendFromApi(options: {
  startDate: string;
  endDate: string;
  metric?: "qty" | "amount";
  groupBy?: "month" | "quarter" | "year";
  includeIngredient?: boolean;
  excludePartialMonths?: boolean;
  warehouse?: string | null;
}, controls: {
  signal?: AbortSignal;
  onJobStarted?: (jobId: string) => void;
  onStatusChange?: (status: "queued" | "running") => void;
} = {}): Promise<SeasonTrendAnalyzeResponse> {
  const expectedOptions = apiAnalysisOptions(options);
  const cached = await getStoredSeasonTrendResult();
  if (cached && matchesApiAnalysisOptions(cached, expectedOptions)) {
    return cached;
  }

  const requestBody = {
    start_date: expectedOptions.start_date,
    end_date: expectedOptions.end_date,
    metric: expectedOptions.metric,
    group_by: expectedOptions.group_by,
    include_ingredient: expectedOptions.include_ingredient,
    exclude_partial_months: expectedOptions.exclude_partial_months,
    warehouse: expectedOptions.warehouse
  };

  const response = await apiFetch(`${FASTAPI_BASE_URL}/season-trend/analyze-api/jobs`, {
    method: "POST",
    headers: {
      ...clientHeaders(),
      "Content-Type": "application/json"
    },
    signal: controls.signal,
    body: JSON.stringify(requestBody)
  });
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
  const started = (await response.json()) as {
    job_id?: string | null;
    status?: string;
    result?: SeasonTrendAnalyzeResponse;
  };
  if (started.job_id) {
    controls.onJobStarted?.(started.job_id);
  }
  if (started.status === "queued") {
    controls.onStatusChange?.("queued");
  }
  const result =
    started.status === "succeeded" && started.result
      ? normalizeSeasonTrendResponse(started.result)
      : await pollSeasonTrendApiJob(
          started.job_id || "",
          controls.signal,
          controls.onStatusChange
        );
  await saveSeasonTrendResult(result);
  return result;
}

async function pollSeasonTrendApiJob(
  jobId: string,
  signal?: AbortSignal,
  onStatusChange?: (status: "queued" | "running") => void
): Promise<SeasonTrendAnalyzeResponse> {
  if (!jobId) {
    throw new ApiRequestError("분석 작업을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.", 500);
  }
  const startedAt = Date.now();
  while (Date.now() - startedAt < API_ANALYSIS_JOB_TIMEOUT_MS) {
    await delay(API_ANALYSIS_JOB_POLL_INTERVAL_MS, signal);
    const response = await apiFetch(`${FASTAPI_BASE_URL}/season-trend/analyze-api/jobs/${encodeURIComponent(jobId)}`, {
      headers: clientHeaders(),
      signal
    });
    if (!response.ok) {
      throw new ApiRequestError(await parseApiError(response), response.status);
    }
    const job = (await response.json()) as {
      status?: string;
      status_code?: number;
      error?: string;
      result?: SeasonTrendAnalyzeResponse;
    };
    if (job.status === "queued" || job.status === "running") {
      onStatusChange?.(job.status);
    }
    if (job.status === "succeeded" && job.result) {
      return normalizeSeasonTrendResponse(job.result);
    }
    if (job.status === "failed") {
      const status = Number(job.status_code || 500);
      throw new ApiRequestError(status === 504 ? ANALYSIS_DELAYED_MESSAGE : job.error || "수요 분석 작업이 실패했습니다.", status);
    }
    if (job.status === "cancelled") {
      throw new DOMException("분석 요청이 취소되었습니다.", "AbortError");
    }
  }
  throw new ApiRequestError(ANALYSIS_DELAYED_MESSAGE, 408);
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  if (!signal) return new Promise((resolve) => window.setTimeout(resolve, ms));
  if (signal.aborted) return Promise.reject(new DOMException("분석 요청이 취소되었습니다.", "AbortError"));
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("분석 요청이 취소되었습니다.", "AbortError"));
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export async function cancelSeasonTrendAnalysis(jobId: string): Promise<void> {
  const response = await apiFetch(
    `${FASTAPI_BASE_URL}/season-trend/analyze-api/jobs/${encodeURIComponent(jobId)}`,
    { method: "DELETE", headers: clientHeaders() }
  );
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
}

export async function fetchLatestSeasonTrendResult(): Promise<SeasonTrendAnalyzeResponse | null> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/season-trend/latest`, {
    headers: clientHeaders()
  });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
  const result = (await response.json()) as SeasonTrendAnalyzeResponse;
  return normalizeSeasonTrendResponse(result);
}

export async function fetchBrandReportData(): Promise<{
  brandReports: BrandReportAggregate[];
  monthCoverage: SeasonTrendAnalyzeResponse["season_analysis"]["monthCoverage"];
  dataQuality: SeasonTrendAnalyzeResponse["season_analysis"]["sourceDataQuality"];
  analysisOptions: SeasonTrendAnalyzeResponse["analysis_options"];
} | null> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/season-trend/brand-reports`, { headers: clientHeaders() });
  if (response.status === 404) return null;
  if (!response.ok) throw new ApiRequestError(await parseApiError(response), response.status);
  return await response.json() as {
    brandReports: BrandReportAggregate[];
    monthCoverage: SeasonTrendAnalyzeResponse["season_analysis"]["monthCoverage"];
    dataQuality: SeasonTrendAnalyzeResponse["season_analysis"]["sourceDataQuality"];
    analysisOptions: SeasonTrendAnalyzeResponse["analysis_options"];
  };
}

function postSeasonTrendFormData(
  formData: FormData,
  onUploadProgress?: (progress: { loaded: number; total?: number; percent?: number }) => void
) {
  return new Promise<SeasonTrendAnalyzeResponse>((resolve, reject) => {
    const requestEntityCode = getActiveEntityCode();
    const request = new XMLHttpRequest();
    request.open("POST", `${FASTAPI_BASE_URL}/season-trend/analyze`);

    const headers = requestContextHeaders();
    Object.entries(headers).forEach(([key, value]) => {
      request.setRequestHeader(key, String(value));
    });

    request.upload.onprogress = (event) => {
      if (!onUploadProgress) {
        return;
      }
      const total = event.lengthComputable ? event.total : undefined;
      onUploadProgress({
        loaded: event.loaded,
        total,
        percent: total ? Math.min(100, Math.round((event.loaded / total) * 100)) : undefined
      });
    };

    request.onload = () => {
      if (getActiveEntityCode() !== requestEntityCode) {
        reject(new Error("법인이 변경되어 이전 법인의 시즌 분석 응답을 폐기했습니다."));
        return;
      }
      if (request.status < 200 || request.status >= 300) {
        reject(new ApiRequestError(parseXhrError(request), request.status));
        return;
      }
      try {
        resolve(JSON.parse(request.responseText) as SeasonTrendAnalyzeResponse);
      } catch {
        reject(new Error("분석 응답을 해석하지 못했습니다."));
      }
    };

    request.onerror = () => reject(new Error("Failed to fetch"));
    request.onabort = () => reject(new Error("분석 요청이 취소되었습니다."));
    request.send(formData);
  });
}

function parseXhrError(request: XMLHttpRequest) {
  try {
    const body = JSON.parse(request.responseText) as {
      detail?: unknown;
      error?: { message?: unknown };
    };
    if (typeof body.error?.message === "string") {
      return body.error.message;
    }
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (body.detail) {
      return JSON.stringify(body.detail);
    }
  } catch {
    // Fallback below.
  }
  return request.statusText || `HTTP ${request.status}`;
}
