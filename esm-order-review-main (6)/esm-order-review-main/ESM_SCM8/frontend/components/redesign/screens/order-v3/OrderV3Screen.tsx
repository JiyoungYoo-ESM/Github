"use client";

import {
  ChevronDown,
  Download,
  GitCompareArrows,
  Info,
  Loader2,
  Play,
  Search,
  Square,
  X
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip
} from "recharts";

import { useAuthSession } from "@/components/auth/AuthSessionContext";
import {
  cancelOrderLogicV3Job,
  OrderLogicV3CancellationError,
  OrderLogicV3ConnectionError,
  runOrderLogicV3,
  type OrderLogicV3ApiRow,
  type OrderLogicV3Result
} from "@/lib/api/order-logic-v3";
import { isAbortError } from "@/lib/api/client";
import { ENTITY_BY_CODE, type EntityCode } from "@/lib/entities";
import { getActiveEntityCode } from "@/lib/entity-session";
import { useUserPermissions } from "@/lib/use-user-permissions";
import { cn } from "@/lib/utils";
import { chartColors } from "@/lib/chart-tokens";
import {
  clearOrderV3ActiveJob,
  loadOrderV3ActiveJob,
  saveOrderV3ActiveJob
} from "@/lib/order-v3-job-session";
import { BrandSearchSelect } from "../../shared/BrandSearchSelect";

import { OrderV3EvidenceDrawer } from "./OrderV3EvidenceDrawer";
import { attentionExportRows, displayOrderQuantity, exclusionReasonKey, filterReviewRows, reviewActionLabel, reviewExportRows, reviewProgress, reviewViewOf, type OrderV3ReviewView } from "./reviewList";
import { downloadOrderV3Excel } from "@/lib/api/order-v3-excel";
import type { OrderV3DecisionState, OrderV3ReviewDecision, OrderV3Row, OrderV3Scenario } from "./types";

const integerFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 });
const eokFormatter = new Intl.NumberFormat("ko-KR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1
});
const REVIEW_PAGE_SIZE = 10;
const SCENARIO_PAGE_SIZE = 10;
const SCENARIO_LABELS: Record<OrderV3Scenario, string> = {
  SHORTAGE: "쇼티지 방어 시나리오",
  CASH: "현금흐름 우선 시나리오"
};

const REVIEW_VIEW_TITLES: Record<OrderV3ReviewView, string> = {
  needed: "발주 검토 대상",
  "not-needed": "발주 불필요 상품",
  excluded: "보류·차단 상품",
  unknown: "상태 확인 필요 상품"
};

const REVIEW_EMPTY_MESSAGES: Record<OrderV3ReviewView, string> = {
  needed: "발주가 필요한 상품이 없습니다.",
  "not-needed": "발주 불필요 상품이 없습니다.",
  excluded: "보류·차단 상품이 없습니다.",
  unknown: "상태 확인이 필요한 상품이 없습니다."
};

const EXCLUSION_REASON_LABELS: Record<string, string> = {
  DEMAND_HISTORY_INSUFFICIENT: "판매이력 부족",
  HOLT_POLICY_PENDING: "추세형 계산 조건 확인",
  CROSTON_POLICY_PENDING: "간헐형 계산 조건 확인",
  V3_INPUT_OR_POLICY_INVALID: "입력 데이터·계산 조건 확인"
};

function exclusionReasonLabel(row: OrderV3Row) {
  return EXCLUSION_REASON_LABELS[row.validationCode ?? ""] || row.validationError || row.validationCode || "사유 미확인";
}

function formatInteger(value: number) {
  return integerFormatter.format(value);
}

function formatKrw(value: number) {
  return `₩${integerFormatter.format(value)}`;
}

function formatKrwInEok(value: number) {
  return `₩${eokFormatter.format(value / 100_000_000)}억`;
}

function formatSignedInteger(value: number) {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${formatInteger(Math.abs(value))}`;
}

function formatComparisonAmount(value: number | null | undefined, signed = false) {
  if (value == null || !Number.isFinite(value)) return "미확인";
  const roundedAmount = Math.round(Math.abs(value));
  const sign = roundedAmount === 0 ? "" : value < 0 ? "−" : signed ? "+" : "";
  return `${sign}${formatKrw(roundedAmount)}`;
}

function safeFileLabel(value: string) {
  return value.replace(/[\\/:*?"<>|]/g, "_").replace(/\s+/g, "_").slice(0, 80);
}

function createInitialDecisions(rows: OrderV3Row[]) {
  return Object.fromEntries(
    rows.filter((row) => reviewViewOf(row) === "needed").map((row) => [
      row.sku,
      { decision: "미검토", finalQty: row.finalOrderQty } satisfies OrderV3DecisionState
    ])
  ) as Record<string, OrderV3DecisionState>;
}

function orderUnitLabel(row: OrderV3Row) {
  if (row.orderUnitSource === "OUTBOX") return `아웃박스 ${formatInteger(row.orderUnitQty ?? 0)}입수 올림`;
  if (row.orderUnitSource === "INBOX") return `인박스 ${formatInteger(row.orderUnitQty ?? 0)}입수 올림`;
  if (row.orderUnitSource === "FALLBACK_10") return "10단위 올림";
  return "올림 미적용";
}

function patternLabel(value?: string | null): OrderV3Row["pattern"] {
  if (value === "STABLE") return "안정형";
  if (value === "TREND_UP" || value === "TREND_DOWN") return "추세형";
  if (value === "INTERMITTENT") return "간헐형";
  if (value === "SHORT_HISTORY") return "신규/이력부족";
  return "신규/이력부족";
}

function engineLabel(value?: string | null): OrderV3Row["engine"] {
  if (value === "SES") return "SES";
  if (value === "HOLT_DAMPED") return "HOLT+감쇠";
  if (value === "CROSTON_SBA") return "Croston+SBA";
  if (value === "MOVING_AVERAGE") return "이동평균";
  return "미분류";
}

function mapApiRow(
  row: OrderLogicV3ApiRow,
  cashRow?: OrderLogicV3ApiRow,
  shortageRow?: OrderLogicV3ApiRow
): OrderV3Row {
  const calculable = row.calculable !== false;
  const cv2 = Number(row.cv2 ?? 0);
  const adi = Number(row.adi ?? 0);
  const trend = Number(row.trend_signal ?? 0);
  return {
    sku: row.sku_code,
    productName: row.product_name || "상품명 미확인",
    brand: row.brand || "브랜드 미확인",
    barcode: row.barcode?.trim() || "",
    calculable,
    validationCode: row.reason_code ?? null,
    validationError: row.validation_error ?? null,
    inventoryWarnings: row.inventory_warning_messages ?? [],
    dataStatus: calculable ? "정상" : "계산차단",
    pattern: patternLabel(row.pattern),
    engine: engineLabel(row.engine),
    seasonalApplied: Boolean(row.seasonal_applied),
    seasonFactorVersion: row.season_factor_version,
    functionClass1: row.function_class_1_code,
    functionClass2: row.function_class_2_code,
    seasonFactorAvailable: row.season_factor_available,
    seasonFactorScope: row.season_factor_scope,
    seasonFactorsByMonth: row.season_factors_by_month ?? {},
    seasonFactorDefaulted: row.season_factor_application_reason_code === "SEASON_FACTOR_CALC_FAILED_USE_DEFAULT_1",
    seasonFactorOriginalReasonCode: row.season_factor_original_reason_code,
    seasonFactorOriginalMessage: row.season_factor_original_message,
    seasonalFactors: { f1: row.seasonal_f1 ?? null, f2: row.seasonal_f2 ?? null, fLR: row.seasonal_f_lr ?? null },
    averageDemand: Number(row.demand_per_period ?? 0),
    forecastRmse: Number(row.forecast_rmse ?? 0),
    crostonForecastCap:
      row.croston_forecast_cap_per_period == null
        ? null
        : Number(row.croston_forecast_cap_per_period),
    crostonForecastCapped: row.croston_forecast_was_capped ?? null,
    inventoryPosition: Number(row.inventory_position ?? 0),
    reorderPoint: Number(row.reorder_point ?? 0),
    targetStock: Number(row.target_stock ?? 0),
    suggestedQty: Number(row.raw_order_quantity ?? 0),
    finalOrderQty: Number(row.final_order_quantity ?? row.raw_order_quantity ?? 0),
    orderUnitQty: row.order_unit_quantity ?? null,
    orderUnitSource: row.order_unit_source ?? null,
    inboxQty: row.inbox_quantity ?? null,
    outboxQty: row.outbox_quantity ?? null,
    cashSuggestedQty: Number(cashRow?.raw_order_quantity ?? 0),
    shortageSuggestedQty: Number(shortageRow?.raw_order_quantity ?? 0),
    cashFinalOrderQty: Number(cashRow?.final_order_quantity ?? cashRow?.raw_order_quantity ?? 0),
    shortageFinalOrderQty: Number(shortageRow?.final_order_quantity ?? shortageRow?.raw_order_quantity ?? 0),
    cashOrderAmountKrw: cashRow?.order_amount_krw ?? null,
    shortageOrderAmountKrw: shortageRow?.order_amount_krw ?? null,
    orderAmountKrw: Number(row.order_amount_krw ?? 0),
    signal: calculable
      ? row.order_signal === "즉시 발주"
        ? "즉시 발주"
        : row.order_signal === "발주 제외"
          ? "발주 제외"
          : "확인 후 발주"
      : "계산 차단",
    adiLabel: adi > 1.32 ? "높음" : adi > 1 ? "보통" : "낮음",
    cv2Label: cv2 > 0.49 ? "높음" : cv2 > 0.25 ? "보통" : "낮음",
    trendLabel: Math.abs(trend) > 0.2 ? "있음" : "없음",
    firstSaleDate: row.first_sale_date ?? null,
    analysisSalesCutoff: row.analysis_sales_cutoff ?? null,
    calendarDaysSinceFirstSale:
      row.calendar_days_since_first_sale == null
        ? null
        : Number(row.calendar_days_since_first_sale),
    isNewSku: row.is_new_sku ?? null,
    leadTimeDays: row.lead_time_days == null ? null : Number(row.lead_time_days),
    reviewDays: row.review_days == null ? null : Number(row.review_days),
    leadTimeSigmaDays:
      row.sigma_lead_time_days == null ? null : Number(row.sigma_lead_time_days),
    salesHistory: (row.original_period_sales ?? []).slice(0, 13),
    adjustedForecast: (row.adjusted_period_sales ?? row.adjusted_forecast ?? []).slice(0, 13),
    targetLayers: {
      leadTimeDemand: Number(row.layer1 ?? 0),
      safetyStockRaw: Number(row.layer2_raw ?? row.layer2 ?? 0),
      safetyStock: Number(row.layer2 ?? 0),
      safetyStockFloor: Number(row.safety_stock_floor ?? 0),
      safetyStockCap: Number(row.safety_stock_cap ?? 0),
      reviewDemand: Number(row.layer3 ?? 0)
    },
    inventoryParts: {
      localAvailable: Number(row.on_hand_qty ?? 0),
      incoming: Number(row.unreceived_qty ?? 0),
      hqAvailable: Number(row.upstream_available_qty ?? 0),
      inTransit: Number(row.in_transit_qty ?? 0),
      holding: Number(row.holding_qty ?? 0)
    },
    coefficients: {
      alpha: row.alpha == null ? null : Number(row.alpha),
      beta: row.beta == null ? null : Number(row.beta),
      phi: row.phi == null ? null : Number(row.phi)
    }
  };
}

function mapScenarioRows(payload: OrderLogicV3Result, scenario: OrderV3Scenario): OrderV3Row[] {
  const shortageRows = payload.scenarios.SHORTAGE?.rows ?? payload.rows;
  const cashRows = payload.scenarios.CASH?.rows ?? [];
  const primaryRows = scenario === "SHORTAGE" ? shortageRows : cashRows;
  const cashBySku = new Map(cashRows.map((row) => [row.sku_code, row]));
  const shortageBySku = new Map(shortageRows.map((row) => [row.sku_code, row]));
  return primaryRows.map((row) => mapApiRow(row, cashBySku.get(row.sku_code), shortageBySku.get(row.sku_code)));
}

function riskLabel(row: OrderV3Row) {
  if (row.calculable === false) return row.dataStatus === "발주보류" ? "발주 보류" : "계산 차단";
  if (row.signal === "발주 제외") return "발주 불필요";
  if (row.signal === "즉시 발주") return "발주 필요";
  return "상태 확인 필요";
}

function trendMeta(row: OrderV3Row) {
  const history = row.salesHistory;
  const first = history[0] ?? 0;
  const last = history[history.length - 1] ?? 0;
  if (row.signal === "발주 제외") return { label: "▼ 감소", color: "text-muted", stroke: chartColors.slateMuted };
  if (row.pattern === "추세형" && last < first) return { label: "▼ 감소", color: "text-muted", stroke: chartColors.slateLight };
  if (row.pattern === "추세형" || row.signal === "즉시 발주") return { label: "▲ 성장", color: "text-blue-700", stroke: chartColors.blue };
  return { label: "─ 안정", color: "text-muted", stroke: chartColors.slateMuted };
}

function TrendSparkline({ row }: { row: OrderV3Row }) {
  const meta = trendMeta(row);
  const values = row.salesHistory.length ? row.salesHistory : row.adjustedForecast;
  const chartData = values.map((value, index) => ({ index, value }));
  return (
    <div className="flex min-w-[118px] items-center gap-2" aria-label={`${row.sku} 13기간 추세 ${meta.label}`}>
      <div className="h-9 w-[68px] shrink-0">
        {chartData.length > 1 ? (
          <ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <AreaChart data={chartData} margin={{ top: 4, right: 0, bottom: 3, left: 0 }}>
              <Area type="monotone" dataKey="value" stroke={meta.stroke} strokeWidth={1.7} fill={meta.stroke} fillOpacity={0.1} dot={false} isAnimationActive={false} />
              <ChartTooltip cursor={false} contentStyle={{ borderRadius: 7, borderColor: chartColors.line, fontSize: 10 }} formatter={(value) => [formatInteger(Number(value ?? 0)), "판매"]} labelFormatter={() => ""} />
            </AreaChart>
          </ResponsiveContainer>
        ) : <span className="block pt-3 text-[10px] text-muted2">추세 없음</span>}
      </div>
      <span className={cn("whitespace-nowrap text-[10px] font-black", meta.color)}>{meta.label}</span>
    </div>
  );
}

function ExclusionStatusBadge({ row }: { row: OrderV3Row }) {
  return <span className="inline-flex shrink-0 items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-[9px] font-black text-amber-700">{riskLabel(row)}</span>;
}

function PriorityBadge({ row }: { row: OrderV3Row }) {
  if (row.calculable === false) {
    return <span className="inline-flex min-w-[52px] items-center justify-center rounded-full border border-amber-200 bg-amber-50 px-2 py-1 text-[9px] font-black text-amber-800">{row.dataStatus === "발주보류" ? "발주 보류" : "계산 차단"}</span>;
  }
  const priority = row.signal === "확인 후 발주";
  return (
    <span
      className={cn(
        "inline-flex min-w-[52px] items-center justify-center rounded-full border px-2 py-1 text-[9px] font-black",
        priority
          ? "border-brand/25 bg-brand-50 text-brand"
          : "border-border bg-surface-soft text-muted"
      )}
    >
      {priority ? "우선 검토" : "일반"}
    </span>
  );
}

function DecisionBadge({ decision }: { decision: OrderV3DecisionState }) {
  const styles =
    decision.decision === "권고 유지"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : decision.decision === "수량 수정"
        ? "border-blue-200 bg-blue-50 text-blue-700"
        : decision.decision === "발주 보류"
          ? "border-amber-200 bg-amber-50 text-amber-800"
          : "border-border bg-white text-muted";
  return (
    <span className={cn("inline-flex rounded-[6px] border px-2 py-1 text-[9.5px] font-black", styles)}>
      {decision.decision === "미검토" ? "검토하기" : decision.decision}
    </span>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="relative min-w-[136px] flex-1 sm:flex-none">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 w-full appearance-none rounded-[8px] border border-border bg-white pl-3 pr-8 text-[10.5px] font-black text-ink outline-none transition hover:border-muted2 focus:border-brand focus:ring-2 focus:ring-brand/15"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
    </label>
  );
}

function ExecutionStatusBar({
  entityCode,
  result,
  lastCalculatedAt,
  running,
  stopping,
  stopped,
  stopFailed,
  exporting,
  exportLabel,
  exportDescription,
  canExport,
  onRun,
  onStop,
  onExport
}: {
  entityCode: EntityCode;
  result: OrderLogicV3Result | null;
  lastCalculatedAt: string;
  running: boolean;
  stopping: boolean;
  stopped: boolean;
  stopFailed: boolean;
  exporting: boolean;
  exportLabel: string;
  exportDescription: string;
  canExport: boolean;
  onRun: () => void;
  onStop: () => void;
  onExport: () => void;
}) {
  const executionLabel = stopping ? "중단 중" : stopFailed ? "중단 확인 실패" : running ? "계산 중" : stopped ? "분석 중단" : result?.status === "blocked" ? "계산 차단" : result?.status === "success" ? "계산 완료" : "실행 전";
  const sourceDate = result?.source_fetched_at ? new Date(result.source_fetched_at) : null;
  const sourceTimeLabel = sourceDate && !Number.isNaN(sourceDate.getTime())
    ? sourceDate.toLocaleString("ko-KR", {
        timeZone: "Asia/Seoul",
        year: "numeric",
        month: "numeric",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit"
      })
    : "미확인";
  return (
    <header className="relative flex flex-col gap-3 border-b border-border bg-white px-4 py-3 lg:flex-row lg:items-center lg:justify-between lg:px-6">
      <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-[128px] shrink-0">
          <p className="text-[10px] font-black uppercase tracking-[.05em] text-brand">발주 · QUANTITATIVE</p>
          <h1 className="mt-[6px] text-[19px] font-black leading-none tracking-normal text-ink">발주분석 V3</h1>
        </div>
        <span aria-label="분석 대상 법인" className="text-[10px] font-bold text-muted">
          분석 대상 <strong className="text-ink">{ENTITY_BY_CODE[entityCode].legalName}</strong>
        </span>
        <span className={cn("rounded-full border px-2.5 py-1 text-[9px] font-black", stopped || stopFailed || result?.status === "blocked" ? "border-amber-200 bg-amber-50 text-amber-700" : !running && result?.status === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-border bg-surface-soft text-muted")}>{executionLabel}</span>
        <span
          className="cursor-help text-[10px] font-bold text-muted"
          title={`데이터 기준 시각: ${sourceTimeLabel} (한국 시간)`}
        >
          최근 계산 <strong className="text-ink">{lastCalculatedAt}</strong>
        </span>
      </div>
      <div className="flex shrink-0 gap-2">
        <button
          type="button"
          onClick={onRun}
          disabled={running || exporting}
          className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-[8px] border border-border bg-white px-4 text-[10.5px] font-black text-ink transition hover:bg-surface-soft disabled:opacity-60 lg:flex-none"
        >
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {running ? "분석 중…" : result ? "새로 분석" : "분석 실행"}
        </button>
        {running ? <button
          type="button"
          onClick={onStop}
          disabled={stopping}
          title="진행 중인 분석을 중단합니다. 이미 시작된 원천 조회는 서버에서 마무리될 수 있습니다."
          className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-[8px] border border-brand bg-white px-4 text-[10.5px] font-black text-brand transition hover:bg-brand-50 disabled:opacity-60 lg:flex-none"
        >
          {stopping ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-3.5 w-3.5" />}
          {stopping ? "중단 중" : "분석 중단"}
        </button> : null}
        <button
          type="button"
          onClick={onExport}
          disabled={exporting || running || !canExport}
          title={exportDescription}
          className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-[8px] bg-brand px-4 text-[10.5px] font-black text-white transition hover:bg-brand/90 disabled:opacity-60 lg:flex-none"
        >
          {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          {exportLabel}
        </button>
      </div>
    </header>
  );
}

function ReviewSummary({
  rows,
  reviewedCount,
  reviewTotalCount,
  canViewAmountData,
  exclusionsOpen,
  onToggleExclusions
}: {
  rows: OrderV3Row[];
  reviewedCount: number;
  reviewTotalCount: number;
  canViewAmountData: boolean;
  exclusionsOpen: boolean;
  onToggleExclusions: () => void;
}) {
  const [reviewHelpOpen, setReviewHelpOpen] = useState(false);
  const hasResult = rows.length > 0;
  const calculableRows = rows.filter((row) => row.calculable !== false);
  const blockedRows = rows.filter((row) => row.calculable === false);
  const orderRequiredRows = calculableRows.filter((row) => row.suggestedQty > 0);
  const totalQuantity = calculableRows.reduce((sum, row) => sum + row.finalOrderQty, 0);
  const totalOrderAmount = orderRequiredRows.reduce((sum, row) => sum + row.orderAmountKrw, 0);
  const items = [
    ["발주 필요 SKU", `${formatInteger(reviewTotalCount)}건`],
    ["총 발주수량", hasResult ? `${formatInteger(totalQuantity)} EA` : "—"],
    ...(canViewAmountData ? [["총 발주금액", hasResult ? formatKrwInEok(totalOrderAmount) : "—"]] : []),
    ["발주 보류·계산 차단", `${formatInteger(blockedRows.length)}건`],
    ["검토 완료", `${formatInteger(reviewedCount)} / ${formatInteger(reviewTotalCount)}건`]
  ];
  return (
    <section aria-label="발주 요약" className={cn("grid rounded-[12px] border border-border bg-white shadow-card sm:grid-cols-2", canViewAmountData ? "xl:grid-cols-5" : "xl:grid-cols-4")}>
      {items.map(([label, value], index) => (
        <div key={label} className={cn(
          "min-w-0 border-border xl:border-t-0",
          index > 0 && "border-t xl:border-l",
          index === 1 && "sm:border-t-0",
          index % 2 === 1 && "sm:border-l",
          canViewAmountData && index === 4 && "sm:col-span-2 xl:col-span-1"
        )}>
          {label === "발주 보류·계산 차단" ? (
            <button
              type="button"
              onClick={onToggleExclusions}
              disabled={!blockedRows.length && !exclusionsOpen}
              aria-expanded={exclusionsOpen}
              aria-controls="order-v3-exclusion-reasons"
              title={exclusionsOpen ? "보류·차단 필터 닫기" : "보류·차단 상품만 보기 (검색·필터 초기화)"}
              className={cn("h-full w-full px-4 py-3 text-left transition hover:bg-amber-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-amber-500 disabled:cursor-default disabled:hover:bg-transparent", exclusionsOpen && "bg-amber-50")}
            >
              <span className="flex min-h-4 items-center text-[9.5px] font-black text-muted">{label}</span>
              <strong className={cn("mt-1.5 block whitespace-nowrap text-[19px] font-black tracking-tight", blockedRows.length ? "text-amber-700" : "text-ink")}>{value}</strong>
            </button>
          ) : (
            <div className="px-4 py-3">
              <div className="flex min-h-4 items-center gap-1.5 text-[9.5px] font-black text-muted">
                <span>{label}</span>
                {label === "검토 완료" ? (
                  <span className="relative" onMouseEnter={() => setReviewHelpOpen(true)} onMouseLeave={() => setReviewHelpOpen(false)}>
                    <button type="button" aria-label="검토 완료 집계 기준" aria-describedby={reviewHelpOpen ? "order-v3-review-basis" : undefined} onFocus={() => setReviewHelpOpen(true)} onBlur={() => setReviewHelpOpen(false)} onClick={() => setReviewHelpOpen(true)} onKeyDown={(event) => { if (event.key === "Escape") setReviewHelpOpen(false); }} className="flex h-4 w-4 items-center justify-center rounded text-muted2 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40">
                      <Info aria-hidden="true" className="h-3 w-3" />
                    </button>
                    {reviewHelpOpen ? <span id="order-v3-review-basis" role="tooltip" className="absolute left-0 top-full z-20 w-56 pt-2 xl:left-auto xl:right-0"><span className="block rounded-[8px] bg-ink px-3 py-2 text-[10px] font-semibold leading-5 text-white shadow-panel">현재 시나리오에서 발주가 필요한 상품 중 검토를 마친 건수입니다. 수량을 수정하거나 담당자가 발주를 보류한 상품도 검토 완료에 포함합니다.</span></span> : null}
                  </span>
                ) : null}
              </div>
              <strong className="mt-1.5 block whitespace-nowrap text-[19px] font-black tracking-tight text-ink">{value}</strong>
            </div>
          )}
        </div>
      ))}
    </section>
  );
}

function ProposalTable({
  rows,
  decisions,
  selectedSku,
  selectedSkus,
  canViewAmountData,
  onToggle,
  onToggleAll,
  onOpen
}: {
  rows: OrderV3Row[];
  decisions: Record<string, OrderV3DecisionState>;
  selectedSku: string | null;
  selectedSkus: Set<string>;
  canViewAmountData: boolean;
  onToggle: (sku: string) => void;
  onToggleAll: () => void;
  onOpen: (sku: string) => void;
}) {
  const selectableRows = rows.filter((row) => row.calculable !== false);
  const allSelected = selectableRows.length > 0 && selectableRows.every((row) => selectedSkus.has(row.sku));
  if (!rows.length) {
    return <div className="grid min-h-[240px] place-items-center border-t border-border px-6 text-center"><div><Search className="mx-auto h-6 w-6 text-muted2" /><p className="mt-3 text-[13px] font-black text-ink">조건에 맞는 SKU가 없습니다.</p><p className="mt-1 text-[10.5px] font-semibold text-muted">필터나 검색어를 바꿔 주세요.</p></div></div>;
  }
  return (
    <>
      <div className="hidden overflow-x-auto border-t border-border md:block">
        <table className="w-full min-w-[760px] table-fixed border-collapse text-left">
          <thead className="bg-surface-soft text-[9.5px] font-black text-muted">
            <tr>
              <th className="w-[44px] px-3 py-3 text-center"><input aria-label="현재 페이지 전체 선택" type="checkbox" checked={allSelected} onChange={onToggleAll} disabled={!selectableRows.length} className="h-3.5 w-3.5 accent-brand disabled:opacity-35" /></th>
              <th className="w-[86px] px-2 py-3">우선순위</th>
              <th className="px-3 py-3">상품</th>
              <th className="w-[112px] px-3 py-3 text-right">제안수량</th>
              {canViewAmountData ? <th className="w-[132px] px-3 py-3 text-right">제안금액</th> : null}
              <th className="w-[116px] px-3 py-3 text-center">담당자 결정</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rowline">
            {rows.map((row) => {
              const decision = decisions[row.sku] ?? { decision: "미검토", finalQty: row.finalOrderQty };
              return (
                <tr key={row.sku} onClick={() => onOpen(row.sku)} className={cn("group cursor-pointer text-[10.5px] font-bold text-ink transition hover:bg-brand-50/60", selectedSku === row.sku && "bg-brand-50")}>
                  <td className="px-3 py-3 text-center" onClick={(event) => event.stopPropagation()}><input aria-label={`${row.sku} Excel 선택`} type="checkbox" disabled={row.calculable === false} checked={selectedSkus.has(row.sku)} onChange={() => onToggle(row.sku)} className="h-3.5 w-3.5 accent-brand disabled:opacity-35" /></td>
                  <td className="px-2 py-3"><PriorityBadge row={row} /></td>
                  <td className="min-w-0 px-3 py-3"><div className="flex min-w-0 items-center gap-3"><span className={cn("h-8 w-1 shrink-0 rounded-full", row.signal === "확인 후 발주" ? "bg-brand" : "bg-slate-200")} /><div className="min-w-0"><strong className="block text-[11px] font-black text-ink">{row.sku}</strong><span className="mt-0.5 block truncate text-[10px] text-muted" title={row.productName}>{row.productName} · {row.brand}</span></div></div></td>
                  <td className="px-3 py-3 text-right"><strong className="text-[12px] font-black">{row.calculable === false ? "-" : formatInteger(decision.finalQty)}</strong>{row.calculable === false ? null : <span className="ml-1 text-[9px] text-muted">EA</span>}{row.calculable === false ? null : <span className="mt-0.5 block whitespace-nowrap text-[9px] font-bold text-muted">원시 {formatInteger(row.suggestedQty)} · {orderUnitLabel(row)}</span>}</td>
                  {canViewAmountData ? <td className="px-3 py-3 text-right font-black">{formatKrw(row.orderAmountKrw)}</td> : null}
                  <td className="px-3 py-3 text-center"><DecisionBadge decision={decision} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="divide-y divide-rowline border-t border-border md:hidden">
        {rows.map((row) => {
          const decision = decisions[row.sku] ?? { decision: "미검토", finalQty: row.finalOrderQty };
          return (
            <button key={row.sku} type="button" onClick={() => onOpen(row.sku)} className="block w-full px-4 py-4 text-left transition hover:bg-brand-50/60">
              <div className="flex items-start gap-3">
                <input aria-label={`${row.sku} Excel 선택`} type="checkbox" disabled={row.calculable === false} checked={selectedSkus.has(row.sku)} onClick={(event) => event.stopPropagation()} onChange={() => onToggle(row.sku)} className="mt-1 h-4 w-4 shrink-0 accent-brand disabled:opacity-35" />
                <div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><strong className="text-[11px] font-black text-ink">{row.sku}</strong><PriorityBadge row={row} /></div><p className="mt-1 truncate text-[10px] font-bold text-muted">{row.productName}</p><div className="mt-3 flex items-end justify-between gap-3"><div><span className="text-[9px] font-bold text-muted">제안수량</span><strong className="ml-2 text-[14px] font-black text-ink">{row.calculable === false ? "-" : `${formatInteger(decision.finalQty)} EA`}</strong>{row.calculable === false ? null : <span className="mt-0.5 block text-[9px] font-bold text-muted">원시 {formatInteger(row.suggestedQty)} · {orderUnitLabel(row)}</span>}{canViewAmountData ? <span className="mt-1 block text-[10px] font-black text-muted">{formatKrw(row.orderAmountKrw)}</span> : null}</div><DecisionBadge decision={decision} /></div></div>
              </div>
            </button>
          );
        })}
      </div>
    </>
  );
}

function BulkActionBar({ selectedCount, onHold, onKeep }: { selectedCount: number; onHold: () => void; onKeep: () => void }) {
  if (!selectedCount) return null;
  return (
    <div className="flex flex-col gap-2 border-t border-brand/20 bg-blue-50/75 px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between">
      <span className="text-[10px] font-black text-blue-800">{formatInteger(selectedCount)}건 선택됨 · 선택 항목 일괄 처리</span>
      <div className="flex gap-2">
        <button type="button" onClick={onHold} className="h-8 rounded-[7px] border border-blue-300 bg-white px-3 text-[10px] font-black text-blue-800 transition hover:bg-blue-100">일괄 보류</button>
        <button type="button" onClick={onKeep} className="h-8 rounded-[7px] bg-blue-700 px-3 text-[10px] font-black text-white transition hover:bg-blue-800">일괄 권고유지</button>
      </div>
    </div>
  );
}

function TriageProposalTable({
  rows,
  hasResult,
  showExclusionReasons,
  emptyMessage,
  emptyDescription,
  decisions,
  selectedSku,
  selectedSkus,
  canViewAmountData,
  onToggle,
  onToggleAll,
  onOpen
}: {
  rows: OrderV3Row[];
  hasResult: boolean;
  showExclusionReasons: boolean;
  emptyMessage: string;
  emptyDescription: string;
  decisions: Record<string, OrderV3DecisionState>;
  selectedSku: string | null;
  selectedSkus: Set<string>;
  canViewAmountData: boolean;
  onToggle: (sku: string) => void;
  onToggleAll: () => void;
  onOpen: (sku: string) => void;
}) {
  const selectableRows = rows;
  const isReviewList = rows.some((row) => ["needed", "not-needed"].includes(reviewViewOf(row)));
  const allSelected = selectableRows.length > 0 && selectableRows.every((row) => selectedSkus.has(row.sku));
  if (!rows.length) {
    return <div className="grid min-h-[250px] place-items-center border-t border-border px-6 text-center"><div><Search className="mx-auto h-6 w-6 text-muted2" /><p className="mt-3 text-[13px] font-black text-ink">{hasResult ? emptyMessage : "분석을 실행하면 발주 검토 목록이 표시됩니다."}</p><p className="mt-1 text-[10.5px] font-semibold text-muted">{hasResult ? emptyDescription : "상단의 ‘분석 실행’ 버튼을 눌러 주세요."}</p></div></div>;
  }
  return (
    <>
      <div className="hidden overflow-x-auto border-t border-border md:block">
        <table className="w-full min-w-[900px] table-fixed border-collapse text-left">
          <thead className="bg-surface-soft text-[9.5px] font-black text-muted">
            <tr>
              <th className="w-[48px] px-3 py-3 text-center"><input aria-label="현재 페이지 전체 선택" type="checkbox" checked={allSelected} onChange={onToggleAll} disabled={!selectableRows.length} className="h-3.5 w-3.5 accent-brand disabled:opacity-35" /></th>
              <th className="w-[144px] px-3 py-3">바코드</th>
              <th className="px-3 py-3">상품</th>
              <th className={cn("px-3 py-3", showExclusionReasons ? "w-[220px]" : "w-[160px]")}>{showExclusionReasons ? "보류·차단 사유" : "추세 (91일 / 13주)"}</th>
              <th className="w-[148px] px-3 py-3 text-right">제안수량 · 금액</th>
              <th className="w-[100px] px-3 py-3 text-center">{isReviewList ? "검토" : showExclusionReasons ? "사유" : "상세"}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rowline">
            {rows.map((row) => {
              const decision = decisions[row.sku] ?? { decision: "미검토", finalQty: row.finalOrderQty };
              const canReview = reviewViewOf(row) === "needed";
              const displayedQuantity = displayOrderQuantity(row, decision);
              return <tr key={row.sku} onClick={() => onOpen(row.sku)} className={cn("group cursor-pointer text-[10.5px] font-bold text-ink transition hover:bg-brand-50/60", selectedSku === row.sku && "bg-brand-50")}>
                <td className="px-3 py-3 text-center" onClick={(event) => event.stopPropagation()}><input aria-label={`${row.sku} Excel 선택`} type="checkbox" checked={selectedSkus.has(row.sku)} onChange={() => onToggle(row.sku)} className="h-3.5 w-3.5 accent-brand disabled:opacity-35" /></td>
                <td className="select-text whitespace-nowrap px-3 py-3 font-mono font-semibold tabular-nums text-muted">{row.barcode || "미확인"}</td>
                <td className="min-w-0 px-3 py-3"><div className="flex flex-wrap items-center gap-2"><strong className="text-[11px] font-black text-ink">{row.sku}</strong>{showExclusionReasons ? <ExclusionStatusBadge row={row} /> : null}</div><span className="mt-0.5 block truncate text-[10px] text-muted" title={row.productName}>{row.productName} · {row.brand}</span></td>
                <td className="px-3 py-3">{showExclusionReasons ? <p className="break-words text-[10px] leading-5 text-amber-800" title={row.validationError ?? undefined}>{exclusionReasonLabel(row)}</p> : <TrendSparkline row={row} />}</td>
                <td className="px-3 py-3 text-right">
                  <div className="whitespace-nowrap">
                    <strong className="text-[12px] font-black tabular-nums">{row.calculable === false ? "-" : formatInteger(displayedQuantity)}</strong>
                    {row.calculable === false ? null : <span className="ml-1 text-[9px] text-muted">EA</span>}
                  </div>
                  {canViewAmountData && row.calculable !== false ? <span className="block text-[9px] tabular-nums text-muted">{formatKrw(row.orderAmountKrw)}</span> : null}
                </td>
                <td className="px-3 py-3 text-center"><button type="button" onClick={(event) => { event.stopPropagation(); onOpen(row.sku); }} className={cn("rounded-[7px] border px-2.5 py-1.5 text-[9.5px] font-black transition", canReview && decision.decision === "미검토" ? "border-brand/40 bg-white text-brand hover:bg-brand-50" : "border-border bg-white text-muted hover:bg-surface-soft")}>{reviewActionLabel(row, decision)}</button></td>
              </tr>;
            })}
          </tbody>
        </table>
      </div>
      <div className="divide-y divide-rowline border-t border-border md:hidden">
        {rows.map((row) => {
          const decision = decisions[row.sku] ?? { decision: "미검토", finalQty: row.finalOrderQty };
          return <button key={row.sku} type="button" onClick={() => onOpen(row.sku)} className="block w-full px-4 py-4 text-left transition hover:bg-brand-50/60"><div className="flex items-start gap-3"><input aria-label={`${row.sku} Excel 선택`} type="checkbox" checked={selectedSkus.has(row.sku)} onClick={(event) => event.stopPropagation()} onChange={() => onToggle(row.sku)} className="mt-1 h-4 w-4 shrink-0 accent-brand disabled:opacity-35" /><div className="min-w-0 flex-1"><p className="mb-1 break-all font-mono text-[10px] font-semibold tabular-nums text-muted">바코드 {row.barcode || "미확인"}</p><div className="flex items-center justify-between gap-2"><strong className="text-[11px] font-black text-ink">{row.sku}</strong>{showExclusionReasons ? <ExclusionStatusBadge row={row} /> : null}</div><p className="mt-1 truncate text-[10px] font-bold text-muted">{row.productName} · {row.brand}</p><div className="mt-3 flex items-center justify-between gap-3">{showExclusionReasons ? <p className="min-w-0 flex-1 break-words text-[10px] leading-5 text-amber-800">{exclusionReasonLabel(row)}</p> : <TrendSparkline row={row} />}<div className="shrink-0 text-right"><span className="block text-[9px] font-bold text-muted">제안수량</span><strong className="text-[13px] font-black text-ink">{row.calculable === false ? "-" : `${formatInteger(displayOrderQuantity(row, decision))} EA`}</strong>{canViewAmountData && row.calculable !== false ? <span className="block text-[9.5px] font-black text-muted">{formatKrw(row.orderAmountKrw)}</span> : null}</div></div><div className="mt-3 flex justify-end"><span className="text-[10px] font-black text-muted">{reviewActionLabel(row, decision)}</span></div></div></div></button>;
        })}
      </div>
    </>
  );
}

function ScenarioComparison({ open, rows, canViewAmountData, onClose }: {
  open: boolean;
  rows: OrderV3Row[];
  canViewAmountData: boolean;
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  const changedRows = useMemo(
    () => rows
      .filter((row) => row.calculable !== false && row.shortageSuggestedQty !== row.cashSuggestedQty)
      .sort((left, right) => Math.abs(right.shortageSuggestedQty - right.cashSuggestedQty) - Math.abs(left.shortageSuggestedQty - left.cashSuggestedQty)),
    [rows]
  );
  const totalPages = Math.max(1, Math.ceil(changedRows.length / SCENARIO_PAGE_SIZE));
  const activePage = Math.min(page, totalPages);
  const pageRows = changedRows.slice((activePage - 1) * SCENARIO_PAGE_SIZE, activePage * SCENARIO_PAGE_SIZE);
  const comparisonTitle = canViewAmountData ? "발주수량·금액 비교" : "발주수량 비교";

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/35 p-4" role="presentation">
      <section role="dialog" aria-modal="true" aria-labelledby="scenario-comparison-title" className="flex max-h-[calc(100vh-2rem)] w-full max-w-[1120px] flex-col overflow-hidden rounded-[14px] border border-border bg-white shadow-panel">
        <header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="flex items-start gap-3"><div className="grid h-9 w-9 shrink-0 place-items-center rounded-[9px] bg-surface-soft"><GitCompareArrows className="h-4 w-4 text-brand" /></div><div><h2 id="scenario-comparison-title" className="text-[16px] font-black text-ink">{comparisonTitle}</h2><p className="mt-1 text-[10.5px] font-semibold text-muted">두 시나리오에서 수량이 다른 SKU만 표시합니다.</p>{canViewAmountData ? <p className="mt-1 text-[10px] font-semibold text-muted">수량 아래는 발주금액(원)입니다. 차이는 쇼티지 방어 − 현금흐름 우선 기준입니다.</p> : null}</div></div>
          <button type="button" onClick={onClose} aria-label={`${comparisonTitle} 닫기`} className="grid h-8 w-8 shrink-0 place-items-center rounded-[7px] text-muted hover:bg-surface-soft hover:text-ink"><X className="h-4 w-4" /></button>
        </header>
        {changedRows.length ? <>
          <div className="min-h-0 overflow-auto px-5 py-4">
            <div className="overflow-hidden rounded-[10px] border border-border">
              <table className="w-full min-w-[900px] table-fixed text-left text-[10.5px]">
                <thead className="bg-surface-soft text-muted">
                  <tr>
                    <th className="w-[20%] px-4 py-3">바코드</th>
                    <th className="w-[34%] px-4 py-3">상품명 · SKU</th>
                    <th className="px-4 py-3 text-right">쇼티지 방어</th>
                    <th className="px-4 py-3 text-right">현금흐름 우선</th>
                    <th className="px-4 py-3 text-right">차이</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {pageRows.map((row) => {
                    const amountDifference = row.cashOrderAmountKrw != null && row.shortageOrderAmountKrw != null
                      ? row.shortageOrderAmountKrw - row.cashOrderAmountKrw
                      : null;
                    return (
                      <tr key={row.sku}>
                        <td className="select-text whitespace-nowrap px-4 py-3 font-mono tabular-nums text-muted">{row.barcode || "미확인"}</td>
                        <td className="px-4 py-3">
                          <strong className="block break-words text-[11px] font-black leading-5 text-ink">{row.productName}</strong>
                          <span className="mt-1 block break-all text-[10px] font-semibold text-muted">{row.sku}</span>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right font-black tabular-nums">
                          <span className="block">{formatInteger(row.shortageSuggestedQty)} EA</span>
                          {canViewAmountData ? <span className="mt-1 block text-[10px] text-muted">{formatComparisonAmount(row.shortageOrderAmountKrw)}</span> : null}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums">
                          <span className="block">{formatInteger(row.cashSuggestedQty)} EA</span>
                          {canViewAmountData ? <span className="mt-1 block text-[10px] font-semibold text-muted">{formatComparisonAmount(row.cashOrderAmountKrw)}</span> : null}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right font-black tabular-nums text-brand">
                          <span className="block">{formatSignedInteger(row.shortageSuggestedQty - row.cashSuggestedQty)} EA</span>
                          {canViewAmountData ? <span className="mt-1 block text-[10px]">{formatComparisonAmount(amountDifference, true)}</span> : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
          <footer className="flex flex-col gap-2 border-t border-border bg-surface-soft/60 px-5 py-3 text-[10px] font-bold text-muted sm:flex-row sm:items-center sm:justify-between"><span>수량 차이 {formatInteger(changedRows.length)}건 · 큰 차이 순</span><div className="flex items-center gap-2"><button type="button" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={activePage === 1} className="h-8 rounded-[7px] border border-border bg-white px-3 text-[10px] font-black text-ink disabled:cursor-not-allowed disabled:opacity-40">이전</button><span>{activePage} / {totalPages}</span><button type="button" onClick={() => setPage((current) => Math.min(totalPages, current + 1))} disabled={activePage === totalPages} className="h-8 rounded-[7px] border border-border bg-white px-3 text-[10px] font-black text-ink disabled:cursor-not-allowed disabled:opacity-40">다음</button></div></footer>
        </> : <div className="px-5 py-10 text-center"><p className="text-[13px] font-black text-ink">두 시나리오의 수량 차이가 없습니다.</p><p className="mt-1 text-[10.5px] font-semibold text-muted">계산 가능한 SKU의 제안수량이 동일합니다.</p></div>}
      </section>
    </div>
  );
}

export function OrderV3Screen() {
  const { user, selectedEntity } = useAuthSession();
  if (!selectedEntity) return <div role="status" className="p-6 text-sm text-muted">분석할 법인을 선택해 주세요.</div>;
  // Reset the entire review session before displaying another entity's screen.
  return <OrderV3EntityScreen
    key={`${user?.username ?? ""}:${selectedEntity}`}
    entityCode={selectedEntity}
    username={user?.username ?? ""}
  />;
}

function OrderV3EntityScreen({ entityCode, username }: { entityCode: EntityCode; username: string }) {
  const { canViewAmountData: canDownloadAmountData } = useUserPermissions();
  // 발주분석 V3 화면은 모든 계정에 발주금액을 표시한다(2026-09-02 사용자 요청).
  // 엑셀 내보내기의 금액 포함 여부는 서버가 /auth/me 권한으로 다시 판정하므로
  // 화면 표시용 플래그와 다운로드 권한 플래그를 분리해 둔다.
  const canViewAmountData = true;
  const disposed = useRef(false);
  const analysisRequest = useRef<AbortController | null>(null);
  const analysisJobId = useRef<string | null>(null);
  const exportRequest = useRef<AbortController | null>(null);
  useEffect(() => {
    disposed.current = false;
    return () => {
      disposed.current = true;
      analysisRequest.current?.abort();
      exportRequest.current?.abort();
    };
  }, []);
  const isScreenActive = () => !disposed.current && getActiveEntityCode() === entityCode;
  const [result, setResult] = useState<OrderLogicV3Result | null>(null);
  const [scenario, setScenario] = useState<OrderV3Scenario>("SHORTAGE");
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const [reviewView, setReviewView] = useState<OrderV3ReviewView>("needed");
  const [exclusionReason, setExclusionReason] = useState("all");
  const [brand, setBrand] = useState("all");
  const [reviewDecision, setReviewDecision] = useState("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [decisionsByScenario, setDecisionsByScenario] = useState<Record<OrderV3Scenario, Record<string, OrderV3DecisionState>>>({
    SHORTAGE: {},
    CASH: {}
  });
  const [selectedSku, setSelectedSku] = useState<string | null>(null);
  const [selectedSkus, setSelectedSkus] = useState<Set<string>>(new Set());
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [stopped, setStopped] = useState(false);
  const [stopFailed, setStopFailed] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [lastCalculatedAt, setLastCalculatedAt] = useState("실행 전");
  const [statusMessage, setStatusMessage] = useState("");
  const rows = useMemo(() => result ? mapScenarioRows(result, scenario) : [], [result, scenario]);
  const decisions = decisionsByScenario[scenario];

  const viewRows = useMemo(() => rows.filter((row) => reviewViewOf(row) === reviewView), [rows, reviewView]);
  const viewCounts = useMemo(() => {
    const counts: Record<OrderV3ReviewView, number> = { needed: 0, "not-needed": 0, excluded: 0, unknown: 0 };
    rows.forEach((row) => { counts[reviewViewOf(row)] += 1; });
    return counts;
  }, [rows]);
  const showExclusionReasons = reviewView === "excluded";
  const brands = useMemo(() => Array.from(new Set(rows.map((row) => row.brand))).sort(), [rows]);
  const summaryRows = useMemo(
    () => brand === "all" ? rows : rows.filter((row) => row.brand === brand),
    [brand, rows]
  );
  const excludedRows = useMemo(() => rows.filter((row) => row.calculable === false), [rows]);
  const heldCount = excludedRows.filter((row) => row.dataStatus === "발주보류").length;
  const exclusionReasons = useMemo(() => {
    const groups = new Map<string, { key: string; label: string; count: number }>();
    for (const row of excludedRows) {
      const key = exclusionReasonKey(row);
      const group = groups.get(key);
      if (group) group.count += 1;
      else groups.set(key, { key, label: `${row.dataStatus === "발주보류" ? "보류" : "차단"} · ${exclusionReasonLabel(row)}`, count: 1 });
    }
    return Array.from(groups.values()).sort((left, right) => right.count - left.count);
  }, [excludedRows]);
  const filteredRows = useMemo(
    () => filterReviewRows(rows, { view: reviewView, brand, query, reviewDecision, exclusionReason }, decisions),
    [brand, decisions, exclusionReason, query, reviewDecision, reviewView, rows]
  );
  const totalPages = Math.max(1, Math.ceil(filteredRows.length / REVIEW_PAGE_SIZE));
  const activePage = Math.min(page, totalPages);
  const pageRows = filteredRows.slice((activePage - 1) * REVIEW_PAGE_SIZE, activePage * REVIEW_PAGE_SIZE);
  const pageStart = filteredRows.length ? (activePage - 1) * REVIEW_PAGE_SIZE + 1 : 0;
  const pageEnd = Math.min(activePage * REVIEW_PAGE_SIZE, filteredRows.length);
  const priorityRows = useMemo(() => filteredRows.filter((row) => row.signal === "확인 후 발주" || row.signal === "즉시 발주"), [filteredRows]);
  const reviewQueue = filteredRows;
  const selectedRow = rows.find((row) => row.sku === selectedSku) ?? null;
  const selectedQueueIndex = selectedRow ? reviewQueue.findIndex((row) => row.sku === selectedRow.sku) : -1;
  const priorityIndex = selectedRow ? priorityRows.findIndex((row) => row.sku === selectedRow.sku) : -1;
  const { completed: reviewedCount, total: reviewTotalCount } = reviewProgress(summaryRows, decisions);
  const selectedReviewCount = filteredRows.filter((row) => reviewViewOf(row) === "needed" && selectedSkus.has(row.sku)).length;
  const exportRows = reviewExportRows(filteredRows, selectedSkus);
  const attentionRows = attentionExportRows(rows, { view: reviewView, brand, query, exclusionReason }, selectedSkus);
  const canExport = exportRows.length > 0 || (attentionRows.length > 0 && (reviewView === "excluded" || selectedSkus.size === 0));
  const exportCount = reviewView === "excluded" ? attentionRows.length : exportRows.length;
  const emptyMessage = viewRows.length ? "조건에 맞는 상품이 없습니다." : REVIEW_EMPTY_MESSAGES[reviewView];
  const emptyDescription = viewRows.length
    ? "필터나 검색어를 바꿔 주세요."
    : reviewView === "needed"
      ? "발주 불필요 또는 보류·차단 목록에서 다른 상품을 확인할 수 있습니다."
      : "발주 검토 목록에서 발주가 필요한 상품을 확인하세요.";

  const openRow = (sku: string) => { setSelectedSku(sku); setDrawerOpen(true); };
  const moveQueue = (direction: 1 | -1) => {
    if (!reviewQueue.length) return;
    const current = selectedQueueIndex >= 0 ? selectedQueueIndex : 0;
    setSelectedSku(reviewQueue[(current + direction + reviewQueue.length) % reviewQueue.length].sku);
  };
  const applyDecision = (decision: OrderV3ReviewDecision, quantity?: number) => {
    if (!selectedRow || reviewViewOf(selectedRow) !== "needed") return;
    const finalQty = decision === "발주 보류" ? 0 : quantity ?? selectedRow.finalOrderQty;
    setDecisionsByScenario((current) => ({
      ...current,
      [scenario]: { ...current[scenario], [selectedRow.sku]: { decision, finalQty } }
    }));
    const currentIndex = reviewQueue.findIndex((row) => row.sku === selectedRow.sku);
    const candidates = reviewQueue.filter((row) => row.sku !== selectedRow.sku && reviewViewOf(row) === "needed" && (decisions[row.sku]?.decision ?? "미검토") === "미검토");
    const next = candidates.find((row) => reviewQueue.indexOf(row) > currentIndex) ?? candidates[0];
    if (next) setSelectedSku(next.sku);
  };
  const applyBulkDecision = (decision: OrderV3ReviewDecision) => {
    const targets = filteredRows.filter((row) => selectedSkus.has(row.sku) && reviewViewOf(row) === "needed");
    if (!targets.length) return;
    setDecisionsByScenario((current) => ({
      ...current,
      [scenario]: {
        ...current[scenario],
        ...Object.fromEntries(targets.map((row) => [row.sku, {
          decision,
          finalQty: decision === "발주 보류" ? 0 : row.finalOrderQty
        }]))
      }
    }));
    setSelectedSkus(new Set());
    setStatusMessage(`${targets.length}건을 ${decision} 처리했습니다.`);
    window.setTimeout(() => setStatusMessage(""), 2400);
  };
  const toggleSelected = (sku: string) => setSelectedSkus((current) => { const next = new Set(current); if (next.has(sku)) next.delete(sku); else next.add(sku); return next; });
  const toggleAll = () => setSelectedSkus((current) => {
    const selectableRows = pageRows;
    const next = new Set(current);
    if (selectableRows.length && selectableRows.every((row) => next.has(row.sku))) selectableRows.forEach((row) => next.delete(row.sku));
    else selectableRows.forEach((row) => next.add(row.sku));
    return next;
  });
  const resetFilters = () => {
    setBrand("all"); setReviewDecision("all"); setQuery(""); setExclusionReason("all"); setPage(1);
    setSelectedSkus(new Set()); setSelectedSku(null); setDrawerOpen(false);
  };
  const changeReviewView = (nextView: OrderV3ReviewView) => {
    setReviewView(nextView);
    resetFilters();
  };
  const toggleExclusions = () => changeReviewView(showExclusionReasons ? "needed" : "excluded");
  const changeScenario = (nextScenario: OrderV3Scenario) => {
    if (nextScenario === scenario) return;
    setScenario(nextScenario);
    setExclusionReason("all");
    setSelectedSkus(new Set());
    setSelectedSku(null);
    setDrawerOpen(false);
    setPage(1);
  };

  const stopAnalysis = async () => {
    const controller = analysisRequest.current;
    if (!controller || stopping || !isScreenActive()) return;
    setStopping(true); setStopFailed(false); setStatusMessage("");
    if (!controller.signal.aborted) {
      // runOrderLogicV3 will cancel the server job once its ID is available.
      controller.abort();
      return;
    }
    // A failed cancellation keeps the job ID and allows an explicit retry.
    const jobId = analysisJobId.current;
    if (!jobId) return;
    try {
      const status = await cancelOrderLogicV3Job(jobId, entityCode);
      if (analysisRequest.current !== controller || !isScreenActive()) return;
      analysisRequest.current = null;
      analysisJobId.current = null;
      clearOrderV3ActiveJob(username, entityCode);
      setRunning(false); setStopping(false); setStopped(true);
      setStatusMessage(status === "cancelled"
        ? "분석을 중단했습니다. 이미 시작된 원천 조회는 서버에서 마무리될 수 있습니다."
        : "이미 종료된 분석의 결과 수신을 중단했습니다.");
    } catch {
      if (analysisRequest.current !== controller || !isScreenActive()) return;
      setStopping(false); setStopFailed(true);
      setStatusMessage("서버의 분석 중단을 확인하지 못했습니다. ‘분석 중단’을 눌러 다시 시도해 주세요.");
    }
  };

  const executeAnalysis = async (resumeJobId?: string, recovering = false) => {
    if (running || exporting || exportRequest.current || analysisRequest.current || !isScreenActive()) return;
    const controller = new AbortController();
    analysisRequest.current = controller;
    analysisJobId.current = null;
    let keepForStopRetry = false;
    setRunning(true); setStopping(false); setStopped(false); setStopFailed(false);
    setStatusMessage(recovering ? "진행 중이던 분석을 확인하고 있습니다." : "");
    try {
      const now = new Date();
      const asOf = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
      let reconnectJobId = resumeJobId;
      let payload: OrderLogicV3Result;
      for (;;) {
        try {
          payload = await runOrderLogicV3(asOf, {
            entityCode, signal: controller.signal, resumeJobId: reconnectJobId,
            onJobStarted: (jobId) => {
              if (analysisRequest.current === controller) {
                analysisJobId.current = jobId;
                saveOrderV3ActiveJob(username, entityCode, jobId);
              }
            },
            onStatusChange: (status) => {
              if (analysisRequest.current === controller && !controller.signal.aborted && isScreenActive()) {
                setStatusMessage(status === "queued"
                  ? "V3 분석 요청이 접수되었습니다. 사용 가능한 분석 Worker를 기다리는 중입니다."
                  : "V3 분석을 실행하고 있습니다. 원천 데이터 조회와 계산을 진행 중입니다.");
              }
            },
            onReceiveProgress: (received, total) => {
              if (analysisRequest.current === controller && !controller.signal.aborted && isScreenActive()) {
                setStatusMessage(`분석 결과 받는 중 ${formatInteger(received)} / ${formatInteger(total)} SKU`);
              }
            }
          });
          break;
        } catch (caught) {
          if (!(caught instanceof OrderLogicV3ConnectionError) || controller.signal.aborted || !isScreenActive()) throw caught;
          reconnectJobId = caught.jobId;
          analysisJobId.current = caught.jobId;
          saveOrderV3ActiveJob(username, entityCode, caught.jobId);
          setStatusMessage("서버 연결이 지연되어 같은 분석에 자동으로 다시 연결하고 있습니다.");
          await new Promise<void>((resolve) => window.setTimeout(resolve, 1_500));
          controller.signal.throwIfAborted();
        }
      }
      if (analysisRequest.current !== controller || controller.signal.aborted || !isScreenActive()) return;
      clearOrderV3ActiveJob(username, entityCode);
      const nextShortageRows = mapScenarioRows(payload, "SHORTAGE");
      const nextCashRows = mapScenarioRows(payload, "CASH");
      setResult(payload);
      setStatusMessage("");
      setReviewView("needed");
      resetFilters();
      setDecisionsByScenario({
        SHORTAGE: createInitialDecisions(nextShortageRows),
        CASH: createInitialDecisions(nextCashRows)
      });
      setSelectedSkus(new Set());
      setSelectedSku(null);
      setDrawerOpen(false);
      setPage(1);
      setLastCalculatedAt(new Date(payload.calculated_at).toLocaleString("ko-KR"));
      if (payload.status === "blocked") {
        setStatusMessage(
          payload.blocking_contracts.length
            ? `V3 계산이 ${payload.blocking_contracts.length}개 미확정 계약 때문에 차단됐습니다.`
            : `${payload.summary.blocked_sku_count}개 SKU가 계산 사유와 함께 차단됐습니다.`
        );
      }
    } catch (caught) {
      if (analysisRequest.current === controller && isScreenActive()) {
        if (caught instanceof OrderLogicV3CancellationError) {
          keepForStopRetry = true;
          analysisJobId.current = caught.jobId;
          setStopFailed(true);
          setStatusMessage(caught.message);
        } else if (isAbortError(caught)) {
          clearOrderV3ActiveJob(username, entityCode);
          setStopped(true);
          setStatusMessage(`${caught instanceof Error ? caught.message : "분석 요청이 중단되었습니다."}${result ? " 이전 완료 결과는 유지됩니다." : ""}`);
        } else if (!controller.signal.aborted) {
          clearOrderV3ActiveJob(username, entityCode);
          setStatusMessage(recovering
            ? "이전에 진행하던 분석을 불러올 수 없어 정리했습니다. 새로 분석해 주세요."
            : caught instanceof Error ? caught.message : "V3 계산 요청에 실패했습니다.");
        }
      }
    } finally {
      if (analysisRequest.current === controller) {
        if (!keepForStopRetry) { analysisRequest.current = null; analysisJobId.current = null; }
        if (isScreenActive()) { setRunning(keepForStopRetry); setStopping(false); }
      }
    }
  };
  const runAnalysis = () => executeAnalysis();

  useEffect(() => {
    const activeJobId = loadOrderV3ActiveJob(username, entityCode);
    if (activeJobId) void executeAnalysis(activeJobId, true);
    // The screen is keyed by account and entity, so this recovery check runs
    // once for that exact scope. Subsequent connection retries stay in the
    // same executeAnalysis call and never create another calculation job.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const exportExcel = async () => {
    if (exporting || exportRequest.current || running || !canExport || !result || result.entity_code !== entityCode || !isScreenActive()) return;
    const controller = new AbortController();
    exportRequest.current = controller;
    setExporting(true);
    const brandLabel = brand === "all" ? "전체 브랜드" : brand;
    setStatusMessage(`${brandLabel} 엑셀을 서버에서 준비 중입니다. 분석은 다시 실행하지 않습니다.`);
    try {
      const blob = await downloadOrderV3Excel({
        result, scenario, skus: exportRows.map((row) => row.sku), decisions, canViewAmountData: canDownloadAmountData,
        viewTitle: `${selectedSkus.size ? `선택 ${exportCount}건` : REVIEW_VIEW_TITLES[reviewView]} · ${brandLabel}`,
        attentionSkus: attentionRows.map((row) => row.sku),
        brandScope: brand === "all" ? null : brand,
        attentionScope: reviewView === "excluded"
          ? `${brandLabel} 보류·차단 목록의 검색·사유 필터 및 선택 적용`
          : `${brandLabel} 범위의 검색 조건 전체 보류·차단 상품 (검토상태·상품 선택과 별도)`
      }, controller.signal, (bytes) => {
        if (isScreenActive()) setStatusMessage(`엑셀 파일 받는 중 · ${(bytes / 1024 / 1024).toFixed(1)} MB`);
      });
      if (!isScreenActive() || controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const scenarioFileLabel = scenario === "SHORTAGE" ? "쇼티지방어" : "현금흐름우선";
      const scopeFileLabel = brand === "all" ? "전체브랜드" : safeFileLabel(brand);
      const link = document.createElement("a");
      link.href = url;
      link.download = `발주분석_V3_${entityCode}_${scopeFileLabel}_${scenarioFileLabel}_${selectedSkus.size ? `선택_${exportCount}건` : REVIEW_VIEW_TITLES[reviewView]}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setStatusMessage(`${brandLabel} 엑셀 다운로드가 준비되었습니다.`);
    } catch (caught) {
      if (isScreenActive()) setStatusMessage(caught instanceof Error ? caught.message : "엑셀 생성에 실패했습니다.");
    } finally {
      if (exportRequest.current === controller) exportRequest.current = null;
      if (isScreenActive()) setExporting(false);
    }
  };

  return (
    <div className="min-h-full bg-page">
      <ExecutionStatusBar entityCode={entityCode} result={result} lastCalculatedAt={lastCalculatedAt} running={running} stopping={stopping} stopped={stopped} stopFailed={stopFailed} exporting={exporting} exportLabel="엑셀 내려받기" exportDescription={`${brand === "all" ? "전체 브랜드" : brand} · 발주제안·물류전망 ${exportRows.length}개 / 확인필요 ${attentionRows.length}개. 같은 브랜드·검색 범위의 보류·차단 목록을 함께 내보냅니다.`} canExport={canExport} onRun={runAnalysis} onStop={stopAnalysis} onExport={exportExcel} />
      <main className="mx-auto max-w-[1480px] space-y-4 px-4 py-4 lg:px-6 lg:py-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-[18px] font-black tracking-tight text-ink">발주 제안 검토</h2>
            <p className="mt-1 text-[10.5px] font-semibold text-muted">발주가 필요한 상품의 제안수량을 검토하세요</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div role="group" aria-label="발주 시나리오 선택" className="inline-flex h-9 rounded-[8px] border border-border bg-white p-0.5">
              <button type="button" onClick={() => changeScenario("SHORTAGE")} disabled={running} aria-pressed={scenario === "SHORTAGE"} className={cn("rounded-[6px] px-3 text-[10px] font-black transition disabled:cursor-not-allowed disabled:opacity-50", scenario === "SHORTAGE" ? "bg-brand-50 text-brand" : "text-muted hover:bg-surface-soft hover:text-ink")}>쇼티지 방어</button>
              <button type="button" onClick={() => changeScenario("CASH")} disabled={running} aria-pressed={scenario === "CASH"} className={cn("rounded-[6px] px-3 text-[10px] font-black transition disabled:cursor-not-allowed disabled:opacity-50", scenario === "CASH" ? "bg-brand-50 text-brand" : "text-muted hover:bg-surface-soft hover:text-ink")}>현금흐름 우선</button>
            </div>
            <button type="button" onClick={() => setComparisonOpen(true)} className="inline-flex h-9 items-center gap-2 rounded-[8px] border border-border bg-white px-3 text-[10px] font-black text-ink hover:bg-surface-soft"><GitCompareArrows className="h-3.5 w-3.5" /> {canViewAmountData ? "발주수량·금액 비교" : "발주수량 비교"}</button>
          </div>
        </div>
        <ReviewSummary rows={summaryRows} reviewedCount={reviewedCount} reviewTotalCount={reviewTotalCount} canViewAmountData={canViewAmountData} exclusionsOpen={showExclusionReasons} onToggleExclusions={toggleExclusions} />
        <section className="rounded-[12px] border border-border bg-white shadow-card">
          <div className="flex flex-col gap-3 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2"><h3 className="text-[13px] font-black text-ink">{REVIEW_VIEW_TITLES[reviewView]}</h3><span className="rounded-full bg-surface-soft px-2 py-1 text-[9px] font-black text-muted">{formatInteger(filteredRows.length)}건</span></div>
              <p className="mt-1 text-[9.5px] font-semibold text-muted">{showExclusionReasons
                ? "사유를 선택해 상품을 좁히고, 각 상품에서 상세 내용을 확인하세요."
                : reviewView === "needed"
                  ? "발주가 필요한 상품만 표시합니다. 제안수량은 최종 주문 확정 전 참고값입니다."
                  : reviewView === "not-needed"
                    ? "현재 분석에서 발주가 불필요한 상품입니다. 상품을 눌러 계산 근거를 확인하세요."
                    : "발주 여부를 확인할 수 없는 상품입니다. 상품별 상세 내용을 확인하세요."}</p>
            </div>
            <nav aria-label="다른 상품 목록" className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[10px] font-bold">
              {reviewView !== "needed" ? <button type="button" onClick={() => changeReviewView("needed")} className="rounded text-brand underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand">발주 검토 목록으로</button> : null}
              {reviewView !== "not-needed" ? <button type="button" onClick={() => changeReviewView("not-needed")} className="rounded text-muted underline underline-offset-4 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand">발주 불필요 {formatInteger(viewCounts["not-needed"])}건 보기</button> : null}
              {!showExclusionReasons ? <button type="button" onClick={() => changeReviewView("excluded")} className="rounded text-muted underline underline-offset-4 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand">보류·차단 {formatInteger(viewCounts.excluded)}건 보기</button> : null}
              {reviewView !== "unknown" && viewCounts.unknown > 0 ? <button type="button" onClick={() => changeReviewView("unknown")} className="rounded text-amber-800 underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand">상태 확인 필요 {formatInteger(viewCounts.unknown)}건 보기</button> : null}
            </nav>
          </div>
          <div className="border-t border-border bg-surface-soft/60 px-4 py-3">
            <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
              <label className="relative min-w-0 flex-1"><span className="sr-only">상품 검색</span><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="상품코드, 상품명, 브랜드 검색" className="h-10 w-full rounded-[8px] border border-border bg-white pl-9 pr-3 text-[10.5px] font-bold text-ink outline-none placeholder:text-muted2 focus:border-brand focus:ring-2 focus:ring-brand/15" /></label>
              <div className="flex flex-wrap gap-2">
                <div className="min-w-[136px] flex-1 sm:flex-none">
                  <BrandSearchSelect
                    value={brand}
                    options={brands}
                    allValue="all"
                    allLabel="전체 브랜드"
                    onChange={(value) => { setBrand(value); setPage(1); }}
                    dropdownAlign="responsive"
                    buttonClassName="h-10 w-full min-w-[136px] rounded-[8px] bg-white px-3 text-[10.5px] outline-none transition hover:border-muted2 focus:border-brand focus:ring-2 focus:ring-brand/15"
                    testId="order-v3-brand-filter"
                  />
                </div>
                {reviewView === "needed" ? <FilterSelect label="검토 상태" value={reviewDecision} onChange={(value) => { setReviewDecision(value); setPage(1); }} options={[{ value: "all", label: "전체 검토상태" }, { value: "미검토", label: "미검토" }, { value: "권고 유지", label: "권고 유지" }, { value: "수량 수정", label: "수량 수정" }, { value: "발주 보류", label: "발주 보류" }]} /> : null}
                {(exclusionReason !== "all" || brand !== "all" || reviewDecision !== "all" || query) ? <button type="button" onClick={resetFilters} aria-label="필터 초기화" className="grid h-10 w-10 place-items-center rounded-[8px] border border-border bg-white text-muted hover:text-ink"><X className="h-4 w-4" /></button> : null}
              </div>
            </div>
          </div>
          {showExclusionReasons ? (
            <section id="order-v3-exclusion-reasons" aria-label="보류·차단 사유 필터" className="space-y-3 border-t border-amber-200 bg-amber-50/50 px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[11px] font-black text-amber-900">발주 보류 {formatInteger(heldCount)}건 · 계산 차단 {formatInteger(excludedRows.length - heldCount)}건 <span className="font-semibold text-muted">(현재 시나리오 전체)</span></p>
              </div>
              <div role="group" aria-label="보류·차단 사유 선택" className="flex flex-wrap gap-2">
                {[{ key: "all", label: "전체 사유", count: excludedRows.length }, ...exclusionReasons].map((reason) => (
                  <button key={reason.key} type="button" aria-pressed={exclusionReason === reason.key} onClick={() => { setExclusionReason(reason.key); setPage(1); }} className={cn("rounded-[7px] border px-3 py-2 text-left text-[10px] font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500", exclusionReason === reason.key ? "border-amber-400 bg-amber-100 text-amber-900" : "border-border bg-white text-muted hover:border-amber-300")}>
                    {reason.label} <span className="ml-1 font-black">{formatInteger(reason.count)}건</span>
                  </button>
                ))}
              </div>
            </section>
          ) : null}
          <BulkActionBar selectedCount={selectedReviewCount} onHold={() => applyBulkDecision("발주 보류")} onKeep={() => applyBulkDecision("권고 유지")} />
          <TriageProposalTable rows={pageRows} hasResult={Boolean(result)} showExclusionReasons={showExclusionReasons} emptyMessage={emptyMessage} emptyDescription={emptyDescription} decisions={decisions} selectedSku={selectedSku} selectedSkus={selectedSkus} canViewAmountData={canViewAmountData} onToggle={toggleSelected} onToggleAll={toggleAll} onOpen={openRow} />
          {filteredRows.length ? <div className="flex flex-col gap-2 border-t border-border bg-surface-soft/60 px-4 py-3 text-[10px] font-bold text-muted sm:flex-row sm:items-center sm:justify-between"><span>{formatInteger(pageStart)}–{formatInteger(pageEnd)} / 총 {formatInteger(filteredRows.length)}건 · 페이지당 {REVIEW_PAGE_SIZE}건</span><div className="flex items-center gap-2"><button type="button" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={activePage === 1} className="h-8 rounded-[7px] border border-border bg-white px-3 text-[10px] font-black text-ink disabled:cursor-not-allowed disabled:opacity-40">이전</button><label className="flex items-center gap-1.5"><span className="sr-only">페이지 선택</span><select value={activePage} onChange={(event) => setPage(Number(event.target.value))} className="h-8 rounded-[7px] border border-border bg-white px-2 text-[10px] font-black text-ink"><option value={activePage}>{activePage} / {totalPages}</option>{Array.from({ length: totalPages }, (_, index) => index + 1).filter((value) => value !== activePage).map((value) => <option key={value} value={value}>{value} / {totalPages}</option>)}</select></label><button type="button" onClick={() => setPage((current) => Math.min(totalPages, current + 1))} disabled={activePage === totalPages} className="h-8 rounded-[7px] border border-border bg-white px-3 text-[10px] font-black text-ink disabled:cursor-not-allowed disabled:opacity-40">다음</button></div></div> : null}
        </section>
      </main>
      <ScenarioComparison open={comparisonOpen} rows={rows} canViewAmountData={canViewAmountData} onClose={() => setComparisonOpen(false)} />
      <OrderV3EvidenceDrawer open={drawerOpen} row={selectedRow} overallPosition={Math.max(selectedQueueIndex, 0)} overallTotal={reviewQueue.length} priorityPosition={Math.max(priorityIndex, 0)} priorityTotal={priorityRows.length} decision={selectedRow ? decisions[selectedRow.sku] : null} scenarioLabel={SCENARIO_LABELS[scenario]} canViewAmountData={canViewAmountData} onClose={() => setDrawerOpen(false)} onPrevious={() => moveQueue(-1)} onNext={() => moveQueue(1)} onKeep={() => applyDecision("권고 유지")} onSaveQuantity={(quantity) => applyDecision("수량 수정", quantity)} onHold={() => applyDecision("발주 보류")} />
      {statusMessage ? <div role="status" className="fixed bottom-4 left-1/2 z-[100] w-max max-w-[calc(100%-2rem)] -translate-x-1/2 rounded-[12px] bg-ink px-4 py-2 text-center text-[10.5px] font-black text-white shadow-panel">{statusMessage}</div> : null}
    </div>
  );
}
