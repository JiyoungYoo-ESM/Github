import type { StockGapEtaItem, StockGapItem, StockGapStatus } from "@/types/api";

export type GapTiming = "none" | "active" | "future" | "ended" | "unknown";

export type StockGapComputedItem = Omit<StockGapItem, "stockoutDate" | "earliestEtaDate" | "etaItems"> & {
  baseDate: string | null;
  dailySalesQty: number | null;
  stockoutDate: Date | null;
  backendStockoutDate: Date | null;
  earliestEta: StockGapEtaItem | null;
  earliestEtaDate: Date | null;
  pastEtaDate: Date | null;
  gapDays: number | null;
  gapTiming: GapTiming;
  status: StockGapStatus;
  stockoutBasis: string;
  etaItems: StockGapEtaItem[];
};

export type TimelinePoint = {
  key: string;
  label: "오늘" | "재고 소진" | "가장 빠른 ETA" | "추가 입고";
  date: Date;
  quantity?: number;
  transportMode?: string;
  kind: "today" | "stockout" | "eta";
  isEarliestEta?: boolean;
};

export const stockGapStatusLabels: Record<StockGapStatus, string> = {
  sufficient: "정상",
  waiting_eta: "주의",
  stock_gap: "주의",
  stockout_no_inbound: "입고예정 없음",
  urgent_replenishment: "긴급보충",
  needs_check: "확인필요"
};

export const stockGapStatusOrder: StockGapStatus[] = [
  "urgent_replenishment",
  "stock_gap",
  "stockout_no_inbound",
  "waiting_eta",
  "needs_check",
  "sufficient"
];

export const DAY_MS = 24 * 60 * 60 * 1000;
const SAFE_STOCKOUT_DAYS_WITHOUT_ETA = 90;

export function startOfDay(date: Date) {
  const next = new Date(date);
  next.setHours(0, 0, 0, 0);
  return next;
}

export function dayDiff(from: Date, to: Date) {
  return Math.round((startOfDay(to).getTime() - startOfDay(from).getTime()) / DAY_MS);
}

export function parseDate(value: string | Date | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : startOfDay(value);
  }

  const text = String(value).trim();
  const match = text.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/);
  if (match) {
    const [, year, month, day] = match;
    const date = new Date(Number(year), Number(month) - 1, Number(day));
    return Number.isNaN(date.getTime()) ? null : startOfDay(date);
  }

  const date = new Date(`${text.slice(0, 10)}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : startOfDay(date);
}

export function formatDate(value: Date | string | null | undefined): string {
  const date = value instanceof Date ? value : parseDate(value);
  if (!date) {
    return "-";
  }
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function calculateDailySales(recent3mSalesQty: number | null): number | null {
  if (recent3mSalesQty === null || !Number.isFinite(recent3mSalesQty) || recent3mSalesQty <= 0) {
    return null;
  }
  return recent3mSalesQty / 90;
}

export function calculateStockoutDate(baseDate: Date, availableQty: number, dailySalesQty: number): Date | null {
  if (!Number.isFinite(availableQty) || !Number.isFinite(dailySalesQty) || availableQty < 0 || dailySalesQty <= 0) {
    return null;
  }

  const daysUntilStockout = Math.max(Math.floor(availableQty / dailySalesQty), 0);
  const date = startOfDay(baseDate);
  date.setDate(date.getDate() + daysUntilStockout);
  return date;
}

export function groupEtaItems(etaItems: StockGapEtaItem[]): StockGapEtaItem[] {
  const grouped = new Map<string, StockGapEtaItem>();

  for (const item of etaItems) {
    const etaDate = parseDate(item.eta);
    if (!etaDate || item.inTransitQty <= 0) {
      continue;
    }
    const key = formatDate(etaDate);
    const current = grouped.get(key);
    if (!current) {
      grouped.set(key, {
        ...item,
        eta: formatDate(etaDate),
        transportMode: normalizeTransportMode(item.transportMode)
      });
      continue;
    }
    current.inTransitQty += item.inTransitQty;
    if (current.transportMode !== normalizeTransportMode(item.transportMode)) {
      current.transportMode = "혼합";
    }
    current.referenceNo = [current.referenceNo, item.referenceNo].filter(Boolean).join(", ");
    current.note = [current.note, item.note].filter(Boolean).join(" / ");
  }

  return Array.from(grouped.values()).sort((a, b) => Number(parseDate(a.eta)) - Number(parseDate(b.eta)));
}

export function getEarliestEta(etaItems: StockGapEtaItem[], minDate?: Date): StockGapEtaItem | null {
  const min = minDate ? startOfDay(minDate) : null;
  return (
    [...etaItems]
      .filter((item) => {
        const etaDate = parseDate(item.eta);
        return item.inTransitQty > 0 && etaDate && (!min || etaDate.getTime() >= min.getTime());
      })
      .sort((a, b) => Number(parseDate(a.eta)) - Number(parseDate(b.eta)))[0] ?? null
  );
}

export function getLatestPastEta(etaItems: StockGapEtaItem[], baseDate: Date): StockGapEtaItem | null {
  const base = startOfDay(baseDate);
  return (
    [...etaItems]
      .filter((item) => {
        const etaDate = parseDate(item.eta);
        return item.inTransitQty > 0 && etaDate && etaDate.getTime() < base.getTime();
      })
      .sort((a, b) => Number(parseDate(b.eta)) - Number(parseDate(a.eta)))[0] ?? null
  );
}

export function calculateGapDays(stockoutDate: Date | null, earliestEta: Date | null): number | null {
  if (!stockoutDate || !earliestEta) {
    return null;
  }
  return Math.max(dayDiff(stockoutDate, earliestEta), 0);
}

export function getGapTiming(baseDate: Date, stockoutDate: Date | null, earliestEtaDate: Date | null): GapTiming {
  if (!stockoutDate || !earliestEtaDate) {
    return "unknown";
  }
  if (earliestEtaDate.getTime() <= stockoutDate.getTime()) {
    return "none";
  }
  if (baseDate.getTime() > earliestEtaDate.getTime()) {
    return "ended";
  }
  if (baseDate.getTime() >= stockoutDate.getTime()) {
    return "active";
  }
  return "future";
}

export function normalizeTransportMode(mode: string | null | undefined) {
  const text = String(mode ?? "").trim();
  if (!text || text === "-") {
    return "미확인";
  }
  if (text.includes("항공") || text.toLowerCase().includes("air")) {
    return "항공특송";
  }
  if (text.includes("해운") || text.includes("해상") || text.toLowerCase().includes("sea")) {
    return "해운";
  }
  if (text.includes("철송") || text.includes("철도") || text.toLowerCase().includes("rail")) {
    return "철도";
  }
  if (text.includes("트럭") || text.includes("육상") || text.toLowerCase().includes("truck")) {
    return "트럭";
  }
  return text;
}

function determineStockGapStatus(params: {
  baseDate: Date;
  availableQty: number | null;
  dailySalesQty: number | null;
  stockoutDate: Date | null;
  earliestEtaDate: Date | null;
  gapDays: number | null;
  gapTiming: GapTiming;
  riskScore?: number;
  backendStatus?: string;
  priorityAction?: string;
  riskReason?: string;
  preArrivalStockoutRisk?: boolean;
  etaDelayFlag?: boolean;
  urgentReplenishmentQty?: number;
  urgentAction?: string;
}): StockGapStatus {
  const decisionText = [
    params.backendStatus,
    params.priorityAction,
    params.riskReason,
    params.urgentAction
  ].filter(Boolean).join(" ");

  if (decisionText.includes("확인필요") || decisionText.includes("확인 필요")) {
    return "needs_check";
  }
  if (params.availableQty === null || params.dailySalesQty === null || !params.stockoutDate) {
    return "needs_check";
  }
  if (
    params.gapTiming === "active" ||
    params.preArrivalStockoutRisk ||
    params.etaDelayFlag ||
    decisionText.includes("ETA 지연") ||
    decisionText.includes("결품")
  ) {
    return (params.gapDays ?? 0) >= 7 || (params.urgentReplenishmentQty ?? 0) > 0 || decisionText.includes("긴급")
      ? "urgent_replenishment"
      : "stock_gap";
  }
  if (params.gapTiming === "future") {
    return (params.gapDays ?? 0) >= 7 || (params.riskScore ?? 0) >= 90 ? "urgent_replenishment" : "stock_gap";
  }
  if (!params.earliestEtaDate) {
    const daysUntilStockout = dayDiff(params.baseDate, params.stockoutDate);
    if (daysUntilStockout >= SAFE_STOCKOUT_DAYS_WITHOUT_ETA) {
      return "sufficient";
    }
    // 이미 소진됐고 예정된 입고가 없으면 공백이 언제 끝나는지 계산할 수 없다. 이 행을
    // 확인필요(중립)로 묶으면 판매 이력조차 없는 행들과 섞여 묻힌다. 공백 구간을 계산할 수
    // 있는 재고공백(긴급) 집계와는 분리해 별도 상태로 남긴다.
    return params.stockoutDate.getTime() <= params.baseDate.getTime() ? "stockout_no_inbound" : "waiting_eta";
  }
  return "sufficient";
}

/**
 * 판매 이력·현재고·운송중·미입고가 모두 없는 행. 참조 엑셀 양식과 행 수를 맞추려고 결과에
 * 남겨 두는 SKU라서 재고 공백을 판정할 근거가 아예 없다. 기본 목록에서 빼지 않으면 확인필요
 * 버킷의 대부분을 차지해 실제로 봐야 할 행을 가린다.
 */
export function isDormantStockGapItem(item: {
  availableQty?: number | null;
  recent3mSalesQty?: number | null;
  avgDailySalesQty?: number | null;
  inTransitQty?: number | null;
  openPoQty?: number | null;
}): boolean {
  const empty = (value: number | null | undefined) => !Number.isFinite(Number(value)) || Number(value) <= 0;
  return (
    empty(item.availableQty) &&
    empty(item.recent3mSalesQty) &&
    empty(item.avgDailySalesQty) &&
    empty(item.inTransitQty) &&
    empty(item.openPoQty)
  );
}

export function calculateStockGapShortageQty(item: {
  gapDays?: number | null;
  dailySalesQty?: number | null;
}): number {
  const gapDays = Number(item.gapDays ?? 0);
  const dailySalesQty = Number(item.dailySalesQty ?? 0);
  if (!Number.isFinite(gapDays) || !Number.isFinite(dailySalesQty) || gapDays <= 0 || dailySalesQty <= 0) {
    return 0;
  }
  return Math.ceil(gapDays * dailySalesQty);
}

export function buildTimelinePoints(item: StockGapComputedItem): TimelinePoint[] {
  const baseDate = parseDate(item.baseDate) ?? startOfDay(new Date());
  const points: TimelinePoint[] = [
    {
      key: "today",
      label: "오늘",
      date: baseDate,
      kind: "today"
    }
  ];

  if (item.stockoutDate) {
    points.push({
      key: "stockout",
      label: "재고 소진",
      date: item.stockoutDate,
      kind: "stockout"
    });
  }

  for (const eta of item.etaItems) {
    const etaDate = parseDate(eta.eta);
    if (!etaDate) {
      continue;
    }
    points.push({
      key: `eta-${eta.eta}-${eta.transportMode}`,
      label: eta === item.earliestEta ? "가장 빠른 ETA" : "추가 입고",
      date: etaDate,
      quantity: eta.inTransitQty,
      transportMode: eta.transportMode,
      kind: "eta",
      isEarliestEta: eta === item.earliestEta
    });
  }

  return points.sort((a, b) => a.date.getTime() - b.date.getTime());
}

export function validateTimelineOrder(item: StockGapComputedItem) {
  const baseDate = parseDate(item.baseDate) ?? startOfDay(new Date());
  const points = buildTimelinePoints(item);
  const outOfOrder = points.some((point, index) => index > 0 && point.date.getTime() < points[index - 1].date.getTime());
  const stockoutBeforeBase = item.stockoutDate && item.stockoutDate.getTime() < baseDate.getTime();
  // 기준일 이전 ETA는 pastEtaDate로 분리해 화면에 표시하므로 더 이상 이상 신호가 아니다.
  const etaBeforeBase = item.earliestEtaDate && item.earliestEtaDate.getTime() < baseDate.getTime();
  const backendMismatch =
    item.backendStockoutDate &&
    item.stockoutDate &&
    Math.abs(dayDiff(item.backendStockoutDate, item.stockoutDate)) >= 1;

  if (outOfOrder || stockoutBeforeBase || etaBeforeBase || backendMismatch) {
    console.warn("[stock-gap] timeline consistency check", {
      sku: item.sku,
      baseDate: formatDate(baseDate),
      stockoutDate: formatDate(item.stockoutDate),
      backendStockoutDate: formatDate(item.backendStockoutDate),
      earliestEtaDate: formatDate(item.earliestEtaDate),
      pastEtaDate: formatDate(item.pastEtaDate),
      outOfOrder,
      stockoutBeforeBase,
      etaBeforeBase,
      backendMismatch
    });
  }
}

export function computeStockGapItem(item: StockGapItem, fallbackBaseDate = new Date()): StockGapComputedItem {
  const baseDate = parseDate(item.baseDate) ?? startOfDay(fallbackBaseDate);
  const dailySalesQty = item.avgDailySalesQty ?? calculateDailySales(item.recent3mSalesQty);
  const availableQty = item.availableQty === null ? null : Math.max(item.availableQty, 0);
  const backendStockoutDate = parseDate(item.stockoutDate);
  const stockoutDate =
    availableQty === null || dailySalesQty === null ? null : calculateStockoutDate(baseDate, availableQty, dailySalesQty);
  const etaItems = groupEtaItems(item.etaItems);
  const earliestEta = getEarliestEta(etaItems, baseDate);
  // 기준일보다 이른 ETA는 이미 입고됐거나 지연된 건이고, 입고 완료 상태는 데이터에 없다.
  // 미래 입고처럼 쓰면 "ETA가 소진일보다 빠르니 공백 없음"으로 잘못 안전 판정된다.
  // 백엔드 긴급 보충 계산(apply_pre_arrival_shortage_risk)도 미래 ETA만 쓴다.
  const reportedEtaDate = parseDate(item.earliestEtaDate);
  const upcomingReportedEtaDate =
    reportedEtaDate && reportedEtaDate.getTime() >= baseDate.getTime() ? reportedEtaDate : null;
  const earliestEtaDate = parseDate(earliestEta?.eta) ?? upcomingReportedEtaDate;
  const pastEtaDate = earliestEtaDate
    ? null
    : parseDate(getLatestPastEta(etaItems, baseDate)?.eta) ?? reportedEtaDate;
  const gapDays = calculateGapDays(stockoutDate, earliestEtaDate);
  const gapTiming = getGapTiming(baseDate, stockoutDate, earliestEtaDate);
  const stockoutBasis =
    availableQty === null || dailySalesQty === null
      ? "소진일 계산 불가: 현재 가용재고 또는 일평균 판매량이 없습니다."
      : `소진일 기준: 기준일 ${formatDate(baseDate)} + floor(현재 가용재고 ${availableQty.toLocaleString("ko-KR")} ÷ 일평균 판매량 ${dailySalesQty.toLocaleString("ko-KR", { maximumFractionDigits: 1 })})일`;
  const status = determineStockGapStatus({
    baseDate,
    availableQty,
    dailySalesQty,
    stockoutDate,
    earliestEtaDate,
    gapDays,
    gapTiming,
    riskScore: item.riskScore,
    backendStatus: item.backendStatus,
    priorityAction: item.priorityAction,
    riskReason: item.riskReason,
    preArrivalStockoutRisk: item.preArrivalStockoutRisk,
    etaDelayFlag: item.etaDelayFlag,
    urgentReplenishmentQty: item.urgentReplenishmentQty,
    urgentAction: item.urgentAction
  });

  const computed = {
    ...item,
    baseDate: formatDate(baseDate),
    availableQty,
    etaItems,
    dailySalesQty,
    stockoutDate,
    backendStockoutDate,
    earliestEta,
    earliestEtaDate,
    pastEtaDate,
    gapDays,
    gapTiming,
    status,
    stockoutBasis
  };

  validateTimelineOrder(computed);
  return computed;
}
