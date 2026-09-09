import type { SeasonTrendAnalyzeResponse } from "@/types/api";
import { setAnalysisAmountCurrencyCode } from "@/lib/analysis-amount-currency";

const seasonKeyPairs = [
  ["category1Monthly", "category1_monthly"],
  ["category2Monthly", "category2_monthly"],
  ["category1Share", "category1_share"],
  ["category2Share", "category2_share"],
  ["ytdComparison", "ytd_comparison"],
  ["topSku", "top_sku"],
  ["skuMonthly", "sku_monthly"],
  ["mappingQuality", "mapping_quality"],
  ["uncategorizedSku", "uncategorized_sku"],
  ["countryCategoryMonthly", "country_category_monthly"],
  ["countryCategory2Monthly", "country_category2_monthly"],
  ["countryTopSku", "country_top_sku"],
  ["countrySkuSummary", "country_sku_summary"],
  ["countrySkuMonthly", "country_sku_monthly"],
  ["monthCoverage", "month_coverage"],
  ["countryCustomerSummary", "country_customer_summary"],
  ["countryCategoryCustomerSummary", "country_category_customer_summary"],
  ["customerSalesSummary", "customer_sales_summary"]
] as const;

const ingredientKeyPairs = [
  ["keywordMap", "keyword_map"],
  ["skuTags", "sku_tags"],
  ["monthlyTrend", "monthly_trend"],
  ["summary", "summary"],
  ["growth3m", "growth_3m"],
  ["ytdComparison", "ytd_comparison"],
  ["topSku", "top_sku"],
  ["topBrand", "top_brand"],
  ["unmatchedSku", "unmatched_sku"],
  ["coverage", "coverage"],
  ["countryCoverage", "country_coverage"],
  ["countryMonthlyTrend", "country_monthly_trend"],
  ["countrySummary", "country_summary"],
  ["countryGrowth3m", "country_growth_3m"],
  ["countryYtdComparison", "country_ytd_comparison"],
  ["countryTopSku", "country_top_sku"],
  ["countryTopBrand", "country_top_brand"]
] as const;

function arrayValue(source: Record<string, unknown>, camelKey: string, snakeKey: string) {
  const camel = source[camelKey];
  if (Array.isArray(camel)) return camel as Array<Record<string, unknown>>;
  const snake = source[snakeKey];
  return Array.isArray(snake) ? (snake as Array<Record<string, unknown>>) : [];
}

function stringArrayValue(source: Record<string, unknown>, camelKey: string, snakeKey: string) {
  const value = Array.isArray(source[camelKey]) ? source[camelKey] : source[snakeKey];
  return Array.isArray(value) ? value.map(String) : [];
}

export function normalizeSeasonTrendResponse(response: SeasonTrendAnalyzeResponse): SeasonTrendAnalyzeResponse {
  setAnalysisAmountCurrencyCode(response.analysis_options?.sales_amount_currency_code);
  const rawSeason = (response.season_analysis ?? {}) as unknown as Record<string, unknown>;
  const rawIngredient = (response.ingredient_analysis ?? {}) as unknown as Record<string, unknown>;
  return {
    ...response,
    season_analysis: {
      ...response.season_analysis,
      ...Object.fromEntries(seasonKeyPairs.map(([camel, snake]) => [camel, arrayValue(rawSeason, camel, snake)])),
      dataMonths: stringArrayValue(rawSeason, "dataMonths", "data_months")
    },
    ingredient_analysis: {
      ...response.ingredient_analysis,
      ...Object.fromEntries(ingredientKeyPairs.map(([camel, snake]) => [camel, arrayValue(rawIngredient, camel, snake)]))
    }
  };
}
