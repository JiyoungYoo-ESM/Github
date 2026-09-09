"use client";

import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { chartColors, chartRgb, rgba } from "@/lib/chart-tokens";
import { monthLabel, same, type SkuRow } from "@/lib/global-demand-view-model";
import { cn, formatNumber } from "@/lib/utils";
import { MONTHS, type HeatmapRow } from "./SeasonHeatmap";
import {
  calendarVisibleRows,
  compactNumber,
  currentMonth,
  type ChartPoint,
  type DonutRow,
  type IngredientLensRow
} from "./GlobalDemandViewModel";
import { KpiCard } from "./GlobalDemandShared";

function DemandLineChart({
  country,
  category,
  points,
  peakMonth,
  peakValue
}: {
  country: string;
  category: string;
  points: ChartPoint[];
  peakMonth: number;
  peakValue: number;
}) {
  const titleScope = category ? `${country} ${category}` : country;
  const title = `${titleScope} 월별 수요`;
  const chartData = points.map((point) => ({
    ...point,
    peak: point.monthNo === peakMonth ? point.value : null
  }));
  return (
    <Card className="rounded-lg border-line bg-white shadow-sm">
      <CardHeader className="flex flex-row items-start justify-between gap-4 pb-3">
        <div>
          <CardTitle className="text-xl font-black">{title}</CardTitle>
          <p className="mt-1 text-sm font-semibold text-slate-500">
            선택 범위의 과거 판매수량을 월별로 합산한 값입니다
          </p>
        </div>
        <Badge variant="default" className="shrink-0">
          피크 {monthLabel(peakMonth)}
        </Badge>
      </CardHeader>
      <CardContent className="h-[330px] p-5 pt-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 14, right: 22, bottom: 8, left: 0 }}>
            <CartesianGrid vertical={false} stroke={chartColors.line} />
            <XAxis dataKey="month" tick={{ fontSize: 12, fontWeight: 700 }} axisLine={false} tickLine={false} />
            <YAxis
              tick={{ fontSize: 12, fontWeight: 700 }}
              axisLine={false}
              tickLine={false}
              width={70}
              tickFormatter={(value) => compactNumber(Number(value))}
            />
            <Tooltip
              formatter={(value) => formatNumber(Number(value))}
              labelFormatter={(label) => `${label}`}
            />
            <Area type="monotone" dataKey="value" fill={rgba(chartRgb.brand, 0.12)} stroke="none" tooltipType="none" />
            <Line name="판매수량" type="monotone" dataKey="value" stroke={chartColors.brand} strokeWidth={3.5} dot={false} activeDot={{ r: 5 }} />
            <Line
              type="monotone"
              dataKey="peak"
              stroke={chartColors.brand}
              strokeWidth={0}
              dot={(props) => {
                const point = props as { cx?: number; cy?: number; value?: number | null };
                if (point.value == null || typeof point.cx !== "number" || typeof point.cy !== "number") return null;
                return <circle cx={point.cx} cy={point.cy} r={6} fill={chartColors.brand} stroke={chartColors.white} strokeWidth={3} />;
              }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
      <div className="px-6 pb-5 text-xs font-bold text-slate-500">
        피크값 {formatNumber(peakValue)}
      </div>
    </Card>
  );
}

function CategoryDonut({
  rows,
  selectedCategory,
  onToggle
}: {
  rows: DonutRow[];
  selectedCategory: string;
  onToggle: (category: string) => void;
}) {
  const focus = selectedCategory ? rows.find((row) => same(row.name, selectedCategory)) : rows[0];
  return (
    <Card className="rounded-lg border-line bg-white shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg font-black">대분류 비중</CardTitle>
        <p className="text-sm font-semibold text-slate-500">조각 또는 범례를 클릭하면 전체가 필터됩니다</p>
      </CardHeader>
      <CardContent className="grid gap-4 p-5 pt-0 lg:grid-cols-[210px_1fr] xl:grid-cols-1 2xl:grid-cols-[210px_1fr]">
        <div className="relative h-[210px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={rows} dataKey="value" innerRadius={62} outerRadius={92} paddingAngle={1} isAnimationActive={false}>
                {rows.map((row) => (
                  <Cell
                    key={row.name}
                    fill={row.color}
                    opacity={!selectedCategory || same(row.name, selectedCategory) ? 1 : 0.32}
                    onClick={() => row.name !== "그 외" && onToggle(row.name)}
                    className="cursor-pointer outline-none"
                  />
                ))}
              </Pie>
              <Tooltip formatter={(value) => formatNumber(Number(value))} />
            </PieChart>
          </ResponsiveContainer>
          <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
            <div>
              <p className="max-w-[110px] truncate text-sm font-black text-ink">{focus?.name ?? "-"}</p>
              <p className="text-2xl font-black tabular-nums text-ink">{formatNumber(focus?.share ?? 0, 1)}%</p>
            </div>
          </div>
        </div>
        <div className="space-y-2">
          {rows.map((row) => (
            <button
              key={row.name}
              type="button"
              disabled={row.name === "그 외"}
              onClick={() => onToggle(row.name)}
              className={cn(
                "flex w-full items-center justify-between gap-3 rounded-lg px-2 py-2 text-left transition",
                row.name === "그 외" ? "cursor-default" : "hover:bg-slate-50",
                selectedCategory && !same(row.name, selectedCategory) && "opacity-40"
              )}
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className="h-3.5 w-3.5 shrink-0 rounded-sm" style={{ backgroundColor: row.color }} />
                <span className="truncate text-sm font-black text-ink">{row.name}</span>
              </span>
              <span className="text-sm font-black tabular-nums text-ink">{formatNumber(row.share, 1)}%</span>
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function SeasonCalendar({
  title,
  rowLabel,
  rows,
  selected,
  drillLevel,
  available = true,
  onRowClick,
  onLevelChange
}: {
  title: string;
  rowLabel: string;
  rows: HeatmapRow[];
  selected: string;
  drillLevel: "category1" | "category2";
  available?: boolean;
  onRowClick: (row: string) => void;
  onLevelChange: (level: "category1" | "category2") => void;
}) {
  const maxValue = Math.max(...rows.flatMap((row) => row.months), 1);
  return (
    <Card className="rounded-lg border-line bg-white shadow-sm">
      <CardHeader className="flex flex-row items-start justify-between gap-4 pb-4">
        <div>
          <CardTitle className="text-lg font-black">{title}</CardTitle>
          <p className="mt-1 text-sm font-semibold text-slate-500">주요 {rowLabel}만 표시 · 행 클릭 → 전체 크로스필터</p>
        </div>
        <div className="inline-flex shrink-0 rounded-lg border border-line bg-slate-50 p-1">
          <button
            type="button"
            onClick={() => onLevelChange("category1")}
            disabled={!available}
            className={cn(
              "h-8 rounded-md px-3 text-sm font-black transition",
              !available && "cursor-not-allowed opacity-50",
              drillLevel === "category1" ? "bg-ink text-white shadow-sm" : "text-slate-500 hover:text-ink"
            )}
          >
            대분류
          </button>
          <button
            type="button"
            onClick={() => onLevelChange("category2")}
            disabled={!available}
            title="중분류 기준으로 봅니다"
            className={cn(
              "h-8 rounded-md px-3 text-sm font-black transition",
              !available && "cursor-not-allowed opacity-50",
              drillLevel === "category2" ? "bg-ink text-white shadow-sm" : "text-slate-500 hover:text-ink"
            )}
          >
            중분류
          </button>
        </div>
      </CardHeader>
      <CardContent className="p-5 pt-0">
        {!available ? (
          <div className="rounded-lg border border-dashed border-line bg-slate-50 py-12 text-center">
            <p className="text-base font-black text-ink">분석 조회 불가</p>
            <p className="mt-2 text-sm font-semibold text-slate-500">시즌 캘린더는 1년 이상의 판매 데이터가 있을 때 표시됩니다.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <div className="min-w-[820px]">
              <div className="grid grid-cols-[150px_repeat(12,minmax(42px,1fr))_54px] items-center gap-1.5 pb-2 text-xs font-black text-slate-400">
                <div>{rowLabel}</div>
                {MONTHS.map((month) => (
                  <div key={month} className={cn("text-center", month === currentMonth && "text-brand")}>
                    {month}
                  </div>
                ))}
                <div className="text-right">피크</div>
              </div>
              <div className="space-y-1.5">
                {rows.map((row) => {
                  const active = selected && same(row.category, selected);
                  const muted = selected && !active;
                  return (
                    <div
                      key={row.category}
                      className={cn(
                        "grid grid-cols-[150px_repeat(12,minmax(42px,1fr))_54px] items-center gap-1.5 rounded-lg py-1 transition",
                        active && "bg-red-50/70 px-1",
                        muted && "opacity-35"
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => onRowClick(row.category)}
                        className="truncate px-2 text-left text-sm font-black text-ink hover:text-brand"
                        title={row.category}
                      >
                        {row.category}
                      </button>
                      {row.months.map((value, index) => {
                        const month = index + 1;
                        const ratio = value > 0 ? value / maxValue : 0;
                        const isPeak = month === row.peakMonth;
                        return (
                          <button
                            key={month}
                            type="button"
                            onClick={() => onRowClick(row.category)}
                            title={`${row.category} ${monthLabel(month)} ${formatNumber(value)}`}
                            className={cn(
                              "h-[22px] rounded-md border transition hover:border-brand",
                              isPeak ? "border-2 border-brand" : "border-transparent",
                              value === 0 && "bg-slate-50"
                            )}
                            style={value > 0 ? { backgroundColor: rgba(chartRgb.brand, 0.08 + ratio * 0.62) } : undefined}
                            aria-label={`${row.category} ${monthLabel(month)} ${formatNumber(value)}`}
                          />
                        );
                      })}
                      <div className="text-right text-sm font-black text-brand">{monthLabel(row.peakMonth)}</div>
                    </div>
                  );
                })}
                {rows.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-line py-10 text-center text-sm font-semibold text-slate-500">
                    표시할 시즌 데이터가 없습니다.
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MonthlyLensView({
  country,
  category,
  chartPoints,
  peakMonth,
  peakValue,
  monthlyValues,
  totalQty,
  scopedSkuRows,
  scopedSkuCount,
  topIngredient,
  donutRows,
  selectedCategory,
  heatmapRows,
  heatmapSelected,
  drillLevel,
  seasonCalendarAvailable,
  onCategory1,
  onCategory2,
  onDrillLevel,
  onSkuDetail
}: {
  country: string;
  category: string;
  chartPoints: ChartPoint[];
  peakMonth: number;
  peakValue: number;
  monthlyValues: number[];
  totalQty: number;
  scopedSkuRows: SkuRow[];
  scopedSkuCount: number;
  topIngredient?: IngredientLensRow;
  donutRows: DonutRow[];
  selectedCategory: string;
  heatmapRows: HeatmapRow[];
  heatmapSelected: string;
  drillLevel: "category1" | "category2";
  seasonCalendarAvailable: boolean;
  onCategory1: (category: string) => void;
  onCategory2: (category: string) => void;
  onDrillLevel: (level: "category1" | "category2") => void;
  onSkuDetail: (sku: string) => void;
}) {
  const calendarRows = useMemo(
    () => calendarVisibleRows(heatmapRows, heatmapSelected, drillLevel),
    [drillLevel, heatmapRows, heatmapSelected]
  );
  return (
    <>
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="판매수량" value={compactNumber(totalQty)} detail={selectedCategory || "전체 대분류"} />
        <KpiCard label="피크월" value={monthLabel(peakMonth)} detail={category || "전체"} accent={chartColors.black} />
        <KpiCard label="TOP 성분" value={topIngredient?.name ?? "-"} detail={topIngredient ? `성분 매칭 내 ${formatNumber(topIngredient.share, 1)}%` : "-"} />
        <KpiCard
          label="전체 SKU 수"
          value={`${formatNumber(scopedSkuCount)}개`}
          accent={chartColors.slateMuted}
        />
      </section>
      <section className="grid gap-5 xl:grid-cols-[1.7fr_1fr]">
        <DemandLineChart country={country} category={category} points={chartPoints} peakMonth={peakMonth} peakValue={peakValue} />
        <CategoryDonut rows={donutRows} selectedCategory={selectedCategory} onToggle={onCategory1} />
      </section>
      <SeasonCalendar
        title="시즌 캘린더"
        rowLabel={drillLevel === "category2" ? "중분류" : "대분류"}
        rows={calendarRows}
        selected={heatmapSelected}
        drillLevel={drillLevel}
        available={seasonCalendarAvailable}
        onRowClick={drillLevel === "category2" ? onCategory2 : onCategory1}
        onLevelChange={onDrillLevel}
      />
    </>
  );
}

export { MonthlyLensView };

