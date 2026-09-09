import { readRawItem, writeJsonItem } from "@/lib/storage/adapter";
import { DEFAULT_FAVORITE_NAV_IDS, FAVORITE_NAV_STORAGE_KEY } from "@/components/redesign/lib/nav-config";
import type { Screen } from "@/components/redesign/lib/types";

/**
 * 저장된 즐겨찾기 탭 목록을 읽는다.
 *
 * 저장된 값이 없으면 `null`을 반환한다(호출자가 현재 상태를 그대로 유지해야 함을
 * 뜻한다) — "저장값 없음"과 "저장값이 있지만 파싱 실패"를 구분해야 하기 때문이다.
 * 파싱에 실패하면 기본 즐겨찾기 목록으로 폴백한다. `validScreenIds`에 없는 값은
 * 걸러낸다(예: 화면이 삭제된 경우). 예전에 자동으로 저장된 brand/cross 기본값은
 * 한 번만 빈 목록으로 마이그레이션한다.
 */
export function readFavoriteNavIds(validScreenIds: readonly Screen[]): Screen[] | null {
  const raw = readRawItem("local", FAVORITE_NAV_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as Screen[];
    const validIds = Array.from(new Set(parsed.filter((id) => validScreenIds.includes(id))));
    const isLegacyDefault = validIds.length === 2 && validIds.includes("brand") && validIds.includes("cross");
    return isLegacyDefault ? [] : validIds;
  } catch {
    return DEFAULT_FAVORITE_NAV_IDS;
  }
}

export function writeFavoriteNavIds(ids: readonly Screen[]): void {
  writeJsonItem("local", FAVORITE_NAV_STORAGE_KEY, ids);
}
