"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { SkuStockGapDrawer } from "@/components/order-review/SkuStockGapDrawer";
import { Download, Search } from "lucide-react";
import { AnalysisRequiredState } from "@/components/analysis/AnalysisRequiredState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PaginationControls } from "@/components/common/PaginationControls";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { getSkuConcentrationRows } from "@/lib/api";
import { getStoredAnalysisResultAsync } from "@/lib/api/storage";
import { displayBrandName } from "@/lib/brand-display";
import {
  calculateBrandDependency,
  calculateSkuConcentration,
  concentrationStatusLabels,
  defaultSkuConcentrationThresholds,
  type BrandDependencyResult,
  type ConcentrationJudgement,
  type SkuConcentrationResult,
  type SkuConcentrationThresholds
} from "@/lib/sku-concentration";
import {
  allSkuConcentrationBrands,
  amount,
  concentrationFillClass,
  concentrationLevelClass,
  concentrationLevelLabel,
  concentrationTopClass,
  defaultSkuConcentrationPageSize,
  diffPercent,
  diffToneClass,
  gradeBadgeClass,
  judgementBadgeClass,
  percent,
  readSkuConcentrationThresholds,
  skuConcentrationSortOptions,
  skuConcentrationStatusOptions,
  type SkuConcentrationSortKey
} from "@/lib/sku-concentration-view";
import { cn, formatNumber } from "@/lib/utils";
import type { SkuConcentrationSource } from "@/types/api";
import { useUserPermissions } from "@/lib/use-user-permissions";


function csvCell(value: string | number | null | undefined) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function InlineShareBar({ value, tone = "sales" }: { value: number; tone?: "sales" | "stock" }) {
  const width = Math.min(Math.max(value, 0), 100);
  return (
    <div className="flex items-center justify-end gap-3 tabular-nums">
      <div className="h-2 w-20 rounded-full bg-slate-100">
        <div
          className={cn("h-2 rounded-full", tone === "sales" ? "bg-blue-600" : "bg-slate-400")}
          style={{ width: `${width}%` }}
        />
      </div>
      <span className="w-12 text-right font-semibold text-ink">{percent(value)}</span>
    </div>
  );
}

function DivergingDiffBar({ row, maxAbsDiff }: { row: SkuConcentrationResult; maxAbsDiff: number }) {
  if (row.shareDiffPct === null) {
    return <span className="block text-right text-slate-400">-</span>;
  }

  const width = maxAbsDiff > 0 ? Math.min((Math.abs(row.shareDiffPct) / maxAbsDiff) * 50, 50) : 0;
  const isNegative = row.shareDiffPct < 0;
  const isPositive = row.shareDiffPct > 0;

  return (
    <div className="grid grid-cols-[1fr_56px] items-center gap-3 tabular-nums">
      <div className="relative h-6 rounded-full bg-slate-50">
        <div className="absolute left-1/2 top-0 h-6 w-px bg-slate-300" />
        {isNegative ? (
          <div
            className="absolute right-1/2 top-2 h-2 rounded-l-full bg-brand"
            style={{ width: `${width}%` }}
          />
        ) : null}
        {isPositive ? (
          <div
            className="absolute left-1/2 top-2 h-2 rounded-r-full bg-orange-500"
            style={{ width: `${width}%` }}
          />
        ) : null}
        {!isNegative && !isPositive ? <div className="absolute left-1/2 top-2 h-2 w-2 -translate-x-1/2 rounded-full bg-slate-300" /> : null}
      </div>
      <span className={cn("text-right font-bold", diffToneClass[row.judgement])}>{diffPercent(row.shareDiffPct)}</span>
    </div>
  );
}

function BrandConcentrationBar({ dependency }: { dependency: BrandDependencyResult }) {
  return (
    <div className="flex items-center justify-end gap-4 tabular-nums">
      <span className="w-12 text-right font-bold text-ink">{percent(dependency.top1SharePct)}</span>
      <div className="relative h-2.5 w-full max-w-[280px] rounded-full bg-slate-100">
        <div
          className={cn("absolute inset-y-0 left-0 rounded-full", concentrationFillClass[dependency.risk])}
          style={{ width: `${Math.min(dependency.top3SharePct, 100)}%` }}
        />
        <div
          className={cn("absolute inset-y-0 left-0 rounded-full", concentrationTopClass[dependency.risk])}
          style={{ width: `${Math.min(dependency.top1SharePct, 100)}%` }}
        />
      </div>
      <span className="w-14 text-right font-bold text-ink">{percent(dependency.top3SharePct)}</span>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  detail
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <Card className="border-line">
      <CardContent className="p-5">
        <p className="text-sm font-bold text-slate-500">{label}</p>
        <p className="mt-2 truncate text-2xl font-black text-ink tabular-nums" title={value}>
          {value}
        </p>
        {detail ? <p className="mt-1 text-xs font-semibold text-slate-500">{detail}</p> : null}
      </CardContent>
    </Card>
  );
}

export function SkuConcentrationClient() {
  const { canViewAmountData } = useUserPermissions();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [items, setItems] = useState<SkuConcentrationSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [brand, setBrand] = useState(() => searchParams.get("brand") ?? allSkuConcentrationBrands);
  const [query, setQuery] = useState(() => searchParams.get("q") ?? "");
  const [sortKey, setSortKey] = useState<SkuConcentrationSortKey>(() => (searchParams.get("sort") as SkuConcentrationSortKey) || "salesShare");
  const [judgement, setJudgement] = useState<"all" | ConcentrationJudgement>(() => (searchParams.get("judgement") as "all" | ConcentrationJudgement) || "all");
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(() => Number(searchParams.get("pageSize") ?? defaultSkuConcentrationPageSize));
  const [thresholds, setThresholds] = useState<SkuConcentrationThresholds>(defaultSkuConcentrationThresholds);
  const [drawerSku, setDrawerSku] = useState<string | null>(null);

  const load = useCallback(() => {
    let mounted = true;
    setLoading(true);
    setError(false);
    Promise.all([getSkuConcentrationRows(), getStoredAnalysisResultAsync()])
      .then(([rows, result]) => {
        if (mounted) {
          setItems(rows);
          setThresholds(readSkuConcentrationThresholds(result?.settings));
        }
      })
      .catch(() => {
        if (mounted) setError(true);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => load(), [load]);

  const brandDependencies = useMemo(() => calculateBrandDependency(items), [items]);

  const allRows = useMemo(
    () =>
      calculateSkuConcentration(
        items,
        brand === allSkuConcentrationBrands ? "global" : "brand",
        brand === allSkuConcentrationBrands ? undefined : brand,
        thresholds
      ),
    [brand, items, thresholds]
  );

  const rows = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const judgementFiltered = judgement === "all" ? allRows : allRows.filter((row) => row.judgement === judgement);
    const filtered = normalized
      ? judgementFiltered.filter((row) =>
          [row.sku, row.productName, row.brand, displayBrandName(row.brand)].some((value) => value.toLowerCase().includes(normalized))
        )
      : judgementFiltered;
    return [...filtered].sort((a, b) => {
      if (a.missingProductName !== b.missingProductName) {
        return a.missingProductName ? 1 : -1;
      }
      if (sortKey === "salesShare") return b.salesSharePct - a.salesSharePct;
      if (sortKey === "stockShare") return b.stockSharePct - a.stockSharePct;
      if (sortKey === "diff") return Math.abs(b.shareDiffPct ?? 0) - Math.abs(a.shareDiffPct ?? 0);
      return a.grade.localeCompare(b.grade) || b.salesSharePct - a.salesSharePct;
    });
  }, [allRows, judgement, query, sortKey]);

  useEffect(() => {
    setPageIndex(0);
  }, [brand, judgement, pageSize, query, sortKey]);

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    const setOrDelete = (key: string, value: string, emptyValue = "") => {
      if (!value || value === emptyValue) params.delete(key);
      else params.set(key, value);
    };
    setOrDelete("brand", brand, allSkuConcentrationBrands);
    setOrDelete("q", query);
    setOrDelete("sort", sortKey, "salesShare");
    setOrDelete("judgement", judgement, "all");
    if (pageSize !== defaultSkuConcentrationPageSize) params.set("pageSize", String(pageSize));
    else params.delete("pageSize");
    const next = params.toString();
    if (next !== searchParams.toString()) {
      router.replace(next ? `${pathname}?${next}` : pathname, { scroll: false });
    }
  }, [brand, judgement, pageSize, pathname, query, router, searchParams, sortKey]);

  const pageCount = Math.max(Math.ceil(rows.length / pageSize), 1);
  const safePageIndex = Math.min(pageIndex, pageCount - 1);
  const paginatedRows = useMemo(
    () => rows.slice(safePageIndex * pageSize, safePageIndex * pageSize + pageSize),
    [pageSize, rows, safePageIndex]
  );

  const maxAbsDiff = useMemo(
    () => Math.max(...rows.map((row) => Math.abs(row.shareDiffPct ?? 0)), 0),
    [rows]
  );

  const totals = useMemo(
    () =>
      rows.reduce(
        (acc, row) => {
          acc.sales += row.salesAmount ?? 0;
          acc.stock += row.stockAmount ?? 0;
          acc.shortage += row.judgement === "shortage_risk" ? 1 : 0;
          acc.overstock += row.judgement === "overstock" ? 1 : 0;
          acc.missing += row.missingProductName ? 1 : 0;
          acc.salesMatched += (row.salesAmount ?? 0) > 0 ? 1 : 0;
          acc.stockMatched += (row.stockAmount ?? 0) > 0 ? 1 : 0;
          return acc;
        },
        { sales: 0, stock: 0, shortage: 0, overstock: 0, missing: 0, salesMatched: 0, stockMatched: 0 }
      ),
    [rows]
  );

  const exportCurrentView = () => {
    const header = [
      "등급",
      "SKU",
      "상품명",
      "브랜드",
      ...(canViewAmountData ? ["판매금액(KRW)", "재고 평가액(KRW)"] : []),
      "판매비중",
      "재고비중",
      "비중 차이",
      "판단"
    ];
    const lines = rows.map((row) =>
      [
        row.grade,
        row.sku,
        row.productName,
        displayBrandName(row.brand),
        ...(canViewAmountData ? [row.salesAmount ?? "", row.stockAmount ?? ""] : []),
        row.salesSharePct,
        row.stockSharePct,
        row.shareDiffPct ?? "",
        concentrationStatusLabels[row.judgement]
      ].map(csvCell).join(",")
    );
    const blob = new Blob([`\uFEFF${[header.map(csvCell).join(","), ...lines].join("\n")}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `sku-concentration-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const selectedBrandLabel = brand === allSkuConcentrationBrands ? "전체" : displayBrandName(brand);
  const skuSummaryLabel = brand === allSkuConcentrationBrands ? "현재 필터 SKU" : "선택 브랜드 SKU";
  const activeFilterDetail =
    rows.length === allRows.length
      ? `선택 범위 ${formatNumber(allRows.length)} SKU`
      : `현재 필터 ${formatNumber(rows.length)} SKU · 선택 범위 ${formatNumber(allRows.length)} SKU`;

  if (loading) {
    return <LoadingState panel />;
  }

  if (error) {
    return (
      <ErrorState
        title="SKU 집중도 데이터를 불러오지 못했습니다"
        message="API 연결 또는 데이터 파일을 확인해 주세요."
        onRetry={load}
      />
    );
  }

  if (items.length === 0) {
    return <AnalysisRequiredState title="SKU 집중도 결과가 아직 없습니다." />;
  }

  const hasSalesAmountData = items.some((item) => typeof item.salesAmount === "number" && Number.isFinite(item.salesAmount) && item.salesAmount > 0);
  if (!hasSalesAmountData) {
    return (
      <AnalysisRequiredState
        title="판매금액 데이터가 아직 없습니다."
        description="SKU 집중도는 CMS가 거래일 환율로 계산한 실제 원화 판매금액을 사용합니다. 발주 분석을 다시 실행하면 이 화면에 반영됩니다."
      />
    );
  }

  return (
    <>
    <div className="space-y-5">
      <div className={cn("grid gap-4", canViewAmountData ? "xl:grid-cols-4" : "xl:grid-cols-2")}>
        <SummaryCard label={skuSummaryLabel} value={formatNumber(rows.length)} detail={activeFilterDetail} />
        {canViewAmountData ? <SummaryCard
          label="현재 필터 판매금액(KRW)"
          value={amount(totals.sales)}
          detail={`판매금액 매칭 ${formatNumber(totals.salesMatched)}/${formatNumber(rows.length)} SKU · CMS 실제 원화 판매금액`}
        /> : null}
        {canViewAmountData ? <SummaryCard
          label="현재 필터 현지 재고 평가액(KRW)"
          value={amount(totals.stock)}
          detail={`재고가치 매칭 ${formatNumber(totals.stockMatched)}/${formatNumber(rows.length)} SKU · CMS 조회일 원화 재고금액`}
        /> : null}
        <SummaryCard
          label="현재 필터 판매-재고 불균형"
          value={`${formatNumber(totals.shortage)} 부족 · ${formatNumber(totals.overstock)} 과잉`}
          detail="판매비중과 재고가치 비중 차이 기준"
        />
      </div>

      <Card className="border-line">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <CardTitle>브랜드 집중도 요약</CardTitle>
              <p className="mt-1 text-sm text-slate-500">
                브랜드 매출이 일부 SKU에 몰려 있는지 봅니다.{" "}
                <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-600">
                  행 클릭 → 브랜드 필터
                </span>
              </p>
            </div>
            <p className="text-sm font-bold text-slate-500">
              선택: <span className="text-ink">{selectedBrandLabel}</span>
            </p>
          </div>
        </CardHeader>
        <CardContent>
          <div className="max-h-[360px] overflow-y-auto rounded-xl border border-line">
            <Table className="table-fixed">
              <TableHeader className="sticky top-0 z-10 bg-slate-50">
                <TableRow>
                  <TableHead className="w-[28%]">브랜드</TableHead>
                  <TableHead className="w-[12%] text-right">판매 SKU / 전체</TableHead>
                  <TableHead className="w-[42%] text-right">상위 SKU 매출 비중</TableHead>
                  <TableHead className="w-[18%] text-right">집중도</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {brandDependencies.map((dependency) => {
                  const selected = brand === dependency.brand;
                  return (
                    <TableRow
                      key={dependency.brand}
                      role="button"
                      tabIndex={0}
                      onClick={() => {
                        setBrand((current) => (current === dependency.brand ? allSkuConcentrationBrands : dependency.brand));
                        setJudgement("all");
                      }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setBrand((current) => (current === dependency.brand ? allSkuConcentrationBrands : dependency.brand));
                          setJudgement("all");
                        }
                      }}
                      className={cn(
                        "cursor-pointer transition-colors hover:bg-slate-50",
                        selected
                          ? "border-l-4 border-l-ink bg-slate-100 hover:bg-slate-100"
                          : "hover:bg-slate-50"
                      )}
                    >
                      <TableCell className="font-black text-ink">{displayBrandName(dependency.brand)}</TableCell>
                      <TableCell className="text-right font-semibold tabular-nums">
                        {formatNumber(dependency.activeSkuCount)} / {formatNumber(dependency.skuCount)}
                      </TableCell>
                      <TableCell>
                        <BrandConcentrationBar dependency={dependency} />
                      </TableCell>
                      <TableCell className="text-right">
                        <Badge className={concentrationLevelClass[dependency.risk]}>
                          집중도 {concentrationLevelLabel[dependency.risk]}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card className="border-line">
        <CardHeader className="pb-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <CardTitle>SKU별 판매-재고 비중 비교</CardTitle>
              <p className="mt-1 text-sm text-slate-500">
                판매 비중 대비 재고 비중의 격차로 발주/소진 우선순위를 판단합니다.
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-3">
              <div className="flex flex-wrap gap-2 text-xs font-bold text-slate-500">
                <span className="inline-flex items-center gap-1">
                  <span className="h-2.5 w-4 rounded bg-brand" /> 재고 부족
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="h-2.5 w-4 rounded bg-orange-500" /> 과잉 재고
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="h-2.5 w-4 rounded bg-slate-300" /> 적정
                </span>
              </div>
              <button
                type="button"
                onClick={exportCurrentView}
                disabled={rows.length === 0}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line bg-white px-3 text-xs font-bold text-ink shadow-sm hover:border-slate-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Download className="h-3.5 w-3.5" />
                CSV 다운로드
              </button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(220px,1fr)_minmax(180px,220px)_minmax(180px,220px)_1fr]">
            <label className="space-y-1">
              <span className="text-xs font-bold text-slate-500">검색</span>
              <span className="relative block">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="SKU · 상품명 · 브랜드"
                  className="h-11 w-full rounded-2xl border border-line bg-white pl-9 pr-4 text-sm font-semibold text-ink shadow-sm outline-none focus:border-slate-400"
                />
              </span>
            </label>
            <label className="space-y-1">
              <span className="text-xs font-bold text-slate-500">정렬</span>
              <Select value={sortKey} onChange={(event) => setSortKey(event.target.value as SkuConcentrationSortKey)} className="font-semibold">
                {skuConcentrationSortOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </label>
            <label className="space-y-1">
              <span className="text-xs font-bold text-slate-500">판단</span>
              <Select
                value={judgement}
                onChange={(event) => setJudgement(event.target.value as "all" | ConcentrationJudgement)}
                className="font-semibold"
              >
                {skuConcentrationStatusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </label>
            <div className="flex items-end justify-end gap-2 text-sm font-bold text-slate-500">
              <span>선택: <span className="text-ink">{selectedBrandLabel}</span></span>
              {totals.missing > 0 ? (
                <Badge className="border-slate-200 bg-slate-100 text-slate-600">상품명 미확인 {formatNumber(totals.missing)}건</Badge>
              ) : null}
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-line">
            <div className="max-h-[760px] overflow-y-auto">
              <Table className="table-fixed">
                <TableHeader className="sticky top-0 z-10 bg-slate-50">
                  <TableRow>
                    <TableHead className="w-[7%] text-center">등급</TableHead>
                    <TableHead className="w-[27%]">SKU·상품명</TableHead>
                    {canViewAmountData ? <TableHead className="w-[13%] text-right">판매금액</TableHead> : null}
                    <TableHead className="w-[14%] text-right">판매비중</TableHead>
                    <TableHead className="w-[14%] text-right">재고비중</TableHead>
                    <TableHead className="w-[17%] text-right">비중 차이</TableHead>
                    <TableHead className="w-[8%] text-right">판단</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={canViewAmountData ? 7 : 6} className="py-8 text-center text-slate-500">
                        조건에 맞는 SKU가 없습니다.
                      </TableCell>
                    </TableRow>
                  ) : (
                    paginatedRows.map((row) => (
                      <TableRow
                        key={`${row.brand}-${row.sku}`}
                        className={cn("hover:bg-slate-50", row.missingProductName && "bg-slate-50 text-slate-400")}
                      >
                        <TableCell className="text-center">
                          <Badge className={gradeBadgeClass[row.grade] ?? gradeBadgeClass.C}>{row.grade}</Badge>
                        </TableCell>
                        <TableCell className="min-w-0 whitespace-normal">
                          <button
                            type="button"
                            onClick={() => setDrawerSku(row.sku)}
                            className={cn("truncate font-mono font-black hover:text-brand", row.missingProductName ? "text-slate-500" : "text-brand-700")}
                          >
                            {row.sku}
                          </button>
                          <p className={cn("mt-1 line-clamp-2 text-sm", row.missingProductName ? "text-slate-400" : "text-ink")}>
                            {row.productName}
                          </p>
                          <p className="mt-1 truncate text-xs font-semibold text-slate-400">{row.brand ? displayBrandName(row.brand) : "-"}</p>
                        </TableCell>
                        {canViewAmountData ? <TableCell className="text-right font-bold text-ink tabular-nums">{amount(row.salesAmount)}</TableCell> : null}
                        <TableCell>
                          <InlineShareBar value={row.salesSharePct} tone="sales" />
                        </TableCell>
                        <TableCell>
                          <InlineShareBar value={row.stockSharePct} tone="stock" />
                        </TableCell>
                        <TableCell>
                          <DivergingDiffBar row={row} maxAbsDiff={maxAbsDiff} />
                        </TableCell>
                        <TableCell className="text-right">
                          <Badge className={judgementBadgeClass[row.judgement]}>{concentrationStatusLabels[row.judgement]}</Badge>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </div>

          <PaginationControls
            page={safePageIndex + 1}
            pageSize={pageSize}
            totalItems={rows.length}
            onPageChange={(page) => setPageIndex(page - 1)}
            onPageSizeChange={(nextPageSize) => {
              setPageSize(nextPageSize);
              setPageIndex(0);
            }}
          />
        </CardContent>
      </Card>
    </div>
    <SkuStockGapDrawer sku={drawerSku} onClose={() => setDrawerSku(null)} />
    </>
  );
}
