"use client";

import { useMemo } from "react";

import { allocateCrossMatrixShares } from "@/lib/cross-analysis-share";
import {
  crossMatrixData,
  type CrossAxis,
  type CrossMetric,
  type CrossMomPeriod,
  type CrossScale
} from "@/lib/cross-analysis-matrix";
import type { IngredientAnalysis, SeasonAnalysis } from "@/types/api";
import {
  buildCrossSummaryCards,
  type CrossSummaryCardData
} from "./crossAnalysisSummaryModel";

function SummaryCard({ label, value, sub }: CrossSummaryCardData) {
  return (
    <div className="rounded-[12px] border border-border bg-surface-soft px-4 py-[13px]">
      <p className="text-[11.5px] font-semibold text-muted2">{label}</p>
      <p className="mt-[7px] truncate text-[17px] font-black leading-none text-ink" title={value}>
        {value}
      </p>
      <p className="mt-[8px] line-clamp-2 text-[11px] font-bold text-muted2" title={sub}>
        {sub}
      </p>
    </div>
  );
}

export function CrossAnalysisSummaryStrip({
  axis,
  metric,
  scale,
  season,
  ingredient,
  selectedRows,
  selectedColumns,
  flipped,
  momPeriod,
  yoyMonthRange,
  eurKrwRate
}: {
  axis: CrossAxis;
  metric: CrossMetric;
  scale: CrossScale;
  season: SeasonAnalysis | null;
  ingredient: IngredientAnalysis | null;
  selectedRows: string[];
  selectedColumns: string[];
  flipped: boolean;
  momPeriod?: CrossMomPeriod;
  yoyMonthRange?: [number, number] | null;
  eurKrwRate?: number | null;
}) {
  const selected = useMemo(
    () => crossMatrixData(axis, metric, season, ingredient, selectedRows, selectedColumns, flipped, momPeriod, yoyMonthRange),
    [axis, metric, season, ingredient, selectedRows, selectedColumns, flipped, momPeriod, yoyMonthRange]
  );
  const shareAllocation = useMemo(
    () => allocateCrossMatrixShares(selected.values, 1, selected.shareTieBreakKeys),
    [selected.shareTieBreakKeys, selected.values]
  );

  const cards = useMemo(
    () =>
      buildCrossSummaryCards({
        selected,
        metric,
        scale,
        shareAllocation,
        eurKrwRate
      }),
    [selected, metric, scale, shareAllocation, eurKrwRate]
  );

  if (!cards) return null;

  return (
    <div className="grid grid-cols-2 gap-[10px] border-b border-divider px-[18px] py-[14px] lg:grid-cols-4">
      {cards.map((card) => (
        <SummaryCard key={card.label} label={card.label} value={card.value} sub={card.sub} />
      ))}
    </div>
  );
}
