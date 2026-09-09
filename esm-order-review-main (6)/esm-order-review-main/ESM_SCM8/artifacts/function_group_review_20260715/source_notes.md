# CMS 기능군 분석 검토 — 소스 노트

## 보고서 구조 매핑

- Title: `CMS 기능군 분석 탭 검토`
- Executive Summary: 구현 가능 여부, 핵심 10개 타당성, 미입고 공백, 파생 기능군 필요성
- Key findings with visual evidence: 기능구분 매출 집중도 차트와 원천별 연결률 근거
- Recommended next steps: 매핑표 → 백엔드 집계 → 전체 상품 마스터 보충 → UI → 품질 게이트
- Further questions: 크림·선크림·마스크팩 포함 규칙, 순위 기준, 반품 처리
- Caveats and assumptions: 캐시 스냅샷, 보정 의존성, 비표준 분류, open PO ETA 부재

## 차트 맵

| 섹션 | 질문 | 형식 | 데이터 | 근거 주장 | 팔레트 | 산출물 |
|---|---|---|---|---|---|---|
| 매출 집중도 | 어느 기능구분 조합이 매출을 주도하는가 | leaderboard | 기능구분 조합, 매출 비중, SKU 수 | 상위 10개 조합이 매출 85.37%를 포괄 | single-root blue | `cms_function_group_review.html` |
| 운영 데이터 연결 | 기능구분을 재고·운송·미입고에 연결할 수 있는가 | horizontal bar(검토 데이터 유지, 최종 블록에서는 제외) | 원천별 SKU·수량 연결률 | open PO만 SKU 연결률 80.54%로 낮음 | single-root blue | 노트북 및 보고서 본문 |

두 차트가 모두 비교형 막대 계열인 이유는 첫 번째가 기능군 순위, 두 번째가 데이터 원천별 연결률 비교라는 서로 다른 범주 비교 문제이기 때문이다. 최종 HTML에서는 브라우저 가로폭 검증 실패를 줄이기 위해 첫 번째 시각화만 노출하고, 두 번째는 본문 수치로 유지했다.

## 계산 및 품질 판정

- 판매 원천: `/eu/sales/local`, 2024-07-15~2026-07-14
- 상품 원천: `/eu/products?eu_sold_only=true` 및 누락 판매 SKU 전체 상품목록 보충
- 발주 검토 원천: 현지/HQ 재고, 현지/HQ 판매, 운송, open PO
- SKU 키: 앞뒤 공백 제거 후 대소문자 보존 정확 일치
- 기능군 순위: 기존 EU 판매 Biz Type 필터·기능구분 보정·비핵심 상품 제외 후 판매금액 내림차순
- 기능군 수요: 판매수량 합계
- 연결률: 연결 고유 SKU / 원천 고유 SKU
- 수량 연결률: 연결 행 절대 수량 합 / 전체 절대 수량 합

## 검증 상태

- `artifact.json`: 공식 portable artifact validator 통과
- `cms_function_group_review.html`: 공식 builder로 생성 및 payload/semantic fallback 구조 검증 통과
- 브라우저 검증: 데스크톱 1,440px에서 `horizontal_overflow` 판정이 반복되어 완전 통과하지 못함. 차트 유형·데이터 열·표 블록·소스 경로를 축소해 재검증했으나 동일했다.
- 노트북: 프로젝트 가상환경에 `jupyter`, `nbformat`, `nbclient`, `ipykernel`이 없어 실행본 저장은 불가. 동일 코드는 프로젝트 가상환경 Python으로 셸에서 실행해 수치를 검증했다.
