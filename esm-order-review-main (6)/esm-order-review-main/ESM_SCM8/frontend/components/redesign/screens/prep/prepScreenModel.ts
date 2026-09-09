import {
  getLatestOrderReviewEtaRows,
  getLatestOrderReviewMeta,
  getLatestOrderReviewRawRows,
  type AnalyzeOptions,
  type LatestOrderReviewMeta
} from "@/lib/api";
import { isOrderExcludedRow } from "@/lib/api/mappers";
import type { AnalyzeResponse, ExchangeRateResponse, OrderReviewRow } from "@/types/api";

/** 백엔드 dataframe_preview와 같은 미리보기 행 수. */
const RECOVERED_PREVIEW_ROWS = 300;

/**
 * 세션 복구 결과의 테이블은 서버 원본 행을 그대로 쓴다. 매핑된 OrderReviewRow에는 기준일과
 * 일평균 판매수량이 없어서, 그 행으로 재고공백을 계산하면 분석 기준일이 아니라 화면을 연
 * 날짜로 소진일이 다시 계산된다.
 */
export function recoveredOrderReviewRecords(rows: OrderReviewRow[]): Array<Record<string, unknown>> {
  const rawRows = getLatestOrderReviewRawRows();
  if (rawRows && rawRows.length === rows.length) {
    return rawRows;
  }
  return rows as unknown as Array<Record<string, unknown>>;
}

export function buildRecoveredOrderAnalysisResult(
  rows: OrderReviewRow[],
  exchangeRate: ExchangeRateResponse | null,
  options: AnalyzeOptions = {},
  latestMeta: LatestOrderReviewMeta | null = getLatestOrderReviewMeta()
): AnalyzeResponse {
  const requiredRows = rows.filter(
    (row) => !isOrderExcludedRow(row) && (row.requiredOrderQty > 0 || row.requiredOrderAmount > 0)
  );
  const rowRecords = recoveredOrderReviewRecords(rows);
  const etaRecords = getLatestOrderReviewEtaRows() ?? [];
  return {
    job_id: latestMeta?.jobId || `latest_order_review_${Date.now()}`,
    status: "success",
    summary: {
      total_sku: rows.length,
      order_required_sku: requiredRows.length,
      check_required_sku: 0,
      order_required_qty: requiredRows.reduce((sum, row) => sum + row.requiredOrderQty, 0),
      order_amount_eur: requiredRows.reduce((sum, row) => sum + row.requiredOrderAmount, 0)
    },
    tables: {
      // 같은 배열을 두 키에 담으면 직렬화 크기가 두 배가 된다(원본 행은 행당 84개 컬럼).
      // 백엔드도 order_review는 미리보기, stock_gap_order_review는 전체로 내려준다.
      order_review: rowRecords.slice(0, RECOVERED_PREVIEW_ROWS),
      check_required: [],
      stock_eta: [],
      stock_gap_order_review: rowRecords,
      stock_gap_eta: etaRecords
    },
    download_url: latestMeta?.downloadUrl || "",
    settings: {
      eur_krw_rate: options.eurKrwRate ?? exchangeRate?.eur_krw_rate ?? 0,
      rate_source: options.eurKrwRate !== undefined ? "manual" : exchangeRate?.rate_source ?? "api",
      rate_date: exchangeRate?.rate_date,
      safety_months: options.safetyMonths,
      lead_times: options.leadTimeOverrides ?? {}
    },
    uploaded_files: []
  };
}
