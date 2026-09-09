# 원화 환산 연동 인수인계

> 상태: CMS 원화 환산 필드 연동 및 운영 데이터 검산 완료
> 적용 기준일: 2026-08-24
> 적용 범위: 발주분석 V1·V2, 분석 전체, 본사 전사 재고현황

## 1. 목적

과거에는 현지 법인 금액을 화면에서 단일 현재 환율로 다시 원화 환산할 수
있었다. 이 방식은 거래 당시 환율 또는 인보이스 계약환율을 보존하지 못하므로,
2026-08-24부터 CMS가 건별로 제공하는 원화 환산값을 권위값으로 사용한다.

애플리케이션은 현재 환율 API를 다시 호출해 CMS 원화값을 재환산하지 않는다.
API 원통화 금액은 상세 설명과 현지통화 표시를 위해 유지하고, 원화 분석과
합계에는 아래에서 정한 실제 원화 필드를 사용한다.

## 2. API별 원화 필드와 환율 기준

| 대상 | 엔드포인트 | 원화 필드 | 환율 기준 | `xrate_source` |
| --- | --- | --- | --- | --- |
| EU 현지판매 | `/eu/sales/local` | `amount_krw_actual` | 출고일, 반품은 반품처리일의 고시환율 | `DAILY_RATE` |
| US 현지판매 | `/us/sales/local` | `amount_krw_actual` | 출고일, 반품은 반품처리일의 고시환율 | `DAILY_RATE` |
| EU 컨테이너 | `/eu/shipping/containers` | `amount_krw` | 인보이스에 기록된 계약환율 | `INVOICE` |
| US 컨테이너 | `/us/shipping/containers` | `amount_krw` | 인보이스에 기록된 계약환율 | `INVOICE` |
| EU 현지재고 | `/eu/stock/local` | `unit_cost_krw`, `stock_amount_krw` | 조회 기준일 고시환율 | `DAILY_RATE` |
| US 현지재고 | `/us/stock/local` | `unit_cost_krw`, `stock_amount_krw` | 조회 기준일 고시환율 | `DAILY_RATE` |
| 전사 운송중 | `/esm/in-transit` | `amount_krw` | 인보이스에 기록된 계약환율 | `INVOICE` |

CMS 공용 쿼리 구조로 다음 API에도 같은 필드 계약이 함께 적용됐다.

- `/eu/sales/hq-to-eu`, `/us/sales/hq-to-us`: 인보이스 계약환율
- `/eu/stock/hq`, `/us/stock/hq`: 본사 원화 단가이므로 `BASE_KRW`

모든 대상 API는 적용 환율과 근거를 `xrate`, `xrate_dt`, `xrate_source`로
제공한다.

## 3. 필드 사용 규칙

### 판매

- 현지판매 API의 기존 `amount_krw`는 이름과 달리 실제 원화가 아니다.
  CMS 판매내역상세의 법인 기준통화 환산액으로, EUR 판매에서는 원통화 금액과
  같은 값이 내려올 수 있다.
- 실제 원화 매출은 반드시 `amount_krw_actual`을 사용한다.
- 반품은 반품처리일 환율이 적용된 음수 `amount_krw_actual`로 내려오므로
  건별 값을 그대로 합산한다.
- 하위호환을 위해 기존 `amount_krw` 필드는 유지되지만 원화 분석에는 사용하지
  않는다.

### 재고

- 원화 단가는 `unit_cost_krw`, 원화 재고평가액은 `stock_amount_krw`를 사용한다.
- 재고에는 거래일 개념이 없으므로 조회 기준일 환율이 적용된다. 같은 수량과
  현지통화 단가라도 조회일이 달라지면 원화 평가액은 달라질 수 있다.
- API에 표시되는 단가는 소수 둘째 자리까지지만 `stock_amount_krw`는 CMS 내부의
  더 정밀한 평균단가로 계산될 수 있다. 화면 단가 × 수량으로 재계산하지 말고
  `stock_amount_krw`를 권위값으로 합산한다.

### 컨테이너와 전사 운송중

- 인보이스에 남아 있는 계약환율이 실제 거래 근거이므로 `amount_krw`를 그대로
  사용한다.
- 목적지·운송수단·통화별 합계는 인보이스별 `amount_krw`를 먼저 원화로 합산한다.
- `/esm/in-transit`과 EU·US 컨테이너 API의 환율 기준을 `INVOICE`로 통일해 대사
  기준이 달라지는 문제를 방지한다.

### 환율 출처 코드

| 값 | 의미 | 처리 |
| --- | --- | --- |
| `INVOICE` | 인보이스 계약환율 | 컨테이너·운송중·본사 출고에 사용 |
| `DAILY_RATE` | 거래일 또는 조회일 고시환율 | 현지판매·현지재고에 사용 |
| `BASE_KRW` | 원화라 환산 불필요 | 본사 재고에 사용 |
| `UNRESOLVED` | 환율 확인 불가 | 원화 금액 계산을 정상값으로 사용하지 않음 |

고시환율의 `xrate_dt`는 주말·휴일 때문에 거래일보다 앞선 최근 고시 영업일일
수 있다. 계약환율의 `xrate_dt`는 출고일이 아니라 인보이스 계약환율의 기준일일
수 있다.

## 4. 애플리케이션 반영 위치

### 공통 CMS 매핑

- `backend/cms_mapping.py`
  - 판매 `amount_krw_actual` → `실제 원화 환산금액`
  - 호환 별칭 `환산금액`도 실제 원화 환산금액을 가리키도록 설정
  - 재고 `unit_cost_krw` → `CMS 원화 입고단가`
  - 재고 `stock_amount_krw` → `CMS 재고금액(KRW)`
  - 컨테이너 `amount_krw` → `CMS 원화 환산금액`

### 발주분석 V1과 분석 전체

- 최근 판매금액은 거래별 실제 원화금액을 합산한다.
- 재고평가액은 `CMS 재고금액(KRW)`을 합산한다.
- 국가, 브랜드, 제품군, SKU, 시즌 캘린더, 교차분석, 브랜드 리포트와 데이터
  진단은 같은 원화 필드가 매핑된 분석 원천을 사용한다.
- 데이터 입력 화면의 수동 EUR/KRW 환율 입력·재조회·CMS 환율 안내 영역은
  제거했다. 사용자가 입력한 단일 환율로 전체 데이터를 다시 환산하지 않는다.

### 발주분석 V2

- Pareto 매출등급은 판매 `amount_krw_actual`을 SKU별로 합산한다.
- 원화 발주금액은 `제안수량 × unit_cost_krw`로 계산한다.
- 현지통화 단가와 현지통화 발주금액은 별도 표시용으로 유지한다.
- EU V2의 제품 모집단에서는 상품이 아닌 `Delivery Charge`를 의도적으로
  제외한다.

### 본사 전사 재고현황

- 보유재고는 `/esm/stock-ledger`의 법인 `eqty_cost` KRW를 사용한다.
- 운송중은 `/esm/in-transit` 인보이스의 `amount_krw`를 목적지·운송수단별로
  합산한다.
- 인보이스 계약환율이 아니거나 필수 금액·통화·환율이 누락되면 부분 합계나
  0원으로 대체하지 않고 운송중 집계를 실패 처리한다.

## 5. 2026-08-24 운영 데이터 검산 결과

최종 검산 snapshot에서 자동 반영된 본사 API까지 포함해 11개 API의
499,851행을 확인했다.

| 검산 항목 | 결과 |
| --- | ---: |
| 원화 산식 불일치 | 0건 |
| 필수 원화·환율 필드 누락 | 0건 |
| `UNRESOLVED` | 0건 |
| 예상 환율 출처 불일치 | 0건 |
| CMS 원천 → 백엔드 매핑 행 누락 | 0건 |
| 발주분석 V1 원천 대비 화면용 판매·재고 합계 차이 | 0원 |
| 발주분석 V2 원천 대비 매출·원화 제안금액 합계 차이 | 0원 |
| 전사 운송중 인보이스 → 목적지·운송수단 합계 차이 | 0원 |

전사 운송중은 검산 시점의 334개 인보이스 합계
`117,508,469,791원`이 화면용 총합과 일치했다. CMS 운영 데이터는 계속
변경되므로 이후 검산에서는 기준일과 원천 snapshot 생성시각을 함께 기록한다.

재고 검산은 API에 표시된 단가의 둘째 자리 반올림 오차 범위를 고려했다.
이 범위를 벗어난 행은 EU·US 현지재고와 본사재고 모두 0건이었다.

## 6. 테스트와 재검산 기준

관련 백엔드 회귀 테스트:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/test_cms_api_mapping.py `
  tests/test_order_review_unit_price_currency.py `
  tests/test_order_logic_v2_source.py `
  tests/test_eta_actual_krw.py `
  tests/test_corporate_inventory.py `
  tests/test_season_exchange_rate_options.py `
  tests/test_season_cosmetic_scope.py `
  tests/test_sku_concentration_amounts.py -q
```

2026-08-24 실행 결과는 87개 테스트 통과다.

관련 프런트엔드 검증:

```powershell
Set-Location frontend
npm run typecheck
npm test
```

재검산할 때는 다음 순서로 확인한다.

1. API별 모든 행의 필수 원화 필드와 `xrate`, `xrate_dt`, `xrate_source`를 확인한다.
2. 판매·컨테이너·운송중은 원통화 `amount × xrate`와 원화 필드를 비교한다.
3. 재고는 표시 단가의 반올림 범위를 고려하고 `stock_amount_krw`를 권위값으로
   합산한다.
4. CMS 원천 행 수·원화 합계와 `backend/cms_mapping.py` 변환 후 행 수·합계를
   비교한다.
5. V1의 SKU 집중도 판매·재고 합계, V2의 매출·원화 단가·제안금액 합계,
   전사 운송중 목적지·운송수단 합계를 각각 원천과 대사한다.
6. 기준일, API snapshot 생성시각, 허용오차와 의도적 제외 항목을 결과에 남긴다.

API 키, CMS 원문 행, 인보이스 번호와 실제 사용자 데이터는 저장소나 검산
문서에 기록하지 않는다.

## 7. 변경 이력

| 날짜 | 내용 |
| --- | --- |
| 2026-08-24 | EU·US 판매·재고·컨테이너 6개 API에 실제 원화 필드 반영 |
| 2026-08-24 | 공용 쿼리의 본사 출고·본사 재고 API에도 같은 환율 계약 반영 |
| 2026-08-24 | `/esm/in-transit`을 고시환율에서 인보이스 계약환율로 통일 |
| 2026-08-24 | 발주분석 V1·V2, 분석 전체, 전사 재고현황 연동 및 운영 데이터 검산 완료 |
