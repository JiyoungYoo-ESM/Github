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
import { cn } from "@/lib/utils";
import type { IngredientAnalysis, SeasonAnalysis } from "@/types/api";
import { krwEokFromEur, formatCrossAmountK } from "../../lib/currency-format";
import { ingredientCrossScopeNote } from "../../shared/ingredient-analysis";
import { GROWTH_DISPLAY_CAP } from "../../lib/yoy-comparison";
import { lowBaseAmountLabel } from "@/lib/low-base";
import type { CrossMomStatus } from "@/lib/cross-analysis-mom";
import { formatCrossCellKrw, formatCrossCellValue, isCrossGrowthMetric } from "./crossAnalysisCellFormat";

function CrossHeatCell({
  value,
  status,
  max,
  metric,
  scale,
  eurKrwRate,
  shareUnavailable = false
}: {
  value: number | null;
  status?: CrossMomStatus | null;
  max: number;
  metric: CrossMetric;
  scale: CrossScale;
  eurKrwRate?: number | null;
  shareUnavailable?: boolean;
}) {
  const isGrowth = isCrossGrowthMetric(metric);
  if (value === null) {
    const emptyTitle =
      status === "current_month_missing"
        ? "기준 기간 데이터가 없어 성장률을 계산할 수 없습니다."
        : status === "comparison_month_missing"
          ? "비교 기간 데이터가 없어 성장률을 계산할 수 없습니다."
          : status === "same_period"
            ? "기준 기간과 비교 기간이 같아 성장률을 계산할 수 없습니다."
          : status === "current_month_partial"
            ? "기준 기간 데이터가 부분 적재된 것으로 보여 성장률을 계산하지 않습니다."
            : status === "comparison_month_partial"
              ? "비교 기간 데이터가 부분 적재된 것으로 보여 성장률을 계산하지 않습니다."
          : status === "zero_base"
            ? "비교월 실적이 0이라 성장률을 계산할 수 없습니다."
            : status === "low_base"
              ? `비교월 실적이 최소 기준(${lowBaseAmountLabel()}) 미만입니다.`
              : isGrowth
                ? "비교 기준 데이터가 없어 성장률을 계산할 수 없습니다."
                : shareUnavailable
                  ? "선택 범위 합계가 0이어서 비중을 계산할 수 없습니다."
                  : undefined;
    return (
      <td
        className="h-[38px] border-b border-white bg-surface-soft px-[10px] text-right text-[12.5px] font-black text-muted2"
        title={emptyTitle}
      >
        -
      </td>
    );
  }
  // 성장률 셀은 색상 강도를 캡 기준으로 계산해, 극단값 한 셀이 나머지 셀 색을 씻어내지 않게 한다.
  const intensity = isGrowth ? Math.min(Math.abs(value), GROWTH_DISPLAY_CAP) : Math.abs(value);
  const ratio = max > 0 ? Math.min(intensity / max, 1) : 0;
  const backgroundColor = isGrowth
    ? value < 0
      ? `rgba(230, 0, 45, ${0.12 + ratio * 0.48})`
      : `rgba(22, 163, 74, ${0.1 + ratio * 0.5})`
    : `rgba(230, 0, 45, ${0.08 + ratio * 0.58})`;
  const color = ratio > 0.72 ? "white" : value < 0 && isGrowth ? "rgb(230, 0, 45)" : isGrowth ? "rgb(0, 145, 73)" : "black";
  const display = formatCrossCellValue(value, metric, scale);
  const krwDisplay = formatCrossCellKrw(value, metric, scale, eurKrwRate);

  return (
    <td
      className={cn("border-b border-white px-[10px] text-right text-[12.5px] font-black", krwDisplay ? "h-[52px] py-[7px]" : "h-[38px]")}
      style={{ backgroundColor, color }}
    >
      <span className="block">{display}</span>
      {krwDisplay ? <span className="mt-[2px] block text-[11px] font-black opacity-80">{krwDisplay}</span> : null}
    </td>
  );
}

function CrossHeatmapCard({
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
  const values = selected.values;
  const isGrowthMetric = isCrossGrowthMetric(metric);
  const shareAllocation = useMemo(
    () => allocateCrossMatrixShares(values, 1, selected.shareTieBreakKeys),
    [selected.shareTieBreakKeys, values]
  );
  const numericValues = values.flat().filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  // 성장률 색상 스케일은 캡 기준으로 정규화해 극단 셀 하나가 전체 색을 지배하지 않게 한다.
  const max = numericValues.length > 0 ? Math.max(...numericValues.map((value) => (isGrowthMetric ? Math.min(Math.abs(value), GROWTH_DISPLAY_CAP) : Math.abs(value)))) : 0;
  const rowTotals = values.map((row, rowIndex) => {
    const numericRow = row.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
    if (isGrowthMetric) {
      return selected.growthRowTotals[rowIndex] ?? null;
    }
    return numericRow.reduce((sum, value) => sum + value, 0);
  });

  if (selected.rows.length === 0 || selected.columns.length === 0) {
    return (
      <div data-testid="cross-empty-state" className="px-[20px] py-[34px] text-center text-[13px] font-semibold text-muted2">
        {selected.rowOptions.length === 0 || selected.columnOptions.length === 0
          ? "교차분석에 표시할 CMS 분석 결과가 없습니다. 데이터 입력 탭에서 분석 시작을 먼저 실행해 주세요."
          : `${selected.rowLabel}와 ${selected.columnLabel}을 선택하면 교차표가 채워집니다.`}
      </div>
    );
  }

  return (
    <>
      <table data-testid="cross-heatmap" className="w-full table-fixed border-collapse text-[12.5px]">
        <thead>
          <tr className="bg-surface-soft text-muted">
            <th className="w-[220px] border-b border-divider px-[16px] py-[12px] text-left font-black">
              {selected.rowLabel} / {selected.columnLabel}
            </th>
            {selected.columns.map((column) => (
              <th key={column} className="border-b border-divider px-[10px] py-[12px] text-right font-black">
                {column}
              </th>
            ))}

            <th className="w-[175px] border-b border-divider bg-row px-[12px] py-[12px] text-right font-black">
              {scale === "share" && !isGrowthMetric ? "행 비중" : selected.totalLabel}
            </th>
          </tr>
        </thead>
        <tbody>
          {selected.rows.map((row, rowIndex) => (
            <tr key={row}>
              <th className="border-b border-rowline px-[16px] py-[12px] text-left text-[13px] font-black text-ink">{row}</th>
              {values[rowIndex].map((value, colIndex) => (
                <CrossHeatCell
                  key={`${row}-${selected.columns[colIndex]}`}
                  value={
                    scale === "share" && !isGrowthMetric
                      ? shareAllocation.calculable
                        ? shareAllocation.values[rowIndex]?.[colIndex] ?? null
                        : null
                      : value
                  }
                  status={selected.cellStatuses[rowIndex]?.[colIndex]}
                  max={scale === "share" && !isGrowthMetric ? 100 : max}
                  metric={metric}
                  scale={scale}
                  eurKrwRate={eurKrwRate}
                  shareUnavailable={
                    scale === "share" && !isGrowthMetric && !shareAllocation.calculable
                  }
                />
              ))}
              <td className="border-b border-rowline bg-surface-soft px-[12px] py-[12px] text-right text-[12.5px] font-black text-ink">
                {(() => {
                  const rowTotal = rowTotals[rowIndex];
                  if (rowTotal === null) {
                    return <span className="block text-muted2">-</span>;
                  }
                  const totalDisplay = isGrowthMetric
                    ? `${rowTotal > 0 ? "+" : ""}${rowTotal}%`
                    : scale === "share"
                      ? shareAllocation.calculable
                        ? `${shareAllocation.rowTotals[rowIndex]?.toFixed(1) ?? "0.0"}%`
                        : "-"
                      : metric === "quantity"
                        ? `${rowTotal.toFixed(1)}만`
                        : formatCrossAmountK(rowTotal);
                  const totalKrwDisplay = !isGrowthMetric && scale === "amount" && metric === "sales"
                    ? krwEokFromEur(rowTotal * 1_000, eurKrwRate)
                    : "";
                  return (
                    <>
                      <span className="block">{totalDisplay}</span>
                      {totalKrwDisplay ? <span className="mt-[2px] block text-[11px] font-black text-muted2">{totalKrwDisplay}</span> : null}
                    </>
                  );
                })()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-[18px] py-[13px] text-[12px] font-semibold text-muted2">
        {axis.startsWith("ingredient-")
          ? ingredientCrossScopeNote(ingredient)
          : "CMS 전체 교차 원천을 기준으로 선택한 행과 열을 집계합니다."}
      </p>
    </>
  );
}

export { CrossHeatmapCard };
