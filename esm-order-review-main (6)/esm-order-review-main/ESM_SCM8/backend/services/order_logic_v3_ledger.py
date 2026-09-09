"""V3 sales quantities from CMS stock-in-out (2026-09-07 approval).

Only daily sales aggregates are cached. Customer, remarks and document numbers
never enter the cache, logs or browser. Repeated document numbers are not row IDs.
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import hashlib
import json
import threading
from typing import Callable, Mapping

from backend.cms_client import _get_json
from backend.services import analysis_cancel
from backend.services.cms_fetch_cache import get_or_fetch_cms_raw_data
from core.common import korea_today


LEDGER_ENDPOINT = "/esm/stock-in-out"
LEDGER_POLICY = "V3_STOCK_IN_OUT_SALE_AND_ONLINE_V1"
SALE_TYPES = frozenset({"OUT-SALE", "OUT-SALE (ONLINE)"})
LEDGER_SCOPES = {
    "HQ": {"comp_cd": "CO000001", "whouse_cd": "WH000028"},
    "PL": {"comp_cd": "CO000016"},
    "USA": {"comp_cd": "CO000007"},
}
PAGE_SIZE = 5000
PAGE_WORKERS = 4
_REQUEST_LIMIT = threading.BoundedSemaphore(PAGE_WORKERS)


class LedgerSourceError(ValueError):
    """Safe, field-only errors; never include source rows or customer data."""


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerSourceError(f"수불 API의 {field} 값이 정수가 아닙니다.")
    return value


def _day(value: object, field: str) -> date:
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise LedgerSourceError(f"수불 API의 {field} 날짜가 올바르지 않습니다.") from None


def _check_cancel(token: analysis_cancel.CancelToken | None) -> None:
    if token is not None and token.cancelled:
        raise analysis_cancel.AnalysisCancelled("사용자가 분석을 중단했습니다.")


def _page(params: dict[str, object], page: int, token) -> dict[str, object]:
    while not _REQUEST_LIMIT.acquire(timeout=0.25):
        _check_cancel(token)
    try:
        _check_cancel(token)
        payload = _get_json(LEDGER_ENDPOINT, {
            **params, "page": page, "page_size": PAGE_SIZE,
            "include_total": "true" if page == 1 else "false",
        })
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise LedgerSourceError("수불 API의 페이지 응답 형식이 올바르지 않습니다.")
        if payload.get("page") != page or payload.get("page_size") != PAGE_SIZE:
            raise LedgerSourceError("수불 API의 페이지 번호 또는 크기가 요청과 다릅니다.")
        return payload
    finally:
        _REQUEST_LIMIT.release()


def _fetch_month(*, entity_code: str, start: date, end: date, token=None, progress=None) -> dict[str, object]:
    scope = LEDGER_SCOPES[entity_code]
    params = {**scope, "date_from": start.isoformat(), "date_to": end.isoformat(),
              "biz_gbn": "COSMETIC", "lang": "KOR"}
    first = _page(params, 1, token)
    total = _integer(first.get("total"), "total")
    if total < 0:
        raise LedgerSourceError("수불 API의 전체 건수가 음수입니다.")
    page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    # Preserve source names until the approved product-identity resolver runs.
    # Multiple real lines with the same fields must contribute their quantities.
    daily: dict[tuple[str, str | None, str | None, str, str], int] = defaultdict(int)
    type_counts: dict[str, int] = defaultdict(int)
    type_quantities: dict[str, int] = defaultdict(int)
    read_count = 0
    sales_inbound_only_row_count = 0

    def consume(page_number: int, payload: Mapping[str, object]) -> None:
        nonlocal read_count, sales_inbound_only_row_count
        _check_cancel(token)
        items = payload["items"]
        expected = min(PAGE_SIZE, max(0, total - (page_number - 1) * PAGE_SIZE))
        if len(items) != expected:
            raise LedgerSourceError("수불 API의 페이지 건수와 전체 건수가 맞지 않습니다. 다시 조회해 주세요.")
        if payload.get("total") is not None and payload["total"] != total:
            raise LedgerSourceError("수불 API 조회 중 전체 건수가 변경됐습니다. 다시 조회해 주세요.")
        for row in items:
            if not isinstance(row, dict):
                raise LedgerSourceError("수불 API의 행 형식이 올바르지 않습니다.")
            if any(row.get(key) != value for key, value in scope.items()):
                raise LedgerSourceError("수불 API에 요청한 법인·창고 범위 밖의 행이 있습니다.")
            if not row.get("whouse_cd") or row.get("biz_gbn") != "COSMETIC":
                raise LedgerSourceError("수불 API의 창고 또는 사업군이 올바르지 않습니다.")
            day = _day(row.get("ledger_dt"), "ledger_dt")
            if not start <= day <= end:
                raise LedgerSourceError("수불 API에 조회기간 밖의 행이 있습니다.")
            sku = row.get("prod_cd")
            kind = row.get("ledger_type_nm")
            if not isinstance(sku, str) or not sku.strip() or not isinstance(kind, str) or not kind.strip():
                raise LedgerSourceError("수불 API의 상품코드 또는 수불구분이 비어 있습니다.")
            qty = _integer(row.get("qty"), "qty")
            qty_in = _integer(row.get("qty_in"), "qty_in")
            qty_out = _integer(row.get("qty_out"), "qty_out")
            if qty_in < 0 or qty_out < 0 or (qty_in and qty_out) or qty != qty_in - qty_out:
                raise LedgerSourceError("수불 API의 입출고 수량과 부호가 일치하지 않습니다.")
            type_counts[kind] += 1
            type_quantities[kind] += qty_out
            read_count += 1
            if kind not in SALE_TYPES:
                continue
            if qty_out == 0:
                # CMS can retain a sale label on an inbound-only ledger line.
                # The approved demand field is qty_out, so this contributes zero;
                # do not subtract qty_in or infer a return/cancellation type.
                # All scope, date and signed-quantity checks above still apply.
                sales_inbound_only_row_count += int(qty_in > 0)
                continue
            for key in ("prod_nm", "brand_nm"):
                if row.get(key) is not None and not isinstance(row[key], str):
                    raise LedgerSourceError(f"수불 API의 {key} 형식이 올바르지 않습니다.")
            daily[(sku, row.get("prod_nm"), row.get("brand_nm"), day.isoformat(), kind)] += qty_out
        if progress:
            progress({"completed_pages": page_number, "total_pages": page_count})

    consume(1, first)
    del first
    with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as pool:
        # Bounded batches avoid holding an entire month's raw ledger in memory.
        for first_page in range(2, page_count + 1, PAGE_WORKERS):
            _check_cancel(token)
            pages = range(first_page, min(page_count + 1, first_page + PAGE_WORKERS))
            for number, payload in zip(pages, pool.map(lambda p: _page(params, p, token), pages)):
                consume(number, payload)
    rows = [
        {"prod_cd": sku, "prod_nm": name, "brand_nm": brand, "ledger_dt": day,
         "ledger_type_nm": kind, "qty_out": qty, "comp_cd": scope["comp_cd"]}
        for (sku, name, brand, day, kind), qty in sorted(
            daily.items(), key=lambda item: tuple(value or "" for value in item[0]))
    ]
    return {"daily_sales": rows, "audit": {
        "raw_row_count": read_count, "pages": page_count,
        "rows_by_type": dict(type_counts), "out_qty_by_type": dict(type_quantities),
        "sales_row_count": sum(type_counts[kind] for kind in SALE_TYPES),
        "sales_inbound_only_row_count": sales_inbound_only_row_count,
        "sales_quantity": sum(row["qty_out"] for row in rows),
    }}


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def fetch_v3_ledger_sales(*, entity_code: str, date_from: str, date_to: str,
                          force_refresh: bool = False,
                          progress: Callable[[dict[str, object]], None] | None = None) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Canonical monthly cache shared by 91-day demand and 24-month factors.

    Historical cache refresh follows existing CMS behavior: reuse closed months,
    allow explicit force_refresh for backdated corrections; current month has TTL.
    Only a complete month fetch is cached, with no transaction-level raw payload.
    """
    if entity_code not in LEDGER_SCOPES:
        raise LedgerSourceError("수불 API의 V3 대상 법인이 아닙니다.")
    start, end = _day(date_from, "date_from"), _day(date_to, "date_to")
    today = korea_today()
    if start > end or end > today:
        raise LedgerSourceError("수불 API의 조회기간이 올바르지 않습니다.")
    token = analysis_cancel.current_token()
    month = start.replace(day=1)
    rows: list[dict[str, object]] = []
    chunks: list[dict[str, object]] = []
    total_months = (end.year - start.year) * 12 + end.month - start.month + 1
    while month <= end:
        _check_cancel(token)
        month_end = min(_next_month(month) - timedelta(days=1), today)
        scope = json.dumps(LEDGER_SCOPES[entity_code], sort_keys=True)
        if progress:
            progress({"stage": "fetching", "month": month.strftime("%Y-%m"),
                      "completed_months": len(chunks), "total_months": total_months,
                      "completed_pages": 0, "total_pages": None})
        raw, cache = get_or_fetch_cms_raw_data(
            as_of=month_end.isoformat(), date_from=month.isoformat(),
            date_to=month_end.isoformat(), logistics_date_from=None, entity_code=entity_code,
            cache_scope=f"{LEDGER_POLICY}:{scope}:COSMETIC:daily",
            fetcher=lambda: _fetch_month(entity_code=entity_code, start=month, end=month_end, token=token,
                                        **({"progress": progress} if progress else {})),
            force_refresh=force_refresh,
        )
        rows.extend(row for row in raw["daily_sales"] if date_from <= row["ledger_dt"] <= date_to)
        chunks.append({"date_from": month.isoformat(), "date_to": month_end.isoformat(),
                       **raw["audit"], "cache": cache})
        month = _next_month(month)
        if progress:
            progress({"completed_months": len(chunks)})
    checksum = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return rows, {
        "source": "CMS_STOCK_IN_OUT", "path": LEDGER_ENDPOINT, "policy": LEDGER_POLICY,
        "scope": {**LEDGER_SCOPES[entity_code], "biz_gbn": "COSMETIC"},
        "included_types": sorted(SALE_TYPES), "quantity_field": "qty_out",
        "date_field": "ledger_dt", "date_from": date_from, "date_to": date_to,
        "sales_quantity": sum(row["qty_out"] for row in rows),
        "daily_row_count": len(rows), "sha256": checksum, "month_chunks": chunks,
        "deduplication": "NONE_ORIGIN_NO_IS_NOT_A_LINE_ID",
    }
