import assert from "node:assert/strict";

import {
  buildSeasonCalendarRows,
  completeSeasonMonthKeys
} from "../lib/season-calendar.ts";
import { amountOf, category1Of, category2Of, monthKeyOf, qtyOf } from "../lib/global-demand-view-model.ts";

const API_URL = process.env.BACKTEST_URL || "http://127.0.0.1:8002/api/season-trend/latest";

function close(actual, expected, message, tolerance = 1e-6) {
  assert.ok(Number.isFinite(actual), `${message}: non-finite actual ${actual}`);
  assert.ok(Math.abs(actual - expected) <= tolerance, `${message}: ${actual} !== ${expected}`);
}

function sum(rows, getter) {
  return rows.reduce((total, row) => total + getter(row), 0);
}

function group(rows, keyOf, valueOf) {
  const totals = new Map();
  for (const row of rows) {
    const key = keyOf(row);
    totals.set(key, (totals.get(key) ?? 0) + valueOf(row));
  }
  return totals;
}

const response = await fetch(API_URL);
assert.equal(response.ok, true, `latest endpoint failed: ${response.status}`);
const payload = await response.json();
assert.equal(payload.status, "success");
assert.ok(Number(payload.analysis_schema_version) >= 5, "season cache schema is stale; rerun analysis");

const season = payload.season_analysis;
const c1 = season.category1Monthly ?? [];
const c2 = season.category2Monthly ?? [];
const c1Share = season.category1Share ?? [];
const c2Share = season.category2Share ?? [];
const coverageRows = season.monthCoverage ?? [];
assert.ok(c1.length > 0 && c2.length > 0 && coverageRows.length >= 12, "season source tables are incomplete");

let checks = 0;
for (const [name, rows, dimensions] of [
  ["category1Monthly", c1, [category1Of]],
  ["category2Monthly", c2, [category1Of, category2Of]]
]) {
  const keys = rows.map((row) => [monthKeyOf(row), ...dimensions.map((getter) => getter(row))].join("\u0000"));
  assert.equal(new Set(keys).size, keys.length, `${name}: duplicate composite keys`);
  assert.ok(rows.every((row) => /^\d{4}-\d{2}$/.test(monthKeyOf(row))), `${name}: invalid month key`);
  assert.ok(rows.every((row) => Number.isFinite(amountOf(row)) && Number.isFinite(qtyOf(row))), `${name}: non-finite metric`);
  checks += rows.length * 3;
}

const coverageMonths = coverageRows.map((row) => String(row.month));
assert.equal(new Set(coverageMonths).size, coverageMonths.length, "monthCoverage: duplicate months");
assert.ok(coverageRows.every((row) => ["complete", "partial", "missing"].includes(row.status)), "invalid coverage status");

const c1AmountByMonth = group(c1, monthKeyOf, amountOf);
const c1QtyByMonth = group(c1, monthKeyOf, qtyOf);
const c2AmountByMonth = group(c2, monthKeyOf, amountOf);
const c2QtyByMonth = group(c2, monthKeyOf, qtyOf);
for (const coverage of coverageRows) {
  const month = String(coverage.month);
  close(c1AmountByMonth.get(month) ?? 0, Number(coverage.totalAmount), `${month}: category1/coverage amount`);
  close(c1QtyByMonth.get(month) ?? 0, Number(coverage.totalQty), `${month}: category1/coverage qty`);
  close(c2AmountByMonth.get(month) ?? 0, Number(coverage.totalAmount), `${month}: category2/coverage amount`);
  close(c2QtyByMonth.get(month) ?? 0, Number(coverage.totalQty), `${month}: category2/coverage qty`);
  checks += 4;
}

const c1Parent = group(c1, (row) => `${monthKeyOf(row)}\u0000${category1Of(row)}`, qtyOf);
const c2Parent = group(c2, (row) => `${monthKeyOf(row)}\u0000${category1Of(row)}`, qtyOf);
assert.deepEqual([...c1Parent.keys()].sort(), [...c2Parent.keys()].sort(), "category1/category2 parent populations differ");
for (const [key, expected] of c1Parent) {
  close(c2Parent.get(key) ?? 0, expected, `${key}: parent/children quantity`);
  checks += 1;
}

for (const [name, rows, shareField] of [
  ["category1Share", c1Share, "qty_share_pct"],
  ["category2Share", c2Share, "qty_share_pct"]
]) {
  const sharesByMonth = group(rows, monthKeyOf, (row) => Number(row[shareField] ?? 0));
  for (const [month, total] of sharesByMonth) {
    const monthQty = sum(rows.filter((row) => monthKeyOf(row) === month), qtyOf);
    close(total, monthQty === 0 ? 0 : 100, `${name}/${month}: share sum`, 1e-5);
  }
  for (const row of rows) {
    const denominator = name === "category1Share" ? c1QtyByMonth.get(monthKeyOf(row)) : c2QtyByMonth.get(monthKeyOf(row));
    const expected = denominator ? (qtyOf(row) / denominator) * 100 : 0;
    close(Number(row[shareField]), expected, `${name}: share formula`, 1e-8);
    checks += 1;
  }
}

const completeKeys = completeSeasonMonthKeys(coverageRows);
const metricKind = payload.analysis_options?.metric === "amount" ? "amount" : "qty";
const metricOf = metricKind === "amount" ? amountOf : qtyOf;
const calendar1 = buildSeasonCalendarRows(c1, "기능1", metricKind, completeKeys);
const calendar2 = buildSeasonCalendarRows(c2, "기능2", metricKind, completeKeys);
assert.ok(calendar1.length > 0 && calendar2.length > 0, "calendar rows are empty");
for (const row of calendar1) {
  for (let month = 1; month <= 12; month += 1) {
    const keys = [...completeKeys].filter((key) => Number(key.slice(5, 7)) === month);
    const expected = keys.length
      ? sum(c1.filter((source) => keys.includes(monthKeyOf(source)) && category1Of(source) === row.group), (source) => Math.max(0, metricOf(source))) / keys.length
      : 0;
    close(row.rawValues[month - 1], expected, `${row.group}/${month}: calendar raw value`);
    checks += 1;
  }
  const maximum = Math.max(...row.rawValues);
  assert.equal(row.peakMonth, row.rawValues.indexOf(maximum) + 1, `${row.group}: peak month`);
  assert.ok(row.values.every((value) => Number.isInteger(value) && value >= 2 && value <= 11), `${row.group}: invalid intensity`);
}

const calendar2ByParent = new Map();
for (const row of calendar2) {
  const children = calendar2ByParent.get(row.parentGroup) ?? [];
  children.push(row);
  calendar2ByParent.set(row.parentGroup, children);
}
for (const parent of calendar1) {
  const children = calendar2ByParent.get(parent.group) ?? [];
  assert.ok(children.some((row) => row.group === "미분류") || !c2.some((row) => category1Of(row) === parent.group && category2Of(row) === "미분류"), `${parent.group}: unmapped child hidden`);
  for (let month = 0; month < 12; month += 1) {
    close(sum(children, (row) => row.rawValues[month]), parent.rawValues[month], `${parent.group}/${month + 1}: calendar parent/children`);
    checks += 1;
  }
}

const completeList = [...completeKeys].sort();
const anchorMonth = Number(completeList.at(-1).slice(5, 7));
const years = [...new Set(completeList.map((key) => Number(key.slice(0, 4))))]
  .filter((year) => Array.from({ length: anchorMonth }, (_, index) => `${year}-${String(index + 1).padStart(2, "0")}`).every((key) => completeKeys.has(key)))
  .sort();
const expectedYtdRows = group(
  c2.filter((row) => years.includes(Number(monthKeyOf(row).slice(0, 4))) && Number(monthKeyOf(row).slice(5, 7)) <= anchorMonth),
  (row) => `${category1Of(row)}\u0000${category2Of(row)}\u0000${monthKeyOf(row).slice(0, 4)}`,
  qtyOf
);
const ytdRows = season.ytdComparison ?? [];
assert.ok(ytdRows.length > 0, "YTD comparison is unexpectedly empty");
for (const row of ytdRows) {
  for (const year of years) {
    const key = `${category1Of(row)}\u0000${category2Of(row)}\u0000${year}`;
    close(Number(row[`YTD_수량_${year}`] ?? 0), expectedYtdRows.get(key) ?? 0, `${key}: YTD qty`);
    checks += 1;
  }
  for (let index = 1; index < years.length; index += 1) {
    const previousYear = years[index - 1];
    const currentYear = years[index];
    const previous = Number(row[`YTD_수량_${previousYear}`] ?? 0);
    const current = Number(row[`YTD_수량_${currentYear}`] ?? 0);
    const actual = row[`수량YTD성장률_${previousYear}_to_${currentYear}(%)`];
    if (previous === 0) assert.equal(actual, null, "zero-base YTD growth must be null");
    else close(Number(actual), ((current - previous) / previous) * 100, "YTD growth formula", 1e-8);
    checks += 1;
  }
}
assert.ok(!Object.keys(season.ytdComparison?.[0] ?? {}).some((key) => key.includes("2024")), "incomplete 2024 population leaked into YTD");

console.log(JSON.stringify({
  status: "passed",
  schema: payload.analysis_schema_version,
  sourceMonths: coverageRows.length,
  completeMonths: completeKeys.size,
  excludedMonths: coverageRows.length - completeKeys.size,
  category1Rows: c1.length,
  category2Rows: c2.length,
  calendarRows: calendar1.length + calendar2.length,
  ytdYears: years,
  checks
}, null, 2));
