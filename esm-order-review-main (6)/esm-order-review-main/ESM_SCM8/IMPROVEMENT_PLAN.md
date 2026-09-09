# 코드 개선 계획 (2026-07-13 감사 기반)

> 2026-07-13 전체 코드 감사(백엔드/프론트엔드/테스트·위생 3방향 병렬 리뷰) 결과에서 도출된 개선 백로그.
> 원칙: **안전망 먼저, 구조 변경은 그 뒤.** 모든 항목은 발주검토/분석 로직의 계산 결과를 바꾸지 않는 구조·인프라 작업임.
> 2026-07-13 추가: UI/UX 안전성 4방향 검증 완료 — 각 항목에 검증 결과와 실행 조건 반영됨. §"UI/UX 안전성 검증" 참조.
> 2026-07-13 오후 추가: 발주분석탭 신규 커밋 2개(bcddc69, cba8bc0) 리뷰 완료 — 확정 결함 7건을 신규 항목 1.5로 편입, 라인 참조 전면 갱신(워크스페이스 10,167→10,562줄). §"발주분석탭 신규 커밋 리뷰" 참조.
> **2026-07-20 갱신: 풀스택 관점 재감사.** 1·1.5·2번 완료·커밋 확인, 워킹트리 클린. 지난 일주일 리포트 내보내기 기능 작업으로 두 god 파일이 크게 성장 — **Workspace.tsx 10,562→12,517줄(+18%), report_template_export.py 4,357→7,790줄(+79%, 거의 2배)**. 남은 항목(3·4·5) 판정은 전부 유효하며 5번·백엔드 god module의 시급성만 상승. 계획 구조 변경 없음, 수치·시급성만 갱신. §진행 기록 2026-07-20 참조.

## 감사 요약

| 부문 | 점수 | 한 줄 요약 |
|---|---|---|
| 백엔드 (Python ~23K줄) | 6.5/10 | 계층 분리·캐시 설계는 성숙, god module과 동시성 결함이 발목 |
| 프론트엔드 (TS ~28K→32K줄) | 4.5/10 | 타입은 모범생(`any` 10건 이하), 구조는 응급실 — 전체의 36%→**40%가 파일 하나**(07-20 재측정) |
| 테스트 | 5.5/10 | 백엔드 137개는 진짜배기, API 계층·프론트는 0, CI 부재 |
| 저장소 위생 | 6.0/10 | git 내부는 깨끗, 작업 트리는 로그 78개+임시파일 311MB |

종합: **6.0/10 — "실력 부족이 아니라 정리 미루기." 지금은 잘 돌아가지만 수정 비용이 복리로 늘어나는 구조.**

---

## UI/UX 안전성 검증 (2026-07-13, 코드 실측)

| 항목 | UI 영향 판정 | 근거 |
|---|---|---|
| 1. 다운로드 폴링 | **없음** (대기 방식만 변경) | 단, pytest 137개는 HTTP 경로를 안 봄 → 실브라우저 다운로드 1회 필수 |
| 2. CI+ESLint | **없음** (코드 수정 0줄) | 자동수정 금지 원칙 유지 시 |
| 3. 죽은 코드 삭제 | **없음** — 후보 전원 삭제 가능 확정 | 정적/동적/문자열 참조 전수 검색 + 도달 불가 증명 완료 |
| 4. 인증 이관 | **로그인 주변만** — 화면 생김새는 유지 가능 | 분석·발주 화면은 lib/auth 참조 0건 검증됨. 단 구현 함정 4개(아래) |
| 5. 워크스페이스 해체 | **픽셀-동일 가능** — 분리 친화적 구조 확인 | 모듈 가변상태 0·부수효과 0·Context 0. 단 3조건(아래) |

**안전망 실측 (냉정한 현실)**: 웹 UI 시각·인터랙션 회귀를 잡는 자동 장치는 현재 사실상 없음.
- `npm test`(ui-regression) = 소스 문자열 grep 8건, 0.1초. 화면이 백지가 돼도 통과.
- `npm run lint`(디자인 토큰 감사) = **이미 42건 위반으로 exit 1 상태라 무력화됨** (about SVG 35건 + manual 1건 + 워크스페이스 인쇄템플릿 6건). 새 위반이 생겨도 구분 불가.
- `tsc --noEmit`(6.7초, 현재 0오류) = 해체 작업의 실질적 1차 방어선. 깨진 import/타입은 잡지만 "타입은 맞는데 화면이 깨지는" 손상은 전부 통과.
- pytest 레이아웃 회귀 35개(5.7초) = 다운로드 엑셀 산출물은 촘촘히 보호. 웹 화면과는 무관.

**보완책 (비용 순, 5번 착수 전 완료 권장)**:
1. [30분] 토큰 감사 42건을 수정 또는 ignore 등록으로 0건화 → 게이트 복구
2. [반나절] 이미 설치된 playwright(^1.61.0, 현재 미사용)로 35개 라우트 순회 스모크: 페이지 로드 → 콘솔 에러 0건 + 본문 비어있지 않음 + 전체 스크린샷 저장 → 해체 커밋마다 이전 스크린샷과 대조
3. [즉시] 해체 대상 화면별 수동 QA 체크리스트(핵심 인터랙션 2~3개)를 5번의 커밋 리듬에 포함 — **2026-07-20 확정, `Screen` 유니온 13개 전수**(⚠️ 워크스페이스 내부 화면 전환은 URL을 안 바꾸는 순수 in-memory state라 "필터→URL 반영"은 적용 안 됨 — 확인 항목은 대신 눈에 보이는 값/화면전환 자체로 검증):

   | 화면(`Screen`) | 체크리스트 |
   |---|---|
   | `prep` (데이터 준비) | ① 환율 "재조회" 클릭 시 값 갱신 ② 설정값 입력 후 "분석 시작" → `order`로 자동 이동 ③ 다른 화면 다녀온 뒤 재방문해도 입력값·환율 유지(재조회 안 됨) |
   | `diag` (데이터 진단) | ① 매핑 성공률 수치 표시 ② 미매핑 항목 목록 표시 |
   | `order` (발주분석) | ① 발주 필요 SKU 표 렌더 ② 엑셀 다운로드 클릭 시 가드(중복클릭 방지)+파일 저장 ③ 통합발주 큐에 담기 |
   | `gap` (재고공백) | ① 재고갭 표 렌더 ② 엑셀 다운로드 정상 동작(요약 밴드 스타일 포함) ③ 긴급 보충 필터 |
   | `season` (시즌캘린더) | ① 캘린더 히트맵 렌더 ② 월별 피크 강도 표시 |
   | `final` | ⚠️ 07-13 조사에서 진입 경로 전무로 확인됨(fallback 블록) — **QA 대상 아님, 5단계 착수 시 실제로 도달 불가 재확인 후 죽은 코드로 삭제 검토** |
   | `idata` (인사이트 데이터입력) | ① 기간(날짜범위) 설정 ② "분석 시작" → `country`로 자동 이동 |
   | `country` (국가분석) | ① 국가별 순위/지도 렌더 ② 보고서 카드에 담기 |
   | `brand` (브랜드분석) | ① 브랜드 순위 렌더 ② 보고서 카드에 담기 |
   | `sku` (SKU분석) | ① SKU 검색·선택 ② SKU 상세 카드 렌더 |
   | `ingredient` (성분분석) | ① 성분 트렌드 렌더 |
   | `cross` (교차분석) | ① 행/열 축 선택 ② 매트릭스 렌더(축 이름이 올바른지 — 07-20에 고친 회귀와 같은 종류의 버그 재발 감시) |
   | `report` (보고서) | ① 보고서 드로어 열기·블록 추가 ② PPT/HTML 내보내기 다운로드 |

---

## 발주분석탭 신규 커밋 리뷰 (2026-07-13 오후, 적대적 검증 통과분만)

**대상**: `bcddc69`(발주검토 엑셀 내보내기 — SheetJS 값 덤프 → exceljs 서식 워크북 전면 교체: B2 드롭다운으로 미입고 해소 전/후 시나리오를 엑셀 내부 수식으로 전환, 숨김 계산 시트, 통화·조건부서식, 상품코드/바코드 컬럼) + `cba8bc0`(재고갭 내보내기 동일 방식 교체 + mergeProductIdentity 최초유효값 누적으로 개선 + 인증 UI 표시 변경).

**확정 결함 7건** (후보 10건 중 3건은 검증에서 반증·기각됨):

| # | 심각도 | 결함 | 위치 |
|---|---|---|---|
| N1 | 중 | 대용량 내보내기 시 메인 스레드 프리즈 + 재클릭 가드 부재 — 브랜드 필터 "전체"면 분석 전체 SKU를 동기 처리, 같은 파일의 다른 내보내기 5곳은 전부 가드+finally 패턴이 있는데 이 경로만 누락 | 워크스페이스 :1786 (downloadOrderRowsXlsx), :2673/:2684 (핸들러) |
| N2 | 중 | scopeLabel 옵션이 전달만 되고 미사용 — "현재 필터"와 "선택 SKU" 내보내기 파일의 요약 밴드가 완전히 동일해 구분 불가 (미완성 기능) | 워크스페이스 :2078, 호출부 :3196/:3208 |
| N3 | 하 | 내보내기 실패 시 unhandled rejection — try/catch 없음, exceljs가 동적 import 청크(~940KB)라 오프라인/재배포 후 ChunkLoadError 시 아무 피드백 없이 침묵. :9700의 보고서 내보내기 try/catch 패턴을 그대로 적용하면 됨 | 워크스페이스 :2673-2692 |
| N4 | 하 | 발주검토 엑셀 메타 밴드(2~4행) L·M열 스타일 미적용 — exceljs `eachCell({includeEmpty})`는 그 행의 마지막 정의 셀까지만 순회. 밴드 오른쪽이 끊긴 채 항상 재현 | 워크스페이스 :1998-2030 |
| N5 | 하 | 재고갭 엑셀 요약 밴드 3행 J3~L3 동일 증상 (N4와 같은 메커니즘 — 공통 수정 가능) | 워크스페이스 :2186 |
| N6 | 하 | numberFormat의 `.replace(/\\"/g,'"')`는 항상 no-op인 잔재 코드 (1964·2003·2193행 3곳) — 이스케이프 규칙 오해 유발 | 워크스페이스 :2193 외 |
| N7 | 하 | `xlsx@0.18.5` 죽은 의존성 — cba8bc0가 마지막 사용처를 제거해 import 0건 확정(실은 감사 시점에도 이미 미사용). CVE 이슈는 패치가 아니라 **제거**로 해소 → 3b에 편입 | frontend/package.json:34 |

**기각 3건** (기록용): Safari blob revoke 타이밍(영향 브라우저가 6~10년 전 EOL + 기존 6개 경로와 동일 관행), 매퍼 SKU 키 불일치(백엔드 고정 스키마상 도달 불가 경로), null→"-" 문자열 셀(기존 동작과 실질 동일한 표시 차이).

---

## 실행 순서 (우선순위 순)

### ☑ 1. 다운로드 라우트 블로킹 제거 — **완료 (2026-07-13)**

- **문제**: `backend/routers/analysis.py:415-419`의 `async def download`가 `backend/services/storage.py:98-99`의 `time.sleep(0.25)` 폴링 루프를 이벤트 루프에서 직접 호출 → Excel 생성 지연 시 **서버 전체 요청이 최대 90초 정지**. 발견된 결함 중 유일하게 지금도 사용자 피해 중.
- **수정**: 폴링을 `await asyncio.sleep` 기반으로 바꾸거나 라우트 전체를 `run_in_threadpool`로 위임. 10줄 미만.
- **검증**: `py -3.14 -m pytest tests/ -q` (137 passed 기준선) **+ 실제 브라우저에서 엑셀 다운로드 1회** — pytest는 "엑셀을 만드는 함수"까지만 보고 HTTP로 내려주는 경로는 테스트 0건이라, 라우트가 깨져도 pytest는 녹색임.
- **주의**: "파일 생길 때까지 최대 90초 대기"라는 동작 자체는 유지. 대기 *방식*만 변경.

### ☑ 1.5 신규 엑셀 내보내기 마감 수정 (N1~N6) — **완료 (2026-07-13)**

- **왜 이 순번**: 오늘 작성된 코드라 맥락이 생생할 때 고치는 게 가장 싸고, 전부 발주분석탭 사용자가 직접 체감하는 결함. 5번 해체 전에 고쳐야 이 코드가 깨끗한 상태로 이동됨.
- N1+N3: `exportingReport`(:9700) 패턴 그대로 — 진행 상태 + 버튼 disabled + try/catch/finally. 근본 해결(Web Worker)은 과잉, 가드+로딩 표시로 충분.
- N4+N5: 스타일 패스를 `eachCell` 대신 고정 열 범위 루프(1~13열 / 1~12열)로 — 두 함수 공통 헬퍼로 추출하면 한 번에 수정.
- N2: scopeLabel을 요약 밴드에 실제 기록. N6: no-op replace 3곳 제거.
- **검증**: 발주검토·재고갭에서 "현재 필터"/"선택 SKU" 내보내기 각 1회 → 엑셀 열어 밴드 스타일·범위 표기 확인, B2 드롭다운 전환 동작 확인.

### ☑ 2. CI + ESLint 도입 — **완료 (2026-07-13)**

- **CI**: `.github/workflows/ci.yml` — backend(ubuntu, Python 3.14, pytest) + frontend(node 24, `npm ci` → `tsc --noEmit` → `eslint .` → `next build`) 2개 잡. push/PR to main에서 실행. ⚠️ ubuntu에서의 pip 설치·pytest는 첫 푸시 때 확인 필요(로컬은 Windows).
- **requirements-dev.txt** 신설: pytest==9.0.3.
- **ESLint**: eslint 9.39.5 + eslint-config-next@16.2.6, `eslint.config.mjs`(flat config 네이티브 — Next 16은 FlatCompat 불가). `npm run lint:js`. 기존 `lint`(토큰 감사)는 그대로.
- **도입 시점 기준선: 81건(오류 60+경고 21)** → 전부 `frontend/ESLINT_BACKLOG.md`에 규칙별·파일별로 기록. 자동 수정 안 함(계획 원칙). 위반이 존재하던 오류 규칙 5종(set-state-in-effect 41건 등)은 config에서 warn으로 강등해 게이트를 초록으로 시작 — 위반 0건인 `react-hooks/rules-of-hooks`는 error 유지되어 새 훅 규칙 위반은 즉시 차단됨.
- 백로그 해소는 5번 해체 때 화면 단위로 검토 권장.

### ◐ 3. 청소 (임시파일 + 죽은 코드) — **3a 완료 + 3b 부분완료 (2026-07-20)**

**3a. 작업 트리 파일 삭제** (전부 git 미추적 → 삭제 시 복구 불가, 실행 전 범위 확정 필요):
- 로그 78개 (루트 18 + ESM_SCM8/ 34 + frontend/ 26, 최대 `frontend-run.err.log` 9.2MB)
- `_tmp_sales_history.xls` 217MB + `_tmp_prod.xls` 94MB, `tmp_*.csv` 5개, `test_out*.xlsx`, 디버그 xlsx 4개
- `git gc` (loose object 10,604개 / 241MiB 방치 상태)
- **[결정 대기]** 백업 폴더 3개도 삭제할지: `ESM_SCM8_backup_before_uiux_data_20260623-120915/`(515MB), `_uiux_reference_*` 2개(64MB), `.git-backups/ESM_SCM8.git`. git 이력이 있으므로 이론상 불필요한 사본.

**3b. 죽은 코드 삭제 — 2026-07-13 전수 재검증 완료, 후보 전원 삭제 가능 확정**
(정적 import·배럴·dynamic import·next/dynamic·React.lazy·문자열 참조 전수 검색. 삭제 후 `tsc + next build`로 검증):
- `frontend/lib/mock-data.ts` (492줄) — 참조 0건 확정
- `frontend/components/season-trend/CountryInsightMap.tsx` (776줄) — 외부 참조 0건, 구 진입점은 이미 redirect로 퇴역
- ⚠️ **같은 커밋으로**: `d3-geo`, `topojson-client`, `world-atlas` + 고아가 되는 `@types/d3-geo`, `@types/topojson-client` — 패키지만 먼저 지우면 빌드가 깨짐
- `three`, `@types/three` (소스 참조 0건), **`xlsx@^0.18.5`** (2026-07-13 오후 확정: import 0건, CVE 이슈도 제거로 해소 — N7), ~~playwright~~ → **playwright는 삭제하지 말 것**: 보완책 2(라우트 스모크)에 활용 예정
- 워크스페이스 내부(참조 0건 또는 도달 불가 증명, 2026-07-13 오후 커밋 2개 반영 후에도 판정 유지 재확인됨. ⚠️ 라인 번호는 커밋마다 밀림 — 심볼명이 정본): `InsightInputScreenExact`(3590행)+전용 하위 `SourceDataRow`(3532행)·`InputDateBox`(3562행), `BrandSeasonBars`(5677행), 데모 `SeasonHeatmap`(9059행)+`CrossMatrix`(9098행)+`ExtraPanel`(9555-9560행)·"final" fallback 블록(10514-10539행 — "final" 화면으로의 진입 경로 전무 증명, 단 내부 `ReportBuilder`는 10513행에서 별도 렌더되므로 유지)
- ⚠️ **혼동 금지 — 이름이 비슷한 살아있는 코드** (절대 삭제 금지):
  - `InsightInputScreenExactV2`(3747행) — 10492행에서 실제 렌더되는 진짜 입력 화면 (+`SourceDataRowV2` 3690행, `InputDateBoxV2` 3719행)
  - `demandRange`/`demandYearRange`(333,342행) — V2가 공유 사용
  - `buildCrossMatrix`(7068행)·`CrossMatrixData`(6831행)·`crossMatrixData`(7183행) — CrossHeatmapCard가 실사용
  - `components/season-trend/SeasonHeatmap.tsx` — GlobalDemandTab·MappingCheckTab이 import하는 별개 파일
- ☑ **`OrderReviewTable.tsx`(1,077줄) — 2026-07-20 삭제 완료** (조사로 도달 불가 죽은 코드 확정 후 사용자 승인). 삭제: `OrderReviewTable.tsx` + `app/order-review/OrderReviewClient.tsx`. 정리: `OrderAnalysisClient.tsx`의 OrderReviewClient import 제거 + ActiveTabContent order-review fallback을 `return null`(주석: 이 shell은 sku-concentration에서만 마운트, 실 발주검토는 Workspace가 담당)로 교체, `ui-regression.test.mjs`의 obsolete 어서션 3개 제거. 검증: tsc 0오류 + npm test 통과 + next build 성공. **미해결 관찰(별건)**: OrderAnalysisClient의 order-review·stock-gap 분기 둘 다 실사용 라우트 없음 — 이 shell 자체가 절반 마이그레이션 잔재라 더 넓은 정리 여지 있음.

### ☑ 4. NEXT_PUBLIC 비밀번호 제거 — **완료 (2026-07-20)**

- **문제**: `.env.local`의 `NEXT_PUBLIC_DEMO_ADMIN_PASSWORD` → 브라우저 번들에 평문 포함. `lib/auth.ts:25-28`이 클라이언트에서 평문 비교, 세션은 localStorage `s2_auth` 플래그(만료 없음).
- **수정**: 백엔드 검증 엔드포인트 + 서버측 검증 쿠키로 이관. 로그인 화면(app/login/page.tsx) 외관은 그대로 유지 가능 — handleSubmit 내부 1줄이 fetch로 바뀌는 것.
- **검증된 영향 범위**: lib/auth를 import하는 파일은 정확히 3개(login/page.tsx, AuthGuard.tsx, LogoutButton.tsx). **분석·발주 화면 내부 UI 영향 0.**
- ⚠️ **구현 함정 4개 (2026-07-13 검증에서 발견)**:
  1. **credentials 함정**: dev는 :3000→:8002 교차 출처인데 현재 코드베이스 전체에 fetch `credentials` 옵션 0건. 쿠키 인증에는 CORS `allow-credentials` + `credentials:"include"` 필수 — 빠지면 "로그인 성공했는데 계속 /login으로 튕기는" 무한 루프 발생.
  2. **오류 메시지 분기**: 현재 로그인 오류 UI는 "아이디 또는 비밀번호가 올바르지 않습니다" 단일 메시지 — 서버 다운/네트워크 오류 분기를 추가하지 않으면 백엔드 장애가 비밀번호 오류로 오인 표시됨.
  3. **HttpOnly 쿠키면 AuthGuard 재작성**: 현행 `isLoggedIn()`은 동기 localStorage 조회. HttpOnly 쿠키는 JS가 못 읽으므로 가드가 비동기(`/auth/me` 류)로 바뀌어야 하고, 캐싱 없이는 페이지 이동마다 서버 확인 발생. PUBLIC_PATHS가 `["/login"]`뿐이라 랜딩·소개 페이지까지 전부 영향권.
  4. **데이터 API는 건드리지 말 것**: 이번 이관은 로그인 엔드포인트만. 데이터 API까지 쿠키를 요구하게 만들면 전 화면 fetch에 credentials가 없어서 401 전면 실패.
- **예상되는 체감 변화 (버그 아님, 공지 사항)**: 배포 시점에 전 직원 브라우저당 1회 재로그인. 서버 세션에 만료를 두면 "작업 중 세션 만료 → /login" 이벤트가 새로 생김(발주 검토 상태는 별도 localStorage라 데이터 유실은 없음).

**구현 (2026-07-20)**:
- 백엔드: `backend/services/auth.py`(인메모리 세션 store, 기존 `_JOBS`/`_memo` 패턴과 동일하게 lock+dict, DB 없음 — 재기동 시 전원 로그아웃은 감내), `backend/routers/auth.py`(`POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`), `backend/config.py`에 `ADMIN_ID`/`ADMIN_PASSWORD`(기본값 빈 문자열 — `.env` 미설정 시 로그인 항상 실패)/세션 쿠키 설정 추가. 비밀번호는 `backend/.env`(gitignore 대상, `python-dotenv`로 로드)에만 존재 — git에는 절대 안 들어감.
- CORS: `allow_credentials=False→True`. `allow_origins`가 명시적 목록(와일드카드 아님)이라 스펙과 충돌 없음 — 데이터 API는 여전히 credentials 없이 호출되므로 영향 없음(함정 ④ 확인됨).
- 프론트: `lib/auth.ts` 전면 교체(localStorage/DEMO_ADMIN 제거 → `verifyCredentialsRemote`/`checkSession`/`logoutRemote` + 탭당 1회 검증 캐시), `AuthGuard.tsx`(비동기 `checkSession`, 함정 ③ 해결), `login/page.tsx`(비동기 제출 + 자격증명 오류/네트워크 오류 메시지 분기, 함정 ②), `LogoutButton.tsx`(서버 로그아웃 호출), `.env.local`에서 `NEXT_PUBLIC_DEMO_ADMIN_*` 제거.
- 세션 만료: 기본 30일(`SCM_AUTH_SESSION_DAYS`로 조정 가능) — "무기한 로그인 유지"보다는 보안이 낫고, 매주 재로그인시키는 것보다는 체감 마찰이 적은 절충.
- **검증**: 백엔드 신규 테스트 `tests/test_auth.py` 7개 통과(오답 비밀번호, 빈 비밀번호, 쿠키 없는 me, 로그인→me, 로그아웃→me 재실패, ID 공백 trim, 위조 토큰 거부). curl로 실제 쿠키 왕복 확인(`Set-Cookie` 속성, `access-control-allow-credentials`/`allow-origin`이 특정 origin만 반영되고 허용 안 된 origin은 헤더 자체가 없음을 직접 확인 — 함정 ① CORS/쿠키 실증). Playwright로 실제 브라우저 종단 검증: 무세션→`/login` 리다이렉트, 로그인 성공→`/`, 인증 상태로 보호 라우트 정상 렌더(발주 컨텐츠 확인), 오답 비밀번호 시 정확한 한글 오류 메시지. tsc 0오류, `next build`/`npm test` 통과.
- **부수 발견**: 검증 중 `.venv`(Python 3.11.15)가 CI(3.14)와 다른 버전이며 `starlette` 1.3.1의 `TestClient`가 신규 `httpx2` 패키지를 요구함을 발견 — `requirements-dev.txt`에 `httpx2==2.7.0` 추가. 또한 전체 pytest 실행 중 `tests/test_report_export_masking.py` 6개가 이미 실패 중임을 발견(내 변경과 무관 — 두 파일 모두 diff 0, 마지막 수정 커밋은 07-13 이전 `b0a5277`/`dd5ae1b` "PowerPoint 렌더러 없이 HTML로 전환" 시점. PPTX 경로가 그 전환 이후 방치된 것으로 추정) — 백엔드 리포트 모듈 분해(제외 항목) 착수 시 함께 처리 필요.

### ☐ 5. SiliconAnalyticsWorkspace.tsx 해체 — [1~2주, 화면 단위 진행]

- **현황 (2026-07-20 재측정)**: **12,517줄** (07-13 10,562 → +1,955, 일주일간 리포트 기능 작업으로 계속 자람 — 방치 시 복리 증가 실증됨, 시급성 상승 중), 내부 컴포넌트 64개, useState 73, useEffect 45, useMemo 120, export 1개. ⚠️ **아래 라인 번호는 07-13 기준이라 ~2,000줄 밀림 — 심볼명이 정본, 착수 시 심볼로 재탐색할 것.**
- **2026-07-13 검증 결과: 픽셀-동일 분리 가능한 구조 확인** — 모듈 스코프 가변 상태 0(let/var 0, 싱글턴 캐시 0), 모듈 스코프 부수효과 0, createContext/useContext 0, 컴포넌트 전부 최상위 선언, 상태는 단일 루트(현재 10101행)에서 props로만 흐름. 외부 export는 1개뿐이고 app/ 13개 페이지가 같은 경로를 import하므로 진입 파일 경로·이름만 유지하면 라우팅 무변경.
- **분리 3조건 (위반 시 UI 깨짐)**:
  1. 분리 파일은 tailwind content 글롭(`./app`, `./components`, `./lib`) **안에** 둘 것 — 밖으로 나가면 해당 파일의 클래스가 purge되어 스타일 통째로 증발
  2. 공유 심볼 약 110개(YoY 창 로직 740-898행, `todayKst` 357행, titles/metrics/allNavItems, escapeReportHtml, useLoadingDots 등)는 **복제 금지, 단일 shared 모듈로 추출** — 특히 `todayKst`는 로드타임 평가값이라 파일별 복제 시 자정 넘김 불일치 가능
  3. YoY 헬퍼들(776-796행, 추가로 6405·7013행의 `const window = ...`)이 파라미터·지역변수 이름을 `window`로 써서 전역 window를 섀도잉 — **순수 텍스트 이동만** 할 것. ESLint autofix·IDE 자동 리네임·"미사용 import 정리" 개입 금지
- **선행 조건**: ① ~~미커밋 1줄 커밋~~ **충족됨**(CategorySelectPill 변경이 커밋에 포함, 워킹트리 클린), ② 2번 CI 가동, ③ **보완책 1~3 전부 완료(2026-07-20)** — 아래 참조, ④ 1.5(N1~N6) 수정 완료 — 결함 있는 코드를 그대로 옮기지 않기 위해. **→ 5단계 착수 가능 상태.**
  - 보완책 1(토큰 감사): 실제 위반 1건(`SiliconAnalyticsWorkspace.tsx:1307`의 `bg-[#151519]`, 다른 34건은 07-13 이후 이미 해소돼 있었음) — `--dropdown-panel` CSS 변수+`dropdownpanel` Tailwind 컬러 신설해 정식 토큰화(시각적 변화 0, 컴파일된 CSS로 확인). `npm run lint` 0건.
  - 보완책 2(playwright 스모크): `frontend/scripts/route-smoke.mjs` 신설(`npm run smoke`) — 로그인 후 라우트 35개 전수 순회, 콘솔에러·빈 본문 검사 + 전체 스크린샷을 `scripts/route-smoke-screenshots/`에 저장(gitignore 대상). `networkidle` 대기는 Next dev의 HMR 연결 때문에 SPA에서 자주 멈춰서 `domcontentloaded`+명시적 대기로 교체. 35/35 통과, baseline 스크린샷 생성 완료 — **5단계 커밋마다 재실행해 latest/와 baseline/을 육안 대조**.
  - 보완책 3(QA 체크리스트): 위 §"3. [즉시]" 참조, `Screen` 13개 전수 확정.
- **추출 1순위 후보 (신규)**: `downloadOrderRowsXlsx`(1786행)와 `downloadStockGapRowsXlsx`(2081행)는 구조가 거의 동일한 중복(요약 밴드, 스타일 패스, Blob 다운로드) — `redesign/lib/excel-export.ts`로 공통화하면 N4/N5 수정도 한 곳에서 유지됨.
- **방법**: `redesign/screens/` 화면 13개 + `redesign/shared/` 프리미티브 + `redesign/lib/`(순수 함수 → 분리 즉시 단위 테스트 가능). 목표 파일당 500줄 이하.
- **리듬**: 화면 1개 분리 → `tsc + build + npm test` + 해당 화면 스크린샷 대조 + QA 체크리스트 → 커밋. 반복. 코드는 **이동만, 수정 금지**.

#### 진행 상태 (2026-07-20 착수)

**완료 — 1단계: 공유 lib 선(先)추출** (화면 분리 전 필수 선행 작업. 아직 화면은 하나도 안 뗐음)

- **무엇을 뺐는지**: 전방참조가 없는 순수 로직/타입/설정 데이터만. `AnalysisPeriodBadge`/`AnalysisPeriodCaveat`(뒤쪽 `exchangeRateBasisLabel` 필요)와 전역검색 헬퍼 일부(`addGlobalSearchCandidate`/`buildGlobalSearchResults`, 뒤쪽 `validCrossLabel` 필요)는 **의도적으로 남김** — 그 의존 대상이 있는 화면(아마 `cross`)을 뗄 때 같이 처리.
- **새 파일 5개** (`frontend/components/redesign/lib/`, 총 1,042줄):
  - `types.ts`(102줄): `Screen`,`Mode`,`ComparisonBasis`,`NavItem`,`SharedAnalysisSettings`,`SharedAnalysisRuntime`,`Metric`,`TableRow`,`ReportBlock`류 5종,`GlobalSearch`류 3종,`ComparableYearWindow`
  - `report-card-snapshot.ts`(147줄): `REPORT_CARD_SNAPSHOT_ATTR`,`lastReportCardClickTarget`(⚠️ 모듈스코프 가변상태 — 07-13 "가변상태 0" 전제가 이제 깨져있음을 발견, 단일 모듈로만 존재하게 유지),`rememberReportCardClickTarget`,`captureReportCardHtmlSnapshot` 등
  - `workspace-format.ts`(176줄): `koreaDateString`,`todayKst`,`useLoadingDots`,`demandRange`/`demandYearRange`,`analysisPeriod*` 라벨류,`numberSetting`,`seasonOptionsFromSharedSettings` 등
  - `nav-config.ts`(368줄): `orderNav`~`allNavItems`,`corporationOptions`,`titles`/`metrics`/`rows`(화면별 데모 표시값 테이블),`modeOf`,`DEFAULT_SHARED_ANALYSIS_SETTINGS`
  - `yoy-comparison.ts`(249줄): YoY/MoM 비교창 로직 전체(`comparableYearWindow`~`comparisonPeriodLabel`). `window` 파라미터명이 전역 `window`를 섀도잉하는 지점 5곳 — 순수 텍스트 이동만 함, 리네임 안 함(계획서 트랩 ③ 그대로 준수)
- **메인 파일**: 12,547→**11,623줄**(-924줄). 위 심볼들을 import로 교체.
- **검증**: `tsc --noEmit` 0오류 · `next build` 성공(전 라우트) · `npm run lint`(토큰감사) 0건 · `npm test` 7개 스크립트 전부 통과(단, `ui-regression.test.mjs`가 `SiliconAnalyticsWorkspace.tsx`에서 `excludePartialMonths: false` 문자열을 grep하던 게 이동으로 깨짐 → 파일 경로를 `lib/workspace-format.ts`로 갱신해서 고침, 코드 자체는 무변경) · `npm run smoke` 35/35 통과, 콘솔에러 0 · 스크린샷 baseline/latest 육안 대조(가장 큰 차이 난 `sku-concentration`은 세션 중 실제 분석이 한 번 실행된 상태 차이였을 뿐 코드 회귀 아님 확인, 그 외 페이지는 픽셀 동일).
- **알려진 이슈**: 없음(전부 그린).
- **남은 것**:
  - 화면 13개 전부 아직 메인 파일 안에 있음(다음 단계)
  - 전방참조 있는 항목 2건: `AnalysisPeriodBadge`/`Caveat`(→`exchangeRateBasisLabel` 위치 확인 후 같이 이동), 전역검색 헬퍼(→`validCrossLabel` 위치 확인 후 같이 이동)
  - `add_slide_header`류처럼(백엔드에서 발견한 것과 같은 패턴) 프론트에도 중복 정의가 더 있을 가능성 — 화면별 추출 중 발견되면 그때 처리
  - **다음 담당자 시작 명령**: `git log -1 --stat`로 이 커밋 확인 → `redesign/lib/` 5개 파일과 위 심볼 목록을 참고해 다음 화면(예: `diag`, 가장 작고 독립적)부터 `redesign/screens/`로 추출 시작

**완료 — 2단계: `diag`(데이터 진단) 화면 추출** (13개 중 1번째, props 없이 완전 자기완결형이라 첫 화면으로 선택)

- **무엇을 뺐는지**: `DiagnosticsScreenExact` 및 전용 헬퍼 전부(`DiagnosticMetricCard`,`SelectPill`,`CategorySelectPill`,`diagnostic*` 함수군,`buildDiagnosticCorrectionRows`,`buildDiagnosticRegionRows`,`DiagnosticDraftCorrection`형,`DIAGNOSTIC_UNMAPPED`) — 이 화면 밖에서 참조하는 곳 0건 확인 후 통째로 이동.
- **새 파일**: `frontend/components/redesign/screens/diag/DiagnosticsScreenExact.tsx`(432줄). `export function DiagnosticsScreenExact()` — props 없음(자체 useState/useEffect로 CMS 시즌·성분 분석 결과와 카테고리 보정 옵션을 직접 fetch).
- **메인 파일**: 11,623→**11,220줄**(-403줄). `import { DiagnosticsScreenExact } from "./screens/diag/DiagnosticsScreenExact"` 추가, 렌더 호출부(`<DiagnosticsScreenExact />`)는 무변경.
- **검증**: tsc 0오류 · build 성공 · 토큰감사 0건 · test 7개 전부 통과(이번엔 파일 경로 갱신 불필요, 이 화면 관련 grep 어서션 없었음) · smoke 35/35 콘솔에러 0 · `/mapping-check`(`diag` 렌더 경로) 스크린샷 baseline/latest **픽셀 동일** 확인(분류필요 SKU 1·성분미매칭 344·권역확인 0·성분태깅 195 전부 동일) · QA 체크리스트(매핑 성공률/미매핑 항목 표시) 충족.
- **알려진 이슈**: 없음. (참고: `analysisOptions`/`setAnalysisOptions` state가 원본부터 미사용이었음 — 이동만 했고 손대지 않음.)
- **남은 것**: 화면 12개(`prep`,`order`,`gap`,`season`,`final`,`idata`,`country`,`brand`,`sku`,`ingredient`,`cross`,`report`). `final`은 도달 불가 확인됨(위 QA 표 참조) — 추출 대상에서 제외하고 삭제 검토로 이동 가능.
- **다음 담당자 시작 명령**: `diag`와 같은 패턴(전용 헬퍼 범위 확인 → 새 폴더에 이동 → import 교체 → tsc/build/test/smoke → 스크린샷대조 → 커밋)으로 다음 화면 진행. 추천 순서: `gap`(재고공백, props 적음) → `season` → 나머지. `cross`를 뗄 때 `validCrossLabel`/전역검색 헬퍼, `country`류를 뗄 때 `exchangeRateBasisLabel`/`AnalysisPeriodBadge`도 같이 이동(1단계에서 보류해둔 전방참조 2건).

**완료 — 3단계: 공유 UI 프리미티브 5개 + `gap`(재고공백) 화면 추출** (13개 중 2번째 화면. `gap`은 `order`와 헬퍼 5개를 공유해서, 화면 자체보다 먼저 그 공유분을 shared/로 빼야 했음 — diag처럼 깔끔하게 안 끝남)

- **부수 발견**: `gap`은 `diag`처럼 자기완결형이 아니었음. `AnalysisStartRequiredState`/`InsightAnalysisRequiredState`/`OrderMetricCard`/`StatusPill`/`OrderSubTabs` 5개가 `order`(그리고 `OrderMetricCard`는 `country`까지) 화면과 공유돼 있었고, `gap`의 실제 소스 코드도 파일 안에서 `order` 관련 코드와 **비연속으로 섞여** 있었음(청크 3개로 흩어져 있어서 각각 따로 찾아 옮겨야 했음).
- **새 파일 6개**:
  - `redesign/shared/`(4개, 137줄): `AnalysisRequiredState.tsx`(`AnalysisStartRequiredState`+`InsightAnalysisRequiredState`), `OrderMetricCard.tsx`, `StatusPill.tsx`, `OrderSubTabs.tsx`
  - `redesign/screens/gap/GapScreenExact.tsx`(763줄): `GapScreenExact` + 전용 타입/헬퍼(`StockGapExportColumn`,`stockGapExportColumns`,`StockGapExportOptions`,`downloadStockGapRowsXlsx`,`GapSortKey`,`GapTableColumnKey`,`gapTableColumns`,`sortableGapColumns`,`gapSortLabels`,`dateSortValue`,`stockGapSortValue`,`compareStockGapRows`,`stockGapReason`) + `SortDirection`(트리비얼 타입이라 판단상 의도적으로 복제, 위험 없음)
- **⚠️ 임시 조치(다음 담당자가 반드시 알아야 함)**: `BrandSearchSelect`,`resolveFullOrderReviewDownload`,`isVisibleAnalysisBrandOption` 3개는 `order`와도 공유되는데 아직 `order`를 안 뗐어서 **`redesign/shared/`로 완전히 옮기지 않고, 메인 파일에 `export`만 붙여서 gap 파일이 상대경로로 import**하게 해뒀음(`import { BrandSearchSelect, ... } from "../../SiliconAnalyticsWorkspace"`). 반대 방향으로도 하나 있음: `StockGapComputed` 타입과 `stockGapShortageQty` 함수는 `report`(`ReportBuilder`) 화면도 써서, gap 파일에서 `export`하고 메인 파일이 gap 파일에서 import함. **`order`를 뗄 때 이 3개를 `redesign/shared/`로 정식 이동하고 gap 파일의 import 경로를 갱신할 것.**
- **메인 파일**: 11,220→**10,359줄**(-861줄). `import { GapScreenExact, stockGapShortageQty } from "./screens/gap/GapScreenExact"` + `import type { StockGapComputed } from "./screens/gap/GapScreenExact"` 추가.
- **검증**: tsc 0오류 · build 성공 · 토큰감사 0건 · test 7개 통과(이번에도 파일경로 갱신 1건 필요 — `order-analysis-data-integrity.test.mjs`가 `calculateStockGapShortageQty(item)` 문자열을 메인파일에서 찾다 깨짐 → `gap/GapScreenExact.tsx`도 같이 읽도록 고침) · smoke 1차 34/35(`/order-analysis/order-review`에서 "Failed to fetch" — gap과 무관한 화면, 스모크 스크립트의 네비게이션 타이밍 플레이크로 이미 알려진 종류) → **2차 재실행 35/35로 플레이크임을 확증** · `/order-analysis/stock-gap` 스크린샷 baseline/latest **픽셀 동일**(분석 미실행 게이트 화면까지 정확히 일치).
- **알려진 이슈**: 없음. 단 위 "임시 조치" 항목은 `order` 추출 전까지 남는 부채로 기록.
- **남은 것**: 화면 11개(`prep`,`order`,`season`,`idata`,`country`,`brand`,`sku`,`ingredient`,`cross`,`report` — `final`은 제외).
- **다음 담당자 시작 명령**: `order`를 다음으로 추천(위 3개 임시조치 심볼을 정식으로 `redesign/shared/`에 옮길 좋은 기회). 이후 `season`→나머지. `cross`/`country` 뗄 때 1단계에서 보류한 전방참조 2건(`validCrossLabel`, `exchangeRateBasisLabel`/`AnalysisPeriodBadge`) 처리.

**완료 — 4단계: `order`(발주 분석) 화면 + 임시조치 3개 심볼 정식 이동** (13개 중 3번째 화면. `gap` 단계에서 남겨둔 부채를 해소하는 단계)

- **무엇을 뺐는지**: `OrderScreenExact` + 전용 헬퍼 전부(`InboundScenario`/`OrderSortKey`/`SortDirection`/`OrderTableColumnKey` 타입, `orderTableColumns`/`sortableOrderColumns`/`orderSortLabels`, `orderMoi`/`formatMoiDisplay`/`adjustedOrderQty`/`displayedInboundQty`/`scenarioStockQty`/`orderUnitAmount`/`adjustedOrderAmount`/`meaningfulOrderText`/`compactKrw`, `OrderExportColumn`/`orderExportColumns`/`downloadOrderRowsXlsx`, `orderStatus`/`orderReason`/`orderReasonDisplay`/`orderSortValue`/`compareOrderRows`/`productDisplayName`) — 전부 order 스코프 밖 참조 0건 확인 후 이동. 추가로 `gap` 단계에서 메인 파일에 임시 `export`로 남겨뒀던 3개(`BrandSearchSelect`,`resolveFullOrderReviewDownload`,`isVisibleAnalysisBrandOption`)도 이번에 `redesign/shared/`로 정식 이동.
- **새 파일 3개**:
  - `redesign/shared/BrandSearchSelect.tsx`(140줄): `BrandSearchSelect` — `order`뿐 아니라 아직 메인 파일에 남아있는 `sku`/`brand`/`cross`/`report` 화면도 이 컴포넌트를 직접 참조 중이라, 폭넓게 공유되는 시점에서 바로 최종 위치로 이동(추가 임시조치 불필요).
  - `redesign/shared/order-review-shared.ts`(24줄): `resolveFullOrderReviewDownload`(async), `isVisibleAnalysisBrandOption` — `order`와 `gap` 둘만 공유하는 순수 로직.
  - `redesign/screens/order/OrderScreenExact.tsx`(1,036줄): `OrderScreenExact` + 위 전용 헬퍼 전부.
- **기존 파일 갱신**: `GapScreenExact.tsx`의 임시 상대경로 import(`from "../../SiliconAnalyticsWorkspace"`)를 새 shared 경로 2곳(`../../shared/BrandSearchSelect`, `../../shared/order-review-shared`)으로 교체 — gap 단계에서 기록해둔 부채 해소 완료.
- **메인 파일**: 10,359→**9,182줄**(-1,177줄. 3개 블록 총 1,174줄 삭제 + import 2줄 추가 + 중복 빈 줄 정리 -3줄). `import { OrderScreenExact } from "./screens/order/OrderScreenExact";` + `import { BrandSearchSelect } from "./shared/BrandSearchSelect";` 추가, 렌더 호출부(`<OrderScreenExact .../>`)는 무변경.
- **검증**: `tsc --noEmit` 0오류 · `next build` 성공(전 37라우트) · `npm run lint`(토큰감사) 0건 · `npm test` 7개 스크립트 전부 통과(`order-analysis-data-integrity.test.mjs`가 `resolveFullOrderReviewDownload`/`getOrderReviewRows`/`errorStyle: "stop"`/`전체 ESM_order 다중 시트 파일` grep 대상을 `OrderScreenExact.tsx`·`order-review-shared.ts`로 갱신해서 통과, 코드 자체는 무변경). 이동 코드는 원본 소스를 바이트 단위로 그대로 옮김(원본에 섞여있던 JS 유니코드 이스케이프 표기 `\uXXXX`도 그대로 보존 — 재입력하지 않고 sed로 원본 라인을 그대로 추출).
- **당시 미실행 검증(후속 단계에서 해소)**: order 추출 커밋 당시 `npm run smoke`는 토큰 예산 때문에 미실행이었다. 바로 다음 season 단계 착수 전에 실행했고, 이후 season·idata 단계에서 모두 **35/35 통과·콘솔 오류 0**을 재확인했다.
- **당시 남은 화면**: `season`, `idata`, `country`, `brand`, `sku`, `ingredient`, `cross`, `report`, `prep`(`final`은 도달 불가라 제외).
- **후속 주의사항**: `cross`/`country` 추출 때 전방참조(`validCrossLabel`, 당시의 `exchangeRateBasisLabel`/기간 배지)를 함께 처리해야 했다. 환율·기간 배지 의존성은 아래 season 단계에서 해소됨.

#### 완료 — 5단계: `season`(시즌 캘린더) 화면 추출 (13개 중 5번째 화면)

- **무엇을 뺐는지**: `SeasonCalendarScreenExact`와 전용 보조 컴포넌트 `SeasonMetricCard`, `SeasonDemandCell`을 화면 파일로 이동.
- **공유 부채 해소**: 이전 단계에서 전방참조 때문에 보류했던 `AnalysisPeriodBadge`/`AnalysisPeriodCaveat`를 `redesign/shared/AnalysisPeriod.tsx`로 이동. `wonEok`, `krwEokFromEur`, `exchangeRateText`, `exchangeRateBasisLabel`은 `redesign/lib/currency-format.ts`로 단일화해 기존 brand/sku/country/cross 화면과 신규 season 화면이 같은 구현을 사용하도록 정리.
- **새 파일 3개**: `redesign/screens/season/SeasonCalendarScreenExact.tsx`(473줄), `redesign/shared/AnalysisPeriod.tsx`, `redesign/lib/currency-format.ts`.
- **메인 파일**: 9,182→**8,638줄**(-544줄). 화면 import만 추가하고 렌더 props(`reportBlocks`, `onToggleReportBlock`)는 그대로 유지.
- **스모크 안정화**: 로그인 직후 React hydration 전에 입력값만 채워져 인증 state가 비는 Playwright 레이스를 수정. `route-smoke.mjs`가 hydration 대기 후 로그인하고, 첫 루트 전환은 `domcontentloaded` 기준으로 기다리도록 보완.
- **검증**: `npm run typecheck` 0오류 · `npm run lint` 통과 · `npm test` 7개 스크립트 전체 통과(시즌 캘린더 회귀 30 assertions 포함) · `next build` 37라우트 성공 · `npm run smoke` **35/35 통과, 콘솔 오류 0**.

#### 완료 — 5단계: `idata`(인사이트 데이터입력) 화면 추출 (13개 중 6번째 화면)

- **무엇을 뺐는지**: 실제 렌더에 연결된 `InsightInputScreenExactV2`와 전용 `SourceDataRowV2`, `InputDateBoxV2`를 `redesign/screens/idata/InsightInputScreenExact.tsx`로 이동하고 표준 이름으로 정리.
- **죽은 코드 제거**: 어느 라우트에서도 쓰이지 않던 V1 화면과 보조 컴포넌트 `SourceDataRow`, `InputReadBox`, `InputDateBox`를 함께 삭제. 기존 분석 실행 API(`analyzeSeasonTrendFromApi`, `clearSeasonTrendResult`, `saveSeasonTrendResult`)는 이 화면 전용임을 확인해 정확히 함께 이동.
- **새 파일**: `redesign/screens/idata/InsightInputScreenExact.tsx`(280줄).
- **메인 파일**: 8,638→**8,207줄**(-431줄). 루트는 완료·무효화·화면이동 콜백과 `analysisSettings`를 동일 props로 전달.
- **검증**: `npm run typecheck` 0오류 · `npm run lint` 통과 · `npm test` 7개 스크립트 전체 통과 · `next build` 37라우트 성공 · `npm run smoke` **35/35 통과, 콘솔 오류 0**.

#### 완료 — 5단계: `sku`(SKU 분석) 화면 추출 (13개 중 7번째 화면)

- **무엇을 뺐는지**: `SkuScreenExact`와 전용 `SkuChoiceCard`, `SkuSearchSelect`을 `redesign/screens/sku/SkuScreenExact.tsx`로 이동.
- **공유 컴포넌트 정리**: SKU·브랜드·국가가 함께 쓰는 `BrandBar`/ `SkuNameWithCode`를 `redesign/shared/BrandBar.tsx`로, SKU·브랜드의 보고서 카드 추가 버튼을 `redesign/shared/ReportCardAddButton.tsx`로 분리. 브랜드 전용 보조 컴포넌트는 메인에 보존해 화면 경계를 유지.
- **회귀 테스트 갱신**: `ui-regression.test.mjs`가 메인 파일만 읽던 SKU 카드 검증을 새 SKU 화면 파일도 읽도록 변경해, 이후 파일 이동으로 인한 거짓 실패를 방지.
- **메인 파일**: 8,207→**7,402줄**(-805줄).
- **검증**: `npm run typecheck` 0오류 · `npm run lint` 통과 · `npm test` 7개 스크립트 전체 통과 · `next build` 37라우트 성공 · `npm run smoke` **35/35 통과, 콘솔 오류 0**.

#### 완료 — 5단계: `ingredient`(성분 분석) 화면 추출 (13개 중 8번째 화면)

- **무엇을 뺐는지**: `IngredientScreenExact`와 성분 전용 조회·순위·표시 보조 로직을 `redesign/screens/ingredient/IngredientScreenExact.tsx`로 이동.
- **공유 로직 정리**: 성분 화면과 교차분석 화면이 모두 쓰는 데이터 범위 안내·커버리지 계산을 `redesign/shared/ingredient-analysis.ts`로 분리. 산식별 화면 구현은 공유하지 않고, 단순 집계·표시 원칙만 단일화했다.
- **메인 파일**: SKU 단계의 7,402줄에서 성분 화면 이동 후 약 6,800줄대로 축소.
- **검증**: `npm run typecheck` 0오류 · `npm run lint` 통과 · `npm test` 7개 스크립트 전체 통과. 뒤이은 교차분석 단계의 build·전 라우트 smoke에서 함께 재검증.

#### 완료 — 5단계: `cross`(교차분석) 화면 추출 (13개 중 9번째 화면)

- **무엇을 뺐는지**: `CrossAnalysisScreenExact`와 탭·세그먼트·히트맵 셀·매트릭스 보조 컴포넌트 및 YoY/MoM 월 선택·PDF 내보내기 로직을 `redesign/screens/cross/CrossAnalysisScreenExact.tsx`로 이동.
- **전방참조·공유 유틸 해소**: 전역검색이 참조하던 `validCrossLabel`을 `redesign/lib/cross-label.ts`로, 브랜드·국가·교차 보고서 출력이 함께 쓰는 HTML 이스케이프를 `redesign/lib/report-html.ts`로 분리해 루트 파일과 화면 파일의 순환 의존을 만들지 않았다.
- **회귀 테스트 갱신**: `ui-regression.test.mjs`의 교차분석 정적 검증 5개를 새 화면 파일 경로로 이동. 기능 검증 자체는 유지해 단순 파일 이동으로 테스트가 무력화되지 않게 했다.
- **메인 파일**: 약 6,800줄대→**5,684줄**(-약 1,140줄). 루트는 화면 import와 렌더 연결만 담당한다.
- **검증**: `npm run typecheck` 0오류 · `npm run lint` 통과 · `npm test` 7개 스크립트 전체 통과(교차 매트릭스 8,988 케이스 포함) · `next build` 37라우트 성공 · `npm run smoke` **35/35 통과, 콘솔 오류 0**. 첫 실행의 `/insight/brand` 1건 `ERR_ABORTED`는 개발 서버 이동 타이밍 플래이크였고, 즉시 재실행에서 전 라우트 통과로 코드 회귀가 아님을 확인.

#### 완료 — 5단계: `country`(국가 분석) 화면 추출 (13개 중 10번째 화면)

- **무엇을 뺐는지**: 국가별 매출·권역 점유·성장(MoM/YoY)·상위 SKU·국가 시즌성·국가 PDF 내보내기까지 포함한 `CountryScreenExact`를 `redesign/screens/country/CountryScreenExact.tsx`로 이동.
- **화면 경계 정리**: 국가 화면에만 쓰이던 `ShareCard`/`CountryRankRow`도 함께 이동. 브랜드와 국가가 공통으로 쓰는 성장률 숫자 판정은 `redesign/lib/growth-display.ts`로 분리해 다음 브랜드 추출에서도 같은 구현을 재사용하도록 했다.
- **회귀 테스트 갱신**: 국가 성장 기준월·자동 비교월·월 완결성 검증 4개를 새 화면 파일을 대상으로 변경해, 경로 이동으로 테스트가 약해지지 않게 유지.
- **메인 파일**: 5,684→**4,018줄**(-1,666줄). 사용하지 않는 데모 컴포넌트는 이번 화면 이동 범위에 섞지 않고 별도 죽은 코드 정리 대상으로 보존했다.
- **검증**: `npm run typecheck` 0오류 · `npm run lint` 통과 · `npm test` 7개 스크립트 전체 통과 · `next build` 37라우트 성공 · `npm run smoke` **35/35 통과, 콘솔 오류 0**.

#### 완료 — 5단계: `brand`(브랜드 분석) 화면 추출 (13개 중 11번째 화면)

- **무엇을 뺐는지**: 브랜드 매출·성장(MoM/YoY)·SKU 집중도·월별 추이·브랜드 PDF 내보내기를 담당하는 `BrandScreenExact`와 전용 SKU 선택·브랜드 순위 컴포넌트를 `redesign/screens/brand/BrandScreenExact.tsx`로 이동.
- **회귀 테스트 갱신**: 브랜드 PDF 기준일, 성장 비교월, 시즌성 차트, 성장 보고서 등 정적 검증을 새 화면 경계로 이전했다.
- **검증**: `npm run typecheck` 0오류 · `npm run lint` 통과 · `npm test` 전체 통과 · `next build` 37라우트 성공 · `npm run smoke` **35/35 통과, 콘솔 오류 0**.

#### 완료 — 5단계: `report`(보고서 빌더) 화면 추출 (13개 중 12번째 화면)

- **무엇을 뺐는지**: 보고서 카드 선택·정렬·미리보기·내보내기 UI를 담당하는 `ReportBuilder`를 `redesign/screens/report/ReportBuilder.tsx`로 이동. 화면 내부 상태와 보고서 전용 보조 렌더링을 화면 경계 안에 보존했다.
- **메인 파일**: `SiliconAnalyticsWorkspace.tsx`에서 보고서 구현 블록을 제거하고, 화면 import와 기존 `<ReportBuilder />` 렌더 연결만 유지.
- **검증**: `npm run typecheck` 0오류 · `npm run lint` 통과 · `npm test` 7개 스크립트 전체 통과 · `next build` 37라우트 성공 · 최신 `npm run smoke` **35/35 통과, 콘솔 오류 0**.

#### 완료 — 5단계: `prep`(데이터 준비) 화면 추출 (13개 중 13번째 화면)

- **무엇을 뺐는지**: 분석 기준값 입력·환율 재조회·분석 실행 UI를 담당하는 `PrepScreenExact`를 `redesign/screens/prep/PrepScreenExact.tsx`로 이동. 전용 입력 컴포넌트 `FieldBox`와, 새로고침 뒤 마지막 분석 결과를 안전하게 복원하는 `buildRecoveredOrderAnalysisResult`도 화면 파일로 함께 이동했다.
- **상태 경계**: 이미 루트로 승격된 `analysisDate`·환율 런타임 상태와 공통 분석 설정은 props로만 받아, 화면 전환 시 환율 재조회·사용자 입력 상태가 달라지지 않는 기존 동작을 유지했다.
- **메인 파일**: 데이터 준비 구현 블록을 제거했다. 루트는 환율/공통 설정 상태, 분석 결과 복구 콜백, 화면 이동 콜백만 소유한다.
- **검증**: `npm run typecheck` 0오류 · `npm run lint` 통과 · `npm test` 7개 스크립트 전체 통과 · `next build` 37라우트 성공 · 최신 `npm run smoke` **35/35 통과, 콘솔 오류 0**.

- **5단계 화면 추출 완료**: 도달 불가로 확인된 `final` fallback을 제외한 실사용 화면 12개(`diag`, `gap`, `order`, `season`, `idata`, `sku`, `ingredient`, `cross`, `country`, `brand`, `report`, `prep`)의 분리를 완료했다.

---

## 신규 발주 로직(BETA) 병렬 개발 설계 (2026-07-20 확정)

> 5단계(워크스페이스 해체)와 신규 화면("신규 발주 로직 BETA", 좌측 발주·QUANTITATIVE 섹션에 데이터준비·발주분석과 나란히 배치) 개발을 병렬로 진행하기 위한 설계. 실제 코드 조사(2개 Explore 에이전트) 기반으로 도출, 여러 라운드 교차검증 완료. **신규 산식 자체(가중치·예외규칙·MOQ)는 아직 미정 — 착수 전 사용자가 실제 계산 규칙을 확정해야 함.**

### 소유권 원칙

| 데이터 | 정본 | 비고 |
|---|---|---|
| 편집 중인 공통 설정(6필드: 목표재고월수2+리드타임4) | 프론트 독립 store(`analysisSettings` 패턴 확장) | 백엔드 정본 불필요 — 인증이 단일 공용 계정이라 "사용자별 저장"이 성립 안 함 |
| **실행에 쓰인 설정** | **각 백엔드 job의 불변 스냅샷**(`AnalyzeResponse.settings`처럼 에코백) | 프론트 store가 정본이 아님 — 나중에 store 값이 바뀌어도 과거 결과엔 그 당시 값이 남아야 함 |
| CMS 원본 | 백엔드 `cms_fetch_cache`(기존) | `(as_of,date_from,date_to,logistics_date_from)` 키로 이미 dedup — 신규 로직이 같은 파라미터로 요청하면 캐시 자동 재사용 |
| 정규화된 공통 입력 | 백엔드 `cms_mapping.py`의 6키 매핑까지만 공유(`eu_stock`/`hq_eu_stock`/`sales_detail`/`hq_to_eu_sales_detail`/`shipping`/`open_po`). 프론트는 `mappers.ts`의 저수준 헬퍼(`cleanSku`/`readNumber`/`pick`)만 공유, 상위 함수(`orderReviewRowFromTable` 등)는 legacy 결과 전용이라 공유 대상 아님 | "무리한 공통화 금지" 원칙 — 결측값 판정(기계적)은 공유, 결측값 대응(산식별로 다름)은 비공유 |
| 기존/신규 결과 | **완전히 분리된 `job_id`** (legacy 것 안 건드림, 신규는 새 job store+새 결과 캐시 키) | 신규 산식 실패가 기존 결과를 덮어쓰면 안 됨. `CURRENT_ANALYSIS_JOB_STORAGE_KEY` 재사용 금지 |
| 실행 이력 영구 저장 | **당장 안 만듦** — 기존 `cms_analysis_jobs.py` 패턴(요청시 settings를 job_id에 매달아 저장, in-memory) 재사용으로 BETA엔 충분. 기존 발주분석도 이 수준의 보장만 갖고 있어서 신규만 더 견고하게 만들 근거 없음 | 과잉설계 방지 |

### 타입 계약 (구현 전 확정, 코드 위치는 개발 시작 전에 합의)

```ts
// 사용자가 직접 입력
type SharedAnalysisSettings = { localTargetMonths; transportTargetMonths; leadTimeSea; leadTimeAir; leadTimeRail; leadTimeTruck };
// 자동 계산/조회됨 — 워크스페이스 루트 소유, 화면 전환으로 재조회 안 됨
type SharedAnalysisRuntime = { analysisDate: string; exchangeRate: ExchangeRateResponse | null };
// 신규 산식 전용 — 아직 미정, 사용자 결정 필요
type NewOrderLogicSettings = { /* 가중치·예외규칙·MOQ 등 */ };
```
신규 화면(`NewOrderLogicScreen`)은 `sharedSettings`/`analysisDate`/`exchangeRate`를 props로만 받고, `SiliconAnalyticsWorkspace.tsx`의 상태를 직접 import/참조하지 않음. 신규 산식도 `calculateNewOrderLogic({ cmsRows, sharedSettings, logicSettings })` 형태로 설정을 인자로만 받음(암묵적 전역 의존 금지).

### 환율/날짜 정책

- 워크스페이스 최초 마운트 시 자동 조회 1회, 데이터 준비 탭 재방문으로 재조회 안 함(기존 재조회 버튼으로만 수동 갱신)
- 분석 실행 직전 암묵적 재조회 금지 — 화면에 표시된 값을 그대로 스냅샷해서 요청에 사용(이미 기존 동작과 일치, 새 동작 아님)
- job 결과에 실제 사용한 환율·환율 기준일·분석 기준일 보존

### 병렬 작업 매트릭스

| 작업 | 시점 | 비고 |
|---|---|---|
| `core/new_order_logic.py` 순수 함수+테스트, `lib/new-order-logic/*`, `backend/routers/new_order_logic.py`, `backend/services/new_order_logic/*`, `redesign/screens/new-order-logic/*` | **즉시 병렬 가능** | 전부 신규 파일, 5단계와 파일 안 겹침. 신규 기능의 70~75% 추정 |
| `analysisDate`/`exchangeRate`를 `PrepScreenExact`에서 루트로 추출 | **선행 작업, 5단계 담당자만** | 신규 탭 담당자는 이 파일을 직접 안 건드림. **2026-07-20 완료** (아래 진행 기록) |
| 워크스페이스에 `Screen` 유니온 멤버 + nav 배열 항목 + 1줄 `case` 연결 | **신규 탭이 5단계 완료 전에 실사용돼야 할 때만, 5단계 담당자가 수행** | 5단계 화면 추출 리듬과 겹칠 수 있어 타이밍 조율 필요. 임시 연결이면 별도 커밋으로 남기고 5단계 분리 대상에 포함 |
| 공통 설정 store를 `analysisSettings`에서 독립 모듈로 완전히 빼내는 것 | **5단계 착수 시점에 맞춰서만** | 지금 당기면 5단계와 충돌 위험 큼 |

### 실행 순서

1. 공통 설정 8필드 타입/검증 스키마 확정(`SharedAnalysisSettings`+`SharedAnalysisRuntime`)
2. 신규 로직 전용 설정 타입 확정(**사용자가 실제 규칙 제공해야 진행 가능**)
3. 신규 산식 입력/출력 계약 확정
4. 신규 산식을 순수 함수로 구현 + 고정 fixture 단위테스트
5. 신규 백엔드 job API(별도 `job_id`) + 실행결과에 `settings_snapshot` 포함
6. 신규 화면을 props 기반 독립 컴포넌트로 구현
7. (5단계 담당자) 공통 설정을 독립 store로 추출, 기존 발주분석·신규 화면 둘 다 연결
8. (5단계 담당자) 최종 내비게이션에 신규 메뉴 등록
9. 통합 테스트: 두 분석의 job_id·캐시·결과가 독립적인지 확인

### 진행 기록

| 날짜 | 항목 | 내용 |
|---|---|---|
| 2026-07-20 | **선행 작업 완료** | `analysisDate`(useMemo)와 `exchangeRate`/`exchangeRateError`/`refreshingExchangeRate`/`refreshExchangeRate`를 `PrepScreenExact`(지역)에서 `SiliconAnalyticsWorkspace` 루트로 이동. `SharedAnalysisRuntime` 타입 신설. `PrepScreenExact`는 이제 이 값들을 props로만 받음(`onRefreshExchangeRate` 콜백 포함). Context 미도입, 기존 `analysisSettings`와 동일한 "루트 상태+props" 패턴 유지. 검증: tsc 0오류, `next build`/`npm test` 통과, Playwright 실브라우저로 (a) 최초 마운트 시 환율조회 1회(dev StrictMode로 표시상 2회지만 동일 이펙트가 이전에도 있던 dev-only 현상, 프로덕션엔 영향 없음 확인) (b) 데이터준비→다른화면→데이터준비 왕복 시 재조회 0회 (c) 재조회 버튼 클릭 시 정확히 +1회 (d) 분석 시작 시 암묵적 재조회 없음 (e) `/analyze/cms/jobs` 요청 바디가 화면 표시값과 정확히 일치함을 확인. 코드는 이동만, 로직 변경 없음. |

---

## 이번 계획에서 의도적으로 제외 (다음 단계 후보)

안전망(CI+테스트) 확보 후 진행. 발주/분석 로직이 담긴 파일을 직접 옮기므로 위험도 한 단계 위.

- **백엔드 god module 분해**: `backend/analysis.py` 2,117줄(07-13 1,920)(4모듈로), `report_template_export.py` **7,790줄(07-13 4,357 → +79%, 거의 2배 — 07-20 우선순위 상향 권고**: 마스킹/xlsx/html/pptx/pdf 5개 백엔드 + 보안 계층이 한 파일. 리포트 기능이 계속 여기 쌓이는 중이라 다음 단계 선착수 후보. ⚠️ 07-20 발견 및 **분류 완료**: `tests/test_report_export_masking.py` 6개 전부 **REGRESSION**(stale-test/bad-test 아님) — HTML 전환(`dd5ae1b`)과는 무관, 진짜 원인은 **같은 함수명이 파일 안에서 2~4번 중복 정의**되어 있고(`normalize_report_title`, `report_card_title`, `report_card_slide_title`, `clean_cross_title`, `clean_cross_axis_name`) Python이 조용히 마지막 정의로 덮어써서 나중에 추가된 버전이 원래 정확했던 버전을 가림(커밋 `99afb78`, `b0a5277`에서 발생). 예: `normalize_report_title` 180행(정확)이 7544행(부실)에 가려짐; `clean_cross_axis_name`이 block id의 "country" 부분일치로 축 이름을 오분류; `should_paginate_ranking_card`가 "sku" 부분일치로 고정 레이아웃을 잘못 페이지네이션; `cross_matrix` 블록만 제목이 통째로 버려짐. **분해 착수 전 이 6개를 먼저 초록화해야 함** — 안 그러면 분해 중 "어느 버전이 진짜였는지" 판단 불가 → **07-20 완료**: 6개 전부 수정, 진행 기록 참조), `core/order_review.py`의 `order_review_df` 526줄 함수
- **동시성 슬롯 조기 해제 수정**: `routers/cms.py:267-340` — 타임아웃 후 유령 스레드가 돌아도 슬롯 즉시 해제 → `MAX_CONCURRENT_ANALYSES=2` 뚫림
- **print → logging 전환** (22개 파일)
- **core 순환 의존 해소** (kpi↔loaders↔order_review↔transport) + 죽은 plotly import/핀 제거
- **FastAPI TestClient 테스트**: 라우터 7개 전부 + `storage.py` 다운로드 토큰 검증(보안) 테스트 0건
- **행 타입 계약 강화**: `types/api.ts`의 `Record<string, unknown>` 164회 → 주요 테이블 명시 타입
- **react-query 도입**: `storage.ts` 483줄 커스텀 이벤트 동기화 대체
- **기타**: openpyxl deprecated `copy()`(`core/export_excel_report.py:337-340`), ~~`xlsx@0.18.5` CVE 미패치~~ → 3b 삭제 목록으로 편입(제거로 해소), OPERATIONS.md 100↔250MB 드리프트, README "Python 3.11"→3.14 정정, 골든 테스트 silent skip → fixture 동봉, `_JOBS` dict eviction 부재, 폴더 복사 버전관리(ESM_SCM4~10_old 6세대) 중단 검토, `test_order_sheet_reference_layout.py:452` return 뒤 도달 불가 assert 3줄 정리

## 진행 기록

| 날짜 | 항목 | 내용 |
|---|---|---|
| 2026-07-13 | — | 감사 완료, 계획 수립. 작업 착수 전. |
| 2026-07-13 | 검증 | UI/UX 안전성 4방향 코드 실측 완료 — 죽은 코드 전원 삭제 가능 확정, 해체 픽셀-동일 가능(3조건), 인증 함정 4개 식별, 안전망 공백(토큰 감사 42건 위반 무력화) 발견 → 보완책 3개 추가. |
| 2026-07-13 | 리뷰 | 발주분석탭 커밋 2개(bcddc69 발주검토 엑셀, cba8bc0 재고갭 엑셀+인증UI) 리뷰 — 확정 결함 7건(N1~N7) → 신규 항목 1.5 편입, xlsx 패키지 삭제 확정, 죽은 코드 판정 전원 유지 재확인, 라인 참조 전면 갱신(파일 10,562줄), 5번 선행조건 ① 충족됨. |
| 2026-07-13 | **1번 완료** | storage.py에 `output_path_for_job_async`(threadpool 체크 + `asyncio.sleep` 폴링) 추가, download 라우트의 동기 호출 3개(ensure_storage_dirs·verify_download_token·폴링)를 루프 밖으로 이동, analyze·latest-order-review의 `ensure_storage_dirs()`도 threadpool로. 검증: pytest 137 passed 유지 + 실서버(8011) 실측 — 다운로드가 6.9초 대기 중일 때 /api/health 응답 0.24~0.26초(기준선과 동일), 파일 생성 후 다운로드 200 정상. 커밋은 아직 안 됨. |
| 2026-07-13 | CI 수정 | 첫 CI 실행 ❌ 원인 규명: `.gitignore`의 `*.csv`가 tests/fixtures/까지 무시해 CI 체크아웃에서 test_regression_dras01이 FileNotFoundError. 화이트리스트+픽스처 4개 커밋(0e0b65a). 두 잡 모두 도커(python:3.14, node:24)에서 클린 체크아웃 기준 초록 재현 확인. |
| 2026-07-13 | **2번 완료** | CI(.github/workflows/ci.yml: pytest / tsc / eslint / build) + ESLint(flat config, next/core-web-vitals) 도입. 기준선 81건을 ESLINT_BACKLOG.md로 기록, 위반 있던 오류 규칙 5종 warn 강등으로 게이트 초록 시작. requirements-dev.txt(pytest==9.0.3) 신설. 로컬 검증: eslint exit 0(0 err/81 warn), tsc 0오류, next build 성공(.next 클린 후), pytest 137 passed. ubuntu 러너 동작은 첫 푸시 때 확인 필요. |
| 2026-07-13 | **1.5 완료** | N1+N3: 발주(exportingExcel)·재고갭(gapExportingExcel) 내보내기에 :9700 패턴(가드+disabled+try/catch/finally+진행 라벨) 적용, 재고갭 화면에 에러 배너 신설(기존엔 침묵 실패). N2: scopeLabel을 재고갭 요약 밴드 J3("내보내기 범위")/K3:L3에 기록. N4+N5: 스타일 패스를 `eachCell({includeEmpty})`→고정 열 범위 for 루프로(두 함수 모두). N6: no-op `.replace(/\\"/g,'"')` 3곳 제거. 검증: tsc 0오류, ui-regression 통과, 토큰 감사 42건 동일(신규 위반 0), 실물 exceljs 왕복 테스트로 기존 방식 L·M열 미스타일 재현 + 수정 방식 전체 스타일 확인. 커밋은 아직 안 됨. |
| 2026-07-20 | **3a 완료** | 작업 트리 청소: 로그 132개 삭제(21.7MB, 실행 중 서버 로그 4개만 잔존), tmp 데이터 13개 삭제(`_tmp_sales_history.xls` 217MB·`_tmp_prod.xls` 94MB 등 ~313MB), 백업 폴더 3개+`.git-backups` 삭제(~581MB), `git gc --prune=now`(.git 354M→56M). 총 회수 ≈ 1.2GB. 전부 git 미추적 확인 후 삭제(추적 파일 영향 0). ⚠️ repo 루트는 `ESM_SCM10_old`(부모), 프로젝트는 `ESM_SCM8/` 하위임을 확인. |
| 2026-07-20 | **3b 부분완료** | 파일·패키지 레벨 죽은 코드 삭제: `lib/mock-data.ts`(492줄, 0참조), `components/season-trend/CountryInsightMap.tsx`(776줄, 외부참조 0) + 그 파일 전용 패키지 `d3-geo`·`topojson-client`·`world-atlas`·`@types/d3-geo`·`@types/topojson-client` + 소스참조 0인 `three`·`@types/three`·`xlsx`(N7, CVE는 제거로 해소) 총 8개 제거(npm이 전이 포함 24개 제거). 검증: tsc 0오류 + `next build` 전 라우트 성공 + `npm test` 전 항목 통과. ⚠️ npm audit moderate 4건 잔존(별도 검토). **미착수분**: ① 워크스페이스 내부 죽은코드(InsightInputScreenExact 등)는 라인 +2,000줄 밀림·모놀리스 내부 편집 위험 → 5번 해체 시 심볼 기준 처리로 이월. 커밋 안 됨(working tree). |
| 2026-07-20 | **3b OrderReviewTable 삭제 완료** | 사용자 승인 후 죽은 코드 `OrderReviewTable.tsx`(1,077줄)+`OrderReviewClient.tsx` 삭제, `OrderAnalysisClient.tsx` import·fallback 정리(order-review 분기 `return null`), `ui-regression.test.mjs` obsolete 어서션 3개 제거. 검증: tsc 0오류 + npm test 전 항목 통과 + next build 전 라우트 성공. 조사 중 발견: OrderAnalysisClient shell의 order-review·stock-gap 분기 모두 실사용 경로 없음(절반 마이그레이션 잔재, 별건 정리 여지). 3번 전체(3a+3b) 커밋 `5884329`. |
| 2026-07-20 | **4번 완료** | NEXT_PUBLIC 비밀번호 서버측 이관 — 백엔드 `/api/auth/login·me·logout` + 인메모리 세션(30일 만료) + `backend/.env`(gitignore, python-dotenv), CORS `allow_credentials=True`(명시적 origin 목록이라 스펙 충돌 없음, 데이터 API 영향 0 확인), 프론트 `lib/auth.ts`/`AuthGuard.tsx`/`login/page.tsx`/`LogoutButton.tsx` 전면 교체(구현 함정 4개 전부 해결). 검증 3단계: ① pytest 신규 7개 통과 ② curl로 쿠키·CORS 헤더 직접 확인(허용/비허용 origin 둘 다) ③ Playwright 실브라우저로 무세션 리다이렉트→로그인→보호라우트 렌더→오답 오류메시지 전종단 확인. tsc/build/test 전부 통과. 부수 발견 2건: `httpx2==2.7.0`을 requirements-dev.txt에 추가(로컬 .venv가 CI와 다른 3.11이라 발견), `test_report_export_masking.py` 6개가 이미(07-13 이전부터) 실패 중임을 확인 — 내 변경과 무관, 백엔드 god module 분해 시 처리 필요로 기록. 커밋 안 됨(working tree). |
| 2026-07-20 | 재감사 | 풀스택 관점 전체 재감사(직접 실측 + 서브에이전트 심층 검증). **1·1.5·2번 커밋 반영·워킹트리 클린 확인**(storage `output_path_for_job_async`+`asyncio.sleep` 폴링 존재, exportingExcel/gapExportingExcel 가드 존재). 강점 재확인: 백엔드 라우터→서비스→core 분리 실질적, 에러처리 시니어급, TS `any`≤10·strict, bare except 0, 테스트 진짜배기. **드리프트 발견 후 계획 반영**: Workspace 10,562→12,517(+18%), report_template_export 4,357→7,790(+79%, 거의 2배 — 제외 항목 우선순위 상향), analysis 1,920→2,117. god 파일이 방치 기간에 복리로 성장함을 실증 → 5번·백엔드 god module 시급성 상승. 남은 항목(3·4·5) 판정 전원 유효, 구조 변경 없음. **[결정 대기 2건 여전히 미해결]**: 백업 폴더 3개(3a) 삭제, OrderReviewTable 존폐(3b/5). |
| 2026-07-20 | **신규 발주 로직 선행 작업 완료** | `analysisDate`/`exchangeRate` 관련 5개(값+함수)를 `PrepScreenExact` 지역상태에서 `SiliconAnalyticsWorkspace` 루트로 이동(`SharedAnalysisRuntime` 타입 신설). Context 미도입, 기존 `analysisSettings`와 동일한 루트+props 패턴. 검증: tsc/build/test 통과 + Playwright로 최초조회 1회·재방문 재조회 0회·수동재조회 +1회·분석시작 시 암묵재조회 0회·요청바디가 화면표시값과 일치함을 실증. 같은 커밋(`d8b181e`)에 "신규 발주 로직(BETA) 병렬 개발 설계" 섹션도 기록. |
| 2026-07-20 | **리포트 회귀 6건 수정 완료** | `test_report_export_masking.py`의 6개 실패를 07-20 재감사에서 REGRESSION으로 분류한 뒤 전부 수정. 원인은 전부 "같은 함수명이 파일 안에 2~4번 중복 정의돼 있고 Python이 조용히 마지막(대개 더 부실한) 정의로 덮어씀": `normalize_report_title`(180행 정확 vs 7544행 부실, 이스케이프 표기 확인상 서로 다른 도구로 작성된 것으로 추정) → 두 로직 병합 후 중복 제거. `should_paginate_ranking_card`의 제외 목록에 `sku_detail` 추가(부분일치 "sku"가 고정 KPI 타일을 잘못 페이지네이션하던 문제). `report_card_title`/`report_card_slide_title`(4중 정의) → cross_matrix에서 `block.title`을 완전히 버리고 `clean_cross_title(block)`으로 대체하던 로직 제거, 대신 `compact_cross_text`로 압축만 하도록 통합(1개 정의로). `clean_cross_axis_name`(2중 정의, 시그니처도 다름) → block id/제목에 우연히 "country" 같은 단어가 들어있으면 실제 축 값("성분")을 무시하고 강제로 "국가"를 반환하던 fallback 로직을 "실제 값이 진짜 비었을 때만" 작동하도록 고쳐서 재작성(1개 정의로, 시그니처는 확장판 유지 — 매트릭스 그리드 렌더링 코드가 이 시그니처로 직접 호출하는 게 있어서 삭제 시도 중 발견). `clean_cross_title`은 호출부 소멸로 완전히 죽은 코드가 되어 삭제. 부수 발견(범위 밖, 다음 분해 시 처리): `add_slide_header`(2중)·`report_card_header_subtitle`(3중)·`add_report_card_cross_matrix`(2중)도 같은 패턴으로 중복 — 오늘은 6개 테스트의 근본원인에 해당하는 것만 고침. 검증: `test_report_export_masking.py` 35 passed/16 skipped/0 failed(이전 29 passed에서 정확히 +6), 전체 백엔드 pytest 180 passed/17 skipped/0 failed(회귀 없음). 이걸로 백엔드 god module(report_template_export.py) 분해의 선행조건 충족. |
| 2026-07-20 | **5번 선행조건(보완책 1~3) 완료** | 토큰 감사: 실제 위반 1건(`bg-[#151519]`)을 `--dropdown-panel`/`dropdownpanel` 정식 토큰으로 교체, 0건화(컴파일 CSS로 시각 변화 없음 확인). Playwright 스모크: `frontend/scripts/route-smoke.mjs`(`npm run smoke`) 신설 — 로그인 후 라우트 35개 순회, 콘솔에러·빈 본문 검사+전체 스크린샷. 첫 시도 2건 실패(`/`, `/login`)는 `networkidle`이 Next dev HMR 때문에 안 settle되는 문제로 `domcontentloaded`+명시적 대기로 교체해 해결. 이후 1건(`/insight/brand-report`, "Failed to fetch")은 각 라우트 풀 네비게이션마다 루트가 재마운트되며 환율 API를 다시 부르는데 다음 라우트로 너무 빨리 넘어가 fetch가 abort된 테스트 한정 타이밍 이슈로 확인(실사용자는 SPA 내부 이동만 해서 안 겪음) — 대기 500ms→1500ms로 해결. 최종 35/35 통과, baseline 스크린샷 생성됨(gitignore 대상, 5단계 커밋마다 재실행해 대조 예정). QA 체크리스트: `Screen` 13개 전수, 화면별 핵심 인터랙션 2~3개 확정(§"3. [즉시]" 참조), `final` 화면은 도달 불가로 확인돼 QA 대상 제외·삭제 검토 표시. **5단계(워크스페이스 해체) 착수 조건 전부 충족.** 검증: tsc 0오류, lint 통과, npm test 통과. |
