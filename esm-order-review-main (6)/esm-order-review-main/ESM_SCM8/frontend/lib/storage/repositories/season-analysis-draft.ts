import { readRawItem, writeJsonItem } from "@/lib/storage/adapter";

const ANALYSIS_DRAFT_STORAGE_KEY = "esm_scm_season_analysis_draft";

/**
 * 시즌 분석 초안을 읽는다. `createDefault`는 매번 새로 호출된다(기본값이 "최근 N개월"처럼
 * 시간에 따라 달라지므로 캐시하면 안 됨). 저장된 값과 기본값을 병합해 반환한다.
 */
export function readSeasonAnalysisDraft<T extends object>(createDefault: () => T): T {
  const raw = readRawItem("session", ANALYSIS_DRAFT_STORAGE_KEY);
  if (!raw) {
    return createDefault();
  }
  try {
    return { ...createDefault(), ...(JSON.parse(raw) as Partial<T>) };
  } catch {
    return createDefault();
  }
}

export function writeSeasonAnalysisDraft<T>(next: T): void {
  writeJsonItem("session", ANALYSIS_DRAFT_STORAGE_KEY, next);
}
