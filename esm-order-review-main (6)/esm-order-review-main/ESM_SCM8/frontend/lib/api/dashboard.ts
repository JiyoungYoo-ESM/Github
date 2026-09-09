import type {
  DashboardKpi,
  AnalyzeResponse,
  EtaEvent,
  OrderDistributionPoint,
  OrderReviewRow,
  PrioritySku,
  SeasonTrendAnalyzeResponse,
  SkuConcentrationSource,
  StockGapEtaItem,
  StockGapItem
} from "@/types/api";
import { wait } from "./client";
import { computeStockGapItem, formatDate, startOfDay } from "@/lib/stock-gap";
import {
  cleanSku,
  emptyIngredientAnalysis,
  emptySeasonAnalysis,
  etaEventsFromRows,
  etaItemFromTable,
  etaItemsFromStockEtaPivotRow,
  isRequiredOrderReviewRow,
  orderReviewRowFromTable,
  pick,
  readNumber,
  stockGapItemFromOrderReview
} from "./mappers";
import {
  fetchLatestOrderReviewRows,
  getCurrentAnalysisJobId,
  getStoredAnalysisResultAsync,
  hasExplicitCurrentAnalysisResult,
  getStoredSeasonTrendResult,
  hasCurrentSeasonTrendResult,
  isStaleSeasonTrendResult,
  saveSeasonTrendResult
} from "./storage";
import { getExchangeRate } from "./health";
import { fetchLatestSeasonTrendResult } from "./season";
import { getActiveEntityCode } from "@/lib/entity-session";

export async function getDashboardData(): Promise<{
  kpis: DashboardKpi[];
  distribution: OrderDistributionPoint[];
  prioritySkus: PrioritySku[];
  etaEvents: EtaEvent[];
}> {
  await wait();
    const result = await getStoredAnalysisResultAsync();
    if (result) {
      const { summary, settings, tables } = result;
      const eurKrwRate = readNumber(settings.eur_krw_rate, 0);
      const liveExchangeRate = await getExchangeRate(
        getActiveEntityCode() === "USA" ? "USD" : "EUR"
      ).catch(() => null);
      const currentEurKrwRate = liveExchangeRate?.eur_krw_rate ?? eurKrwRate;
      const exchangeSource = liveExchangeRate?.rate_source ?? settings.rate_source;
      const exchangeDate = liveExchangeRate?.rate_date ?? settings.rate_date;
      const orderReviewRows = tables.stock_gap_order_review ?? tables.order_review ?? [];
      const orderReview = orderReviewRows.map(orderReviewRowFromTable);
      const orderAmountKrwFromRows = orderReview.reduce((total, row) => total + row.requiredOrderAmount, 0);
      const orderAmountKrw = orderAmountKrwFromRows > 0 ? orderAmountKrwFromRows : summary.order_amount_eur * eurKrwRate;
      const etaRows = tables.stock_gap_eta ?? tables.stock_eta ?? [];
    const priorityRows = orderReview
      .filter(isRequiredOrderReviewRow)
      .sort((a, b) => b.requiredOrderAmount - a.requiredOrderAmount || b.requiredOrderQty - a.requiredOrderQty)
      .slice(0, 10);

    const gapEtaItems = (tables.stock_gap_eta ?? []).map(etaItemFromTable).filter((item): item is StockGapEtaItem => Boolean(item));
    const allEtaItems = gapEtaItems.length > 0 ? gapEtaItems : (tables.stock_eta ?? []).flatMap(etaItemsFromStockEtaPivotRow);
    const etaBySku = new Map<string, StockGapEtaItem[]>();
    for (const etaItem of allEtaItems) {
      const skuKey = cleanSku(etaItem.sku);
      const list = etaBySku.get(skuKey) ?? [];
      list.push(etaItem);
      etaBySku.set(skuKey, list);
    }
    const baseDate = startOfDay(new Date());
    const gapBySku = new Map<string, ReturnType<typeof computeStockGapItem>>();
    for (const row of tables.stock_gap_order_review ?? tables.order_review ?? []) {
      const item = stockGapItemFromOrderReview(row, etaBySku.get(cleanSku(pick(row, ["상품코드", "SKU", "sku"], (row as { sku?: unknown }).sku))) ?? []);
      if (item.sku && item.sku !== "-") {
        gapBySku.set(item.sku, computeStockGapItem(item, baseDate));
      }
    }
    const brandOrderAmount = new Map<string, number>();
    for (const row of orderReview) {
      if (row.requiredOrderQty <= 0) {
        continue;
      }
      const brand = row.brand || "미지정";
      brandOrderAmount.set(brand, (brandOrderAmount.get(brand) ?? 0) + row.requiredOrderAmount);
    }
    const brandDistribution = Array.from(brandOrderAmount.entries())
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 5);
    const orderRequiredQty =
      readNumber(summary.order_required_qty, Number.NaN) ||
      orderReview.reduce((total, row) => total + row.requiredOrderQty, 0);

    return {
      kpis: [
        { label: "전체 SKU", value: summary.total_sku, unit: "SKU", trend: "", tone: "slate" },
        { label: "발주 필요 SKU", value: summary.order_required_sku, unit: "SKU", trend: "", tone: "blue" },
        { label: "발주 총 필요수량", value: orderRequiredQty, unit: "개", trend: "", tone: "blue" },
        {
          label: "발주 금액",
          value: orderAmountKrw,
          unit: "KRW",
          trend: "",
          tone: "blue"
        },
        {
          label: "현재 환율",
          value: currentEurKrwRate,
          unit: "KRW/EUR",
          trend: `${exchangeSource === "api" ? "자동 조회" : exchangeSource === "manual" ? "수동 입력" : "기본값"}${exchangeDate ? ` · ${exchangeDate}` : ""}`,
          tone: "slate"
        }
      ],
      distribution: brandDistribution,
      prioritySkus: priorityRows.map((row) => {
        const gap = gapBySku.get(row.sku);
        return {
          sku: row.sku,
          productName: row.productName,
          brand: row.brand,
          shortageQty: row.requiredOrderQty,
          orderAmountEur: row.requiredOrderAmount,
          action: row.priorityAction,
          stockoutDate: gap?.stockoutDate ? formatDate(gap.stockoutDate) : null,
          earliestEtaDate: gap?.earliestEtaDate ? formatDate(gap.earliestEtaDate) : null,
          gapDays: gap?.gapDays ?? null,
          status: gap?.status ?? null,
        };
      }),
      etaEvents: etaEventsFromRows(etaRows).slice(0, 12)
    };
  }

  return {
    kpis: [],
    distribution: [],
    prioritySkus: [],
    etaEvents: []
  };
}

type GetOrderReviewRowsOptions = {
  includeLatestFallback?: boolean;
  requireCurrentSession?: boolean;
};

export async function getOrderReviewRows(options: GetOrderReviewRowsOptions = {}): Promise<OrderReviewRow[]> {
  await wait();
  if (options.requireCurrentSession) {
    const currentResult = await getStoredAnalysisResultAsync();
    if (!currentResult || currentResult.job_id !== getCurrentAnalysisJobId()) {
      return [];
    }
    return hydrateProductIdentity(
      (currentResult.tables.stock_gap_order_review ?? currentResult.tables.order_review ?? []).map(orderReviewRowFromTable)
    );
  }

  const shouldUseLatest = options.includeLatestFallback ?? true;
  if (shouldUseLatest) {
    try {
      const latestRows = await fetchLatestOrderReviewRows();
      if (latestRows.length > 0) {
        return hydrateProductIdentity(latestRows);
      }
    } catch {
      // Fall back to the in-tab result below so the just-finished analysis can still render offline.
    }
  }

  const result = await getStoredAnalysisResultAsync();
  if (result) {
    const storedRows = hydrateProductIdentity(
      (result.tables.stock_gap_order_review ?? result.tables.order_review ?? []).map(orderReviewRowFromTable)
    );
    if (!shouldUseLatest || !storedRows.some((row) => isMissingProductText(row.productName) || isMissingBrandText(row.brand))) {
      return storedRows;
    }
    try {
      return hydrateProductIdentity(mergeProductIdentity(storedRows, await fetchLatestOrderReviewRows()));
    } catch {
      return storedRows;
    }
  }
  if (!shouldUseLatest) {
    return [];
  }
  return hydrateProductIdentity(await fetchLatestOrderReviewRows());
}

export async function getSkuConcentrationRows(): Promise<SkuConcentrationSource[]> {
  await wait();
  const result = await getStoredAnalysisResultAsync();
  const concentrationRows = result?.tables.sku_concentration ?? [];
  if (concentrationRows.length > 0) {
    return hydrateProductIdentity(
      concentrationRows.map((row) => ({
        sku: String(pick(row, ["SKU", "상품코드", "sku"], "-")),
        productName: String(pick(row, ["상품명", "productName", "제품명"], "-")),
        brand: String(pick(row, ["브랜드", "brand"], "-")),
        recentSalesQty: readNumber(pick(row, ["최근 3개월 판매수량", "판매수량", "recentSalesQty"])),
        euAvailableStock: readNumber(pick(row, ["EU 현지 가용수량", "EU 가용재고", "euAvailableStock"])),
        salesAmount: readNumber(pick(row, ["최근 3개월 판매금액(KRW)", "판매금액(KRW)", "salesAmount"]), 0),
        stockAmount: readNumber(pick(row, ["재고 평가액(KRW)", "재고금액(KRW)", "stockAmount"]), 0),
        unitPrice: readNumber(pick(row, ["현지 입고단가", "현지 입고단가(EUR)", "현지 입고단가(USD)", "EU 입고단가", "EU 입고단가(EUR)", "unitPrice"])),
        abcGrade: String(pick(row, ["ABC 등급", "등급", "abcGrade"], ""))
      }))
    );
  }
  const rows = await getOrderReviewRows({ includeLatestFallback: false });
  return rows.map((row) => ({
    sku: row.sku,
    productName: row.productName,
    brand: row.brand,
    recentSalesQty: row.recentSalesQty,
    euAvailableStock: row.euAvailableStock,
    salesAmount: row.salesAmount,
    stockAmount: row.stockAmount,
    unitPrice: row.unitPrice,
    abcGrade: row.abcGrade
  }));
}

type GetStockGapItemsOptions = {
  requireCurrentSession?: boolean;
};

export type CurrentStockGapSnapshot = {
  status: "ready" | "missing" | "stale";
  jobId: string | null;
  entityCode: string | null;
  items: StockGapItem[];
};

function stockGapItemsFromResult(result: AnalyzeResponse): StockGapItem[] {
  const detailedEtaItems = (result.tables.stock_gap_eta ?? [])
    .map(etaItemFromTable)
    .filter((item): item is StockGapEtaItem => Boolean(item));
  const etaItems =
    detailedEtaItems.length > 0 ? detailedEtaItems : (result.tables.stock_eta ?? []).flatMap(etaItemsFromStockEtaPivotRow);
  const etaBySku = new Map<string, StockGapEtaItem[]>();

  for (const etaItem of etaItems) {
    const skuKey = cleanSku(etaItem.sku);
    const rows = etaBySku.get(skuKey) ?? [];
    rows.push(etaItem);
    etaBySku.set(skuKey, rows);
  }

  const stockGapRows = result.tables.stock_gap_order_review ?? result.tables.order_review ?? [];
  const identityRows = [
    ...(result.tables.order_review ?? []).map(orderReviewRowFromTable),
    ...etaItems
  ];
  const stockGapItems = stockGapRows
    .map((row) => stockGapItemFromOrderReview(row, etaBySku.get(cleanSku(pick(row, ["상품코드", "SKU", "sku"], (row as { sku?: unknown }).sku))) ?? []))
    .filter((item) => item.sku && item.sku !== "-");

  return mergeProductIdentity(hydrateProductIdentity(stockGapItems), identityRows);
}

export async function getCurrentStockGapSnapshot(): Promise<CurrentStockGapSnapshot> {
  await wait();
  const result = await getStoredAnalysisResultAsync();
  if (!result) {
    return { status: "missing", jobId: null, entityCode: null, items: [] };
  }
  if (result.job_id !== getCurrentAnalysisJobId()) {
    return {
      status: "stale",
      jobId: result.job_id || null,
      entityCode: result.entity_code ?? null,
      items: []
    };
  }
  if (!hasExplicitCurrentAnalysisResult(result)) {
    return {
      status: "missing",
      jobId: result.job_id || null,
      entityCode: result.entity_code ?? null,
      items: []
    };
  }
  return {
    status: "ready",
    jobId: result.job_id || null,
    entityCode: result.entity_code ?? null,
    items: stockGapItemsFromResult(result)
  };
}

export async function getStockGapItems(options: GetStockGapItemsOptions = {}): Promise<StockGapItem[]> {
  await wait();
  const result = await getStoredAnalysisResultAsync();
  if (!result) {
    return [];
  }
  if (options.requireCurrentSession && result.job_id !== getCurrentAnalysisJobId()) {
    return [];
  }
  return stockGapItemsFromResult(result);
}

type GetSeasonTrendAnalysisOptions = {
  includeLatestFallback?: boolean;
  requireCurrentSession?: boolean;
};

let latestSeasonTrendFallbackPromise: Promise<SeasonTrendAnalyzeResponse | null> | null = null;

async function loadLatestSeasonTrendFallback(): Promise<SeasonTrendAnalyzeResponse | null> {
  const activeRequest =
    latestSeasonTrendFallbackPromise ??
    (latestSeasonTrendFallbackPromise = (async () => {
      const latest = await fetchLatestSeasonTrendResult();
      if (latest) {
        await saveSeasonTrendResult(latest);
      }
      return latest;
    })());
  try {
    return await activeRequest;
  } finally {
    if (latestSeasonTrendFallbackPromise === activeRequest) {
      latestSeasonTrendFallbackPromise = null;
    }
  }
}

export async function getSeasonTrendAnalysis(options: GetSeasonTrendAnalysisOptions = {}) {
  await wait();
  const emptyResult = {
    hasAnalysisResult: false,
    hasSeasonTrendData: false,
    seasonAnalysis: emptySeasonAnalysis,
    ingredientAnalysis: emptyIngredientAnalysis,
    uploadedFileRoles: [],
    uploadedFiles: [],
    analysisOptions: undefined
  };

  if (options.requireCurrentSession && !hasCurrentSeasonTrendResult()) {
    return emptyResult;
  }

  let seasonTrendResult = await getStoredSeasonTrendResult();
  if (!seasonTrendResult && (options.includeLatestFallback ?? true)) {
    try {
      seasonTrendResult = await loadLatestSeasonTrendFallback();
    } catch {
      seasonTrendResult = null;
    }
  }
  const storedAnalysisResult = await getStoredAnalysisResultAsync();
  const result = seasonTrendResult ?? (isStaleSeasonTrendResult(storedAnalysisResult) ? null : storedAnalysisResult);
  const seasonAnalysis = seasonTrendResult?.season_analysis ?? result?.season_analysis ?? emptySeasonAnalysis;
  const ingredientAnalysis = seasonTrendResult?.ingredient_analysis ?? result?.ingredient_analysis ?? emptyIngredientAnalysis;
  const uploadedFileRoles = seasonTrendResult?.uploaded_files?.map((file) => file.role) ?? result?.uploaded_files?.map((file) => file.role) ?? [];
  const uploadedFiles = seasonTrendResult?.uploaded_files ?? result?.uploaded_files ?? [];
  const analysisOptions = seasonTrendResult?.analysis_options;

  return {
    hasAnalysisResult: Boolean(result),
    hasSeasonTrendData: Boolean(
      (seasonAnalysis.category1Monthly?.length ?? 0) > 0 ||
        (seasonAnalysis.countryCategoryMonthly?.length ?? 0) > 0 ||
        (seasonAnalysis.category2Monthly?.length ?? 0) > 0 ||
        (seasonAnalysis.countryCategory2Monthly?.length ?? 0) > 0 ||
        (ingredientAnalysis.summary?.length ?? 0) > 0
    ),
    seasonAnalysis,
    ingredientAnalysis,
    uploadedFileRoles,
    uploadedFiles,
    analysisOptions
  };
}

function normalizedSkuKey(sku: string) {
  const text = cleanSku(sku);
  return text.endsWith(".0") ? text.slice(0, -2) : text;
}

function isMissingProductText(value: string) {
  const text = value.trim();
  return !text || text === "-" || text.includes("상품명 미확인");
}

function isMissingBrandText(value: string) {
  const text = value.trim();
  return !text || text === "-";
}

function mergeProductIdentity<T extends { sku: string; productName: string; brand: string; productCode?: string; barcode?: string }>(
  rows: T[],
  identityRows: Array<{ sku: string; productName: string; brand: string; productCode?: string; barcode?: string }>
): T[] {
  const identityBySku = new Map<string, { productName?: string; brand?: string; productCode?: string; barcode?: string }>();

  for (const row of identityRows) {
    const key = normalizedSkuKey(row.sku);
    if (!key) continue;
    const current = identityBySku.get(key) ?? {};
    if (!current.productName && !isMissingProductText(row.productName)) {
      current.productName = row.productName;
    }
    if (!current.brand && !isMissingBrandText(row.brand)) {
      current.brand = row.brand;
    }
    const productCode = row.productCode && row.productCode !== "-" ? row.productCode : row.sku;
    if (!current.productCode && productCode && productCode !== "-") {
      current.productCode = productCode;
    }
    if (!current.barcode && row.barcode && row.barcode !== "-") {
      current.barcode = row.barcode;
    }
    identityBySku.set(key, current);
  }

  return rows.map((row) => {
    const identity = identityBySku.get(normalizedSkuKey(row.sku));
    if (!identity) return row;
    const productName = isMissingProductText(row.productName) && identity.productName ? identity.productName : row.productName;
    const brand = isMissingBrandText(row.brand) && identity.brand ? identity.brand : row.brand;
    const productCode = (!row.productCode || row.productCode === "-") && identity.productCode ? identity.productCode : row.productCode;
    const barcode = (!row.barcode || row.barcode === "-") && identity.barcode ? identity.barcode : row.barcode;
    return productName === row.productName && brand === row.brand && productCode === row.productCode && barcode === row.barcode
      ? row
      : { ...row, productName, brand, productCode, barcode };
  });
}

function hydrateProductIdentity<T extends { sku: string; productName: string; brand: string; productCode?: string; barcode?: string }>(rows: T[]): T[] {
  const identityBySku = new Map<string, { productName?: string; brand?: string; productCode?: string; barcode?: string }>();

  for (const row of rows) {
    const key = normalizedSkuKey(row.sku);
    if (!key) continue;
    const current = identityBySku.get(key) ?? {};
    if (!current.productName && !isMissingProductText(row.productName)) {
      current.productName = row.productName;
    }
    if (!current.brand && !isMissingBrandText(row.brand)) {
      current.brand = row.brand;
    }
    if (!current.productCode && row.productCode && row.productCode !== "-") {
      current.productCode = row.productCode;
    }
    if (!current.barcode && row.barcode && row.barcode !== "-") {
      current.barcode = row.barcode;
    }
    identityBySku.set(key, current);
  }

  return rows.map((row) => {
    const identity = identityBySku.get(normalizedSkuKey(row.sku));
    if (!identity) return row;
    const productName = isMissingProductText(row.productName) && identity.productName ? identity.productName : row.productName;
    const brand = isMissingBrandText(row.brand) && identity.brand ? identity.brand : row.brand;
    const productCode = (!row.productCode || row.productCode === "-") && identity.productCode ? identity.productCode : row.productCode;
    const barcode = (!row.barcode || row.barcode === "-") && identity.barcode ? identity.barcode : row.barcode;
    return productName === row.productName && brand === row.brand && productCode === row.productCode && barcode === row.barcode
      ? row
      : { ...row, productName, brand, productCode, barcode };
  });
}
