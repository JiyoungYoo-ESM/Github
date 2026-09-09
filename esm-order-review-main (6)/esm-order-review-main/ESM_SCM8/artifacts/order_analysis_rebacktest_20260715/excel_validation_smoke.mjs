import fs from "node:fs";
import path from "node:path";

import ExcelJS from "../../frontend/node_modules/exceljs/excel.js";

const outputPath = path.join(import.meta.dirname, "excel_validation_smoke.xlsx");
const workbook = new ExcelJS.Workbook();
const worksheet = workbook.addWorksheet("validation");
worksheet.getCell("A1").value = "시나리오";
worksheet.getCell("A2").value = "미반영";
worksheet.getCell("A2").dataValidation = {
  type: "list",
  allowBlank: false,
  formulae: ['"미반영,반영"'],
  showErrorMessage: true,
  errorStyle: "stop",
  errorTitle: "입력 오류",
  error: "목록에서 값을 선택하세요.",
};
await workbook.xlsx.writeFile(outputPath);
const stats = fs.statSync(outputPath);
process.stdout.write(`${JSON.stringify({ file: outputPath, bytes: stats.size })}\n`);
