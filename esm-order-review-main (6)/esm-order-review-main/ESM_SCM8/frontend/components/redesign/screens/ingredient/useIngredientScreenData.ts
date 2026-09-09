import { useCallback, useEffect, useState } from "react";

import { getSeasonTrendAnalysis, useApiQuery } from "@/lib/api";
import type { ComparisonBasis } from "../../lib/types";
import { automaticComparisonBasis, comparisonBasisFromValue } from "../../lib/yoy-comparison";

export function useIngredientScreenData() {
  const { data: result, loading } = useApiQuery({
    query: useCallback(() => getSeasonTrendAnalysis({ requireCurrentSession: true }), []),
    initialData: null
  });
  const [comparisonBasis, setComparisonBasis] = useState<ComparisonBasis>("none");
  const analysisOptions = result?.analysisOptions ?? null;

  useEffect(() => {
    if (!analysisOptions) return;
    setComparisonBasis(analysisOptions.comparison_basis
      ? comparisonBasisFromValue(analysisOptions.comparison_basis)
      : automaticComparisonBasis(String(analysisOptions.start_date ?? ""), String(analysisOptions.end_date ?? "")));
  }, [analysisOptions]);

  return {
    ingredient: result?.ingredientAnalysis ?? null,
    monthCoverage: result?.seasonAnalysis?.monthCoverage ?? [],
    comparisonBasis,
    analysisOptions,
    loading
  };
}
