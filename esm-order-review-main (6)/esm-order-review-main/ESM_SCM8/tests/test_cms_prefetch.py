from __future__ import annotations

from datetime import datetime

from backend.services import cms_prefetch
from backend.services.cms_source import resolve_cms_effective_dates
from core.common import KST


def _patch_common(monkeypatch, captured: dict[str, object]) -> None:
    def fake_fetch_cached_cms_raw_data(
        *,
        as_of: str,
        date_from: str | None = None,
        force_refresh: bool = False,
    ):
        captured["as_of"] = as_of
        captured["date_from"] = date_from
        captured["force_refresh"] = force_refresh
        return {"sales_local": []}, {"hit": False, "source": "cms_api"}, resolve_cms_effective_dates(as_of, date_from)

    def fake_fetch_cached_season_trend_source_data(
        *,
        date_from: str,
        date_to: str,
        eu_sold_only: bool = True,
        force_refresh: bool = False,
    ):
        captured["season_date_from"] = date_from
        captured["season_date_to"] = date_to
        captured["season_force_refresh"] = force_refresh
        return {"sales_history": [], "prod_list": []}, {"sales_history": {"rows": 0}}

    monkeypatch.setattr(cms_prefetch, "SCM_PRE_ANALYSIS_HOURS_KST", "8-20")
    monkeypatch.setattr(cms_prefetch, "fetch_cached_cms_raw_data", fake_fetch_cached_cms_raw_data)
    monkeypatch.setattr(cms_prefetch, "fetch_cached_season_trend_source_data", fake_fetch_cached_season_trend_source_data)
    monkeypatch.setattr(cms_prefetch, "prune_disk_cache", lambda: {"removed": 0, "kept": 0, "freed_bytes": 0, "skipped": False})
    monkeypatch.setattr(cms_prefetch, "write_audit_event", lambda *args, **kwargs: None)


def test_prefetch_uses_force_refresh_inside_business_hours(monkeypatch):
    captured: dict[str, object] = {}
    _patch_common(monkeypatch, captured)

    result = cms_prefetch.prefetch_cms_raw_data_once(datetime(2026, 7, 2, 10, 0, tzinfo=KST))

    assert result["status"] == "done"
    assert captured["as_of"] == "2026-07-02"
    assert captured["date_from"] is None
    assert captured["force_refresh"] is True


def test_prefetch_warms_season_default_range(monkeypatch):
    captured: dict[str, object] = {}
    _patch_common(monkeypatch, captured)

    result = cms_prefetch.prefetch_cms_raw_data_once(datetime(2026, 7, 2, 10, 0, tzinfo=KST))

    # 분석 탭 기본 선택(최근 1년)과 동일한 기간이어야 캐시 키가 일치한다.
    # 프론트 demandRange(12)는 종료일을 "어제"로 잡는다. 2026-07-02에 예열하면
    # 화면이 요청하는 구간은 2025-07-01~2026-07-01이다.
    assert captured["season_date_from"] == "2025-07-01"
    assert captured["season_date_to"] == "2026-07-01"
    assert captured["season_force_refresh"] is True
    assert result["season"]["status"] == "done"


def test_prefetch_warms_season_even_when_order_fetch_fails(monkeypatch):
    captured: dict[str, object] = {}
    _patch_common(monkeypatch, captured)

    def failing_fetch(**kwargs: object):
        raise RuntimeError("CMS down")

    monkeypatch.setattr(cms_prefetch, "fetch_cached_cms_raw_data", failing_fetch)

    result = cms_prefetch.prefetch_cms_raw_data_once(datetime(2026, 7, 2, 10, 0, tzinfo=KST))

    assert result["status"] == "failed"
    assert result["season"]["status"] == "done"
    assert captured["season_date_to"] == "2026-07-01"


def test_prefetch_skips_outside_business_hours(monkeypatch):
    called = {"value": False}

    def fake_fetch_cached_cms_raw_data(**kwargs: object):
        called["value"] = True
        return {}, {}, resolve_cms_effective_dates("2026-07-02")

    monkeypatch.setattr(cms_prefetch, "SCM_PRE_ANALYSIS_HOURS_KST", "8-20")
    monkeypatch.setattr(cms_prefetch, "fetch_cached_cms_raw_data", fake_fetch_cached_cms_raw_data)
    monkeypatch.setattr(cms_prefetch, "fetch_cached_season_trend_source_data", fake_fetch_cached_cms_raw_data)

    result = cms_prefetch.prefetch_cms_raw_data_once(datetime(2026, 7, 2, 22, 0, tzinfo=KST))

    assert result["status"] == "skipped"
    assert result["reason"] == "outside_hours"
    assert called["value"] is False


def test_season_default_range_clamps_month_end():
    """종료일(어제)이 말일인 경우의 12개월 전 계산.

    화면 기본값과의 정합성 표는 tests/test_cms_prefetch_range_alignment.py에 있다.
    """
    # 2026-04-01 예열 → 어제는 2026-03-31, 12개월 전 2025-03-31은 존재한다.
    assert cms_prefetch._season_default_range("2026-04-01") == ("2025-03-31", "2026-03-31")
    # 2026-03-01 예열 → 어제는 평년 2월 말일 2026-02-28.
    assert cms_prefetch._season_default_range("2026-03-01") == ("2025-02-28", "2026-02-28")
    # 윤년: 어제가 2028-02-29면 12개월 전은 2027-02-28로 클램프된다.
    assert cms_prefetch._season_default_range("2028-03-01") == ("2027-02-28", "2028-02-29")
