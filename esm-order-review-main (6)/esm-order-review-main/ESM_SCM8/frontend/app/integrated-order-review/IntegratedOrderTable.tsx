"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Check, ChevronRight, Download, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import { getOrderReviewRows } from "@/lib/api";
import { getStoredSeasonTrendResult } from "@/lib/api/storage";
import { getSeasonOrderQueue, SEASON_QUEUE_CHANGE_EVENT, type SeasonOrderItem } from "@/lib/season-order-queue";
import {
  chooseTransportForAvailableDays,
  effectiveLeadTimeMethods,
  type EffectiveLeadTimeMethod
} from "@/lib/lead-times";
import { useSharedLeadTimes } from "@/lib/shared-lead-times";
import { ORDER_WORKFLOW_CHANGED_EVENT, getOrderWorkflowState } from "@/lib/order-workflow";
import { readIntegratedOrderState, writeIntegratedOrderState } from "@/lib/storage/repositories/integrated-order-state";
import { cn, formatNumber } from "@/lib/utils";
import type { OrderReviewRow } from "@/types/api";

// ── Types ────────────────────────────────────────────────────────────────────

type RowStatus = "pending" | "confirmed" | "excluded";
type Filter = "all" | "pending" | "confirmed" | "excluded";
type RowSource = "order" | "season";

type IntegratedRow = {
  sku: string;
  productName: string;
  brand: string;
  abcGrade?: string;
  riskReason: string;
  priorityAction: string;
  requiredOrderQty: number;
  peakMonth: number | null;
  orderDate: Date | null;
  transportLabel: string;
  isUrgent: boolean;
  finalQty: number;
  status: RowStatus;
  source: RowSource;
};

// ── Helpers ──────────────────────────────────────────────────────────────────

const MONTH_LABELS = ["1월","2월","3월","4월","5월","6월","7월","8월","9월","10월","11월","12월"];
const monthLabel = (m: number) => MONTH_LABELS[m - 1] ?? "-";
const cleanCode = (s: string) => {
  const text = s.trim();
  return text.endsWith(".0") ? text.slice(0, -2) : text;
};

const numVal = (v: unknown): number => {
  if (typeof v === "number") return v;
  if (typeof v === "string") { const n = parseFloat(v.replace(/,/g, "")); return isFinite(n) ? n : 0; }
  return 0;
};
const strVal = (v: unknown): string => (typeof v === "string" ? v : v == null ? "" : String(v));

function isRequired(row: OrderReviewRow) {
  const a = row.priorityAction.replace(/\s+/g, "");
  return !a.includes("불필요") && !a.includes("제외") && (row.requiredOrderQty > 0 || a.includes("발주필요"));
}

function findPeakMonth(skuCode: string, rows: Array<Record<string, unknown>>): number | null {
  const code = cleanCode(skuCode);
  const totals = new Map<number, number>();
  for (const row of rows) {
    const rc = cleanCode(strVal(row["상품코드"]) || strVal(row["sku"]) || strVal(row["prod_cd"]));
    if (rc !== code) continue;
    const m = numVal(row["month"]);
    if (m < 1 || m > 12) continue;
    totals.set(m, (totals.get(m) ?? 0) + numVal(row["판매수량"]));
  }
  if (!totals.size) return null;
  let peak = 0, peakQty = 0;
  totals.forEach((q, m) => { if (q > peakQty) { peakQty = q; peak = m; } });
  return peak || null;
}

function nextPeakDate(month: number): Date {
  const today = new Date();
  const y = today.getFullYear();
  const d = new Date(y, month - 1, 1);
  return d > today ? d : new Date(y + 1, month - 1, 1);
}

function computeTransport(
  peakMonth: number,
  methods: EffectiveLeadTimeMethod[]
): { label: string; orderDate: Date } | null {
  const peakDate = nextPeakDate(peakMonth);
  const daysUntilPeak = Math.ceil((peakDate.getTime() - Date.now()) / 86_400_000);
  const chosen = chooseTransportForAvailableDays(methods, daysUntilPeak);
  if (!chosen) return null;
  return { label: chosen.label, orderDate: new Date(peakDate.getTime() - chosen.days * 86_400_000) };
}

const formatDate = (d: Date) =>
  `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;

function readIntegratedState(): {
  statusMap: Record<string, RowStatus>;
  finalQtyMap: Record<string, number>;
} {
  return readIntegratedOrderState<RowStatus>();
}

function writeIntegratedState(statusMap: Record<string, RowStatus>, finalQtyMap: Record<string, number>) {
  writeIntegratedOrderState<RowStatus>({ statusMap, finalQtyMap });
}

// ── Main Component ────────────────────────────────────────────────────────────

export function IntegratedOrderTable() {
  const { selectedEntity } = useAuthSession();
  return selectedEntity ? <EntityScopedIntegratedOrderTable key={selectedEntity} /> : null;
}

function EntityScopedIntegratedOrderTable() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [orderRows, setOrderRows] = useState<OrderReviewRow[]>([]);
  const [skuMonthly, setSkuMonthly] = useState<Array<Record<string, unknown>>>([]);
  const [seasonQueue, setSeasonQueue] = useState<SeasonOrderItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusMap, setStatusMap] = useState<Record<string, RowStatus>>(() => readIntegratedState().statusMap);
  const [finalQtyMap, setFinalQtyMap] = useState<Record<string, number>>(() => readIntegratedState().finalQtyMap);
  const [filter, setFilter] = useState<Filter>(() => (searchParams.get("status") as Filter) || "all");
  const [showDetail, setShowDetail] = useState(() => searchParams.get("detail") === "1");
  const [queuedSkus, setQueuedSkus] = useState<string[]>(() => getOrderWorkflowState().queuedSkus);
  const { methods: leadTimeMethods, values: leadTimeValues } = useSharedLeadTimes();
  const effectiveMethods = useMemo(
    () => effectiveLeadTimeMethods(leadTimeMethods, leadTimeValues),
    [leadTimeMethods, leadTimeValues]
  );
  const hasLeadTimes = leadTimeMethods.length > 0 && effectiveMethods.length === leadTimeMethods.length;

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      try {
        const [rows, seasonResult] = await Promise.all([
          getOrderReviewRows(),
          getStoredSeasonTrendResult(),
        ]);
        if (!mounted) return;
        setOrderRows(rows.filter(isRequired));
        setSkuMonthly(
          (seasonResult?.season_analysis?.countrySkuMonthly ??
            seasonResult?.season_analysis?.skuMonthly ?? []) as Array<Record<string, unknown>>
        );
        setSeasonQueue(getSeasonOrderQueue());
      } catch {
        if (mounted) setOrderRows([]);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    void load();
    return () => { mounted = false; };
  }, []);

  // 시즌 큐 변경 시 실시간 반영
  useEffect(() => {
    const handler = () => setSeasonQueue(getSeasonOrderQueue());
    window.addEventListener(SEASON_QUEUE_CHANGE_EVENT, handler);
    return () => window.removeEventListener(SEASON_QUEUE_CHANGE_EVENT, handler);
  }, []);

  useEffect(() => {
    const handler = () => setQueuedSkus(getOrderWorkflowState().queuedSkus);
    window.addEventListener(ORDER_WORKFLOW_CHANGED_EVENT, handler);
    return () => window.removeEventListener(ORDER_WORKFLOW_CHANGED_EVENT, handler);
  }, []);

  useEffect(() => {
    writeIntegratedState(statusMap, finalQtyMap);
  }, [finalQtyMap, statusMap]);

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    if (filter !== "all") params.set("status", filter);
    else params.delete("status");
    if (showDetail) params.set("detail", "1");
    else params.delete("detail");
    const next = params.toString();
    if (next !== searchParams.toString()) {
      router.replace(next ? `${pathname}?${next}` : pathname, { scroll: false });
    }
  }, [filter, pathname, router, searchParams, showDetail]);

  const integratedRows = useMemo<IntegratedRow[]>(() => {
    const today = new Date();
    const orderSkuCodes = new Set(orderRows.map(r => cleanCode(r.sku)));

    // 발주 검토 rows
    const fromOrder: IntegratedRow[] = orderRows.map(row => {
      const peakMonth = skuMonthly.length > 0 ? findPeakMonth(row.sku, skuMonthly) : null;
      const transport = peakMonth && hasLeadTimes ? computeTransport(peakMonth, effectiveMethods) : null;
      return {
        sku: row.sku,
        productName: row.productName,
        brand: row.brand,
        abcGrade: row.abcGrade ?? undefined,
        riskReason: row.riskReason,
        priorityAction: row.priorityAction,
        requiredOrderQty: row.requiredOrderQty,
        peakMonth,
        orderDate: transport?.orderDate ?? null,
        transportLabel: transport?.label ?? "-",
        isUrgent: transport ? transport.orderDate <= today : false,
        finalQty: finalQtyMap[row.sku] ?? row.requiredOrderQty,
        status: (statusMap[row.sku] ?? "pending") as RowStatus,
        source: "order" as RowSource,
      };
    });

    // 시즌 큐 rows (발주 검토에 없는 SKU만)
    const fromSeason: IntegratedRow[] = seasonQueue
      .filter(item => !orderSkuCodes.has(cleanCode(item.sku)))
      .map(item => {
        const transport = hasLeadTimes ? computeTransport(item.peakMonth, effectiveMethods) : null;
        return {
          sku: item.sku,
          productName: item.productName,
          brand: item.brand,
          riskReason: "시즌 수요 신호",
          priorityAction: "시즌 신호",
          requiredOrderQty: 0,
          peakMonth: item.peakMonth,
          orderDate: transport?.orderDate ?? null,
          transportLabel: transport?.label ?? "-",
          isUrgent: transport ? transport.orderDate <= today : false,
          finalQty: finalQtyMap[item.sku] ?? 0,
          status: (statusMap[item.sku] ?? "pending") as RowStatus,
          source: "season" as RowSource,
        };
      });

    return [...fromOrder, ...fromSeason].sort((a, b) => {
      const aQueued = queuedSkus.includes(a.sku);
      const bQueued = queuedSkus.includes(b.sku);
      if (aQueued !== bQueued) return aQueued ? -1 : 1;
      if (a.isUrgent !== b.isUrgent) return a.isUrgent ? -1 : 1;
      return b.requiredOrderQty - a.requiredOrderQty;
    });
  }, [orderRows, skuMonthly, seasonQueue, effectiveMethods, hasLeadTimes, statusMap, finalQtyMap, queuedSkus]);

  const hasSeasonData = skuMonthly.length > 0;

  const counts = useMemo(() => ({
    pending: integratedRows.filter(r => r.status === "pending").length,
    confirmed: integratedRows.filter(r => r.status === "confirmed").length,
    excluded: integratedRows.filter(r => r.status === "excluded").length,
    urgent: integratedRows.filter(r => r.status === "pending" && r.isUrgent).length,
  }), [integratedRows]);

  const filtered = useMemo(
    () => {
      const base = searchParams.get("queue") === "1" ? integratedRows.filter((row) => queuedSkus.includes(row.sku)) : integratedRows;
      return filter === "all" ? base : base.filter(r => r.status === filter);
    },
    [integratedRows, filter, queuedSkus, searchParams]
  );

  const setStatus = (sku: string, s: RowStatus) => setStatusMap(p => ({ ...p, [sku]: s }));
  const setFinalQty = (sku: string, q: number) => setFinalQtyMap(p => ({ ...p, [sku]: q }));

  const handleExport = () => {
    const confirmed = integratedRows.filter(r => r.status === "confirmed");
    const csv = [
      ["SKU", "상품명", "브랜드", "구분", "최종수량", "피크월", "권장발주일", "운송수단"].join(","),
      ...confirmed.map(r => [
        r.sku,
        `"${r.productName}"`,
        `"${r.brand}"`,
        r.source === "season" ? "시즌신호" : "발주검토",
        r.finalQty,
        r.peakMonth ? monthLabel(r.peakMonth) : "-",
        r.orderDate ? formatDate(r.orderDate) : "-",
        r.transportLabel,
      ].join(","))
    ].join("\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "integrated-order.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <Card className="border-slate-200">
        <CardContent className="flex h-40 items-center justify-center">
          <p className="text-sm text-slate-500">발주 데이터를 불러오는 중...</p>
        </CardContent>
      </Card>
    );
  }

  if (integratedRows.length === 0) {
    return (
      <Card className="border-slate-200">
        <CardContent className="flex h-40 flex-col items-center justify-center gap-2">
          <p className="text-sm font-semibold text-slate-600">발주가 필요한 SKU가 없습니다.</p>
          <p className="text-xs text-slate-400">발주 분석을 실행하거나 시즌 트렌드에서 SKU를 추가해 주세요.</p>
        </CardContent>
      </Card>
    );
  }

  const FILTER_LABELS: Record<Filter, string> = {
    all: "전체", pending: "검토 중", confirmed: "확정됨", excluded: "제외됨",
  };

  return (
    <Card className="border-slate-200">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>발주 대상 SKU</CardTitle>
            <p className="mt-1 text-sm text-slate-500">수량을 수정한 뒤 확정하거나 제외합니다.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {counts.urgent > 0 && (
              <Badge className="border-red-200 bg-red-50 text-red-700">긴급 {counts.urgent}건</Badge>
            )}
            <Badge variant={hasSeasonData ? "success" : "slate"}>
              시즌 데이터 {hasSeasonData ? "연결됨" : "없음"}
            </Badge>
            {seasonQueue.length > 0 && (
              <Badge className="border-blue-200 bg-blue-50 text-blue-700">
                시즌 추가 {seasonQueue.length}개
              </Badge>
            )}
            {queuedSkus.length > 0 && (
              <Badge className="border-slate-200 bg-slate-100 text-slate-700">
                발주 검토 목록 {queuedSkus.length}개
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {/* 요약 */}
        <div className="mb-5 grid gap-3 sm:grid-cols-4">
          {[
            { label: "전체", value: integratedRows.length, highlight: false },
            { label: "검토 중", value: counts.pending, highlight: false },
            { label: "확정됨", value: counts.confirmed, highlight: true },
            { label: "제외됨", value: counts.excluded, highlight: false },
          ].map(({ label, value, highlight }) => (
            <div key={label} className={cn(
              "rounded-lg border px-4 py-3",
              highlight ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-slate-50"
            )}>
              <p className={cn("text-xs font-semibold", highlight ? "text-emerald-700" : "text-slate-500")}>{label}</p>
              <p className={cn("mt-1 text-2xl font-black", highlight ? "text-emerald-900" : "text-slate-950")}>
                {formatNumber(value)}
              </p>
            </div>
          ))}
        </div>

        {/* 필터 + 내보내기 */}
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex gap-1">
            {(["all", "pending", "confirmed", "excluded"] as Filter[]).map(f => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-semibold transition",
                  filter === f ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                )}
              >
                {FILTER_LABELS[f]}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowDetail(v => !v)}
              className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-600 transition hover:bg-slate-50"
            >
              <ChevronRight className={cn("h-4 w-4 transition-transform", showDetail && "rotate-90")} />
              {showDetail ? "간략히 보기" : "상세 컬럼 보기"}
            </button>
            {counts.confirmed > 0 && (
              <Button type="button" size="sm" variant="secondary" onClick={handleExport}>
                <Download className="h-4 w-4" />
                확정 목록 내보내기
              </Button>
            )}
          </div>
        </div>

        {/* 테이블 */}
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full text-sm" style={{ minWidth: showDetail ? 1080 : 680 }}>
            <thead className="sticky top-0 z-10 bg-slate-50 text-slate-600 shadow-sm">
              <tr>
                <th className="px-4 py-3 text-left">SKU</th>
                <th className="px-4 py-3 text-left">상품명</th>
                {showDetail && <th className="px-4 py-3 text-left">근거</th>}
                {showDetail && <th className="px-4 py-3 text-right">현재 필요수량</th>}
                {showDetail && <th className="px-4 py-3 text-center">피크월</th>}
                <th className="px-4 py-3 text-center">권장 발주일</th>
                {showDetail && <th className="px-4 py-3 text-center">운송</th>}
                <th className="px-4 py-3 text-right">최종 수량</th>
                <th className="min-w-[140px] px-4 py-3 text-center">결정</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(row => (
                <tr
                  key={row.sku}
                  className={cn(
                    "border-t border-slate-100 transition-colors",
                    row.source === "season" && row.status === "pending" && "bg-blue-50/30",
                    row.status === "confirmed" && "bg-emerald-50/50",
                    row.status === "excluded" && "opacity-40"
                  )}
                >
                  {/* SKU */}
                  <td className="whitespace-nowrap px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-900">{row.sku}</span>
                      {row.abcGrade && (
                        <span className={cn(
                          "rounded px-1.5 py-0.5 text-xs font-black",
                          row.abcGrade === "A" ? "bg-red-50 text-red-700" :
                          row.abcGrade === "B" ? "bg-yellow-50 text-yellow-700" :
                          "bg-slate-100 text-slate-600"
                        )}>
                          {row.abcGrade}
                        </span>
                      )}
                      {row.source === "season" && (
                        <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs font-black text-blue-700">
                          시즌
                        </span>
                      )}
                      {queuedSkus.includes(row.sku) && (
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-black text-slate-700">
                          큐
                        </span>
                      )}
                    </div>
                  </td>
                  {/* 상품명 */}
                  <td className="max-w-[200px] truncate px-4 py-3 text-slate-700" title={row.productName}>
                    {row.productName}
                  </td>
                  {/* 근거 (상세 모드) */}
                  {showDetail && (
                    <td className="max-w-[160px] truncate px-4 py-3 text-xs text-slate-500" title={row.riskReason || row.priorityAction}>
                      {row.riskReason || row.priorityAction || "-"}
                    </td>
                  )}
                  {/* 현재 필요수량 (상세 모드) */}
                  {showDetail && (
                    <td className="whitespace-nowrap px-4 py-3 text-right font-semibold text-slate-900">
                      {row.requiredOrderQty > 0 ? formatNumber(row.requiredOrderQty) : <span className="text-slate-300">-</span>}
                    </td>
                  )}
                  {/* 피크월 (상세 모드) */}
                  {showDetail && (
                    <td className="whitespace-nowrap px-4 py-3 text-center">
                      {row.peakMonth ? (
                        <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-bold text-blue-700">
                          {monthLabel(row.peakMonth)}
                        </span>
                      ) : <span className="text-slate-300">-</span>}
                    </td>
                  )}
                  {/* 권장 발주일 */}
                  <td className="whitespace-nowrap px-4 py-3 text-center">
                    {row.orderDate ? (
                      <span className={cn(
                        "rounded-full px-2.5 py-1 text-xs font-bold",
                        row.isUrgent ? "bg-red-50 text-red-700" : "bg-slate-100 text-slate-700"
                      )}>
                        {row.isUrgent ? "⚠ " : ""}{formatDate(row.orderDate)}
                      </span>
                    ) : <span className="text-slate-300">-</span>}
                  </td>
                  {/* 운송 (상세 모드) */}
                  {showDetail && (
                    <td className="whitespace-nowrap px-4 py-3 text-center text-slate-600">
                      {row.transportLabel}
                    </td>
                  )}
                  {/* 최종 수량 */}
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <input
                      type="number"
                      min={0}
                      value={row.finalQty}
                      onChange={e => {
                        const v = Number(e.target.value);
                        setFinalQty(row.sku, isFinite(v) && v >= 0 ? v : row.requiredOrderQty);
                      }}
                      disabled={row.status === "excluded"}
                      className="h-8 w-24 rounded-md border border-slate-200 bg-white px-2 text-right text-sm font-semibold text-slate-900 outline-none transition focus:border-slate-400 disabled:opacity-40"
                    />
                  </td>
                  {/* 결정 */}
                  <td className="whitespace-nowrap px-4 py-3">
                    <div className="flex items-center justify-center gap-1.5">
                      {row.status === "confirmed" ? (
                        <button
                          type="button"
                          title="클릭하면 검토 중으로 되돌아갑니다"
                          onClick={() => setStatus(row.sku, "pending")}
                          className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2.5 py-1.5 text-xs font-bold text-white hover:bg-emerald-700"
                        >
                          <Check className="h-3 w-3" />확정됨
                        </button>
                      ) : row.status === "excluded" ? (
                        <button
                          type="button"
                          title="클릭하면 검토 중으로 되돌아갑니다"
                          onClick={() => setStatus(row.sku, "pending")}
                          className="inline-flex items-center gap-1 rounded-md bg-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-300"
                        >
                          <X className="h-3 w-3" />제외됨
                        </button>
                      ) : (
                        <>
                          <button
                            type="button"
                            onClick={() => setStatus(row.sku, "confirmed")}
                            className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs font-bold text-emerald-700 transition hover:bg-emerald-100"
                          >
                            <Check className="h-3 w-3" />확정
                          </button>
                          <button
                            type="button"
                            onClick={() => setStatus(row.sku, "excluded")}
                            className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2.5 py-1.5 text-xs font-bold text-slate-500 transition hover:bg-slate-50"
                          >
                            <X className="h-3 w-3" />제외
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={showDetail ? 9 : 5} className="px-4 py-10 text-center text-slate-400">
                    해당 상태의 SKU가 없습니다.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
