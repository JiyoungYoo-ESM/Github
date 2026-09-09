import { getActiveEntityCode } from "./entity-session.ts";
import { formatNumber } from "./utils.ts";

// 저기준(low base) 금액 컷오프.
// 비교 기간 매출이 이 값 미만이면 성장률 %가 소음이 되므로 순위·표시에서 "기저 미미/낮은
// 기준값"으로 다룬다. 기존 EUR 기준 €500과 같은 취지의 통화별 하한선이다.
//   - HQ(원화): ₩1,000,000
//   - 그 외(EUR/USD): 500
// 수량 기저 하한선(LOW_BASE_QTY)은 통화와 무관하므로 여기서 다루지 않는다.
export function lowBaseAmount(): number {
  return getActiveEntityCode() === "HQ" ? 1_000_000 : 500;
}

// 사용자 안내 문구용 라벨. 활성 법인 통화 기호로 표기한다(₩ / $ / €).
export function lowBaseAmountLabel(): string {
  const entityCode = getActiveEntityCode();
  const symbol = entityCode === "HQ" ? "₩" : entityCode === "USA" ? "$" : "€";
  return `${symbol}${formatNumber(lowBaseAmount(), 0)}`;
}
