"""Opaque server-side sessions bound to one configured user account.

The process-local store preserves the existing single-worker deployment model,
but callers depend only on :class:`SessionStore`.  It can therefore be swapped
for Redis or a DB without changing routers or analysis code.
"""

from __future__ import annotations

import secrets
import hashlib
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from fastapi import HTTPException, Request

from backend.auth.models import UserAccount
from backend.auth.user_store import get_user_store
from backend.config import AUTH_SESSION_COOKIE, AUTH_SESSION_MAX_AGE_SECONDS
from backend import database
from backend.models.persistence import AuthSession
from backend.services.request_security import require_safe_browser_origin


@dataclass(frozen=True, slots=True)
class SessionRecord:
    username: str
    expires_at: float


class SessionStore(Protocol):
    def create(self, username: str, ttl_seconds: int) -> str: ...

    def get(self, token: str | None) -> SessionRecord | None: ...

    def revoke(self, token: str | None) -> None: ...

    def clear(self) -> None: ...


class InMemorySessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionRecord] = {}

    def create(self, username: str, ttl_seconds: int) -> str:
        token = secrets.token_urlsafe(32)
        record = SessionRecord(username=username, expires_at=time.time() + ttl_seconds)
        with self._lock:
            self._sessions[token] = record
        return token

    def get(self, token: str | None) -> SessionRecord | None:
        if not token:
            return None
        with self._lock:
            record = self._sessions.get(token)
            if record is None:
                return None
            if record.expires_at < time.time():
                del self._sessions[token]
                return None
            return record

    def revoke(self, token: str | None) -> None:
        if token:
            with self._lock:
                self._sessions.pop(token, None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


class DatabaseSessionStore:
    """Store only a SHA-256 digest of opaque session tokens at rest."""

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create(self, username: str, ttl_seconds: int) -> str:
        token = secrets.token_urlsafe(32)
        with database.get_session_factory()() as session:
            session.add(
                AuthSession(
                    token_digest=self._digest(token),
                    username=username,
                    expires_at=datetime.fromtimestamp(time.time() + ttl_seconds, timezone.utc),
                )
            )
            session.commit()
        return token

    def get(self, token: str | None) -> SessionRecord | None:
        if not token:
            return None
        with database.get_session_factory()() as session:
            row = session.get(AuthSession, self._digest(token))
            if row is None:
                return None
            expires_at = row.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                session.delete(row)
                session.commit()
                return None
            return SessionRecord(username=row.username, expires_at=expires_at.timestamp())

    def revoke(self, token: str | None) -> None:
        if not token:
            return
        with database.get_session_factory()() as session:
            row = session.get(AuthSession, self._digest(token))
            if row is not None:
                session.delete(row)
                session.commit()

    def clear(self) -> None:
        # This is intentionally a test/admin helper, not part of normal logout.
        from sqlalchemy import delete

        with database.get_session_factory()() as session:
            session.execute(delete(AuthSession))
            session.commit()


_memory_session_store: SessionStore = InMemorySessionStore()


def _session_store_for_runtime() -> SessionStore:
    return DatabaseSessionStore() if database.DATABASE_URL else _memory_session_store


def verify_credentials(login_id: str, password: str) -> UserAccount | None:
    """Authenticate through the replaceable repository; never expose hashes."""

    if not login_id or not password:
        return None
    return get_user_store().authenticate(login_id, password)


def create_session(user: UserAccount) -> tuple[str, int]:
    token = _session_store_for_runtime().create(user.username, AUTH_SESSION_MAX_AGE_SECONDS)
    return token, AUTH_SESSION_MAX_AGE_SECONDS


def session_record(token: str | None) -> SessionRecord | None:
    return _session_store_for_runtime().get(token)


def is_session_valid(token: str | None) -> bool:
    return session_record(token) is not None


def revoke_session(token: str | None) -> None:
    _session_store_for_runtime().revoke(token)


def reset_sessions() -> None:
    _session_store_for_runtime().clear()


def session_token_from(request: Request) -> str | None:
    return request.cookies.get(AUTH_SESSION_COOKIE)


def current_user_or_none(request: Request) -> UserAccount | None:
    existing = getattr(request.state, "current_user", None)
    if isinstance(existing, UserAccount):
        return existing
    record = session_record(session_token_from(request))
    if record is None:
        return None
    account = get_user_store().get(record.username)
    if account is None or not account.is_active:
        revoke_session(session_token_from(request))
        return None
    request.state.current_user = account
    return account


def is_request_authenticated(request: Request) -> bool:
    return current_user_or_none(request) is not None


_CSRF_PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = "x-requested-with"


def require_authenticated_user(request: Request) -> UserAccount:
    user = current_user_or_none(request)
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    if request.method in _CSRF_PROTECTED_METHODS:
        require_safe_browser_origin(request)
    if request.method in _CSRF_PROTECTED_METHODS and request.headers.get(CSRF_HEADER) != "fetch":
        raise HTTPException(status_code=403, detail="요청 출처를 확인할 수 없습니다.")
    return user
