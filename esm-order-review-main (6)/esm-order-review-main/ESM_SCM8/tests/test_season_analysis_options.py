from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from backend.routers.season import (
    SeasonTrendApiAnalyzeRequest,
    _api_analysis_options_for_request,
)
from backend.services.season_analysis_options import validate_season_analysis_options


def _validate(*, entity_code: str, start_date: str, end_date: str):
    return validate_season_analysis_options(
        start_date=start_date,
        end_date=end_date,
        metric="qty",
        group_by="month",
        api_source=True,
        entity_code=entity_code,
    )


def test_hq_api_history_allows_dates_before_eu_minimum_within_two_years():
    assert _validate(
        entity_code="HQ",
        start_date="2010-01-01",
        end_date="2012-01-01",
    ) == ("2010-01-01", "2012-01-01")


def test_us_api_history_allows_dates_before_eu_minimum_within_two_years():
    assert _validate(
        entity_code="USA",
        start_date="2015-11-07",
        end_date="2017-11-07",
    ) == ("2015-11-07", "2017-11-07")


@pytest.mark.parametrize("entity_code", ["HQ", "USA"])
def test_long_history_api_rejects_ranges_over_two_years(entity_code: str):
    with pytest.raises(HTTPException) as caught:
        _validate(
            entity_code=entity_code,
            start_date="2024-07-27",
            end_date="2026-07-28",
        )

    assert caught.value.status_code == 400
    assert "최대 24개월" in caught.value.detail


def test_hq_api_request_uses_hq_long_history_validation_policy():
    request = SimpleNamespace(state=SimpleNamespace(entity_code="HQ"))
    body = SeasonTrendApiAnalyzeRequest(
        start_date="2010-01-01",
        end_date="2011-01-01",
    )

    options = _api_analysis_options_for_request(request, body)

    assert options["start_date"] == "2010-01-01"
    assert options["end_date"] == "2011-01-01"


def test_hq_api_request_normalizes_selected_warehouse():
    request = SimpleNamespace(state=SimpleNamespace(entity_code="HQ"))
    body = SeasonTrendApiAnalyzeRequest(
        start_date="2026-01-01",
        end_date="2026-07-28",
        warehouse=" opo ",
    )

    options = _api_analysis_options_for_request(request, body)

    assert options["warehouse"] == "OPO"


def test_non_hq_api_request_rejects_warehouse_filter():
    request = SimpleNamespace(state=SimpleNamespace(entity_code="USA"))
    body = SeasonTrendApiAnalyzeRequest(
        start_date="2026-01-01",
        end_date="2026-07-28",
        warehouse="OPO",
    )

    with pytest.raises(HTTPException) as caught:
        _api_analysis_options_for_request(request, body)

    assert caught.value.status_code == 400
    assert "본사" in caught.value.detail


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        ("2024-03-31", "2024-12-31"),
        ("2024-04-01", "2026-04-02"),
    ],
)
def test_pl_api_history_keeps_existing_eu_date_limits(start_date: str, end_date: str):
    with pytest.raises(HTTPException) as caught:
        _validate(entity_code="PL", start_date=start_date, end_date=end_date)

    assert caught.value.status_code == 400
