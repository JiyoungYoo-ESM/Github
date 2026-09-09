"""In-memory sliding-window rate limiter.

Single-process only, like the session store (see ``auth.py``). Before running
multiple workers this must move to a shared backend (Redis) or each worker will
enforce its own separate limit. Intended as best-effort brute-force mitigation,
not an authorization control."""

from __future__ import annotations

import threading
import time
from uuid import uuid4

from fastapi import Request
from backend.services.request_security import client_ip_from_request
from backend.services import shared_redis


class SlidingWindowRateLimiter:
    """Allow at most ``max_events`` per ``window_seconds`` for a given key."""

    def __init__(self, max_events: int, window_seconds: int) -> None:
        self._max = max_events
        self._window = window_seconds
        self._lock = threading.Lock()
        self._events: dict[str, list[float]] = {}

    def check_and_record(self, key: str) -> bool:
        """Record an event for ``key`` and return whether it is within the limit.

        Returns ``False`` (and does not record) once the window is full, so a
        blocked caller cannot keep pushing the window forward."""
        now = time.time()
        cutoff = now - self._window
        with self._lock:
            bucket = [t for t in self._events.get(key, ()) if t >= cutoff]
            if len(bucket) >= self._max:
                self._events[key] = bucket
                return False
            bucket.append(now)
            self._events[key] = bucket
            return True

    def reset(self, key: str | None = None) -> None:
        """Forget one key, or all keys when ``key`` is ``None`` (test hook)."""
        with self._lock:
            if key is None:
                self._events.clear()
            else:
                self._events.pop(key, None)


class RedisSlidingWindowRateLimiter:
    """Atomic Redis sorted-set limiter shared by every backend worker."""

    _SCRIPT = """
local now = tonumber(ARGV[1])
local cutoff = now - tonumber(ARGV[2])
local maximum = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cutoff)
if redis.call('ZCARD', KEYS[1]) >= maximum then return 0 end
redis.call('ZADD', KEYS[1], now, ARGV[4])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
return 1
"""

    def __init__(self, max_events: int, window_seconds: int, namespace: str = "login-rate") -> None:
        self._max = max_events
        self._window = window_seconds
        self._namespace = namespace
        self._keys: set[str] = set()

    def _key(self, value: str) -> str:
        return shared_redis.key(f"{self._namespace}:{value}")

    def check_and_record(self, value: str) -> bool:
        redis_key = self._key(value)
        try:
            allowed = shared_redis.client().eval(
                self._SCRIPT,
                1,
                redis_key,
                time.time(),
                self._window,
                self._max,
                uuid4().hex,
            )
        except Exception as exc:
            raise shared_redis.RedisUnavailable("Login rate limiter is unavailable.") from exc
        self._keys.add(redis_key)
        return bool(allowed)

    def reset(self, value: str | None = None) -> None:
        keys = [self._key(value)] if value is not None else list(self._keys)
        if not keys:
            return
        try:
            shared_redis.client().delete(*keys)
        except Exception as exc:
            raise shared_redis.RedisUnavailable("Login rate limiter is unavailable.") from exc


def login_rate_limiter(max_events: int, window_seconds: int) -> SlidingWindowRateLimiter | RedisSlidingWindowRateLimiter:
    return (
        RedisSlidingWindowRateLimiter(max_events, window_seconds)
        if shared_redis.enabled()
        else SlidingWindowRateLimiter(max_events, window_seconds)
    )


def client_ip(request: Request) -> str:
    """Best-effort client IP for rate-limit keying.

    Honors the left-most ``X-Forwarded-For`` entry so that behind a reverse
    proxy each real client is limited separately (without it, every request
    would share the proxy's IP). Note this header is client-controllable and so
    can be spoofed to dodge the limit — acceptable for brute-force mitigation,
    not for anything security-critical. Falls back to the direct peer address."""
    return client_ip_from_request(request)
