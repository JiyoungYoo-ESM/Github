# Railway deployment

The production application uses four service roles in the same Railway project
and environment: `Frontend` (Next.js), `Backend` (FastAPI), a general analysis
`Worker`, and one or more dedicated `V3 Worker` replicas. PostgreSQL persists
job ownership/status and Redis brokers work. Browser requests go to the
same-origin `/backend-api/*` path. Next.js forwards those requests to the
FastAPI service over Railway private networking.

Large binary downloads such as the order-logic V2 Excel export use the
same-origin `/api/*` path directly so Next.js does not buffer the generated
workbook. The public ingress for `esm.pikicat.com` must therefore continue to
route `/api/*` to the Backend service while all page routes go to Frontend.

## Backend service

- Working directory: the directory containing `backend/`, `frontend/`, and
  `requirements.txt`
- Build command: `pip install -r requirements.txt`
- Start command: `sh backend/scripts/start_production.sh`
- Healthcheck path: `/api/health/ready`
- Required variables:

```text
PORT=8002
APP_ENV=production
FRONTEND_ORIGIN=https://esm.pikicat.com
DATABASE_URL=<Railway PostgreSQL private DATABASE_URL>
REDIS_URL=<Railway Redis private REDIS_URL>
CELERY_BROKER_URL=<defaults to REDIS_URL when omitted>
CELERY_RESULT_BACKEND=<defaults to CELERY_BROKER_URL when omitted>
CELERY_TASK_MAX_RETRIES=3
CELERY_TASK_RETRY_BACKOFF_SECONDS=30
CELERY_WORKER_CONCURRENCY=1
CELERY_WORKER_QUEUES=analysis
SENTRY_DSN=<Sentry Python/FastAPI project DSN>
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_RELEASE=<optional deployed Git SHA or release version>
NEXT_PUBLIC_PERFORMANCE_SAMPLE_RATE=0.1
OBJECT_STORAGE_BUCKET=<private S3/R2/MinIO bucket name>
OBJECT_STORAGE_ENDPOINT_URL=<optional S3-compatible endpoint URL>
OBJECT_STORAGE_REGION=auto
OBJECT_STORAGE_ACCESS_KEY_ID=<secret when not using an IAM role>
OBJECT_STORAGE_SECRET_ACCESS_KEY=<secret when not using an IAM role>
OBJECT_STORAGE_PREFIX=esm-scm
OBJECT_STORAGE_PRESIGN_SECONDS=300
OBJECT_STORAGE_OUTPUT_RETENTION_DAYS=1
OBJECT_STORAGE_SUPPORT_RETENTION_DAYS=90
SCM_STORAGE_DIR=<mounted persistent volume path, for example /data/esm-scm>
# Set only when requests arrive through a known reverse proxy CIDR.
SCM_TRUSTED_PROXY_CIDRS=<optional, e.g. 10.0.0.0/8>
AUTH_ADMINMASTER_PASSWORD_HASH=<secret>
AUTH_EU_MANAGER_PASSWORD_HASH=<secret>
AUTH_BM1_PASSWORD_HASH=<secret>
AUTH_BM2_PASSWORD_HASH=<secret>
AUTH_BM3_PASSWORD_HASH=<secret>
AUTH_HNB_TEAM_PASSWORD_HASH=<secret>
AUTH_IA_PASSWORD_HASH=<secret>
AUTH_MY_TEAM_PASSWORD_HASH=<secret>
AUTH_SALES_TEAM_PASSWORD_HASH=<secret>
AUTH_VN_TEAM_PASSWORD_HASH=<secret>
```

Attach a Railway Volume to the backend service first, then set
`SCM_STORAGE_DIR` to its mount path. Do not use the application container path
as a substitute: it is erased on redeploy.

The production start script automatically applies Alembic migrations and
checks account hashes, database connectivity, mounted storage, and disk before
Uvicorn begins accepting traffic. Do not configure a second migration command
in Railway; one controlled startup path avoids drift.

## Frontend service

- Working directory: `frontend`
- Build command: `npm ci && npm run build`
- Start command: `npm run start`
- Required variables:

```text
PORT=3000
FASTAPI_INTERNAL_BASE_URL=http://${{Backend.RAILWAY_PRIVATE_DOMAIN}}:${{Backend.PORT}}
```

`Backend` in the reference above must exactly match the Railway backend service
name. `Backend.PORT` is a manually defined service variable; it is not inferred
from Railway's runtime port. Do not set `NEXT_PUBLIC_FASTAPI_BASE_URL` for the
same-origin configuration.

## Release verification

After both services have deployed, run from `frontend/`:

```text
npm run smoke:deployment -- https://esm.pikicat.com
```

This verifies the login page, the Next.js-to-FastAPI health proxy, and the
anonymous authentication boundary. A `500` from `/backend-api/health` means the
frontend service cannot reach `FASTAPI_INTERNAL_BASE_URL`; check the service
reference, port, environment, and backend health before releasing.

Also verify `https://esm.pikicat.com/api/health/live` returns `200`. This direct
Backend route is used for large V2 Excel downloads.

All services must be in the same Railway project and environment for the
private `*.railway.internal` address to resolve.

## Production release checklist

1. Copy [backend/.env.example](../backend/.env.example) as the variable
   checklist; do not upload that file or any secrets to Git.
2. Configure the Backend Railway Volume and `SCM_STORAGE_DIR`.
3. Add a Railway Redis service and configure the Backend `REDIS_URL` from its
   private connection URL. Redis backs login rate limits and global analysis
   concurrency across every worker.
4. Add a separate Railway **Worker** service from the same repository. Use the
   start command `sh backend/scripts/start_worker.sh`, set
   `CELERY_WORKER_QUEUES=analysis`, configure the same `DATABASE_URL`,
   `REDIS_URL`, object-storage, and authentication variables as Backend, and
   attach its own writable volume for `SCM_STORAGE_DIR`. Keep
   `CELERY_WORKER_CONCURRENCY=1`. CMS and season analysis jobs are acknowledged
   late and run outside the web process; the volume need not be shared with
   Backend because completed workbooks are published to object storage.
5. Add a dedicated Railway **V3 Worker** service from the same repository with
   the same start command and shared PostgreSQL/Redis/object-storage variables.
   Set `CELERY_WORKER_QUEUES=order-v3` and `CELERY_WORKER_CONCURRENCY=1` so one
   memory-heavy calculation runs in each isolated worker process. Scale this
   service by replicas after measuring peak memory: two replicas execute two V3
   jobs concurrently, four execute four, and excess jobs remain queued instead
   of returning HTTP 409. V3 result rows are compressed into 250-SKU objects
   under `outputs/order-v3/`; PostgreSQL stores only the small job manifest.
6. Configure the Backend `DATABASE_URL`, frontend origin, and all password-hash
   variables.
7. Create a Sentry Python/FastAPI project, then configure its `SENTRY_DSN`.
   Set `SENTRY_TRACES_SAMPLE_RATE=0.1` initially and optionally set
   `SENTRY_RELEASE` to the deployed Git SHA. The backend removes cookies,
   authorization headers, request bodies, query strings, and user identity
   before sending events.
8. Create a private S3-compatible bucket and configure `OBJECT_STORAGE_BUCKET`.
   Completed workbooks, their download-token metadata, and support attachments
   are stored there. The API checks authorization first, then returns a
   five-minute presigned URL; do not make the bucket public.
   Before the first release, run the following once with deployment credentials:

   ```text
   python -m backend.scripts.configure_object_lifecycle --apply
   ```

   It adds only the managed `outputs/` and `support/` rules under
   `OBJECT_STORAGE_PREFIX`, preserving unrelated bucket rules. Runtime
   readiness fails if either managed rule is absent or cannot be checked.
9. Configure the Frontend `FASTAPI_INTERNAL_BASE_URL` with the private Railway
   service reference.
10. Set the Backend Start Command to `sh backend/scripts/start_production.sh`
   and healthcheck to `/api/health/ready`, not the liveness-only endpoint.
11. Confirm the startup log contains successful Alembic migration and runtime
   readiness JSON. If Railway shell access is available, rerun
   `python -m backend.scripts.verify_runtime` to diagnose a failed startup.
12. Run the deployed smoke test and retain its CI result with the release.

## Automated deployed smoke test

Create a GitHub Actions repository variable named `DEPLOYMENT_ORIGIN` with the
public frontend origin, for example `https://esm.pikicat.com`. Every push to
`main` then runs the deployed smoke job after CI. It retries for five minutes
to allow Railway's rollout to finish, and checks:

- `/login` is served;
- the same-origin frontend-to-backend proxy returns 200 for `/health/live` and
  `/health/ready`;
- anonymous API access stays unauthenticated; and
- public static guides and reports redirect anonymous users to `/login`.

For a release retry or a different environment, run the **CI** workflow
manually and enter `deployment_origin`. The job is deliberately skipped on
main until the repository variable is configured, so a missing production URL
does not create a false pass.

## Authenticated browser E2E

Run `npm run test:e2e` from `frontend/` against staging or production after a
deployment. Supply `E2E_BASE_URL`, `E2E_LOGIN_ID`, and `E2E_LOGIN_PASSWORD`
as protected CI secrets. The test verifies anonymous protection, real login
cookie issuance, report-drawer interaction, and the brand-report route.

For GitHub Actions, configure `DEPLOYMENT_ORIGIN` as the `production`
environment variable and `E2E_LOGIN_ID` / `E2E_LOGIN_PASSWORD` as
`production` environment secrets. The `deployment-e2e` job runs after the
deployed smoke test and deliberately fails if either credential is absent.
