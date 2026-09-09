import fs from "node:fs/promises";

import {
  buildCalendarMonthAverageProfile,
  buildTopSkuConcentration,
  completeSeasonalityMonthKeys
} from "../lib/brand-analysis.ts";
import { displayBrandName } from "../lib/brand-display.ts";
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
} from "../lib/global-demand-view-model.ts";

const API_URL = process.env.BACKTEST_URL || "http://127.0.0.1:8002/api/season-trend/latest";
const OUTPUT_PATH = process.env.BACKTEST_OUTPUT || "";
const ALLOW_FINDINGS = process.env.BACKTEST_ALLOW_FINDINGS === "1";
const EPSILON = 1e-5;
const LOW_BASE_AMOUNT_EUR = 500;

function sum(rows, valueOf) {
  return rows.reduce((total, row) => total + valueOf(row), 0);
}

function close(left, right, tolerance = EPSILON) {
  return Number.isFinite(left) && Number.isFinite(right) && Math.abs(left - right) <= tolerance;
}

function previousMonthKey(monthKey) {
  const [year, month] = monthKey.split("-").map(Number);
  if (!Number.isFinite(year) || !Number.isFinite(month)) return "";
  const previous = new Date(year, month - 2, 1);
  return `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, "0")}`;
}

function previousYearMonthKey(monthKey) {
  const match = monthKey.match(/^(\d{4})-(\d{2})$/);
  return match ? `${Number(match[1]) - 1}-${match[2]}` : "";
}

function normalizeLabel(value) {
  return String(value ?? "").normalize("NFKC").replace(/\s+/g, "").toLowerCase();
}

function addNumber(map, key, value) {
  map.set(key, (map.get(key) ?? 0) + value);
}

function addSet(map, key, value) {
  const values = map.get(key) ?? new Set();
  values.add(value);
  map.set(key, values);
}

function groupMetrics(rows) {
  const grouped = new Map();
  for (const row of rows) {
    const brand = brandOf(row);
    const current = grouped.get(brand) ?? {
      amount: 0,
      qty: 0,
      skus: new Set(),
      countries: new Set(),
      categories: new Set(),
      rows: 0
    };
    current.amount += amountOf(row);
    current.qty += qtyOf(row);
    const sku = skuCodeOf(row);
    if (sku && sku !== "-") current.skus.add(sku);
    const country = countryOf(row);
    if (country && country !== "미상") current.countries.add(country);
    const category = category1Of(row);
    if (category && !category.includes("미분류")) current.categories.add(category);
    current.rows += 1;
    grouped.set(brand, current);
  }
  return grouped;
}

function duplicateKeyStats(rows, keyOf) {
  const counts = new Map();
  for (const row of rows) {
    const key = keyOf(row);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const duplicates = [...counts.entries()].filter(([, count]) => count > 1);
  return {
    duplicatedKeys: duplicates.length,
    affectedRows: duplicates.reduce((total, [, count]) => total + count, 0),
    samples: duplicates.slice(0, 5).map(([key, count]) => ({ key, count }))
  };
}

function lineCategoryOf(row) {
  const category1 = category1Of(row);
  const category2 = category2Of(row);
  const hasCategory1 = category1 && !category1.includes("미분류");
  const hasCategory2 = category2 && !category2.includes("미분류");
  if (hasCategory1 && hasCategory2 && category1 !== category2) return `${category1} · ${category2}`;
  if (hasCategory2) return category2;
  if (hasCategory1) return category1;
  return "미분류";
}

const findings = [];
const checks = [];

function recordCheck(id, passed, evidence) {
  checks.push({ id, passed, evidence });
}

function recordFinding(severity, id, title, evidence, impact, recommendation) {
  findings.push({ severity, id, title, evidence, impact, recommendation });
}

const response = await fetch(API_URL);
if (!response.ok) throw new Error(`latest endpoint failed: ${response.status}`);
const payload = await response.json();
const season = payload.season_analysis ?? {};
const summaryRows = season.countrySkuSummary ?? [];
const monthlyRows = season.countrySkuMonthly ?? [];
const coverageRows = season.monthCoverage ?? [];

recordCheck("payload.status", payload.status === "success", { status: payload.status });
recordCheck("payload.schema", Number(payload.analysis_schema_version) >= 5, { schema: payload.analysis_schema_version });
recordCheck("source.complete_cross_analysis_cube", season.crossAnalysisComplete === true, { crossAnalysisComplete: season.crossAnalysisComplete });
recordCheck("source.non_empty", summaryRows.length > 0 && monthlyRows.length > 0, {
  summaryRows: summaryRows.length,
  monthlyRows: monthlyRows.length
});

const summaryAmount = sum(summaryRows, amountOf);
const monthlyAmount = sum(monthlyRows, amountOf);
const summaryQty = sum(summaryRows, qtyOf);
const monthlyQty = sum(monthlyRows, qtyOf);
recordCheck("source.total_amount_reconciliation", close(summaryAmount, monthlyAmount), { summaryAmount, monthlyAmount, difference: summaryAmount - monthlyAmount });
recordCheck("source.total_qty_reconciliation", close(summaryQty, monthlyQty), { summaryQty, monthlyQty, difference: summaryQty - monthlyQty });

const summaryGrain = duplicateKeyStats(summaryRows, (row) => [
  countryOf(row), category1Of(row), category2Of(row), skuCodeOf(row), brandOf(row), productNameOf(row)
].join("\u0000"));
const monthlyGrain = duplicateKeyStats(monthlyRows, (row) => [
  monthKeyOf(row), countryOf(row), category1Of(row), category2Of(row), skuCodeOf(row), brandOf(row), productNameOf(row)
].join("\u0000"));
recordCheck("source.summary_grain_unique", summaryGrain.duplicatedKeys === 0, summaryGrain);
recordCheck("source.monthly_grain_unique", monthlyGrain.duplicatedKeys === 0, monthlyGrain);

if (summaryGrain.duplicatedKeys > 0 || monthlyGrain.duplicatedKeys > 0) {
  recordFinding(
    "critical",
    "duplicated_source_grain",
    "브랜드 집계의 원천 키가 중복됩니다.",
    { summary: summaryGrain, monthly: monthlyGrain },
    "브랜드 매출·수량·SKU 수가 중복 합산될 수 있습니다.",
    "백엔드 집계 키를 국가·카테고리·SKU·브랜드·월 단위로 고정하고 유일성 테스트를 추가하세요."
  );
}

const summaryByBrand = groupMetrics(summaryRows);
const monthlyByBrand = groupMetrics(monthlyRows);
const allBrands = [...new Set([...summaryByBrand.keys(), ...monthlyByBrand.keys()])].sort();
const brandReconciliationFailures = [];
for (const brand of allBrands) {
  const summary = summaryByBrand.get(brand) ?? { amount: 0, qty: 0, skus: new Set(), countries: new Set() };
  const monthly = monthlyByBrand.get(brand) ?? { amount: 0, qty: 0, skus: new Set(), countries: new Set() };
  const skuOnlyInSummary = [...summary.skus].filter((sku) => !monthly.skus.has(sku));
  const skuOnlyInMonthly = [...monthly.skus].filter((sku) => !summary.skus.has(sku));
  if (!close(summary.amount, monthly.amount) || !close(summary.qty, monthly.qty) || skuOnlyInSummary.length || skuOnlyInMonthly.length) {
    brandReconciliationFailures.push({
      brand,
      summaryAmount: summary.amount,
      monthlyAmount: monthly.amount,
      summaryQty: summary.qty,
      monthlyQty: monthly.qty,
      skuOnlyInSummary: skuOnlyInSummary.slice(0, 10),
      skuOnlyInMonthly: skuOnlyInMonthly.slice(0, 10)
    });
  }
}
recordCheck("brand.summary_monthly_reconciliation", brandReconciliationFailures.length === 0, {
  brandsChecked: allBrands.length,
  failures: brandReconciliationFailures.length,
  samples: brandReconciliationFailures.slice(0, 5)
});
if (brandReconciliationFailures.length) {
  recordFinding(
    "critical",
    "brand_cube_mismatch",
    "브랜드 요약과 월별 큐브가 일치하지 않습니다.",
    { failures: brandReconciliationFailures.length, samples: brandReconciliationFailures.slice(0, 5) },
    "브랜드 순위/KPI와 월별 추이·성장률이 서로 다른 값을 표시할 수 있습니다.",
    "동일 필터와 동일 집계 키로 summary/monthly 큐브를 생성하고 브랜드별 합계 대조를 배포 테스트로 고정하세요."
  );
}

const coverageByMonth = new Map(coverageRows.map((row) => [String(row.month), row]));
const monthlyAmountByMonth = new Map();
const monthlyQtyByMonth = new Map();
for (const row of monthlyRows) {
  addNumber(monthlyAmountByMonth, monthKeyOf(row), amountOf(row));
  addNumber(monthlyQtyByMonth, monthKeyOf(row), qtyOf(row));
}
const coverageFailures = [];
for (const [month, coverage] of coverageByMonth) {
  const amount = monthlyAmountByMonth.get(month) ?? 0;
  const qty = monthlyQtyByMonth.get(month) ?? 0;
  if (!close(amount, Number(coverage.totalAmount)) || !close(qty, Number(coverage.totalQty))) {
    coverageFailures.push({ month, coverageAmount: Number(coverage.totalAmount), monthlyAmount: amount, coverageQty: Number(coverage.totalQty), monthlyQty: qty });
  }
}
recordCheck("month.coverage_reconciliation", coverageFailures.length === 0, {
  monthsChecked: coverageRows.length,
  failures: coverageFailures
});

const completeMonths = coverageRows.filter((row) => row.status === "complete").map((row) => String(row.month)).sort();
const completeMonthSet = new Set(completeMonths);
const momTargets = completeMonths.filter((month) => completeMonthSet.has(previousMonthKey(month)));
const yoyTargets = completeMonths.filter((month) => completeMonthSet.has(previousYearMonthKey(month)));
recordCheck("growth.complete_month_only", momTargets.every((month) => coverageByMonth.get(month)?.status === "complete" && coverageByMonth.get(previousMonthKey(month))?.status === "complete") && yoyTargets.every((month) => coverageByMonth.get(month)?.status === "complete" && coverageByMonth.get(previousYearMonthKey(month))?.status === "complete"), {
  completeMonths,
  momTargets,
  yoyTargets
});

const partialMonths = coverageRows.filter((row) => row.status !== "complete");
const partialAmount = partialMonths.reduce((total, row) => total + Number(row.totalAmount ?? 0), 0);
if (partialMonths.length > 0 && summaryAmount !== 0) {
  recordFinding(
    "low",
    "partial_month_scope_difference",
    "브랜드 순위/KPI와 성장률의 반영 월 범위가 다릅니다.",
    {
      partialMonths: partialMonths.map((row) => ({ month: row.month, status: row.status, reason: row.reason, totalAmount: row.totalAmount })),
      partialAmount,
      partialAmountSharePct: (partialAmount / summaryAmount) * 100,
      growthCompleteMonths: completeMonths
    },
    "순위·점유율·SKU/국가 분포는 선택기간 전체, 성장률·시즌성은 완료월 기준이며 화면의 집계 기준 배너에서 이를 구분합니다.",
    "부분월 포함 정책이 변경되면 집계 기준 배너와 보고서 메타데이터를 함께 갱신하세요."
  );
}

const invalidBrandRows = summaryRows.filter((row) => ["", "-", "미분류 브랜드", "unknown", "n/a", "nan", "none"].includes(brandOf(row).toLowerCase()));
const invalidSkuRows = summaryRows.filter((row) => !skuCodeOf(row) || skuCodeOf(row) === "-");
const unknownCountryRows = summaryRows.filter((row) => countryOf(row) === "미상");
const uncategorizedRows = summaryRows.filter((row) => category1Of(row).includes("미분류") || category2Of(row).includes("미분류"));
const negativeAmountRows = summaryRows.filter((row) => amountOf(row) < 0);
const negativeQtyRows = summaryRows.filter((row) => qtyOf(row) < 0);
recordCheck("domain.required_dimensions", invalidBrandRows.length === 0 && invalidSkuRows.length === 0, {
  invalidBrandRows: invalidBrandRows.length,
  invalidSkuRows: invalidSkuRows.length,
  unknownCountryRows: unknownCountryRows.length,
  uncategorizedRows: uncategorizedRows.length
});
recordCheck("domain.negative_metrics", true, {
  negativeAmountRows: negativeAmountRows.length,
  negativeAmount: sum(negativeAmountRows, amountOf),
  negativeQtyRows: negativeQtyRows.length,
  negativeQty: sum(negativeQtyRows, qtyOf)
});
if (invalidBrandRows.length || invalidSkuRows.length) {
  recordFinding(
    "high",
    "missing_brand_or_sku",
    "브랜드 또는 SKU 식별자가 없는 판매행이 있습니다.",
    { invalidBrandRows: invalidBrandRows.length, invalidSkuRows: invalidSkuRows.length },
    "미분류 브랜드가 별도 순위로 노출되거나 SKU 수와 집중도가 왜곡될 수 있습니다.",
    "상품 마스터 보강 후 필수키 not-null 테스트를 추가하세요."
  );
}
if (unknownCountryRows.length || uncategorizedRows.length) {
  recordFinding(
    "medium",
    "unmapped_dimensions",
    "국가 또는 카테고리 매핑이 완전하지 않습니다.",
    {
      unknownCountryRows: unknownCountryRows.length,
      unknownCountryAmount: sum(unknownCountryRows, amountOf),
      uncategorizedRows: uncategorizedRows.length,
      uncategorizedAmount: sum(uncategorizedRows, amountOf)
    },
    "국가 분포와 제품군 구성비에 '미상/미분류'가 포함되어 Top 5와 점유율 해석이 달라질 수 있습니다.",
    "매핑률을 브랜드 탭에 함께 표시하고 미상/미분류 비중 임계치를 자동 점검하세요."
  );
}

const rawBrands = [...summaryByBrand.keys()];
const normalizedGroups = new Map();
const displayGroups = new Map();
for (const brand of rawBrands) {
  addSet(normalizedGroups, normalizeLabel(brand), brand);
  addSet(displayGroups, displayBrandName(brand), brand);
}
const normalizedCollisions = [...normalizedGroups.entries()].filter(([, brands]) => brands.size > 1).map(([normalized, brands]) => ({ normalized, brands: [...brands] }));
const displayCollisions = [...displayGroups.entries()].filter(([, brands]) => brands.size > 1).map(([display, brands]) => ({ display, brands: [...brands] }));
recordCheck("brand.label_normalization", normalizedCollisions.length === 0 && displayCollisions.length === 0, {
  normalizedCollisions,
  displayCollisions
});
if (normalizedCollisions.length || displayCollisions.length) {
  recordFinding(
    "high",
    "brand_label_collisions",
    "서로 다른 원본 브랜드명이 같은 정규화/표시명으로 합쳐집니다.",
    { normalizedCollisions, displayCollisions },
    "화면에는 같은 브랜드명이 여러 순위로 보이고 점유율·성장률·SKU 집중도가 분산될 수 있습니다.",
    "집계 전에 canonical brand id/name으로 통합하고 표시명 변환은 집계 이후에만 적용하세요."
  );
}

const totalBrandAmount = [...summaryByBrand.values()].reduce((total, row) => total + row.amount, 0);
const brandShareSum = totalBrandAmount === 0 ? 0 : [...summaryByBrand.values()].reduce((total, row) => total + (row.amount / totalBrandAmount) * 100, 0);
recordCheck("brand.share_sum", totalBrandAmount === 0 || close(brandShareSum, 100, 1e-8), { totalBrandAmount, brandShareSum });

const rowsByBrand = new Map();
for (const row of summaryRows) {
  const brand = brandOf(row);
  const rows = rowsByBrand.get(brand) ?? [];
  rows.push(row);
  rowsByBrand.set(brand, rows);
}

const skuConcentrationFailures = [];
let maxSkuConcentrationDifferencePp = 0;
const countryDistributionFailures = [];
const lineCompositionFailures = [];
for (const [brand, brandRows] of rowsByBrand) {
  const brandAmount = sum(brandRows, amountOf);
  const bySku = new Map();
  const byCountry = new Map();
  const byLine = new Map();
  for (const row of brandRows) {
    const sku = skuCodeOf(row);
    if (sku && sku !== "-") addNumber(bySku, sku, amountOf(row));
    addNumber(byCountry, countryOf(row), amountOf(row));
    addNumber(byLine, lineCategoryOf(row), amountOf(row));
  }
  const skuRows = [...bySku.entries()].sort((a, b) => b[1] - a[1]);
  const topFive = skuRows.slice(0, 5);
  const topFiveAmount = topFive.reduce((total, [, amount]) => total + amount, 0);
  const concentration = buildTopSkuConcentration(
    skuRows.map(([sku, amount]) => ({ sku, name: sku, category: "", amount, qty: 0 })),
    5,
    brandAmount
  );
  const displayedTopFiveSharePct = concentration.rows.reduce((total, row) => total + row.sharePct, 0);
  const expectedTopFiveSharePct = brandAmount > 0 ? (topFiveAmount / brandAmount) * 100 : 0;
  const differencePp = Math.abs(displayedTopFiveSharePct - expectedTopFiveSharePct);
  maxSkuConcentrationDifferencePp = Math.max(maxSkuConcentrationDifferencePp, differencePp);
  if (!close(concentration.totalAmount, brandAmount) || !close(displayedTopFiveSharePct, expectedTopFiveSharePct, 1e-8)) {
    skuConcentrationFailures.push({
      brand,
      skuCount: skuRows.length,
      brandAmount,
      topFiveAmount,
      expectedTopFiveSharePct,
      displayedTopFiveSharePct,
      differencePp
    });
  }

  const countryTotal = [...byCountry.values()].reduce((total, amount) => total + amount, 0);
  const lineTotal = [...byLine.values()].reduce((total, amount) => total + amount, 0);
  if (!close(countryTotal, brandAmount)) countryDistributionFailures.push({ brand, brandAmount, countryTotal });
  if (!close(lineTotal, brandAmount)) lineCompositionFailures.push({ brand, brandAmount, lineTotal });
}
skuConcentrationFailures.sort((a, b) => b.differencePp - a.differencePp);
recordCheck("brand.sku_concentration_denominator", skuConcentrationFailures.length === 0, {
  brandsChecked: rowsByBrand.size,
  affectedBrands: skuConcentrationFailures.length,
  maxDifferencePp: maxSkuConcentrationDifferencePp,
  samples: skuConcentrationFailures.slice(0, 10)
});
recordCheck("brand.country_distribution_denominator", countryDistributionFailures.length === 0, {
  failures: countryDistributionFailures.length,
  samples: countryDistributionFailures.slice(0, 5)
});
recordCheck("brand.line_composition_denominator", lineCompositionFailures.length === 0, {
  failures: lineCompositionFailures.length,
  samples: lineCompositionFailures.slice(0, 5)
});
if (skuConcentrationFailures.length) {
  recordFinding(
    "high",
    "sku_concentration_top5_denominator",
    "SKU 집중도가 브랜드 전체가 아니라 상위 5개 SKU 합계를 분모로 계산됩니다.",
    {
      affectedBrands: skuConcentrationFailures.length,
      affectedSharePct: (skuConcentrationFailures.length / rowsByBrand.size) * 100,
      worstExamples: skuConcentrationFailures.slice(0, 10)
    },
    "상위 5개 막대의 표시 비중이 항상 약 100%로 합산되어 실제 브랜드 내 집중도를 과대 표시합니다.",
    "분모를 selectedBrand.amount 또는 선택 브랜드의 전체 SKU 매출 합계로 변경하고 Top 1/Top 3/Top 5 합계 테스트를 추가하세요."
  );
}

const monthlyByBrandMonth = new Map();
for (const row of monthlyRows) {
  const brand = brandOf(row);
  const month = monthKeyOf(row);
  const key = `${brand}\u0000${month}`;
  addNumber(monthlyByBrandMonth, key, amountOf(row));
}
const growthProfile = { momPairs: [], yoyPairs: [] };
for (const [kind, targets, comparisonOf] of [
  ["momPairs", momTargets, previousMonthKey],
  ["yoyPairs", yoyTargets, previousYearMonthKey]
]) {
  for (const target of targets) {
    const comparison = comparisonOf(target);
    let comparableBrands = 0;
    let newBrands = 0;
    let lowBaseBrands = 0;
    for (const brand of allBrands) {
      const current = monthlyByBrandMonth.get(`${brand}\u0000${target}`) ?? 0;
      const previous = monthlyByBrandMonth.get(`${brand}\u0000${comparison}`) ?? 0;
      if (previous > 0) {
        comparableBrands += 1;
        if (previous < LOW_BASE_AMOUNT_EUR) lowBaseBrands += 1;
      } else if (current > 0) {
        newBrands += 1;
      }
    }
    growthProfile[kind].push({ target, comparison, comparableBrands, newBrands, lowBaseBrands });
  }
}
recordCheck("growth.pair_profile", true, growthProfile);

const monthYears = [...new Set(monthlyRows.map((row) => monthKeyOf(row).slice(0, 4)).filter((year) => /^\d{4}$/.test(year)))];
if (monthYears.length > 1) {
  const eligibleSeasonalityMonths = completeSeasonalityMonthKeys(coverageRows, monthlyRows.map(monthKeyOf));
  const completeCoverageCountByCalendarMonth = new Map();
  for (const monthKey of eligibleSeasonalityMonths) {
    const calendarMonth = Number(monthKey.slice(5, 7));
    addNumber(completeCoverageCountByCalendarMonth, calendarMonth, 1);
  }
  const seasonalityFailures = [];
  const legacyPeakDistortions = [];
  for (const brand of allBrands) {
    const brandRows = monthlyRows.filter((row) => brandOf(row) === brand);
    const profile = buildCalendarMonthAverageProfile({
      rows: brandRows,
      calendarMonths: Array.from({ length: 12 }, (_, index) => index + 1),
      eligibleMonthKeys: eligibleSeasonalityMonths,
      monthKey: monthKeyOf,
      amount: amountOf
    });
    const legacyAmountByCalendarMonth = new Map();
    const completeAmountByCalendarMonth = new Map();
    for (const row of brandRows) {
      const key = monthKeyOf(row);
      const calendarMonth = Number(key.slice(5, 7));
      if (!Number.isFinite(calendarMonth)) continue;
      addNumber(legacyAmountByCalendarMonth, calendarMonth, amountOf(row));
      if (eligibleSeasonalityMonths.has(key)) addNumber(completeAmountByCalendarMonth, calendarMonth, amountOf(row));
    }
    const expected = Array.from({ length: 12 }, (_, index) => {
      const month = index + 1;
      const coverage = completeCoverageCountByCalendarMonth.get(month) ?? 0;
      return { month, amount: coverage > 0 ? (completeAmountByCalendarMonth.get(month) ?? 0) / coverage : 0, observationCount: coverage };
    });
    const differences = profile.filter((point, index) =>
      point.observationCount !== expected[index].observationCount || !close(point.amount, expected[index].amount, 1e-8)
    );
    if (differences.length > 0) seasonalityFailures.push({ brand, differences });

    const legacyPeak = [...legacyAmountByCalendarMonth.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0])[0];
    const normalizedPeak = [...expected].sort((a, b) => b.amount - a.amount || a.month - b.month)[0];
    if (legacyPeak && normalizedPeak?.amount > 0 && legacyPeak[0] !== normalizedPeak.month) {
      legacyPeakDistortions.push({
        brand,
        previousPeakMonth: legacyPeak[0],
        previousPeakAmount: legacyPeak[1],
        correctedPeakMonth: normalizedPeak.month,
        correctedPeakAverageAmount: normalizedPeak.amount
      });
    }
  }
  recordCheck("brand.seasonality_complete_month_average", seasonalityFailures.length === 0, {
    years: monthYears,
    completeCoverageCountByCalendarMonth: Object.fromEntries([...completeCoverageCountByCalendarMonth.entries()].sort((a, b) => a[0] - b[0])),
    failures: seasonalityFailures.length,
    correctedLegacyPeakDistortions: legacyPeakDistortions.length,
    correctedSamples: legacyPeakDistortions.slice(0, 10),
    samples: seasonalityFailures.slice(0, 5)
  });
  if (seasonalityFailures.length > 0) {
    recordFinding(
      "high",
      "seasonality_average_mismatch",
      "완료월 달력월 연평균 시즌성 계산이 독립 재계산 결과와 다릅니다.",
      { failures: seasonalityFailures.length, samples: seasonalityFailures.slice(0, 5) },
      "최고월과 월별 비중이 잘못 표시될 수 있습니다.",
      "완료월 필터와 달력월별 관측 개수 분모를 다시 확인하세요."
    );
  }
}

const failedChecks = checks.filter((check) => !check.passed);
const severityOrder = { critical: 4, high: 3, medium: 2, low: 1 };
findings.sort((a, b) => severityOrder[b.severity] - severityOrder[a.severity] || a.id.localeCompare(b.id));
const blockingFindings = findings.filter((finding) => finding.severity === "critical" || finding.severity === "high");

const result = {
  status: blockingFindings.length ? "failed" : findings.length ? "passed_with_warnings" : "passed",
  generatedAt: new Date().toISOString(),
  source: {
    apiUrl: API_URL,
    analysisSchemaVersion: payload.analysis_schema_version,
    analysisOptions: payload.analysis_options,
    summaryRows: summaryRows.length,
    monthlyRows: monthlyRows.length,
    brandCount: summaryByBrand.size,
    monthCount: coverageRows.length,
    completeMonthCount: completeMonths.length
  },
  metrics: {
    summaryAmount,
    summaryQty,
    monthlyAmount,
    monthlyQty,
    totalBrandAmount,
    brandShareSum
  },
  checkSummary: {
    total: checks.length,
    passed: checks.length - failedChecks.length,
    failed: failedChecks.length
  },
  findingSummary: {
    total: findings.length,
    critical: findings.filter((finding) => finding.severity === "critical").length,
    high: findings.filter((finding) => finding.severity === "high").length,
    medium: findings.filter((finding) => finding.severity === "medium").length,
    low: findings.filter((finding) => finding.severity === "low").length
  },
  checks,
  findings
};

const serialized = `${JSON.stringify(result, null, 2)}\n`;
if (OUTPUT_PATH) await fs.writeFile(OUTPUT_PATH, serialized, "utf8");
process.stdout.write(serialized);

if (!ALLOW_FINDINGS && blockingFindings.length) process.exitCode = 1;
