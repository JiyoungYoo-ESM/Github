# Design QA — 브랜드 그래프 상세 호버 툴팁

- source visual truth path: `artifacts/brand-monthly-multiline-spaced.png`
- implementation screenshot path: `artifacts/brand-graph-hover-tooltip.png`
- side-by-side comparison path: `artifacts/brand-hover-tooltip-qa-side-by-side.png`
- viewport: 1780 × 1250, device scale factor 1
- state: 브랜드 분석 · 비교 브랜드 6개 · 닥터엘시아 3월 포인트 호버

## Full-view comparison evidence

- 기존 상위 SKU 표, 카드 배치, 그래프 크기와 범례 구조는 유지했다.
- 호버 상태에서만 상세 툴팁이 나타나므로 기본 화면의 정보 밀도는 변하지 않는다.
- 활성 브랜드 선은 굵게 유지되고 나머지 5개 선은 투명도 20%로 낮아져 선택 맥락이 분명하다.

## Focused region comparison evidence

- 툴팁은 브랜드명, 월, 월 매출 비중, 유로 매출, 원화 환산액, 선택 기간 총매출을 표시한다.
- 툴팁 실제 크기는 210 × 124px이며 그래프 래퍼 내부에 완전히 들어온다.
- 각 데이터 포인트는 11~12 SVG 좌표 단위의 투명 히트 영역을 제공해 작은 점보다 쉽게 호버할 수 있다.
- 왼쪽 시즌성 그래프에도 월, 매출 비중, 유로 매출, 원화 환산액 툴팁이 동일하게 동작한다.

## Findings

- P0/P1/P2 차이 없음.
- P3: 툴팁이 일부 선을 가릴 수 있으나 활성 선 강조와 함께 일시적으로만 표시되므로 정보 확인을 방해하지 않는다.

## Required fidelity surfaces

- Fonts and typography: 기존 카드 타이포그래피와 맞춘 10~12px 계층으로 상세 정보를 구성했다.
- Spacing and layout rhythm: 190~210px 폭, 10px 라운드, 12px 내부 여백으로 기존 팝오버 계층과 일치한다.
- Colors and visual tokens: 기존 표면, 테두리, 그림자, 구분선 및 시리즈 색상을 그대로 사용한다.
- Image quality and asset fidelity: 그래프와 포인트는 SVG로 유지되며 HTML 툴팁 텍스트가 선명하게 렌더링된다.
- Copy and content: 비중과 매출액의 기준을 각각 `월 매출`, `선택 기간 총매출`로 명확히 구분했다.

## Primary interactions tested

- 왼쪽 시즌성 그래프 3월 포인트 호버 시 월 상세 툴팁 표시 확인.
- 오른쪽 비교 그래프 3월 포인트 호버 시 5개 비활성 선 흐림 처리 확인.
- 상세 항목 5개와 원화 환산 정보 표시 확인.
- 툴팁이 그래프 래퍼 영역을 벗어나지 않는지 좌표로 검증.
- 마우스 호버, 키보드 포커스, 클릭을 동일 상태 처리 함수에 연결.
- 브라우저 콘솔 및 페이지 런타임 오류 없음.

## Comparison history

- Iteration 1: SVG 내부 툴팁을 구현했으나 실제 화면에서 텍스트가 작고 카드 아래쪽이 잘렸다.
- Iteration 2: 툴팁을 HTML 오버레이로 변경해 읽기 쉬운 크기로 확대했다.
- Iteration 3: 그래프 내부 상단에 위치를 고정하고 실제 호버 화면에서 전체 내용이 보이는지 확인했다.

## Verification

- `npm run typecheck`: passed
- `npm run build`: passed
- Playwright hover tooltip and active-series capture: passed
- Console and page errors: none

final result: passed

# Design QA — 발주분석 V3 계산 근거 공개

- source visual truth paths:
  - `C:/Users/USER/AppData/Local/Temp/codex-clipboard-7a54b49f-1678-4f15-b603-4a93079885d5.png`
  - `C:/Users/USER/AppData/Local/Temp/codex-clipboard-cd6d664b-e2fa-480f-bedb-d994b4627dea.png`
- implementation screenshot paths:
  - `artifacts/order-v3-detail-implementation-20260901/desktop-top-final.png`
  - `artifacts/order-v3-detail-implementation-20260901/mobile-top-final.png`
  - `artifacts/order-v3-detail-implementation-20260901/mobile-formula-final.png`
- comparison paths:
  - `artifacts/order-v3-detail-implementation-20260901/comparison-full.png`
  - `artifacts/order-v3-detail-implementation-20260901/comparison-formula.png`
- viewport: desktop 1440 × 1100 CSS px, mobile 390 × 844 CSS px, device scale factor 1
- source pixels: 525 × 821 및 521 × 416
- implementation pixels: desktop drawer 560 × 1100, mobile 390 × 844
- density normalization: 전체 비교는 구현 드로어를 525px 폭으로 축소한 뒤 상단 821px을 동일 크기로 비교했다. 산식 비교는 원본 두 번째 이미지를 560px 폭으로 맞추고 구현의 예측·산식 영역을 560px 폭으로 잘라 한 입력에서 비교했다.
- state: DRASO1-CRR · 쇼티지 방어 시나리오 · 담당자 결정 전 · SKU 계산 근거 드로어 열림

## Full-view comparison evidence

- 기존 560px 드로어, 카드 반경, 붉은 발주 강조색, 회색 표면, 고정 검토 버튼의 디자인 언어를 유지했다.
- 정보 순서는 요청에 맞춰 `향후 수요 예측 → 목표재고·발주판정 → 364일 판매 → 자동 분류 근거`로 변경했다.
- 요약 카드에서 제안수량·재고포지션을 각각 `발주필요수량 (원시)`·`발주반영 총재고 (IP)`로 명확히 바꾸고, IP·ROP·S·Q의 관계를 한 문장으로 설명했다.
- 390px 모바일에서는 예상수요 영역을 2×2 그리드로 전환해 긴 지표명이 겹치지 않으며, 두 줄 산식도 가로 잘림 없이 노출된다.

## Focused region comparison evidence

- 기존 `L1 + L2 + L3 = S` 한 줄을 `L1 + L2 = ROP`, `ROP + L3 = S` 두 줄로 분리했다.
- 산식 아래에 순수 정기발주 `IP < S → 발주 필요`와 `Q=max(0,S−IP)`를 별도 판정 박스로 표시하고, ROP는 미사용 참고값으로 구분했다.
- 판매 차트의 왼쪽 여백과 Y축 폭을 조정하고 숫자 포맷을 적용해 원본에서 잘렸던 눈금이 데스크톱·모바일 모두 완전히 표시된다.

## Required fidelity surfaces

- Fonts and typography: 기존 제품 글꼴, 굵기, 9~19px 위계와 숫자 탭 정렬을 유지했다. 모바일의 긴 예상수요·오차 라벨은 2열 배치로 가독성을 확보했다.
- Spacing and layout rhythm: 기존 12px 카드, 9~10px 내부 박스, 3단 수식 카드의 간격을 유지하고 산식을 두 행으로 확장했다.
- Colors and visual tokens: `brand`, `surface`, `border`, `muted`, `emerald` 토큰만 사용했으며 디자인 토큰 감사가 통과했다.
- Image quality and asset fidelity: 신규 래스터 자산은 없고 기존 Recharts와 Lucide 아이콘을 유지했다. 차트 선·막대와 축 라벨 선명도를 브라우저 캡처에서 확인했다.
- Copy and content: `기초 예상수요 (향후 28일)`, `예측오차 (RMSE, EA/기)`, `발주점 ROP`, `발주필요수량`을 사용자 언어로 명시했다.

## Primary interactions tested

- 데스크톱 및 390px 모바일 드로어 내부 스크롤.
- `계산에 사용한 값 자세히 보기` 열기·닫기와 `aria-expanded` 상태 전환.
- 고정 `권고 유지`, `수량 수정`, `발주 보류` 버튼의 노출 유지.
- 브라우저 콘솔 error 없음. Next.js 개발 모드의 기존 `scroll-behavior` 안내 warning 1건만 확인했다.

## Comparison history

1. 최초 검토에서 ROP가 화면에 없고 과거 판매가 예상수요보다 먼저 나와 발주 산식의 인과관계를 바로 읽기 어려운 문제를 확인했다.
2. 예측·산식 영역을 상단으로 이동하고 ROP와 발주 게이트를 추가했다.
3. 390px 첫 캡처에서 4열 예상수요 카드의 긴 라벨이 과도하게 줄바꿈되는 P2를 확인해 모바일을 2×2 그리드로 수정했다.
4. 수정 후 모바일 예상수요·ROP·S·Q와 차트 축이 겹침이나 잘림 없이 표시되는 것을 확인했다.

## Findings

- P0: 없음.
- P1: 없음.
- P2: 없음. 모바일 예상수요 밀도와 차트 Y축 잘림은 수정 후 해소됐다.
- P3: 긴 근거를 읽는 동안 하단 담당자 결정 바가 콘텐츠 일부를 덮지만, 드로어에 충분한 하단 여백과 독립 스크롤이 있어 모든 내용을 확인할 수 있으며 기존 검토 동작을 유지하기 위한 의도된 구조다.

## Verification

- `npm run test:order-v3-review-list`: passed
- `npm run typecheck`: passed
- `npm run lint`: passed
- desktop/mobile browser render: passed
- details accordion interaction: passed
- browser console errors: none

final result: passed

# Design QA — 계절지수 관리 자동 적용 화면

- 기준 시안: `C:/Users/USER/AppData/Local/Temp/codex-clipboard-f7d6f262-22be-4978-9452-59861cb3dca3.png`
- 구현 경로: `/order-analysis/season-factors`
- 구현 범위: 관리자 전용 내비게이션, 활성 artifact 조회, `계절지수 갱신` 실행, 자동 검증 결과와 V3 자동 적용 상태 표시

## 구현 확인

- 수동 `후보 생성` 및 `승인하여 V3 적용` 동작을 화면에서 제거했다.
- 관리자 갱신 요청은 기존 백엔드의 `/api/order-logic-v3/season-factors/refresh`를 호출한다.
- 서버가 `active` 및 검증 통과 artifact를 반환한 경우에만 `V3 자동 적용 중`으로 표시한다.
- 이번 결과가 검증에 실패하면 기존 활성 artifact를 다시 조회해 유지하고, 실패 사유를 화면에 표시한다.
- 기능구분1 프로파일은 `기능구분1 기준`으로 명시해 기능구분2 미분류 SKU에도 상위 계절지수가 적용됨을 보여 준다.

## 검증

- `npm run typecheck`: passed
- `npm run lint`: passed
- `npm run test:order-analysis`: passed (76 assertions)
- `scripts/order-access.test.mjs`: passed
- `npm test`: blocked by an existing V2 lead-time display assertion in `scripts/order-logic-v2-lead-time-basis.test.mjs`; 계절지수 관리 변경과는 무관함.

## 브라우저 디자인 QA

- 인앱 브라우저와 Chrome 모두 현재 로컬 앱 로그인 화면으로 이동해, 인증된 화면 상태·실제 artifact 데이터·갱신 버튼을 캡처할 수 없었다.
- 인증 정보를 임의로 입력하거나 갱신 API를 호출하지 않았으므로, 시안과 구현 화면의 최종 픽셀 비교 및 실제 버튼 상호작용은 미검증이다.

final result: blocked

# Design QA — 발주분석 V3 옵션 1 실행형 검토 큐

- source visual truth path: `artifacts/order-v3-option1-action-queue-reference.png`
- implementation screenshot path: `artifacts/order-v3-option1-final-desktop-1487x1058.png`
- full-view comparison evidence: `artifacts/order-v3-option1-final-reference-vs-implementation.png`
- responsive evidence: `artifacts/order-v3-option1-mobile-390x844.png`, `artifacts/order-v3-option1-final-mobile-drawer-390x844.png`
- viewport: desktop 1487 × 1058 CSS px, mobile 390 × 844 CSS px
- pixel dimensions and density: source 1487 × 1058 px, implementation 1487 × 1058 px, CSS viewport와 1:1 비교, 별도 density normalization 없음
- state: TOR-DIV-030 우선 검토 SKU 상세 패널 열림, 담당자 결정 전

## Full-view comparison evidence

- 좌측 기존 제품 내비게이션, 중앙 실행형 검토 큐, 우측 결론 우선 근거 패널의 3영역 비율을 동일 상태에서 비교했다.
- 선택 시안의 핵심인 압축 실행 상태, 검토 요약, 5개 핵심 열, 첫 미검토 CTA, 고정 담당자 결정 바를 유지했다.
- 기존 웹사이트의 전역 헤더·검색·색상 토큰을 보존하기 위해 시안의 독립 페이지 헤더는 기존 셸 내부 상태바로 통합했다. 이는 제품 일관성을 위한 의도적 차이다.

## Focused region comparison evidence

- 우측 패널 상단에서 권고수량, 제안금액, 재고포지션, 목표재고, 권고 이유를 먼저 확인한 뒤 13기간 판매·자동 분류·적용 엔진·목표재고 근거로 내려가는 순서를 비교했다.
- 하단 권고 유지·수량 수정·발주 보류 버튼은 데스크톱과 390px 모바일에서 모두 고정 노출되는지 별도로 확인했다.
- 표의 Excel 체크박스와 `선택 1건 Excel` 레이블 전환을 실제 상호작용으로 확인했으므로 핵심 컨트롤의 focused region은 별도 이미지 크롭 없이 전체 캡처에서 판독 가능했다.

## Required fidelity surfaces

- Fonts and typography: 기존 Pretendard 계열 제품 타이포그래피, 굵은 숫자 위계, 작은 상태 라벨, 한글 줄바꿈을 유지했다. 모바일 단계 제목은 한 줄로 고정했다.
- Spacing and layout rhythm: 12px 카드 반경, 8px 컨트롤 반경, 3~4px 영역 간격 체계를 적용하고 데스크톱 드로어 폭을 시안과 유사한 560px로 맞췄다.
- Colors and visual tokens: 제품의 brand, surface, border, muted 토큰만 사용했고 raw hex 색상은 제거했다.
- Image quality and asset fidelity: 시안의 가시 자산은 기존 Silicon2 로고와 코드 네이티브 차트·Lucide 아이콘뿐이며 대체 이미지나 임의 SVG를 추가하지 않았다.
- Copy and content: `긴급` 대신 원천 fixture로 설명 가능한 `우선 검토`를 사용했다. V3 UI 샘플 경고와 금액 권한 정책도 유지했다.

## Comparison history

1. 최초 비교에서 모바일 상세 패널 하단의 전역 사용자 버튼이 `권고 유지` CTA 위에 겹치는 P1 문제를 확인했다.
2. 근거 패널과 배경 레이어의 z-index를 기존 셸보다 높이고 모바일 단계 제목 줄바꿈을 방지했다.
3. 수정 후 `artifacts/order-v3-option1-final-mobile-drawer-390x844.png`에서 세 결정 버튼이 가려짐 없이 노출되는 것을 확인했다.
4. 데스크톱 최종 비교에서 선택 SKU 강조, 4개 검토 요약, 결론 우선 근거 구조를 재확인했으며 추가 P0/P1/P2 차이는 없었다.

## Primary interactions tested

- SKU 체크박스 선택 시 `선택 1건 Excel`, 해제 시 `우선 검토 Excel`로 전환.
- 첫 미검토 SKU 열기, 권고 유지 처리, 다음 미검토 SKU 자동 이동.
- 실행 정보 팝오버와 시나리오 비교 진입·복귀.
- 데스크톱 및 모바일 상세 패널, 고정 결정 버튼, Escape/focus-trap 구현 유지.
- 브라우저 콘솔 error 없음. 기존 전역 Silicon2 로고 aspect-ratio warning 1건만 확인했으며 이번 변경 범위 밖이다.

## Findings

- P0: 없음.
- P1: 없음. 최초 모바일 CTA 겹침은 수정 후 해소됨.
- P2: 없음.
- P3: 독립 시안과 달리 기존 제품 전역 헤더가 유지되어 중앙 큐의 첫 행 시작점이 약간 낮다. 사이트 전체 UI 통일을 위해 허용한 차이다.

final result: passed

# Design QA — 발주분석 V3 탭

- source visual truth path: `C:\Users\USER\.codex\generated_images\01a040b0-1d92-7e92-939f-f66495e20a5f\exec-9ae0971a-bbc7-475b-877f-916b43adccf7.png`
- implementation route: `http://192.168.0.245:3000/order-analysis/order-v3`
- implementation screenshot path: `artifacts/order-v3-implementation-final-1497x1051.png`
- side-by-side comparison path: `artifacts/order-v3-reference-vs-implementation.png`
- mobile screenshot path: `artifacts/order-v3-mobile-drawer-390x844.png`
- viewport target: 1497 × 1051 CSS px, device scale factor 1
- source pixels: 1497 × 1051
- implementation pixels: 1497 × 1051
- density normalization: source and implementation are compared at the same 1× pixel size
- state: 발주 제안 탭 · `TOR-DIV-030` 선택 · SKU 계산 근거 드로어 열림

## Full-view comparison evidence

- 1497 × 1051 동일 뷰포트에서 기준 목업과 인증된 구현 화면을 한 이미지로 합쳐 비교했다.
- 헤더, 실행 메타데이터, 3개 탭, KPI 4개, 필터, 우선순위 테이블, 우측 계산 근거 드로어의 시각적 계층과 붉은 포인트 색을 유지했다.
- 기존 웹사이트와의 통일성을 위해 공용 좌측 사이드바와 상단 작업영역을 유지했으며, 드로어가 열리면 배경 목록을 딤 처리해 검토 대상에 집중하도록 했다.

## Focused region comparison evidence

- 13기간 판매 차트, ADI/CV²/추세 자동 분류, 적용 엔진, L1/L2/L3 목표재고, IP 구성, 최종 제안 수량과 3개 결정 버튼이 기준 목업과 같은 순서로 표시된다.
- 목표재고와 IP 계산 카드는 1497px 데스크톱에서 가로 스크롤 없이 한 줄에 노출되고, 390px 모바일에서는 전체 폭 드로어와 가로 탐색으로 정보 손실을 막는다.
- 액션 버튼은 드로어 하단에 고정되어 긴 근거를 스크롤하는 동안에도 `권고 유지`, `수량 수정`, `발주 보류`를 즉시 실행할 수 있다.

## Findings

- P0/P1/P2 차이 없음.
- P3: 기준 목업은 콘텐츠 단독 화면이고 구현은 기존 공용 사이드바를 포함한다. 사용자가 요청한 기존 UI 통일성을 위한 의도된 차이다.
- P3: 공용 사이드바 로고의 Next.js 종횡비 경고 1건이 있으나 기존 셸 자산에서 발생하며 V3 기능·레이아웃에는 영향이 없다.

## Required fidelity surfaces

- Fonts and typography: 기존 Pretendard 계층과 V2의 9~24px UI 타입 스케일을 재사용하고 실제 렌더에서 위계를 확인했다.
- Spacing and layout rhythm: 기존 1600px 콘텐츠 폭, 14px 카드 반경, V2 표 밀도, 560px 드로어를 사용했다.
- Colors and visual tokens: brand, surface, border, status 토큰만 사용했고 디자인 토큰 감사가 통과했다.
- Image quality and asset fidelity: 별도 래스터 자산은 없고 판매 추이는 기존 Recharts와 공용 차트 색상 토큰을 사용한다. 데스크톱·모바일에서 선명도를 확인했다.
- Copy and content: V3 계산 API 미연동을 화면과 Excel에 명시했고, 자료 간 충돌하는 자동 분류 임계값은 UI 기본값으로 노출하지 않았다.

## Primary interactions tested

- 발주 제안, 시나리오 비교, 설정 탭 전환.
- 브랜드 필터에서 `토리든` 선택 시 헤더 포함 2개 행으로 축소되고 전체로 복원되는 동작.
- `TOR-DIV-030`에서 `권고 유지` 후 `MDH-COL-021`로 자동 이동하는 동작.
- `MDH-COL-021` 수량을 8,000으로 수정·저장한 뒤 `ANU-NIA-030`로 이동하는 동작.
- `ANU-NIA-030` 발주 보류 후 `COS-RTN-110`로 이동하는 동작.
- 390 × 844 모바일에서 목록이 렌더되고 SKU 선택 시 전체 폭 계산 근거 드로어와 고정 액션이 표시되는 동작.
- 신규 V3 코드의 런타임 콘솔 오류 없음.

## Comparison history

- Iteration 1: 로그인 전 인증 리다이렉트로 비교가 차단됐다.
- Iteration 2: 로그인 후 동일 뷰포트·동일 드로어 상태를 캡처하고 전체 화면과 핵심 영역을 비교했다.
- Iteration 3: 목표재고와 최종 제안 카드 폭을 줄여 데스크톱의 불필요한 가로 스크롤을 제거했다.
- Iteration 4: Recharts 초기 크기를 명시해 V3 차트의 초기 렌더 경고를 제거했다.

## Verification

- `npm run typecheck`: passed
- `npm run lint`: passed
- `npm test`: passed
- production `npm run build`: passed
- authenticated browser design QA: passed
- desktop and mobile render: passed
- tab, filter, drawer, keep/edit/hold interactions: passed
- V3 runtime console errors: none

final result: passed

# Design QA — 법인별 보유 재고 행 가독성

- source visual truth path: `C:/Users/USER/AppData/Local/Temp/codex-clipboard-aaf72058-3793-4ea6-9fb4-f96e1f41b52d.png`
- implementation screenshot path: `artifacts/design-qa-inventory-spacing-expanded.png`
- focused comparison path: `artifacts/design-qa-inventory-spacing-detail-comparison.png`
- viewport: 1633 × 918 CSS px, device scale factor 1
- source pixels: 1633 × 918
- implementation pixels: 1633 × 918
- density normalization: 동일 픽셀 크기와 동일 뷰포트로 비교
- state: 현재 보유 재고 상세 펼침, 법인 14개 2열 표시

## Full-view comparison evidence

- 2열 구조와 14개 법인의 한 화면 노출을 유지했다.
- 행 높이를 56px에서 실제 렌더 기준 61px로 키웠지만 상세 카드 하단과 비중 안내 문구가 918px 뷰포트 안에 모두 표시된다.
- 카드 폭, 열 배치, 상단 KPI 카드와의 시각적 계층은 기존 구조를 유지한다.

## Focused region comparison evidence

- 법인명은 13px, 국가·창고 정보는 10.5px로 소폭 확대했다.
- 법인명과 보조 정보 사이의 실제 간격은 4px이며, 보조 정보와 비중 막대 사이도 6px로 늘어 두 줄이 붙어 보이지 않는다.
- 순위, 비중, 원화 금액, 현지 통화 금액도 같은 비율로 확대해 행 내부의 시각적 균형을 맞췄다.

## Findings

- P0/P1/P2 차이 없음.
- 의도된 차이: 사용자의 가독성 요청에 따라 상세 카드 높이가 원본보다 약 31px 증가했지만 한 화면 노출 조건은 유지된다.

## Required fidelity surfaces

- Fonts and typography: 기존 글꼴과 굵기를 유지하고 법인명·금액을 13px, 보조 정보를 10.5px로 조정했다.
- Spacing and layout rhythm: 행 최소 높이 60px, 상하 패딩 8px, 법인명과 보조 정보 간격 4px로 조정했다.
- Colors and visual tokens: 기존 `text-ink`, `text-muted2`, `border-rowline`, `bg-brand/50` 토큰을 그대로 사용했다.
- Image quality and asset fidelity: 이번 변경 범위에 이미지 자산은 없다.
- Copy and content: 법인명, 국가, 창고 수, 비중, 재고금액 문구와 데이터는 변경하지 않았다.

## Primary interactions tested

- 현재 보유 재고 카드를 클릭해 법인별 상세 카드 펼침 동작 확인.
- 14개 법인 행과 각 비중·금액이 모두 렌더링되는지 확인.
- 브라우저 콘솔 오류 없음.

## Comparison history

- Iteration 1: 행 높이와 글자 크기를 소폭 키우고 법인명·보조 정보·비중 막대 사이 간격을 늘렸다.
- Post-fix evidence: 1633 × 918 화면에서 전체 14개 법인과 카드 하단 안내까지 노출되며 P0/P1/P2 이슈가 없음을 확인했다.

## Verification

- `npm run typecheck`: passed
- `npm run lint`: passed
- `git diff --check`: passed
- browser render and expand interaction: passed
- console errors: none

final result: passed

# Design QA — 신규 발주 로직

- source visual truth: 사용자 제공 인라인 목업 3장(발주 제안, 산식 기준 설정, 시나리오 비교)
- implementation screenshot paths:
  - `artifacts/order-v2-proposal-1335x937.png`
  - `artifacts/order-v2-comparison-1335x937.png`
  - `artifacts/order-v2-settings-1335x937.png`
  - `artifacts/order-v2-mobile-390x844.png`
- desktop viewport: 1335 × 937
- mobile viewport: 390 × 844
- review context: 인라인 원본 목업과 브라우저 캡처를 같은 검토 문맥에서 비교

## Full-view comparison evidence

- 목업의 BETA 헤더, 안내 배너, 3개 탭, KPI 카드, 필터, 결과 표의 시각적 계층과 붉은 포인트 컬러를 유지했다.
- 기술명세의 추적성 요구를 반영해 Job ID, 로직버전, 적용모드, 원천 기준시각, 수요기간, 완료주, 계산시각을 별도 메타데이터 영역으로 보강했다.
- 시나리오 비교는 동일 snapshot이라는 전제를 상단 안내와 적용/비교 배지로 명시하고, 수량·신호·금액 차이를 한 표에서 비교할 수 있게 했다.
- 산식 기준 설정은 목적 중심의 시나리오 카드 두 개를 먼저 제공하고, 전문 변수는 접을 수 있는 `고급 산식 설정`으로 분리했다. DB 미연동 상태의 비영속성도 화면에 명시했다.

## Focused region comparison evidence

- 발주 제안 표는 기술명세 산식 결과와 엑셀 표시 컬럼을 함께 보여주므로 목업보다 열이 많다. 데스크톱에서는 가로 스크롤 표, 모바일에서는 SKU 카드로 전환한다.
- 확정수량과 메모를 제안수량과 분리했으며, 데이터상태·등급·발주신호 배지를 서로 다른 색으로 구분했다.
- EUR 입고단가와 참고금액은 권한이 있는 사용자에게만 표시되는 열로 구성했다.
- 다음 ETA와 고갈주수는 컬럼명에 `참고`를 표시해 공식 발주수량 산식과 혼동되지 않게 했다.

## Findings

- P0/P1/P2 차이 없음.
- P3: 데스크톱 결과 표는 표시 컬럼 수가 많아 한 화면에 모든 열이 보이지 않는다. 기술명세 추적성과 엑셀 컬럼 일치를 우선하고 가로 스크롤 및 모바일 카드로 보완했다.
- 개발 모드에서 Next.js의 전역 `scroll-behavior` 안내 경고 1건이 있으나 신규 화면 기능이나 레이아웃에는 영향이 없다.

## Primary interactions tested

- 발주 제안, 시나리오 비교, 산식 기준 설정 탭 전환.
- 브랜드 필터에서 `아누아` 선택 후 6개 행이 2개 카드로 축소되는 동작.
- 390px 모바일에서 표가 SKU 카드로 전환되고 확정수량·메모 입력이 유지되는 동작.
- 계산불가 SKU의 등급·산식값·발주신호가 `–`로 유지되고 확정수량·메모 입력이 잠기는 동작.
- MOQ 배수와 제안수량 변경 메모 검증이 Excel 내보내기 전 동작하는 상태.
- 시나리오 카드의 선택 상태와 고급 산식 설정의 고정 규칙·편집 가능한 숫자 입력 노출.
- 브라우저 콘솔 오류 없음.

## Intentional differences from the mockup

- 기술명세 감사 요구에 따라 실행 메타데이터를 추가했다.
- 기술명세의 두 내부 정책모드는 동일 snapshot으로 모두 계산하지만 사용자 화면에는 `현금흐름 우선`과 `쇼티지 방어` 시나리오로 표시하며 적용 시나리오는 한 개만 선택한다.
- 엑셀 표시 컬럼 기준을 반영해 원재고 구성, IP, MOQ, 확정수량, 메모, 참고 ETA·고갈주수 열을 추가했다.
- DB 구축 전 단계이므로 승인 흐름과 설정 이력 UI는 넣지 않고 세션 적용과 비영속성 안내만 제공한다.

## Verification

- desktop and mobile browser render: passed
- tab/filter responsive interaction: passed
- runtime console errors: none

final result: passed

# Design QA — 전사 재고 현황

- 기준 시안: `C:\Users\USER\.codex\generated_images\01a03731-85ff-7d81-a5b8-7df230f922e3\exec-8bb3f547-2e91-472d-938c-8490c8d578c0.png`
- 구현 캡처: `.codex_tmp/corporate-inventory-ui/implementation-final-desktop.png`
- 동시 비교 이미지: `.codex_tmp/corporate-inventory-ui/reference-vs-implementation.png`
- 비교 뷰포트: 1874 × 839
- 검증 상태: 현재환율 평가액 선택

## 확인 결과

- P0: 없음
- P1: 없음
- P2: 없음
- 정보 구조: 보유재고 평가와 운송중 재고를 분리하고, 관리 기준 총 재고를 고정 합계로 표시함
- 상호작용: 장부금액/현재환율 평가액 토글, 법인 순위·비중 재계산, 창고 상세, 운송중 상세가 동작함
- 시각 일치: 카드 비율, 토글 위치, 금액 위계, 계약환율 배지, 관리 합계 스트립, 2열 법인표를 선택 시안과 동일한 구조로 구현함
- 데이터 의미: 운송중 재고는 계약환율 기준으로 고정되며 보유재고 토글의 영향을 받지 않음

final result: passed

## Latest Product Design QA Status — 발주분석 V3 탭

인증된 인앱 브라우저에서 동일 뷰포트 비교, 모바일 반응형, 탭·필터·드로어·검토 의사결정 흐름까지 검증했다. P0/P1/P2 이슈는 없다.

final result: passed
