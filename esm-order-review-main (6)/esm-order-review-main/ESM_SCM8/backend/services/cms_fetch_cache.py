"""Small on-disk cache for raw CMS fetch payloads.

캐시 키는 (as_of, date_from, date_to, logistics_date_from) 조합이며, 같은 조건의
반복 분석은 CMS API를 다시 부르지 않고 memory → disk 순서로 재사용한다.
- as_of=오늘: ``CMS_TODAY_CACHE_TTL_SECONDS``(기본 14400초) 동안 유효
- as_of=과거: 데이터가 확정이므로 TTL 없이 무기한 유효

hit/miss는 ``[perf][cms_fetch_cache]`` 로그와 caller의 audit event(``cms_fetch_cache``
필드)에서 확인할 수 있다. 운영 지표는 OPERATIONS.md의 "CMS 분석 성능/캐시" 참고.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
import threading
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

from backend.config import CMS_FETCH_CACHE_DIR, CMS_FETCH_CACHE_MAX_AGE_DAYS, CMS_TODAY_CACHE_TTL_SECONDS
from core.common import korea_today

_MEMORY_CACHE_LIMIT = 4
_MEMORY_CACHE: OrderedDict[str, tuple[float, dict[str, object]]] = OrderedDict()
_MEMORY_CACHE_LOCK = threading.Lock()
_KEY_LOCKS: dict[str, threading.Lock] = {}
_KEY_LOCKS_LOCK = threading.Lock()


def _perf_log(message: str, **fields: object) -> None:
    suffix = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    print(f"[perf][cms_fetch_cache] {message}{(' ' + suffix) if suffix else ''}", flush=True)


def _cache_key(
    *,
    as_of: str,
    date_from: str | None,
    date_to: str | None,
    logistics_date_from: str | None,
    entity_code: str = "PL",
    cache_scope: str | None = None,
) -> str:
    payload = {
        # v3 requires the entity lead-time enrichment feed in V1 CMS snapshots.
        # v5 requires the latest EU/USA open-po status fields (②/③/④) and the
        # HQ shared full product master. Invalidate all older snapshots so a
        # V2 run cannot silently reuse the pre-update open-po contract.
        "version": 5,
        "entity_code": entity_code,
        "as_of": as_of,
        "date_from": date_from,
        "date_to": date_to,
        "logistics_date_from": logistics_date_from,
    }
    # A V3 inventory-only snapshot intentionally omits sales and ETA-enrichment
    # feeds.  It must never share a cache entry with the complete V2 snapshot.
    if cache_scope:
        payload["cache_scope"] = cache_scope
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _cache_path(key: str) -> Path:
    return CMS_FETCH_CACHE_DIR / f"{key}.json"


def _lock_for_key(key: str) -> threading.Lock:
    with _KEY_LOCKS_LOCK:
        lock = _KEY_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _KEY_LOCKS[key] = lock
        return lock


def _cache_ttl_seconds(as_of: str) -> int | None:
    if as_of == korea_today().isoformat():
        return CMS_TODAY_CACHE_TTL_SECONDS
    return None


def _is_fresh(created_at: float, ttl_seconds: int | None) -> bool:
    if ttl_seconds is None:
        return True
    return time.time() - created_at <= ttl_seconds


def _cache_info(*, hit: bool, source: str, created_at: float, ttl_seconds: int | None) -> dict[str, object]:
    return {
        "hit": hit,
        "source": source,
        "created_at": datetime.fromtimestamp(created_at, timezone.utc).isoformat(),
        "age_seconds": round(max(time.time() - created_at, 0.0), 3),
        "ttl_seconds": ttl_seconds,
    }


def _read_disk_cache(path: Path, ttl_seconds: int | None) -> tuple[dict[str, object], dict[str, object]] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        created_at = float(payload["created_at"])
        if not _is_fresh(created_at, ttl_seconds):
            path.unlink(missing_ok=True)
            return None
        raw = payload["raw"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
        return None
    if not isinstance(raw, dict):
        path.unlink(missing_ok=True)
        return None
    # Disk pruning uses mtime as an idle-retention signal. Renew it on a
    # successful read so frequently reused monthly source caches are not
    # removed merely because their underlying historical data is old.
    try:
        path.touch()
    except OSError:
        # A transient OneDrive/file-lock failure must not invalidate an
        # otherwise readable cache entry.
        pass
    return raw, _cache_info(hit=True, source="disk", created_at=created_at, ttl_seconds=ttl_seconds)


def prune_disk_cache(max_age_days: int | None = None) -> dict[str, object]:
    """보관 일수를 넘긴 디스크 캐시 파일을 삭제한다.

    만료 파일은 같은 키를 다시 읽을 때만 지워지므로, 다시는 요청되지 않는
    키의 파일이 무한히 쌓인다(기준일이 지난 발주 캐시, 일회성 기간 캐시 등).
    서버 기동 시와 프리페치 사이클에서 호출한다.
    """
    days = CMS_FETCH_CACHE_MAX_AGE_DAYS if max_age_days is None else max_age_days
    if days <= 0:
        return {"removed": 0, "kept": 0, "freed_bytes": 0, "skipped": True}
    cutoff = time.time() - days * 86400
    removed = kept = freed = 0
    for path in CMS_FETCH_CACHE_DIR.glob("*.json"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime >= cutoff:
            kept += 1
            continue
        try:
            path.unlink()
        except OSError:
            # OneDrive 동기화/동시 읽기로 잠긴 파일은 다음 사이클에서 재시도한다.
            kept += 1
            continue
        removed += 1
        freed += stat.st_size
    if removed:
        _perf_log(
            "pruned",
            removed=removed,
            kept=kept,
            freed_mb=round(freed / 1048576, 1),
            max_age_days=days,
        )
    return {"removed": removed, "kept": kept, "freed_bytes": freed, "skipped": False}


def _write_disk_cache(path: Path, raw: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": time.time(),
        "raw": raw,
    }
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temp_file:
        json.dump(payload, temp_file, ensure_ascii=False)
        temp_path = Path(temp_file.name)
    temp_path.replace(path)


def _read_memory_cache(key: str, ttl_seconds: int | None) -> tuple[dict[str, object], dict[str, object]] | None:
    with _MEMORY_CACHE_LOCK:
        cached = _MEMORY_CACHE.get(key)
        if cached is None:
            return None
        created_at, raw = cached
        if not _is_fresh(created_at, ttl_seconds):
            _MEMORY_CACHE.pop(key, None)
            return None
        _MEMORY_CACHE.move_to_end(key)
        return raw, _cache_info(hit=True, source="memory", created_at=created_at, ttl_seconds=ttl_seconds)


def _write_memory_cache(key: str, raw: dict[str, object]) -> None:
    with _MEMORY_CACHE_LOCK:
        _MEMORY_CACHE[key] = (time.time(), raw)
        _MEMORY_CACHE.move_to_end(key)
        while len(_MEMORY_CACHE) > _MEMORY_CACHE_LIMIT:
            _MEMORY_CACHE.popitem(last=False)


def _read_existing_cache(
    *,
    key: str,
    path: Path,
    ttl_seconds: int | None,
) -> tuple[dict[str, object], dict[str, object]] | None:
    memory_cached = _read_memory_cache(key, ttl_seconds)
    if memory_cached is not None:
        return memory_cached

    disk_cached = _read_disk_cache(path, ttl_seconds)
    if disk_cached is not None:
        raw, info = disk_cached
        _write_memory_cache(key, raw)
        return raw, info


def get_or_fetch_cms_raw_data(
    *,
    as_of: str,
    date_from: str | None,
    date_to: str | None,
    logistics_date_from: str | None,
    fetcher: Callable[[], dict[str, object]],
    entity_code: str = "PL",
    cache_scope: str | None = None,
    force_refresh: bool = False,
) -> tuple[dict[str, object], dict[str, object]]:
    key = _cache_key(
        as_of=as_of,
        date_from=date_from,
        date_to=date_to,
        logistics_date_from=logistics_date_from,
        entity_code=entity_code,
        cache_scope=cache_scope,
    )
    ttl_seconds = _cache_ttl_seconds(as_of)
    path = _cache_path(key)

    if not force_refresh:
        cached = _read_existing_cache(key=key, path=path, ttl_seconds=ttl_seconds)
        if cached is not None:
            raw, info = cached
            _perf_log("hit", source=info["source"], as_of=as_of, key=key[:12], age_seconds=info["age_seconds"], ttl_seconds=ttl_seconds)
            return raw, info

    _perf_log("refresh" if force_refresh else "miss", as_of=as_of, key=key[:12], ttl_seconds=ttl_seconds)
    wait_started_at = time.perf_counter()
    key_lock = _lock_for_key(key)
    with key_lock:
        waited_seconds = time.perf_counter() - wait_started_at
        if waited_seconds >= 0.001:
            _perf_log(
                "lock_waited",
                as_of=as_of,
                key=key[:12],
                seconds=round(waited_seconds, 3),
                force_refresh=force_refresh,
            )

        cached_after_wait = _read_existing_cache(key=key, path=path, ttl_seconds=ttl_seconds)
        if cached_after_wait is not None:
            raw, info = cached_after_wait
            if not force_refresh or waited_seconds >= 0.001:
                _perf_log(
                    "hit_after_wait",
                    source=info["source"],
                    as_of=as_of,
                    key=key[:12],
                    age_seconds=info["age_seconds"],
                    ttl_seconds=ttl_seconds,
                )
                return raw, info

        fetch_started_at = time.perf_counter()
        raw = fetcher()
        fetched_at = time.time()
        _write_memory_cache(key, raw)
        _write_disk_cache(path, raw)
        _perf_log(
            "refresh_fetched" if force_refresh else "miss_fetched",
            as_of=as_of,
            key=key[:12],
            seconds=round(time.perf_counter() - fetch_started_at, 3),
            ttl_seconds=ttl_seconds,
        )
        return raw, _cache_info(hit=False, source="cms_api", created_at=fetched_at, ttl_seconds=ttl_seconds)
