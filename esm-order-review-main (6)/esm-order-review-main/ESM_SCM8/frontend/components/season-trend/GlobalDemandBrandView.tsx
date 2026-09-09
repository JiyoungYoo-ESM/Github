"use client";

import { ChevronRight, PanelRightClose } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { chartColors } from "@/lib/chart-tokens";
import { monthLabel } from "@/lib/global-demand-view-model";
import { formatNumber } from "@/lib/utils";
import {
  BRAND_ACCENTS,
  brandInitial,
  buildChartPoints,
  compactNumber,
  type BrandLensRow,
  type BrandSort
} from "./GlobalDemandViewModel";
import { KpiCard, MiniSparkline } from "./GlobalDemandShared";

function BrandAutoInsight({ country, rows }: { country: string; rows: BrandLensRow[] }) {
  const top = rows[0];
  if (!top) {
    return (
      <Card className="rounded-lg border-line bg-white shadow-sm">
        <CardContent className="p-5 text-sm font-semibold text-slate-500">AUTO INSIGHT를 생성할 브랜드 데이터가 없습니다.</CardContent>
      </Card>
    );
  }
  const top3Share = rows.slice(0, 3).reduce((sum, row) => sum + row.share, 0);
  return (
    <Card className="rounded-lg border-line bg-white shadow-sm">
      <CardContent className="p-5">
        <p className="text-sm font-black uppercase tracking-[0.12em] text-brand">AUTO INSIGHT</p>
        <p className="mt-4 text-lg font-semibold leading-8 text-ink">
          {country} 시장은 <span className="font-black">{top.brand}</span>가 판매의 {formatNumber(top.share, 1)}%를 차지합니다.
          상위 3개 브랜드가 전체의 {formatNumber(top3Share, 1)}%로, 브랜드 집중도를 함께 확인해야 합니다. 피크는 브랜드별로 분산되어 있어 연중 고른 발주 계획이 필요합니다.
        </p>
      </CardContent>
    </Card>
  );
}

function BrandDetailDrawer({ row, country, onClose }: { row: BrandLensRow; country: string; onClose: () => void }) {
  return (
    <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-2xl border-l border-line bg-white shadow-2xl">
      <div className="flex items-start justify-between gap-4 border-b border-line p-5">
        <div className="min-w-0">
          <p className="text-xs font-black uppercase tracking-[0.16em] text-slate-400">{country} Brand</p>
          <h3 className="mt-1 truncate text-2xl font-black text-ink">{row.brand}</h3>
          <p className="mt-1 truncate text-sm font-semibold text-slate-500">{row.topCategory} 중심</p>
        </div>
        <button type="button" onClick={onClose} className="rounded-full p-2 text-slate-500 hover:bg-slate-100 hover:text-ink">
          <PanelRightClose className="h-5 w-5" />
        </button>
      </div>
      <div className="space-y-5 overflow-y-auto p-5">
        <div className="grid grid-cols-2 gap-3">
          <KpiCard label="판매수량" value={compactNumber(row.qty)} detail="선택 국가 합계" />
          <KpiCard label="SKU 수" value={`${formatNumber(row.skuCount)}개`} detail="브랜드 보유 SKU" accent={chartColors.black} />
          <KpiCard label="피크월" value={monthLabel(row.peakMonth)} detail="브랜드 수요 집중" accent={chartColors.brand} />
          <KpiCard label="판매비중" value={`${formatNumber(row.share, 1)}%`} detail="국가 내 브랜드 비중" accent={chartColors.slateMuted} />
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
            {row.skus.slice(0, 10).map((sku) => (
              <div key={sku.code} className="flex items-start justify-between gap-4 rounded-lg border border-line px-4 py-3">
                <div className="min-w-0">
                  <p className="font-black text-ink">{sku.code}</p>
                  <p className="mt-1 truncate text-sm font-semibold text-slate-500">{sku.name}</p>
                </div>
                <p className="shrink-0 font-black tabular-nums text-ink">{compactNumber(sku.qty)}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </aside>
  );
}

function BrandLensView({
  country,
  rows,
  sort,
  selectedRow,
  onSort,
  onDetail,
  onCloseDetail
}: {
  country: string;
  rows: BrandLensRow[];
  sort: BrandSort;
  selectedRow?: BrandLensRow;
  onSort: (sort: BrandSort) => void;
  onDetail: (brand: string) => void;
  onCloseDetail: () => void;
}) {
  const sortedRows = [...rows].sort((a, b) => {
    if (sort === "sku") return b.skuCount - a.skuCount || b.qty - a.qty;
    if (sort === "share") return b.share - a.share || b.qty - a.qty;
    return b.qty - a.qty;
  });
  const maxQty = Math.max(...sortedRows.map((row) => row.qty), 1);
  return (
    <>
      <section className="grid gap-5 xl:grid-cols-[1.7fr_1fr]">
        <Card className="rounded-lg border-line bg-white shadow-sm">
          <CardHeader className="flex flex-row items-start justify-between gap-4 pb-3">
            <div>
              <CardTitle className="text-xl font-black">{country} · 브랜드 판매 순위</CardTitle>
              <p className="mt-1 text-sm font-semibold text-slate-500">브랜드를 클릭하면 우측에 상세가 열립니다</p>
            </div>
            <Select value={sort} onChange={(event) => onSort(event.target.value as BrandSort)} wrapperClassName="w-44 shrink-0">
              <option value="qty">정렬: 판매수량</option>
              <option value="share">정렬: 비중</option>
              <option value="sku">정렬: SKU 수</option>
            </Select>
          </CardHeader>
          <CardContent className="p-5 pt-0">
            <div className="grid grid-cols-[46px_1.8fr_118px_1.5fr_1fr_72px_78px_24px] gap-4 border-b border-line py-3 text-sm font-black text-slate-400">
              <div>#</div>
              <div>브랜드</div>
              <div className="text-right">판매수량</div>
              <div>비중</div>
              <div>대표 대분류</div>
              <div className="text-right">피크</div>
              <div className="text-right">SKU 수</div>
              <div />
            </div>
            {sortedRows.map((row, index) => {
              const accent = BRAND_ACCENTS[index % BRAND_ACCENTS.length];
              return (
                <button
                  key={row.brand}
                  type="button"
                  onClick={() => onDetail(row.brand)}
                  className="grid w-full grid-cols-[46px_1.8fr_118px_1.5fr_1fr_72px_78px_24px] items-center gap-4 border-b border-line py-4 text-left transition hover:bg-slate-25"
                >
                  <div className="text-base font-black text-slate-400">{index + 1}</div>
                  <div className="flex min-w-0 items-center gap-4">
                    <span
                      className="grid h-10 w-10 shrink-0 place-items-center rounded-lg text-sm font-black text-white"
                      style={{ backgroundColor: accent }}
                    >
                      {brandInitial(row.brand)}
                    </span>
                    <span className="truncate text-base font-black text-ink">{row.brand}</span>
                  </div>
                  <div className="text-right text-base font-black tabular-nums text-ink">{compactNumber(row.qty)}</div>
                  <div className="flex items-center gap-3">
                    <div className="h-2.5 flex-1 rounded-full bg-slate-100">
                      <div className="h-2.5 rounded-full bg-brand" style={{ width: `${Math.max(4, (row.qty / maxQty) * 100)}%` }} />
                    </div>
                    <span className="w-14 text-right text-base font-black tabular-nums text-ink">{formatNumber(row.share, 1)}%</span>
                  </div>
                  <div className="truncate text-sm font-semibold text-slate-600">{row.topCategory}</div>
                  <div className="text-right text-base font-black text-brand">{monthLabel(row.peakMonth)}</div>
                  <div className="text-right text-base font-semibold tabular-nums text-slate-600">{formatNumber(row.skuCount)}</div>
                  <ChevronRight className="h-5 w-5 text-slate-300" />
                </button>
              );
            })}
          </CardContent>
        </Card>
        <div className="space-y-5">
          <Card className="rounded-lg border-line bg-white shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg font-black">브랜드 시즌 분포</CardTitle>
              <p className="text-sm font-semibold text-slate-500">상위 5개 브랜드 피크월</p>
            </CardHeader>
            <CardContent className="space-y-4">
              {sortedRows.slice(0, 5).map((row, index) => (
                <div key={row.brand} className="grid grid-cols-[150px_1fr_46px] items-center gap-4">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: BRAND_ACCENTS[index % BRAND_ACCENTS.length] }} />
                    <p className="truncate text-base font-black text-ink">{row.brand}</p>
                  </div>
                  <MiniSparkline values={row.months} color={BRAND_ACCENTS[index % BRAND_ACCENTS.length]} />
                  <p className="text-right text-base font-black text-brand">{monthLabel(row.peakMonth)}</p>
                </div>
              ))}
            </CardContent>
          </Card>
          <BrandAutoInsight country={country} rows={sortedRows} />
        </div>
      </section>
      {selectedRow ? <BrandDetailDrawer row={selectedRow} country={country} onClose={onCloseDetail} /> : null}
    </>
  );
}

export { BrandLensView };


