export type CrossNumericMatrix = Array<Array<number | null>>;

export type CrossShareAllocation = {
  values: CrossNumericMatrix;
  rowTotals: number[];
  total: number;
  calculable: boolean;
};

type ShareCell = {
  rowIndex: number;
  columnIndex: number;
  units: number;
  remainder: number;
  tieBreakKey: string;
  order: number;
};

/**
 * 선택된 교차표 전체를 100%로 보고 표시용 비중을 배분한다.
 *
 * 셀을 각각 반올림하면 표시 합계가 100%에서 벗어날 수 있으므로,
 * 최대 나머지 방식으로 0.1% 단위를 배분해 표시값 합계를 정확히 맞춘다.
 */
export function allocateCrossMatrixShares(
  values: CrossNumericMatrix,
  decimals = 1,
  tieBreakKeys: Array<Array<string>> = []
): CrossShareAllocation {
  const safeDecimals = Number.isInteger(decimals) && decimals >= 0 ? decimals : 1;
  const scale = 10 ** safeDecimals;
  const targetUnits = 100 * scale;
  const total = values.flat().reduce<number>((sum, value) => {
    return typeof value === "number" && Number.isFinite(value) ? sum + value : sum;
  }, 0);
  const allocated: CrossNumericMatrix = values.map((row) => row.map((value) => (value === null ? null : 0)));

  if (Math.abs(total) <= Number.EPSILON) {
    return { values: allocated, rowTotals: allocated.map(() => 0), total: 0, calculable: false };
  }

  const cells: ShareCell[] = [];
  let allocatedUnits = 0;
  let order = 0;

  values.forEach((row, rowIndex) => {
    row.forEach((value, columnIndex) => {
      if (typeof value !== "number" || !Number.isFinite(value) || value === 0) {
        order += 1;
        return;
      }
      const exactUnits = (value / total) * targetUnits;
      const units = Math.floor(exactUnits);
      allocatedUnits += units;
      cells.push({
        rowIndex,
        columnIndex,
        units,
        remainder: exactUnits - units,
        tieBreakKey: tieBreakKeys[rowIndex]?.[columnIndex] ?? String(order).padStart(12, "0"),
        order
      });
      order += 1;
    });
  });

  const unitsToDistribute = Math.max(0, Math.round(targetUnits - allocatedUnits));
  const rankedCells = [...cells].sort(
    (left, right) =>
      right.remainder - left.remainder || left.tieBreakKey.localeCompare(right.tieBreakKey) || left.order - right.order
  );
  for (let index = 0; index < unitsToDistribute && rankedCells.length > 0; index += 1) {
    rankedCells[index % rankedCells.length].units += 1;
  }

  cells.forEach((cell) => {
    allocated[cell.rowIndex][cell.columnIndex] = cell.units / scale;
  });
  const rowTotals = allocated.map((row) =>
    Number(
      row
        .reduce<number>((sum, value) => (typeof value === "number" && Number.isFinite(value) ? sum + value : sum), 0)
        .toFixed(safeDecimals)
    )
  );

  return { values: allocated, rowTotals, total, calculable: true };
}
