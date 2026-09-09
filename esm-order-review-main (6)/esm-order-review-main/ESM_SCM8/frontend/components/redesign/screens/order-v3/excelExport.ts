import type { Workbook } from "exceljs";
import type { OrderLogicV3ApiRow, OrderLogicV3Result } from "@/lib/api/order-logic-v3";
import type { OrderV3DecisionState, OrderV3Scenario } from "./types";
import { DEMAND_HORIZON_DAYS, DEMAND_HORIZON_PERIODS, demandOverHorizon } from "./demandHorizon.ts";
import { band, body, group, header, LOGISTICS_WIDTHS, templateSheet } from "./excelTemplate.ts";

type CellValue = string | number | boolean | Date | null;
type ExportRow = { source: OrderLogicV3ApiRow; decision?: OrderV3DecisionState };
type ExportColumn = {
  key: string;
  label: string;
  width: number;
  source: string;
  format?: string;
  read: (row: ExportRow) => CellValue;
};

export const V3_EXCEL_HEADER_ROW = 7;
const DETAIL_FORMAT = "#,##0.000000";
const AMOUNT_FORMAT = "#,##0";
const SCENARIOS = { CASH: "현금흐름 우선", SHORTAGE: "쇼티지 방어" };

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function text(value: unknown, missing = "미확인"): string {
  return typeof value === "string" && value.length > 0 ? value : missing;
}

function calculationValue(row: OrderLogicV3ApiRow, key: keyof OrderLogicV3ApiRow) {
  return row.calculable === true ? finite(row[key]) : null;
}

function reviewable(row: OrderLogicV3ApiRow) {
  return row.calculable === true && row.order_signal === "즉시 발주";
}

function calculationStatus(row: OrderLogicV3ApiRow) {
  if (row.calculable !== true) return "⚠계산차단";
  if (row.inventory_warnings?.length) return row.order_signal === "발주 제외" ? "⚠재고확인" : "⚠확인후발주";
  if (row.order_signal === "즉시 발주") return "🔴발주필요";
  if (row.order_signal === "발주 제외") return "🟢발주불필요";
  return "⚠상태확인";
}

function seasonStatus(row: OrderLogicV3ApiRow) {
  const defaulted = row.season_factor_application_reason_code === "SEASON_FACTOR_CALC_FAILED_USE_DEFAULT_1";
  if (row.seasonal_applied) return defaulted ? "기본값 1.0 적용" : "계산된 지수 적용";
  if (row.season_factor_available) return defaulted ? "기본값 1.0 연결 · 발주 계산 미완료" : "지수 연결 · 발주 계산 미완료";
  return "미적용";
}

function field(key: keyof OrderLogicV3ApiRow, label: string, width = 20): ExportColumn {
  return { key, label, width, source: key, format: "@", read: ({ source }) => text(source[key], "") };
}

function numeric(key: keyof OrderLogicV3ApiRow, label: string, calculated = true, format = DETAIL_FORMAT): ExportColumn {
  return {
    key, label, width: 22, source: key, format,
    read: ({ source }) => calculated ? calculationValue(source, key) : finite(source[key])
  };
}

const identityColumns: ExportColumn[] = [
  field("barcode", "바코드", 21), field("sku_code", "상품코드", 20),
  field("product_name", "상품명", 55), field("brand", "브랜드", 20)
];

const REFERENCE_NOTE = "참고지표: 해당 V3 분석의 판매 기준으로 집계한 일별 판매량의 최근 완료 91일(13주) 합계. 판매 원천은 숨김 계산기준에 기록. 월평균=ROUND(13주 합계÷3,0), 주평균=합계÷13. 예측엔진 산출값과는 구분하며 월평균 원값은 숨김 계산기준에 보존.";
const LOCAL_AMOUNT_NOTE = "API order_amount_local = 최종 주문수량(박스 올림)×현지 통화 단가(PL=EUR, USA=USD). 환율·표시 반올림·담당자 검토수량을 재적용하지 않음. 원값 보존·소수 2자리 표시. 단가/통화 누락은 미확인, 계산 차단은 미산출.";
const TIMING_NOTE = "첨부 수식의 서버 계산 결과. IP·ROP·Z는 선택한 V3 시나리오, 주평균·주간σ는 최근 완료 13주 실제 판매(무판매 주 0, σ=STDEV.S). 여유 주수는 소수 1자리 반올림, 날짜는 반올림 전 주수×7일. –는 분모 0 또는 필요한 계산값 없음.";
const ETA_NOTE = "PL·USA는 V2와 동일한 ETA 기준. 원천 ETA(USA Invoice 비고 ETA 포함) 우선, 없으면 출고일+Invoice 비고의 운송수단별 V2 평균 LT(실측 대상은 실측값, 비대상은 V2 기본값, σ 미가산). 지연/월요일 시작 13주/이후 도착량 합산. 미확인 ETA는 주별 합계에서 제외하고 별도 표시하며 도착량 0을 뜻하지 않음. HQ 국제운송은 해당없음.";
const INBOUND_NOTE = "V2와 동일: 조회기간 내 해당 상품의 미입고/입고 원천 행이 없거나 ①~④ 특정 항목 값이 비어 있으면 0으로 표시. 계산용 입고예정 합계도 이미 0으로 처리하므로 표시와 계산이 일치함. V3의 ① 미입고 조회기간은 PO 등록일 기준 분석 기준일 포함 최근 30일입니다. 그보다 오래된 PO의 ① 잔량은 0으로 보고, 이미 확실히 들어올 ② PNFM확정·③ 입고진행중·④ 입고완료는 기간 제한 없이 그대로 반영합니다.";
const CALCULATION_FLOW_NOTE = "계산 흐름: 목표재고(S)=Layer 1+Layer 2+Layer 3. 순수 정기발주 기준으로 발주필요수량=max(0,S−IP)를 계산하고, 필요량>0이면 아웃박스→인박스→10단위 순서로 올림해 최종 주문수량을 만듭니다. ROP=Layer 1+Layer 2는 비교용 참고값이며 발주조건에 사용하지 않습니다. Excel은 서버 계산값을 재계산하지 않고 그대로 표시합니다.";
const VALIDATION_MESSAGE_KO: Record<string, string> = {
  "Croston requires at least two non-zero sales periods": "Croston 예측을 하려면 판매가 발생한 완료 주가 최소 2개 필요합니다.",
  "all-zero sales require an approved V3 new/no-sales policy": "최근 완료 13주 판매량이 모두 0이라 승인된 V3 신규/무판매 정책이 필요합니다.",
  "trend signal is undefined because the preceding six periods sum to zero": "추세판정 비교기준인 앞 6주 판매 합계가 0이라 추세율을 계산할 수 없습니다."
};

function validationMessage(value: string | null | undefined) {
  return value ? VALIDATION_MESSAGE_KO[value] ?? value : value;
}

function inboundQuantity(key: "open_po_qty" | "pnfm_qty" | "inbound_progress_qty" | "inbound_completed_qty", label: string): ExportColumn {
  return { ...numeric(key, label, false, "#,##0"), source: `${key}. ${INBOUND_NOTE}`,
    read: ({ source }) => finite(source[key]) ?? 0 };
}

function referenceMetric(key: keyof OrderLogicV3ApiRow, label: string, format = "#,##0.0"): ExportColumn {
  return { ...numeric(key, label, false, format), source: TIMING_NOTE,
    read: ({ source }) => source[key] === undefined ? "미확인" : finite(source[key]) ?? "–" };
}

function referenceDate(key: keyof OrderLogicV3ApiRow, label: string): ExportColumn {
  return { key, label, width: 14, source: key === "next_eta" ? ETA_NOTE : TIMING_NOTE, format: "yyyy-mm-dd",
    read: ({ source }) => {
      if (key === "next_eta") {
        if (source.eta_reference_status === "NOT_APPLICABLE") return "해당없음";
        if (!["AVAILABLE", "PARTIAL"].includes(source.eta_reference_status ?? "")) return "미확인";
        if (!source[key]) return source.eta_reference_status === "PARTIAL" ? "미확인" : "–";
      }
      const value = source[key];
      if (value === undefined) return "미확인";
      if (value === null) return "–";
      // Source-calendar time: do not reinterpret it in the browser's timezone.
      const parsed = typeof value === "string" ? new Date(value.length === 10 ? `${value}T00:00:00Z` : `${value}Z`) : null;
      return parsed && Number.isFinite(parsed.valueOf()) ? parsed : "미확인";
    } };
}

function reference(key: "reference_sales_13w" | "reference_monthly_sales" | "reference_weekly_sales", label: string, format = "#,##0"): ExportColumn {
  return { ...numeric(key, label, false, format), source: `${key} — ${REFERENCE_NOTE}`,
    read: ({ source }) => source.reference_sales_status === "AVAILABLE" && source.reference_sales_days === 91 ? finite(source[key]) ?? "미확인" : "미확인" };
}

export function v3ReviewColumns(canViewAmountData: boolean, entity: OrderLogicV3Result["entity_code"] = "PL"): ExportColumn[] {
  const currency = { PL: "EUR", USA: "USD", HQ: "KRW" }[entity];
  const n = (key: keyof OrderLogicV3ApiRow, label: string, calculated = true, format = "#,##0.0"): ExportColumn => ({
    ...numeric(key, label, calculated, format),
    read: ({ source }) => (calculated ? calculationValue(source, key) : finite(source[key])) ?? (calculated && !source.calculable ? "미산출" : "미확인")
  });
  const money = (column: ExportColumn): ExportColumn => canViewAmountData ? column : { ...column, source: "금액 조회 권한 없음", read: () => null };
  const sized = (column: ExportColumn, width: number): ExportColumn => ({ ...column, width });
  const moneyColumns: ExportColumn[] = [
    money(sized(n("unit_price_krw", "단가\n(KRW)", false, "#,##0.00"), 9)),
    money(sized({ ...n("order_amount_krw", "발주필요금액\n(KRW)", true, AMOUNT_FORMAT), source: "API order_amount_krw = 최종 주문수량(박스 올림)×원화 단가. 표시 수량이나 담당자 검토수량으로 재계산하지 않음. 원값 보존·원 단위 표시." }, 13)),
    ...(entity === "HQ" ? [] : [
      money(sized({ ...n("unit_price_local", `단가\n(${currency})`, false, "#,##0.00"), read: ({ source }) => source.local_currency === currency ? finite(source.unit_price_local) ?? "미확인" : "미확인" }, 8)),
      money(sized({
        ...n("order_amount_local", `발주필요금액\n(${currency})`, true, "#,##0.00"), source: LOCAL_AMOUNT_NOTE,
        read: ({ source }) => !source.calculable ? "미산출" : source.local_currency === currency
          ? calculationValue(source, "order_amount_local") ?? "미확인" : "미확인"
      }, 11))
    ])
  ];
  const columns: ExportColumn[] = [
    sized(field("sku_code", "상품코드"), 15), sized(field("product_name", "상품명"), 30),
    sized(field("brand", "브랜드"), 10), sized(field("barcode", "바코드"), 18),

    sized(reference("reference_sales_13w", "판매량\n(13주)"), 10),
    sized(reference("reference_monthly_sales", "월평균\n판매량(/3)\n참고지표"), 11),
    sized(reference("reference_weekly_sales", "주평균\n판매량", "#,##0.0"), 10),
    sized({
      ...n("demand_per_period", `향후 ${DEMAND_HORIZON_PERIODS}주(${DEMAND_HORIZON_DAYS}일)\n예상 수요`),
      source: `API demand_per_period × ${DEMAND_HORIZON_PERIODS}기. 계절 제거 후 예측엔진이 산출한 1기(7일) 기초수요를 ${DEMAND_HORIZON_DAYS}일 기준으로 환산한 표시값이며, 달력상 다음 달 수요나 계절 재적용 후 수요로 바꾸어 해석하지 않습니다. 1기 원값은 숨김 계산기준의 기초 수요(EA/주)에 보존합니다.`,
      read: ({ source }) => {
        const perPeriod = calculationValue(source, "demand_per_period");
        return perPeriod === null ? (source.calculable ? "미확인" : "미산출") : demandOverHorizon(perPeriod);
      }
    }, 13),
    { key: "classification", label: "최종분류", width: 9, source: "API pattern", read: ({ source }) => !source.calculable ? "미분류" : ({ STABLE: "안정형", TREND_UP: "추세형", TREND_DOWN: "추세형", INTERMITTENT: "간헐형", SHORT_HISTORY: "신규/이력부족" }[source.pattern ?? ""] ?? "미분류") },
    { key: "trend", label: "추세판정", width: 9, source: "API pattern. 추세율에 새 임계값을 적용하지 않음.", read: ({ source }) => !source.calculable ? "미산출" : source.pattern === "TREND_UP" ? "상승" : source.pattern === "TREND_DOWN" ? "하락" : "–" },
    { key: "forecast_engine", label: "적용엔진", width: 12, source: "API engine", read: ({ source }) => ({ SES: "SES", HOLT_DAMPED: "HOLT+감쇠", CROSTON_SBA: "Croston+SBA", MOVING_AVERAGE: "이동평균" }[source.engine ?? ""] ?? "미분류") },
    { key: "season", label: "계절보정\n유무", width: 8, source: "API seasonal_applied. 기본값 1.0 여부와 버전은 셀 메모·숨김 계산기준 참조.", read: ({ source }) => source.seasonal_applied ? "o" : "x" },

    sized({ ...n("lead_time_days", "리드타임\n(달력일)"), source: "API lead_time_days. 선택 시나리오의 실측 리드타임이며 주말·공휴일을 포함한 달력일입니다." }, 11),
    sized({ ...n("review_days", "발주주기\n(달력일)"), source: "API review_days. 다음 발주 검토까지의 달력일입니다." }, 11),

    sized({ ...n("layer1", "리드타임 수요\n(Layer 1)"), source: "API layer1. 리드타임 동안 필요한 수요입니다." }, 13),
    sized({ ...n("layer2", "안전재고\n(Layer 2)"), source: "API layer2. 원시 안전재고에 법인별 하한·상한을 적용한 최종 안전재고입니다." }, 12),
    sized({ ...n("layer3", "발주주기 수요\n(Layer 3)"), source: "API layer3. 리드타임 이후 다음 발주 검토까지 필요한 수요입니다." }, 13),
    sized({ ...n("reorder_point", "참고 ROP\n(L1+L2·미사용)"), source: "API reorder_point = Layer 1 + Layer 2. 순수 정기발주의 발주조건에는 사용하지 않는 참고값입니다." }, 12),
    sized({ ...n("target_stock", "목표재고\n(S=L1+L2+L3)"), source: "API target_stock = Layer 1 + Layer 2 + Layer 3." }, 13),

    ...(entity === "HQ" ? [] : [sized(n("upstream_available_qty", "본사 창고\n가용재고", false, "#,##0"), 12)]),
    ...(entity === "HQ" ? [] : [sized(n("in_transit_qty", "운송중", false, "#,##0"), 10)]),
    sized(n("on_hand_qty", entity === "HQ" ? "본사 가용재고" : "현지 가용재고", false, "#,##0"), 12),
    sized({ ...n("unreceived_qty", "입고예정 합계\n(①+②+③)", false, "#,##0"), source: "API unreceived_qty. V2 재고 adapter의 미입고+PNFM확정+입고진행중 합계이며 입고완료는 제외합니다. V3는 ① 미입고만 PO 등록일 기준 최근 30일로 제한하며, ② PNFM확정·③ 입고진행중은 기간 제한 없이 합산합니다." }, 14),
    sized({ ...n("inventory_position", "확보 물량\n(IP)", true, "#,##0"), source: "API inventory_position = 현재 가용+상위거점 가용+운송중+입고예정−V3 추가 홀딩차감. V3는 V2 adapter의 순가용재고를 재사용합니다." }, 14),
    sized(inboundQuantity("open_po_qty", "① 미입고\n수량"), 9), sized(inboundQuantity("pnfm_qty", "② PNFM확정\n수량"), 10),
    sized(inboundQuantity("inbound_progress_qty", "③ 입고진행중\n수량"), 10), sized(inboundQuantity("inbound_completed_qty", "④ 입고완료\n수량"), 9),
    ...(entity === "HQ" ? [] : [sized(referenceDate("next_eta", "다음 입고예정\n(운송중 최소 ETA)"), 12)]),
    sized({ ...referenceMetric("reference_moi", "재고보유\n개월수(MOI)"), source: "ROUND((현지가용+운송중)/ROUND(13주 판매÷3,0),1). 월평균 0/누락 또는 IP 누락이면 –." }, 9),
    sized({ ...referenceMetric("reference_depletion_weeks", "고갈주수\n(현지+운송)"), source: "(현지가용+운송중)/최근 완료 13주 주평균. 분모 0/누락이면 –." }, 9),

    { key: "signal", label: "발주 판단\n(IP<S)", width: 12, source: "calculable / order_signal / reason_code. 순수 정기발주 기준으로 IP<S이면 발주 필요, IP≥S이면 발주 불필요입니다.", read: ({ source }) => calculationStatus(source) },
    sized({ ...n("raw_order_quantity", "발주필요수량\n(원시)" , true, "#,##0"), source: "API raw_order_quantity 원값 = max(0,S−IP). ROP gate는 사용하지 않습니다. 정수 표시는 반올림 서식일 뿐이며 박스 올림 전의 원시 필요량입니다." }, 14),
    sized({ ...n("final_order_quantity", "최종 주문수량\n(박스 올림)", true, "#,##0"), source: "API final_order_quantity = 원시 필요량>0일 때 아웃박스→인박스→10단위 순서로 올림. 원시 0은 0 유지. MOQ·팔레트 제약은 미적용." }, 14),
    { key: "order_unit", label: "주문단위", width: 11, source: "API order_unit_source / order_unit_quantity. OUTBOX=아웃박스, INBOX=인박스, FALLBACK_10=박스입수 미설정 10단위.", read: ({ source }) => !source.calculable ? "미산출" : source.order_unit_source === "OUTBOX" ? `아웃박스 ${source.order_unit_quantity}` : source.order_unit_source === "INBOX" ? `인박스 ${source.order_unit_quantity}` : source.order_unit_source === "FALLBACK_10" ? "10단위" : "미확인" },
    ...moneyColumns,

    sized(referenceMetric("reference_weekly_sigma", "(hidden)\n주간수요σ", DETAIL_FORMAT), 10), sized(n("z_value", "(hidden)\nZ-score", true, "General"), 8)
  ];
  return columns;
}

export const V3_DETAIL_COLUMNS: ExportColumn[] = [
  ...identityColumns,
  field("data_status", "계산 상태 코드"), field("order_signal", "발주 신호"),
  { key: "product_identity_source_codes", label: "동일 제품 원천 상품코드", width: 40, source: "product_identity_source_codes", read: ({ source }) => source.product_identity_source_codes?.join(" / ") ?? null },
  field("product_identity_reason_code", "동일 제품 연결 사유", 45),
  { key: "inbound_status_source_present", label: "미입고/입고 원천 행 존재", width: 27, source: INBOUND_NOTE,
    read: ({ source }) => source.inbound_status_source_present ?? null },
  field("inventory_validation_error", "V2 재고 검증 오류", 55),
  { key: "inventory_warnings", label: "V2 재고 경고 코드", width: 45, source: "V2 inventory adapter warnings", read: ({ source }) => source.inventory_warnings?.join(" / ") ?? "" },
  { key: "inventory_warning_messages", label: "재고 원천 확인", width: 65, source: "V2 inventory warning messages", read: ({ source }) => source.inventory_warning_messages?.join("\n") ?? "" },
  field("pattern", "상품분류 코드"), field("engine", "예측엔진", 23),
  numeric("adi", "ADI"), numeric("cv2", "CV²"), numeric("trend_signal", "추세율", true, "0.00%"),
  numeric("demand_per_period", "기초 수요(EA/주)"), numeric("forecast_rmse", "예측 RMSE(EA/주)"),
  numeric("forecast_sigma", "예측 σ(EA/주)"),
  numeric("alpha", "α"), numeric("beta", "β"), numeric("phi", "φ"),
  numeric("z_value", "Z"), field("z_policy", "Z 적용 시나리오"),
  field("transport_mode", "운송수단"),
  numeric("lead_time_periods", "리드타임 L(주)"), numeric("review_periods", "검토주기 R(주)"),
  numeric("sigma_lead_time_periods", "리드타임 σL(주)"),
  numeric("safety_stock_floor_periods", "안전재고 하한(주)"), numeric("safety_stock_cap_periods", "안전재고 상한(주)"),
  numeric("layer1", "Layer 1 수요(EA)"), numeric("layer2_raw", "Layer 2 원시값(EA)"),
  numeric("safety_stock_floor", "안전재고 하한(EA)"), numeric("safety_stock_cap", "안전재고 상한(EA)"),
  numeric("layer2", "Layer 2 적용값(EA)"), numeric("layer3", "Layer 3 수요(EA)"),
  numeric("reorder_point", "참고 ROP(EA, 미사용)"), numeric("target_stock", "목표재고 S(EA)"),
  numeric("on_hand_qty", "현지 가용재고(EA)", false), numeric("upstream_available_qty", "상위 가용재고(EA)", false),
  numeric("in_transit_qty", "운송중(EA)", false), numeric("unreceived_qty", "미입고(EA)", false),
  numeric("holding_qty", "V3 추가 홀딩차감(EA)", false), numeric("inventory_position", "재고위치 IP(EA)"),
  numeric("raw_order_quantity", "V3 원시 필요량(EA)"),
  numeric("final_order_quantity", "최종 주문수량(EA)", true, "#,##0"),
  field("order_unit_source", "주문단위 출처", 18),
  numeric("order_unit_quantity", "주문단위 수량(EA)", true, "#,##0"),
  numeric("inbox_quantity", "인박스 입수량", false, "#,##0"),
  numeric("outbox_quantity", "아웃박스 입수량", false, "#,##0"),
  { key: "season_application_status", label: "계절지수 적용 상태", width: 43, source: "seasonal_applied / season_factor_available / season_factor_application_reason_code", read: ({ source }) => seasonStatus(source) },
  field("season_factor_version", "계절지수 버전", 50),
  numeric("seasonal_f1", "계절지수 f1"), numeric("seasonal_f2", "계절지수 f2"), numeric("seasonal_f_lr", "계절지수 fLR"),
  field("function_class_1_code", "기능구분1"), field("function_class_2_code", "기능구분2"),
  { key: "season_factor_available", label: "계절지수 연결 상태", width: 24, source: "season_factor_available / seasonal_applied", read: ({ source }) => source.season_factor_available === false ? "연결 불가" : source.season_factor_available || source.seasonal_applied ? "연결 완료" : "미확인" },
  field("season_factor_scope", "계절지수 적용범위", 34),
  field("season_factor_function_class_1_code", "적용 팩터 기능구분1", 26), field("season_factor_function_class_2_code", "적용 팩터 기능구분2", 26),
  field("season_factor_application_reason_code", "계절지수 적용 사유 코드", 52),
  field("season_factor_original_reason_code", "계절지수 원래 보류 코드", 40), field("season_factor_original_message", "계절지수 원래 보류 사유", 55),
  field("season_factor_window_start", "팩터 관측 시작일", 22), field("season_factor_window_end", "팩터 관측 종료일", 22),
  ...Array.from({ length: 12 }, (_, index): ExportColumn => ({
    key: `season_month_${index + 1}`, label: `${index + 1}월 연결 계절지수`, width: 23, format: DETAIL_FORMAT,
    source: `season_factors_by_month[${index + 1}]: 연결된 월지수이며 발주 계산 적용 여부는 별도 열 참조`,
    read: ({ source }) => source.season_factor_available || source.seasonal_applied ? finite(source.season_factors_by_month?.[String(index + 1)]) : null
  })),
  field("first_sale_date", "최초 정상판매일", 22), field("analysis_sales_cutoff", "판매 마감일", 22),
  numeric("calendar_days_since_first_sale", "최초판매 경과 달력일", false, "#,##0"),
  field("lead_time_source", "리드타임 원천", 45), numeric("lead_time_sample_size", "리드타임 표본수", false, "#,##0"),
  field("lead_time_completion_from", "LT 관측 시작일", 22), field("lead_time_completion_to", "LT 관측 종료일", 22),
  ...(["original_period_sales", "adjusted_period_sales"] as const).flatMap((key) =>
    Array.from({ length: 13 }, (_, index): ExportColumn => ({
      key: `${key}_${index + 1}`, label: `${key === "original_period_sales" ? "원판매" : "계절제거"} ${index + 1}주(EA)`,
      width: 24, format: DETAIL_FORMAT, source: `${key}[${index}]: 1주=가장 오래된 완료 7일, 13주=가장 최근`,
      read: ({ source }) => finite(source[key]?.[index])
    }))
  )
];

function dateOnly(value: string): Date {
  const parsed = new Date(`${value}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== value) {
    throw new Error("V3 분석 기준일이 올바르지 않습니다. 다시 분석해 주세요.");
  }
  return parsed;
}
function plusDays(date: Date, days: number) { return new Date(date.valueOf() + days * 86400000); }
function excelColumn(index: number) {
  let value = index;
  let label = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    label = String.fromCharCode(65 + remainder) + label;
    value = Math.floor((value - 1) / 26);
  }
  return label;
}

export type V3ExcelOptions = {
  result: OrderLogicV3Result;
  scenario: OrderV3Scenario;
  skus: string[];
  decisions: Record<string, OrderV3DecisionState>;
  canViewAmountData: boolean;
  viewTitle: string;
  attentionSkus?: string[];
  attentionScope?: string;
  brandScope?: string | null;
};

export type V3ExcelProgress = { sheet: string; completed: number; total: number };

export function populateV3Excel(workbook: Workbook, options: V3ExcelOptions) {
  // Retain the synchronous document-workbook API for small-file tests/tools.
  for (const progress of generateV3Excel(workbook, options)) void progress;
}

function commitSheet(sheet: ReturnType<Workbook["addWorksheet"]>) {
  (sheet as typeof sheet & { commit?: () => void }).commit?.();
}

export function* generateV3Excel(workbook: Workbook, options: V3ExcelOptions): Generator<V3ExcelProgress> {
  const { result, scenario, skus, decisions, canViewAmountData, viewTitle, attentionSkus, attentionScope = viewTitle } = options;
  if (!Number.isInteger(result.result_schema_version) || result.result_schema_version < 18) {
    throw new Error("이전 분석 결과에는 최신 재고 오류·경고 검증이 적용되지 않았습니다. V3를 다시 분석한 뒤 엑셀을 내려받아 주세요.");
  }
  if (result.result_schema_version < 19) {
    throw new Error("이전 분석 결과에는 외화 제안금액이 연결되지 않았습니다. V3를 다시 분석한 뒤 엑셀을 내려받아 주세요.");
  }
  if (result.result_schema_version < 20) {
    throw new Error("이전 분석 결과에는 미입고 원천 행 존재 여부가 없습니다. V3를 다시 분석한 뒤 엑셀을 내려받아 주세요.");
  }
  if (result.entity_code !== "HQ" && result.result_schema_version < 21) {
    throw new Error("이전 분석 결과에는 PL·USA의 V2 동일 ETA 기준이 적용되지 않았습니다. V3를 다시 분석한 뒤 엑셀을 내려받아 주세요.");
  }
  if (result.result_schema_version < 22) {
    throw new Error("이전 분석 결과에는 선택 시나리오의 운송수단이 SKU 결과에 연결되지 않았습니다. V3를 다시 분석한 뒤 엑셀을 내려받아 주세요.");
  }
  if (result.result_schema_version < 23) {
    throw new Error("이전 분석 결과에는 순수 정기발주 Q=max(0,S−IP)가 적용되지 않았습니다. V3를 다시 분석한 뒤 엑셀을 내려받아 주세요.");
  }
  if (result.result_schema_version < 24) {
    throw new Error("이전 분석 결과에는 해설서 기준 13주 수요창과 분류 규칙이 적용되지 않았습니다. V3를 다시 분석한 뒤 엑셀을 내려받아 주세요.");
  }
  // Exact SKU + selected scenario, never positional joins, fixture values or UI zero fallbacks.
  const sourceRows = result.scenarios[scenario]?.rows;
  if (!sourceRows) throw new Error("선택한 시나리오의 V3 결과가 없습니다. 다시 분석해 주세요.");
  const sourceBySku = new Map<string, OrderLogicV3ApiRow>();
  sourceRows.forEach((source) => {
    if (sourceBySku.has(source.sku_code)) throw new Error("V3 결과에 중복 상품코드가 있어 엑셀 생성을 중단했습니다.");
    sourceBySku.set(source.sku_code, source);
  });
  if (new Set(skus).size !== skus.length) throw new Error("엑셀 대상 상품코드가 중복되었습니다.");
  const rows = skus.map((sku): ExportRow => {
    const source = sourceBySku.get(sku);
    if (!source) throw new Error("엑셀 대상 상품과 V3 원본 결과가 일치하지 않습니다. 다시 분석해 주세요.");
    return { source, decision: decisions[sku] };
  });
  const checkSkus = attentionSkus ?? rows.filter(({ source }) => source.calculable === false).map(({ source }) => source.sku_code);
  if (new Set(checkSkus).size !== checkSkus.length) throw new Error("확인필요 대상 상품코드가 중복되었습니다.");
  const blocked = checkSkus.map((sku): ExportRow => {
    const source = sourceBySku.get(sku);
    if (!source || source.calculable !== false) throw new Error("확인필요 대상 상품과 선택 시나리오의 보류·차단 결과가 일치하지 않습니다.");
    return { source, decision: decisions[sku] };
  });
  const proposalSkus = new Set(skus);
  const auditRows = [...rows, ...blocked.filter(({ source }) => !proposalSkus.has(source.sku_code))];
  const asOf = dateOnly(result.as_of);
  const monday = plusDays(asOf, -((asOf.getUTCDay() + 6) % 7));
  const context = `${result.entity_code} | ${SCENARIOS[scenario]} | ${viewTitle} | ${rows.length.toLocaleString("ko-KR")}개 상품 | 기준일 ${result.as_of}`;
  const referenceWindow = auditRows[0]?.source.reference_sales_start && auditRows[0]?.source.reference_sales_end
    ? `${auditRows[0].source.reference_sales_start}~${auditRows[0].source.reference_sales_end}` : "새 분석 후 확인";
  const ledgerSales = result.source_audit?.demand_source?.policy === "V3_STOCK_IN_OUT_SALE_AND_ONLINE_V1";
  const salesSource = ledgerSales
    ? "수불 API /esm/stock-in-out: OUT-SALE + OUT-SALE (ONLINE)의 qty_out 합계. 재고조정·이동·입고·반품 제외. 매출액 기준 상품등급은 기존 판매 API 유지."
    : "기존 분석의 판매 기준: 저장된 로직 버전 참조. 수불 판매 기준으로 소급 변경하지 않음.";
  const referenceNote = `참고 판매기간: ${referenceWindow} (91일). 월평균=13주 판매량÷3 정수 반올림, 주평균=÷13. V3 예측은 ${result.period_count}기×${result.period_days}일 기준이며 이 참고평균으로 대체하지 않습니다.`;
  const columns = v3ReviewColumns(canViewAmountData, result.entity_code);
  const columnByKey = new Map(columns.map((column, index) => [column.key, { column, index: index + 1 }]));
  const proposalColumn = (key: string) => {
    const entry = columnByKey.get(key);
    if (!entry) throw new Error(`V3 Excel 열 구성을 찾을 수 없습니다: ${key}`);
    return entry.index;
  };
  const proposalColumnDefinition = (key: string) => {
    const entry = columnByKey.get(key);
    if (!entry) throw new Error(`V3 Excel 열 구성을 찾을 수 없습니다: ${key}`);
    return entry.column;
  };
  const proposalRange = (startKey: string, endKey: string, row: number) =>
    `${excelColumn(proposalColumn(startKey))}${row}:${excelColumn(proposalColumn(endKey))}${row}`;
  const proposalEnd = excelColumn(columns.length);
  const coreResultEnd = result.entity_code === "HQ" ? "order_amount_krw" : "order_amount_local";
  const inventoryStatusEnd = "reference_depletion_weeks";
  const proposal = templateSheet(workbook, "발주제안", columns.map((column) => column.width), V3_EXCEL_HEADER_ROW, 3);
  band(proposal, `A1:${proposalEnd}1`, "발주분석 결과 · 재고현황 · 발주 제안", true);
  band(proposal, `A2:${proposalEnd}2`, `${context}\n값 전용 snapshot: 웹에서 다시 분석·다운로드해야 갱신됩니다. 발주필요수량·최종 주문수량·금액은 표시 서식과 무관하게 서버 원값을 보존합니다. 최종 주문수량은 아웃박스→인박스→10단위 올림만 적용한 값입니다. –는 계산 조건 미충족, 미확인은 원천/값 누락입니다.`);
  band(proposal, proposalRange("sku_code", coreResultEnd, 4), `${CALCULATION_FLOW_NOTE}\n${referenceNote}`);
  proposal.getRow(1).height = 26.1;
  proposal.getRow(2).height = 27.95;
  proposal.getRow(3).height = 6;
  proposal.getRow(4).height = 34;
  proposal.getRow(6).height = 18;
  // One extra line makes the approved "/3 · 참고지표" definition visible.
  proposal.getRow(7).height = 42;
  for (const [range, label, color] of [
    [proposalRange("sku_code", "barcode", 6), "SKU 식별", "FFE9ECF2"],
    [proposalRange("reference_sales_13w", "season", 6), "판매정보 · 미래예측", "FFFBF1DE"],
    [proposalRange("lead_time_days", "review_days", 6), "공급조건", "FFE9F4F8"],
    [proposalRange("layer1", "target_stock", 6), "Layer 1·2·3 · 목표재고", "FFE8F5EC"],
    [proposalRange(result.entity_code === "HQ" ? "on_hand_qty" : "upstream_available_qty", inventoryStatusEnd, 6), "재고현황 · 확보 물량", "FFEFEFEF"],
    [proposalRange("signal", coreResultEnd, 6), "발주 판단 · 필요수량", "FFFDF1DE"]
  ]) group(proposal, range, label, color);
  columns.forEach((column, index) => header(proposal.getCell(7, index + 1), column.label, column.source));
  for (const key of ["reference_weekly_sigma", "z_value"]) proposal.getColumn(proposalColumn(key)).hidden = true;
  if (!canViewAmountData) for (const key of ["unit_price_krw", "order_amount_krw", "unit_price_local", "order_amount_local"]) {
    const entry = columnByKey.get(key);
    if (entry) proposal.getColumn(entry.index).hidden = true;
  }
  const centeredProposalKeys = new Set(["signal", "classification", "trend", "forecast_engine", "season", "next_eta"]);
  const emphasizedProposalKeys = new Set(["signal", "raw_order_quantity", "final_order_quantity", "order_amount_krw", "order_amount_local", "inventory_position"]);
  for (const [index, item] of rows.entries()) {
    const rowNumber = index + 8;
    proposal.getRow(rowNumber).height = 27;
    columns.forEach((column, col) => {
      const cell = proposal.getCell(rowNumber, col + 1);
      cell.value = column.read(item);
      body(cell, column.format, col < 4 ? "left" : centeredProposalKeys.has(column.key) ? "center" : "right", emphasizedProposalKeys.has(column.key));
      if (cell.value === "미산출") cell.note = column.source;
    });
    proposal.getCell(rowNumber, proposalColumn("season")).note = `${seasonStatus(item.source)} | 버전 ${text(item.source.season_factor_version)}`;
    proposal.getCell(rowNumber, proposalColumn("signal")).note = [
      validationMessage(item.source.validation_error) || text(item.source.order_signal),
      ...(item.source.inventory_warning_messages ?? [])
    ].join("\n");
    proposal.getCell(rowNumber, proposalColumn("raw_order_quantity")).note = `서버 원시 필요량: ${calculationValue(item.source, "raw_order_quantity") ?? "미산출"}. 표시만 반올림. 최종 주문수량은 박스 올림 열 참조.`;
    if (columnByKey.has("next_eta")) proposal.getCell(rowNumber, proposalColumn("next_eta")).note = `${ETA_NOTE}\n상태: ${item.source.eta_reference_status ?? "UNAVAILABLE"}, ETA 미확인 수량: ${item.source.eta_missing_qty ?? "미확인"}`;
    proposal.getRow(rowNumber).commit();
    if ((index + 1) % 250 === 0) yield { sheet: "발주제안", completed: index + 1, total: rows.length };
  }
  if (rows.length) {
    const signalColumn = excelColumn(proposalColumn("signal"));
    proposal.addConditionalFormatting({
    ref: `${signalColumn}8:${signalColumn}${7 + rows.length}`,
    rules: [["🔴", "FFF8D7DA"], ["🟡", "FFFFF3CD"], ["🟢", "FFD4EDDA"], ["⚠", "FFFCE8D6"]].map(([symbol, color], index) => ({
      type: "containsText" as const, operator: "containsText" as const, text: symbol, priority: index + 1,
      formulae: [`NOT(ISERROR(SEARCH("${symbol}",${signalColumn}8)))`],
      style: { fill: { type: "pattern" as const, pattern: "solid" as const, fgColor: { argb: color } } }
    }))
  });
  }
  commitSheet(proposal);
  yield { sheet: "발주제안", completed: rows.length, total: rows.length };

  const isHq = result.entity_code === "HQ";
  if (!isHq) {
    const logisticsEnd = "I";
    const logistics = templateSheet(workbook, "물류전망", LOGISTICS_WIDTHS, 6);
    band(logistics, `A1:${logisticsEnd}1`, "물류전망 · 재고 현황", true);
    band(logistics, `A2:${logisticsEnd}2`, "동일 V3 실행의 내보낸 상품 재고 현황입니다. 운송중 합계는 재고 기준값이며, ETA 상세은 숨김 _운송원천 시트에서 확인할 수 있습니다. 날짜는 확정 또는 추정이며 실제 입고를 보장하지 않습니다.");
    band(logistics, `A3:${logisticsEnd}3`, `${context}\n${referenceNote}`);
    group(logistics, "A5:C5", "상품 식별", "FFE9ECF2");
    group(logistics, "D5:F5", "판매 참고지표", "FFE8F5EC");
    group(logistics, `G5:${logisticsEnd}5`, "재고 현황", "FFEFEFEF");
    [26.1, 30, 33.95, 6, 18, 39.95].forEach((height, index) => { logistics.getRow(index + 1).height = height; });
    const logisticsHeaders = [
      "상품코드", "상품명", "바코드", "판매량\n(13주)", "월평균\n판매량(/3)\n참고지표", "주평균\n판매량",
      "현재고\n(현지가용)", "운송중\n합계", "재고보유\n개월수(MOI)",
    ];
    const logisticsMoiIndex = 8;
    logisticsHeaders.forEach((label, index) => header(logistics.getCell(6, index + 1), label, index === logisticsMoiIndex ? proposalColumnDefinition("reference_moi").source : index >= 3 && index <= 5 ? REFERENCE_NOTE : undefined));
    for (const [index, item] of rows.entries()) {
      const source = item.source;
      const values: CellValue[] = [
        source.sku_code, text(source.product_name, ""), text(source.barcode, ""),
        ...["reference_sales_13w", "reference_monthly_sales", "reference_weekly_sales"].map((key) => proposalColumnDefinition(key).read(item)),
        finite(source.on_hand_qty) ?? "미확인",
        finite(source.in_transit_qty) ?? "미확인",
        referenceMetric("reference_logistics_moi", "MOI").read(item)
      ];
      logistics.getRow(index + 7).height = 27;
      values.forEach((value, col) => {
        const cell = logistics.getCell(index + 7, col + 1);
        cell.value = value;
        body(cell, col < 3 ? "@" : [5, logisticsMoiIndex].includes(col) ? "#,##0.0" : "#,##0", col < 3 ? "left" : "right");
      });
      logistics.getRow(index + 7).commit();
      if ((index + 1) % 250 === 0) yield { sheet: "물류전망", completed: index + 1, total: rows.length };
    }
    commitSheet(logistics);
    yield { sheet: "물류전망", completed: rows.length, total: rows.length };
  }

  const checkEnd = isHq ? "F" : "G";
  const checkWidths = isHq ? [22, 34, 18, 14, 14, 60] : [22, 34, 18, 14, 14, 14, 60];
  const check = templateSheet(workbook, "확인필요", checkWidths, 5, 0, false);
  band(check, `A1:${checkEnd}1`, "발주분석 V3 · 보류 / 계산 차단 SKU", true);
  band(check, `A2:${checkEnd}2`, "V3에서 발주 계산을 완료하지 못한 SKU입니다. 아래 사유를 확인한 뒤 웹에서 다시 분석하세요. 재고 마스터 미등록으로 일괄 단정하지 않습니다.");
  band(check, `A3:${checkEnd}3`, `${result.entity_code} | ${SCENARIOS[scenario]} | 기준일 ${result.as_of} | 확인필요 ${blocked.length}개 | ${attentionScope}`);
  check.getCell("A3").note = "판매수량은 최근 완료 13주 참고지표이며 계산 차단도 판매 0을 뜻하지 않습니다.";
  [26.1, 30, 24, 6, 24].forEach((height, index) => { check.getRow(index + 1).height = height; });
  const checkHeaders = ["상품코드", "상품명", "브랜드", "13주 판매수량", ...(isHq ? [] : ["운송중 수량"]), "미입고/입고예정 수량", "확인필요 사유"];
  checkHeaders.forEach((label, index) => header(check.getCell(5, index + 1), label));
  const checkNumericEndIndex = isHq ? 4 : 5;
  for (const [index, item] of blocked.entries()) {
    const values = [item.source.sku_code, text(item.source.product_name, ""), text(item.source.brand, ""), proposalColumnDefinition("reference_sales_13w").read(item),
      ...(isHq ? [] : [finite(item.source.in_transit_qty) ?? "미확인"]), finite(item.source.unreceived_qty) ?? "미확인",
      validationMessage(item.source.validation_error) || item.source.reason_code || "계산 차단 사유 미확인"];
    check.getRow(index + 6).height = 30;
    values.forEach((value, col) => {
      const cell = check.getCell(index + 6, col + 1);
      cell.value = value;
      body(cell, col >= 3 && col <= checkNumericEndIndex ? "#,##0" : "@", col >= 3 && col <= checkNumericEndIndex ? "right" : "left");
      cell.style = { ...cell.style, alignment: { ...cell.alignment, wrapText: true } };
    });
    check.getRow(index + 6).commit();
    if ((index + 1) % 250 === 0) yield { sheet: "확인필요", completed: index + 1, total: blocked.length };
  }
  if (!blocked.length) {
    band(check, `A6:${checkEnd}6`, "현재 내보내기 범위에 보류·계산 차단 상품이 없습니다.");
    check.getRow(6).height = 30;
  }
  check.autoFilter = { from: "A5", to: `${checkEnd}${Math.max(5, blocked.length + 5)}` };
  commitSheet(check);
  yield { sheet: "확인필요", completed: blocked.length, total: blocked.length };

  // Preserve diagnostics without changing the template's three visible sheets.
  const info = workbook.addWorksheet("_계산기준", { state: "hidden" });
  const metadata: Array<[string, CellValue | Date]> = [
    ["분석 기준일", asOf], ["적용 시나리오", scenario], ["이번 주 월요일", monday],
    ["법인 / 조회 범위", `${result.entity_code} / ${viewTitle}\n확인필요 ${blocked.length}개: ${attentionScope}`],
    ["실행 ID", result.job_id], ["원천 snapshot ID", result.source_snapshot_id ?? "미확인"],
    ["로직 버전", result.logic_version], ["결과 스키마 버전", result.result_schema_version],
    ["V3 예측 관측기간", `${result.period_start}~${result.period_end}: ${result.period_count}×${result.period_days}일`],
    ["판매 참고 관측기간", `${referenceWindow}\n${salesSource}`], ["월평균 참고 정의", "ROUND(13주 판매수량 ÷ 3,0); 4주 평균 아님. 원값 별도 보존"],
    ["주평균 참고 정의", "13주 판매수량 ÷ 13"],
    ["최종 주문수량", "박스 올림 적용 · PACK_ROUNDING_APPLIED (아웃박스→인박스→10단위, MOQ·팔레트 미적용)"],
    ["표시 정밀도", "제안수량·원화 금액 정수, 외화 금액 소수 2자리 표시. 계산 원값 보존. 표시 수량×단가와 원시 필요량 기준 금액이 다를 수 있음."],
    ["참고지표·계산 기준", `${TIMING_NOTE} ${ETA_NOTE}`],
    ["실행 경고", result.warnings?.join("\n") || "없음"],
    ["계산 시각(API 원문)", result.calculated_at],
    ["원천 조회 시각(API 원문)", result.source_fetched_at ?? "미확인"],
    ...(canViewAmountData ? [["금액 정의", `원화: API order_amount_krw. 최종 주문수량(박스 올림)×원화 단가. ${LOCAL_AMOUNT_NOTE} HQ 현지금액은 기존 원화 금액 사용.`] as [string, CellValue]] : [])
  ];
  metadata.forEach(values => {
    const row = info.addRow(values);
    row.height = values[0] === "참고지표·계산 기준" ? 96 : ["금액 정의", "법인 / 조회 범위", "판매 참고 관측기간"].includes(values[0]) ? 60 : 30;
    for (const col of [1, 2]) {
      body(row.getCell(col), values[col - 1] instanceof Date ? "yyyy-mm-dd" : undefined, "left");
      const cell = row.getCell(col);
      cell.style = { ...cell.style, alignment: { ...cell.alignment, wrapText: true } };
    }
  });
  const auditColumns: ExportColumn[] = [...V3_DETAIL_COLUMNS,
    reference("reference_sales_13w", "13주 참고 판매량"), reference("reference_monthly_sales", "월평균 참고(/3)", DETAIL_FORMAT),
    reference("reference_weekly_sales", "주평균 참고(/13)", DETAIL_FORMAT),
    numeric("reference_monthly_sales_raw", "월평균 /3 반올림 전", false),
    ...["reference_moi", "reference_depletion_weeks"].map(proposalColumnDefinition),
    { ...referenceMetric("reference_order_slack_weeks", "발주까지 여유\n(주, 평균)"), width: 10 },
    { ...referenceDate("reference_early_warning_at", "조기경보일\n(CV·서비스수준)"), width: 11 },
    { ...referenceMetric("reference_conservative_slack_weeks", "보수적 발주\n여유(주)"), width: 10 },
    { ...referenceDate("reference_order_at", "예상 발주일\n(평균)"), width: 11 },
    ...["reference_weekly_sigma", "z_value"].map(proposalColumnDefinition),
    field("eta_reference_status", "ETA 계산 상태"), numeric("eta_missing_qty", "ETA 미확인 수량", false),
    ...Array.from({ length: 13 }, (_, index): ExportColumn => ({
      key: `reference_week_${index + 1}`, label: `참고 주간판매 ${index + 1}주`, width: 20, format: DETAIL_FORMAT,
      source: "최근 완료 13주 실제 판매, 오래된 주부터. 무판매 주 0. STDEV.S 검산 원천.",
      read: ({ source }) => finite(source.reference_weekly_sales_history?.[index])
    })),
    field("reason_code", "보류·차단 코드"), field("validation_error", "보류·차단 사유"),
    { key: "review_decision", label: "담당자결정", width: 18, source: "V3 계산과 별개", read: ({ source, decision }) => reviewable(source) ? decision?.decision ?? "미검토" : "검토 대상 아님" },
    { key: "review_quantity", label: "담당자 검토수량", width: 18, source: "V3 원시 필요량을 덮어쓰지 않음", format: DETAIL_FORMAT,
      read: ({ source, decision }) => reviewable(source) && decision && decision.decision !== "미검토" ? finite(decision.finalQty) : null }
  ];
  auditColumns.forEach((column, index) => {
    info.getColumn(index + 1).width = column.width;
    header(info.getCell(20, index + 1), column.label, column.source);
  });
  info.getColumn(1).width = 30;
  info.getColumn(2).width = 110;
  info.getRow(20).height = 42;
  for (const [index, item] of auditRows.entries()) {
    auditColumns.forEach((column, col) => {
      const cell = info.getCell(index + 21, col + 1);
      cell.value = column.read(item);
      body(cell, column.format);
    });
    info.getRow(index + 21).commit();
    if ((index + 1) % 250 === 0) yield { sheet: "_계산기준", completed: index + 1, total: auditRows.length };
  }
  commitSheet(info);
  yield { sheet: "_계산기준", completed: auditRows.length, total: auditRows.length };
  const transport = workbook.addWorksheet("_운송원천", { state: "hidden" });
  transport.addRow(["상품코드", "ETA", "수량", "ETA 구분", "출고일", "운송수단", "적용 L/T(일)", "SKU 대소문자 구분키"]);
  [22, 14, 14, 24, 14, 14, 18, 24].forEach((width, index) => {
    transport.getColumn(index + 1).width = width;
    const cell = transport.getCell(1, index + 1);
    header(cell, String(cell.value), ETA_NOTE);
  });
  transport.getRow(1).height = 30;
  transport.getCell("J1").value = ETA_NOTE;
  for (const [index, { source }] of auditRows.entries()) {
    for (const item of source.shipping_eta_details ?? []) {
      const row = transport.addRow([source.sku_code, item.eta ? dateOnly(item.eta) : null, finite(item.qty), item.eta_status,
        item.ship_date ? dateOnly(item.ship_date) : null, item.transport_mode, finite(item.lead_time_days), `sku-${index + 1}`]);
      row.height = 24;
      for (let col = 1; col <= 8; col++) {
        body(row.getCell(col), col === 1 ? "@" : [2, 5].includes(col) ? "yyyy-mm-dd" : [3, 7].includes(col) ? "#,##0.000000" : undefined,
          [3, 7].includes(col) ? "right" : "left");
      }
      row.commit();
    }
    if ((index + 1) % 250 === 0) yield { sheet: "_운송원천", completed: index + 1, total: auditRows.length };
  }
  commitSheet(transport);
  yield { sheet: "_운송원천", completed: auditRows.length, total: auditRows.length };
}
