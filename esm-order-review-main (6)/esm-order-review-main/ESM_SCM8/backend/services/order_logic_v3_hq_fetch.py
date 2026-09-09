"""V3-only HQ component fetches; V2's immutable full snapshot is unchanged.

Fetch the interactive demand window through canonical monthly sales/product
caches. Rolling 24-month history belongs only to the separate monthly season-
factor refresh and is not requested by this web path.
"""

from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

from backend.cms_client import CMS_HQ_ENDPOINTS, HQ_WAREHOUSE_CODE, _fetch_paged, _get_json
from backend.season_trend_api_client import fetch_cached_season_trend_source_data
from backend.services.cms_fetch_cache import get_or_fetch_cms_raw_data
from backend.services.order_logic_v3_unreceived_window import (
    zero_stale_hq_unreceived_quantities,
)


def _legacy_order_from_months(rows):
    """Restore the invoice order used by the HQ feed, without deduplicating.

    A monthly concat is chronological, whereas the existing HQ feed is ordered
    by invoice (ship_dt is not monotonic). Preserve within-invoice line order.
    If monthly partitioning cannot preserve that order, use the original query.
    """
    invoice_months = {}
    previous_by_month = {}
    for row in rows:
        invoice = row.get("invc_no")
        month = str(row.get("ship_dt") or "")[:7]
        if not isinstance(invoice, str) or not invoice or len(month) != 7:
            return None
        if invoice in invoice_months and invoice_months[invoice] != month:
            return None
        if invoice < previous_by_month.get(month, ""):
            return None
        invoice_months[invoice] = month
        previous_by_month[month] = invoice
    return sorted(rows, key=lambda row: row["invc_no"])


def _fetch_inventory() -> dict[str, object]:
    warehouse = {"warehouse": HQ_WAREHOUSE_CODE}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            key: pool.submit(_fetch_paged, CMS_HQ_ENDPOINTS[key], None, None, warehouse)
            for key in ("inventory", "open_po", "inbound_confirmed")
        }
        futures["leadtime_stats"] = pool.submit(
            _get_json, CMS_HQ_ENDPOINTS["leadtime_stats"], {**warehouse, "months": 6},
        )
        # Every component is required; never cache a partial/failed snapshot.
        return {key: future.result() for key, future in futures.items()}


def _cached_inventory(*, as_of: str, force_refresh: bool):
    return get_or_fetch_cms_raw_data(
        as_of=as_of, date_from=None, date_to=None, logistics_date_from=None,
        entity_code="HQ", cache_scope="v3_hq_inventory_position_guide_6m_v2",
        fetcher=_fetch_inventory, force_refresh=force_refresh,
    )


def fetch_cached_hq_opo_raw_data(
    *, as_of: str, date_from: str, date_to: str, force_refresh: bool = False,
) -> tuple[dict[str, object], dict[str, object]]:
    started = perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        inventory_future = pool.submit(_cached_inventory, as_of=as_of, force_refresh=force_refresh)
        history_future = pool.submit(
            fetch_cached_season_trend_source_data,
            date_from=date_from, date_to=date_to, eu_sold_only=False,
            entity_code="HQ", force_refresh=force_refresh,
        )
        inventory, inventory_meta = inventory_future.result()
        history, history_meta = history_future.result()
    # The window is applied client-side ON PURPOSE, on each row's
    # ``created_date``. ``/opo/po/open`` does accept ``created_after`` (a live
    # probe narrowed 4,200 rows to 1,129), but a server-side filter would DROP
    # those rows, and with them the SKU's inbound-source presence, its
    # product-identity evidence, and — for a SKU with no sales, stock or
    # confirmed inbound — the SKU itself. Zeroing only the ① quantity keeps the
    # cached snapshot the complete warehouse population and changes just the
    # operand this decision covers. ``inbound_confirmed`` (②/③/④) is
    # already-notified inbound and is not touched at all.
    open_po_rows, unreceived_window = zero_stale_hq_unreceived_quantities(
        list(inventory.get("open_po") or []), as_of=as_of,
    )
    inventory = {**inventory, "open_po": open_po_rows}
    sales_meta = history_meta.get("sales_history") or {}
    invalid_date_rows = sum(
        int(chunk.get("invalid_date_rows") or 0)
        for chunk in sales_meta.get("date_chunks", [])
    )
    # The monthly client excludes malformed dates before returning rows. Such
    # rows may still be identity evidence in the original HQ query; do not
    # silently change that evidence just to reuse a cache.
    sales_rows = None if invalid_date_rows else _legacy_order_from_months(history["sales_history"])
    if sales_rows is None:
        # This fallback changes no business policy: it is exactly the original
        # required source query, not a partial history or an inferred row order.
        sales_rows = _fetch_paged(CMS_HQ_ENDPOINTS["sales_history"], date_from, date_to)
        history_meta = {
            **history_meta,
            "sales_order_source": "original_full_range_query",
            "full_range_reason": "invalid_month_dates" if invalid_date_rows else "ambiguous_invoice_order",
        }
    else:
        history_meta = {**history_meta, "sales_order_source": "invoice_order_from_months"}
    duration = round(perf_counter() - started, 3)
    print(f"[perf][order_logic_v3] stage=hq_component_fetch seconds={duration}", flush=True)
    return {
        **inventory,
        "sales_history": sales_rows,
        "products": history["prod_list"],
    }, {
        "source": "v3_hq_component_cache",
        "inventory": inventory_meta,
        "unreceived_window": unreceived_window,
        "history": history_meta,
        "duration_seconds": duration,
        "date_from": date_from,
        "date_to": date_to,
        "warehouse_code": HQ_WAREHOUSE_CODE,
    }
