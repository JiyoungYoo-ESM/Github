# EU order logic v2 isolated experiment

이 폴더는 신규 EU 발주 로직 검증을 위한 격리된 실험 환경입니다. 운영 반영용 코드가 아니며, 기존 발주 로직, 화면, API 응답, 운영 저장소/cache 구조를 변경하지 않습니다.

## 원칙

- CMS API는 읽기 전용으로만 호출합니다.
- 기존 `backend/`, `core/`, `frontend/`, `tests/` 파일을 수정하지 않습니다.
- 실험 결과는 `experiments/order_logic_v2/outputs/` 아래에만 저장됩니다.
- 파일명에는 실행 시각을 붙여 기존 결과를 덮어쓰지 않습니다.
- 운영 분석 결과 파일이나 운영 CMS cache 디렉터리에 실험 결과를 저장하지 않습니다.

## 파일

- `utils.py`: 출력 경로 보호, SKU 정규화, 월별/주별 판매 집계, 필드 가용성 진단, 간단 Holt 후보, Excel 저장 공통 함수
- `run_data_audit.py`: 신규 산식 검증에 필요한 CMS 데이터 필드/품질 감사
- `run_monthly_vs_weekly_test.py`: 기존 3개월 평균, 월별 후보 예측, 8주 주차 재고전망 비교 PoC
- `outputs/`: Excel/JSON 결과 저장 위치

## 실행 예시

```bash
python experiments/order_logic_v2/run_data_audit.py --as-of 2026-07-06 --date-from 2024-07-01 --date-to 2026-07-06
python experiments/order_logic_v2/run_monthly_vs_weekly_test.py --as-of 2026-07-06 --date-from 2024-07-01 --date-to 2026-07-06 --limit-skus 200
```

특정 SKU만 빠르게 보고 싶을 때:

```bash
python experiments/order_logic_v2/run_monthly_vs_weekly_test.py --as-of 2026-07-06 --date-from 2024-07-01 --date-to 2026-07-06 --sample-sku ABCD01-EU --sample-sku WXYZ02-EU
```

## 결과 해석

`run_data_audit.py`는 `data_audit_YYYYMMDD_HHMMSS.xlsx`와 `raw_field_report_YYYYMMDD_HHMMSS.json`을 만듭니다.

- `summary`: 신규 산식, 월별 예측, 현재 주차 재고전망, 진짜 주차별 수요예측, 완전 백테스트 가능 여부
- `field_availability`: CMS raw JSON과 매핑 DataFrame 기준 필드 존재/활용 가능 여부
- `sales_monthly_quality`: SKU별 판매월 수, 최근 6/12/24개월 판매 존재 여부, 급변 SKU
- `sales_weekly_quality`: 실제 출고일 기반 주별 집계 가능 SKU와 주 수
- `stock_quality`, `transport_quality`, `po_quality`: 재고/운송/PO 핵심 필드 점검
- `missing_fields`: 부족한 핵심 필드 Top 10
- `recommendation`: 다음 데이터 보강/검증 방향

`run_monthly_vs_weekly_test.py`는 `monthly_vs_weekly_YYYYMMDD_HHMMSS.xlsx`를 만듭니다.

- `sku_comparison`: SKU별 기존 3개월 평균, 월별 예측값, 주평균 환산값, 재고/운송/ETA, 방식별 추천 발주량 차이
- `monthly_forecast`: 최근 3개월 평균, 최근 12/24개월 평균, 간단 Holt 후보와 선택된 월별 예측값
- `weekly_projection`: SKU별 8주 재고전망. 운송중 수량은 ETA 주차에만 더합니다.
- `stockout_risk`: 8주 안에 재고가 0 미만이 되거나 4주 커버 목표 아래로 내려가는 SKU
- `method_differences`: 방식별 추천 발주량 차이가 큰 SKU
- `data_limitations`: PoC 해석 시 주의해야 할 데이터 한계

## 계산상 주의

- 기존 방식은 최근 3개월 판매량 기반 월평균을 사용하고, 주평균은 `월평균 / 4.33`으로 환산합니다.
- 월별 방식은 12~24개월 월별 판매 이력을 우선 사용하며, 간단 Holt 후보를 포함합니다.
- 현재 주차 방식은 진짜 주차별 수요예측이 아니라 월평균을 주평균으로 환산한 뒤 ETA를 8주 달력에 펼치는 재고전망입니다.
- 운송중 재고는 지금 당장 판매 가능한 재고가 아니므로, 주차 재고전망에서는 ETA 도착 주차에만 입고로 반영합니다.
- IP 계산용 수량과 날짜별 OH_t 재고전망은 분리해서 봐야 합니다.

## 한계

- 과거 `as_of` 재고 스냅샷이 없으면 완전한 백테스트는 불가합니다.
- `sellable_days`가 없으면 품절로 눌린 판매량 보정은 불가합니다.
- `promo_flag` 또는 `bulk deal` 식별 필드가 없으면 일반 수요가 왜곡될 수 있습니다.
- SKU alias mapping이 없으면 코드 변경으로 끊긴 판매 이력을 연결하기 어렵습니다.
- 실제 `arrival_date`가 없으면 리드타임 보정과 ETA 백테스트가 불가합니다.

## 검증 명령

```bash
python -m compileall experiments/order_logic_v2
python experiments/order_logic_v2/run_data_audit.py --help
python experiments/order_logic_v2/run_monthly_vs_weekly_test.py --help
```
