"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeftRight, ChevronDown, FileText, Search, X } from "lucide-react";
import { getSeasonTrendAnalysis } from "@/lib/api";
import {
  buildCalendarMonthAverageProfile,
  buildTopSkuConcentration,
  completeSeasonalityMonthKeys
} from "@/lib/brand-analysis";
import { displayBrandName } from "@/lib/brand-display";
import { trendLineColors } from "@/lib/chart-tokens";
import { lowBaseAmountLabel } from "@/lib/low-base";
import {
  amountOf,
  brandOf,
  category1Of,
  category2Of,
  countryOf,
  monthKeyOf,
  productNameOf,
  qtyOf,
  skuCodeOf
} from "@/lib/global-demand-view-model";
import { cn, formatNumber } from "@/lib/utils";
import type { MonthCoverage } from "@/types/api";
import type { ComparisonBasis, ReportBlock } from "../../lib/types";
import {
  krwEokFromEur,
  signedEur,
  signedKrwEokFromEur,
  wonEok
} from "../../lib/currency-format";
import { growthPercentValue } from "../../lib/growth-display";
import { escapeReportHtml } from "../../lib/report-html";
import { analysisPeriodLabel, longKoreanDateLabel, reportAnalysisPeriodParams, reportBrandRole } from "../../lib/workspace-format";
import { AnalysisPeriodBadge, AnalysisPeriodCaveat } from "../../shared/AnalysisPeriod";
import { BrandBar, SkuNameWithCode } from "../../shared/BrandBar";
import { BrandSearchSelect } from "../../shared/BrandSearchSelect";
import {
  RankingDetailDialog,
  RankingDetailOpenButton,
  type RankingDetailColumn,
  type RankingDetailRow
} from "../../shared/RankingDetailDialog";
import {
  availableComparisonBasis,
  automaticComparisonBasis,
  automaticGrowthTargetMonths,
  comparableYearWindow,
  comparisonBasisFromValue,
  growthBadgeClass,
  growthDisplayLabel,
  growthLabelsForMonthPair,
  isGrowthStatusLabel,
  latestComparableMonths,
  latestComparableYears,
  previousMonthKey,
  previousYearMonthKey,
  shortMonthPairLabel,
  yoyBucketOf
} from "../../lib/yoy-comparison";

import {
  BrandMetricBox,
  BrandRankRow,
  BrandStatusPill,
  SkuSearchSelect,
  type SkuSearchOption
} from "./BrandScreenParts";
import { formatQuarterLabel } from "../country/country-quarter-growth";
import { useBrandScreenData } from "./useBrandScreenData";
import { useBrandScreenModel } from "./useBrandScreenModel";
import { useUserPermissions } from "@/lib/use-user-permissions";
import { isAmountField } from "@/lib/amount-permissions";

export function BrandScreenExact({
  reportBlocks,
  onToggleReportBlock
}: {
  reportBlocks: ReportBlock[];
  onToggleReportBlock: (block: ReportBlock) => void;
}) {
  const { canViewAmountData } = useUserPermissions();
  const {
    BRAND_COMPARISON_PICKER,
    exportingBrandPdf,
    loading,
    loadFailed,
    analysisOptions,
    setSelectedBrandName,
    setBrandPage,
    brandGrowthBasis,
    setBrandGrowthBasis,
    brandGrowthTargetQuarter,
    setBrandGrowthTargetQuarter,
    brandGrowthComparisonQuarter,
    activeBrandQuarterOptions,
    comparisonBrands,
    setComparisonBrands,
    brandComparisonTooltip,
    setBrandComparisonTooltip,
    brandSummaries,
    brandExcludedMonthCount,
    brandSeasonMonths,
    brandPageCount,
    safeBrandPage,
    visibleBrandSummaries,
    visibleBrandStart,
    visibleBrandEnd,
    selectedBrand,
    selectedShare,
    brandComparisonSeries,
    availableComparisonBrandOptions,
    brandComparisonAxisMax,
    brandComparisonBaselineShare,
    brandComparisonChartSeries,
    averageEurKrwRate,
    brandGrowthPeriodLabel,
    brandYtdPeriodLabel,
    brandYoyByName,
    hasBrandQoqGrowth,
    hasBrandQuarterYoyGrowth,
    brandGrowthRows,
    risingBrandRows,
    decliningBrandRows,
    allRisingBrandRows,
    allDecliningBrandRows,
    brandQuarterTrend,
    brandQuarterTrendMax,
    brandGrowthBlock,
    selectedBrandMetrics,
    selectedSkuRows,
    allSelectedSkuRows,
    selectedTopSkuShare,
    skuConcentrationRows,
    allSkuConcentrationRows,
    countryDistributionRows,
    allCountryDistributionRows,
    lineCompositionRows,
    allLineCompositionRows,
    selectedBrandDisplayName,
    peakMonth,
    exportBrandReportPdf
  } = useBrandScreenModel({ reportBlocks, onToggleReportBlock });
  const totalBrandAmount = useMemo(
    () => brandSummaries.reduce((sum, row) => sum + row.amount, 0),
    [brandSummaries]
  );
  const [rankingDetail, setRankingDetail] = useState<"growth" | "decline" | "sku-concentration" | "country" | "line" | "top-sku" | null>(null);
  const risingDeltaTotal = allRisingBrandRows.reduce((sum, row) => sum + row.deltaAmount, 0);
  const decliningDeltaTotal = allDecliningBrandRows.reduce((sum, row) => sum + Math.abs(row.deltaAmount), 0);
  const rankingDetailConfig: {
    title: string;
    subtitle: string;
    valueLabel?: string;
    shareLabel?: string;
    rows?: RankingDetailRow[];
    columns?: RankingDetailColumn[];
  } | null =
    rankingDetail === "growth" || rankingDetail === "decline"
      ? {
          title: "브랜드별 성장·감소 전체 변화",
          subtitle: brandGrowthPeriodLabel,
          columns: [
            {
              key: "growth",
              label: "성장 상위",
              badge: { text: "상승", className: "bg-pos-bg text-pos" },
              valueLabel: "매출 증가",
              shareLabel: "증가 기여율",
              rows: allRisingBrandRows.map((row) => ({
                id: `up:${row.brand}`,
                label: displayBrandName(row.brand),
                detail: [row.growth, row.lowBase ? "낮은 기준값" : "", canViewAmountData ? `${wonEok(row.previousAmount)} → ${wonEok(row.currentAmount)}` : ""].filter(Boolean).join(" · "),
                ...(canViewAmountData ? { amount: signedEur(row.deltaAmount), amountKrw: signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate) } : {}),
                sharePct: risingDeltaTotal > 0 ? (row.deltaAmount / risingDeltaTotal) * 100 : 0
              }))
            },
            {
              key: "decline",
              label: "감소 상위",
              badge: { text: "하락", className: "bg-brand-50 text-brand" },
              valueLabel: "매출 감소",
              shareLabel: "감소 기여율",
              rows: allDecliningBrandRows.map((row) => ({
                id: `down:${row.brand}`,
                label: displayBrandName(row.brand),
                detail: [row.growth, row.lowBase ? "낮은 기준값" : "", canViewAmountData ? `${wonEok(row.previousAmount)} → ${wonEok(row.currentAmount)}` : ""].filter(Boolean).join(" · "),
                ...(canViewAmountData ? { amount: signedEur(row.deltaAmount), amountKrw: signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate) } : {}),
                sharePct: decliningDeltaTotal > 0 ? (Math.abs(row.deltaAmount) / decliningDeltaTotal) * 100 : 0
              }))
            }
          ]
        }
        : rankingDetail === "sku-concentration"
      ? {
          title: `${selectedBrandDisplayName} SKU 집중도 전체 순위`,
          subtitle: "브랜드 전체 매출 기준 · 매출액 및 점유율",
          rows: allSkuConcentrationRows.map((row) => ({
            id: row.sku,
            label: row.name,
            detail: [row.sku, row.category].filter(Boolean).join(" · "),
            ...(canViewAmountData ? { amount: wonEok(row.amount), amountKrw: row.amountKrw } : {}),
            sharePct: row.sharePct
          }))
        }
      : rankingDetail === "country"
        ? {
            title: `${selectedBrandDisplayName} 국가 분포 전체 순위`,
            subtitle: "선택 기간 브랜드 매출 기준",
            rows: allCountryDistributionRows.map((row) => ({
              id: row.name,
              label: row.name,
              ...(canViewAmountData ? { amount: row.amountDisplay, amountKrw: row.amountKrw } : {}),
              sharePct: row.sharePct
            }))
          }
        : rankingDetail === "line"
          ? {
              title: `${selectedBrandDisplayName} 제품군·라인 전체 순위`,
              subtitle: "선택 기간 브랜드 매출 기준",
              rows: allLineCompositionRows.map((row) => ({
                id: row.name,
                label: row.name,
                ...(canViewAmountData ? { amount: row.amountDisplay, amountKrw: row.amountKrw } : {}),
                sharePct: row.sharePct
              }))
            }
          : rankingDetail === "top-sku"
            ? {
                title: `${selectedBrandDisplayName} SKU 전체 순위`,
                subtitle: "선택 기간 판매금액 기준",
                rows: allSelectedSkuRows.map((row) => ({
                  id: row.sku,
                  label: row.name,
                  detail: [row.sku, row.category, `판매수량 ${formatNumber(row.qty)}`].filter(Boolean).join(" · "),
                  ...(canViewAmountData ? { amount: wonEok(row.amount), amountKrw: krwEokFromEur(row.amount, averageEurKrwRate) } : {}),
                  sharePct: row.sharePct
                }))
              }
            : null;

  return (
    <div className="mx-auto max-w-[1460px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
      <div className="mb-[20px]">
        <div className="flex items-center justify-between gap-3">
          <h2 className="whitespace-nowrap text-[18px] font-black leading-none text-ink">브랜드 기준 분석</h2>
          {canViewAmountData ? <button type="button" onClick={exportBrandReportPdf} disabled={exportingBrandPdf || !selectedBrand} className="inline-flex h-9 shrink-0 items-center gap-2 rounded-[10px] bg-brand px-3 text-[12px] font-black text-white transition hover:bg-brand/90 disabled:cursor-not-allowed disabled:opacity-70 sm:h-[38px] sm:px-[18px] sm:text-[13px]">
          <FileText className="h-4 w-4" />
          <span className="sm:hidden">{exportingBrandPdf ? "생성 중" : "리포트"}</span>
          <span className="hidden sm:inline">{exportingBrandPdf ? "PDF 생성 중" : "리포트로 내보내기"}</span>
        </button> : null}
        </div>
        <p className="mt-3 max-w-[620px] text-[12.5px] font-semibold leading-5 text-muted sm:mt-[11px] sm:text-[13px]">
          브랜드를 선택해 SKU별 판매 집중도와 국가별 매출 분포를 확인하세요.
        </p>
        <div className="mt-3 sm:mt-[12px]">
          <AnalysisPeriodBadge options={analysisOptions} />
          <AnalysisPeriodCaveat options={analysisOptions} />
        </div>
      </div>

      {loading ? <div className="rounded-[14px] border border-border bg-surface p-8 text-center text-[13px] font-black text-muted shadow-soft">브랜드 분석 데이터를 불러오는 중입니다.</div> : null}
      {!loading && (loadFailed || brandSummaries.length === 0) ? <div className="rounded-[14px] border border-border bg-surface p-8 text-center text-[13px] font-black text-muted shadow-soft">{loadFailed ? "브랜드 분석 데이터를 불러오지 못했습니다." : "브랜드 분석 결과가 없습니다. 데이터 입력에서 분석 시작을 먼저 실행해 주세요."}</div> : null}

      {!loading && !loadFailed && brandSummaries.length > 0 ? (
      <div className="grid items-start gap-[16px] xl:grid-cols-[600px_1fr]">
        <div className="grid content-start gap-[16px]">
        <section className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
          <div className="flex items-center justify-between border-b border-divider px-[20px] py-[16px]">
            <div>
              <h3 className="text-[15px] font-black text-ink">브랜드별 판매 순위</h3>
              <p className="mt-1 text-[11px] font-semibold text-muted2">금액 · 선택 기간 합계</p>
            </div>
            <span className="text-[12px] font-semibold text-muted2">
              {formatNumber(visibleBrandStart)}-{formatNumber(visibleBrandEnd)} / {formatNumber(brandSummaries.length)}
            </span>
          </div>
          {visibleBrandSummaries.map((row) => {
            const displayName = displayBrandName(row.brand);
            return (
              <BrandRankRow
                key={row.brand}
                rank={String(row.rank)}
                name={displayName}
                sales={canViewAmountData ? wonEok(row.amount) : `매출 비중 ${formatNumber(totalBrandAmount > 0 ? (row.amount / totalBrandAmount) * 100 : 0, 1)}%`}
                salesSub={canViewAmountData ? krwEokFromEur(row.amount, averageEurKrwRate) : undefined}
                share={canViewAmountData ? `매출 비중 ${formatNumber(totalBrandAmount > 0 ? (row.amount / totalBrandAmount) * 100 : 0, 1)}%` : undefined}
                growth={undefined}
                growthLabel={undefined}
                width={row.width}
                active={row.brand === selectedBrand?.brand}
                onClick={() => setSelectedBrandName(row.brand)}
              />
            );
          })}
          {brandPageCount > 1 ? (
            <div className="flex items-center justify-between border-t border-divider px-[18px] py-[12px]">
              <button
                type="button"
                onClick={() => setBrandPage((page) => Math.max(1, page - 1))}
                disabled={safeBrandPage <= 1}
                className="h-8 rounded-[8px] border border-border bg-surface px-3 text-[12px] font-black text-ink transition hover:border-brand disabled:cursor-not-allowed disabled:opacity-40"
              >
                이전
              </button>
              <span className="text-[12px] font-black text-muted2">
                {formatNumber(safeBrandPage)} / {formatNumber(brandPageCount)}
              </span>
              <button
                type="button"
                onClick={() => setBrandPage((page) => Math.min(brandPageCount, page + 1))}
                disabled={safeBrandPage >= brandPageCount}
                className="h-8 rounded-[8px] border border-border bg-surface px-3 text-[12px] font-black text-ink transition hover:border-brand disabled:cursor-not-allowed disabled:opacity-40"
              >
                다음
              </button>
            </div>
          ) : null}
        </section>
        <section className="flex flex-col overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
          <div className="border-b border-divider px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-[15px] font-black text-ink">브랜드별 성장 변화</h3>
                <p className="mt-1 text-[12px] font-semibold text-muted2">
                  {brandGrowthPeriodLabel} · 상승 {formatNumber(brandGrowthRows.filter((row) => row.value !== null && row.value > 0).length)}개 · 하락 {formatNumber(brandGrowthRows.filter((row) => row.value !== null && row.value < 0).length)}개
                </p>
              </div>
              <RankingDetailOpenButton onClick={() => setRankingDetail("growth")} />
            </div>
            <div className="mt-3 flex w-fit rounded-[12px] bg-segbg p-1 shadow-card">
              <button
                type="button"
                onClick={() => setBrandGrowthBasis("qoq")}
                disabled={!hasBrandQoqGrowth}
                className={cn(
                  "h-8 rounded-[8px] px-3 text-[12px] font-black transition disabled:cursor-not-allowed disabled:opacity-40",
                  brandGrowthBasis === "qoq" ? "bg-surface text-ink shadow-soft" : "text-muted hover:text-ink"
                )}
              >
                분기 QoQ
              </button>
              <button
                type="button"
                onClick={() => setBrandGrowthBasis("yoy")}
                disabled={!hasBrandQuarterYoyGrowth}
                className={cn(
                  "h-8 rounded-[8px] px-3 text-[12px] font-black transition disabled:cursor-not-allowed disabled:opacity-40",
                  brandGrowthBasis === "yoy" ? "bg-surface text-ink shadow-soft" : "text-muted hover:text-ink"
                )}
              >
                분기 YoY
              </button>
            </div>
            <div className="mt-3 flex flex-col items-stretch gap-1.5 rounded-[10px] border border-border bg-surface p-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
                <label className="flex h-9 w-full items-center justify-between gap-2 rounded-[8px] bg-surface-soft px-2.5 text-[11px] font-black text-muted2 sm:w-auto">
                  기준 분기
                  <select
                    aria-label={`브랜드 성장 ${brandGrowthBasis === "yoy" ? "YoY" : "QoQ"} 기준 분기`}
                    value={brandGrowthTargetQuarter}
                    onChange={(event) => setBrandGrowthTargetQuarter(event.target.value)}
                    className="h-8 rounded-[8px] border border-border bg-surface px-2.5 text-[12px] font-black text-ink outline-none focus:border-brand"
                  >
                    {activeBrandQuarterOptions.map((quarter) => (
                      <option key={quarter} value={quarter}>{formatQuarterLabel(quarter)}</option>
                    ))}
                  </select>
                </label>
                <ArrowLeftRight className="hidden h-4 w-4 text-muted2 sm:block" aria-hidden="true" />
                <div
                  aria-label={`브랜드 성장 ${brandGrowthBasis === "yoy" ? "YoY" : "QoQ"} 자동 비교 분기`}
                  className="flex h-9 w-full items-center gap-2 rounded-[8px] bg-surface-soft px-2.5 text-[11px] font-black text-muted2 sm:h-8 sm:w-auto sm:justify-start sm:border sm:border-border sm:bg-surface"
                >
                  비교 분기
                  <strong className="ml-auto text-[12px] text-ink">
                    {formatQuarterLabel(brandGrowthComparisonQuarter)}
                  </strong>
                  <span>자동</span>
                </div>
                <span className="hidden text-left text-[11px] font-bold text-muted2 sm:block sm:w-auto">
                  {brandGrowthBasis === "yoy" ? "전년도 동일 분기" : "직전 완료 분기"}
                </span>
            </div>
            <p className="mt-2 text-[11px] font-semibold text-muted2">
              완료된 3개월이 모두 있는 분기만 사용합니다. {canViewAmountData ? <>비교 분기 매출 {lowBaseAmountLabel()} 미만은 낮은 기준값으로 표시하며 순위에는 포함합니다. </> : null}비교 분기 매출이 없는 브랜드는 별도로 집계합니다.
            </p>
          </div>
          <div className="grid flex-1 md:grid-cols-2">
            <div className="border-b border-divider p-4 md:border-b-0 md:border-r">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[12.5px] font-black text-ink">
                  성장 상위 <span className="font-semibold text-muted2">· 증감률 표시</span>
                </p>
                <span className="rounded-full bg-pos-bg px-2.5 py-1 text-[11px] font-black text-pos">상승</span>
              </div>
              <div>
                {risingBrandRows.length > 0 ? risingBrandRows.map((row, index) => (
                  <button
                    key={row.brand}
                    type="button"
                    onClick={() => setSelectedBrandName(row.brand)}
                    className="grid w-full grid-cols-[24px_minmax(0,1fr)_auto] items-center gap-2 border-b border-rowline py-2.5 text-left last:border-b-0 hover:bg-surface-soft"
                  >
                    <span className="text-[12px] font-black text-muted2">{index + 1}</span>
                    <span className="min-w-0">
                      <span className="flex min-w-0 items-center gap-1.5">
                        <span className="truncate text-[12.5px] font-black text-ink">{displayBrandName(row.brand)}</span>
                        {row.lowBase ? <span className="shrink-0 rounded-full bg-amber-50 px-1.5 py-0.5 text-[9px] font-black text-amber-700">낮은 기준값</span> : null}
                      </span>
                    </span>
                    <span className="text-right">
                      <span className="flex items-baseline justify-end gap-1.5">
                        {canViewAmountData ? <span className="text-[13px] font-black text-pos">{signedEur(row.deltaAmount)}</span> : null}
                        <span className="text-[10.5px] font-black text-pos">({row.growth})</span>
                      </span>
                      {canViewAmountData && signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate) ? (
                        <span className="mt-0.5 block text-[10.5px] font-bold text-muted2">
                          {signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate)}
                        </span>
                      ) : null}
                      {canViewAmountData ? <span className="mt-0.5 block text-[10.5px] font-bold text-muted2">
                        {wonEok(row.previousAmount)} → {wonEok(row.currentAmount)}
                      </span> : null}
                    </span>
                  </button>
                )) : <p className="py-6 text-center text-[12px] font-semibold text-muted2">상승한 브랜드가 없습니다.</p>}
              </div>
            </div>
            <div className="p-4">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[12.5px] font-black text-ink">
                  감소 상위 <span className="font-semibold text-muted2">· 증감률 표시</span>
                </p>
                <span className="rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-black text-brand">하락</span>
              </div>
              <div>
                {decliningBrandRows.length > 0 ? decliningBrandRows.map((row, index) => (
                  <button
                    key={row.brand}
                    type="button"
                    onClick={() => setSelectedBrandName(row.brand)}
                    className="grid w-full grid-cols-[24px_minmax(0,1fr)_auto] items-center gap-2 border-b border-rowline py-2.5 text-left last:border-b-0 hover:bg-surface-soft"
                  >
                    <span className="text-[12px] font-black text-muted2">{index + 1}</span>
                    <span className="min-w-0">
                      <span className="flex min-w-0 items-center gap-1.5">
                        <span className="truncate text-[12.5px] font-black text-ink">{displayBrandName(row.brand)}</span>
                        {row.lowBase ? <span className="shrink-0 rounded-full bg-amber-50 px-1.5 py-0.5 text-[9px] font-black text-amber-700">낮은 기준값</span> : null}
                      </span>
                    </span>
                    <span className="text-right">
                      <span className="flex items-baseline justify-end gap-1.5">
                        {canViewAmountData ? <span className="text-[13px] font-black text-brand">{signedEur(row.deltaAmount)}</span> : null}
                        <span className="text-[10.5px] font-black text-brand">({row.growth})</span>
                      </span>
                      {canViewAmountData && signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate) ? (
                        <span className="mt-0.5 block text-[10.5px] font-bold text-muted2">
                          {signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate)}
                        </span>
                      ) : null}
                      {canViewAmountData ? <span className="mt-0.5 block text-[10.5px] font-bold text-muted2">
                        {wonEok(row.previousAmount)} → {wonEok(row.currentAmount)}
                      </span> : null}
                      {row.vanished ? <span className="mt-0.5 block text-[9.5px] font-black text-brand">판매 소멸</span> : null}
                    </span>
                  </button>
                )) : <p className="py-6 text-center text-[12px] font-semibold text-muted2">하락한 브랜드가 없습니다.</p>}
              </div>
            </div>
          </div>
          <div className="border-t border-divider px-4 py-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-[12.5px] font-black text-ink">
                  {brandQuarterTrend.length >= 4 ? "최근 분기별 브랜드 매출 추세" : "브랜드 분기 매출 비교"}
                </p>
                <p className="mt-1 text-[11px] font-semibold text-muted2">
                  완료 분기 기준 · {brandQuarterTrend.length >= 4 ? "최대 최근 8개 분기" : `${formatNumber(brandQuarterTrend.length)}개 분기`} · 비중은 표시된 기간 내 분기별 비중
                </p>
              </div>
              <span className="text-[11px] font-semibold text-muted2">전체 브랜드</span>
            </div>
            {brandQuarterTrend.length > 0 ? (
              <div className="grid min-h-[150px] grid-cols-4 items-end gap-2 sm:grid-cols-8">
                {brandQuarterTrend.map((row) => {
                  const badgeValue = brandQuarterTrend.length >= 4 ? row.yoy : row.qoq;
                  return (
                  <div key={row.quarter} className="flex min-w-0 flex-col items-center justify-end">
                    <div className="mb-1 h-4">
                      {badgeValue ? (
                        <span className={cn("block truncate text-[10px] font-black", badgeValue.startsWith("-") ? "text-brand" : "text-pos")}>
                          {badgeValue}
                        </span>
                      ) : null}
                    </div>
                    <div className="flex h-[88px] w-full items-end justify-center rounded-t-[6px] bg-surface-soft px-1">
                      <div
                        className="w-full max-w-[34px] rounded-t-[5px] bg-brand/75"
                        style={{ height: `${Math.max(6, (row.amount / brandQuarterTrendMax) * 100)}%` }}
                        title={
                          canViewAmountData
                            ? `${row.label} · ${wonEok(row.amount)} · 기간 내 비중 ${row.share !== null ? `${row.share.toFixed(1)}%` : "-"}`
                            : `${row.label} · 기간 내 비중 ${row.share !== null ? `${row.share.toFixed(1)}%` : "-"}`
                        }
                      />
                    </div>
                    <span className="mt-1 truncate text-[9.5px] font-black text-muted2">{row.label}</span>
                    {canViewAmountData ? (
                      <>
                        <span className="mt-0.5 truncate text-[9px] font-semibold text-muted">{wonEok(row.amount)}</span>
                        {krwEokFromEur(row.amount, averageEurKrwRate) ? (
                          <span className="mt-0.5 truncate text-[8.5px] font-semibold text-muted">
                            {krwEokFromEur(row.amount, averageEurKrwRate)}
                          </span>
                        ) : null}
                      </>
                    ) : null}
                    <span className="mt-0.5 truncate text-[9px] font-black text-muted2">
                      {row.share !== null ? `기간 비중 ${row.share.toFixed(1)}%` : "기간 비중 -"}
                    </span>
                  </div>
                  );
                })}
              </div>
            ) : (
              <p className="py-6 text-center text-[12px] font-semibold text-muted2">완료된 분기 데이터가 없습니다.</p>
            )}
          </div>
        </section>
        </div>
        {selectedBrand ? (
        <div className="grid gap-[16px]">
          <section className="overflow-hidden rounded-[14px] border border-border bg-surface shadow-soft">
            <div className="flex items-start justify-between gap-4 px-[20px] py-[18px]">
              <div className="min-w-0">
                <p className="text-[12px] font-semibold text-muted2">선택 브랜드</p>
                <h3 className="mt-[5px] text-[23px] font-black leading-none text-ink">{selectedBrandDisplayName}</h3>
              </div>
              <p className="shrink-0 whitespace-nowrap text-right text-[12px] font-black text-brand">점유율 {formatNumber(selectedShare, 1)}%</p>
            </div>
            <div className="grid grid-cols-4 border-t border-divider">
              {selectedBrandMetrics.filter(([label]) => canViewAmountData || !isAmountField(label)).map(([label, value]) => <BrandMetricBox key={label} label={label} value={value} />)}
            </div>
          </section>
          <div className="grid min-w-0 grid-cols-2 gap-[16px]">
            <section className="min-w-0 rounded-[14px] border border-border bg-surface p-[20px] shadow-soft">
              <div className="mb-[15px] flex items-center justify-between gap-3">
                <h3 className="text-[14px] font-black text-ink">SKU 집중도 <span className="font-semibold text-muted2">· TOP 5 SKU가 브랜드 전체 매출의 {formatNumber(selectedTopSkuShare, 1)}% 차지</span></h3>
                <div className="flex items-center gap-2">
                  <RankingDetailOpenButton onClick={() => setRankingDetail("sku-concentration")} />
                </div>
              </div>
              <div className="grid gap-[13px]">{skuConcentrationRows.map((row, index) => <BrandBar key={`${row.sku}-${index}`} name={row.name} code={row.sku} value={canViewAmountData ? row.value : `${formatNumber(row.sharePct, 1)}%`} width={row.width} />)}</div>
            </section>
            <section className="min-w-0 rounded-[14px] border border-border bg-surface p-[20px] shadow-soft">
              <div className="mb-[15px] flex items-center justify-between gap-3">
                <h3 className="text-[14px] font-black text-ink">국가 분포 <span className="font-semibold text-muted2">· TOP 5 · 선택 기간 기준</span></h3>
                <div className="flex items-center gap-2">
                  <RankingDetailOpenButton onClick={() => setRankingDetail("country")} />
                </div>
              </div>
              <div className="grid gap-[13px]">{countryDistributionRows.map((row, index) => <BrandBar key={`${row.name}-${index}`} name={row.name} value={canViewAmountData ? row.value : `${formatNumber(row.sharePct, 1)}%`} width={row.width} detail={row.detail} />)}</div>
            </section>
          </div>
          <section className="rounded-[14px] border border-border bg-surface p-[20px] shadow-soft">
            <div className="mb-[15px] flex items-center justify-between gap-3">
              <h3 className="text-[14px] font-black text-ink">제품군 · 라인 구성비 <span className="font-semibold text-muted2">· TOP 5 · 선택 기간 기준</span></h3>
              <div className="flex items-center gap-2">
                <RankingDetailOpenButton onClick={() => setRankingDetail("line")} />
              </div>
            </div>
            <div className="grid gap-[13px]">{lineCompositionRows.map((row, index) => <BrandBar key={`${row.name}-${index}`} name={row.name} value={canViewAmountData ? row.value : `${formatNumber(row.sharePct, 1)}%`} width={row.width} />)}</div>
          </section>
          <section className="flex min-h-[440px] flex-col rounded-[14px] border border-border bg-surface p-[20px] shadow-soft">
            <div className="mb-[13px] flex items-center justify-between gap-3">
              <h3 className="text-[14px] font-black text-ink">
                상위 SKU 상세 <span className="font-semibold text-muted2">· TOP 5 · 선택 기간 판매금액 기준</span>
              </h3>
              <div className="flex items-center gap-2">
                <RankingDetailOpenButton onClick={() => setRankingDetail("top-sku")} />
              </div>
            </div>
            <div className={cn("grid items-center border-b border-divider pb-2 text-[11px] font-black text-muted2", canViewAmountData ? "grid-cols-[minmax(0,1fr)_100px_72px]" : "grid-cols-[minmax(0,1fr)_72px]")}>
              <span>상품</span>
              {canViewAmountData ? <span className="text-right">매출</span> : null}
              <span className="text-right">판매수량</span>
            </div>
            <div className="flex-1">
              {selectedSkuRows.map((row) => (
                <div key={row.sku} className={cn("grid items-center border-b border-rowline py-[10px] last:border-b-0", canViewAmountData ? "grid-cols-[minmax(0,1fr)_100px_72px]" : "grid-cols-[minmax(0,1fr)_72px]")}>
                  <div className="min-w-0">
                    <SkuNameWithCode name={row.name} sku={row.sku} />
                    <p className="mt-[2px] text-[12px] font-semibold text-muted2">{row.category}</p>
                  </div>
                  {canViewAmountData ? <div className="text-right">
                    <p className="text-[13px] font-black text-ink">{wonEok(row.amount)}</p>
                    {krwEokFromEur(row.amount, averageEurKrwRate) ? (
                      <p className="mt-[2px] text-[11px] font-black text-muted2">{krwEokFromEur(row.amount, averageEurKrwRate)}</p>
                    ) : null}
                  </div> : null}
                  <p className="text-right text-[12px] font-semibold text-ink3">{formatNumber(row.qty)}</p>
                </div>
              ))}
            </div>
          </section>
        </div>
        ) : (
        <section className="rounded-[14px] border border-dashed border-border bg-surface px-[24px] py-[36px] text-center shadow-soft">
          <p className="text-[15px] font-black text-ink">브랜드를 선택해 주세요</p>
          <p className="mt-3 text-[13px] font-semibold leading-6 text-muted">
            왼쪽 판매 순위에서 브랜드명을 클릭하면 선택 브랜드, SKU 집중도, 국가 분포, 제품군 구성비, 상위 SKU 탭이 표시됩니다.
          </p>
        </section>
        )}
        {selectedBrand ? (
          <div className="xl:col-span-2">
              <div className="rounded-[14px] border border-border bg-surface p-[16px] shadow-soft">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[13px] font-black text-ink">브랜드별 월 매출 분포</p>
                    <p className="mt-[4px] text-[12px] font-semibold text-muted2">완료월 기준 · 브랜드별 유효 월 비중 합계 100% · 최대 6개 · 제외 {formatNumber(brandExcludedMonthCount)}개월</p>
                  </div>
                </div>
                <div className="mt-3 flex items-center justify-between gap-3">
                  <BrandSearchSelect
                    value={BRAND_COMPARISON_PICKER}
                    options={comparisonBrands.length >= 6 ? [] : availableComparisonBrandOptions}
                    allValue={BRAND_COMPARISON_PICKER}
                    allLabel="브랜드 추가"
                    getOptionLabel={displayBrandName}
                    dropdownAlign="right"
                    onChange={(brand) => {
                      if (brand === BRAND_COMPARISON_PICKER) return;
                      setComparisonBrands((current) => current.includes(brand) ? current : [...current, brand].slice(0, 6));
                    }}
                  />
                  <span className="text-[11px] font-bold text-muted2">최대 6개 · {formatNumber(comparisonBrands.length)}개 선택</span>
                </div>
                {comparisonBrands.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {comparisonBrands.map((brand, index) => {
                      const series = brandComparisonSeries.find((item) => item.brand === brand);
                      return (
                        <span key={brand} className="inline-flex items-center gap-2 rounded-[10px] border border-border bg-surface px-2.5 py-1.5 text-ink">
                          <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: trendLineColors[index % trendLineColors.length] }} />
                          <span>
                            <span className="block text-[11px] font-black">{displayBrandName(brand)}</span>
                            <span className="mt-0.5 block text-[10.5px] font-black" style={{ color: trendLineColors[index % trendLineColors.length] }}>
                              {series && series.peakMonth > 0 ? `최고월 ${series.peakMonth}월 · ${formatNumber(series.peakShare, 1)}%` : "최고월 -"}
                            </span>
                          </span>
                          <button
                            type="button"
                            aria-label={`${displayBrandName(brand)} 비교에서 제거`}
                            onClick={() => {
                              setComparisonBrands((current) => current.filter((item) => item !== brand));
                              setBrandComparisonTooltip((current) => current?.brand === brand ? null : current);
                            }}
                            className="text-muted2 transition hover:text-brand"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      );
                    })}
                  </div>
                ) : null}
                {brandComparisonChartSeries.length > 0 ? (
                  <div className="relative mt-4">
                  <svg
                    role="img"
                    aria-label="선택 브랜드별 완료월 월 매출 분포 비교 그래프"
                    viewBox="0 0 1220 230"
                    className="h-auto w-full overflow-visible"
                  >
                    {[50, 120, 190].map((y, index) => {
                      const guideValue = index === 0 ? brandComparisonAxisMax : index === 1 ? brandComparisonAxisMax / 2 : 0;
                      return (
                        <g key={y}>
                          <line x1="52" x2="1180" y1={y} y2={y} className="stroke-divider" strokeDasharray={index === 2 ? undefined : "4 5"} />
                          <text x="44" y={y + 3} textAnchor="end" className="fill-muted2 text-[9px] font-semibold">{formatNumber(guideValue, index === 1 ? 1 : 0)}%</text>
                        </g>
                      );
                    })}
                    {brandComparisonBaselineShare !== null && brandComparisonBaselineShare <= brandComparisonAxisMax ? (() => {
                      const baselineY = 190 - (brandComparisonBaselineShare / brandComparisonAxisMax) * 140;
                      return (
                        <g key="equal-distribution-baseline">
                          <line x1="52" x2="1180" y1={baselineY} y2={baselineY} stroke="var(--muted2)" strokeDasharray="2 4" opacity="0.8" />
                          <text x="1180" y={baselineY - 4} textAnchor="end" className="fill-muted2 text-[9px] font-semibold">균등 분포 {formatNumber(brandComparisonBaselineShare, 1)}%</text>
                        </g>
                      );
                    })() : null}
                    {brandComparisonChartSeries.map((series) => {
                      const seriesActive = brandComparisonTooltip?.brand === series.brand;
                      return (
                      <g key={series.brand} opacity={brandComparisonTooltip && !seriesActive ? 0.2 : 1} className="transition-opacity duration-150">
                        {series.points.slice(0, -1).map((row, index) => {
                          const next = series.points[index + 1];
                          if (row.share === null || next.share === null) return null;
                          return (
                            <line
                              key={`${row.month}-${next.month}`}
                              x1={row.x}
                              y1={row.y}
                              x2={next.x}
                              y2={next.y}
                              stroke={series.color}
                              strokeWidth={seriesActive ? 3.5 : 2.25}
                              strokeLinecap="round"
                              vectorEffect="non-scaling-stroke"
                            />
                          );
                        })}
                        {series.points.map((row) => {
                          if (row.share === null) {
                            return (
                              <g key={row.month} aria-label={`${displayBrandName(series.brand)} ${row.month}월 데이터 없음`}>
                                <text x={row.x} y="204" textAnchor="middle" className="fill-muted2 text-[10px] font-black">—</text>
                              </g>
                            );
                          }
                          const pointActive = seriesActive && brandComparisonTooltip?.month === row.month;
                          const isPeak = row.month === series.peakMonth && row.amount > 0;
                          const tooltipPoint = {
                            brand: series.brand,
                             month: row.month,
                             share: row.share,
                             amount: row.amount,
                             observationCount: row.observationCount,
                             totalAmount: series.totalAmount,
                            color: series.color,
                            x: row.x,
                            y: row.y
                          };
                          return (
                            <g key={row.month}>
                              <circle cx={row.x} cy={row.y} r={pointActive ? 5.5 : isPeak ? 4.5 : 2.75} fill={pointActive || isPeak ? series.color : "var(--surface)"} stroke={series.color} strokeWidth={pointActive ? 2.5 : 1.75} vectorEffect="non-scaling-stroke" pointerEvents="none" />
                              <circle
                                data-chart-point="brand-comparison"
                                data-brand={series.brand}
                                data-month={row.month}
                                cx={row.x}
                                cy={row.y}
                                r="11"
                                fill="transparent"
                                className="cursor-crosshair outline-none"
                                tabIndex={0}
                                aria-label={`${displayBrandName(series.brand)} ${row.month}월 유효 월 매출 비중 ${formatNumber(row.share, 1)}%, 관측 ${formatNumber(row.observationCount)}개월${canViewAmountData ? `, 월평균 매출 ${wonEok(row.amount)}` : ""}`}
                                onMouseEnter={() => setBrandComparisonTooltip(tooltipPoint)}
                                onMouseLeave={() => setBrandComparisonTooltip(null)}
                                onFocus={() => setBrandComparisonTooltip(tooltipPoint)}
                                onBlur={() => setBrandComparisonTooltip(null)}
                                onClick={() => setBrandComparisonTooltip((current) => current?.brand === series.brand && current.month === row.month ? null : tooltipPoint)}
                              >
                                <title>{`${displayBrandName(series.brand)} · ${row.month}월 · 유효 월 매출 비중 ${formatNumber(row.share, 1)}% · 관측 ${formatNumber(row.observationCount)}개월${canViewAmountData ? ` · 월평균 ${wonEok(row.amount)}` : ""}`}</title>
                              </circle>
                              <text
                                data-share-label="brand-comparison"
                                x={row.x}
                                y={Math.max(11, row.y - 8 - (series.colorIndex % 3) * 9)}
                                textAnchor="middle"
                                fontSize="8"
                                fontWeight="900"
                                fill={series.color}
                                stroke="var(--surface)"
                                strokeWidth="3"
                                paintOrder="stroke"
                                pointerEvents="none"
                              >
                                {formatNumber(row.share, 1)}%
                              </text>
                            </g>
                          );
                        })}
                      </g>
                      );
                    })}
                    {brandSeasonMonths.map((month, index) => {
                      const x = brandSeasonMonths.length > 1 ? 52 + (index * 1128) / (brandSeasonMonths.length - 1) : 616;
                      return <text key={month} x={x} y="220" textAnchor="middle" className="fill-muted2 text-[9px] font-semibold">{month}월</text>;
                    })}
                  </svg>
                  {brandComparisonTooltip ? (
                    <div
                      data-chart-tooltip="brand-comparison"
                      className="pointer-events-none absolute z-20 w-[210px] rounded-[10px] border border-border bg-surface px-3 py-2.5 text-left shadow-soft"
                      style={{
                        left: `${Math.min(Math.max((brandComparisonTooltip.x / 1220) * 100, 18), 82)}%`,
                        top: "4px",
                        transform: "translateX(-50%)"
                      }}
                    >
                      <div className="flex items-center gap-2">
                        <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: brandComparisonTooltip.color }} />
                        <p className="truncate text-[12px] font-black text-ink">{displayBrandName(brandComparisonTooltip.brand)}</p>
                      </div>
                      <p className="mt-1.5 text-[11px] font-bold text-muted">{brandComparisonTooltip.month}월 · 유효 월 매출 비중 {formatNumber(brandComparisonTooltip.share, 1)}%</p>
                      {canViewAmountData ? <>
                        <p className="mt-1 text-[11px] font-black text-ink">월평균 매출 {wonEok(brandComparisonTooltip.amount)}</p>
                        <p className="mt-0.5 text-[10px] font-bold text-muted2">{krwEokFromEur(brandComparisonTooltip.amount, averageEurKrwRate) || "원화 환산 정보 없음"}</p>
                      </> : null}
                      <p className="mt-1 border-t border-divider pt-1 text-[10px] font-bold text-muted2">관측 완료월 {formatNumber(brandComparisonTooltip.observationCount)}개월{canViewAmountData ? ` · 월평균 프로필 합계 ${wonEok(brandComparisonTooltip.totalAmount)}` : ""}</p>
                    </div>
                  ) : null}
                  </div>
                ) : (
                  <p className="py-8 text-center text-[12px] font-semibold text-muted2">비교할 브랜드를 추가해 주세요.</p>
                )}
              </div>
            </div>
        ) : null}
      </div>
      ) : null}
      <RankingDetailDialog
        open={rankingDetailConfig !== null}
        title={rankingDetailConfig?.title ?? ""}
        subtitle={rankingDetailConfig?.subtitle}
        valueLabel={rankingDetailConfig?.valueLabel}
        shareLabel={rankingDetailConfig?.shareLabel}
        rows={rankingDetailConfig?.rows}
        columns={rankingDetailConfig?.columns}
        onClose={() => setRankingDetail(null)}
      />
    </div>
  );
}
