# Repository agent instructions

이 저장소에서 작업하는 모든 코드 에이전트는 루트의
[`CLAUDE.md`](CLAUDE.md)를 프로젝트 공통 규칙으로 따른다.

## 협업 규칙 (2026-09-08 추가)

이 저장소는 다인 협업 체제로 전환 중이다. 구조 지도와 상세 규칙은
[`ESM_SCM8/docs/ONBOARDING.md`](ESM_SCM8/docs/ONBOARDING.md)를 읽는다.

- `main` 브랜치에 직접 커밋하지 않는다. 작업 브랜치를 만들어 PR로 머지한다.
- 사용자에게 배정된 담당 폴더 밖의 파일은 수정하지 않는다. 담당이
  명시되지 않은 세션에서는 수정 대상 파일 목록을 먼저 제안하고 진행한다.
- 보호 파일(`frontend/app/layout.tsx`, `frontend/lib/` 공용 모듈,
  `Dockerfile*`, `docker/`, `package.json` scripts, `next.config.mjs`,
  `.env*`)은 사용자의 명시적 승인 없이 수정하지 않는다.
- `frontend/` 최상위 폴더 신설·이동·이름 변경, 새 환경변수, 새 인프라
  의존성은 배포 담당자와의 조율이 필요한 변경임을 사용자에게 알린다.
- `frontend/app/` 아래 리다이렉트 껍데기 page.tsx는 옛 주소 호환용이므로
  삭제하지 않는다.

신규 발주 로직 V2를 수정·검토할 때는 작업 전에
[`ESM_SCM8/docs/ORDER_LOGIC_V2_HANDOFF.md`](ESM_SCM8/docs/ORDER_LOGIC_V2_HANDOFF.md)를
끝까지 읽는다.

HQ·PL·USA의 4주 정기보충 `(R,S)` 목표 로직을 수정·검토할 때는 위 문서와
함께 [`ESM_SCM8/docs/ORDER_LOGIC_V2_R_S_SPEC.md`](ESM_SCM8/docs/ORDER_LOGIC_V2_R_S_SPEC.md)를
끝까지 읽는다. 이 문서는 2026-08-14 사용자 인터뷰에서 승인된 계산 계획이며,
기존 구현 설명과 충돌하는 목표 산식은 이 문서의 결정 로그를 우선한다.

본사(`HQ`) 오포 창고 발주분석을 수정·검토할 때는 작업 전에
[`ESM_SCM8/docs/HQ_ORDER_ANALYSIS_HANDOFF.md`](ESM_SCM8/docs/HQ_ORDER_ANALYSIS_HANDOFF.md)를
끝까지 읽는다. 미결로 표시된 산식·필터·fallback은 사용자 결정이나 원천
명세 없이 구현하지 않는다.

발주분석 V3 전체 로직(SES, HOLT+감쇠, Croston+SBA, 상품분류, 재고위치,
Layer 1·2·3, ROP, 목표재고, 발주수량)을 수정하거나 검토할 때는 작업 전에
[`ESM_SCM8/docs/ORDER_LOGIC_V3_DISCOVERY_HANDOFF.md`](ESM_SCM8/docs/ORDER_LOGIC_V3_DISCOVERY_HANDOFF.md)를
끝까지 읽는다. 인터뷰가 끝나지 않은 산식·상수·초기화·fallback을 문서 예시나
프런트 fixture에서 가져와 구현하지 않는다.

발주분석 V3의 시즌팩터·계절지수·계절 보정·월간 사전계산을 수정하거나
검토할 때는 작업 전에
[`ESM_SCM8/docs/ORDER_V3_SEASON_FACTOR_SPEC.md`](ESM_SCM8/docs/ORDER_V3_SEASON_FACTOR_SPEC.md)를
끝까지 읽는다. 문서의 인터뷰 결정 로그에서 미결인 산식·적용범위·fallback·
운영 기본값은 사용자 승인 없이 구현하지 않는다.

추가 원칙:

- 실제 애플리케이션 루트는 `ESM_SCM8/`이다.
- 기술명세에 없는 산식 또는 기본값을 추정해 넣지 않는다.
- 기존 발주분석과 신규 발주 로직 V2의 코드 경계를 유지한다.
- 작업트리의 기존 사용자 변경을 보존하고 관련 없는 변경을 커밋에 섞지 않는다.
- API 키, 비밀번호, CMS 원문 및 실제 사용자 데이터를 저장소에 기록하지 않는다.
- 변경 범위에 맞는 테스트를 실행하고 결과와 미검증 항목을 명확히 보고한다.

