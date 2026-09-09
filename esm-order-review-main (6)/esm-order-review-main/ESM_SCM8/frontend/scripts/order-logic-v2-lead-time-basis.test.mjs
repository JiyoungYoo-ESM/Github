// 발주 로직 V2 화면이 리드타임 실측값을 그대로 표시하는지 검증한다.
// 과거에는 응답 필드가 비면 픽스처 기본값(해운 72.9일/2.18주)으로 조용히
// 떨어져 실측 연결 실패가 정상 표시와 구분되지 않았다.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const MODEL = "components/redesign/screens/order-v2/useNewOrderLogicScreenModel.tsx";
const DRAWER = "components/redesign/screens/order-v2/OrderFormulaDrawer.tsx";
const SCREEN = "components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx";
const DURATION_FORMATTER = "lib/format-calendar-duration.ts";

function read(path) {
  return readFileSync(path, "utf8").replace(/\r\n/g, "\n");
}

const model = read(MODEL);
const drawer = read(DRAWER);
const screen = read(SCREEN);
const durationFormatter = read(DURATION_FORMATTER);

// 1. 리드타임 필드에 명세 고정값 폴백이 되살아나면 실측 실패가 감춰진다.
for (const literal of ["16.4", "36.6", "72.9", "0.68", "1.15", "2.18"]) {
  assert.ok(
    !new RegExp(`payload\\.(lt|sigma_l)[a-z_]*,\\s*${literal}`).test(model),
    `settingsFromApi가 리드타임 응답 필드에 ${literal} 폴백을 두면 안 된다`
  );
}

// 2. 실행 요청에 리드타임을 되돌려 보내면 실측 이전 값이 섞인다.
const apiSettingsBlock = model.slice(
  model.indexOf("function apiSettings"),
  model.indexOf("const ENTITY_TRANSPORT_CODES")
);
assert.ok(
  apiSettingsBlock.length > 0,
  "apiSettings 함수를 찾을 수 없다"
);
for (const field of [
  "lt_air_days",
  "lt_rail_days",
  "lt_sea_days",
  "sigma_l_air_weeks",
  "sigma_l_rail_weeks",
  "sigma_l_sea_weeks"
]) {
  assert.ok(
    !apiSettingsBlock.includes(field),
    `apiSettings가 ${field}를 서버로 되돌려 보내면 안 된다`
  );
}

// 3. 값이 없을 때 확인 필요 상태를 표시해야 한다.
assert.ok(
  model.includes("valueUnavailable"),
  "settingsFromApi가 값 미확인 상태를 표시해야 한다"
);
assert.ok(
  drawer.includes("확인 필요"),
  "리드타임 값을 확정할 수 없으면 화면에 확인 필요로 알려야 한다"
);

// 4. 실측 근거에는 표본 수와 입고완료 기간이 함께 드러나야 한다.
assert.ok(
  drawer.includes("최근 12개월 실측"),
  "실측 근거 문구가 있어야 한다"
);
assert.ok(
  drawer.includes("measuredWindowFrom") && drawer.includes("measuredWindowTo"),
  "실측 근거에 입고완료 기간이 함께 표시되어야 한다"
);

// 5. 실측 72.79일이 명세 72.9일과 같아 보이지 않도록 달력일 표시의
// 기본 소수 2자리를 유지한다.
assert.ok(
  drawer.includes("formatCalendarDuration(meanDays, { showWeeks: true })") &&
    /maximumFractionDigits = 2/.test(durationFormatter),
  "리드타임 표시는 소수 2자리를 유지해야 실측·명세값이 구분된다"
);

// 6. 실측된 운송수단에 명세 고정값 문구가 붙지 않아야 한다.
const basisIndex = drawer.indexOf("leadTimeBasis");
const basisBlock = drawer.slice(basisIndex, basisIndex + 600);
assert.ok(
  basisBlock.includes("measured"),
  "근거 문구는 실측 여부에 따라 갈라져야 한다"
);

// 7. 실제 적용값은 분석 결과가 있을 때만 표시하고, 분석 전에는 기본값을
// 현재 적용값처럼 보여주지 않는다.
assert.ok(
  drawer.includes("hasAnalysisResult ?"),
  "기준 적용값 영역은 분석 결과가 있을 때만 표시해야 한다"
);
assert.ok(
  screen.includes("hasAnalysisResult={Boolean(data) && !running}"),
  "화면은 분석 결과가 없거나 분석 중일 때 기준 적용값을 숨겨야 한다"
);

// 8. 페이지 진입 시 저장된 latest 결과를 자동으로 복원하지 않는다.
assert.ok(
  !model.includes("getLatestOrderLogicV2"),
  "페이지 진입 시 latest 결과를 자동 조회하면 안 된다"
);
assert.ok(
  !model.includes("void loadLatest()"),
  "페이지 진입 시 latest 로드 effect를 실행하면 안 된다"
);
assert.ok(
  model.includes("const [loading, setLoading] = useState(false)"),
  "초기 화면은 분석 결과 로드 대기 상태가 아니라 분석 전 상태여야 한다"
);

// 9. 법인 전환에서는 이전 법인의 완료 표시와 늦게 도착한 실행 응답을 버린다.
assert.ok(
  /analysisWasRunningRef\.current = false;\s*setAnalysisCompletedAt\(null\);\s*}, \[entityCode\]\);/.test(screen),
  "법인 전환 시 분석 완료 표시는 초기화해야 한다"
);
assert.ok(
  model.includes("const selectedEntityRef = useRef(selectedEntity);") &&
    model.includes("const entityGenerationRef = useRef(0);") &&
    model.includes("if (!isCurrentEntityRun()) return;"),
  "법인을 바꾼 뒤 이전 법인의 늦은 실행 응답을 현재 화면에 적용하면 안 된다"
);

// 10. 상단 메타데이터는 공식 적용 시나리오만 보여 혼동을 피한다.
assert.ok(
  !screen.includes('label="현재 보는 결과"'),
  "상단에 현재 보는 결과를 함께 표시하면 공식 적용 시나리오와 혼동된다"
);

// 11. 금액 비교는 단가가 없는 SKU를 0원으로 합산하지 않는다. 상단 경고는
// 중복되지 않으며, 원인 SKU와 시나리오는 각 비교 행에서 확인할 수 있다.
assert.ok(
  screen.includes("priceMissingModesForComparison"),
  "시나리오별 단가 누락 SKU를 판별해야 한다"
);
assert.ok(
  !screen.includes("발주필요금액 차이는 계산하지 않았습니다."),
  "행별 단가 누락 사유와 중복되는 상단 경고는 표시하지 않아야 한다"
);
assert.ok(
  screen.includes("단가(KRW) 누락"),
  "행별 누락 사유는 가격이 아니라 단가(KRW)로 명확히 표시해야 한다"
);
assert.ok(
  !screen.includes("가격 누락으로 비교 불가"),
  "포괄적인 가격 누락 문구 대신 SKU별 단가 누락 정보를 표시해야 한다"
);

console.log("order-logic v2 lead-time basis tests passed");
