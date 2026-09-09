import type { components } from "./openapi";

type ApiSchemas = components["schemas"];

export type UploadRole = ApiSchemas["ClassificationCandidateResponse"]["role"];

export type HealthResponse = ApiSchemas["HealthResponse"];

export type AnalyzeSummary = {
  total_sku: number;
  order_required_sku: number;
  check_required_sku: number;
  order_required_qty?: number;
  order_amount_eur: number;
};

export type AnalyzeSettings = {
  eur_krw_rate: number;
  rate_source: "manual" | "api" | "default" | string;
  rate_date?: string;
  fallback_rate?: number;
  fallback_rate_as_of?: string;
  fallback_rate_source?: string;
  fallback_rate_age_days?: number | null;
  rate_warning?: string;
  safety_months?: number;
  sku_shortage_threshold_pct?: number;
  sku_overstock_threshold_pct?: number;
  lead_times?: Record<string, number>;
};

export type ExchangeRateResponse = ApiSchemas["ExchangeRateResponse"];

export type AnalyzeTables = {
  order_review: Array<Record<string, unknown>>;
  check_required: Array<Record<string, unknown>>;
  stock_eta: Array<Record<string, unknown>>;
  stock_gap_order_review?: Array<Record<string, unknown>>;
  stock_gap_eta?: Array<Record<string, unknown>>;
  sku_concentration?: Array<Record<string, unknown>>;
};

export type MonthCoverage = {
  month: string;
  status: "complete" | "partial" | "missing";
  reason?: string;
  rowCount?: number;
  activeDays?: number;
  expectedBusinessDays?: number;
  activityRatio?: number;
  firstDate?: string | null;
  lastDate?: string | null;
  totalAmount?: number;
  totalQty?: number;
};

export type SeasonAnalysis = {
  /** Complete country/brand/SKU detail tables are present (not bounded top-SKU tables). */
  crossAnalysisComplete?: boolean;
  category1Monthly: Array<Record<string, unknown>>;
  category2Monthly: Array<Record<string, unknown>>;
  category1Share: Array<Record<string, unknown>>;
  category2Share: Array<Record<string, unknown>>;
  ytdComparison: Array<Record<string, unknown>>;
  topSku: Array<Record<string, unknown>>;
  skuMonthly: Array<Record<string, unknown>>;
  mappingQuality: Array<Record<string, unknown>>;
  uncategorizedSku: Array<Record<string, unknown>>;
  countryCategoryMonthly?: Array<Record<string, unknown>>;
  countryCategory2Monthly?: Array<Record<string, unknown>>;
  countryTopSku?: Array<Record<string, unknown>>;
  countrySkuSummary?: Array<Record<string, unknown>>;
  countrySkuMonthly?: Array<Record<string, unknown>>;
  brandReports?: BrandReportAggregate[];
  sourceDataQuality?: SeasonSourceDataQuality;
  dataMonths?: string[];
  monthCoverage?: MonthCoverage[];
  countryCustomerSummary?: Array<Record<string, unknown>>;
  countryCategoryCustomerSummary?: Array<Record<string, unknown>>;
  customerSalesSummary?: Array<Record<string, unknown>>;
};

export type IngredientAnalysis = {
  keywordMap: Array<Record<string, unknown>>;
  skuTags: Array<Record<string, unknown>>;
  monthlyTrend: Array<Record<string, unknown>>;
  summary: Array<Record<string, unknown>>;
  growth3m: Array<Record<string, unknown>>;
  ytdComparison: Array<Record<string, unknown>>;
  topSku: Array<Record<string, unknown>>;
  topBrand: Array<Record<string, unknown>>;
  brandMonthlyTrend?: Array<Record<string, unknown>>;
  skuMonthlyTrend?: Array<Record<string, unknown>>;
  unmatchedSku: Array<Record<string, unknown>>;
  coverage?: Array<Record<string, unknown>>;
  countryCoverage?: Array<Record<string, unknown>>;
  countryMonthlyTrend?: Array<Record<string, unknown>>;
  countrySummary?: Array<Record<string, unknown>>;
  countryGrowth3m?: Array<Record<string, unknown>>;
  countryYtdComparison?: Array<Record<string, unknown>>;
  countryTopSku?: Array<Record<string, unknown>>;
  countryTopBrand?: Array<Record<string, unknown>>;
};

export type UploadedFileInfo = {
  key: string;
  role: string;
  original_name: string;
  saved_name: string;
  source: string;
  score: number | null;
  rows: number;
  columns: number;
  detected_columns?: string[];
  matched_required_columns?: string[];
  missing_required_columns?: string[];
};

export type ClassificationConfidence = ApiSchemas["ClassificationItemResponse"]["confidence"];
export type ClassificationCandidate = ApiSchemas["ClassificationCandidateResponse"];
export type ClassificationItem = ApiSchemas["ClassificationItemResponse"];
export type ClassifyResponse = ApiSchemas["ClassificationResponse"];

export type CmsFetchCacheInfo = {
  hit: boolean;
  source: "memory" | "disk" | "cms_api";
  created_at: string;
  age_seconds?: number;
  ttl_seconds?: number | null;
};

export type AnalyzeResponse = {
  job_id: string;
  entity_code?: string;
  status: string;
  summary: AnalyzeSummary;
  tables: AnalyzeTables;
  download_url: string;
  settings: AnalyzeSettings;
  season_analysis?: SeasonAnalysis;
  ingredient_analysis?: IngredientAnalysis;
  file_mapping?: Record<string, string>;
  uploaded_files?: UploadedFileInfo[];
  cms_fetch_cache?: CmsFetchCacheInfo | null;
};

export type BrandReportAggregate = {
  brand: string;
  amount: number;
  qty: number;
  skuCount: number;
  countryCount: number;
  categoryCount: number;
  countries: Array<{ name: string; amount: number }>;
  topSkus: Array<{ sku: string; name: string; category: string; amount: number; qty: number }>;
  categories: Array<{ category1: string; category2: string; amount: number }>;
  monthly: Array<{ month: string; amount: number }>;
};

export type SeasonSourceDataQuality = {
  status: "ok" | "warning" | "blocked";
  sourceRows: number;
  stableIdColumn: string | null;
  stableIdDuplicateRows: number;
  duplicateCandidateGroups: number;
  duplicateCandidateRows: number;
  duplicateCandidateExcessRows: number;
  duplicateCandidateAmountEur: number;
  duplicateCandidateAmountSharePct: number;
  freeOfChargeRowsExcluded: number;
  freeOfChargeQtyExcluded: number;
  recommendationBlocked: boolean;
  blockThresholdPct: number;
  notes: string[];
};

export type SeasonTrendAnalyzeResponse = {
  status: string;
  analysis_schema_version?: number;
  season_analysis: SeasonAnalysis;
  ingredient_analysis: IngredientAnalysis;
  uploaded_files: UploadedFileInfo[];
  analysis_options?: {
    start_date?: string | null;
    end_date?: string | null;
    metric?: "qty" | "amount" | string;
    group_by?: "month" | "quarter" | "year" | string;
    comparison_basis?: "none" | "yoy" | "mom" | string;
    include_ingredient?: boolean;
    exclude_partial_months?: boolean;
    lead_time_air?: number | null;
    lead_time_sea?: number | null;
    lead_time_rail?: number | null;
    lead_time_truck?: number | null;
    average_eur_krw_rate?: number | null;
    exchange_rate_basis?: string | null;
    exchange_rate_source?: "api" | "default" | string | null;
    exchange_rate_date?: string | null;
    exchange_rate_checked_date?: string | null;
    currency_code?: string | null;
    currency_krw_rate?: number | null;
    sales_amount_currency_code?: string | null;
    sales_amount_field?: string | null;
    entity_code?: string | null;
    warehouse?: string | null;
  };
};

export type CategoryCorrectionOptions = ApiSchemas["CategoryCorrectionOptionsResponse"];
export type CategoryCorrectionItem = ApiSchemas["CategoryCorrectionItem"];
export type CategoryCorrectionSaveResponse = ApiSchemas["CategoryCorrectionSaveResponse"];
export type CategoryCorrectionRequest = ApiSchemas["CategoryCorrectionRequest"];
export type CmsAnalyzeRequest = ApiSchemas["CmsAnalyzeRequest"];
export type AnalysisJobStartResponse = ApiSchemas["AnalysisJobStartResponse"];
export type AnalysisJobStatusResponse = ApiSchemas["AnalysisJobStatusResponse"];
export type LoginRequest = ApiSchemas["LoginRequest"];
export type AuthActionResponse = ApiSchemas["AuthActionResponse"];
export type AuthStatusResponse = ApiSchemas["AuthStatusResponse"];

export type DashboardKpi = {
  label: string;
  value: number;
  unit: string;
  trend: string;
  tone: "blue" | "slate" | "red";
};

export type OrderDistributionPoint = {
  name: string;
  value: number;
};

export type PrioritySku = {
  sku: string;
  productName: string;
  brand: string;
  shortageQty: number;
  orderAmountEur: number;
  action: string;
  stockoutDate?: string | null;
  earliestEtaDate?: string | null;
  gapDays?: number | null;
  status?: string | null;
};

export type EtaEvent = {
  date: string;
  mode: string;
  skuCount: number;
  quantity: number;
  status: string;
};

export type OrderReviewRow = {
  sku: string;
  productCode?: string;
  barcode?: string;
  productName: string;
  brand: string;
  recentSalesQty: number;
  monthlyDemand: number;
  euAvailableStock: number;
  shippingQty: number;
  inboundQty: number;
  requiredOrderQty: number;
  requiredOrderAmount: number;
  priorityAction: string;
  riskReason: string;
  salesAmount?: number | null;
  stockAmount?: number | null;
  unitPrice?: number | null;
  abcGrade?: "A" | "B" | "C" | string;
  shortageQty?: number | null;
  stockoutDate?: string | null;
  earliestEtaDate?: string | null;
  backendStatus?: string;
  preArrivalStockoutRisk?: boolean;
  etaDelayFlag?: boolean;
  /** 미입고 물량이 있는데 도착 근거(운송 ETA)가 없는 상태. */
  openPoEtaUnknown?: boolean;
  urgentReplenishmentQty?: number | null;
  urgentAction?: string;
};

export type SkuConcentrationSource = Pick<
  OrderReviewRow,
  | "sku"
  | "productName"
  | "brand"
  | "recentSalesQty"
  | "euAvailableStock"
  | "salesAmount"
  | "stockAmount"
  | "unitPrice"
  | "abcGrade"
>;

export type StockGapStatus =
  | "sufficient"
  | "waiting_eta"
  /** 이미 소진됐는데 예정된 입고가 없어 공백 종료 시점을 계산할 수 없는 상태. */
  | "stockout_no_inbound"
  | "stock_gap"
  | "urgent_replenishment"
  | "needs_check";

export type StockGapEtaItem = {
  sku: string;
  productName: string;
  brand: string;
  transportMode: string;
  eta: string;
  inTransitQty: number;
  shipmentDate?: string;
  referenceNo?: string;
  note?: string;
};

export type StockGapItem = {
  sku: string;
  productCode?: string;
  barcode?: string;
  productName: string;
  brand: string;
  baseDate?: string | null;
  availableQty: number | null;
  recent3mSalesQty: number | null;
  avgDailySalesQty?: number | null;
  /** 운송중 수량. 판매·재고가 없는 행이 실제로 완전히 비어 있는지 판정하는 데 쓴다. */
  inTransitQty?: number | null;
  /** 미입고(발주 후 미도착) 수량. */
  openPoQty?: number | null;
  riskScore?: number;
  shortageQty?: number;
  stockoutDate?: string | null;
  earliestEtaDate?: string | null;
  backendStatus?: string;
  priorityAction?: string;
  riskReason?: string;
  preArrivalStockoutRisk?: boolean;
  etaDelayFlag?: boolean;
  urgentReplenishmentQty?: number;
  urgentAction?: string;
  etaItems: StockGapEtaItem[];
};
