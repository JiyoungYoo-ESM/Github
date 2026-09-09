"""Synchronous Redis connection shared by rate limiting and job coordination."""

from __future__ import annotations

from functools import lru_cache

from backend.config import REDIS_KEY_PREFIX, REDIS_URL


class RedisUnavailable(RuntimeError):
    pass


def enabled() -> bool:
    return bool(REDIS_URL)


@lru_cache(maxsize=1)
def client():
    if not REDIS_URL:
        raise RedisUnavailable("REDIS_URL is not configured.")
    try:
        import redis
    except ImportError as exc:  # pragma: no cover - dependency is installed in production
        raise RedisUnavailable("redis package is not installed.") from exc
    return redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
        health_check_interval=30,
    )


def key(name: str) -> str:
    return f"{REDIS_KEY_PREFIX}:{name}"


def status() -> str:
    if not enabled():
        return "not_configured"
    try:
        return "ok" if client().ping() else "unavailable"
    except Exception:
        return "unavailable"
