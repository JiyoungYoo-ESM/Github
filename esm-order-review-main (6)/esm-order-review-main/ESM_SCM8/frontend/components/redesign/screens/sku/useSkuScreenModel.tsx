"use client";

import { useEffect, useMemo, useState } from "react";

import { displayBrandName } from "@/lib/brand-display";
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
import { formatNumber } from "@/lib/utils";
import type { ReportBlock } from "../../lib/types";
import { krwEokFromEur, wonEok } from "../../lib/currency-format";
import { reportAnalysisPeriodParams, reportBrandRole } from "../../lib/workspace-format";
import { useSkuScreenData } from "./useSkuScreenData";

const ALL_FILTER = "__all__";

export function useSkuScreenModel({
  reportBlocks,
  onToggleReportBlock
}: {
  reportBlocks: ReportBlock[];
  onToggleReportBlock: (block: ReportBlock) => void;
}) {
  const { rows, monthlyRows, analysisOptions, loading, loadFailed } = useSkuScreenData();
  const [selectedSku, setSelectedSku] = useState("");
  const [brandFilter, setBrandFilter] = useState(ALL_FILTER);
  const [activeSkuTab, setActiveSkuTab] = useState<"trend" | "detail">("trend");
  const savedReportBlockIds = useMemo(() => new Set(reportBlocks.map((block) => block.id)), [reportBlocks]);
  const skuSummaries = useMemo(() => {
    const bySku = new Map<
      string,
      {
        sku: string;
        name: string;
        brand: string;
        category: string;
        amount: number;
        qty: number;
        countries: Set<string>;
      }
    >();

    rows.forEach((row) => {
      const sku = skuCodeOf(row);
      if (!sku || sku === "-") return;
      const category = [category1Of(row), category2Of(row)]
        .filter((item) => item && !item.includes("미분류"))
        .join(" > ");
      const current = bySku.get(sku) ?? {
        sku,
        name: productNameOf(row),
        brand: brandOf(row),
        category,
        amount: 0,
        qty: 0,
        countries: new Set<string>()
      };
      current.amount += amountOf(row);
      current.qty += qtyOf(row);
      if (!current.category && category) current.category = category;
      const country = countryOf(row);
      if (country && country !== "미상") current.countries.add(country);
      bySku.set(sku, current);
    });

    const values = Array.from(bySku.values());
    const hasAmount = values.some((row) => row.amount > 0);
    return values.sort((a, b) => (hasAmount ? b.amount - a.amount : b.qty - a.qty));
  }, [rows]);

  const brandOptions = useMemo(
    () => Array.from(new Set(skuSummaries.map((row) => row.brand).filter(Boolean))).sort((a, b) => displayBrandName(a).localeCompare(displayBrandName(b))),
    [skuSummaries]
  );
  const filteredSkuSummaries = useMemo(() => {
    return skuSummaries.filter((sku) => {
      const brandMatches = brandFilter === ALL_FILTER || sku.brand === brandFilter;
      return brandMatches;
    });
  }, [brandFilter, skuSummaries]);
  const skuSearchOptions = useMemo(
    () => filteredSkuSummaries.map((sku) => ({ value: sku.sku, name: sku.name, code: sku.sku })),
    [filteredSkuSummaries]
  );

  const filteredSkuSet = useMemo(() => new Set(filteredSkuSummaries.map((sku) => sku.sku)), [filteredSkuSummaries]);
  const selectedDetail = filteredSkuSummaries.find((row) => row.sku === selectedSku) ?? null;

  useEffect(() => {
    if (selectedSku && !filteredSkuSet.has(selectedSku)) {
      setSelectedSku("");
    }
  }, [filteredSkuSet, selectedSku]);

  const activeRows = useMemo(() => {
    return rows.filter((row) => skuCodeOf(row) === selectedDetail?.sku);
  }, [rows, selectedDetail?.sku]);

  const activeMonthlyRows = useMemo(() => {
    return monthlyRows.filter((row) => skuCodeOf(row) === selectedDetail?.sku);
  }, [monthlyRows, selectedDetail?.sku]);

  const activeSummary = useMemo(() => {
    return selectedDetail ?? {
      sku: "",
      name: "검색 결과 없음",
      brand: "",
      category: "조건에 맞는 SKU가 없습니다",
      amount: 0,
      qty: 0,
      countries: new Set<string>()
    };
  }, [selectedDetail]);

  const monthlySales = useMemo(() => {
    const totals = Array.from({ length: 12 }, (_, index) => ({ month: index + 1, amount: 0, qty: 0 }));
    activeMonthlyRows.forEach((row) => {
      const key = monthKeyOf(row);
      const month = Number(key.slice(-2));
      if (month >= 1 && month <= 12) {
        totals[month - 1].amount += amountOf(row);
        totals[month - 1].qty += qtyOf(row);
      }
    });
    return totals;
  }, [activeMonthlyRows]);
  const observedMonthKeys = useMemo(() => {
    const keys = new Set<string>();
    activeMonthlyRows.forEach((row) => {
      const key = monthKeyOf(row);
      if (key) keys.add(key);
    });
    return keys;
  }, [activeMonthlyRows]);

  // 데이터셋 전체(전 SKU) 기준으로 집계가 존재하는 달 — 이 SKU의 진짜 0%와 "기간에 데이터 없음"을 구분
  const datasetMonthNumbers = useMemo(() => {
    const months = new Set<number>();
    monthlyRows.forEach((row) => {
      const key = monthKeyOf(row);
      if (!key) return;
      const month = Number(key.slice(-2));
      if (month >= 1 && month <= 12) months.add(month);
    });
    return months;
  }, [monthlyRows]);

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
    return Array.from(observedMonthKeys)
      .sort()
      .map((key) => Number(key.slice(-2)))
      .filter((month) => month >= 1 && month <= 12);
  }, [endDateText, observedMonthKeys, startDateText]);
  const analysisMonthCount = rangeMonthNumbers.length || observedMonthKeys.size;
  const isShortAnalysisRange = analysisMonthCount > 0 && analysisMonthCount < 12;
  const chartMonthlySales = isShortAnalysisRange && rangeMonthNumbers.length > 0 ? rangeMonthNumbers.map((month) => monthlySales[month - 1]) : monthlySales;
  const hasAmountMetric = monthlySales.some((row) => row.amount > 0) || activeSummary.amount > 0;
  const peakMonth = chartMonthlySales.reduce(
    (best, row) => ((hasAmountMetric ? row.amount : row.qty) > (hasAmountMetric ? best.amount : best.qty) ? row : best),
    chartMonthlySales[0] ?? monthlySales[0]
  );
  const skuTrendTotalValue = chartMonthlySales.reduce((sum, row) => sum + (hasAmountMetric ? row.amount : row.qty), 0);
  const skuTrendShareAxisMax = Math.max(
    10,
    Math.ceil(Math.max(...chartMonthlySales.map((row) => skuTrendTotalValue > 0 ? ((hasAmountMetric ? row.amount : row.qty) / skuTrendTotalValue) * 100 : 0), 0) / 5) * 5
  );
  const skuTrendChartRows = chartMonthlySales.map((row, index) => {
    const value = hasAmountMetric ? row.amount : row.qty;
    const share = skuTrendTotalValue > 0 ? (value / skuTrendTotalValue) * 100 : 0;
    return {
      ...row,
      value,
      share,
      hasData: datasetMonthNumbers.size === 0 ? true : datasetMonthNumbers.has(row.month),
      active: row.month === peakMonth.month,
      x: chartMonthlySales.length > 1 ? 52 + (index * 1128) / (chartMonthlySales.length - 1) : 616,
      y: 122 - (share / skuTrendShareAxisMax) * 84
    };
  });
  // 데이터 없는 달에서 선을 끊기 위한 연속 구간 분할
  const skuTrendSegments = (() => {
    const segments: Array<typeof skuTrendChartRows> = [];
    let current: typeof skuTrendChartRows = [];
    skuTrendChartRows.forEach((point) => {
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
  const peakTrendShare = skuTrendChartRows.find((row) => row.active)?.share ?? 0;
  const averageEurKrwRate = Number(analysisOptions?.average_eur_krw_rate ?? 0) || null;
  const activeSummaryKrwLabel = hasAmountMetric && activeSummary.amount > 0 ? krwEokFromEur(activeSummary.amount, averageEurKrwRate) : "";

  const allCountryShares = useMemo(() => {
    const byCountry = new Map<string, { amount: number; qty: number; value: number }>();
    activeRows.forEach((row) => {
      const country = countryOf(row);
      const amount = amountOf(row);
      const qty = qtyOf(row);
      const value = hasAmountMetric ? amountOf(row) : qtyOf(row);
      if (country && country !== "미상") {
        const current = byCountry.get(country) ?? { amount: 0, qty: 0, value: 0 };
        current.amount += amount;
        current.qty += qty;
        current.value += value;
        byCountry.set(country, current);
      }
    });
    const sortedRows = Array.from(byCountry.entries()).sort((a, b) => b[1].value - a[1].value);
    const total = sortedRows.reduce((sum, [, value]) => sum + value.value, 0);
    const max = Math.max(...sortedRows.map(([, value]) => value.value), 1);
    return sortedRows.map(([name, value]) => ({
      name,
      amount: value.amount,
      qty: value.qty,
      percent: total > 0 ? (value.value / total) * 100 : 0,
      value: `${formatNumber(total > 0 ? (value.value / total) * 100 : 0, 0)}%`,
      width: `${Math.max(4, (value.value / max) * 100)}%`
    }));
  }, [activeRows, hasAmountMetric]);
  const countryShares = allCountryShares.slice(0, 5);

  const selectedCategory = activeSummary.category || "카테고리 미분류";
  const selectedRank = Math.max(filteredSkuSummaries.findIndex((sku) => sku.sku === activeSummary.sku) + 1, 0);
  const recommendedOrderMonth = ((peakMonth.month + 9 - 1) % 12) + 1;
  const currentPeakValue = hasAmountMetric ? monthlySales[peakMonth.month - 1].amount : monthlySales[peakMonth.month - 1].qty;
  const prePeakMonth = recommendedOrderMonth;
  const prePeakIndex = prePeakMonth - 1;
  const prePeakValue = hasAmountMetric ? monthlySales[prePeakIndex].amount : monthlySales[prePeakIndex].qty;
  const trendMetricName = hasAmountMetric ? "매출" : "판매수량";
  const peakMetricValueLabel = currentPeakValue > 0 ? (hasAmountMetric ? wonEok(currentPeakValue) : `${formatNumber(currentPeakValue)}개`) : "-";
  const peakMetricKrwLabel = hasAmountMetric && currentPeakValue > 0 ? krwEokFromEur(currentPeakValue, averageEurKrwRate) : "";
  const peakLabel = isShortAnalysisRange ? "선택 기간 내 최고월" : "피크 월";
  const preparationLabel = isShortAnalysisRange ? "피크 준비월" : "피크 3개월 전 준비월";
  const peakValueMetricLabel = isShortAnalysisRange ? `최고월 ${trendMetricName}` : `피크월 ${trendMetricName}`;
  const preparationValue = isShortAnalysisRange ? "산출 불가" : `${recommendedOrderMonth}월`;
  const peakValueBasisText = `${peakMonth.month}월 · 선택 SKU 월 최대 ${trendMetricName}`;
  const peakSubtitleLabel = isShortAnalysisRange ? "최고월" : "피크";

  const skuReportBlock: ReportBlock = {
    id: `sku:detail:${activeSummary.sku}`,
    title: `${activeSummary.name} SKU 분석`,
    subtitle: `${displayBrandName(activeSummary.brand)} · ${peakSubtitleLabel} ${peakMonth.month}월 · ${hasAmountMetric ? wonEok(activeSummary.amount) : `${formatNumber(activeSummary.qty)}개`}`,
    meta: "SKU 월별 추이 · 국가별 판매 분포",
    type: "sku_detail",
    kind: "trend",
    section: "sku",
    size: "full",
    params: {
      sku: activeSummary.sku,
      brand: activeSummary.brand,
      brand_role: reportBrandRole(activeSummary.brand),
      category: selectedCategory,
      rank: selectedRank,
      peakMonth: peakMonth.month,
      eur_krw_rate: averageEurKrwRate,
      ...reportAnalysisPeriodParams(analysisOptions)
    },
    snapshot: {
      columns: ["구분", "항목", "매출액", "매출표시", "원화표시", "판매수량", "점유율", "비고"],
      rows: [
        ...skuTrendChartRows.map((row) => ({
          구분: "월별 추이",
          항목: `${row.month}월`,
          매출액: row.amount,
          매출표시: wonEok(row.amount),
          원화표시: krwEokFromEur(row.amount, averageEurKrwRate),
          판매수량: row.qty,
          점유율: `${formatNumber(row.share, 1)}%`,
          비고: row.month === peakMonth.month ? peakLabel : ""
        })),
        ...countryShares.map((row) => ({
          구분: "국가 분포",
          항목: row.name,
          매출액: row.amount,
          매출표시: wonEok(row.amount),
          원화표시: krwEokFromEur(row.amount, averageEurKrwRate),
          판매수량: row.qty,
          점유율: `${formatNumber(row.percent, 1)}%`,
          비고: ""
        }))
      ]
    }
  };
  const skuReportBlockAdded = savedReportBlockIds.has(skuReportBlock.id);

  const skuOrderReferenceBlock: ReportBlock = {
    id: `sku:order-reference:${activeSummary.sku}`,
    title: `${activeSummary.name} 발주 참고 정보`,
    subtitle: `${displayBrandName(activeSummary.brand)} · ${peakSubtitleLabel} ${peakMonth.month}월 · ${activeSummary.sku}`,
    meta: "SKU 발주 참고 정보",
    type: "sku_detail",
    kind: "kpi",
    section: "sku",
    size: "half",
    params: {
      sku: activeSummary.sku,
      brand: activeSummary.brand,
      brand_role: reportBrandRole(activeSummary.brand),
      category: selectedCategory,
      rank: selectedRank,
      peakMonth: peakMonth.month,
      preparationMonth: isShortAnalysisRange ? null : recommendedOrderMonth,
      eur_krw_rate: averageEurKrwRate,
      ...reportAnalysisPeriodParams(analysisOptions)
    },
    snapshot: {
      columns: ["항목", "값", "보조값", "비고"],
      rows: [
        {
          항목: hasAmountMetric ? "매출 순위" : "판매수량 순위",
          값: selectedRank > 0 ? `${formatNumber(selectedRank)}위 / ${formatNumber(filteredSkuSummaries.length)} SKU` : "-",
          보조값: "",
          비고: ""
        },
        {
          항목: preparationLabel,
          값: preparationValue,
          보조값: "",
          비고: isShortAnalysisRange ? "12개월 미만 분석에서는 연중 피크월 판단 제외" : `${peakMonth.month}월 피크 기준`
        },
        { 항목: "판매수량", 값: `${formatNumber(activeSummary.qty)}개`, 보조값: "", 비고: "" },
        { 항목: "전체 매출", 값: hasAmountMetric ? wonEok(activeSummary.amount) : "-", 보조값: activeSummaryKrwLabel, 비고: "" },
        { 항목: "판매 국가", 값: `${formatNumber(activeSummary.countries.size)}개국`, 보조값: "", 비고: "" },
        { 항목: peakValueMetricLabel, 값: peakMetricValueLabel, 보조값: peakMetricKrwLabel, 비고: peakValueBasisText }
      ]
    }
  };
  const skuOrderReferenceBlockAdded = savedReportBlockIds.has(skuOrderReferenceBlock.id);

  const skuCountryDistributionBlock: ReportBlock = {
    id: `sku:country-distribution:${activeSummary.sku}`,
    title: `${activeSummary.name} 국가별 판매 분포`,
    subtitle: `${displayBrandName(activeSummary.brand)} · ${formatNumber(activeSummary.countries.size)}개국 · ${activeSummary.sku}`,
    meta: "SKU 국가별 판매 분포",
    type: "sku_detail",
    kind: "share",
    section: "sku",
    size: "half",
    params: {
      sku: activeSummary.sku,
      brand: activeSummary.brand,
      brand_role: reportBrandRole(activeSummary.brand),
      category: selectedCategory,
      eur_krw_rate: averageEurKrwRate,
      ...reportAnalysisPeriodParams(analysisOptions)
    },
    snapshot: {
      columns: ["국가", "매출액", "매출표시", "원화표시", "판매수량", "점유율"],
      rows: countryShares.map((row) => ({
        국가: row.name,
        매출액: row.amount,
        매출표시: wonEok(row.amount),
        원화표시: krwEokFromEur(row.amount, averageEurKrwRate),
        판매수량: row.qty,
        점유율: `${formatNumber(row.percent, 1)}%`
      }))
    }
  };
  const skuCountryDistributionBlockAdded = savedReportBlockIds.has(skuCountryDistributionBlock.id);

  return {
    ALL_FILTER,
    loading,
    loadFailed,
    skuSummaries,
    brandOptions,
    brandFilter,
    setBrandFilter,
    filteredSkuSummaries,
    skuSearchOptions,
    selectedSku,
    setSelectedSku,
    selectedDetail,
    activeSummary,
    activeSkuTab,
    setActiveSkuTab,
    selectedCategory,
    selectedRank,
    peakMonth,
    peakLabel,
    peakSubtitleLabel,
    peakTrendShare,
    peakMetricValueLabel,
    peakMetricKrwLabel,
    peakValueMetricLabel,
    peakValueBasisText,
    preparationLabel,
    preparationValue,
    recommendedOrderMonth,
    prePeakMonth,
    prePeakValue,
    trendMetricName,
    hasAmountMetric,
    isShortAnalysisRange,
    analysisMonthCount,
    skuTrendShareAxisMax,
    skuTrendChartRows,
    skuTrendSegments,
    countryShares,
    allCountryShares,
    averageEurKrwRate,
    activeSummaryKrwLabel,
    analysisOptions,
    skuReportBlock,
    skuReportBlockAdded,
    skuOrderReferenceBlock,
    skuOrderReferenceBlockAdded,
    skuCountryDistributionBlock,
    skuCountryDistributionBlockAdded
  };
}
