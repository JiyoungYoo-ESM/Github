"use client";

import { useEffect, useState } from "react";
import { FileText, Search } from "lucide-react";

import { displayBrandName } from "@/lib/brand-display";
import { cn, formatNumber } from "@/lib/utils";
import { useUserPermissions } from "@/lib/use-user-permissions";
import type { Screen } from "../../lib/types";
import { krwEokFromEur, wonEok } from "../../lib/currency-format";
import { AnalysisPeriodBadge, AnalysisPeriodCaveat } from "../../shared/AnalysisPeriod";
import { InsightAnalysisRequiredState } from "../../shared/AnalysisRequiredState";
import { Pagination } from "../../shared/Pagination";
import { RankingDetailDialog, RankingDetailOpenButton, type RankingDetailRow } from "../../shared/RankingDetailDialog";
import { useCategoryScreenModel } from "./useCategoryScreenModel";

const CATEGORY_PAGE_SIZE = 10;

export function CategoryScreenExact({ onNavigate }: { onNavigate: (screen: Screen) => void }) {
  const { canViewAmountData } = useUserPermissions();
  const {
    loading,
    loadFailed,
    analysisOptions,
    averageEurKrwRate,
    metricBasis,
    setMetricBasis,
    hasAmount,
    categorySummaries,
    selectedCategory,
    setSelectedCategory,
    activeCategory,
    categorySkuRows,
    allCategorySkuRows,
    exportingCategoryPdf,
    exportCategoryReportPdf
  } = useCategoryScreenModel();
  const [skuDetailOpen, setSkuDetailOpen] = useState(false);
  const [categorySearch, setCategorySearch] = useState("");
  const [categoryPage, setCategoryPage] = useState(1);

  // 매출 열람 권한이 없으면 판매량 기준으로 강제한다(순위 산출 기준까지 일치시킨다).
  useEffect(() => {
    if (!canViewAmountData) setMetricBasis("qty");
  }, [canViewAmountData, setMetricBasis]);

  // 검색어가 바뀌면 필터링된 목록 기준으로 다시 1페이지부터 보여준다.
  useEffect(() => {
    setCategoryPage(1);
  }, [categorySearch]);

  const amountAllowed = canViewAmountData && hasAmount;
  const metricLabel = metricBasis === "amount" ? "매출액" : "판매량";
  const valueText = (amount: number, qty: number) => (metricBasis === "amount" ? wonEok(amount) || "-" : `${formatNumber(qty)}개`);
  const krwText = (amount: number) => (metricBasis === "amount" ? krwEokFromEur(amount, averageEurKrwRate) : "");

  if (loading) {
    return (
      <div className="mx-auto max-w-[1320px] py-[24px]">
        <div className="grid min-h-[360px] place-items-center rounded-[16px] border border-border bg-surface text-[13px] font-black text-muted shadow-soft">
          제품군 분석 데이터를 불러오는 중입니다.
        </div>
      </div>
    );
  }

  if (loadFailed) {
    return (
      <div className="mx-auto max-w-[1320px] py-[24px]">
        <div className="grid min-h-[360px] place-items-center rounded-[16px] border border-border bg-surface text-center shadow-soft">
          <div>
            <h2 className="text-[20px] font-black text-ink">제품군 분석 데이터를 불러오지 못했습니다.</h2>
            <p className="mt-3 text-[13px] font-semibold text-muted">백엔드 연결 상태와 최신 CMS 분석 결과를 확인해 주세요.</p>
          </div>
        </div>
      </div>
    );
  }

  if (categorySummaries.length === 0 || !activeCategory) {
    return (
      <InsightAnalysisRequiredState
        title="제품군 분석 결과가 아직 없습니다."
        description="데이터 입력 탭에서 CMS API 분석을 실행하면 기능구분별 제품군 순위와 SKU 분포가 이 화면에 반영됩니다."
        onNavigate={onNavigate}
      />
    );
  }

  const rankedCategorySummaries = categorySummaries.map((category, index) => ({ ...category, rank: index + 1 }));
  const normalizedCategorySearch = categorySearch.trim().toLowerCase();
  const visibleCategorySummaries = normalizedCategorySearch
    ? rankedCategorySummaries.filter((category) => category.label.toLowerCase().includes(normalizedCategorySearch))
    : rankedCategorySummaries;
  const categoryTotalPages = Math.max(1, Math.ceil(visibleCategorySummaries.length / CATEGORY_PAGE_SIZE));
  const categoryCurrentPage = Math.min(categoryPage, categoryTotalPages);
  const categoryPageStart = (categoryCurrentPage - 1) * CATEGORY_PAGE_SIZE;
  const pagedCategorySummaries = visibleCategorySummaries.slice(categoryPageStart, categoryPageStart + CATEGORY_PAGE_SIZE);
  const isCategorySearchActive = normalizedCategorySearch.length > 0;

  const skuDetailRows: RankingDetailRow[] = allCategorySkuRows.map((row) => ({
    id: row.sku,
    label: row.name,
    detail: [displayBrandName(row.brand), row.sku, `금액 YTD ${row.ytdGrowth}`, row.peakMonth ? `피크 ${row.peakMonth}월` : ""].filter(Boolean).join(" · "),
    ...(amountAllowed ? { amount: valueText(row.amount, row.qty), amountKrw: krwText(row.amount) } : { amount: `${formatNumber(row.qty)}개` }),
    sharePct: row.sharePct
  }));

  const kpis = [
    ["전체 제품군", `${formatNumber(categorySummaries.length)}개`, "기능구분 1·2 기준"],
    ["선택 제품군", activeCategory.label, `${metricLabel} 기준`],
    ["구성 SKU", `${formatNumber(activeCategory.skuCount)}개`, `${formatNumber(activeCategory.brandCount)} 브랜드`],
    ["전체 비중", `${formatNumber(activeCategory.sharePct, 1)}%`, `${metricLabel} 점유율`]
  ];

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
      <div className="mb-[20px] flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-[18px] font-black leading-none text-ink">제품군 기준 분석</h2>
          <p className="mt-[11px] text-[13px] font-semibold leading-none text-muted">
            기능구분 1·2로 묶은 제품군별 순위와 제품군 내 SKU 경쟁 위치를 확인하세요.
          </p>
          <div className="mt-[12px]">
            <AnalysisPeriodBadge options={analysisOptions} />
            <AnalysisPeriodCaveat options={analysisOptions} />
            <p className="mt-1 text-[11px] font-semibold text-muted2">
              리뉴얼 전후 제품은 별도 SKU 코드로 집계됩니다. 하나의 대표 제품으로 통합하지 않습니다.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={exportCategoryReportPdf}
          disabled={exportingCategoryPdf}
          className="inline-flex h-[38px] items-center gap-2 rounded-[10px] bg-brand px-4 text-[13px] font-black text-white transition hover:bg-brand/90 disabled:cursor-not-allowed disabled:opacity-70"
        >
          <FileText className="h-4 w-4" />
          {exportingCategoryPdf ? "PDF 생성 중" : "리포트로 내보내기"}
        </button>
      </div>

      <div className="mb-[16px] flex flex-wrap items-center justify-between gap-3">
        <div className="flex w-fit rounded-[12px] bg-segbg p-1 shadow-card">
          {([
            ["qty", "판매량"],
            ["amount", "매출액"]
          ] as const).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setMetricBasis(id)}
              disabled={id === "amount" && !amountAllowed}
              className={cn(
                "h-8 rounded-[8px] px-3 text-[12px] font-black transition disabled:cursor-not-allowed disabled:opacity-40",
                metricBasis === id ? "bg-surface text-ink shadow-soft" : "text-muted hover:text-ink"
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="text-[12px] font-black text-muted2">전체 {formatNumber(categorySummaries.length)}개 제품군</p>
      </div>

      <div className="mb-[16px] grid grid-cols-2 gap-[12px] xl:grid-cols-4">
        {kpis.map(([label, value, sub]) => (
          <div key={label} className="rounded-[14px] border border-border bg-surface px-4 py-[15px] shadow-soft">
            <p className="text-[12px] font-semibold text-muted2">{label}</p>
            <p className="mt-[8px] truncate text-[18px] font-black leading-none text-ink" title={value}>{value}</p>
            <p className="mt-[9px] text-[11px] font-bold text-muted2">{sub}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-[16px] lg:grid-cols-2">
        <section className="flex flex-col overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
          <div className="border-b border-divider px-5 py-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-[13px] font-black text-ink">제품군 전체 목록 <span className="font-semibold text-muted2">· {metricLabel} 기준</span></h3>
                <p className="mt-1 text-[10.5px] font-semibold text-muted2">금액 · 선택 기간 합계</p>
              </div>
              <span className="shrink-0 text-[11px] font-semibold text-muted2">
                {isCategorySearchActive
                  ? `검색 ${formatNumber(visibleCategorySummaries.length)}개 · 전체 순위 표시`
                  : `전체 ${formatNumber(categorySummaries.length)}개`}
              </span>
            </div>
            <div className="relative mt-3">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted2" aria-hidden="true" />
              <input
                type="text"
                value={categorySearch}
                onChange={(event) => setCategorySearch(event.target.value)}
                placeholder="제품군 검색"
                aria-label="제품군 검색"
                className="h-9 w-full rounded-[8px] border border-border bg-surface pl-9 pr-3 text-[12.5px] font-semibold text-ink outline-none placeholder:text-muted2 focus:border-brand"
              />
            </div>
          </div>
          <div className="px-4 py-2">
            {pagedCategorySummaries.length > 0 ? pagedCategorySummaries.map((category) => {
              const active = category.key === selectedCategory;
              return (
                <button
                  key={category.key}
                  type="button"
                  onClick={() => setSelectedCategory(category.key)}
                  className={cn(
                    "grid w-full grid-cols-[48px_minmax(0,1fr)_auto] items-center gap-3 rounded-[9px] border-b border-rowline px-2 py-2.5 text-left transition last:border-b-0",
                    active ? "bg-brand-50/50" : "hover:bg-surface-soft"
                  )}
                >
                  <span className={cn("text-[12px] font-black", active ? "text-brand" : "text-muted2")}>
                    {isCategorySearchActive ? `전체 ${category.rank}위` : category.rank}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-[12.5px] font-black text-ink">{category.label}</span>
                    <span className="mt-1.5 block h-1.5 overflow-hidden rounded-full bg-surface-soft">
                      <span className="block h-full rounded-full bg-brand" style={{ width: category.width }} />
                    </span>
                  </span>
                  <span className="text-right">
                    {amountAllowed ? (
                      <>
                        <span className="block text-[12.5px] font-black text-ink">{valueText(category.amount, category.qty)}</span>
                        {krwText(category.amount) ? <span className="mt-0.5 block text-[10.5px] font-semibold text-muted2">{krwText(category.amount)}</span> : null}
                        <span className="mt-0.5 block text-[11px] font-black text-brand">{formatNumber(category.sharePct, 1)}%</span>
                      </>
                    ) : (
                      <span className="block text-[12.5px] font-black text-ink">{formatNumber(category.sharePct, 1)}%</span>
                    )}
                    <span className="mt-0.5 block text-[10.5px] font-semibold text-muted2">{formatNumber(category.skuCount)} SKU</span>
                  </span>
                </button>
              );
            }) : (
              <p className="py-8 text-center text-[12px] font-semibold text-muted2">검색 결과가 없습니다.</p>
            )}
          </div>
          {visibleCategorySummaries.length > CATEGORY_PAGE_SIZE ? (
            <div className="border-t border-divider px-4 py-3">
              <Pagination currentPage={categoryCurrentPage} totalPages={categoryTotalPages} onPageChange={setCategoryPage} />
            </div>
          ) : null}
        </section>

        <section className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
          <div className="flex items-center justify-between border-b border-divider px-5 py-4">
            <div className="min-w-0">
              <h3 className="truncate text-[13px] font-black text-ink" title={activeCategory.label}>{activeCategory.label}</h3>
              <p className="mt-1 text-[11px] font-semibold text-muted2">제품군 내 SKU 순위 · {metricLabel} 기준</p>
              <p className="mt-1 text-[10.5px] font-semibold text-muted2">금액 · 선택 기간 합계</p>
            </div>
            <RankingDetailOpenButton onClick={() => setSkuDetailOpen(true)} />
          </div>
          <div className="px-4 py-2">
            {categorySkuRows.length > 0 ? categorySkuRows.map((row, index) => (
              <div
                key={row.sku}
                className="grid grid-cols-[24px_minmax(0,1fr)_auto] items-center gap-3 border-b border-rowline py-2.5 last:border-b-0"
              >
                <span className="text-[12px] font-black text-muted2">{index + 1}</span>
                <span className="min-w-0">
                  <span className="block truncate text-[12.5px] font-black text-ink">{row.name}</span>
                  <span className="mt-0.5 block truncate text-[11px] font-semibold text-muted2">
                    {[displayBrandName(row.brand), row.sku, row.peakMonth ? `피크 ${row.peakMonth}월` : ""].filter(Boolean).join(" · ")}
                  </span>
                  <span className="mt-1.5 block h-1.5 overflow-hidden rounded-full bg-surface-soft">
                    <span className="block h-full rounded-full bg-brand" style={{ width: row.width }} />
                  </span>
                </span>
                <span className="text-right">
                  {amountAllowed ? (
                    <>
                      <span className="block text-[12.5px] font-black text-ink">{valueText(row.amount, row.qty)}</span>
                      {krwText(row.amount) ? <span className="mt-0.5 block text-[10.5px] font-semibold text-muted2">{krwText(row.amount)}</span> : null}
                    </>
                  ) : (
                    <span className="block text-[12.5px] font-black text-ink">{formatNumber(row.qty)}개</span>
                  )}
                  <span className="mt-0.5 block text-[11px] font-black text-brand">{formatNumber(row.sharePct, 1)}%</span>
                </span>
              </div>
            )) : (
              <p className="py-8 text-center text-[12px] font-semibold text-muted2">이 제품군에 표시할 SKU가 없습니다.</p>
            )}
          </div>
        </section>
      </div>

      <RankingDetailDialog
        open={skuDetailOpen}
        title={`${activeCategory.label} · SKU 전체 순위`}
        subtitle={`${metricLabel} 기준 · 제품군 내 비중`}
        valueLabel={metricLabel}
        shareLabel="제품군 내 비중"
        rows={skuDetailRows}
        onClose={() => setSkuDetailOpen(false)}
      />
    </div>
  );
}
