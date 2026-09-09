# ESM SCM 운영 장애 대응 문서

## 문서 목적

이 문서는 BM본부 내부 링크 운영 단계의 1차 장애 대응 기준입니다.
로그인/계정 권한 체계가 없는 현재 구조에서는 담당자가 서버 상태, 감사 로그, 입력 파일 상태를 기준으로 원인을 좁히고 사용자에게 임시 안내합니다.

## 1. 운영 등급

| 등급 | 기준 | 예시 | 1차 목표 |
|---|---|---|---|
| P1 | 다수 사용자가 핵심 기능을 사용할 수 없음 | 사이트 접속 불가, 업로드/분석 전체 불가 | 서비스 복구 또는 기존 엑셀 방식 임시 전환 |
| P2 | 일부 핵심 기능 장애 | 결과 다운로드 실패, 특정 파일 분석 실패, 환율 조회 실패 | 우회 방법 안내 및 원인 확인 |
| P3 | 기능은 가능하나 품질/속도 저하 | 동시 사용 시 느림, AI 응답 지연 | 로그 확인 후 개선 과제 등록 |

## 2. 1차 확인 순서

1. 프론트 도메인 접속 확인
2. 프론트 프록시 health 확인: `<프론트 도메인>/backend-api/health`
3. 백엔드 직접 health 확인: `<백엔드 주소>/api/health`
4. 프론트 운영 환경변수 확인: `FASTAPI_INTERNAL_BASE_URL`
5. 백엔드 CORS 환경변수 확인: `FRONTEND_ORIGIN`
6. 감사 로그 확인: `backend/storage/audit/audit_YYYYMMDD.jsonl`
7. 백엔드 저장공간 확인: health 응답의 `disk.free_bytes`
8. 최근 배포/커밋 확인
9. 필요 시 백엔드/프론트 서버 재시작
10. 사용자에게 임시 안내
11. `INCIDENT_LOG_TEMPLATE.md` 기준으로 장애 이력 기록

## 3. 주요 장애별 대응

## 3-1. 1차 운영 제한 정책

| 항목 | 기본값 | 환경변수 |
|---|---:|---|
| 전체 동시 분석 | 2개 | `SCM_MAX_CONCURRENT_ANALYSES` |
| 사용자당 동시 분석 | 1개 | `SCM_MAX_ANALYSES_PER_CLIENT` |
| 파일 1개 최대 용량 | 100MB | `SCM_MAX_UPLOAD_FILE_MB` |
| 전체 업로드 최대 용량 | 300MB | `SCM_MAX_UPLOAD_TOTAL_MB` |
| 분석 timeout | 180초 | `SCM_ANALYSIS_TIMEOUT_SECONDS` |

동시 분석 제한을 초과하면 즉시 실행 방식은 `429 Too Many Requests`를 반환합니다.
Worker를 사용하는 시즌/수요 분석은 요청을 먼저 대기열에 접수하고, Worker가
실제로 시작할 때 실행 슬롯을 사용합니다.
파일 용량 제한을 초과하면 API는 `413 Payload Too Large`를 반환합니다.
분석 시간이 timeout을 초과하면 API는 `504 Gateway Timeout`을 반환하고 감사 로그에 `error_type=timeout`을 남깁니다.

현재 1차 운영 버전은 pandas/openpyxl 분석 로직을 요청 안에서 실행합니다.
분석 시간이 자주 1~3분 이상 걸리거나, 429가 업무 지연으로 자주 발생하면 백그라운드 작업 큐 도입을 검토합니다.

## 3-2. CMS 분석 성능/캐시

CMS 기반 분석(`POST /api/analyze/cms`)의 병목 1순위는 CMS API 원본 fetch입니다
(실측: uncached 130~181초, 분석 본체는 캐시 기준 20~28초).
같은 조건(as_of/date_from/date_to/logistics_date_from)의 반복 분석은
memory → disk 캐시를 재사용해 20~30초대에 끝나야 정상입니다.

시즌/수요 분석(`POST /api/season-trend/analyze-api`)도 같은 raw-data 캐시 저장소를
사용합니다. 캐시 키는 선택 기간(date_from/date_to)과 시즌 분석 namespace로 분리되어
발주검토 원천 캐시와 충돌하지 않습니다. 1년 기간처럼 `/eu/sales/local` 페이지가
200개 이상인 요청은 최초 실행 시 CMS fetch가 수 분 걸릴 수 있으며, 같은 기간의
반복 실행은 latest result 캐시 또는 raw-data 캐시를 재사용해야 합니다.

### 캐시 동작

- as_of=오늘: `SCM_CMS_TODAY_CACHE_TTL_SECONDS`(기본 14400초=4시간) 동안 캐시 재사용.
  당일 최신 데이터가 급히 필요하면 TTL을 줄이거나 백엔드 재시작이 아니라
  `backend/storage/cms_fetch_cache/`의 해당 캐시 파일 삭제로 무효화합니다.
- as_of=과거: 데이터가 확정이므로 TTL 없이 무기한 재사용.
- 캐시는 memory(최근 4개) + disk(`backend/storage/cms_fetch_cache/*.json`) 2단계이며,
  백엔드 재시작 후에도 disk 캐시로 CMS API 재호출 없이 복구됩니다.

### 관련 환경변수

| 이름 | 용도 | 기본값 |
|---|---|---:|
| `SCM_CMS_TODAY_CACHE_TTL_SECONDS` | 오늘자 CMS raw 캐시 TTL | 14400 |
| `SCM_CMS_ANALYSIS_TIMEOUT_SECONDS` | CMS 분석 서버 timeout | 600 |
| `SCM_CMS_FETCH_CACHE_MAX_AGE_DAYS` | 디스크 캐시 파일 보관 일수. 0 이하면 정리 안 함 | 7 |
| `SCM_PRE_ANALYSIS_ENABLED` | CMS raw 캐시 사전 프리페치 사용 여부 | false |
| `SCM_PRE_ANALYSIS_INTERVAL_SECONDS` | CMS raw 캐시 사전 프리페치 주기. 오늘자 TTL보다 짧게 유지 | 1500 |
| `SCM_PRE_ANALYSIS_HOURS_KST` | 프리페치 허용 KST 시간대. 예: `8-20`, `8-12,13-20` | 8-20 |
| `SCM_V3_SEASON_FACTOR_MONTHLY_ENABLED` | V3 시즌팩터 월간 candidate 생성·검증·자동 활성화 | false |
| `SCM_V3_SEASON_FACTOR_MONTHLY_DAY` | 공식 월 마감 후 실행할 KST 일자. 활성화 시 필수 | 미설정 |
| `SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST` | 월간 실행 KST 시각(0~23). 활성화 시 필수 | 미설정 |
| `SCM_V3_SEASON_FACTOR_CHECK_INTERVAL_SECONDS` | 월간 실행 여부 확인 주기 | 900 |
| `CMS_API_PAGE_SIZE` | 페이지당 행 수 (100~2000, 5000은 502 이력) | 2000 |
| `CMS_API_PARALLEL_PAGES` | 페이지 병렬 호출 수 (1~12) | 8 |
| `CMS_API_REQUEST_TIMEOUT_SECONDS` | CMS API 요청 1건 timeout (10~600) | 120 |

프론트 fetch timeout은 `frontend/lib/api/analysis.ts`의
`CMS_ANALYSIS_CLIENT_TIMEOUT_MS`(630초)로, 서버 timeout(600초)보다 길게 유지해야
서버의 504가 브라우저 abort보다 먼저 도착합니다.

### 확인할 로그 (백엔드 콘솔 + 감사 로그)

캐시 hit (반복 분석, 20~30초대에 끝나야 함):

```
[perf][cms_fetch_cache] hit source=disk as_of=2026-07-02 key=1a2b3c4d5e6f age_seconds=412.3 ttl_seconds=14400
[perf][cms_analysis] job_id=... raw_data_ready seconds=3.1 cache_hit=True cache_source=disk rows={...}
```

캐시 miss (CMS API 신규 fetch, 2~3분 걸릴 수 있음):

```
[perf][cms_fetch_cache] miss as_of=2026-07-02 key=1a2b3c4d5e6f ttl_seconds=14400
[perf][cms_api] paged_done path=/eu/sales/local pages=62 page_size=2000 parallel=8 total=122611 rows=122611 seconds=78.4
[perf][cms_api] endpoint_done key=sales_local rows=122611 seconds=78.4
[perf][cms_api] fetch_all_done rows=136853 seconds=80.2
[perf][cms_fetch_cache] miss_fetched as_of=2026-07-02 key=1a2b3c4d5e6f seconds=80.2 ttl_seconds=14400
```

### CMS raw 사전 프리페치

Cold-start 방지는 opt-in입니다. `SCM_PRE_ANALYSIS_ENABLED=true`일 때만 FastAPI
lifespan에서 백그라운드 asyncio task가 시작됩니다(`start_backend.bat`은 이 값을
기본으로 켭니다). 이 작업은 CMS raw 캐시만 재충전하며, 발주 분석 본체를 실행하지
않고 사용자 분석 동시성 슬롯도 잡지 않습니다.

프리페치 1사이클이 데우는 것(2026-07-09 실측):

- 발주용 원천 6종(as_of=오늘, 판매이력 연초~오늘) — 콜드 fetch 72~86초
- 분석 탭 기본 선택 구간(최근 1년, 오늘 종료) — 콜드 fetch 2~4분.
  프론트 기본값(demandRange(12))과 같은 날짜 계산(12개월 전 같은 날, 말일 클램프)을
  쓰는 `_season_default_range`로 캐시 키를 일치시킨다.

캐시가 데워진 뒤 사용자 체감: 발주 분석 총 10~12초, 분석 탭 기본값 총 15~22초
(분석 본체 계산만 남음). 과거 종료일 구간(연도 칩 등)은 최초 1회 실행 후 무기한
캐시라 프리페치 대상이 아니며, 임의 기간 첫 실행은 여전히 콜드(행 수 비례, 8초~5분).

프리페치 사이클과 서버 기동 시 `SCM_CMS_FETCH_CACHE_MAX_AGE_DAYS`(기본 7일)를 넘긴
디스크 캐시 파일을 정리합니다(`prune_disk_cache`). 만료 파일은 같은 키를 다시 읽을
때만 지워지는 lazy-delete 구조라, 이 정리가 없으면 다시는 요청되지 않는 파일
(지난 날짜 기준 발주/시즌 캐시, 하루 ~85MB×2)이 무한히 쌓입니다.

로컬 테스트 예시:

```bat
set SCM_PRE_ANALYSIS_ENABLED=true
set SCM_PRE_ANALYSIS_INTERVAL_SECONDS=60
set SCM_PRE_ANALYSIS_HOURS_KST=8-20
```

운영 권장값:

- `SCM_CMS_TODAY_CACHE_TTL_SECONDS=14400` 유지.
- `SCM_PRE_ANALYSIS_INTERVAL_SECONDS=1500` 유지. TTL 만료 전에 다음 refresh가 시작됩니다.
- 프리페치는 `POST /api/analyze/cms`와 같은 `(as_of, date_from, date_to, logistics_date_from)` 캐시 키를 사용합니다.
- 백엔드 콘솔에서 `[prefetch] started/done/season_done/skipped/failed`를 확인하고, 감사 로그에서
  `cms_prefetch_succeeded` / `cms_prefetch_failed` / `cms_prefetch_season_succeeded` /
  `cms_prefetch_season_failed` 이벤트를 확인합니다.

감사 로그 `cms_analysis_succeeded` 이벤트의 `cms_fetch_cache` 필드
(`hit`/`source`/`created_at`/`age_seconds`/`ttl_seconds`)와
분석 응답 JSON의 `cms_fetch_cache` 필드에서도 동일 정보를 확인할 수 있습니다.
브라우저 개발자 콘솔에서는 `[perf][analysis-client] cms_fetch_cache`로 표시됩니다.

### 운영 판단 기준

- 반복 분석인데 매번 `miss`가 찍히면: 요청 조건(as_of 등)이 매번 달라지는지, TTL이
  너무 짧게 override됐는지, disk 캐시 디렉터리 쓰기 권한을 확인합니다.
- `[perf][cms_api] request_retryable_status`(502/503/504)가 자주 보이면
  `CMS_API_PARALLEL_PAGES`를 낮춥니다. 거의 없으면 8~10으로 올려 uncached fetch를
  단축할 수 있습니다.
- 2차 개선 후보(아직 미착수): 분석 본체 중 `order_review_df`(~12.8초),
  `build_check_required_df`(~6.8초). uncached가 여전히 느리면 비동기 job/polling
  구조 도입을 검토합니다.

## 3-3. 대용량 엑셀 업로드 성능

**배경(2026-07-22 실측)**: 단일 파일(eu_stock, 97MB/179만행) 업로드+분석 요청이
180초 분석 timeout(504) 이후에도 서버가 13분 넘게 응답하지 않는 문제를 확인했습니다
(`/api/health`도 같은 기간 응답 없음 — 다른 사용자의 요청도 함께 지연됩니다).

원인은 분석 로직이 아니라 파일을 읽는 단계였습니다. `core/loaders.py`의 헤더 행
자동판별이 `sales_history`/`prod_list`를 제외한 모든 업로드 role(eu_stock,
sales_detail, shipping 등)에 대해 헤더 후보 0~5행을 확인하려고 시트 전체를 최대
6번 다시 읽고 있었습니다. 30만행/12MB 샘플에서 `read_excel` 1회가 33초였으므로,
97MB 파일은 6회 반복하면 20분 이상이 됩니다.

**수정(커밋 `f2f51bc`)**: 헤더 후보 판별은 1,000행 미리보기만으로 채점하고(점수
함수가 컬럼명과 1,000행 캡 행 수만 보므로 미리보기와 전체읽기 점수가 항상
동일합니다), 승자 header_row에 대해서만 시트 전체를 1회 읽도록 변경했습니다.
같은 샘플에서 이론상 198초 → 실측 40.8초로 약 5배 개선되었습니다.

**남은 한계**: openpyxl 자체의 시트 파싱 속도는 그대로이므로, 100MB에 근접한
대용량 단일 파일은 여전히 수 분 걸릴 수 있고 그 구간에는 다른 요청도 지연될 수
있습니다(pandas 행 단위 계산이 GIL을 오래 점유). 구조화된 perf 로그는 아직 이
경로에 없습니다 — 반복적으로 큰 파일 업로드가 느리다는 문의가 들어오면 먼저 파일
용량과 행 수를 확인하고, 필요 시 비동기 작업 큐 도입(3-1 참고)을 검토합니다.

사용자 안내:

```text
파일 용량이 커서 분석에 시간이 오래 걸리고 있습니다.
가능하면 파일을 역할별로 나누거나 불필요한 행을 정리한 뒤 다시 시도해 주세요.
```

### 사이트 접속 불가

- 프론트 배포 상태와 도메인/DNS 상태를 확인합니다.
- 프론트 서버 로그에서 빌드/실행 오류를 확인합니다.
- 운영에서 `FASTAPI_INTERNAL_BASE_URL`이 없으면 Next 실행이 실패하도록 되어 있으므로 환경변수를 먼저 확인합니다.

사용자 안내:

```text
현재 사이트 접속이 원활하지 않아 확인 중입니다.
긴급 업무는 기존 엑셀 방식으로 우선 진행해 주세요.
```

### 업로드 또는 분석 버튼 멈춤

- 프론트 경유 `/backend-api/health`와 백엔드 직접 `/api/health`를 각각 확인합니다.
- 감사 로그에서 `analysis_started`, `analysis_failed` 이벤트를 확인합니다.
- 파일 크기, 확장자, role 중복/누락, 필수 컬럼 미감지 여부를 확인합니다.
- 저장공간 부족이면 `backend/storage/outputs`, `backend/storage/audit` 보관 정책과 디스크 용량을 확인합니다.

사용자 안내:

```text
분석 서버 상태와 업로드 파일 형식을 확인 중입니다.
파일 role, 확장자, 주요 컬럼을 확인한 뒤 다시 시도해 주세요.
```

### 결과 엑셀 다운로드 실패

- 분석 응답의 `download_url`에 token이 포함되어 있는지 확인합니다.
- 감사 로그에서 `download_failed` 이벤트를 확인합니다.
- 결과 파일 위치를 확인합니다: `backend/storage/outputs/{job_id}/ESM_order_review_{job_id}.xlsx`
- 결과 파일은 기본 24시간 보관 후 자동 삭제됩니다.

사용자 안내:

```text
결과 다운로드 링크가 만료되었거나 접근 토큰이 맞지 않을 수 있습니다.
같은 파일로 다시 분석을 실행해 주세요.
```

### 환율 API 실패

- 환율 API는 실패 시 fallback 값을 사용하도록 되어 있습니다.
- 분석 화면의 환율 표시와 결과 설정값을 확인합니다.
- 필요 시 사용자가 수동 환율 입력 후 재분석하도록 안내합니다.

사용자 안내:

```text
환율 자동 조회가 실패하여 기본값 또는 수동 입력값을 사용해야 합니다.
필요 시 환율을 직접 입력한 뒤 다시 분석해 주세요.
```

### 특정 파일에서 계산 오류

- 감사 로그에서 해당 `job_id`의 `analysis_failed`를 확인합니다.
- 자동분류 결과의 confidence, 필수 컬럼 미감지, role 매핑을 확인합니다.
- 원본 파일 내용은 감사 로그에 남기지 않습니다. 필요 시 사용자에게 파일명/컬럼 구조만 확인 요청합니다.

사용자 안내:

```text
해당 파일의 필수 컬럼 또는 파일 role 매핑을 확인해야 합니다.
파일명, role, 주요 컬럼을 확인한 뒤 다시 업로드해 주세요.
```

### 결과 숫자가 기존 엑셀과 다름

- 같은 입력 파일인지 확인합니다.
- 파일 role 매핑과 분석 설정값을 확인합니다.
- 감사 로그의 `analysis_succeeded.details.file_mapping`, `settings`, `summary`를 확인합니다.
- 필요 시 기존 엑셀 방식으로 임시 진행하고, 차이 항목을 별도 이슈로 남깁니다.

임시 복귀 기준:

- 발주 금액/수량이 업무 의사결정에 직접 영향을 주고 원인을 당일 확인하기 어려운 경우
- 특정 브랜드/SKU에 한정되지 않고 다수 결과가 기존 방식과 크게 다른 경우
- 분석 서버 장애가 30분 이상 지속되는 경우

### AI/Ollama 응답 없음

- AI 기능은 분석 결과 엑셀에서 제한된 요약과 일부 행만 읽어 Ollama로 보냅니다.
- 기본 Ollama 주소는 `http://localhost:11434`입니다.
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL` 환경변수와 Ollama 프로세스 상태를 확인합니다.
- AI가 안 되더라도 업로드/분석/다운로드는 독립적으로 운영합니다.

사용자 안내:

```text
AI 요약 기능 응답이 지연되고 있습니다.
분석 결과 엑셀 다운로드와 기본 화면 조회는 계속 사용할 수 있습니다.
```

## 4. 서버 재시작

로컬 개발 환경:

```bat
start_backend.bat
start_frontend.bat
```

운영 배포 환경:

- 배포 플랫폼의 재시작 버튼 또는 재배포 기능을 사용합니다.
- 재시작 전 최근 오류 로그와 감사 로그를 먼저 보존합니다.
- 재시작 후 `/api/health`와 업로드 화면 접속을 확인합니다.

## 5. 로그 위치

| 로그 | 위치 | 용도 |
|---|---|---|
| 감사 로그 | `backend/storage/audit/audit_YYYYMMDD.jsonl` | 분석/다운로드/AI 접근 이력 |
| 결과 엑셀 | `backend/storage/outputs/{job_id}/` | 24시간 임시 보관 |
| 원본 업로드 | `backend/storage/uploads/{job_id}/` | 분석 중 임시 저장 후 삭제 |
| 서버 로그 | 배포 플랫폼 또는 실행 콘솔 | 예외 traceback, 서버 실행 오류 |

감사 로그에는 원본 엑셀 내용과 다운로드 token을 남기지 않습니다.

## 6. 환경변수

| 이름 | 용도 | 기본/필수 |
|---|---|---|
| `FASTAPI_INTERNAL_BASE_URL` | 프론트 `/backend-api` 프록시가 연결할 백엔드 주소 | 운영 필수 |
| `NEXT_PUBLIC_FASTAPI_BASE_URL` | 브라우저가 직접 호출할 공개 백엔드 주소 | 선택. 없으면 같은 도메인의 `/backend-api` 사용 |
| `APP_ENV` | 운영 모드에서 Swagger/OpenAPI 문서 비활성화 | 운영은 `production` |
| `FRONTEND_ORIGIN` | 백엔드 CORS 허용 프론트 도메인 | 운영 권장 |
| `SCM_STORAGE_MAX_AGE_HOURS` | 결과 엑셀 보관 시간 | 기본 24 |
| `SCM_AUDIT_RETENTION_DAYS` | 감사 로그 보관 일수 | 기본 90 |
| `SCM_MAX_CONCURRENT_ANALYSES` | 전체 동시 분석 제한 | 기본 2 |
| `SCM_MAX_ANALYSES_PER_CLIENT` | 사용자당 동시 분석 제한 | 기본 1 |
| `SCM_MAX_UPLOAD_FILE_MB` | 파일 1개 최대 업로드 용량 | 기본 100 |
| `SCM_MAX_UPLOAD_TOTAL_MB` | 전체 업로드 최대 용량 | 기본 300 |
| `SCM_ANALYSIS_TIMEOUT_SECONDS` | 분석 요청 timeout | 기본 180 |
| `SCM_CMS_ANALYSIS_TIMEOUT_SECONDS` | CMS 분석 요청 timeout | 기본 600 |
| `SCM_CMS_TODAY_CACHE_TTL_SECONDS` | 오늘자 CMS raw 캐시 TTL | 기본 14400 |
| `SCM_PRE_ANALYSIS_ENABLED` | CMS raw 캐시 사전 프리페치 사용 여부 | 기본 false |
| `SCM_PRE_ANALYSIS_INTERVAL_SECONDS` | CMS raw 캐시 사전 프리페치 주기 | 기본 1500 |
| `SCM_PRE_ANALYSIS_HOURS_KST` | 프리페치 허용 KST 시간대 | 기본 8-20 |
| `SCM_V3_SEASON_FACTOR_MONTHLY_ENABLED` | V3 시즌팩터 월간 candidate 생성·자동 활성화 | 기본 false |
| `SCM_V3_SEASON_FACTOR_MONTHLY_DAY` | 공식 월 마감 후 실행할 KST 일자 | 미설정 |
| `SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST` | 월간 실행 KST 시각 | 미설정 |
| `SCM_V3_SEASON_FACTOR_CHECK_INTERVAL_SECONDS` | 월간 실행 여부 확인 주기 | 기본 900 |
| `CMS_API_PAGE_SIZE` | CMS API 페이지당 행 수 | 기본 2000 |
| `CMS_API_PARALLEL_PAGES` | CMS API 페이지 병렬 호출 수 | 기본 8 |
| `CMS_API_REQUEST_TIMEOUT_SECONDS` | CMS API 요청 1건 timeout | 기본 120 |
| `KOREAEXIM_API_KEY` | 환율 조회 API 키 | 선택 |
| `OLLAMA_BASE_URL` | AI/Ollama 서버 주소 | 기본 localhost |
| `OLLAMA_MODEL` | Ollama 모델명 | 기본 gemma4 |

운영 배포에서는 `APP_ENV=production`을 설정해 `/docs`, `/redoc`, `/openapi.json`이 외부에 노출되지 않도록 합니다.
대용량 엑셀 업로드도 기본적으로 같은 도메인의 `/backend-api`를 거쳐 전송합니다.
백엔드 도메인을 별도로 둘 때만 `NEXT_PUBLIC_FASTAPI_BASE_URL`을 설정합니다.
별도 도메인으로 호출하는 경우 백엔드 `FRONTEND_ORIGIN`에는 운영 프론트 도메인이 반드시 포함되어야 합니다.

## 7. 장애 종료 기준

- 사용자가 다시 사이트에 접속할 수 있습니다.
- `/backend-api/health`와 백엔드 직접 `/api/health`의 `status`가 모두 `ok`입니다.
- 업로드, 분석, 다운로드 중 장애 난 기능이 재현되지 않습니다.
- 감사 로그에 성공 이벤트가 다시 남습니다.
- 장애 이력 템플릿에 원인, 조치, 재발 방지 항목을 기록했습니다.
