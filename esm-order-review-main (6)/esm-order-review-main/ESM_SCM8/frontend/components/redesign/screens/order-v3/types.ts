export type OrderV3DataStatus = "정상" | "대량포함" | "확인(간헐)" | "이력부족" | "계산차단" | "발주보류";

export type OrderV3Pattern = "안정형" | "추세형" | "간헐형" | "신규/이력부족";

export type OrderV3Engine = "SES" | "HOLT+감쇠" | "Croston+SBA" | "이동평균" | "미분류";

export type OrderV3ReviewDecision = "미검토" | "권고 유지" | "수량 수정" | "발주 보류";

export type OrderV3Signal = "즉시 발주" | "확인 후 발주" | "발주 제외" | "계산 차단";

export type OrderV3Scenario = "CASH" | "SHORTAGE";

export type OrderV3Row = {
  sku: string;
  productName: string;
  brand: string;
  barcode?: string;
  calculable?: boolean;
  validationCode?: string | null;
  validationError?: string | null;
  inventoryWarnings?: string[];
  dataStatus: OrderV3DataStatus;
  pattern: OrderV3Pattern;
  engine: OrderV3Engine;
  seasonalApplied: boolean;
  seasonFactorVersion?: string | null;
  functionClass1?: string | null;
  functionClass2?: string | null;
  seasonFactorAvailable?: boolean | null;
  seasonFactorScope?: "FUNCTION_CLASS_1_AND_2" | "FUNCTION_CLASS_1" | null;
  seasonFactorsByMonth?: Record<string, number>;
  seasonFactorDefaulted?: boolean;
  seasonFactorOriginalReasonCode?: string | null;
  seasonFactorOriginalMessage?: string | null;
  seasonalFactors?: { f1: number | null; f2: number | null; fLR: number | null };
  seasonFactorReview?: {
    artifactStatus: string;
    seasonalityStatus: string;
    reasonCode?: string | null;
    windowStart?: string | null;
    windowEnd?: string | null;
    factorsByMonth: Record<string, number>;
  };
  inventorySourceReview?: {
    status: string;
    missingFields: string[];
  };
  averageDemand: number;
  forecastRmse: number;
  crostonForecastCap?: number | null;
  crostonForecastCapped?: boolean | null;
  inventoryPosition: number;
  reorderPoint: number;
  targetStock: number;
  suggestedQty: number;
  /** Server pack-rounded final quantity (outbox -> inbox -> 10-unit). */
  finalOrderQty: number;
  orderUnitQty?: number | null;
  orderUnitSource?: "OUTBOX" | "INBOX" | "FALLBACK_10" | null;
  inboxQty?: number | null;
  outboxQty?: number | null;
  cashSuggestedQty: number;
  shortageSuggestedQty: number;
  cashFinalOrderQty: number;
  shortageFinalOrderQty: number;
  cashOrderAmountKrw?: number | null;
  shortageOrderAmountKrw?: number | null;
  orderAmountKrw: number;
  signal: OrderV3Signal;
  adiLabel: "낮음" | "보통" | "높음";
  cv2Label: "낮음" | "보통" | "높음";
  trendLabel: "있음" | "없음";
  firstSaleDate?: string | null;
  analysisSalesCutoff?: string | null;
  calendarDaysSinceFirstSale?: number | null;
  isNewSku?: boolean | null;
  leadTimeDays?: number | null;
  reviewDays?: number | null;
  leadTimeSigmaDays?: number | null;
  salesHistory: number[];
  adjustedForecast: number[];
  targetLayers: {
    leadTimeDemand: number;
    safetyStockRaw: number;
    safetyStock: number;
    safetyStockFloor: number;
    safetyStockCap: number;
    reviewDemand: number;
  };
  inventoryParts: {
    localAvailable: number;
    incoming: number;
    hqAvailable: number;
    inTransit: number;
    holding?: number;
  };
  coefficients: {
    alpha: number | null;
    beta: number | null;
    phi: number | null;
  };
  leadTimePolicy?: {
    transportMode: string;
    leadTimeDays: number;
    reviewDays: number;
    sigmaDays: number;
    safetyStockFloorPeriods: number;
    safetyStockCapPeriods: number;
    source: string;
    sampleSize?: number | null;
    completionFrom?: string | null;
    completionTo?: string | null;
  };
};

export type OrderV3DecisionState = {
  decision: OrderV3ReviewDecision;
  finalQty: number;
};
