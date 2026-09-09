"use client";

import { useEffect, useMemo, useState } from "react";

import {
  sourceRowsForCrossAxis,
  type CrossAxis,
  type CrossMetric,
  type CrossMomPeriod
} from "@/lib/cross-analysis-matrix";
import type { IngredientAnalysis, SeasonAnalysis } from "@/types/api";
import { completedYtdComparableYearWindow, monthsBetweenInclusive, previousMonthKey } from "../../lib/yoy-comparison";
import {
  buildCrossGrowthBasisLabel,
  buildCrossMonthCoverageModel,
  buildMomCoverageModel,
  resolveMomPeriodDefaults
} from "./crossAnalysisPeriodModel";

export function useCrossAnalysisPeriodState({
  axis,
  season,
  ingredient,
  analysisOptions,
  preferMom
}: {
  axis: CrossAxis;
  season: SeasonAnalysis | null;
  ingredient: IngredientAnalysis | null;
  analysisOptions: Record<string, unknown> | null;
  preferMom: boolean;
}) {
  const [metric, setMetric] = useState<CrossMetric>("yoy");
  const [momCurrentMonth, setMomCurrentMonth] = useState("");
  const [momComparisonMonth, setMomComparisonMonth] = useState("");
  const [yoyBaseMonth, setYoyBaseMonth] = useState(0);

  useEffect(() => {
    if (preferMom) setMetric("mom");
  }, [preferMom]);

  const {
    monthCoverageByKey,
    observedMonthSet,
    partialMonthSet,
    completeMonthKeys,
    momMonthOptions
  } = useMemo(
    () => buildCrossMonthCoverageModel({ axis, season, ingredient, analysisOptions }),
    [analysisOptions, axis, ingredient, season]
  );

  useEffect(() => {
    if (momMonthOptions.length === 0) return;
    const defaults = resolveMomPeriodDefaults({
      currentMonth: momCurrentMonth,
      monthOptions: momMonthOptions,
      completeMonths: completeMonthKeys
    });
    setMomCurrentMonth(defaults.currentMonth);
    setMomComparisonMonth(defaults.comparisonMonth);
  }, [completeMonthKeys, momMonthOptions, momCurrentMonth]);

  useEffect(() => {
    if (!momCurrentMonth) return;
    setMomComparisonMonth(previousMonthKey(momCurrentMonth));
  }, [momCurrentMonth]);

  const momPeriod = useMemo<CrossMomPeriod>(
    () => ({
      currentMonth: momCurrentMonth,
      comparisonMonth: momComparisonMonth,
      availableMonths: observedMonthSet,
      partialMonths: partialMonthSet,
      expectedMonths: new Set(momMonthOptions)
    }),
    [momComparisonMonth, momCurrentMonth, momMonthOptions, observedMonthSet, partialMonthSet]
  );
  const crossYoySourceRows = useMemo(
    () => sourceRowsForCrossAxis(axis, "yoy", season, ingredient),
    [axis, ingredient, season]
  );
  const crossYoyWindow = useMemo(
    () => completedYtdComparableYearWindow(
      crossYoySourceRows,
      completeMonthKeys.length > 0 ? new Set(completeMonthKeys) : undefined
    ),
    [completeMonthKeys, crossYoySourceRows]
  );
  const crossYoyMonthOptions = useMemo(
    () => Array.from(crossYoyWindow?.months ?? []).sort((left, right) => right - left),
    [crossYoyWindow]
  );

  useEffect(() => {
    if (crossYoyMonthOptions.length === 0) {
      setYoyBaseMonth(0);
      return;
    }
    setYoyBaseMonth((current) =>
      crossYoyMonthOptions.includes(current) ? current : crossYoyMonthOptions[0]
    );
  }, [crossYoyMonthOptions]);

  const yoyMonthRange = useMemo<[number, number] | null>(
    () => (yoyBaseMonth >= 1 ? [1, yoyBaseMonth] : null),
    [yoyBaseMonth]
  );
  const analysisMonthCount = monthsBetweenInclusive(
    String(analysisOptions?.start_date ?? ""),
    String(analysisOptions?.end_date ?? "")
  );
  const yoyDisabled = !crossYoyWindow;
  const momDisabled = momMonthOptions.length > 0
    ? momMonthOptions.length < 2
    : analysisMonthCount > 0 && analysisMonthCount < 2;
  const averageEurKrwRate = Number(analysisOptions?.average_eur_krw_rate) > 0
    ? Number(analysisOptions?.average_eur_krw_rate)
    : null;

  useEffect(() => {
    if (crossYoySourceRows.length === 0) return;
    if (yoyDisabled && metric === "yoy") setMetric("mom");
    if (momDisabled && metric === "mom") setMetric("sales");
  }, [crossYoySourceRows.length, metric, momDisabled, yoyDisabled]);

  const momCoverage = useMemo(
    () =>
      buildMomCoverageModel({
        metric,
        currentMonth: momCurrentMonth,
        comparisonMonth: momComparisonMonth,
        observedMonths: observedMonthSet,
        partialMonths: partialMonthSet,
        completeMonths: completeMonthKeys,
        coverageByMonth: monthCoverageByKey
      }),
    [
      completeMonthKeys,
      metric,
      momComparisonMonth,
      momCurrentMonth,
      monthCoverageByKey,
      observedMonthSet,
      partialMonthSet
    ]
  );
  const applyNearestAvailableMonths = () => {
    if (!momCoverage.currentMonthUsable && momCoverage.nearestCurrentMonth) {
      setMomCurrentMonth(momCoverage.nearestCurrentMonth);
    }
    if (!momCoverage.comparisonMonthUsable && momCoverage.nearestComparisonMonth) {
      setMomComparisonMonth(momCoverage.nearestComparisonMonth);
    }
  };
  const crossGrowthBasisLabel = useMemo(
    () =>
      buildCrossGrowthBasisLabel({
        metric,
        sourceRows: sourceRowsForCrossAxis(axis, metric, season, ingredient),
        momCurrentMonth,
        momComparisonMonth,
        yoyMonthRange
      }),
    [axis, ingredient, metric, momComparisonMonth, momCurrentMonth, season, yoyMonthRange]
  );

  return {
    metric,
    setMetric,
    momCurrentMonth,
    setMomCurrentMonth,
    momComparisonMonth,
    momPeriod,
    momMonthOptions,
    observedMonthSet,
    partialMonthSet,
    momPeriodReady: momCoverage.periodReady,
    momHasMissingMonth: momCoverage.hasMissingMonth,
    momHasPartialMonth: momCoverage.hasPartialMonth,
    momHasCoverageIssue: momCoverage.hasCoverageIssue,
    momCoverageWarningMessage: momCoverage.warningMessage,
    nearestUsableMonth: momCoverage.nearestUsableMonth,
    applyNearestAvailableMonths,
    crossYoyWindow,
    crossYoyMonthOptions,
    yoyBaseMonth,
    setYoyBaseMonth,
    yoyMonthRange,
    yoyDisabled,
    momDisabled,
    averageEurKrwRate,
    crossGrowthBasisLabel
  };
}
