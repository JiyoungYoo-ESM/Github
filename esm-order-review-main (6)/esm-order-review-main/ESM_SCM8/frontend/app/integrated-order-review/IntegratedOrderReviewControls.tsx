"use client";

import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuthSession } from "@/components/auth/AuthSessionContext";
import { getOrderReviewRows } from "@/lib/api";
import { useSharedLeadTimes } from "@/lib/shared-lead-times";
import { formatNumber } from "@/lib/utils";
import type { OrderReviewRow } from "@/types/api";

const DEFAULT_LEAD_DAYS = 90;

function isOrderRequired(row: OrderReviewRow | undefined) {
  if (!row) {
    return false;
  }
  const action = row.priorityAction.replace(/\s+/g, "");
  const explicitlyNotRequired = action.includes("불필요") || action.includes("제외");
  if (explicitlyNotRequired) {
    return false;
  }
  return row.requiredOrderQty > 0 || row.requiredOrderAmount > 0 || action.includes("발주필요");
}

export function IntegratedOrderReviewControls() {
  const { selectedEntity } = useAuthSession();
  return selectedEntity ? <EntityScopedIntegratedOrderReviewControls key={selectedEntity} /> : null;
}

function EntityScopedIntegratedOrderReviewControls() {
  const [orderReviewRows, setOrderReviewRows] = useState<OrderReviewRow[]>([]);
  const [isConnectingOrderReview, setIsConnectingOrderReview] = useState(false);
  const [orderReviewMessage, setOrderReviewMessage] = useState("");
  const [leadDays, setLeadDays] = useState(DEFAULT_LEAD_DAYS);
  const {
    methods: leadTimeMethods,
    values: leadTimeValues,
    loading: leadTimeLoading,
    error: leadTimeError,
    setLeadTime
  } = useSharedLeadTimes();

  const requiredOrderRows = useMemo(() => orderReviewRows.filter(isOrderRequired), [orderReviewRows]);
  const leadMonths = Math.max(1, Math.round(leadDays / 30));

  useEffect(() => {
    let isMounted = true;
    getOrderReviewRows()
      .then((rows) => {
        if (isMounted) {
          setOrderReviewRows(rows);
        }
      })
      .catch(() => {
        if (isMounted) {
          setOrderReviewRows([]);
        }
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const handleConnectOrderReview = async () => {
    setIsConnectingOrderReview(true);
    setOrderReviewMessage("저장된 발주검토 결과를 통합 발주 검토와 연결하는 중입니다.");
    try {
      const rows = await getOrderReviewRows({ includeLatestFallback: true });
      const requiredRows = rows.filter(isOrderRequired);
      setOrderReviewRows(rows);
      setOrderReviewMessage(
        rows.length > 0
          ? `발주검토 연결 완료: 발주필요 ${formatNumber(requiredRows.length)}개 SKU를 시즌 수요 패턴과 비교합니다.`
          : "저장된 발주검토 결과가 없습니다. 발주 분석 화면에서 분석 시작을 먼저 실행해 주세요."
      );
    } catch (caught) {
      setOrderReviewRows([]);
      const message = caught instanceof Error ? caught.message : "";
      setOrderReviewMessage(
        message.includes("Failed to fetch")
          ? "발주검토 결과 서버와 연결되지 않았습니다. 백엔드 실행 상태를 확인해 주세요."
          : `발주검토 결과를 연결하지 못했습니다.${message ? ` ${message}` : ""}`
      );
    } finally {
      setIsConnectingOrderReview(false);
    }
  };

  return (
    <section className="rounded-lg border border-line bg-white px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold">시즌 발주 검토</h2>
          <p className="mt-1 text-sm text-slate-500">
            월별 판매 패턴을 보고, 발주검토 산출물과 연결해 현재 발주필요 SKU의 권장 수량과 발주월을 확인합니다.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={orderReviewRows.length > 0 ? "success" : "slate"}>
            {orderReviewRows.length > 0 ? `발주필요 ${formatNumber(requiredOrderRows.length)}개 비교` : "발주 검토 미연결"}
          </Badge>
          <Button type="button" size="sm" onClick={handleConnectOrderReview} disabled={isConnectingOrderReview}>
            {isConnectingOrderReview ? "연결 중..." : orderReviewRows.length > 0 ? "발주검토 다시 연결" : "발주검토 연결하기"}
          </Button>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label htmlFor="integrated-season-lead-days" className="text-sm font-semibold text-slate-700">
          피크 전 발주 준비기간(일)
        </label>
        <input
          id="integrated-season-lead-days"
          type="number"
          min={15}
          max={365}
          step={15}
          value={leadDays}
          onChange={(event) => {
            const next = Number(event.target.value);
            setLeadDays(Number.isFinite(next) && next > 0 ? Math.min(next, 365) : DEFAULT_LEAD_DAYS);
          }}
          className="h-9 w-24 rounded-md border border-line px-3 text-sm font-semibold text-slate-900"
        />
        <span className="text-sm text-slate-500">
          피크 시즌보다 약 {leadMonths}개월 앞서 발주하도록 권장 발주월을 계산합니다.
        </span>
      </div>
      {orderReviewMessage ? (
        <p className={`mt-3 text-sm ${orderReviewRows.length > 0 ? "text-emerald-700" : "text-slate-500"}`}>
          {orderReviewMessage}
        </p>
      ) : null}

      <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
        <div>
          <h3 className="text-sm font-bold text-slate-950">운송 리드타임</h3>
          <p className="mt-1 text-xs text-slate-500">
            선택한 법인이 지원하는 운송수단만 표시하며, 최종 발주 시점 판단에 사용합니다.
          </p>
        </div>
        {leadTimeLoading ? (
          <p className="mt-4 text-sm font-semibold text-slate-500">법인별 운송 리드타임을 불러오는 중입니다.</p>
        ) : leadTimeError ? (
          <p className="mt-4 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
            {leadTimeError}
          </p>
        ) : leadTimeMethods.length === 0 ? (
          <p className="mt-4 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-600">
            본사는 해외 운송 리드타임을 적용하지 않습니다.
          </p>
        ) : (
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {leadTimeMethods.map((method) => (
              <label key={method.code}>
                <span className="text-sm font-semibold text-slate-700">{method.label} L/T(일)</span>
                <input
                  className="mt-2 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-800 outline-none focus:border-slate-950"
                  value={leadTimeValues[method.code] ?? ""}
                  onChange={(event) => setLeadTime(method.code, event.target.value)}
                  inputMode="numeric"
                  type="number"
                  min={1}
                  max={365}
                />
                <span className="mt-1 block text-xs font-semibold text-slate-500">
                  법인 기본값 {method.lead_time_days}일
                </span>
              </label>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
