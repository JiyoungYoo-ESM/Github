import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import ts from "typescript";

const require = createRequire(import.meta.url);
const source = readFileSync("components/redesign/screens/order-v3/OrderV3Screen.tsx", "utf8");
const ast = ts.createSourceFile("OrderV3Screen.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let selectorNode;
let brandsNode;
function visit(node) {
  if (ts.isJsxSelfClosingElement(node) && node.tagName.getText(ast) === "BrandSearchSelect") selectorNode = node;
  if (ts.isVariableDeclaration(node) && node.name.getText(ast) === "brands") brandsNode = node;
  ts.forEachChild(node, visit);
}
visit(ast);
assert.ok(selectorNode, "V3 must use the searchable brand selector.");
assert.ok(brandsNode);
assert.ok(source.includes("const summaryRows = useMemo("), "V3 summary cards must derive a brand-scoped result set.");
assert.ok(source.includes("row.brand === brand"), "V3 summary scope must match the selected brand exactly.");
assert.ok(source.includes("<ReviewSummary rows={summaryRows}"), "V3 summary cards must receive the brand-scoped result set.");

const compile = code => ts.transpileModule(code, {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
}).outputText;
const context = {
  require, exports: {}, BrandSearchSelect: () => null,
  useMemo: fn => fn(), brand: "all", page: 3,
  rows: ["가나다", "Alpha Beauty", "Beta", "Alpha Beauty"].map(brand => ({ brand })),
  setBrand(value) { context.brand = value; }, setPage(value) { context.page = value; }
};
vm.createContext(context);
vm.runInContext(compile(`const brands = ${brandsNode.initializer.getText(ast)}; function renderFilter() { return ${selectorNode.getText(ast)}; }`), context);
const props = context.renderFilter().props;
assert.deepEqual(Array.from(props.options), ["Alpha Beauty", "Beta", "가나다"], "Search all brands in the completed analysis, not only the current review tab or page.");
assert.equal(props.allLabel, "전체 브랜드");
assert.equal(props.allValue, "all");
assert.equal(props.dropdownAlign, "responsive");
props.onChange("Beta");
assert.equal(context.brand, "Beta");
assert.equal(context.page, 1, "Changing brand returns to page one.");
assert.ok(!source.includes('<section className="overflow-hidden rounded-[12px] border border-border bg-white shadow-card">'), "The review card must not clip the brand dropdown.");
const scenarioHandler = source.match(/  const changeScenario = \(nextScenario: OrderV3Scenario\) => \{[\s\S]*?\n  \};/)?.[0];
assert.ok(scenarioHandler, "V3 must retain an explicit scenario change handler.");
assert.ok(!scenarioHandler.includes('setBrand("all")'), "Changing scenarios must preserve the selected brand filter.");

// Exercise the actual component and its event handlers with a small hook harness.
const states = [];
let cursor = 0;
const react = {
  ...React,
  useState(initial) {
    const index = cursor++;
    if (!(index in states)) states[index] = initial;
    return [states[index], next => { states[index] = typeof next === "function" ? next(states[index]) : next; }];
  },
  useMemo: fn => fn(), useRef: () => ({ current: null }), useEffect: () => {}
};
const selectorContext = {
  exports: {},
  require(name) {
    if (name === "react") return react;
    if (name === "@/lib/utils") return { cn: (...values) => twMerge(clsx(values)) };
    return require(name);
  }
};
vm.createContext(selectorContext);
vm.runInContext(compile(readFileSync("components/redesign/shared/BrandSearchSelect.tsx", "utf8")), selectorContext);
const render = (extra = {}) => {
  cursor = 0;
  return selectorContext.exports.BrandSearchSelect({ ...props, value: context.brand, ...extra });
};
function elements(node) {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!React.isValidElement(node)) return [];
  return [node, ...elements(node.props.children)];
}
const find = (tree, predicate) => elements(tree).find(predicate);
const trigger = tree => find(tree, node => node.props["data-testid"] === "order-v3-brand-filter");
const input = tree => find(tree, node => node.type === "input");
const options = tree => elements(tree).filter(node => node.props.role === "option");
const labels = tree => options(tree).map(node => node.props.children);

let tree = render();
assert.equal(trigger(tree).props["aria-expanded"], false);
assert.ok(trigger(tree).props.className.includes("h-10"));
assert.ok(!trigger(tree).props.className.includes("h-[38px]"), "V3 overrides must preserve filter height.");
trigger(tree).props.onClick();
tree = render();
assert.equal(trigger(tree).props["aria-expanded"], true);
assert.ok(find(tree, node => node.props.className?.includes("left-0 lg:left-auto lg:right-0")), "Align with the left-stacked filters until V3 switches to a horizontal row at lg.");
assert.deepEqual(labels(tree), ["전체 브랜드", "Alpha Beauty", "Beta", "가나다"]);
input(tree).props.onChange({ target: { value: "  aLPHa  " } });
tree = render();
assert.deepEqual(labels(tree), ["Alpha Beauty"], "Search ignores letter case and surrounding spaces.");
options(tree)[0].props.onClick();
tree = render();
assert.equal(context.brand, "Alpha Beauty");
assert.equal(trigger(tree).props["aria-expanded"], false);
trigger(tree).props.onClick();
tree = render();
assert.equal(input(tree).props.value, "", "Reopening clears the previous search.");
input(tree).props.onChange({ target: { value: "나다" } });
tree = render();
assert.deepEqual(labels(tree), ["가나다"], "Korean partial names are searchable.");
input(tree).props.onChange({ target: { value: "no-match" } });
tree = render();
assert.equal(options(tree).length, 0);
assert.ok(find(tree, node => node.type === "p" && node.props.children === "검색 결과가 없습니다."));
find(tree, node => node.props["aria-label"] === "브랜드 검색어 지우기").props.onClick();
tree = render();
assert.equal(labels(tree).length, 4);
options(tree)[0].props.onClick();
assert.equal(context.brand, "all", "The all-brands option resets the filter.");
tree = render();
trigger(tree).props.onClick();
tree = render();
tree.props.onKeyDown({ key: "Escape" });
assert.equal(trigger(render()).props["aria-expanded"], false);
trigger(render()).props.onClick();
tree = render({ options: [] });
assert.deepEqual(labels(tree), ["전체 브랜드"], "Empty results still allow all-brands selection.");
console.log("V3 brand search checks passed: full-list options, page reset, styling, Korean/English search, selection, clear, empty results and Escape.");
