import { useCallback, useEffect, useState } from "react";

import { getSeasonTrendAnalysis, useApiQuery } from "@/lib/api";
import type { ComparisonBasis } from "../../lib/types";
import { automaticComparisonBasis, comparisonBasisFromValue } from "../../lib/yoy-comparison";

const EMPTY_ROWS: never[] = [];

export function useBrandScreenData() {
  const { data: result, hasError: loadFailed, loading } = useApiQuery({
    query: useCallback(() => getSeasonTrendAnalysis({ requireCurrentSession: true }), []),
    initialData: null
  });
  const [comparisonBasis, setComparisonBasis] = useState<ComparisonBasis>("yoy");
  const analysisOptions = result?.analysisOptions ?? null;
  const season = result?.seasonAnalysis;
  const rows = season?.countrySkuSummary ?? season?.countryTopSku ?? season?.topSku ?? EMPTY_ROWS;
  const monthlyRows = season?.countrySkuMonthly ?? season?.skuMonthly ?? EMPTY_ROWS;
  const monthCoverage = season?.monthCoverage ?? EMPTY_ROWS;

  useEffect(() => {
    if (!analysisOptions) return;
    setComparisonBasis(analysisOptions.comparison_basis
      ? comparisonBasisFromValue(analysisOptions.comparison_basis)
      : automaticComparisonBasis(String(analysisOptions.start_date ?? ""), String(analysisOptions.end_date ?? "")));
  }, [analysisOptions]);

  return {
    rows, monthlyRows, monthCoverage, loading, loadFailed,
    comparisonBasis, setComparisonBasis, analysisOptions
  };
}
