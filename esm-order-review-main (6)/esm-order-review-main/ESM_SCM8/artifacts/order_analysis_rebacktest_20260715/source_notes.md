# 발주분석 수정 후 재백테스트 — 소스 노트

## 판정

조건부 공유 가능(Share with caveat). 수정 대상 수용 조건 14개와 전체 회귀검사는 통과했다. 수정 후 UI가 직접 생성한 Excel이 아직 없고, 저장 결과의 기준일 이전 ETA 303행은 입고 상태 대조가 필요하다.

## 데이터와 변환

- 기준선 발주검토 Excel: `ESM_order_review_filtered_all_2026-07-15 (1).xlsx`, 2,571행.
- 기준선 재고공백 Excel: `ESM_stock_gap_filtered_all_2026-07-13 (2).xlsx`, 2,570행.
- 수정 후 실데이터 규모 재산출: `backend/storage/latest_order_review/849fa1db-cffa-43bd-aaf6-832f21f35036.json`, 2,571행.
- 현행 계산: `frontend/lib/api/mappers.ts`와 `frontend/lib/stock-gap.ts`를 Node TypeScript 실행기로 직접 호출.
- 기간·결측 경계값: `backend/analysis.py` 공개 계산 함수를 합성 데이터로 실행.
- Excel 호환성: ExcelJS로 `errorStyle=stop` 파일을 생성하고 openpyxl로 재로드한 뒤 OOXML 속성을 검사.

## 지표 정의

- 부족수량: `ceil(재고공백 일수 × 일평균 판매량)`.
- 최근 3개월: 설정된 `period_start`와 `period_end`를 모두 포함하는 판매 상세.
- 과거 ETA 경고: `earliest_eta_date < base_date`.
- 위험 행: `stock_gap` 또는 `urgent_replenishment` 상태.

## 실행 검증

- 발주분석 프런트 회귀: 11 assertions passed.
- Python 전체: 168 passed, 1 skipped, 104 warnings.
- 프런트 타입검사: 통과.
- Next.js 프로덕션 빌드: 통과, 37개 페이지 생성.
- Portable HTML 검증: 1 chart, 11 blocks, source dialog, 1,440px·390px 뷰포트 통과.

## 한계

- 수정 후 UI에서 새로 내려받은 발주검토·재고공백 Excel이 없어 실제 새 파일 전체 레이아웃은 직접 대조하지 못했다.
- 기준일 이전 ETA 303행은 입고 완료일 수 있으나 저장 결과에 입고 완료 상태가 없어 현재 ETA로 사용할 수 있는지 확정할 수 없다.
- 기준선 두 Excel의 생성일이 달라 SKU 단위 동시점 교차 조인은 하지 않았다.
