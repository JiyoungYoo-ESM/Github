import type {
  EtaEvent,
  OrderReviewRow,
  StockGapEtaItem,
  StockGapItem
} from "@/types/api";

export function readNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : fallback;
  }
  if (typeof value === "string") {
    const parsed = Number(value.replace(/[,₩€$]/g, "").trim());
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

export function readNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = readNumber(value, Number.NaN);
  return Number.isFinite(parsed) ? parsed : null;
}

export function readText(value: unknown, fallback = ""): string {
  if (value === null || value === undefined) {
    return fallback;
  }
  const text = String(value).trim();
  return text || fallback;
}

export function pick(row: Record<string, unknown>, keys: string[], fallback: unknown = ""): unknown {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(row, key) && row[key] !== null && row[key] !== undefined && row[key] !== "") {
      return row[key];
    }
  }
  return fallback;
}

export function cleanSku(value: unknown): string {
  return readText(value, "").trim();
}

export function readFlag(value: unknown): boolean {
  const text = readText(value).toUpperCase();
  return text === "Y" || text === "TRUE" || text === "1" || text === "YES";
}

// 백엔드 `상태`가 발주제외/확인필요면 발주 대상이 아니다. 예전에 저장된 분석 결과에는
// 제외 행에도 발주필요수량이 남아 있을 수 있어 화면·합계 모두 이 판정을 기준으로 막는다.
const excludedBackendStatuses = new Set(["발주제외", "확인필요"]);

export function isOrderExcludedRow(row: Pick<OrderReviewRow, "backendStatus">) {
  return excludedBackendStatuses.has((row.backendStatus ?? "").trim());
}

export function isRequiredOrderReviewRow(row: OrderReviewRow) {
  if (isOrderExcludedRow(row)) {
    return false;
  }
  const action = row.priorityAction.replace(/\s+/g, "");
  const explicitlyNotRequired = action.includes("불필요") || action.includes("불요") || action.includes("제외");
  if (explicitlyNotRequired) {
    return false;
  }
  return row.requiredOrderQty > 0 || row.requiredOrderAmount > 0 || action.includes("발주필요");
}

export function orderReviewRowFromTable(row: Record<string, unknown>): OrderReviewRow {
  const direct = row as Partial<Record<keyof OrderReviewRow, unknown>>;
  const productCode = readText(direct.productCode ?? direct.sku ?? pick(row, ["상품코드", "productCode", "prod_cd", "품목코드", "코드", "SKU", "sku"]), "-");
  const barcode = readText(direct.barcode ?? pick(row, ["바코드", "barcode", "barCode", "bar_code"]), "");
  const recentSalesQty = readNumber(direct.recentSalesQty ?? pick(row, ["최근 3개월 수요", "최근 3개월 판매수량", "PA+CA 판매수량", "판매수량 기준", "recentSalesQty"]));
  const euAvailableStock = readNumber(
    direct.euAvailableStock ??
      pick(row, ["EU 현지 가용수량", "EU 현지 재고", "현지 창고재고", "EU 창고재고", "EU 가용재고", "유럽 가용재고", "유럽 재고", "현재 가용재고"])
  );
  const requiredOrderQty = readNumber(
    direct.requiredOrderQty ?? pick(row, ["발주필요수량", "발주 필요수량", "추가 발주 필요 수량", "발주 필요 수량", "최종 부족수량", "부족수량"])
  );
  const requiredOrderAmount = readNumber(
    direct.requiredOrderAmount ??
      pick(row, ["발주 필요 금액", "발주필요금액", "발주금액", "발주필요금액_KRW", "발주필요금액(KRW)", "=발주 금액(KRW)", "부족금액_KRW", "추가 발주 필요 금액", "부족금액_EUR"])
  );
  const explicitUnitPrice = readNullableNumber(direct.unitPrice ?? pick(row, ["현지 입고단가", "현지 입고단가(EUR)", "현지 입고단가(USD)", "EU 입고단가(EUR)", "EU 입고단가", "입고단가", "단가", "unitPrice"]));
  const unitPrice = explicitUnitPrice ?? (requiredOrderQty > 0 && requiredOrderAmount > 0 ? requiredOrderAmount / requiredOrderQty : null);
  const salesAmount = readNullableNumber(
    pick(row, ["최근 3개월 판매금액(KRW)", "최근 3개월 판매금액", "판매금액(KRW)", "판매금액_KRW", "환산금액", "환산금액(KRW)", "amount_krw", "salesAmount"])
  );
  const stockAmount = readNullableNumber(
    pick(row, ["재고 평가액(KRW)", "재고금액(KRW)", "재고금액_KRW", "stockAmount"])
  );
  const shortageQty =
    readNullableNumber(
      direct.shortageQty ??
        pick(row, ["부족수량", "최종 부족수량", "발주필요수량", "추가 발주 필요 수량", "발주 필요 수량", "requiredOrderQty"])
    ) ?? requiredOrderQty;
  const stockoutDate = readText(direct.stockoutDate ?? pick(row, ["예상 소진일", "고갈 예상일", "재고 소진 예정일", "stockoutDate"]), "") || null;
  const earliestEtaDate =
    readText(direct.earliestEtaDate ?? pick(row, ["예상 입고일", "첫 입고 예정일", "최초 ETA", "가장 빠른 ETA", "earliestEtaDate"]), "") || null;
  const urgentReplenishmentQty = readNullableNumber(
    direct.urgentReplenishmentQty ?? pick(row, ["긴급 보충 필요 수량", "입고 전 예상 결품량", "urgentReplenishmentQty"])
  );

  return {
    sku: productCode,
    productCode,
    barcode,
    productName: readText(direct.productName ?? pick(row, ["상품명", "productName", "제품명"]), "-"),
    brand: readText(direct.brand ?? pick(row, ["브랜드", "brand"]), "-"),
    recentSalesQty,
    monthlyDemand: readNumber(direct.monthlyDemand ?? pick(row, ["월평균 판매수량", "월평균", "월평균 판매수량(기준/3)", "monthlyDemand"])),
    euAvailableStock,
    shippingQty: readNumber(direct.shippingQty ?? pick(row, ["운송중 수량", "운송중", "shippingQty"])),
    inboundQty: readNumber(direct.inboundQty ?? pick(row, ["미입고수량", "미입고 수량", "미입고현황", "미입고", "미입고 현황", "inboundQty"])),
    requiredOrderQty,
    requiredOrderAmount,
    priorityAction: readText(direct.priorityAction ?? pick(row, ["우선 액션", "최종 액션", "상태", "priorityAction"]), "-"),
    riskReason: readText(direct.riskReason ?? pick(row, ["판단 사유", "근거", "조치 요약", "예외 사유", "riskReason"]), "-"),
    salesAmount,
    stockAmount,
    unitPrice,
    abcGrade: readText(pick(row, ["ABC 등급", "등급", "abcGrade"]), ""),
    shortageQty,
    stockoutDate,
    earliestEtaDate,
    backendStatus: readText(direct.backendStatus ?? pick(row, ["상태", "backendStatus"]), ""),
    preArrivalStockoutRisk: readFlag(direct.preArrivalStockoutRisk ?? pick(row, ["입고 전 결품 위험 여부", "입고 전 품절 여부", "preArrivalStockoutRisk"])),
    etaDelayFlag: readFlag(direct.etaDelayFlag ?? pick(row, ["ETA 지연 플래그", "입고지연위험", "etaDelayFlag"])),
    openPoEtaUnknown: readFlag(direct.openPoEtaUnknown ?? pick(row, ["ETA미확인", "ETA 미확인", "openPoEtaUnknown"])),
    urgentReplenishmentQty,
    urgentAction: readText(direct.urgentAction ?? pick(row, ["권장 긴급 액션", "운송 검토안", "운송수단 검토안", "urgentAction"]), "")
  };
}

export function etaEventFromTable(row: Record<string, unknown>): EtaEvent {
  return {
    date: readText(pick(row, ["도착일", "계산 ETA", "ETA", "도착 예정월", "date"]), "-"),
    mode: readText(pick(row, ["운송수단", "mode"]), "-"),
    skuCount: readNumber(pick(row, ["SKU 수", "skuCount", "SKU수"])),
    quantity: readNumber(pick(row, ["총 도착 수량", "수량", "quantity"])),
    status: readText(pick(row, ["위험도", "상태", "status"]), "정상")
  };
}

export function etaEventsFromRows(rows: Array<Record<string, unknown>>): EtaEvent[] {
  const grouped = new Map<string, { date: string; mode: string; skuSet: Set<string>; quantity: number; status: string }>();

  for (const row of rows) {
    const date = readText(pick(row, ["도착일", "계산 ETA", "ETA", "도착 예정월", "date"]), "");
    const mode = readText(pick(row, ["운송수단", "mode"]), "-");
    const quantity = readNumber(pick(row, ["총 도착 수량", "수량", "quantity"]));
    const sku = cleanSku(pick(row, ["상품코드", "SKU", "sku"]));

    if (!date || quantity <= 0) {
      continue;
    }

    const key = `${date}__${mode}`;
    const current = grouped.get(key) ?? {
      date,
      mode,
      skuSet: new Set<string>(),
      quantity: 0,
      status: readText(pick(row, ["위험도", "상태", "status"]), "정상")
    };
    if (sku) {
      current.skuSet.add(sku);
    }
    current.quantity += quantity;
    grouped.set(key, current);
  }

  return Array.from(grouped.values())
    .map((item) => ({
      date: item.date,
      mode: item.mode,
      skuCount: item.skuSet.size,
      quantity: item.quantity,
      status: item.status
    }))
    .sort((a, b) => a.date.localeCompare(b.date) || a.mode.localeCompare(b.mode));
}

export function etaItemFromTable(row: Record<string, unknown>): StockGapEtaItem | null {
  const sku = cleanSku(pick(row, ["상품코드", "SKU", "sku"]));
  const eta = readText(pick(row, ["도착일", "계산 ETA", "ETA", "예상 입고일", "첫 입고 예정일", "date"]), "");
  const inTransitQty = readNumber(pick(row, ["수량", "입고 예정 수량", "운송중 수량", "총 도착 수량", "quantity"]));

  if (!sku || !eta) {
    return null;
  }

  return {
    sku,
    productName: readText(pick(row, ["상품명", "productName", "제품명"]), "-"),
    brand: readText(pick(row, ["브랜드", "brand"]), "-"),
    transportMode: readText(pick(row, ["운송수단", "mode"]), "-"),
    eta,
    inTransitQty,
    shipmentDate: readText(pick(row, ["출고일", "shipmentDate"]), ""),
    referenceNo: readText(pick(row, ["B/L", "BL", "B/L No", "컨테이너번호", "컨테이너 번호", "container_no", "referenceNo"]), ""),
    note: readText(pick(row, ["비고", "note", "위험도", "상태"]), "")
  };
}

export function etaItemsFromStockEtaPivotRow(row: Record<string, unknown>): StockGapEtaItem[] {
  const sku = cleanSku(pick(row, ["상품코드", "SKU", "sku"]));
  if (!sku) {
    return [];
  }

  return Object.entries(row)
    .filter(([key]) => /^\d{4}-\d{1,2}-\d{1,2}$/.test(key))
    .map(([eta, value]) => ({
      eta,
      inTransitQty: readNumber(value),
      sku,
      productName: readText(pick(row, ["상품명", "productName", "제품명"]), "-"),
      brand: readText(pick(row, ["브랜드", "brand"]), "-"),
      transportMode: "-",
      note: "상세 운송 로우 없음 - 재고 ETA 요약 기준"
    }))
    .filter((item) => item.inTransitQty > 0);
}

export function stockGapItemFromOrderReview(row: Record<string, unknown>, etaItems: StockGapEtaItem[]): StockGapItem {
  const direct = row as Partial<Record<keyof StockGapItem, unknown>>;
  const sku = cleanSku(direct.sku ?? pick(row, ["상품코드", "SKU", "sku"])) || "-";
  const productCode = readText(direct.productCode ?? sku, sku);
  const barcode = readText(direct.barcode ?? pick(row, ["바코드", "barcode", "barCode", "bar_code"]), "");
  const recent3mSalesQty = readNullableNumber(
    direct.recent3mSalesQty ?? pick(row, ["최근 3개월 판매수량", "PA+CA 판매수량", "판매수량 기준", "recentSalesQty"])
  );

  return {
    sku,
    productCode,
    barcode,
    productName: readText(direct.productName ?? pick(row, ["상품명", "productName", "제품명"]), "-"),
    brand: readText(direct.brand ?? pick(row, ["브랜드", "brand"]), "-"),
    baseDate: readText(direct.baseDate ?? pick(row, ["기준일", "검토일", "baseDate"]), "") || null,
    availableQty: readNullableNumber(direct.availableQty ?? pick(row, ["EU 현지 가용수량", "EU 현지 재고", "유럽 가용재고", "유럽 재고", "현재 가용재고", "euAvailableStock"])),
    recent3mSalesQty,
    avgDailySalesQty: readNullableNumber(direct.avgDailySalesQty ?? pick(row, ["일평균 판매수량", "일평균 판매량", "avgDailySalesQty"])),
    inTransitQty: readNullableNumber(direct.inTransitQty ?? pick(row, ["운송중", "운송중 수량", "shippingQty", "inTransitQty"])),
    openPoQty: readNullableNumber(direct.openPoQty ?? pick(row, ["미입고 수량", "미입고수량", "미입고", "inboundQty", "openPoQty"])),
    riskScore: readNullableNumber(direct.riskScore ?? pick(row, ["riskScore", "리스크 점수", "위험 점수"])) ?? undefined,
    shortageQty:
      readNullableNumber(
        direct.shortageQty ??
          pick(row, ["부족수량", "최종 부족수량", "발주필요수량", "추가 발주 필요 수량", "발주 필요 수량", "requiredOrderQty"])
      ) ?? undefined,
    stockoutDate: readText(direct.stockoutDate ?? pick(row, ["예상 소진일", "고갈 예상일", "재고 소진 예정일"]), "") || null,
    earliestEtaDate: readText(direct.earliestEtaDate ?? pick(row, ["예상 입고일", "첫 입고 예정일", "최초 ETA", "가장 빠른 ETA"]), "") || null,
    backendStatus: readText(direct.backendStatus ?? pick(row, ["상태"]), ""),
    priorityAction: readText(direct.priorityAction ?? pick(row, ["우선 액션", "최종 액션"]), ""),
    riskReason: readText(direct.riskReason ?? pick(row, ["판단 사유", "근거", "조치 요약"]), ""),
    preArrivalStockoutRisk: readFlag(direct.preArrivalStockoutRisk ?? pick(row, ["입고 전 결품 위험 여부", "입고 전 품절 여부"])),
    etaDelayFlag: readFlag(direct.etaDelayFlag ?? pick(row, ["ETA 지연 플래그", "입고지연위험"])),
    urgentReplenishmentQty: readNullableNumber(direct.urgentReplenishmentQty ?? pick(row, ["긴급 보충 필요 수량", "입고 전 예상 결품량"])) ?? undefined,
    urgentAction: readText(direct.urgentAction ?? pick(row, ["권장 긴급 액션", "운송 검토안", "운송수단 검토안"]), ""),
    etaItems
  };
}

export const emptySeasonAnalysis = {
  crossAnalysisComplete: false,
  category1Monthly: [],
  category2Monthly: [],
  category1Share: [],
  category2Share: [],
  ytdComparison: [],
  topSku: [],
  skuMonthly: [],
  mappingQuality: [],
  uncategorizedSku: [],
  countryCategoryMonthly: [],
  countryCategory2Monthly: [],
  countryTopSku: [],
  countrySkuSummary: [],
  countrySkuMonthly: [],
  dataMonths: [],
  monthCoverage: [],
  countryCustomerSummary: [],
  countryCategoryCustomerSummary: [],
  customerSalesSummary: []
};

export const emptyIngredientAnalysis = {
  keywordMap: [],
  skuTags: [],
  monthlyTrend: [],
  summary: [],
  growth3m: [],
  ytdComparison: [],
  topSku: [],
  topBrand: [],
  brandMonthlyTrend: [],
  skuMonthlyTrend: [],
  unmatchedSku: [],
  coverage: [],
  countryCoverage: []
};
