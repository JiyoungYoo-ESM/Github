"""Account login and opaque server-side session endpoints.

These three endpoints are public (a caller must be able to log in before it has
a session). Entity data APIs are gated by ``require_entity_access`` in
``backend.main``; the current-user response exposes only the caller's public
profile and allowed entities."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from backend.config import (
    AUTH_SESSION_COOKIE,
    IS_PRODUCTION,
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
)
from backend.schemas import AuthActionResponse, AuthStatusResponse
from backend.entities import public_entity_definitions
from backend.auth.amount_permissions import can_view_amount_data
from backend.services.audit import write_audit_event
from backend.services.auth import (
    create_session,
    current_user_or_none,
    revoke_session,
    verify_credentials,
)
from backend.services.rate_limit import SlidingWindowRateLimiter, client_ip, login_rate_limiter
from backend.services.shared_redis import RedisUnavailable
from backend.services.request_security import require_safe_browser_origin

router = APIRouter()

# IP당 로그인 시도 제한기. 프로세스 로컬(단일 워커 전제) — auth.py 모듈 주석 참고.
_login_limiter = login_rate_limiter(
    max_events=LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    window_seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS,
)


class LoginRequest(BaseModel):
    id: str
    password: str


@router.post("/api/auth/login", response_model=AuthActionResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, bool]:
    require_safe_browser_origin(request)
    login_id = payload.id.strip()
    rate_limit_key = f"{client_ip(request)}:{login_id.casefold() or '(empty)'}"
    try:
        allowed = _login_limiter.check_and_record(rate_limit_key)
    except RedisUnavailable as exc:
        raise HTTPException(status_code=503, detail="Login protection is temporarily unavailable.") from exc
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.",
            headers={"Retry-After": str(LOGIN_RATE_LIMIT_WINDOW_SECONDS)},
        )
    account = verify_credentials(login_id, payload.password)
    if account is None:
        write_audit_event("login_failed", request, username=login_id, result="invalid_credentials")
        raise HTTPException(status_code=401, detail="invalid_credentials")
    try:
        _login_limiter.reset(rate_limit_key)
    except RedisUnavailable as exc:
        raise HTTPException(status_code=503, detail="Login protection is temporarily unavailable.") from exc
    # Rotate the browser session on successful login so an older cookie cannot
    # remain usable after re-authentication on this device.
    revoke_session(request.cookies.get(AUTH_SESSION_COOKIE))
    token, max_age = create_session(account)
    response.set_cookie(
        AUTH_SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=IS_PRODUCTION,
        path="/",
    )
    write_audit_event("login_succeeded", request, username=account.username, result="success")
    return {"ok": True}


@router.get("/api/auth/me", response_model=AuthStatusResponse)
def me(request: Request) -> dict[str, object]:
    account = current_user_or_none(request)
    if account is None:
        raise HTTPException(status_code=401, detail="unauthenticated")
    amount_allowed = can_view_amount_data(account)
    return {
        "authenticated": True,
        **account.public_dict(),
        "entities": public_entity_definitions(account.allowed_entities),
        "permissions": {
            "canViewAmountData": amount_allowed,
            "canDownloadAmountData": amount_allowed,
            "canExportAmountReport": amount_allowed,
        },
    }


@router.post("/api/auth/logout", response_model=AuthActionResponse)
def logout(request: Request, response: Response) -> dict[str, bool]:
    require_safe_browser_origin(request)
    token = request.cookies.get(AUTH_SESSION_COOKIE)
    account = current_user_or_none(request)
    revoke_session(token)
    response.delete_cookie(AUTH_SESSION_COOKIE, path="/")
    write_audit_event("logout", request, username=account.username if account else None, result="success")
    return {"ok": True}
