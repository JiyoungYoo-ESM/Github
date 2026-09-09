import type { Cell, Style, Workbook, Worksheet } from "exceljs";

// Layout tokens transcribed from the supplied workbook; no sample business data.
export const PROPOSAL_WIDTHS = [15, 30, 10, 12, 10, 9, 13, 8, 11, 9, 9, 12, 8, 10, 9, 9, 11, 10, 11, 9, 10, 10, 9, 12, 10, 9, 10, 10, 9, 9, 10, 11, 10, 11, 10, 8];
export const LOGISTICS_WIDTHS = [18, 34, 18, 13, 13, 13, 15, 14, 14];
const font = { name: "맑은 고딕", family: 3, charset: 129, size: 9 };
const edge = { style: "thin" as const, color: { argb: "FFC7CDD6" } };
const border = { left: edge, right: edge, top: edge, bottom: edge };
const fill = (argb: string): Style["fill"] => ({ type: "pattern", pattern: "solid", fgColor: { argb } });

export function templateSheet(workbook: Workbook, name: string, widths: number[], headerRow: number, xSplit = 0, showGridLines = true) {
  // The streaming writer emits views/properties when the sheet is created.
  const sheet = workbook.addWorksheet(name, {
    properties: { defaultColWidth: 9 },
    views: [{ state: "frozen", xSplit, ySplit: headerRow, showGridLines, zoomScale: 100 }],
    pageSetup: { orientation: "landscape", fitToPage: true, fitToWidth: 1, fitToHeight: 0, printTitlesRow: `1:${headerRow}` }
  });
  // ExcelJS omits explicit width=9 columns on save; keep that default explicit
  // so the template's narrow columns do not fall back to Excel's 8.43 width.
  sheet.columns = widths.map(width => ({ width }));
  return sheet;
}

export function band(sheet: Worksheet, range: string, value: string, title = false) {
  sheet.mergeCells(range);
  const cell = sheet.getCell(range.split(":")[0]);
  cell.value = value;
  cell.font = { ...font, size: title ? 15 : 8, bold: title, color: { argb: title ? "FFFFFFFF" : "FF4A4E58" } };
  cell.fill = fill(title ? "FF12324F" : "FFEEF1F7");
  cell.alignment = { horizontal: "left", vertical: "middle", wrapText: !title, indent: 1 };
}

export function group(sheet: Worksheet, range: string, value: string, color: string) {
  sheet.mergeCells(range);
  const cell = sheet.getCell(range.split(":")[0]);
  cell.value = value;
  cell.font = { ...font, bold: true, color: { argb: "FF12324F" } };
  cell.fill = fill(color);
  cell.border = border;
  cell.alignment = { horizontal: "center", vertical: "middle", wrapText: true };
}

export function header(cell: Cell, value: string, note?: string) {
  cell.value = value;
  cell.font = { ...font, bold: true, color: { argb: "FFFFFFFF" } };
  cell.fill = fill("FF12324F");
  cell.border = border;
  cell.alignment = { horizontal: "center", vertical: "middle", wrapText: true };
  if (note) cell.note = note;
}

const bodyStyles = new Map<string, Partial<Style>>();
export function body(cell: Cell, format = "General", alignment: "left" | "center" | "right" = "right", emphasis = false) {
  const key = `${format}:${alignment}:${emphasis}`;
  let style = bodyStyles.get(key);
  if (!style) {
    style = {
      font: { ...font, bold: emphasis, color: { argb: emphasis ? "FF7A1F1F" : "FF20232A" } },
      border, fill: { type: "pattern", pattern: "none" }, numFmt: format,
      alignment: { horizontal: alignment, vertical: "middle" }
    };
    bodyStyles.set(key, style);
  }
  // Shared styles are immutable. Callers that override one field copy first.
  cell.style = style;
}
