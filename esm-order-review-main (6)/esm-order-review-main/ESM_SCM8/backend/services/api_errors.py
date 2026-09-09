"""Uniform API error envelopes and request correlation IDs."""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from backend.services.observability import log_exception

STATUS_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_server_error",
    502: "upstream_error",
    503: "service_unavailable",
    504: "timeout",
}
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


def request_id_for(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return str(request_id)
    request_id = uuid4().hex
    request.state.request_id = request_id
    return request_id


def error_response(
    request: Request,
    *,
    status_code: int,
    message: str,
    code: str | None = None,
    details: Any | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = request_id_for(request)
    error_code = code or STATUS_ERROR_CODES.get(status_code, "request_failed")
    response_headers = dict(headers or {})
    response_headers["X-Request-Id"] = request_id
    return JSONResponse(
        status_code=status_code,
        headers=response_headers,
        content={
            "detail": message,
            "error": {
                "code": error_code,
                "message": message,
                "status": status_code,
                "request_id": request_id,
                "details": details,
            },
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, str):
        message = detail
        code = detail if CODE_PATTERN.fullmatch(detail) else None
        details = None
    else:
        message = "요청을 처리할 수 없습니다."
        code = None
        details = detail
    return error_response(
        request,
        status_code=exc.status_code,
        message=message,
        code=code,
        details=details,
        headers=exc.headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        request,
        status_code=422,
        code="validation_error",
        message="요청 값이 올바르지 않습니다.",
        details=exc.errors(),
    )


async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log_exception(
        "unhandled_api_error",
        request_id=request_id_for(request),
        method=request.method,
        path=request.url.path,
        error_type=type(exc).__name__,
    )
    return error_response(
        request,
        status_code=500,
        code="internal_server_error",
        message="서버 내부 오류가 발생했습니다.",
    )
