"""저장된 분석 결과 재사용 규칙.

2026-07-30 결정: 결과 캐시에 신선도 규칙이 아예 없어서, 기간이 오늘을 포함한
채 계산된 결과(마지막 하루가 미완성)가 그날이 끝난 뒤에도 영구히 재사용됐다.
"""

from __future__ import annotations

import pytest

from backend.services.season_cache_service import (
    SEASON_ANALYSIS_SCHEMA_VERSION,
    cached_result_is_current,
    latest_api_analysis_matches,
)


class TestCachedResultIsCurrent:
    def test_period_already_closed_when_computed_is_reusable_forever(self) -> None:
        """2025년 분석을 2026년에 계산 → 판매가 더 늘어날 수 없으므로 재사용."""
        assert cached_result_is_current(
            computed_date="2026-07-30",
            end_date="2025-12-31",
            today="2026-07-30",
        )
        # 몇 달이 지나도 여전히 유효하다.
        assert cached_result_is_current(
            computed_date="2026-07-30",
            end_date="2025-12-31",
            today="2026-11-05",
        )

    def test_yesterday_ending_period_is_reusable_forever(self) -> None:
        """PL 기본 프리셋은 종료일이 어제 → 계산 시점에 이미 확정."""
        assert cached_result_is_current(
            computed_date="2026-07-30",
            end_date="2026-07-29",
            today="2026-08-02",
        )

    def test_today_ending_period_is_reusable_only_on_the_same_day(self) -> None:
        """07-30 11:33에 계산한 ~07-30 결과는 07-30에만 재사용한다."""
        assert cached_result_is_current(
            computed_date="2026-07-30",
            end_date="2026-07-30",
            today="2026-07-30",
        )
        # 07-30이 끝났으므로 그 하루를 온전히 담기 위해 재계산해야 한다.
        assert not cached_result_is_current(
            computed_date="2026-07-30",
            end_date="2026-07-30",
            today="2026-07-31",
        )

    def test_result_without_a_computed_date_is_never_reused(self) -> None:
        """검증할 수 없는 예전 결과는 재계산한다(fail-closed)."""
        assert not cached_result_is_current(
            computed_date=None,
            end_date="2026-07-30",
            today="2026-07-30",
        )
        assert not cached_result_is_current(
            computed_date="2026-07-30",
            end_date=None,
            today="2026-07-30",
        )


def _payload(*, computed_date: str | None, end_date: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "success",
        "analysis_schema_version": SEASON_ANALYSIS_SCHEMA_VERSION,
        "data_source": "source_api",
        "analysis_options": {
            "start_date": "2025-07-30",
            "end_date": end_date,
            "metric": "qty",
            "group_by": "month",
            "eu_local": True,
            "include_ingredient": False,
            "exclude_partial_months": False,
            "lead_time_air": None,
            "lead_time_sea": None,
            "lead_time_rail": None,
            "lead_time_truck": None,
            "entity_code": "PL",
            "warehouse": None,
        },
        "source_meta": {"sales_history": {"path": "/eu/sales/local"}},
        "season_analysis": {"monthlySkuCube": [{"row": 1}]},
    }
    if computed_date is not None:
        payload["computed_date"] = computed_date
    return payload


@pytest.fixture
def stale_today_ending_payload(monkeypatch: pytest.MonkeyPatch):
    """07-30에 계산된 ~07-30 결과. 오늘은 07-31."""
    from backend.services import season_cache_service

    monkeypatch.setattr(
        season_cache_service,
        "cached_cross_analysis_complete",
        lambda payload: True,
    )
    import datetime

    class FakeToday:
        @staticmethod
        def isoformat() -> str:
            return "2026-07-31"

    monkeypatch.setattr(season_cache_service, "korea_today", lambda: FakeToday())
    del datetime
    return _payload(computed_date="2026-07-30", end_date="2026-07-30")


def test_stale_today_ending_result_is_not_served_the_next_day(
    stale_today_ending_payload: dict[str, object],
) -> None:
    requested = dict(stale_today_ending_payload["analysis_options"])  # type: ignore[arg-type]

    result = latest_api_analysis_matches(
        requested,
        load_latest=lambda: stale_today_ending_payload,
        save_latest=lambda payload: None,
        sales_endpoint="/eu/sales/local",
    )

    assert result is None, "미완성 하루가 굳은 결과를 다음 날에도 재사용했다"


def _match_with_today(
    payload: dict[str, object],
    today: str,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object] | None:
    from backend.services import season_cache_service

    monkeypatch.setattr(
        season_cache_service,
        "cached_cross_analysis_complete",
        lambda candidate: True,
    )

    class FakeToday:
        @staticmethod
        def isoformat() -> str:
            return today

    monkeypatch.setattr(season_cache_service, "korea_today", lambda: FakeToday())
    return latest_api_analysis_matches(
        dict(payload["analysis_options"]),  # type: ignore[arg-type]
        load_latest=lambda: payload,
        save_latest=lambda candidate: None,
        sales_endpoint="/eu/sales/local",
    )


def test_closed_period_result_is_still_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    """확정된 기간은 계속 즉시 재사용돼야 한다(느려지면 안 됨)."""
    payload = _payload(computed_date="2026-07-30", end_date="2026-07-29")
    assert _match_with_today(payload, "2026-08-05", monkeypatch) is not None


def test_today_ending_result_is_reused_within_the_same_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """같은 날 안에서는 즉시 재사용한다(하루 단위 기준)."""
    payload = _payload(computed_date="2026-07-30", end_date="2026-07-30")
    assert _match_with_today(payload, "2026-07-30", monkeypatch) is not None
