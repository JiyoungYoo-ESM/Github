"use client";

import { useCallback } from "react";

import { getSeasonTrendAnalysis, useApiQuery } from "@/lib/api";
import { monthsBetweenInclusive } from "../../lib/yoy-comparison";

export function useCrossAnalysisSource() {
  const { data: result, hasError: loadFailed, loading } = useApiQuery({
    query: useCallback(() => getSeasonTrendAnalysis({ requireCurrentSession: true }), []),
    initialData: null
  });
  const analysisOptions = result?.analysisOptions ?? null;
  const rangeMonths = monthsBetweenInclusive(
    String(analysisOptions?.start_date ?? ""),
    String(analysisOptions?.end_date ?? "")
  );

  return {
    season: result?.seasonAnalysis ?? null,
    ingredient: result?.ingredientAnalysis ?? null,
    analysisOptions,
    loading,
    loadFailed,
    preferMom: rangeMonths > 0 && rangeMonths < 12
  };
}
