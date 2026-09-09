"""Background warmer for today's CMS raw-data cache."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import time
import traceback

from backend.config import (
    SCM_PRE_ANALYSIS_ENABLED,
    SCM_PRE_ANALYSIS_HOURS_KST,
    SCM_PRE_ANALYSIS_INTERVAL_SECONDS,
)
from backend.season_trend_api_client import fetch_cached_season_trend_source_data
from backend.services.audit import write_audit_event
from backend.services.cms_fetch_cache import prune_disk_cache
from backend.services.cms_source import fetch_cached_cms_raw_data
from backend.services.request_validation import add_months
from core.common import korea_now, korea_today


def _prefetch_log(message: str, **fields: object) -> None:
    suffix = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    print(f"[prefetch] {message}{(' ' + suffix) if suffix else ''}", flush=True)


def _is_within_kst_hours(now: datetime, hours_spec: str) -> bool:
    spec = (hours_spec or "").strip().lower()
    if spec in {"", "*", "all", "always"}:
        return True

    hour = now.hour
    for part in spec.split(","):
        text = part.strip()
        if not text:
            continue
        if "-" not in text:
            try:
                if hour == int(text):
                    return True
            except ValueError:
                return False
            continue

        start_text, end_text = [item.strip() for item in text.split("-", 1)]
        try:
            start_hour = int(start_text)
            end_hour = int(end_text)
        except ValueError:
            return False
        if not 0 <= start_hour <= 23 or not 0 <= end_hour <= 24:
            return False
        if start_hour == end_hour:
            return True
        if start_hour < end_hour and start_hour <= hour < end_hour:
            return True
        if start_hour > end_hour and (hour >= start_hour or hour < end_hour):
            return True
    return False


def _season_default_range(as_of: str) -> tuple[str, str]:
    """분석 탭 기본 선택(최근 1년)과 같은 기간을 계산한다.

    정본은 프론트 ``demandRange(12)``
    (``frontend/components/redesign/lib/workspace-format.ts``)이며 **종료일이
    어제**다. 예열이 종료일을 오늘로 잡으면 캐시 키가 하루 어긋나 사용자의
    기본값 분석이 예열 결과를 전혀 쓰지 못한다(2026-07-30 실측: 25분마다
    2~3분씩 22만 행을 받아놓고 체감 효과 0).

    PL 기준으로 맞춘다. 예열은 ``entity_code``를 넘기지 않아 PL 경로만
    데우고, 본사·미주는 구간 전체가 아니라 달 단위로 캐싱하므로 맞출 구간
    키가 없다.
    """
    end = date.fromisoformat(as_of) - timedelta(days=1)
    return add_months(end, -12).isoformat(), end.isoformat()


def _prefetch_season_default_range(as_of: str) -> dict[str, object]:
    date_from, date_to = _season_default_range(as_of)
    started_at = time.perf_counter()
    try:
        raw, source_meta = fetch_cached_season_trend_source_data(
            date_from=date_from,
            date_to=date_to,
            eu_sold_only=True,
            force_refresh=True,
        )
    except Exception as exc:
        seconds = round(time.perf_counter() - started_at, 3)
        traceback.print_exc()
        _prefetch_log(
            "season_failed",
            date_from=date_from,
            date_to=date_to,
            seconds=seconds,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        write_audit_event(
            "cms_prefetch_season_failed",
            None,
            date_from=date_from,
            date_to=date_to,
            duration_seconds=seconds,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return {
            "status": "failed",
            "date_from": date_from,
            "date_to": date_to,
            "duration_seconds": seconds,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    seconds = round(time.perf_counter() - started_at, 3)
    rows = len(raw.get("sales_history", [])) if isinstance(raw.get("sales_history"), list) else 0
    result = {
        "status": "done",
        "date_from": date_from,
        "date_to": date_to,
        "duration_seconds": seconds,
        "rows": rows,
    }
    _prefetch_log("season_done", date_from=date_from, date_to=date_to, seconds=seconds, rows=rows)
    write_audit_event(
        "cms_prefetch_season_succeeded",
        None,
        date_from=date_from,
        date_to=date_to,
        duration_seconds=seconds,
        rows=rows,
    )
    return result


def prefetch_cms_raw_data_once(now: datetime | None = None) -> dict[str, object]:
    current = now or korea_now()
    hours_spec = SCM_PRE_ANALYSIS_HOURS_KST
    if not _is_within_kst_hours(current, hours_spec):
        result = {
            "status": "skipped",
            "reason": "outside_hours",
            "now_kst": current.isoformat(),
            "hours_kst": hours_spec,
        }
        _prefetch_log("skipped", **result)
        return result

    cache_prune = prune_disk_cache()

    as_of = korea_today().isoformat() if now is None else current.date().isoformat()
    started_at = time.perf_counter()
    _prefetch_log("started", as_of=as_of)
    try:
        raw, cache_info, dates = fetch_cached_cms_raw_data(
            as_of=as_of,
            date_from=None,
            force_refresh=True,
        )
    except Exception as exc:
        seconds = round(time.perf_counter() - started_at, 3)
        traceback.print_exc()
        _prefetch_log("failed", as_of=as_of, seconds=seconds, error_type=type(exc).__name__, error=str(exc))
        write_audit_event(
            "cms_prefetch_failed",
            None,
            as_of=as_of,
            duration_seconds=seconds,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        # 발주용 fetch가 실패해도 시즌 기본 구간 워밍은 독립적으로 시도한다.
        return {
            "status": "failed",
            "as_of": as_of,
            "duration_seconds": seconds,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "season": _prefetch_season_default_range(as_of),
            "cache_prune": cache_prune,
        }

    seconds = round(time.perf_counter() - started_at, 3)
    row_counts = {key: len(value) for key, value in raw.items() if isinstance(value, list)}
    result = {
        "status": "done",
        "as_of": as_of,
        "date_from": dates.date_from,
        "date_to": dates.date_to,
        "logistics_date_from": dates.logistics_date_from,
        "duration_seconds": seconds,
        "cache_info": cache_info,
        "rows": row_counts,
        "cache_prune": cache_prune,
    }
    _prefetch_log(
        "done",
        as_of=as_of,
        seconds=seconds,
        cache_hit=cache_info.get("hit"),
        cache_source=cache_info.get("source"),
        date_from=dates.date_from,
        date_to=dates.date_to,
        logistics_date_from=dates.logistics_date_from,
        rows=row_counts,
    )
    write_audit_event(
        "cms_prefetch_succeeded",
        None,
        as_of=as_of,
        date_from=dates.date_from,
        date_to=dates.date_to,
        logistics_date_from=dates.logistics_date_from,
        duration_seconds=seconds,
        cms_fetch_cache=cache_info,
        rows=row_counts,
    )
    # 분석 탭 기본 선택(최근 1년)도 함께 데워 첫 분석이 캐시를 타게 한다.
    result["season"] = _prefetch_season_default_range(as_of)
    return result


async def cms_prefetch_loop() -> None:
    interval_seconds = max(SCM_PRE_ANALYSIS_INTERVAL_SECONDS, 1)
    _prefetch_log("loop_started", interval_seconds=interval_seconds, hours_kst=SCM_PRE_ANALYSIS_HOURS_KST)
    while True:
        try:
            await asyncio.to_thread(prefetch_cms_raw_data_once)
        except Exception as exc:
            traceback.print_exc()
            _prefetch_log("failed", error_type=type(exc).__name__, error=str(exc))
            write_audit_event(
                "cms_prefetch_failed",
                None,
                error_type=type(exc).__name__,
                error=str(exc),
            )
        await asyncio.sleep(interval_seconds)


def start_cms_prefetch_task() -> asyncio.Task[None] | None:
    if not SCM_PRE_ANALYSIS_ENABLED:
        return None
    return asyncio.create_task(cms_prefetch_loop(), name="cms-raw-prefetch")
