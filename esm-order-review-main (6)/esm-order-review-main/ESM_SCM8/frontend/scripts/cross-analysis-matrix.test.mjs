import assert from "node:assert/strict";

import { allocateCrossMatrixShares } from "../lib/cross-analysis-share.ts";
import {
  buildCrossMatrix,
  crossDimensionValue,
  crossMatrixData,
  sourceRowsForCrossAxis
} from "../lib/cross-analysis-matrix.ts";

const AXES = {
  "country-brand": ["country", "brand"],
  "country-sku": ["country", "sku"],
  "brand-sku": ["brand", "sku"],
  "ingredient-country": ["ingredient", "country"],
  "ingredient-brand": ["ingredient", "brand"],
  "ingredient-sku": ["ingredient", "sku"]
};
const countries = ["France", "Germany", "United Kingdom"];
const brands = ["Audit Brand A", "Audit Brand B", "Audit Brand C"];
const skus = ["SKU-A", "SKU-B", "SKU-C"];
const skuNames = ["Same Product", "Same Product", "Different Product"];
const ingredients = ["Audit Ingredient A", "Audit Ingredient B", "Audit Ingredient C"];
const months = Array.from({ length: 24 }, (_, index) => ({ year: 2025 + Math.floor(index / 12), month: (index % 12) + 1 }));
const monthKeys = months.map(({ year, month }) => `${year}-${String(month).padStart(2, "0")}`);

function row({ country, brand, sku, ingredient, year, month, amount, qty }) {
  const skuIndex = Math.max(0, skus.indexOf(sku));
  return {
    country,
    brand,
    prod_cd: sku,
    prod_nm: skuNames[skuIndex],
    ingredient,
    year,
    month,
    amount,
    qty
  };
}

const countrySkuMonthly = months.flatMap(({ year, month }) =>
  countries.flatMap((country, countryIndex) =>
    brands.flatMap((brand, brandIndex) =>
      skus.map((sku, skuIndex) => {
        const base = 1_000 + countryIndex * 170 + brandIndex * 90 + skuIndex * 40;
        const multiplier = year === 2026 ? 1.18 + month * 0.003 : 1;
        return row({
          country,
          brand,
          sku,
          ingredient: ingredients[(countryIndex + brandIndex + skuIndex) % ingredients.length],
          year,
          month,
          amount: Number((base * multiplier).toFixed(2)),
          qty: base * 10 + month
        });
      })
    )
  )
);

function summarize(rows, keys) {
  const grouped = new Map();
  for (const source of rows) {
    const key = keys.map((field) => source[field]).join("\u0000");
    const current = grouped.get(key) ?? Object.fromEntries(keys.map((field) => [field, source[field]]));
    current.amount = (current.amount ?? 0) + source.amount;
    current.qty = (current.qty ?? 0) + source.qty;
    current.prod_nm = source.prod_nm;
    grouped.set(key, current);
  }
  return Array.from(grouped.values());
}

const countrySkuSummary = summarize(countrySkuMonthly, ["country", "brand", "prod_cd"]);

function ingredientMonthly(dimension) {
  const values = dimension === "country" ? countries : dimension === "brand" ? brands : skus;
  return months.flatMap(({ year, month }) =>
    ingredients.flatMap((ingredient, ingredientIndex) =>
      values.map((value, valueIndex) => {
        const base = 900 + ingredientIndex * 210 + valueIndex * 80;
        return row({
          country: dimension === "country" ? value : countries[valueIndex],
          brand: dimension === "brand" ? value : brands[valueIndex],
          sku: dimension === "sku" ? value : skus[valueIndex],
          ingredient,
          year,
          month,
          amount: Number((base * (year === 2026 ? 1.12 + month * 0.005 : 1)).toFixed(2)),
          qty: base * 9 + month
        });
      })
    )
  );
}

const countryMonthlyTrend = ingredientMonthly("country");
const brandMonthlyTrend = ingredientMonthly("brand");
const skuMonthlyTrend = ingredientMonthly("sku");
const season = {
  countrySkuSummary,
  countrySkuMonthly,
  countryTopSku: countrySkuSummary.slice(0, 2),
  topSku: countrySkuSummary.slice(0, 2)
};
const ingredient = {
  countryMonthlyTrend,
  countrySummary: summarize(countryMonthlyTrend, ["ingredient", "country"]),
  brandMonthlyTrend,
  skuMonthlyTrend,
  topBrand: summarize(brandMonthlyTrend, ["ingredient", "brand"]).slice(0, 2),
  topSku: summarize(skuMonthlyTrend, ["ingredient", "prod_cd"]).slice(0, 2),
  skuTags: []
};

function nonEmptySubsets(values) {
  return Array.from({ length: 2 ** values.length - 1 }, (_, maskIndex) => {
    const mask = maskIndex + 1;
    return values.filter((_, index) => mask & (1 << index));
  });
}

function transpose(matrix) {
  return matrix[0]?.map((_, columnIndex) => matrix.map((rowValues) => rowValues[columnIndex])) ?? [];
}

function matrixTotal(matrix) {
  return matrix.flat().reduce((sum, value) => sum + (typeof value === "number" && Number.isFinite(value) ? value : 0), 0);
}

function transposeStatus(matrix) {
  return transpose(matrix);
}

function assertClose(actual, expected, message) {
  assert.ok(Math.abs(actual - expected) < 1e-8, `${message}: ${actual} !== ${expected}`);
}

const fullPeriod = {
  currentMonth: "2026-12",
  comparisonMonth: "2026-11",
  availableMonths: new Set(monthKeys),
  partialMonths: new Set(),
  expectedMonths: new Set(monthKeys)
};

assert.deepEqual(
  sourceRowsForCrossAxis("ingredient-brand", "sales", null, { topBrand: [{ ingredient: "I", brand: "B", amount: 1 }] }),
  [],
  "상위 10개 랭킹 테이블을 전체 교차 원천으로 대체하면 안 됩니다."
);
assert.deepEqual(
  sourceRowsForCrossAxis("country-sku", "mom", { countryTopSku: [{ country: "C", prod_cd: "S", amount: 1 }] }, null),
  [],
  "월 정보가 없는 상위 SKU 테이블을 성장률 원천으로 사용하면 안 됩니다."
);

let staticViews = 0;
for (const axis of Object.keys(AXES)) {
  for (const metric of ["sales", "quantity"]) {
    const optionMatrix = crossMatrixData(axis, metric, season, ingredient, [], [], false, fullPeriod);
    assert.equal(optionMatrix.rowOptions.length, 3, `${axis}/${metric}: 모든 행 차원이 노출되어야 합니다.`);
    assert.equal(optionMatrix.columnOptions.length, 3, `${axis}/${metric}: 모든 열 차원이 노출되어야 합니다.`);
    if (axis.endsWith("sku")) {
      assert.equal(new Set(optionMatrix.columnOptions).size, 3, `${axis}: 상품명이 같은 서로 다른 SKU가 합쳐졌습니다.`);
      assert.ok(optionMatrix.columnOptions.some((label) => label.includes("SKU-A")));
      assert.ok(optionMatrix.columnOptions.some((label) => label.includes("SKU-B")));
    }

    for (const selectedRows of nonEmptySubsets(optionMatrix.rowOptions)) {
      for (const selectedColumns of nonEmptySubsets(optionMatrix.columnOptions)) {
        const normal = crossMatrixData(axis, metric, season, ingredient, selectedRows, selectedColumns, false, fullPeriod);
        const flipped = crossMatrixData(axis, metric, season, ingredient, selectedColumns, selectedRows, true, fullPeriod);
        assert.deepEqual(flipped.values, transpose(normal.values), `${axis}/${metric}: 금액 행·열 전치 불일치`);
        assert.deepEqual(flipped.cellPresence, transpose(normal.cellPresence), `${axis}/${metric}: 원천 조합 존재 행·열 전치 불일치`);
        assertClose(matrixTotal(flipped.values), matrixTotal(normal.values), `${axis}/${metric}: 전치 후 합계 불일치`);

        const normalShare = allocateCrossMatrixShares(normal.values, 1, normal.shareTieBreakKeys);
        const flippedShare = allocateCrossMatrixShares(flipped.values, 1, flipped.shareTieBreakKeys);
        assert.equal(Number(matrixTotal(normalShare.values).toFixed(1)), 100, `${axis}/${metric}: 비중 합이 100%가 아님`);
        assert.deepEqual(flippedShare.values, transpose(normalShare.values), `${axis}/${metric}: 비중 행·열 전치 불일치`);
        assert.deepEqual(flippedShare.rowTotals, normalShare.values[0].map((_, index) => Number(normalShare.values.reduce((sum, values) => sum + values[index], 0).toFixed(1))));

        // 화면, 즉시 PDF, 담기 보고서는 같은 matrix와 같은 tie key로 계산하므로 결과가 같아야 한다.
        assert.deepEqual(allocateCrossMatrixShares(normal.values, 1, normal.shareTieBreakKeys), normalShare);
        assert.deepEqual(allocateCrossMatrixShares(normal.values, 1, normal.shareTieBreakKeys), normalShare);
        staticViews += 4; // 금액/비중 × normal/flipped
      }
    }
  }
}

function monthAmountMap(sourceRows, rowDimension, columnDimension) {
  const totals = new Map();
  for (const source of sourceRows) {
    const monthKey = `${source.year}-${String(source.month).padStart(2, "0")}`;
    const key = `${crossDimensionValue(source, rowDimension)}\u0000${crossDimensionValue(source, columnDimension)}\u0000${monthKey}`;
    totals.set(key, (totals.get(key) ?? 0) + source.amount / 1_000);
  }
  return totals;
}

function expectedCellGrowth(totals, rowLabel, columnLabel, currentMonth, comparisonMonth) {
  const current = totals.get(`${rowLabel}\u0000${columnLabel}\u0000${currentMonth}`) ?? 0;
  const comparison = totals.get(`${rowLabel}\u0000${columnLabel}\u0000${comparisonMonth}`) ?? 0;
  return comparison <= 0.5 ? null : Math.round(((current - comparison) / comparison) * 100);
}

let monthPairViews = 0;
const orderedMonthPairs = monthKeys.flatMap((currentMonth) =>
  monthKeys.filter((comparisonMonth) => comparisonMonth !== currentMonth).map((comparisonMonth) => ({ currentMonth, comparisonMonth }))
);
assert.equal(orderedMonthPairs.length, 24 * 23);

for (const axis of Object.keys(AXES)) {
  const [rowDimension, columnDimension] = AXES[axis];
  const options = crossMatrixData(axis, "mom", season, ingredient, [], [], false, fullPeriod);
  const sourceRows = sourceRowsForCrossAxis(axis, "mom", season, ingredient);
  const sourceMonthAmounts = monthAmountMap(sourceRows, rowDimension, columnDimension);
  for (const { currentMonth, comparisonMonth } of orderedMonthPairs) {
    const period = { ...fullPeriod, currentMonth, comparisonMonth };
    const normal = crossMatrixData(axis, "mom", season, ingredient, options.rowOptions, options.columnOptions, false, period);
    const flipped = crossMatrixData(axis, "mom", season, ingredient, options.columnOptions, options.rowOptions, true, period);
    assert.deepEqual(flipped.values, transpose(normal.values), `${axis}/${currentMonth}/${comparisonMonth}: MoM 전치 불일치`);
    assert.deepEqual(transposeStatus(flipped.cellStatuses), normal.cellStatuses, `${axis}/${currentMonth}/${comparisonMonth}: MoM 상태 전치 불일치`);
    normal.rows.forEach((rowLabel, rowIndex) => {
      normal.columns.forEach((columnLabel, columnIndex) => {
        assert.equal(
          normal.values[rowIndex][columnIndex],
          expectedCellGrowth(sourceMonthAmounts, rowLabel, columnLabel, currentMonth, comparisonMonth),
          `${axis}/${rowLabel}/${columnLabel}/${currentMonth}/${comparisonMonth}: MoM 공식 불일치`
        );
      });
    });
    monthPairViews += 2;
  }
}

let yoyViews = 0;
for (const axis of Object.keys(AXES)) {
  const options = crossMatrixData(axis, "yoy", season, ingredient, [], [], false, fullPeriod);
  const normal = crossMatrixData(axis, "yoy", season, ingredient, options.rowOptions, options.columnOptions, false, fullPeriod);
  const flipped = crossMatrixData(axis, "yoy", season, ingredient, options.columnOptions, options.rowOptions, true, fullPeriod);
  assert.deepEqual(flipped.values, transpose(normal.values), `${axis}: YoY 전치 불일치`);
  assert.deepEqual(transposeStatus(flipped.cellStatuses), normal.cellStatuses, `${axis}: YoY 상태 전치 불일치`);

  // 합계 성장률은 셀 성장률 평균이 아니라 원금액 합산 후 계산되어야 한다.
  const [rowDimension, columnDimension] = AXES[axis];
  const sourceRows = sourceRowsForCrossAxis(axis, "yoy", season, ingredient);
  normal.rows.forEach((rowLabel, rowIndex) => {
    let current = 0;
    let comparison = 0;
    for (const columnLabel of normal.columns) {
      for (const source of sourceRows) {
        if (crossDimensionValue(source, rowDimension) !== rowLabel || crossDimensionValue(source, columnDimension) !== columnLabel) continue;
        if (source.year === 2026) current += source.amount / 1_000;
        if (source.year === 2025) comparison += source.amount / 1_000;
      }
    }
    assert.equal(normal.growthRowTotals[rowIndex], Math.round(((current - comparison) / comparison) * 100));
  });
  yoyViews += 2;
}

// 월 YoY는 선택한 기준월과 전년도 동일 월만 집계한다.
const decemberYoy = crossMatrixData(
  "country-brand",
  "yoy",
  season,
  ingredient,
  countries,
  brands,
  false,
  fullPeriod,
  [12, 12]
);
const decemberSourceAmounts = monthAmountMap(countrySkuMonthly, "country", "brand");
decemberYoy.rows.forEach((rowLabel, rowIndex) => {
  decemberYoy.columns.forEach((columnLabel, columnIndex) => {
    assert.equal(
      decemberYoy.values[rowIndex][columnIndex],
      expectedCellGrowth(decemberSourceAmounts, rowLabel, columnLabel, "2026-12", "2025-12"),
      `${rowLabel}/${columnLabel}: 월 YoY는 전년도 동일 월만 비교해야 합니다.`
    );
  });
});

// 최신 연도의 바로 전년이 없으면 더 오래된 연도로 건너뛰어 YoY를 계산하지 않는다.
const gapCountrySkuMonthly = countrySkuMonthly.map((source) => ({
  ...source,
  year: source.year === 2026 ? 2027 : source.year
}));
const gapMonthKeys = monthKeys.map((month) => month.replace(/^2026-/, "2027-"));
const gapPeriod = {
  ...fullPeriod,
  availableMonths: new Set(gapMonthKeys),
  expectedMonths: new Set(gapMonthKeys)
};
const gapSeason = {
  ...season,
  countrySkuMonthly: gapCountrySkuMonthly,
  countrySkuSummary: summarize(gapCountrySkuMonthly, ["country", "brand", "prod_cd"])
};
const gapYoyOptions = crossMatrixData("country-brand", "yoy", gapSeason, ingredient, [], [], false, gapPeriod, [12, 12]);
const gapYoy = crossMatrixData(
  "country-brand",
  "yoy",
  gapSeason,
  ingredient,
  gapYoyOptions.rowOptions,
  gapYoyOptions.columnOptions,
  false,
  gapPeriod,
  [12, 12]
);
assert.ok(gapYoy.values.flat().every((value) => value === null), "연속되지 않은 연도를 YoY로 비교하면 안 됩니다.");
assert.ok(gapYoy.cellStatuses.flat().every((status) => status === "current_month_missing"));

// 동일월 방어, 누락/부분 월의 YoY 차단, 음수 반품의 순매출 반영을 고정한다.
const samePeriod = { ...fullPeriod, currentMonth: "2026-06", comparisonMonth: "2026-06" };
const sameOptions = crossMatrixData("country-brand", "mom", season, ingredient, [], [], false, samePeriod);
const sameMatrix = crossMatrixData("country-brand", "mom", season, ingredient, sameOptions.rowOptions, sameOptions.columnOptions, false, samePeriod);
assert.ok(sameMatrix.cellStatuses.flat().every((status) => status === "same_period"));
assert.ok(sameMatrix.values.flat().every((value) => value === null));

const missingYoyPeriod = { ...fullPeriod, availableMonths: new Set(monthKeys.filter((month) => month !== "2026-05")) };
const missingYoy = crossMatrixData("country-brand", "yoy", season, ingredient, countries, brands, false, missingYoyPeriod);
assert.ok(missingYoy.cellStatuses.flat().every((status) => status === "current_month_missing"));
const partialYoyPeriod = { ...fullPeriod, partialMonths: new Set(["2025-07"]) };
const partialYoy = crossMatrixData("country-brand", "yoy", season, ingredient, countries, brands, false, partialYoyPeriod);
assert.ok(partialYoy.cellStatuses.flat().every((status) => status === "comparison_month_partial"));

const netSales = buildCrossMatrix(
  [
    { country: "France", brand: "Returns", amount: 1_000, qty: 100 },
    { country: "France", brand: "Returns", amount: -200, qty: -20 }
  ],
  "country",
  "brand",
  "sales",
  "국가",
  "브랜드",
  ["France"],
  ["Returns"]
);
assert.equal(netSales.values[0][0], 0.8);

console.log(
  `Cross-analysis production matrix checks passed (${staticViews} static views, ${monthPairViews} ordered month-pair views, ${yoyViews} YoY views).`
);
