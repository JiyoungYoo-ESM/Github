import { useCallback, useMemo } from "react";

import { getLatestOrderReviewMeta, getOrderReviewRows, useApiQuery } from "@/lib/api";

export function useOrderScreenData(analysisReady: boolean) {
  const { data, hasError: loadFailed } = useApiQuery({
    query: useCallback(
      () => getOrderReviewRows({ includeLatestFallback: false, requireCurrentSession: true }),
      []
    ),
    enabled: analysisReady,
    initialData: null
  });
  const latestRunMeta = useMemo(() => (data === null ? null : getLatestOrderReviewMeta()), [data]);

  return { rows: analysisReady ? data : [], latestRunMeta, loadFailed };
}
