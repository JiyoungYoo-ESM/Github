import assert from "node:assert/strict";
import ExcelJS from "exceljs";
import { SEASON_FACTOR_EXPORT_COLUMNS, seasonFactorExportValues } from "../components/redesign/screens/order-v3/seasonFactorExport.ts";

const rows = [
  {
    seasonalApplied: true,
    seasonFactorDefaulted: true,
    seasonFactorVersion: "test-default-version",
    seasonFactorOriginalReasonCode: "SEASON_FACTOR_CALC_FAILED",
    seasonFactorOriginalMessage: "zero monthly factor",
    seasonalFactors: { f1: 1, f2: 1, fLR: 1 }
  },
  {
    seasonalApplied: true,
    seasonFactorDefaulted: false,
    seasonFactorVersion: "test-calculated-version",
    seasonalFactors: { f1: 0.8, f2: 1.2, fLR: 1.05 }
  }
];
const workbook = new ExcelJS.Workbook();
const sheet = workbook.addWorksheet("audit");
sheet.addRow(SEASON_FACTOR_EXPORT_COLUMNS);
rows.forEach((row) => sheet.addRow(seasonFactorExportValues(row)));
const roundtrip = new ExcelJS.Workbook();
await roundtrip.xlsx.load(await workbook.xlsx.writeBuffer());
const values = roundtrip.getWorksheet("audit");
assert.deepEqual(values.getRow(2).values.slice(1), [
  "기본값 1.0 적용", "test-default-version", 1, 1, 1,
  "SEASON_FACTOR_CALC_FAILED", "zero monthly factor", "", "", "연결 완료"
]);
assert.deepEqual(values.getRow(3).values.slice(1), [
  "계산된 지수 적용", "test-calculated-version", 0.8, 1.2, 1.05, "", "", "", "", "연결 완료"
]);
assert.deepEqual(seasonFactorExportValues({ seasonalApplied: false }), ["미적용", "", null, null, null, "", "", "", "", "미확인"]);
const held = {
  seasonalApplied: false, seasonFactorAvailable: true, seasonFactorDefaulted: true,
  functionClass1: "스킨케어", functionClass2: "패치", seasonFactorVersion: "synthetic-active",
};
assert.deepEqual(seasonFactorExportValues(held), [
  "기본값 1.0 연결 · 발주 계산 미완료", "synthetic-active", null, null, null, "", "", "스킨케어", "패치", "연결 완료"
]);
assert.equal(seasonFactorExportValues({ ...held, seasonFactorDefaulted: false })[0], "지수 연결 · 발주 계산 미완료");
assert.equal(seasonFactorExportValues({ ...held, seasonFactorAvailable: false })[0], "미적용");
assert.equal(seasonFactorExportValues({ ...held, seasonFactorAvailable: false }).at(-1), "연결 불가");
assert.equal(SEASON_FACTOR_EXPORT_COLUMNS.length, 10);
console.log("V3 season default Excel round-trip passed");
