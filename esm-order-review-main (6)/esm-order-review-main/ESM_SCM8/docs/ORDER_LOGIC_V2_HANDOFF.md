# 신규 발주 로직 V2 인수인계

마지막 갱신: 2026-08-28
구현 버전: `2.1.0-rs.5`
화면 경로: `/order-analysis/new-order-logic`

원화 매출·재고단가·발주금액의 공통 필드 계약과 검산 기준은
[`KRW_CONVERSION_HANDOFF.md`](KRW_CONVERSION_HANDOFF.md)를 따른다.

## 1. 목적과 현재 범위

신규 발주 로직 V2는 최근 완료 주의 수요, 수요 변동성, 리드타임 변동성,
서비스 수준, 현재 재고 위치를 함께 사용해 SKU별 발주 제안량을 계산한다.
기존 발주분석을 대체하지 않는 별도 BETA 탭이다.

현재 CMS API로 실제 계산 가능한 법인은 PL이다. 법인별 화면이 이미 분리되어
있으므로 V2 화면에 `PL 전용` 같은 중복 표시는 넣지 않았다. 다만 코드 구조상
리드타임이 아직 법인별 테이블로 분리된 것은 아니다. 다른 법인을 연결할 때는
반드시 이 제약을 먼저 해결해야 한다.

## 2. 기준 자료와 우선순위

충돌 시 다음 순서로 판단한다. 단, 이 문서에 날짜와 함께 기록된 사용자의
후속 확정 결정은 해당 기술명세 조항을 대체한다.

1. `EU_발주로직_웹개발_기술명세서.html`
2. 사용자가 명시적으로 확정한 후속 결정
3. `EU_발주로직_버전2_확정_로직설명서.html`
4. `ESM_CV발주템플릿_v4.0_리드타임시그마수동입력.xlsx`
5. 목업 이미지

기술명세는 기본 산식과 정책값의 기준이다. 로직설명서는 업무 의도를
보완한다. Excel은 리드타임 시그마 검산 예시 및 사용자에게 보여줄 컬럼명을
참고하는 자료다. 목업은 UI/UX 방향이며, 기술명세와 Excel 표시 컬럼을
수용하기 위해 화면 구성이 달라질 수 있다.

원본 자료는 저장소 밖의 사용자 로컬 파일로 제공되었으므로 이를 자동으로
재배포하거나 저장소에 복사하지 않는다.

## 3. 확정된 업무 결정

- 기본 산식은 기술명세를 그대로 따른다.
- `CASH`와 `SHORTAGE` 두 정책모드를 모두 웹에서 보여준다.
- 두 모드는 동일한 CMS 원천 snapshot과 동일한 SKU 집합으로 계산한다.
- 한 실행에서 공식 적용모드는 하나만 선택한다.
- 사용자 표시 컬럼과 Excel 내보내기 컬럼은 제공된 Excel 템플릿의 용어를
  최대한 따른다.
- 설정은 실행 시뮬레이션에는 적용할 수 있지만 DB 구축 전까지 영속 설정으로
  취급하지 않는다.
- 승인 기능은 현재 범위가 아니다.
- BETA 표시는 로직이 계속 조정될 수 있으므로 유지한다.
- 기존 CMS API와 기존 인증·법인 권한·금액 권한 체계를 사용한다.
- 원천 데이터가 없거나 신선하지 않으면 임의 fixture로 운영 결과를 만들지
  않고 계산을 차단한다.
- 2026-07-28 결정: 회사에 SKU별 MOQ가 확정되어 있지 않으므로 V2에서 MOQ
  입력·표시·배수 검증·누락 경고를 제거한다. 최종 제안수량은 낱개 단위로
  올림한다.
- 2026-07-28 결정: API의 `policy_mode`, `CASH`, `SHORTAGE` 계약은 유지하되
  사용자 화면에서는 `정책모드`라는 표현을 사용하지 않는다. 각각
  `현금흐름 우선 시나리오`, `쇼티지 방어 시나리오`로 표시한다.
- 2026-07-28 UI 결정: 상단 KPI는 `즉시발주 SKU`, `발주필요 SKU`,
  `총 발주필요수량`, `총 발주필요금액`을 사용한다. 계산 방식·정수 올림·단가 보유 건수 같은
  내부 설명은 KPI 카드의 상시 보조문구로 노출하지 않는다.
- 2026-08-24 결정: 발주분석 권한 사용자의 `총 발주필요금액`은 CMS 현지재고 API의
  `unit_cost_krw`와 제안수량을 곱해 원화로 표시한다. 현재 환율 API를 다시 조회하거나
  법인 통화 금액에 재적용하지 않는다. 원화 단가 누락은 별도 상태 메시지로 알린다.
- 상단 안내 영역은 경고가 아니라 `발주 전 참고사항`으로 표시하며, CMS·원천 snapshot 같은
  내부 용어보다 사용자가 발주 전에 확인할 데이터 기준시점·ETA·단가와 계산 한계를 설명한다.
- 2026-07-28 권한 결정: `adminmaster`와 `ia`만 서비스 수준, 재고 기준·추가
  확보량, 운송 리드타임·변동성을 수동 설정할 수 있다. 그 외 일반계정은
  `현금흐름 우선`·`쇼티지 방어` 중 적용 시나리오만 선택하고 기술명세 기본
  산식값을 사용한다. 이 제한은 화면뿐 아니라 `/jobs` API에서도 검증한다.
- 2026-07-29 Excel 결정: `확정수량(담당자 발주)` 컬럼은 Excel 내보내기에서
  제외한다. 화면의 담당자 검토 입력과 API의 확정수량 검증 계약은 유지한다.
- 2026-07-30 결정: `EU_발주템플릿_발주담당자교과서_v2_최종검증판.docx`의
  미입고 불신 상한수량을 V2 엔진·API·화면·Excel에 적용한다. 기존
  `suggested_qty`는 미입고를 인정한 제안수량으로 유지하고,
  `upper_suggested_qty`는 `IP - qty_incoming`을 재고 위치로 사용한다.
  MOQ 제거 결정은 유지하므로 두 수량 모두 낱개 단위로 올림한다.
- 2026-08-04 결정: 발주분석 탭(V1/V2 및 발주 Excel)은 모든 발주분석
  계정에 단가·금액을 표시한다. 일반계정의 금액 제한은 그 밖의 분석 탭에만
  유지한다. 아래의 과거 금액 제한 문구보다 이 결정이 우선한다.
- 2026-08-04 결정: 미주는 `CASH=AIR`, `SHORTAGE=SEA`로 계산한다. 두
  운송수단의 평균 리드타임과 리드타임 표준편차는
  `/api/v1/us/logistics/lead-time`의 최근 6개월 입고 완료 건을 Packing No
  단위로 집계한다.
- 2026-08-06 결정: EU도 `/api/v1/eu/logistics/lead-time`의 실측값을 사용한다.
  `CASH=RAIL`, `SHORTAGE=SEA` 매핑은 그대로 유지하고, RAIL과 SEA의 평균
  리드타임·리드타임 표준편차만 미주와 동일한 Packing No 단위 집계 규칙으로
  대체한다. EU 피드에는 `항공`과 `트럭` 건도 포함되지만 두 수단은 V2 정책
  운송수단이 아니므로 집계 모집단에서 제외한다. AIR은 실측 대상이 아니므로
  기술명세 고정값(16.4일, 0.68주)을 유지한다. RAIL 또는 SEA 유효 표본이 2건
  미만이거나 조회가 실패하면 고정값으로 대체하지 않고 계산을 차단한다.
- 2026-08-05 결정: CMS `stock_ucost`는 법인별 현지통화 단가로 해석한다.
  PL은 EUR, USA는 USD다. 계산 내부 표준 컬럼은 `현지 입고단가`, `현지 입고단가 통화`를
  사용한다. `EU 입고단가`와 `*_EUR` 필드는 과거 V1/V2 결과 및 Excel 소비자
  호환을 위한 별칭일 뿐, USA 계산의 통화 기준으로 사용하지 않는다.
- 2026-08-24 결정: `stock_ucost`의 현지통화 표시는 유지하되 원화 단가·발주금액은
  `unit_cost_krw`를 사용한다. Pareto 매출등급은 판매 API의 `amount_krw_actual`을
  건별 합산한다. 두 값 모두 CMS가 기준일 환율을 반영한 값이므로 현재 환율을 재적용하지 않는다.
- 2026-08-05 결정: 미주 법인의 `데이터 입력`, `발주분석 V1`, `발주분석 V2`
  화면 차단을 해제한다. 발주분석 권한이 있는 계정은 EU와 동일하게 세 화면에
  접근하고 분석을 실행할 수 있다.
- 2026-08-14 결정: 모든 법인(PL·USA)과 본사(HQ)의 V1/V2 발주 수요 표본에서
  CMS 판매행 중 `amount < 0`이면서 `qty > 0`인 행은 확인된 사고처리 조정으로
  간주해 수요수량과 Pareto 등급 매출에서 제외한다. 원본 판매내역과 재무용
  순매출 계산은 보존하고, 제외 건수·수량·금액·Biz Type 분포를 감사정보에 남긴다.
  PL·USA V2의 CASH/SHORTAGE는 같은 정제 snapshot을 사용하며 V1도 동일한
  수요 집계 기준을 사용한다. 이 규칙은 `source_type`을 대체하는 영구 원천식별자가
  아니라 현재 확정된 발주 수요 정책이다.
- 2026-08-15 결정: V2 수요 관측기간을 12주 상당으로 통일한다. PL·USA는
  현재 주를 제외한 직전 12개 완료 주, HQ는 현재일을 제외한 직전 84개
  완료일을 사용하며, `d_bar`와 수요 시그마 `sigma_d`를 모두 같은 기간에서
  계산한다. PL·USA의 `R=4주`, HQ의 `R=28일`, 리드타임과 안전재고 fence는
  변경하지 않는다. PL·USA의 간헐 기준도 판매 7주 미만으로 유지한다(RS-019).
- 2026-08-24 결정: RS-019의 수요 관측기간을 13주 상당으로 다시 변경한다.
  PL·USA는 현재 주를 제외한 직전 13개 완료 주, HQ는 현재일을 제외한 직전
  91개 완료일을 사용하며, `d_bar`와 `sigma_d`를 모두 같은 기간에서 계산한다.
  `R`, 리드타임, 안전재고 fence와 PL·USA의 판매 7주 미만 간헐 기준은
  변경하지 않는다(RS-024).
- 2026-08-28 결정: 웹 발주 로직의 리드타임과 모든 기간 계산은 CMS와 같은
  **Calendar Day(달력일)** 기준으로 한다. 주말·공휴일을 제외하거나 영업일 수로
  보정하지 않는다. PL·USA의 Monday–Sunday 완료 주, HQ의 91일 관측창,
  리드타임 표본의 날짜 차이와 출고일 기반 ETA 추정에도 이 기준을 일관되게 쓴다.
- 2026-08-18 결정: `FREE SAMPLE` 등 무상샘플 거래행은 기존처럼 발주 수요에서
  제외한다. 다만 상품명이나 SKU 속성이 샘플·샤쉐·사쉐라는 이유만으로 상품을
  제외하지 않는다. 법인별 허용 거래유형으로 발생한 정상 출고수량은 다른
  상품과 동일하게 발주 수요에 포함한다(RS-020).
- 2026-08-18 결정: PL·USA `open-po`의 `completed_qty`(④ 입고완료 수량)는
  발주제안 Excel의 원천 확인용 컬럼에 표시한다. 입고완료 수량은 이미 가용재고에
  반영되므로 재고 위치(`IP`)와 제안수량 산식에는 별도로 더하지 않는다.
- 2026-08-18 결정: HQ/OPO 발주제안 Excel의 상태 컬럼은
  `/opo/inbound/confirmed`의 `pnfm_confirmed_qty`(②),
  `inbound_in_progress_qty`(③), `completed_qty`(④)를 각각 표시한다. HQ 재고
  위치는 기존처럼 같은 응답의 `remaining_qty = ②+③`을 한 번만 반영하고
  ④는 표시만 하므로 제안수량 산식은 변경하지 않는다.
- 2026-08-18 결정: HQ/OPO 상품명·브랜드는 전체 COSMETIC 상품마스터
  `/eu/products?eu_sold_only=false`를 최우선 원천으로 사용하고 기존 판매·재고·
  PO·입고 원천은 누락 보충용으로만 사용한다. 상품마스터 단독 SKU는 계산대상에
  추가하지 않으므로 SKU 모집단과 수량 산식은 변경하지 않는다.
- 2026-08-18 확인·반영: EU `open-po` 최신 응답의 `open_qty`(①),
  `pnfm_confirmed_qty`(②), `inbound_in_progress_qty`(③),
  `completed_qty`(④)를 각각 사용한다. EU V2 재고 위치에는 ①+②+③을 반영하고,
  ④는 이미 재고에 반영된 수량이므로 표시만 한다.
- 2026-08-19 후속 확정(RS-022): USA V2의 계산용 입고예정수량은 `open-po`의
  ① 미입고 + ② PNFM확정 + ③ 입고진행중 합계다. 운송중 수량은 기존처럼
  `/us/shipping/containers`의 SKU별 `qty` 합계를 별도로 사용한다. 따라서 USA
  재고 위치는 ①+②+③ + 본사 미주창고 가용재고 + 실제 shipping 운송중 + 미주
  현지가용재고다. ④ 입고완료는 이미 재고에 반영됐으므로 Excel에 원천값만
  표시하고 재고 위치와 제안수량에는 더하지 않는다. 이 결정은 USA ②·③을
  표시 전용으로 두었던 2026-08-18 결정을 대체한다.
- 2026-08-19 최종 확정(RS-023): EU와 USA는 동일하게 계산한다.
  `입고예정 = ① 미입고 + ② PNFM확정 + ③ 입고진행중`이고,
  `IP = 입고예정 + 본사 해당 법인창고 가용 + shipping 운송중 + 현지가용`이다.
  HQ/OPO도 `입고예정 = ①+②+③`을 사용하지만 shipping 운송중은 IP에서
  제외하므로 `IP = 입고예정 + OPO 가용`이다. 전 법인에서 ④ 입고완료는
  표시만 하고 IP에는 더하지 않는다. 이 결정은 EU shipping 제외와 HQ의
  ②+③ 운송중 분류 및 RS-022를 대체한다.
- PL·USA `open-po`는 실행 기준일이 속한 연도의 1월 1일부터 실행 기준일까지
  `date_from`·`date_to`를 명시해 조회한다. 예를 들어 `as_of=2026-08-19`이면
  `date_from=2026-01-01&date_to=2026-08-19`다.

## 4. 기술명세 기준 산식

산식의 단일 구현 지점은 `core/order_logic_v2.py`다. 백엔드 서비스나
프런트엔드에서 이 산식을 복제하지 않는다.

### 4.1 수요 표본

- 기준일이 속한 현재 주는 제외한다.
- 직전 13개 완료 주(Monday–Sunday)를 사용한다.
- `d_bar`: 13주 주간 판매량의 산술평균
- `sigma`: 13주 주간 판매량의 표본표준편차
- 정확히 13주가 아니면 행을 삭제하지 않고 `데이터부족`으로 유지하며 산식
  결과를 비운다.

판매 상태:

- 평균이 0이면 `판매없음`
- 판매가 발생한 주가 7주 미만이면 `⚠확인(간헐)`(13주 전환 후에도 유지)
- 최대 주 판매량이 실제 판매 주 평균(`총판매 ÷ 판매 주수`)의 3배를 초과하면
  `⚠대량포함`. 무판매 주를 포함한 13주 평균과 비교하지 않는다(RS-017, RS-024).
- 그 외는 `정상`

### 4.2 Pareto 등급

SKU를 매출 내림차순, 동일 매출이면 SKU 코드 오름차순으로 정렬한다.
해당 행을 더하기 전 누적 매출 비중이 80% 미만이면 `MAJOR(주력)`, 아니면
`MINOR(일반)`이다. 80%를 넘기는 행 자체는 MAJOR이고 다음 행부터 MINOR다.
전체 매출이 0이면 모두 MINOR다.

### 4.3 기본 정책값

| 항목 | 값 |
| --- | ---: |
| Pareto 기준 | 0.80 |
| 추가 커버 | 2주 |
| 안전재고 하한 | 평균수요 2주 |
| 안전재고 상한 | 평균수요 13주 |
| AIR 리드타임 | 16.4일 |
| RAIL 리드타임 | 36.6일 |
| SEA 리드타임 | 72.9일 |
| AIR 리드타임 시그마 | 0.68주 |
| RAIL 리드타임 시그마 | 1.15주 |
| SEA 리드타임 시그마 | 2.18주 |
| CASH MAJOR Z | 1.28 |
| CASH MINOR Z | 1.08 |
| SHORTAGE MAJOR Z | 1.68 |
| SHORTAGE MINOR Z | 1.28 |

### 4.4 정책모드 매핑

| 정책모드 | 현재 운송수단 | 적용 LT | 적용 LT 시그마 |
| --- | --- | ---: | ---: |
| `CASH` | RAIL | 36.6일 | 1.15주 |
| `SHORTAGE` | SEA | 72.9일 | 2.18주 |

AIR 값은 설정 계약과 향후 확장을 위해 존재하지만 현재 두 정책모드의 공식
계산에는 선택되지 않는다.

위 표의 LT와 시그마는 기술명세 기본값이다. PL과 USA는 실행 시점에 법인별
리드타임 API 실측값이 이 기본값을 덮어쓰며, 실제 적용값은 응답의
`settings`와 `lead_time_audit`에서 확인한다.

2026-08-07 확인: PL과 USA 모두 리드타임 API가 연결되어 두 정책모드가
선택하는 LT와 시그마는 항상 실측 파생값이다. 위 표의 값이 실제로 쓰이는
자리는 실측 대상이 아닌 PL AIR 하나뿐이며, 그것도 어느 정책모드에도
선택되지 않는다. 따라서 화면과 문서에서 정책모드가 적용하는 리드타임을
`기술명세 고정값`으로 설명하면 안 된다. 근거는 `최근 12개월 실측 · 표본 N건`
과 `lead_time_audit`의 입고완료 기간으로 표기한다.

중요: 현재 매핑은 정책모드가 운송수단을 결정하는 전역 구조다. 아직
`entity_code + transport_mode` 키로 리드타임을 조회하지 않는다. 신규 법인을
연결할 때 기존 값을 그대로 공용 적용하면 안 된다.

### 4.5 3개 레이어

정책모드와 등급에 따라 `LT`, `sigma_L`, `Z`를 정한 뒤:

```text
P_weeks = (LT_days + 7) / 7

Layer1 = d_bar × P_weeks

Layer2_SS_raw =
  Z × sqrt(P_weeks × sigma² + d_bar² × sigma_L²)

SS_floor = d_bar × 2
SS_cap   = d_bar × 13
Layer2_SS = clamp(Layer2_SS_raw, SS_floor, SS_cap)

Layer3 = d_bar × 2

reorder_point_s = Layer1 + Layer2_SS
target_stock_S  = reorder_point_s + Layer3
```

`Layer1`은 평균 리드타임 및 검토주기 수요, `Layer2`는 수요·리드타임 변동성을
반영한 안전재고, `Layer3`는 추가 2주 커버다.

### 4.6 재고 위치와 발주량

```text
IP =
  입고예정수량(qty_incoming)
  + EU 가용재고(qty_eu_available)
  + 운송중수량(qty_in_transit)
  + 현지 가용재고(qty_local_available)

if IP < reorder_point_s:
    raw_order_qty = target_stock_S - IP
    suggested_qty = ceil(raw_order_qty)
else:
    raw_order_qty = 0
    suggested_qty = 0

IP_without_incoming = IP - qty_incoming

if IP_without_incoming < reorder_point_s:
    raw_upper_order_qty = target_stock_S - IP_without_incoming
    upper_suggested_qty = ceil(raw_upper_order_qty)
else:
    raw_upper_order_qty = 0
    upper_suggested_qty = 0
```

- 재고 구성값이 `null`이면 `0`을 적용하되 각 필드별 경고를 남긴다.
- 음수 재고와 미승인 음수 판매는 의미를 조용히 바꾸지 않고 계산불가로 처리한다.
  단, `amount < 0 AND qty > 0` 사고처리 행은 공통 정책에 따라 발주 수요와
  Pareto에서 제외하고 감사정보를 남긴다.
- 제안수량과 확정수량은 낱개 단위 정수로 처리한다. 평균·표준편차·레이어와
  원시 발주량은 계산 중 소수 정밀도를 유지한다.
- `확정수량`과 `메모`는 사용자의 검토 결과이며 `suggested_qty`를 덮어쓰는
  산식 입력이 아니다.

## 5. 데이터와 실행 계약

원천 흐름:

```text
CMS API/cache
  -> order_logic_v2_source.py
  -> immutable 13-week-equivalent source snapshot
  -> core/order_logic_v2.py (CASH + SHORTAGE)
  -> service response / latest JSON / Excel export
  -> frontend
```

- 폴란드 현지 날짜 판단은 `Europe/Warsaw` 시간대를 사용한다.
- CMS cache가 24시간을 초과하면 강제 재조회한다.
- 재조회 후에도 24시간을 초과하거나 조회에 실패하면 계산을 차단한다.
- source snapshot에는 SHA-256 식별자를 남긴다.
- 두 정책모드는 같은 snapshot ID를 공유해야 한다.
- 실행 설정은 요청별 immutable snapshot으로 응답과 감사 정보에 남긴다.
- 현재 결과 계약은 `result_schema_version=10`이다. 13주/91일 수요기간 identity,
  상한수량, 운송 건별 ETA 상세, 법인별 운송수단 매핑 또는 리드타임 감사값이
  없는 이전 결과를
  새 Excel 양식으로 내보내면 필수 값이 비게 되므로,
  `/latest`와 Excel 내보내기에서 이전 계약의 저장 결과를 재사용하지 않는다.
  이 경우 사용자가 `분석 실행`으로 새 snapshot을 계산하게 한다.
- `preview=true` 실행은 latest 운영 결과를 갱신하지 않는다.
- DB 구축 전 latest 결과는
  `LATEST_ORDER_LOGIC_V2_DIR` 아래의 파일 저장소를 사용한다.
- 실제 API 비밀값과 CMS 원천 payload를 fixture나 로그에 저장하지 않는다.

### 5.1 전 법인·본사 판매 수요 원천 정제

PL·USA V1/V2와 HQ V2는 기존 거래유형·창고 필터가 허용한 판매행을 수요 표본으로
만들기 전에 아래 공통 규칙을 적용한다.

```text
if amount < 0 and qty > 0:
    발주 수요용 daily/weekly demand와 Pareto 매출에서 제외
else:
    기존 V2 거래유형 규칙에 따라 처리
```

적용 불변조건:

- 제외 행의 `qty`는 V1/V2의 `daily/weekly_sales`, `d_bar`, `sigma`, 판매상태 및
  그 수요값을 사용하는 발주량 계산에 기여하면 안 된다.
- 제외 행의 금액은 Pareto 등급 매출을 낮추지 않아야 한다.
- 정상 양수 `SELF(자사간거래)`는 계속 수요에 포함한다.
- 상품명 또는 SKU 속성이 샘플·샤쉐·사쉐라는 이유만으로 제외하지 않는다.
  법인별 허용 거래유형의 정상 출고수량은 발주 수요에 포함하고, `FREE SAMPLE`
  등 무상샘플 거래행만 기존 거래유형 필터로 제외한다(RS-020).
- 원본 판매내역·재무용 순매출과 공통 `core/sales.py`의 거래유형 계약은 보존한다.
  단, 발주 수요·Pareto 모집단에서는 위 사고처리 행을 제외한다.
- V1에서 판매상세 원천이 있으면 정제된 판매상세 수량을 실제 발주 기준으로
  사용하고, 재고 API의 원래 `PA+CA` 집계값은 차이 검증용으로 보존한다. 판매상세
  원천이 없을 때만 기존 API 집계값으로 fallback한다.
- API가 반환한 사고처리의 T/B 병합, 대표 처리일 선택 또는 날짜 필터를 V2가
  재구현하지 않는다. V2는 실제 응답으로 받은 행에 대해서만 위 규칙을 적용한다.
- CMS API에서 향후 `source_type` 같은 안정적인 원천 구분값을 제공하면 이
  형태 기반 규칙을 재검토한다.

실행 감사정보에는 최소한 제외 행 수, 영향 SKU 수, 제외 수량 합계, 제외 금액
합계와 거래유형별 분포를 남긴다. 직전 실행 대비 제외 규모의 급변도 사용자에게
알려야 하지만, 급변 임계값은 아직 확정되지 않았으므로 임의 수치를 넣지 않는다.

2026-08-13 검증에서 확인된 API 사고처리 날짜 동작은 다음과 같다.

- 확인된 사례에서 T 처리가 있으면 API `ship_dt`는 최초 T 처리일과 일치했다.
- T가 없고 B만 있는 사례에서는 B 처리일과 일치했다.
- T/B 대표 선택 우선순위와 조회 WHERE 날짜 컬럼은 공식 API 명세로 확정되지
  않았다. 따라서 이를 V2 로직이나 감사 문구에서 확정 계약처럼 표현하지 않는다.

현재 구현 상태: 2026-08-14 작업에서 이 절의 규칙이 운영 코드에 반영됐다.
`backend/services/order_logic_v2_source.py`의 `_sales_by_sku`와 HQ source adapter가
모든 적용 법인에서 `amount < 0 AND qty > 0` 행의 수량을 일/주별 수요에서 제외하고,
같은 행의 금액을 Pareto 등급 매출에서도 제외한다. 해당 SKU에는
`NEGATIVE_AMOUNT_POSITIVE_QTY_EXCLUDED` 경고가 붙고, 제외 행 수·SKU 수·수량
합계·금액 합계·거래유형 분포는 source audit에 남는다.

리드타임 집계 계약(PL·USA 공통):

- 기준일에서 12개월 전 같은 날짜부터 기준일까지의 `iw_dt` 완료 건만 쓴다.
  (2026-08-14 결정 `RS-005`로 기존 6개월 관측창을 12개월로 확대했다.)
- API가 `invc_dt` 기준으로 필터하므로 완료기간 시작일보다 180일 앞서 조회한다.
- `include_in_transit=false`를 사용하고, 법인의 정책 운송수단만 집계한다.
  USA는 `AIR/SEA`, PL은 `RAIL/SEA`이며 그 밖의 운송수단 건은 제외한다.
- `ow_to_iw_days`가 1~180일인 정수 건만 사용하고 0일·음수·초과값은 제외한다.
- 상품 라인 중복은 Packing No 단위로 한 건으로 접는다. 같은 Packing No의
  운송수단·출고일·입고일·리드타임이 충돌하면 해당 Packing 전체를 제외한다.
- 평균은 산술평균, `sigma_l_*_weeks`는 `STDEV.S(days) / 7`이다.
- 정책 운송수단 중 하나라도 유효 표본이 2건 미만이면 임의 기본값으로 대체하지
  않고 실행을 차단한다. 원문 식별자는 저장하지 않고 집계 건수와 응답 hash만
  감사값에 남긴다.
- 실측 대상이 아닌 운송수단(PL의 AIR)은 기술명세 고정값을 그대로 유지한다.
- 실제 적용값과 표본 수는 응답의 `settings`와 `lead_time_audit`에 남고,
  `lead_time_audit`은 `calculated_at`을 제외한 뒤 source snapshot ID 계산에
  포함된다.

## 6. API

Base path: `/api/order-logic-v2`

| 메서드 | 경로 | 역할 |
| --- | --- | --- |
| POST | `/jobs` | 비동기 계산 작업 생성 |
| GET | `/jobs/{job_id}` | 소유 클라이언트의 작업 상태/결과 조회 |
| GET | `/latest` | 해당 클라이언트의 최신 공식 결과 조회 |
| POST | `/export` | 선택 행과 확정수량/메모를 Excel로 내보내기 |

요청 정책모드는 `CASH` 또는 `SHORTAGE`만 허용한다. 응답에는 두 시나리오를
모두 포함하지만 `applied_mode`로 공식 모드를 구분한다.

`/export`는 `export_mode`를 필수로 받아 현재 보고 있는 시나리오를 명시한다.
공식 적용모드와 다른 시나리오도 같은 source snapshot에서 계산된 결과인지
검증한 뒤 내보낸다. 수정하지 않은 화면 기본수량은 override로 전송하지 않는다.

발주분석 권한이 있는 인증 사용자는 이 탭과 Excel에서 단가·금액을 볼 수 있다.
그 밖의 분석 탭의 일반계정 금액 제한은 유지한다. API 소유권 검사와 감사
이벤트를 우회하지 않는다.

## 7. 파일 지도

### 계산 및 백엔드

- `core/order_logic_v2.py`: 외부 의존성이 없는 순수 산식
- `backend/services/order_logic_v2_source.py`: CMS DataFrame을 산식 입력으로 매핑
- `backend/services/order_logic_v2_lead_time.py`: 미주 운송모드별 실측 리드타임 집계
- `backend/services/order_logic_v2_service.py`: 실행, 두 모드 비교, 권한, 감사
- `backend/services/order_logic_v2_jobs.py`: 비동기 job 상태
- `backend/services/order_logic_v2_store.py`: DB 이전 latest 파일 저장
- `backend/services/order_logic_v2_excel.py`: 사용자 검토용 Excel
- `backend/schemas_order_logic_v2.py`: 요청 스키마와 기본 설정
- `backend/routers/order_logic_v2.py`: HTTP route

### 프런트엔드

- `frontend/app/order-analysis/new-order-logic/page.tsx`: route entry
- `frontend/components/redesign/screens/order-v2/NewOrderLogicScreenExact.tsx`:
  화면과 반응형 레이아웃
- `frontend/components/redesign/screens/order-v2/useNewOrderLogicScreenModel.tsx`:
  API 상태와 사용자 상호작용
- `frontend/components/redesign/screens/order-v2/types.ts`: 화면 타입
- `frontend/components/redesign/screens/order-v2/fixtures.ts`: 화면 개발용 예시
- `frontend/lib/api/order-logic-v2.ts`: API client

운영 계산 성공 결과를 프런트 fixture로 대체하지 않는다. fixture는 API가
없는 상태의 디자인 개발에만 사용하며 운영 데이터처럼 표시하면 안 된다.

## 8. UI 및 Excel 불변 규칙

- 메뉴와 화면의 `BETA` 표시를 유지한다.
- 발주 제안, 시나리오 비교, 산식 기준 설정의 세 탭을 유지한다.
- 시나리오 선택 화면에는 각 선택의 목적, 운송수단, 재고 방향과 커버 주수를
  먼저 보여준다.
- Z값, 리드타임 통계, 안전재고 범위 등 전문 변수는 `고급 산식 설정` 안에서
  제공한다.
- 발주 산식 안내의 `기준 적용값`은 리드타임 근거를 함께 밝힌다. 실측이면
  `최근 12개월 실측 · 표본 N건 · 입고완료 기간`을, 실측 대상이 아니면 명세
  고정값임을 표기한다. 리드타임은 소수 2자리로 표시해 실측 72.79일이 명세
  72.9일과 같아 보이지 않게 한다.
- 응답에 리드타임 값이 없으면 화면 기본값으로 메우지 않고 `확인 필요`로
  표시한다. 화면 기본값으로 떨어지면 실측 연결 실패가 정상 표시와 구분되지
  않는다.
- 리드타임과 정책 운송수단은 화면에서 실행 요청으로 되돌려 보내지 않는다.
  서버가 매 실행마다 실측으로 결정하므로 요청에 실어 보내면 실측 이전 값이
  섞인다.
- 두 정책 결과가 같은 snapshot에서 계산되었다는 사실을 확인 가능하게 한다.
- 공식 적용모드와 참고 비교모드를 시각적으로 구분한다.
- 화면에서는 제안수량과 확정수량을 별도 값으로 유지하되, Excel에는
  `확정수량(담당자 발주)` 컬럼을 표시하지 않는다.
- 다음 ETA와 고갈주수는 공식 발주 산식이 아닌 참고값임을 표시한다.
- 운송중 ETA는 원천 ETA를 우선 사용하고, 원천 ETA가 없으면 `출고일 + remark에서
  판별한 실제 운송수단의 V2 평균 리드타임`으로 추정한다. AIR 16.4일, RAIL 36.6일,
  SEA 72.9일을 실행 설정에서 가져오며 선택한 시나리오의 기본 운송수단으로 기존
  운송 건을 덮어쓰지 않는다. 운송수단 또는 출고일을 확인할 수 없는 물량만
  `ETA 미확인`으로 남긴다. 리드타임 표준편차(σL)는 ETA 날짜에 더하지 않는다.
- ETA 신뢰도 구분은 근거 기준으로 표기한다. 원천 ETA가 있으면 `원천 ETA`,
  출고일과 운송수단으로 추정했으면 `출고일 추정 ETA`, 둘 다 없으면
  `ETA 미확인`이다. `원천 ETA`는 CMS에 입력된 예정일이라는 뜻이며 도착
  확정을 의미하지 않는다.
- 물류전망 Excel의 `ETA 미확인 물량` 컬럼은 해당 물량이 1개 이상일 때만
  표시한다. 0이면 컬럼을 감추고 상단 안내행의 집계 수치로만 남긴다.
- 데이터부족 행을 숨기지 않고 확인 필요 상태로 보여준다.
- 데스크톱은 상세 표, 모바일은 SKU 카드로 제공한다.
- Excel 표시 컬럼의 업무 용어를 존중하되 중간 산식값과 snapshot 메타데이터를
  잃지 않는다.
- 발주분석 권한이 있는 사용자는 계정의 일반 분석 금액 권한과 관계없이 V2
  화면·API·Excel에서 단가와 금액을 볼 수 있다.

## 9. 알려진 제약과 후속 과제

### 현재 제약

- CMS API가 연결된 법인은 PL과 USA뿐이다.
- 리드타임은 PL·USA만 법인별 리드타임 API 실측값을 사용하고, 아직
  법인별·운송수단별 master 조회 구조는 아니다. 실측 대상이 아닌 운송수단은
  기술명세 고정값을 유지한다.
- DB가 없어 정책 설정 이력, 실행 이력, 승인 이력을 영속 관리하지 않는다.
- 승인 워크플로는 구현하지 않았다.
- BETA 기본값은 변경될 수 있지만 변경 시 기술명세 개정과 회귀 테스트가
  함께 필요하다.
- CMS 판매 API에는 사고처리 원천을 직접 구분할 `source_type`, `trbl_no`,
  `thdl_gbn`이 없다. 전 법인·본사에 적용한 `amount < 0 AND qty > 0` 제외는
  검증된 형태 기반 규칙이며, 향후 정상 음수 인보이스나 새로운 사고처리 유형이
  생기면 재검증이 필요하다.
- 사고처리 API의 T/B 대표 선택 및 조회 날짜 기준은 공식 명세가 없다. 확인된
  표본의 동작을 전체 계약으로 확대해 추정하지 않는다.

### 다른 법인을 추가할 때

다음 구조를 먼저 설계한다.

```text
(entity_code, transport_mode, effective_from)
  -> lt_days
  -> sigma_l_weeks
  -> provenance/source
```

필수 고려사항:

- 법인별 운송수단 지원 범위
- 기준일에 따른 유효기간
- 값 누락 시 차단할지 명시적 fallback을 쓸지
- 수동 입력값의 작성자·변경시각·근거
- 실행 snapshot에 실제 적용값과 출처 보존
- 과거 실행 재현성

법인 정보가 없을 때 PL 값으로 조용히 fallback하지 않는다.

### DB를 추가할 때

- policy configuration version
- calculation run
- immutable source snapshot reference
- per-SKU result
- reviewer override
- audit event

위 개념을 분리한다. 설정 변경이 과거 실행 결과를 바꾸지 않도록 실행 시
적용된 설정 snapshot을 별도로 보존한다.

## 10. 변경 체크리스트

산식 또는 정책을 변경하기 전:

1. 기술명세 변경 근거가 있는지 확인한다.
2. 변경이 순수 산식, 소스 매핑, 표시 변경 중 어디에 해당하는지 구분한다.
3. 기존 발주분석에 영향이 없는지 확인한다.
4. 두 정책모드가 같은 snapshot을 쓰는지 확인한다.
5. 금액 권한과 클라이언트 소유권이 유지되는지 확인한다.
6. 데이터부족/판매없음/간헐/대량포함/정수 올림/음수 입력을 검증한다.
7. API, 화면, Excel의 필드 의미가 일치하는지 확인한다.
8. 전 법인·본사 판매 원천 정제를 변경할 때는 고정 합성 fixture로 다음을 검증한다.
   - 정상 양수 `SALE`은 포함
   - 정상 양수 `SELF`는 포함
   - `amount < 0 AND qty > 0`인 T형 사고처리 표본은 수요에서 제외
   - `amount < 0 AND qty > 0`인 B형 사고처리 표본은 수요에서 제외
   - 제외 전후 CASH/SHORTAGE의 일/주 수요, `d_bar`, `sigma`, 등급이 같은
     정제 snapshot을 기준으로 계산됨
   - 제외 행 수·SKU 수·수량·금액 감사값이 입력과 일치
9. 실제 CMS 원문이나 운영 SKU 수치를 fixture에 저장하지 않는다. 운영
   통합검증은 동일 snapshot의 외부 대사표로 수행하고, 영향 SKU 전체를 배포 전
   다시 확인한다.
10. 아래 테스트를 실행한다.

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

현재 구현 기준 V2 백엔드 회귀 테스트는 46건이다. 테스트 수 자체보다 위의
업무 불변조건이 계속 검증되는지가 중요하다.
