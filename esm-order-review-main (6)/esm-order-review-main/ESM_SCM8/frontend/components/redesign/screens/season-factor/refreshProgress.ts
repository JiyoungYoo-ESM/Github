import type { SeasonFactorRefreshStatus } from "@/lib/api/order-logic-v3";

export function refreshFailure(job: SeasonFactorRefreshStatus): string {
  const error = job.error || "계절지수 갱신에 실패했습니다. 기존 버전은 유지됩니다.";
  const pages = job.total_pages ? ` (${job.completed_pages ?? 0}/${job.total_pages}페이지 검증 완료)` : "";
  const location = job.month && !error.includes(job.month) ? `${job.month} 조회 중 · ` : "";
  return `${location}${error}${pages}`;
}

export function refreshProgress(job: SeasonFactorRefreshStatus | null): string {
  if (!job) return "";
  if (job.status === "queued") return job.waiting_for_entity
    ? `갱신 대기 중 · ${job.waiting_for_entity} 법인 갱신이 끝나면 시작합니다.` : "갱신 대기 중입니다.";
  if (job.status !== "running") return "";
  if (job.stage === "product_master") return "판매 데이터 조회 완료 · 상품분류를 연결하고 있습니다.";
  if (job.stage === "calculating") return "계절지수를 계산하고 검증하고 있습니다.";
  if (job.stage === "fetching") {
    const pages = job.total_pages ? ` · 현재 월 ${job.completed_pages ?? 0}/${job.total_pages}페이지` : "";
    return `판매 데이터 조회 중 · ${job.completed_months ?? 0}/${job.total_months ?? 24}개월 완료 · ${job.month ?? ""}${pages}`;
  }
  return "계절지수 갱신을 시작하고 있습니다.";
}

export function hasCurrentSalesPolicy(artifact: { source_request?: { demand_policy?: string } }): boolean {
  return artifact.source_request?.demand_policy === "V3_STOCK_IN_OUT_SALE_AND_ONLINE_V1";
}
