"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronDown, Download, HelpCircle, Search } from "lucide-react";
import { AnalysisRequiredState } from "@/components/analysis/AnalysisRequiredState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getStockGapItems } from "@/lib/api";
import { displayBrandName } from "@/lib/brand-display";
import {
  buildTimelinePoints,
  computeStockGapItem,
  dayDiff,
  formatDate,
  parseDate,
  startOfDay,
  type StockGapComputedItem
} from "@/lib/stock-gap";
import {
  numberText,
  sortStockGapRiskItems,
  stockGapActionText,
  stockGapBadgeClass,
  stockGapBadgeText,
  stockGapDotClass,
  stockGapNarrative,
  stockGapStatusCounts,
  stockGapStatusMeta,
  stockoutLabel
} from "@/lib/stock-gap-view";
import { cn, formatNumber } from "@/lib/utils";

const allBrands = "전체 브랜드";

function csvCell(value: string | number | null | undefined) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function RiskSummary({ items }: { items: StockGapComputedItem[] }) {
  const counts = stockGapStatusCounts(items);

  return (
    <section className="grid gap-4 lg:grid-cols-4">
      <Card className="border-slate-200">
        <CardContent className="p-5">
          <p className="flex items-center gap-2 text-sm font-bold text-slate-500">
            <span className="h-2.5 w-2.5 rounded-full bg-brand" />
            긴급보충
          </p>
          <p className="mt-3 text-2xl font-black tabular-nums text-ink">{formatNumber(counts.urgent)}건</p>
        </CardContent>
      </Card>
      <Card className="border-slate-200">
        <CardContent className="p-5">
          <p className="flex items-center gap-2 text-sm font-bold text-slate-500">
            <span className="h-2.5 w-2.5 rounded-full bg-orange-500" />
            주의
          </p>
          <p className="mt-3 text-2xl font-black tabular-nums text-ink">{formatNumber(counts.warning)}건</p>
        </CardContent>
      </Card>
      <Card className="border-slate-200">
        <CardContent className="p-5">
          <p className="flex items-center gap-2 text-sm font-bold text-slate-500">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
            정상
          </p>
          <p className="mt-3 text-2xl font-black tabular-nums text-ink">{formatNumber(counts.normal)}건</p>
        </CardContent>
      </Card>
      <Card className="border-slate-200">
        <CardContent className="p-5">
          <p className="text-sm font-bold text-slate-500">평균 공백일</p>
          <p className="mt-3 text-2xl font-black tabular-nums text-ink">{formatNumber(counts.avgGap)}일</p>
        </CardContent>
      </Card>
    </section>
  );
}

function RiskList({
  items,
  selectedSku,
  onSelect
}: {
  items: StockGapComputedItem[];
  selectedSku: string;
  onSelect: (sku: string) => void;
}) {
  return (
    <div className="max-h-[760px] overflow-y-auto">
      {items.map((item) => {
        const active = item.sku === selectedSku;

        return (
          <button
            key={item.sku}
            type="button"
            onClick={() => onSelect(item.sku)}
            className={cn(
              "grid w-full grid-cols-[1fr_auto] gap-3 border-b border-slate-200 px-5 py-4 text-left transition hover:bg-slate-25",
              active && "border-l-4 border-l-ink bg-slate-50"
            )}
          >
            <span className="min-w-0">
              <span className="flex items-center gap-3">
                <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", stockGapDotClass(item))} />
                <span className="truncate font-mono text-sm font-black text-ink">{item.sku}</span>
              </span>
              <span className="mt-1 block truncate text-sm font-bold text-ink">{item.productName}</span>
              <span className="mt-0.5 block truncate text-xs font-semibold text-slate-500">{displayBrandName(item.brand)}</span>
            </span>
            <Badge className={cn("self-start whitespace-nowrap", stockGapBadgeClass(item))}>{stockGapBadgeText(item)}</Badge>
          </button>
        );
      })}
    </div>
  );
}

function DetailMetric({
  label,
  value,
  sub,
  emphasized,
  warning,
  danger,
  compact
}: {
  label: string;
  value: string;
  sub?: string;
  emphasized?: boolean;
  warning?: boolean;
  danger?: boolean;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-slate-200 bg-white p-4",
        danger && "border-red-100 bg-red-50",
        warning && !danger && "border-orange-100 bg-orange-50",
        emphasized && !danger && !warning && "border-slate-200 bg-slate-50"
      )}
    >
      <p className="text-xs font-bold text-slate-500">{label}</p>
      <p
        className={cn(
          "mt-2 break-keep font-black leading-tight tabular-nums text-ink",
          compact ? "text-xl" : "text-xl xl:text-2xl",
          value.match(/^\d{4}-\d{2}-\d{2}$/) && "whitespace-nowrap text-lg xl:text-xl",
          danger && "text-brand",
          warning && !danger && "text-orange-700"
        )}
      >
        {value}
      </p>
      {sub ? <p className="mt-1 text-xs font-semibold text-slate-500">{sub}</p> : null}
    </div>
  );
}

function TransportBadge({ mode }: { mode: string }) {
  return <span className="inline-flex rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-700">{mode}</span>;
}

function TimelineLegend({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap text-xs font-bold text-slate-600">
      <span className={cn("inline-block", className)} />
      {label}
    </span>
  );
}

function StockGapTimeline({ item }: { item: StockGapComputedItem }) {
  const baseDate = parseDate(item.baseDate) ?? startOfDay(new Date());
  const points = buildTimelinePoints(item).filter(
    (point) => point.kind === "today" || point.date.getTime() > baseDate.getTime()
  );
  const lastPoint = points[points.length - 1]?.date ?? baseDate;
  const totalDays = Math.max(dayDiff(baseDate, lastPoint), 1);
  const position = (date: Date) => Math.min(Math.max((dayDiff(baseDate, date) / totalDays) * 100, 0), 100);
  const stockoutLeft = item.stockoutDate ? position(item.stockoutDate) : 0;
  const etaLeft = item.earliestEtaDate ? position(item.earliestEtaDate) : 0;
  const gapWidth = item.gapDays && item.gapDays > 0 ? Math.max(etaLeft - stockoutLeft, 0) : 0;
  const plottedPoints = points.reduce<Array<(typeof points)[number] & { left: number; lane: number }>>((result, point) => {
    const left = position(point.date);
    const previousLeft = result.at(-1)?.left ?? -Infinity;
    result.push({ ...point, left, lane: left - previousLeft < 8 ? 1 : 0 });
    return result;
  }, []);

  return (
    <Card className="border-slate-200">
      <CardHeader className="flex flex-row items-center justify-between gap-4">
        <CardTitle>SKU 타임라인</CardTitle>
        <div className="flex flex-wrap justify-end gap-4">
          <TimelineLegend className="h-1 w-8 rounded-full bg-emerald-500" label="재고 버팀" />
          <TimelineLegend className="h-0 w-8 border-t-2 border-dashed border-orange-500" label="공백 구간" />
          <TimelineLegend className="h-2.5 w-2.5 rounded-full bg-orange-500" label="소진" />
          <TimelineLegend className="h-2.5 w-2.5 rounded-full bg-blue-600" label="입고" />
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto pb-2">
          <div className="relative h-44 min-w-[900px] px-8">
            <div className="absolute left-8 right-8 top-16 h-2 rounded-full bg-slate-200" />
            <div className="absolute left-8 right-8 top-16 h-2">
              <div className="h-full rounded-full bg-emerald-500" style={{ width: `${stockoutLeft}%` }} />
            </div>
            {gapWidth > 0 ? (
              <div className="absolute left-8 right-8 top-16 h-2">
                <div
                  className="h-2 border-t-2 border-dashed border-orange-500"
                  style={{ marginLeft: `${stockoutLeft}%`, width: `${gapWidth}%` }}
                />
              </div>
            ) : null}
            <div className="absolute left-8 right-8 top-0 h-full">
            {plottedPoints.map((point) => {
              const edge = point.left <= 4 ? "translate-x-0 text-left" : point.left >= 96 ? "-translate-x-full text-right" : "-translate-x-1/2 text-center";
              const dotClass =
                point.kind === "stockout"
                  ? "bg-orange-500"
                  : point.kind === "eta"
                    ? point.isEarliestEta
                      ? "bg-blue-600"
                      : "bg-slate-500"
                    : "bg-slate-400";
              const labelTop = point.lane ? 18 : 0;
              const dateTop = point.lane ? 108 : 84;

              return (
                <div key={point.key} className="absolute top-0 h-full" style={{ left: `${point.left}%` }}>
                  <p className={cn("absolute left-0 w-40 text-xs font-bold text-slate-600", edge)} style={{ top: labelTop }}>
                    {point.label}
                  </p>
                  <span className={cn("absolute left-0 top-[56px] block h-5 w-5 -translate-x-1/2 rounded-full border-4 border-white shadow-sm", dotClass)} />
                  <p className={cn("absolute left-0 w-40 text-sm font-black tabular-nums text-ink", edge)} style={{ top: dateTop }}>
                    {formatDate(point.date)}
                  </p>
                  {point.kind === "eta" ? (
                    <p className={cn("absolute left-0 w-40 text-xs font-bold tabular-nums text-slate-500", edge)} style={{ top: dateTop + 24 }}>
                      +{formatNumber(point.quantity ?? 0)}개
                    </p>
                  ) : null}
                </div>
              );
            })}
          </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function EtaTable({ item }: { item: StockGapComputedItem }) {
  return (
    <Card className="border-slate-200">
      <CardHeader>
        <CardTitle>입고 일정</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>#</TableHead>
              <TableHead>운송수단</TableHead>
              <TableHead>ETA</TableHead>
              <TableHead className="text-right">입고 예정</TableHead>
              <TableHead>출고일</TableHead>
              <TableHead>B/L 또는 컨테이너</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {item.etaItems.length > 0 ? (
              item.etaItems.map((eta, index) => (
                <TableRow key={`${eta.eta}-${eta.transportMode}`}>
                  <TableCell className="tabular-nums">{index + 1}</TableCell>
                  <TableCell>
                    <TransportBadge mode={eta.transportMode} />
                  </TableCell>
                  <TableCell className="tabular-nums">{formatDate(eta.eta)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatNumber(eta.inTransitQty)}개</TableCell>
                  <TableCell className="tabular-nums">{eta.shipmentDate || "-"}</TableCell>
                  <TableCell>{eta.referenceNo || "-"}</TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={6} className="py-10 text-center text-slate-500">
                  ETA 입고 일정이 없습니다.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function StockGapDetail({ item }: { item: StockGapComputedItem }) {
  const status = stockGapStatusMeta[item.status];
  const isRisk = item.status === "urgent_replenishment" || item.status === "stock_gap";
  const isWarning = item.status === "waiting_eta" || item.status === "stockout_no_inbound";
  const actionText = stockGapActionText(item);

  return (
    <div className="min-w-0 space-y-5">
      <Card className="border-slate-200">
        <CardContent className="p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="font-mono text-sm font-black text-brand-700">{item.sku}</p>
              <h2 className="mt-1 text-xl font-black leading-tight tracking-tight text-ink xl:text-2xl">{item.productName}</h2>
              <p className="mt-1 text-sm font-semibold text-slate-500">{displayBrandName(item.brand)}</p>
            </div>
            <Badge className={cn("gap-2", status.badge)}>
              <span className={cn("h-2 w-2 rounded-full", status.dot)} />
              {status.label}
            </Badge>
          </div>

          <div className="mt-6 grid gap-3 md:grid-cols-3 xl:grid-cols-6">
            <DetailMetric label="현재 가용재고" value={`${numberText(item.availableQty)}개`} />
            <DetailMetric label="일평균 판매" value={`${numberText(item.dailySalesQty, 1)}개`} sub="최근 3개월" />
            <DetailMetric label="재고 소진" value={formatDate(item.stockoutDate)} sub={stockoutLabel(item)} />
            <DetailMetric label="가장 빠른 ETA" value={formatDate(item.earliestEtaDate)} sub={item.earliestEta?.transportMode ?? "-"} />
            <DetailMetric
              label="재고 공백일"
              value={item.gapDays === null ? "-" : `${formatNumber(item.gapDays)}일`}
              sub={item.gapTiming === "active" ? "이미 진행 중" : item.gapTiming === "future" ? "발생 예정" : "공백 없음"}
              emphasized
              danger={isRisk}
              warning={isWarning}
            />
            <DetailMetric label="상태/권장 액션" value={actionText} emphasized danger={isRisk} warning={isWarning} compact />
          </div>

          <div className="mt-5 border-t border-slate-200 pt-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-bold text-slate-500">판단 문구</p>
                <p className="mt-2 text-sm font-semibold leading-6 text-slate-700">{stockGapNarrative(item)}</p>
              </div>
              <div className="group relative shrink-0">
                <button
                  type="button"
                  className="inline-flex cursor-help items-center gap-1.5 text-xs font-bold text-slate-400 hover:text-slate-600"
                  aria-label={`계산 기준: ${item.stockoutBasis}`}
                >
                  <HelpCircle className="h-3.5 w-3.5" />
                  계산 기준
                </button>
                <div className="pointer-events-none absolute right-0 top-7 z-20 hidden w-80 rounded-xl border border-line bg-white p-3 text-xs font-semibold leading-5 text-slate-700 shadow-xl group-hover:block">
                  {item.stockoutBasis}
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <StockGapTimeline item={item} />
      <EtaTable item={item} />
    </div>
  );
}

export function StockGapClient() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const brandMenuRef = useRef<HTMLDivElement>(null);
  const [items, setItems] = useState<StockGapComputedItem[] | null>(null);
  const [error, setError] = useState(false);
  const [brand, setBrand] = useState(() => {
    const brandParam = searchParams.get("brand");
    return brandParam ? displayBrandName(brandParam) : allBrands;
  });
  const [query, setQuery] = useState(() => searchParams.get("q") ?? "");
  const [selectedSku, setSelectedSku] = useState(() => searchParams.get("sku") ?? "");
  const [brandMenuOpen, setBrandMenuOpen] = useState(false);
  const fallbackBaseDate = useMemo(() => startOfDay(new Date()), []);

  const load = useCallback(() => {
    let active = true;
    setError(false);
    setItems(null);
    getStockGapItems()
      .then((nextItems) => {
        if (!active) return;
        const computed = nextItems.map((item) => computeStockGapItem(item, fallbackBaseDate));
        const sorted = sortStockGapRiskItems(computed);
        setItems(sorted);
        setSelectedSku((current) => current || sorted[0]?.sku || "");
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [fallbackBaseDate]);

  useEffect(() => load(), [load]);

  useEffect(() => {
    if (!brandMenuOpen) {
      return;
    }
    const handleClickOutside = (event: MouseEvent) => {
      if (brandMenuRef.current && !brandMenuRef.current.contains(event.target as Node)) {
        setBrandMenuOpen(false);
      }
    };
    window.addEventListener("mousedown", handleClickOutside);
    return () => window.removeEventListener("mousedown", handleClickOutside);
  }, [brandMenuOpen]);

  const brands = useMemo(() => {
    if (!items) {
      return [allBrands];
    }
    return [
      allBrands,
      ...Array.from(new Set(items.map((item) => displayBrandName(item.brand)))).sort((a, b) => a.localeCompare(b, "ko"))
    ];
  }, [items]);

  const filteredItems = useMemo(() => {
    if (!items) {
      return [];
    }
    const normalized = query.trim().toLowerCase();
    return sortStockGapRiskItems(
      items.filter((item) => {
        const brandMatch = brand === allBrands || displayBrandName(item.brand) === brand;
        const textMatch =
          !normalized ||
          item.sku.toLowerCase().includes(normalized) ||
                  item.productName.toLowerCase().includes(normalized) ||
                  item.brand.toLowerCase().includes(normalized) ||
                  displayBrandName(item.brand).toLowerCase().includes(normalized);
        return brandMatch && textMatch;
      })
    );
  }, [brand, items, query]);

  const selected = filteredItems.find((item) => item.sku === selectedSku) ?? filteredItems[0] ?? null;

  useEffect(() => {
    if (selected && selected.sku !== selectedSku) {
      setSelectedSku(selected.sku);
    }
  }, [selected, selectedSku]);

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    if (selectedSku) {
      params.set("sku", selectedSku);
    } else {
      params.delete("sku");
    }
    if (query) {
      params.set("q", query);
    } else {
      params.delete("q");
    }
    if (brand !== allBrands) {
      params.set("brand", brand);
    } else {
      params.delete("brand");
    }
    const next = params.toString();
    if (next !== searchParams.toString()) {
      router.replace(next ? `${pathname}?${next}` : pathname, { scroll: false });
    }
  }, [brand, pathname, query, router, searchParams, selectedSku]);

  const exportCurrentView = () => {
    const header = [
      "SKU",
      "상품명",
      "브랜드",
      "현재 가용재고",
      "일평균 판매",
      "재고 소진일",
      "가장 빠른 ETA",
      "재고 공백일",
      "상태",
      "권장 액션",
      "판단 문구"
    ];
    const lines = filteredItems.map((item) =>
      [
        item.sku,
        item.productName,
        displayBrandName(item.brand),
        item.availableQty ?? "",
        item.dailySalesQty ?? "",
        formatDate(item.stockoutDate),
        formatDate(item.earliestEtaDate),
        item.gapDays ?? "",
        stockGapStatusMeta[item.status].label,
        stockGapActionText(item),
        stockGapNarrative(item)
      ].map(csvCell).join(",")
    );
    const blob = new Blob([`\uFEFF${[header.map(csvCell).join(","), ...lines].join("\n")}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `stock-gap-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  if (error) {
    return (
      <ErrorState
        title="재고공백 데이터를 불러오지 못했습니다"
        message="API 연결 또는 데이터 파일을 확인해 주세요."
        onRetry={load}
      />
    );
  }

  if (!items) {
    return <LoadingState cards={4} panel={false} />;
  }

  if (items.length === 0) {
    return <AnalysisRequiredState title="재고공백 결과가 아직 없습니다." />;
  }

  return (
    <div className="space-y-5">
      <RiskSummary items={items} />

      <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
        <Card className="h-fit overflow-hidden border-slate-200">
          <CardContent className="p-0">
            <div className="space-y-3 border-b border-slate-200 p-5">
              <div ref={brandMenuRef} className="relative">
                <button
                  type="button"
                  onClick={() => setBrandMenuOpen((current) => !current)}
                  className="flex h-10 w-full items-center justify-between rounded-lg border border-line bg-white px-3 text-sm font-bold text-ink shadow-sm transition hover:border-slate-300"
                >
                  <span className="truncate">{brand === allBrands ? "전체" : displayBrandName(brand)}</span>
                  <ChevronDown className={cn("ml-2 h-4 w-4 shrink-0 text-slate-400 transition", brandMenuOpen && "rotate-180")} />
                </button>
                {brandMenuOpen ? (
                  <div className="absolute left-0 top-11 z-[80] max-h-64 w-full overflow-y-auto rounded-xl border border-line bg-white py-1 shadow-xl">
                    {brands.map((item) => {
                      const label = item === allBrands ? "전체" : displayBrandName(item);
                      const selected = item === brand;
                      return (
                        <button
                          key={item}
                          type="button"
                          onClick={() => {
                            setBrand(item);
                            setBrandMenuOpen(false);
                          }}
                          className={cn(
                            "block h-10 w-full truncate px-4 text-left text-[13px] font-bold leading-10 transition hover:bg-slate-50",
                            selected ? "text-brand" : "text-ink"
                          )}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </div>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-slate-400" />
                <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="상품명 또는 SKU 검색" className="pl-9" />
              </div>
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-bold text-slate-500">SKU 목록 · 총 {formatNumber(filteredItems.length)}건</p>
                <button
                  type="button"
                  onClick={exportCurrentView}
                  disabled={filteredItems.length === 0}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line bg-white px-3 text-xs font-bold text-ink shadow-sm hover:border-slate-400 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Download className="h-3.5 w-3.5" />
                  CSV 다운로드
                </button>
              </div>
            </div>
            <RiskList items={filteredItems} selectedSku={selected?.sku ?? ""} onSelect={setSelectedSku} />
          </CardContent>
        </Card>

        {selected ? (
          <StockGapDetail item={selected} />
        ) : (
          <Card className="border-slate-200">
            <CardContent className="p-10 text-center text-slate-500">조건에 맞는 SKU가 없습니다.</CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
