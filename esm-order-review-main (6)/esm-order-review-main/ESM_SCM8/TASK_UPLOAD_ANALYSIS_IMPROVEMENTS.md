# 작업 지시서: /upload 분석 속도 개선 + 입력 이원화 해소

> 이 문서는 코딩 에이전트(Claude Code / Codex)가 단독으로 읽고 작업할 수 있도록 작성됨.
> 아래 파일 경로·라인 번호는 2026-07-02 기준 main 브랜치(`b2047f0`)에서 검증된 값이다.
> **라인 번호는 참고용이며 코드 변경으로 밀릴 수 있으니, 작업 전 반드시 심볼명/문자열로 grep 해서 실제 위치를 재확인할 것.**

---

## 0. 시스템 구조 요약 (작업 전 필독)

- **프론트엔드**: Next.js — `frontend/`. `/upload` 페이지의 실제 UI는 `frontend/components/redesign/SiliconAnalyticsWorkspace.tsx` (8,000줄 이상의 대형 단일 파일. 전체를 읽지 말고 필요한 함수만 grep으로 찾아 읽을 것).
- **백엔드**: FastAPI — `backend/`. DB 없음, 결과는 `backend/storage/` 하위 JSON/파일로 저장.
- 데이터 원천은 **CMS API** (외부 HTTP API). `backend/cms_client.py`가 6종 데이터를 병렬로 fetch한다. 판매이력(`/eu/sales/local`)은 페이지네이션(1,000행/페이지, 병렬 6워커)이라 **10만 행 이상이면 fetch에만 3~4분** 걸린다 (이 사실은 `backend/config.py`의 주석에도 명시돼 있음).

### /upload 페이지의 두 분석 흐름 (현재 상태)

| | 발주 탭 (`PrepScreenExact`) | 인사이트 > 데이터 입력 탭 (`InsightInputScreenExactV2`) |
|---|---|---|
| 컴포넌트 | `SiliconAnalyticsWorkspace.tsx` 내 함수 (약 1191행~) | 같은 파일 내 함수 (약 3019행~) |
| 사용자 입력 | 환율(EUR/KRW), 현지/운송 목표(개월), 해운·항공·철송·트럭 L/T(일) | 분석 시작일~종료일 |
| 버튼 | `▶ 분석 시작` | `분석 시작` |
| API | `POST /api/analyze/cms` (`backend/routers/cms.py:68`) | `POST /api/season-trend/analyze-api` (`backend/routers/season.py:317`) |
| 하는 일 | CMS 6종 fetch → 발주 리뷰 + **시즌/성분 분석(`build_season_ingredient_analysis`)까지 전부 계산**해서 한 응답에 반환 | CMS 판매이력을 **다시 fetch** (`fetch_season_trend_source_data`, `backend/season_trend_api_client.py:61`) → **같은 `build_season_ingredient_analysis`를 다시 실행** |

핵심 문제: **두 흐름이 같은 무거운 작업(판매이력 fetch + 시즌/성분 분석)을 각각 수행**하고, 입력 폼도 따로라서 사용자가 값을 두 번 입력한다.

---

## 작업 1 (우선순위: 높음, 난이도: 낮음) — 프론트/백엔드 타임아웃 불일치 수정

### 현상
- 프론트 타임아웃: **180초** — `frontend/lib/api/analysis.ts:38` `const CMS_ANALYSIS_CLIENT_TIMEOUT_MS = 180_000;` (AbortController로 중단, 408 에러 "CMS 분석 응답이 3분을 넘었습니다")
- 백엔드 타임아웃: **600초** — `backend/config.py` `CMS_ANALYSIS_TIMEOUT_SECONDS` (기본 600)
- 백엔드 주석 자체가 "fetch에만 3~4분 걸릴 수 있음"이라고 명시하는데 프론트가 3분에 끊어버림 → **데이터가 큰 날은 백엔드가 정상 계산 중인데 프론트가 실패 처리**한다.

### 할 일
1. `CMS_ANALYSIS_CLIENT_TIMEOUT_MS`를 백엔드와 정합되게 상향: **630_000 (10분 30초, 백엔드 600초 + 여유 30초)**.
2. 타임아웃 에러 메시지의 "3분" 문구도 새 값에 맞게 수정.
3. `frontend/lib/api/analysis.ts` 안에서 이 상수를 쓰는 다른 곳(fetch 옵션, AbortController 등)이 모두 같은 상수를 참조하는지 확인. 하드코딩된 `180`/`3분`이 다른 파일에 또 있는지 `grep -rn "180_000\|3분" frontend/` 로 확인하고, /upload 분석 흐름에 해당하는 것만 수정 (무관한 곳은 건드리지 말 것).

### 완료 기준
- 분석 요청이 3분을 넘어도 프론트가 끊지 않고 백엔드 응답(또는 백엔드 자체 타임아웃)을 기다린다.
- 사용자에게 보이는 타임아웃 안내 문구와 실제 동작이 일치한다.

---

## 작업 2 (우선순위: 높음, 난이도: 중간) — 입력 이원화 해소 + 중복 계산 제거

### 2-A. L/T 하드코딩 버그 (반드시 수정)

`SiliconAnalyticsWorkspace.tsx`의 `InsightInputScreenExactV2` 내 `analyzeSeasonTrendFromApi(...)` 호출부(약 3092~3101행)가 L/T를 **하드코딩**으로 보낸다:

```ts
leadTimeSea: 70,
leadTimeAir: 15,
leadTimeRail: 30,
leadTimeTruck: 30
```

발주 탭에서 사용자가 L/T를 수정해도 시즌 분석에는 반영되지 않는다 (사용자는 반영된다고 믿음 → 조용한 데이터 오류).

**할 일**: 발주 탭에서 입력한 L/T 값을 시즌 분석 호출에도 사용하도록 수정. 방법은 2-B의 상태 공유와 함께 해결할 것.

### 2-B. 입력 상태 공유

현재 `PrepScreenExact`와 `InsightInputScreenExactV2`는 각자 로컬 `useState`를 쓰고 상위 컴포넌트는 분석 결과(`currentAnalysisResult`, `insightAnalysisReady`)만 보관한다.

**할 일**:
1. 분석 설정(환율, 현지/운송 목표 개월, L/T 4종)을 상위 컴포넌트(또는 React Context)로 끌어올려 두 화면이 공유하게 한다.
2. 발주 탭에서 입력/수정한 값이 데이터 입력 탭의 시즌 분석 요청에 그대로 사용되어야 한다.
3. 데이터 입력 탭에는 (원하면 확인할 수 있게) 현재 적용될 설정값을 읽기 전용으로 표시하는 정도가 적당하다. **동일 값을 다시 입력받는 폼을 만들지 말 것.**
4. 기존 localStorage 저장/복원 로직이 있다면 (grep으로 확인) 끌어올린 상태와 충돌하지 않게 정리.

### 2-C. 중복 계산 제거 (프론트 우선, 백엔드는 최소 변경)

`/api/analyze/cms` 응답에는 이미 `season_analysis`(시즌/성분 분석 결과)가 포함된다. 데이터 입력 탭이 요청하는 분석이 **이미 받은 결과와 같은 조건**이면 재호출 없이 그 결과를 쓴다.

**할 일**:
1. 데이터 입력 탭의 `분석 시작` 처리에서: 요청하려는 기간·옵션이 `currentAnalysisResult.season_analysis`의 분석 옵션과 일치하면 → API 호출 생략, 저장된 결과 사용.
2. 기간이 다르면(예: 사용자가 과거 2년 선택) 기존대로 `/api/season-trend/analyze-api` 호출 — 이 경로는 유지한다.
3. (백엔드, 선택적 개선) `backend/routers/season.py`의 `analyze_season_trend_from_api`에는 이미 동일 옵션 캐시(`_latest_api_analysis_matches`)가 있다. 여기에 더해, 판매이력 fetch가 `backend/services/cms_fetch_cache.py`의 디스크 캐시를 활용할 수 있는지 검토하라. 단, `fetch_season_trend_source_data`는 기간 파라미터가 자유(date_from/date_to)라 캐시 키 체계가 다르다 — **키 설계가 억지스러우면 이 항목은 건너뛰고 그 사유를 결과 보고에 남길 것.**

### 완료 기준
- 발주 탭에서 L/T를 예: 80/20/35/35로 바꾼 뒤 데이터 입력 탭에서 분석 실행 → 네트워크 탭에서 요청 payload의 L/T가 80/20/35/35인지 확인.
- 발주 분석 직후 같은 기간으로 데이터 입력 탭 분석 실행 → `/api/season-trend/analyze-api` 네트워크 요청이 발생하지 않고 결과가 즉시 표시된다.
- 다른 기간 선택 시에는 기존대로 API 호출이 발생하고 정상 결과가 나온다.

---

## 작업 3 (우선순위: 중간, 난이도: 중상) — 백엔드 백그라운드 사전 분석

### 목적
사용자가 "▶ 분석 시작"을 누르기 전에 서버가 미리 CMS fetch + 분석을 끝내두어, 버튼 클릭 시 수 초 내 응답하게 한다.

### 이미 존재하는 기반 (새로 만들지 말 것)
- **CMS fetch 캐시**: `backend/services/cms_fetch_cache.py` — 메모리 LRU + 디스크 JSON 2단. 당일 데이터 TTL은 `config.py`의 `CMS_TODAY_CACHE_TTL_SECONDS` (기본 300초), 과거 날짜는 무기한. `backend/routers/cms.py`의 `get_or_fetch_cms_raw_data(...)`가 사용 중.
- **분석 결과 저장소**: `backend/services/order_review_store.py` → `backend/storage/latest_order_review/{client_id}.json`. GET 엔드포인트도 이미 있음: `backend/routers/analysis.py:374` (`latest_order_review`).
- **주의**: 현재 스케줄러는 없음. `backend/main.py`에 lifespan/startup 훅도 없음. BackgroundTasks는 `cms.py:253`의 엑셀 지연 내보내기에만 사용 중.

### 설계 지침

1. **스케줄러 도입**: 외부 의존성 최소화를 위해 **APScheduler 또는 asyncio 기반 자체 루프** 중 택1. 이 프로젝트 컨벤션(무DB, 단순 구조)상 celery 같은 무거운 스택은 금지.
   - FastAPI `lifespan`에서 시작/종료하도록 구현.
   - 실행 시각: **매일 새벽 (기본 06:00 KST, 환경변수로 조정 가능하게)**. 환경변수 이름 컨벤션은 기존 `SCM_*` 패턴을 따를 것 (예: `SCM_PRE_ANALYSIS_ENABLED`, `SCM_PRE_ANALYSIS_HOUR_KST`).
   - **기본값은 비활성(`SCM_PRE_ANALYSIS_ENABLED=false`)으로 두고 환경변수로 켜는 방식** — 배포 안전성 확보.

2. **사전 분석 작업 내용**: `routers/cms.py`의 `_fetch_and_analyze`와 동일한 파이프라인을 기본 설정값으로 1회 실행.
   - 기본 설정값: 환율은 자동 조회 값, 목표 개월/L/T는 프론트 기본값과 동일(현지 2 / 운송 1 / 해운 70 / 항공 15 / 철송 30 / 트럭 30). **프론트 기본값이 바뀌면 어긋나므로, 기본값 상수를 백엔드 config에 정의하고 주석으로 프론트 위치를 상호 참조해 둘 것.**
   - 라우터의 HTTP 핸들러를 내부에서 호출하지 말고, fetch+분석 로직을 **함수로 분리(리팩터링)** 해서 라우터와 스케줄러가 공유하게 한다.
   - 동시성: 기존 `acquire_analysis_slot`(`backend/services/concurrency.py`)과 충돌하지 않게 처리. 사전 분석은 사용자 요청과 경합하면 양보(스킵)해도 된다.

3. **효과가 나는 지점**: 사전 분석이 돌고 나면 CMS fetch 디스크 캐시가 데워진다. 이때 사용자 요청이 캐시를 실제로 타려면 **당일 TTL(300초)이 문제** — 사전 분석 후 사용자가 출근할 때쯤이면 이미 만료된다.
   - `CMS_TODAY_CACHE_TTL_SECONDS` 기본값을 상향하는 것은 **데이터 신선도 요구를 모르므로 임의로 바꾸지 말 것.** 대신 환경변수이므로 운영에서 조정 가능하다는 점을 결과 보고에 명시하고, 사전 분석 기능 문서(아래 4)에 권장값(예: 21600=6시간)을 적어라.
   - 또는: 사전 분석 결과 JSON을 `latest_order_review` 저장소에 별도 `client_id`(예: `"_preanalysis"`)로 저장하고, 프론트가 분석 시작 전에 "오늘자 사전 분석 결과가 있으면 즉시 로드 + 백그라운드 재검증" 하는 방식도 가능하다. **이 프론트 연동까지는 이번 작업 범위에 넣지 말고, 백엔드에서 결과를 저장·조회 가능한 상태까지만 만들 것.** (프론트 연동은 후속 작업)
   - 주의: `client_id`는 `backend/services/audit.py:31` `client_id_from_request`로 요청에서 파생된다. 사전 분석은 요청이 없으므로 예약 ID를 쓰되, 실제 사용자 client_id와 충돌하지 않는 값인지 확인할 것.

4. **문서화**: 새 환경변수·동작을 README 또는 기존 문서 패턴에 맞는 위치에 짧게 기록.

### 완료 기준
- `SCM_PRE_ANALYSIS_ENABLED=true`로 백엔드 기동 → 지정 시각(테스트 시엔 임박한 시각으로 설정)에 사전 분석이 실행되고, `storage/cms_fetch_cache/`와 `storage/latest_order_review/`에 산출물이 생긴다.
- 사전 분석 직후(캐시 TTL 내) `/api/analyze/cms` 호출 → CMS fetch 없이 캐시 히트로 응답 시간이 크게 단축된다 (audit 로그의 cache hit 이벤트로 확인 가능).
- `SCM_PRE_ANALYSIS_ENABLED` 미설정(기본) 상태에서는 기존 동작과 완전히 동일하다.
- 사전 분석 실행 중 예외가 발생해도 서버 기동/서빙에 영향이 없다 (try/except + 로깅).

---

## 공통 주의사항

1. **작업 순서**: 작업 1 → 작업 2 → 작업 3 순서로, **각 작업을 별도 커밋**으로 분리할 것. 커밋 메시지는 기존 히스토리 스타일(영문 명령형, 예: `Fix analysis timeout mismatch between frontend and backend`)을 따를 것.
2. `SiliconAnalyticsWorkspace.tsx`는 매우 큰 파일이다. 전체 리팩터링 금지 — **이번 작업에 필요한 최소 변경만** 할 것.
3. 백엔드 코드 컨벤션: 주석·에러 메시지는 한국어, 기존 파일들의 스타일을 따를 것. 응답 envelope 래핑 금지(기존 그대로).
4. 기존 API의 요청/응답 스키마를 **깨뜨리지 말 것** — 프론트 구버전 캐시가 남아있을 수 있다. 필드 추가는 가능, 제거/의미 변경은 금지.
5. 검증:
   - 백엔드: 기존 테스트가 있으면 실행(`pytest` 등, 프로젝트 설정 확인). 없으면 최소한 `python -c "import backend.main"` 수준의 임포트 확인 + 로컬 기동 확인.
   - 프론트: `npm run build` (또는 프로젝트의 빌드/린트 스크립트, `frontend/package.json` 확인)가 통과해야 한다.
6. 확신이 없는 지점(특히 작업 3의 캐시 TTL, client_id 설계)은 임의 판단으로 밀어붙이지 말고, 구현 가능한 안전한 범위까지만 하고 **결과 보고에 판단 근거와 미결 사항을 명시**할 것.

## 배경 (참고)

- 사용자 불만: "분석 시작 버튼을 누르면 너무 느리다" — 실측 병목은 ① CMS 판매이력 페이지네이션 fetch(수분), ② `build_season_ingredient_analysis` 계산(수십 초).
- 발주 탭과 데이터 입력 탭이 같은 무거운 작업을 각각 수행 + 입력도 따로 받아 혼란 → 작업 2.
- 근본 개선은 서버 사전 계산 → 작업 3.
