import { apiFetch, ApiRequestError, clientHeaders, FASTAPI_BASE_URL, parseApiError, wait } from "./client";

export type V3SeasonFactorGroup = {
  function_class_1_code: string;
  function_class_2_code: string;
  sku_count: number;
  seasonality_status: "PENDING" | "CONFIRMED" | "NOT_CONFIRMED" | "CALC_FAILED";
  reason_code?: string | null;
  factors_by_month: Record<string, number>;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
};

export type V3SeasonFactorArtifact = {
  artifact_id: string;
  entity_code: string;
  artifact_status: "CANDIDATE" | "ACTIVE" | "RETIRED";
  window_start: string;
  window_end: string;
  created_at: string;
  created_by: string;
  approved_at?: string | null;
  approved_by?: string | null;
  categories: V3SeasonFactorGroup[];
};

export type V3SeasonFactorSummary = Pick<
  V3SeasonFactorArtifact,
  "artifact_id" | "entity_code" | "artifact_status" | "window_start" | "window_end" | "created_at" | "created_by" | "approved_at" | "approved_by"
> & { group_count: number; pending_count: number };

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw new ApiRequestError(await parseApiError(response), response.status);
  return response.json() as Promise<T>;
}

export async function listV3SeasonFactors(): Promise<V3SeasonFactorSummary[]> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v3/season-factors`, { headers: clientHeaders() });
  const payload = await readJson<{ items: V3SeasonFactorSummary[] }>(response);
  return payload.items;
}

export async function getV3SeasonFactor(artifactId: string): Promise<V3SeasonFactorArtifact> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v3/season-factors/${encodeURIComponent(artifactId)}`, { headers: clientHeaders() });
  return readJson<V3SeasonFactorArtifact>(response);
}

export async function createV3SeasonFactorCandidate(asOf: string): Promise<V3SeasonFactorArtifact> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v3/season-factors/candidates`, {
    method: "POST",
    headers: { ...clientHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ as_of: asOf, force_refresh: false })
  });
  const started = await readJson<{ job_id: string }>(response);
  const startedAt = Date.now();
  while (Date.now() - startedAt < 15 * 60 * 1_000) {
    await wait(500);
    const jobResponse = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v3/jobs/${encodeURIComponent(started.job_id)}`, { headers: clientHeaders() });
    const job = await readJson<{ status: string; result?: V3SeasonFactorArtifact; error?: string }>(jobResponse);
    if (job.status === "succeeded" && job.result) return job.result;
    if (job.status === "failed") throw new ApiRequestError(job.error || "계절지수 후보 생성에 실패했습니다.", 422);
  }
  throw new ApiRequestError("계절지수 후보 생성 시간이 초과되었습니다.", 408);
}

export async function reviewV3SeasonFactorGroup(
  artifactId: string,
  group: Pick<V3SeasonFactorGroup, "function_class_1_code" | "function_class_2_code">,
  decision: "CONFIRMED" | "NOT_CONFIRMED"
): Promise<V3SeasonFactorArtifact> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v3/season-factors/${encodeURIComponent(artifactId)}/review`, {
    method: "PATCH",
    headers: { ...clientHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ ...group, decision })
  });
  return readJson<V3SeasonFactorArtifact>(response);
}

export async function activateV3SeasonFactor(artifactId: string): Promise<V3SeasonFactorArtifact> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/order-logic-v3/season-factors/${encodeURIComponent(artifactId)}/activate`, {
    method: "POST",
    headers: clientHeaders()
  });
  return readJson<V3SeasonFactorArtifact>(response);
}
