# Claude Code 프로젝트 규칙

이 저장소의 실제 애플리케이션 루트는 `ESM_SCM8/`이다.

## 금액·발주 산식 변경 시 작업 방식

사용자는 비개발자이며 바이브코딩으로 작업한다. 코드만 보고 계산 결과의
정합성을 스스로 판단하기 어려우므로, 검증은 예시 숫자와 설명에 의존한다.
신규 V2뿐 아니라 **기존 발주분석·재고갭·환율 환산 등 금액·수량이 걸린 산식**
전체에 적용한다.

1. 금액·발주 산식(신규든 기존이든)에 손대는 작업은 실행 전에 항상 계산
   계획을 자연어로 설명하고 진행 여부를 확인받은 뒤 진행한다. 작은 수정이라도
   건너뛰지 않는다.
2. 계산 로직을 설명할 때는 손으로 검증 가능한 구체적 예시 숫자 1~2개를
   함께 제시한다. 예: "SKU A: 재고 100 + 입고 50 − 판매 30 = 120, 목표재고
   150 대비 부족분 30이 발주필요수량."
3. "테스트 통과"를 "결과가 맞다"와 동일시하지 않는다. 금액·수량이 걸린
   화면이나 Excel 결과는 실제 화면·파일을 열어 예시 숫자로 대조하도록
   안내한다.

## 신규 발주 로직 V2 작업 전 필독

신규 발주 로직을 수정하거나 검토할 때는 먼저
[`ESM_SCM8/docs/ORDER_LOGIC_V2_HANDOFF.md`](ESM_SCM8/docs/ORDER_LOGIC_V2_HANDOFF.md)를
끝까지 읽는다.

핵심 원칙:

1. 발주 산식의 최상위 기준은 사용자가 제공한
   `EU_발주로직_웹개발_기술명세서.html`이다.
2. `EU_발주로직_버전2_확정_로직설명서.html`은 산식 의도와 업무 해석의
   보조 자료다.
3. `ESM_CV발주템플릿_v4.0_리드타임시그마수동입력.xlsx`는 화면·내보내기
   컬럼명과 검산 예시를 참고하는 자료다. 엑셀 예시가 기술명세의 기본 산식을
   덮어쓰면 안 된다.
4. 2026-07-28 사용자 결정에 따라 MOQ 개념은 V2에서 제거했다. 제안수량은
   MOQ 배수 대신 원시 발주량을 낱개 단위로 올림한다.
5. 기존 발주분석과 V2는 독립 기능이다. V2 변경을 이유로 기존 발주 산식이나
   기존 API 응답을 바꾸지 않는다.
6. (2026-09-04 사용자 결정으로 대체) V2의 사이드바/타이틀 `BETA` 표시는
   제거했다. 이 항목의 이전 버전(V2는 계속 BETA로 표시, 제거 금지)은 더 이상
   유효하지 않다. 승인 워크플로 추가는 여전히 별도 논의 없이 임의로 하지
   않는다.
7. 두 정책모드 `CASH`와 `SHORTAGE`를 항상 같은 원천 snapshot으로 계산해
   비교 가능하게 유지한다. 공식 적용모드는 한 개만 선택한다.
   사용자 화면에서는 내부 용어인 `정책모드`를 노출하지 않고
   `현금흐름 우선 시나리오`, `쇼티지 방어 시나리오`로 표시한다.
8. 현재 연동 가능한 법인은 PL이다. 현 구현은 아직
   `(entity_code, transport_mode)`별 리드타임 테이블 구조가 아니므로, 다른
   법인까지 계산된다고 추정하거나 UI에 불필요한 법인 표시를 추가하지 않는다.
9. DB 구축은 후속 작업이다. 현재 설정과 실행 결과의 영속성을 DB가 있다고
   가정해 구현하지 않는다.
10. 금액·단가 필드는 기존 권한 정책을 반드시 통과시킨다. 신규 응답이나
   Excel 내보내기로 금액 권한을 우회하지 않는다.
11. V2 상단 KPI의 사용자 용어는 `즉시발주 SKU`, `발주필요 SKU`,
    `총 발주필요수량`, `총 발주필요금액`이다. 금액은 기존 환율 API로 원화 환산하되
    환율 실패와 단가 누락을 숨기지 않는다.
12. 2026-08-13 확정: PL V2의 발주 수요 표본에서는 CMS 판매행 중
    `amount < 0`이면서 `qty > 0`인 행을 제외한다. 검증 시점의 이 패턴은
    전수 대사에서 확정 사고처리와 일치했지만, API가 사고처리 원천 구분값을
    제공하지 않아 필드 형태로 판별하는 V2 전용 원천 정제 규칙이다. 이 규칙을
    기존 발주분석이나 공통 `core/sales.py`로 옮기지 않는다. 정상 양수
    `자사간거래(SELF)`는 계속 포함한다.

## 코드 경계

- 순수 산식: `ESM_SCM8/core/order_logic_v2.py`
- CMS 원천 매핑: `ESM_SCM8/backend/services/order_logic_v2_source.py`
- 실행·정책 비교·권한·감사: `ESM_SCM8/backend/services/order_logic_v2_service.py`
- API: `ESM_SCM8/backend/routers/order_logic_v2.py`
- Excel: `ESM_SCM8/backend/services/order_logic_v2_excel.py`
- 화면: `ESM_SCM8/frontend/components/redesign/screens/order-v2/`
- 프런트 API 클라이언트: `ESM_SCM8/frontend/lib/api/order-logic-v2.ts`
- V2 테스트: `ESM_SCM8/tests/test_order_logic_v2*.py`

산식을 바꿀 때는 소스 매핑이나 UI에서 우회 계산하지 말고 순수 산식 모듈과
해당 테스트를 함께 수정한다. 기술명세에 없는 새로운 기본값이나 fallback을
임의로 만들지 않는다.

## 발주분석 V3 전체 로직 작업 전 필독

발주분석 V3 전체 로직(SES, HOLT+감쇠, Croston+SBA, 상품분류, 재고위치,
Layer 1·2·3, ROP, 목표재고, 발주수량)을 수정하거나 검토할 때는 먼저
[`ESM_SCM8/docs/ORDER_LOGIC_V3_DISCOVERY_HANDOFF.md`](ESM_SCM8/docs/ORDER_LOGIC_V3_DISCOVERY_HANDOFF.md)를
끝까지 읽는다. 인터뷰가 끝나지 않은 산식·상수·초기화·fallback을 교과서 예시,
테스트베드 또는 프런트 fixture에서 가져와 구현하지 않는다.

## 발주분석 V3 시즌팩터 작업 전 필독

V3의 시즌팩터, 계절지수, 계절 보정, 월간 사전계산 또는 팩터 배포를 수정·검토할
때는 먼저
[`ESM_SCM8/docs/ORDER_V3_SEASON_FACTOR_SPEC.md`](ESM_SCM8/docs/ORDER_V3_SEASON_FACTOR_SPEC.md)를
끝까지 읽는다.

- 인터뷰 결정 로그의 미결 항목을 코드 기본값이나 fallback으로 추정하지 않는다.
- 월간 사전계산과 웹 요청 계산의 경계를 유지한다.
- 프런트에서 운영 팩터를 계산하거나 하드코딩하지 않는다.
- 발주수량에 영향을 주는 변경 전에는 자연어 계산 계획과 손검산 예시를 제시하고
  사용자 승인을 받는다.
- 승인된 팩터 버전·관측기간·적용값이 API, 화면, Excel에서 추적 가능해야 한다.
- CMS 원본 판매행과 민감정보를 팩터 artifact나 저장소에 기록하지 않는다.

## 검증 명령

Windows PowerShell 기준:

```powershell
cd ESM_SCM8
.\.venv\Scripts\python.exe -m pytest `
  tests/test_order_logic_v2.py `
  tests/test_order_logic_v2_source.py `
  tests/test_order_logic_v2_api.py `
  tests/test_order_logic_v2_excel.py -q

cd frontend
npm run typecheck
npm test
$env:FASTAPI_INTERNAL_BASE_URL='http://127.0.0.1:8002'
npm run build
```

프로덕션 빌드에서는 `FASTAPI_INTERNAL_BASE_URL`이 필수다. 실제 비밀값,
API 키, 사용자 데이터 또는 CMS 원문을 문서·fixture·커밋에 넣지 않는다.

## Git 작업 규칙

- 작업 시작 전 `git status --short --branch`로 기존 변경을 확인한다.
- 사용자 변경을 덮어쓰거나 정리하지 않는다.
- 신규 발주 로직과 무관한 변경은 같은 커밋에 섞지 않는다.
- push 전 테스트 결과와 커밋 범위를 확인한다.
