# ESM SCM

Railway 운영 배포와 API 프록시 점검 방법은 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)를 참고하세요.

로그인 계정, 법인 권한, 비밀번호 해시 생성 및 배포 설정은 [docs/AUTHORIZATION.md](docs/AUTHORIZATION.md)를 참고하세요.

유럽 법인 발주 검토 자동화 시스템. CMS/ERP 파일을 업로드하면 SKU 단위 발주 필요 여부, 본사 이동 가능 물량, ETA 캘린더, 내부 보고용 엑셀을 자동으로 생성합니다.

**스택:** FastAPI (Python) + Next.js (TypeScript)

---

## 처음 설치

### 요구사항

- Python 3.11 이상
- Node.js LTS (18 이상)
- Git

### 저장소 내려받기

```bat
git clone https://github.com/siliconii-vibe/esm-order-review.git
cd esm-order-review
```

### Python 패키지 설치

```bat
pip install -r requirements.txt
```

### 프론트엔드 패키지 설치

```bat
cd frontend
npm install
cd ..
```

---

## 실행

백엔드와 프론트엔드를 각각 별도 터미널에서 실행합니다.

```bat
:: 터미널 1 - 백엔드
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8002

:: 터미널 2 - 프론트엔드
cd frontend
npm run dev
```

| 서비스 | 주소 |
| --- | --- |
| 프론트엔드 | http://127.0.0.1:3000 |
| 백엔드 health check | http://127.0.0.1:8002/api/health |
| API 문서 (개발 환경) | http://127.0.0.1:8002/docs |

운영 배포에서는 `APP_ENV=production`으로 설정해 `/docs`, `/redoc`, `/openapi.json`을 비활성화합니다.
프론트 배포 환경에는 `FASTAPI_INTERNAL_BASE_URL`을 실제 백엔드 주소로 설정해야 합니다.
브라우저 API 호출은 기본적으로 같은 도메인의 `/backend-api`를 사용하고, Next.js가 이를 백엔드의 `/api`로 전달합니다.
백엔드 도메인을 브라우저에 직접 공개하는 별도 구성에서만 `NEXT_PUBLIC_FASTAPI_BASE_URL`을 설정합니다.

---

## 코드 구조

```
ESM_SCM8/
├── backend/          # FastAPI 서버
│   ├── main.py       # 라우터 (업로드, 분석, 다운로드)
│   ├── analysis.py   # 분석 워크플로우
│   └── ai.py         # AI 어시스턴트 (Ollama)
├── core/             # 핵심 분석 엔진
│   ├── session.py    # 세션 상태 관리
│   ├── common.py     # 공통 상수 및 유틸
│   ├── loaders.py    # 파일 로드 및 파싱
│   ├── order_review.py         # 발주 검토 메인 로직
│   ├── order_review_data.py    # 데이터 집계
│   ├── order_review_report.py  # 리포트 빌더
│   ├── export_excel.py         # 엑셀 생성
│   ├── export_excel_util.py    # 엑셀 유틸
│   ├── eta.py        # ETA 캘린더/타임라인
│   ├── transport.py  # 운송 데이터 처리
│   └── validation.py # 필터/검증
├── frontend/         # Next.js 프론트엔드
│   ├── app/          # 페이지
│   └── components/   # UI 컴포넌트
└── tests/            # 회귀 테스트
```

---

## 최신 코드 받기

```bat
git pull
```

## 수정한 코드 올리기

```bat
git status
git add .
git commit -m "작업 내용"
git push
```

---

## 테스트 실행

```bat
python -m pytest tests -q
cd frontend
npm run typecheck
npm run build
```
