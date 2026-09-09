"use client";

import { useEffect, useMemo, useState } from "react";

import { displayBrandName } from "@/lib/brand-display";
import {
  amountOf,
  brandOf,
  category1Of,
  category2Of,
  monthKeyOf,
  productNameOf,
  qtyOf,
  skuCodeOf
} from "@/lib/global-demand-view-model";
import { completeSeasonMonthKeys } from "@/lib/season-calendar";
import { formatNumber } from "@/lib/utils";
import { exchangeRateBasisLabel, krwEokFromEur, wonEok } from "../../lib/currency-format";
import { escapeReportHtml, injectReportWatermark } from "../../lib/report-html";
import { analysisPeriodLabel, longKoreanDateLabel } from "../../lib/workspace-format";
import {
  completedYtdComparableYearWindow,
  completedYtdPeriodLabel,
  ytdAmountComparisonsByLabel
} from "../../lib/yoy-comparison";
import { useSkuScreenData } from "../sku/useSkuScreenData";

const REPORT_SKU_LIMIT = 50;

export type CategoryMetricBasis = "amount" | "qty";

export type CategorySummary = {
  key: string;
  label: string;
  amount: number;
  qty: number;
  skuCount: number;
  brandCount: number;
  value: number;
  sharePct: number;
  width: string;
  ytdGrowth: string;
};

export type CategorySkuRow = {
  sku: string;
  name: string;
  brand: string;
  amount: number;
  qty: number;
  value: number;
  peakMonth: number;
  sharePct: number;
  width: string;
  ytdGrowth: string;
};

function categoryLabelOf(row: Record<string, unknown>): string {
  const c1 = category1Of(row);
  const c2 = category2Of(row);
  const has1 = c1 && !c1.includes("미분류");
  const has2 = c2 && !c2.includes("미분류");
  if (has1 && has2 && c1 !== c2) return `${c1} > ${c2}`;
  if (has2) return c2;
  if (has1) return c1;
  return "미분류";
}

export function useCategoryScreenModel() {
  const { rows, monthlyRows, monthCoverage, analysisOptions, loading, loadFailed } = useSkuScreenData();
  const [metricBasis, setMetricBasis] = useState<CategoryMetricBasis>("amount");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [exportingCategoryPdf, setExportingCategoryPdf] = useState(false);

  const averageEurKrwRate = Number(analysisOptions?.average_eur_krw_rate ?? 0) || null;
  const completeMonthKeys = useMemo(() => completeSeasonMonthKeys(monthCoverage), [monthCoverage]);
  const categoryYtdWindow = useMemo(
    () => completedYtdComparableYearWindow(
      monthlyRows,
      monthCoverage.length > 0 ? completeMonthKeys : undefined
    ),
    [completeMonthKeys, monthCoverage.length, monthlyRows]
  );
  const categoryYtdComparisons = useMemo(
    () => ytdAmountComparisonsByLabel(monthlyRows, categoryYtdWindow, categoryLabelOf),
    [categoryYtdWindow, monthlyRows]
  );
  const skuYtdComparisons = useMemo(
    () => ytdAmountComparisonsByLabel(monthlyRows, categoryYtdWindow, skuCodeOf),
    [categoryYtdWindow, monthlyRows]
  );
  const categoryYtdPeriodLabel = completedYtdPeriodLabel(categoryYtdWindow);

  // 제품군(기능구분1 > 기능구분2) 단위로 판매 데이터를 집계한다. 각 제품군은 소속 SKU와
  // 브랜드 집합을 함께 유지해 순위·점유율·SKU 드릴다운을 한 번의 순회로 만든다.
  const categoryData = useMemo(() => {
    const byCategory = new Map<
      string,
      {
        label: string;
        amount: number;
        qty: number;
        skus: Map<string, { sku: string; name: string; brand: string; amount: number; qty: number }>;
        brands: Set<string>;
      }
    >();
    rows.forEach((row) => {
      const label = categoryLabelOf(row);
      const current = byCategory.get(label) ?? { label, amount: 0, qty: 0, skus: new Map(), brands: new Set<string>() };
      current.amount += amountOf(row);
      current.qty += qtyOf(row);
      const brand = brandOf(row);
      if (brand) current.brands.add(brand);
      const sku = skuCodeOf(row);
      if (sku && sku !== "-") {
        const skuCurrent = current.skus.get(sku) ?? { sku, name: productNameOf(row), brand, amount: 0, qty: 0 };
        skuCurrent.amount += amountOf(row);
        skuCurrent.qty += qtyOf(row);
        current.skus.set(sku, skuCurrent);
      }
      byCategory.set(label, current);
    });
    return byCategory;
  }, [rows]);

  const hasAmount = useMemo(() => Array.from(categoryData.values()).some((category) => category.amount > 0), [categoryData]);
  const effectiveBasis: CategoryMetricBasis = metricBasis === "amount" && !hasAmount ? "qty" : metricBasis;

  const categorySummaries = useMemo<CategorySummary[]>(() => {
    const valueOf = (item: { amount: number; qty: number }) => (effectiveBasis === "amount" ? item.amount : item.qty);
    const list = Array.from(categoryData.values());
    const total = list.reduce((sum, category) => sum + valueOf(category), 0);
    const max = Math.max(...list.map((category) => valueOf(category)), 1);
    return list
      .map((category) => ({
        key: category.label,
        label: category.label,
        amount: category.amount,
        qty: category.qty,
        skuCount: category.skus.size,
        brandCount: category.brands.size,
        value: valueOf(category),
        sharePct: total > 0 ? (valueOf(category) / total) * 100 : 0,
        width: `${Math.max(4, (valueOf(category) / max) * 100)}%`,
        ytdGrowth: categoryYtdComparisons.get(category.label)?.growth ?? "-"
      }))
      .sort((a, b) => b.value - a.value);
  }, [categoryData, categoryYtdComparisons, effectiveBasis]);

  // 선택 제품군이 없거나 더 이상 존재하지 않으면 최상위 제품군으로 되돌린다.
  useEffect(() => {
    if (categorySummaries.length === 0) return;
    if (!selectedCategory || !categorySummaries.some((category) => category.key === selectedCategory)) {
      setSelectedCategory(categorySummaries[0].key);
    }
  }, [categorySummaries, selectedCategory]);

  const activeCategory = categorySummaries.find((category) => category.key === selectedCategory) ?? categorySummaries[0] ?? null;

  const selectedSkuSet = useMemo(() => {
    const category = categoryData.get(activeCategory?.key ?? "");
    return category ? new Set(category.skus.keys()) : new Set<string>();
  }, [categoryData, activeCategory?.key]);

  // 선택 제품군 소속 SKU의 피크월(선택 지표 기준). 월별 데이터가 없으면 0.
  const peakMonthBySku = useMemo(() => {
    const monthsBySku = new Map<string, number[]>();
    monthlyRows.forEach((row) => {
      const sku = skuCodeOf(row);
      if (!selectedSkuSet.has(sku)) return;
      const month = Number(monthKeyOf(row).slice(-2));
      if (month < 1 || month > 12) return;
      const months = monthsBySku.get(sku) ?? Array.from({ length: 12 }, () => 0);
      months[month - 1] += effectiveBasis === "amount" ? amountOf(row) : qtyOf(row);
      monthsBySku.set(sku, months);
    });
    const peak = new Map<string, number>();
    monthsBySku.forEach((months, sku) => {
      let bestMonth = 0;
      let bestValue = 0;
      months.forEach((value, index) => {
        if (value > bestValue) {
          bestValue = value;
          bestMonth = index + 1;
        }
      });
      if (bestMonth > 0) peak.set(sku, bestMonth);
    });
    return peak;
  }, [monthlyRows, selectedSkuSet, effectiveBasis]);

  const allCategorySkuRows = useMemo<CategorySkuRow[]>(() => {
    const category = categoryData.get(activeCategory?.key ?? "");
    if (!category) return [];
    const valueOf = (item: { amount: number; qty: number }) => (effectiveBasis === "amount" ? item.amount : item.qty);
    const skus = Array.from(category.skus.values());
    const total = skus.reduce((sum, sku) => sum + valueOf(sku), 0);
    const max = Math.max(...skus.map((sku) => valueOf(sku)), 1);
    return skus
      .map((sku) => ({
        sku: sku.sku,
        name: sku.name,
        brand: sku.brand,
        amount: sku.amount,
        qty: sku.qty,
        value: valueOf(sku),
        peakMonth: peakMonthBySku.get(sku.sku) ?? 0,
        sharePct: total > 0 ? (valueOf(sku) / total) * 100 : 0,
        width: `${Math.max(4, (valueOf(sku) / max) * 100)}%`,
        ytdGrowth: skuYtdComparisons.get(sku.sku)?.growth ?? "-"
      }))
      .sort((a, b) => b.value - a.value);
  }, [categoryData, activeCategory?.key, peakMonthBySku, effectiveBasis, skuYtdComparisons]);

  const categorySkuRows = allCategorySkuRows.slice(0, 5);
  const totalValue = useMemo(() => categorySummaries.reduce((sum, category) => sum + category.value, 0), [categorySummaries]);

  // design-token-audit: report-template-start — 별도 인쇄 문서로 자체 팔레트를 내장한다.
  const exportCategoryReportPdf = () => {
    if (exportingCategoryPdf || !activeCategory) return;
    setExportingCategoryPdf(true);

    const generatedAt = new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    }).format(new Date());
    const fileDate = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" }).format(new Date());
    const reportPeriod = analysisPeriodLabel(analysisOptions);
    const reportDataAsOf = longKoreanDateLabel(analysisOptions?.end_date);
    const metricLabel = effectiveBasis === "amount" ? "매출액" : "판매량";
    const showAmount = effectiveBasis === "amount";
    const valueText = (amount: number, qty: number) => (showAmount ? wonEok(amount) || "-" : `${formatNumber(qty)}개`);
    const krwText = (amount: number) => (showAmount ? krwEokFromEur(amount, averageEurKrwRate) : "");
    const rateNote = showAmount ? exchangeRateBasisLabel(analysisOptions, averageEurKrwRate) : "";

    const reportWindow = window.open("", "_blank", "width=1200,height=900");
    if (!reportWindow) {
      setExportingCategoryPdf(false);
      return;
    }

    const skuRowsForReport = allCategorySkuRows.slice(0, REPORT_SKU_LIMIT);
    const skuOverflowNote = allCategorySkuRows.length > REPORT_SKU_LIMIT
      ? `상위 ${formatNumber(REPORT_SKU_LIMIT)}개만 표시 · 전체 ${formatNumber(allCategorySkuRows.length)}개`
      : `전체 ${formatNumber(allCategorySkuRows.length)}개`;

    const categoryRowsHtml = categorySummaries
      .map((category, index) => `<tr><td class="rank">${index + 1}</td><td><div class="name">${escapeReportHtml(category.label)}</div><div class="bar-bg"><div class="bar" style="width:${escapeReportHtml(category.width)}"></div></div></td><td class="num">${escapeReportHtml(`${formatNumber(category.skuCount)} SKU · ${formatNumber(category.brandCount)} 브랜드`)}</td><td class="amount">${escapeReportHtml(valueText(category.amount, category.qty))}</td><td class="amount accent">${escapeReportHtml(formatNumber(category.sharePct, 1))}%</td></tr>`)
      .join("");

    const skuRowsHtml = skuRowsForReport.length > 0
      ? skuRowsForReport
        .map((row, index) => `<tr><td class="rank">${index + 1}</td><td><div class="name">${escapeReportHtml(row.name)}</div><div class="muted">${escapeReportHtml([displayBrandName(row.brand), row.sku, row.peakMonth ? `피크 ${row.peakMonth}월` : ""].filter(Boolean).join(" · "))}</div></td><td class="amount">${escapeReportHtml(valueText(row.amount, row.qty))}${krwText(row.amount) ? `<br /><span class="muted">${escapeReportHtml(krwText(row.amount))}</span>` : ""}</td><td class="amount accent">${escapeReportHtml(formatNumber(row.sharePct, 1))}%</td></tr>`)
        .join("")
      : `<tr><td colspan="4" class="muted" style="padding:16px 0;text-align:center">이 제품군에 표시할 SKU가 없습니다.</td></tr>`;

    const metricCards = [
      ["전체 제품군", `${formatNumber(categorySummaries.length)}개`, "기능구분 1·2 기준"],
      ["최대 제품군", categorySummaries[0]?.label ?? "-", `${formatNumber(categorySummaries[0]?.sharePct ?? 0, 1)}% 비중`],
      ["분석 기준", metricLabel, "순위·비중 기준 지표"],
      ["선택 제품군", activeCategory.label, `${formatNumber(activeCategory.sharePct, 1)}% · ${formatNumber(activeCategory.skuCount)} SKU`]
    ];

    const html = `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>제품군 분석 리포트 ${escapeReportHtml(fileDate)}</title>
  <style>
    @page { size: A4 landscape; margin: 12mm; }
    * { box-sizing: border-box; -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
    body { margin: 0; background: #f3f4f6; color: #05060a; font-family: Arial, "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; }
    .page { padding: 24px; }
    .header { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; margin-bottom: 18px; }
    .eyebrow { font-size: 11px; font-weight: 900; color: #e90035; letter-spacing: .02em; }
    h1 { margin: 4px 0 8px; font-size: 24px; line-height: 1.15; }
    .desc, .muted { color: #69707f; font-weight: 700; }
    .desc { font-size: 12px; }
    .date { font-size: 11px; text-align: right; }
    .rate-note { margin-top: 8px; color: #69707f; font-size: 11px; font-weight: 800; }
    .grid { display: grid; gap: 14px; }
    .metrics { grid-template-columns: repeat(4, 1fr); margin-bottom: 14px; }
    .metric, .section { background: #fff; border: 1px solid #e2e4e8; border-radius: 14px; box-shadow: 0 6px 16px rgba(15, 23, 42, .06); }
    .metric { padding: 16px 18px; min-height: 82px; }
    .label { color: #69707f; font-size: 11px; font-weight: 800; }
    .value { margin-top: 10px; font-size: 20px; font-weight: 950; word-break: keep-all; }
    .accent { color: #e90035; }
    .section { padding: 18px; margin-bottom: 14px; }
    .section-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
    h2 { margin: 0; font-size: 15px; }
    table { width: 100%; border-collapse: collapse; }
    td, th { border-bottom: 1px solid #edf0f3; padding: 10px 8px; font-size: 12px; vertical-align: middle; }
    th { color: #69707f; text-align: left; font-size: 11px; }
    .rank { width: 32px; color: #9aa1ad; font-weight: 900; }
    .name { font-weight: 900; }
    .num { color: #69707f; font-weight: 800; white-space: nowrap; }
    .amount { text-align: right; font-weight: 950; white-space: nowrap; }
    th.amount { text-align: right; }
    .bar-bg { height: 6px; border-radius: 999px; background: #f0f1f4; overflow: hidden; margin-top: 8px; }
    .bar { height: 100%; border-radius: 999px; background: #e90035; }
    .print-note { margin-top: 16px; color: #69707f; font-size: 10px; font-weight: 700; text-align: right; }
    @media print { body { background: #f3f4f6; } .page { padding: 0; } }
  </style>
</head>
<body>
  <main class="page">
    <header class="header">
      <div>
        <div class="eyebrow">분석 · INSIGHT</div>
        <h1>제품군 기준 분석 리포트</h1>
        <div class="desc">기능구분 1·2로 묶은 제품군별 순위와 제품군 내 SKU 경쟁 위치를 요약합니다.</div>
        <div class="desc" style="margin-top:6px;color:#303746;font-weight:900">집계 기간 ${escapeReportHtml(reportPeriod)} · 판매 데이터 기준 ${escapeReportHtml(reportDataAsOf)}</div>
        <div class="desc" style="margin-top:4px">리뉴얼 전후 제품은 별도 SKU 코드로 집계됩니다.</div>
        ${rateNote ? `<div class="rate-note">${escapeReportHtml(rateNote)}</div>` : ""}
      </div>
      <div class="date muted">생성일<br />${escapeReportHtml(generatedAt)}</div>
    </header>
    <section class="grid metrics">
      ${metricCards.map(([label, value, sub]) => `<div class="metric"><div class="label">${escapeReportHtml(label)}</div><div class="value">${escapeReportHtml(value)}</div><div class="rate-note" style="margin-top:6px">${escapeReportHtml(sub)}</div></div>`).join("")}
    </section>
    <section class="section">
      <div class="section-head"><h2>제품군 전체 순위</h2><span class="muted">${escapeReportHtml(`${metricLabel} 기준 · 전체 ${formatNumber(categorySummaries.length)}개`)}</span></div>
      <table>
        <thead><tr><th class="rank">순위</th><th>제품군</th><th>구성</th><th class="amount">${escapeReportHtml(metricLabel)}</th><th class="amount">비중</th></tr></thead>
        <tbody>${categoryRowsHtml}</tbody>
      </table>
    </section>
    <section class="section">
      <div class="section-head"><h2>${escapeReportHtml(activeCategory.label)} · SKU 순위</h2><span class="muted">${escapeReportHtml(`${metricLabel} 기준 · ${skuOverflowNote}`)}</span></div>
      <table>
        <thead><tr><th class="rank">순위</th><th>상품 · 브랜드 · 코드</th><th class="amount">${escapeReportHtml(metricLabel)}</th><th class="amount">제품군 내 비중</th></tr></thead>
        <tbody>${skuRowsHtml}</tbody>
      </table>
    </section>
    <div class="print-note">Silicon2 SCM · 제품군 분석 리포트</div>
  </main>
  <script>
    window.addEventListener("load", () => {
      document.title = "category-analysis-report-${escapeReportHtml(fileDate)}";
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
    window.setTimeout(() => setExportingCategoryPdf(false), 800);
  };
  // design-token-audit: report-template-end

  return {
    loading,
    loadFailed,
    analysisOptions,
    averageEurKrwRate,
    categoryYtdPeriodLabel,
    metricBasis: effectiveBasis,
    setMetricBasis,
    hasAmount,
    categorySummaries,
    totalValue,
    selectedCategory: activeCategory?.key ?? "",
    setSelectedCategory,
    activeCategory,
    categorySkuRows,
    allCategorySkuRows,
    exportingCategoryPdf,
    exportCategoryReportPdf
  };
}
