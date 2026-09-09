"use client";

import { useEffect, useMemo, useState } from "react";

import {
  crossMatrixData,
  type CrossAxis,
  type CrossMetric,
  type CrossMomPeriod
} from "@/lib/cross-analysis-matrix";
import type { IngredientAnalysis, SeasonAnalysis } from "@/types/api";

// 행/열 각각 6개까지만 허용한다. 더 늘면 히트맵 헤더가 여러 줄로 접혀 표와 요약 카드 모두 읽기 어려워진다.
export const CROSS_SELECTION_LIMIT = 6;

export function useCrossAnalysisSelection({
  axis,
  metric,
  season,
  ingredient,
  flipped,
  momPeriod,
  yoyMonthRange
}: {
  axis: CrossAxis;
  metric: CrossMetric;
  season: SeasonAnalysis | null;
  ingredient: IngredientAnalysis | null;
  flipped: boolean;
  momPeriod: CrossMomPeriod;
  yoyMonthRange: [number, number] | null;
}) {
  const [selectedRows, setSelectedRows] = useState<string[]>([]);
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const displayedSelectedRows = flipped ? selectedColumns : selectedRows;
  const displayedSelectedColumns = flipped ? selectedRows : selectedColumns;

  useEffect(() => {
    setSelectedRows([]);
    setSelectedColumns([]);
  }, [axis]);

  const filterOptions = useMemo(
    () =>
      crossMatrixData(
        axis,
        metric,
        season,
        ingredient,
        displayedSelectedRows,
        displayedSelectedColumns,
        flipped,
        momPeriod,
        yoyMonthRange
      ),
    [
      axis,
      displayedSelectedColumns,
      displayedSelectedRows,
      flipped,
      ingredient,
      metric,
      momPeriod,
      season,
      yoyMonthRange
    ]
  );

  useEffect(() => {
    if (flipped) {
      const rowOptionSet = new Set(filterOptions.filteredRowOptions);
      const columnOptionSet = new Set(filterOptions.filteredColumnOptions);
      setSelectedColumns((current) => {
        const next = current.filter((item) => rowOptionSet.has(item));
        return next.length === current.length ? current : next;
      });
      setSelectedRows((current) => {
        const next = current.filter((item) => columnOptionSet.has(item));
        return next.length === current.length ? current : next;
      });
      return;
    }

    const rowOptionSet = new Set(filterOptions.filteredRowOptions);
    const columnOptionSet = new Set(filterOptions.filteredColumnOptions);
    setSelectedRows((current) => {
      const next = current.filter((item) => rowOptionSet.has(item));
      return next.length === current.length ? current : next;
    });
    setSelectedColumns((current) => {
      const next = current.filter((item) => columnOptionSet.has(item));
      return next.length === current.length ? current : next;
    });
  }, [filterOptions.filteredColumnOptions, filterOptions.filteredRowOptions, flipped]);

  const addSelectedRow = (value: string) => {
    if (!value) return;
    const setter = flipped ? setSelectedColumns : setSelectedRows;
    setter((current) => (current.includes(value) || current.length >= CROSS_SELECTION_LIMIT ? current : [...current, value]));
  };

  const addSelectedColumn = (value: string) => {
    if (!value) return;
    const setter = flipped ? setSelectedRows : setSelectedColumns;
    setter((current) => (current.includes(value) || current.length >= CROSS_SELECTION_LIMIT ? current : [...current, value]));
  };

  const removeSelectedRow = (item: string) => {
    const setter = flipped ? setSelectedColumns : setSelectedRows;
    setter((current) => current.filter((value) => value !== item));
  };

  const removeSelectedColumn = (item: string) => {
    const setter = flipped ? setSelectedRows : setSelectedColumns;
    setter((current) => current.filter((value) => value !== item));
  };

  const clearSelection = () => {
    setSelectedRows([]);
    setSelectedColumns([]);
  };

  return {
    filterOptions,
    displayedSelectedRows,
    displayedSelectedColumns,
    selectedRowCount: selectedRows.length,
    selectedColumnCount: selectedColumns.length,
    rowSelectionLimitReached: displayedSelectedRows.length >= CROSS_SELECTION_LIMIT,
    columnSelectionLimitReached: displayedSelectedColumns.length >= CROSS_SELECTION_LIMIT,
    rowSelectOptions: filterOptions.filteredRowOptions.filter(
      (option) => !displayedSelectedRows.includes(option)
    ),
    columnSelectOptions: filterOptions.filteredColumnOptions.filter(
      (option) => !displayedSelectedColumns.includes(option)
    ),
    selectedAxisLabel:
      filterOptions.rowLabel && filterOptions.columnLabel
        ? `${filterOptions.rowLabel} × ${filterOptions.columnLabel}`
        : "교차분석",
    addSelectedRow,
    addSelectedColumn,
    removeSelectedRow,
    removeSelectedColumn,
    clearSelection
  };
}
