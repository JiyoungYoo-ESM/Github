# 발주분석 V2 산식 및 현재 설정값 — 법인별

작성 기준일: 2026-08-24
기준: 현재 저장소 코드와 V2 인수인계 문서  
현재 코드 버전: `2.1.0-rs.5`
결과 스키마: `result_schema_version=10`

2026-08-24 사용자 결정(RS-024)에 따라 수요 관측기간은 PL·USA 13개 완료 주,
HQ 91개 완료일이다. 평균수요와 수요 표준편차는 법인별 같은 관측기간에서
계산하며 `R`, 리드타임과 안전재고 fence는 변경하지 않았다.

이 문서는 발주분석 V2의 공식 수량 산식, 입력 매핑, 법인별 설정값, 금액·ETA·Excel 참고 산식을 한 곳에 정리한 문서다. 실제 설정은 DB에 영속 저장되지 않으며, 매 실행의 요청값과 서버가 계산한 법인별 리드타임 실측값이 해당 실행의 immutable snapshot으로 남는다.

## 1. 법인별 현재 적용 현황

| 법인 | V2 현재 상태 | 원천 | 통화 | 공식 정책 운송수단 | 현재 설정의 성격 |
| --- | --- | --- | --- | --- | --- |
| `PL` | 사용 가능 | `/eu/...` CMS API 6개 + `/eu/logistics/lead-time` | EUR | `CASH=RAIL`, `SHORTAGE=SEA` | 고정 정책값 + RAIL/SEA 실행 시점 실측 |
| `USA` | 사용 가능 | `/us/...` CMS API 6개 + `/us/logistics/lead-time` | USD | `CASH=AIR`, `SHORTAGE=SEA` | 고정 정책값 + AIR/SEA 실행 시점 실측 |
| `HQ` | 사용 가능 | `/opo/...` 4개 + `/us/sales/history`(OPO 창고 필터) | KRW | 국내조달 단일 LT(시나리오별 Z만 상이) | 승인 정책 고정값 + 최근 12개월 실측 LT |
| `UK`, `ME`, `MX`, `MY`, `VN` | 차단 | V2 CMS 발주 연동 없음 | V2 미설정 | 없음 | PL/USA 값 fallback 없음 |

> **2026-08-14 갱신**: V2 API 라우터는 이제 `HQ`, `PL`, `USA`를 허용한다. `HQ`는 일 단위 `(R,S)` 전용 경로(`core/order_logic_v2.py::calculate_hq_sku_order`)와 전용 source adapter(`backend/services/order_logic_v2_hq_source.py`)를 사용하며, PL/USA의 주 단위 경로·통화·리드타임을 공유하지 않는다. 아래 3~9절의 주 단위 서술은 `PL`·`USA` 기준이고 HQ는 1.1절과 `ORDER_LOGIC_V2_R_S_SPEC.md`를 따른다.

### 1.1 법인별 상세

#### PL — 폴란드/EU

- CMS 법인 코드는 `PL`, 외부 API 코드는 `EU`다.
- 통화는 현지 입고단가 `EUR`, 결과의 `currency_code`는 `EUR`다.
- 정책 매핑은 `CASH=RAIL`, `SHORTAGE=SEA`다.
- `RAIL`과 `SEA`의 평균 리드타임 및 리드타임 표준편차는 매 실행마다 최근 6개월 입고 완료 건으로 다시 계산한다.
- `AIR`은 PL의 공식 정책 운송수단이 아니므로 기술명세 고정값 `16.4일`, `0.68주`를 유지한다.
- 기준일 생성과 최근 완료 주 계산은 현재 공통 `Europe/Warsaw` 기준을 사용한다.

#### USA — 미국/미주

- CMS 법인 코드는 `USA`, 외부 API 코드는 `US`다.
- 통화는 현지 입고단가 `USD`, 결과의 `currency_code`는 `USD`다.
- 정책 매핑은 `CASH=AIR`, `SHORTAGE=SEA`다.
- `AIR`과 `SEA`의 평균 리드타임 및 리드타임 표준편차는 매 실행마다 최근 6개월 입고 완료 건으로 다시 계산한다.
- `RAIL`은 미주 정책 운송수단이 아니며, 실행 시점에 별도 입력값이 없으면 기술명세 고정값 `36.6일`, `1.15주`가 설정 객체에 남는다. 공식 두 시나리오에는 선택되지 않는다.
- 현재 화면과 백엔드의 기준일 helper는 법인별 시간대가 아니라 공통 `Europe/Warsaw`를 사용한다. 미국 현지 시간대라고 해석하면 안 된다.

#### HQ — 본사/OPO

- 창고는 CMS 코드 `OPO`, 통화는 `KRW`, 시간대는 `Asia/Seoul`이다.
- 모든 기간값은 **일** 단위다. 수요는 직전 완료 91일, `R`은 28일, 안전재고 fence는 14~35일분이다.
- 수요 원천은 `/us/sales/history`(본사 CO000001 전 창고)에서 `whouse_nm=OPO` 행만 사용하고, 허용 거래유형은 `KR-OVERSEAS`, `KR-DOMESTIC`, `KR-DOMESTIC 0%`다. 임직원판매·무상샘플·반품·상계·회계조정(커미션·기타제조사)은 제외한다.
- `입고예정 = ① po/open 미입고 + ② PNFM확정 + ③ 입고진행중`이며,
  `IP = 입고예정 + inventory 가용`이다. shipping 운송중과 ④ 입고완료는 IP에서
  제외한다. 불량재고(`stock_status=trouble`)는 가용재고에서 제외한다.
- 리드타임은 `/opo/leadtime/stats?months=12`의 `avg_days`·`stddev_days`를 그대로 쓴다. PO 생성일에서 실입고일까지의 달력일이고 실입고 이벤트 단위 동일가중이며, SKU·브랜드별로 나누지 않는다. 유효 표본이 2건 미만이면 계산을 차단한다.
- `CASH`와 `SHORTAGE`는 같은 LT와 `sigma_L`을 쓰고 `Z`만 다르다. 운송수단 개념이 없어 결과의 `transport_mode`는 `HQ_DOMESTIC`이다.
- 단가는 `inventory.avg_unit_cost`(KRW 수량가중평균)이며 환율을 적용하지 않는다.
- PL의 EU 재고, EUR 단가, RAIL/SEA 정책 또는 PL 리드타임을 HQ에 적용하지 않는다.

#### 기타 미연동 법인 — UK, ME, MX, MY, VN

- 법인 선택 자체와 별개로 V2 발주 계산 법인으로 등록되어 있지 않다.
- 법인별 산식·리드타임·통화·원천 매핑이 없으므로 계산을 제공하지 않는다.

## 2. 코드상 기준점과 실행 흐름

공식 수량 산식의 단일 구현 지점은 [`core/order_logic_v2.py`](../core/order_logic_v2.py)다.

```text
법인 권한 확인
  -> 법인별 CMS/cache 원천 조회
  -> PL·USA 최근 13개 완료 주 / HQ 최근 91개 완료일 판매 표본과 재고 원천 매핑
  -> 법인별 리드타임 실측값 계산 및 실행 설정 snapshot 생성
  -> 같은 원천 snapshot으로 CASH + SHORTAGE 각각 계산
  -> 공식 적용모드 1개와 비교 시나리오 1개 응답
  -> 화면 / latest JSON / Excel
```

관련 코드:

- 순수 산식: `core/order_logic_v2.py`
- 원천 매핑: `backend/services/order_logic_v2_source.py`, `backend/cms_mapping.py`
- 법인별 리드타임: `backend/services/order_logic_v2_lead_time.py`, `backend/services/order_logic_v2_service.py`
- 실행·권한·결과·금액: `backend/services/order_logic_v2_service.py`, `backend/routers/order_logic_v2.py`
- Excel: `backend/services/order_logic_v2_excel.py`
- 요청 기본값: `backend/schemas_order_logic_v2.py`

## 3. 공통 입력 산식

### 3.1 수요 표본

기준일 `as_of`가 속한 현재 주는 제외하고, 직전 13개 월요일–일요일 완료 주를 사용한다.

```text
weekly_sales = [w1, w2, ..., w13]

d_bar = Σ(weekly_sales[i]) / 13

sigma = STDEV.S(weekly_sales)
       = sqrt(Σ(weekly_sales[i] - d_bar)^2 / (13 - 1))
```

- 주별 판매량이 없는 SKU의 해당 주 수량은 0으로 채운다.
- 원천 판매 데이터가 13개 주 전체를 덮지 못하면 실행 자체를 차단한다.
- 순수 코어 함수에 13개가 아닌 표본이 직접 들어오면 해당 SKU를 `데이터부족`으로 유지하고 산식 결과를 비운다.
- `d_bar`는 주평균 판매량, `sigma`는 주간 판매량의 표본표준편차다.
- 음수 재고·음수 수량과 미승인 음수 판매량은 0으로 바꾸지 않고 해당 SKU 계산을
  차단한다. 단, `amount < 0 AND qty > 0` 사고처리 행은 발주 수요·Pareto에서
  제외하고 감사정보에 남긴다.

### 3.2 판매 상태

| 조건 | 상태 |
| --- | --- |
| `d_bar = 0` | `판매없음` |
| 판매가 발생한 주 수 `< 7` | `⚠확인(간헐)` |
| `max(weekly_sales) > 3 × (총판매 ÷ 판매 주수)` | `⚠대량포함` |
| 그 외 | `정상` |
| 표본 주 수가 정확히 13개가 아님 | `데이터부족` |

`minWeeksWithSales=7`, `bulkSalesMultiple=3`은 현재 코어/UI에 고정된 기준이며, 일반 실행 설정 API 필드는 아니다.

대량포함 비교 대상은 무판매 주를 제외한 실제 판매 주 평균이다(RS-017). 13주
평균과 비교하면 판매 주가 5주 미만인 SKU가 수치와 무관하게 항상 위반이 된다.
발주량 산식의 `d_bar`는 13주 평균이며 이 판정은 `S`·`Q`를 바꾸지 않는다.

### 3.3 Pareto 등급

SKU를 매출 내림차순, 매출이 같으면 SKU 코드 오름차순으로 정렬한다.

```text
누적매출비중_before = 현재 행을 더하기 전 누적매출 / 전체매출

누적매출비중_before < 0.80  -> MAJOR(주력)
그 외                    -> MINOR(일반)
```

- 80%를 넘기는 행 자체는 `MAJOR`, 그 다음 행부터 `MINOR`다.
- 전체 매출이 0이면 모든 SKU를 `MINOR`로 처리한다.
- Pareto 등급은 법인별·운송수단별로 따로 재계산하지 않고, 해당 실행의 전체 SKU 모집단에서 한 번 계산한다.

## 4. 공식 발주 산식

### 4.1 정책값 선택

각 SKU에 대해 법인·시나리오·Pareto 등급으로 `LT`, `sigma_L`, `Z`를 선택한다.

| 시나리오 | 등급 | 적용 Z |
| --- | --- | ---: |
| `CASH` / 현금흐름 우선 | `MAJOR` | 1.28 |
| `CASH` / 현금흐름 우선 | `MINOR` | 1.08 |
| `SHORTAGE` / 쇼티지 방어 | `MAJOR` | 1.68 |
| `SHORTAGE` / 쇼티지 방어 | `MINOR` | 1.28 |

법인별 공식 운송수단은 다음과 같다.

| 법인 | `CASH` | `SHORTAGE` |
| --- | --- | --- |
| `PL` | `RAIL` | `SEA` |
| `USA` | `AIR` | `SEA` |

### 4.2 보호기간과 3개 레이어

```text
P_weeks = (LT_days + 7) / 7

Layer1 = d_bar × P_weeks

Layer2_SS_raw = Z × sqrt(P_weeks × sigma² + d_bar² × sigma_L²)

SS_floor = d_bar × ss_floor_weeks
SS_cap   = d_bar × ss_cap_weeks
Layer2_SS = clamp(Layer2_SS_raw, SS_floor, SS_cap)

Layer3 = d_bar × cover_weeks

reorder_point_s = Layer1 + Layer2_SS
target_stock_S  = reorder_point_s + Layer3
```

현재 기본값은 `ss_floor_weeks=2`, `ss_cap_weeks=13`, `cover_weeks=2`다. `P_weeks`에는 검토주기 1주가 포함되어 있으므로, 단순히 커버버퍼를 바꾸는 것과 발주 검토주기를 바꾸는 것은 같은 변경이 아니다.

API의 `applied_mode`는 필수 입력이며 서버 기본값은 없다. 현재 화면 초기 선택값은 fixture 기준 `SHORTAGE`지만, 한 실행에서는 사용자가 선택한 한 모드가 공식 적용모드가 된다. 두 모드의 결과는 같은 원천 snapshot으로 모두 계산된다.

### 4.3 재고 위치와 제안수량

```text
IP = qty_incoming
   + qty_eu_available
   + qty_in_transit
   + qty_local_available

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

- `suggested_qty`: 미입고 수량을 인정한 기본 제안수량
- `upper_suggested_qty`: 미입고 수량을 제외한 불신 상한수량
- MOQ는 V2에서 제거되었다. 두 제안수량 모두 낱개 단위로 올림한다.
- 평균·표준편차·레이어·원시 발주량은 계산 중 소수 정밀도를 유지한다.
- 재고 원천값이 `null`이면 해당 필드만 0으로 대체하고 경고를 남긴다.
- `확정수량`은 담당자의 검토 결과이며 코어 산식의 입력이 아니다. 제안수량을 변경해 Excel로 내보내려면 낱개 정수와 변경 메모가 필요하다.

### 4.4 화면·결과에 같이 제공되는 참고값

공식 발주량과 별개로 다음 값을 결과에 제공한다.

```text
CV = sigma / d_bar                         (d_bar > 0일 때)
depletion_weeks = (qty_local_available + qty_in_transit) / d_bar
```

`depletion_weeks`는 현지 가용재고와 운송중 수량만 사용하며, 본사 가용재고와 미입고를 포함하지 않는다. 이는 고갈 참고값이지 공식 `IP`, 발주점, 목표재고 산식을 대체하지 않는다.

## 5. 현재 공통 기본 설정값

아래는 `OrderLogicConfig`와 `OrderLogicV2Settings`에 정의된 기술명세 기본값이다. `PL`·`USA`는 실행 시 법인별 리드타임 실측값이 일부 항목을 덮어쓴다.

| 설정 필드 | 기본값 | 단위 | 적용 범위 |
| --- | ---: | --- | --- |
| `grade_cutoff` | `0.80` | 비율 | Pareto 등급 |
| `cover_weeks` | `2.0` | 주 | Layer3 추가 커버 |
| `ss_floor_weeks` | `2.0` | 주 | 안전재고 하한 |
| `ss_cap_weeks` | `13.0` | 주 | 안전재고 상한 |
| `lt_air_days` | `16.4` | 일 | AIR 보호기간 |
| `lt_rail_days` | `36.6` | 일 | RAIL 보호기간 |
| `lt_sea_days` | `72.9` | 일 | SEA 보호기간 |
| `sigma_l_air_weeks` | `0.68` | 주 | AIR 리드타임 표준편차 |
| `sigma_l_rail_weeks` | `1.15` | 주 | RAIL 리드타임 표준편차 |
| `sigma_l_sea_weeks` | `2.18` | 주 | SEA 리드타임 표준편차 |
| `cash_transport_mode` | `RAIL` | 코드 | 코어 기본값; PL/USA 서버가 법인별로 덮어씀 |
| `shortage_transport_mode` | `SEA` | 코드 | 코어 기본값; PL/USA 서버가 법인별로 덮어씀 |
| `z_cash_major` | `1.28` | Z | CASH·MAJOR |
| `z_cash_minor` | `1.08` | Z | CASH·MINOR |
| `z_shortage_major` | `1.68` | Z | SHORTAGE·MAJOR |
| `z_shortage_minor` | `1.28` | Z | SHORTAGE·MINOR |

설정값 검증 범위는 `grade_cutoff`가 0~1, 커버·안전재고 주수가 0 이상, 안전재고 상한이 하한 이상, 리드타임 일수가 0 초과, 리드타임 시그마가 0 이상, Z값이 0 초과다. NaN·무한대는 허용하지 않는다. 요청 스키마에는 정책 운송수단 필드가 없으며, `cash_transport_mode`와 `shortage_transport_mode`는 서버가 법인별로 결정해 결과 `settings`에 기록한다.

보호기간은 각 운송수단별로 다음처럼 계산한다.

| 운송수단 | 기본 보호기간 |
| --- | ---: |
| AIR | `(16.4 + 7) / 7 = 3.3429주` |
| RAIL | `(36.6 + 7) / 7 = 6.2286주` |
| SEA | `(72.9 + 7) / 7 = 11.4143주` |

화면에만 존재하는 표시 기준은 `demandWeeks=13`, `minWeeksWithSales=7`, `bulkSalesMultiple=3`, `reviewBufferDays=7`이다. 13주 전환 후에도 간헐 기준 7주는 유지한다. 이 중 수요 주 수·간헐 기준·대량 기준·검토 buffer 7일은 코어 산식/상태 판정과 연결되지만, `reviewBufferDays`라는 이름의 별도 API 설정 필드는 없다.

## 6. 법인별 실행 설정값과 리드타임 실측

### 6.1 PL 설정 snapshot

| 항목 | 현재 적용값 |
| --- | --- |
| `cash_transport_mode` | `RAIL` |
| `shortage_transport_mode` | `SEA` |
| `lt_rail_days` | 최근 6개월 유효 `RAIL` Packing No들의 산술평균 |
| `sigma_l_rail_weeks` | `STDEV.S(RAIL 입고완료 소요일) / 7` |
| `lt_sea_days` | 최근 6개월 유효 `SEA` Packing No들의 산술평균 |
| `sigma_l_sea_weeks` | `STDEV.S(SEA 입고완료 소요일) / 7` |
| `lt_air_days` | `16.4`일 고정값 |
| `sigma_l_air_weeks` | `0.68`주 고정값 |
| Z·Pareto·안전재고·추가 커버 | 공통 기본값 또는 실행 요청값 |

### 6.2 USA 설정 snapshot

| 항목 | 현재 적용값 |
| --- | --- |
| `cash_transport_mode` | `AIR` |
| `shortage_transport_mode` | `SEA` |
| `lt_air_days` | 최근 6개월 유효 `AIR` Packing No들의 산술평균 |
| `sigma_l_air_weeks` | `STDEV.S(AIR 입고완료 소요일) / 7` |
| `lt_sea_days` | 최근 6개월 유효 `SEA` Packing No들의 산술평균 |
| `sigma_l_sea_weeks` | `STDEV.S(SEA 입고완료 소요일) / 7` |
| `lt_rail_days` | `36.6`일 기본값이 남지만 공식 시나리오에는 사용하지 않음 |
| `sigma_l_rail_weeks` | `1.15`주 기본값이 남지만 공식 시나리오에는 사용하지 않음 |
| Z·Pareto·안전재고·추가 커버 | 공통 기본값 또는 실행 요청값 |

### 6.3 실측 리드타임 집계 규칙 — PL·USA 공통

```text
완료기간 = [as_of에서 6개월을 뺀 날짜, as_of]
API 조회 시작일 = 완료기간 시작일 - 180일
유효 리드타임 = ow_to_iw_days가 1~180일 범위의 정수인 건
```

- `iw_dt`가 완료기간 안에 있는 건만 사용한다.
- API에는 `include_in_transit=false`를 전달한다.
- 법인별 정책 모집단만 사용한다: PL은 `RAIL`, `SEA`; USA는 `AIR`, `SEA`.
- 같은 `Packing No`의 상품 라인 중복은 Packing No 단위로 한 건으로 접는다.
- 같은 Packing No에서 운송수단·출고일·입고일·소요일이 충돌하면 해당 Packing 전체를 제외한다.
- 운송수단별 유효 표본이 2건 미만이면 고정값 fallback 없이 실행을 차단한다.
- 실행 응답의 `settings`에 적용값을, `lead_time_audit`에 표본 수·기간·제외 건수·응답 hash를 남긴다.
- `calculated_at`은 감사 표시용이며 source snapshot ID 계산에서는 제외한다.

따라서 소스 코드와 테스트 fixture에 보이는 `36.6`, `72.9`, `6`, `22`, `40`, `72` 등의 숫자를 모두 현재 운영 리드타임으로 해석하면 안 된다. 실제 PL·USA 공식 적용값은 실행 시점 응답의 `settings`와 `lead_time_audit`를 확인해야 한다. 테스트에 사용된 숫자는 검산용 fixture다.

## 7. 법인별 원천 매핑

### 7.1 내부 계산 필드

| 내부 필드 | PL/USA 원천 매핑 | 산식에서의 역할 |
| --- | --- | --- |
| `weekly_sales` | `sales_local`의 `상품코드`, `수량`, `출고일`을 13개 주로 집계 | `d_bar`, `sigma` |
| `revenue` | `sales_local`의 `환산금액` 우선, 없으면 `금액`; SKU별 합계 | Pareto 등급 |
| `qty_incoming` | PL/USA: `open_po`의 ① 미입고+② PNFM확정+③ 입고진행중 | `IP`, 상한수량 |
| `qty_eu_available` | `stock_hq`의 `본사 EU창고 가용수량` SKU별 합계 | `IP` |
| `qty_in_transit` | PL/USA: 법인별 `shipping`의 `수량` SKU별 합계 | `IP`, 고갈주수; shipping은 ETA 원천 |
| `qty_local_available` | `stock_local`의 `EU 현지 가용수량` SKU별 합계 | `IP`, 고갈주수 |
| `unit_price_local` | `stock_local`의 `현지 입고단가`; 없으면 `EU 입고단가` | 발주금액 |

필드명에 `EU`가 남아 있는 `qty_eu_available`, `EU 현지 가용수량`, `EU 입고단가`는 과거 PL/V1 소비자 호환을 위한 명칭이다. USA 계산에서는 실제 법인 원천과 `USD` 통화를 사용하며, EUR로 환산하지 않는다.

PL/EU와 USA IP는 `open_po` ①+②+③, 본사 해당 법인창고 가용, 법인별
shipping 운송중, 현지가용을 모두 합한다(RS-023). `completed_qty`(④)는 발주제안
Excel에 원천값을 표시하지만 이미 재고에 반영된 값이므로 IP에는 더하지 않는다.
Excel의 ① 열은 계산용 `qty_incoming` 합계가 아니라 원천 `open_qty`를 표시한다.

HQ/OPO는 동일하게 ①+②+③을 `qty_incoming`으로 묶지만 shipping 운송중을
사용하지 않는다. 따라서 `IP = qty_incoming + OPO 가용`이며 공유 결과의
`qty_in_transit`은 0이다.

### 7.2 판매 필터

| 법인 | 기본 포함 | 기본 제외 | 음수 금액 |
| --- | --- | --- | --- |
| `PL` | `EU-OVERSEAS`, `EU-PL`, `KR-OVERSEAS`, `자사간거래` | `EU-STAFFSALES`, `STAFFSALES`, staff/free-sample 거래행, 반품, 추후상계, TP 조정, `기타제조사` 등 | `amount < 0 AND qty > 0`은 발주 수요·Pareto에서 제외; 원본·재무 순매출은 보존 |
| `USA` | `US-DOMESTIC`, `US-OVERSEAS`, `KR-OVERSEAS`, `자사간거래` | staff/free-sample 거래행, 반품, 추후상계, TP 조정, `기타제조사` 등 | `amount < 0 AND qty > 0`은 발주 수요·Pareto에서 제외; 원본·재무 순매출은 보존 |
| `HQ` | `KR-OVERSEAS`, `KR-DOMESTIC`, `KR-DOMESTIC 0%` 및 `OPO` | 반품·취소·무상샘플 거래행·유효하지 않은 창고 등 | `amount < 0 AND qty > 0`은 발주 수요에서 제외; 원본·재무 순매출은 보존 |

V2는 판매 필터에서 `PL`의 `EU-PL`을 기본 포함하고 `ETC`는 포함하지 않는다. 이는 V2 source adapter가 현재 `entity_code`만으로 기존 판매 필터를 호출하기 때문이다. 모든 법인·본사의 V1/V2 발주 수요와 Pareto 산정에서는 `amount < 0 AND qty > 0` 행을 동일하게 제외하며, 제외 건수·수량·금액·Biz Type 분포를 감사정보로 남긴다.

상품명 또는 SKU 속성이 샘플·샤쉐·사쉐라는 이유만으로는 제외하지 않는다.
법인별 허용 거래유형의 정상 출고수량은 발주 수요에 포함하며, `FREE SAMPLE`
등 무상샘플 거래행만 위 거래유형 필터로 제외한다(RS-020).

V1은 판매상세 원천이 있는 실행에서 사고처리 행을 제거한 판매상세 수량을 실제
발주 기준으로 사용한다. 재고 API의 원래 `PA+CA` 집계값은 `PA_CA_3M_판매수량`으로
보존해 차이 검증에 사용하고, 판매상세 원천이 없을 때만 기존 집계값으로 fallback한다.

### 7.3 단가·통화

| 법인 | CMS `stock_ucost` 해석 | 결과 단가 통화 | 원화 금액 환산 |
| --- | --- | --- | --- |
| `PL` | 현지 입고단가 + `unit_cost_krw` | EUR / KRW | CMS 조회 기준일 원화 단가 사용 |
| `USA` | 현지 입고단가 + `unit_cost_krw` | USD / KRW | CMS 조회 기준일 원화 단가 사용 |
| `HQ` | OPO 원화 평균단가 | KRW | 환산하지 않음 |

공식 금액 산식은 다음과 같다.

```text
suggested_amount_local = suggested_qty × unit_price_local
confirmed_amount_local = confirmed_qty × unit_price_local

suggested_amount_krw = suggested_qty × unit_price_krw
confirmed_amount_krw = confirmed_qty × unit_price_krw
```

`suggested_amount_eur`, `confirmed_amount_eur`, `suggested_amount_eur_total`이라는 결과 필드명은 기존 Excel/API 소비자 호환 별칭이다. `PL`에서는 EUR, `USA`에서는 USD라는 결과의 `currency_code`를 따라야 한다.

V2 발주분석 화면과 Excel은 발주분석 권한 계정에 단가·금액을 표시한다. CMS 원화 단가가 없으면 해당 SKU 금액을 정상 숫자로 꾸미지 않고 별도 확인 상태로 남긴다. 화면과 Excel은 현재 환율 API를 다시 조회해 재환산하지 않는다.

## 8. 운송중 ETA 참고 산식

ETA는 공식 발주량 산식이 아니라 물류전망 참고값이다.

```text
원천 ETA가 있으면       -> 원천 ETA 사용
원천 ETA가 없고
출고일 + 실제 운송수단이 있으면 -> 출고일 + 해당 운송수단의 평균 LT
둘 다 없으면            -> ETA 미확인
```

- 원천 ETA가 최우선이다.
- 출고일 추정 ETA에는 `sigma_L`을 더하지 않는다.
- 선택한 정책 시나리오의 운송수단으로 기존 운송 건을 덮어쓰지 않는다. 실제 운송수단은 리드타임 API 매칭 또는 운송 비고에서 판별한다.
- SKU의 `next_eta`는 확인 가능한 ETA 중 가장 이른 날짜다.
- `eta_actual_qty`, `eta_estimated_qty`, `eta_missing_qty`를 나누어 기록한다.
- Excel의 `ETA 미확인 물량` 열은 해당 수량이 0보다 클 때만 표시한다.

## 9. Excel에서만 계산되는 참고 산식

공식 `suggested_qty`, `upper_suggested_qty`, `reorder_point`, `target_stock`은 서버가 계산한 값을 Excel에 기록한다. 다음 항목은 검토용 Excel 수식이며 공식 코어 산식을 다시 계산하거나 대체하지 않는다.

```text
월평균판매량 = ROUND(13주 판매량 / 3, 0)

MOI = (현지가용 + 운송중) / 월평균판매량
      (월평균판매량이 0이면 –)

발주까지 여유주 = MAX(0, ROUND((IP - 발주점) / 주평균, 1))

예상 발주일 = 기준일 + MAX(0, (IP - 발주점) / 주평균) × 7일

보수적 발주 여유주 = MAX(
  0,
  ROUND(
    ((sqrt((Z × sigma)^2 + 4 × 주평균 × MAX(0, IP - 발주점))
      - Z × sigma) / (2 × 주평균))^2,
    1
  )
)

조기경보일 = 기준일 +
  ((sqrt((Z × sigma)^2 + 4 × 주평균 × MAX(0, IP - 발주점))
    - Z × sigma) / (2 × 주평균))^2 × 7일
```

현재 Excel 템플릿의 `운송수단 추천`은 보호기간 임계값을 비교해 `항공`, `철송`, `해운(여유)`, `🚨항공긴급`을 표시하는 검토용 ladder다. 공식 코어의 법인별 정책 매핑과 동일한 값으로 취급하지 않는다. 특히 USA export에서도 템플릿의 일부 표시 라벨은 공통 `철송` 기준을 사용하므로, 공식 정책 운송수단은 결과의 `transport_mode`와 법인별 설정 snapshot을 기준으로 확인해야 한다.

물류전망 주차별 재고 상태의 Excel 표시값은 다음 개념을 사용한다.

```text
예상재고(주차) = 현지가용 + 해당 주차까지의 누적 ETA 입고량
                - 월평균판매량 × 경과 주 수
```

이 값은 안전재고·발주점과 비교해 색상만 표시하며, 공식 발주수량을 재산출하지 않는다.

## 10. 실행·권한·검증 규칙

### 10.1 실행 snapshot

- CMS cache가 24시간을 초과하면 강제 재조회한다.
- 재조회 후에도 24시간 초과 또는 조회 실패이면 계산을 차단한다.
- `CASH`와 `SHORTAGE`는 동일한 원천 snapshot ID를 공유한다.
- source snapshot ID에는 CMS rows와 리드타임 감사 집계가 포함된다. `calculated_at`은 제외한다.
- `preview=true`는 latest 운영 결과를 갱신하지 않는다.
- 이전 `result_schema_version` 결과는 새 Excel 계약에 재사용하지 않는다.

### 10.2 설정 권한

- `adminmaster`, `ia`: 실행 시 고급 설정값을 보낼 수 있다.
- 그 외 일반계정: `현금흐름 우선` 또는 `쇼티지 방어` 시나리오만 선택하고 기본 설정값을 사용한다.
- 서버가 `/jobs` API에서 동일한 제한을 다시 검증한다.
- 설정은 실행별 snapshot이며 현재 DB에 영속 설정 테이블은 없다.
- 리드타임과 정책 운송수단은 화면에서 요청으로 되돌려 보내지 않고, PL/USA 실행 때 서버가 법인별로 결정한다.

### 10.3 행 상태 및 계산 차단

- 판매 없음: 수량 산식을 계산하지 않고 발주 신호를 `-`로 둔다.
- 데이터 부족·음수·필수 원천 누락: `계산불가` 또는 확인 필요로 유지한다.
- 현지·본사 재고 마스터 양쪽에 없는 SKU: `확인필요` 목록으로 분리한다.
- 재고 구성값 null: 필드별 0 대체 경고를 남긴다.
- 단가 누락: 수량은 계산할 수 있어도 금액은 비워 둔다.

## 11. 손검산 예시

아래 예시는 기본값과 `PL CASH` 고정값을 사용한 산식 검산 예시다. 실제 PL 운영 리드타임은 실행 시 실측값으로 대체될 수 있다.

### 예시 A — 발주 필요

가정:

```text
13주 판매량 = 매주 100개
d_bar = 100
sigma = 0
Pareto = MAJOR
PL CASH: LT = 36.6일, sigma_L = 1.15주, Z = 1.28
qty_incoming = 20
qty_eu_available = 10
qty_in_transit = 5
qty_local_available = 100
```

계산:

```text
P_weeks = (36.6 + 7) / 7 = 6.2286
Layer1 = 100 × 6.2286 = 622.86
Layer2_SS_raw = 1.28 × sqrt(6.2286 × 0^2 + 100^2 × 1.15^2)
              = 147.20
SS_floor = 100 × 2 = 200
Layer2_SS = 200  (하한 적용)
Layer3 = 100 × 2 = 200
ROP = 622.86 + 200 = 822.86
S = 822.86 + 200 = 1,022.86
IP = 20 + 10 + 5 + 100 = 135
suggested_qty = ceil(1,022.86 - 135) = 888개
IP_without_incoming = 115
upper_suggested_qty = ceil(1,022.86 - 115) = 908개
```

### 예시 B — 발주 불필요

같은 목표재고 `S=1,022.86`에서 `IP=900`이고 `ROP=822.86`이면 `IP >= ROP`이므로 `suggested_qty=0`이다. 미입고를 제외한 `IP_without_incoming`이 발주점보다 작으면 `upper_suggested_qty`만 양수가 될 수 있다.

## 12. 현재 미지원·주의사항

1. PL·USA의 실제 적용 리드타임 숫자는 문서의 고정값이 아니라 각 실행의 `settings`와 `lead_time_audit`에서 확인해야 한다.
2. HQ/OPO는 일 단위 전용 산식과 KRW·Asia/Seoul 계약을 사용하므로 PL/USA의 주 단위 정책값을 적용하면 안 된다.
3. 현재 결과·Excel의 일부 필드명은 과거 EU/PL 호환 때문에 `*_eur`라는 이름을 유지하지만 USA에서는 USD 값이다.
4. Excel의 운송수단 추천과 MOI·발주 여유·조기경보는 검토용 표시 산식이며 공식 발주량 산식과 분리되어 있다.
5. 이 문서는 로직을 변경하지 않는다. 산식 변경 시 기술명세, 코어, source mapping, API, 화면, Excel, 회귀 테스트를 함께 갱신해야 한다.

## 13. 검토 기준 파일

- [`ORDER_LOGIC_V2_HANDOFF.md`](ORDER_LOGIC_V2_HANDOFF.md)
- [`HQ_ORDER_ANALYSIS_HANDOFF.md`](HQ_ORDER_ANALYSIS_HANDOFF.md)
- [`core/order_logic_v2.py`](../core/order_logic_v2.py)
- [`backend/schemas_order_logic_v2.py`](../backend/schemas_order_logic_v2.py)
- [`backend/services/order_logic_v2_source.py`](../backend/services/order_logic_v2_source.py)
- [`backend/services/order_logic_v2_lead_time.py`](../backend/services/order_logic_v2_lead_time.py)
- [`backend/services/order_logic_v2_service.py`](../backend/services/order_logic_v2_service.py)
- [`backend/services/order_logic_v2_excel.py`](../backend/services/order_logic_v2_excel.py)
- [`backend/routers/order_logic_v2.py`](../backend/routers/order_logic_v2.py)
- [`backend/cms_client.py`](../backend/cms_client.py)
- [`backend/entities.py`](../backend/entities.py)
- [`tests/test_order_logic_v2.py`](../tests/test_order_logic_v2.py)
- [`tests/test_order_logic_v2_api.py`](../tests/test_order_logic_v2_api.py)
- [`tests/test_order_logic_v2_lead_time.py`](../tests/test_order_logic_v2_lead_time.py)

> PL V1/V2 sales demand population includes `EU-OVERSEAS`, `EU-PL`, `KR-OVERSEAS`, and `자사간거래`; USA V1/V2 includes `US-DOMESTIC`, `US-OVERSEAS`, `KR-OVERSEAS`, and `자사간거래`. Staff, free-sample, return, deferred-settlement, and accounting-adjustment rows remain excluded.
