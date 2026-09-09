import type { CellFormulaValue, CellValue, Worksheet } from "exceljs";

import { downloadHref } from "@/lib/api";
import { displayBrandName } from "@/lib/brand-display";
import type { AnalyzeResponse, OrderReviewRow } from "@/types/api";
import {
  adjustedOrderAmount,
  adjustedOrderQty,
  formatMoiDisplay,
  orderMoi,
  orderReason,
  orderStatus,
  productDisplayName,
  scenarioStockQty,
  type InboundScenario
} from "./orderScreenModel";

type OrderExportColumn = {
  header: string;
  width: number;
  numberFormat?: string;
};

export function downloadFullOrderReviewXlsx(
  result: Pick<AnalyzeResponse, "download_url" | "job_id">,
  scenario: InboundScenario,
  filename: string
) {
  const downloadUrl = downloadHref(result);
  const separator = downloadUrl.includes("?") ? "&" : "?";
  const link = document.createElement("a");
  link.href = `${downloadUrl}${separator}scenario=${encodeURIComponent(scenario)}`;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

const orderExportColumns: readonly OrderExportColumn[] = [
  { header: "상품코드", width: 18 },
  { header: "바코드", width: 18 },
  { header: "SKU명", width: 42 },
  { header: "브랜드", width: 16 },
  { header: "현지 재고", width: 13, numberFormat: "#,##0" },
  { header: "판매(3개월)", width: 15, numberFormat: "#,##0" },
  { header: "MOI(커버기간)", width: 25, numberFormat: '0.0"개월"' },
  { header: "발주필요수량", width: 15, numberFormat: "#,##0" },
  { header: "권장 발주 금액", width: 17, numberFormat: "\"₩\" #,##0" },
  { header: "미입고 수량", width: 14, numberFormat: "#,##0" },
  { header: "운송중", width: 13, numberFormat: "#,##0" },
  { header: "추천 사유", width: 52 },
  { header: "상태", width: 12 }
];

export async function downloadOrderRowsXlsx(
  rows: OrderReviewRow[],
  scenario: InboundScenario,
  filename: string,
  canDownloadAmountData = true
) {
  const ExcelJS = (await import("exceljs")).default;
  if (!canDownloadAmountData) {
    const workbook = new ExcelJS.Workbook();
    workbook.creator = "Silicon2 SCM";
    workbook.created = new Date();
    const worksheet = workbook.addWorksheet("발주 추천 SKU", {
      views: [{ state: "frozen", ySplit: 2 }]
    });
    const headers = [
      "상품코드", "바코드", "SKU명", "브랜드", "현지 재고", "판매(3개월)",
      "MOI(커버기간)", "발주필요수량", "미입고 수량", "운송중", "추천 사유", "상태"
    ];
    worksheet.addRow(["Silicon2 SCM 발주 추천 SKU · 일반 계정용(금액 제외)"]);
    worksheet.mergeCells(1, 1, 1, headers.length);
    worksheet.addRow(headers);
    rows.forEach((row) => {
      const moi = orderMoi(row, scenario);
      worksheet.addRow([
        row.productCode || row.sku,
        row.barcode || "",
        productDisplayName(row),
        displayBrandName(row.brand),
        scenarioStockQty(row, scenario),
        Math.round(row.recentSalesQty),
        formatMoiDisplay(moi, scenarioStockQty(row, scenario)),
        adjustedOrderQty(row, scenario),
        scenario === "after" ? 0 : row.inboundQty,
        Math.round(row.shippingQty),
        orderReason(row, scenario),
        orderStatus(row, scenario)
      ]);
    });
    worksheet.columns = [
      { width: 18 }, { width: 18 }, { width: 42 }, { width: 16 },
      { width: 13 }, { width: 15 }, { width: 25 }, { width: 15 },
      { width: 14 }, { width: 13 }, { width: 52 }, { width: 12 }
    ];
    worksheet.getRow(1).font = { bold: true, size: 16, color: { argb: "FFFFFFFF" } };
    worksheet.getRow(1).fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF111827" } };
    worksheet.getRow(2).font = { bold: true, color: { argb: "FFFFFFFF" } };
    worksheet.getRow(2).fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFE90035" } };
    worksheet.autoFilter = {
      from: { row: 2, column: 1 },
      to: { row: Math.max(2, rows.length + 2), column: headers.length }
    };
    const buffer = await workbook.xlsx.writeBuffer();
    const blob = new Blob([buffer], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename.replace(/\.xlsx$/i, "_no_amount.xlsx");
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    return;
  }
  const headers = orderExportColumns.map((column) => column.header);
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
  workbook.calcProperties.fullCalcOnLoad = true;

  const worksheet = workbook.addWorksheet("발주 추천 SKU", {
    views: [{ state: "frozen", ySplit: 5, activeCell: "B2" }]
  });
  const calcSheetName = "_계산값";
  const calcWorksheet = workbook.addWorksheet(calcSheetName);
  calcWorksheet.state = "veryHidden";
  const initialScenarioLabel = scenario === "after" ? "미입고 해소 후" : "미입고 해소 전";
  const headerRow = 5;
  const firstDataRow = headerRow + 1;
  const lastDataRow = headerRow + rows.length;
  const formulaLastDataRow = Math.max(lastDataRow, firstDataRow);
  const visibleColumnCount = orderExportColumns.length;
  const helperColumns = [
    "해소전_기준재고",
    "해소후_기준재고",
    "해소전_MOI",
    "해소후_MOI",
    "해소전_발주필요수량",
    "해소후_발주필요수량",
    "해소전_권장발주금액",
    "해소후_권장발주금액",
    "해소전_미입고수량",
    "해소후_미입고수량",
    "해소전_추천사유",
    "해소후_추천사유",
    "해소전_상태",
    "해소후_상태"
  ];
  const helperIndex = Object.fromEntries(helperColumns.map((name, index) => [name, index + 1]));
  const beforeTotalOrderQty = rows.reduce((sum, row) => sum + adjustedOrderQty(row, "before"), 0);
  const afterTotalOrderQty = rows.reduce((sum, row) => sum + adjustedOrderQty(row, "after"), 0);
  const beforeTotalOrderAmount = rows.reduce((sum, row) => sum + adjustedOrderAmount(row, "before"), 0);
  const afterTotalOrderAmount = rows.reduce((sum, row) => sum + adjustedOrderAmount(row, "after"), 0);
  const scenarioFormula = (afterCell: string, beforeCell: string) => `IF($B$2="미입고 해소 후",${afterCell},${beforeCell})`;
  const calcRef = (address: string) => `'${calcSheetName}'!${address}`;
  const calcRange = (key: string) => {
    const columnLetter = calcWorksheet.getColumn(helperIndex[key]).letter;
    return `'${calcSheetName}'!${columnLetter}${firstDataRow}:${columnLetter}${formulaLastDataRow}`;
  };
  const writeRow = (targetWorksheet: Worksheet, rowNumber: number, values: CellValue[]) => {
    values.forEach((value, index) => {
      targetWorksheet.getCell(rowNumber, index + 1).value = value;
    });
  };

  worksheet.mergeCells(1, 1, 1, visibleColumnCount);
  worksheet.mergeCells("D2:H2");
  worksheet.mergeCells("F3:J3");
  worksheet.mergeCells("B4:H4");
  worksheet.getCell("A1").value = "Silicon2 SCM 발주 추천 SKU";
  worksheet.getCell("A2").value = "시나리오 선택";
  worksheet.getCell("B2").value = initialScenarioLabel;
  worksheet.getCell("B2").dataValidation = {
    type: "list",
    allowBlank: false,
    formulae: ['"미입고 해소 전,미입고 해소 후"'],
    showErrorMessage: true,
    errorStyle: "stop",
    errorTitle: "시나리오 선택",
    error: "목록에서 미입고 해소 전 또는 미입고 해소 후를 선택해 주세요.",
    showInputMessage: true,
    promptTitle: "시나리오 선택",
    prompt: "드롭다운에서 미입고 해소 전/후를 선택하면 표가 자동 계산됩니다."
  };
  worksheet.getCell("C2").value = "사용 방법";
  worksheet.getCell("D2").value = "B2 셀을 클릭해 미입고 해소 전/후를 선택하면 아래 표가 자동 계산됩니다.";
  worksheet.getCell("I2").value = "대상 SKU 수";
  worksheet.getCell("J2").value = rows.length;
  worksheet.getCell("A3").value = "총 발주필요수량";
  worksheet.getCell("B3").value = {
    formula: `IF($B$2="미입고 해소 후",SUM(${calcRange("해소후_발주필요수량")}),SUM(${calcRange("해소전_발주필요수량")}))`,
    result: scenario === "after" ? afterTotalOrderQty : beforeTotalOrderQty
  };
  worksheet.getCell("C3").value = "총 권장 발주 금액";
  worksheet.getCell("D3").value = {
    formula: `IF($B$2="미입고 해소 후",SUM(${calcRange("해소후_권장발주금액")}),SUM(${calcRange("해소전_권장발주금액")}))`,
    result: scenario === "after" ? afterTotalOrderAmount : beforeTotalOrderAmount
  };
  worksheet.getCell("E3").value = "생성일";
  worksheet.getCell("F3").value = generatedAt;
  worksheet.getCell("A4").value = "표시 기준";
  worksheet.getCell("B4").value = {
    formula: 'IF($B$2="미입고 해소 후","미입고 수량을 현재고에 반영한 기준","미입고 수량을 아직 반영하지 않은 기준")',
    result: scenario === "after" ? "미입고 수량을 현재고에 반영한 기준" : "미입고 수량을 아직 반영하지 않은 기준"
  };

  writeRow(worksheet, headerRow, headers);
  writeRow(calcWorksheet, headerRow, helperColumns);
  rows.forEach((row, index) => {
    const excelRow = firstDataRow + index;
    const beforeMoi = orderMoi(row, "before");
    const afterMoi = orderMoi(row, "after");
    const beforeQty = adjustedOrderQty(row, "before");
    const afterQty = adjustedOrderQty(row, "after");
    const beforeAmount = adjustedOrderAmount(row, "before");
    const afterAmount = adjustedOrderAmount(row, "after");
    const beforeReason = orderReason(row, "before");
    const afterReason = orderReason(row, "after");
    const beforeStatus = orderStatus(row, "before");
    const afterStatus = orderStatus(row, "after");
    const helperValues: Record<string, string | number> = {
      "해소전_기준재고": scenarioStockQty(row, "before"),
      "해소후_기준재고": scenarioStockQty(row, "after"),
      "해소전_MOI": Number.isFinite(beforeMoi) ? beforeMoi : "",
      "해소후_MOI": Number.isFinite(afterMoi) ? afterMoi : "",
      "해소전_발주필요수량": beforeQty,
      "해소후_발주필요수량": afterQty,
      "해소전_권장발주금액": beforeAmount,
      "해소후_권장발주금액": afterAmount,
      "해소전_미입고수량": row.inboundQty,
      "해소후_미입고수량": 0,
      "해소전_추천사유": beforeReason,
      "해소후_추천사유": afterReason,
      "해소전_상태": beforeStatus,
      "해소후_상태": afterStatus
    };
    const formulaCell = (formula: string, result: string | number): CellFormulaValue => ({ formula, result });
    // ExcelJS는 캐시 결과가 0이나 빈 문자열이면 <v>를 생략한다. 그러면 수식을 계산하지 않는
    // 도구(pandas 등)에서 그 셀이 빈칸으로 읽힌다. 미입고 해소 전/후 값이 같은 셀은 시나리오를
    // 바꿔도 결과가 같아 수식이 필요 없으므로, 리터럴로 써서 값이 항상 파일에 남게 한다.
    const scenarioCell = (
      formula: string,
      beforeValue: string | number,
      afterValue: string | number
    ): CellValue => {
      if (beforeValue === afterValue) {
        return beforeValue;
      }
      return formulaCell(formula, scenario === "after" ? afterValue : beforeValue);
    };
    const beforeMoiRef = calcRef(calcWorksheet.getCell(excelRow, helperIndex[helperColumns[2]]).address);
    const afterMoiRef = calcRef(calcWorksheet.getCell(excelRow, helperIndex[helperColumns[3]]).address);
    const scenarioMoiFormula = scenarioFormula(afterMoiRef, beforeMoiRef);
    const moiDisplayFormula = `IF($F${excelRow}=0,"판매 없음",IF(${scenarioMoiFormula}=0,"재고 없음 (0.00개월)",IF(${scenarioMoiFormula}<1/30,"<1일 ("&TEXT(${scenarioMoiFormula},"0.00")&"개월)",IF(${scenarioMoiFormula}<1,ROUND(${scenarioMoiFormula}*30,0)&"일 ("&TEXT(${scenarioMoiFormula},"0.00")&"개월)",TEXT(${scenarioMoiFormula},"0.0")&"개월 ("&ROUND(${scenarioMoiFormula}*30,0)&"일)"))))`;
    const values: CellValue[] = [
      row.productCode || row.sku,
      row.barcode || "",
      productDisplayName(row),
      displayBrandName(row.brand),
      scenarioCell(
        scenarioFormula(calcRef(calcWorksheet.getCell(excelRow, helperIndex["해소후_기준재고"]).address), calcRef(calcWorksheet.getCell(excelRow, helperIndex["해소전_기준재고"]).address)),
        helperValues["해소전_기준재고"],
        helperValues["해소후_기준재고"]
      ),
      Math.round(row.recentSalesQty),
      formulaCell(moiDisplayFormula, formatMoiDisplay(scenario === "after" ? afterMoi : beforeMoi, scenarioStockQty(row, scenario))),
      scenarioCell(
        scenarioFormula(calcRef(calcWorksheet.getCell(excelRow, helperIndex["해소후_발주필요수량"]).address), calcRef(calcWorksheet.getCell(excelRow, helperIndex["해소전_발주필요수량"]).address)),
        helperValues["해소전_발주필요수량"],
        helperValues["해소후_발주필요수량"]
      ),
      scenarioCell(
        scenarioFormula(calcRef(calcWorksheet.getCell(excelRow, helperIndex["해소후_권장발주금액"]).address), calcRef(calcWorksheet.getCell(excelRow, helperIndex["해소전_권장발주금액"]).address)),
        helperValues["해소전_권장발주금액"],
        helperValues["해소후_권장발주금액"]
      ),
      scenarioCell(
        scenarioFormula(calcRef(calcWorksheet.getCell(excelRow, helperIndex["해소후_미입고수량"]).address), calcRef(calcWorksheet.getCell(excelRow, helperIndex["해소전_미입고수량"]).address)),
        helperValues["해소전_미입고수량"],
        helperValues["해소후_미입고수량"]
      ),
      Math.round(row.shippingQty),
      scenarioCell(
        scenarioFormula(calcRef(calcWorksheet.getCell(excelRow, helperIndex["해소후_추천사유"]).address), calcRef(calcWorksheet.getCell(excelRow, helperIndex["해소전_추천사유"]).address)),
        beforeReason,
        afterReason
      ),
      scenarioCell(
        scenarioFormula(calcRef(calcWorksheet.getCell(excelRow, helperIndex["해소후_상태"]).address), calcRef(calcWorksheet.getCell(excelRow, helperIndex["해소전_상태"]).address)),
        beforeStatus,
        afterStatus
      )
    ];
    writeRow(worksheet, excelRow, values);
    writeRow(calcWorksheet, excelRow, helperColumns.map((name) => helperValues[name]));
  });

  orderExportColumns.forEach((column, index) => {
    const excelColumn = worksheet.getColumn(index + 1);
    excelColumn.width = column.width;
    if (column.numberFormat) {
      excelColumn.numFmt = column.numberFormat;
    }
  });
  worksheet.getColumn(1).numFmt = "@";
  worksheet.getColumn(2).numFmt = "@";
  worksheet.getColumn(5).numFmt = "#,##0";
  worksheet.getColumn(6).numFmt = "#,##0";
  worksheet.getColumn(7).numFmt = '0.0"개월"';
  worksheet.getColumn(8).numFmt = "#,##0";
  worksheet.getColumn(9).numFmt = '"₩" #,##0';
  worksheet.getColumn(10).numFmt = "#,##0";
  worksheet.getColumn(11).numFmt = "#,##0";
  worksheet.getCell("J2").numFmt = "#,##0";
  worksheet.getCell("B3").numFmt = "#,##0";
  worksheet.getCell("D3").numFmt = '"₩" #,##0';
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
        text: "긴급",
        priority: 1,
        style: { font: { bold: true, color: { argb: "FFE90035" } } }
      }
    ]
  });

  const border = { style: "thin" as const, color: { argb: "FFE5E7EB" } };
  worksheet.eachRow((row, rowNumber) => {
    // eachCell은 그 행의 마지막 정의 셀까지만 순회해 상단 밴드 우측 스타일이 끊기므로 고정 열 범위로 돈다
    for (let colNumber = 1; colNumber <= visibleColumnCount; colNumber += 1) {
      const cell = row.getCell(colNumber);
      const columnDefinition = orderExportColumns[colNumber - 1];
      if (columnDefinition?.numberFormat) {
        cell.numFmt = columnDefinition.numberFormat;
      }
      cell.border = { top: border, left: border, bottom: border, right: border };
      cell.alignment = {
        vertical: rowNumber >= firstDataRow ? "top" : "middle",
        horizontal:
          rowNumber >= firstDataRow && columnDefinition?.numberFormat
            ? "right"
            : colNumber === 3 || colNumber === 12
              ? "left"
              : "center",
        wrapText: colNumber === 12
      };
      if (rowNumber === 1) {
        cell.font = { bold: true, size: 16, color: { argb: "FFFFFFFF" } };
        cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF111827" } };
        cell.alignment = { horizontal: "left", vertical: "middle" };
      } else if (rowNumber === headerRow) {
        cell.font = { bold: true, color: { argb: "FFFFFFFF" } };
        cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFE90035" } };
      } else if (rowNumber <= 4) {
        const hasValue = cell.value !== null && cell.value !== undefined && cell.value !== "";
        const labelCell = hasValue && colNumber % 2 === 1;
        cell.font = { bold: labelCell, color: { argb: labelCell ? "FF4B5563" : "FF111827" } };
        cell.fill = { type: "pattern", pattern: "solid", fgColor: { argb: labelCell ? "FFF3F4F6" : "FFFFFFFF" } };
      }
    }
  });
  worksheet.getCell("B2").font = { bold: true, color: { argb: "FFFFFFFF" } };
  worksheet.getCell("B2").fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FFE90035" } };
  worksheet.getCell("B2").alignment = { horizontal: "center", vertical: "middle" };
  worksheet.getRow(1).height = 22;
  worksheet.getRow(2).height = 24;
  worksheet.getRow(3).height = 22;
  worksheet.getRow(4).height = 28;

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
