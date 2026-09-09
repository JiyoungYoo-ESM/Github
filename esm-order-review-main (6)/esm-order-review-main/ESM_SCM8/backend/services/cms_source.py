"""Shared CMS raw-data date resolution and cached fetch helpers."""

from __future__ import annotations

from dataclasses import dataclass

from concurrent.futures import ThreadPoolExecutor

from backend.cms_client import fetch_cms_data, fetch_cms_open_po, fetch_hq_opo_data
from backend.services.cms_fetch_cache import get_or_fetch_cms_raw_data
from backend.services.order_logic_v3_unreceived_window import (
    merge_open_po_unreceived_window,
    unreceived_cache_scope,
    unreceived_po_window,
)
from backend.services.request_validation import cms_date_settings


@dataclass(frozen=True)
class CmsEffectiveDates:
    analysis_settings: dict[str, object]
    date_from: str
    date_to: str
    logistics_date_from: str

    def cache_fields(self) -> dict[str, str]:
        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "logistics_date_from": self.logistics_date_from,
        }


def _has_actual_krw_contract(raw: object) -> bool:
    """Return whether a cached EU/US snapshot has the deployed KRW fields."""

    if not isinstance(raw, dict):
        return False
    required = {
        "sales_local": "amount_krw_actual",
        "stock_local": "unit_cost_krw",
        "shipping": "amount_krw",
    }
    for source_key, field in required.items():
        rows = raw.get(source_key)
        if not isinstance(rows, list):
            return False
        if rows and not all(isinstance(row, dict) and field in row for row in rows):
            return False
    return True


def resolve_cms_effective_dates(as_of: str, date_from: str | None = None) -> CmsEffectiveDates:
    analysis_settings = cms_date_settings(as_of)
    logistics_date_from = str(analysis_settings["logistics_period_start"])
    return CmsEffectiveDates(
        analysis_settings=analysis_settings,
        date_from=date_from or logistics_date_from,
        date_to=str(analysis_settings["period_end"]),
        logistics_date_from=logistics_date_from,
    )


def fetch_cached_cms_raw_data(
    *,
    as_of: str,
    date_from: str | None = None,
    force_refresh: bool = False,
    entity_code: str = "PL",
) -> tuple[dict[str, object], dict[str, object], CmsEffectiveDates]:
    resolved_entity_code = str(entity_code or "").strip().upper()
    dates = resolve_cms_effective_dates(as_of, date_from)
    raw, cache_info = get_or_fetch_cms_raw_data(
        as_of=as_of,
        date_from=dates.date_from,
        date_to=dates.date_to,
        logistics_date_from=dates.logistics_date_from,
        entity_code=resolved_entity_code,
        fetcher=lambda: fetch_cms_data(
            as_of,
            date_from=dates.date_from,
            date_to=dates.date_to,
            shipping_date_from=dates.logistics_date_from,
            open_po_date_from=dates.logistics_date_from,
            include_sales_detail=True,
            entity_code=resolved_entity_code,
        ),
        force_refresh=force_refresh,
    )
    # The cache key predates the CMS actual-KRW rollout. Do not let a valid but
    # older snapshot silently restore the legacy current-rate conversion path.
    if not force_refresh and not _has_actual_krw_contract(raw):
        raw, cache_info = get_or_fetch_cms_raw_data(
            as_of=as_of,
            date_from=dates.date_from,
            date_to=dates.date_to,
            logistics_date_from=dates.logistics_date_from,
            entity_code=resolved_entity_code,
            fetcher=lambda: fetch_cms_data(
                as_of,
                date_from=dates.date_from,
                date_to=dates.date_to,
                shipping_date_from=dates.logistics_date_from,
                open_po_date_from=dates.logistics_date_from,
                include_sales_detail=True,
                entity_code=resolved_entity_code,
            ),
            force_refresh=True,
        )
    return raw, cache_info, dates


def _fetch_v3_inventory_snapshot(
    *,
    as_of: str,
    dates: CmsEffectiveDates,
    entity_code: str,
) -> dict[str, object]:
    """Fetch a PL/USA V3 snapshot whose ① 미입고 uses the 30-day PO window.

    The two open-PO queries are independent, so they run together and the pair
    costs about one extra request rather than a second serial round trip.
    """

    unreceived_start, unreceived_end = unreceived_po_window(as_of)
    with ThreadPoolExecutor(max_workers=2) as pool:
        full_future = pool.submit(
            fetch_cms_data,
            as_of,
            date_from=dates.date_from,
            date_to=dates.date_to,
            shipping_date_from=dates.logistics_date_from,
            open_po_date_from=dates.logistics_date_from,
            include_sales_detail=False,
            include_lead_time_detail=False,
            entity_code=entity_code,
        )
        recent_future = pool.submit(
            fetch_cms_open_po,
            entity_code,
            date_from=unreceived_start.isoformat(),
            date_to=unreceived_end.isoformat(),
        )
        # Both sources are required; never cache a partial snapshot.
        raw = full_future.result()
        recent_open_po = recent_future.result()

    merged_open_po, unreceived_window = merge_open_po_unreceived_window(
        raw.get("open_po") or [], recent_open_po, as_of=as_of,
    )
    return {
        **raw,
        "open_po": merged_open_po,
        # Audit only. Consumers iterate list-valued sources, so this mapping is
        # carried through the snapshot without joining the calculation inputs.
        "open_po_unreceived_window": unreceived_window,
    }


def fetch_cached_cms_inventory_raw_data(
    *,
    as_of: str,
    date_from: str | None = None,
    force_refresh: bool = False,
    entity_code: str = "PL",
) -> tuple[dict[str, object], dict[str, object], CmsEffectiveDates]:
    """Fetch a PL/USA inventory-position snapshot without V2-only sales/ETA feeds.

    V3 keeps its demand history in the dedicated 24-month season source.  The
    inventory-position adapter needs only stocks, shipping quantities, and
    open-PO statuses, so using the complete V2 raw snapshot would refetch a
    second, overlapping sales window on every cold V3 run.

    ① 미입고 수량만 PO 등록일 최근 30 달력일로 좁힌다. ``/eu/open-po``·
    ``/us/open-po``는 ①~④를 상품 단위 한 행으로 집계하고 행에 PO 등록일을 주지
    않으므로, 같은 피드를 전체 창과 30일 창으로 두 번 조회해 ① 계열 수량만
    바꿔 넣는다. ② PNFM확정·③ 입고진행중은 이미 확실히 들어올 물량이라 PO
    등록일이 오래되었다는 이유로 빼지 않는다. 운송중(shipping) 조회창과 V2의
    ``fetch_cached_cms_raw_data`` 조회창도 그대로 1월 1일 기준을 유지한다.
    """

    resolved_entity_code = str(entity_code or "").strip().upper()
    dates = resolve_cms_effective_dates(as_of, date_from)
    raw, cache_info = get_or_fetch_cms_raw_data(
        as_of=as_of,
        date_from=dates.date_from,
        date_to=dates.date_to,
        logistics_date_from=dates.logistics_date_from,
        entity_code=resolved_entity_code,
        # The cache key covers as_of but NOT the 미입고 lookback length, so the
        # scope carries it. Changing V3_UNRECEIVED_LOOKBACK_DAYS therefore
        # invalidates these snapshots instead of serving a payload built for
        # the previous window.
        cache_scope=unreceived_cache_scope(),
        fetcher=lambda: _fetch_v3_inventory_snapshot(
            as_of=as_of, dates=dates, entity_code=resolved_entity_code,
        ),
        force_refresh=force_refresh,
    )
    return raw, cache_info, dates


def fetch_cached_hq_opo_raw_data(
    *,
    as_of: str,
    date_from: str,
    date_to: str,
    force_refresh: bool = False,
) -> tuple[dict[str, object], dict[str, object]]:
    """Fetch and cache one HQ/OPO snapshot for the given demand window.

    The headquarters sales feed spans every warehouse and pages slowly, so the
    shared on-disk cache keeps a repeated HQ run from refetching it.  The cache
    key already includes ``entity_code``, which keeps HQ payloads separate from
    PL and USA.
    """

    raw, cache_info = get_or_fetch_cms_raw_data(
        as_of=as_of,
        date_from=date_from,
        date_to=date_to,
        logistics_date_from=date_from,
        entity_code="HQ",
        fetcher=lambda: fetch_hq_opo_data(
            date_from=date_from,
            date_to=date_to,
        ),
        force_refresh=force_refresh,
    )
    # HQ v4 캐시 도입 직후 생성된 일부 snapshot에는 과거 표시용
    # inbound_history가 남아 있다. 현재 ④는 inbound_confirmed.completed_qty가
    # 기준이므로 계산 원천에서 제거해 새 계약과 동일하게 정규화한다.
    normalized = dict(raw)
    normalized.pop("inbound_history", None)
    return normalized, cache_info
