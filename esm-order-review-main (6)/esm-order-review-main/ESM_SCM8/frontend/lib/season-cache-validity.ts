/**
 * 브라우저에 저장된 분석 결과를 재사용해도 되는지 판정한다.
 *
 * 백엔드 `season_cache_service.cached_result_is_current`와 동일한 규칙이어야
 * 한다. 이 층은 백엔드를 아예 호출하지 않으므로, 여기서 규칙이 빠지면 서버
 * 규칙만으로는 묵은 결과를 막을 수 없다.
 *
 * 원칙: 그 결과가 만들어진 뒤로 원천 데이터가 더 변할 수 없을 때만 재사용한다.
 * - 계산 시점에 분석 기간이 이미 끝나 있었다면 그 기간 판매는 확정이므로
 *   무기한 재사용한다.
 * - 계산한 날이 분석 기간 안에 있었다면 마지막 하루가 미완성 상태로 굳은
 *   결과다. 같은 날 안에서만 재사용하고, 날짜가 바뀌면 재계산한다.
 *
 * 계산 날짜를 모르는 예전 결과는 검증할 수 없으므로 재사용하지 않는다.
 */
/**
 * KST 기준 오늘 날짜(YYYY-MM-DD).
 *
 * `components/redesign/lib/workspace-format.ts`의 `koreaDateString`과 같은
 * 구현이다. `lib/api`는 components 층을 import하지 않으므로 여기에 둔다.
 */
export function koreaTodayString(date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(date);
}

export function cachedSeasonResultIsCurrent({
  computedDate,
  endDate,
  today
}: {
  computedDate: string | null | undefined;
  endDate: string | null | undefined;
  today: string;
}): boolean {
  if (!computedDate || !endDate) return false;
  if (computedDate > endDate) return true;
  return computedDate === today;
}
