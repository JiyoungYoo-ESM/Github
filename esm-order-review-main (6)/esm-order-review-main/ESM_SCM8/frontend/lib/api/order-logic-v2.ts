import {
  apiFetch,
  ApiRequestError,
  clientHeaders,
  FASTAPI_BASE_URL,
  parseApiError,
  wait
} from "./client";
import { resolveBrowserDirectApiBase } from "./base-url";

export type OrderLogicV2PolicyMode = "CASH" | "SHORTAGE";

function orderLogicV2ExportApiBase(): string {
  if (typeof window === "undefined") return FASTAPI_BASE_URL;
  return resolveBrowserDirectApiBase(
    process.env.NEXT_PUBLIC_FASTAPI_BASE_URL,
    window.location
  );
}

export type OrderLogicV2SettingsPayload = {
  grade_cutoff: number;
  // PL/USA는 주 단위 정책값을 사용한다. HQ는 아래 일 단위 필드를 쓰므로
  // 주 단위 필드가 응답에 없다.
  cover_weeks?: number;
  ss_floor_weeks?: number;
  ss_cap_weeks?: number;
  // 리드타임과 정책 운송수단은 서버가 법인별 리드타임 API 실측으로 결정한다.
  // 요청에서는 보내지 않으므로 응답 전용 필드로 둔다.
  lt_air_days?: number;
  lt_rail_days?: number;
  lt_sea_days?: number;
  sigma_l_air_weeks?: number;
  sigma_l_rail_weeks?: number;
  sigma_l_sea_weeks?: number;
  // HQ/OPO 일 단위 정책값. 리드타임은 운송수단이 아니라 국내조달
  // `실입고일 - PO 생성일` 실측 하나를 사용한다.
  review_days?: number;
  ss_floor_days?: number;
  ss_cap_days?: number;
  lt_days?: number;
  sigma_l_days?: number;
  z_cash_major: number;
  z_cash_minor: number;
  z_shortage_major: number;
  z_shortage_minor: number;
  cash_transport_mode?: "AIR" | "RAIL" | "SEA" | "HQ_DOMESTIC";
  shortage_transport_mode?: "AIR" | "RAIL" | "SEA" | "HQ_DOMESTIC";
};

export type OrderLogicV2ApiRow = {
  sku_code: string;
  product_name?: string;
  brand?: string;
  calculable?: boolean;
  validation_error?: string | null;
  data_status?: string;
  grade?: "MAJOR" | "MINOR" | null;
  grade_label?: string | null;
  policy_mode: OrderLogicV2PolicyMode;
  transport_mode?: "AIR" | "RAIL" | "SEA";
  demand_avg?: number | null;
  demand_sigma?: number | null;
  cv?: number | null;
  z_applied?: number | null;
  lead_time_days?: number | null;
  /** Derived display value; calendar days remain the duration base. */
  lead_time_weeks?: number | null;
  lead_time_sigma_weeks?: number | null;
  lead_time_sigma_days?: number | null;
  protection_days?: number | null;
  review_days?: number | null;
  safety_stock?: number | null;
  reorder_point?: number | null;
  target_stock?: number | null;
  incoming_qty?: number | null;
  eu_available_qty?: number | null;
  transit_qty?: number | null;
  next_eta?: string | null;
  next_eta_status?: string | null;
  local_available_qty?: number | null;
  inventory_position?: number | null;
  inventory_position_without_incoming?: number | null;
  depletion_weeks?: number | null;
  suggested_qty?: number | null;
  upper_suggested_qty?: number | null;
  order_signal?: string;
  confirmed_qty?: number | null;
  memo?: string | null;
  unit_price_eur?: number | null;
  suggested_amount_eur?: number | null;
  unit_price_local?: number | null;
  unit_price_krw?: number | null;
  suggested_amount_local?: number | null;
  suggested_amount_krw?: number | null;
  confirmed_amount_local?: number | null;
  confirmed_amount_krw?: number | null;
  check_required?: boolean;
  check_required_reason?: string | null;
  warnings?: string[];
};

export type OrderLogicV2Scenario = {
  source_snapshot_id?: string;
  summary?: Record<string, unknown>;
  rows: OrderLogicV2ApiRow[];
};

export type OrderLogicV2LeadTimeModeStats = {
  sample_size?: number;
  mean_days?: number;
  stdev_days?: number;
  sigma_weeks?: number;
};

export type OrderLogicV2LeadTimeAudit = {
  entity_code?: string;
  completion_date_from?: string;
  completion_date_to?: string;
  packing_count?: number;
  modes?: Record<string, OrderLogicV2LeadTimeModeStats>;
  // HQ/OPO는 운송수단별 집계가 없다. `실입고일 - PO 생성일` 실측 한 벌을
  // 입고 이벤트 단위 동일가중으로 집계한 결과가 담긴다.
  observation_months?: number;
  sample_size?: number;
  mean_days?: number;
  stdev_days?: number;
  median_days?: number;
  min_days?: number;
  max_days?: number;
  basis?: string;
};

export type OrderLogicV2Result = {
  status: string;
  job_id: string;
  logic_version: string;
  result_schema_version: number;
  as_of: string;
  entity_code?: string;
  currency_code?: "EUR" | "USD" | "KRW";
  warehouse_code?: string;
  timezone?: string;
  /** "day" for HQ, "week" for PL/USA. Absent on pre-HQ results. */
  period_unit?: "week" | "day";
  demand_period_count?: number;
  /** Additive calendar-day contract; absent on snapshots created before it. */
  duration_unit?: "CALENDAR_DAY";
  observation_window_days?: number;
  demand_grain?: "DAY_1D" | "WEEK_7D";
  demand_grain_days?: number;
  applied_mode: OrderLogicV2PolicyMode;
  calculated_at: string;
  period_start: string;
  period_end: string;
  source_fetched_at?: string | null;
  source_snapshot_id?: string;
  lead_time_audit?: OrderLogicV2LeadTimeAudit | null;
  settings: OrderLogicV2SettingsPayload;
  warnings?: string[];
  summary?: Record<string, unknown>;
  rows: OrderLogicV2ApiRow[];
  scenarios: Record<OrderLogicV2PolicyMode, OrderLogicV2Scenario>;
};

export type OrderLogicV2RunInput = {
  as_of: string;
  applied_mode: OrderLogicV2PolicyMode;
  settings: OrderLogicV2SettingsPayload;
  preview?: boolean;
};

export type OrderLogicV2ExportOverride = {
  sku_code: string;
  confirmed_qty: number;
  memo?: string;
};

type JobStartResponse = {
  job_id: string;
  status: string;
  result?: OrderLogicV2Result;
};

type JobStatusResponse = JobStartResponse & {
  status_code?: number;
  error?: string;
};

export type OrderLogicV2JobStartedHandler = (jobId: string) => void;

const POLL_INTERVAL_MS = 1_250;
const POLL_TIMEOUT_MS = 15 * 60 * 1_000;

export async function getLatestOrderLogicV2(): Promise<OrderLogicV2Result | null> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v2/latest`, {
    headers: clientHeaders()
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
  const payload = (await response.json()) as OrderLogicV2Result | { status: "empty" };
  return payload.status === "empty" ? null : (payload as OrderLogicV2Result);
}

export async function runOrderLogicV2(
  input: OrderLogicV2RunInput,
  onJobStarted?: OrderLogicV2JobStartedHandler
): Promise<OrderLogicV2Result> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v2/jobs`, {
    method: "POST",
    headers: { ...clientHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(input)
  });
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
  const started = (await response.json()) as JobStartResponse;
  if (started.status === "succeeded" && started.result) return started.result;
  if (!started.job_id) {
    throw new ApiRequestError("발주 계산 작업을 시작하지 못했습니다.", 500);
  }
  onJobStarted?.(started.job_id);

  const startedAt = Date.now();
  while (Date.now() - startedAt < POLL_TIMEOUT_MS) {
    await wait(POLL_INTERVAL_MS);
    let job: JobStatusResponse | null = null;
    try {
      const jobResponse = await apiFetch(
        `${FASTAPI_BASE_URL}/order-logic-v2/jobs/${encodeURIComponent(started.job_id)}`,
        { headers: clientHeaders() }
      );
      if (!jobResponse.ok) {
        const message = await parseApiError(jobResponse);
        if (
          jobResponse.status === 408 ||
          jobResponse.status === 429 ||
          jobResponse.status >= 500
        ) {
          continue;
        }
        throw new ApiRequestError(message, jobResponse.status);
      }
      job = (await jobResponse.json()) as JobStatusResponse;
    } catch (caught) {
      if (
        caught instanceof ApiRequestError &&
        caught.status !== 408 &&
        caught.status !== 429 &&
        caught.status < 500
      ) {
        throw caught;
      }
      // A development proxy reload or a brief network interruption must not
      // turn a still-running server job into a failed analysis. Keep polling.
      continue;
    }
    if (job.status === "succeeded" && job.result) return job.result;
    if (job.status === "cancelled") {
      throw new DOMException("사용자가 분석을 중단했습니다.", "AbortError");
    }
    if (job.status === "failed") {
      throw new ApiRequestError(
        job.error || "발주 계산이 실패했습니다.",
        Number(job.status_code || 500)
      );
    }
  }
  throw new ApiRequestError(
    "발주 계산이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.",
    408
  );
}

export async function cancelOrderLogicV2(jobId: string): Promise<void> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v2/jobs/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
    headers: clientHeaders()
  });
  if (!response.ok) throw new ApiRequestError(await parseApiError(response), response.status);
}

export async function exportOrderLogicV2Excel(
  jobId: string,
  exportMode: OrderLogicV2PolicyMode,
  rowIds: string[],
  overrides: OrderLogicV2ExportOverride[]
): Promise<{ blob: Blob; filename: string }> {
  const response = await apiFetch(`${orderLogicV2ExportApiBase()}/order-logic-v2/export`, {
    method: "POST",
    headers: { ...clientHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: jobId,
      export_mode: exportMode,
      row_ids: rowIds,
      overrides
    })
  });
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
  const disposition = response.headers.get("content-disposition") || "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  const filename = encoded
    ? decodeURIComponent(encoded)
    : plain || `order_logic_v2_${exportMode.toLowerCase()}_${jobId}.xlsx`;
  return { blob: await response.blob(), filename };
}
