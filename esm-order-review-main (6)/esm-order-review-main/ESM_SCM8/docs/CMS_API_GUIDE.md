# CMS API 연동 워크플로우 (바이브코딩용)

> 원화 환산 필드와 환율 기준의 단일 기준 문서:
> [`KRW_CONVERSION_HANDOFF.md`](KRW_CONVERSION_HANDOFF.md)

> **목표**: 지금 `/upload` 페이지에서 **엑셀 6개를 수동 업로드**하던 걸,
> **CMS API에서 자동으로 불러와 분석**하도록 바꾼다.
> 이 문서는 비개발자가 AI 코딩 도구(Claude Code / Cursor 등)에 **그대로 복붙**하며 진행하도록 만들어졌다.

---

## 0. 이걸 먼저 이해하고 시작하세요

- 분석 엔진(`core/`, `backend/analysis.py`)은 **건드리지 않습니다.** 이미 정확합니다.
- 우리가 추가하는 건 **"파일 대신 CMS API에서 데이터를 가져오는 입력 경로"** 하나입니다.
- 검증 끝난 사실: shipping·open-po·sales는 **CMS 공식 추출 기준과 동일**(같은 날짜범위로 호출하면 값까지 일치, open-po 930/930 검증). 재고 단가 미세차로 전체 발주금액은 ±소폭.
- **참고용 정답 코드가 이미 있습니다**: `tools/api_end_to_end.py`
  → API를 호출해서 분석까지 돌리는 전 과정이 들어있습니다. AI에게 **"이 파일을 참고하라"** 고 하면 가장 정확합니다.

### CMS API 접속 정보
| 항목 | 값 |
|---|---|
| 운영 Base URL | `https://cms.pikicat.com/api/v1` |
| Health | `https://cms.pikicat.com/health` |
| Swagger 문서 | `https://cms.pikicat.com/api/v1/docs` |
| 로컬 서버 | RDS가 사설망(VPC)에 있어 **로컬에서는 DB 연결 불가**. 운영 URL을 쓰세요. |

---

## 1. 엔드포인트 ↔ 분석 입력 매핑 (가장 중요)

분석 엔진은 내부적으로 **6종류의 데이터(key)** 를 기대합니다. CMS API 6개를 아래처럼 연결합니다.

| 분석 key | CMS 엔드포인트 | 비고 |
|---|---|---|
| `eu_stock` | `GET /eu/stock/local?as_of=YYYY-MM-DD` | EU현지재고 + **수요(`sales_qty_3m`)** + EUR단가 |
| `hq_eu_stock` | `GET /eu/stock/hq?as_of=YYYY-MM-DD` | 본사 EU창고재고 |
| `sales_detail` | `GET /eu/sales/local?page=&page_size=` | 유럽판매(페이지네이션) |
| `hq_to_eu_sales_detail` | `GET /eu/sales/hq-to-eu?page=&page_size=` | 본사→EU 출고(페이지네이션) |
| `shipping` | `GET /eu/shipping/containers` | 해상컨테이너 상세 (**리스트 응답, 페이지네이션 아님**). CMS 공식 리포트와 동일. 날짜 미지정 시 **최근 3개월** |
| `open_po` | `GET /eu/open-po` | 미입고현황. CMS 공식 리포트와 동일. 날짜 미지정 시 **최근 3개월** |

### 미주 법인(`USA`) 매핑

미주 일반 분석은 같은 6개 분석 key를 아래 API로 채운다.

| 분석 key | CMS 엔드포인트 |
|---|---|
| `eu_stock` | `GET /us/stock/local?as_of=YYYY-MM-DD` |
| `hq_eu_stock` | `GET /us/stock/hq?as_of=YYYY-MM-DD` |
| `sales_detail` | `GET /us/sales/local?page=&page_size=` |
| `hq_to_eu_sales_detail` | `GET /us/sales/hq-to-us?page=&page_size=` |
| `shipping` | `GET /us/shipping/containers` |
| `open_po` | `GET /us/open-po` |

- 미주 현지 판매와 시즌 분석은 `/us/sales/local`을 사용한다.
- `/us/sales/history`는 본사(`CO000001`) 전체 창고의 장기 판매내역 상세이며, 미주 현지 판매로 합산하지 않는다.
- 시즌 상품 마스터는 별도 `/us/products`가 없으므로 전사 COSMETIC 상품 마스터인 `/eu/products?eu_sold_only=false`를 사용한다.
- 미주 현지 원통화 금액은 USD다. 원화 분석에는 판매 `amount_krw_actual`, 재고 `unit_cost_krw`·`stock_amount_krw`, 컨테이너 `amount_krw`를 그대로 사용하고 현재 환율을 다시 곱하지 않는다.
- 신규 발주 로직 V2는 미주 정책값이 확정될 때까지 미주 요청을 차단하며 PL 정책을 대신 적용하지 않는다.

### 본사(`HQ`) 분석 매핑

본사는 발주 계산이 아니라 분석 탭의 판매 인사이트만 제공한다.

| 분석 입력 | CMS 엔드포인트 | 사용 기준 |
|---|---|---|
| `sales_history` | `GET /us/sales/history?date_from=&date_to=&page=&page_size=` | 본사 전 창고 COSMETIC 판매이력 |
| `prod_list` | `GET /eu/products?eu_sold_only=false&page=&page_size=` | 전사 상품·브랜드·기능구분1/2 마스터 |

- 두 응답은 `prod_cd`로 결합한다.
- 본사 판매금액은 `amount_krw`를 원화 매출로 사용하며 EUR/USD 환율을 다시 곱하지 않는다.
- `/us/sales/history`가 이미 `EXCS`를 제외한 본사 전체 판매 모집단을 반환하므로, 본사에서는 별도 법인 거래유형 허용목록으로 다시 제한하지 않는다.
- 국가·브랜드·제품군·SKU·시즌 캘린더·교차분석·브랜드 리포트가 이 결합 데이터에서 생성된다.
- 재고·미입고·운송 API가 없는 본사에서는 발주 분석 및 발주분석 V2를 실행하지 않는다.

### 1-1. 필드 매핑 (API 영문 → 분석이 기대하는 한글 컬럼)

분석 엔진은 한글 컬럼명을 기대합니다. 아래 표대로 이름을 바꿔서 넣어야 합니다.

**stock/local → `eu_stock`**, **stock/hq → `hq_eu_stock`**
| API 필드 | → 한글 컬럼 |
|---|---|
| `prod_cd` | 상품코드 |
| `prod_nm` | 상품명 |
| `bar_code` | 바코드 |
| `brand_nm` | 브랜드 |
| `stock_ucost` | EU 입고단가 *(이미 EUR로 환산된 값)* |
| `unit_cost_krw` | CMS 원화 입고단가 *(조회 기준일 고시환율 반영)* |
| `stock_amount_krw` | CMS 재고금액(KRW) |
| `xrate`, `xrate_dt`, `xrate_source` | 적용 환율·기준일·출처 |
| `stock_qty` | 재고수량 |
| `hold_qty` | Hold수량 |
| `avbl_qty` | 가용수량 |
| `sales_qty_3m` | 최근 3개월 판매수량 *(수요의 핵심. stock/local에만 의미있음)* |

**sales/local → `sales_detail`**, **sales/hq-to-eu → `hq_to_eu_sales_detail`**
| API 필드 | → 한글 컬럼 |
|---|---|
| `prod_cd` | 상품코드 |
| `qty` | 수량 |
| `amount` | 금액 *(현지통화)* |
| `amount_krw` | 법인 기준통화 환산금액 *(원화 아님)* |
| `amount_krw_actual` | 실제 원화 환산금액 *(거래일 고시환율 반영)* |
| `xrate`, `xrate_dt`, `xrate_source` | 적용 환율·기준일·출처 |
| `curr` | Curr |
| `ship_dt` | 출고일 |
| `invc_no` | Invoice No |
| `biz_type` | Biz Type |
| `site` | Site |

**shipping → `shipping`** *(CMS '해상컨테이너 상세내역' 리포트와 동일 14컬럼)*
| API 필드 | → 한글 컬럼 |
|---|---|
| `pckg_no` | Packing No |
| `invc_no` | Invoice No |
| `ship_dt` | 출고일 |
| `site` | Site |
| `whouse_nm` | 창고 |
| `cust_nm` | 거래처 |
| `prod_cd` | 상품코드 |
| `prod_nm` | 상품명 |
| `brand_nm` | 브랜드 |
| `qty` | 수량 |
| `curr` | Curr |
| `amount` | 금액 |
| `amount_krw` | CMS 원화 환산금액 *(인보이스 계약환율 반영)* |
| `xrate`, `xrate_dt`, `xrate_source` | 계약환율·기준일·출처 |
| `remark` | Invoice 비고 *(여기서 운송수단(해운/항공/철송)을 자동 추출함)* |
| `internal_type_nm` | 지사 구분 |

> ⚠️ **변경**: `eta_dt`·`pnfm_no`·`curr_gbn` 는 **제거**됐습니다. 출고일은 `ship_dt` 를 쓰세요.

**open-po → `open_po`** *(CMS '미입고현황' 리포트와 동일 컬럼)*
| API 필드 | → 한글 컬럼 |
|---|---|
| `prod_cd` | 상품코드 |
| `prod_nm` | 상품명 |
| `bar_code` | 바코드 |
| `brand_nm` | 브랜드 |
| `po_qty` | PO 수량 |
| `pnfm_qty` | PNFM 수량 |
| `pnfm_confirmed_qty` | PNFM확정 수량(②) |
| `inbound_in_progress_qty` | 입고진행중 수량(③) |
| `open_qty` | 미입고 수량 |
| `open_amt` | 미입고 금액 |
| `completed_qty` | 입고완료 수량(④, 표시 전용) |

- PL 발주분석 V2의 재고 위치에는 `open_qty`(①)와
  `pnfm_confirmed_qty + inbound_in_progress_qty`(②+③)를 반영한다.
- USA 발주분석 V2의 운송중 수량은 `/us/shipping/containers`의 SKU별 `qty`
  합계를 사용한다. USA의 ②·③·④는 원천 확인용으로 표시하되 재고 위치에
  별도로 더하지 않는다.
- `completed_qty`(④)는 이미 재고에 반영된 수량이므로 어느 법인에서도 발주
  산식에 별도로 더하지 않는다.

---

## 2. 꼭 지켜야 할 규칙 (안 지키면 결과가 크게 틀어짐)

1. **날짜 파라미터** (전 엔드포인트 지원):
   - `stock/local`·`stock/hq`: `as_of=YYYY-MM-DD` (재고 스냅샷 기준일). 미지정 시 오늘.
   - `sales/local`·`sales/hq-to-eu`: `date_from=YYYY-MM-DD` (이 날짜 이후 출고). 미지정 시 **최근 3개월**.
   - `shipping`·`open-po`: `date_from`·`date_to` (선적일 / PO등록일 범위). 미지정 시 **최근 3개월(오늘 기준 3개월 전 같은 일자 ~ 오늘)**.
   - **CMS 엑셀과 똑같이 맞추려면**: 엑셀 다운로드 때 쓴 날짜범위를 그대로 `date_from`·`date_to`(또는 `as_of`)로 넣으세요. (예: 6/12에 3/12~6/12로 뽑았으면 동일 범위 전달 → 값까지 100% 일치 확인됨)
2. **단가는 이미 EUR**: `stock_ucost`는 EUR로 환산되어 옵니다. **추가로 환율 나누지 마세요.** (과거에 KRW로 와서 금액이 1,700배 폭증한 적 있음)
3. **숫자 컬럼은 문자열로 채우기**: 재고 프레임을 만들 때 빈값(null)을 빈 문자열 `""`로 채운 뒤 문자열로 넣으세요. (전부 NaN인 컬럼이 분석 내부에서 에러를 냄)
4. **shipping은 페이지네이션 아님**: `GET /eu/shipping/containers`는 리스트를 통째로 반환합니다. **페이지 루프 돌리지 마세요** (무한루프 위험). 한 번 `GET`으로 받으세요.
5. **sales는 페이지네이션 필수**: `page=1`부터 `total`까지 `page_size=1000`으로 순회. (`page_size=5000`은 502 납니다. 1000 권장)
6. **느린 응답 재시도**: 운영 API가 가끔 502/timeout → 2~3회 재시도 로직 넣으세요.

---

## 3. 단계별 작업 (AI에게 줄 프롬프트)

각 단계의 회색 박스를 AI 코딩 도구에 **그대로 붙여넣고**, 끝나면 ✅ 확인 항목을 직접 체크하세요.

### STEP 1 — CMS에서 데이터 가져오는 모듈 만들기

```
ESM_SCM8 프로젝트에 backend/cms_client.py 를 새로 만들어줘.
목적: CMS API(https://cms.pikicat.com/api/v1)에서 6개 엔드포인트 데이터를 가져온다.
요구사항:
- base URL은 환경변수 CMS_API_BASE_URL 로 받고, 기본값은 https://cms.pikicat.com/api/v1
- 함수 fetch_cms_data(as_of: str) 하나를 만들어, 아래 6개를 dict로 반환:
  stock_local, stock_hq, sales_local, sales_hq, shipping, open_po
- stock_local/stock_hq 는 ?as_of={as_of} 붙여서 호출
- sales_local/sales_hq 는 page=1부터 total까지 page_size=1000으로 페이지네이션
- shipping, open_po 는 페이지네이션 없이 한 번에 GET (리스트 반환)
- 502/503/504/timeout 발생 시 2~3회 재시도
- 참고: tools/api_end_to_end.py 에 이미 동작하는 호출/페이지네이션 코드가 있으니 그걸 따라줘
```
✅ 확인: `python -c "from backend.cms_client import fetch_cms_data; d=fetch_cms_data('2026-06-10'); print({k:len(v) for k,v in d.items()})"` 실행 시 6개 행수가 출력됨.

### STEP 2 — API 응답을 분석 입력으로 변환하는 모듈 만들기

```
backend/cms_mapping.py 를 새로 만들어줘.
목적: STEP1에서 받은 CMS API JSON을, 분석 엔진이 기대하는 한글 컬럼 DataFrame 6개(dict)로 변환한다.
- 함수 build_uploaded_data_from_cms(raw: dict) -> dict[str, pandas.DataFrame]
- 반환 dict의 key는 정확히: eu_stock, hq_eu_stock, sales_detail, hq_to_eu_sales_detail, shipping, open_po
- 컬럼 매핑은 docs/CMS_API_연동_워크플로우.md 의 "1-1 필드 매핑" 표를 그대로 따른다
- eu_stock, hq_eu_stock 프레임은 .fillna("").astype(str) 로 문자열화 (전부 NaN인 컬럼 에러 방지)
- shipping 출고일은 ship_dt 를 쓴다 (eta_dt 는 제거됨)
- 참고: tools/api_end_to_end.py 에 이미 동작하는 매핑 코드가 있으니 그걸 그대로 가져와줘
```
✅ 확인: 변환 결과 각 DataFrame의 컬럼명이 한글(상품코드/재고수량 등)로 나옴.

### STEP 3 — 분석 본체를 재사용하는 새 분석 함수 + 엔드포인트

```
backend/analysis.py 의 run_core_analysis 를 참고해서,
"이미 만들어진 uploaded_data dict"를 받아 분석을 돌리는 함수를 추가해줘.
- 기존 run_core_analysis 는 prepare_uploaded_data(saved_uploads) 로 uploaded_data 를 만든 뒤
  분석 본체(order_review_df ~ summary/tables 생성)를 돈다.
- 그 "분석 본체" 부분을 재사용할 수 있게,
  run_core_analysis_from_uploaded_data(uploaded_data, uploaded_files, output_path, eur_krw_rate, settings_overrides)
  함수를 만들어줘. 반환 형태는 run_core_analysis 와 100% 동일(summary, tables, file_mapping, uploaded_files, settings).
- 그 다음 backend/main.py 에 새 엔드포인트 POST /api/analyze/cms 를 추가:
  body 로 as_of(필수), eur_krw_rate(선택)를 받아서
  cms_client.fetch_cms_data → cms_mapping.build_uploaded_data_from_cms → 위 새 함수 실행 →
  기존 /api/analyze 와 똑같은 JSON(job_id, summary, tables, download_url, settings, file_mapping, uploaded_files)을 반환.
- 참고: tools/api_end_to_end.py 가 바로 이 "uploaded_data 로 분석 돌리기"를 하고 있다.
```
✅ 확인: `curl -X POST http://127.0.0.1:8001/api/analyze/cms -H "Content-Type: application/json" -d '{"as_of":"2026-06-10"}'` → summary에 total_sku/order_required_sku 등이 나옴.

### STEP 4 — 프론트엔드에 "CMS에서 불러와 분석" 버튼 추가

```
frontend 에서 /upload 페이지(components/upload/UploadWorkflow.tsx)에
"CMS에서 불러와 분석" 버튼을 추가해줘.
- 클릭하면 파일 선택 없이 백엔드 POST /api/analyze/cms 를 호출 (기준일 as_of 입력칸 하나, 기본 오늘 날짜)
- 응답 처리는 기존 파일 업로드 분석과 동일하게 결과 화면으로 이어지게 해줘
- API 호출 함수는 frontend/lib/api.ts 에 analyzeFromCms(asOf, options) 로 추가
  (기존 analyzeFiles 가 호출하는 방식/baseUrl 그대로 재사용)
```
✅ 확인: 브라우저 `/upload`에서 버튼 클릭 → 파일 없이 분석 결과(발주/보고서/확인필요/재고ETA)가 뜸.

### STEP 5 — 검증 (수동 업로드 결과와 비교)

```
같은 기준일(2026-06-10) 데이터로,
(A) 기존 엑셀 6개 수동 업로드 분석 결과와
(B) 새 /api/analyze/cms 분석 결과의 summary 를 나란히 비교해줘.
- 비교 항목: total_sku, order_required_sku, check_required_sku, order_required_qty, order_amount_eur
- 각 항목 차이(%)를 표로 보여줘. ±5% 이내면 정상.
```
✅ 합격 기준: 발주필요 SKU·발주수량·발주금액이 **±5% 이내**. (검증 시 ±1~5% 확인됨)

---

## 4. 정확도 현황 (대부분 해결됨)

| 항목 | 상태 |
|---|---|
| **날짜 파라미터** | ✅ 해결 — sales/shipping/open-po 모두 `date_from`/`date_to`, stock은 `as_of` 지원. 미지정 시 최근 3개월 |
| **shipping 스코프** | ✅ 해결 — CMS 공식 '해상컨테이너 상세내역' 추출 기준으로 교체. 같은 시점/범위면 일치 |
| **open_po 스코프** | ✅ 해결 — CMS 공식 '미입고현황' 추출 기준으로 교체. 같은 PO등록일 범위면 **값까지 100% 일치(930/930 검증)** |
| **단가(stock_ucost)** | EUR 환산 ~98.7% 일치 (미세차 잔존, 발주금액에 ±소폭) |

> shipping·open-po·sales는 **CMS 엑셀과 동일 범위로 호출하면 동일 결과**입니다.

> ⚠️ **기존 연동 코드 재정렬 필요**: API 응답 필드가 바뀌었으므로(shipping 14컬럼·`eta_dt` 제거, open-po에 상품명·금액 추가), 기존 `backend/cms_mapping.py` 와 `tools/api_end_to_end.py` 의 매핑을 **위 1-1 표 기준으로 다시 맞춰야** 합니다.

---

## 5. 트러블슈팅 (우리가 실제로 겪은 것들)

| 증상 | 원인 | 해결 |
|---|---|---|
| 발주 금액이 수십억 EUR로 폭증 | 단가를 KRW로 받아 EUR처럼 씀 | `stock_ucost`는 이미 EUR. 환율 나누지 말 것 |
| `Can only use .str accessor with ... floating` | 전부 NaN인 컬럼 | 재고 프레임 `.fillna("").astype(str)` |
| shipping 호출이 안 끝남 | 리스트 응답에 페이지 루프 | shipping은 `GET` 한 번만 |
| `502 Bad Gateway` | page_size 너무 큼 | `page_size=1000`로 |
| `read operation timed out` | 운영 API 일시 지연 | 2~3회 재시도 |
| 발주필요가 절반으로 뚝 | (과거) shipping 스코프 과다 | ✅ 공식 쿼리로 해결됨. 엑셀과 같은 날짜범위로 호출 |

---

## 6. 체크리스트 (다 끝나면)

- [ ] `backend/cms_client.py` — 6개 호출 + 재시도 + 페이지네이션
- [ ] `backend/cms_mapping.py` — 한글 컬럼 변환 (1-1 표 준수)
- [ ] `backend/analysis.py` — `run_core_analysis_from_uploaded_data` 추가
- [ ] `backend/main.py` — `POST /api/analyze/cms` 추가
- [ ] `frontend/lib/api.ts` + `UploadWorkflow.tsx` — "CMS에서 불러와 분석" 버튼
- [ ] STEP 5 검증 — 수동 업로드 대비 ±5% 확인
- [ ] (운영 전) 환경변수 `CMS_API_BASE_URL` 설정

> **막히면**: AI에게 `tools/api_end_to_end.py 를 참고해서 고쳐줘` 라고 하세요.
> 그 파일이 "API 호출 → 한글 매핑 → 분석 실행 → 결과 비교"의 완성된 예시입니다.
