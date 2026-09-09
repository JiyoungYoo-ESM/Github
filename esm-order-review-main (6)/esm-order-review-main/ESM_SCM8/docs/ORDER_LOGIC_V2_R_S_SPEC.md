# 발주분석 V2 4주 정기보충 `(R,S)` 통합 기술명세

작성일: 2026-08-14  
마지막 갱신: 2026-08-24
상태: **사용자 승인 계산 계획 — 2026-08-24 수요기간 변경 반영 기준 문서**
적용 대상: `HQ/OPO`, `PL/Europe`, `USA`

## 0. 문서의 권위와 사용법

이 문서는 사용자가 제공한 다음 두 자료와 2026-08-14 인터뷰 결정을 합쳐,
발주분석 V2의 목표 산식을 코드로 구현할 수 있도록 정리한 저장소 내 기준이다.

- 저장소 밖 `ORDER_LOGIC_REPLENISHMENT_R_S_MODEL.md`
- 저장소 밖 `오포_미주_유럽_4주정기발주_UIUX개선본.html`
- 2026-08-14 사용자 인터뷰 확정사항

외부 자료는 참고 원문이며 저장소에 복사하지 않는다. 외부 자료의 계산 오류,
MOQ 문구, USA 운송수단 설명처럼 이 문서와 충돌하는 내용은 이 문서의 날짜별
사용자 결정을 우선한다.

이 문서는 **목표 명세와 공통 수요 제외 규칙의 현재 기준**이다. 전체 V2 산식의
세부 구현 상태는 코드와 handoff 문서를 함께 확인한다.
다음 문서도 함께 읽는다.

- [`ORDER_LOGIC_V2_HANDOFF.md`](ORDER_LOGIC_V2_HANDOFF.md)
- [`HQ_ORDER_ANALYSIS_HANDOFF.md`](HQ_ORDER_ANALYSIS_HANDOFF.md)
- 현재 코드 기준 요약인 `ORDER_LOGIC_V2_FORMULAS_BY_ENTITY.md`가 존재하면 함께 비교

기존 발주분석 V1의 전체 산식은 이 명세의 적용 대상이 아니지만, RS-014의
`amount < 0 AND qty > 0` 공통 수요 제외 규칙은 V1에도 동일하게 적용한다.
확정되지 않은 필드명, 원천 endpoint, fallback, 필터를 이 문서의 의도라고
추정해 구현하지 않는다.

## 1. 범위와 기능 경계

| 법인 | 의미 | 목표 상태 |
| --- | --- | --- |
| `HQ` | 본사, 창고 `OPO` | 현재 열려 있는 V2 탭에 신규 `(R,S)` 계산을 연결한다. 기존 데이터 입력과 V1은 계속 비활성화한다. |
| `PL` | 첨부 자료의 `Europe` | 현행 V2 원천을 유지하면서 목표 `(R,S)` 산식으로 전환한다. |
| `USA` | 첨부 자료의 `미주` | 현행 V2 원천을 유지하면서 목표 `(R,S)` 산식으로 전환한다. |
| `UK/ME/MX/MY/VN` | 기타 법인 | 이 명세의 범위가 아니며 PL/USA/HQ 값으로 fallback하지 않는다. |

공통 기능 경계:

- `CASH`와 `SHORTAGE`를 하나의 immutable source snapshot으로 항상 함께 계산한다.
- 공식 기본 적용 시나리오는 `SHORTAGE`다.
- 사용자는 화면에서 두 시나리오를 전환해 볼 수 있다.
- Excel은 사용자가 현재 선택한 시나리오를 같은 snapshot인지 검증한 뒤 출력한다.
- 분석 실행과 Excel 출력은 언제든 가능하다.
- `R=4주`는 산식 파라미터이며 분석 실행을 4주에 한 번으로 제한하는 gate가 아니다.
- 승인 워크플로, 구매요청 자동 전송, RS-014 외의 V1 변경은 이 명세 범위 밖이다.
- `BETA` 표시는 유지한다.

## 2. 기호와 단위

| 기호 | 의미 |
| --- | --- |
| `d_bar` | 단위기간 평균 유효수요 |
| `sigma_d` | 단위기간 수요의 표본표준편차 `STDEV.S` |
| `L` | 평균 리드타임 |
| `sigma_L` | 리드타임의 표본표준편차 `STDEV.S` |
| `R` | 정기보충 주기, HQ 28일·PL/USA 4주 |
| `P` | 보호기간, `L + R` |
| `Z` | 시나리오·Pareto 등급별 서비스 계수 |
| `SS` | fence 적용 후 안전재고 |
| `S` | 정기 목표재고 |
| `IP` | 재고 위치(보유전체) |
| `Q` | 낱개 단위 최종 제안수량 |

단위 불변조건:

- HQ는 `d_bar`, `sigma_d`, `L`, `sigma_L`, `R`, `P`, SS fence를 모두 **일** 단위로 계산한다.
- PL과 USA는 위 값을 모두 **주** 단위로 계산한다. 일 단위 LT와 `sigma_L`은 `/7`로 환산한다.
- 프런트의 기존 설명에서 주평균수요를 `R`이라고 부르는 표현은 제거한다. 수요평균은 `d_bar`, `R`은 보충주기로만 사용한다.

## 3. 목표 `(R,S)` 산식

SKU와 시나리오별로 다음을 계산한다.

```text
P = L + R

Layer1 = d_bar * L

SS_raw =
  Z * sqrt(P * sigma_d^2 + d_bar^2 * sigma_L^2)

SS_floor = d_bar * ss_floor_periods
SS_cap   = d_bar * ss_cap_periods
SS       = min(max(SS_raw, SS_floor), SS_cap)

Layer3 = d_bar * R

S = Layer1 + SS + Layer3
  = d_bar * (L + R) + SS

raw_Q = max(0, S - IP)
Q     = ceil(raw_Q)
```

불변조건:

- 기존 조건부 발주점 `s`와 `IP < s` gate를 사용하지 않는다.
- 분석을 실행한 시점마다 `S - IP`를 계산한다.
- 중간값은 소수 정밀도를 유지하고 최종 `Q`만 낱개 단위로 올림한다.
- MOQ, 박스입수, 공급사 발주배수는 사용하지 않는다.
- `Q`가 음수이면 0이다.
- CASH와 SHORTAGE는 수요, 재고, Pareto 모집단, source snapshot을 공유한다.

## 4. 법인별 정책 레지스트리

| 항목 | `HQ/OPO` | `USA` | `PL/Europe` |
| --- | --- | --- | --- |
| 수요 grain | SKU × 일 | SKU × 주 | SKU × 주 |
| 수요 관측창 | 직전 완료 91일 | 직전 완료 13주 | 직전 완료 13주 |
| 현재 일/주 | 제외 | 제외 | 제외 |
| 무수요 기간 | 0으로 채움 | 0으로 채움 | 0으로 채움 |
| `R` | 28일 | 4주 | 4주 |
| LT 완료 관측창 | 최근 12개월 | 최근 12개월 | 최근 12개월 |
| SS 하한 | 14일분 | 2주분 | 2주분 |
| SS 상한 | 35일분 | 8주분 | 13주분 |
| CASH 운송/LT | HQ 국내조달 공통 LT | AIR | RAIL |
| SHORTAGE 운송/LT | HQ 국내조달 공통 LT | SEA | SEA |
| 시나리오 차이 | Z만 다름 | Z, `L`, `sigma_L`이 다름 | Z, `L`, `sigma_L`이 다름 |
| MOQ/배수 | 없음 | 없음 | 없음 |

Pareto와 Z는 다음을 유지한다.

| 시나리오 | MAJOR | MINOR |
| --- | ---: | ---: |
| `CASH` | 1.28 | 1.08 |
| `SHORTAGE` | 1.68 | 1.28 |

- 매출 누적 80% 기준으로 `MAJOR/MINOR`를 구분한다.
- 공식 기본 적용 시나리오는 `SHORTAGE`다.
- SS fence는 두 시나리오에 동일하고 Z 및 법인별 LT 입력만 달라진다.

## 5. 수요 계약

### 5.1 HQ/OPO

- API는 발주수요로 유효한 OPO 국내 B2B 수요만 반환한다.
- 반품, 취소, `FREE SAMPLE` 등 무상샘플 거래행 및 발주수요로 인정하지 않는
  내부 처리는 API 모집단에서 제외한다.
- 상품명 또는 SKU 속성이 샘플·샤쉐·사쉐라는 이유만으로 상품을 제외하지 않는다.
  허용 거래유형의 정상 출고수량은 발주 수요에 포함한다(RS-020).
- V2의 최소 입력 grain은 `demand_date + sku_code + net_demand_qty`다.
- 직전 완료 91개 달력일을 사용하고 판매가 없는 날짜는 0으로 채운다.
- `d_bar`는 91개 일별 값의 산술평균, `sigma_d`는 `STDEV.S`다.
- HQ는 간헐 판정을 적용하지 않는다(RS-018). PL/USA의 현재 기준인 `13주 중
  7주`를 일 단위 비율로 옮기면 `91일 중 49일`이 되어 주말·공휴일이 0으로
  고정되는 HQ 조달 패턴을 과도하게 간헐로 분류한다. 판매없음과 대량포함
  판정은 유지한다.
- 대량포함 판정은 `최대 일판매 > 3 × (총판매 ÷ 판매일수)`로, 무판매일을 제외한
  실제 판매일 평균과 비교한다(RS-017). 91일 평균과 비교하면 판매일이 31일
  미만인 SKU가 수치와 무관하게 항상 위반이 된다.
- 발주량 산식의 `d_bar`는 91일 평균이다. 위 변경은 데이터 품질 판정에만
  적용하며 `S`와 `Q`를 바꾸지 않는다.
- API가 유효 순수요만 반환한다는 계약을 V2가 임의의 거래유형 추정으로 재구현하지 않는다.

### 5.2 PL/USA

- 직전 완료 13개 Monday–Sunday 주를 사용한다.
- 판매가 없는 주는 0으로 채운다.
- `d_bar`는 13개 주별 값의 산술평균, `sigma_d`는 `STDEV.S`다.
- 대량포함 판정은 `최대 주판매 > 3 × (총판매 ÷ 판매 주수)`로, 무판매 주를 제외한
  실제 판매 주 평균과 비교한다(RS-017). 13주 평균과 비교하면 판매 주가 5주
  미만인 SKU가 수치와 무관하게 항상 위반이 된다.
- 발주량 산식의 `d_bar`는 13주 평균이다. 위 변경은 데이터 품질 판정에만
  적용하며 `S`와 `Q`를 바꾸지 않는다.
- PL과 USA는 공통 `amount < 0 AND qty > 0` 수요 제외 규칙을 적용한다.
- 이 행은 확인된 사고처리이므로 수요수량과 Pareto 등급 매출에서 모두 제외한다(RS-014). 사고처리가 정상 SKU의 등급을 끌어내리지 않는다.
- 정상 양수 `SELF`는 기존처럼 해당 법인의 수요에 계속 포함한다.
- 상품명 또는 SKU 속성이 샘플·샤쉐·사쉐라는 이유만으로 상품을 제외하지 않는다.
  법인별 허용 거래유형의 정상 출고수량은 포함하고 `FREE SAMPLE` 등 무상샘플
  거래행만 기존 거래유형 필터로 제외한다(RS-020).
- USA도 기존 승인 판매 모집단과 필터를 유지하되, 해당 사고처리 행만 공통 규칙으로 제외한다.

## 6. 리드타임 계약

### 6.1 공통

- 완료일/실입고일이 기준일 직전 12개월 안에 있는 표본을 사용한다.
- 시작일은 LT 계산에 필요하므로 완료 관측창보다 이전일 수 있다.
- 평균은 산술평균, 변동성은 표본표준편차 `STDEV.S`다.
- 입고수량으로 가중하지 않는다.
- 실제 적용 기간, 표본 수, 평균, 표준편차, 제외 건수와 원천 hash를 실행 snapshot에 남긴다.

### 6.2 HQ/OPO

API 반환 한 행의 의미:

```text
실제 입고가 완료된 유효한 PO × SKU 기록 1건
```

최소 필드:

```text
po_number
sku_code
po_created_at
actual_received_at
```

계산:

```text
sample_LT_days = actual_received_at - po_created_at

HQ_L_days       = mean(최근 12개월의 모든 유효 PO×SKU sample_LT_days)
HQ_sigma_L_days = STDEV.S(최근 12개월의 모든 유효 PO×SKU sample_LT_days)
```

HQ 불변조건:

- 모든 HQ SKU에 하나의 HQ 전체 통합 `L`, `sigma_L`을 공통 적용한다.
- 각 `PO × SKU` 입고 건은 입고수량과 무관하게 동일한 표본 1건이다.
- SKU별, 브랜드별, 공급사별 LT를 계산하지 않는다.
- SKU별 또는 타 법인 fallback을 사용하지 않는다.
- CASH와 SHORTAGE는 같은 `HQ_L_days`, `HQ_sigma_L_days`를 쓰고 Z만 바꾼다.
- API가 취소·미입고를 제외한 실제 완료 유효 건만 반환한다는 원천 계약을 사용한다.
- 5~6주는 업무상 예상 범위이지 LT hard cutoff가 아니다. 별도 승인 없이 35일·42일 상한 필터를 넣지 않는다.
- `STDEV.S`의 수학적 전제상 HQ 전체 유효 표본이 2건 미만이면 계산할 수 없다. 임의 fallback을 만들지 않는다.

### 6.3 PL/USA

- PL은 시나리오별 `RAIL`, `SEA` 완료 Packing No 표본을 각각 집계한다.
- USA는 시나리오별 `AIR`, `SEA` 완료 Packing No 표본을 각각 집계한다.
- 각 운송수단별 `L_days = mean(days)`, `sigma_L_weeks = STDEV.S(days) / 7`이다.
- 현행 6개월 완료 관측창을 12개월로 변경한다.
- Packing No 중복 접기와 충돌 Packing 제외 등 현행 원천 grain은 유지한다.
- 현행 `1~180일` 유효기간과 운송수단별 최소 2건 차단 규칙은 새 `(R,S)`에서도 그대로 유지한다(RS-013). 표본이 2건 미만이면 계산을 차단하며 임의 fallback을 만들지 않는다.

## 7. 재고 위치 `IP`

### 7.1 HQ/OPO

```text
qty_incoming = ① 미입고 + ② PNFM확정 + ③ 입고진행중

IP = qty_incoming
   + qty_opo_available
```

- `qty_incoming`: `open-po` ①과 `inbound/confirmed` ②·③의 합
- shipping 운송중은 HQ/OPO IP에서 제외한다.
- `qty_opo_available`: OPO 창고 가용재고
- ④ 입고완료는 OPO 가용재고에 반영됐으므로 표시만 한다.
- 실제 API 필드명이 위 이름과 다르면 source adapter에서 의미를 명시적으로 매핑한다.

### 7.2 PL/USA

```text
qty_incoming = ① 미입고 + ② PNFM확정 + ③ 입고진행중
qty_in_transit = 법인별 shipping 운송중

IP = qty_incoming
   + qty_hq_available
   + qty_in_transit
   + qty_local_available
```

- 법인별 기존 원천 매핑을 유지한다.
- 같은 물량이 미입고·HQ 가용·운송중·현지가용에 중복되지 않아야 한다.
- PL과 USA가 같은 HQ 재고를 동시에 전량 가용으로 계산하지 않도록 원천의 법인별 할당 의미를 확인한다.
- 2026-08-19 최종 확정(RS-023): PL/EU와 USA 모두 `open-po` ①+②+③을
  `qty_incoming`으로 사용하고, 법인별 shipping SKU 수량을 `qty_in_transit`으로
  별도 가산한다. ④는 Excel 원천 확인용으로만 표시하고 IP에는 더하지 않는다.
  이 결정은 RS-022와 PL/EU shipping 제외 매핑을 대체한다.

## 8. 화면·API·Excel 계약

### 8.1 화면

- HQ는 일 단위, PL/USA는 주 단위로 레이블과 검산값을 표시한다.
- `reorder_point_s`에 기반한 설명과 `IP < s` 발주 신호는 제거 또는 목표 산식에 맞게 대체한다.
- 화면에는 최소한 `d_bar`, `sigma_d`, `L`, `sigma_L`, `R`, `P`, `SS_raw`, 적용 SS, `S`, `IP`, `Q`를 검산 가능하게 제공한다.
- 기본 제안수량과 미입고 제외 상한수량을 기존처럼 함께 표시한다(RS-015). 두 값은 미입고를 신뢰할 때와 신뢰하지 않을 때의 발주량이며, 공식 계산값은 기본 제안수량이다.
- 상단 KPI 명칭은 기존 문구를 그대로 유지한다(RS-016). `s` 제거와 무관하게 KPI 레이블 개편은 이 명세의 범위가 아니다.
- 결과 identity로 `entity_code`, `warehouse_code`, `timezone`, `currency_code`, `policy_version`, `source_snapshot_id`를 표시 또는 보존한다.
- 법인 또는 창고가 현재 선택과 다른 결과는 표시하지 않는다.
- HQ V2 탭은 유지하고 HQ의 기존 데이터 입력과 V1은 계속 비활성화한다.

### 8.2 API

- 현재 async jobs/latest/export 흐름과 클라이언트 소유권 검증을 유지한다.
- 결과에는 두 시나리오를 모두 포함하고 `applied_mode`로 공식 결과를 구분한다.
- `upper_suggested_qty`와 `inventory_position_without_incoming`은 참고값으로 계속 응답에 포함한다.
- `reorder_point`는 목표 모델에서 사용하지 않는다. 필드 제거 또는 deprecated/null 호환 정책은 schema version 변경 시 명시한다.
- 법인·창고·시간대·정책 version이 없는 이전 결과를 새 결과로 재사용하지 않는다.
- HQ adapter나 승인된 법인 정책이 없으면 계산을 차단하며 PL/EUR/Warsaw 값으로 fallback하지 않는다.

### 8.3 Excel

- 화면에서 선택한 `export_mode`의 시나리오를 동일 snapshot 검증 후 출력한다.
- 법인별 단위와 `Layer1`, `SS_raw`, 적용 SS, `Layer3`, `S`, `IP`, `raw_Q`, `Q` 검산열을 제공한다.
- MOQ/배수 관련 문구와 검증을 제거한다.
- 적용 법인·창고·시간대·정책 version·기준기간·LT 표본기간·표본 수를 기록한다.
- 기존의 담당자 검토수량/메모 계약을 바꾸려면 별도 결정을 받는다.

## 9. 정정된 손검산 예시

아래 값은 산식 회귀 테스트의 기준 예시다. 외부 Markdown의 잘못된 중간값을
fixture 정답으로 사용하지 않는다.

### 9.1 HQ/OPO

```text
d_bar=15/day, sigma_d=9/day
L=12 days, sigma_L=6 days, R=28 days
Z=1.68, IP=150

P = 12 + 28 = 40
SS_raw = 1.68 * sqrt(40 * 9^2 + 15^2 * 6^2)
       = 1.68 * sqrt(3,240 + 8,100)
       = 178.90
SS_floor = 15 * 14 = 210
SS_cap   = 15 * 35 = 525
SS = 210
S = 15 * 12 + 210 + 15 * 28 = 810
Q = ceil(max(0, 810 - 150)) = 660
```

### 9.2 USA

```text
d_bar=80/week, sigma_d=50/week
L=8 weeks, sigma_L=1.2 weeks, R=4 weeks
Z=1.68, IP=650

P = 12
SS_raw = 1.68 * sqrt(12 * 50^2 + 80^2 * 1.2^2)
       = 332.69
SS = 332.69  (floor=160, cap=640)
S = 80 * 8 + 332.69 + 80 * 4 = 1,292.69
Q = ceil(1,292.69 - 650) = 643
```

### 9.3 PL/Europe

```text
d_bar=60/week, sigma_d=40/week
L=9.14 weeks, sigma_L=1.5 weeks, R=4 weeks
Z=1.68, IP=410

P = 13.14
SS_raw = 1.68 * sqrt(13.14 * 40^2 + 60^2 * 1.5^2)
       = 1.68 * sqrt(21,024 + 8,100)
       = 286.70
SS = 286.70  (floor=120, cap=780)
S = 60 * 9.14 + 286.70 + 60 * 4 = 1,075.10
Q = ceil(1,075.10 - 410) = 666
```

## 10. 구현 경계

| 변경 영역 | 구현 위치 |
| --- | --- |
| 순수 `(R,S)` 산식, 법인별 일/주 단위, SS fence | `core/order_logic_v2.py` |
| HQ/PL/USA source adapter와 수요·IP 매핑 | `backend/services/order_logic_v2_source.py` 및 entity-specific adapter |
| 12개월 LT 집계, HQ 전체 PO×SKU LT | `backend/services/order_logic_v2_lead_time.py` 또는 HQ 전용 LT 모듈 |
| 법인 정책 snapshot, 두 시나리오, 결과 identity | `backend/services/order_logic_v2_service.py` |
| HQ 허용 gate와 API schema | `backend/routers/order_logic_v2.py`, `backend/schemas_order_logic_v2.py` |
| Excel 검산열·단위·메타데이터 | `backend/services/order_logic_v2_excel.py` |
| 법인별 화면 문구·시나리오·산식 설명 | `frontend/components/redesign/screens/order-v2/` |

산식은 source adapter, service, UI 또는 Excel에서 복제하지 않는다. 순수 코어가
단일 구현 지점이며 나머지 계층은 승인된 입력과 결과를 전달·표시한다.

## 11. 필수 검증

### 11.1 순수 산식

- HQ 정답 `Q=660`
- USA 정답 `Q=643`
- PL 정답 `Q=666`
- `IP >= S`이면 `Q=0`
- SS 하한·상한 경계
- 최종 수량만 낱개 올림
- MOQ/배수 미적용
- `s`와 `IP < s` gate 미사용

### 11.2 기간과 단위

- HQ 직전 완료 91일과 일별 zero-fill
- PL/USA 직전 완료 13주와 주별 zero-fill
- HQ 일 단위 LT, PL/USA `/7` 주 단위 환산
- 세 법인 모두 최근 12개월 완료 LT 관측창

### 11.3 법인·원천 격리

- HQ가 PL/USA endpoint, EUR, Warsaw, PL 정책값을 사용하지 않음
- PL/USA/HQ 전환 시 이전 법인 결과가 남지 않음
- `entity_code + warehouse_code + policy_version + snapshot_id` 일치
- HQ adapter가 없거나 핵심 원천이 실패하면 계산 차단

### 11.4 시나리오·Excel

- CASH/SHORTAGE가 동일 source snapshot과 SKU 모집단 사용
- HQ는 동일 LT·다른 Z
- USA는 AIR/SEA, PL은 RAIL/SEA 매핑
- 화면에서 선택한 시나리오와 Excel 수량·메타데이터 일치

## 12. 구현 전에 남은 미결사항

다음은 이 인터뷰에서 확정되지 않았다. 별도 사용자 결정 또는 실제 API 명세
없이 구현 기본값을 만들지 않는다.

1. HQ API의 실제 endpoint, 정확한 필드명, unique key, schema version, freshness 계약.
2. HQ·PL·USA의 최종 timezone과 day/week boundary를 결과 identity에 어떻게 기록할지.
3. HQ 단가·통화 및 발주금액 표시 계약.

2026-08-14 2차 결정으로 종결된 항목은 아래 결정 로그의 `RS-013`~`RS-016`을
참고한다. 종결된 항목을 다시 미결로 되돌리지 않는다.

## 13. 결정 로그

| ID | 상태 | 결정 |
| --- | --- | --- |
| RS-001 | 확정 | 목표 `(R,S)`를 HQ·PL·USA 모두에 적용하며 Europe은 PL을 뜻한다. |
| RS-002 | 확정 | HQ는 V2 탭을 사용하고 기존 데이터 입력과 V1은 계속 비활성화한다. |
| RS-003 | 확정 | CASH/SHORTAGE를 같은 snapshot으로 함께 계산하고 공식 기본은 SHORTAGE, Excel은 현재 선택 시나리오로 출력한다. |
| RS-004 | 확정 | HQ는 동일 국내조달 LT와 `sigma_L`을 두 시나리오에 쓰고 Z만 변경한다. PL은 CASH=RAIL/SHORTAGE=SEA, USA는 CASH=AIR/SHORTAGE=SEA다. |
| RS-005 | 확정 | 세 법인의 LT 완료 관측창은 최근 12개월이다. |
| RS-006 | 확정 | HQ LT는 유효 완료 `PO×SKU`별 `실제 입고일 - PO 생성일`을 동일 가중으로 모은 HQ 전체 평균과 `STDEV.S`다. |
| RS-007 | 확정 | HQ LT는 SKU별·브랜드별로 나누지 않고, SKU별 fallback도 사용하지 않는다. |
| RS-008 | 대체됨 | HQ 미입고+운송중+OPO 가용재고 정의는 RS-023이 대체한다. |
| RS-009 | 확정 | MOQ·박스입수·발주배수 없이 `ceil(max(0, S-IP))`를 사용한다. |
| RS-010 | 확정 | 분석과 Excel은 언제든 실행 가능하며 R=4주는 실행 gate가 아닌 산식 파라미터다. |
| RS-011 | 확정 | SS fence는 HQ 14~35일, USA 2~8주, PL 2~13주다. |
| RS-012 | 확정(명확화됨) | HQ 수요 API는 반품·취소·무상샘플 거래행 등을 제외한 발주용 유효 순수요를 반환한다. 상품 자체가 샘플·샤쉐인지는 RS-020을 따른다. |
| RS-013 | 확정 | PL·USA LT 데이터 품질 계약인 `1~180일` 유효기간과 운송수단별 최소 2건 차단 규칙을 새 `(R,S)`에서도 유지한다. |
| RS-014 | 확정 | 모든 법인·본사에서 `amount < 0 AND qty > 0` 행은 확인된 사고처리 조정으로 간주해 발주 수요수량과 Pareto 등급 매출에서 모두 제외한다. 원본 판매내역과 재무용 순매출은 보존하고, 제외 건수·수량·금액·Biz Type 분포를 감사정보에 기록한다. |
| RS-015 | 확정 | 미입고 포함 기본 제안수량과 미입고 제외 상한수량을 기존처럼 함께 제공한다. 공식 계산값은 기본 제안수량이다. |
| RS-016 | 확정 | 상단 KPI 명칭은 기존 문구를 그대로 유지하고 이번 범위에서 개편하지 않는다. |
| RS-017 | 확정 | 대량포함 판정은 전체 기간 평균이 아니라 실제 판매 기간 평균(`총판매 ÷ 판매 기간수`)의 3배와 비교한다. HQ는 판매일수, PL/USA는 판매 주수를 분모로 쓰며 수요 단위는 각각 일·주로 유지한다. 당시 전체 기간은 HQ 91일, PL/USA 13주였고 RS-019가 한때 84일/12주로 변경했으나 현재 기간은 RS-024가 다시 91일/13주로 확정한다. |
| RS-018 | 확정 | HQ 발주분석 V2는 간헐 판정을 적용하지 않는다. PL/USA의 판매 7주 미만 기준은 수요 관측기간이 바뀌어도 유지한다. |
| RS-019 | 대체됨 | 2026-08-15 사용자 결정으로 V2 수요 관측기간을 PL·USA 12주, HQ 84일로 변경했으나 RS-024가 대체한다. |
| RS-020 | 확정 | 2026-08-18 사용자 결정으로 `FREE SAMPLE` 등 무상샘플 거래행은 계속 제외하되, 상품명 또는 SKU 속성이 샘플·샤쉐·사쉐라는 이유만으로 상품을 제외하지 않는다. 법인별 허용 거래유형의 정상 출고수량은 HQ·PL·USA V2 발주 수요에 포함한다. |
| RS-021 | 대체됨 | 2026-08-18 USA ②·③ 표시 전용 결정은 2026-08-19 RS-022가 대체한다. |
| RS-022 | 대체됨 | USA ①+②+③ 및 shipping 가산 결정은 RS-023의 전 법인 공통 정의로 통합됐다. |
| RS-023 | 확정 | PL/EU·USA는 `IP=(①+②+③)+본사 해당 법인창고 가용+shipping 운송중+현지가용`, HQ/OPO는 `IP=(①+②+③)+OPO 가용`으로 계산한다. HQ shipping 운송중과 전 법인의 ④ 입고완료는 IP에서 제외한다. |
| RS-024 | 확정 | 2026-08-24 사용자 결정으로 V2 수요 관측기간을 13주 상당으로 변경한다. PL·USA는 현재 주를 제외한 직전 완료 13주, HQ는 현재일을 제외한 직전 완료 91일을 사용하고 `d_bar`와 `sigma_d`를 모두 같은 기간에서 계산한다. 무수요 기간은 0으로 채우며 `R`, 리드타임, 안전재고 fence와 PL·USA의 판매 7주 미만 간헐 기준은 변경하지 않는다. RS-019를 대체한다. |
