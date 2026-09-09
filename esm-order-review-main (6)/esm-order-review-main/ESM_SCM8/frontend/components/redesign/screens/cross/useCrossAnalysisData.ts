"use client";

import { useMemo } from "react";

import type { CrossAxis } from "@/lib/cross-analysis-matrix";
import { allocateCrossMatrixShares } from "@/lib/cross-analysis-share";
import { ingredientCrossScopeNote } from "../../shared/ingredient-analysis";
import { buildYoyCoverageWarning } from "./crossAnalysisPeriodModel";
import { useCrossAnalysisPeriodState } from "./useCrossAnalysisPeriodState";
import { useCrossAnalysisSelection } from "./useCrossAnalysisSelection";
import { useCrossAnalysisSource } from "./useCrossAnalysisSource";

export function useCrossAnalysisData({
  axis,
  flipped
}: {
  axis: CrossAxis;
  flipped: boolean;
}) {
  const sourceState = useCrossAnalysisSource();
  const {
    season,
    ingredient,
    analysisOptions,
    loading,
    loadFailed,
    preferMom
  } = sourceState;
  const period = useCrossAnalysisPeriodState({
    axis,
    season,
    ingredient,
    analysisOptions,
    preferMom
  });
  const selectionState = useCrossAnalysisSelection({
    axis,
    metric: period.metric,
    season,
    ingredient,
    flipped,
    momPeriod: period.momPeriod,
    yoyMonthRange: period.yoyMonthRange
  });
  const { filterOptions, ...selection } = selectionState;

  const crossDataScopeWarning = axis.startsWith("ingredient-")
    ? ingredientCrossScopeNote(ingredient)
    : "";
  const yoyCoverageWarningMessage = buildYoyCoverageWarning(
    period.metric,
    filterOptions.cellStatuses
  );
  const crossShareAllocation = useMemo(
    () => allocateCrossMatrixShares(filterOptions.values, 1, filterOptions.shareTieBreakKeys),
    [filterOptions.shareTieBreakKeys, filterOptions.values]
  );

  return {
    source: {
      season,
      ingredient,
      analysisOptions,
      loading,
      loadFailed
    },
    period,
    selection,
    matrix: {
      filterOptions,
      crossDataScopeWarning,
      yoyCoverageWarningMessage,
      crossShareAllocation
    }
  };
}
