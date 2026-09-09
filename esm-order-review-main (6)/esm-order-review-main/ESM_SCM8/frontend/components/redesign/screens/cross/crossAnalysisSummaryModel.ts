import type {
  CrossMatrixData,
  CrossMetric,
  CrossScale
} from "../../../../lib/cross-analysis-matrix.ts";
import type { CrossShareAllocation } from "../../../../lib/cross-analysis-share.ts";
import { formatNumber } from "../../../../lib/utils.ts";
import {
  formatCrossCellKrw,
  formatCrossCellValue,
  isCrossGrowthMetric
} from "./crossAnalysisCellFormat.ts";

export type CrossSummaryCardData = {
  label: string;
  value: string;
  sub: string;
};

type FilledCell = {
  row: number;
  col: number;
  value: number;
};

function extremum(
  cells: FilledCell[],
  select: (candidate: FilledCell, current: FilledCell) => boolean
) {
  return cells.reduce<FilledCell | null>(
    (current, candidate) => (!current || select(candidate, current) ? candidate : current),
    null
  );
}

export function buildCrossSummaryCards({
  selected,
  metric,
  scale,
  shareAllocation,
  eurKrwRate
}: {
  selected: CrossMatrixData;
  metric: CrossMetric;
  scale: CrossScale;
  shareAllocation: CrossShareAllocation;
  eurKrwRate?: number | null;
}): CrossSummaryCardData[] | null {
  const { rows, columns, values, rowLabel, columnLabel } = selected;
  if (rows.length === 0 || columns.length === 0) return null;

  const isGrowthMetric = isCrossGrowthMetric(metric);
  const totalCount = rows.length * columns.length;
  const filledCells: FilledCell[] = [];
  let filledCount = 0;

  rows.forEach((_, rowIndex) => {
    columns.forEach((_, columnIndex) => {
      const rawValue = values[rowIndex]?.[columnIndex];
      if (isGrowthMetric) {
        if (rawValue === null || !Number.isFinite(rawValue)) return;
        filledCount += 1;
        filledCells.push({ row: rowIndex, col: columnIndex, value: rawValue });
        return;
      }

      // Static coverage describes whether the source combination exists. A real
      // zero net value must not be confused with an absent row×column pair.
      const sourceCombinationExists =
        selected.cellPresence?.[rowIndex]?.[columnIndex] ??
        (typeof rawValue === "number" && Number.isFinite(rawValue) && rawValue !== 0);
      if (!sourceCombinationExists) return;
      filledCount += 1;

      const displayValue =
        scale === "share"
          ? shareAllocation.calculable
            ? shareAllocation.values[rowIndex]?.[columnIndex]
            : null
          : rawValue;
      if (typeof displayValue === "number" && Number.isFinite(displayValue)) {
        filledCells.push({ row: rowIndex, col: columnIndex, value: displayValue });
      }
    });
  });

  const coveragePct = totalCount > 0 ? (filledCount / totalCount) * 100 : 0;
  const comboLabel = (row: number, column: number) => `${rows[row]} × ${columns[column]}`;

  if (isGrowthMetric) {
    const positiveCells = filledCells.filter((cell) => cell.value > 0);
    const negativeCells = filledCells.filter((cell) => cell.value < 0);
    const bestGrowthCell = extremum(
      positiveCells,
      (candidate, current) => candidate.value > current.value
    );
    const worstDeclineCell = extremum(
      negativeCells,
      (candidate, current) => candidate.value < current.value
    );

    return [
      {
        label: "가장 많이 증가",
        value: bestGrowthCell ? formatCrossCellValue(bestGrowthCell.value, metric, scale) : "-",
        sub: bestGrowthCell
          ? comboLabel(bestGrowthCell.row, bestGrowthCell.col)
          : "성장 조합 없음"
      },
      {
        label: "가장 많이 감소",
        value: worstDeclineCell ? formatCrossCellValue(worstDeclineCell.value, metric, scale) : "-",
        sub: worstDeclineCell
          ? comboLabel(worstDeclineCell.row, worstDeclineCell.col)
          : "감소 조합 없음"
      },
      {
        label: "증가한 조합",
        value:
          filledCount > 0
            ? `${formatNumber(positiveCells.length)}개`
            : "-",
        sub:
          filledCount > 0
            ? `비교 가능한 ${formatNumber(filledCount)}개 중 ${formatNumber(positiveCells.length)}개 증가 (${formatNumber((positiveCells.length / filledCount) * 100, 1)}%)`
            : "비교 가능한 조합 없음"
      },
      {
        label: "비교 가능한 조합",
        value: `${formatNumber(filledCount)}개 / ${formatNumber(totalCount)}개`,
        sub:
          `전체 ${formatNumber(totalCount)}개 조합 중 ${formatNumber(filledCount)}개 비교 가능 (${formatNumber(coveragePct, 1)}%)`
      }
    ];
  }

  const flatValues = filledCells.map((cell) => cell.value);
  const sumAll = flatValues.reduce((sum, value) => sum + value, 0);
  const bestCell = extremum(
    filledCells,
    (candidate, current) => candidate.value > current.value
  );
  const sortedDesc = [...flatValues].sort((left, right) => right - left);
  const top3Sum = sortedDesc.slice(0, 3).reduce((sum, value) => sum + value, 0);
  const concentrationCalculable = shareAllocation.calculable && sumAll > 0;
  const concentrationPct = concentrationCalculable ? (top3Sum / sumAll) * 100 : null;
  const shareUnavailable = scale === "share" && !shareAllocation.calculable;

  return [
    {
      label: "최강 조합",
      value: bestCell ? formatCrossCellValue(bestCell.value, metric, scale) : "-",
      sub: bestCell
        ? [
            comboLabel(bestCell.row, bestCell.col),
            formatCrossCellKrw(bestCell.value, metric, scale, eurKrwRate)
          ]
            .filter(Boolean)
            .join(" · ")
        : shareUnavailable
          ? "선택 범위 합계가 0이라 비중 계산 불가"
          : "실적 있는 조합 없음"
    },
    {
      label: "상위 3 조합 집중도",
      value: concentrationPct === null ? "-" : `${formatNumber(concentrationPct, 1)}%`,
      sub: shareUnavailable
        ? "선택 범위 합계가 0이라 계산 불가"
        : "선택 범위 합계 대비 비중"
    },
    scale === "amount"
      ? {
          label: "선택 범위 합계",
          value:
            filledCells.length > 0
              ? formatCrossCellValue(sumAll, metric, scale)
              : "-",
          sub:
            formatCrossCellKrw(sumAll, metric, scale, eurKrwRate) ||
            "선택한 행 × 열의 합계"
        }
      : {
          label: "선택 조합 수",
          value: `${formatNumber(totalCount)}개`,
          sub: `${rowLabel} ${formatNumber(rows.length)}개 × ${columnLabel} ${formatNumber(columns.length)}개`
        },
    {
      label: "비교 가능한 조합",
      value: `${formatNumber(filledCount)}개 / ${formatNumber(totalCount)}개`,
      sub: `전체 ${formatNumber(totalCount)}개 조합 중 ${formatNumber(filledCount)}개 비교 가능 (${formatNumber(coveragePct, 1)}%)`
    }
  ];
}
