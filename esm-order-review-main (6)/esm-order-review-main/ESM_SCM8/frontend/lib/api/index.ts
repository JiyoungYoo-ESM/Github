export {
  FASTAPI_BASE_URL,
  FASTAPI_UPLOAD_BASE_URL,
  MAX_UPLOAD_FILE_BYTES,
  MAX_UPLOAD_FILES,
  MAX_UPLOAD_TOTAL_BYTES,
  getClientId,
  ApiRequestError,
  isAbortError
} from "./client";

export {
  LAST_RESULT_STORAGE_KEY,
  SEASON_TREND_RESULT_STORAGE_KEY,
  getLastAnalysisResult,
  getLatestOrderReviewMeta,
  getLatestOrderReviewEtaRows,
  getLatestOrderReviewRawRows,
  clearCurrentAnalysisStatus,
  clearLastAnalysisResult,
  saveLastAnalysisResult,
  clearSeasonTrendResult,
  saveSeasonTrendResult
} from "./storage";
export type { LatestOrderReviewMeta } from "./storage";

export { getHealth, getExchangeRate } from "./health";

export {
  getDashboardData,
  getOrderReviewRows,
  getSkuConcentrationRows,
  getCurrentStockGapSnapshot,
  getStockGapItems,
  getSeasonTrendAnalysis
} from "./dashboard";
export type { CurrentStockGapSnapshot } from "./dashboard";

export {
  startMockAnalysis,
  classifyFiles,
  analyzeFileList,
  analyzeFiles,
  analyzeFromCms,
  cancelCmsAnalysis,
  downloadHref
} from "./analysis";
export type { AnalysisRequestControls, AnalyzeOptions } from "./analysis";

export {
  analyzeSeasonTrendFiles,
  analyzeSeasonTrendFromApi,
  cancelSeasonTrendAnalysis,
  fetchBrandReportData
} from "./season";

export { getCategoryCorrectionOptions, saveCategoryCorrections } from "./category";

export { getCorporateInventory } from "./corporate-inventory";
export type {
  CorporateInventoryCompany,
  CorporateInventoryHoldings,
  CorporateInventoryInTransit,
  CorporateInventoryResponse,
  CorporateInventoryTotal,
  CorporateInventoryTransitCurrency,
  CorporateInventoryTransitDestination,
  CorporateInventoryTransitMode,
  CorporateInventoryWarehouse
} from "./corporate-inventory";

export { exportReportFromTemplate } from "./reports";
export type { ReportAudience, ReportExportBlock, ReportExportFormat } from "./reports";

export { createSupportTicket, getSupportTickets } from "./support";
export { useApiQuery } from "./useApiQuery";
export {
  exportOrderLogicV2Excel,
  cancelOrderLogicV2,
  getLatestOrderLogicV2,
  runOrderLogicV2
} from "./order-logic-v2";
export type {
  OrderLogicV2ApiRow,
  OrderLogicV2ExportOverride,
  OrderLogicV2LeadTimeAudit,
  OrderLogicV2PolicyMode,
  OrderLogicV2Result,
  OrderLogicV2RunInput,
  OrderLogicV2SettingsPayload
} from "./order-logic-v2";
export type {
  CreateSupportTicketInput,
  SupportAttachment,
  SupportTicket,
  SupportTicketList,
  SupportTicketSummary
} from "./support";
