import { useCallback } from "react";

import { getStockGapItems, useApiQuery } from "@/lib/api";
import { computeStockGapItem } from "@/lib/stock-gap";

export function useGapScreenData(analysisReady: boolean) {
  const { data, hasError: loadFailed } = useApiQuery({
    query: useCallback(
      async () => (await getStockGapItems()).map((item) => computeStockGapItem(item)),
      []
    ),
    enabled: analysisReady,
    initialData: null
  });

  return { rows: analysisReady ? data : [], loadFailed };
}
