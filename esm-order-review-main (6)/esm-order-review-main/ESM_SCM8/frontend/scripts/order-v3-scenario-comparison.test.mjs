import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Exercise the actual mapper and component using synthetic data only.
const screenFile = "components/redesign/screens/order-v3/OrderV3Screen.tsx";
const source = readFileSync(screenFile, "utf8");
const ast = ts.createSourceFile(screenFile, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const functionNames = [
  "formatInteger", "formatKrw", "formatSignedInteger", "formatComparisonAmount",
  "patternLabel", "engineLabel", "mapApiRow", "mapScenarioRows", "ScenarioComparison"
];
const functions = ast.statements.filter(node => ts.isFunctionDeclaration(node) && functionNames.includes(node.name?.text));
assert.equal(functions.length, functionNames.length, "Compile the actual comparison component and its helpers.");
const compiled = ts.transpileModule(functions.map(node => node.getText(ast)).join("\n"), {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
}).outputText;
const context = {
  require: createRequire(import.meta.url), exports: {},
  useMemo: React.useMemo, useState: React.useState,
  integerFormatter: new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }),
  SCENARIO_PAGE_SIZE: 10,
  GitCompareArrows: () => null, X: () => null
};
vm.createContext(context);
vm.runInContext(compiled, context);

const apiRow = (sku, quantity, amount) => ({
  sku_code: sku, product_name: `테스트 상품 ${sku}`, brand: "테스트 브랜드",
  barcode: "0001234567890",
  calculable: true, raw_order_quantity: quantity, order_amount_krw: amount
});
const cash = apiRow("EXAMPLE", 100, 1_000_000);
const shortage = apiRow("EXAMPLE", 150, 1_500_000);
const payload = { rows: [shortage], scenarios: { CASH: { rows: [cash] }, SHORTAGE: { rows: [shortage] } } };
const originalPayload = JSON.stringify(payload);
const [mapped] = context.mapScenarioRows(payload, "SHORTAGE");
assert.equal(mapped.cashOrderAmountKrw, 1_000_000);
assert.equal(mapped.shortageOrderAmountKrw, 1_500_000);
assert.equal(mapped.cashSuggestedQty, 100);
assert.equal(mapped.shortageSuggestedQty, 150);
assert.equal(mapped.orderAmountKrw, 1_500_000, "Existing selected-scenario amount is unchanged.");
const [cashSelected] = context.mapScenarioRows(payload, "CASH");
assert.equal(cashSelected.cashOrderAmountKrw, mapped.cashOrderAmountKrw);
assert.equal(cashSelected.shortageOrderAmountKrw, mapped.shortageOrderAmountKrw);
assert.equal(cashSelected.orderAmountKrw, 1_000_000);
assert.equal(context.mapApiRow(shortage).cashOrderAmountKrw, null);
assert.equal(context.mapApiRow(shortage).shortageOrderAmountKrw, null);
assert.equal(context.mapApiRow(shortage, apiRow("EXAMPLE", 0, 0), shortage).cashOrderAmountKrw, 0);
assert.equal(context.mapApiRow(shortage, apiRow("EXAMPLE", 100, null), shortage).cashOrderAmountKrw, null);

const render = (rows = [mapped], extra = {}) => renderToStaticMarkup(React.createElement(context.ScenarioComparison, {
  open: true, rows, canViewAmountData: true, onClose() {}, ...extra
}));
const cellTexts = (markup, tag) => [...markup.matchAll(new RegExp(`<${tag}\\b[^>]*>([\\s\\S]*?)</${tag}>`, "g"))]
  .map(match => match[1].replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim());
const visible = render();
assert.ok(visible.includes("발주수량·금액 비교"));
assert.ok(visible.includes("100 EA") && visible.includes("150 EA") && visible.includes("+50 EA"));
assert.ok(visible.includes("₩1,000,000") && visible.includes("₩1,500,000") && visible.includes("+₩500,000"));
assert.ok(visible.includes("발주금액(원)") && visible.includes("쇼티지 방어 − 현금흐름 우선"));
assert.equal((visible.match(/<th\b/g) ?? []).length, 5, "Amounts belong below quantities, not in extra columns.");
assert.deepEqual(cellTexts(visible, "th"), ["바코드", "상품명 · SKU", "쇼티지 방어", "현금흐름 우선", "차이"]);
assert.deepEqual(cellTexts(visible, "td").slice(0, 2), ["0001234567890", "테스트 상품 EXAMPLE EXAMPLE"], "Barcode is first and preserves leading zeros.");
assert.equal(cellTexts(render([{ ...mapped, barcode: undefined }]), "td")[0], "미확인", "Missing barcodes remain explicit in the first column.");
assert.deepEqual(cellTexts(visible, "td").slice(2), ["150 EA ₩1,500,000", "100 EA ₩1,000,000", "+50 EA +₩500,000"], "Scenario values must follow their headers and the subtraction order.");

const negative = render([{ ...mapped, cashOrderAmountKrw: 1_500_000, shortageOrderAmountKrw: 1_000_000 }]);
assert.ok(negative.includes("−₩500,000"));
const zero = render([{ ...mapped, cashSuggestedQty: 0, cashOrderAmountKrw: 0, shortageOrderAmountKrw: 0 }]);
assert.equal((zero.match(/₩0/g) ?? []).length, 3);
assert.ok(!zero.includes("미확인</span>") && !zero.includes("+₩0") && !zero.includes("−₩0"));
const fromZero = render([{ ...mapped, cashSuggestedQty: 0, cashOrderAmountKrw: 0 }]);
assert.ok(fromZero.includes("₩0") && fromZero.includes("+₩1,500,000"));

for (const missing of [null, undefined]) {
  const noCash = render([{ ...mapped, cashOrderAmountKrw: missing }]);
  assert.equal((noCash.match(/>미확인<\/span>/g) ?? []).length, 2, "Missing one amount also makes the difference unknown.");
  assert.ok(noCash.includes("₩1,500,000") && !noCash.includes("₩0"));
  const noShortage = render([{ ...mapped, shortageOrderAmountKrw: missing }]);
  assert.equal((noShortage.match(/>미확인<\/span>/g) ?? []).length, 2);
  const neither = render([{ ...mapped, cashOrderAmountKrw: missing, shortageOrderAmountKrw: missing }]);
  assert.equal((neither.match(/>미확인<\/span>/g) ?? []).length, 3);
  assert.ok(!neither.includes("₩"));
}
for (const invalid of [null, undefined, NaN, Infinity, -Infinity]) {
  assert.equal(context.formatComparisonAmount(invalid), "미확인");
}
const decimal = render([{ ...mapped, cashOrderAmountKrw: 10_000.4, shortageOrderAmountKrw: 10_001.6 }]);
assert.ok(decimal.includes("₩10,000") && decimal.includes("₩10,002") && decimal.includes("+₩1"));
assert.ok(!decimal.includes("+₩2"), "Subtract raw server amounts before display rounding.");
assert.equal(context.formatComparisonAmount(0.2, true), "₩0");
assert.equal(context.formatComparisonAmount(-0.2, true), "₩0");

const hidden = render([mapped], { canViewAmountData: false });
assert.deepEqual(cellTexts(hidden, "th"), cellTexts(visible, "th"));
assert.deepEqual(cellTexts(hidden, "td").slice(0, 2), cellTexts(visible, "td").slice(0, 2));
assert.deepEqual(cellTexts(hidden, "td").slice(2), ["150 EA", "100 EA", "+50 EA"], "The same column order applies without amount permissions.");
assert.ok(hidden.includes("발주수량 비교") && hidden.includes("+50 EA"));
assert.ok(!hidden.includes("₩") && !hidden.includes("1,000,000") && !hidden.includes("1,500,000"));
assert.ok(!hidden.includes("금액"), "Amount labels, values and differences all respect the permission.");
assert.equal(render([mapped], { open: false }), "");
assert.ok(render([{ ...mapped, calculable: false }]).includes("수량 차이가 없습니다."));
assert.ok(render([{ ...mapped, shortageSuggestedQty: mapped.cashSuggestedQty }]).includes("수량 차이가 없습니다."));
assert.ok(render([], { canViewAmountData: false }).includes("수량 차이가 없습니다."));

const pageRows = Array.from({ length: 11 }, (_, index) => ({ ...mapped, sku: `SYNTHETIC-${index}`, productName: `샘플 상품 ${index}` }));
assert.equal((render(pageRows).match(/<tr\b/g) ?? []).length, 11, "One header plus the unchanged ten-row page.");
assert.ok(render(pageRows).includes("1 / 2"));
const sorted = render([
  { ...mapped, sku: "SMALL", productName: "SMALL", shortageSuggestedQty: 101 },
  { ...mapped, sku: "LARGE", productName: "LARGE", shortageSuggestedQty: 200 }
]);
assert.ok(sorted.indexOf(">LARGE<") < sorted.indexOf(">SMALL<"), "Quantity-difference ordering stays unchanged.");
assert.equal(JSON.stringify(payload), originalPayload, "The comparison never changes server results.");
assert.match(source, /<ScenarioComparison\b[^>]*canViewAmountData=\{canViewAmountData\}/, "Wire the actual user permission into the dialog.");
console.log("V3 scenario comparison checks passed: server amount mapping, signed KRW difference, missing/zero values, rounding, permissions, filtering and pagination.");
