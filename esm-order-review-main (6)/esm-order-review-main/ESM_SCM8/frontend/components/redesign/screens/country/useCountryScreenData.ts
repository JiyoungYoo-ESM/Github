import { useCallback, useEffect, useState } from "react";

import { getSeasonTrendAnalysis, useApiQuery } from "@/lib/api";
import type { ComparisonBasis } from "../../lib/types";
import { automaticComparisonBasis, comparisonBasisFromValue } from "../../lib/yoy-comparison";

const EMPTY_ROWS: never[] = [];

export function useCountryScreenData() {
  const { data: result, hasError: loadFailed, loading } = useApiQuery({
    query: useCallback(() => getSeasonTrendAnalysis({ requireCurrentSession: true }), []),
    initialData: null
  });
  const [comparisonBasis, setComparisonBasis] = useState<ComparisonBasis>("yoy");
  const analysisOptions = result?.analysisOptions ?? null;
  const season = result?.seasonAnalysis;
  const seasonRows = season?.countryCategory2Monthly?.length
    ? season.countryCategory2Monthly
    : season?.countryCategoryMonthly ?? season?.category1Monthly ?? EMPTY_ROWS;
  const completeSkuRows = season?.countrySkuSummary;
  const skuSummaryComplete = Boolean(completeSkuRows?.length);
  const skuSourceRows = completeSkuRows ?? season?.countryTopSku ?? season?.topSku ?? EMPTY_ROWS;
  const countryMonthCoverage = season?.monthCoverage ?? EMPTY_ROWS;

  useEffect(() => {
    if (!analysisOptions) return;
    setComparisonBasis(analysisOptions.comparison_basis
      ? comparisonBasisFromValue(analysisOptions.comparison_basis)
      : automaticComparisonBasis(String(analysisOptions.start_date ?? ""), String(analysisOptions.end_date ?? "")));
  }, [analysisOptions]);

  return {
    seasonRows, skuSourceRows, countryMonthCoverage, skuSummaryComplete,
    loading, loadFailed, comparisonBasis, setComparisonBasis, analysisOptions
  };
}
