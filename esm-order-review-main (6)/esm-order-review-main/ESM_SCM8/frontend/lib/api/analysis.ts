import type {
  AnalysisJobStartResponse,
  AnalysisJobStatusResponse,
  AnalyzeResponse,
  ClassifyResponse,
  UploadRole
} from "@/types/api";
import type { LeadTimeOverrides } from "@/lib/lead-times";
import {
  apiFetch,
  ApiRequestError,
  clientHeaders,
  FASTAPI_BASE_URL,
  FASTAPI_UPLOAD_BASE_URL,
  parseApiError,
  ROLE_ORDER,
  wait
} from "./client";
import { getActiveEntityCode } from "@/lib/entity-session";

export async function startMockAnalysis(): Promise<{
  jobId: string;
  status: "queued" | "success";
  message: string;
}> {
  await wait(600);
  return {
    jobId: `mock_${Date.now()}`,
    status: "success",
    message: "Mock 분석이 완료되었습니다. 실제 연결 시 FastAPI /api/analyze 응답으로 대체됩니다."
  };
}

export type AnalyzeOptions = {
  eurKrwRate?: number;
  safetyMonths?: number;
  skuShortageThresholdPct?: number;
  skuOverstockThresholdPct?: number;
  leadTimeOverrides?: LeadTimeOverrides;
};

export type AnalysisRequestControls = {
  signal?: AbortSignal;
  onJobStarted?: (jobId: string) => void;
};

type CmsAnalyzeRequestBody = {
  as_of: string;
  eur_krw_rate?: number;
  safety_months?: number;
  sku_shortage_threshold_pct?: number;
  sku_overstock_threshold_pct?: number;
  lead_time_overrides?: LeadTimeOverrides;
};

const CMS_ANALYSIS_JOB_POLL_INTERVAL_MS = 1_500;
const CMS_ANALYSIS_JOB_TIMEOUT_MS = 15 * 60 * 1000;

type CmsAnalysisJobStartResponse = AnalysisJobStartResponse & {
  result?: AnalyzeResponse;
};

type CmsAnalysisJobStatusResponse = AnalysisJobStatusResponse & {
  status_code?: number;
  error?: string;
  result?: AnalyzeResponse;
};

const ANALYSIS_DELAYED_MESSAGE = "서버 응답이 지연되었습니다. 잠시 후 다시 분석을 눌러주세요.";

function perfLog(message: string, fields: Record<string, unknown> = {}) {
  if (typeof window === "undefined") {
    return;
  }
  console.info(`[perf][analysis-client] ${message}`, fields);
}

function appendAnalyzeOptions(formData: FormData, options: AnalyzeOptions) {
  if (options.eurKrwRate !== undefined) {
    formData.append("eur_krw_rate", String(options.eurKrwRate));
  }
  if (options.safetyMonths !== undefined) {
    formData.append("safety_months", String(options.safetyMonths));
  }
  if (options.skuShortageThresholdPct !== undefined) {
    formData.append("sku_shortage_threshold_pct", String(options.skuShortageThresholdPct));
  }
  if (options.skuOverstockThresholdPct !== undefined) {
    formData.append("sku_overstock_threshold_pct", String(options.skuOverstockThresholdPct));
  }
  if (options.leadTimeOverrides !== undefined) {
    formData.append("lead_time_overrides", JSON.stringify(options.leadTimeOverrides));
  }
}

export async function classifyFiles(files: File[]): Promise<ClassifyResponse> {
  const formData = new FormData();

  for (const file of files) {
    formData.append("files", file);
  }

  const response = await apiFetch(`${FASTAPI_UPLOAD_BASE_URL}/classify`, {
    method: "POST",
    headers: clientHeaders(),
    body: formData
  });

  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }

  return response.json() as Promise<ClassifyResponse>;
}

export async function analyzeFileList(
  files: File[],
  roles: UploadRole[],
  options: AnalyzeOptions = {}
): Promise<AnalyzeResponse> {
  const startedAt = performance.now();
  const formData = new FormData();

  files.forEach((file, index) => {
    formData.append("files", file);
    formData.append("roles", roles[index]);
  });

  appendAnalyzeOptions(formData, options);

  const response = await apiFetch(`${FASTAPI_UPLOAD_BASE_URL}/analyze`, {
    method: "POST",
    headers: clientHeaders(),
    body: formData
  });
  perfLog("upload_quick_fetch_done", { seconds: Number(((performance.now() - startedAt) / 1000).toFixed(3)), fileCount: files.length });

  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }

  const parseStartedAt = performance.now();
  const payload = (await response.json()) as AnalyzeResponse;
  perfLog("upload_quick_json_done", { seconds: Number(((performance.now() - parseStartedAt) / 1000).toFixed(3)), jobId: payload.job_id });
  return payload;
}

export async function analyzeFiles(
  filesByRole: Partial<Record<UploadRole, File>>,
  options: AnalyzeOptions = {}
): Promise<AnalyzeResponse> {
  const startedAt = performance.now();
  const formData = new FormData();

  for (const role of ROLE_ORDER) {
    const file = filesByRole[role];
    if (file) {
      formData.append("files", file);
      formData.append("roles", role);
    }
  }

  appendAnalyzeOptions(formData, options);

  const response = await apiFetch(`${FASTAPI_BASE_URL}/analyze`, {
    method: "POST",
    headers: clientHeaders(),
    body: formData
  });
  perfLog("upload_manual_fetch_done", { seconds: Number(((performance.now() - startedAt) / 1000).toFixed(3)), fileCount: Object.values(filesByRole).filter(Boolean).length });

  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }

  const parseStartedAt = performance.now();
  const payload = (await response.json()) as AnalyzeResponse;
  perfLog("upload_manual_json_done", { seconds: Number(((performance.now() - parseStartedAt) / 1000).toFixed(3)), jobId: payload.job_id });
  return payload;
}

export async function analyzeFromCms(
  asOf: string,
  options: AnalyzeOptions = {},
  controls: AnalysisRequestControls = {}
): Promise<AnalyzeResponse> {
  const startedAt = performance.now();
  const response = await apiFetch(`${FASTAPI_BASE_URL}/analyze/cms/jobs`, {
    method: "POST",
    headers: { ...clientHeaders(), "Content-Type": "application/json" },
    signal: controls.signal,
    body: JSON.stringify(cmsAnalyzeRequestBody(asOf, options))
  });
  perfLog("cms_job_start_done", { seconds: Number(((performance.now() - startedAt) / 1000).toFixed(3)), asOf });

  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }

  const started = (await response.json()) as CmsAnalysisJobStartResponse;
  if (started.job_id) {
    controls.onJobStarted?.(started.job_id);
  }
  const payload =
    started.status === "succeeded" && started.result
      ? started.result
      : await pollCmsAnalysisJob(started.job_id || "", controls.signal);
  perfLogCmsResult(payload, startedAt);
  return payload;
}

function cmsAnalyzeRequestBody(asOf: string, options: AnalyzeOptions): CmsAnalyzeRequestBody {
  return {
    as_of: asOf,
    eur_krw_rate: options.eurKrwRate,
    safety_months: options.safetyMonths,
    sku_shortage_threshold_pct: options.skuShortageThresholdPct,
    sku_overstock_threshold_pct: options.skuOverstockThresholdPct,
    lead_time_overrides: options.leadTimeOverrides
  };
}

async function pollCmsAnalysisJob(jobId: string, signal?: AbortSignal): Promise<AnalyzeResponse> {
  if (!jobId) {
    throw new ApiRequestError("발주분석 작업을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.", 500);
  }
  const startedAt = Date.now();
  while (Date.now() - startedAt < CMS_ANALYSIS_JOB_TIMEOUT_MS) {
    await abortableWait(CMS_ANALYSIS_JOB_POLL_INTERVAL_MS, signal);
    const response = await apiFetch(`${FASTAPI_BASE_URL}/analyze/cms/jobs/${encodeURIComponent(jobId)}`, {
      headers: clientHeaders(),
      signal
    });
    if (!response.ok) {
      throw new ApiRequestError(await parseApiError(response), response.status);
    }
    const job = (await response.json()) as CmsAnalysisJobStatusResponse;
    if (job.status === "succeeded" && job.result) {
      return job.result;
    }
    if (job.status === "failed") {
      const status = Number(job.status_code || 500);
      throw new ApiRequestError(status === 504 ? ANALYSIS_DELAYED_MESSAGE : job.error || "발주분석 작업이 실패했습니다.", status);
    }
    if (job.status === "cancelled") {
      throw new DOMException("분석 요청이 취소되었습니다.", "AbortError");
    }
  }
  throw new ApiRequestError(ANALYSIS_DELAYED_MESSAGE, 408);
}

export async function cancelCmsAnalysis(jobId: string): Promise<void> {
  const response = await apiFetch(
    `${FASTAPI_BASE_URL}/analyze/cms/jobs/${encodeURIComponent(jobId)}`,
    { method: "DELETE", headers: clientHeaders() }
  );
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
}

function abortableWait(ms: number, signal?: AbortSignal): Promise<void> {
  if (!signal) return wait(ms);
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

function perfLogCmsResult(payload: AnalyzeResponse, startedAt: number) {
  perfLog("cms_result_ready", {
    seconds: Number(((performance.now() - startedAt) / 1000).toFixed(3)),
    jobId: payload.job_id
  });
  if (payload.cms_fetch_cache) {
    perfLog("cms_fetch_cache", {
      jobId: payload.job_id,
      hit: payload.cms_fetch_cache.hit,
      source: payload.cms_fetch_cache.source,
      createdAt: payload.cms_fetch_cache.created_at,
      ageSeconds: payload.cms_fetch_cache.age_seconds,
      ttlSeconds: payload.cms_fetch_cache.ttl_seconds
    });
  }
}

export function downloadHref(resultOrJobId: Pick<AnalyzeResponse, "download_url" | "job_id"> | string): string {
  const withEntity = (url: string) => {
    const entityCode = getActiveEntityCode();
    if (!entityCode) return url;
    return `${url}${url.includes("?") ? "&" : "?"}entity=${encodeURIComponent(entityCode)}`;
  };
  if (typeof resultOrJobId !== "string") {
    const downloadUrl = resultOrJobId.download_url;
    if (/^https?:\/\//.test(downloadUrl)) {
      return withEntity(downloadUrl);
    }
    if (downloadUrl.startsWith("/api/")) {
      return withEntity(`${FASTAPI_BASE_URL}${downloadUrl.slice(4)}`);
    }
    if (downloadUrl.startsWith("/")) {
      return withEntity(downloadUrl);
    }
    return withEntity(`${FASTAPI_BASE_URL}/${downloadUrl.replace(/^\/+/, "")}`);
  }

  return withEntity(`${FASTAPI_BASE_URL}/download/${encodeURIComponent(resultOrJobId)}`);
}
