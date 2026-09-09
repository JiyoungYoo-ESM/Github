"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { readFavoriteNavIds, writeFavoriteNavIds } from "@/lib/storage/repositories/favorite-nav";
import type { NavItem, Screen } from "../lib/types";

/** Keeps persisted navigation preferences out of the workspace screen orchestrator. */
export function useWorkspaceFavorites(allItems: NavItem[]) {
  const [favoriteNavIds, setFavoriteNavIds] = useState<Screen[]>([]);
  const loadedRef = useRef(false);

  useEffect(() => {
    const stored = readFavoriteNavIds(allItems.map((item) => item.id));
    if (stored) setFavoriteNavIds(stored);
    loadedRef.current = true;
  }, [allItems]);

  useEffect(() => {
    if (loadedRef.current) writeFavoriteNavIds(favoriteNavIds);
  }, [favoriteNavIds]);

  const favoriteNavItems = useMemo(
    () => favoriteNavIds
      .map((id) => allItems.find((item) => item.id === id))
      .filter((item): item is NavItem => Boolean(item)),
    [allItems, favoriteNavIds]
  );

  const toggleFavoriteNav = useCallback((id: Screen) => {
    setFavoriteNavIds((currentIds) => currentIds.includes(id)
      ? currentIds.filter((currentId) => currentId !== id)
      : [...currentIds, id]);
  }, []);

  return { favoriteNavIds, favoriteNavItems, toggleFavoriteNav };
}
