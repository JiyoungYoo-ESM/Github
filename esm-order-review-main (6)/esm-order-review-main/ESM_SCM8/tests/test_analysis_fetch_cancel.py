"""Cooperative cancellation of the CMS page loop.

The abandoned fetch used to keep pulling all 75 pages after 중단, competing with
the user's restarted analysis (measured 2026-07-30: page latency 2s → 10s).
"""

from __future__ import annotations

import threading

import pytest

from backend import season_trend_api_client as client
from backend.services import analysis_cancel

PAGE_SIZE = client.PAGE_SIZE
TOTAL_ROWS = PAGE_SIZE * 8  # 8 pages


@pytest.fixture(autouse=True)
def clean_tokens():
    analysis_cancel._CURRENT_TOKEN.set(None)
    with analysis_cancel._TOKENS_LOCK:
        analysis_cancel._TOKENS.clear()
    yield
    analysis_cancel._CURRENT_TOKEN.set(None)
    with analysis_cancel._TOKENS_LOCK:
        analysis_cancel._TOKENS.clear()


def _page_rows(page: int) -> list[dict[str, object]]:
    return [{"row": (page - 1) * PAGE_SIZE + index} for index in range(PAGE_SIZE)]


def test_page_loop_fetches_every_page_when_not_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[int] = []
    lock = threading.Lock()

    def fake_fetch_page(path, params, page, include_total=True, page_size=PAGE_SIZE):
        with lock:
            requested.append(page)
        return {"items": _page_rows(page), "total": TOTAL_ROWS}

    monkeypatch.setattr(client, "_fetch_page", fake_fetch_page)

    # PL sales history uses the monthly streaming path; exercise the ordinary
    # total-based paginator with the product endpoint instead.
    items, meta = client._fetch_paged(client.EU_PRODUCTS_ENDPOINT, {"date_from": "2026-01-01"})

    assert len(items) == TOTAL_ROWS
    assert sorted(requested) == list(range(1, 9))
    assert meta["pages"] == 8


def test_cancelling_stops_the_page_loop_and_returns_no_partial_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancel after page 1: remaining pages must not be requested, and the
    fetch must raise rather than hand back the pages it already had."""
    token = analysis_cancel.register("job-cancel-test")
    requested: list[int] = []
    lock = threading.Lock()

    def fake_fetch_page(path, params, page, include_total=True, page_size=PAGE_SIZE):
        with lock:
            requested.append(page)
        if page == 1:
            # The user presses 중단 while the first page is in flight.
            token.cancel()
        return {"items": _page_rows(page), "total": TOTAL_ROWS}

    monkeypatch.setattr(client, "_fetch_page", fake_fetch_page)

    with pytest.raises(analysis_cancel.AnalysisCancelled):
        client._fetch_paged(client.EU_PRODUCTS_ENDPOINT, {"date_from": "2026-01-01"})

    # Page 1 was already in flight; pages 2..8 must have been skipped.
    assert requested == [1], f"cancelled fetch still hit CMS pages: {requested}"


def test_cancelling_stops_the_hq_long_history_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """본사/미주 판매이력은 배치 스트리밍이라 배치 경계에서 멈춰야 한다."""
    token = analysis_cancel.register("job-hq-cancel")
    requested: list[int] = []
    lock = threading.Lock()
    long_page_size = client.LONG_HISTORY_PAGE_SIZE

    def fake_fetch_page(path, params, page, include_total=True, page_size=long_page_size):
        with lock:
            requested.append(page)
        if page == 1:
            token.cancel()
        # A full page keeps the stream asking for more until cancelled.
        return {"items": [{"row": index} for index in range(long_page_size)]}

    monkeypatch.setattr(client, "_fetch_page", fake_fetch_page)

    with pytest.raises(analysis_cancel.AnalysisCancelled):
        client._fetch_long_history_without_total("/us/sales/history", {"date_from": "2026-01-01"})

    # Without the check this would stream up to MAX_STREAMED_PAGES (10,000).
    assert len(requested) <= client.MAX_PARALLEL_PAGE_REQUESTS, (
        f"cancelled HQ stream kept paging: {len(requested)} pages"
    )


def test_cancel_token_is_scoped_to_its_own_job() -> None:
    first = analysis_cancel.register("job-a")
    assert not analysis_cancel.is_cancelled()

    # Cancelling an unrelated job must not stop this one.
    assert analysis_cancel.cancel("job-b") is False
    assert not analysis_cancel.is_cancelled()

    assert analysis_cancel.cancel("job-a") is True
    assert analysis_cancel.is_cancelled()
    assert first.cancelled

    analysis_cancel.unregister("job-a")
    assert analysis_cancel.active_token_count() == 0


def test_unregistered_job_never_blocks_a_normal_fetch() -> None:
    """With no token bound, the fetch must behave exactly as before."""
    assert not analysis_cancel.is_cancelled()
    analysis_cancel.raise_if_cancelled()
