"use client";

import { ArrowUpDown, ChevronRight, PanelRightClose, Search } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { chartColors } from "@/lib/chart-tokens";
import { monthLabel, type SkuRow } from "@/lib/global-demand-view-model";
import { formatNumber } from "@/lib/utils";
import {
  ALL,
  buildChartPoints,
  compactNumber,
  stockStatusVariant,
  type SkuLensRow
} from "./GlobalDemandViewModel";
import { KpiCard } from "./GlobalDemandShared";

function LegacySkuLensView({
  country,
  rows,
  query,
  brand,
  category,
  page,
  onQuery,
  onBrand,
  onCategory,
  onPage
}: {
  country: string;
  rows: SkuRow[];
  query: string;
  brand: string;
  category: string;
  page: number;
  onQuery: (value: string) => void;
  onBrand: (value: string) => void;
  onCategory: (value: string) => void;
  onPage: (value: number) => void;
}) {
  const brands = [ALL, ...Array.from(new Set(rows.map((row) => row.brand))).sort((a, b) => a.localeCompare(b, "ko"))];
  const categories = [ALL, ...Array.from(new Set(rows.map((row) => row.category1))).sort((a, b) => a.localeCompare(b, "ko"))];
  const normalized = query.trim().toLowerCase();
  const filtered = rows.filter((row) => {
    const textOk =
      !normalized ||
      row.code.toLowerCase().includes(normalized) ||
      row.name.toLowerCase().includes(normalized) ||
      row.brand.toLowerCase().includes(normalized);
    const brandOk = brand === ALL || row.brand === brand;
    const categoryOk = category === ALL || row.category1 === category;
    return textOk && brandOk && categoryOk;
  });
  const pageSize = 10;
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(Math.max(page, 1), pageCount);
  const paged = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);
  const totalQty = filtered.reduce((sum, row) => sum + row.qty, 0);

  return (
    <Card className="rounded-lg border-line bg-white shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-xl font-black">{country} SKU별</CardTitle>
        <p className="mt-1 text-sm font-semibold text-slate-500">SKU · 상품명 · 브랜드 검색과 필터로 국가 내 SKU 수요를 좁혀 봅니다</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 lg:grid-cols-[minmax(220px,1fr)_220px_220px]">
          <input
            value={query}
            onChange={(event) => onQuery(event.target.value)}
            placeholder="SKU · 상품명 · 브랜드 검색"
            className="h-11 rounded-2xl border border-line bg-white px-4 text-sm font-semibold text-ink shadow-sm outline-none focus:border-slate-400"
          />
          <Select value={brand} onChange={(event) => onBrand(event.target.value)}>
            {brands.map((item) => (
              <option key={item} value={item}>
                {item === ALL ? "전체 브랜드" : item}
              </option>
            ))}
          </Select>
          <Select value={category} onChange={(event) => onCategory(event.target.value)}>
            {categories.map((item) => (
              <option key={item} value={item}>
                {item === ALL ? "전체 대분류" : item}
              </option>
            ))}
          </Select>
        </div>
        <div className="overflow-hidden rounded-lg border border-line">
          <div className="grid grid-cols-[56px_120px_1fr_140px_110px_90px_80px_28px] gap-4 border-b border-line bg-slate-50 px-4 py-3 text-sm font-black text-slate-500">
            <div>#</div>
            <div>SKU코드</div>
            <div>상품명</div>
            <div>브랜드</div>
            <div className="text-right">판매수량</div>
            <div className="text-right">비중</div>
            <div className="text-right">피크월</div>
            <div />
          </div>
          {paged.map((row, index) => (
            <div key={row.code} className="grid grid-cols-[56px_120px_1fr_140px_110px_90px_80px_28px] items-center gap-4 border-b border-line px-4 py-4 last:border-0">
              <div className="font-black text-ink">{(safePage - 1) * pageSize + index + 1}</div>
              <div className="truncate font-mono font-black text-brand">{row.code}</div>
              <div className="truncate text-sm font-semibold text-ink">{row.name}</div>
              <div className="truncate text-sm font-semibold text-slate-500">{row.brand}</div>
              <div className="text-right font-black tabular-nums text-ink">{compactNumber(row.qty)}</div>
              <div className="text-right font-black tabular-nums text-ink">{formatNumber(totalQty > 0 ? (row.qty / totalQty) * 100 : 0, 1)}%</div>
              <div className="text-right font-black text-brand">-</div>
              <ChevronRight className="h-5 w-5 text-slate-300" />
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-semibold text-slate-500">
            총 {formatNumber(filtered.length)}건 · {safePage}/{pageCount}
          </p>
          <div className="flex gap-2">
            <Button type="button" variant="secondary" size="sm" disabled={safePage <= 1} onClick={() => onPage(safePage - 1)}>
              이전
            </Button>
            <Button type="button" variant="secondary" size="sm" disabled={safePage >= pageCount} onClick={() => onPage(safePage + 1)}>
              다음
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function SkuDetailDrawer({ row, country, onClose }: { row: SkuLensRow; country: string; onClose: () => void }) {
  const recommendedOrderMonth = ((row.peakMonth + 9 - 1) % 12) + 1;
  return (
    <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-2xl border-l border-line bg-white shadow-2xl">
      <div className="flex items-start justify-between gap-4 border-b border-line p-5">
        <div className="min-w-0">
          <p className="text-xs font-black uppercase tracking-[0.16em] text-slate-400">{country} SKU</p>
          <h3 className="mt-1 truncate text-2xl font-black text-ink">{row.code}</h3>
          <p className="mt-1 truncate text-sm font-semibold text-slate-500">{row.name}</p>
        </div>
        <button type="button" onClick={onClose} className="rounded-full p-2 text-slate-500 hover:bg-slate-100 hover:text-ink">
          <PanelRightClose className="h-5 w-5" />
        </button>
      </div>
      <div className="space-y-5 overflow-y-auto p-5">
        <div className="grid grid-cols-2 gap-3">
          <KpiCard label="판매수량" value={compactNumber(row.qty)} detail={row.brand} />
          <KpiCard label="판매비중" value={`${formatNumber(row.share, 1)}%`} detail={row.category1} accent={chartColors.black} />
          <KpiCard label="피크월" value={monthLabel(row.peakMonth)} detail="시즌 수요 집중" accent={chartColors.brand} />
          <KpiCard label="권장 발주월" value={monthLabel(recommendedOrderMonth)} detail="피크 전 준비" accent={chartColors.slateMuted} />
        </div>
        <Card className="rounded-lg border-line">
          <CardHeader className="pb-3">
            <CardTitle>월별 수요</CardTitle>
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
          <CardContent className="grid gap-3 p-5 text-sm font-semibold text-slate-600">
            <div className="flex items-center justify-between gap-4">
              <span>재고 상태</span>
              <Badge variant={stockStatusVariant(row.stockStatus)}>{row.stockStatus}</Badge>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span>대분류</span>
              <span className="font-black text-ink">{row.category1}</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span>중분류</span>
              <span className="font-black text-ink">{row.category2}</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </aside>
  );
}

function SkuLensView({
  country,
  rows,
  query,
  brand,
  category,
  page,
  selectedRow,
  onQuery,
  onBrand,
  onCategory,
  onPage,
  onDetail,
  onCloseDetail
}: {
  country: string;
  rows: SkuLensRow[];
  query: string;
  brand: string;
  category: string;
  page: number;
  selectedRow?: SkuLensRow;
  onQuery: (value: string) => void;
  onBrand: (value: string) => void;
  onCategory: (value: string) => void;
  onPage: (value: number) => void;
  onDetail: (sku: string) => void;
  onCloseDetail: () => void;
}) {
  const brands = [ALL, ...Array.from(new Set(rows.map((row) => row.brand))).sort((a, b) => a.localeCompare(b, "ko"))];
  const categories = [ALL, ...Array.from(new Set(rows.map((row) => row.category1))).sort((a, b) => a.localeCompare(b, "ko"))];
  const normalized = query.trim().toLowerCase();
  const filtered = rows.filter((row) => {
    const textOk =
      !normalized ||
      row.code.toLowerCase().includes(normalized) ||
      row.name.toLowerCase().includes(normalized) ||
      row.brand.toLowerCase().includes(normalized);
    const brandOk = brand === ALL || row.brand === brand;
    const categoryOk = category === ALL || row.category1 === category;
    return textOk && brandOk && categoryOk;
  });
  const pageSize = 10;
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(Math.max(page, 1), pageCount);
  const paged = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  return (
    <>
      <Card className="rounded-lg border-line bg-white shadow-sm">
        <CardHeader className="flex flex-col gap-4 pb-3 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <CardTitle className="text-xl font-black">{country} · SKU 판매 순위</CardTitle>
            <p className="mt-1 text-sm font-semibold text-slate-500">SKU를 클릭하면 우측에 재고·발주·CBM 상세가 열립니다</p>
          </div>
          <div className="grid gap-3 md:grid-cols-[minmax(260px,1fr)_190px_190px] xl:w-[760px]">
            <label className="relative block">
              <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                value={query}
                onChange={(event) => onQuery(event.target.value)}
                placeholder="SKU · 상품명 · 브랜드 검색"
                className="h-11 w-full rounded-lg border border-line bg-white pl-10 pr-4 text-sm font-semibold text-ink shadow-sm outline-none focus:border-slate-400"
              />
            </label>
            <Select value={brand} onChange={(event) => onBrand(event.target.value)} wrapperClassName="w-full">
              {brands.map((item) => (
                <option key={item} value={item}>
                  {item === ALL ? "브랜드 전체" : item}
                </option>
              ))}
            </Select>
            <Select value={category} onChange={(event) => onCategory(event.target.value)} wrapperClassName="w-full">
              {categories.map((item) => (
                <option key={item} value={item}>
                  {item === ALL ? "대분류 전체" : item}
                </option>
              ))}
            </Select>
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-0">
          <div className="overflow-x-auto">
            <div className="min-w-[1060px]">
              <div className="grid grid-cols-[56px_180px_2fr_150px_140px_100px_90px_120px_24px] gap-4 border-b border-line py-3 text-sm font-black text-slate-400">
                <div>#</div>
                <div>SKU</div>
                <div>상품명</div>
                <div>브랜드</div>
                <div className="flex items-center justify-end gap-1">
                  판매수량 <ArrowUpDown className="h-4 w-4" />
                </div>
                <div className="text-right">비중</div>
                <div className="text-right">피크</div>
                <div className="text-center">재고 상태</div>
                <div />
              </div>
              {paged.map((row, index) => (
                <button
                  key={row.code}
                  type="button"
                  onClick={() => onDetail(row.code)}
                  className="grid w-full grid-cols-[56px_180px_2fr_150px_140px_100px_90px_120px_24px] items-center gap-4 border-b border-line py-4 text-left transition hover:bg-slate-25"
                >
                  <div className="text-base font-black text-slate-400">{(safePage - 1) * pageSize + index + 1}</div>
                  <div className="truncate font-black tabular-nums text-brand">{row.code}</div>
                  <div className="truncate text-sm font-semibold text-ink">{row.name}</div>
                  <div className="truncate text-sm font-semibold text-slate-600">{row.brand}</div>
                  <div className="text-right text-base font-black tabular-nums text-ink">{compactNumber(row.qty)}</div>
                  <div className="text-right text-base font-black tabular-nums text-slate-600">{formatNumber(row.share, 1)}%</div>
                  <div className="text-right text-base font-black text-brand">{monthLabel(row.peakMonth)}</div>
                  <div className="text-center">
                    <Badge variant={stockStatusVariant(row.stockStatus)}>{row.stockStatus}</Badge>
                  </div>
                  <ChevronRight className="h-5 w-5 text-slate-300" />
                </button>
              ))}
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-slate-500">
              총 {formatNumber(filtered.length)}건 · {safePage}/{pageCount}
            </p>
            <div className="flex gap-2">
              <Button type="button" variant="secondary" size="sm" disabled={safePage <= 1} onClick={() => onPage(safePage - 1)}>
                이전
              </Button>
              <Button type="button" variant="secondary" size="sm" disabled={safePage >= pageCount} onClick={() => onPage(safePage + 1)}>
                다음
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
      {selectedRow ? <SkuDetailDrawer row={selectedRow} country={country} onClose={onCloseDetail} /> : null}
    </>
  );
}

export { SkuLensView };


