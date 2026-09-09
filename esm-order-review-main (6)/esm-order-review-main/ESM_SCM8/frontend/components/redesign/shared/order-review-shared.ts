import { getLatestOrderReviewMeta, getOrderReviewRows } from "@/lib/api";
import type { AnalyzeResponse } from "@/types/api";

export async function resolveFullOrderReviewDownload(
  currentResult: AnalyzeResponse | null
): Promise<Pick<AnalyzeResponse, "download_url" | "job_id"> | null> {
  await getOrderReviewRows({ includeLatestFallback: true });
  const latestMeta = getLatestOrderReviewMeta();
  if (latestMeta?.jobId && latestMeta.downloadUrl) {
    return {
      job_id: latestMeta.jobId,
      download_url: latestMeta.downloadUrl
    };
  }
  if (currentResult?.download_url) {
    return currentResult;
  }
  return null;
}

export function isVisibleAnalysisBrandOption(brand: string) {
  const normalized = brand.trim().toLowerCase();
  return normalized !== "etc" && normalized !== "기타";
}
