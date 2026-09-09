"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowUpDown, ChevronRight, Info, PanelRightClose, Search, X } from "lucide-react";
import {
  Area,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { chartColors, chartRgb, rgba } from "@/lib/chart-tokens";
import {
  amountOf,
  brandOf,
  buildCountrySummary,
  category1Of,
  category2Of,
  cleanCode,
  countryOf,
  field,
  hasKnownCountry,
  ingredientOf,
  monthLabel,
  numberValue,
  productNameOf,
  qtyOf,
  regionOfCountry,
  same,
  skuCodeOf,
  textValue,
  type CountrySummary,
  type SkuRow
} from "@/lib/global-demand-view-model";
import { cn, formatNumber } from "@/lib/utils";
import type { IngredientAnalysis, SeasonAnalysis, SeasonTrendAnalyzeResponse } from "@/types/api";
import { buildHeatmapRows, MONTHS, type HeatmapRow } from "./SeasonHeatmap";

type GlobalDemandTabProps = {
  season: SeasonAnalysis;
  ingredient: IngredientAnalysis;
  analysisOptions?: SeasonTrendAnalyzeResponse["analysis_options"];
};

const MIN_SEASON_CALENDAR_MONTHS = 12;

function parseDateValue(value?: string | null) {
  if (!value) return null;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function addMonths(date: Date, months: number) {
  const next = new Date(date);
  const day = next.getDate();
  next.setDate(1);
  next.setMonth(next.getMonth() + months);
  next.setDate(Math.min(day, new Date(next.getFullYear(), next.getMonth() + 1, 0).getDate()));
  return next;
}

function isSeasonCalendarAvailable(options?: SeasonTrendAnalyzeResponse["analysis_options"]) {
  const start = parseDateValue(options?.start_date);
  const end = parseDateValue(options?.end_date);
  if (!start || !end) return true;
  return end >= addMonths(start, MIN_SEASON_CALENDAR_MONTHS);
}

import {
  ALL,
  CALENDAR_EXCLUDED_CATEGORY1,
  CONTINENTS,
  DONUT_COLORS,
  BrandLensView,
  IngredientLensView,
  LensSegment,
  MonthlyLensView,
  ScopeChip,
  SkuLensView,
  brandCountOf,
  buildChartPoints,
  buildIngredientYoyMap,
  continentOfRegion,
  coverageFromRecord,
  emptyYoyMetric,
  encodeDetail,
  ingredientHelper,
  isUncategorizedIngredient,
  monthOfRow,
  parseDetail,
  skuCountOf,
  skuStockStatus,
  stockStatusOf,
  useQueryState,
  type BrandLensRow,
  type BrandSort,
  type CoverageStats,
  type DonutRow,
  type IngredientLensRow,
  type IngredientSort,
  type Lens,
  type SkuLensRow
} from "./GlobalDemandViews";

export function GlobalDemandTab({ season, ingredient, analysisOptions }: GlobalDemandTabProps) {
  const { get, setMany } = useQueryState();
  const queryContinentValue = get("continent") || ALL;
  const queryContinent = CONTINENTS.includes(queryContinentValue) ? queryContinentValue : ALL;
  const queryRegion = get("region") || ALL;
  const queryCountry = get("country");
  const queryCategory1 = get("cat1");
  const queryCategory2 = get("cat2");
  const lens = (["monthly", "ingredient", "brand", "sku"].includes(get("lens")) ? get("lens") : "ingredient") as Lens;
  const sort = (["qty", "share", "sku"].includes(get("sort")) ? get("sort") : "qty") as IngredientSort;
  const brandSort = (["qty", "share", "sku"].includes(get("brandSort")) ? get("brandSort") : "qty") as BrandSort;
  const skuQuery = get("skuQ");
  const skuBrand = get("skuBrand") || ALL;
  const skuCategory = get("skuCat") || ALL;
  const skuPage = Math.max(1, numberValue(get("skuPage")) || 1);
  const [calendarDrillLevel, setCalendarDrillLevel] = useState<"category1" | "category2">(
    get("drill") === "category2" || Boolean(queryCategory2) ? "category2" : "category1"
  );
  const drillLevel = queryCategory2 ? "category2" : calendarDrillLevel;
  const detail = parseDetail(get("detail"));
  const seasonCalendarAvailable = isSeasonCalendarAvailable(analysisOptions);

  const category1Rows = useMemo(() => season.countryCategoryMonthly ?? season.category1Monthly ?? [], [season]);
  const category2Rows = useMemo(() => season.countryCategory2Monthly ?? season.category2Monthly ?? [], [season]);
  const skuSourceRows = useMemo(() => season.countryTopSku ?? season.topSku ?? [], [season]);
  const skuSummaryRows = useMemo(() => season.countrySkuSummary ?? skuSourceRows, [season, skuSourceRows]);
  const skuMonthlyRows = useMemo(() => season.countrySkuMonthly ?? season.skuMonthly ?? [], [season]);
  const countrySummary = useMemo<CountrySummary[]>(() => buildCountrySummary(category1Rows), [category1Rows]);
  const regions = useMemo(() => {
    const availableRegions = Array.from(new Set(countrySummary.map((country) => country.region))).filter((region) => region !== "기타").sort();
    return [ALL, ...availableRegions.filter((region) => queryContinent === ALL || continentOfRegion(region) === queryContinent)];
  }, [countrySummary, queryContinent]);
  const effectiveRegion = regions.includes(queryRegion) ? queryRegion : ALL;
  const visibleCountries = useMemo(
    () =>
      countrySummary.filter((country) => {
        const continentOk = queryContinent === ALL || continentOfRegion(country.region) === queryContinent;
        const regionOk = effectiveRegion === ALL || country.region === effectiveRegion;
        return continentOk && regionOk;
      }),
    [countrySummary, effectiveRegion, queryContinent]
  );
  const countryOptions = useMemo(() => [ALL, ...visibleCountries.map((item) => item.country)], [visibleCountries]);
  const effectiveCountry = visibleCountries.some((item) => same(item.country, queryCountry)) ? queryCountry : "";
  const countryLabel = effectiveCountry || ALL;
  const isCountryInScope = useCallback((row: Record<string, unknown>) => {
    const country = countryOf(row);
    const region = regionOfCountry(country);
    const continentOk = queryContinent === ALL || continentOfRegion(region) === queryContinent;
    const regionOk = effectiveRegion === ALL || region === effectiveRegion;
    return hasKnownCountry(country) && (effectiveCountry ? same(country, effectiveCountry) : continentOk && regionOk);
  }, [effectiveCountry, effectiveRegion, queryContinent]);

  const countryScopedCategoryRows = useMemo(
    () =>
      category1Rows.filter((row) => {
        return isCountryInScope(row);
      }),
    [category1Rows, isCountryInScope]
  );
  const categoryHeatmapRows = useMemo(
    () =>
      buildHeatmapRows(countryScopedCategoryRows, {
        getCategory: category1Of,
        getValue: qtyOf
      }).sort((a, b) => a.peakMonth - b.peakMonth || b.rawTotal - a.rawTotal),
    [countryScopedCategoryRows]
  );
  const category2HeatmapRows = useMemo(
    () => {
      if (drillLevel !== "category2") return [];
      return (
      buildHeatmapRows(
        category2Rows.filter((row) => {
          return isCountryInScope(row) && (!queryCategory1 || same(category1Of(row), queryCategory1));
        }),
        {
          getCategory: category2Of,
          getValue: qtyOf
        }
      ).sort((a, b) => a.peakMonth - b.peakMonth || b.rawTotal - a.rawTotal)
      );
    },
    [category2Rows, drillLevel, isCountryInScope, queryCategory1]
  );

  const scopedMonthlyRows = useMemo(() => {
    const source = queryCategory2 ? category2Rows : category1Rows;
    return source.filter((row) => {
      const cat1Ok = !queryCategory1 || same(category1Of(row), queryCategory1);
      const cat2Ok = !queryCategory2 || same(category2Of(row), queryCategory2);
      return isCountryInScope(row) && cat1Ok && cat2Ok;
    });
  }, [category1Rows, category2Rows, isCountryInScope, queryCategory1, queryCategory2]);
  const monthlyValues = useMemo(() => {
    const values = Array(12).fill(0) as number[];
    scopedMonthlyRows.forEach((row) => {
      const month = monthOfRow(row);
      if (month >= 1 && month <= 12) values[month - 1] += qtyOf(row);
    });
    return values;
  }, [scopedMonthlyRows]);
  const chartPoints = useMemo(() => buildChartPoints(monthlyValues), [monthlyValues]);
  const totalQty = monthlyValues.reduce((sum, value) => sum + value, 0);
  const peakValueActual = Math.max(...monthlyValues, 0);
  const peakMonth = monthlyValues.findIndex((value) => value === peakValueActual) + 1 || 1;
  const peakValue = peakValueActual;

  const donutRows = useMemo<DonutRow[]>(() => {
    const shareRows = categoryHeatmapRows
      .filter((row) => !CALENDAR_EXCLUDED_CATEGORY1.has(row.category))
      .sort((a, b) => b.rawTotal - a.rawTotal);
    const total = shareRows.reduce((sum, row) => sum + row.rawTotal, 0);
    const top = shareRows.slice(0, 5);
    const etc = shareRows.slice(5).reduce((sum, row) => sum + row.rawTotal, 0);
    return [...top.map((row) => ({ name: row.category, value: row.rawTotal })), ...(etc > 0 ? [{ name: "그 외", value: etc }] : [])].map((row, index) => ({
      ...row,
      share: total > 0 ? (row.value / total) * 100 : 0,
      color: DONUT_COLORS[index] ?? chartColors.slatePale
    }));
  }, [categoryHeatmapRows]);

  const scopedSkuRows = useMemo<SkuRow[]>(() => {
    const buckets = new Map<string, SkuRow>();
    skuSourceRows.forEach((row) => {
      if (!isCountryInScope(row) || (queryCategory1 && !same(category1Of(row), queryCategory1)) || (queryCategory2 && !same(category2Of(row), queryCategory2))) return;
      const code = skuCodeOf(row);
      if (code === "-") return;
      const key = cleanCode(code);
      const current = buckets.get(key) ?? {
        code,
        name: productNameOf(row),
        brand: brandOf(row),
        category1: category1Of(row),
        category2: category2Of(row),
        qty: 0,
        amount: 0,
        stockStatus: stockStatusOf(row)
      };
      current.qty += qtyOf(row);
      current.amount += amountOf(row);
      current.stockStatus = current.stockStatus || stockStatusOf(row);
      buckets.set(key, current);
    });
    return Array.from(buckets.values()).sort((a, b) => b.qty - a.qty);
  }, [isCountryInScope, queryCategory1, queryCategory2, skuSourceRows]);

  const scopedSkuCount = useMemo(() => {
    const codes = new Set<string>();
    skuSummaryRows.forEach((row) => {
      if (!isCountryInScope(row) || (queryCategory1 && !same(category1Of(row), queryCategory1)) || (queryCategory2 && !same(category2Of(row), queryCategory2))) return;
      const code = cleanCode(skuCodeOf(row));
      if (code && code !== "-") codes.add(code);
    });
    return codes.size || scopedSkuRows.length;
  }, [isCountryInScope, queryCategory1, queryCategory2, scopedSkuRows.length, skuSummaryRows]);

  const skuLensRows = useMemo<SkuLensRow[]>(() => {
    const total = scopedSkuRows.reduce((sum, sku) => sum + sku.qty, 0);
    const byCode = new Map(scopedSkuRows.map((sku) => [cleanCode(sku.code), Array(12).fill(0) as number[]]));
    skuMonthlyRows.forEach((row) => {
      const code = cleanCode(skuCodeOf(row));
      const months = byCode.get(code);
      const month = monthOfRow(row);
      if (!months || month < 1 || month > 12) return;
      months[month - 1] += qtyOf(row);
    });
    return scopedSkuRows.map((sku, index) => {
      const months = byCode.get(cleanCode(sku.code)) ?? Array(12).fill(0);
      const peakValue = Math.max(...months, 0);
      return {
        ...sku,
        share: total > 0 ? (sku.qty / total) * 100 : 0,
        months,
        peakMonth: months.findIndex((value) => value === peakValue) + 1 || 1,
        stockStatus: skuStockStatus(sku, index + 1)
      };
    });
  }, [scopedSkuRows, skuMonthlyRows]);

  const brandRows = useMemo<BrandLensRow[]>(() => {
    const total = scopedSkuRows.reduce((sum, sku) => sum + sku.qty, 0);
    const buckets = new Map<string, { qty: number; amount: number; skus: Map<string, SkuRow>; categories: Map<string, number>; months: number[] }>();
    scopedSkuRows.forEach((sku) => {
      const current = buckets.get(sku.brand) ?? { qty: 0, amount: 0, skus: new Map(), categories: new Map(), months: Array(12).fill(0) as number[] };
      current.qty += sku.qty;
      current.amount += sku.amount;
      current.skus.set(cleanCode(sku.code), sku);
      current.categories.set(sku.category1, (current.categories.get(sku.category1) ?? 0) + sku.qty);
      buckets.set(sku.brand, current);
    });
    skuMonthlyRows.forEach((row) => {
      const code = cleanCode(skuCodeOf(row));
      const sku = scopedSkuRows.find((item) => cleanCode(item.code) === code);
      if (!sku) return;
      const current = buckets.get(sku.brand);
      const month = monthOfRow(row);
      if (!current || month < 1 || month > 12) return;
      current.months[month - 1] += qtyOf(row);
    });
    return Array.from(buckets.entries())
      .map(([brand, item]) => {
        const peakValue = Math.max(...item.months, 0);
        const topCategory = Array.from(item.categories.entries()).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "-";
        return {
          brand,
          qty: item.qty,
          amount: item.amount,
          skuCount: item.skus.size,
          share: total > 0 ? (item.qty / total) * 100 : 0,
          peakMonth: item.months.findIndex((value) => value === peakValue) + 1 || 1,
          topCategory,
          months: item.months,
          skus: Array.from(item.skus.values()).sort((a, b) => b.qty - a.qty)
        };
      })
      .sort((a, b) => b.qty - a.qty);
  }, [scopedSkuRows, skuMonthlyRows]);

  const ingredientMonthlyByName = useMemo(() => {
    const rows = ingredient.countryMonthlyTrend?.length ? ingredient.countryMonthlyTrend : ingredient.monthlyTrend;
    const buckets = new Map<string, number[]>();
    rows.forEach((row) => {
      if (ingredient.countryMonthlyTrend?.length && !isCountryInScope(row)) return;
      const name = ingredientOf(row);
      if (isUncategorizedIngredient(name)) return;
      const month = monthOfRow(row);
      if (month < 1 || month > 12) return;
      const values = buckets.get(name) ?? Array(12).fill(0);
      values[month - 1] += qtyOf(row);
      buckets.set(name, values);
    });
    return buckets;
  }, [ingredient.countryMonthlyTrend, ingredient.monthlyTrend, isCountryInScope]);

  const ingredientSkuCounts = useMemo(() => {
    const scopedCodes = new Set(scopedSkuRows.map((sku) => cleanCode(sku.code)));
    const buckets = new Map<string, Set<string>>();
    (ingredient.skuTags ?? []).forEach((row) => {
      const name = ingredientOf(row);
      const code = cleanCode(skuCodeOf(row));
      if (!name || !code || !scopedCodes.has(code)) return;
      const current = buckets.get(name) ?? new Set<string>();
      current.add(code);
      buckets.set(name, current);
    });
    return new Map(Array.from(buckets.entries()).map(([name, codes]) => [name, codes.size]));
  }, [ingredient.skuTags, scopedSkuRows]);

  const ingredientYoyByName = useMemo(() => {
    const rows = ingredient.countryMonthlyTrend?.length ? ingredient.countryMonthlyTrend : ingredient.monthlyTrend;
    const scopedRows = rows.filter((row) => (ingredient.countryMonthlyTrend?.length ? isCountryInScope(row) : true));
    return buildIngredientYoyMap(scopedRows);
  }, [ingredient.countryMonthlyTrend, ingredient.monthlyTrend, isCountryInScope]);

  const ingredientRows = useMemo<IngredientLensRow[]>(() => {
    const summaryRows = ingredient.countrySummary?.length ? ingredient.countrySummary : ingredient.summary;
    const source = summaryRows.filter((row) => {
      const countryOk = ingredient.countrySummary?.length ? isCountryInScope(row) : true;
      return countryOk && !isUncategorizedIngredient(ingredientOf(row));
    });
    const grouped = new Map<string, IngredientLensRow>();
    source.forEach((row) => {
      const name = ingredientOf(row);
      const months = ingredientMonthlyByName.get(name) ?? Array(12).fill(0);
      const peakValue = Math.max(...months, 0);
      const current =
        grouped.get(name) ??
        ({
          name,
          helper: ingredientHelper(name),
          qty: 0,
          amount: 0,
          skuCount: 0,
          brandCount: 0,
          months,
          peakMonth: months.findIndex((value) => value === peakValue) + 1 || 1,
          share: 0,
          yoy: ingredientYoyByName.get(name) ?? emptyYoyMetric
        } satisfies IngredientLensRow);
      current.qty += qtyOf(row);
      current.amount += amountOf(row);
      current.skuCount += skuCountOf(row);
      current.brandCount += brandCountOf(row);
      grouped.set(name, current);
    });
    const rawRows = Array.from(grouped.values()).map((row) => ({
      ...row,
      skuCount: ingredientSkuCounts.get(row.name) || row.skuCount,
      yoy: ingredientYoyByName.get(row.name) ?? row.yoy
    }));
    const total = rawRows.reduce((sum, row) => sum + row.qty, 0);
    return rawRows
      .map((row) => ({ ...row, share: total > 0 ? (row.qty / total) * 100 : 0 }))
      .sort((a, b) => {
        if (sort === "sku") return b.skuCount - a.skuCount || b.qty - a.qty;
        if (sort === "share") return b.share - a.share || b.qty - a.qty;
        return b.qty - a.qty;
      });
  }, [ingredient.countrySummary, ingredient.summary, ingredientMonthlyByName, ingredientSkuCounts, ingredientYoyByName, isCountryInScope, sort]);

  const coverage = useMemo<CoverageStats>(() => {
    const countryCoverageRows = ingredient.countryCoverage ?? [];
    const globalCoverage = coverageFromRecord(ingredient.coverage?.[0]);
    const matchingCountries = countryCoverageRows.filter((row) => {
      return isCountryInScope(row);
    });
    if (matchingCountries.length > 0) {
      const initialCoverage: CoverageStats = {
        totalSkuCount: 0,
        matchedSkuCount: 0,
        unmatchedSkuCount: 0,
        coveragePct: 0
      };
      const sum = matchingCountries.reduce<CoverageStats>(
        (acc, row) => {
          const item = coverageFromRecord(row);
          if (!item) return acc;
          acc.totalSkuCount += item.totalSkuCount;
          acc.matchedSkuCount += item.matchedSkuCount;
          acc.unmatchedSkuCount += item.unmatchedSkuCount;
          return acc;
        },
        initialCoverage
      );
      return {
        ...sum,
        coveragePct: sum.totalSkuCount > 0 ? (sum.matchedSkuCount / sum.totalSkuCount) * 100 : 0
      };
    }
    if (globalCoverage) return globalCoverage;
    const taggedCodes = new Set((ingredient.skuTags ?? []).map((row) => cleanCode(skuCodeOf(row))).filter(Boolean));
    const scopedCodes = new Set(scopedSkuRows.map((sku) => cleanCode(sku.code)));
    const matched = Array.from(scopedCodes).filter((code) => taggedCodes.has(code)).length;
    const total = scopedCodes.size;
    return {
      totalSkuCount: total,
      matchedSkuCount: matched,
      unmatchedSkuCount: Math.max(0, total - matched),
      coveragePct: total > 0 ? (matched / total) * 100 : 0
    };
  }, [ingredient.countryCoverage, ingredient.coverage, ingredient.skuTags, isCountryInScope, scopedSkuRows]);

  const topIngredient = ingredientRows[0];
  const heatmapRows = drillLevel === "category2" ? category2HeatmapRows : categoryHeatmapRows;
  const heatmapSelected = drillLevel === "category2" ? queryCategory2 : queryCategory1;
  const selectedIngredient = detail?.type === "ingredient" ? ingredientRows.find((row) => same(row.name, detail.id)) : undefined;
  const selectedBrand = detail?.type === "brand" ? brandRows.find((row) => same(row.brand, detail.id)) : undefined;
  const selectedSku = detail?.type === "sku" ? skuLensRows.find((row) => same(row.code, detail.id)) : undefined;
  const representativeSkus = useMemo(() => {
    if (!selectedIngredient) return [];
    const tagged = new Set(
      (ingredient.skuTags ?? [])
        .filter((row) => same(ingredientOf(row), selectedIngredient.name))
        .map((row) => cleanCode(skuCodeOf(row)))
    );
    return scopedSkuRows.filter((sku) => tagged.has(cleanCode(sku.code))).slice(0, 20);
  }, [ingredient.skuTags, scopedSkuRows, selectedIngredient]);

  const setCategory1 = (category: string) => {
    const next = category === ALL || same(category, queryCategory1) ? null : category;
    setMany({ cat1: next, cat2: null, drill: null, detail: null });
  };
  const setCategory2 = (category: string) => {
    const next = category === ALL || same(category, queryCategory2) ? null : category;
    setMany({ cat2: next, detail: null });
  };
  const setContinent = (continent: string) =>
    setMany({ continent: continent === ALL ? null : continent, region: null, country: null, cat1: null, cat2: null, drill: null, detail: null });
  const setRegion = (region: string) => setMany({ region: region === ALL ? null : region, country: null, cat1: null, cat2: null, drill: null, detail: null });
  const setCountry = (country: string) => setMany({ country: country === ALL ? null : country, cat1: null, cat2: null, drill: null, detail: null });
  const setLens = (nextLens: Lens) => setMany({ lens: nextLens === "ingredient" ? null : nextLens, detail: null });

  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-black text-slate-500">시즌 분석 · 국가 분석</p>
        <h2 className="mt-1 text-3xl font-black tracking-tight text-ink">국가별 수요 분석</h2>
      </div>

      <Card className="rounded-lg border-line bg-white shadow-sm">
        <CardContent className="flex flex-wrap items-center gap-2 p-3">
          <span className="mr-2 text-sm font-black text-slate-500">분석 범위</span>
          <ScopeChip label="대륙" value={queryContinent} options={CONTINENTS} onSelect={setContinent} />
          <ChevronRight className="h-4 w-4 text-slate-300" />
          <ScopeChip label="권역" value={effectiveRegion} options={regions} onSelect={setRegion} />
          <ChevronRight className="h-4 w-4 text-slate-300" />
          <ScopeChip label="국가" value={effectiveCountry || ALL} options={countryOptions} onSelect={setCountry} />
        </CardContent>
      </Card>

      <LensSegment lens={lens} onChange={setLens} />

      {lens === "ingredient" ? (
        <IngredientLensView
          country={countryLabel}
          rows={ingredientRows}
          sort={sort}
          coverage={coverage}
          selectedRow={selectedIngredient}
          representativeSkus={representativeSkus}
          onSort={(nextSort) => setMany({ sort: nextSort === "qty" ? null : nextSort })}
          onDetail={(name) => setMany({ detail: encodeDetail({ type: "ingredient", id: name }) })}
          onCloseDetail={() => setMany({ detail: null })}
        />
      ) : null}

      {lens === "monthly" ? (
        <MonthlyLensView
          country={countryLabel}
          category={queryCategory2 || queryCategory1}
          chartPoints={chartPoints}
          peakMonth={peakMonth}
          peakValue={peakValue}
          monthlyValues={monthlyValues}
          totalQty={totalQty}
          scopedSkuRows={scopedSkuRows}
          scopedSkuCount={scopedSkuCount}
          topIngredient={topIngredient}
          donutRows={donutRows}
          selectedCategory={queryCategory1}
          heatmapRows={heatmapRows}
          heatmapSelected={heatmapSelected}
          drillLevel={drillLevel}
          seasonCalendarAvailable={seasonCalendarAvailable}
          onCategory1={setCategory1}
          onCategory2={setCategory2}
          onDrillLevel={(level) => {
            setCalendarDrillLevel(level);
            if (level === "category1" && queryCategory2) {
              setMany({ cat2: null, detail: null });
            }
          }}
          onSkuDetail={(sku) => setMany({ detail: encodeDetail({ type: "sku", id: sku }) })}
        />
      ) : null}

      {lens === "brand" ? (
        <BrandLensView
          country={countryLabel}
          rows={brandRows}
          sort={brandSort}
          selectedRow={selectedBrand}
          onSort={(nextSort) => setMany({ brandSort: nextSort === "qty" ? null : nextSort })}
          onDetail={(brand) => setMany({ detail: encodeDetail({ type: "brand", id: brand }) })}
          onCloseDetail={() => setMany({ detail: null })}
        />
      ) : null}
      {lens === "sku" ? (
        <SkuLensView
          country={countryLabel}
          rows={skuLensRows}
          query={skuQuery}
          brand={skuBrand}
          category={skuCategory}
          page={skuPage}
          selectedRow={selectedSku}
          onQuery={(value) => setMany({ skuQ: value || null, skuPage: null })}
          onBrand={(value) => setMany({ skuBrand: value === ALL ? null : value, skuPage: null })}
          onCategory={(value) => setMany({ skuCat: value === ALL ? null : value, skuPage: null })}
          onPage={(value) => setMany({ skuPage: value <= 1 ? null : String(value) })}
          onDetail={(sku) => setMany({ detail: encodeDetail({ type: "sku", id: sku }) })}
          onCloseDetail={() => setMany({ detail: null })}
        />
      ) : null}
    </div>
  );
}

