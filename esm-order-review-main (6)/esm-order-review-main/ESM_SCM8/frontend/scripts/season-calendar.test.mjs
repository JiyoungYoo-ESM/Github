import assert from "node:assert/strict";

import {
  buildSeasonCalendarRows,
  completeSeasonMonthKeys,
  daysUntilSeasonMonth,
  seasonPeakDistance
} from "../lib/season-calendar.ts";

function source(year, month, category1, category2, qty, amount, skuCount = 1) {
  return {
    year,
    month,
    기능구분1: category1,
    기능구분2: category2,
    판매수량: qty,
    판매금액: amount,
    SKU수: skuCount
  };
}

const coverage = completeSeasonMonthKeys([
  { month: "2025-01", status: "complete" },
  { month: "2025-02", status: "complete" },
  { month: "2026-01", status: "complete" },
  { month: "2026-02", status: "partial" }
]);
assert.deepEqual([...coverage].sort(), ["2025-01", "2025-02", "2026-01"]);

const rows = [
  source(2025, 1, "스킨케어", "크림", 10, 10_000, 2),
  source(2025, 1, "스킨케어", "미분류", 5, 5_000, 1),
  source(2025, 2, "스킨케어", "크림", 0, 50_000, 2),
  source(2026, 1, "스킨케어", "크림", 30, 30_000, 3),
  source(2026, 2, "스킨케어", "크림", 10_000, 1_000_000, 3),
  source(2025, 1, "미분류", "미분류", 999, 999, 1)
];

const quantity = buildSeasonCalendarRows(rows, "기능1", "qty", coverage);
assert.equal(quantity.length, 1);
assert.equal(quantity[0].metricKind, "qty");
assert.equal(quantity[0].rawValues[0], 22.5, "동월 2개년 수량은 연도 평균이어야 합니다.");
assert.equal(quantity[0].rawValues[1], 0, "완료월의 0 판매도 관측 분모에 포함해야 합니다.");
assert.equal(quantity[0].peakMonth, 1);
assert.equal(quantity[0].values[0], 11);
assert.equal(quantity[0].values[1], 2);
assert.equal(quantity[0].skuCount, 3);

const amount = buildSeasonCalendarRows(rows, "기능1", "amount", coverage);
assert.equal(amount[0].metricKind, "amount");
assert.equal(amount[0].rawValues[0], 22_500);
assert.equal(amount[0].rawValues[1], 50_000);
assert.equal(amount[0].peakMonth, 2, "선택 지표가 바뀌면 피크도 해당 지표를 따라야 합니다.");
assert.ok(amount[0].rawValues.every((value) => value < 1_000_000), "부분월의 큰 값이 반영되었습니다.");

const children = buildSeasonCalendarRows(rows, "기능2", "qty", coverage);
assert.ok(children.some((row) => row.group === "미분류"), "미분류 하위 항목을 숨기면 부모 합계와 불일치합니다.");
for (let month = 0; month < 12; month += 1) {
  const childTotal = children.reduce((sum, row) => sum + row.rawValues[month], 0);
  assert.equal(childTotal, quantity[0].rawValues[month], `${month + 1}월 부모/자식 합계가 다릅니다.`);
}

const duplicated = buildSeasonCalendarRows(
  [
    source(2025, 1, "헤어", "샴푸", 4, 40),
    source(2025, 1, "헤어", "샴푸", 6, 60)
  ],
  "기능1",
  "qty",
  new Set(["2025-01"])
);
assert.equal(duplicated[0].rawValues[0], 10, "중복 집계 행은 합산되어야 합니다.");

assert.equal(seasonPeakDistance(7, 7), 0);
assert.equal(seasonPeakDistance(1, 12), 1);
assert.equal(daysUntilSeasonMonth(7, new Date(2026, 6, 15)), 0, "현재월은 다음 해가 아니라 D-0이어야 합니다.");
assert.ok(daysUntilSeasonMonth(8, new Date(2026, 6, 15)) > 0);

console.log("season calendar regression: 30 assertions passed");
