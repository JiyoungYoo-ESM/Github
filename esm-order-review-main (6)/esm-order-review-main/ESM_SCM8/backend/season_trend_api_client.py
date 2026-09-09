"""CMS source API client for season-trend/global-demand analysis."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import BoundedSemaphore

from backend.cms_client import MAX_PARALLEL_PAGE_REQUESTS, PAGE_SIZE, _get_json
from backend.services import analysis_cancel
from backend.services.cms_fetch_cache import get_or_fetch_cms_raw_data
from core.common import korea_today

# CMS source endpoints for season-trend analysis. Kept as constants so the
# actual request path and the user-facing source label never drift apart.
EU_SALES_ENDPOINT = "/eu/sales/local"
EU_PRODUCTS_ENDPOINT = "/eu/products"
US_SALES_ENDPOINT = "/us/sales/local"
HQ_SALES_HISTORY_ENDPOINT = "/us/sales/history"
SEASON_SALES_ENDPOINTS = {
    "HQ": HQ_SALES_HISTORY_ENDPOINT,
    "PL": EU_SALES_ENDPOINT,
    "USA": US_SALES_ENDPOINT,
}
SEASON_AMOUNT_CURRENCIES = {
    "HQ": "KRW",
    "PL": "EUR",
    "USA": "USD",
}
# v2: eu_sold 목록에 없는 실판매 SKU를 전체 상품목록에서 보충하는 로직 포함.
# v1 캐시는 보충 데이터가 없어 재사용하면 안 되므로 네임스페이스로 분리한다
# (남은 v1 파일은 보관일수 경과 후 prune_disk_cache가 정리).
SEASON_TREND_CACHE_NAMESPACE = "season_trend_source_api_v4_actual_krw"
LONG_HISTORY_MONTH_CACHE_NAMESPACE = "season_trend_sales_month_v2_actual_krw"
PRODUCT_MASTER_CACHE_NAMESPACE = "season_trend_product_master_v1"
_SOURCE_META_KEY = "__source_meta"
_MONTH_ITEMS_KEY = "items"
MAX_STREAMED_PAGES = 10_000
LONG_HISTORY_PAGE_SIZE = 5_000


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


LONG_HISTORY_MONTH_WORKERS = _env_int(
    "SEASON_LONG_HISTORY_MONTH_WORKERS",
    2,
    1,
    MAX_PARALLEL_PAGE_REQUESTS,
)
LONG_HISTORY_PAGE_WORKERS = _env_int(
    "SEASON_LONG_HISTORY_PAGE_WORKERS",
    3,
    1,
    MAX_PARALLEL_PAGE_REQUESTS,
)
LONG_HISTORY_MAX_IN_FLIGHT = _env_int(
    "SEASON_LONG_HISTORY_MAX_IN_FLIGHT",
    6,
    1,
    MAX_PARALLEL_PAGE_REQUESTS,
)
_LONG_HISTORY_REQUEST_LIMIT = BoundedSemaphore(LONG_HISTORY_MAX_IN_FLIGHT)
LONG_HISTORY_ENTITY_BY_PATH = {
    EU_SALES_ENDPOINT: "PL",
    HQ_SALES_HISTORY_ENDPOINT: "HQ",
    US_SALES_ENDPOINT: "USA",
}


class SeasonTrendSourceApiError(RuntimeError):
    """Raised when the CMS source API cannot provide usable season-trend data."""


def _fetch_long_history_page(
    path: str,
    params: dict[str, object],
    page: int,
    cancel_token: analysis_cancel.CancelToken | None = None,
) -> dict[str, object]:
    """Apply one process-wide cap across concurrent long-history jobs."""

    while not _LONG_HISTORY_REQUEST_LIMIT.acquire(timeout=0.25):
        if cancel_token is not None and cancel_token.cancelled:
            raise analysis_cancel.AnalysisCancelled("사용자가 분석을 중단했습니다.")
    try:
        if cancel_token is not None and cancel_token.cancelled:
            raise analysis_cancel.AnalysisCancelled("사용자가 분석을 중단했습니다.")
        return _fetch_page(
            path,
            params,
            page,
            include_total=False,
            page_size=LONG_HISTORY_PAGE_SIZE,
        )
    finally:
        _LONG_HISTORY_REQUEST_LIMIT.release()


def _fetch_page(
    path: str,
    params: dict[str, object],
    page: int,
    include_total: bool = True,
    page_size: int = PAGE_SIZE,
) -> dict[str, object]:
    page_params = {
        **params,
        "page": page,
        "page_size": page_size,
    }
    if not include_total:
        page_params["include_total"] = "false"
    payload = _get_json(path, page_params)
    if not isinstance(payload, dict):
        raise SeasonTrendSourceApiError(f"CMS API {path} response is not a page object: {type(payload).__name__}")
    return payload


def _fetch_long_history_without_total(
    path: str,
    params: dict[str, object],
    *,
    max_workers: int | None = None,
    cancel_token: analysis_cancel.CancelToken | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Stream long-history pages without the endpoint's expensive COUNT query."""

    started_at = time.perf_counter()
    active_cancel_token = cancel_token or analysis_cancel.current_token()
    items: list[dict[str, object]] = []
    recovered_pages: list[int] = []
    effective_workers = min(
        max_workers or LONG_HISTORY_PAGE_WORKERS,
        MAX_PARALLEL_PAGE_REQUESTS,
        LONG_HISTORY_MAX_IN_FLIGHT,
    )
    next_page = 1
    terminal_page = 0

    def fetch_parallel_page(page: int) -> tuple[int, dict[str, object] | None, Exception | None]:
        if active_cancel_token is not None and active_cancel_token.cancelled:
            return page, None, analysis_cancel.AnalysisCancelled()
        try:
            return page, _fetch_long_history_page(
                path, params, page, active_cancel_token,
            ), None
        except Exception as exc:  # noqa: BLE001 - retry failed pages sequentially below
            return page, None, exc

    with ThreadPoolExecutor(max_workers=effective_workers) as pool:
        while next_page <= MAX_STREAMED_PAGES:
            # HQ/USA history streams one small batch at a time, so a check here
            # stops within a single batch.
            if active_cancel_token is not None and active_cancel_token.cancelled:
                raise analysis_cancel.AnalysisCancelled("사용자가 분석을 중단했습니다.")
            pages = range(next_page, min(next_page + effective_workers, MAX_STREAMED_PAGES + 1))
            page_results = pool.map(fetch_parallel_page, pages)
            reached_end = False
            for page, payload, error in page_results:
                if isinstance(error, analysis_cancel.AnalysisCancelled):
                    raise error
                if active_cancel_token is not None and active_cancel_token.cancelled:
                    raise analysis_cancel.AnalysisCancelled("사용자가 분석을 중단했습니다.")
                if error is not None:
                    payload = _fetch_long_history_page(
                        path, params, page, active_cancel_token,
                    )
                    recovered_pages.append(page)
                assert payload is not None
                page_items = list(payload.get("items") or [])
                items.extend(page_items)
                terminal_page = page
                if len(page_items) < LONG_HISTORY_PAGE_SIZE:
                    reached_end = True
                    break
            if reached_end:
                break
            next_page += effective_workers
        else:
            raise SeasonTrendSourceApiError(
                f"CMS API {path} exceeded the {MAX_STREAMED_PAGES}-page safety limit."
            )

    return items, {
        "path": path,
        "rows": len(items),
        "api_total": len(items),
        "pages": terminal_page,
        "page_size": LONG_HISTORY_PAGE_SIZE,
        "include_total": False,
        "max_in_flight": LONG_HISTORY_MAX_IN_FLIGHT,
        "recovered_pages": recovered_pages,
        "duration_seconds": round(time.perf_counter() - started_at, 3),
    }


def _next_month(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _long_history_param_fingerprint(params: dict[str, object]) -> str:
    cache_params = {
        str(key): value
        for key, value in params.items()
        if key not in {"date_from", "date_to", "page", "page_size", "include_total"}
    }
    encoded = json.dumps(cache_params, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _fetch_cached_long_history_month(
    path: str,
    params: dict[str, object],
    *,
    month_start: date,
    month_end: date,
    force_refresh: bool = False,
    cancel_token: analysis_cancel.CancelToken | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Fetch one canonical calendar month through the shared raw-data cache."""

    entity_code = LONG_HISTORY_ENTITY_BY_PATH.get(path)
    if entity_code is None:
        fetch_options: dict[str, object] = {
            "max_workers": LONG_HISTORY_PAGE_WORKERS,
        }
        if cancel_token is not None:
            fetch_options["cancel_token"] = cancel_token
        return _fetch_long_history_without_total(
            path,
            {
                **params,
                "date_from": month_start.isoformat(),
                "date_to": month_end.isoformat(),
            },
            **fetch_options,
        )

    today = korea_today()
    is_open_month = month_start <= today <= month_end
    fetch_end = today if is_open_month else month_end
    cache_as_of = today if is_open_month else month_end
    fetch_params = {
        **params,
        "date_from": month_start.isoformat(),
        "date_to": fetch_end.isoformat(),
    }
    namespace = (
        f"{LONG_HISTORY_MONTH_CACHE_NAMESPACE}:path={path}:"
        f"params={_long_history_param_fingerprint(params)}:"
        f"page_size={LONG_HISTORY_PAGE_SIZE}"
    )

    def _fetcher() -> dict[str, object]:
        fetch_options: dict[str, object] = {
            "max_workers": LONG_HISTORY_PAGE_WORKERS,
        }
        if cancel_token is not None:
            fetch_options["cancel_token"] = cancel_token
        rows, source_meta = _fetch_long_history_without_total(
            path, fetch_params, **fetch_options,
        )
        return {
            _MONTH_ITEMS_KEY: rows,
            _SOURCE_META_KEY: source_meta,
        }

    cached_raw, cache_info = get_or_fetch_cms_raw_data(
        as_of=cache_as_of.isoformat(),
        date_from=month_start.isoformat(),
        date_to=fetch_end.isoformat(),
        logistics_date_from=namespace,
        entity_code=entity_code,
        fetcher=_fetcher,
        force_refresh=force_refresh,
    )
    rows = list(cached_raw.get(_MONTH_ITEMS_KEY) or [])
    source_meta = cached_raw.get(_SOURCE_META_KEY)
    if not isinstance(source_meta, dict):
        source_meta = {
            "path": path,
            "rows": len(rows),
            "api_total": len(rows),
            "pages": 0,
            "include_total": False,
        }
    return rows, {
        **source_meta,
        "cache_date_from": month_start.isoformat(),
        "cache_date_to": fetch_end.isoformat(),
        "cache": cache_info,
    }


def _filter_long_history_rows(
    rows: list[dict[str, object]],
    *,
    range_start: date,
    range_end: date,
) -> tuple[list[dict[str, object]], int]:
    """Keep only rows whose CMS ship date is inside the requested boundary."""

    filtered: list[dict[str, object]] = []
    invalid_date_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            invalid_date_rows += 1
            continue
        raw_date = None
        for key in ("ship_dt", "date", "Date", "출고일"):
            value = row.get(key)
            if value is not None and value != "":
                raw_date = value
                break
        try:
            row_date = date.fromisoformat(str(raw_date)[:10])
        except (TypeError, ValueError):
            invalid_date_rows += 1
            continue
        if range_start <= row_date <= range_end:
            filtered.append(row)
    return filtered, invalid_date_rows


def _fetch_long_history_by_month(
    path: str,
    params: dict[str, object],
    *,
    force_refresh: bool = False,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Assemble a selected range from reusable canonical calendar months."""

    raw_from = str(params.get("date_from") or "")
    raw_to = str(params.get("date_to") or "")
    try:
        range_start = date.fromisoformat(raw_from)
        range_end = date.fromisoformat(raw_to)
    except ValueError:
        return _fetch_long_history_without_total(path, params)

    started_at = time.perf_counter()
    cancel_token = analysis_cancel.current_token()
    chunks: list[tuple[date, date, date, date]] = []
    cursor = date(range_start.year, range_start.month, 1)
    while cursor <= range_end:
        next_month = _next_month(cursor)
        month_end = next_month - timedelta(days=1)
        selected_start = max(range_start, cursor)
        selected_end = min(range_end, month_end)
        chunks.append((selected_start, selected_end, cursor, month_end))
        cursor = next_month

    def fetch_chunk(
        chunk: tuple[date, date, date, date],
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        if cancel_token is not None and cancel_token.cancelled:
            raise analysis_cancel.AnalysisCancelled("사용자가 분석을 중단했습니다.")
        selected_start, selected_end, month_start, month_end = chunk
        fetch_options: dict[str, object] = {
            "month_start": month_start,
            "month_end": month_end,
            "force_refresh": force_refresh,
        }
        if cancel_token is not None:
            fetch_options["cancel_token"] = cancel_token
        month_items, meta = _fetch_cached_long_history_month(
            path,
            params,
            **fetch_options,
        )
        chunk_items, invalid_date_rows = _filter_long_history_rows(
            month_items,
            range_start=selected_start,
            range_end=selected_end,
        )
        cached_rows = int(meta.get("rows") or len(month_items))
        cached_api_total = int(meta.get("api_total") or cached_rows)
        return chunk_items, {
            **meta,
            "date_from": selected_start.isoformat(),
            "date_to": selected_end.isoformat(),
            "cached_rows": cached_rows,
            "cached_api_total": cached_api_total,
            "rows": len(chunk_items),
            "api_total": len(chunk_items),
            "invalid_date_rows": invalid_date_rows,
        }

    items: list[dict[str, object]] = []
    chunk_meta: list[dict[str, object]] = []
    month_workers = min(LONG_HISTORY_MONTH_WORKERS, max(len(chunks), 1))
    # ``Executor.map`` submits every month eagerly.  If an early month is slow,
    # later completed futures retain all their full JSON lists at once.  Keep
    # only one pending result per worker so 24-month V3 runs cannot build that
    # extra memory spike while preserving chronological output order.
    with ThreadPoolExecutor(max_workers=month_workers) as pool:
        remaining_chunks = iter(chunks)
        pending = deque()
        for _ in range(month_workers):
            try:
                pending.append(pool.submit(fetch_chunk, next(remaining_chunks)))
            except StopIteration:
                break
        while pending:
            chunk_items, meta = pending.popleft().result()
            items.extend(chunk_items)
            chunk_meta.append(meta)
            try:
                pending.append(pool.submit(fetch_chunk, next(remaining_chunks)))
            except StopIteration:
                pass

    cache_infos = [
        meta.get("cache")
        for meta in chunk_meta
        if isinstance(meta.get("cache"), dict)
    ]
    cache_hits = sum(1 for info in cache_infos if info.get("hit") is True)
    cache_misses = len(cache_infos) - cache_hits
    return items, {
        "path": path,
        "rows": len(items),
        "api_total": len(items),
        "pages": sum(int(meta.get("pages") or 0) for meta in chunk_meta),
        "include_total": False,
        "max_in_flight": LONG_HISTORY_MAX_IN_FLIGHT,
        "date_chunks": chunk_meta,
        "cache": {
            "hit": bool(cache_infos) and cache_misses == 0,
            "source": "monthly_cache",
            "chunks": len(cache_infos),
            "hits": cache_hits,
            "misses": cache_misses,
        },
        "duration_seconds": round(time.perf_counter() - started_at, 3),
    }


def _fetch_paged(
    path: str,
    params: dict[str, object] | None = None,
    *,
    force_refresh: bool = False,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    started_at = time.perf_counter()
    request_params = dict(params or {})
    if path in {EU_SALES_ENDPOINT, HQ_SALES_HISTORY_ENDPOINT, US_SALES_ENDPOINT}:
        return _fetch_long_history_by_month(
            path,
            request_params,
            force_refresh=force_refresh,
        )

    first = _fetch_page(path, request_params, 1)
    items: list[dict[str, object]] = list(first.get("items") or [])
    total = int(first.get("total") or len(items))
    total_pages = math.ceil(total / PAGE_SIZE) if total > 0 else 1
    recovered_pages: list[int] = []

    if total_pages > 1:
        max_workers = (
            min(4, MAX_PARALLEL_PAGE_REQUESTS)
            if path == EU_PRODUCTS_ENDPOINT and request_params.get("eu_sold_only") == "false"
            else MAX_PARALLEL_PAGE_REQUESTS
        )

        # Read the token here, in the thread that owns the context, and capture
        # it: page workers are ThreadPoolExecutor children and do not inherit
        # contextvars.
        cancel_token = analysis_cancel.current_token()

        def fetch_parallel_page(page: int) -> tuple[int, dict[str, object] | None, Exception | None]:
            # Pages still queued when the user cancels never reach CMS.
            if cancel_token is not None and cancel_token.cancelled:
                return page, None, analysis_cancel.AnalysisCancelled()
            try:
                return page, _fetch_page(path, request_params, page, include_total=False), None
            except Exception as exc:  # noqa: BLE001 - retry failed pages sequentially below
                return page, None, exc

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            page_results = pool.map(
                fetch_parallel_page,
                range(2, total_pages + 1),
            )
            for page, payload, error in page_results:
                if isinstance(error, analysis_cancel.AnalysisCancelled):
                    # Never retry and never return the pages already fetched:
                    # partial history must not reach the analysis or the cache.
                    raise error
                if cancel_token is not None and cancel_token.cancelled:
                    raise analysis_cancel.AnalysisCancelled("사용자가 분석을 중단했습니다.")
                if error is not None:
                    # A single overloaded CMS page must not discard every page
                    # already fetched successfully. Retry it once more outside
                    # the parallel burst; _fetch_page/_get_json applies the
                    # normal per-request retry policy again.
                    payload = _fetch_page(path, request_params, page, include_total=False)
                    recovered_pages.append(page)
                assert payload is not None
                items.extend(payload.get("items") or [])

    return items, {
        "path": path,
        "rows": len(items),
        "api_total": total,
        "pages": total_pages,
        "recovered_pages": recovered_pages,
        "duration_seconds": round(time.perf_counter() - started_at, 3),
    }


def _fetch_cached_product_master(
    *,
    eu_sold_only: bool,
    force_refresh: bool = False,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Cache the global product master independently from analysis dates."""

    product_params: dict[str, object] = {
        "eu_sold_only": "true" if eu_sold_only else "false"
    }
    today = korea_today().isoformat()
    namespace = (
        f"{PRODUCT_MASTER_CACHE_NAMESPACE}:path={EU_PRODUCTS_ENDPOINT}:"
        f"eu_sold_only={str(eu_sold_only).lower()}"
    )

    def _fetcher() -> dict[str, object]:
        rows, source_meta = _fetch_paged(EU_PRODUCTS_ENDPOINT, product_params)
        return {
            "prod_list": rows,
            _SOURCE_META_KEY: source_meta,
        }

    cached_raw, cache_info = get_or_fetch_cms_raw_data(
        as_of=today,
        date_from=None,
        date_to=None,
        logistics_date_from=namespace,
        entity_code="GLOBAL",
        fetcher=_fetcher,
        force_refresh=force_refresh,
    )
    rows = list(cached_raw.get("prod_list") or [])
    source_meta = cached_raw.get(_SOURCE_META_KEY)
    if not isinstance(source_meta, dict):
        source_meta = {
            "path": EU_PRODUCTS_ENDPOINT,
            "rows": len(rows),
            "api_total": len(rows),
            "pages": 0,
        }
    return rows, {
        **source_meta,
        "cache": cache_info,
    }


def _supplement_missing_products(
    sales_rows: list[dict[str, object]],
    product_rows: list[dict[str, object]],
    *,
    force_refresh: bool = False,
) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    """판매이력에는 있는데 eu_sold 상품목록에 없는 SKU를 전체 목록에서 보충한다.

    CMS `/eu/products?eu_sold_only=true`가 실판매 SKU를 누락하는 사례
    (예: EDGE U 네일 44종, 2026-07 확인)를 흡수한다. 전체 목록에도 없거나
    분류가 비어 있는 코드는 기존대로 분류 필요 SKU로 남아 점검 탭에서 보정한다.
    """
    listed_codes = {str(row.get("prod_cd")) for row in product_rows}
    missing_codes = {
        code
        for code in (str(row.get("prod_cd") or "") for row in sales_rows)
        if code and code not in listed_codes
    }
    if not missing_codes:
        return product_rows, None

    full_rows, full_meta = _fetch_cached_product_master(
        eu_sold_only=False,
        force_refresh=force_refresh,
    )
    supplements = [row for row in full_rows if str(row.get("prod_cd")) in missing_codes]
    supplement_meta = {
        "missing_codes": len(missing_codes),
        "supplemented_rows": len(supplements),
        "full_list_rows": full_meta.get("rows"),
        "duration_seconds": full_meta.get("duration_seconds"),
    }
    print(
        f"[season_trend] prod_list_supplemented missing={len(missing_codes)} "
        f"added={len(supplements)} seconds={full_meta.get('duration_seconds')}",
        flush=True,
    )
    return product_rows + supplements, supplement_meta


def fetch_season_trend_source_data(
    *,
    date_from: str,
    date_to: str,
    eu_sold_only: bool = True,
    entity_code: str = "PL",
    force_refresh: bool = False,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, object]]:
    code = str(entity_code or "").strip().upper()
    sales_endpoint = SEASON_SALES_ENDPOINTS.get(code)
    if sales_endpoint is None:
        raise SeasonTrendSourceApiError(
            f"시즌 분석 판매 API가 연결되지 않은 법인입니다: {code or '(empty)'}"
        )

    # /eu/products is a global COSMETIC product master despite its legacy
    # route prefix. PL may use the EU-sold optimization; USA needs the full
    # catalog because no /us/products endpoint exists.
    effective_eu_sold_only = bool(eu_sold_only and code == "PL")
    # Make the full-catalog contract explicit for HQ/USA instead of relying
    # on the CMS endpoint's current default.
    with ThreadPoolExecutor(max_workers=2) as pool:
        sales_future = pool.submit(
            _fetch_paged,
            sales_endpoint,
            {
                "date_from": date_from,
                "date_to": date_to,
            },
            force_refresh=force_refresh,
        )
        product_future = pool.submit(
            _fetch_cached_product_master,
            eu_sold_only=effective_eu_sold_only,
            force_refresh=force_refresh,
        )
        sales_rows, sales_meta = sales_future.result()
        product_rows, product_meta = product_future.result()

    if effective_eu_sold_only:
        product_rows, supplement_meta = _supplement_missing_products(
            sales_rows,
            product_rows,
            force_refresh=force_refresh,
        )
        if supplement_meta is not None:
            product_meta = {**product_meta, "rows": len(product_rows), "supplement": supplement_meta}

    return {
        "sales_history": sales_rows,
        "prod_list": product_rows,
    }, {
        "sales_history": sales_meta,
        "prod_list": product_meta,
        "entity_code": code,
        "eu_sold_only": effective_eu_sold_only,
        "amount_currency": SEASON_AMOUNT_CURRENCIES[code],
    }


def fetch_cached_season_trend_source_data(
    *,
    date_from: str,
    date_to: str,
    eu_sold_only: bool = True,
    force_refresh: bool = False,
    entity_code: str = "PL",
) -> tuple[dict[str, list[dict[str, object]]], dict[str, object]]:
    """Fetch season-trend CMS source data with the shared raw-data cache.

    The cache key intentionally uses a season-trend namespace in the
    logistics_date_from slot so it cannot collide with order-review CMS caches
    that share the same storage helper.
    """

    code = str(entity_code or "").strip().upper()
    sales_endpoint = SEASON_SALES_ENDPOINTS.get(code)
    if sales_endpoint is None:
        raise SeasonTrendSourceApiError(
            f"시즌 분석 판매 API가 연결되지 않은 법인입니다: {code or '(empty)'}"
        )

    # HQ/USA raw sales are already cached by canonical calendar month and the
    # global product master has its own current-data cache. Avoid writing a
    # second, very large exact-range JSON file for every date-bound change.
    if code in {"HQ", "USA"}:
        raw, source_meta = fetch_season_trend_source_data(
            date_from=date_from,
            date_to=date_to,
            eu_sold_only=eu_sold_only,
            entity_code=code,
            force_refresh=force_refresh,
        )
        sales_meta = source_meta.get("sales_history")
        product_meta = source_meta.get("prod_list")
        sales_cache = (
            sales_meta.get("cache")
            if isinstance(sales_meta, dict) and isinstance(sales_meta.get("cache"), dict)
            else {}
        )
        product_cache = (
            product_meta.get("cache")
            if isinstance(product_meta, dict) and isinstance(product_meta.get("cache"), dict)
            else {}
        )
        source_meta = {
            **source_meta,
            "cache": {
                "hit": sales_cache.get("hit") is True and product_cache.get("hit") is True,
                "source": "component_cache",
                "sales_history": sales_cache,
                "prod_list": product_cache,
            },
        }
        return raw, source_meta

    def _fetcher() -> dict[str, object]:
        raw, source_meta = fetch_season_trend_source_data(
            date_from=date_from,
            date_to=date_to,
            eu_sold_only=eu_sold_only,
            entity_code=code,
            force_refresh=force_refresh,
        )
        return {**raw, _SOURCE_META_KEY: source_meta}

    cached_raw, cache_info = get_or_fetch_cms_raw_data(
        as_of=date_to,
        date_from=date_from,
        date_to=date_to,
        logistics_date_from=(
            f"{SEASON_TREND_CACHE_NAMESPACE}:"
            f"entity={code}:eu_sold_only={str(bool(eu_sold_only and code == 'PL')).lower()}"
        ),
        entity_code=code,
        fetcher=_fetcher,
        force_refresh=force_refresh,
    )
    source_meta = cached_raw.get(_SOURCE_META_KEY)
    if not isinstance(source_meta, dict):
        source_meta = {
            "sales_history": {
                "path": sales_endpoint,
                "rows": len(cached_raw.get("sales_history", [])) if isinstance(cached_raw.get("sales_history"), list) else 0,
            },
            "prod_list": {
                "path": EU_PRODUCTS_ENDPOINT,
                "rows": len(cached_raw.get("prod_list", [])) if isinstance(cached_raw.get("prod_list"), list) else 0,
            },
            "entity_code": code,
            "eu_sold_only": bool(eu_sold_only and code == "PL"),
            "amount_currency": SEASON_AMOUNT_CURRENCIES[code],
        }
    source_meta = dict(source_meta)
    source_meta["cache"] = cache_info
    return {
        "sales_history": list(cached_raw.get("sales_history") or []),
        "prod_list": list(cached_raw.get("prod_list") or []),
    }, source_meta
