"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowRight, BarChart3, CheckCircle2, PackageSearch, Upload } from "lucide-react";
import { AnalysisRequiredState } from "@/components/analysis/AnalysisRequiredState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getDashboardData } from "@/lib/api";
import { displayBrandName } from "@/lib/brand-display";
import { routes } from "@/lib/routes";
import { cn, formatNumber } from "@/lib/utils";
import type { DashboardKpi, EtaEvent, OrderDistributionPoint, PrioritySku } from "@/types/api";
import { useUserPermissions } from "@/lib/use-user-permissions";
import { isAmountField } from "@/lib/amount-permissions";

type DashboardData = {
  kpis: DashboardKpi[];
  distribution: OrderDistributionPoint[];
  prioritySkus: PrioritySku[];
  etaEvents: EtaEvent[];
};

function KpiCard({ item }: { item: DashboardKpi }) {
  const Icon = item.tone === "red" ? AlertCircle : PackageSearch;
  const isKrw = item.unit === "KRW";
  const isExchangeRate = item.unit === "KRW/EUR";
  return (
    <Card className="border-slate-200">
      <CardContent className="flex items-center gap-4 p-5">
        <span
          className={cn(
            "grid h-11 w-11 place-items-center rounded-xl",
            item.tone === "red" ? "bg-brand-50 text-brand-700" : "bg-slate-100 text-slate-600"
          )}
        >
          {isKrw || isExchangeRate ? <span className="text-xl font-black leading-none">₩</span> : <Icon className="h-5 w-5" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-bold text-slate-500">{item.label}</p>
          <p className={cn("mt-1 font-black tabular-nums text-ink", isKrw ? "text-xl tracking-normal xl:text-[1.35rem]" : "text-2xl")}>
            {isKrw || isExchangeRate ? "₩" : ""}
            {formatNumber(item.value, isExchangeRate ? 2 : 0)}
            {!isKrw && !isExchangeRate ? <span className="ml-1 text-base text-slate-500">{item.unit}</span> : null}
            {isExchangeRate ? <span className="ml-1 text-base text-slate-500">/EUR</span> : null}
          </p>
          {item.trend ? <p className="mt-1 truncate text-xs font-semibold text-slate-400">{item.trend}</p> : null}
        </div>
      </CardContent>
    </Card>
  );
}

function PriorityQueue({ rows }: { rows: PrioritySku[] }) {
  return (
    <Card className="border-slate-200">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>우선 확인 SKU</CardTitle>
        <Link href={routes.orderAnalysis} className="inline-flex items-center gap-1 text-sm font-bold text-brand-700 hover:text-brand">
          전체 보기 <ArrowRight className="h-4 w-4" />
        </Link>
      </CardHeader>
      <CardContent className="p-0">
        {rows.length === 0 ? (
          <div className="px-6 py-10 text-center text-sm font-semibold text-slate-500">우선 확인할 SKU가 없습니다.</div>
        ) : (
          <div className="divide-y divide-line">
            {rows.map((row) => (
              <Link
                key={row.sku}
                href={`${routes.stockGap}?sku=${encodeURIComponent(row.sku)}`}
                className="grid gap-3 px-5 py-4 transition hover:bg-slate-25 md:grid-cols-[1.1fr_1.4fr_0.8fr_auto]"
              >
                <div className="min-w-0">
                  <p className="font-mono text-sm font-black text-brand-700">{row.sku}</p>
                  <p className="mt-0.5 truncate text-xs font-semibold text-slate-500">{displayBrandName(row.brand)}</p>
                  {(row.stockoutDate ?? row.gapDays) && (
                    <p className="mt-1 text-xs font-semibold text-slate-400">
                      {row.stockoutDate ? `소진 ${row.stockoutDate}` : ""}
                      {row.stockoutDate && row.earliestEtaDate ? " · " : ""}
                      {row.earliestEtaDate ? `ETA ${row.earliestEtaDate}` : ""}
                      {(row.gapDays ?? 0) > 0 ? ` · ${row.gapDays}일 공백` : ""}
                    </p>
                  )}
                </div>
                <p className="truncate text-sm font-bold text-ink">{row.productName}</p>
                <p className="text-right text-sm font-black tabular-nums text-ink">{formatNumber(row.shortageQty)}개</p>
                <span className="inline-flex h-8 items-center justify-center rounded-full bg-brand-50 px-3 text-xs font-black text-brand-700">
                  재고공백
                </span>
              </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function BrandDistribution({ rows }: { rows: OrderDistributionPoint[] }) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <Card className="border-slate-200">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>브랜드별 발주 필요 금액</CardTitle>
        <Link href={routes.orderAnalysis} className="inline-flex items-center gap-1 text-sm font-bold text-brand-700 hover:text-brand">
          전체 보기 <ArrowRight className="h-4 w-4" />
        </Link>
      </CardHeader>
      <CardContent className="space-y-4">
        {rows.length === 0 ? (
          <p className="py-8 text-center text-sm font-semibold text-slate-500">브랜드 분포 데이터가 없습니다.</p>
        ) : (
          rows.map((row) => (
            <div key={row.name} className="space-y-1.5">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="truncate font-bold text-ink">{displayBrandName(row.name)}</span>
                <span className="font-black tabular-nums text-ink">₩{formatNumber(row.value)}</span>
              </div>
              <div className="h-2 rounded-full bg-slate-100">
                <div className="h-full rounded-full bg-brand-700" style={{ width: `${Math.max((row.value / max) * 100, 3)}%` }} />
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function EtaQueue({ rows }: { rows: EtaEvent[] }) {
  return (
    <Card className="border-slate-200">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>다가오는 입고</CardTitle>
        <Link href={routes.stockGap} className="inline-flex items-center gap-1 text-sm font-bold text-brand-700 hover:text-brand">
          전체 보기 <ArrowRight className="h-4 w-4" />
        </Link>
      </CardHeader>
      <CardContent className="space-y-3">
        {rows.length === 0 ? (
          <p className="py-8 text-center text-sm font-semibold text-slate-500">입고 일정 데이터가 없습니다.</p>
        ) : (
          rows.slice(0, 6).map((row) => (
            <div key={`${row.date}-${row.mode}-${row.status}`} className="flex items-center justify-between gap-3 rounded-xl border border-line px-4 py-3">
              <div className="min-w-0">
                <p className="text-sm font-black tabular-nums text-ink">{row.date}</p>
                <p className="mt-0.5 truncate text-xs font-semibold text-slate-500">
                  {row.mode} · {formatNumber(row.skuCount)} SKU · {row.status}
                </p>
              </div>
              <span className="text-sm font-black tabular-nums text-ink">{formatNumber(row.quantity)}개</span>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

export function DashboardClient() {
  const { canViewAmountData } = useUserPermissions();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    let active = true;
    setError(false);
    setData(null);
    getDashboardData()
      .then((next) => {
        if (active) setData(next);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => load(), [load]);

  const hasData = useMemo(() => Boolean(data && (data.kpis.length > 0 || data.prioritySkus.length > 0)), [data]);

  if (error) {
    return <ErrorState title="대시보드 데이터를 불러오지 못했습니다" message="분석 결과 또는 API 연결을 확인해 주세요." onRetry={load} />;
  }

  if (!data) {
    return <LoadingState cards={6} panel={false} />;
  }

  if (!hasData) {
    return (
      <AnalysisRequiredState
        title="대시보드에 표시할 분석 결과가 없습니다."
        description="데이터 준비에서 기준값과 파일 상태를 확인한 뒤 분석을 실행하면 우선 확인 SKU와 발주 금액이 표시됩니다."
      />
    );
  }

  return (
    <div className="space-y-5">
      <section className="grid gap-4 xl:grid-cols-[1.2fr_1fr_1fr]">
        <Link href={routes.upload} className="flex items-center gap-4 rounded-2xl border border-line bg-white p-5 shadow-sm transition hover:border-slate-400 hover:bg-slate-25">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-slate-100 text-slate-700">
            <Upload className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm font-bold text-slate-500">1단계</p>
            <p className="font-black text-ink">데이터 준비 / 기준값 확인</p>
          </div>
        </Link>
        <Link href={routes.orderAnalysis} className="flex items-center gap-4 rounded-2xl border border-line bg-white p-5 shadow-sm transition hover:border-slate-400 hover:bg-slate-25">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-50 text-brand-700">
            <BarChart3 className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm font-bold text-slate-500">2단계</p>
            <p className="font-black text-ink">긴급 SKU 검토</p>
          </div>
        </Link>
        <Link href={routes.integratedOrderReview} className="flex items-center gap-4 rounded-2xl border border-line bg-white p-5 shadow-sm transition hover:border-slate-400 hover:bg-slate-25">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-50 text-emerald-700">
            <CheckCircle2 className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm font-bold text-slate-500">3단계</p>
            <p className="font-black text-ink">통합 발주 확정</p>
          </div>
        </Link>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {data.kpis.filter((item) => canViewAmountData || !isAmountField(item.label)).map((item) => (
          <KpiCard key={item.label} item={item} />
        ))}
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,0.8fr)]">
        <PriorityQueue rows={data.prioritySkus} />
        <div className="space-y-5">
          {canViewAmountData ? <BrandDistribution rows={data.distribution} /> : null}
          <EtaQueue rows={data.etaEvents} />
        </div>
      </section>
    </div>
  );
}
