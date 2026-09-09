"use client";

import { ChevronRight, PanelRightClose } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { chartColors } from "@/lib/chart-tokens";
import { monthLabel, type SkuRow } from "@/lib/global-demand-view-model";
import { cn, formatNumber } from "@/lib/utils";
import {
  UNCATEGORIZED,
  buildChartPoints,
  compactNumber,
  formatYoy,
  yoyToneClass,
  type CoverageStats,
  type IngredientLensRow,
  type IngredientSort
} from "./GlobalDemandViewModel";
import { KpiCard, MiniSparkline } from "./GlobalDemandShared";

function CoverageBanner({ coverage }: { coverage: CoverageStats }) {
  const analyzedWidth = coverage.totalSkuCount > 0 ? (coverage.matchedSkuCount / coverage.totalSkuCount) * 100 : 0;
  return (
    <Card className="rounded-lg border-line bg-white shadow-sm">
      <CardContent className="grid gap-5 p-5 lg:grid-cols-[1fr_420px_180px] lg:items-center">
        <div>
          <p className="text-lg font-black text-ink">성분 분석 커버리지 {formatNumber(coverage.coveragePct, 0)}%</p>
          <p className="mt-2 text-sm font-semibold leading-6 text-slate-600">
            대표 성분 기준에 매칭된 SKU만 집계됩니다. 색조 등 기능성 성분 기준이 불명확한 미분류{" "}
            <span className="font-black text-ink">{formatNumber(coverage.unmatchedSkuCount)}건</span>은 제외
          </p>
        </div>
        <div>
          <div className="h-4 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-brand" style={{ width: `${Math.min(100, analyzedWidth)}%` }} />
          </div>
          <div className="mt-2 flex justify-between text-sm font-black text-slate-500">
            <span>분석됨 {formatNumber(coverage.matchedSkuCount)}건</span>
            <span>미분류 {formatNumber(coverage.unmatchedSkuCount)}건</span>
          </div>
        </div>
        <a
          href="/season-trend/mapping-check"
          className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-line bg-white px-5 text-sm font-semibold text-black transition-colors hover:border-brand hover:bg-white hover:text-brand"
        >
          데이터 진단
          <ChevronRight className="h-4 w-4" />
        </a>
      </CardContent>
    </Card>
  );
}

function IngredientSeasonality({ rows }: { rows: IngredientLensRow[] }) {
  return (
    <Card className="rounded-lg border-line bg-white shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg font-black">성분 시즌성</CardTitle>
        <p className="text-sm font-semibold text-slate-500">성분별 피크월 · 발주 타이밍 참고</p>
      </CardHeader>
      <CardContent className="space-y-4 p-5 pt-0">
        {rows.slice(0, 4).map((row) => (
          <div key={row.name} className="grid grid-cols-[120px_1fr_46px] items-center gap-4">
            <p className="truncate text-sm font-black text-ink" title={row.name}>
              {row.name}
            </p>
            <MiniSparkline values={row.months} observedOnly peakMonth={row.peakMonth} />
            <p className="text-right text-sm font-black text-brand">{monthLabel(row.peakMonth)}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function AutoInsight({ country, row }: { country: string; row?: IngredientLensRow }) {
  if (!row) {
    return (
      <Card className="rounded-lg border-line bg-white shadow-sm">
        <CardContent className="p-5 text-sm font-semibold text-slate-500">AUTO INSIGHT를 생성할 성분 데이터가 없습니다.</CardContent>
      </Card>
    );
  }
  return (
    <Card className="rounded-lg border-line bg-white shadow-sm">
      <CardContent className="p-5">
        <p className="text-sm font-black uppercase tracking-[0.12em] text-brand">AUTO INSIGHT</p>
        <p className="mt-4 text-lg font-semibold leading-8 text-ink">
          {country}에서 가장 강한 성분은 <span className="font-black">{row.name}</span>
          (판매 {formatNumber(row.share, 1)}%, {formatNumber(row.skuCount)} SKU)이며 {monthLabel(row.peakMonth)} 수요가 집중됩니다.{" "}
          {row.helper} 수요가 시즌을 주도합니다.
        </p>
      </CardContent>
    </Card>
  );
}

function IngredientRankingTable({
  country,
  rows,
  sort,
  coverage,
  onSort,
  onDetail
}: {
  country: string;
  rows: IngredientLensRow[];
  sort: IngredientSort;
  coverage: CoverageStats;
  onSort: (sort: IngredientSort) => void;
  onDetail: (name: string) => void;
}) {
  const maxQty = Math.max(...rows.map((row) => row.qty), 1);
  return (
    <Card className="rounded-lg border-line bg-white shadow-sm">
      <CardHeader className="flex flex-row items-start justify-between gap-4 pb-3">
        <div>
          <CardTitle className="text-xl font-black">{country} 내 TOP 성분</CardTitle>
          <p className="mt-1 text-sm font-semibold text-slate-500">판매수량 기준 · 성분을 클릭하면 우측에 상세가 열립니다</p>
        </div>
        <Select value={sort} onChange={(event) => onSort(event.target.value as IngredientSort)} wrapperClassName="w-44 shrink-0">
          <option value="qty">정렬: 판매수량</option>
          <option value="share">정렬: 비중</option>
          <option value="sku">정렬: SKU수</option>
        </Select>
      </CardHeader>
      <CardContent className="p-5 pt-0">
        <div className="grid grid-cols-[54px_2fr_1.5fr_120px_96px_90px_28px] gap-4 border-b border-line py-3 text-sm font-black text-slate-400">
          <div>#</div>
          <div>성분</div>
          <div>판매 비중</div>
          <div className="text-right">판매수량</div>
          <div className="text-right">YoY</div>
          <div className="text-right">SKU수</div>
          <div />
        </div>
        <div>
          {rows.map((row, index) => (
            <button
              key={row.name}
              type="button"
              onClick={() => onDetail(row.name)}
              className="grid w-full grid-cols-[54px_2fr_1.5fr_120px_96px_90px_28px] items-center gap-4 border-b border-line py-4 text-left transition hover:bg-slate-25"
            >
              <div className="text-base font-black text-ink">{index + 1}</div>
              <div className="min-w-0">
                <p className="truncate text-base font-black text-ink">{row.name}</p>
                <p className="mt-1 truncate text-sm font-semibold text-slate-400">{row.helper}</p>
              </div>
              <div className="flex items-center gap-4">
                <div className="h-3 w-full rounded-full bg-slate-100">
                  <div className="h-3 rounded-full bg-brand" style={{ width: `${Math.max(4, (row.qty / maxQty) * 100)}%` }} />
                </div>
                <span className="w-16 text-right text-base font-black tabular-nums text-ink">{formatNumber(row.share, 1)}%</span>
              </div>
              <div className="text-right text-base font-black tabular-nums text-ink">{compactNumber(row.qty)}</div>
              <div className={cn("text-right text-base font-black tabular-nums", yoyToneClass(row.yoy))}>{formatYoy(row.yoy)}</div>
              <div className="text-right text-base font-semibold tabular-nums text-slate-600">{formatNumber(row.skuCount)}</div>
              <ChevronRight className="h-5 w-5 text-slate-300" />
            </button>
          ))}
          <div className="grid grid-cols-[54px_2fr_1.5fr_120px_96px_90px_28px] items-center gap-4 border-b border-line py-5 opacity-65">
            <div className="text-base font-black text-slate-400">-</div>
            <div>
              <p className="text-base font-black text-slate-500">{UNCATEGORIZED}</p>
              <p className="mt-1 text-sm font-semibold text-slate-400">색조 등 성분 기준 불명확</p>
            </div>
            <div className="flex items-center gap-4">
              <div className="h-3 w-full rounded-full bg-slate-100">
                <div className="h-3 rounded-full bg-slate-300" style={{ width: "38%" }} />
              </div>
              <span className="w-16 text-right text-base font-black text-slate-500">-</span>
            </div>
            <div className="text-right text-base font-black text-slate-500">-</div>
            <div className="text-right text-base font-black text-slate-400">-</div>
            <div className="text-right text-base font-semibold tabular-nums text-slate-600">{formatNumber(coverage.unmatchedSkuCount)}</div>
            <div />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function IngredientDetailDrawer({
  row,
  country,
  representativeSkus,
  onClose
}: {
  row: IngredientLensRow;
  country: string;
  representativeSkus: SkuRow[];
  onClose: () => void;
}) {
  return (
    <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-2xl border-l border-line bg-white shadow-2xl">
      <div className="flex items-start justify-between gap-4 border-b border-line p-5">
        <div className="min-w-0">
          <p className="text-xs font-black uppercase tracking-[0.16em] text-slate-400">{country} Ingredient</p>
          <h3 className="mt-1 truncate text-2xl font-black text-ink">{row.name}</h3>
          <p className="mt-1 truncate text-sm font-semibold text-slate-500">{row.helper}</p>
        </div>
        <button type="button" onClick={onClose} className="rounded-full p-2 text-slate-500 hover:bg-slate-100 hover:text-ink">
          <PanelRightClose className="h-5 w-5" />
        </button>
      </div>
      <div className="space-y-5 overflow-y-auto p-5">
        <div className="grid grid-cols-2 gap-3">
          <KpiCard label="판매수량" value={compactNumber(row.qty)} detail="선택 국가 합계" />
          <KpiCard label="SKU수" value={`${formatNumber(row.skuCount)}개`} detail="대표 성분 매칭" accent={chartColors.black} />
          <KpiCard label="피크월" value={monthLabel(row.peakMonth)} detail="발주 타이밍 참고" />
          <KpiCard label="YoY" value={formatYoy(row.yoy)} detail={row.yoy.status === "none" ? "전년 동월 데이터 필요" : "전년 동월 매출 기준"} accent={chartColors.slateMuted} />
        </div>
        <Card className="rounded-lg border-line">
          <CardHeader className="pb-3">
            <CardTitle>월별 판매 추이</CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={buildChartPoints(row.months)} margin={{ top: 8, right: 14, bottom: 8, left: 0 }}>
                <CartesianGrid vertical={false} stroke={chartColors.line} />
                <XAxis dataKey="month" tick={{ fontSize: 12, fontWeight: 700 }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={(value) => compactNumber(Number(value))} width={64} axisLine={false} tickLine={false} />
                <Tooltip formatter={(value) => formatNumber(Number(value))} />
                <Line type="monotone" dataKey="value" stroke={chartColors.brand} strokeWidth={3} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card className="rounded-lg border-line">
          <CardHeader className="pb-3">
            <CardTitle>대표 SKU</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {representativeSkus.slice(0, 10).map((sku) => (
              <div key={sku.code} className="flex items-start justify-between gap-4 rounded-lg border border-line px-4 py-3">
                <div className="min-w-0">
                  <p className="font-black text-ink">{sku.code}</p>
                  <p className="mt-1 truncate text-sm font-semibold text-slate-500">{sku.name}</p>
                </div>
                <p className="shrink-0 font-black tabular-nums text-ink">{compactNumber(sku.qty)}</p>
              </div>
            ))}
            {representativeSkus.length === 0 ? <p className="text-sm font-semibold text-slate-500">대표 SKU 데이터가 없습니다.</p> : null}
          </CardContent>
        </Card>
      </div>
    </aside>
  );
}

function IngredientLensView({
  country,
  rows,
  sort,
  coverage,
  selectedRow,
  representativeSkus,
  onSort,
  onDetail,
  onCloseDetail
}: {
  country: string;
  rows: IngredientLensRow[];
  sort: IngredientSort;
  coverage: CoverageStats;
  selectedRow?: IngredientLensRow;
  representativeSkus: SkuRow[];
  onSort: (sort: IngredientSort) => void;
  onDetail: (name: string) => void;
  onCloseDetail: () => void;
}) {
  return (
    <>
      <CoverageBanner coverage={coverage} />
      <section className="grid gap-5 xl:grid-cols-[1.55fr_1fr]">
        <IngredientRankingTable country={country} rows={rows} sort={sort} coverage={coverage} onSort={onSort} onDetail={onDetail} />
        <div className="space-y-5">
          <IngredientSeasonality rows={rows} />
          <AutoInsight country={country} row={rows[0]} />
        </div>
      </section>
      {selectedRow ? (
        <IngredientDetailDrawer row={selectedRow} country={country} representativeSkus={representativeSkus} onClose={onCloseDetail} />
      ) : null}
    </>
  );
}

export { IngredientLensView };


