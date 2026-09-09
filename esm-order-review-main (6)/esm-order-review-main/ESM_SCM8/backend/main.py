"""FastAPI application composition.

Configuration lives in ``backend.config``, request/response models in
``backend.schemas``, reusable helpers in ``backend.services`` and the endpoints
in ``backend.routers``. This module only wires those pieces together."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.config import (
    ALLOWED_ORIGINS,
    IS_PRODUCTION,
    REPORT_MAX_REQUEST_BYTES,
    SLOW_REQUEST_THRESHOLD_MS,
    validate_config,
)
from backend.routers import ai, analysis, auth, cms, corporate_inventory, health, order_logic_v2, order_logic_v3, reference, reports, season, support, uploads
from backend.schemas import ApiErrorDetail, ApiErrorResponse
from backend.services.api_errors import (
    http_exception_handler,
    request_id_for,
    unexpected_exception_handler,
    validation_exception_handler,
)
from backend.services.auth import require_authenticated_user
from backend.auth.permissions import require_entity_access, require_order_analysis_access
from backend.auth.user_store import get_user_store, validate_user_store
from backend.services.cms_prefetch import start_cms_prefetch_task
from backend.services.housekeeping import run_storage_housekeeping, storage_housekeeping_loop
from backend.services.order_logic_v3_season_factor_scheduler import (
    start_season_factor_monthly_task,
)
from backend.services.storage import ensure_storage_dirs
from backend.services.observability import configure_observability, log_event, request_metrics
from backend.services.monitoring import configure_monitoring


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 보관 일수를 넘긴 CMS raw 캐시 파일 정리. 실패해도 기동은 막지 않는다.
    with suppress(Exception):
        await asyncio.to_thread(run_storage_housekeeping)
    housekeeping_task = asyncio.create_task(storage_housekeeping_loop())
    prefetch_task = start_cms_prefetch_task()
    season_factor_task = start_season_factor_monthly_task()
    try:
        yield
    finally:
        housekeeping_task.cancel()
        with suppress(asyncio.CancelledError):
            await housekeeping_task
        if prefetch_task is not None:
            prefetch_task.cancel()
            with suppress(asyncio.CancelledError):
                await prefetch_task
        if season_factor_task is not None:
            season_factor_task.cancel()
            with suppress(asyncio.CancelledError):
                await season_factor_task


# 잘못된 설정으로는 서버가 뜨지 않게 기동 시점에 즉시 검증한다(fail-fast).
validate_config()
validate_user_store(get_user_store(), require_all_hashes=IS_PRODUCTION)
configure_observability()
configure_monitoring()

app = FastAPI(
    title="ESM SCM Backend",
    version="0.1.0",
    description="FastAPI skeleton for the existing ESM SCM calculation core.",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
    lifespan=lifespan,
)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unexpected_exception_handler)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    supplied_request_id = request.headers.get("X-Request-Id", "").strip()
    request_id = (
        supplied_request_id
        if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", supplied_request_id)
        else request_id_for(request)
    )
    request.state.request_id = request_id
    request_metrics.begin()
    started_at = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Response-Time-Ms"] = str(round((time.perf_counter() - started_at) * 1000, 2))
        return response
    finally:
        duration_ms = (time.perf_counter() - started_at) * 1000
        slow = duration_ms >= SLOW_REQUEST_THRESHOLD_MS
        request_metrics.complete(status_code, duration_ms, slow=slow)
        log_event(
            logging.WARNING if slow or status_code >= 500 else logging.INFO,
            "http_request_completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=round(duration_ms, 2),
            slow=slow,
        )


@app.middleware("http")
async def limit_report_request_body(request: Request, call_next):
    if request.url.path == "/api/reports/export":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                exceeds_limit = int(content_length) > REPORT_MAX_REQUEST_BYTES
            except ValueError:
                exceeds_limit = True
            if exceeds_limit:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "보고서 요청 데이터가 서버 허용 크기를 초과했습니다."},
                )
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # 로그인 세션 쿠키를 브라우저가 보내려면 credentials 허용이 필요하다. allow_origins가
    # 명시적 목록(와일드카드 아님)이라 브라우저 CORS 스펙과 충돌하지 않는다. 다른 API 호출은
    # credentials를 안 보내므로(기존 fetch 그대로) 이 변경으로 동작이 바뀌지 않는다.
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Client-Id", "X-Entity-Code", "X-Request-Id", "X-Requested-With"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)

# 인증 없이 접근 가능한 공개 라우터: 헬스체크/환율(health), 로그인·세션(auth).
# 모든 법인 데이터 API는 유효한 세션과 법인 권한을 함께 요구한다(require_entity_access).
# 라우터 단위로 의존성을 걸어 개별 엔드포인트 누락을 원천 차단한다 — 새 엔드포인트를
# 법인 데이터 라우터에 추가하면 자동으로 인증·법인 권한 검증 대상이 된다.
_PUBLIC_ROUTERS = (health, auth)
_ENTITY_DATA_ROUTERS = (uploads, season, analysis, cms, ai, reports, order_logic_v2, order_logic_v3)
_ORDER_DATA_ROUTERS = (analysis, cms, ai, order_logic_v2, order_logic_v3)
_AUTHENTICATED_ROUTERS = (support, reference, corporate_inventory)

for _router_module in _PUBLIC_ROUTERS:
    app.include_router(_router_module.router)
for _router_module in _ENTITY_DATA_ROUTERS:
    _dependencies = [Depends(require_entity_access)]
    if _router_module in _ORDER_DATA_ROUTERS:
        _dependencies.append(Depends(require_order_analysis_access))
    app.include_router(
        _router_module.router,
        dependencies=_dependencies,
    )
for _router_module in _AUTHENTICATED_ROUTERS:
    app.include_router(
        _router_module.router,
        dependencies=[Depends(require_authenticated_user)],
    )


def mark_binary_upload_fields(schema: object) -> None:
    if isinstance(schema, dict):
        if schema.get("contentMediaType") == "application/octet-stream":
            schema["format"] = "binary"
            schema.pop("contentMediaType", None)

        for value in schema.values():
            mark_binary_upload_fields(value)
    elif isinstance(schema, list):
        for item in schema:
            mark_binary_upload_fields(item)


def custom_openapi() -> dict[str, object]:
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    mark_binary_upload_fields(openapi_schema)
    schemas = openapi_schema.setdefault("components", {}).setdefault("schemas", {})
    schemas["ApiErrorDetail"] = ApiErrorDetail.model_json_schema()
    api_error_schema = ApiErrorResponse.model_json_schema(
        ref_template="#/components/schemas/{model}",
    )
    api_error_schema.pop("$defs", None)
    schemas["ApiErrorResponse"] = api_error_schema
    for path_item in openapi_schema.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            operation["responses"].setdefault(
                "default",
                {
                    "description": "Standard API error",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
                        }
                    },
                },
            )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

ensure_storage_dirs()
