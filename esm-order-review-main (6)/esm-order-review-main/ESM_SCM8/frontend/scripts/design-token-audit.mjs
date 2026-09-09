import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = process.cwd();
const scanRoots = ["app", "components", "lib"];
const exts = new Set([".ts", ".tsx"]);
const ignored = new Set([
  "lib/chart-tokens.ts",
  "lib/design-tokens.ts",
  "lib/region-groups.ts"
]);
const embeddedStylesheets = new Set(["app/manual/page.tsx"]);
const manualPalette = new Set(["#0f6e56", "#185fa5", "#854f0b", "#8b2520", "#c0392b", "#f0d5cf", "#fdf3f1", "#fff"]);
const reportTemplatePalette = new Set([
  "#05060a", "#0a9f4b", "#0f1115", "#15171a", "#303746", "#69707f", "#8a92a3", "#9aa1ad", "#c6cad1",
  "#d8dbe0", "#e2e4e8", "#e6002d", "#e8ebef", "#e90035", "#edf0f3", "#eef0f5", "#f0f1f4",
  "#f1f2f4", "#f3f4f6", "#f7f8fa", "#fafbfc", "#fff"
]);

function rawHexColors(line) {
  return [...line.matchAll(/#[0-9a-fA-F]{3,8}/gu)].map((match) => match[0].toLowerCase());
}

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    const stat = statSync(path);
    if (stat.isDirectory()) out.push(...walk(path));
    else if ([...exts].some((ext) => path.endsWith(ext))) out.push(path);
  }
  return out;
}

const violations = [];

for (const scanRoot of scanRoots) {
  for (const file of walk(join(root, scanRoot))) {
    const rel = relative(root, file).replace(/\\/g, "/");
    if (ignored.has(rel)) continue;
    const text = readFileSync(file, "utf8");
    const lines = text.split(/\r?\n/);
    let independentReportTemplate = false;
    lines.forEach((line, index) => {
      if (line.includes("design-token-audit: report-template-start")) independentReportTemplate = true;
      if (line.includes("design-token-audit: report-template-end")) independentReportTemplate = false;
      if (independentReportTemplate) {
        rawHexColors(line)
          .filter((color) => !reportTemplatePalette.has(color))
          .forEach((color) => violations.push(`${rel}:${index + 1} unapproved report-template color ${color}`));
        return;
      }
      if (/(bg|text|border|ring|from|to|via)-\[#/u.test(line)) {
        violations.push(`${rel}:${index + 1} arbitrary Tailwind color class`);
      }
      const embeddedStylesheetDeclaration = embeddedStylesheets.has(rel) && line.startsWith("const manualStyles = ");
      if (embeddedStylesheetDeclaration) {
        rawHexColors(line)
          .filter((color) => !manualPalette.has(color))
          .forEach((color) => violations.push(`${rel}:${index + 1} unapproved embedded-stylesheet color ${color}`));
      }
      if (!embeddedStylesheetDeclaration && /["'`][^"'`]*#[0-9a-fA-F]{3,8}/u.test(line)) {
        violations.push(`${rel}:${index + 1} raw hex color outside token file`);
      }
    });
  }
}

if (violations.length > 0) {
  console.error("Design token audit failed:");
  violations.forEach((item) => console.error(`- ${item}`));
  process.exit(1);
}

console.log("Design token audit passed.");
