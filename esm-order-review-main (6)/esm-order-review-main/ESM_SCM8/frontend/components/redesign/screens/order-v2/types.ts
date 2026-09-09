export type NewOrderPolicyMode = "SHORTAGE" | "CASH";

export type NewOrderProductGrade = "주력" | "일반";

export type NewOrderDataStatus =
  | "정상"
  | "확인필요"
  | "판매없음"
  | "확인(간헐)"
  | "대량포함"
  | "이력부족";

export type NewOrderSignal = "발주" | "확인후발주" | "충분" | "-";

export type NewOrderTransportCode = "AIR" | "RAIL" | "SEA";

/** HQ replenishes domestically, so it has no shipping transport mode. */
export type NewOrderSourcingCode = NewOrderTransportCode | "HQ_DOMESTIC";

export type NewOrderCurrencyCode = "EUR" | "USD" | "KRW";

export type NewOrderPeriodUnit = "week" | "day";

export type NewOrderModeResult = {
  transportMode?: NewOrderTransportCode;
  zApplied: number | null;
  leadTimeDays: number | null;
  leadTimeSigmaWeeks: number | null;
  safetyStock: number | null;
  reorderPoint: number | null;
  targetStock: number | null;
  suggestedQty: number | null;
  upperSuggestedQty: number | null;
  signal: NewOrderSignal;
  referenceAmountEur?: number | null;
  referenceAmountKrw?: number | null;
};

export type NewOrderLogicRow = {
  id: string;
  productCode: string;
  productName: string;
  brand: string;
  dataStatus: NewOrderDataStatus;
  grade: NewOrderProductGrade | null;
  isCalculable: boolean;
  decisionLockReason?: string;
  weeklyMean: number | null;
  cv: number | null;
  inboundQty: number;
  euAvailableQty: number;
  inTransitQty: number;
  localAvailableQty: number;
  inventoryPosition: number;
  inventoryPositionWithoutIncoming: number;
  nextEta: string | null;
  nextEtaStatus:
    | "원천 ETA"
    | "출고일 추정 ETA"
    | "원천·추정 ETA"
    | "ETA 미확인"
    | "입고 예정 없음";
  /** 참고 표시 전용: (현지가용 + 운송중) ÷ 주평균. 품절이력 보정값이 아닙니다. */
  stockoutWeeks: number | null;
  confirmedQty?: number | null;
  memo?: string;
  unitPriceEur?: number | null;
  unitPriceKrw?: number | null;
  modes: Record<NewOrderPolicyMode, NewOrderModeResult>;
  comparisonReasonsByMode: Record<NewOrderPolicyMode, string[]>;
};

export type NewOrderLeadTimeSetting = {
  code: NewOrderTransportCode;
  label: string;
  meanDays: number;
  sigmaWeeks: number;
  // 법인 리드타임 API 실측 표본에서 산출된 값이면 표본 수가 채워진다.
  // 기술명세 고정값을 그대로 쓰는 운송수단은 undefined로 남는다.
  measuredSampleSize?: number;
  // 실측 표본의 입고 완료 기간. 표본 수와 함께 근거를 밝히는 데 쓴다.
  measuredWindowFrom?: string;
  measuredWindowTo?: string;
  // API 응답에 해당 운송수단 값이 없어 실측·명세값 어느 쪽으로도
  // 확정할 수 없는 상태. 화면에서 숫자를 단정하지 않고 확인 필요로 알린다.
  valueUnavailable?: boolean;
};

// HQ/OPO는 운송수단이 없다. 국내조달 리드타임 하나를 일 단위로 사용하며,
// 값은 `실입고일 - PO 생성일` 실측 집계에서 나온다.
export type NewOrderDomesticLeadTimeSetting = {
  meanDays: number;
  sigmaDays: number;
  reviewDays: number;
  safetyStockFloorDays: number;
  safetyStockCapDays: number;
  measuredSampleSize?: number;
  measuredWindowMonths?: number;
  valueUnavailable?: boolean;
};

export type NewOrderLogicPolicySettings = {
  policyMode: NewOrderPolicyMode;
  demandWeeks: number;
  gradeCutoffPct: number;
  minWeeksWithSales: number;
  bulkSalesMultiple: number;
  coverWeeks: number;
  reviewBufferDays: number;
  safetyStockFloorWeeks: number;
  safetyStockCapWeeks: number;
  zMatrix: {
    shortageMajor: number;
    shortageMinor: number;
    cashMajor: number;
    cashMinor: number;
  };
  policyTransports: Record<NewOrderPolicyMode, NewOrderTransportCode>;
  leadTimes: NewOrderLeadTimeSetting[];
  // 본사 전용. PL/USA 결과에는 존재하지 않는다.
  domesticLeadTime?: NewOrderDomesticLeadTimeSetting;
};

export type NewOrderLogicMeta = {
  jobId: string;
  logicVersion: string;
  currencyCode: NewOrderCurrencyCode;
  appliedMode: NewOrderPolicyMode;
  sourceAsOf: string;
  calculatedAt: string;
  demandPeriod: {
    from: string;
    to: string;
    completedWeeks: number;
    observationWindowDays?: number;
    demandGrain?: "DAY_1D" | "WEEK_7D";
  };
  /** HQ reports day-grain demand; PL/USA report week-grain demand. */
  periodUnit: NewOrderPeriodUnit;
  entityCode?: string;
  warehouseCode?: string;
  sourceSnapshotId?: string;
  warnings?: string[];
};

export type NewOrderLogicDataset = {
  meta: NewOrderLogicMeta;
  rows: NewOrderLogicRow[];
};

export type NewOrderSimulationSummary = {
  mode: NewOrderPolicyMode;
  orderSkuCount: number;
  confirmSkuCount: number;
  totalSuggestedQty: number;
  totalReferenceAmountEur?: number | null;
};

export type NewOrderSimulationResult = {
  jobId: string;
  simulatedAt: string;
  baseline: NewOrderSimulationSummary;
  candidate: NewOrderSimulationSummary;
  changedSkuCount: number;
};

export type NewOrderLogicTab = "proposal" | "comparison" | "settings";

export type NewOrderFilterState = {
  brand: string;
};

export type NewOrderExportContext = {
  jobId: string | null;
  tab: NewOrderLogicTab;
  appliedMode: NewOrderPolicyMode;
  filters: NewOrderFilterState;
  rowIds: string[];
};

export type NewOrderLogicScreenProps = {
  entityCode?: string | null;
  data?: NewOrderLogicDataset | null;
  settings: NewOrderLogicPolicySettings;
  defaultSettings?: NewOrderLogicPolicySettings;
  exchangeRateKrw?: number | null;
  exchangeRateDate?: string | null;
  exchangeRateSource?: string | null;
  simulation?: NewOrderSimulationResult | null;
  loading?: boolean;
  running?: boolean;
  cancelling?: boolean;
  simulating?: boolean;
  applyingSettings?: boolean;
  exportingExcel?: boolean;
  error?: string | null;
  canViewAmountData?: boolean;
  canEditAdvancedSettings?: boolean;
  className?: string;
  onRetry?: () => void;
  onRun?: (settings: NewOrderLogicPolicySettings) => void | Promise<void>;
  onCancelRun?: () => void | Promise<void>;
  onExportExcel?: (context: NewOrderExportContext) => void | Promise<void>;
  onSettingsChange?: (settings: NewOrderLogicPolicySettings) => void;
  onSimulate?: (settings: NewOrderLogicPolicySettings) => void | Promise<void>;
  onApplySettings?: (settings: NewOrderLogicPolicySettings) => void | Promise<void>;
  onConfirmedQtyChange?: (rowId: string, quantity: number | null) => void;
  onMemoChange?: (rowId: string, memo: string) => void;
};
