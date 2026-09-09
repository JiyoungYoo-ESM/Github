from __future__ import annotations

from datetime import date
import threading

import pytest

from backend import season_trend_api_client
from backend.services import analysis_cancel, cms_fetch_cache


@pytest.fixture(autouse=True)
def isolated_source_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cms_fetch_cache, "CMS_FETCH_CACHE_DIR", tmp_path)
    cms_fetch_cache._MEMORY_CACHE.clear()
    cms_fetch_cache._KEY_LOCKS.clear()
    yield
    cms_fetch_cache._MEMORY_CACHE.clear()
    cms_fetch_cache._KEY_LOCKS.clear()


def _paged_meta(path: str, rows: int) -> dict[str, object]:
    return {"path": path, "rows": rows, "api_total": rows, "pages": 1, "duration_seconds": 0.01}


def test_paged_fetch_retries_a_failed_parallel_page_sequentially(monkeypatch):
    attempts: dict[int, int] = {}
    attempt_lock = threading.Lock()
    monkeypatch.setattr(season_trend_api_client, "LONG_HISTORY_PAGE_SIZE", 1)

    def fake_fetch_page(
        path: str,
        params: dict[str, object],
        page: int,
        include_total: bool = True,
        page_size: int = season_trend_api_client.PAGE_SIZE,
    ):
        assert path == season_trend_api_client.EU_SALES_ENDPOINT
        assert page_size == 1
        with attempt_lock:
            attempts[page] = attempts.get(page, 0) + 1
            attempt = attempts[page]
        if page == 1:
            return {"items": [{"page": 1}]}
        if page == 2 and attempt == 1:
            raise RuntimeError("temporary CMS overload")
        if page in {2, 3}:
            return {"items": [{"page": page}]}
        return {"items": []}

    monkeypatch.setattr(season_trend_api_client, "_fetch_page", fake_fetch_page)

    rows, meta = season_trend_api_client._fetch_long_history_without_total(
        season_trend_api_client.EU_SALES_ENDPOINT,
        {"date_from": "2025-01-01", "date_to": "2026-01-01"},
    )

    assert [row["page"] for row in rows] == [1, 2, 3]
    assert attempts[2] == 2
    assert meta["recovered_pages"] == [2]


def test_hq_history_streams_pages_without_total_count(monkeypatch):
    calls: list[tuple[int, bool, int]] = []
    monkeypatch.setattr(season_trend_api_client, "LONG_HISTORY_PAGE_SIZE", 2)
    monkeypatch.setattr(season_trend_api_client, "MAX_PARALLEL_PAGE_REQUESTS", 2)

    def fake_fetch_page(
        path: str,
        params: dict[str, object],
        page: int,
        include_total: bool = True,
        page_size: int = season_trend_api_client.PAGE_SIZE,
    ):
        assert path == season_trend_api_client.HQ_SALES_HISTORY_ENDPOINT
        calls.append((page, include_total, page_size))
        if page == 1:
            return {"items": [{"page": 1}, {"page": 1}]}
        if page == 2:
            return {"items": [{"page": 2}]}
        return {"items": []}

    monkeypatch.setattr(season_trend_api_client, "_fetch_page", fake_fetch_page)

    rows, meta = season_trend_api_client._fetch_long_history_without_total(
        season_trend_api_client.HQ_SALES_HISTORY_ENDPOINT,
        {"date_from": "2025-01-01", "date_to": "2026-01-01"},
    )

    assert [row["page"] for row in rows] == [1, 1, 2]
    assert calls[:2] == [(1, False, 2), (2, False, 2)]
    assert meta["include_total"] is False
    assert meta["api_total"] == 3
    assert meta["pages"] == 2
    assert meta["page_size"] == 2


def test_hq_history_splits_broad_date_range_into_month_chunks(monkeypatch):
    chunks: list[tuple[str, str]] = []

    def fake_fetch_without_total(
        path: str,
        params: dict[str, object],
        *,
        max_workers: int | None = None,
    ):
        assert max_workers == season_trend_api_client.LONG_HISTORY_PAGE_WORKERS
        date_from = str(params["date_from"])
        date_to = str(params["date_to"])
        chunks.append((date_from, date_to))
        rows = [
            {"ship_dt": date_from, "range": f"{date_from}:{date_to}:start"},
            {"ship_dt": date_to, "range": f"{date_from}:{date_to}:end"},
        ]
        return rows, {
            "path": path,
            "rows": 2,
            "api_total": 2,
            "pages": 1,
            "include_total": False,
            "recovered_pages": [],
            "duration_seconds": 0.01,
        }

    monkeypatch.setattr(
        season_trend_api_client,
        "_fetch_long_history_without_total",
        fake_fetch_without_total,
    )

    rows, meta = season_trend_api_client._fetch_paged(
        season_trend_api_client.HQ_SALES_HISTORY_ENDPOINT,
        {"date_from": "2025-01-15", "date_to": "2025-03-05"},
    )

    assert sorted(chunks) == [
        ("2025-01-01", "2025-01-31"),
        ("2025-02-01", "2025-02-28"),
        ("2025-03-01", "2025-03-31"),
    ]
    assert [row["ship_dt"] for row in rows] == [
        "2025-01-31",
        "2025-02-01",
        "2025-02-28",
        "2025-03-01",
    ]
    assert meta["pages"] == 3
    assert len(meta["date_chunks"]) == 3
    assert meta["date_chunks"][0]["date_from"] == "2025-01-15"
    assert meta["date_chunks"][0]["cache_date_from"] == "2025-01-01"
    assert meta["date_chunks"][-1]["date_to"] == "2025-03-05"
    assert meta["date_chunks"][-1]["cache_date_to"] == "2025-03-31"


def test_month_fetch_submits_only_one_pending_result_per_worker(monkeypatch):
    january_release = threading.Event()
    february_done = threading.Event()
    march_started = threading.Event()
    completed: list[tuple[list[dict[str, object]], dict[str, object]]] = []
    failures: list[BaseException] = []
    monkeypatch.setattr(season_trend_api_client, "LONG_HISTORY_MONTH_WORKERS", 2)

    def fake_fetch_month(
        path: str,
        params: dict[str, object],
        *,
        month_start: date,
        month_end: date,
        force_refresh: bool = False,
    ):
        del params, force_refresh
        if month_start.month == 1:
            assert january_release.wait(5)
        elif month_start.month == 2:
            february_done.set()
        else:
            march_started.set()
        rows = [{"ship_dt": month_start.isoformat()}]
        return rows, {
            "path": path,
            "rows": 1,
            "api_total": 1,
            "pages": 1,
            "include_total": False,
            "cache": {"hit": False},
            "cache_date_from": month_start.isoformat(),
            "cache_date_to": month_end.isoformat(),
        }

    monkeypatch.setattr(
        season_trend_api_client,
        "_fetch_cached_long_history_month",
        fake_fetch_month,
    )

    def run_fetch() -> None:
        try:
            completed.append(
                season_trend_api_client._fetch_long_history_by_month(
                    season_trend_api_client.HQ_SALES_HISTORY_ENDPOINT,
                    {"date_from": "2025-01-01", "date_to": "2025-03-31"},
                )
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    worker = threading.Thread(target=run_fetch)
    worker.start()
    try:
        assert february_done.wait(5)
        # January still owns the first ordered result.  An eager Executor.map
        # would already start March on the now-free second worker.
        assert not march_started.wait(0.05)
    finally:
        january_release.set()
        worker.join(5)

    assert not worker.is_alive()
    assert failures == []
    assert march_started.is_set()
    assert len(completed[0][0]) == 3


def test_month_worker_receives_parent_analysis_cancel_token(monkeypatch):
    token = analysis_cancel.CancelToken()
    observed_tokens = []
    monkeypatch.setattr(season_trend_api_client.analysis_cancel, "current_token", lambda: token)

    def fake_fetch_month(
        path: str,
        params: dict[str, object],
        *,
        month_start: date,
        month_end: date,
        force_refresh: bool = False,
        cancel_token=None,
    ):
        del params, force_refresh
        observed_tokens.append(cancel_token)
        return [{"ship_dt": month_start.isoformat()}], {
            "path": path,
            "rows": 1,
            "api_total": 1,
            "pages": 1,
            "cache_date_from": month_start.isoformat(),
            "cache_date_to": month_end.isoformat(),
            "cache": {"hit": False},
        }

    monkeypatch.setattr(
        season_trend_api_client,
        "_fetch_cached_long_history_month",
        fake_fetch_month,
    )

    rows, _meta = season_trend_api_client._fetch_long_history_by_month(
        season_trend_api_client.HQ_SALES_HISTORY_ENDPOINT,
        {"date_from": "2025-01-01", "date_to": "2025-02-28"},
    )

    assert len(rows) == 2
    assert observed_tokens == [token, token]


def test_cancelled_long_history_stops_before_requesting_another_page(monkeypatch):
    token = analysis_cancel.CancelToken()
    token.cancel()
    monkeypatch.setattr(
        season_trend_api_client,
        "_fetch_page",
        lambda *args, **kwargs: pytest.fail("cancelled fetch must not call CMS"),
    )

    with pytest.raises(analysis_cancel.AnalysisCancelled):
        season_trend_api_client._fetch_long_history_without_total(
            season_trend_api_client.HQ_SALES_HISTORY_ENDPOINT,
            {"date_from": "2025-01-01", "date_to": "2025-01-31"},
            cancel_token=token,
        )


@pytest.mark.parametrize(
    ("path", "entity_code"),
    [
        (season_trend_api_client.HQ_SALES_HISTORY_ENDPOINT, "HQ"),
        (season_trend_api_client.US_SALES_ENDPOINT, "USA"),
    ],
)
def test_long_history_overlapping_ranges_fetch_only_new_calendar_month(
    path,
    entity_code,
    monkeypatch,
):
    assert season_trend_api_client.LONG_HISTORY_ENTITY_BY_PATH[path] == entity_code
    calls: dict[tuple[str, str], int] = {}

    def fake_fetch_without_total(
        requested_path: str,
        params: dict[str, object],
        *,
        max_workers: int | None = None,
    ):
        assert requested_path == path
        assert max_workers == season_trend_api_client.LONG_HISTORY_PAGE_WORKERS
        key = (str(params["date_from"]), str(params["date_to"]))
        calls[key] = calls.get(key, 0) + 1
        return (
            [{"ship_dt": f"{str(params['date_from'])[:7]}-15"}],
            {
                "path": path,
                "rows": 1,
                "api_total": 1,
                "pages": 1,
                "include_total": False,
                "recovered_pages": [],
                "duration_seconds": 0.01,
            },
        )

    monkeypatch.setattr(
        season_trend_api_client,
        "_fetch_long_history_without_total",
        fake_fetch_without_total,
    )

    first_rows, first_meta = season_trend_api_client._fetch_paged(
        path,
        {"date_from": "2025-01-15", "date_to": "2025-03-20"},
    )
    second_rows, second_meta = season_trend_api_client._fetch_paged(
        path,
        {"date_from": "2025-02-10", "date_to": "2025-04-20"},
    )

    assert len(first_rows) == 3
    assert len(second_rows) == 3
    assert calls == {
        ("2025-01-01", "2025-01-31"): 1,
        ("2025-02-01", "2025-02-28"): 1,
        ("2025-03-01", "2025-03-31"): 1,
        ("2025-04-01", "2025-04-30"): 1,
    }
    assert first_meta["cache"]["misses"] == 3
    assert second_meta["cache"]["hits"] == 2
    assert second_meta["cache"]["misses"] == 1

    _refreshed_rows, refreshed_meta = season_trend_api_client._fetch_paged(
        path,
        {"date_from": "2025-02-10", "date_to": "2025-02-20"},
        force_refresh=True,
    )
    assert calls[("2025-02-01", "2025-02-28")] == 2
    assert refreshed_meta["cache"]["misses"] == 1


def test_current_month_cache_fetches_through_today_and_reuses_partial_bound(monkeypatch):
    today = date(2026, 7, 28)
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(season_trend_api_client, "korea_today", lambda: today)
    monkeypatch.setattr(cms_fetch_cache, "korea_today", lambda: today)
    monkeypatch.setattr(cms_fetch_cache, "CMS_TODAY_CACHE_TTL_SECONDS", 100)

    def fake_fetch_without_total(
        path: str,
        params: dict[str, object],
        *,
        max_workers: int | None = None,
    ):
        del path, max_workers
        calls.append((str(params["date_from"]), str(params["date_to"])))
        return (
            [
                {"ship_dt": "2026-07-27"},
                {"ship_dt": "2026-07-28"},
            ],
            {
                "path": season_trend_api_client.HQ_SALES_HISTORY_ENDPOINT,
                "rows": 2,
                "api_total": 2,
                "pages": 1,
                "include_total": False,
                "duration_seconds": 0.01,
            },
        )

    monkeypatch.setattr(
        season_trend_api_client,
        "_fetch_long_history_without_total",
        fake_fetch_without_total,
    )

    first_rows, first_meta = season_trend_api_client._fetch_paged(
        season_trend_api_client.HQ_SALES_HISTORY_ENDPOINT,
        {"date_from": "2026-07-01", "date_to": "2026-07-27"},
    )
    second_rows, second_meta = season_trend_api_client._fetch_paged(
        season_trend_api_client.HQ_SALES_HISTORY_ENDPOINT,
        {"date_from": "2026-07-20", "date_to": "2026-07-26"},
    )

    assert calls == [("2026-07-01", "2026-07-28")]
    assert [row["ship_dt"] for row in first_rows] == ["2026-07-27"]
    assert second_rows == []
    assert first_meta["date_chunks"][0]["cache"]["ttl_seconds"] == 100
    assert second_meta["cache"]["hits"] == 1


def test_product_master_cache_is_independent_from_analysis_period(monkeypatch):
    calls = {"count": 0}

    def fake_fetch_paged(
        path: str,
        params: dict[str, object] | None = None,
        *,
        force_refresh: bool = False,
    ):
        del force_refresh
        assert path == season_trend_api_client.EU_PRODUCTS_ENDPOINT
        assert dict(params or {})["eu_sold_only"] == "false"
        calls["count"] += 1
        rows = [{"prod_cd": "SKU-1"}]
        return rows, _paged_meta(path, len(rows))

    monkeypatch.setattr(season_trend_api_client, "_fetch_paged", fake_fetch_paged)

    first_rows, first_meta = season_trend_api_client._fetch_cached_product_master(
        eu_sold_only=False,
    )
    second_rows, second_meta = season_trend_api_client._fetch_cached_product_master(
        eu_sold_only=False,
    )

    assert first_rows == second_rows == [{"prod_cd": "SKU-1"}]
    assert calls["count"] == 1
    assert first_meta["cache"]["hit"] is False
    assert second_meta["cache"]["hit"] is True


def test_fetch_supplements_products_missing_from_eu_sold_list(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_fetch_paged(
        path: str,
        params: dict[str, object] | None = None,
        *,
        force_refresh: bool = False,
    ):
        del force_refresh
        request_params = dict(params or {})
        calls.append({"path": path, "params": request_params})
        if path == season_trend_api_client.EU_SALES_ENDPOINT:
            rows = [{"prod_cd": "NAIL-1", "ship_dt": "2024-05-01"}, {"prod_cd": "SKU-1", "ship_dt": "2024-05-02"}]
            return rows, _paged_meta(path, len(rows))
        if request_params.get("eu_sold_only") == "true":
            rows = [{"prod_cd": "SKU-1", "class1_nm": "스킨케어"}]
            return rows, _paged_meta(path, len(rows))
        # eu_sold_only 없는 전체 상품목록
        rows = [
            {"prod_cd": "NAIL-1", "class1_nm": "네일", "class2_nm": "네일컬러"},
            {"prod_cd": "UNRELATED", "class1_nm": "기타"},
        ]
        return rows, _paged_meta(path, len(rows))

    monkeypatch.setattr(season_trend_api_client, "_fetch_paged", fake_fetch_paged)

    raw, meta = season_trend_api_client.fetch_season_trend_source_data(
        date_from="2024-04-01",
        date_to="2024-12-31",
    )

    codes = {row["prod_cd"] for row in raw["prod_list"]}
    assert codes == {"SKU-1", "NAIL-1"}  # 판매된 누락 SKU만 보충, 무관 SKU는 제외
    assert meta["prod_list"]["rows"] == 2
    assert meta["prod_list"]["supplement"]["missing_codes"] == 1
    assert meta["prod_list"]["supplement"]["supplemented_rows"] == 1
    # 판매이력 1회 + eu_sold 목록 1회 + 전체 목록 1회
    assert len(calls) == 3


def test_fetch_skips_full_catalog_when_nothing_missing(monkeypatch):
    calls: list[str] = []

    def fake_fetch_paged(
        path: str,
        params: dict[str, object] | None = None,
        *,
        force_refresh: bool = False,
    ):
        del force_refresh
        request_params = dict(params or {})
        calls.append(path)
        if path == season_trend_api_client.EU_SALES_ENDPOINT:
            rows = [{"prod_cd": "SKU-1", "ship_dt": "2024-05-01"}]
            return rows, _paged_meta(path, len(rows))
        assert request_params.get("eu_sold_only") == "true", "누락 SKU가 없으면 전체 목록을 조회하지 않아야 한다"
        rows = [{"prod_cd": "SKU-1", "class1_nm": "스킨케어"}]
        return rows, _paged_meta(path, len(rows))

    monkeypatch.setattr(season_trend_api_client, "_fetch_paged", fake_fetch_paged)

    raw, meta = season_trend_api_client.fetch_season_trend_source_data(
        date_from="2024-04-01",
        date_to="2024-12-31",
    )

    assert len(calls) == 2
    assert "supplement" not in meta["prod_list"]


def test_fetch_cached_season_trend_source_data_reuses_same_date_range(tmp_path, monkeypatch):
    calls = {"count": 0}

    def fake_fetch_season_trend_source_data(
        *,
        date_from: str,
        date_to: str,
        eu_sold_only: bool = True,
        entity_code: str = "PL",
        force_refresh: bool = False,
    ):
        del force_refresh
        calls["count"] += 1
        return (
            {
                "sales_history": [{"prod_cd": "SKU-1", "ship_dt": date_from}],
                "prod_list": [{"prod_cd": "SKU-1"}],
            },
            {
                "sales_history": {
                    "path": season_trend_api_client.EU_SALES_ENDPOINT,
                    "rows": 1,
                    "api_total": 1,
                    "pages": 1,
                    "duration_seconds": 0.01,
                },
                "prod_list": {
                    "path": season_trend_api_client.EU_PRODUCTS_ENDPOINT,
                    "rows": 1,
                    "api_total": 1,
                    "pages": 1,
                    "duration_seconds": 0.01,
                },
                "eu_sold_only": eu_sold_only,
                "entity_code": entity_code,
                "amount_currency": "EUR",
            },
        )

    monkeypatch.setattr(cms_fetch_cache, "CMS_FETCH_CACHE_DIR", tmp_path)
    cms_fetch_cache._MEMORY_CACHE.clear()
    cms_fetch_cache._KEY_LOCKS.clear()
    monkeypatch.setattr(
        season_trend_api_client,
        "fetch_season_trend_source_data",
        fake_fetch_season_trend_source_data,
    )

    raw, meta = season_trend_api_client.fetch_cached_season_trend_source_data(
        date_from="2025-07-07",
        date_to="2026-07-07",
    )
    raw_again, meta_again = season_trend_api_client.fetch_cached_season_trend_source_data(
        date_from="2025-07-07",
        date_to="2026-07-07",
    )

    assert calls["count"] == 1
    assert raw_again == raw
    assert meta["cache"]["source"] == "cms_api"
    assert meta_again["cache"]["hit"] is True
    assert meta_again["cache"]["source"] == "memory"


def test_us_season_source_uses_local_sales_and_full_product_catalog(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_fetch_paged(
        path: str,
        params: dict[str, object] | None = None,
        *,
        force_refresh: bool = False,
    ):
        del force_refresh
        request_params = dict(params or {})
        calls.append((path, request_params))
        if path == season_trend_api_client.US_SALES_ENDPOINT:
            rows = [{"prod_cd": "US-SKU", "ship_dt": "2026-07-01"}]
        else:
            rows = [{"prod_cd": "US-SKU", "class1_nm": "스킨케어"}]
        return rows, _paged_meta(path, len(rows))

    monkeypatch.setattr(season_trend_api_client, "_fetch_paged", fake_fetch_paged)

    _raw, meta = season_trend_api_client.fetch_season_trend_source_data(
        date_from="2025-07-01",
        date_to="2026-07-01",
        entity_code="USA",
    )

    assert {path for path, _params in calls} == {
        season_trend_api_client.US_SALES_ENDPOINT,
        season_trend_api_client.EU_PRODUCTS_ENDPOINT,
    }
    product_params = next(params for path, params in calls if path == season_trend_api_client.EU_PRODUCTS_ENDPOINT)
    assert product_params["eu_sold_only"] == "false"
    assert meta["entity_code"] == "USA"
    assert meta["amount_currency"] == "USD"


def test_hq_season_source_uses_hq_history_and_full_product_catalog(monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_fetch_paged(
        path: str,
        params: dict[str, object] | None = None,
        *,
        force_refresh: bool = False,
    ):
        del force_refresh
        request_params = dict(params or {})
        calls.append((path, request_params))
        if path == season_trend_api_client.HQ_SALES_HISTORY_ENDPOINT:
            rows = [{"prod_cd": "HQ-SKU", "ship_dt": "2026-07-01", "amount_krw": "10000"}]
        else:
            rows = [{"prod_cd": "HQ-SKU", "class1_nm": "스킨케어"}]
        return rows, _paged_meta(path, len(rows))

    monkeypatch.setattr(season_trend_api_client, "_fetch_paged", fake_fetch_paged)

    raw, meta = season_trend_api_client.fetch_season_trend_source_data(
        date_from="2025-07-01",
        date_to="2026-07-01",
        entity_code="HQ",
    )

    assert raw["sales_history"][0]["amount_krw"] == "10000"
    assert {path for path, _params in calls} == {
        season_trend_api_client.HQ_SALES_HISTORY_ENDPOINT,
        season_trend_api_client.EU_PRODUCTS_ENDPOINT,
    }
    product_params = next(params for path, params in calls if path == season_trend_api_client.EU_PRODUCTS_ENDPOINT)
    assert product_params["eu_sold_only"] == "false"
    assert meta["entity_code"] == "HQ"
    assert meta["amount_currency"] == "KRW"
