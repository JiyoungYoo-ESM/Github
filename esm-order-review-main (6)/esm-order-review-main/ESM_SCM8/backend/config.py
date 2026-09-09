"""Backend configuration: storage paths, upload constraints and environment
driven runtime limits. Imported by the service and router modules so that the
FastAPI app composition (``backend.main``) stays thin."""

from __future__ import annotations

import os
import re
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent
# 관리자 비밀번호 등 커밋하면 안 되는 값은 backend/.env(gitignore 대상)에 둔다.
# 파일이 없으면 조용히 넘어가고, 이미 설정된 OS 환경변수가 있으면 그걸 우선한다.
load_dotenv(BACKEND_ROOT / ".env")
_storage_root_env = os.environ.get("SCM_STORAGE_DIR", "").strip()
# Production must supply a mounted persistent volume here. Development keeps
# the repository-local storage directory for convenience.
STORAGE_ROOT = Path(_storage_root_env or BACKEND_ROOT / "storage")
UPLOAD_DIR = STORAGE_ROOT / "uploads"
OUTPUT_DIR = STORAGE_ROOT / "outputs"
AUDIT_DIR = STORAGE_ROOT / "audit"
CMS_FETCH_CACHE_DIR = STORAGE_ROOT / "cms_fetch_cache"
LATEST_ORDER_REVIEW_DIR = STORAGE_ROOT / "latest_order_review"
LATEST_ORDER_LOGIC_V2_DIR = STORAGE_ROOT / "latest_order_logic_v2"
LATEST_SEASON_TREND_DIR = STORAGE_ROOT / "latest_season_trend"
ORDER_LOGIC_V3_SEASON_FACTOR_DIR = STORAGE_ROOT / "order_logic_v3_season_factors"
SUPPORT_ATTACHMENT_DIR = Path(
    os.environ.get(
        "SCM_SUPPORT_ATTACHMENT_DIR",
        str(STORAGE_ROOT / "support_attachments"),
    )
)
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL and os.environ.get("PGHOST", "").strip():
    # ECS/RDS injects connection parts as discrete PG* env vars (host/port from
    # the RDS-generated secret, PGPASSWORD from Secrets Manager). Assemble the
    # single DATABASE_URL the app and Alembic expect, URL-encoding credentials.
    from urllib.parse import quote as _pg_quote

    _pg_user = _pg_quote(os.environ.get("PGUSER", "").strip(), safe="")
    _pg_pw = _pg_quote(os.environ.get("PGPASSWORD", "").strip(), safe="")
    _pg_auth = f"{_pg_user}:{_pg_pw}@" if _pg_user else ""
    _pg_port = os.environ.get("PGPORT", "5432").strip() or "5432"
    DATABASE_URL = (
        f"postgresql://{_pg_auth}{os.environ['PGHOST'].strip()}:{_pg_port}"
        f"/{os.environ.get('PGDATABASE', '').strip()}"
    )
REDIS_URL = os.environ.get("REDIS_URL", "").strip()
REDIS_KEY_PREFIX = os.environ.get("SCM_REDIS_KEY_PREFIX", "esm_scm").strip() or "esm_scm"
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL).strip()
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL).strip()
# Keep the process hard limit outside the analysis-level timeout.  When both
# limits were 1,800 seconds, Celery could kill the worker before the service
# persisted a terminal job state, leaving the browser polling ``running``.
CELERY_TASK_TIME_LIMIT_SECONDS = int(os.environ.get("CELERY_TASK_TIME_LIMIT_SECONDS", "2100"))
CELERY_TASK_MAX_RETRIES = int(os.environ.get("CELERY_TASK_MAX_RETRIES", "3"))
CELERY_TASK_RETRY_BACKOFF_SECONDS = int(os.environ.get("CELERY_TASK_RETRY_BACKOFF_SECONDS", "30"))
ANALYSIS_WORKER_GRACE_SECONDS = int(
    os.environ.get("SCM_ANALYSIS_WORKER_GRACE_SECONDS", "60")
)
V3_LOCAL_WORKER_CONCURRENCY = int(os.environ.get("SCM_V3_LOCAL_WORKER_CONCURRENCY", "1"))
SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
SENTRY_RELEASE = os.environ.get("SENTRY_RELEASE", "").strip()
OBJECT_STORAGE_BUCKET = os.environ.get("OBJECT_STORAGE_BUCKET", "").strip()
OBJECT_STORAGE_ENDPOINT_URL = os.environ.get("OBJECT_STORAGE_ENDPOINT_URL", "").strip()
OBJECT_STORAGE_REGION = os.environ.get("OBJECT_STORAGE_REGION", "auto").strip() or "auto"
OBJECT_STORAGE_ACCESS_KEY_ID = os.environ.get("OBJECT_STORAGE_ACCESS_KEY_ID", "").strip()
OBJECT_STORAGE_SECRET_ACCESS_KEY = os.environ.get("OBJECT_STORAGE_SECRET_ACCESS_KEY", "").strip()
OBJECT_STORAGE_PREFIX = os.environ.get("OBJECT_STORAGE_PREFIX", "esm-scm").strip().strip("/")
OBJECT_STORAGE_PRESIGN_SECONDS = int(os.environ.get("OBJECT_STORAGE_PRESIGN_SECONDS", "300"))
OBJECT_STORAGE_FORCE_PATH_STYLE = os.environ.get("OBJECT_STORAGE_FORCE_PATH_STYLE", "false").strip().lower() in {"1", "true", "yes", "on"}
OBJECT_STORAGE_OUTPUT_RETENTION_DAYS = int(os.environ.get("OBJECT_STORAGE_OUTPUT_RETENTION_DAYS", "1"))
OBJECT_STORAGE_SUPPORT_RETENTION_DAYS = int(os.environ.get("OBJECT_STORAGE_SUPPORT_RETENTION_DAYS", "90"))
SUPPORT_MAX_ATTACHMENT_BYTES = int(
    os.environ.get("SCM_SUPPORT_MAX_ATTACHMENT_MB", "15")
) * 1024 * 1024
# 보고서 장바구니 템플릿. 파일이 있으면 템플릿 UIUX를 유지해 데이터만 교체하고,
# 없으면 코드 생성형 섹션 덱으로 fallback한다.
# 기본값은 레포에 포함된 backend/assets 사본이라 배포/다른 PC에서도 동일하게 동작한다.
# 다른 템플릿을 쓰려면 SCM_REPORT_CART_TEMPLATE_PPTX 환경변수로 경로를 지정한다.
REPORT_CART_TEMPLATE_PPTX = Path(
    os.environ.get(
        "SCM_REPORT_CART_TEMPLATE_PPTX",
        str(BACKEND_ROOT / "assets" / "report_cart_template.pptx"),
    )
)
# 보고서 장바구니 익명화에서 자사 브랜드로 취급할 이름 목록.
# 프론트가 snapshot row에 brand_role="self"를 넣는 것이 우선이며, 이 값은 구버전 요청의 fallback이다.
SCM_REPORT_SELF_BRAND = os.environ.get("SCM_REPORT_SELF_BRAND", "아누아,Anua,ANUA")

ALLOWED_EXCEL_EXTENSIONS = {".xlsx", ".xls", ".xlsm"}
JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
DOWNLOAD_META_FILENAME = "download_meta.json"

STORAGE_MAX_AGE_HOURS = int(os.environ.get("SCM_STORAGE_MAX_AGE_HOURS", "24"))
STORAGE_CLEANUP_INTERVAL_SECONDS = int(os.environ.get("SCM_STORAGE_CLEANUP_INTERVAL_SECONDS", "900"))
JOB_RETENTION_HOURS = int(os.environ.get("SCM_JOB_RETENTION_HOURS", "24"))
JOB_MAX_RETAINED = int(os.environ.get("SCM_JOB_MAX_RETAINED", "20"))
AUDIT_RETENTION_DAYS = int(os.environ.get("SCM_AUDIT_RETENTION_DAYS", "90"))
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV in {"prod", "production"}
MAX_CONCURRENT_ANALYSES = int(os.environ.get("SCM_MAX_CONCURRENT_ANALYSES", "2"))
MAX_ANALYSES_PER_CLIENT = int(os.environ.get("SCM_MAX_ANALYSES_PER_CLIENT", "1"))
MAX_UPLOAD_FILE_BYTES = int(os.environ.get("SCM_MAX_UPLOAD_FILE_MB", "100")) * 1024 * 1024
MAX_UPLOAD_TOTAL_BYTES = int(os.environ.get("SCM_MAX_UPLOAD_TOTAL_MB", "300")) * 1024 * 1024
MAX_UPLOAD_FILES = int(os.environ.get("SCM_MAX_UPLOAD_FILES", "10"))
UPLOAD_CHUNK_BYTES = int(os.environ.get("SCM_UPLOAD_CHUNK_MB", "1")) * 1024 * 1024
ANALYSIS_TIMEOUT_SECONDS = int(os.environ.get("SCM_ANALYSIS_TIMEOUT_SECONDS", "180"))
# CMS API는 판매내역 페이지네이션(10만 행 이상)으로 fetch에만 3~4분 걸릴 수 있음
CMS_ANALYSIS_TIMEOUT_SECONDS = int(os.environ.get("SCM_CMS_ANALYSIS_TIMEOUT_SECONDS", "600"))
SEASON_ANALYSIS_TIMEOUT_SECONDS = int(
    os.environ.get("SCM_SEASON_ANALYSIS_TIMEOUT_SECONDS", "1800")
)
ORDER_LOGIC_V3_ANALYSIS_TIMEOUT_SECONDS = int(
    os.environ.get("SCM_ORDER_LOGIC_V3_ANALYSIS_TIMEOUT_SECONDS", "1800")
)
# A worker can be terminated by the OS or Celery without executing a Python
# exception handler.  Polling a job after this boundary converts such an
# orphaned ``running`` record into an explicit failure before Redis redelivery.
ANALYSIS_JOB_STALE_SECONDS = int(
    os.environ.get(
        "SCM_ANALYSIS_JOB_STALE_SECONDS",
        str(CELERY_TASK_TIME_LIMIT_SECONDS + ANALYSIS_WORKER_GRACE_SECONDS),
    )
)
ANALYSIS_SLOT_TTL_SECONDS = int(os.environ.get("SCM_ANALYSIS_SLOT_TTL_SECONDS", "2400"))


def bounded_worker_timeout_seconds(configured_seconds: float) -> float:
    """Leave time for a queued worker to persist failure before hard exit.

    Local development has no Celery hard limit, so its configured timeout is
    returned unchanged.  This also protects deployments that still override
    the old 1,800-second Celery value in their environment.
    """

    if not CELERY_BROKER_URL:
        return configured_seconds
    return min(
        configured_seconds,
        max(float(CELERY_TASK_TIME_LIMIT_SECONDS - ANALYSIS_WORKER_GRACE_SECONDS), 1.0),
    )


MAX_CONCURRENT_REPORT_EXPORTS = int(os.environ.get("SCM_MAX_CONCURRENT_REPORT_EXPORTS", "1"))
REPORT_EXPORT_TIMEOUT_SECONDS = int(os.environ.get("SCM_REPORT_EXPORT_TIMEOUT_SECONDS", "180"))
REPORT_MAX_REQUEST_BYTES = int(os.environ.get("SCM_REPORT_MAX_REQUEST_MB", "25")) * 1024 * 1024
REPORT_MAX_OUTPUT_BYTES = int(os.environ.get("SCM_REPORT_MAX_OUTPUT_MB", "100")) * 1024 * 1024
SLOW_REQUEST_THRESHOLD_MS = int(os.environ.get("SCM_SLOW_REQUEST_THRESHOLD_MS", "1000"))
# 오늘 날짜(as_of=오늘) CMS raw 캐시의 TTL.
# - 같은 as_of/date_from/date_to/logistics_date_from 조합이면 이 시간 동안 CMS API를
#   다시 부르지 않고 memory/disk 캐시를 재사용한다(uncached 130~180초 → 캐시 시 20~30초대).
# - 과거 날짜(as_of≠오늘)는 데이터가 확정이라 TTL 없이 무기한 재사용한다.
# - 값을 줄이면 "당일 최신 데이터 반영"이 빨라지는 대신 반복 분석마다 2~3분 fetch를 다시 기다린다.
CMS_TODAY_CACHE_TTL_SECONDS = int(os.environ.get("SCM_CMS_TODAY_CACHE_TTL_SECONDS", "14400"))
# 디스크 캐시 파일 보관 일수. 만료 파일은 같은 조건을 다시 조회할 때만 지워지므로(lazy delete),
# 다시는 요청되지 않는 키(지난 날짜 기준 캐시, 일회성 기간 캐시)의 파일이 무한히 쌓인다.
# 이 값보다 오래된 파일은 서버 기동 시와 프리페치 사이클마다 정리한다. 0 이하면 정리 안 함.
CMS_FETCH_CACHE_MAX_AGE_DAYS = int(os.environ.get("SCM_CMS_FETCH_CACHE_MAX_AGE_DAYS", "7"))
# 기본 OFF: 업무시간(KST 8-20시) 동안 오늘자 CMS 데이터를 미리 받으려면
# SCM_PRE_ANALYSIS_ENABLED=true로 명시적으로 켠다.
SCM_PRE_ANALYSIS_ENABLED = os.environ.get("SCM_PRE_ANALYSIS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
SCM_PRE_ANALYSIS_INTERVAL_SECONDS = int(os.environ.get("SCM_PRE_ANALYSIS_INTERVAL_SECONDS", "1500"))
SCM_PRE_ANALYSIS_HOURS_KST = os.environ.get("SCM_PRE_ANALYSIS_HOURS_KST", "8-20").strip()
SCM_V3_SEASON_FACTOR_MONTHLY_ENABLED = os.environ.get(
    "SCM_V3_SEASON_FACTOR_MONTHLY_ENABLED",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}
_v3_season_factor_monthly_day = os.environ.get(
    "SCM_V3_SEASON_FACTOR_MONTHLY_DAY",
    "",
).strip()
SCM_V3_SEASON_FACTOR_MONTHLY_DAY = (
    int(_v3_season_factor_monthly_day)
    if _v3_season_factor_monthly_day
    else None
)
_v3_season_factor_monthly_hour = os.environ.get(
    "SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST",
    "",
).strip()
SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST = (
    int(_v3_season_factor_monthly_hour)
    if _v3_season_factor_monthly_hour
    else None
)
SCM_V3_SEASON_FACTOR_CHECK_INTERVAL_SECONDS = int(
    os.environ.get("SCM_V3_SEASON_FACTOR_CHECK_INTERVAL_SECONDS", "900")
)
DOWNLOAD_WAIT_FOR_OUTPUT_SECONDS = int(os.environ.get("SCM_DOWNLOAD_WAIT_FOR_OUTPUT_SECONDS", "90"))

# 인증은 backend.auth.user_store의 9개 계정 정의와 AUTH_*_PASSWORD_HASH
# 환경변수를 사용한다. 평문 비밀번호 설정은 더 이상 읽지 않는다.
AUTH_SESSION_COOKIE = "s2_session"
AUTH_SESSION_MAX_AGE_SECONDS = int(os.environ.get("SCM_AUTH_SESSION_DAYS", "30")) * 86400
# 로그인 무차별 대입 완화: 한 IP가 창 시간 동안 허용되는 최대 로그인 시도 횟수.
# 초과하면 429로 거절한다. 사내망에선 사실상 무의미하지만 외부 노출 시 크리덴셜
# 스터핑을 늦춘다. 정상 사용자의 오타 재시도(기본 10회/5분)는 넉넉히 허용한다.
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = int(os.environ.get("SCM_LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "10"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("SCM_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300"))

# 로컬 개발용 기본 허용 출처. 프로덕션 도메인은 FRONTEND_ORIGIN 환경변수로 주입한다.
# 예) FRONTEND_ORIGIN="https://esm.example.com,https://xxx.up.railway.app"
_DEFAULT_ALLOWED_ORIGINS = [
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
    "http://192.168.0.5:3000",
    "http://192.168.0.245:3000",
]
_extra_origins = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGIN", "").split(",")
    if origin.strip()
]
ALLOWED_ORIGINS = _DEFAULT_ALLOWED_ORIGINS + _extra_origins
_trusted_proxy_cidrs_raw = os.environ.get("SCM_TRUSTED_PROXY_CIDRS", "").strip()


def _trusted_proxy_networks() -> tuple[IPv4Network | IPv6Network, ...]:
    networks: list[IPv4Network | IPv6Network] = []
    for value in _trusted_proxy_cidrs_raw.split(","):
        if not value.strip():
            continue
        try:
            networks.append(ip_network(value.strip(), strict=False))
        except ValueError:
            continue
    return tuple(networks)


TRUSTED_PROXY_CIDRS = _trusted_proxy_networks()


class ConfigError(RuntimeError):
    """Raised at startup when the runtime configuration is invalid."""


def _origin_is_wellformed(origin: str) -> bool:
    """A CORS origin must be ``scheme://host[:port]`` with no path/query."""
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    # 경로/쿼리/프래그먼트가 붙은 값은 오리진이 아니다.
    return parsed.path in {"", "/"} and not parsed.query and not parsed.fragment


def is_allowed_browser_origin(origin: str) -> bool:
    """Exact origin comparison for credentialed browser requests."""
    return origin.rstrip("/") in {allowed.rstrip("/") for allowed in ALLOWED_ORIGINS}


def validate_config() -> None:
    """Fail fast on invalid configuration at startup instead of surfacing the
    problem only when a request hits the broken path.

    Raises :class:`ConfigError` listing every problem found. Called from
    ``backend.main`` at import time so the server refuses to start misconfigured."""
    problems: list[str] = []

    if APP_ENV not in {"development", "dev", "test", "production", "prod"}:
        problems.append("APP_ENV must be one of development, test, or production.")

    # 숫자 설정은 개발/운영 공통으로 양수여야 한다.
    positive_ints = {
        "SCM_MAX_UPLOAD_FILE_MB": MAX_UPLOAD_FILE_BYTES,
        "SCM_MAX_UPLOAD_TOTAL_MB": MAX_UPLOAD_TOTAL_BYTES,
        "SCM_MAX_UPLOAD_FILES": MAX_UPLOAD_FILES,
        "SCM_ANALYSIS_TIMEOUT_SECONDS": ANALYSIS_TIMEOUT_SECONDS,
        "SCM_CMS_ANALYSIS_TIMEOUT_SECONDS": CMS_ANALYSIS_TIMEOUT_SECONDS,
        "SCM_SEASON_ANALYSIS_TIMEOUT_SECONDS": SEASON_ANALYSIS_TIMEOUT_SECONDS,
        "SCM_ORDER_LOGIC_V3_ANALYSIS_TIMEOUT_SECONDS": ORDER_LOGIC_V3_ANALYSIS_TIMEOUT_SECONDS,
        "SCM_ANALYSIS_WORKER_GRACE_SECONDS": ANALYSIS_WORKER_GRACE_SECONDS,
        "SCM_ANALYSIS_JOB_STALE_SECONDS": ANALYSIS_JOB_STALE_SECONDS,
        "SCM_ANALYSIS_SLOT_TTL_SECONDS": ANALYSIS_SLOT_TTL_SECONDS,
        "SCM_MAX_CONCURRENT_ANALYSES": MAX_CONCURRENT_ANALYSES,
        "SCM_LOGIN_RATE_LIMIT_MAX_ATTEMPTS": LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
        "SCM_LOGIN_RATE_LIMIT_WINDOW_SECONDS": LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        "SCM_AUTH_SESSION_DAYS": AUTH_SESSION_MAX_AGE_SECONDS,
        "SCM_SUPPORT_MAX_ATTACHMENT_MB": SUPPORT_MAX_ATTACHMENT_BYTES,
        "SCM_SLOW_REQUEST_THRESHOLD_MS": SLOW_REQUEST_THRESHOLD_MS,
        "SCM_V3_SEASON_FACTOR_CHECK_INTERVAL_SECONDS": SCM_V3_SEASON_FACTOR_CHECK_INTERVAL_SECONDS,
        "SCM_V3_LOCAL_WORKER_CONCURRENCY": V3_LOCAL_WORKER_CONCURRENCY,
    }
    for name, value in positive_ints.items():
        if value <= 0:
            problems.append(f"{name} 값은 0보다 커야 합니다 (현재 {value}).")

    if MAX_UPLOAD_TOTAL_BYTES < MAX_UPLOAD_FILE_BYTES:
        problems.append(
            "SCM_MAX_UPLOAD_TOTAL_MB는 SCM_MAX_UPLOAD_FILE_MB보다 작을 수 없습니다."
        )

    if ANALYSIS_SLOT_TTL_SECONDS <= max(
        ANALYSIS_TIMEOUT_SECONDS,
        CMS_ANALYSIS_TIMEOUT_SECONDS,
        SEASON_ANALYSIS_TIMEOUT_SECONDS,
        ORDER_LOGIC_V3_ANALYSIS_TIMEOUT_SECONDS,
        CELERY_TASK_TIME_LIMIT_SECONDS,
    ):
        problems.append(
            "SCM_ANALYSIS_SLOT_TTL_SECONDS must exceed every analysis timeout so a live job keeps its Redis lease."
        )

    if not 0 <= SENTRY_TRACES_SAMPLE_RATE <= 1:
        problems.append("SENTRY_TRACES_SAMPLE_RATE must be between 0 and 1.")
    if SENTRY_DSN:
        sentry_dsn = urlparse(SENTRY_DSN)
        if (
            sentry_dsn.scheme not in {"http", "https"}
            or not sentry_dsn.hostname
            or not sentry_dsn.username
            or not sentry_dsn.path.strip("/")
        ):
            problems.append("SENTRY_DSN must be a valid Sentry DSN URL.")
    if OBJECT_STORAGE_ENDPOINT_URL:
        endpoint = urlparse(OBJECT_STORAGE_ENDPOINT_URL)
        if endpoint.scheme not in {"http", "https"} or not endpoint.netloc:
            problems.append("OBJECT_STORAGE_ENDPOINT_URL must be an http(s) URL.")
    if OBJECT_STORAGE_PREFIX and (".." in OBJECT_STORAGE_PREFIX.split("/") or "\\" in OBJECT_STORAGE_PREFIX):
        problems.append("OBJECT_STORAGE_PREFIX must be a safe slash-separated prefix.")
    if OBJECT_STORAGE_PRESIGN_SECONDS <= 0:
        problems.append("OBJECT_STORAGE_PRESIGN_SECONDS must be greater than 0.")
    if OBJECT_STORAGE_OUTPUT_RETENTION_DAYS <= 0 or OBJECT_STORAGE_SUPPORT_RETENTION_DAYS <= 0:
        problems.append("Object storage retention days must be greater than 0.")
    if CELERY_TASK_TIME_LIMIT_SECONDS <= 0:
        problems.append("CELERY_TASK_TIME_LIMIT_SECONDS must be greater than 0.")
    if ANALYSIS_WORKER_GRACE_SECONDS >= CELERY_TASK_TIME_LIMIT_SECONDS:
        problems.append(
            "SCM_ANALYSIS_WORKER_GRACE_SECONDS must be shorter than CELERY_TASK_TIME_LIMIT_SECONDS."
        )
    if ANALYSIS_JOB_STALE_SECONDS <= max(
        CELERY_TASK_TIME_LIMIT_SECONDS,
        SEASON_ANALYSIS_TIMEOUT_SECONDS,
        ORDER_LOGIC_V3_ANALYSIS_TIMEOUT_SECONDS,
    ):
        problems.append(
            "SCM_ANALYSIS_JOB_STALE_SECONDS must exceed the worker and analysis time limits."
        )
    if CELERY_TASK_MAX_RETRIES < 0 or CELERY_TASK_RETRY_BACKOFF_SECONDS <= 0:
        problems.append("Celery retry settings must be non-negative retries and a positive backoff.")

    if SCM_V3_SEASON_FACTOR_MONTHLY_ENABLED:
        if SCM_V3_SEASON_FACTOR_MONTHLY_DAY is None:
            problems.append(
                "SCM_V3_SEASON_FACTOR_MONTHLY_DAY must be configured when monthly season-factor refresh is enabled."
            )
        elif not 1 <= SCM_V3_SEASON_FACTOR_MONTHLY_DAY <= 28:
            problems.append("SCM_V3_SEASON_FACTOR_MONTHLY_DAY must be between 1 and 28.")
        if SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST is None:
            problems.append(
                "SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST must be configured when monthly season-factor refresh is enabled."
            )
        elif not 0 <= SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST <= 23:
            problems.append("SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST must be between 0 and 23.")

    # CORS 오리진 형식 검증(공통) + 와일드카드 금지.
    for origin in ALLOWED_ORIGINS:
        if origin == "*":
            problems.append("CORS 허용 오리진에 와일드카드('*')는 허용되지 않습니다.")
        elif not _origin_is_wellformed(origin):
            problems.append(f"잘못된 CORS 오리진 형식입니다: {origin!r}")

    if _trusted_proxy_cidrs_raw:
        try:
            for value in _trusted_proxy_cidrs_raw.split(","):
                if value.strip():
                    ip_network(value.strip(), strict=False)
        except ValueError:
            problems.append("SCM_TRUSTED_PROXY_CIDRS must contain comma-separated IP networks.")

    # 운영 환경 전용 강제 조건.
    if IS_PRODUCTION:
        if not DATABASE_URL:
            problems.append("DATABASE_URL must be configured in production.")
        # Redis/Celery/Sentry are optional: without REDIS_URL the app falls back
        # to in-memory rate limiting and concurrency (single replica) and runs
        # analyses in-process; Sentry stays disabled when SENTRY_DSN is empty.
        if not OBJECT_STORAGE_BUCKET:
            problems.append("OBJECT_STORAGE_BUCKET must be configured in production.")
        if not _storage_root_env:
            problems.append(
                "SCM_STORAGE_DIR must point to a mounted persistent volume in production."
            )
        prod_origins = [o for o in _extra_origins if _origin_is_wellformed(o)]
        if not prod_origins:
            problems.append(
                "운영 환경에서는 FRONTEND_ORIGIN에 실제 프론트 도메인을 1개 이상 "
                "지정해야 합니다 (예: https://esm.example.com)."
            )

    if problems:
        raise ConfigError(
            "설정 오류로 서버를 시작할 수 없습니다:\n  - " + "\n  - ".join(problems)
        )
