import type { CellValue, Worksheet } from "exceljs";

import { displayBrandName } from "@/lib/brand-display";
import { formatDate as formatStockGapDate } from "@/lib/stock-gap";
import {
  isEtaMissingRow,
  stockGapDisplayStatus,
  stockGapEtaLabel,
  stockGapReason,
  stockGapShortageQty,
  type StockGapComputed
} from "./gapScreenModel";

type StockGapExportColumn = {
  header: string;
  width: number;
  numberFormat?: string;
  textFormat?: boolean;
  align?: "left" | "center" | "right";
  wrapText?: boolean;
};

const stockGapExportColumns: readonly StockGapExportColumn[] = [
  { header: "상품코드", width: 18, textFormat: true, align: "left" },
  { header: "바코드", width: 18, textFormat: true, align: "left" },
  { header: "SKU", width: 44, align: "left" },
  { header: "브랜드", width: 16 },
  { header: "현재고", width: 18, numberFormat: "#,##0" },
  { header: "판매 속도", width: 13, numberFormat: '0.0"/일"' },
  { header: "소진 예정", width: 14 },
  { header: "최초 ETA", width: 14 },
  { header: "공백", width: 10, numberFormat: '0"일"' },
  { header: "부족 수량", width: 14, numberFormat: "#,##0" },
  { header: "판단 사유", width: 54, align: "left", wrapText: true },
  { header: "상태", width: 13 }
];

export type StockGapExportOptions = {
  brandLabel: string;
  sortLabel: string;
  scopeLabel: string;
};

export async function downloadStockGapRowsXlsx(rows: StockGapComputed[], filename: string, options: StockGapExportOptions) {
  const ExcelJS = (await import("exceljs")).default;
  const generatedAt = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date());
  const workbook = new ExcelJS.Workbook();
  workbook.creator = "Silicon2 SCM";
  workbook.created = new Date();
  workbook.modified = new Date();

  const worksheet = workbook.addWorksheet("재고공백", {
    views: [{ state: "frozen", ySplit: 5 }]
  });
  const summaryLastRow = 4;
  const headerRow = summaryLastRow + 1;
  const firstDataRow = headerRow + 1;
  const lastDataRow = headerRow + rows.length;
  const formulaLastDataRow = Math.max(lastDataRow, firstDataRow);
  const visibleColumnCount = stockGapExportColumns.length;
  const riskRows = rows.filter((row) => row.status === "stock_gap" || row.status === "urgent_replenishment");
  const longGapRows = riskRows.filter((row) => (row.gapDays ?? 0) >= 7);
  const etaMissingRows = rows.filter(isEtaMissingRow);
  const noInboundRows = rows.filter((row) => row.status === "stockout_no_inbound");
  const pastEtaRows = rows.filter((row) => row.pastEtaDate !== null);
  const totalShortageQty = riskRows.reduce((sum, row) => sum + stockGapShortageQty(row), 0);
  const writeRow = (targetWorksheet: Worksheet, rowNumber: number, values: CellValue[]) => {
    values.forEach((value, index) => {
      targetWorksheet.getCell(rowNumber, index + 1).value = value;
    });
  };

  worksheet.mergeCells(1, 1, 1, visibleColumnCount);
  worksheet.mergeCells("B2:C2");
  worksheet.mergeCells("E2:G2");
  worksheet.mergeCells(2, 11, 2, visibleColumnCount);
  worksheet.mergeCells("G3:H3");
  worksheet.mergeCells(3, 11, 3, visibleColumnCount);
  worksheet.mergeCells("A4:B4");
  worksheet.mergeCells("E4:F4");
  worksheet.mergeCells(4, 11, 4, visibleColumnCount);
  worksheet.getCell("A1").value = "Silicon2 SCM 재고 공백";
  worksheet.getCell("A2").value = "생성일";
  worksheet.getCell("B2").value = generatedAt;
  worksheet.getCell("D2").value = "표시 기준";
  worksheet.getCell("E2").value = options.sortLabel;
  worksheet.getCell("H2").value = "대상 SKU 수";
  worksheet.getCell("I2").value = rows.length;
  worksheet.getCell("J2").value = "브랜드";
  worksheet.getCell("K2").value = options.brandLabel;
  worksheet.getCell("A3").value = "재고공백 SKU";
  worksheet.getCell("B3").value = riskRows.length;
  worksheet.getCell("C3").value = "7일 이상 공백 SKU";
  worksheet.getCell("D3").value = longGapRows.length;
  worksheet.getCell("E3").value = "예상 부족 수량";
  worksheet.getCell("F3").value = totalShortageQty;
  worksheet.getCell("G3").value = "ETA 미확인 SKU";
  worksheet.getCell("I3").value = etaMissingRows.length;
  worksheet.getCell("J3").value = "내보내기 범위";
  worksheet.getCell("K3").value = options.scopeLabel;
  // 공백 구간을 계산할 수 없는(=예상 부족 수량에 잡히지 않는) 상태를 별도 지표로 남긴다.
  worksheet.getCell("A4").value = "입고예정 없는 소진 SKU";
  worksheet.getCell("C4").value = noInboundRows.length;
  worksheet.getCell("E4").value = "ETA 경과 SKU";
  worksheet.getCell("G4").value = pastEtaRows.length;
  worksheet.getCell("H4").value = "공백 산정 제외";
  worksheet.getCell("I4").value = noInboundRows.length + etaMissingRows.length;
  worksheet.getCell("J4").value = "부족 수량 기준";
  worksheet.getCell("K4").value = "공백 일수 × 판매 속도 (입고 예정이 있는 SKU만 산정)";

  writeRow(worksheet, headerRow, stockGapExportColumns.map((column) => column.header));
  rows.forEach((row, index) => {
    const displayName = row.productName && row.productName !== "-" ? row.productName : "";
    const shortageQty = stockGapShortageQty(row);
    writeRow(worksheet, firstDataRow + index, [
      row.productCode || row.sku,
      row.barcode || "",
      displayName,
      displayBrandName(row.brand),
      row.availableQty === null ? "-" : row.availableQty,
      row.dailySalesQty === null ? "-" : Number(row.dailySalesQty.toFixed(1)),
      formatStockGapDate(row.stockoutDate),
      stockGapEtaLabel(row),
      row.gapDays === null ? "-" : row.gapDays,
      shortageQty,
      stockGapReason(row) || "-",
      stockGapDisplayStatus(row)
    ]);
  });

  stockGapExportColumns.forEach((column, index) => {
    const excelColumn = worksheet.getColumn(index + 1);
    excelColumn.width = column.width;
  });
  worksheet.getCell("I2").numFmt = "#,##0";
  worksheet.getCell("B3").numFmt = "#,##0";
  worksheet.getCell("D3").numFmt = "#,##0";
  worksheet.getCell("F3").numFmt = "#,##0";
  worksheet.getCell("I3").numFmt = "#,##0";
  worksheet.getCell("C4").numFmt = "#,##0";
  worksheet.getCell("G4").numFmt = "#,##0";
  worksheet.getCell("I4").numFmt = "#,##0";
  worksheet.autoFilter = {
    from: { row: headerRow, column: 1 },
    to: { row: Math.max(lastDataRow, headerRow), column: visibleColumnCount }
  };
  const statusColumnLetter = worksheet.getColumn(visibleColumnCount).letter;
  worksheet.addConditionalFormatting({
    ref: `${statusColumnLetter}${firstDataRow}:${statusColumnLetter}${formulaLastDataRow}`,
    rules: [
      {
        type: "containsText",
        operator: "containsText",
        text: "재고공백",
        priority: 1,
        style: { font: { bold: true, color: { argb: "FFE90035" } } }
      }
    ]
  });

  const border = { style: "thin" as const, color: { argb: "FFE5E7EB" } };
  const summaryLabelCells = new Set([
    "A2", "D2", "H2", "J2",
    "A3", "C3", "E3", "G3", "J3",
    "A4", "E4", "H4", "J4"
  ]);
  worksheet.eachRow((row, rowNumber) => {
    // eachCell은 그 행의 마지막 정의 셀까지만 순회해 상단 밴드 우측 스타일이 끊기므로 고정 열 범위로 돈다
    for (let colNumber = 1; colNumber <= visibleColumnCount; colNumber += 1) {
      const cell = row.getCell(colNumber);
      const columnDefinition = stockGapExportColumns[colNumber - 1];
      const dataHorizontal =
        columnDefinition?.align ?? (columnDefinition?.numberFormat ? "right" : "center");
      if (rowNumber >= firstDataRow && columnDefinition?.numberFormat) {
        cell.numFmt = columnDefinition.numberFormat;
      } else if (rowNumber >= firstDataRow && columnDefinition?.textFormat) {
        cell.numFmt = "@";
      }
      cell.border = { top: border, left: border, bottom: border, right: border };
      cell.alignment = {
        vertical: rowNumber >= firstDataRow ? "top" : "middle",
        horizontal: rowNumber >= firstDataRow ? dataHorizontal : "center",
        wrapText: Boolean(rowNumber >= firstDataRow && columnDefinition?.wrapText)
      };
      if (rowNumber === 1) {
        cell.font = { bold: true, size: 16, color: { argb: "FFFFFFFF" } };
        cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF111827" } };
        cell.alignment = { horizontal: "left", vertical: "middle" };
      } else if (rowNumber === headerRow) {
        cell.font = { bold: true, color: { argb: "FFFFFFFF" } };
        cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFE90035" } };
      } else if (rowNumber <= summaryLastRow) {
        const hasValue = cell.value !== null && cell.value !== undefined && cell.value !== "";
        const labelCell = hasValue && summaryLabelCells.has(cell.address);
        cell.font = { bold: labelCell, color: { argb: labelCell ? "FF4B5563" : "FF111827" } };
        cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: labelCell ? "FFF3F4F6" : "FFFFFFFF" } };
      }
    }
  });
  worksheet.getRow(1).height = 22;
  worksheet.getRow(2).height = 22;
  worksheet.getRow(3).height = 22;
  worksheet.getRow(4).height = 22;
  worksheet.getRow(headerRow).height = 24;

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
