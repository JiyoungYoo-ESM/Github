# 신규 팀원 온보딩 가이드

이 문서는 처음 합류한 팀원(그리고 그 팀원이 쓰는 AI 코딩 도구)이
저장소 구조를 빠르게 파악하도록 돕는 지도다. 설치·실행 방법은
[README.md](../README.md), 상세 규칙은 루트 [CLAUDE.md](../../CLAUDE.md)와
[AGENTS.md](../../AGENTS.md)를 본다.

## 한눈에 보는 구조

```
ESM_SCM8/                  <- 실제 애플리케이션 루트
  core/                    <- 순수 산식 모듈 (발주 로직 V2 등)
  backend/                 <- FastAPI
    routers/               <- API 엔드포인트 (도메인별 1파일)
    services/              <- 비즈니스 로직 (routers가 호출)
    models/                <- DB 모델
  frontend/                <- Next.js (App Router)
    app/                   <- 라우트. 상당수가 리다이렉트 껍데기 (아래 지도 참고)
    components/redesign/   <- 실제 화면 본진. 이름과 달리 임시가 아니라 현역이다
    components/(기타)/     <- 도메인별 컴포넌트
    lib/                   <- 공용 모듈 (auth, routes, api 클라이언트 등)
    scripts/*.test.mjs     <- 프런트 테스트
  tests/                   <- 백엔드 pytest
  docs/                    <- 스펙·핸드오프 문서 (산식 수정 전 필독 문서 포함)
```

## 화면(라우트) 지도

`frontend/app/` 아래 `page.tsx`가 43개지만 실제 화면은 28개다.
나머지 15개는 옛 주소 호환용 리다이렉트 껍데기이므로 삭제하거나
수정하지 않는다. 주요 현역 화면:

| 주소 | 화면 | 코드 위치 |
| --- | --- | --- |
| `/order-analysis/order-review` | 기존 발주분석 | `components/redesign/SiliconAnalyticsWorkspace` |
| `/order-analysis/new-order-logic` | 신규 발주 로직 V2 | `components/redesign/screens/order-v2/` |
| `/order-analysis/order-v3` | 발주분석 V3 | `components/redesign/screens/order-v3/` (스펙 문서 필독) |
| `/order-analysis/stock-gap` | 재고 갭 | `components/redesign/screens/` |
| `/order-analysis/sku-concentration` | SKU 집중도 | `components/redesign/screens/` |
| `/integrated-order-review` | 통합 발주 검토 | `app/integrated-order-review/` |
| `/insight/*` | 브랜드·국가·성분 등 인사이트 | `components/redesign/screens/` |
| `/season-trend/global-demand` | 글로벌 수요 | `components/redesign/screens/` |
| `/upload` | 파일 업로드 | `components/upload/` |

리다이렉트 껍데기(수정 금지): `/order-review`, `/stock-gap`,
`/sku-concentration`, `/season-calendar`, `/order-analysis`(루트),
`/order-analysis/final`, `/season-trend` 하위 다수, `/ingredient-trend`,
`/insight/ingredient`. 각 파일 상단 주석에 리다이렉트 대상이 적혀 있다.

"발주" 관련 화면이 여러 개인 이유: 기존 발주분석, V2, V3는 **의도적으로
분리된 독립 기능**이다. 하나를 고치면서 다른 것을 통합하거나 건드리지
않는다 (CLAUDE.md 코드 경계 참고).

## 협업 규칙

### 브랜치

- `main` 직접 push 금지. `main`은 배포 대상 브랜치다.
- 작업은 `feature/기능명` 또는 `codex/기능명` 브랜치에서 하고 PR로 머지한다.
- 머지 전 리뷰 승인 1명 이상 (초기에는 장원정이 머지 담당).

### 담당 영역

- 자신에게 배정된 폴더 밖의 파일은 수정 전에 담당자와 상의한다.
- AI 코딩 도구에게 작업을 시킬 때는 허용 폴더를 명시한다.
  (예: "이번 작업은 `backend/services/xxx.py`와 `tests/test_xxx.py`만 수정해.")
- 팀원별 담당 폴더: (합류 시 여기에 기록)

### 보호 파일 (수정 전 반드시 상의)

아래 파일은 전체 화면·빌드·배포에 영향을 준다.

- `frontend/app/layout.tsx`, `frontend/app/globals.css`
- `frontend/lib/` 공용 모듈 (`auth.ts`, `routes.ts`, `entities.ts`, `api/` 등)
- `frontend/package.json`의 scripts, `next.config.mjs`, `tailwind.config.ts`
- `Dockerfile.backend`, `frontend/Dockerfile`, `docker/` — 배포 담당(정현님) 태그 필수
- `.env*`, `backend/config.py` — 시크릿은 인프라(민우님)가 관리

### 배포 담당자에게 미리 알려야 하는 변경

Docker 이미지가 최상위 폴더를 명시적으로 COPY하므로, 아래 변경은
배포를 깨뜨릴 수 있다. PR에 배포 담당자를 태그한다.

1. `frontend/` 바로 아래 새 폴더 신설, 기존 폴더 이동·이름 변경
2. 새 환경변수 추가
3. 새 외부 서비스·인프라 의존성 추가 (예: Redis)
4. `package.json`의 `build`/`start` 스크립트 변경

### 산식(금액·수량 계산) 수정

발주·재고·환율 등 숫자가 걸린 로직은 수정 전에 해당 스펙 문서를
끝까지 읽는다 (AGENTS.md에 문서 목록). 문서에 없는 산식·기본값·fallback을
임의로 추가하지 않는다. AI가 "그럴듯한 기본값"을 제안해도 사용자 승인
없이는 구현하지 않는다.

## 테스트

- 백엔드: `ESM_SCM8/`에서 `pytest tests/` (변경 범위에 맞는 파일만이라도 실행)
- 프런트: `frontend/`에서 `npm test` (전체) 또는 `npm run test:...` (개별)
- 테스트 통과가 곧 "숫자가 맞다"는 뜻이 아니다. 금액·수량 화면은
  예시 숫자로 실제 화면·엑셀을 대조한다 (CLAUDE.md 참고).
