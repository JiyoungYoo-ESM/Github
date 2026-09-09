"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchBrandReportData, getCurrentStockGapSnapshot, useApiQuery } from "@/lib/api";
import { brandIdentityKey, displayBrandName } from "@/lib/brand-display";
import { completeSeasonMonthKeys } from "@/lib/season-calendar";
import { computeStockGapItem } from "@/lib/stock-gap";
import { formatNumber } from "@/lib/utils";
import { exchangeRateBasisLabel, krwEokFromEur, wonEok } from "../../lib/currency-format";
import { analysisPeriodCompactLabel, analysisPeriodSentenceLabel } from "../../lib/workspace-format";
import { completedYtdComparableYearWindow, compactYoyPeriodLabel } from "../../lib/yoy-comparison";
import { lowBaseAmount } from "@/lib/low-base";
import { stockGapShortageQty, type StockGapComputed } from "../gap/GapScreenExact";
import { useReportPdfExport } from "./useReportPdfExport";
import type { BrandSummary, ReportBasisRow, ReportMetricRow, ReportSummaryRow } from "./reportBuilderTypes";
import { isAmountField, redactAmountText } from "@/lib/amount-permissions";
import { useUserPermissions } from "@/lib/use-user-permissions";

const EMPTY_STOCK: StockGapComputed[] = [];

type YoYComparison = {
  latestYear: number;
  previousYear: number;
  months: number[];
  current: number;
  previous: number;
  growth: number | "low-base" | null;
};

function buildYoYComparison(
  monthlyRows: Array<{ month: string; amount: number }>,
  completeMonths: ReadonlySet<string>,
): YoYComparison | null {
  const window = completedYtdComparableYearWindow(
    monthlyRows,
    completeMonths.size > 0 ? completeMonths : undefined
  );
  if (!window?.months?.size) return null;
  const { latestYear, previousYear } = window;
  const months = [...window.months].sort((a, b) => a - b);

  const amountByMonth = new Map(monthlyRows.map((row) => [row.month, Number(row.amount) || 0]));
  const totalFor = (year: number) => months.reduce(
    (sum, month) => sum + (amountByMonth.get(`${year}-${String(month).padStart(2, "0")}`) ?? 0),
    0,
  );
  const current = totalFor(latestYear);
  const previous = totalFor(previousYear);
  const growth = previous <= 0
    ? null
    : previous < lowBaseAmount()
      ? "low-base" as const
      : ((current - previous) / previous) * 100;
  return { latestYear, previousYear, months, current, previous, growth };
}

function yoyWindowLabel(yoy: YoYComparison) {
  const first = yoy.months[0];
  const last = yoy.months[yoy.months.length - 1];
  const monthLabel = first === last ? `${first}월` : `${first}~${last}월`;
  return `${yoy.previousYear}년 ${monthLabel} vs ${yoy.latestYear}년 ${monthLabel}`;
}

function reportAmountText(amount: number, eurKrwRate: number | null) {
  const krwText = krwEokFromEur(amount, eurKrwRate);
  return `${wonEok(amount)}${krwText ? ` (${krwText})` : ""}`;
}

export function useReportBuilderModel() {
  const { canViewAmountData } = useUserPermissions();
  const [selectedBrandName, setSelectedBrandName] = useState("");
  const { data: result, hasError: loadFailed, loading } = useApiQuery({
    query: useCallback(async () => {
      const [report, stockSnapshot] = await Promise.all([
        fetchBrandReportData(),
        getCurrentStockGapSnapshot()
      ]);
      return { report, stockSnapshot, stockGapRows: stockSnapshot.items.map((item) => computeStockGapItem(item)) };
    }, []),
    initialData: null
  });

  const report = result?.report ?? null;
  const aggregates = useMemo(() => report?.brandReports ?? [], [report?.brandReports]);
  const stockGapRows = result?.stockGapRows ?? EMPTY_STOCK;
  const stockSnapshot = result?.stockSnapshot;
  const analysisOptions = report?.analysisOptions ?? null;
  const dataQuality = report?.dataQuality;
  const completeMonths = useMemo(() => completeSeasonMonthKeys(report?.monthCoverage), [report?.monthCoverage]);
  const reportDataIssue = report && aggregates.length === 0 ? "브랜드 리포트에 사용할 분석 데이터가 없습니다." : null;

  const brandSummaries = useMemo<BrandSummary[]>(() => aggregates.map((row) => ({
    brand: row.brand, amount: Number(row.amount) || 0, qty: Number(row.qty) || 0,
    skuCount: Number(row.skuCount) || 0, countryCount: Number(row.countryCount) || 0, categoryCount: Number(row.categoryCount) || 0
  })), [aggregates]);

  useEffect(() => {
    if (!brandSummaries.length) { if (selectedBrandName) setSelectedBrandName(""); return; }
    if (!brandSummaries.some((item) => item.brand === selectedBrandName)) setSelectedBrandName(brandSummaries[0].brand);
  }, [brandSummaries, selectedBrandName]);

  const selectedBrand = brandSummaries.find((item) => item.brand === selectedBrandName) ?? brandSummaries[0];
  const aggregate = aggregates.find((item) => item.brand === selectedBrand?.brand) ?? aggregates[0];
  const totalBrandAmount = useMemo(() => brandSummaries.reduce((sum, item) => sum + item.amount, 0), [brandSummaries]);
  const selectedShare = selectedBrand && totalBrandAmount > 0 ? selectedBrand.amount / totalBrandAmount * 100 : 0;
  const rate = Number(analysisOptions?.average_eur_krw_rate) > 0 ? Number(analysisOptions?.average_eur_krw_rate) : null;
  const reportPeriod = analysisPeriodSentenceLabel(analysisOptions);
  const reportPeriodShort = analysisPeriodCompactLabel(analysisOptions);

  const countryRows = useMemo(() => aggregate?.countries ?? [], [aggregate?.countries]);
  const topSkuRows = useMemo(() => aggregate?.topSkus ?? [], [aggregate?.topSkus]);
  const categoryRows = useMemo(() => aggregate?.categories ?? [], [aggregate?.categories]);
  const reportMonthlyRows = useMemo(() => aggregate?.monthly ?? [], [aggregate?.monthly]);
  const monthlyRows = useMemo(
    () => reportMonthlyRows.filter((row) => completeMonths.size === 0 || completeMonths.has(row.month)),
    [completeMonths, reportMonthlyRows]
  );
  const peak = [...monthlyRows].sort((a, b) => b.amount - a.amount || b.month.localeCompare(a.month))[0];

  const yoy = useMemo(
    () => buildYoYComparison(reportMonthlyRows, completeMonths),
    [completeMonths, reportMonthlyRows],
  );
  const yoyLabel = yoy ? yoyWindowLabel(yoy) : "전년 동기간 비교 데이터 없음";
  const yoyText = !yoy || yoy.growth === null ? "산출 불가" : yoy.growth === "low-base" ? "기준 미달" : `${yoy.growth >= 0 ? "+" : ""}${formatNumber(yoy.growth, 1)}%`;

  const selectedStock = useMemo(() => {
    const selectedIdentity = selectedBrand ? brandIdentityKey(selectedBrand.brand) : "";
    if (!selectedIdentity) return [];
    return stockGapRows.filter((row) => brandIdentityKey(row.brand) === selectedIdentity);
  }, [selectedBrand, stockGapRows]);
  const stockBaseDate = useMemo(() => {
    const dates = selectedStock.map((row) => row.baseDate).filter((date): date is string => Boolean(date)).sort();
    return dates[dates.length - 1] ?? null;
  }, [selectedStock]);
  const salesEntityCode = String(analysisOptions?.entity_code ?? "").trim().toUpperCase();
  const stockEntityCode = String(stockSnapshot?.entityCode ?? "").trim().toUpperCase();
  const stockEntityMismatch = Boolean(salesEntityCode && stockEntityCode && salesEntityCode !== stockEntityCode);
  const stockText = useMemo(() => {
    if (stockSnapshot?.status === "missing") return "현재 세션의 발주분석 결과가 없어 재고·MOI를 결합하지 않았습니다.";
    if (stockSnapshot?.status === "stale") return "발주분석 결과가 현재 세션과 달라 재고·MOI를 결합하지 않았습니다. 발주분석을 다시 실행해 주세요.";
    if (stockEntityMismatch) return `판매 법인(${salesEntityCode})과 재고 법인(${stockEntityCode})이 달라 재고·MOI를 결합하지 않았습니다.`;
    if (!selectedStock.length) return "선택한 브랜드와 일치하는 재고·MOI 데이터가 없습니다.";
    const quantity = selectedStock.reduce((sum, row) => sum + Math.max(row.availableQty ?? 0, 0), 0);
    const daily = selectedStock.reduce((sum, row) => sum + Math.max(row.dailySalesQty ?? 0, 0), 0);
    const moi = daily > 0 ? quantity / daily / 30 : null;
    const risks = selectedStock.filter((row) => row.status === "urgent_replenishment" || row.status === "stock_gap").length;
    const shortage = selectedStock.reduce((sum, row) => sum + stockGapShortageQty(row), 0);
    return `${stockBaseDate ? `재고 기준일 ${stockBaseDate} · ` : ""}현재고 ${formatNumber(quantity)}개 · 평균 MOI ${moi === null ? "산출 불가" : `${formatNumber(moi, 1)}개월`} · 위험 SKU ${formatNumber(risks)}개${shortage > 0 ? ` · 부족 ${formatNumber(shortage)}개` : ""}`;
  }, [salesEntityCode, selectedStock, stockBaseDate, stockEntityCode, stockEntityMismatch, stockSnapshot?.status]);

  // The API intentionally bounds these lists. Their subtotal must never be a
  // concentration denominator: all shares are against the full brand amount.
  const brandAmount = selectedBrand?.amount ?? 0;
  const salesDataIssue = Boolean(selectedBrand && selectedBrand.qty > 0 && brandAmount <= 0);
  const hasUsableSales = Boolean(selectedBrand && brandAmount > 0);
  const salesDataMessage = salesDataIssue
    ? `판매수량 ${formatNumber(selectedBrand?.qty ?? 0)}개가 있으나 매출이 €0입니다. 판매금액 집계를 재검증한 뒤 리포트를 다시 생성해 주세요.`
    : "선택 기간에 유효한 판매금액이 없어 판매 인사이트를 생성하지 않았습니다.";
  const topOneShare = brandAmount > 0 ? (topSkuRows[0]?.amount ?? 0) / brandAmount * 100 : 0;
  const topThreeShare = brandAmount > 0 ? topSkuRows.slice(0, 3).reduce((sum, row) => sum + row.amount, 0) / brandAmount * 100 : 0;
  const salesQualityBlocked = Boolean(dataQuality?.recommendationBlocked || dataQuality?.status === "blocked");
  const stockRecommendationReady = stockSnapshot?.status === "ready" && !stockEntityMismatch;
  const riskStockRows = useMemo(
    () => selectedStock
      .filter((row) => row.status === "urgent_replenishment" || row.status === "stock_gap")
      .sort((left, right) => (right.gapDays ?? 0) - (left.gapDays ?? 0)),
    [selectedStock],
  );
  const recommendationLines = useMemo(() => {
    if (!hasUsableSales) return [salesDataMessage];
    if (!topSkuRows.length) return ["판매 SKU 집계가 없어 발주 우선순위를 제안하지 않았습니다."];
    if (salesQualityBlocked) {
      return [
        `선택 기간 매출 상위 SKU: ${topSkuRows[0].name}`,
        `중복 후보의 최대 매출 영향이 ${formatNumber(dataQuality?.duplicateCandidateAmountSharePct ?? 0, 2)}%로 품질 기준을 초과해 발주 참고를 생성하지 않았습니다.`,
        "CMS 원천의 판매행 고유 ID를 확인한 뒤 분석을 다시 실행해 주세요."
      ];
    }
    if (!stockRecommendationReady) {
      const unavailableText = stockSnapshot?.status === "missing"
        ? "현재 발주분석 결과가 없어 발주 참고를 생성하지 않았습니다. 발주분석을 먼저 실행해 주세요."
        : stockSnapshot?.status === "stale"
          ? "현재 세션과 일치하는 발주분석 결과가 없어 발주 참고를 생성하지 않았습니다. 발주분석을 다시 실행해 주세요."
          : stockEntityMismatch
            ? `판매 법인(${salesEntityCode})과 재고 법인(${stockEntityCode})이 달라 발주 참고를 생성하지 않았습니다.`
            : "현재 재고·MOI를 확인할 수 없어 발주 참고를 생성하지 않았습니다.";
      return [
        `선택 기간 매출 상위 SKU: ${topSkuRows[0].name}`,
        unavailableText
      ];
    }
    if (!selectedStock.length) {
      return [
        `선택 기간 매출 상위 SKU: ${topSkuRows[0].name}`,
        "선택한 브랜드의 재고·MOI 데이터가 없어 발주 참고를 생성하지 않았습니다."
      ];
    }
    if (riskStockRows.length) {
      const riskNames = riskStockRows.slice(0, 2).map((row) => row.productName || row.sku);
      const action = riskStockRows[0].priorityAction?.trim();
      return [
        "현재 재고·MOI 기준 재고공백 또는 긴급보충 위험 SKU입니다.",
        ...riskNames,
        action ? `권장 조치: ${action}` : "입고 예정과 가용재고를 확인한 뒤 보충 수량을 검토해 주세요."
      ];
    }
    return [
      `선택 기간 매출 상위 SKU: ${topSkuRows[0].name}`,
      "현재 재고·MOI 기준 긴급보충 또는 재고공백 위험은 확인되지 않았습니다."
    ];
  }, [
    hasUsableSales,
    riskStockRows,
    salesDataMessage,
    salesEntityCode,
    salesQualityBlocked,
    selectedStock.length,
    stockEntityCode,
    stockEntityMismatch,
    stockRecommendationReady,
    stockSnapshot?.status,
    topSkuRows,
    dataQuality?.duplicateCandidateAmountSharePct
  ]);
  const hasPartialMonth = (report?.monthCoverage ?? []).some((item) => item.status !== "complete");
  const salesBasis = hasPartialMonth ? "선택 기간 합계 · 부분 월 포함" : "선택 기간 합계";

  const exchangeRateBasis =
    exchangeRateBasisLabel(analysisOptions, rate) || "금액 기준 정보 없음";
  const amountBasisLabel = String(analysisOptions?.currency_code ?? "").toUpperCase() === "KRW"
    ? "매출 금액 기준"
    : "원화 환산 기준";
  const reportBasisRows: ReportBasisRow[] = [
    ["판매 기간", reportPeriodShort], ["YTD YoY 기준", yoyLabel], ["점유율 기준", "전체 브랜드 매출 대비"], [amountBasisLabel, exchangeRateBasis]
  ];
  const metricRows: ReportMetricRow[] = [
    ["총매출", selectedBrand ? salesDataIssue ? "검증 필요" : wonEok(selectedBrand.amount) : "-", salesDataIssue ? "neg" : "ink", salesDataIssue ? "판매수량·매출 불일치" : krwEokFromEur(selectedBrand?.amount ?? 0, rate) || salesBasis],
    ["YTD YoY", yoyText, typeof yoy?.growth === "number" && yoy.growth < 0 ? "neg" : "brand", yoyLabel],
    ["점유율", `${formatNumber(selectedShare, 1)}%`, "ink", "전체 브랜드 매출 대비"],
    ["판매 SKU", selectedBrand ? formatNumber(selectedBrand.skuCount) : "-", "ink", "판매 발생 SKU 수"]
  ];
  const countryText = countryRows.map((row) => `${row.name} ${formatNumber(selectedBrand && selectedBrand.amount > 0 ? row.amount / selectedBrand.amount * 100 : 0, 0)}%`);
  const categoryText = categoryRows.map((row) => `${row.category1}${row.category2 !== row.category1 ? ` - ${row.category2}` : ""} ${formatNumber(brandAmount > 0 ? row.amount / brandAmount * 100 : 0, 0)}%`);
  const countrySummaryLines = hasUsableSales
    ? [`${reportPeriod} 기준 국가별 매출 비중입니다.`, ...(countryText.length ? countryText : ["국가 데이터 없음"])]
    : [salesDataMessage];
  const topSkuSummaryLines = hasUsableSales
    ? [`${reportPeriod} 기준 매출 상위 SKU입니다.`, ...(topSkuRows.length ? topSkuRows.slice(0, 3).map((row) => row.name) : ["SKU 데이터 없음"])]
    : [salesDataMessage];
  const concentrationLines = hasUsableSales
    ? [`상위 1종 ${formatNumber(topOneShare, 0)}%`, `상위 3종 ${formatNumber(topThreeShare, 0)}%`]
    : [salesDataMessage];
  const peakLines = hasUsableSales && peak && peak.amount > 0
    ? [`${peak.month} 매출이 ${reportAmountText(peak.amount, rate)}로 가장 높습니다.`]
    : [salesDataMessage];
  const categorySummaryLines = hasUsableSales
    ? [`${reportPeriod} 기준 카테고리별 매출 비중입니다.`, ...(categoryText.length ? categoryText : ["카테고리 데이터 없음"])]
    : [salesDataMessage];
  const showOrderAnalysisSections = Boolean(
    selectedBrand && stockSnapshot?.status === "ready" && !stockEntityMismatch
  );
  const orderAnalysisRows: ReportSummaryRow[] = showOrderAnalysisSections ? [
    ["08", "현재 재고 · MOI", [stockText]],
    ["09", "향후 발주 참고", [topSkuRows[0] ? `${topSkuRows[0].name} 중심으로 최신 판매와 재고 추이를 확인해 주세요.` : "상위 SKU 데이터를 확인해 주세요."]]
  ] : [];
  const baseSummaryRows: ReportSummaryRow[] = [
    ["01", "브랜드 전체 판매 현황", selectedBrand ? [`${salesBasis}(${reportPeriod}) 기준 ${displayBrandName(selectedBrand.brand)} 매출은 ${reportAmountText(selectedBrand.amount, rate)}입니다.`, `전체 브랜드 매출 대비 점유율은 ${formatNumber(selectedShare, 1)}%입니다.`, `판매수량은 ${formatNumber(selectedBrand.qty)}개입니다.`] : ["브랜드를 선택해 주세요."]],
    ["02", "YTD YoY 비교", [yoy ? `${yoyLabel} 매출 ${reportAmountText(yoy.previous, rate)} → ${reportAmountText(yoy.current, rate)} 기준입니다.` : "전년 동기간 비교 데이터가 없어 YTD YoY를 산출하지 않았습니다."]],
    ["03", "주요 판매 국가", [`${reportPeriod} 기준 국가별 매출 비중입니다.`, ...(countryText.length ? countryText : ["국가 데이터 없음"])]],
    ["04", "상위 SKU", [`${reportPeriod} 기준 매출 상위 SKU입니다.`, ...(topSkuRows.slice(0, 3).map((row) => row.name) || ["SKU 데이터 없음"])]],
    ["05", "SKU 집중도", [`상위 1종 ${formatNumber(topOneShare, 0)}%`, `상위 3종 ${formatNumber(topThreeShare, 0)}%`]],
    ["06", "기간 내 최고 매출월", [peak ? `${peak.month} 매출이 ${reportAmountText(peak.amount, rate)}로 가장 높습니다.` : "완결 월별 매출 데이터가 없습니다."]],
    ["07", "카테고리 · 라인 매출 비중", [`${reportPeriod} 기준 카테고리별 매출 비중입니다.`, ...(categoryText.length ? categoryText : ["카테고리 데이터 없음"]) ]],
    ...orderAnalysisRows
  ];
  const summaryRows: ReportSummaryRow[] = baseSummaryRows.map<ReportSummaryRow>(([number, title, bodyLines]) => {
    if (!hasUsableSales && number !== "08") return [number, title, [salesDataMessage]];
    if (number === "03") return [number, title, countrySummaryLines];
    if (number === "04") return [number, title, topSkuSummaryLines];
    if (number === "05") return [number, title, concentrationLines];
    if (number === "06") return [number, title, peakLines];
    if (number === "07") return [number, title, categorySummaryLines];
    if (number === "09") return [number, title, recommendationLines];
    return [number, title, bodyLines];
  });

  const visibleMetricRows = canViewAmountData
    ? metricRows
    : metricRows.filter(([label]) => !isAmountField(label));
  const visibleSummaryRows = canViewAmountData
    ? summaryRows
    : summaryRows.map(([number, title, bodyLines]) => [
        number,
        title,
        bodyLines.map(redactAmountText)
      ] as ReportSummaryRow);
  const { exportingPdf, pdfExportError, exportReportPdf } = useReportPdfExport({
    selectedBrand,
    reportBasisRows,
    metricRows: visibleMetricRows,
    summaryRows: visibleSummaryRows
  });
  return {
    loading,
    loadFailed,
    reportDataIssue,
    brandSummaries,
    selectedBrand,
    selectedBrandName,
    setSelectedBrandName,
    analysisOptions,
    reportBasisRows,
    metricRows: visibleMetricRows,
    summaryRows: visibleSummaryRows,
    exportingPdf,
    pdfExportError,
    exportReportPdf
  };
}
