import { parseLeadTimeReference, type LeadTimeReference } from "@/lib/lead-times";
import { apiFetch, ApiRequestError, FASTAPI_BASE_URL, parseApiError } from "./client";

export async function getLeadTimeReference(
  entityCode: string,
  signal?: AbortSignal
): Promise<LeadTimeReference> {
  const query = new URLSearchParams({ entity_code: entityCode });
  const response = await apiFetch(`${FASTAPI_BASE_URL}/reference/lead-times?${query.toString()}`, {
    cache: "no-store",
    signal
  });
  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }
  const reference = parseLeadTimeReference(await response.json());
  if (reference.entity_code !== entityCode) {
    throw new Error(
      `요청한 법인(${entityCode})과 리드타임 응답 법인(${reference.entity_code})이 일치하지 않습니다.`
    );
  }
  return reference;
}
