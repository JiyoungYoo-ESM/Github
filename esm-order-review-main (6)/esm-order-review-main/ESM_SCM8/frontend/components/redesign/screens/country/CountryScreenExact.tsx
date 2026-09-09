"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, FileText } from "lucide-react";
import { getSeasonTrendAnalysis } from "@/lib/api";
import { displayBrandName } from "@/lib/brand-display";
import { lowBaseAmountLabel } from "@/lib/low-base";
import {
  amountOf,
  brandOf,
  buildCountrySummary,
  category1Of,
  category2Of,
  countryOf,
  monthKeyOf,
  productNameOf,
  skuCodeOf
} from "@/lib/global-demand-view-model";
import { completeSeasonMonthKeys } from "@/lib/season-calendar";
import { cn, formatNumber } from "@/lib/utils";
import type { MonthCoverage } from "@/types/api";
import type { ComparisonBasis, ReportBlock, Screen } from "../../lib/types";
import {
  krwEokFromEur,
  signedEur,
  signedKrwEokFromEur,
  wonEok
} from "../../lib/currency-format";
import { escapeReportHtml } from "../../lib/report-html";
import { reportAnalysisPeriodParams } from "../../lib/workspace-format";
import { AnalysisPeriodBadge, AnalysisPeriodCaveat } from "../../shared/AnalysisPeriod";
import { BrandBar, SkuNameWithCode } from "../../shared/BrandBar";
import { OrderMetricCard } from "../../shared/OrderMetricCard";
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
  compactYoyPeriodLabel,
  growthDisplayLabel,
  growthLabelsForMonthPair,
  growthBadgeClass,
  isGrowthStatusLabel,
  latestComparableMonths,
  previousMonthKey,
  previousYearMonthKey,
  shortMonthPairLabel,
  yoyBucketOf
} from "../../lib/yoy-comparison";

import { CountryRankRow, ShareCard } from "./CountryScreenParts";
import { formatQuarterLabel } from "./country-quarter-growth";
import { useCountryScreenData } from "./useCountryScreenData";
import { useCountryScreenModel } from "./useCountryScreenModel";
import { useUserPermissions } from "@/lib/use-user-permissions";

export function CountryScreenExact({
  reportBlocks,
  onToggleReportBlock,
  onSyncReportBlock,
  onNavigate
}: {
  reportBlocks: ReportBlock[];
  onToggleReportBlock: (block: ReportBlock) => void;
  onSyncReportBlock: (block: ReportBlock) => void;
  onNavigate: (screen: Screen) => void;
}) {
  const { canViewAmountData } = useUserPermissions();
  const {
    loading,
    loadFailed,
    analysisOptions,
    setSelectedCountry,
    selectedRegion,
    setSelectedRegion,
    countryGrowthBasis,
    setCountryGrowthBasis,
    countryGrowthTargetQuarter,
    setCountryGrowthTargetQuarter,
    countryGrowthComparisonQuarter,
    activeCountryQuarterOptions,
    exportingCountryPdf,
    setCountryPage,
    countryRows,
    totalAmount,
    activeCountryCount,
    brandCountDisplay,
    skuCountDisplay,
    staleCountCaveat,
    countryMetricDeltas,
    averageEurKrwRate,
    totalAmountKrw,
    effectiveCountry,
    selectedCountryRow,
    selectedCountryShare,
    countryYtdPeriodLabel,
    rankRows,
    hasCountryQoqGrowth,
    hasCountryQuarterYoyGrowth,
    countryGrowthRows,
    risingCountryRows,
    decliningCountryRows,
    allRisingCountryRows,
    allDecliningCountryRows,
    countryGrowthPeriodLabel,
    countryQuarterTrend,
    countryQuarterTrendMax,
    countryGrowthBlock,
    countryPageCount,
    safeCountryPage,
    visibleRankRows,
    visibleCountryStart,
    visibleCountryEnd,
    regionRows,
    selectedSkuRows,
    allSelectedSkuRows,
    selectedSkuTotalAmount,
    selectedBrandRows,
    allSelectedBrandRows,
    selectedPeakMonth,
    selectedPeakMonthLabel,
    selectedPeakShare,
    selectedSeasonChartMaxShare,
    selectedSeasonChartPoints,
    selectedSeasonChartSegments,
    selectedTopCategories,
    allSelectedTopCategories,
    exportCountryReportPdf
  } = useCountryScreenModel({ reportBlocks, onToggleReportBlock, onSyncReportBlock, onNavigate });
  const [rankingDetail, setRankingDetail] = useState<"growth" | "decline" | "brand" | "category" | "sku" | null>(null);
  const risingDeltaTotal = allRisingCountryRows.reduce((sum, row) => sum + row.deltaAmount, 0);
  const decliningDeltaTotal = allDecliningCountryRows.reduce((sum, row) => sum + Math.abs(row.deltaAmount), 0);
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
          title: `국가별 성장·감소 전체 변화`,
          subtitle: countryGrowthPeriodLabel,
          columns: [
            {
              key: "growth",
              label: "성장 상위",
              badge: { text: "상승", className: "bg-pos-bg text-pos" },
              valueLabel: "매출 증가",
              shareLabel: "증가 기여율",
              rows: allRisingCountryRows.map((row) => ({
                id: `up:${row.country}`,
                label: row.country,
                detail: [row.region, row.growth, row.lowBase ? "낮은 기준값" : "", canViewAmountData ? `${wonEok(row.previousAmount)} → ${wonEok(row.currentAmount)}` : ""].filter(Boolean).join(" · "),
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
              rows: allDecliningCountryRows.map((row) => ({
                id: `down:${row.country}`,
                label: row.country,
                detail: [row.region, row.growth, row.lowBase ? "낮은 기준값" : "", canViewAmountData ? `${wonEok(row.previousAmount)} → ${wonEok(row.currentAmount)}` : ""].filter(Boolean).join(" · "),
                ...(canViewAmountData ? { amount: signedEur(row.deltaAmount), amountKrw: signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate) } : {}),
                sharePct: decliningDeltaTotal > 0 ? (Math.abs(row.deltaAmount) / decliningDeltaTotal) * 100 : 0
              }))
            }
          ]
        }
        : rankingDetail === "brand"
      ? {
          title: `${effectiveCountry || "선택 국가"} 브랜드 전체 순위`,
          subtitle: "선택 기간 국가 매출 기준",
          rows: allSelectedBrandRows.map((row) => ({
            id: row.brand,
            label: displayBrandName(row.brand),
            ...(canViewAmountData ? { amount: wonEok(row.amount), amountKrw: krwEokFromEur(row.amount, averageEurKrwRate) } : {}),
            sharePct: row.sharePct
          }))
        }
      : rankingDetail === "category"
        ? {
            title: `${effectiveCountry || "선택 국가"} 카테고리 전체 순위`,
            subtitle: "선택 기간 국가 매출 기준",
            rows: allSelectedTopCategories.map((row) => ({
              id: row.category,
              label: row.category,
              ...(canViewAmountData ? { amount: wonEok(row.amount), amountKrw: krwEokFromEur(row.amount, averageEurKrwRate) } : {}),
              sharePct: row.sharePct
            }))
          }
        : rankingDetail === "sku"
          ? {
              title: `${effectiveCountry || "선택 국가"} SKU 전체 순위`,
              subtitle: "선택 기간 판매금액 기준",
              rows: allSelectedSkuRows.map((row) => ({
                id: row.sku,
                label: row.name,
                detail: [row.sku, displayBrandName(row.brand)].filter(Boolean).join(" · "),
                ...(canViewAmountData ? { amount: wonEok(row.amount), amountKrw: krwEokFromEur(row.amount, averageEurKrwRate) } : {}),
                sharePct: selectedSkuTotalAmount > 0 ? (row.amount / selectedSkuTotalAmount) * 100 : 0
              }))
            }
          : null;

  const warehouseCode = String(analysisOptions?.warehouse ?? "").trim().toUpperCase();
  const isHqResult =
    String(analysisOptions?.entity_code ?? "").toUpperCase() === "HQ" || warehouseCode !== "";
  const warehouseLabel = warehouseCode
    ? warehouseCode === "OPO"
      ? "오포창고 (OPO)"
      : warehouseCode
    : "전체 창고";
  const showAllWarehouseWarning = isHqResult && warehouseCode === "";

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-5 sm:px-6 sm:py-6 lg:px-0 lg:py-[24px]">
      <div className="mb-[20px] flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-[17px] font-black leading-none text-ink">국가 · 권역 기준 판매 인사이트</h2>
          <p className="mt-[10px] text-[13px] font-semibold leading-none text-muted">
            &quot;어느 국가에서 가장 잘 팔리는가?&quot; — 권역과 국가를 선택하면 강한 브랜드 · SKU · 시즌성이 함께 갱신됩니다.
          </p>
          <div className="mt-[12px]">
            <AnalysisPeriodBadge options={analysisOptions} />
            {isHqResult ? (
              <span
                className={cn(
                  "ml-2 inline-flex h-[30px] items-center rounded-full border px-[14px] text-[13px] font-black",
                  showAllWarehouseWarning
                    ? "border-amber-300 bg-amber-50 text-amber-700"
                    : "border-border bg-surface text-muted2"
                )}
              >
                본사 창고: {warehouseLabel}
              </span>
            ) : null}
            <AnalysisPeriodCaveat options={analysisOptions} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          {canViewAmountData ? <button
            type="button"
            onClick={exportCountryReportPdf}
            disabled={exportingCountryPdf}
            className="inline-flex h-[38px] items-center gap-2 rounded-[10px] bg-brand px-4 text-[13px] font-black text-white transition hover:bg-brand/90 disabled:cursor-not-allowed disabled:opacity-70"
          >
            <FileText className="h-4 w-4" />
            {exportingCountryPdf ? "PDF 생성 중" : "리포트로 내보내기"}
          </button> : null}
        </div>
      </div>

      {!loading && showAllWarehouseWarning && countryRows.length > 0 ? (
        <div className="mb-4 rounded-[12px] border border-amber-300 bg-amber-50 px-4 py-3 text-[12.5px] font-bold leading-[1.6] text-amber-800">
          이 결과는 <strong className="font-black">전체 창고</strong> 기준입니다 — 자사·계열 창고 출고분(자사간거래 등)이 포함되어 본사 순수 대외매출보다 크게 잡힙니다.
          본사 창고만 보려면 데이터 입력에서 <strong className="font-black">오포창고(OPO)</strong>를 선택해 다시 분석해 주세요.
        </div>
      ) : null}

      {loading ? (
        <div className="mb-4 rounded-[16px] border border-border bg-surface p-8 text-center text-[13px] font-black text-muted shadow-soft">
          국가 분석 데이터를 불러오는 중입니다.
        </div>
      ) : null}
      {!loading && (loadFailed || countryRows.length === 0) ? (
        <div className="mb-4 rounded-[16px] border border-border bg-surface p-8 text-center text-[13px] font-black text-muted shadow-soft">
          {loadFailed ? "국가 분석 데이터를 불러오지 못했습니다." : "국가 분석 결과가 없습니다. 데이터 입력에서 분석 시작을 먼저 실행해 주세요."}
        </div>
      ) : null}

      <div className={cn("mb-4 grid gap-[14px] md:grid-cols-2", canViewAmountData ? "xl:grid-cols-4" : "xl:grid-cols-3")}>
        {canViewAmountData ? (
          <OrderMetricCard
            label="전체 매출"
            value={wonEok(totalAmount)}
            accent
          />
        ) : null}
        <OrderMetricCard
          label="매출 발생 국가"
          value={`${formatNumber(activeCountryCount)}개국`}
        />
        <OrderMetricCard label="매출 발생 브랜드" value={brandCountDisplay} sub={staleCountCaveat ?? countryMetricDeltas.brands?.text} subTone={staleCountCaveat ? "muted" : countryMetricDeltas.brands?.tone} />
        <OrderMetricCard label="매출 발생 SKU" value={skuCountDisplay} sub={staleCountCaveat ?? countryMetricDeltas.skus?.text} subTone={staleCountCaveat ? "muted" : countryMetricDeltas.skus?.tone} />
      </div>

      <div className="mb-4 rounded-[16px] border border-border bg-surface p-5 shadow-soft">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-[15px] font-black text-ink">권역별 매출 비중</h3>
          <span className="text-[12px] font-semibold text-muted2">전 세계 {formatNumber(activeCountryCount)}개국 · 최신 분석 기준</span>
        </div>
        <div className="flex gap-3 overflow-x-auto pb-1">
          {regionRows.length > 0 ? (
            regionRows.map((row) => (
              <ShareCard
                key={row.region}
                region={row.region}
                percent={row.percent}
                amount={canViewAmountData ? row.amount : undefined}
                countries={row.countries}
                selected={selectedRegion === row.region}
                onSelect={() => {
                  setSelectedRegion((current) => (current === row.region ? "" : row.region));
                  setSelectedCountry("");
                }}
              />
            ))
          ) : (
            <div className="w-full rounded-[12px] border border-border bg-row px-4 py-8 text-center text-[13px] font-black text-muted">
              권역별 매출 데이터가 없습니다.
            </div>
          )}
        </div>
      </div>

      {selectedRegion ? (
      <div className="grid gap-4 xl:grid-cols-[1fr_650px]">
        <div className="grid content-start gap-4">
        <div className="overflow-hidden rounded-[16px] border border-border bg-surface shadow-soft">
          <div className="border-b border-divider px-4 py-4 sm:px-5">
            <h3 className="whitespace-nowrap text-[15px] font-black text-ink">국가별 판매 순위</h3>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] font-semibold text-muted2 sm:mt-0 sm:justify-end sm:text-[12px]">
              <span>
                {formatNumber(visibleCountryStart)}-{formatNumber(visibleCountryEnd)} / {formatNumber(rankRows.length)}
              </span>
              <span className="text-[12px] font-semibold text-muted2">매출 기준 · 금액 선택 기간 합계 · 클릭하여 상세 보기</span>
            </div>
          </div>
          <div>
            {visibleRankRows.map(([rank, country, region, share, yoy, , width, amount]) => {
              return (
                <CountryRankRow
                  key={country}
                  rank={rank}
                  country={country}
                  region={region}
                  share={share}
                  amount={canViewAmountData ? amount : undefined}
                  growth={undefined}
                  growthLabel={undefined}
                  width={width}
                  active={country === effectiveCountry}
                  onSelect={() => setSelectedCountry((current) => (current === country ? "" : country))}
                />
              );
            })}
          </div>
          {countryPageCount > 1 ? (
            <div className="flex items-center justify-between border-t border-divider px-[18px] py-[12px]">
              <button
                type="button"
                onClick={() => setCountryPage((page) => Math.max(1, page - 1))}
                disabled={safeCountryPage <= 1}
                className="h-8 rounded-[8px] border border-border bg-surface px-3 text-[12px] font-black text-ink transition hover:border-brand disabled:cursor-not-allowed disabled:opacity-40"
              >
                이전
              </button>
              <span className="text-[12px] font-black text-muted2">
                {formatNumber(safeCountryPage)} / {formatNumber(countryPageCount)}
              </span>
              <button
                type="button"
                onClick={() => setCountryPage((page) => Math.min(countryPageCount, page + 1))}
                disabled={safeCountryPage >= countryPageCount}
                className="h-8 rounded-[8px] border border-border bg-surface px-3 text-[12px] font-black text-ink transition hover:border-brand disabled:cursor-not-allowed disabled:opacity-40"
              >
                다음
              </button>
            </div>
          ) : null}
        </div>

        <div className="overflow-hidden rounded-[16px] border border-border bg-surface shadow-soft">
          <div className="border-b border-divider px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-[15px] font-black text-ink">국가별 성장 변화</h3>
                <p className="mt-1 text-[12px] font-semibold text-muted2">
                  {countryGrowthPeriodLabel} · 상승 {formatNumber(countryGrowthRows.filter((row) => row.value !== null && row.value > 0).length)}개국 · 하락 {formatNumber(countryGrowthRows.filter((row) => row.value !== null && row.value < 0).length)}개국
                </p>
              </div>
              <RankingDetailOpenButton onClick={() => setRankingDetail("growth")} />
            </div>
            <div className="mt-3 flex w-fit rounded-[12px] bg-segbg p-1 shadow-card">
              <button
                type="button"
                onClick={() => setCountryGrowthBasis("qoq")}
                disabled={!hasCountryQoqGrowth}
                className={cn(
                  "h-8 rounded-[8px] px-3 text-[12px] font-black transition disabled:cursor-not-allowed disabled:opacity-40",
                  countryGrowthBasis === "qoq" ? "bg-surface text-ink shadow-soft" : "text-muted hover:text-ink"
                )}
              >
                분기 QoQ
              </button>
              <button
                type="button"
                onClick={() => setCountryGrowthBasis("yoy")}
                disabled={!hasCountryQuarterYoyGrowth}
                className={cn(
                  "h-8 rounded-[8px] px-3 text-[12px] font-black transition disabled:cursor-not-allowed disabled:opacity-40",
                  countryGrowthBasis === "yoy" ? "bg-surface text-ink shadow-soft" : "text-muted hover:text-ink"
                )}
              >
                분기 YoY
              </button>
            </div>
            <div className="mt-3 flex flex-col items-stretch gap-1.5 rounded-[10px] border border-border bg-surface p-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-end">
              <label className="flex h-9 w-full items-center justify-between gap-2 rounded-[8px] bg-surface-soft px-2.5 text-[11px] font-black text-muted2 sm:w-auto">
                기준 분기
                <select
                  aria-label={`국가 성장 ${countryGrowthBasis === "yoy" ? "YoY" : "QoQ"} 기준 분기`}
                  value={countryGrowthTargetQuarter}
                  onChange={(event) => setCountryGrowthTargetQuarter(event.target.value)}
                  className="h-8 rounded-[8px] border border-border bg-surface px-2.5 text-[12px] font-black text-ink outline-none focus:border-brand"
                >
                  {activeCountryQuarterOptions.map((quarter) => (
                    <option key={quarter} value={quarter}>{formatQuarterLabel(quarter)}</option>
                  ))}
                </select>
              </label>
              <ArrowLeftRight className="hidden h-4 w-4 text-muted2 sm:block" aria-hidden="true" />
              <div
                aria-label={`국가 성장 ${countryGrowthBasis === "yoy" ? "YoY" : "QoQ"} 자동 비교 분기`}
                className="flex h-9 w-full items-center gap-2 rounded-[8px] bg-surface-soft px-2.5 text-[11px] font-black text-muted2 sm:h-8 sm:w-auto sm:justify-start sm:border sm:border-border sm:bg-surface"
              >
                비교 분기
                <strong className="ml-auto text-[12px] text-ink">
                  {formatQuarterLabel(countryGrowthComparisonQuarter)}
                </strong>
                <span>자동</span>
              </div>
              <span className="hidden text-left text-[11px] font-bold text-muted2 sm:block sm:w-auto">
                {countryGrowthBasis === "yoy" ? "전년도 동일 분기" : "직전 완료 분기"}
              </span>
            </div>
            <p className="mt-2 text-[11px] font-semibold text-muted2">
              완료된 3개월이 모두 있는 분기만 사용합니다. {canViewAmountData ? <>비교 분기 매출 {lowBaseAmountLabel()} 미만은 낮은 기준값으로 표시하며 순위에는 포함합니다. </> : null}비교 분기 매출이 없는 국가는 별도로 집계합니다.
            </p>
          </div>
          <div className="grid md:grid-cols-2">
            <div className="border-b border-divider p-4 md:border-b-0 md:border-r">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[12.5px] font-black text-ink">
                  성장 상위 <span className="font-semibold text-muted2">· 증감률 표시</span>
                </p>
                <span className="rounded-full bg-pos-bg px-2.5 py-1 text-[11px] font-black text-pos">상승</span>
              </div>
              <div>
                {risingCountryRows.length > 0 ? risingCountryRows.map((row, index) => (
                  <button
                    key={row.country}
                    type="button"
                    onClick={() => setSelectedCountry(row.country)}
                    className="grid w-full grid-cols-[24px_minmax(0,1fr)_auto] items-center gap-2 border-b border-rowline py-2.5 text-left last:border-b-0 hover:bg-surface-soft"
                  >
                    <span className="text-[12px] font-black text-muted2">{index + 1}</span>
                    <span className="min-w-0">
                      <span className="flex min-w-0 items-center gap-1.5">
                        <span className="truncate text-[12.5px] font-black text-ink">{row.country}</span>
                        {row.lowBase ? <span className="shrink-0 rounded-full bg-amber-50 px-1.5 py-0.5 text-[9px] font-black text-amber-700">낮은 기준값</span> : null}
                      </span>
                      <span className="mt-0.5 block text-[11px] font-bold text-muted2">{row.region}</span>
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
                )) : (
                  <p className="py-6 text-center text-[12px] font-semibold text-muted2">상승한 국가가 없습니다.</p>
                )}
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
                {decliningCountryRows.length > 0 ? decliningCountryRows.map((row, index) => (
                  <button
                    key={row.country}
                    type="button"
                    onClick={() => setSelectedCountry(row.country)}
                    className="grid w-full grid-cols-[24px_minmax(0,1fr)_auto] items-center gap-2 border-b border-rowline py-2.5 text-left last:border-b-0 hover:bg-surface-soft"
                  >
                    <span className="text-[12px] font-black text-muted2">{index + 1}</span>
                    <span className="min-w-0">
                      <span className="flex min-w-0 items-center gap-1.5">
                        <span className="truncate text-[12.5px] font-black text-ink">{row.country}</span>
                        {row.lowBase ? <span className="shrink-0 rounded-full bg-amber-50 px-1.5 py-0.5 text-[9px] font-black text-amber-700">낮은 기준값</span> : null}
                      </span>
                      <span className="mt-0.5 block text-[11px] font-bold text-muted2">{row.region}</span>
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
                )) : (
                  <p className="py-6 text-center text-[12px] font-semibold text-muted2">하락한 국가가 없습니다.</p>
                )}
              </div>
            </div>
          </div>
          <div className="border-t border-divider px-4 py-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-[12.5px] font-black text-ink">
                  {countryQuarterTrend.length >= 4 ? "최근 분기별 매출 추세" : "분기 매출 비교"}
                </p>
                <p className="mt-1 text-[11px] font-semibold text-muted2">
                  완료 분기 기준 · {countryQuarterTrend.length >= 4 ? "최대 최근 8개 분기" : `${formatNumber(countryQuarterTrend.length)}개 분기`} · 비중은 표시된 기간 내 분기별 비중
                </p>
              </div>
              <span className="text-[11px] font-semibold text-muted2">
                {selectedRegion || "전체 권역"}
              </span>
            </div>
            {countryQuarterTrend.length > 0 ? (
              <div className="grid min-h-[150px] grid-cols-4 items-end gap-2 sm:grid-cols-8">
                {countryQuarterTrend.map((row) => {
                  const badgeValue = countryQuarterTrend.length >= 4 ? row.yoy : row.qoq;
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
                        style={{ height: `${Math.max(6, (row.amount / countryQuarterTrendMax) * 100)}%` }}
                        title={
                          canViewAmountData
                            ? `${formatQuarterLabel(row.quarter)} · ${wonEok(row.amount)} · 기간 내 비중 ${row.share !== null ? `${row.share.toFixed(1)}%` : "-"}`
                            : `${formatQuarterLabel(row.quarter)} · 기간 내 비중 ${row.share !== null ? `${row.share.toFixed(1)}%` : "-"}`
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
              <p className="py-6 text-center text-[12px] font-semibold text-muted2">완료된 분기 추세 데이터가 없습니다.</p>
            )}
          </div>
        </div>
        </div>

        {effectiveCountry ? (
        <div className="grid gap-4">
          <div className="rounded-[16px] border border-border bg-surface p-5 shadow-soft">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-[12px] font-semibold text-muted2">선택 국가</p>
                <h3 className="mt-1 text-[22px] font-black leading-none text-ink">{effectiveCountry || "-"}</h3>
              </div>
              <div className="flex items-start gap-3">
                <div className="text-right">
                  {canViewAmountData ? <>
                  <p className="text-[24px] font-black leading-none text-ink">{wonEok(selectedCountryRow?.amount ?? 0)}</p>
                  {krwEokFromEur(selectedCountryRow?.amount ?? 0, averageEurKrwRate) ? (
                    <p className="mt-1 text-[12px] font-black text-muted2">
                      {krwEokFromEur(selectedCountryRow?.amount ?? 0, averageEurKrwRate)}
                    </p>
                  ) : null}</> : null}
                  <p className="mt-2 text-[12px] font-black text-brand">점유율 {formatNumber(selectedCountryShare, 1)}%</p>
                </div>
              </div>
            </div>
            {canViewAmountData ? <div className="mt-5 border-y border-divider">
              <div className="py-4">
                <p className="text-[12px] font-semibold text-muted2">월 최고 매출</p>
                <div className="mt-2 flex flex-wrap items-end justify-between gap-2">
                  <div>
                    <p className="text-[18px] font-black text-ink">{selectedPeakMonth ? wonEok(selectedPeakMonth.amount) : "-"}</p>
                    {selectedPeakMonth ? (
                      <p className="mt-1 text-[11px] font-black text-muted2">{krwEokFromEur(selectedPeakMonth.amount, averageEurKrwRate)}</p>
                    ) : null}
                  </div>
                  <p className="text-[12px] font-black text-brand">
                    {selectedPeakMonth ? `${selectedPeakMonthLabel} 최고` : "월별 데이터 없음"}
                  </p>
                </div>
              </div>
            </div> : null}

            <div className="mt-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <p className="text-[13px] font-black text-ink">상위 브랜드 · 미리보기</p>
                <RankingDetailOpenButton onClick={() => setRankingDetail("brand")} />
              </div>
              <div className="grid gap-[12px]">
                {selectedBrandRows.length > 0 ? (
                  selectedBrandRows.map((row) => (
                    <BrandBar
                      key={row.brand}
                      name={displayBrandName(row.brand)}
                      value={canViewAmountData ? [wonEok(row.amount), krwEokFromEur(row.amount, averageEurKrwRate)].filter(Boolean).join(" · ") : `점유율 ${formatNumber(row.sharePct, 1)}%`}
                      width={row.width}
                    />
                  ))
                ) : (
                  <p className="text-[12px] font-semibold text-muted2">상위 브랜드 데이터가 없습니다.</p>
                )}
              </div>
            </div>

            <div className="mt-6 border-t border-divider pt-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <p className="text-[13px] font-black text-ink">Top 5 카테고리</p>
                <RankingDetailOpenButton onClick={() => setRankingDetail("category")} />
              </div>
              <div className="flex flex-wrap gap-2">
                {(selectedTopCategories.length > 0 ? selectedTopCategories.map((row) => row.category) : ["데이터 없음"]).map((category, index) => (
                  <span key={`${category}-${index}`} className="rounded-full border border-border bg-row px-3 py-1 text-[12px] font-black text-ink3">{category}</span>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-[16px] border border-border bg-surface p-5 shadow-soft">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="text-[14px] font-black text-ink">상위 SKU · TOP 5 · {effectiveCountry || "-"}</h3>
              <div className="flex items-center gap-2">
                <RankingDetailOpenButton onClick={() => setRankingDetail("sku")} />
              </div>
            </div>
            <div className="grid gap-0">
              {selectedSkuRows.length > 0 ? selectedSkuRows.map((row, index) => (
                <div key={row.sku} className="grid grid-cols-[32px_minmax(0,1fr)_120px] items-center border-b border-rowline py-[10px] last:border-b-0">
                  <span className="text-[13px] font-black text-muted2">{index + 1}</span>
                  <div className="min-w-0">
                    <SkuNameWithCode name={row.name} sku={row.sku} />
                    <p className="mt-[2px] text-[12px] font-semibold text-muted2">{displayBrandName(row.brand)}</p>
                  </div>
                  {canViewAmountData ? <span className="text-right">
                    <span className="block text-[13px] font-black text-ink">{wonEok(row.amount)}</span>
                    <span className="mt-[2px] block text-[11px] font-black text-muted2">{krwEokFromEur(row.amount, averageEurKrwRate)}</span>
                  </span> : null}
                </div>
              )) : (
                <p className="py-4 text-[12px] font-semibold text-muted2">상위 SKU 데이터가 없습니다.</p>
              )}
            </div>
            <div className="mt-5 rounded-[10px] border border-border bg-surface px-4 py-3">
              <div className="mb-3 flex items-start justify-between gap-3">
                <p className="text-[13px] font-black text-ink">국가 시즌성 · 월별 매출 비중</p>
                <p className="max-w-[70%] text-right text-[11px] font-black leading-[1.35] text-muted2">
                  {selectedPeakMonth ? `${selectedPeakMonthLabel} 최고 비중 · ${formatNumber(selectedPeakShare, 1)}%` : "월별 데이터 없음"}
                </p>
              </div>
              <svg
                viewBox="0 0 620 112"
                role="img"
                aria-label={`${effectiveCountry} 월별 매출 비중 꺾은선 그래프`}
                className="h-[112px] w-full overflow-visible"
              >
                {[26, 57, 88].map((y) => (
                  <line key={y} x1="42" x2="590" y1={y} y2={y} stroke="var(--border-soft)" strokeWidth="1" />
                ))}
                <text x="4" y="29" fill="var(--muted-2)" fontSize="9" fontWeight="700">{formatNumber(selectedSeasonChartMaxShare, 0)}%</text>
                <text x="12" y="91" fill="var(--muted-2)" fontSize="9" fontWeight="700">0%</text>
                {selectedSeasonChartSegments.map((segment, segmentIndex) =>
                  segment.length > 1 ? (
                    <polyline
                      key={`season-segment-${segmentIndex}`}
                      points={segment.map((row) => `${row.x},${row.y}`).join(" ")}
                      fill="none"
                      stroke="var(--accent)"
                      strokeWidth="3"
                      strokeLinejoin="round"
                      strokeLinecap="round"
                    />
                  ) : null
                )}
                {selectedSeasonChartPoints.map((row) => {
                  if (!row.hasData) {
                    return (
                      <g key={row.month}>
                        <circle cx={row.x} cy={88} r={3} fill="var(--track)" stroke="var(--border)" strokeWidth="1.5">
                          <title>{`${row.month}월 · 분석 기간에 데이터 없음`}</title>
                        </circle>
                        <text x={row.x} y="106" textAnchor="middle" fill="var(--muted-2)" fontSize="9" fontWeight="700" opacity="0.5">
                          {row.month}월
                        </text>
                      </g>
                    );
                  }
                  const active = selectedPeakMonth?.monthKey === String(row.month).padStart(2, "0");
                  return (
                    <g key={row.month}>
                      <circle cx={row.x} cy={row.y} r={active ? 5 : 3.5} fill={active ? "var(--accent)" : "var(--surface)"} stroke="var(--accent)" strokeWidth="2">
                        <title>{`${row.month}월 매출 비중 ${formatNumber(row.share, 1)}%`}</title>
                      </circle>
                      <text x={row.x} y={Math.max(11, row.y - 8)} textAnchor="middle" fill={active ? "var(--accent)" : "var(--text-3)"} fontSize="9" fontWeight="800">
                        {formatNumber(row.share, 1)}%
                      </text>
                      <text x={row.x} y="106" textAnchor="middle" fill="var(--muted-2)" fontSize="9" fontWeight="700">{row.month}월</text>
                    </g>
                  );
                })}
              </svg>
            </div>
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
