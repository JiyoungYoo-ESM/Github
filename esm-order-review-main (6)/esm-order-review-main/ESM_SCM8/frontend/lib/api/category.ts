import type {
  CategoryCorrectionItem,
  CategoryCorrectionOptions,
  CategoryCorrectionRequest,
  CategoryCorrectionSaveResponse
} from "@/types/api";
import { apiFetch, ApiRequestError, clientHeaders, FASTAPI_BASE_URL, parseApiError } from "./client";
import { clearSeasonTrendResult } from "./storage";

export async function getCategoryCorrectionOptions(): Promise<CategoryCorrectionOptions> {
  const response = await apiFetch(`${FASTAPI_BASE_URL}/category-corrections/options`, {
    headers: clientHeaders()
  });

  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }

  return response.json() as Promise<CategoryCorrectionOptions>;
}

export async function saveCategoryCorrections(items: CategoryCorrectionItem[]): Promise<CategoryCorrectionSaveResponse> {
  const request: CategoryCorrectionRequest = { items };
  const response = await apiFetch(`${FASTAPI_BASE_URL}/category-corrections`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...clientHeaders()
    },
    body: JSON.stringify(request)
  });

  if (!response.ok) {
    throw new ApiRequestError(await parseApiError(response), response.status);
  }

  const result = (await response.json()) as CategoryCorrectionSaveResponse;
  clearSeasonTrendResult();
  return result;
}
