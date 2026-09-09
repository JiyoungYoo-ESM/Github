+"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeftRight, Check, ChevronDown, FileText, Search, X } from "lucide-react";
import { getSeasonTrendAnalysis } from "@/lib/api";
import {
  buildCalendarMonthAverageProfile,
  buildCalendarMonthShareProfile,
  buildTopSkuConcentration,
  completeSeasonalityMonthKeys
} from "@/lib/brand-analysis";
import { displayBrandName } from "@/lib/brand-display";
import { trendLineColors } from "@/lib/chart-tokens";
import { formatAnalysisMonthLabel } from "@/lib/cross-analysis-mom";
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
  exchangeRateBasisLabel,
  krwEokFromEur,
  signedEur,
  signedKrwEokFromEur,
  wonEok
} from "../../lib/currency-format";
import { escapeReportHtml, injectReportWatermark } from "../../lib/report-html";
import { analysisPeriodLabel, longKoreanDateLabel, reportAnalysisPeriodParams, reportBrandRole } from "../../lib/workspace-format";
import { AnalysisPeriodBadge, AnalysisPeriodCaveat } from "../../shared/AnalysisPeriod";
import { BrandBar, SkuNameWithCode } from "../../shared/BrandBar";
import { BrandSearchSelect } from "../../shared/BrandSearchSelect";
import {
  availableComparisonBasis,
  automaticComparisonBasis,
  automaticGrowthTargetMonths,
  comparableYearWindow,
  comparisonBasisFromValue,
  completedYtdComparableYearWindow,
  completedYtdPeriodLabel,
  growthBadgeClass,
  growthDisplayLabel,
  growthLabelsForMonthPair,
  isGrowthStatusLabel,
  latestComparableMonths,
  latestComparableYears,
  LOW_BASE_QTY,
  previousMonthKey,
  previousYearMonthKey,
  shortMonthPairLabel,
  ytdAmountComparisonsByLabel,
  yoyBucketOf
} from "../../lib/yoy-comparison";

import {
  BrandMetricBox,
  BrandRankRow,
  BrandStatusPill,
  SkuSearchSelect,
  type SkuSearchOption
} from "./BrandScreenParts";
import {
  comparableQuarterKeys,
  completeQuarterKeys,
  formatQuarterLabel,
  previousQuarterKey,
  previousYearQuarterKey,
  quarterKeyFromMonthKey,
  type CountryQuarterGrowthBasis
} from "../country/country-quarter-growth";
import { lowBaseAmount } from "@/lib/low-base";
import { useBrandScreenData } from "./useBrandScreenData";

export function useBrandScreenModel({
  reportBlocks,
  onToggleReportBlock
}: {
  reportBlocks: ReportBlock[];
  onToggleReportBlock: (block: ReportBlock) => void;
}) {
  const BRAND_COMPARISON_PICKER = "__brand_comparison_picker__";
  const [exportingBrandPdf, setExportingBrandPdf] = useState(false);
  const {
    rows,
    monthlyRows,
    monthCoverage,
    loading,
    loadFailed,
    comparisonBasis,
    setComparisonBasis,
    analysisOptions
  } = useBrandScreenData();
  const [selectedBrandName, setSelectedBrandName] = useState("");
  const [brandPage, setBrandPage] = useState(1);
  const [brandGrowthBasis, setBrandGrowthBasis] = useState<CountryQuarterGrowthBasis>("yoy");
  const [brandGrowthTargetQuarter, setBrandGrowthTargetQuarter] = useState("");
  const [brandMomTargetMonth, setBrandMomTargetMonth] = useState("");
  const [brandYoyTargetMonth, setBrandYoyTargetMonth] = useState("");
  const [comparisonBrands, setComparisonBrands] = useState<string[]>([]);
  const [brandComparisonTooltip, setBrandComparisonTooltip] = useState<{
    brand: string;
    month: number;
    share: number;
    amount: number;
    observationCount: number;
    totalAmount: number;
    color: string;
    x: number;
    y: number;
  } | null>(null);
  const savedReportBlockIds = useMemo(() => new Set(reportBlocks.map((block) => block.id)), [reportBlocks]);

  const brandSummaries = useMemo(() => {
    const byBrand = new Map<string, { brand: string; amount: number; qty: number; skus: Set<string>; countries: Set<string>; categories: Set<string> }>();
    rows.forEach((row) => {
      const brand = brandOf(row);
      const current = byBrand.get(brand) ?? { brand, amount: 0, qty: 0, skus: new Set<string>(), countries: new Set<string>(), categories: new Set<string>() };
      current.amount += amountOf(row);
      current.qty += qtyOf(row);
      const sku = skuCodeOf(row);
      if (sku && sku !== "-") current.skus.add(sku);
      const country = countryOf(row);
      if (country && country !== "미상") current.countries.add(country);
      const category = category1Of(row);
      if (category && !category.includes("미분류")) current.categories.add(category);
      byBrand.set(brand, current);
    });
    const maxAmount = Math.max(...Array.from(byBrand.values()).map((row) => row.amount), 1);
    return Array.from(byBrand.values())
      .sort((a, b) => b.amount - a.amount)
      .map((row, index) => ({ ...row, rank: index + 1, width: `${Math.max(4, (row.amount / maxAmount) * 100)}%` }));
  }, [rows]);
  const brandGrowthMonthOptions = useMemo(() => {
    const monthlyOptions = Array.from(new Set(monthlyRows.map((row) => monthKeyOf(row)).filter((month) => /^\d{4}-\d{2}$/.test(month)))).sort();
    const availableOptions = monthlyOptions.length >= 2
      ? monthlyOptions
      : Array.from(new Set(rows.map((row) => monthKeyOf(row)).filter((month) => /^\d{4}-\d{2}$/.test(month)))).sort();
    if (monthCoverage.length === 0) return availableOptions;
    const completeMonthSet = new Set(monthCoverage.filter((item) => item.status === "complete").map((item) => item.month));
    return availableOptions.filter((month) => completeMonthSet.has(month));
  }, [monthCoverage, monthlyRows, rows]);
  const brandGrowthSourceRows = useMemo(
    () => (monthlyRows.some((row) => /^\d{4}-\d{2}$/.test(monthKeyOf(row))) ? monthlyRows : rows),
    [monthlyRows, rows]
  );
  const brandCompleteQuarterOptions = useMemo(
    () => completeQuarterKeys(brandGrowthMonthOptions),
    [brandGrowthMonthOptions]
  );
  const brandQoqTargetOptions = useMemo(
    () => comparableQuarterKeys(brandCompleteQuarterOptions, "qoq"),
    [brandCompleteQuarterOptions]
  );
  const brandQuarterYoyTargetOptions = useMemo(
    () => comparableQuarterKeys(brandCompleteQuarterOptions, "yoy"),
    [brandCompleteQuarterOptions]
  );
  const activeBrandQuarterOptions = brandGrowthBasis === "yoy"
    ? brandQuarterYoyTargetOptions
    : brandQoqTargetOptions;
  useEffect(() => {
    setBrandGrowthTargetQuarter((current) =>
      activeBrandQuarterOptions.includes(current)
        ? current
        : activeBrandQuarterOptions.at(-1) ?? ""
    );
  }, [activeBrandQuarterOptions]);
  const brandMomTargetOptions = useMemo(
    () => automaticGrowthTargetMonths(brandGrowthMonthOptions, previousMonthKey),
    [brandGrowthMonthOptions]
  );
  const brandYoyTargetOptions = useMemo(
    () => automaticGrowthTargetMonths(brandGrowthMonthOptions, previousYearMonthKey),
    [brandGrowthMonthOptions]
  );
  useEffect(() => {
    if (brandGrowthMonthOptions.length < 2) return;
    setBrandMomTargetMonth((current) =>
      brandMomTargetOptions.includes(current) ? current : brandMomTargetOptions.at(-1) ?? ""
    );
    setBrandYoyTargetMonth((current) =>
      brandYoyTargetOptions.includes(current) ? current : brandYoyTargetOptions.at(-1) ?? ""
    );
  }, [brandGrowthMonthOptions, brandMomTargetOptions, brandYoyTargetOptions]);
  const brandMomComparisonMonth = previousMonthKey(brandMomTargetMonth);
  const brandYoyComparisonMonth = previousYearMonthKey(brandYoyTargetMonth);
  const brandMomByName = useMemo(
    () => growthLabelsForMonthPair(brandGrowthSourceRows, brandMomTargetMonth, brandMomComparisonMonth, brandOf),
    [brandGrowthSourceRows, brandMomComparisonMonth, brandMomTargetMonth]
  );
  const brandCompleteMonthSet = useMemo(
    () => new Set(brandGrowthMonthOptions),
    [brandGrowthMonthOptions]
  );
  const brandYtdWindow = useMemo(
    () => completedYtdComparableYearWindow(
      brandGrowthSourceRows,
      monthCoverage.length > 0 ? brandCompleteMonthSet : undefined
    ),
    [brandCompleteMonthSet, brandGrowthSourceRows, monthCoverage.length]
  );
  const brandYtdComparisons = useMemo(
    () => ytdAmountComparisonsByLabel(brandGrowthSourceRows, brandYtdWindow, brandOf),
    [brandGrowthSourceRows, brandYtdWindow]
  );
  const brandYoyByName = useMemo(
    () => new Map(Array.from(brandYtdComparisons, ([brand, comparison]) => [brand, comparison.growth])),
    [brandYtdComparisons]
  );
  const brandYtdPeriodLabel = completedYtdPeriodLabel(brandYtdWindow);
  const startDateText = String(analysisOptions?.start_date ?? "");
  const endDateText = String(analysisOptions?.end_date ?? "");
  const observedBrandMonthKeys = useMemo(
    () => new Set(monthlyRows.map((row) => monthKeyOf(row)).filter((month) => /^\d{4}-\d{2}$/.test(month))),
    [monthlyRows]
  );
  const brandSeasonalityMonthKeys = useMemo(
    () => completeSeasonalityMonthKeys(monthCoverage, observedBrandMonthKeys),
    [monthCoverage, observedBrandMonthKeys]
  );
  const brandCompleteMonthCount = brandSeasonalityMonthKeys.size;
  const brandExcludedMonthCount = monthCoverage.filter((item) => item.status !== "complete").length;
  const brandSeasonalityCalendarMonthCount = useMemo(
    () => new Set(Array.from(brandSeasonalityMonthKeys).map((key) => Number(key.slice(5, 7)))).size,
    [brandSeasonalityMonthKeys]
  );
  const brandUncategorizedQuality = useMemo(() => {
    const affectedRows = rows.filter((row) => category1Of(row).includes("미분류") || category2Of(row).includes("미분류"));
    const affectedAmount = affectedRows.reduce((sum, row) => sum + amountOf(row), 0);
    const totalAmount = rows.reduce((sum, row) => sum + amountOf(row), 0);
    return {
      affectedRows: affectedRows.length,
      affectedAmount,
      affectedSharePct: totalAmount > 0 ? (affectedAmount / totalAmount) * 100 : 0
    };
  }, [rows]);
  const rangeMonthNumbers = useMemo(() => {
    const startYear = Number(startDateText.slice(0, 4));
    const startMonth = Number(startDateText.slice(5, 7));
    const endYear = Number(endDateText.slice(0, 4));
    const endMonth = Number(endDateText.slice(5, 7));
    if (startYear > 0 && startMonth >= 1 && startMonth <= 12 && endYear > 0 && endMonth >= 1 && endMonth <= 12) {
      const monthsInRange: number[] = [];
      let year = startYear;
      let month = startMonth;
      while (year < endYear || (year === endYear && month <= endMonth)) {
        monthsInRange.push(month);
        month += 1;
        if (month > 12) {
          month = 1;
          year += 1;
        }
        if (monthsInRange.length > 24) break;
      }
      return monthsInRange;
    }
    return [];
  }, [endDateText, startDateText]);
  const isShortAnalysisRange = rangeMonthNumbers.length > 0 && rangeMonthNumbers.length < 12;
  const brandSeasonMonths = useMemo(() => {
    if (!isShortAnalysisRange) return Array.from({ length: 12 }, (_, index) => index + 1);
    const coveredCalendarMonths = new Set(Array.from(brandSeasonalityMonthKeys).map((key) => Number(key.slice(5, 7))));
    const completeRangeMonths = rangeMonthNumbers.filter((month) => coveredCalendarMonths.has(month));
    return completeRangeMonths.length > 0 ? completeRangeMonths : rangeMonthNumbers;
  }, [brandSeasonalityMonthKeys, isShortAnalysisRange, rangeMonthNumbers]);

  useEffect(() => {
    if (selectedBrandName && !brandSummaries.some((row) => row.brand === selectedBrandName)) {
      setSelectedBrandName("");
    }
  }, [brandSummaries, selectedBrandName]);

  useEffect(() => {
    setComparisonBrands((current) => current.filter((brand) => brandSummaries.some((row) => row.brand === brand)));
  }, [brandSummaries]);

  useEffect(() => {
    if (!selectedBrandName) return;
    setComparisonBrands((current) => current.includes(selectedBrandName) ? current : [selectedBrandName, ...current].slice(0, 6));
    setBrandComparisonTooltip(null);
  }, [selectedBrandName]);

  const brandPageSize = 10;
  const brandPageCount = Math.max(1, Math.ceil(brandSummaries.length / brandPageSize));
  const safeBrandPage = Math.min(brandPage, brandPageCount);
  const visibleBrandSummaries = brandSummaries.slice((safeBrandPage - 1) * brandPageSize, safeBrandPage * brandPageSize);
  const visibleBrandStart = brandSummaries.length > 0 ? (safeBrandPage - 1) * brandPageSize + 1 : 0;
  const visibleBrandEnd = Math.min(safeBrandPage * brandPageSize, brandSummaries.length);

  useEffect(() => {
    if (brandPage > brandPageCount) setBrandPage(brandPageCount);
  }, [brandPage, brandPageCount]);

  const selectedBrand = brandSummaries.find((row) => row.brand === selectedBrandName);
  const selectedBrandRows = useMemo(() => rows.filter((row) => brandOf(row) === selectedBrand?.brand), [rows, selectedBrand?.brand]);
  const selectedMonthlyRows = useMemo(() => monthlyRows.filter((row) => brandOf(row) === selectedBrand?.brand), [monthlyRows, selectedBrand?.brand]);
  const totalBrandAmount = brandSummaries.reduce((sum, row) => sum + row.amount, 0);
  const selectedShare = selectedBrand && totalBrandAmount > 0 ? (selectedBrand.amount / totalBrandAmount) * 100 : 0;
  const brandComparisonSeries = useMemo(() => comparisonBrands.flatMap((brand, colorIndex) => {
    const summary = brandSummaries.find((row) => row.brand === brand);
    if (!summary) return [];
    const monthlyAmounts = buildCalendarMonthAverageProfile({
      rows: monthlyRows.filter((row) => brandOf(row) === brand),
      calendarMonths: brandSeasonMonths,
      eligibleMonthKeys: brandSeasonalityMonthKeys,
      monthKey: monthKeyOf,
      amount: amountOf
    });
    const totalAmount = monthlyAmounts
      .filter((row) => row.observationCount > 0)
      .reduce((sum, row) => sum + row.amount, 0);
    const monthly = buildCalendarMonthShareProfile(monthlyAmounts);
    const peak = monthly.reduce(
      (best, row) => (row.share ?? -1) > (best.share ?? -1) ? row : best,
      { month: 0, amount: 0, observationCount: 0, share: null }
    );
    return [{
      ...summary,
      colorIndex,
      color: trendLineColors[colorIndex % trendLineColors.length],
      totalAmount,
      peakMonth: peak.month,
      peakShare: peak.share ?? 0,
      monthly
    }];
  }), [brandSeasonMonths, brandSeasonalityMonthKeys, brandSummaries, comparisonBrands, monthlyRows]);
  const availableComparisonBrandOptions = useMemo(
    () => brandSummaries.map((row) => row.brand).filter((brand) => !comparisonBrands.includes(brand)),
    [brandSummaries, comparisonBrands]
  );
  const brandComparisonAxisMax = useMemo(
    () => Math.max(
      10,
      Math.ceil(Math.max(...brandComparisonSeries.flatMap((series) => series.monthly.map((row) => row.share ?? 0)), 0) / 5) * 5
    ),
    [brandComparisonSeries]
  );
  const brandComparisonBaselineShare = brandSeasonalityCalendarMonthCount > 0
    ? 100 / brandSeasonalityCalendarMonthCount
    : null;
  const brandComparisonChartSeries = useMemo(
    () => brandComparisonSeries.map((series) => ({
      ...series,
      points: series.monthly.map((row, index) => ({
        ...row,
        x: series.monthly.length > 1 ? 52 + (index * 1128) / (series.monthly.length - 1) : 616,
        y: row.share === null ? 190 : 190 - (row.share / brandComparisonAxisMax) * 140
      }))
    })),
    [brandComparisonSeries, brandComparisonAxisMax]
  );
  const averageEurKrwRate =
    Number(analysisOptions?.average_eur_krw_rate) > 0
      ? Number(analysisOptions?.average_eur_krw_rate)
      : null;
  const exchangeBasis = exchangeRateBasisLabel(analysisOptions, averageEurKrwRate);
  const selectedBrandKrw = krwEokFromEur(selectedBrand?.amount ?? 0, averageEurKrwRate);
  const selectedBrandMom = brandMomByName.get(selectedBrand?.brand ?? "") ?? "";
  const effectiveBrandComparisonBasis = useMemo(
    () => availableComparisonBasis(comparisonBasis, latestComparableYears(monthlyRows) ? monthlyRows : rows, latestComparableMonths(monthlyRows) ? monthlyRows : rows),
    [comparisonBasis, monthlyRows, rows]
  );
  const brandMomLabel = useMemo(
    () => shortMonthPairLabel(latestComparableMonths(latestComparableMonths(monthlyRows) ? monthlyRows : rows)),
    [monthlyRows, rows]
  );
  const comparisonShortLabel = effectiveBrandComparisonBasis === "mom" ? brandMomLabel : effectiveBrandComparisonBasis === "yoy" ? "YoY" : "";
  const hasBrandQoqGrowth = brandQoqTargetOptions.length > 0;
  const hasBrandQuarterYoyGrowth = brandQuarterYoyTargetOptions.length > 0;
  const brandGrowthComparisonQuarter = brandGrowthBasis === "yoy"
    ? previousYearQuarterKey(brandGrowthTargetQuarter)
    : previousQuarterKey(brandGrowthTargetQuarter);
  const brandGrowthPeriodLabel = brandGrowthTargetQuarter && brandGrowthComparisonQuarter
    ? `${formatQuarterLabel(brandGrowthComparisonQuarter)} → ${formatQuarterLabel(brandGrowthTargetQuarter)}`
    : "비교 기간 없음";
  const brandGrowthBasisLabel = brandGrowthBasis === "yoy"
    ? "분기 YoY · 전년 동일 분기 대비"
    : "분기 QoQ · 전 분기 대비";
  // 분기 성장률은 월별 성장률을 평균하지 않고, 완료된 3개월의 매출을 먼저 합산한 뒤 계산한다.
  const brandGrowthAmountsByName = useMemo(() => {
    const amounts = new Map<string, { current: number; previous: number }>();
    const add = (brand: string, bucket: "current" | "previous", amount: number) => {
      const entry = amounts.get(brand) ?? { current: 0, previous: 0 };
      entry[bucket] += amount;
      amounts.set(brand, entry);
    };
    if (!brandGrowthTargetQuarter || !brandGrowthComparisonQuarter) return amounts;
    brandGrowthSourceRows.forEach((row) => {
      const brand = brandOf(row);
      if (!brand) return;
      const quarter = quarterKeyFromMonthKey(monthKeyOf(row));
      if (quarter === brandGrowthTargetQuarter) add(brand, "current", amountOf(row));
      else if (quarter === brandGrowthComparisonQuarter) add(brand, "previous", amountOf(row));
    });
    return amounts;
  }, [brandGrowthComparisonQuarter, brandGrowthSourceRows, brandGrowthTargetQuarter]);
  const brandGrowthRows = useMemo(
    () =>
      brandSummaries.flatMap((row) => {
        const amounts = brandGrowthAmountsByName.get(row.brand);
        const currentAmount = amounts?.current ?? 0;
        const previousAmount = amounts?.previous ?? 0;
        if (currentAmount <= 0 && previousAmount <= 0) return [];
        const comparisonNoSales = previousAmount <= 0 && currentAmount > 0;
        const lowBase = previousAmount > 0 && previousAmount < lowBaseAmount();
        const value = previousAmount > 0
          ? ((currentAmount - previousAmount) / previousAmount) * 100
          : null;
        const growth = comparisonNoSales
          ? "비교 분기 매출 없음"
          : growthDisplayLabel(currentAmount, previousAmount, 0) ?? "-";
        return [
          {
            brand: row.brand,
            growth,
            value,
            currentAmount,
            previousAmount,
            deltaAmount: currentAmount - previousAmount,
            vanished: value !== null && value <= -100 && currentAmount <= 0,
            lowBase,
            comparisonNoSales
          }
        ];
      }),
    [brandGrowthAmountsByName, brandSummaries]
  );
  // 정렬은 %가 아니라 금액 변화(임팩트) 기준 — 저기저 %폭등의 착시 방지
  const allRisingBrandRows = useMemo(
    () => brandGrowthRows
      .filter((row) => !row.comparisonNoSales && row.value !== null && row.value > 0)
      .sort((a, b) => b.deltaAmount - a.deltaAmount),
    [brandGrowthRows]
  );
  const allDecliningBrandRows = useMemo(
    () => brandGrowthRows
      .filter((row) => !row.comparisonNoSales && row.value !== null && row.value < 0)
      .sort((a, b) => a.deltaAmount - b.deltaAmount),
    [brandGrowthRows]
  );
  const comparisonNoSalesBrandRows = useMemo(
    () => brandGrowthRows
      .filter((row) => row.comparisonNoSales)
      .sort((a, b) => b.currentAmount - a.currentAmount),
    [brandGrowthRows]
  );
  const risingBrandRows = allRisingBrandRows.slice(0, 5);
  const decliningBrandRows = allDecliningBrandRows.slice(0, 5);
  const brandQuarterTrend = useMemo(() => {
    const amountByQuarter = new Map<string, number>();
    brandGrowthSourceRows.forEach((row) => {
      const quarter = quarterKeyFromMonthKey(monthKeyOf(row));
      if (!quarter || !brandCompleteQuarterOptions.includes(quarter)) return;
      amountByQuarter.set(quarter, (amountByQuarter.get(quarter) ?? 0) + amountOf(row));
    });
    const quarters = brandCompleteQuarterOptions.slice(-8);
    const periodTotalAmount = quarters.reduce((sum, quarter) => sum + (amountByQuarter.get(quarter) ?? 0), 0);
    return quarters.map((quarter) => {
      const amount = amountByQuarter.get(quarter) ?? 0;
      const previousYearAmount = amountByQuarter.get(previousYearQuarterKey(quarter)) ?? 0;
      const previousQuarterAmount = amountByQuarter.get(previousQuarterKey(quarter)) ?? 0;
      return {
        quarter,
        label: formatQuarterLabel(quarter).replace("년 ", "·"),
        amount,
        share: periodTotalAmount > 0 ? (amount / periodTotalAmount) * 100 : null,
        yoy: growthDisplayLabel(amount, previousYearAmount),
        qoq: growthDisplayLabel(amount, previousQuarterAmount)
      };
    });
  }, [brandCompleteQuarterOptions, brandGrowthSourceRows]);
  const brandQuarterTrendMax = Math.max(...brandQuarterTrend.map((row) => row.amount), 1);
  const brandRankGrowthColumn = "금액 YTD YoY";
  const allBrandsReportBlock: ReportBlock = {
    id: "brand:ranking:all",
    title: "전체 브랜드 판매 순위",
    subtitle: `선택기간 전체 매출 기준 ${formatNumber(brandSummaries.length)}개 브랜드${brandExcludedMonthCount > 0 ? ` · 부분·누락월 ${formatNumber(brandExcludedMonthCount)}개월 포함` : ""}`,
    meta: "브랜드 기준 분석",
    type: "brand_rank",
    kind: "ranking",
    section: "brand",
    size: "full",
    params: {
      scope: "all_brands",
      metric: "sales",
      comparison_basis: "yoy",
      comparison_mode: "completed_ytd",
      period_label: brandYtdPeriodLabel,
      eur_krw_rate: averageEurKrwRate,
      ...reportAnalysisPeriodParams(analysisOptions)
    },
    snapshot: {
      columns: ["순위", "브랜드명", "매출액", "매출표시", "원화표시", "SKU수", "국가수", brandRankGrowthColumn],
      rows: brandSummaries.map((row) => ({
        순위: row.rank,
        브랜드명: displayBrandName(row.brand),
        brand_original: row.brand,
        brand_role: reportBrandRole(row.brand),
        is_self: reportBrandRole(row.brand) === "self",
        매출액: row.amount,
        매출표시: wonEok(row.amount),
        원화표시: krwEokFromEur(row.amount, averageEurKrwRate),
        SKU수: row.skus.size,
        국가수: row.countries.size,
        [brandRankGrowthColumn]: brandYoyByName.get(row.brand) ?? "-",
        비교기간: brandYtdPeriodLabel
      }))
    }
  };
  const brandGrowthSnapshotRow = (row: (typeof brandGrowthRows)[number], index: number, category: string) => ({
    구분: category,
    순위: index + 1,
    브랜드명: displayBrandName(row.brand),
    brand_original: row.brand,
    brand_role: reportBrandRole(row.brand),
    is_self: reportBrandRole(row.brand) === "self",
    성장률: row.growth,
    "기준 분기 매출": wonEok(row.currentAmount),
    "비교 분기 매출": wonEok(row.previousAmount),
    "매출 증감": signedEur(row.deltaAmount),
    "기준 분기 원화": krwEokFromEur(row.currentAmount, averageEurKrwRate),
    "비교 분기 원화": krwEokFromEur(row.previousAmount, averageEurKrwRate),
    "원화 증감": signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate),
    비교기간: brandGrowthPeriodLabel
  });
  const brandGrowthBlock: ReportBlock = {
    id: `brand:growth:${brandGrowthBasis}:${brandGrowthPeriodLabel}`,
    title: "브랜드별 성장 변화",
    subtitle: `${brandGrowthBasisLabel} · ${brandGrowthPeriodLabel} · 상승 ${formatNumber(allRisingBrandRows.length)}개 · 하락 ${formatNumber(allDecliningBrandRows.length)}개`,
    meta: "브랜드별 분기 매출 성장 비교",
    type: "brand_growth",
    kind: "ranking",
    section: "brand",
    size: "full",
    params: {
      comparison_basis: brandGrowthBasis,
      comparison_quarter: brandGrowthComparisonQuarter,
      target_quarter: brandGrowthTargetQuarter,
      period_label: brandGrowthPeriodLabel,
      low_base_eur: lowBaseAmount(),
      eur_krw_rate: averageEurKrwRate,
      ...reportAnalysisPeriodParams(analysisOptions)
    },
    snapshot: {
      columns: ["구분", "순위", "브랜드명", "성장률", "기준 분기 매출", "비교 분기 매출", "매출 증감", "기준 분기 원화", "비교 분기 원화", "원화 증감", "비교기간"],
      rows: [
        ...allRisingBrandRows.map((row, index) => brandGrowthSnapshotRow(row, index, "성장 상위")),
        ...allDecliningBrandRows.map((row, index) => brandGrowthSnapshotRow(row, index, "감소 상위"))
      ]
    }
  };

  useEffect(() => {
    if (brandGrowthBasis === "qoq" && !hasBrandQoqGrowth && hasBrandQuarterYoyGrowth) setBrandGrowthBasis("yoy");
    if (brandGrowthBasis === "yoy" && !hasBrandQuarterYoyGrowth && hasBrandQoqGrowth) setBrandGrowthBasis("qoq");
  }, [brandGrowthBasis, hasBrandQoqGrowth, hasBrandQuarterYoyGrowth]);
  const selectedBrandMetricDeltas = useMemo(() => {
    const empty: Record<string, { text: string; tone: "brand" | "pos" | "muted" } | undefined> = {};
    if (!selectedBrand?.brand || effectiveBrandComparisonBasis === "none") return empty;
    const sourceRows = effectiveBrandComparisonBasis === "mom" ? (latestComparableMonths(monthlyRows) ? monthlyRows : rows) : (comparableYearWindow(monthlyRows) ? monthlyRows : rows);
    const momPeriods = effectiveBrandComparisonBasis === "mom" ? latestComparableMonths(sourceRows) : null;
    const yoyWindow = effectiveBrandComparisonBasis === "yoy" ? comparableYearWindow(sourceRows) : null;
    if (!momPeriods && !yoyWindow) return empty;
    const current = { amount: 0, qty: 0, skus: new Set<string>(), countries: new Set<string>() };
    const previous = { amount: 0, qty: 0, skus: new Set<string>(), countries: new Set<string>() };

    sourceRows.forEach((row) => {
      if (brandOf(row) !== selectedBrand.brand) return;
      let bucket: typeof current | null = null;
      if (momPeriods) {
        const period = monthKeyOf(row);
        bucket = period === momPeriods[0] ? current : period === momPeriods[1] ? previous : null;
      } else if (yoyWindow) {
        const side = yoyBucketOf(row, yoyWindow);
        bucket = side === "current" ? current : side === "previous" ? previous : null;
      }
      if (!bucket) return;
      bucket.amount += amountOf(row);
      bucket.qty += qtyOf(row);
      const sku = skuCodeOf(row);
      if (sku && sku !== "-") bucket.skus.add(sku);
      const country = countryOf(row);
      if (country && country !== "미상") bucket.countries.add(country);
    });

    const comparisonSuffix = comparisonShortLabel ? ` (${comparisonShortLabel})` : "";
    const pctDelta = (currentValue: number, previousValue: number, lowBaseThreshold: number) => {
      const label = growthDisplayLabel(currentValue, previousValue, lowBaseThreshold);
      if (!label) return undefined;
      if (isGrowthStatusLabel(label)) return { text: `${label}${comparisonSuffix}`, tone: "muted" as const };
      return { text: `${label}${comparisonSuffix}`, tone: label.startsWith("-") ? "brand" as const : "pos" as const };
    };
    const countDelta = (currentValue: number, previousValue: number, unit = "") => {
      const value = currentValue - previousValue;
      if (value === 0) return undefined;
      return { text: `${value > 0 ? "+" : ""}${formatNumber(value)}${unit}${comparisonSuffix}`, tone: value > 0 ? "pos" as const : "brand" as const };
    };

    return {
      amount: pctDelta(current.amount, previous.amount, lowBaseAmount()),
      qty: pctDelta(current.qty, previous.qty, LOW_BASE_QTY),
      skus: countDelta(current.skus.size, previous.skus.size),
      countries: countDelta(current.countries.size, previous.countries.size, "개국")
    };
  }, [comparisonShortLabel, effectiveBrandComparisonBasis, monthlyRows, rows, selectedBrand?.brand]);
  const selectedBrandMetrics = [
    ["매출", selectedBrand ? wonEok(selectedBrand.amount) : "-", undefined],
    ["판매수량", selectedBrand ? formatNumber(selectedBrand.qty) : "-", undefined],
    ["매출 발생 SKU", selectedBrand ? formatNumber(selectedBrand.skus.size) : "-", undefined],
    ["판매 국가", selectedBrand ? `${formatNumber(selectedBrand.countries.size)}개국` : "-", undefined]
  ] as const;

  const selectedSkuConcentration = useMemo(() => {
    const bySku = new Map<string, { sku: string; name: string; category: string; amount: number; qty: number }>();
    selectedBrandRows.forEach((row) => {
      const sku = skuCodeOf(row);
      if (!sku || sku === "-") return;
      const current = bySku.get(sku) ?? { sku, name: productNameOf(row), category: category1Of(row), amount: 0, qty: 0 };
      current.amount += amountOf(row);
      current.qty += qtyOf(row);
      bySku.set(sku, current);
    });
    return buildTopSkuConcentration(Array.from(bySku.values()), Number.MAX_SAFE_INTEGER, selectedBrand?.amount);
  }, [selectedBrand?.amount, selectedBrandRows]);
  const allSelectedSkuRows = selectedSkuConcentration.rows;
  const selectedSkuRows = allSelectedSkuRows.slice(0, 5);
  const selectedTopSkuShare = selectedSkuConcentration.totalAmount > 0
    ? (selectedSkuRows.reduce((sum, row) => sum + row.amount, 0) / selectedSkuConcentration.totalAmount) * 100
    : 0;

  const allSkuConcentrationRows = useMemo(() => {
    return allSelectedSkuRows.map((row) => ({
      sku: row.sku,
      name: row.name,
      category: row.category,
      amount: row.amount,
      amountKrw: krwEokFromEur(row.amount, averageEurKrwRate),
      sharePct: row.sharePct,
      value: `${formatNumber(row.sharePct, 1)}%`,
      width: `${Math.max(4, row.barWidthPct)}%`
    }));
  }, [allSelectedSkuRows, averageEurKrwRate]);
  const skuConcentrationRows = allSkuConcentrationRows.slice(0, 5);

  const allCountryDistributionRows = useMemo(() => {
    const byCountry = new Map<string, number>();
    selectedBrandRows.forEach((row) => {
      const country = countryOf(row);
      byCountry.set(country, (byCountry.get(country) ?? 0) + amountOf(row));
    });
    const sortedRows = Array.from(byCountry.entries()).sort((a, b) => b[1] - a[1]);
    const total = sortedRows.reduce((sum, [, amount]) => sum + amount, 0);
    const max = Math.max(...sortedRows.map(([, amount]) => amount), 1);
    return sortedRows.map(([name, amount]) => ({
      name,
      detail: "",
      amount,
      amountDisplay: wonEok(amount),
      amountKrw: krwEokFromEur(amount, averageEurKrwRate),
      sharePct: total > 0 ? (amount / total) * 100 : 0,
      value: `${formatNumber(total > 0 ? (amount / total) * 100 : 0, 0)}%`,
      width: `${Math.max(4, (amount / max) * 100)}%`
    }));
  }, [averageEurKrwRate, selectedBrandRows]);
  const countryDistributionRows = allCountryDistributionRows.slice(0, 5);

  const allLineCompositionRows = useMemo(() => {
    const byCategory = new Map<string, number>();
    selectedBrandRows.forEach((row) => {
      const category1 = category1Of(row);
      const category2 = category2Of(row);
      const hasCategory1 = category1 && !category1.includes("미분류");
      const hasCategory2 = category2 && !category2.includes("미분류");
      const category =
        hasCategory1 && hasCategory2 && category1 !== category2
          ? `${category1} > ${category2}`
          : hasCategory2
            ? category2
            : hasCategory1
              ? category1
              : "미분류";
      byCategory.set(category, (byCategory.get(category) ?? 0) + amountOf(row));
    });
    const items = Array.from(byCategory.entries()).sort((a, b) => b[1] - a[1]);
    const total = Array.from(byCategory.values()).reduce((sum, amount) => sum + amount, 0);
    const max = Math.max(...items.map(([, amount]) => amount), 1);
    return items.map(([name, amount]) => ({
      name,
      amount,
      amountDisplay: wonEok(amount),
      amountKrw: krwEokFromEur(amount, averageEurKrwRate),
      sharePct: total > 0 ? (amount / total) * 100 : 0,
      value: `${formatNumber(total > 0 ? (amount / total) * 100 : 0, 0)}%`,
      width: `${Math.max(4, (amount / max) * 100)}%`
    }));
  }, [averageEurKrwRate, selectedBrandRows]);
  const lineCompositionRows = allLineCompositionRows.slice(0, 5);

  const selectedBrandKey = selectedBrand?.brand ?? "none";
  const selectedBrandDisplayName = displayBrandName(selectedBrand?.brand ?? "-");
  const selectedBrandReportParams = {
    brand: selectedBrand?.brand ?? "",
    display_brand: selectedBrandDisplayName,
    brand_role: reportBrandRole(selectedBrand?.brand ?? ""),
    summary_scope: "selected_range_including_partial_months",
    seasonality_scope: "complete_month_calendar_average",
    complete_month_count: brandCompleteMonthCount,
    excluded_month_count: brandExcludedMonthCount,
    uncategorized_row_count: brandUncategorizedQuality.affectedRows,
    uncategorized_amount_share_pct: brandUncategorizedQuality.affectedSharePct,
    ...reportAnalysisPeriodParams(analysisOptions)
  };
  const brandOverviewBlock: ReportBlock = {
    id: `brand:overview:${selectedBrandKey}`,
    title: `${selectedBrandDisplayName} 브랜드 요약`,
    subtitle: `매출 ${selectedBrand ? wonEok(selectedBrand.amount) : "-"} · 판매수량 ${formatNumber(selectedBrand?.qty ?? 0)} · SKU ${formatNumber(selectedBrand?.skus.size ?? 0)}개 · 판매 국가 ${formatNumber(selectedBrand?.countries.size ?? 0)}개국`,
    meta: "선택 브랜드 핵심 지표",
    type: "brand_overview",
    kind: "kpi",
    section: "brand",
    size: "full",
    params: selectedBrandReportParams,
    snapshot: {
      columns: ["브랜드명", "매출액", "매출표시", "원화표시", "판매수량", "SKU수", "국가수", "점유율"],
      rows: selectedBrand ? [{
        브랜드명: selectedBrandDisplayName,
        brand_original: selectedBrand.brand,
        brand_role: reportBrandRole(selectedBrand.brand),
        is_self: reportBrandRole(selectedBrand.brand) === "self",
        매출액: selectedBrand.amount,
        매출표시: wonEok(selectedBrand.amount),
        원화표시: selectedBrandKrw,
        판매수량: selectedBrand.qty,
        SKU수: selectedBrand.skus.size,
        국가수: selectedBrand.countries.size,
        점유율: `${formatNumber(selectedShare, 1)}%`
      }] : []
    }
  };
  const brandSkuConcentrationBlock: ReportBlock = {
    id: `brand:sku-concentration:${selectedBrandKey}`,
    title: `${selectedBrandDisplayName} SKU 집중도`,
    subtitle: `브랜드 전체 매출 기준 상위 ${formatNumber(skuConcentrationRows.length)}개 SKU · 합계 ${formatNumber(selectedTopSkuShare, 1)}%`,
    meta: "브랜드별 SKU 매출 집중도",
    type: "brand_sku_concentration",
    kind: "share",
    section: "brand",
    size: "full",
    params: selectedBrandReportParams,
    snapshot: {
      columns: ["순위", "SKU", "상품명", "카테고리", "매출액", "매출표시", "판매수량", "매출비중"],
      rows: selectedSkuRows.map((row, index) => ({
        순위: index + 1,
        SKU: row.sku,
        상품명: row.name,
        카테고리: row.category,
        매출액: row.amount,
        매출표시: wonEok(row.amount),
        판매수량: row.qty,
        매출비중: skuConcentrationRows[index]?.value ?? ""
      }))
    }
  };
  const brandCountryDistributionBlock: ReportBlock = {
    id: `brand:country-distribution:${selectedBrandKey}`,
    title: `${selectedBrandDisplayName} 국가 분포`,
    subtitle: `선택 기간 매출 기준 상위 판매 국가`,
    meta: "브랜드별 국가 매출 분포",
    type: "brand_country_distribution",
    kind: "share",
    section: "brand",
    size: "half",
    params: selectedBrandReportParams,
    snapshot: {
      columns: ["순위", "국가", "매출비중"],
      rows: countryDistributionRows.map((row, index) => ({ 순위: index + 1, 국가: row.name, 매출비중: row.value }))
    }
  };
  const brandLineCompositionBlock: ReportBlock = {
    id: `brand:line-composition:${selectedBrandKey}`,
    title: `${selectedBrandDisplayName} 제품군·라인 구성비`,
    subtitle: `선택 기간 매출 기준 상위 제품군`,
    meta: "브랜드별 제품군 및 라인 구성",
    type: "brand_line_composition",
    kind: "share",
    section: "brand",
    size: "full",
    params: selectedBrandReportParams,
    snapshot: {
      columns: ["순위", "제품군·라인", "매출비중"],
      rows: lineCompositionRows.map((row, index) => ({ 순위: index + 1, "제품군·라인": row.name, 매출비중: row.value }))
    }
  };
  const brandComparisonBlock: ReportBlock = {
    id: `brand:comparison:${brandComparisonSeries.map((row) => row.rank).join("-") || "empty"}`,
    title: "브랜드 월별 시즌성 비교",
    subtitle: `완료월 기준 월 매출 분포 · ${formatNumber(brandComparisonSeries.length)}개 브랜드`,
    meta: "선택 브랜드별 유효 월 매출 비중 비교",
    type: "brand_comparison",
    kind: "trend",
    section: "brand",
    size: "half",
    params: {
      brands: brandComparisonSeries.map((row) => row.brand),
      eur_krw_rate: averageEurKrwRate,
      seasonality_scope: "complete_month_calendar_average",
      complete_month_count: brandCompleteMonthCount,
      excluded_month_count: brandExcludedMonthCount,
      ...reportAnalysisPeriodParams(analysisOptions)
    },
    snapshot: {
      columns: ["브랜드명", "최고월", "최고 비중", "월", "관측 완료월 수", "월평균 매출액", "매출표시", "브랜드 내 월평균 매출 비중"],
      rows: brandComparisonSeries.flatMap((series) => series.monthly.map((row) => ({
        브랜드명: displayBrandName(series.brand),
        brand_original: series.brand,
        brand_role: reportBrandRole(series.brand),
        is_self: reportBrandRole(series.brand) === "self",
        최고월: series.peakMonth > 0 ? `${series.peakMonth}월` : "-",
        "최고 비중": `${formatNumber(series.peakShare, 1)}%`,
        월: `${row.month}월`,
        "관측 완료월 수": row.observationCount,
        "월평균 매출액": row.observationCount > 0 ? row.amount : null,
        매출표시: row.observationCount > 0 ? wonEok(row.amount) : "데이터 없음",
        "브랜드 내 월평균 매출 비중": row.share === null ? "데이터 없음" : `${formatNumber(row.share, 1)}%`
      })))
    }
  };

  const monthlySales = useMemo(() => {
    return buildCalendarMonthAverageProfile({
      rows: selectedMonthlyRows,
      calendarMonths: brandSeasonMonths,
      eligibleMonthKeys: brandSeasonalityMonthKeys,
      monthKey: monthKeyOf,
      amount: amountOf
    });
  }, [brandSeasonMonths, brandSeasonalityMonthKeys, selectedMonthlyRows]);
  const maxMonthlyAmount = Math.max(...monthlySales.map((row) => row.amount), 1);
  const peakMonth = monthlySales.reduce((best, row) => (row.amount > best.amount ? row : best), monthlySales[0] ?? { month: 0, amount: 0 });
  const monthlySalesTotal = monthlySales.reduce((sum, row) => sum + row.amount, 0);
  const monthlyShareRows = monthlySales.map((row, index) => ({
    ...row,
    share: monthlySalesTotal > 0 ? (row.amount / monthlySalesTotal) * 100 : 0,
    x: monthlySales.length > 1 ? 38 + (index * 582) / (monthlySales.length - 1) : 329
  }));
  const peakMonthShare = monthlyShareRows.find((row) => row.month === peakMonth.month)?.share ?? 0;
  const brandTopSkuSeasonalityBlock: ReportBlock = {
    id: `brand:top-sku-seasonality:${selectedBrandKey}`,
    title: `${selectedBrandDisplayName} 상위 SKU·월별 판매 시즌성`,
    subtitle: `상위 ${formatNumber(selectedSkuRows.length)}개 SKU · 완료월 연평균 ${peakMonth.amount > 0 ? `피크월 ${peakMonth.month}월 ${formatNumber(peakMonthShare, 1)}%` : "월별 비중 데이터 없음"}`,
    meta: "선택 브랜드 상위 SKU 및 완료월 월평균 매출 비중",
    type: "brand_top_sku_seasonality",
    kind: "trend",
    section: "brand",
    size: "full",
    params: selectedBrandReportParams,
    snapshot: {
      columns: ["구분", "순위", "SKU", "상품명", "카테고리", "관측 완료월 수", "매출액", "매출표시", "판매수량", "월", "매출비중"],
      rows: [
        ...selectedSkuRows.map((row, index) => ({
          구분: "상위 SKU",
          순위: index + 1,
          SKU: row.sku,
          상품명: row.name,
          카테고리: row.category,
          "관측 완료월 수": "",
          매출액: row.amount,
          매출표시: wonEok(row.amount),
          판매수량: row.qty,
          월: "",
          매출비중: ""
        })),
        ...monthlyShareRows.map((row) => ({
          구분: "월별 매출 비중",
          순위: "",
          SKU: "",
          상품명: "",
          카테고리: "",
          "관측 완료월 수": row.observationCount,
          매출액: row.amount,
          매출표시: wonEok(row.amount),
          판매수량: "",
          월: `${row.month}월`,
          매출비중: `${formatNumber(row.share, 1)}%`
        }))
      ]
    }
  };
  const brandSeasonPdfPeakLabel = isShortAnalysisRange ? "완료월 매출 최고" : "완료월 월평균 피크";
  const brandPeakAmountLabel = peakMonth.amount > 0
    ? [wonEok(peakMonth.amount), krwEokFromEur(peakMonth.amount, averageEurKrwRate)].filter(Boolean).join(" / ")
    : "";

  // design-token-audit: report-template-start — standalone print document with its own embedded palette
  const exportBrandReportPdf = () => {
    if (exportingBrandPdf) return;
    setExportingBrandPdf(true);
    const generatedAt = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date());
    const fileDate = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date());
    const reportPeriod = analysisPeriodLabel(analysisOptions);
    const reportDataAsOf = longKoreanDateLabel(analysisOptions?.end_date);
    const reportWindow = window.open("", "_blank", "width=1200,height=900");
    if (!reportWindow) {
      setExportingBrandPdf(false);
      return;
    }
    const barRowsHtml = (items: Array<{ name: string; value: string; width: string; sku?: string }>) => items.map((item) => {
      const skuHtml = item.sku
        ? `<span title="상품코드 ${escapeReportHtml(item.sku)}" style="display:block;width:max-content;max-width:100%;margin-top:3px;border-radius:5px;background:#f3f4f6;padding:2px 5px;color:#69707f;font-size:9px;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeReportHtml(item.sku)}</span>`
        : "";
      return `<div class="bar-row"><div class="row-between"><div style="min-width:0;flex:1;line-height:1.25"><strong style="display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden">${escapeReportHtml(item.name)}</strong>${skuHtml}</div><strong style="flex:none;white-space:nowrap;align-self:flex-start">${escapeReportHtml(item.value)}</strong></div><div class="bar-bg"><div class="bar" style="width:${escapeReportHtml(item.width)}"></div></div></div>`;
    }).join("");
    const reportComparisonPeaksHtml = brandComparisonChartSeries.length > 0
      ? `<div style="display:flex;flex-wrap:wrap;gap:7px;margin:2px 0 10px">${brandComparisonChartSeries.map((series) => `<div style="display:flex;align-items:center;gap:7px;border:1px solid #e2e4e8;border-radius:9px;padding:6px 9px"><span style="width:7px;height:7px;border-radius:999px;background:${escapeReportHtml(series.color)}"></span><span style="font-size:10px;font-weight:900">${escapeReportHtml(displayBrandName(series.brand))}</span><span style="font-size:10px;font-weight:900;color:${escapeReportHtml(series.color)}">최고월 ${series.peakMonth > 0 ? `${series.peakMonth}월 · ${formatNumber(series.peakShare, 1)}%` : "-"}</span></div>`).join("")}</div>`
      : "";
    const reportComparisonBaselineY = brandComparisonBaselineShare !== null && brandComparisonBaselineShare <= brandComparisonAxisMax
      ? 190 - (brandComparisonBaselineShare / brandComparisonAxisMax) * 140
      : null;
    const reportComparisonBaselineHtml = reportComparisonBaselineY === null
      ? ""
      : `<line x1="52" x2="1180" y1="${reportComparisonBaselineY}" y2="${reportComparisonBaselineY}" stroke="#9aa1ad" stroke-dasharray="2 4"/><text x="1180" y="${reportComparisonBaselineY - 4}" text-anchor="end" fill="#9aa1ad" font-size="9" font-weight="700">균등 분포 ${formatNumber(brandComparisonBaselineShare!, 1)}%</text>`;
    const reportComparisonSegmentsHtml = brandComparisonChartSeries.map((series) => series.points.slice(0, -1).map((row, index) => {
      const next = series.points[index + 1];
      if (row.share === null || next.share === null) return "";
      return `<line x1="${row.x}" y1="${row.y}" x2="${next.x}" y2="${next.y}" stroke="${escapeReportHtml(series.color)}" stroke-width="2.25" stroke-linecap="round"/>`;
    }).join("")).join("");
    const reportComparisonPointsHtml = brandComparisonChartSeries.map((series) => series.points.map((row) => {
      if (row.share === null) return `<text x="${row.x}" y="204" text-anchor="middle" fill="#9aa1ad" font-size="10" font-weight="900">—</text>`;
      const isPeak = row.month === series.peakMonth && row.amount > 0;
      return `<circle cx="${row.x}" cy="${row.y}" r="${isPeak ? 4.5 : 2.75}" fill="${isPeak ? escapeReportHtml(series.color) : "#fff"}" stroke="${escapeReportHtml(series.color)}" stroke-width="1.75"/><text x="${row.x}" y="${Math.max(11, row.y - 8 - (series.colorIndex % 3) * 9)}" text-anchor="middle" fill="${escapeReportHtml(series.color)}" stroke="#fff" stroke-width="3" paint-order="stroke" font-size="8" font-weight="900">${formatNumber(row.share, 1)}%</text>`;
    }).join("")).join("");
    const reportComparisonChartHtml = brandComparisonChartSeries.length > 0
      ? `<svg viewBox="0 0 1220 230" style="display:block;width:100%;height:auto;overflow:visible" aria-label="브랜드별 월 매출 분포 비교">${[50, 120, 190].map((y, index) => { const guideValue = index === 0 ? brandComparisonAxisMax : index === 1 ? brandComparisonAxisMax / 2 : 0; return `<line x1="52" x2="1180" y1="${y}" y2="${y}" stroke="#e2e4e8" stroke-dasharray="${index === 2 ? "0" : "4 5"}"/><text x="44" y="${y + 3}" text-anchor="end" fill="#9aa1ad" font-size="9" font-weight="700">${formatNumber(guideValue, index === 1 ? 1 : 0)}%</text>`; }).join("")}${reportComparisonBaselineHtml}${reportComparisonSegmentsHtml}${reportComparisonPointsHtml}${brandSeasonMonths.map((month, index) => { const x = brandSeasonMonths.length > 1 ? 52 + (index * 1128) / (brandSeasonMonths.length - 1) : 616; return `<text x="${x}" y="220" text-anchor="middle" fill="#9aa1ad" font-size="9" font-weight="700">${month}월</text>`; }).join("")}</svg>`
      : `<div class="muted">비교할 브랜드가 없습니다.</div>`;
    const reportComparisonSectionHtml = `<div class="section-head" style="margin-top:18px"><h2>브랜드별 월 매출 분포</h2><span class="muted">완료월 기준 · 유효 월별 비중 합계 100%</span></div>${reportComparisonPeaksHtml}${reportComparisonChartHtml}`;
    const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8" /><title>브랜드 분석 리포트 ${escapeReportHtml(fileDate)}</title><style>@page{size:A4 landscape;margin:0}*{box-sizing:border-box;-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}body{margin:0;background:#f3f4f6;color:#05060a;font-family:Arial,"Malgun Gothic",sans-serif}.page{padding:24px}.header{display:flex;justify-content:space-between;gap:24px;margin-bottom:18px}.eyebrow{font-size:11px;font-weight:900;color:#e90035}h1{margin:4px 0 8px;font-size:24px}h2{margin:0;font-size:15px}.desc,.muted{color:#69707f;font-weight:700}.desc{font-size:12px}.date{text-align:right;font-size:11px}.rate-note{margin-top:8px;color:#69707f;font-size:11px;font-weight:800}.grid{display:grid;gap:14px}.columns{grid-template-columns:1fr 1fr;align-items:start}.section,.metric{background:#fff;border:1px solid #e2e4e8;border-radius:14px;box-shadow:0 6px 16px rgba(15,23,42,.06)}.section{padding:18px}.section-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}table{width:100%;border-collapse:collapse}td{border-bottom:1px solid #edf0f3;padding:10px 0;font-size:12px}.rank{width:28px;color:#9aa1ad;font-weight:900}.name{font-weight:900}.amount{text-align:right;font-weight:950;white-space:nowrap}.accent{color:#e90035}.bar-bg{height:6px;border-radius:999px;background:#f0f1f4;overflow:hidden;margin-top:8px}.bar{height:100%;border-radius:999px;background:#e90035}.blackbar{background:#15171a}.brand-card{padding:18px;background:#fff;border:1px solid #e2e4e8;border-radius:14px;box-shadow:0 6px 16px rgba(15,23,42,.06)}.brand-head{display:flex;justify-content:space-between;border-bottom:1px solid #edf0f3;padding-bottom:16px}.brand-head h2{font-size:24px;margin-top:4px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid #edf0f3}.metric{box-shadow:none;border-width:0 1px 0 0;border-radius:0;padding:15px}.metric:last-child{border-right:0}.label{color:#69707f;font-size:11px;font-weight:800}.value{margin-top:8px;font-size:18px;font-weight:950}.row-between{display:flex;justify-content:space-between;gap:12px}.bar-row{margin-bottom:13px;font-size:12px}.season{display:grid;gap:5px;align-items:end;height:82px;margin-top:14px}.month{display:flex;flex-direction:column;justify-content:end;gap:6px;height:100%;text-align:center;color:#9aa1ad;font-size:9px;font-weight:800}.month-bar{width:100%;border-radius:4px 4px 0 0;background:rgba(233,0,53,.72)}.growth-columns{grid-template-columns:1fr 1fr}.growth-panel{border:1px solid #edf0f3;border-radius:12px;padding:14px}.growth-panel h3{margin:0 0 8px;font-size:12px}.growth-row{display:grid;grid-template-columns:24px 1fr auto;gap:8px;align-items:center;border-bottom:1px solid #edf0f3;padding:9px 0;font-size:11px}.growth-row:last-child{border-bottom:0}.growth-value{font-size:12px;font-weight:950}.positive{color:#0a9f4b}@media print{body{background:#f3f4f6}.page{padding:12mm}}</style></head><body><main class="page"><header class="header"><div><div class="eyebrow">분석 · INSIGHT</div><h1>브랜드 기준 분석 리포트</h1><div class="desc">CMS 판매 분석 데이터 기준 브랜드별 매출 집중도와 국가 분포를 요약합니다.</div>${exchangeBasis ? `<div class="rate-note">${escapeReportHtml(exchangeBasis)}</div>` : ""}</div><div class="date muted">생성일<br/>${escapeReportHtml(generatedAt)}</div></header><section class="grid columns"><div class="section"><div class="section-head"><h2>브랜드별 판매 순위</h2><span class="muted">매출 기준</span></div><table><tbody>${brandSummaries.slice(0, 8).map((row) => `<tr><td class="rank ${row.brand === selectedBrand?.brand ? "accent" : ""}">${row.rank}</td><td><div class="name">${escapeReportHtml(displayBrandName(row.brand))}</div><div class="bar-bg"><div class="bar ${row.brand === selectedBrand?.brand ? "" : "blackbar"}" style="width:${escapeReportHtml(row.width)}"></div></div></td><td class="amount">${escapeReportHtml(wonEok(row.amount))}<br/><span class="muted">${escapeReportHtml(krwEokFromEur(row.amount, averageEurKrwRate) || `${formatNumber(row.skus.size)} SKU`)}</span></td></tr>`).join("")}</tbody></table></div><div class="grid"><div class="brand-card"><div class="brand-head"><div><div class="label">선택 브랜드</div><h2>${escapeReportHtml(displayBrandName(selectedBrand?.brand ?? "-"))}</h2></div><strong class="accent">점유율 ${escapeReportHtml(formatNumber(selectedShare, 1))}%</strong></div><div class="metrics">${selectedBrandMetrics.map(([label, value]) => `<div class="metric"><div class="label">${escapeReportHtml(label)}</div><div class="value">${escapeReportHtml(value)}</div></div>`).join("")}</div></div><div class="grid columns"><section class="section"><div class="section-head"><h2>SKU 집중도</h2></div>${barRowsHtml(skuConcentrationRows)}</section><section class="section"><div class="section-head"><h2>국가 분포</h2></div>${barRowsHtml(countryDistributionRows)}</section></div><section class="section"><div class="section-head"><h2>제품군 · 라인 구성비</h2></div>${barRowsHtml(lineCompositionRows)}</section></div></section><section class="section" style="margin-top:14px"><div class="section-head"><h2>브랜드별 성장 변화</h2><span class="muted">${escapeReportHtml(`${brandGrowthBasisLabel} · ${brandGrowthPeriodLabel}`)}</span></div><div class="grid growth-columns"><div class="growth-panel"><h3 class="positive">성장 상위 · 금액 증가순</h3>${risingBrandRows.length > 0 ? risingBrandRows.map((row, index) => `<div class="growth-row"><span class="rank">${index + 1}</span><span><strong>${escapeReportHtml(displayBrandName(row.brand))}</strong></span><span class="growth-value positive">${escapeReportHtml(signedEur(row.deltaAmount))}<br/><span class="muted">${escapeReportHtml([signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate), row.growth, `${wonEok(row.previousAmount)} → ${wonEok(row.currentAmount)}`].filter(Boolean).join(" · "))}</span></span></div>`).join("") : `<div class="muted">성장한 브랜드가 없습니다.</div>`}</div><div class="growth-panel"><h3 class="accent">감소 상위 · 금액 감소순</h3>${decliningBrandRows.length > 0 ? decliningBrandRows.map((row, index) => `<div class="growth-row"><span class="rank">${index + 1}</span><span><strong>${escapeReportHtml(displayBrandName(row.brand))}</strong></span><span class="growth-value accent">${escapeReportHtml(signedEur(row.deltaAmount))}<br/><span class="muted">${escapeReportHtml([signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate), row.vanished ? `판매 소멸 · ${row.growth}` : row.growth, `${wonEok(row.previousAmount)} → ${wonEok(row.currentAmount)}`].filter(Boolean).join(" · "))}</span></span></div>`).join("") : `<div class="muted">감소한 브랜드가 없습니다.</div>`}</div></div></section><section class="section" style="margin-top:14px"><div class="section-head"><h2>상위 SKU</h2><span class="muted">선택 기간 판매금액 기준</span></div><table><tbody>${selectedSkuRows.map((row, index) => `<tr><td class="rank">${index + 1}</td><td><div class="name">${escapeReportHtml(row.name)}</div><div class="muted">${escapeReportHtml(row.category)}</div></td><td class="amount">${escapeReportHtml(wonEok(row.amount))}<br/><span class="muted">${escapeReportHtml(krwEokFromEur(row.amount, averageEurKrwRate))}</span></td></tr>`).join("")}</tbody></table><div class="section-head" style="margin-top:18px"><h2>월별 판매 시즌성</h2><span class="muted">${peakMonth.amount > 0 ? `${peakMonth.month}월 ${brandSeasonPdfPeakLabel} · ${brandPeakAmountLabel}` : "시즌 데이터 없음"}</span></div><div class="season" style="grid-template-columns:repeat(${Math.max(monthlySales.length, 1)},1fr)">${monthlySales.map((row) => `<div class="month"><div class="month-bar" style="height:${row.amount > 0 ? Math.max(6, (row.amount / maxMonthlyAmount) * 70) : 2}px${row.amount > 0 ? "" : ";background:#e2e4e8"}"></div><span>${row.month}월</span></div>`).join("")}</div></section></main><script>window.addEventListener("load",()=>{document.title="brand-analysis-report-${escapeReportHtml(fileDate)}";setTimeout(()=>{window.focus();window.print();},250);});</script></body></html>`;
    const legacySeasonalityHtml = `<div class="section-head" style="margin-top:18px"><h2>월별 판매 시즌성</h2><span class="muted">${peakMonth.amount > 0 ? `${peakMonth.month}월 ${brandSeasonPdfPeakLabel} · ${brandPeakAmountLabel}` : "시즌 데이터 없음"}</span></div><div class="season" style="grid-template-columns:repeat(${Math.max(monthlySales.length, 1)},1fr)">${monthlySales.map((row) => `<div class="month"><div class="month-bar" style="height:${row.amount > 0 ? Math.max(6, (row.amount / maxMonthlyAmount) * 70) : 2}px${row.amount > 0 ? "" : ";background:#e2e4e8"}"></div><span>${row.month}월</span></div>`).join("")}</div>`;
    const reportHtml = injectReportWatermark(html.replace(legacySeasonalityHtml, reportComparisonSectionHtml).replace(
      '<div class="desc">CMS 판매 분석 데이터 기준 브랜드별 매출 집중도와 국가 분포를 요약합니다.</div>',
      `<div class="desc">CMS 판매 분석 데이터 기준 브랜드별 매출 집중도와 국가 분포를 요약합니다.</div><div style="margin-top:8px;color:rgb(48,55,70);font-size:11px;font-weight:900">집계 기간 ${escapeReportHtml(reportPeriod)} · 판매 데이터 기준 ${escapeReportHtml(reportDataAsOf)}</div>`
    ));
    reportWindow.document.open();
    reportWindow.document.write(reportHtml);
    reportWindow.document.close();
    window.setTimeout(() => setExportingBrandPdf(false), 800);
  };
  // design-token-audit: report-template-end

  return {
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
    savedReportBlockIds,
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
    exchangeBasis,
    brandGrowthPeriodLabel,
    brandYtdPeriodLabel,
    brandYoyByName,
    allBrandsReportBlock,
    hasBrandQoqGrowth,
    hasBrandQuarterYoyGrowth,
    brandGrowthRows,
    risingBrandRows,
    decliningBrandRows,
    allRisingBrandRows,
    allDecliningBrandRows,
    comparisonNoSalesBrandRows,
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
    brandOverviewBlock,
    brandSkuConcentrationBlock,
    brandCountryDistributionBlock,
    brandLineCompositionBlock,
    brandComparisonBlock,
    peakMonth,
    brandTopSkuSeasonalityBlock,
    exportBrandReportPdf
  };
}
