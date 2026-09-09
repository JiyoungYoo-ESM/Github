import assert from "node:assert/strict";
import { cachedSeasonResultIsCurrent, koreaTodayString } from "../lib/season-cache-validity.ts";

// 백엔드 tests/test_season_result_cache_freshness.py와 같은 규칙이어야 한다.
// 이 층은 백엔드를 아예 호출하지 않으므로 여기서 빠지면 서버 규칙만으로는
// 묵은 결과를 막을 수 없다.

// 확정된 기간: 무기한 재사용
assert.equal(
  cachedSeasonResultIsCurrent({ computedDate: "2026-07-30", endDate: "2025-12-31", today: "2026-11-05" }),
  true,
  "끝난 연도 분석은 계속 재사용해야 한다"
);
assert.equal(
  cachedSeasonResultIsCurrent({ computedDate: "2026-07-30", endDate: "2026-07-29", today: "2026-08-02" }),
  true,
  "종료일이 어제인 결과는 계산 시점에 확정이므로 재사용해야 한다"
);

// 오늘을 포함한 기간: 그날만
assert.equal(
  cachedSeasonResultIsCurrent({ computedDate: "2026-07-30", endDate: "2026-07-30", today: "2026-07-30" }),
  true,
  "같은 날 안에서는 재사용한다"
);
assert.equal(
  cachedSeasonResultIsCurrent({ computedDate: "2026-07-30", endDate: "2026-07-30", today: "2026-07-31" }),
  false,
  "미완성 하루가 굳은 결과를 다음 날 재사용하면 안 된다"
);

// 검증 불가한 예전 결과: fail-closed
assert.equal(
  cachedSeasonResultIsCurrent({ computedDate: undefined, endDate: "2026-07-30", today: "2026-07-30" }),
  false,
  "계산 날짜가 없는 결과는 재사용하지 않는다"
);
assert.equal(
  cachedSeasonResultIsCurrent({ computedDate: "2026-07-30", endDate: null, today: "2026-07-30" }),
  false,
  "종료일이 없는 결과는 재사용하지 않는다"
);

// KST 날짜 문자열 형식
assert.match(koreaTodayString(new Date("2026-07-30T13:00:00Z")), /^\d{4}-\d{2}-\d{2}$/);
assert.equal(koreaTodayString(new Date("2026-07-30T15:30:00Z")), "2026-07-31", "UTC 15:30은 KST로 다음 날");

console.log("season cache validity tests passed.");
