"""CMS API 호출 모듈.

CMS API(https://cms.pikicat.com/api/v1)에서 법인별 발주검토 분석에 필요한 6개
엔드포인트 데이터를 가져온다. 상세 스펙은 docs/CMS_API_GUIDE.md,
docs/cms_openapi.json 참고.

튜닝 가능한 환경변수(기본값은 운영 CMS API 안정성 기준의 보수적인 값):
- CMS_API_PAGE_SIZE          페이지당 행 수 (기본 2000, 허용 100~2000)
- CMS_API_PARALLEL_PAGES     페이지 병렬 호출 수 (기본 8, 허용 1~12)
- CMS_API_REQUEST_TIMEOUT_SECONDS  요청 1건 timeout (기본 120, 허용 10~600)
"""

from __future__ import annotations

import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

DEFAULT_BASE_URL = "https://cms.pikicat.com/api/v1"

CMS_ENTITY_ENDPOINTS: dict[str, dict[str, str]] = {
    "PL": {
        "stock_local": "/eu/stock/local",
        "stock_hq": "/eu/stock/hq",
        "sales_local": "/eu/sales/local",
        "sales_hq": "/eu/sales/hq-to-eu",
        "shipping": "/eu/shipping/containers",
        "open_po": "/eu/open-po",
        "lead_time": "/eu/logistics/lead-time",
    },
    "USA": {
        "stock_local": "/us/stock/local",
        "stock_hq": "/us/stock/hq",
        "sales_local": "/us/sales/local",
        "sales_hq": "/us/sales/hq-to-us",
        "shipping": "/us/shipping/containers",
        "open_po": "/us/open-po",
        "lead_time": "/us/logistics/lead-time",
    },
}

# HQ/OPO order sources.  `sales_history` is the headquarters-wide sales feed
# (CO000001, every warehouse); the HQ adapter narrows it to the OPO warehouse.
# The full COSMETIC product master is exposed under the legacy EU route prefix
# but is shared by HQ/USA too. The remaining OPO paths are warehouse-scoped.
HQ_WAREHOUSE_CODE = "OPO"
CMS_HQ_ENDPOINTS: dict[str, str] = {
    "sales_history": "/us/sales/history",
    "products": "/eu/products",
    "inventory": "/opo/inventory",
    "open_po": "/opo/po/open",
    "inbound_confirmed": "/opo/inbound/confirmed",
    "leadtime_stats": "/opo/leadtime/stats",
}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


# page_size=5000은 502 발생 이력 있음. 2000은 허용 상한 안에서 페이지 수를 줄이는 기본값.
PAGE_SIZE = _env_int("CMS_API_PAGE_SIZE", 2000, 100, 2000)
RETRY_STATUS_CODES = {502, 503, 504}
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = _env_int("CMS_API_REQUEST_TIMEOUT_SECONDS", 120, 10, 600)
# 페이지 병렬 호출 수. 너무 크면 운영 API가 502를 냄 → 재시도가 흡수하지만 보수적으로 유지.
# sales_local이 12만 행 이상(120페이지+)이라 이 값이 uncached fetch 시간을 좌우한다.
# 502(request_retryable_status 로그)가 드물면 8~10까지 올려볼 수 있고, 늘어나면 다시 낮춘다.
MAX_PARALLEL_PAGE_REQUESTS = _env_int("CMS_API_PARALLEL_PAGES", 8, 1, 12)

_thread_local = threading.local()


def _row_count(payload: object) -> int | None:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return len(payload["items"])
    return None


def _perf_log(message: str, **fields: object) -> None:
    suffix = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    print(f"[perf][cms_api] {message}{(' ' + suffix) if suffix else ''}", flush=True)


class CmsAuthenticationError(RuntimeError):
    """Raised when CMS rejects the configured API credentials."""

    def __init__(self, status_code: int, url: str):
        has_api_key = bool(os.environ.get("CMS_API_KEY", "").strip())
        if has_api_key:
            message = f"CMS API 인증에 실패했습니다(HTTP {status_code}). CMS_API_KEY 값이 유효한지 확인해 주세요."
        else:
            message = f"CMS API 인증에 실패했습니다(HTTP {status_code}). 백엔드 실행 환경에 CMS_API_KEY를 설정해 주세요."
        super().__init__(message)
        self.status_code = status_code
        self.url = url


def cms_base_url() -> str:
    return os.environ.get("CMS_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def cms_api_headers() -> dict[str, str] | None:
    api_key = os.environ.get("CMS_API_KEY", "").strip()
    if not api_key:
        return None
    return {"X-API-Key": api_key}


def _http_get(url: str, **kwargs: object) -> requests.Response:
    # requests.get은 호출마다 새 연결(TLS 핸드셰이크)을 만든다. 페이지네이션으로
    # 요청이 120건 이상 나가므로 스레드별 Session으로 keep-alive를 재사용한다.
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        _thread_local.session = session
    return session.get(url, **kwargs)


def _get_json(path: str, params: dict[str, object] | None = None) -> object:
    url = f"{cms_base_url()}{path}"
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        attempt_started_at = time.perf_counter()
        try:
            response = _http_get(url, params=params, headers=cms_api_headers(), timeout=REQUEST_TIMEOUT_SECONDS)
            elapsed = time.perf_counter() - attempt_started_at
            if response.status_code in RETRY_STATUS_CODES:
                last_error = RuntimeError(f"CMS API {url} -> HTTP {response.status_code}")
                _perf_log("request_retryable_status", path=path, status=response.status_code, attempt=attempt, seconds=round(elapsed, 3))
            elif response.status_code in {401, 403}:
                _perf_log("request_auth_failed", path=path, status=response.status_code, attempt=attempt, seconds=round(elapsed, 3))
                raise CmsAuthenticationError(response.status_code, url)
            else:
                response.raise_for_status()
                payload = response.json()
                _perf_log(
                    "request_done",
                    path=path,
                    status=response.status_code,
                    attempt=attempt,
                    seconds=round(elapsed, 3),
                    rows=_row_count(payload),
                )
                return payload
        except requests.RequestException as exc:
            elapsed = time.perf_counter() - attempt_started_at
            last_error = exc
            _perf_log("request_exception", path=path, attempt=attempt, seconds=round(elapsed, 3), error=type(exc).__name__)
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SECONDS * attempt)
    cause = f"{type(last_error).__name__}: {last_error}" if last_error is not None else "unknown"
    raise RuntimeError(f"CMS API 호출 실패({MAX_RETRIES}회 재시도): {url} ({cause})") from last_error


def _fetch_page(
    path: str,
    page: int,
    date_from: str | None,
    date_to: str | None = None,
    include_total: bool = True,
    extra_params: dict[str, object] | None = None,
) -> dict[str, object]:
    params: dict[str, object] = {"page": page, "page_size": PAGE_SIZE}
    params.update(extra_params or {})
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    if not include_total:
        params["include_total"] = "false"
    payload = _get_json(path, params)
    if not isinstance(payload, dict):
        raise RuntimeError(f"CMS API {path} 응답이 페이지 형식이 아닙니다: {type(payload).__name__}")
    return payload


def _fetch_paged(
    path: str,
    date_from: str | None = None,
    date_to: str | None = None,
    extra_params: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    started_at = time.perf_counter()
    first = _fetch_page(path, 1, date_from, date_to, extra_params=extra_params)
    items: list[dict[str, object]] = list(first.get("items") or [])
    total = int(first.get("total") or len(items))
    total_pages = math.ceil(total / PAGE_SIZE) if total > 0 else 1
    if total_pages <= 1:
        _perf_log(
            "paged_done",
            path=path,
            pages=total_pages,
            page_size=PAGE_SIZE,
            rows=len(items),
            seconds=round(time.perf_counter() - started_at, 3),
        )
        return items

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_PAGE_REQUESTS) as pool:
        payloads = pool.map(
            lambda page: _fetch_page(
                path,
                page,
                date_from,
                date_to,
                include_total=False,
                extra_params=extra_params,
            ),
            range(2, total_pages + 1),
        )
        for payload in payloads:
            items.extend(payload.get("items") or [])
    _perf_log(
        "paged_done",
        path=path,
        pages=total_pages,
        page_size=PAGE_SIZE,
        parallel=MAX_PARALLEL_PAGE_REQUESTS,
        total=total,
        rows=len(items),
        seconds=round(time.perf_counter() - started_at, 3),
    )
    return items


def _fetch_list(path: str, params: dict[str, object] | None = None) -> list[dict[str, object]]:
    payload = _get_json(path, params)
    if not isinstance(payload, list):
        raise RuntimeError(f"CMS API {path} 응답이 리스트가 아닙니다: {type(payload).__name__}")
    return payload


def fetch_corporate_stock_ledger(as_of: str) -> list[dict[str, object]]:
    """Fetch one all-company ending-inventory ledger snapshot in Korean.

    The ESM stock-ledger contract requires both dates.  Sending the same KST
    business date makes ``eqty_cost`` the ending inventory amount for the
    dashboard's stated date rather than inventing a reporting window.
    """

    return _fetch_list(
        "/esm/stock-ledger",
        {
            "start_date": as_of,
            "end_date": as_of,
            "lang": "KOR",
        },
    )


CORPORATE_IN_TRANSIT_START_DATE = "2026-01-01"
CORPORATE_IN_TRANSIT_BIZ_GBN = "ALL"


def fetch_corporate_in_transit(as_of: str) -> list[dict[str, object]]:
    """Fetch the current HQ-origin in-transit summary through the stated date.

    CMS defaults this cutoff to 2026-01-01 and the business group to COSMETIC,
    but we send both explicitly so the dashboard includes COSMETIC and KPOP
    without either scope drifting when upstream defaults change.  The end date
    prevents any later-dated packing row from entering this KST business-date
    snapshot.
    """

    return _fetch_list(
        "/esm/in-transit",
        {
            "start_date": CORPORATE_IN_TRANSIT_START_DATE,
            "end_date": as_of,
            "biz_gbn": CORPORATE_IN_TRANSIT_BIZ_GBN,
        },
    )


def cms_entity_endpoints(entity_code: str) -> dict[str, str]:
    code = str(entity_code or "").strip().upper()
    endpoints = CMS_ENTITY_ENDPOINTS.get(code)
    if endpoints is None:
        raise ValueError(f"CMS API가 연결되지 않은 법인입니다: {code or '(empty)'}")
    return endpoints


def fetch_cms_open_po(
    entity_code: str,
    *,
    date_from: str,
    date_to: str,
) -> list[dict[str, object]]:
    """Fetch one PL/USA 미입고현황 window without the other five sources.

    ``date_from``/``date_to`` bound the PO registration date. The response is a
    per-product aggregate with no registration-date column, so a caller that
    needs a narrower 미입고 window has to ask for that window explicitly.
    """

    endpoints = cms_entity_endpoints(entity_code)
    return _fetch_list(
        endpoints["open_po"],
        {"date_from": date_from, "date_to": date_to},
    )


def fetch_cms_lead_time(
    entity_code: str,
    *,
    date_from: str,
    date_to: str,
    include_in_transit: bool = False,
) -> list[dict[str, object]]:
    """Fetch the lead-time feed without changing the shared six-source cache."""

    endpoints = cms_entity_endpoints(entity_code)
    return _fetch_paged(
        endpoints["lead_time"],
        date_from,
        date_to,
        extra_params={
            "include_in_transit": "true" if include_in_transit else "false",
        },
    )


def fetch_hq_opo_data(
    *,
    date_from: str,
    date_to: str,
    leadtime_months: int = 12,
) -> dict[str, object]:
    """Fetch the HQ/OPO order sources for one immutable snapshot.

    Sales history and the shared COSMETIC product master are paginated; the OPO
    feeds are paginated but already scoped to the warehouse; the lead-time
    statistic is a single aggregate object. Every source is required, so a
    failure propagates and the caller blocks the calculation.
    """

    warehouse = {"warehouse": HQ_WAREHOUSE_CODE}
    started_at = time.perf_counter()
    tasks: dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        def submit(key: str, fn, *args, **kwargs) -> None:
            def run() -> object:
                task_started_at = time.perf_counter()
                payload = fn(*args, **kwargs)
                _perf_log(
                    "endpoint_done",
                    key=f"hq_{key}",
                    rows=len(payload) if isinstance(payload, list) else None,
                    seconds=round(time.perf_counter() - task_started_at, 3),
                )
                return payload

            tasks[key] = pool.submit(run)

        submit(
            "sales_history",
            _fetch_paged,
            CMS_HQ_ENDPOINTS["sales_history"],
            date_from,
            date_to,
        )
        submit(
            "products",
            _fetch_paged,
            CMS_HQ_ENDPOINTS["products"],
            None,
            None,
            {"eu_sold_only": False},
        )
        submit(
            "inventory",
            _fetch_paged,
            CMS_HQ_ENDPOINTS["inventory"],
            None,
            None,
            warehouse,
        )
        # `created_after` bounds PO registration, not receipt, so the open-PO
        # remainder must not be filtered by the demand window.
        submit(
            "open_po",
            _fetch_paged,
            CMS_HQ_ENDPOINTS["open_po"],
            None,
            None,
            warehouse,
        )
        submit(
            "inbound_confirmed",
            _fetch_paged,
            CMS_HQ_ENDPOINTS["inbound_confirmed"],
            None,
            None,
            warehouse,
        )
        submit(
            "leadtime_stats",
            _get_json,
            CMS_HQ_ENDPOINTS["leadtime_stats"],
            {**warehouse, "months": leadtime_months},
        )
        result = {key: future.result() for key, future in tasks.items()}

    _perf_log(
        "hq_fetch_all_done",
        rows=sum(len(rows) for rows in result.values() if isinstance(rows, list)),
        seconds=round(time.perf_counter() - started_at, 3),
    )
    return result


def _fetch_lead_time_rows(
    entity_code: str,
    date_from: str | None,
    date_to: str | None,
) -> list[dict[str, object]]:
    """Fetch the lead-time feed used to classify V1 shipment transport modes.

    USA transport mode is authoritative only on this feed.  A failed USA
    request must therefore stop the run instead of producing and caching a
    plausible-looking result in which every shipment silently falls back to
    remark parsing.  Other entities retain the legacy optional enrichment
    behaviour until their V1 source contract is explicitly tightened.
    """

    if not date_from or not date_to:
        return []
    try:
        return fetch_cms_lead_time(
            entity_code,
            date_from=date_from,
            date_to=date_to,
            include_in_transit=True,
        )
    except Exception as error:  # noqa: BLE001 - optional enrichment source
        _perf_log("lead_time_fetch_failed", entity=entity_code, error=type(error).__name__)
        if str(entity_code or "").strip().upper() == "USA":
            raise RuntimeError(
                "미주 운송수단 확인용 리드타임 API를 조회하지 못했습니다. "
                "운송수단과 ETA가 불완전한 상태로 발주분석을 계속할 수 없습니다."
            ) from error
        return []


def fetch_cms_data(
    as_of: str,
    date_from: str | None = None,
    date_to: str | None = None,
    shipping_date_from: str | None = None,
    open_po_date_from: str | None = None,
    include_sales_detail: bool = True,
    include_lead_time_detail: bool = True,
    entity_code: str = "PL",
) -> dict[str, list[dict[str, object]]]:
    """CMS 원천 endpoint를 병렬 호출해 raw 데이터를 dict로 반환한다.

    - stock_local/stock_hq: 재고 스냅샷 (as_of는 최근 3개월 판매수량 기준일)
    - sales_local/sales_hq: 판매 내역 (페이지 병렬 순회)
    - shipping/open_po: 리스트 응답, 별도 date_from/date_to 기준
    - 6개 엔드포인트도 동시에 호출해 전체 소요시간을 줄인다
    """
    endpoints = cms_entity_endpoints(entity_code)
    shipping_params = {
        key: value
        for key, value in {"date_from": shipping_date_from or date_from, "date_to": date_to}.items()
        if value
    }
    open_po_params = {
        key: value
        for key, value in {"date_from": open_po_date_from or date_from, "date_to": date_to}.items()
        if value
    }
    started_at = time.perf_counter()
    tasks: dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=7) as pool:
        def submit(key: str, fn, *args, **kwargs) -> None:
            # endpoint_done의 seconds가 다른 futures 수집 대기시간에 오염되지 않도록
            # 워커 스레드 안에서 해당 엔드포인트의 실제 소요시간을 측정한다.
            def run() -> list[dict[str, object]]:
                task_started_at = time.perf_counter()
                rows = fn(*args, **kwargs)
                _perf_log("endpoint_done", key=key, rows=len(rows), seconds=round(time.perf_counter() - task_started_at, 3))
                return rows

            tasks[key] = pool.submit(run)

        submit("stock_local", _fetch_list, endpoints["stock_local"], {"as_of": as_of})
        submit("stock_hq", _fetch_list, endpoints["stock_hq"], {"as_of": as_of})
        if include_sales_detail:
            submit("sales_local", _fetch_paged, endpoints["sales_local"], date_from, date_to)
            submit("sales_hq", _fetch_paged, endpoints["sales_hq"], date_from, date_to)
        submit("shipping", _fetch_list, endpoints["shipping"], shipping_params or None)
        submit("open_po", _fetch_list, endpoints["open_po"], open_po_params or None)
        # The lead-time feed is required by the V2 ETA view, but V3 inventory
        # mapping only consumes the shipment quantity.  Keep it opt-out so the
        # inventory-only V3 snapshot does not fetch an unused endpoint.
        if include_lead_time_detail and "lead_time" in endpoints:
            submit(
                "lead_time",
                _fetch_lead_time_rows,
                entity_code,
                shipping_params.get("date_from") or date_from,
                date_to,
            )
        result = {}
        for key, future in tasks.items():
            result[key] = future.result()
        if not include_sales_detail:
            result["sales_local"] = []
            result["sales_hq"] = []
        _perf_log("fetch_all_done", rows=sum(len(rows) for rows in result.values()), seconds=round(time.perf_counter() - started_at, 3))
        return result
