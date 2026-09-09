# 로그인 계정 및 법인 권한 운영 가이드

## 현재 구조

- 인증 저장소: `backend.auth.user_store.EnvironmentUserStore`
- 비밀번호: 환경변수에 PBKDF2-SHA256 해시만 저장
- 세션: 서버가 발급한 임의 토큰을 `HttpOnly` 쿠키(`s2_session`)로 전달하고, 사용자 식별값과 만료시각은 서버 메모리에 저장
- 권한 기준: 역할명이 아니라 각 계정의 `allowed_entities`
- 법인 전달: 프론트 공통 API 클라이언트가 `X-Entity-Code` 헤더를 강제로 추가
- 데이터 API: 세션 확인 → 법인 코드 검증 → 계정 권한 검증 → 연동 상태 확인 후에만 실행
- 현재 실제 연동 법인: `PL`(발주·분석), `USA`(발주·분석), `HQ`(판매 분석 전용). 나머지 법인은 권한 모델과 UI에는 존재하지만 데이터 요청 시 `409`와 연동 준비 안내를 반환

쿠키에 권한 정보를 서명해 담는 방식이 아니라, 추측하기 어려운 일회성 토큰을 서버 저장소와 대조하는 방식이다. 따라서 `AUTH_SESSION_SECRET`은 필요하지 않다. 향후 서명 쿠키/JWT로 변경할 때는 그 시크릿을 반드시 환경변수로 추가한다.

`adminmaster`와 내부감사용 `ia`는 현재 전 법인 조회 및 관리자 기능을 함께 사용한다. 추후 메뉴별 세분 권한은 별도 RBAC 정책으로 분리한다. 기존 분석 산식과 EU 데이터 매핑은 변경하지 않았다.

## 권한 매트릭스

| 계정 | 허용 법인 |
| --- | --- |
| `adminmaster` | HQ, PL, UK, USA, ME, MX, MY, VN |
| `eu_manager` | HQ, PL, UK |
| `bm1` | HQ, PL, UK, USA, ME |
| `bm2` | HQ, PL, UK, USA, ME |
| `bm3` | HQ, PL, UK, USA, ME |
| `hnb_team` | HQ, PL, USA |
| `ia` | HQ, PL, UK, USA, ME, MX, MY, VN |
| `my_team` | HQ, MY |
| `sales_team` | HQ, PL |
| `vn_team` | HQ, VN |

## 비밀번호 해시 생성과 설정

프로젝트 루트(`ESM_SCM8`)에서 각 계정마다 서로 다른 비밀번호를 선택하고 다음 명령을 실행한다.

```powershell
.venv\Scripts\python.exe -m backend.scripts.generate_password_hash
```

명령은 비밀번호를 두 번 입력받고 해시만 출력한다. 원문 비밀번호를 파일이나 로그에 저장하지 않는다. 출력된 각 해시를 배포 비밀 설정 또는 로컬 `backend/.env`의 해당 변수에 넣는다.

```text
AUTH_ADMINMASTER_PASSWORD_HASH=
AUTH_EU_MANAGER_PASSWORD_HASH=
AUTH_BM1_PASSWORD_HASH=
AUTH_BM2_PASSWORD_HASH=
AUTH_BM3_PASSWORD_HASH=
AUTH_HNB_TEAM_PASSWORD_HASH=
AUTH_MY_TEAM_PASSWORD_HASH=
AUTH_SALES_TEAM_PASSWORD_HASH=
AUTH_VN_TEAM_PASSWORD_HASH=
```

선택적으로 `AUTH_<ACCOUNT>_ACTIVE=false`를 설정하면 해당 계정 로그인을 차단할 수 있다. 운영(`APP_ENV=production`)에서는 9개 해시 중 하나라도 없거나 `FRONTEND_ORIGIN`이 없으면 서버가 기동하지 않는다. 개발 환경에서는 해시가 없는 계정만 안전하게 로그인 실패한다.

`.env`는 Git 제외 대상이고, 변수명만 포함한 `backend/.env.example`은 추적 대상이다.

### 이 PC에서 초기 비밀번호 복사

초기 비밀번호 원문은 평문 파일이 아닌 현재 Windows 사용자의 **Windows 자격 증명 관리자**에 `ESM_SCM8/<account-id>` 이름으로 보관한다. 필요한 계정 하나만 클립보드로 복사한다.

```powershell
.\backend\scripts\copy_account_password.ps1 adminmaster
```

마지막 인자는 `adminmaster`, `eu_manager`, `bm1`, `bm2`, `bm3`, `hnb_team`, `ia`, `my_team`, `sales_team`, `vn_team` 중 하나다. 도구는 비밀번호를 콘솔이나 파일에 출력하지 않고 클립보드에만 복사한다. 로그인 후에는 다른 텍스트를 복사해 클립보드를 덮어쓴다.

새 계정의 비밀번호를 생성하거나 기존 비밀번호를 교체할 때는 아래 도구를 사용한다. 생성된 원문 비밀번호는 Windows 자격 증명 관리자에만 저장하고, `backend/.env`에는 검증용 해시만 저장한다. 기존 계정의 교체는 의도치 않은 변경을 막기 위해 `-ReplaceExisting` 옵션이 필요하다.

```powershell
.\backend\scripts\provision_account_password.ps1 hnb_team
.\backend\scripts\provision_account_password.ps1 hnb_team -ReplaceExisting
```

## 실행과 검증

백엔드:

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8002
```

백엔드 테스트:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

프론트엔드:

```powershell
cd frontend
npm run typecheck
npm test
npm run build
```

프론트 법인 매트릭스 단독 테스트:

```powershell
node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON --experimental-strip-types scripts/entity-permissions.test.mjs
```

## 권한 및 캐시 경계

- `/api/auth/me`는 현재 계정의 공개 정보와 허용 법인만 반환한다. 비밀번호 해시와 다른 계정 정보는 반환하지 않는다.
- 분석·시즌 작업 상태는 생성 계정/법인 범위와 일치할 때만 조회할 수 있다.
- 최신 발주 결과 경로는 `username + entity + browser client id` 범위로 분리한다.
- 시즌 최신 결과 파일은 `username + entity` 범위로 분리한다.
- CMS 계산 메모 키는 `username + entity`를 포함한다.
- CMS 원본 캐시는 데이터 소스 법인(`HQ`, `PL`, `USA`)을 키에 포함하며, 같은 법인 권한 사용자끼리만 재사용한다.
- 미주 일반 분석은 `/us/stock/local`, `/us/stock/hq`, `/us/sales/local`, `/us/sales/hq-to-us`, `/us/shipping/containers`, `/us/open-po`를 사용한다.
- `/us/sales/history`는 미주 현지 판매가 아니라 본사 전체 판매내역 상세이므로 미주 판매·시즌 분석 입력으로 사용하지 않는다.
- 본사 분석은 `/us/sales/history`와 전사 상품마스터 `/eu/products?eu_sold_only=false`를 상품코드로 결합한다. `amount_krw`를 원화 매출로 사용하며 본사 발주 분석은 제공하지 않는다.
- 신규 발주 로직 V2는 미주 전용 `sigma`, 서비스 수준 등 정책값이 확정되기 전까지 `PL`만 허용한다. `USA` 요청에는 PL 정책을 대입하지 않고 `409`를 반환한다.
- 다운로드 토큰 메타데이터는 생성 사용자와 법인에 묶인다. 토큰 URL을 다른 사용자에게 전달해도 `403`이다.
- 로그아웃 및 법인 전환 시 메모리, sessionStorage, 분석 IndexedDB 결과를 초기화한다.

## 배포 주의사항

- 쿠키는 운영 환경에서 `Secure`, 항상 `HttpOnly`, `SameSite=Lax`로 설정된다.
- CORS는 명시적인 `FRONTEND_ORIGIN`만 허용하며 credentials와 `*`를 함께 사용하지 않는다.
- 현재 세션 저장소는 단일 프로세스 메모리 방식이다. 여러 Uvicorn worker로 확장하기 전에 `SessionStore` 구현을 Redis 또는 DB 저장소로 교체해야 한다.
- UK/ME/MX/MY/VN 데이터 API 코드는 확인되지 않았으므로 임의 매핑하거나 PL 데이터를 대체 표시하지 않는다. 실제 API가 확정되면 `backend/entities.py`의 연동 상태와 외부 코드 매핑, 해당 데이터 어댑터를 함께 추가한다.
