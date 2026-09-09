"""Shared analysis concurrency limits with a development in-memory fallback."""

from __future__ import annotations

import asyncio

from backend.config import ANALYSIS_SLOT_TTL_SECONDS, MAX_ANALYSES_PER_CLIENT, MAX_CONCURRENT_ANALYSES
from backend.services import shared_redis

_active_analysis_lock = asyncio.Lock()
_active_analysis_total = 0
_active_analysis_by_client: dict[str, int] = {}

_ACQUIRE_SCRIPT = """
local total = redis.call('INCR', KEYS[1])
if total > tonumber(ARGV[1]) then redis.call('DECR', KEYS[1]); return 0 end
local client = redis.call('INCR', KEYS[2])
if client > tonumber(ARGV[2]) then
  redis.call('DECR', KEYS[2]); redis.call('DECR', KEYS[1]); return 0
end
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[3]))
return 1
"""
_RELEASE_SCRIPT = """
local total = tonumber(redis.call('GET', KEYS[1]) or '0')
if total <= 1 then redis.call('DEL', KEYS[1]) else redis.call('DECR', KEYS[1]) end
local client = tonumber(redis.call('GET', KEYS[2]) or '0')
if client <= 1 then redis.call('DEL', KEYS[2]) else redis.call('DECR', KEYS[2]) end
return 1
"""


def _redis_keys(client_id: str) -> tuple[str, str]:
    return shared_redis.key("analysis:active:total"), shared_redis.key(f"analysis:active:client:{client_id}")


def _redis_acquire(client_id: str) -> bool:
    total_key, client_key = _redis_keys(client_id)
    try:
        return bool(
            shared_redis.client().eval(
                _ACQUIRE_SCRIPT,
                2,
                total_key,
                client_key,
                MAX_CONCURRENT_ANALYSES,
                MAX_ANALYSES_PER_CLIENT,
                ANALYSIS_SLOT_TTL_SECONDS,
            )
        )
    except Exception as exc:
        raise shared_redis.RedisUnavailable("Analysis concurrency store is unavailable.") from exc


def _redis_release(client_id: str) -> None:
    total_key, client_key = _redis_keys(client_id)
    try:
        shared_redis.client().eval(_RELEASE_SCRIPT, 2, total_key, client_key)
    except Exception as exc:
        raise shared_redis.RedisUnavailable("Analysis concurrency store is unavailable.") from exc


async def acquire_analysis_slot(client_id: str) -> bool:
    global _active_analysis_total
    if shared_redis.enabled():
        return await asyncio.to_thread(_redis_acquire, client_id)
    async with _active_analysis_lock:
        client_count = _active_analysis_by_client.get(client_id, 0)
        if _active_analysis_total >= MAX_CONCURRENT_ANALYSES or client_count >= MAX_ANALYSES_PER_CLIENT:
            return False
        _active_analysis_total += 1
        _active_analysis_by_client[client_id] = client_count + 1
        return True


async def release_analysis_slot(client_id: str) -> None:
    global _active_analysis_total
    if shared_redis.enabled():
        await asyncio.to_thread(_redis_release, client_id)
        return
    async with _active_analysis_lock:
        _active_analysis_total = max(0, _active_analysis_total - 1)
        client_count = _active_analysis_by_client.get(client_id, 0)
        if client_count <= 1:
            _active_analysis_by_client.pop(client_id, None)
        else:
            _active_analysis_by_client[client_id] = client_count - 1


def active_analysis_snapshot() -> dict[str, object]:
    snapshot: dict[str, object] = {
        "scope": "redis" if shared_redis.enabled() else "process_local",
        "max_concurrent": MAX_CONCURRENT_ANALYSES,
        "max_per_client": MAX_ANALYSES_PER_CLIENT,
    }
    if not shared_redis.enabled():
        return {
            **snapshot,
            "active_total": _active_analysis_total,
            "active_clients": len(_active_analysis_by_client),
        }
    try:
        total_key, _ = _redis_keys("snapshot")
        active_total = int(shared_redis.client().get(total_key) or 0)
        return {**snapshot, "active_total": active_total, "active_clients": -1}
    except Exception:
        return {**snapshot, "active_total": -1, "active_clients": -1, "status": "unavailable"}
