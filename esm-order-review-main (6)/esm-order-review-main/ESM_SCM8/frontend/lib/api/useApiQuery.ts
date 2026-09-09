"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type ApiQueryOptions<T> = {
  query: () => Promise<T>;
  enabled?: boolean;
  initialData: T;
};

/** Shared lifecycle for client read requests without a global cache. */
export function useApiQuery<T>({
  query,
  enabled = true,
  initialData
}: ApiQueryOptions<T>) {
  const requestVersion = useRef(0);
  const [fallbackData] = useState(() => initialData);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [data, setData] = useState<T>(fallbackData);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(enabled);

  const refetch = useCallback(() => {
    setRefreshVersion((current) => current + 1);
  }, []);

  useEffect(() => {
    const version = ++requestVersion.current;
    if (!enabled) {
      setData(fallbackData);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    void query()
      .then((nextData) => {
        if (requestVersion.current === version) setData(nextData);
      })
      .catch((caught) => {
        if (requestVersion.current === version) {
          setData(fallbackData);
          setError(caught);
        }
      })
      .finally(() => {
        if (requestVersion.current === version) setLoading(false);
      });

    return () => {
      if (requestVersion.current === version) requestVersion.current += 1;
    };
  }, [enabled, fallbackData, query, refreshVersion]);

  return { data, error, hasError: error !== null, loading, refetch };
}
