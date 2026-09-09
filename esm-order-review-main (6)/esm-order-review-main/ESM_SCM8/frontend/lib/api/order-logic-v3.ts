import {
  apiFetch,
  ApiRequestError,
  clientHeaders,
  FASTAPI_BASE_URL,
  isAbortError,
  parseApiError,
  wait
} from "./client";
import type { EntityCode } from "../entities";
import { getActiveEntityCode } from "../entity-session";

export type OrderLogicV3Blocker = {
  code: string;
  area: string;
  message: string;
};

export type OrderLogicV3ApiRow = {
  sku_code: string;
  product_name?: string;
  brand?: string;
  barcode?: string;
  product_identity_source_codes?: string[];
  product_identity_reason_code?: string | null;
  /** Descriptive 91-day metrics aligned with V3's 13 completed weeks. */
  reference_sales_start?: string;
  reference_sales_end?: string;
  reference_sales_days?: number;
  reference_sales_status?: "AVAILABLE" | "INVALID_SOURCE";
  reference_sales_13w?: number | null;
  reference_monthly_sales?: number | null;
  reference_monthly_sales_raw?: number | null;
  reference_weekly_sales?: number | null;
  reference_weekly_sales_history?: number[] | null;
  reference_weekly_sigma?: number | null;
  reference_moi?: number | null;
  reference_logistics_moi?: number | null;
  reference_depletion_weeks?: number | null;
  reference_order_slack_weeks?: number | null;
  reference_conservative_slack_weeks?: number | null;
  reference_early_warning_at?: string | null;
  reference_order_at?: string | null;
  eta_reference_status?: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | "INVALID_SOURCE" | "SOURCE_MISMATCH" | "NOT_APPLICABLE";
  eta_week_start?: string;
  /** Overdue, thirteen Monday-based weeks, then >= Monday+91 days. */
  eta_bucket_quantities?: number[] | null;
  eta_missing_qty?: number | null;
  next_eta?: string | null;
  shipping_eta_details?: Array<{
    eta: string | null; qty: number; eta_status: string;
    ship_date: string | null; transport_mode: string | null; lead_time_days: number | null;
  }>;
  unit_price_krw?: number | null;
  unit_price_local?: number | null;
  /** Server-valued raw proposal in local_currency; no display rounding or FX. */
  order_amount_local?: number | null;
  local_currency?: "EUR" | "USD" | "KRW";
  /** False means no source row in the query window, not a confirmed zero. */
  inbound_status_source_present?: boolean | null;
  open_po_qty?: number | null;
  pnfm_qty?: number | null;
  inbound_progress_qty?: number | null;
  inbound_completed_qty?: number | null;
  calculable: boolean;
  reason_code?: string | null;
  validation_error?: string | null;
  inventory_validation_error?: string | null;
  inventory_warnings?: string[];
  inventory_warning_messages?: string[];
  data_status?: string;
  pattern?: string | null;
  engine?: string | null;
  seasonal_applied?: boolean;
  adjusted_period_sales?: number[];
  original_period_sales?: number[];
  adjusted_forecast?: number[];
  demand_per_period?: number | null;
  forecast_rmse?: number | null;
  forecast_sigma?: number | null;
  croston_forecast_cap_per_period?: number | null;
  croston_forecast_was_capped?: boolean | null;
  inventory_position?: number | null;
  target_stock?: number | null;
  reorder_point?: number | null;
  raw_order_quantity?: number | null;
  /** CMS master pack sizes; null when unset (~48%/66% of SKUs). */
  inbox_quantity?: number | null;
  outbox_quantity?: number | null;
  /** Applied order-unit ceiling: OUTBOX -> INBOX -> FALLBACK_10. */
  order_unit_quantity?: number | null;
  order_unit_source?: "OUTBOX" | "INBOX" | "FALLBACK_10" | null;
  /** Pack-rounded final quantity; 0 raw stays 0. Null on blocked rows. */
  final_order_quantity?: number | null;
  order_signal?: string;
  order_amount_krw?: number | null;
  adi?: number | null;
  cv2?: number | null;
  trend_signal?: number | null;
  z_value?: number | null;
  z_policy?: "CASH" | "SHORTAGE" | null;
  first_sale_date?: string | null;
  analysis_sales_cutoff?: string | null;
  calendar_days_since_first_sale?: number | null;
  is_new_sku?: boolean | null;
  layer1?: number | null;
  layer2_raw?: number | null;
  layer2?: number | null;
  safety_stock_floor?: number | null;
  safety_stock_cap?: number | null;
  layer3?: number | null;
  lead_time_days?: number | null;
  lead_time_weeks?: number | null;
  lead_time_periods?: number | null;
  review_days?: number | null;
  review_weeks?: number | null;
  review_periods?: number | null;
  sigma_lead_time_days?: number | null;
  sigma_lead_time_weeks?: number | null;
  sigma_lead_time_periods?: number | null;
  safety_stock_floor_days?: number | null;
  safety_stock_floor_weeks?: number | null;
  safety_stock_floor_periods?: number | null;
  safety_stock_cap_days?: number | null;
  safety_stock_cap_weeks?: number | null;
  safety_stock_cap_periods?: number | null;
  on_hand_qty?: number | null;
  upstream_available_qty?: number | null;
  in_transit_qty?: number | null;
  unreceived_qty?: number | null;
  holding_qty?: number | null;
  transport_mode?: string | null;
  lead_time_source?: string | null;
  lead_time_sample_size?: number | null;
  lead_time_completion_from?: string | null;
  lead_time_completion_to?: string | null;
  alpha?: number | null;
  beta?: number | null;
  phi?: number | null;
  season_factor_version?: string | null;
  season_factor_available?: boolean | null;
  function_class_1_code?: string | null;
  function_class_2_code?: string | null;
  season_factor_scope?: "FUNCTION_CLASS_1_AND_2" | "FUNCTION_CLASS_1" | null;
  season_factor_application_reason_code?: string | null;
  season_factor_original_reason_code?: string | null;
  season_factor_original_message?: string | null;
  season_factor_function_class_1_code?: string | null;
  season_factor_function_class_2_code?: string | null;
  seasonal_f1?: number | null;
  seasonal_f2?: number | null;
  seasonal_f_lr?: number | null;
  season_factor_artifact_status?: string | null;
  seasonality_status?: string | null;
  season_factor_reason_code?: string | null;
  season_factor_window_start?: string | null;
  season_factor_window_end?: string | null;
  season_factors_by_month?: Record<string, number> | null;
  inventory_source_status?: string | null;
  inventory_source_missing_fields?: string[] | null;
};

export type OrderLogicV3Result = {
  status: "blocked" | "success";
  job_id: string;
  logic_version: string;
  result_schema_version: number;
  preview: true;
  entity_code: "HQ" | "PL" | "USA";
  date_basis?: "SOURCE_CALENDAR_DATE";
  as_of: string;
  calculated_at: string;
  period_start: string;
  period_end: string;
  period_count: number;
  period_days: number;
  /** Calendar-day duration metadata; missing only on pre-standardization snapshots. */
  duration_unit?: "CALENDAR_DAY";
  observation_window_days?: number;
  demand_grain?: "WEEK_7D" | "PERIOD_28D";
  demand_grain_days?: number;
  source_snapshot_id?: string | null;
  source_fetched_at?: string | null;
  source_audit?: {
    demand_source?: { policy?: string; path?: string; included_types?: string[]; quantity_field?: string };
    grade_rule?: string;
  };
  season_factor_versions?: string[];
  calculation_parameters?: Record<string, unknown>;
  order_constraint_status: "ORDER_CONSTRAINTS_PENDING" | "PACK_ROUNDING_APPLIED";
  order_unit_policy?: Record<string, unknown>;
  summary: {
    total_sku_count: number;
    calculable_sku_count: number;
    blocked_sku_count: number;
    raw_order_quantity: number;
    final_order_quantity: number | null;
  };
  rows: OrderLogicV3ApiRow[];
  scenarios: Record<"CASH" | "SHORTAGE", { rows: OrderLogicV3ApiRow[] }>;
  blocking_contracts: OrderLogicV3Blocker[];
  warnings: string[];
  analysis_ledger?: Record<string, unknown>;
};

type JobStartResponse = { job_id: string; status: string };
type JobStatusResponse = JobStartResponse & {
  result?: OrderLogicV3Result;
  status_code?: number;
  error?: string;
  result_delivery?: "paged-v1" | null;
};

const POLL_INTERVAL_MS = 1_000;
const TRANSIENT_STATUS_CODES = new Set([500, 502, 503, 504]);
const STATUS_RETRY_DELAYS_MS = [500, 1_000, 2_000];
const RESULT_REQUEST_TIMEOUT_MS = 30_000;
// A cold 24-completed-month CMS snapshot can take several minutes. The job is
// already asynchronous, so keep polling long enough for the first uncached run.
const POLL_TIMEOUT_MS = 15 * 60 * 1_000;

export class OrderLogicV3ConnectionError extends Error {
  constructor(public jobId: string) {
    super("서버와의 연결이 지연되고 있습니다. 같은 분석에 자동으로 다시 연결합니다.");
    this.name = "OrderLogicV3ConnectionError";
  }
}

async function readJobJson<T>(url: string, jobId: string, signal: AbortSignal | undefined, assertActive: () => void): Promise<T> {
  for (let attempt = 0; ; attempt += 1) {
    assertActive();
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, RESULT_REQUEST_TIMEOUT_MS);
    try {
      const response = await apiFetch(url, { headers: clientHeaders(), signal: controller.signal });
      if (!response.ok) throw new ApiRequestError(await parseApiError(response), response.status);
      // Reading the body can also disconnect after HTTP headers arrive.
      const payload = await response.json() as T;
      assertActive();
      return payload;
    } catch (error) {
      assertActive();
      if (isAbortError(error) && !timedOut) throw error;
      if (error instanceof ApiRequestError && !TRANSIENT_STATUS_CODES.has(error.status)) throw error;
      if (attempt >= STATUS_RETRY_DELAYS_MS.length) throw new OrderLogicV3ConnectionError(jobId);
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
    }
    await wait(STATUS_RETRY_DELAYS_MS[attempt]);
  }
}

type ResultPage = {
  job_id: string; entity_code: EntityCode; snapshot_id?: string | null;
  offset: number; next_offset: number | null; total: number;
  row_alias?: "CASH" | "SHORTAGE" | null;
  counts: Record<"rows" | "CASH" | "SHORTAGE", number>;
  result?: OrderLogicV3Result;
  rows: OrderLogicV3ApiRow[];
  scenarios: OrderLogicV3Result["scenarios"];
};

async function receiveResultPages(
  jobId: string, entityCode: EntityCode, signal: AbortSignal | undefined,
  assertActive: () => void, onProgress?: (received: number, total: number) => void,
): Promise<OrderLogicV3Result> {
  let result: OrderLogicV3Result | undefined;
  let counts: ResultPage["counts"] | undefined;
  let offset = 0;
  let rowAlias: ResultPage["row_alias"] = null;
  for (;;) {
    const page = await readJobJson<ResultPage>(
      `${FASTAPI_BASE_URL}/order-logic-v3/jobs/${encodeURIComponent(jobId)}/result?offset=${offset}`, jobId, signal, assertActive,
    );
    const invalid = () => new ApiRequestError("분석 결과의 작업·법인·수신 범위가 일치하지 않습니다. 다시 분석해 주세요.", 409);
    if (page.job_id !== jobId || page.entity_code !== entityCode || page.offset !== offset || !page.counts) throw invalid();
    if (offset === 0) {
      result = page.result;
      counts = page.counts;
      rowAlias = page.row_alias ?? null;
      if (!result || result.job_id !== jobId || result.entity_code !== entityCode) throw invalid();
      if (rowAlias) {
        if (!["CASH", "SHORTAGE"].includes(rowAlias) || counts.rows !== counts[rowAlias]) throw invalid();
        result.rows = result.scenarios[rowAlias].rows;
      }
    }
    if (!result || !counts || page.snapshot_id !== result.source_snapshot_id || (page.row_alias ?? null) !== rowAlias) throw invalid();
    for (const key of ["rows", "CASH", "SHORTAGE"] as const) {
      if (!Number.isSafeInteger(page.counts[key]) || page.counts[key] < 0 || page.counts[key] !== counts[key]) throw invalid();
    }
    if (page.total !== Math.max(counts.rows, counts.CASH, counts.SHORTAGE)) throw invalid();
    const end = page.next_offset ?? page.total;
    if (!Number.isSafeInteger(end) || end < offset || end > page.total || (page.next_offset !== null && end <= offset)) throw invalid();
    const arrays = { rows: page.rows, CASH: page.scenarios?.CASH?.rows, SHORTAGE: page.scenarios?.SHORTAGE?.rows };
    for (const key of ["rows", "CASH", "SHORTAGE"] as const) {
      const expected = key === "rows" && rowAlias ? 0 : Math.max(0, Math.min(end, counts[key]) - offset);
      if (!Array.isArray(arrays[key]) || arrays[key].length !== expected) throw invalid();
    }
    if (!rowAlias) result.rows.push(...page.rows);
    result.scenarios.CASH.rows.push(...page.scenarios.CASH.rows);
    result.scenarios.SHORTAGE.rows.push(...page.scenarios.SHORTAGE.rows);
    onProgress?.(end, page.total);
    if (page.next_offset === null) {
      if (result.rows.length !== counts.rows || result.scenarios.CASH.rows.length !== counts.CASH || result.scenarios.SHORTAGE.rows.length !== counts.SHORTAGE) throw invalid();
      return result;
    }
    offset = end;
  }
}

export class OrderLogicV3CancellationError extends Error {
  constructor(public jobId: string) {
    super("서버의 분석 중단을 확인하지 못했습니다. ‘분석 중단’을 눌러 다시 시도해 주세요.");
    this.name = "OrderLogicV3CancellationError";
  }
}

export async function cancelOrderLogicV3Job(jobId: string, entityCode: EntityCode): Promise<string> {
  if (getActiveEntityCode() !== entityCode) throw new DOMException("분석 대상 법인이 변경되었습니다.", "AbortError");
  const response = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v3/jobs/${encodeURIComponent(jobId)}`, {
    method: "DELETE", headers: clientHeaders()
  });
  if (!response.ok) throw new ApiRequestError(await parseApiError(response), response.status);
  const job = (await response.json()) as JobStartResponse;
  if (job.job_id !== jobId || !["cancelled", "succeeded", "failed"].includes(job.status)) {
    throw new ApiRequestError("분석 중단 상태를 확인하지 못했습니다.", 502);
  }
  return job.status;
}

export async function runOrderLogicV3(
  asOf: string,
  { entityCode, signal, onJobStarted, resumeJobId, onReceiveProgress, onStatusChange }: {
    entityCode: EntityCode; signal?: AbortSignal; onJobStarted?: (jobId: string) => void;
    resumeJobId?: string; onReceiveProgress?: (received: number, total: number) => void;
    onStatusChange?: (status: "queued" | "running") => void;
  }
): Promise<OrderLogicV3Result> {
  // Polling waits are also part of the original entity's request lifetime.
  const assertActiveRequest = () => {
    signal?.throwIfAborted();
    if (getActiveEntityCode() !== entityCode) {
      throw new DOMException("분석 대상 법인이 변경되었습니다.", "AbortError");
    }
  };
  assertActiveRequest();
  let jobId: string | null = resumeJobId || null;
  try {
    // Finish receiving the job ID even if Stop is clicked during creation.
    // Aborting this POST could leave a running server job with no cancel target.
    if (!jobId) {
      const response = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v3/jobs`, {
        method: "POST",
        headers: { ...clientHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ as_of: asOf, preview: true })
      });
      if (!response.ok) throw new ApiRequestError(await parseApiError(response), response.status);
      const started = (await response.json()) as JobStartResponse;
      jobId = started.job_id || null;
    }
    if (jobId) {
      onJobStarted?.(jobId);
      onStatusChange?.("queued");
    }
    assertActiveRequest();
    if (!jobId) throw new ApiRequestError("V3 계산 작업을 시작하지 못했습니다.", 500);

    const startedAt = Date.now();
    while (Date.now() - startedAt < POLL_TIMEOUT_MS) {
      await wait(POLL_INTERVAL_MS);
      assertActiveRequest();
      const job = await readJobJson<JobStatusResponse>(
        `${FASTAPI_BASE_URL}/order-logic-v3/jobs/${encodeURIComponent(jobId)}?include_result=false`,
        jobId, signal, assertActiveRequest,
      );
      assertActiveRequest();
      if (job.status === "queued" || job.status === "running") {
        onStatusChange?.(job.status);
      }
      if (job.status === "succeeded" && job.result_delivery === "paged-v1") {
        return await receiveResultPages(jobId, entityCode, signal, assertActiveRequest, onReceiveProgress);
      }
      if (job.status === "succeeded" && job.result) {
        if (job.result.entity_code !== entityCode) {
          throw new ApiRequestError("선택한 법인과 분석 결과의 법인이 일치하지 않습니다. 다시 분석해 주세요.", 409);
        }
        return job.result;
      }
      if (job.status === "cancelled") throw new DOMException("분석이 중단되었습니다.", "AbortError");
      if (job.status === "failed") {
        throw new ApiRequestError(job.error || "V3 계산이 실패했습니다.", Number(job.status_code || 500));
      }
    }
    throw new OrderLogicV3ConnectionError(jobId);
  } catch (error) {
    if (signal?.aborted && jobId && getActiveEntityCode() === entityCode) {
      let status: string;
      try {
        status = await cancelOrderLogicV3Job(jobId, entityCode);
      } catch {
        throw new OrderLogicV3CancellationError(jobId);
      }
      throw new DOMException(status === "cancelled"
        ? "분석을 중단했습니다. 이미 시작된 원천 조회는 서버에서 마무리될 수 있습니다."
        : "이미 종료된 분석의 결과 수신을 중단했습니다.", "AbortError");
    }
    if (signal?.aborted && !jobId) {
      throw new DOMException("분석 요청을 중단했습니다. 서버 작업의 시작 여부는 확인하지 못했습니다.", "AbortError");
    }
    throw error;
  }
}

export type SeasonFactorScope = "FUNCTION_CLASS_1" | "FUNCTION_CLASS_1_AND_2";

export type SeasonFactorMonth = {
  calendar_month: number;
  factor: number;
};

export type SeasonFactorProfile = {
  scope: SeasonFactorScope;
  entity_code: "HQ" | "PL" | "USA";
  function_class_1_code: string;
  function_class_2_code: string;
  application_status: "APPLICABLE" | "DEFAULT_1";
  reason_code: string | null;
  original_reason_code?: string;
  original_message?: string;
  factors: SeasonFactorMonth[];
};

export type SeasonFactorProfileError = {
  scope: SeasonFactorScope;
  entity_code: "HQ" | "PL" | "USA";
  function_class_1_code: string;
  function_class_2_code: string;
  application_status: "BLOCKED";
  reason_code: string;
  message: string;
};

export type SeasonFactorArtifact = {
  source_request?: { demand_policy?: string };
  artifact_schema_version: number;
  status: "active" | "candidate" | "retired";
  entity_code: "HQ" | "PL" | "USA";
  date_basis: "SOURCE_CALENDAR_DATE";
  window_start: string;
  window_end: string;
  calculated_at: string;
  activated_at?: string | null;
  calculation_logic_version: string;
  checksum: string;
  version: string;
  profiles: SeasonFactorProfile[];
  errors: SeasonFactorProfileError[];
  validation: {
    passed: boolean;
    checked_at?: string;
    errors: string[];
  };
};

export async function getActiveSeasonFactorArtifact(): Promise<SeasonFactorArtifact> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v3/season-factors/active`, {
    headers: clientHeaders()
  });
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
  return (await response.json()) as SeasonFactorArtifact;
}

export type SeasonFactorRefreshStatus = {
  entity_code: string;
  job_id?: string;
  status: "idle" | "queued" | "running" | "succeeded" | "failed";
  stage?: string;
  waiting_for_entity?: string | null;
  month?: string;
  completed_months?: number;
  total_months?: number;
  completed_pages?: number;
  total_pages?: number | null;
  error?: string | null;
  version?: string;
};

export async function getSeasonFactorRefreshStatus(): Promise<SeasonFactorRefreshStatus> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v3/season-factors/refresh/status`, {
    headers: clientHeaders(), signal: AbortSignal.timeout(15_000)
  });
  if (!response.ok) throw new ApiRequestError(await parseApiError(response), response.status);
  return response.json() as Promise<SeasonFactorRefreshStatus>;
}

export async function refreshSeasonFactorArtifact(): Promise<SeasonFactorRefreshStatus> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v3/season-factors/refresh`, {
    method: "POST",
    headers: { ...clientHeaders(), "Content-Type": "application/json" },
    signal: AbortSignal.timeout(15_000)
  });
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
  return (await response.json()) as SeasonFactorRefreshStatus;
}
