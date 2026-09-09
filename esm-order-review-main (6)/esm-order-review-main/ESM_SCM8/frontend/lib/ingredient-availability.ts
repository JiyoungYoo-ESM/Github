import { INGREDIENT_ANALYSIS_ENABLED } from "./feature-flags";

/**
 * 정적 HTML로 관리되는 사용자 가이드에서 성분 탭의 현재 제공 상태를 반영한다.
 * 비활성화 상태에서도 준비 중 안내는 보여주며, 데이터 진단의 성분 정합성 안내도 유지한다.
 */
export function applyIngredientAvailabilityToGuide(markup: string) {
  if (!INGREDIENT_ANALYSIS_ENABLED) return markup;

  return markup
    .replace(/ \(준비 중\)/g, "")
    .replace(/<div class="tip" data-ingredient-status="disabled">[\s\S]*?<\/div>/gi, "");
}
