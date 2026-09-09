import { useCallback } from "react";

import { getSeasonTrendAnalysis, useApiQuery } from "@/lib/api";

const EMPTY_ROWS: never[] = [];

export function useSkuScreenData() {
  const { data: result, hasError: loadFailed, loading } = useApiQuery({
    query: useCallback(() => getSeasonTrendAnalysis({ requireCurrentSession: true }), []),
    initialData: null
  });
  const season = result?.seasonAnalysis;

  return {
    rows: season?.countrySkuSummary ?? season?.countryTopSku ?? season?.topSku ?? EMPTY_ROWS,
    monthlyRows: season?.countrySkuMonthly ?? season?.skuMonthly ?? EMPTY_ROWS,
    monthCoverage: season?.monthCoverage ?? EMPTY_ROWS,
    analysisOptions: result?.analysisOptions ?? null,
    loading,
    loadFailed
  };
}
