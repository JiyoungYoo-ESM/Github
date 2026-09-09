import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const source = readFileSync(resolve("components/redesign/screens/report/reportPdfDocument.ts"), "utf8");

assert.match(source, /escapeReportHtml\(brandDisplayName\)/);
assert.match(source, /escapeReportHtml\(part\)/);
assert.match(source, /@page\{size:A4;margin:10mm\}/);
assert.match(source, /break-inside:avoid/);
assert.match(source, /page-break-inside:avoid/);
assert.match(source, /print-color-adjust:exact/);
assert.match(source, /window\.print\(\)/);

console.log("Brand report PDF document checks passed.");
