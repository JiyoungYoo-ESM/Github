+"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, Check, FileText } from "lucide-react";
import { getSeasonTrendAnalysis } from "@/lib/api";
import { displayBrandName } from "@/lib/brand-display";
import { formatAnalysisMonthLabel } from "@/lib/cross-analysis-mom";
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
  exchangeRateBasisLabel,
  krwEokFromEur,
  krwEokValueFromEur,
  signedEur,
  signedKrwEokFromEur,
  wonEok
} from "../../lib/currency-format";
import { escapeReportHtml, injectReportWatermark } from "../../lib/report-html";
import { reportAnalysisPeriodParams } from "../../lib/workspace-format";
import { AnalysisPeriodBadge, AnalysisPeriodCaveat } from "../../shared/AnalysisPeriod";
import { BrandBar, SkuNameWithCode } from "../../shared/BrandBar";
import { OrderMetricCard } from "../../shared/OrderMetricCard";
import {
  availableComparisonBasis,
  automaticComparisonBasis,
  automaticGrowthTargetMonths,
  comparableYearWindow,
  comparisonBasisFromValue,
  completedYtdComparableYearWindow,
  completedYtdPeriodLabel,
  compactYoyPeriodLabel,
  growthDisplayLabel,
  growthLabelsForMonthPair,
  growthBadgeClass,
  isGrowthStatusLabel,
  latestComparableMonths,
  previousMonthKey,
  previousYearMonthKey,
  shortMonthPairLabel,
  ytdAmountComparisonsByLabel,
  yoyBucketOf
} from "../../lib/yoy-comparison";

import { lowBaseAmount } from "@/lib/low-base";
import { CountryRankRow, ShareCard } from "./CountryScreenParts";
import {
  comparableQuarterKeys,
  completeQuarterKeys,
  formatQuarterLabel,
  previousQuarterKey,
  previousYearQuarterKey,
  quarterKeyFromMonthKey,
  type CountryQuarterGrowthBasis
} from "./country-quarter-growth";
import { useCountryScreenData } from "./useCountryScreenData";

export function useCountryScreenModel({
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
  const {
    seasonRows,
    skuSourceRows,
    countryMonthCoverage,
    skuSummaryComplete,
    loading,
    loadFailed,
    comparisonBasis,
    setComparisonBasis,
    analysisOptions
  } = useCountryScreenData();
  const [selectedCountry, setSelectedCountry] = useState("");
  const [selectedRegion, setSelectedRegion] = useState("");
  const [countryGrowthBasis, setCountryGrowthBasis] = useState<CountryQuarterGrowthBasis>("yoy");
  const [countryGrowthTargetQuarter, setCountryGrowthTargetQuarter] = useState("");
  const [countryMomTargetMonth, setCountryMomTargetMonth] = useState("");
  const [countryYoyTargetMonth, setCountryYoyTargetMonth] = useState("");
  const [exportingCountryPdf, setExportingCountryPdf] = useState(false);
  const [countryPage, setCountryPage] = useState(1);
  const savedReportBlockIds = useMemo(() => new Set(reportBlocks.map((block) => block.id)), [reportBlocks]);

  const countryRows = useMemo(() => {
    const base = buildCountrySummary(seasonRows);
    const amountByCountry = new Map<string, number>();
    seasonRows.forEach((row) => {
      const country = countryOf(row);
      amountByCountry.set(country, (amountByCountry.get(country) ?? 0) + amountOf(row));
    });
    const total = Array.from(amountByCountry.values()).reduce((sum, value) => sum + value, 0);
    return base
      .map((row) => {
        const amount = amountByCountry.get(row.country) ?? row.amount;
        return { ...row, amount, amountShare: total > 0 ? (amount / total) * 100 : row.share };
      })
      .sort((a, b) => b.amount - a.amount);
  }, [seasonRows]);
  const totalAmount = countryRows.reduce((sum, row) => sum + row.amount, 0);
  const activeCountryCount = countryRows.length;
  const activeBrandCount = useMemo(() => new Set(skuSourceRows.map((row) => brandOf(row)).filter(Boolean)).size, [skuSourceRows]);
  const activeSkuCount = useMemo(() => new Set(skuSourceRows.map((row) => skuCodeOf(row)).filter((sku) => sku && sku !== "-")).size, [skuSourceRows]);
  // 구버전 저장 결과(countrySkuSummary 부재)는 상위 N개 캡 기준이라 하한값임을 "+"로 표기한다.
  const brandCountDisplay = `${formatNumber(activeBrandCount)}개${skuSummaryComplete ? "" : "+"}`;
  const skuCountDisplay = `${formatNumber(activeSkuCount)}${skuSummaryComplete ? "" : "+"}`;
  const staleCountCaveat = skuSummaryComplete ? undefined : "구버전 결과 · 상위 SKU 기준(재분석 시 정확)";
  const effectiveComparisonBasis = useMemo<ComparisonBasis>(
    () => (comparisonBasis === "none" ? "none" : "yoy"),
    [comparisonBasis]
  );
  const countryGrowthMonthOptions = useMemo(() => {
    const availableOptions = Array.from(
      new Set(seasonRows.map((row) => monthKeyOf(row)).filter((month) => /^\d{4}-\d{2}$/.test(month)))
    ).sort();
    if (countryMonthCoverage.length === 0) return availableOptions;
    const completeMonthSet = completeSeasonMonthKeys(countryMonthCoverage);
    return availableOptions.filter((month) => completeMonthSet.has(month));
  }, [countryMonthCoverage, seasonRows]);
  const countryCompleteQuarterOptions = useMemo(
    () => completeQuarterKeys(countryGrowthMonthOptions),
    [countryGrowthMonthOptions]
  );
  const countryQoqTargetOptions = useMemo(
    () => comparableQuarterKeys(countryCompleteQuarterOptions, "qoq"),
    [countryCompleteQuarterOptions]
  );
  const countryQuarterYoyTargetOptions = useMemo(
    () => comparableQuarterKeys(countryCompleteQuarterOptions, "yoy"),
    [countryCompleteQuarterOptions]
  );
  const activeCountryQuarterOptions = countryGrowthBasis === "yoy"
    ? countryQuarterYoyTargetOptions
    : countryQoqTargetOptions;
  useEffect(() => {
    setCountryGrowthTargetQuarter((current) =>
      activeCountryQuarterOptions.includes(current)
        ? current
        : activeCountryQuarterOptions.at(-1) ?? ""
    );
  }, [activeCountryQuarterOptions]);
  const countryMomTargetOptions = useMemo(
    () => automaticGrowthTargetMonths(countryGrowthMonthOptions, previousMonthKey),
    [countryGrowthMonthOptions]
  );
  const countryYoyTargetOptions = useMemo(
    () => automaticGrowthTargetMonths(countryGrowthMonthOptions, previousYearMonthKey),
    [countryGrowthMonthOptions]
  );
  useEffect(() => {
    if (countryGrowthMonthOptions.length < 2) return;
    setCountryMomTargetMonth((current) =>
      countryMomTargetOptions.includes(current) ? current : countryMomTargetOptions.at(-1) ?? ""
    );
    setCountryYoyTargetMonth((current) =>
      countryYoyTargetOptions.includes(current) ? current : countryYoyTargetOptions.at(-1) ?? ""
    );
  }, [countryGrowthMonthOptions, countryMomTargetOptions, countryYoyTargetOptions]);
  const startDateText = String(analysisOptions?.start_date ?? "");
  const endDateText = String(analysisOptions?.end_date ?? "");
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
  const countrySeasonMonths = isShortAnalysisRange ? rangeMonthNumbers : Array.from({ length: 12 }, (_, index) => index + 1);
  const countryYoyComparisonMonth = previousYearMonthKey(countryYoyTargetMonth);
  const countryMomComparisonMonth = previousMonthKey(countryMomTargetMonth);
  const countryCompleteMonthSet = useMemo(
    () => new Set(countryGrowthMonthOptions),
    [countryGrowthMonthOptions]
  );
  const countryYtdWindow = useMemo(
    () => completedYtdComparableYearWindow(
      seasonRows,
      countryMonthCoverage.length > 0 ? countryCompleteMonthSet : undefined
    ),
    [countryCompleteMonthSet, countryMonthCoverage.length, seasonRows]
  );
  const countryYtdComparisons = useMemo(
    () => ytdAmountComparisonsByLabel(seasonRows, countryYtdWindow, countryOf),
    [countryYtdWindow, seasonRows]
  );
  const countryYoyByName = useMemo(
    () => new Map(Array.from(countryYtdComparisons, ([country, comparison]) => [country, comparison.growth])),
    [countryYtdComparisons]
  );
  const countryYtdPeriodLabel = completedYtdPeriodLabel(countryYtdWindow);
  const countryMomByName = useMemo(
    () => growthLabelsForMonthPair(seasonRows, countryMomTargetMonth, countryMomComparisonMonth, countryOf),
    [countryMomComparisonMonth, countryMomTargetMonth, seasonRows]
  );
  const countryMetricDeltas = useMemo(() => {
    const result: {
      sales?: { text: string; tone: "brand" | "pos" | "muted" };
      countries?: { text: string; tone: "brand" | "pos" | "muted" };
      brands?: { text: string; tone: "brand" | "pos" | "muted" };
      skus?: { text: string; tone: "brand" | "pos" | "muted" };
    } = {};
    if (effectiveComparisonBasis === "none") return result;

    if (effectiveComparisonBasis === "mom") {
      const salesMonths = latestComparableMonths(seasonRows);
      if (salesMonths) {
        const [latestMonth, previousMonth] = salesMonths;
        let currentSales = 0;
        let previousSales = 0;
        const currentCountries = new Set<string>();
        const previousCountries = new Set<string>();

        seasonRows.forEach((row) => {
          const month = monthKeyOf(row);
          const country = countryOf(row);
          if (month === latestMonth) {
            currentSales += amountOf(row);
            if (country) currentCountries.add(country);
          } else if (month === previousMonth) {
            previousSales += amountOf(row);
            if (country) previousCountries.add(country);
          }
        });

        const momLabel = growthDisplayLabel(currentSales, previousSales);
        if (momLabel) {
          result.sales = {
            text: `${momLabel} (${shortMonthPairLabel(salesMonths)})`,
            tone: isGrowthStatusLabel(momLabel) ? "muted" : momLabel.startsWith("-") ? "brand" : "pos"
          };
        }
        const countryDelta = currentCountries.size - previousCountries.size;
        if (countryDelta !== 0) {
          result.countries = {
            text: `${previousMonth.replace("-", ".")} → ${latestMonth.replace("-", ".")} · ${formatNumber(Math.abs(countryDelta))}개국 ${countryDelta > 0 ? "증가" : "감소"}`,
            tone: countryDelta > 0 ? "pos" : "brand"
          };
        }
      }

      const skuMonths = latestComparableMonths(skuSourceRows);
      if (skuMonths) {
        const [latestMonth, previousMonth] = skuMonths;
        const currentBrands = new Set<string>();
        const previousBrands = new Set<string>();
        const currentSkus = new Set<string>();
        const previousSkus = new Set<string>();

        skuSourceRows.forEach((row) => {
          const month = monthKeyOf(row);
          const brand = brandOf(row);
          const sku = skuCodeOf(row);
          if (month === latestMonth) {
            if (brand) currentBrands.add(brand);
            if (sku && sku !== "-") currentSkus.add(sku);
          } else if (month === previousMonth) {
            if (brand) previousBrands.add(brand);
            if (sku && sku !== "-") previousSkus.add(sku);
          }
        });

        const brandDelta = currentBrands.size - previousBrands.size;
        const skuDelta = currentSkus.size - previousSkus.size;
        if (brandDelta !== 0) {
          result.brands = { text: `${brandDelta > 0 ? "+" : ""}${formatNumber(brandDelta)}개 (${shortMonthPairLabel(skuMonths)})`, tone: brandDelta > 0 ? "pos" : "brand" };
        }
        if (skuDelta !== 0) {
          result.skus = { text: `${skuDelta > 0 ? "+" : ""}${formatNumber(skuDelta)} (${shortMonthPairLabel(skuMonths)})`, tone: skuDelta > 0 ? "pos" : "brand" };
        }
      }
      return result;
    }

    const salesWindow = countryYtdWindow;
    if (salesWindow) {
      let currentSales = 0;
      let previousSales = 0;
      const currentCountries = new Set<string>();
      const previousCountries = new Set<string>();

      seasonRows.forEach((row) => {
        const bucket = yoyBucketOf(row, salesWindow);
        const country = countryOf(row);
        if (bucket === "current") {
          currentSales += amountOf(row);
          if (country) currentCountries.add(country);
        } else if (bucket === "previous") {
          previousSales += amountOf(row);
          if (country) previousCountries.add(country);
        }
      });

      const yoyLabel = growthDisplayLabel(currentSales, previousSales);
      if (yoyLabel) {
        result.sales = {
          text: yoyLabel,
          tone: isGrowthStatusLabel(yoyLabel) ? "muted" : yoyLabel.startsWith("-") ? "brand" : "pos"
        };
      }
      const countryDelta = currentCountries.size - previousCountries.size;
      if (countryDelta !== 0) {
        result.countries = {
          text: `${compactYoyPeriodLabel(salesWindow, salesWindow.previousYear)} → ${compactYoyPeriodLabel(salesWindow, salesWindow.latestYear)} · ${formatNumber(Math.abs(countryDelta))}개국 ${countryDelta > 0 ? "증가" : "감소"}`,
          tone: countryDelta > 0 ? "pos" : "brand"
        };
      }
    }

    const skuWindow = completedYtdComparableYearWindow(
      skuSourceRows,
      countryMonthCoverage.length > 0 ? countryCompleteMonthSet : undefined
    );
    if (skuWindow) {
      const currentBrands = new Set<string>();
      const previousBrands = new Set<string>();
      const currentSkus = new Set<string>();
      const previousSkus = new Set<string>();

      skuSourceRows.forEach((row) => {
        const bucket = yoyBucketOf(row, skuWindow);
        const brand = brandOf(row);
        const sku = skuCodeOf(row);
        if (bucket === "current") {
          if (brand) currentBrands.add(brand);
          if (sku && sku !== "-") currentSkus.add(sku);
        } else if (bucket === "previous") {
          if (brand) previousBrands.add(brand);
          if (sku && sku !== "-") previousSkus.add(sku);
        }
      });

      const brandDelta = currentBrands.size - previousBrands.size;
      const skuDelta = currentSkus.size - previousSkus.size;
      if (brandDelta !== 0) {
        result.brands = { text: brandDelta > 0 ? `신규 ${formatNumber(brandDelta)}개` : `${formatNumber(brandDelta)}개`, tone: brandDelta > 0 ? "pos" : "brand" };
      }
      if (skuDelta !== 0) {
        result.skus = { text: `${skuDelta > 0 ? "+" : ""}${formatNumber(skuDelta)}`, tone: skuDelta > 0 ? "pos" : "brand" };
      }
    }
    return result;
  }, [
    countryCompleteMonthSet,
    countryMonthCoverage.length,
    countryYtdWindow,
    effectiveComparisonBasis,
    seasonRows,
    skuSourceRows
  ]);
  const averageEurKrwRate =
    Number(analysisOptions?.average_eur_krw_rate) > 0
      ? Number(analysisOptions?.average_eur_krw_rate)
      : null;
  const exchangeBasis = exchangeRateBasisLabel(analysisOptions, averageEurKrwRate);
  const totalAmountKrw = krwEokFromEur(totalAmount, averageEurKrwRate);
  const visibleCountryRows = useMemo(
    () => (selectedRegion ? countryRows.filter((row) => row.region === selectedRegion) : countryRows),
    [countryRows, selectedRegion]
  );
  const effectiveCountry = selectedCountry && visibleCountryRows.some((row) => row.country === selectedCountry) ? selectedCountry : "";
  const selectedCountryRow = countryRows.find((row) => row.country === effectiveCountry);
  const visibleTotalAmount = visibleCountryRows.reduce((sum, row) => sum + row.amount, 0);
  const selectedCountryShare = selectedCountryRow && visibleTotalAmount > 0 ? (selectedCountryRow.amount / visibleTotalAmount) * 100 : 0;
  const maxCountryAmount = Math.max(...visibleCountryRows.map((row) => row.amount), 1);
  const rankRows = visibleCountryRows.map((row, index) => [
    index + 1,
    row.country,
    row.region,
    `${formatNumber(visibleTotalAmount > 0 ? (row.amount / visibleTotalAmount) * 100 : row.amountShare, 1)}%`,
    countryYoyByName.get(row.country) ?? "",
    countryMomByName.get(row.country) ?? "",
    `${Math.max(5, (row.amount / maxCountryAmount) * 100).toFixed(0)}%`,
    wonEok(row.amount)
  ] as const);
  const hasCountryQoqGrowth = countryQoqTargetOptions.length > 0;
  const hasCountryQuarterYoyGrowth = countryQuarterYoyTargetOptions.length > 0;
  const countryGrowthComparisonQuarter = countryGrowthBasis === "yoy"
    ? previousYearQuarterKey(countryGrowthTargetQuarter)
    : previousQuarterKey(countryGrowthTargetQuarter);
  // 활성 성장 기준의 국가별 현재/비교 분기 금액 — 월별 성장률 평균이 아니라 원천 금액을 분기로 합산한다.
  const countryGrowthAmountsByName = useMemo(() => {
    const amounts = new Map<string, { current: number; previous: number }>();
    const add = (country: string, bucket: "current" | "previous", amount: number) => {
      const entry = amounts.get(country) ?? { current: 0, previous: 0 };
      entry[bucket] += amount;
      amounts.set(country, entry);
    };
    if (!countryGrowthTargetQuarter || !countryGrowthComparisonQuarter) return amounts;
    seasonRows.forEach((row) => {
      const country = countryOf(row);
      if (!country) return;
      const quarter = quarterKeyFromMonthKey(monthKeyOf(row));
      if (quarter === countryGrowthTargetQuarter) add(country, "current", amountOf(row));
      else if (quarter === countryGrowthComparisonQuarter) add(country, "previous", amountOf(row));
    });
    return amounts;
  }, [countryGrowthComparisonQuarter, countryGrowthTargetQuarter, seasonRows]);
  const countryGrowthRows = useMemo(
    () =>
      visibleCountryRows.flatMap((row) => {
        const amounts = countryGrowthAmountsByName.get(row.country);
        const currentAmount = amounts?.current ?? 0;
        const previousAmount = amounts?.previous ?? 0;
        if (currentAmount <= 0 && previousAmount <= 0) return [];
        const newEntry = previousAmount <= 0 && currentAmount > 0;
        const lowBase = previousAmount > 0 && previousAmount < lowBaseAmount();
        const value = previousAmount > 0
          ? ((currentAmount - previousAmount) / previousAmount) * 100
          : null;
        const growth = newEntry
          ? "비교 분기 매출 없음"
          : growthDisplayLabel(currentAmount, previousAmount, 0) ?? "-";
        return [
          {
            country: row.country,
            region: row.region,
            growth,
            value,
            currentAmount,
            previousAmount,
            deltaAmount: currentAmount - previousAmount,
            vanished: value !== null && value <= -100 && currentAmount <= 0,
            lowBase,
            newEntry
          }
        ];
      }),
    [countryGrowthAmountsByName, visibleCountryRows]
  );
  // 기준 매출이 작은 국가도 숨기지 않고 포함하되, %가 아닌 금액 변화(임팩트) 기준으로 정렬한다.
  const allRisingCountryRows = useMemo(
    () => countryGrowthRows
      .filter((row) => !row.newEntry && row.value !== null && row.value > 0)
      .sort((a, b) => b.deltaAmount - a.deltaAmount),
    [countryGrowthRows]
  );
  const allDecliningCountryRows = useMemo(
    () => countryGrowthRows
      .filter((row) => !row.newEntry && row.value !== null && row.value < 0)
      .sort((a, b) => a.deltaAmount - b.deltaAmount),
    [countryGrowthRows]
  );
  const risingCountryRows = allRisingCountryRows.slice(0, 5);
  const decliningCountryRows = allDecliningCountryRows.slice(0, 5);
  const newCountryRows = useMemo(
    () => countryGrowthRows
      .filter((row) => row.newEntry)
      .sort((a, b) => b.currentAmount - a.currentAmount),
    [countryGrowthRows]
  );
  const countryGrowthPeriodLabel = countryGrowthTargetQuarter && countryGrowthComparisonQuarter
    ? `${formatQuarterLabel(countryGrowthComparisonQuarter)} → ${formatQuarterLabel(countryGrowthTargetQuarter)}`
    : "비교 기간 없음";
  const countryGrowthBasisLabel = countryGrowthBasis === "yoy"
    ? "분기 YoY · 전년 동일 분기 대비"
    : "분기 QoQ · 전 분기 대비";
  const visibleCountrySet = useMemo(
    () => new Set(visibleCountryRows.map((row) => row.country)),
    [visibleCountryRows]
  );
  const countryQuarterTrend = useMemo(() => {
    const amountByQuarter = new Map<string, number>();
    seasonRows.forEach((row) => {
      if (!visibleCountrySet.has(countryOf(row))) return;
      const quarter = quarterKeyFromMonthKey(monthKeyOf(row));
      if (!quarter || !countryCompleteQuarterOptions.includes(quarter)) return;
      amountByQuarter.set(quarter, (amountByQuarter.get(quarter) ?? 0) + amountOf(row));
    });
    const quarters = countryCompleteQuarterOptions.slice(-8);
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
  }, [countryCompleteQuarterOptions, seasonRows, visibleCountrySet]);
  const countryQuarterTrendMax = Math.max(...countryQuarterTrend.map((row) => row.amount), 1);
  const countryGrowthCurrentTotal = countryGrowthRows.reduce((sum, row) => sum + Math.max(0, row.currentAmount), 0);
  const countryGrowthSnapshotRow = (row: (typeof countryGrowthRows)[number], index: number, category: string) => {
    const currentShare = countryGrowthCurrentTotal > 0 ? (row.currentAmount / countryGrowthCurrentTotal) * 100 : 0;
    return {
      구분: category,
      순위: index + 1,
      국가: row.country,
      권역: row.region,
      "기준 분기 매출": wonEok(row.currentAmount),
      "비교 분기 매출": wonEok(row.previousAmount),
      "매출 증감": signedEur(row.deltaAmount),
      "기준 분기 원화": krwEokFromEur(row.currentAmount, averageEurKrwRate),
      "비교 분기 원화": krwEokFromEur(row.previousAmount, averageEurKrwRate),
      "원화 증감": signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate),
      점유율: `${formatNumber(currentShare, 1)}%`,
      성장률: row.growth,
      비교기간: countryGrowthPeriodLabel,
      // PPT 템플릿 요약은 아래 정규 키로 매출·원화 환산을 읽는다.
      매출액: row.currentAmount,
      매출표시: wonEok(row.currentAmount),
      원화표시: krwEokFromEur(row.currentAmount, averageEurKrwRate)
    };
  };
  const countryGrowthBlock: ReportBlock = {
    id: `country:growth:${selectedRegion || "all"}:${countryGrowthBasis}:${countryGrowthPeriodLabel}`,
    title: "국가별 성장 변화",
    subtitle: `${selectedRegion || "전체 권역"} · ${countryGrowthPeriodLabel} · 상승 ${formatNumber(countryGrowthRows.filter((row) => row.value !== null && row.value > 0).length)}개국 · 하락 ${formatNumber(countryGrowthRows.filter((row) => row.value !== null && row.value < 0).length)}개국`,
    meta: "국가별 매출 성장률 비교",
    type: "country_growth",
    kind: "ranking",
    section: "region",
    size: "full",
    params: {
      region: selectedRegion || "전체",
      comparison_basis: countryGrowthBasis,
      comparison_quarter: countryGrowthComparisonQuarter,
      target_quarter: countryGrowthTargetQuarter,
      period_label: countryGrowthPeriodLabel,
      ...reportAnalysisPeriodParams(analysisOptions)
    },
    snapshot: {
      columns: ["구분", "순위", "국가", "권역", "기준 분기 매출", "비교 분기 매출", "점유율", "성장률", "비교기간"],
      rows: [
        ...allRisingCountryRows.map((row, index) => countryGrowthSnapshotRow(row, index, "성장률 상위")),
        ...allDecliningCountryRows.map((row, index) => countryGrowthSnapshotRow(row, index, "감소율 상위"))
      ]
    }
  };
  const countryGrowthBlockSignature = JSON.stringify(countryGrowthBlock);
  const syncedCountryGrowthBlock = useMemo(
    () => JSON.parse(countryGrowthBlockSignature) as ReportBlock,
    [countryGrowthBlockSignature]
  );

  useEffect(() => {
    if (!savedReportBlockIds.has(syncedCountryGrowthBlock.id)) return;
    onSyncReportBlock(syncedCountryGrowthBlock);
  }, [onSyncReportBlock, savedReportBlockIds, syncedCountryGrowthBlock]);

  const countryPageSize = 10;
  const countryPageCount = Math.max(1, Math.ceil(rankRows.length / countryPageSize));
  const safeCountryPage = Math.min(countryPage, countryPageCount);
  const visibleRankRows = rankRows.slice((safeCountryPage - 1) * countryPageSize, safeCountryPage * countryPageSize);
  const visibleCountryStart = rankRows.length > 0 ? (safeCountryPage - 1) * countryPageSize + 1 : 0;
  const visibleCountryEnd = Math.min(safeCountryPage * countryPageSize, rankRows.length);

  useEffect(() => {
    setCountryPage(1);
  }, [selectedRegion]);

  useEffect(() => {
    if (countryGrowthBasis === "qoq" && !hasCountryQoqGrowth && hasCountryQuarterYoyGrowth) setCountryGrowthBasis("yoy");
    if (countryGrowthBasis === "yoy" && !hasCountryQuarterYoyGrowth && hasCountryQoqGrowth) setCountryGrowthBasis("qoq");
  }, [countryGrowthBasis, hasCountryQoqGrowth, hasCountryQuarterYoyGrowth]);

  useEffect(() => {
    if (countryPage > countryPageCount) setCountryPage(countryPageCount);
  }, [countryPage, countryPageCount]);
  const regionRows = useMemo(() => {
    const buckets = new Map<string, { amount: number; countries: Set<string> }>();
    countryRows.forEach((row) => {
      const current = buckets.get(row.region) ?? { amount: 0, countries: new Set<string>() };
      current.amount += row.amount;
      current.countries.add(row.country);
      buckets.set(row.region, current);
    });
    return Array.from(buckets.entries())
      .map(([region, item]) => ({
        region,
        percent: `${formatNumber(totalAmount > 0 ? (item.amount / totalAmount) * 100 : 0, 1)}%`,
        amountValue: item.amount,
        amountDisplay: wonEok(item.amount),
        amountKrw: krwEokFromEur(item.amount, averageEurKrwRate),
        amount: [wonEok(item.amount), krwEokFromEur(item.amount, averageEurKrwRate)].filter(Boolean).join(" · "),
        countries: `${item.countries.size}개국`
      }))
      .sort((a, b) => {
        // "기타"는 잔여 버킷이므로 금액과 무관하게 항상 맨 뒤에 둔다.
        const etcGap = Number(a.region === "기타") - Number(b.region === "기타");
        if (etcGap !== 0) return etcGap;
        return b.amountValue - a.amountValue;
      });
  }, [averageEurKrwRate, countryRows, totalAmount]);
  const allSelectedSkuRows = useMemo(() => {
    const rows = skuSourceRows.filter((row) => !effectiveCountry || countryOf(row) === effectiveCountry);
    const bySku = new Map<string, { name: string; brand: string; amount: number }>();
    rows.forEach((row) => {
      const sku = skuCodeOf(row);
      if (!sku || sku === "-") return;
      const current = bySku.get(sku) ?? { name: productNameOf(row), brand: brandOf(row), amount: 0 };
      current.amount += amountOf(row);
      bySku.set(sku, current);
    });
    return Array.from(bySku.entries())
      .map(([sku, row]) => ({ sku, ...row }))
      .sort((a, b) => b.amount - a.amount);
  }, [effectiveCountry, skuSourceRows]);
  const selectedSkuTotalAmount = allSelectedSkuRows.reduce((sum, row) => sum + row.amount, 0);
  const selectedSkuRows = allSelectedSkuRows.slice(0, 5);
  const allSelectedBrandRows = useMemo(() => {
    const rows = skuSourceRows.filter((row) => !effectiveCountry || countryOf(row) === effectiveCountry);
    const byBrand = new Map<string, number>();
    rows.forEach((row) => {
      const brand = brandOf(row);
      byBrand.set(brand, (byBrand.get(brand) ?? 0) + amountOf(row));
    });
    const maxAmount = Math.max(...byBrand.values(), 1);
    const total = Array.from(byBrand.values()).reduce((sum, amount) => sum + amount, 0);
    return Array.from(byBrand.entries())
      .map(([brand, amount]) => ({
        brand,
        amount,
        sharePct: total > 0 ? (amount / total) * 100 : 0,
        width: `${Math.max(4, (amount / maxAmount) * 100)}%`
      }))
      .sort((a, b) => b.amount - a.amount);
  }, [effectiveCountry, skuSourceRows]);
  const selectedBrandRows = allSelectedBrandRows.slice(0, 5);
  const selectedMonthlySales = useMemo(() => {
    // 분석 기간에 집계 자체가 없는 달(진행 중인 달 등)은 매출 0인 달과 구분한다
    const observedMonths = new Set<number>();
    seasonRows.forEach((row) => {
      const monthKey = monthKeyOf(row);
      if (!monthKey) return;
      const month = Number(monthKey.includes("-") ? monthKey.split("-")[1] : monthKey);
      if (month >= 1 && month <= 12) observedMonths.add(month);
    });
    const months = countrySeasonMonths.map((month) => ({
      month,
      amount: 0,
      hasData: observedMonths.has(month)
    }));
    if (!effectiveCountry) return months;

    const byMonth = new Map<number, number>();
    seasonRows
      .filter((row) => countryOf(row) === effectiveCountry)
      .forEach((row) => {
        const monthKey = monthKeyOf(row);
        if (!monthKey) return;
        const month = Number(monthKey.includes("-") ? monthKey.split("-")[1] : monthKey);
        if (month < 1 || month > 12) return;
        byMonth.set(month, (byMonth.get(month) ?? 0) + amountOf(row));
      });

    return months.map((item) => ({
      ...item,
      amount: byMonth.get(item.month) ?? 0
    }));
  }, [countrySeasonMonths, effectiveCountry, seasonRows]);
  const selectedPeakMonth = useMemo(() => {
    const byMonth = new Map<string, number>();
    selectedMonthlySales.forEach((row) => {
      if (row.amount <= 0) return;
      byMonth.set(String(row.month).padStart(2, "0"), row.amount);
    });

    return Array.from(byMonth.entries())
      .map(([monthKey, amount]) => ({ monthKey, amount }))
      .sort((a, b) => b.amount - a.amount)[0] ?? null;
  }, [selectedMonthlySales]);
  const selectedPeakMonthLabel = selectedPeakMonth
    ? selectedPeakMonth.monthKey.includes("-")
      ? selectedPeakMonth.monthKey.replace("-", ".")
      : `${Number(selectedPeakMonth.monthKey)}월`
    : "";
  const selectedSeasonTotalAmount = selectedMonthlySales.reduce((sum, row) => sum + row.amount, 0);
  const selectedMonthlyShares = selectedMonthlySales.map((row) => ({
    ...row,
    share: selectedSeasonTotalAmount > 0 ? (row.amount / selectedSeasonTotalAmount) * 100 : 0
  }));
  const selectedPeakShare = selectedPeakMonth
    ? selectedMonthlyShares.find((row) => String(row.month).padStart(2, "0") === selectedPeakMonth.monthKey)?.share ?? 0
    : 0;
  const selectedSeasonChartMaxShare = Math.max(5, Math.ceil(Math.max(...selectedMonthlyShares.map((row) => row.share), 0) / 5) * 5);
  const selectedSeasonChartPoints = selectedMonthlyShares.map((row, index) => ({
    ...row,
    x: selectedMonthlyShares.length > 1 ? 42 + (index * 548) / (selectedMonthlyShares.length - 1) : 316,
    y: 88 - (row.share / selectedSeasonChartMaxShare) * 62
  }));
  // 데이터 없는 달에서 선을 끊기 위해 연속된 유효 구간으로 분할
  const selectedSeasonChartSegments = (() => {
    const segments: Array<typeof selectedSeasonChartPoints> = [];
    let current: typeof selectedSeasonChartPoints = [];
    selectedSeasonChartPoints.forEach((point) => {
      if (point.hasData) {
        current.push(point);
      } else if (current.length > 0) {
        segments.push(current);
        current = [];
      }
    });
    if (current.length > 0) segments.push(current);
    return segments;
  })();
  const regionSummaryBlock: ReportBlock = {
    id: "country:region-sales-share",
    title: "\uAD8C\uC5ED\uBCC4 \uB9E4\uCD9C \uBE44\uC911",
    subtitle: `\uC804 \uC138\uACC4 ${formatNumber(activeCountryCount)}\uAC1C\uAD6D \u00B7 \uCD1D \uB9E4\uCD9C ${[wonEok(totalAmount), totalAmountKrw].filter(Boolean).join(" · ")}`,
    meta: "\uAD6D\uAC00 \u00B7 \uAD8C\uC5ED \uAE30\uC900 \uD310\uB9E4 \uC778\uC0AC\uC774\uD2B8",
    type: "region_share",
    params: {
      scope: "all",
      countryCount: activeCountryCount,
      totalAmount,
      eur_krw_rate: averageEurKrwRate,
      ...reportAnalysisPeriodParams(analysisOptions)
    },
    kind: "share",
    section: "region",
    size: "full",
    snapshot: {
      columns: ["권역", "매출액", "매출표시", "원화표시", "점유율", "국가수"],
      rows: regionRows.map((row) => ({
        권역: row.region,
        매출액: row.amountValue,
        매출표시: row.amountDisplay,
        원화표시: row.amountKrw,
        점유율: row.percent,
        국가수: row.countries
      }))
    }
  };
  const countryRankBlock: ReportBlock = {
    id: `country:rank:${selectedRegion || "all"}`,
    title: selectedRegion ? `${selectedRegion} 국가별 판매 순위` : "국가별 판매 순위",
    subtitle: `${formatNumber(visibleCountryRows.length)}개국 · 매출 기준`,
    meta: "국가 · 권역 기준 판매 인사이트",
    type: "country_rank",
    kind: "ranking",
    section: "region",
    size: "full",
    params: {
      region: selectedRegion || "전체",
      countryCount: visibleCountryRows.length,
      totalAmount: visibleTotalAmount,
      eur_krw_rate: averageEurKrwRate,
      yoy_mode: "completed_ytd",
      yoy_period: countryYtdPeriodLabel,
      mom_target_month: countryMomTargetMonth,
      mom_comparison_month: countryMomComparisonMonth,
      ...reportAnalysisPeriodParams(analysisOptions)
    },
    snapshot: {
      columns: ["순위", "국가", "권역", "매출액", "매출표시", "원화표시", "점유율", "YoY", "MoM"],
      rows: visibleCountryRows.map((row, index) => ({
        순위: index + 1,
        국가: row.country,
        권역: row.region,
        매출액: row.amount,
        매출표시: wonEok(row.amount),
        원화표시: krwEokFromEur(row.amount, averageEurKrwRate),
        점유율: `${formatNumber(visibleTotalAmount > 0 ? (row.amount / visibleTotalAmount) * 100 : row.amountShare, 1)}%`,
        YoY: countryYoyByName.get(row.country) ?? "-",
        MoM: countryMomByName.get(row.country) ?? ""
      }))
    }
  };
  const allSelectedTopCategories = useMemo(() => {
    const salesByCategory = new Map<string, number>();
    seasonRows
      .filter((row) => !effectiveCountry || countryOf(row) === effectiveCountry)
      .forEach((row) => {
        const category1 = category1Of(row);
        const category2 = category2Of(row);
        if (!category1 || category1.includes("미분류")) return;
        const category = category2 && !category2.includes("미분류")
          ? `${category1} > ${category2}`
          : category1;
        salesByCategory.set(category, (salesByCategory.get(category) ?? 0) + amountOf(row));
      });

    const total = Array.from(salesByCategory.values()).reduce((sum, amount) => sum + amount, 0);
    return Array.from(salesByCategory.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([category, amount]) => ({
        category,
        amount,
        sharePct: total > 0 ? (amount / total) * 100 : 0
      }));
  }, [effectiveCountry, seasonRows]);
  const selectedTopCategories = allSelectedTopCategories.slice(0, 5);

  const selectedCountryDetailBlock: ReportBlock = {
    id: `country:detail:${effectiveCountry}`,
    title: `${effectiveCountry} 국가 판매 상세`,
    subtitle: `${selectedCountryRow?.region ?? selectedRegion} · 총 매출 ${wonEok(selectedCountryRow?.amount ?? 0)} · 점유율 ${formatNumber(selectedCountryShare, 1)}%`,
    meta: "선택 국가 판매 인사이트",
    type: "country_detail",
    kind: "kpi",
    section: "region",
    size: "full",
    params: {
      country: effectiveCountry,
      region: selectedCountryRow?.region ?? selectedRegion,
      amount: selectedCountryRow?.amount ?? 0,
      share: selectedCountryShare,
      peakMonth: selectedPeakMonthLabel,
      eur_krw_rate: averageEurKrwRate,
      ...reportAnalysisPeriodParams(analysisOptions)
    },
    snapshot: {
      columns: ["구분", "순위", "항목", "매출액", "매출표시", "원화표시", "비고"],
      rows: [
        {
          구분: "국가 요약",
          순위: "",
          항목: effectiveCountry,
          매출액: selectedCountryRow?.amount ?? 0,
          매출표시: wonEok(selectedCountryRow?.amount ?? 0),
          원화표시: krwEokFromEur(selectedCountryRow?.amount ?? 0, averageEurKrwRate),
          비고: `점유율 ${formatNumber(selectedCountryShare, 1)}%`
        },
        {
          구분: "월 최고 매출",
          순위: "",
          항목: selectedPeakMonthLabel || "데이터 없음",
          매출액: selectedPeakMonth?.amount ?? 0,
          매출표시: selectedPeakMonth ? wonEok(selectedPeakMonth.amount) : "-",
          원화표시: selectedPeakMonth ? krwEokFromEur(selectedPeakMonth.amount, averageEurKrwRate) : "",
          비고: selectedPeakMonth ? `${selectedPeakMonthLabel} 최고` : "월별 데이터 없음"
        },
        ...selectedBrandRows.map((row, index) => ({
          구분: "상위 브랜드",
          순위: index + 1,
          항목: displayBrandName(row.brand),
          매출액: row.amount,
          매출표시: wonEok(row.amount),
          원화표시: krwEokFromEur(row.amount, averageEurKrwRate),
          비고: ""
        })),
        ...selectedTopCategories.map((row, index) => ({
          구분: "Top 5 카테고리",
          순위: index + 1,
          항목: row.category,
          매출액: row.amount,
          매출표시: wonEok(row.amount),
          원화표시: krwEokFromEur(row.amount, averageEurKrwRate),
          비고: ""
        }))
      ]
    }
  };

  const selectedCountrySkuSeasonBlock: ReportBlock = {
    id: `country:sku-season:${effectiveCountry}`,
    title: `상위 SKU · ${effectiveCountry}`,
    subtitle: `${selectedPeakMonthLabel || "-"} 최고 비중 · ${formatNumber(selectedPeakShare, 1)}%`,
    meta: "선택 국가 상위 SKU 및 월별 매출 비중",
    type: "country_sku_season",
    kind: "trend",
    section: "region",
    size: "full",
    params: {
      country: effectiveCountry,
      peak_month: selectedPeakMonthLabel,
      peak_share: selectedPeakShare,
      eur_krw_rate: averageEurKrwRate,
      ...reportAnalysisPeriodParams(analysisOptions)
    },
    snapshot: {
      columns: ["구분", "순위", "항목", "브랜드", "매출액", "매출표시", "원화표시", "월", "매출비중"],
      rows: [
        ...selectedSkuRows.map((row, index) => ({
          구분: "상위 SKU",
          순위: index + 1,
          항목: row.name,
          브랜드: displayBrandName(row.brand),
          매출액: row.amount,
          매출표시: wonEok(row.amount),
          원화표시: krwEokFromEur(row.amount, averageEurKrwRate),
          월: "",
          매출비중: ""
        })),
        ...selectedMonthlyShares.map((row) => ({
          구분: "국가 시즌성",
          순위: "",
          항목: `${row.month}월`,
          브랜드: "",
          매출액: row.amount,
          매출표시: wonEok(row.amount),
          원화표시: krwEokFromEur(row.amount, averageEurKrwRate),
          월: row.month,
          매출비중: `${formatNumber(row.share, 1)}%`
        }))
      ]
    }
  };

  // design-token-audit: report-template-start — standalone print document with its own embedded palette
  const exportCountryReportPdf = () => {
    if (exportingCountryPdf) return;
    setExportingCountryPdf(true);

    const generatedAt = new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    }).format(new Date());
    const fileDate = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date());
    const maxRankWidth = Math.max(...rankRows.map((row) => Number.parseFloat(row[6])), 1);

    const metricCards = [
      ["전체 매출", [wonEok(totalAmount), totalAmountKrw].filter(Boolean).join(" / ")],
      ["매출 발생 국가", `${formatNumber(activeCountryCount)}개국`],
      ["매출 발생 브랜드", brandCountDisplay],
      ["매출 발생 SKU", skuCountDisplay]
    ];
    const reportWindow = window.open("", "_blank", "width=1200,height=900");
    if (!reportWindow) {
      setExportingCountryPdf(false);
      return;
    }

    const html = `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>국가 분석 리포트 ${escapeReportHtml(fileDate)}</title>
  <style>
    @page { size: A4 landscape; margin: 12mm; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #f3f4f6; color: #05060a; font-family: Arial, "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; }
    .page { padding: 24px; }
    .header { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; margin-bottom: 18px; }
    .eyebrow { font-size: 11px; font-weight: 900; color: #e90035; letter-spacing: .02em; }
    h1 { margin: 4px 0 8px; font-size: 24px; line-height: 1.15; }
    .desc, .muted { color: #69707f; font-weight: 700; }
    .desc { font-size: 12px; }
    .date { font-size: 11px; text-align: right; }
    .grid { display: grid; gap: 14px; }
    .metrics { grid-template-columns: repeat(4, 1fr); margin-bottom: 14px; }
    .metric, .section, .detail { background: #fff; border: 1px solid #e2e4e8; border-radius: 14px; box-shadow: 0 6px 16px rgba(15, 23, 42, .06); }
    .metric { padding: 16px 18px; min-height: 82px; }
    .label { color: #69707f; font-size: 11px; font-weight: 800; }
    .value { margin-top: 10px; font-size: 25px; font-weight: 950; }
    .accent { color: #e90035; }
    .section { padding: 18px; margin-bottom: 14px; }
    .section-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
    h2 { margin: 0; font-size: 15px; }
    .regions { grid-template-columns: repeat(3, 1fr); }
    .region { border: 1px solid #e2e4e8; border-radius: 12px; padding: 13px; }
    .region.selected { border-color: #e90035; }
    .row-between { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
    .bar-bg { height: 6px; border-radius: 999px; background: #f0f1f4; overflow: hidden; margin: 10px 0; }
    .bar { height: 100%; border-radius: 999px; background: #e90035; }
    .columns { grid-template-columns: 1fr 1fr; align-items: start; }
    table { width: 100%; border-collapse: collapse; }
    td, th { border-bottom: 1px solid #edf0f3; padding: 10px 0; font-size: 12px; vertical-align: middle; }
    th { color: #69707f; text-align: left; font-size: 11px; }
    .rank { width: 28px; color: #9aa1ad; font-weight: 900; }
    .name { font-weight: 900; }
    .tag { display: inline-block; border: 1px solid #e2e4e8; border-radius: 7px; padding: 2px 8px; color: #69707f; font-size: 10px; font-weight: 800; margin-left: 8px; }
    .amount { text-align: right; font-weight: 950; }
    .detail { padding: 18px; }
    .country-title { display: flex; justify-content: space-between; border-bottom: 1px solid #edf0f3; padding-bottom: 14px; margin-bottom: 16px; }
    .country-title h2 { font-size: 24px; margin-top: 4px; }
    .big { font-size: 24px; font-weight: 950; text-align: right; }
    .brand-row { margin-bottom: 12px; }
    .brand-row .row-between { font-size: 12px; font-weight: 900; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; }
    .chip { border: 1px solid #e2e4e8; border-radius: 999px; padding: 5px 12px; background: #f7f8fa; font-size: 11px; font-weight: 900; }
    .growth-columns { grid-template-columns: 1fr 1fr; }
    .growth-panel { border: 1px solid #edf0f3; border-radius: 12px; padding: 14px; }
    .growth-panel h3 { margin: 0 0 8px; font-size: 12px; }
    .growth-row { display: grid; grid-template-columns: 24px 1fr auto; gap: 8px; align-items: center; border-bottom: 1px solid #edf0f3; padding: 9px 0; font-size: 11px; }
    .growth-row:last-child { border-bottom: 0; }
    .growth-value { font-size: 12px; font-weight: 950; }
    .positive { color: #0a9f4b; }
    .negative { color: #e90035; }
    .season-line { display: block; width: 100%; height: 112px; margin-top: 8px; overflow: visible; }
    .print-note { margin-top: 16px; color: #69707f; font-size: 10px; font-weight: 700; text-align: right; }
    .rate-note { margin-top: 8px; color: #69707f; font-size: 10px; font-weight: 800; }
    @media print { body { background: #f3f4f6; } .page { padding: 0; } }
  </style>
</head>
<body>
  <main class="page">
    <header class="header">
      <div>
        <div class="eyebrow">분석 · INSIGHT</div>
        <h1>국가 · 권역 기준 판매 인사이트</h1>
        <div class="desc">"어느 국가에서 가장 잘 팔리는가?" — 권역과 국가를 선택하면 강한 브랜드 · SKU · 시즌성이 함께 갱신됩니다.</div>
      </div>
      <div class="date muted">생성일<br />${escapeReportHtml(generatedAt)}</div>
    </header>

    <section class="grid metrics">
      ${metricCards
        .map(
          ([label, value], index) => `<div class="metric"><div class="label">${escapeReportHtml(label)}</div><div class="value ${index === 0 ? "accent" : ""}">${escapeReportHtml(value)}</div></div>`
        )
        .join("")}
    </section>
    ${exchangeBasis ? `<div class="rate-note">${escapeReportHtml(exchangeBasis)}</div>` : ""}

    <section class="section">
      <div class="section-head"><h2>권역별 매출 비중</h2><span class="muted">${escapeReportHtml(`전 세계 ${formatNumber(activeCountryCount)}개국 · 최신 분석 기준`)}</span></div>
      <div class="grid regions">
        ${regionRows
          .map(
            (row) => `<div class="region ${row.region === selectedRegion ? "selected" : ""}">
              <div class="row-between"><strong>${escapeReportHtml(row.region)}</strong><strong class="accent">${escapeReportHtml(row.percent)}</strong></div>
              <div class="bar-bg"><div class="bar" style="width:${escapeReportHtml(row.percent)}"></div></div>
              <div class="row-between muted"><span>${escapeReportHtml(row.amount)}</span><span>${escapeReportHtml(row.countries)}</span></div>
            </div>`
          )
          .join("")}
      </div>
    </section>

    <section class="grid columns">
      <div class="section">
        <div class="section-head"><h2>국가별 판매 순위</h2><span class="muted">매출 기준</span></div>
        <table>
          <tbody>
            ${rankRows
              .map(
                  ([rank, country, region, share, , , width]) => `<tr>
                    <td class="rank">${rank}</td>
                    <td>
                      <div class="name">${escapeReportHtml(country)} <span class="tag">${escapeReportHtml(region)}</span></div>
                      <div class="bar-bg"><div class="bar" style="width:${Math.max(4, (Number.parseFloat(width) / maxRankWidth) * 100)}%"></div></div>
                    </td>
                    <td class="amount">${escapeReportHtml(share)}</td>
                  </tr>`
                )
              .join("")}
          </tbody>
        </table>
      </div>

      <div class="detail">
        <div class="country-title">
          <div><div class="label">선택 국가</div><h2>${escapeReportHtml(effectiveCountry || "-")}</h2></div>
          <div><div class="big">${escapeReportHtml(wonEok(selectedCountryRow?.amount ?? 0))}</div><div class="accent label">점유율 ${escapeReportHtml(formatNumber(selectedCountryShare, 1))}%</div></div>
        </div>
        <div class="row-between" style="border-bottom:1px solid #edf0f3; padding-bottom:14px; margin-bottom:16px;">
          <div><div class="label">월 최고 매출</div><div class="value" style="font-size:18px">${escapeReportHtml(selectedPeakMonth ? wonEok(selectedPeakMonth.amount) : "-")}</div><div class="muted">${escapeReportHtml(selectedPeakMonth ? krwEokFromEur(selectedPeakMonth.amount, averageEurKrwRate) : "")}</div></div>
          <strong class="accent">${escapeReportHtml(selectedPeakMonth ? `${selectedPeakMonthLabel} 최고` : "월별 데이터 없음")}</strong>
        </div>
        <div class="section-head"><h2>상위 브랜드</h2><span class="muted">미리보기</span></div>
        ${selectedBrandRows
          .map(
            (row) => `<div class="brand-row"><div class="row-between"><span>${escapeReportHtml(displayBrandName(row.brand))}</span><span>${escapeReportHtml(wonEok(row.amount))}</span></div><div class="muted" style="text-align:right">${escapeReportHtml(krwEokFromEur(row.amount, averageEurKrwRate))}</div><div class="bar-bg"><div class="bar" style="width:${escapeReportHtml(row.width)}"></div></div></div>`
          )
          .join("")}
        <div style="margin-top:18px;"><h2 style="margin-bottom:10px;">Top 5 카테고리</h2><div class="chips">${(selectedTopCategories.length > 0 ? selectedTopCategories.map((row) => row.category) : ["데이터 없음"]).map((category) => `<span class="chip">${escapeReportHtml(category)}</span>`).join("")}</div></div>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>국가별 성장 변화</h2>
        <span class="muted">${escapeReportHtml(`${countryGrowthBasisLabel} · ${countryGrowthPeriodLabel}`)}</span>
      </div>
      <div class="grid growth-columns">
        <div class="growth-panel">
          <h3 class="positive">성장 상위 · 금액 증가순</h3>
          ${risingCountryRows.length > 0
            ? risingCountryRows.map((row, index) => `<div class="growth-row"><span class="rank">${index + 1}</span><span><strong>${escapeReportHtml(row.country)}</strong><br /><span class="muted">${escapeReportHtml(row.region)}</span></span><span class="growth-value positive">${escapeReportHtml(signedEur(row.deltaAmount))}<br /><span class="muted">${escapeReportHtml([signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate), row.growth, `${wonEok(row.previousAmount)} → ${wonEok(row.currentAmount)}`, averageEurKrwRate ? `${krwEokValueFromEur(row.previousAmount, averageEurKrwRate)} → ${krwEokValueFromEur(row.currentAmount, averageEurKrwRate)}` : ""].filter(Boolean).join(" · "))}</span></span></div>`).join("")
            : `<div class="muted">성장한 국가가 없습니다.</div>`}
        </div>
        <div class="growth-panel">
          <h3 class="negative">감소 상위 · 금액 감소순</h3>
          ${decliningCountryRows.length > 0
            ? decliningCountryRows.map((row, index) => `<div class="growth-row"><span class="rank">${index + 1}</span><span><strong>${escapeReportHtml(row.country)}</strong><br /><span class="muted">${escapeReportHtml(row.region)}</span></span><span class="growth-value negative">${escapeReportHtml(signedEur(row.deltaAmount))}<br /><span class="muted">${escapeReportHtml([signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate), row.vanished ? `판매 소멸 · ${row.growth}` : row.growth, `${wonEok(row.previousAmount)} → ${wonEok(row.currentAmount)}`, averageEurKrwRate ? `${krwEokValueFromEur(row.previousAmount, averageEurKrwRate)} → ${krwEokValueFromEur(row.currentAmount, averageEurKrwRate)}` : ""].filter(Boolean).join(" · "))}</span></span></div>`).join("")
            : `<div class="muted">감소한 국가가 없습니다.</div>`}
        </div>
      </div>
    </section>

    <section class="section" style="margin-top:14px;">
      <div class="section-head"><h2>상위 SKU · ${escapeReportHtml(effectiveCountry || "-")}</h2><span class="muted">판매금액 기준</span></div>
      <table>
        <tbody>
          ${selectedSkuRows
            .map(
              (row, index) => `<tr><td class="rank">${index + 1}</td><td><div class="name">${escapeReportHtml(row.name)}</div><div class="muted">${escapeReportHtml(displayBrandName(row.brand))}</div></td><td class="amount">${escapeReportHtml(wonEok(row.amount))}<br /><span class="muted">${escapeReportHtml(krwEokFromEur(row.amount, averageEurKrwRate))}</span></td></tr>`
            )
            .join("")}
        </tbody>
      </table>
      <div style="margin-top:18px;"><div class="section-head"><h2>국가 시즌성 · 월별 매출 비중</h2><span class="muted">${escapeReportHtml(selectedPeakMonth ? `${selectedPeakMonthLabel} 최고 비중 · ${formatNumber(selectedPeakShare, 1)}%` : "월별 데이터 없음")}</span></div>
        <svg class="season-line" viewBox="0 0 620 112" role="img" aria-label="${escapeReportHtml(effectiveCountry)} 월별 매출 비중 꺾은선 그래프">
          ${[26, 57, 88].map((y) => `<line x1="42" x2="590" y1="${y}" y2="${y}" stroke="#edf0f3" stroke-width="1" />`).join("")}
          <text x="4" y="29" fill="#9aa1ad" font-size="9" font-weight="700">${formatNumber(selectedSeasonChartMaxShare, 0)}%</text>
          <text x="12" y="91" fill="#9aa1ad" font-size="9" font-weight="700">0%</text>
          ${selectedSeasonChartSegments
            .map((segment) =>
              segment.length > 1
                ? `<polyline points="${segment.map((row) => `${row.x},${row.y}`).join(" ")}" fill="none" stroke="#e90035" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" />`
                : ""
            )
            .join("")}
          ${selectedSeasonChartPoints.map((row) => {
            if (!row.hasData) {
              return `<g><circle cx="${row.x}" cy="88" r="3" fill="#f1f2f4" stroke="#d8dbe0" stroke-width="1.5"><title>${row.month}월 · 분석 기간에 데이터 없음</title></circle><text x="${row.x}" y="106" text-anchor="middle" fill="#c6cad1" font-size="9" font-weight="700">${row.month}월</text></g>`;
            }
            const peak = selectedPeakMonth?.monthKey === String(row.month).padStart(2, "0");
            return `<g><circle cx="${row.x}" cy="${row.y}" r="${peak ? 5 : 3.5}" fill="${peak ? "#e90035" : "#fff"}" stroke="#e90035" stroke-width="2"><title>${row.month}월 매출 비중 ${formatNumber(row.share, 1)}%</title></circle><text x="${row.x}" y="${Math.max(11, row.y - 8)}" text-anchor="middle" fill="${peak ? "#e90035" : "#69707f"}" font-size="9" font-weight="800">${formatNumber(row.share, 1)}%</text><text x="${row.x}" y="106" text-anchor="middle" fill="#9aa1ad" font-size="9" font-weight="700">${row.month}월</text></g>`;
          }).join("")}
        </svg>
      </div>
    </section>

    <div class="print-note">Silicon2 SCM · 국가 분석 리포트</div>
  </main>
  <script>
    window.addEventListener("load", () => {
      document.title = "country-analysis-report-${escapeReportHtml(fileDate)}";
      setTimeout(() => {
        window.focus();
        window.print();
      }, 250);
    });
  </script>
</body>
</html>`;

    reportWindow.document.open();
    reportWindow.document.write(injectReportWatermark(html));
    reportWindow.document.close();
    window.setTimeout(() => setExportingCountryPdf(false), 800);
  };
  // design-token-audit: report-template-end

  return {
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
    countryMomTargetMonth,
    setCountryMomTargetMonth,
    countryYoyTargetMonth,
    setCountryYoyTargetMonth,
    exportingCountryPdf,
    setCountryPage,
    savedReportBlockIds,
    countryRows,
    totalAmount,
    activeCountryCount,
    brandCountDisplay,
    skuCountDisplay,
    staleCountCaveat,
    countryMomTargetOptions,
    countryYoyTargetOptions,
    countryYoyComparisonMonth,
    countryMomComparisonMonth,
    countryMetricDeltas,
    averageEurKrwRate,
    exchangeBasis,
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
    newCountryRows,
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
    regionSummaryBlock,
    countryRankBlock,
    selectedTopCategories,
    allSelectedTopCategories,
    selectedCountryDetailBlock,
    selectedCountrySkuSeasonBlock,
    exportCountryReportPdf
  };
}
