# 고객센터 PostgreSQL 설정

## Railway

1. 기존 Railway 프로젝트에 PostgreSQL 서비스를 추가합니다.
2. FastAPI 서비스의 `DATABASE_URL` 변수에 `${{Postgres.DATABASE_URL}}`을 지정합니다.
3. 첨부파일을 유지하려면 FastAPI 서비스에 Volume을 연결하고 마운트 경로를 지정합니다.
4. FastAPI 서비스 변수 `SCM_SUPPORT_ATTACHMENT_DIR`을 해당 마운트 경로 아래 디렉터리로 설정합니다.
5. Pre-deploy Command를 `alembic upgrade head`로 설정합니다.
6. 애플리케이션을 재배포합니다.

예시:

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
SCM_SUPPORT_ATTACHMENT_DIR=/data/support_attachments
SCM_SUPPORT_MAX_ATTACHMENT_MB=15
```

## 로컬 개발

로컬 PostgreSQL의 연결 문자열을 `backend/.env`에 추가한 후 마이그레이션을 실행합니다.

```text
DATABASE_URL=postgresql://postgres:password@127.0.0.1:5432/esm_scm
```

```powershell
python -m alembic upgrade head
```

문의 API는 `DATABASE_URL`이 없으면 `503`을 반환하며, 기존 분석 API는 계속 사용할 수 있습니다.
