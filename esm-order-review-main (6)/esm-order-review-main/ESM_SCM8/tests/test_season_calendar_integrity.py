import pandas as pd

from core.season_calendar import (
    AMOUNT_COL,
    CATEGORY1_COL,
    CATEGORY2_COL,
    DATE_COL,
    QTY_COL,
    build_ytd_comparison,
)
from backend.services.season_trend_jobs import (
    create_season_trend_job,
    is_latest_season_trend_job,
    supersede_running_season_trend_jobs,
)


def _row(date: str, qty: float, amount: float, category1: str = "스킨케어", category2: str = "크림"):
    return {
        DATE_COL: pd.Timestamp(date),
        CATEGORY1_COL: category1,
        CATEGORY2_COL: category2,
        QTY_COL: qty,
        AMOUNT_COL: amount,
    }


def test_ytd_uses_only_equal_complete_month_populations():
    frame = pd.DataFrame(
        [
            _row("2024-07-15", 700, 7_000),
            _row("2025-01-15", 10, 100),
            _row("2025-02-15", 20, 200),
            _row("2025-12-15", 9_999, 99_990),
            _row("2026-01-15", 15, 150),
            _row("2026-02-15", 30, 300),
            _row("2026-03-15", 99_999, 999_990),
        ]
    )
    complete = {"2024-07", "2025-01", "2025-02", "2025-12", "2026-01", "2026-02"}

    result = build_ytd_comparison(frame, complete)

    assert len(result) == 1
    row = result.iloc[0]
    assert "YTD_수량_2024" not in result.columns
    assert row["YTD_수량_2025"] == 30
    assert row["YTD_수량_2026"] == 45
    assert row["YTD_금액_2025"] == 300
    assert row["YTD_금액_2026"] == 450
    assert row["수량YTD성장률_2025_to_2026(%)"] == 50
    assert row["금액YTD성장률_2025_to_2026(%)"] == 50


def test_ytd_returns_empty_when_no_year_has_january_through_anchor():
    frame = pd.DataFrame([_row("2025-07-15", 10, 100), _row("2026-07-15", 20, 200)])
    result = build_ytd_comparison(frame, {"2025-07", "2026-07"})
    assert result.empty
    assert list(result.columns) == [CATEGORY1_COL, CATEGORY2_COL]


def test_only_most_recent_async_job_can_publish_latest_result():
    first = create_season_trend_job({"start_date": "2025-01-01"})
    second = create_season_trend_job({"start_date": "2026-01-01"})
    assert not is_latest_season_trend_job(first)
    assert is_latest_season_trend_job(second)

    supersede_running_season_trend_jobs()
    assert not is_latest_season_trend_job(first)
    assert not is_latest_season_trend_job(second)
