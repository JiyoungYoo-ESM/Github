import { readFileSync } from "node:fs";

const MODULE_COMPANIONS = {
  "components/redesign/screens/country/CountryScreenExact.tsx": [
    "components/redesign/screens/country/useCountryScreenModel.tsx"
  ],
  "components/redesign/screens/brand/BrandScreenExact.tsx": [
    "components/redesign/screens/brand/useBrandScreenModel.tsx"
  ]
};

function readNormalized(path) {
  return readFileSync(path, "utf8").replace(/\r\n/g, "\n");
}

function read(path) {
  const files = [path, ...(MODULE_COMPANIONS[path] ?? [])];
  return files.map(readNormalized).join("\n");
}

function expectContains(file, needle, message) {
  const text = read(file);
  if (!text.includes(needle)) {
    console.error(`FAIL ${message}\n  Missing: ${needle}\n  File: ${file}`);
    process.exitCode = 1;
  }
}

function expectNotContains(file, needle, message) {
  const text = read(file);
  if (text.includes(needle)) {
    console.error(`FAIL ${message}\n  Unexpected: ${needle}\n  File: ${file}`);
    process.exitCode = 1;
  }
}

function expectFileNotContains(file, needle, message) {
  const text = readNormalized(file);
  if (text.includes(needle)) {
    console.error(`FAIL ${message}\n  Unexpected: ${needle}\n  File: ${file}`);
    process.exitCode = 1;
  }
}

function expectMatches(file, pattern, message) {
  const text = read(file);
  if (!pattern.test(text)) {
    console.error(`FAIL ${message}\n  Missing pattern: ${pattern}\n  File: ${file}`);
    process.exitCode = 1;
  }
}

function expectBefore(file, first, second, message) {
  const text = read(file);
  const firstIndex = text.indexOf(first);
  const secondIndex = text.indexOf(second);
  if (firstIndex < 0 || secondIndex < 0 || firstIndex >= secondIndex) {
    console.error(`FAIL ${message}\n  Expected order: ${first} -> ${second}\n  File: ${file}`);
    process.exitCode = 1;
  }
}

expectContains("components/sku-concentration/SkuConcentrationClient.tsx", "useSearchParams", "SKU 집중도 필터는 URL 상태를 사용해야 함");
expectContains("components/layout/GlobalSkuSearch.tsx", "target === \"orderReview\"", "전역검색은 발주검토 목적지를 제공해야 함");
expectContains("components/layout/GlobalSkuSearch.tsx", "target === \"skuConcentration\"", "전역검색은 SKU 집중도 목적지를 제공해야 함");
expectContains("app/integrated-order-review/IntegratedOrderTable.tsx", "getOrderWorkflowState", "통합 발주는 발주 검토 목록을 읽어야 함");
expectContains("app/integrated-order-review/IntegratedOrderTable.tsx", "발주 검토 목록 {queuedSkus.length}개", "통합 발주는 사용자에게 발주 검토 목록으로 안내해야 함");
expectNotContains("app/integrated-order-review/IntegratedOrderTable.tsx", "검토 큐", "통합 발주 화면에 내부 용어인 검토 큐를 표시하지 않아야 함");
expectContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", "분석을 실행하면 발주 검토 목록이 표시됩니다.", "V3 분석 전에는 발주 검토 목록이 표시될 것을 안내해야 함");
expectContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", "상단의 ‘분석 실행’ 버튼을 눌러 주세요.", "V3 분석 전에는 사용자가 눌러야 할 버튼을 간단히 안내해야 함");
expectNotContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", "검토 큐", "V3 화면에 내부 용어인 검토 큐를 표시하지 않아야 함");
expectNotContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", "계획발주", "V3 화면과 Excel에 오해를 부르는 계획발주 문구를 표시하지 않아야 함");
expectNotContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", '"계획"', "V3 상품 행에서 계획이라는 보조 문구도 제거해야 함");
expectContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", 'useState<OrderV3ReviewView>("needed")', "V3는 발주가 필요한 상품 목록으로 시작해야 함");
expectNotContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", "RiskLegend", "V3의 중복 전체·발주 필요 필터를 제거해야 함");
expectNotContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", ">발주 상태</th>", "V3 표의 반복 발주 상태 열을 제거해야 함");
expectNotContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", "<RiskBadge", "V3 모바일과 데스크톱에 반복 발주 필요 배지를 표시하지 않아야 함");
expectNotContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", '"주의"', "V3 화면과 Excel에 계산 기준이 없는 주의 상태를 표시하지 않아야 함");
expectNotContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", '"긴급"', "V3 발주 필요 상태를 긴급으로 과장해 표시하지 않아야 함");
expectNotContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", "위험도", "V3 발주 여부를 별도 위험도 계산 결과처럼 안내하지 않아야 함");
expectContains("components/redesign/screens/order-v3/reviewList.ts", 'if (row.signal === "즉시 발주") return "needed";', "V3 발주 검토 목록은 API의 발주 필요 신호만 사용해야 함");
expectContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", 'if (row.signal === "즉시 발주") return "발주 필요";', "V3 화면과 Excel은 긴급 대신 발주 필요로 표시해야 함");
expectContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", 'return "상태 확인 필요";', "V3 예상 밖 신호를 정상 발주 판정으로 위장하지 않아야 함");
expectContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", 'aria-label="다른 상품 목록"', "V3 발주 불필요·보류·차단 목록을 별도로 확인할 수 있어야 함");
expectContains("components/redesign/screens/order-v3/reviewList.ts", 'if (row.calculable === false) return "excluded";', "V3 보류·차단 상품을 발주 불필요 상품과 별도로 분류해야 함");
expectContains("components/redesign/screens/order-v3/reviewList.ts", 'if (row.signal === "발주 제외") return "not-needed";', "V3 발주 제외 상품의 화면 상태는 발주 불필요여야 함");
expectContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", 'if (row.signal === "발주 제외") return "발주 불필요";', "V3 화면과 Excel에 발주 불필요 상태를 명확하게 표시해야 함");
expectContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", 'row.dataStatus === "발주보류" ? "발주 보류" : "계산 차단"', "V3 보류·차단 상품의 실제 사유 상태를 유지해야 함");
expectContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", 'showExclusionReasons={showExclusionReasons}', "V3 보류·차단 상품의 별도 사유 확인 기능을 유지해야 함");
expectNotContains("components/redesign/screens/order-v3/OrderV3EvidenceDrawer.tsx", "row.validationCode", "V3 보류·차단 사유 안내 아래에 내부 오류코드를 표시하지 않아야 함");
expectContains("components/redesign/screens/order-v3/OrderV3EvidenceDrawer.tsx", 'row.validationError || "필수 원천 또는 정책값이 확정되지 않았습니다."', "V3 보류·차단 사유의 한국어 안내를 유지해야 함");
expectContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", '발주가 필요한 상품이 없습니다.', "V3 발주 필요 상품이 없는 정상 결과를 명확히 안내해야 함");
expectContains("components/redesign/screens/order-v3/OrderV3Screen.tsx", 'const exportRows = reviewExportRows(filteredRows, selectedSkus);', "V3 엑셀은 현재 표시 목록과 선택 범위만 내보내야 함");
expectContains("components/analysis/AnalysisReadinessBanner.tsx", "발주 분석 완료", "선행조건 배너가 발주 분석 상태를 표시해야 함");
expectContains("components/redesign/lib/workspace-format.ts", "excludePartialMonths: false", "최신 판매일이 포함되도록 경계 월을 제외하지 않아야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "판매 데이터 기준", "브랜드 PDF는 실제 판매 데이터 기준일을 표시해야 함");
expectContains("lib/api/storage.ts", 'SEASON_TREND_STORAGE_VERSION = "6"', "과거 대용량 브라우저 저장 결과를 재사용하지 않아야 함");
expectContains("lib/api/storage.ts", "download_url?: string | null", "최신 발주 결과에서 전체 파일 다운로드 링크를 복구해야 함");
expectContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", "etaReferenceText(row)", "V2 입고·소진 참고 열은 ETA 상태와 날짜를 함께 표시해야 함");
expectContains("components/redesign/screens/order-v2/useNewOrderLogicScreenModel.tsx", '"ETA 미확인"', "V2 운송중 물량의 ETA를 계산할 수 없으면 확인 필요로 표시해야 함");
expectContains("components/redesign/screens/order-v2/useNewOrderLogicScreenModel.tsx", '"입고 예정 없음"', "V2 운송중 물량이 없으면 입고 예정 없음으로 표시해야 함");
expectMatches(
  "components/redesign/screens/order-v2/useNewOrderLogicScreenModel.tsx",
  /numberOr\(official\.incoming_qty\) > 0\s*\|\|\s*numberOr\(official\.transit_qty\) > 0/,
  "V2 미입고 또는 운송중 물량의 ETA가 없으면 입고 예정 없음으로 표시하면 안 됨"
);
expectContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", 'const demandAverageLabel = isHqEntity ? "일평균" : "주평균";', "HQ V2 수요 레이블은 일평균이어야 함");
expectContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", 'const depletionUnit = isHqEntity ? "일" : "주";', "HQ V2 고갈 참고값은 일 단위여야 함");
expectContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", '"고갈일수(참고)"', "HQ V2 고갈 참고값 레이블은 일수여야 함");
expectContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", '"미입고/입고예정 수량"', "HQ·EU·USA V2 재고 구성은 계산용 입고예정 합계를 합의된 사용자 문구로 표시해야 함");
expectContains("components/redesign/screens/order-v2/OrderFormulaDrawer.tsx", '입고예정 = ① 미입고 + ② PNFM확정 + ③ 입고진행중', "HQ·EU·USA V2 산식 설명은 승인된 ①+②+③ 입고예정을 표시해야 함");
expectContains("components/redesign/screens/order-v2/OrderFormulaDrawer.tsx", '운송중 제외', "HQ V2 산식 설명은 운송중을 IP에서 제외한다고 명시해야 함");
expectFileNotContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", 'ETA {row.nextEta ? formatPeriodDate(row.nextEta) : "-"}', "V2 ETA를 대시로 숨기면 안 됨");
expectFileNotContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", 'label="API 조회시간"', "V2 화면에 내부 API 조회시각을 노출하지 않아야 함");
expectFileNotContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", 'label="계산 완료 시각"', "V2 화면에 계산 완료시각 칩을 노출하지 않아야 함");
expectFileNotContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", "데이터상태: 전체", "V2 발주 제안과 시나리오 비교에서 데이터상태 필터를 제거해야 함");
expectFileNotContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", "등급: 전체", "V2 발주 제안과 시나리오 비교에서 등급 필터를 제거해야 함");
expectFileNotContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", "발주신호: 전체", "V2 발주 제안과 시나리오 비교에서 발주신호 필터를 제거해야 함");
expectFileNotContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", '"발주신호 비교"', "V2 시나리오 비교 표에서 발주신호 비교 열을 제거해야 함");
expectContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", "if (canViewAmountData)", "V2 발주필요금액 정렬은 금액 조회 권한이 있는 계정에만 적용해야 함");
expectContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", "return rightAmount - leftAmount", "V2 금액 권한 계정은 발주필요금액 내림차순으로 정렬해야 함");
expectMatches(
  "components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx",
  /const officialSummary = useMemo\(\(\) =>[\s\S]*?for \(const row of filteredRows\)[\s\S]*?\}, \[appliedMode, filteredRows, krwFactor\]\);/,
  "V2 상단 KPI는 선택한 브랜드의 필터 행만 집계해야 함"
);
expectMatches(
  "components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx",
  /const comparisonSummary = useMemo\(\(\) =>[\s\S]*?for \(const row of filteredRows\)[\s\S]*?\}, \[appliedMode, filteredRows, krwFactor, referenceMode\]\);/,
  "V2 시나리오 비교 KPI도 선택한 브랜드의 필터 행만 집계해야 함"
);
expectContains(
  "components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx",
  'const EXCLUDED_BRANDS = new Set(["기타제조사"]);',
  "V2에서 기타제조사 브랜드를 제외해야 함"
);
expectContains(
  "components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx",
  "const visibleRows = useMemo",
  "V2는 제외 브랜드를 표와 집계에서 함께 숨겨야 함"
);
expectContains(
  "components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx",
  "!EXCLUDED_BRANDS.has(row.brand.trim())",
  "V2는 기타제조사 행을 렌더링 대상에서 제외해야 함"
);
expectContains("components/redesign/SiliconAnalyticsWorkspace.tsx", 'canViewAmountData', "V2 발주분석은 모든 발주분석 계정에 금액을 표시해야 함");
expectContains("components/redesign/SiliconAnalyticsWorkspace.tsx", 'canEditAdvancedSettings={canViewAmountData}', "V2 고급 산식 설정은 법인과 무관하게 발주분석 권한 계정에 열려 있어야 함");
expectContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", "{canEditAdvancedSettings ? (", "일반계정의 V2 설정 탭에서는 고급 산식 설정을 숨겨야 함");
expectContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", '"선택한 시나리오 적용"', "일반계정은 V2 설정 탭에서 시나리오만 적용할 수 있어야 함");
expectContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", "발주 산식 보기", "V2 화면에서 발주 산식 패널을 열 수 있어야 함");
expectFileNotContains("components/redesign/screens/order-v2/OrderFormulaDrawer.tsx", "교과서 최종검증판", "V2 산식 패널 상단에 최종검증판 출처 카드를 노출하지 않아야 함");
expectFileNotContains("components/redesign/screens/order-v2/OrderFormulaDrawer.tsx", "실제 파일의 설정값은 갱신될 수 있습니다.", "V2 산식 패널 하단에 출처 안내 박스를 노출하지 않아야 함");
expectContains("components/redesign/screens/order-v2/OrderFormulaDrawer.tsx", "목표재고(S) - 보유전체(IP)", "V2 산식 패널은 교과서 용어로 최종 발주량을 요약해야 함");
expectContains("components/redesign/screens/order-v2/OrderFormulaDrawer.tsx", "CEILING(MAX(0, S - IP), 1)", "V2 산식 패널은 순수 R/S 부족분을 MOQ 없이 낱개 단위 올림해야 함");
expectFileNotContains("components/redesign/screens/order-v2/OrderFormulaDrawer.tsx", "MOQ", "V2 산식 패널에서 미확정 MOQ를 표시하면 안 됨");
expectFileNotContains("components/redesign/screens/order-v2/OrderFormulaDrawer.tsx", "상한Q = CEILING(MAX(0, S - (IP - 미입고)), 1)", "V2 산식 패널에서 상한수량을 노출하지 않아야 함");
expectFileNotContains("components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx", "result.upperSuggestedQty", "V2 발주 제안 화면에서 상한수량 컬럼을 노출하지 않아야 함");
expectContains("components/redesign/screens/order-v2/useNewOrderLogicScreenModel.tsx", "row.upper_suggested_qty", "V2 화면 모델은 API 상한수량을 사용해야 함");
expectContains("components/redesign/screens/order-v2/OrderFormulaDrawer.tsx", 'aria-modal="true"', "V2 산식 패널은 모달 대화상자로 노출해야 함");
// 세션 복구 결과 조립은 prepScreenModel 한 곳에만 있다(워크스페이스 훅의 복사본은 제거됨).
expectContains("components/redesign/screens/prep/prepScreenModel.ts", "latestMeta?.downloadUrl", "복구된 발주 결과가 전체 파일 다운로드 링크를 유지해야 함");
// FAQ id를 하드코딩하면 supportData에 같은 id가 추가될 때 React key가 겹치고 아코디언이 함께 펼쳐진다.
expectContains("components/redesign/screens/support/useSupportScreenModel.tsx", "const SYNTHETIC_FAQ_ID = Math.max(", "플래그로 끼워 넣는 FAQ id는 supportData에서 파생시켜야 함");
expectFileNotContains("components/redesign/screens/support/useSupportScreenModel.tsx", "id: 94", "FAQ id를 하드코딩하면 안 됨");
// 법인 전환·로그아웃에서 우리가 끊은 요청은 실패로 표시하면 안 된다.
expectContains("lib/api/transport.ts", "export function isAbortError", "취소된 요청을 판별하는 헬퍼가 있어야 함");
expectContains("components/redesign/workspace/useWorkspaceExchangeRate.ts", "if (isAbortError(error))", "환율 조회 취소는 실패로 표시하지 않아야 함");
expectContains("components/redesign/SiliconAnalyticsWorkspace.tsx", "if (isAbortError(error))", "워크스페이스 환율 조회 취소도 실패로 표시하지 않아야 함");
expectFileNotContains("components/redesign/workspace/useWorkspaceAnalysisSession.ts", "includeLatestFallback: true", "워크스페이스 진입 시 과거 발주 결과를 자동 복구하지 않아야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "SkuNameWithCode", "상위 SKU 카드에는 상품명과 상품코드를 함께 표시해야 함");
expectContains("components/redesign/screens/country/CountryScreenExact.tsx", '국가 성장 ${countryGrowthBasis === "yoy" ? "YoY" : "QoQ"} 자동 비교 분기', "국가 성장 YoY·QoQ는 기준 분기에 따라 비교 분기를 자동 설정해야 함");
expectContains("components/redesign/screens/country/useCountryScreenData.ts", "season?.monthCoverage ?? EMPTY_ROWS", "국가 성장률은 월 완결성 메타데이터를 읽어야 함");
expectContains("components/redesign/screens/country/country-quarter-growth.ts", "monthsForQuarter(quarter).every", "국가 성장률 비교 분기는 3개 월이 모두 완료되어야 함");
expectContains("components/redesign/screens/country/CountryScreenExact.tsx", "낮은 기준값으로 표시하며 순위에는 포함", "낮은 기준값 국가는 숨기지 않고 경고와 함께 성장 순위에 포함해야 함");
expectFileNotContains("components/redesign/screens/country/CountryScreenExact.tsx", "비교 분기 매출 없음", "비교 분기 매출이 없는 국가는 화면에 별도 노출하지 않아야 함");
expectContains("components/redesign/screens/country/CountryScreenExact.tsx", "signedEur(row.deltaAmount)", "국가 성장 순위는 정렬 기준인 매출 증감액을 대표 숫자로 표시해야 함");
expectContains("components/redesign/screens/country/CountryScreenExact.tsx", "signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate)", "국가별 매출 증감액에는 원화 환산값을 함께 표시해야 함");
expectFileNotContains("components/redesign/screens/country/CountryScreenExact.tsx", "krwEokValueFromEur(row.previousAmount, averageEurKrwRate)", "국가 성장 순위에 전후 원화 금액까지 반복해 가독성을 낮추면 안 됨");
expectContains("components/redesign/screens/country/CountryScreenExact.tsx", 'countryQuarterTrend.length >= 4 ? "최근 분기별 매출 추세" : "분기 매출 비교"', "완료 분기가 4개 미만이면 추세가 아닌 분기 비교로 표시해야 함");
expectNotContains("components/redesign/screens/country/CountryScreenExact.tsx", '{row.yoy ?? "-"}', "YoY를 계산할 수 없는 분기의 대시 표시는 숨겨야 함");
expectNotContains("components/redesign/screens/country/useCountryScreenModel.tsx", "!row.lowBase && !row.newEntry", "낮은 기준값 국가는 성장 순위에서 제외하면 안 됨");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", '브랜드 성장 ${brandGrowthBasis === "yoy" ? "YoY" : "QoQ"} 자동 비교 분기', "브랜드 성장 YoY·QoQ는 기준 분기에 따라 비교 분기를 자동 설정해야 함");
expectContains("components/redesign/screens/brand/useBrandScreenModel.tsx", "completeQuarterKeys(brandGrowthMonthOptions)", "브랜드 성장률 비교 분기는 3개 월이 모두 완료되어야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "낮은 기준값으로 표시하며 순위에는 포함", "낮은 기준값 브랜드는 숨기지 않고 경고와 함께 성장 순위에 포함해야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "signedEur(row.deltaAmount)", "브랜드 성장 순위는 정렬 기준인 매출 증감액을 대표 숫자로 표시해야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "signedKrwEokFromEur(row.deltaAmount, averageEurKrwRate)", "브랜드별 매출 증감액에는 원화 환산값을 함께 표시해야 함");
expectFileNotContains("components/redesign/screens/brand/BrandScreenExact.tsx", "krwEokValueFromEur(row.previousAmount, averageEurKrwRate)", "브랜드 성장 순위에 전후 원화 금액까지 반복해 가독성을 낮추면 안 됨");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", 'brandQuarterTrend.length >= 4 ? "최근 분기별 브랜드 매출 추세" : "브랜드 분기 매출 비교"', "브랜드 완료 분기가 4개 미만이면 추세가 아닌 분기 비교로 표시해야 함");
expectContains("components/redesign/screens/country/country-quarter-growth.ts", "previousYearQuarterKey", "국가 YoY는 기준 분기의 전년도 동일 분기를 사용해야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "previousMonthKey(brandMomTargetMonth)", "브랜드 MoM은 기준월의 직전 월을 사용해야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "comparisonNoSalesBrandRows", "비교 분기 매출이 없는 브랜드는 성장률 순위와 분리해야 함");
expectFileNotContains("components/redesign/screens/brand/BrandScreenExact.tsx", "비교 분기 매출 없음", "비교 분기 매출이 없는 브랜드는 화면에 별도 노출하지 않아야 함");
expectContains("components/redesign/shared/RankingDetailDialog.tsx", 'role="dialog"', "전체 순위는 카드 내부 확장이 아닌 독립 대화상자로 표시해야 함");
expectContains("components/redesign/shared/RankingDetailDialog.tsx", 'aria-modal="true"', "전체 순위 대화상자는 보조기기에 모달로 전달되어야 함");
expectContains("components/redesign/shared/RankingDetailDialog.tsx", "순위", "전체 순위 화면에는 순위 열이 있어야 함");
expectContains("components/redesign/shared/RankingDetailDialog.tsx", "점유율", "전체 순위 화면에는 점유율 열이 있어야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "RankingDetailOpenButton", "브랜드 Top 5 카드에서 전체 순위를 열 수 있어야 함");
expectContains("components/redesign/screens/brand/useBrandScreenModel.tsx", "const selectedSkuRows = allSelectedSkuRows.slice(0, 5)", "브랜드 기본 카드는 Top 5를 유지해야 함");
expectContains("components/redesign/screens/country/CountryScreenExact.tsx", "RankingDetailOpenButton", "국가 상세 Top 5 카드에서 전체 순위를 열 수 있어야 함");
expectContains("components/redesign/screens/country/useCountryScreenModel.tsx", "const selectedBrandRows = allSelectedBrandRows.slice(0, 5)", "국가 기본 카드는 Top 5를 유지해야 함");
expectContains("components/redesign/screens/sku/SkuScreenExact.tsx", "RankingDetailOpenButton", "SKU 국가 분포에서 전체 순위를 열 수 있어야 함");
expectContains("components/redesign/screens/sku/useSkuScreenModel.tsx", "const countryShares = allCountryShares.slice(0, 5)", "SKU 국가 분포 기본 카드는 Top 5를 유지해야 함");
expectContains("components/redesign/lib/nav-config.ts", '{ id: "category", label: "제품군"', "분석 탭에 제품군 메뉴가 SKU 다음에 있어야 함");
expectContains("components/redesign/screens/category/CategoryScreenExact.tsx", "RankingDetailOpenButton", "제품군 화면에서 제품군·SKU 전체 순위를 열 수 있어야 함");
expectContains("components/redesign/screens/category/useCategoryScreenModel.tsx", "const categorySkuRows = allCategorySkuRows.slice(0, 5)", "제품군 기본 카드는 SKU Top 5를 유지해야 함");
expectContains("components/redesign/screens/category/CategoryScreenExact.tsx", "리뉴얼 전후 제품은 별도 SKU 코드로 집계", "제품군 화면은 리뉴얼 코드 통합 한계를 명시해야 함");
expectFileNotContains("components/redesign/SiliconAnalyticsWorkspace.tsx", "보고서 담기", "전역 상단에 보고서 담기 영역을 노출하면 안 됨");
expectFileNotContains("components/redesign/SiliconAnalyticsWorkspace.tsx", "<ReportDrawer", "보고서 장바구니 서랍을 렌더링하면 안 됨");
expectFileNotContains("components/redesign/screens/country/CountryScreenExact.tsx", "담기", "국가 화면에 보고서 담기 버튼을 노출하면 안 됨");
expectFileNotContains("components/redesign/screens/brand/BrandScreenExact.tsx", "담기", "브랜드 화면에 보고서 담기 버튼을 노출하면 안 됨");
expectFileNotContains("components/redesign/screens/sku/SkuScreenExact.tsx", "담기", "SKU 화면에 보고서 담기 버튼을 노출하면 안 됨");
expectFileNotContains("components/redesign/screens/season/SeasonCalendarScreenExact.tsx", "담기", "시즌 화면에 보고서 담기 버튼을 노출하면 안 됨");
expectFileNotContains("components/redesign/screens/cross/CrossAnalysisControls.tsx", "cross-add-report", "교차분석 화면에 보고서 담기 버튼을 노출하면 안 됨");
expectContains("components/redesign/screens/country/CountryScreenExact.tsx", 'setRankingDetail("growth")', "국가 성장 상위에서 전체 순위를 열 수 있어야 함");
expectContains("components/redesign/screens/country/CountryScreenExact.tsx", 'rankingDetail === "growth" || rankingDetail === "decline"', "국가 성장/감소 전체 보기는 상승·하락을 하나의 대화상자에 함께 표시해야 함");
expectContains("components/redesign/screens/country/useCountryScreenModel.tsx", "const risingCountryRows = allRisingCountryRows.slice(0, 5)", "국가 성장 기본 카드는 Top 5를 유지해야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", 'setRankingDetail("growth")', "브랜드 성장 상위에서 전체 순위를 열 수 있어야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", 'rankingDetail === "growth" || rankingDetail === "decline"', "브랜드 성장/감소 전체 보기는 상승·하락을 하나의 대화상자에 함께 표시해야 함");
expectContains("components/redesign/screens/brand/useBrandScreenModel.tsx", "const risingBrandRows = allRisingBrandRows.slice(0, 5)", "브랜드 성장 기본 카드는 Top 5를 유지해야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "series.peakMonth", "브랜드 월별 추이 비교에 브랜드별 최고월을 표시해야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", 'data-share-label="brand-comparison"', "브랜드 월별 추이 비교의 모든 월에 비중 라벨을 표시해야 함");
expectNotContains("components/redesign/screens/brand/BrandScreenExact.tsx", 'data-chart-point="monthly-seasonality"', "별도의 월별 판매 시즌성 차트를 제거해야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "reportComparisonSectionHtml", "브랜드 PDF도 월별 추이 비교 섹션을 사용해야 함");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "fetchBrandReportData", "브랜드 리포트는 서버의 완전 집계 결과를 사용해야 함");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "const brandAmount = selectedBrand?.amount ?? 0", "SKU 집중도의 분모는 상위 목록 소계가 아닌 전체 브랜드 매출이어야 함");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "buildYoYComparison", "YoY는 공통 완료월이 있는 기간만 비교해야 함");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "전년 동기간 비교 데이터 없음", "YoY 산출 불가 사유는 사용자 관점의 문구로 표시해야 함");
expectNotContains("components/redesign/screens/report/useReportBuilderModel.tsx", "겹치는 완료월 없음", "YoY 카드에 내부 계산 용어를 노출하면 안 됨");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "brandIdentityKey(row.brand) === selectedIdentity", "재고·MOI는 브랜드 표기 차이와 무관하게 같은 브랜드로 결합해야 함");
expectNotContains("components/redesign/screens/report/useReportBuilderModel.tsx", "stockDateMismatch", "판매기간과 현재 재고 기준일 차이로 발주 참고를 차단하면 안 됨");
expectNotContains("components/redesign/screens/report/useReportBuilderModel.tsx", "재고·MOI는 현재 기준 참고값입니다", "현재 재고·MOI 영역에 판매기간 차이 경고를 표시하면 안 됨");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "stockEntityMismatch", "판매·재고 법인이 다르면 MOI를 결합하면 안 됨");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "showOrderAnalysisSections", "브랜드 리포트의 재고·발주 참고는 현재 세션에서 직접 실행한 발주분석이 있을 때만 표시해야 함");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "stockSnapshot?.status === \"ready\"", "복구된 과거 발주분석 결과를 현재 재고처럼 표시하면 안 됨");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "선택 기간 매출 상위 SKU:", "향후 발주 참고는 과거 판매 순위의 기준을 명시해야 함");
expectNotContains("components/redesign/screens/report/useReportBuilderModel.tsx", "은(는)", "자동 문구에 기계적인 조사 표기를 사용하면 안 됨");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "현재 재고·MOI 기준 긴급보충 또는 재고공백 위험은 확인되지 않았습니다", "향후 발주 참고는 현재 재고 위험을 별도로 설명해야 함");
expectNotContains("components/redesign/screens/report/useReportBuilderModel.tsx", "재고·MOI 기준이 판매 분석과 일치하지 않아", "판매기간과 최신 재고를 불일치 오류처럼 안내하면 안 됨");
expectNotContains("components/redesign/screens/report/useReportBuilderModel.tsx", "countryTopSku ?? season?.topSku", "브랜드 리포트가 상위 SKU 축약 표로 fallback하면 안 됨");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "기간 내 최고 매출월", "1년 조회 리포트는 실제 최고 매출월을 표시해야 함");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "reportAmountText(selectedBrand.amount, rate)", "브랜드 총매출 문구에는 현재 환율 기준 원화 환산액을 함께 표시해야 함");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "reportAmountText(peak.amount, rate)", "최고 매출월 문구에는 현재 환율 기준 원화 환산액을 함께 표시해야 함");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "reportAmountText(yoy.previous, rate)", "YoY 비교 금액에도 현재 환율 기준 원화 환산액을 함께 표시해야 함");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "exchangeRateBasisLabel", "리포트는 API 분석 결과의 건별 환율 기준 설명을 사용해야 함");
expectNotContains("components/redesign/screens/report/useReportBuilderModel.tsx", "현재 적용 환율", "실제 원화 매출에 현재 환율을 다시 적용하면 안 됨");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "카테고리 · 라인 매출 비중", "성분 데이터가 아닌 카테고리/라인 데이터를 정확히 표기해야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "html.replace(legacySeasonalityHtml, reportComparisonSectionHtml)", "브랜드 PDF의 과거 시즌성 막대 그래프를 새 비교 차트로 교체해야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "code={row.sku}", "SKU 집중도 카드에서 상품명 옆에 상품코드를 표시해야 함");
expectContains("components/redesign/screens/sku/SkuScreenExact.tsx", "상품코드 {activeSummary.sku}", "SKU 월별 판매 비중 카드에서 상품명 아래 상품코드를 표시해야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", 'viewBox="0 0 1220 230"', "브랜드 월별 추이 비교 카드는 와이드 비율로 과도한 세로 높이를 방지해야 함");
expectContains("components/redesign/screens/cross/CrossAnalysisPeriodControls.tsx", 'aria-label="YTD YoY 최신 완료월"', "YTD YoY는 최신 완료월을 선택해야 함");
expectContains("components/redesign/screens/cross/CrossAnalysisPeriodControls.tsx", 'aria-label="YTD YoY 자동 비교기간"', "YTD YoY 비교기간은 전년 동일 누계로 자동 설정해야 함");
expectNotContains("components/redesign/screens/cross/CrossAnalysisPeriodControls.tsx", 'label="동일 기간 YoY"', "교차분석에서 별도 기간 YoY 모드를 제거해야 함");
expectContains("components/redesign/screens/cross/CrossAnalysisPeriodControls.tsx", 'aria-label="MoM 자동 비교월"', "MoM 비교월은 직전 월로 자동 고정해야 함");
expectNotContains("components/redesign/screens/cross/CrossAnalysisPeriodControls.tsx", 'aria-label="직접 비교월"', "교차분석에서 임의 월 직접 비교를 제거해야 함");
expectContains("components/redesign/screens/cross/CrossAnalysisScreenExact.tsx", 'from "./CrossAnalysisControls"', "교차분석 상단 제어부는 별도 화면 컴포넌트로 분리해야 함");
expectContains("components/redesign/screens/cross/CrossAnalysisScreenExact.tsx", 'from "./CrossAnalysisHeatmap"', "교차분석 매트릭스는 별도 화면 컴포넌트로 분리해야 함");
expectContains("components/redesign/screens/cross/CrossAnalysisScreenExact.tsx", 'from "./CrossAnalysisPeriodControls"', "교차분석 기간·선택 제어부는 별도 화면 컴포넌트로 분리해야 함");
expectContains("components/redesign/screens/cross/CrossAnalysisScreenExact.tsx", 'from "./useCrossAnalysisData"', "교차분석 데이터·기간 상태는 전용 훅으로 분리해야 함");
expectContains("components/redesign/screens/cross/CrossAnalysisScreenExact.tsx", "const { source, period, selection, matrix }", "교차분석 화면은 데이터 훅 결과를 도메인별로 사용해야 함");
expectContains("components/redesign/screens/cross/CrossAnalysisScreenExact.tsx", 'from "./useCrossAnalysisReport"', "교차분석 리포트 생성은 전용 훅으로 분리해야 함");
expectNotContains("components/redesign/screens/cross/CrossAnalysisScreenExact.tsx", "function CrossHeatCell", "교차분석 컨테이너에 히트맵 셀 구현을 다시 합치면 안 됨");
expectNotContains("components/redesign/screens/cross/CrossAnalysisScreenExact.tsx", "function CrossTabButton", "교차분석 컨테이너에 축 탭 구현을 다시 합치면 안 됨");
expectNotContains("components/redesign/screens/cross/CrossAnalysisScreenExact.tsx", 'window.open("", "_blank"', "교차분석 컨테이너에 PDF 팝업 구현을 다시 합치면 안 됨");
expectNotContains("components/redesign/screens/cross/CrossAnalysisScreenExact.tsx", "getSeasonTrendAnalysis", "교차분석 컨테이너에 API 로딩 구현을 다시 합치면 안 됨");
expectContains("components/redesign/screens/cross/useCrossAnalysisData.ts", 'from "./useCrossAnalysisSource"', "교차분석 데이터 훅은 전용 소스 훅을 사용해야 함");
expectContains("components/redesign/screens/cross/useCrossAnalysisData.ts", "source: {", "교차분석 데이터 훅은 원본 데이터 반환값을 source로 묶어야 함");
expectContains("components/redesign/screens/cross/useCrossAnalysisData.ts", "matrix: {", "교차분석 데이터 훅은 매트릭스 반환값을 matrix로 묶어야 함");
expectMatches("components/redesign/screens/cross/useCrossAnalysisData.ts", /source:\s*\{[\s\S]*?period,[\s\S]*?selection,[\s\S]*?matrix:\s*\{/, "교차분석 데이터 훅은 source·period·selection·matrix 순서의 경계를 유지해야 함");
expectNotContains("components/redesign/screens/cross/useCrossAnalysisData.ts", "getSeasonTrendAnalysis", "교차분석 데이터 훅에 API 호출을 다시 합치면 안 됨");
expectContains("components/redesign/screens/cross/useCrossAnalysisSource.ts", "getSeasonTrendAnalysis", "교차분석 소스 훅은 분석 API 로딩을 담당해야 함");
expectContains("components/redesign/screens/cross/useCrossAnalysisSource.ts", "hasError: loadFailed", "교차분석 소스 훅은 공통 요청 오류 상태를 노출해야 함");
expectContains("components/redesign/screens/cross/useCrossAnalysisData.ts", 'from "./useCrossAnalysisPeriodState"', "교차분석 기간 상태는 전용 훅으로 분리해야 함");
expectNotContains("components/redesign/screens/cross/useCrossAnalysisData.ts", "setMomComparisonMonth", "교차분석 데이터 훅에 비교월 상태를 다시 합치면 안 됨");
expectContains("components/redesign/screens/cross/useCrossAnalysisPeriodState.ts", 'from "./crossAnalysisPeriodModel"', "교차분석 기간 상태 훅은 기간 도메인 모델을 사용해야 함");
expectContains("components/redesign/screens/cross/useCrossAnalysisPeriodState.ts", "setMomComparisonMonth", "교차분석 기간 상태 훅은 비교월 자동 동기화를 소유해야 함");
expectContains("components/redesign/screens/cross/useCrossAnalysisData.ts", 'from "./useCrossAnalysisSelection"', "교차분석 행·열 선택은 전용 훅으로 분리해야 함");
expectNotContains("components/redesign/screens/cross/useCrossAnalysisData.ts", "formatAnalysisMonthLabel", "교차분석 데이터 훅에 월 경고 문자열 계산을 다시 합치면 안 됨");
expectNotContains("components/redesign/screens/cross/useCrossAnalysisData.ts", "setSelectedRows", "교차분석 데이터 훅에 행 선택 상태를 다시 합치면 안 됨");
expectContains("components/redesign/screens/cross/useCrossAnalysisSelection.ts", "crossMatrixData", "교차분석 선택 훅은 선택값과 매트릭스 투영을 함께 관리해야 함");
expectContains("components/redesign/screens/cross/useCrossAnalysisSelection.ts", "setSelectedRows", "교차분석 선택 훅은 행 선택 상태를 소유해야 함");
expectContains("components/redesign/screens/cross/crossAnalysisPeriodModel.ts", "analysisMonthKeys", "교차분석 기간 모델은 분석 범위의 월 목록을 계산해야 함");
expectContains("components/redesign/screens/cross/crossAnalysisPeriodModel.ts", "buildMomCoverageModel", "교차분석 기간 모델은 MoM 커버리지 판정을 담당해야 함");
expectContains("components/redesign/screens/cross/useCrossAnalysisReport.ts", 'window.open("", "_blank"', "교차분석 PDF 생성 훅은 인쇄 창 생성을 담당해야 함");
expectContains("components/redesign/screens/cross/useCrossAnalysisReport.ts", 'from "./crossAnalysisReportDocument"', "교차분석 리포트 훅은 순수 PDF 문서 빌더를 사용해야 함");
expectContains("components/redesign/screens/cross/useCrossAnalysisReport.ts", 'from "./crossAnalysisReportModel"', "교차분석 리포트 훅은 순수 블록 모델을 사용해야 함");
expectNotContains("components/redesign/screens/cross/useCrossAnalysisReport.ts", "<!doctype html>", "교차분석 리포트 훅에 PDF HTML 템플릿을 다시 합치면 안 됨");
expectNotContains("components/redesign/screens/cross/useCrossAnalysisReport.ts", "crossSnapshotRows", "교차분석 리포트 훅에 스냅샷 생성을 다시 합치면 안 됨");
expectContains("components/redesign/screens/cross/crossAnalysisReportModel.ts", "buildCrossSnapshotRows", "교차분석 리포트 모델은 스냅샷 생성을 담당해야 함");
expectContains("components/redesign/screens/cross/crossAnalysisReportModel.ts", "stableShortHash", "교차분석 리포트 모델은 안정적인 블록 ID를 생성해야 함");
expectContains("components/redesign/screens/cross/crossAnalysisReportDocument.ts", "<!doctype html>", "교차분석 PDF 문서 빌더는 독립 HTML 문서를 생성해야 함");
expectContains("components/redesign/screens/cross/crossAnalysisReportDocument.ts", "escapeReportHtml", "교차분석 PDF 문서 빌더는 동적 값을 이스케이프해야 함");
expectContains("lib/cross-analysis-matrix.ts", "const previousYear = latestYear - 1", "YoY 비교연도는 기준연도 바로 전년으로 제한해야 함");

expectMatches("components/redesign/lib/WorkspaceReport.tsx", /audience:\s*"partner"[\s\S]*?disabled:\s*true/, "거래처용 보고서 옵션은 비활성화 상태를 유지해야 함");
expectMatches("components/redesign/lib/WorkspaceReport.tsx", /audience:\s*"sales"[\s\S]*?disabled:\s*true/, "판매용 보고서 옵션은 비활성화 상태를 유지해야 함");
expectContains("components/redesign/screens/brand/useBrandScreenData.ts", "season?.monthCoverage ?? EMPTY_ROWS", "브랜드 성장률은 월 완결성 메타데이터를 읽어야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", 'item.status === "complete"', "브랜드 성장률 기본 비교는 완결 월만 사용해야 함");
expectContains("components/redesign/screens/brand/useBrandScreenModel.tsx", "[brandRankGrowthColumn]: brandYoyByName.get(row.brand) ?? \"-\"", "브랜드 순위 보고서는 모든 순위 브랜드의 완료월 YTD 성장률을 직접 포함해야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "...allRisingBrandRows.map", "브랜드 성장 보고서는 상승 브랜드 전체를 포함해야 함");
expectContains("components/redesign/screens/brand/BrandScreenExact.tsx", "...allDecliningBrandRows.map", "브랜드 성장 보고서는 하락 브랜드 전체를 포함해야 함");
expectContains("components/season-trend/GlobalDemandViews.tsx", 'from "./GlobalDemandMonthlyView"', "글로벌 수요 facade는 월별 렌즈를 전용 모듈에서 재수출해야 함");
expectContains("components/season-trend/GlobalDemandViews.tsx", 'from "./GlobalDemandIngredientView"', "글로벌 수요 facade는 성분 렌즈를 전용 모듈에서 재수출해야 함");
expectContains("components/season-trend/GlobalDemandViews.tsx", 'from "./GlobalDemandBrandView"', "글로벌 수요 facade는 브랜드 렌즈를 전용 모듈에서 재수출해야 함");
expectContains("components/season-trend/GlobalDemandViews.tsx", 'from "./GlobalDemandSkuView"', "글로벌 수요 facade는 SKU 렌즈를 전용 모듈에서 재수출해야 함");
expectNotContains("components/season-trend/GlobalDemandViews.tsx", "function MonthlyLensView", "글로벌 수요 facade가 월별 렌즈 구현을 다시 소유하면 안 됨");
expectNotContains("components/season-trend/GlobalDemandViews.tsx", "function IngredientLensView", "글로벌 수요 facade가 성분 렌즈 구현을 다시 소유하면 안 됨");

expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "const salesDataIssue", "report copy must suppress insights when quantity and sales conflict");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "const stockRecommendationReady", "report recommendations must require a current stock snapshot for the same entity");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "const riskStockRows", "replenishment recommendations must use stock-risk rows");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "const recommendationLines", "report recommendations must be evidence-based");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "...riskNames", "위험 SKU는 상품별로 줄을 분리해야 함");
expectContains("components/redesign/screens/report/BrandReportPreview.tsx", 'part.startsWith("권장 조치:")', "권장 조치는 SKU 목록과 별도 문단으로 표시해야 함");
expectContains("components/redesign/screens/report/reportPdfDocument.ts", 'class="recommendation"', "PDF에서도 권장 조치를 별도 문단으로 표시해야 함");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "const summaryRows: ReportSummaryRow[] = baseSummaryRows.map<ReportSummaryRow>", "dynamic copy must override unsafe default report copy");
expectNotContains("components/redesign/screens/report/useReportBuilderModel.tsx", "데이터 품질 점검", "일반 사용자용 브랜드 리포트에는 내부 데이터 품질 진단 문단을 노출하면 안 됨");
expectContains("components/redesign/screens/report/useReportBuilderModel.tsx", "const salesQualityBlocked", "중복 영향이 큰 경우 발주 추천을 차단해야 함");
expectContains("components/redesign/screens/report/BrandReportPreview.tsx", "grid-cols-1 gap-2", "report basis cards must stack on narrow screens");
expectContains("components/redesign/screens/report/BrandReportPreview.tsx", "grid-cols-1 gap-px", "report metric cards must use a readable mobile grid");
expectContains("components/redesign/screens/report/ReportBuilder.tsx", "responsiveFullWidth", "brand selector must use the full mobile control width");
expectContains("components/redesign/screens/report/useReportPdfExport.ts", "pdfExportError", "blocked PDF popups must be explained to the user");
expectContains("components/redesign/screens/report/reportPdfDocument.ts", "break-inside:avoid", "PDF rows must not split across pages");

// 백엔드 예열(cms_prefetch._season_default_range)이 이 기본값에 캐시 키를
// 맞춘다. 종료일 규칙을 바꾸면 backend/services/cms_prefetch.py와
// tests/test_cms_prefetch_range_alignment.py도 같이 고쳐야 한다(2026-07-30).
expectContains(
  "components/redesign/lib/workspace-format.ts",
  "end.setDate(end.getDate() - 1)",
  "demandRange 종료일이 어제여야 백엔드 예열 캐시 키와 일치함"
);

// 브라우저 결과 캐시는 백엔드를 아예 호출하지 않는다. 신선도 규칙이 이 층에서
// 빠지면 서버 규칙만으로는 묵은 결과를 막을 수 없다(2026-07-30).
expectContains(
  "lib/api/season.ts",
  "cachedSeasonResultIsCurrent",
  "브라우저 결과 캐시도 서버와 같은 신선도 규칙을 적용해야 함"
);

// 2026-07-30 사고: 시작/중단이 한 버튼을 공유하면, 429로 막힌 사용자가 연타하다
// 시작에 성공한 순간 다음 클릭이 방금 시작한 분석을 취소한다(실측: POST 200 →
// 1초 뒤 DELETE). 두 동작은 반드시 별도 버튼이어야 한다.
for (const screen of [
  "components/redesign/screens/idata/InsightInputScreenExact.tsx",
  "components/redesign/screens/prep/PrepScreenExact.tsx"
]) {
  expectNotContains(
    screen,
    "analysisRunning ? stopAnalysis : startAnalysis",
    `${screen}: 분석 시작/중단을 한 버튼에 겹치면 연타가 방금 시작한 분석을 취소함`
  );
  expectContains(screen, "onClick={startAnalysis}", `${screen}: 분석 시작은 전용 버튼이어야 함`);
  expectContains(screen, "onClick={stopAnalysis}", `${screen}: 분석 중단은 전용 버튼이어야 함`);
}

expectNotContains(
  "components/redesign/screens/idata/useInsightInputScreenModel.tsx",
  "const demandQuickRanges = hasLongHistoryApi",
  "분석 기간 빠른 선택 버튼 로직을 다시 추가하지 않음"
);
expectNotContains(
  "components/redesign/screens/idata/InsightInputScreenExact.tsx",
  "demandQuickRanges.map",
  "분석 조건 화면에서 빠른 기간 선택 버튼을 표시하지 않음"
);

if (process.exitCode) {
  process.exit(process.exitCode);
}

console.log("UI regression checks passed.");
