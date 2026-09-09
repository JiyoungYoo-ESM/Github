"use client";

import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  PauseCircle,
  PencilLine,
  X
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { formatCalendarDuration } from "@/lib/format-calendar-duration";
import { cn } from "@/lib/utils";
import { chartColors } from "@/lib/chart-tokens";

import { DEMAND_HORIZON_LABEL, DEMAND_HORIZON_PERIODS, demandOverHorizon } from "./demandHorizon";
import { displayOrderQuantity, reviewViewOf } from "./reviewList";
import type { OrderV3DecisionState, OrderV3Row } from "./types";

const PERIOD_LABELS = [
  "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P11", "P12", "P13"
];

const integerFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 });

function formatInteger(value: number) {
  return integerFormatter.format(value);
}

function orderUnitDescription(row: OrderV3Row) {
  if (row.orderUnitSource === "OUTBOX") return `아웃박스(${formatInteger(row.orderUnitQty ?? 0)}입수) 단위`;
  if (row.orderUnitSource === "INBOX") return `인박스(${formatInteger(row.orderUnitQty ?? 0)}입수) 단위`;
  if (row.orderUnitSource === "FALLBACK_10") return "박스입수 미설정으로 10개 단위";
  return "주문단위 미확인";
}

function StepTitle({ number, children }: { number: number; children: React.ReactNode }) {
  return (
    <h3 className="flex items-center gap-2 whitespace-nowrap text-[13px] font-black text-ink">
      <span className="grid h-5 w-5 place-items-center rounded-full bg-ink text-[10px] text-white">
        {number}
      </span>
      {children}
    </h3>
  );
}

function MetricBox({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <div
      className={cn(
        "flex min-h-[60px] min-w-[68px] flex-1 flex-col items-center justify-center rounded-[10px] border px-2 text-center sm:min-w-[72px]",
        accent ? "border-emerald-300 bg-emerald-50" : "border-border bg-surface"
      )}
    >
      <span className="text-[10px] font-bold text-muted">{label}</span>
      <strong className={cn("mt-1 text-[14px] font-black", accent ? "text-emerald-800" : "text-ink")}>{value}</strong>
    </div>
  );
}

function OrderV3CalculationDetails({ row }: { row: OrderV3Row }) {
  const inventoryParts = row.inventoryParts;

  return (
    <div className="space-y-5 border-t border-border px-4 py-4 text-[11px] font-medium leading-5 text-muted">
      <section>
        <h4 className="text-[12px] font-black text-ink">발주에 반영한 재고</h4>
        <p className="mt-1">현재 사용 가능한 재고와 입고 예정 물량입니다.</p>
        <dl className="mt-3 space-y-2">
          <div className="flex items-start justify-between gap-4">
            <dt>현재 사용 가능한 재고</dt>
            <dd className="shrink-0 font-bold tabular-nums text-ink">{formatInteger(inventoryParts.localAvailable)}개</dd>
          </div>
          {inventoryParts.hqAvailable !== 0 ? (
            <div className="flex items-start justify-between gap-4">
              <dt>다른 거점에서 반영한 재고</dt>
              <dd className="shrink-0 font-bold tabular-nums text-ink">+ {formatInteger(inventoryParts.hqAvailable)}개</dd>
            </div>
          ) : null}
          <div className="flex items-start justify-between gap-4">
            <dt>운송 중인 수량</dt>
            <dd className="shrink-0 font-bold tabular-nums text-ink">+ {formatInteger(inventoryParts.inTransit)}개</dd>
          </div>
          <div className="flex items-start justify-between gap-4">
            <dt>미입고 수량</dt>
            <dd className="shrink-0 font-bold tabular-nums text-ink">+ {formatInteger(inventoryParts.incoming)}개</dd>
          </div>
          {(inventoryParts.holding ?? 0) !== 0 ? (
            <div className="flex items-start justify-between gap-4">
              <dt>추가 차감 수량</dt>
              <dd className="shrink-0 font-bold tabular-nums text-ink">− {formatInteger(inventoryParts.holding ?? 0)}개</dd>
            </div>
          ) : null}
          <div className="flex items-start justify-between gap-4 border-t border-border pt-2 font-black text-ink">
            <dt>발주 판단에 사용하는 총재고</dt>
            <dd className="shrink-0 tabular-nums">{formatInteger(row.inventoryPosition)}개</dd>
          </div>
        </dl>
      </section>

      <section>
        <h4 className="text-[12px] font-black text-ink">입고 소요기간과 검토 주기</h4>
        <dl className="mt-3 space-y-2">
          <div className="flex items-start justify-between gap-4">
            <dt>입고까지 걸리는 기간</dt>
            <dd className="text-right font-bold tabular-nums text-ink">{formatCalendarDuration(row.leadTimeDays, { showV3Periods: true })}</dd>
          </div>
          <div className="flex items-start justify-between gap-4">
            <dt>다음 발주 검토까지</dt>
            <dd className="text-right font-bold tabular-nums text-ink">{formatCalendarDuration(row.reviewDays, { showV3Periods: true })}</dd>
          </div>
        </dl>
        <p className="mt-2">계산에 실제로 사용한 기간이며, 주말·공휴일을 포함합니다. 1기는 1주(7일)입니다.</p>
      </section>

      <section>
        <h4 className="text-[12px] font-black text-ink">판매 예측에 반영한 기준</h4>
        <p className="mt-1">
          {row.engine === "HOLT+감쇠"
            ? "최근 판매의 증가·감소 추세를 반영하되, 먼 미래로 갈수록 추세의 영향을 줄입니다."
            : row.engine === "Croston+SBA"
              ? "판매가 발생하는 간격과 한 번에 판매되는 수량을 나누어 예측합니다."
              : row.engine === "SES"
                ? "최근 판매량에 더 무게를 두어 앞으로의 수요를 예측합니다."
                : "적용된 예측 방식을 확인해야 합니다."}
        </p>
        {row.engine === "HOLT+감쇠" && row.calendarDaysSinceFirstSale != null ? (
          <div className="mt-2 rounded-[8px] bg-surface-soft px-3 py-2">
            <p>첫 판매 {row.firstSaleDate ?? "확인 필요"} · 분석 마감 {row.analysisSalesCutoff ?? "확인 필요"}</p>
            <p>첫 판매 후 {formatInteger(row.calendarDaysSinceFirstSale)}일 경과 · HOLT 감쇠계수 φ=0.90 공통 적용</p>
          </div>
        ) : null}
      </section>

      <details className="group rounded-[8px] border border-border">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 font-bold text-ink marker:content-none [&::-webkit-details-marker]:hidden">
          계산 설정값 보기
          <ChevronDown className="h-4 w-4 shrink-0 text-muted transition group-open:rotate-180" />
        </summary>
        <div className="space-y-4 border-t border-border px-3 py-3">
          <div>
            <p className="font-bold text-ink">예측에 사용한 계수</p>
            <p className="mt-1">{row.engine === "Croston+SBA" ? "최근 판매량·판매 간격 반영" : "최근 판매량 반영"} (α): {row.coefficients.alpha?.toFixed(2) ?? "확인 필요"}</p>
            {row.engine === "HOLT+감쇠" ? (
              <>
                <p>추세 변화 반영 (β): {row.coefficients.beta?.toFixed(2) ?? "확인 필요"}</p>
                <p>미래 추세의 감쇠 정도 (φ): {row.coefficients.phi?.toFixed(2) ?? "확인 필요"}</p>
              </>
            ) : null}
          </div>
          <div>
            <p className="font-bold text-ink">입고 지연과 수요 변동에 대비한 여유 재고</p>
            <p className="mt-1">입고 소요기간의 변동 폭: {formatCalendarDuration(row.leadTimeSigmaDays, { showV3Periods: true })}</p>
            <p>안전재고 계산값: {formatInteger(row.targetLayers.safetyStockRaw)}개</p>
            <p>적용 범위: 최소 {formatInteger(row.targetLayers.safetyStockFloor)}개 ~ 최대 {formatInteger(row.targetLayers.safetyStockCap)}개</p>
            <p className="font-bold text-ink">최종 반영한 안전재고: {formatInteger(row.targetLayers.safetyStock)}개</p>
            <p className="mt-1">계산된 안전재고를 설정된 최소·최대 범위 안에서 적용합니다.</p>
          </div>
        </div>
      </details>

      <p className="rounded-[8px] bg-surface-soft px-3 py-2">
        <span className="font-bold text-ink">발주 전 확인</span><br />
        제안수량에는 박스 단위와 최소 주문수량 조건이 아직 반영되지 않았습니다. 실제 주문 전 별도 확인이 필요합니다.
      </p>
    </div>
  );
}

export function OrderV3EvidenceDrawer({
  open,
  row,
  overallPosition,
  overallTotal,
  decision,
  scenarioLabel,
  canViewAmountData,
  onClose,
  onPrevious,
  onNext,
  onKeep,
  onSaveQuantity,
  onHold
}: {
  open: boolean;
  row: OrderV3Row | null;
  overallPosition: number;
  overallTotal: number;
  priorityPosition: number;
  priorityTotal: number;
  decision: OrderV3DecisionState | null;
  scenarioLabel: string;
  canViewAmountData: boolean;
  onClose: () => void;
  onPrevious: () => void;
  onNext: () => void;
  onKeep: () => void;
  onSaveQuantity: (quantity: number) => void;
  onHold: () => void;
}) {
  const dialogRef = useRef<HTMLElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [editingQuantity, setEditingQuantity] = useState(false);
  const [draftQuantity, setDraftQuantity] = useState(0);

  useEffect(() => {
    if (!row) return;
    setDraftQuantity(displayOrderQuantity(row, decision ?? undefined));
    setEditingQuantity(false);
    setDetailsOpen(false);
  }, [decision, row]);

  useEffect(() => {
    if (!open) return;
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      returnFocusRef.current?.focus();
    };
  }, [open]);

  const chartData = useMemo(
    () =>
      PERIOD_LABELS.map((period, index) => ({
        period,
        sales: row?.salesHistory[index] ?? 0,
        forecast: row?.adjustedForecast[index] ?? 0
      })),
    [row]
  );

  const handleDialogKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), summary, [href], [tabindex]:not([tabindex="-1"])'
      ) ?? []
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  if (!open || !row) return null;

  const reviewView = reviewViewOf(row);
  const canReview = reviewView === "needed";
  const hasOrderResult = canReview || reviewView === "not-needed";
  const needsOrder = row.suggestedQty > 0;
  const resultLabel = reviewView === "not-needed"
    ? "발주 불필요"
    : reviewView === "excluded"
      ? row.dataStatus === "발주보류" ? "발주 보류" : "계산 차단"
      : "상태 확인 필요";
  const recommendationReason =
    reviewView === "not-needed"
      ? `발주반영 총재고(IP) ${formatInteger(row.inventoryPosition)}개가 목표재고(S) ${formatInteger(row.targetStock)} 이상이므로 이번에는 발주가 필요하지 않습니다.`
      : !canReview
        ? "발주 여부를 판단하려면 분석 결과를 확인해야 합니다."
        : `순수 정기발주 기준으로 목표재고(S) ${formatInteger(row.targetStock)}에서 발주반영 총재고(IP) ${formatInteger(row.inventoryPosition)}개를 제외해 발주필요수량 ${formatInteger(row.suggestedQty)}개를 산출하고, ${orderUnitDescription(row)} 최종 주문수량 ${formatInteger(row.finalOrderQty)}개로 올림했습니다.`;

  return (
    <>
      <button
        type="button"
        aria-label="SKU 계산 근거 닫기"
        className="fixed inset-0 z-[110] cursor-default bg-black/20"
        onClick={onClose}
      />
      <aside
        id="order-v3-evidence-dialog"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="order-v3-evidence-title"
        onKeyDown={handleDialogKeyDown}
        className="fixed inset-y-0 right-0 z-[120] flex w-full max-w-[560px] flex-col border-l border-border bg-surface shadow-panel"
      >
        <header className="shrink-0 border-b border-border bg-surface px-5 py-4 sm:px-6">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 id="order-v3-evidence-title" className="text-[19px] font-black text-ink">
                  {hasOrderResult ? "SKU 계산 근거" : reviewView === "excluded" ? "보류·차단 사유" : "상품 상세"}
                </h2>
              </div>
              <p className="mt-1 text-[10.5px] font-bold text-muted">
                {scenarioLabel}{hasOrderResult ? null : ` · 상품 ${overallPosition + 1} / ${Math.max(overallTotal, 1)} · ${resultLabel}`}
              </p>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={onPrevious}
                disabled={overallTotal <= 1}
                aria-label="이전 SKU"
                className="grid h-9 w-9 place-items-center rounded-[8px] border border-border text-muted transition hover:bg-surface-soft hover:text-ink disabled:opacity-35"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={onNext}
                disabled={overallTotal <= 1}
                aria-label="다음 SKU"
                className="grid h-9 w-9 place-items-center rounded-[8px] border border-border text-muted transition hover:bg-surface-soft hover:text-ink disabled:opacity-35"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
              <button
                ref={closeButtonRef}
                type="button"
                onClick={onClose}
                aria-label="SKU 계산 근거 닫기"
                className="grid h-9 w-9 place-items-center rounded-[8px] border border-border text-muted transition hover:bg-surface-soft hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div className="mt-4 border-t border-border pt-4">
            <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
              <strong className="text-[14px] font-black text-ink">{row.sku}</strong>
              <span className="min-w-0 truncate text-[11px] font-bold text-muted">{row.productName}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-bold text-muted">
              <span>{row.brand}</span>
              <span>{canReview ? "발주 필요" : resultLabel}</span>
              {row.functionClass1 ? (
                <span>기능구분: {row.functionClass1} / {row.functionClass2 || "미분류"}</span>
              ) : null}
            </div>
          </div>
        </header>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-page px-4 py-4 sm:px-5">
          {row.inventoryWarnings?.length ? (
            <section aria-label="재고 원천 확인" className="rounded-[12px] border border-amber-200 bg-amber-50 p-4 text-[10.5px] font-semibold leading-5 text-amber-900">
              <strong className="block font-black">재고 원천 확인</strong>
              <ul className="mt-1 list-disc space-y-1 pl-4">
                {row.inventoryWarnings.map((message) => <li key={message}>{message}</li>)}
              </ul>
            </section>
          ) : null}
          {row.calculable === false ? (
            <section className="rounded-[12px] border border-amber-200 bg-amber-50 p-4 text-[10.5px] font-semibold leading-5 text-amber-900">
              <strong className="block font-black">{row.dataStatus === "발주보류" ? "이 SKU의 발주를 보류했습니다." : "이 SKU는 계산이 차단됐습니다."}</strong>
              <p className="mt-1">{row.validationError || "필수 원천 또는 정책값이 확정되지 않았습니다."}</p>
              {row.inventorySourceReview?.missingFields.length ? (
                <p className="mt-2 break-words">
                  IP 원천 확인: {row.inventorySourceReview.missingFields.join(", ")}
                </p>
              ) : null}
              {row.seasonFactorReview ? (
                <div className="mt-3 border-t border-amber-200 pt-3">
                  <p>
                    계절지수 상태: {row.seasonFactorReview.artifactStatus} · {row.seasonFactorReview.seasonalityStatus}
                  </p>
                  {row.seasonFactorReview.windowStart && row.seasonFactorReview.windowEnd ? (
                    <p className="mt-1">
                      계산기간: {row.seasonFactorReview.windowStart}~{row.seasonFactorReview.windowEnd}
                    </p>
                  ) : null}
                  {Object.keys(row.seasonFactorReview.factorsByMonth).length ? (
                    <p className="mt-1 break-words">
                      후보지수: {Object.entries(row.seasonFactorReview.factorsByMonth)
                        .sort(([left], [right]) => Number(left) - Number(right))
                        .map(([month, factor]) => `${month}월 ${Number(factor).toFixed(2)}`)
                        .join(" · ")}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </section>
          ) : null}
          {row.calculable === false && row.seasonFactorAvailable != null ? (
            <section aria-label="계절지수 연결 정보" className="rounded-[12px] border border-border bg-surface p-4 text-[10.5px] leading-5">
              <h3 className="font-black text-ink">계절지수 연결</h3>
              <p className="mt-1 font-bold text-ink">
                {row.seasonFactorAvailable
                  ? row.seasonFactorDefaulted ? "기본값 1.0 연결 완료" : "계산된 지수 연결 완료"
                  : "연결 불가"}
              </p>
              {row.seasonFactorAvailable ? (
                <>
                  <p className="mt-1 text-muted">
                    {row.seasonFactorScope === "FUNCTION_CLASS_1" ? "기능구분1 기준" : "기능구분1·2 기준"}의 동일 법인 지수입니다.
                    계절지수는 연결됐지만, 발주 계산은 위 사유로 완료되지 않았습니다.
                  </p>
                  <dl className="mt-3 grid grid-cols-4 gap-2 sm:grid-cols-6">
                    {Object.entries(row.seasonFactorsByMonth ?? {})
                      .sort(([left], [right]) => Number(left) - Number(right))
                      .map(([month, factor]) => (
                        <div key={month} className="rounded-[8px] bg-surface-soft px-2 py-1.5 text-center">
                          <dt className="text-[9px] text-muted">{month}월</dt>
                          <dd className="font-black tabular-nums text-ink">{factor.toFixed(2)}</dd>
                        </div>
                      ))}
                  </dl>
                  <p className="mt-2 break-all text-[9px] text-muted">연결 버전: {row.seasonFactorVersion}</p>
                </>
              ) : (
                <p className="mt-1 text-muted">분류 또는 해당 법인의 계절지수를 확인해야 합니다. 누락값을 임의 지수로 대체하지 않습니다.</p>
              )}
            </section>
          ) : null}
          {row.calculable !== false ? (
          <>
          <section className="rounded-[12px] border border-brand/25 bg-white p-4 shadow-card">
            <div className="flex items-center justify-between gap-3">
              <div>
                {!hasOrderResult ? <p className="text-[9.5px] font-black text-brand">분석 결과</p> : null}
                <h3 className={cn("text-[14px] font-black text-ink", !hasOrderResult && "mt-1")}>{hasOrderResult ? "이 SKU의 발주 제안" : resultLabel}</h3>
              </div>
              <span className="rounded-full border border-brand/20 bg-brand-50 px-2.5 py-1 text-[9px] font-black text-brand">
                {canReview ? "발주 검토" : "조회 전용"}
              </span>
            </div>
            <div className={cn("mt-4 grid grid-cols-2 gap-2", !canViewAmountData && "sm:grid-cols-3")}>
              <div className="rounded-[9px] bg-brand-50 px-3 py-3">
                <span className="text-[9px] font-bold text-brand">최종 주문수량 (박스 올림)</span>
                <strong className="mt-1 block whitespace-nowrap text-[17px] font-black tabular-nums text-brand">{formatInteger(row.finalOrderQty)} EA</strong>
                <span className="mt-0.5 block whitespace-nowrap text-[9px] font-bold text-muted">원시 {formatInteger(row.suggestedQty)} EA · {orderUnitDescription(row)}</span>
              </div>
              {canViewAmountData ? (
                <div className="rounded-[9px] bg-surface-soft px-3 py-3">
                  <span className="text-[9px] font-bold text-muted">발주필요금액</span>
                  <strong className="mt-1 block whitespace-nowrap text-[13px] font-black tabular-nums text-ink">₩{formatInteger(row.orderAmountKrw)}</strong>
                </div>
              ) : null}
              <div className="rounded-[9px] bg-surface-soft px-3 py-3">
                <span className="text-[9px] font-bold text-muted">발주반영 총재고 (IP)</span>
                <strong className="mt-1 block text-[13px] font-black tabular-nums text-ink">{formatInteger(row.inventoryPosition)}</strong>
              </div>
              <div className="rounded-[9px] bg-surface-soft px-3 py-3">
                <span className="text-[9px] font-bold text-muted">목표재고 (S)</span>
                <strong className="mt-1 block text-[13px] font-black tabular-nums text-ink">{formatInteger(row.targetStock)}</strong>
              </div>
            </div>
            <p className="mt-3 flex items-start gap-2 rounded-[8px] border border-border bg-surface-soft px-3 py-2.5 text-[10px] font-bold leading-4 text-ink">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
              {recommendationReason}
            </p>
          </section>

          <section className="rounded-[12px] border border-border bg-surface p-4 shadow-card">
            <div className="flex items-center justify-between gap-3">
              <StepTitle number={1}>향후 수요 예측</StepTitle>
              <span className="rounded-[6px] border border-emerald-200 bg-emerald-50 px-2 py-1 text-[9px] font-black text-emerald-700">
                {row.seasonFactorDefaulted ? "계절지수 기본값 1.0" : "계절 보정 적용"}
              </span>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-[9px] border border-border bg-border sm:grid-cols-[1fr_1fr_1fr_1.5fr]">
              <div className="bg-surface p-3">
                <dt className="text-[9px] font-bold text-muted">적용 엔진</dt>
                <dd className="mt-2 inline-flex rounded-[5px] bg-blue-50 px-2 py-1 text-[11px] font-black text-blue-700">{row.engine}</dd>
              </div>
              <div className="bg-surface p-3">
                <dt className="text-[9px] font-bold text-muted">{DEMAND_HORIZON_LABEL}</dt>
                <dd className="mt-2 text-[12px] font-black text-ink">{formatInteger(demandOverHorizon(row.averageDemand))}</dd>
              </div>
              <div className="bg-surface p-3">
                <dt className="text-[9px] font-bold text-muted">예측오차 (RMSE, EA/기)</dt>
                <dd className="mt-2 text-[12px] font-black text-ink">{row.forecastRmse ? formatInteger(row.forecastRmse) : "-"}</dd>
              </div>
              <div className="bg-surface p-3">
                <dt className="text-[9px] font-bold text-muted">설명</dt>
                <dd className="mt-2 text-[10px] font-bold leading-4 text-ink">
                  {row.pattern === "추세형"
                    ? "최근 추세 반영 · 감쇠 적용"
                    : row.pattern === "간헐형"
                      ? "판매 간격과 발생량 분리 · SBA 보정"
                      : row.pattern === "안정형"
                        ? "최근 수준을 가중 반영"
                        : "이력 확인 후 모델 확정"}
                </dd>
              </div>
            </dl>
            <p className="mt-2 text-[9.5px] font-semibold leading-4 text-muted">
              {DEMAND_HORIZON_LABEL}는 계절 재적용 전 1기(7일) 예측값({formatInteger(row.averageDemand)} EA/기)에 {DEMAND_HORIZON_PERIODS}기를 곱한 값입니다.
            </p>
          </section>

          <section className="rounded-[12px] border border-border bg-surface p-4 shadow-card">
            <StepTitle number={2}>목표재고·정기발주</StepTitle>
            <p className="mt-2 text-[10px] font-bold text-muted">
              보호기간: L {formatCalendarDuration(row.leadTimeDays, { showWeeks: true, showV3Periods: true })} · R {formatCalendarDuration(row.reviewDays, { showWeeks: true, showV3Periods: true })} · σL {formatCalendarDuration(row.leadTimeSigmaDays, { showWeeks: true, showV3Periods: true })}
            </p>
            <div className="mt-3 space-y-2">
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:overflow-x-visible">
                <MetricBox label="L1 리드타임 수요" value={formatInteger(row.targetLayers.leadTimeDemand)} />
                <span className="font-black text-muted">+</span>
                <MetricBox label="L2 안전재고" value={formatInteger(row.targetLayers.safetyStock)} />
                <span className="font-black text-muted">=</span>
                <MetricBox label="참고 ROP(미사용)" value={formatInteger(row.reorderPoint)} />
              </div>
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:overflow-x-visible">
                <MetricBox label="참고 ROP(미사용)" value={formatInteger(row.reorderPoint)} />
                <span className="font-black text-muted">+</span>
                <MetricBox label="L3 발주주기 수요" value={formatInteger(row.targetLayers.reviewDemand)} />
                <span className="font-black text-muted">=</span>
                <MetricBox label="목표재고 S" value={formatInteger(row.targetStock)} accent />
              </div>
            </div>
            <div
              className={cn(
                "mt-3 rounded-[9px] border px-3 py-2.5 text-[10px] font-bold leading-5",
                needsOrder
                  ? "border-brand/25 bg-brand-50 text-ink"
                  : "border-emerald-200 bg-emerald-50 text-emerald-900"
              )}
            >
              <p>
                정기발주: IP {formatInteger(row.inventoryPosition)} {needsOrder ? "<" : "≥"} 목표재고 S {formatInteger(row.targetStock)} → {needsOrder ? "발주 필요" : "발주 불필요"}
              </p>
              <p>
                {needsOrder
                  ? `목표재고 ${formatInteger(row.targetStock)} − IP ${formatInteger(row.inventoryPosition)} = 발주필요수량 ${formatInteger(row.suggestedQty)}개 → ${orderUnitDescription(row)} 최종 ${formatInteger(row.finalOrderQty)}개`
                  : "IP가 목표재고 이상이므로 발주필요수량은 0개입니다."}
              </p>
            </div>
          </section>

          <section className="rounded-[12px] border border-border bg-surface p-4 shadow-card">
            <div className="flex items-center justify-between gap-3">
              <StepTitle number={3}>91일 판매 (13주)</StepTitle>
              <div className="flex flex-wrap items-center gap-3 text-[9.5px] font-bold text-muted">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 bg-slate-300" /> 원본 실적
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-0.5 w-3 bg-brand" /> 계절 제거 후
                </span>
                <span className="rounded-[6px] border border-emerald-200 bg-emerald-50 px-2 py-1 text-emerald-700">
                  {row.seasonFactorDefaulted ? "계절지수 기본값 1.0" : "계절 보정 적용"}
                </span>
              </div>
            </div>
            {row.seasonFactorDefaulted ? (
              <div className="mt-3 rounded-[8px] border border-amber-200 bg-amber-50 px-3 py-2 text-[10px] font-semibold leading-4 text-amber-900">
                <p>계절지수 계산 보류 항목에 기본값 1.0을 적용했습니다. 과거 실적과 미래 예측에 계절성 가감을 하지 않습니다.</p>
                <p className="mt-1 break-all">적용 버전: {row.seasonFactorVersion}</p>
              </div>
            ) : null}
            <div className="mt-3 h-[150px] min-h-0 min-w-0" aria-label={`${row.sku} 91일 13주 판매 및 계절 제거 추이`}>
              <ResponsiveContainer
                width="100%"
                height="100%"
                minWidth={0}
                initialDimension={{ width: 500, height: 150 }}
              >
                <ComposedChart data={chartData} margin={{ top: 10, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke={chartColors.line} />
                  <XAxis dataKey="period" tick={{ fontSize: 8, fill: chartColors.slateMuted }} tickLine={false} axisLine={{ stroke: chartColors.line }} />
                  <YAxis
                    tick={{ fontSize: 8, fill: chartColors.slateMuted }}
                    tickFormatter={(value) => formatInteger(Number(value))}
                    tickLine={false}
                    axisLine={false}
                    width={48}
                  />
                  <Tooltip
                    contentStyle={{ borderRadius: 8, borderColor: chartColors.line, fontSize: 11 }}
                    formatter={(value, name) => {
                      const numericValue = Array.isArray(value) ? Number(value[0]) : Number(value ?? 0);
                      return [
                        formatInteger(numericValue),
                        name === "sales" ? "원본 실적" : "계절 제거 후"
                      ];
                    }}
                  />
                  <Bar dataKey="sales" fill={chartColors.slateLight} barSize={10} radius={[2, 2, 0, 0]} />
                  <Line type="monotone" dataKey="forecast" stroke={chartColors.brand} strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="rounded-[12px] border border-border bg-surface p-4 shadow-card">
            <StepTitle number={4}>자동 분류 근거</StepTitle>
            <div className="mt-3 grid grid-cols-[1fr_1fr_1fr_auto_1.1fr] items-stretch gap-2">
              {[
                ["ADI", row.adiLabel],
                ["CV²", row.cv2Label],
                ["추세", row.trendLabel]
              ].map(([label, value]) => (
                <div key={label} className="rounded-[9px] border border-border px-3 py-2.5">
                  <span className="block text-[9px] font-bold text-muted">{label}</span>
                  <strong className="mt-1 flex items-center gap-1.5 text-[11px] font-black text-ink">
                    {value}
                    <span
                      className={cn(
                        "h-2 w-2 rounded-full",
                        value === "높음" ? "bg-brand" : value === "보통" ? "bg-amber-400" : "bg-emerald-500"
                      )}
                    />
                  </strong>
                </div>
              ))}
              <ChevronRight className="h-5 w-5 self-center text-muted" />
              <div className="grid place-items-center rounded-[9px] border border-blue-200 bg-blue-50 px-3 text-[13px] font-black text-blue-700">
                {row.pattern}
              </div>
            </div>
          </section>

          <section className="overflow-hidden rounded-[10px] border border-border bg-surface shadow-card">
            <button
              type="button"
              aria-expanded={detailsOpen}
              onClick={() => setDetailsOpen((current) => !current)}
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-[11px] font-black text-ink transition hover:bg-surface-soft"
            >
              계산에 사용한 값 자세히 보기
              <ChevronDown className={cn("h-4 w-4 text-muted transition", detailsOpen && "rotate-180")} />
            </button>
            {detailsOpen ? (
              <OrderV3CalculationDetails row={row} />
            ) : null}
          </section>
          </>
          ) : null}
        </div>

        <footer className="shrink-0 border-t border-border bg-surface px-4 py-4 sm:px-5">
          {canReview ? (
            <>
              {editingQuantity ? (
                <div className="mb-3 flex items-end gap-2 rounded-[10px] border border-blue-200 bg-blue-50 p-3">
                  <label className="min-w-0 flex-1 text-[10px] font-black text-blue-900">
                    최종 검토수량
                    <input
                      value={draftQuantity}
                      min={0}
                      step={1}
                      type="number"
                      onChange={(event) => setDraftQuantity(Math.max(0, Math.floor(Number(event.target.value) || 0)))}
                      className="mt-1 h-10 w-full rounded-[8px] border border-blue-200 bg-white px-3 text-[13px] font-black text-ink outline-none focus:border-blue-500"
                    />
                  </label>
                  <button
                    type="button"
                    onClick={() => onSaveQuantity(draftQuantity)}
                    className="inline-flex h-10 items-center justify-center gap-1.5 rounded-[8px] bg-blue-700 px-4 text-[11px] font-black text-white hover:bg-blue-800"
                  >
                    <Check className="h-4 w-4" /> 저장
                  </button>
                </div>
              ) : null}
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={onKeep}
                  disabled={row.calculable === false}
                  className={cn(
                    "inline-flex h-11 items-center justify-center gap-1.5 rounded-[9px] border text-[11px] font-black transition",
                    decision?.decision === "권고 유지"
                      ? "border-brand bg-brand text-white"
                      : "border-brand/50 bg-surface text-brand hover:bg-brand-50"
                  )}
                >
                  <Check className="h-4 w-4" /> 권고 유지
                </button>
                <button
                  type="button"
                  onClick={() => setEditingQuantity((current) => !current)}
                  disabled={row.calculable === false}
                  className={cn(
                    "inline-flex h-11 items-center justify-center gap-1.5 rounded-[9px] border text-[11px] font-black transition",
                    decision?.decision === "수량 수정"
                      ? "border-blue-700 bg-blue-700 text-white"
                      : "border-border bg-surface text-ink hover:bg-surface-soft"
                  )}
                >
                  <PencilLine className="h-4 w-4" /> 수량 수정
                </button>
                <button
                  type="button"
                  onClick={onHold}
                  disabled={row.calculable === false}
                  className={cn(
                    "inline-flex h-11 items-center justify-center gap-1.5 rounded-[9px] border text-[11px] font-black transition",
                    decision?.decision === "발주 보류"
                      ? "border-amber-500 bg-amber-500 text-white"
                      : "border-border bg-surface text-ink hover:bg-surface-soft"
                  )}
                >
                  <PauseCircle className="h-4 w-4" /> 발주 보류
                </button>
              </div>
            </>
          ) : (
            <button
              type="button"
              onClick={onClose}
              className="h-11 w-full rounded-[9px] border border-border bg-surface text-[11px] font-black text-ink transition hover:bg-surface-soft"
            >
              닫기
            </button>
          )}
        </footer>
      </aside>
    </>
  );
}
