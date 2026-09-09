"""Request-independent validation policy for season analysis options."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime

from fastapi import HTTPException

from backend.services.request_validation import validate_date_string


SEASON_DATA_MIN_DATE = "2024-04-01"
SEASON_SOURCE_API_MIN_DATE = SEASON_DATA_MIN_DATE
MAX_DIRECT_RANGE_MONTHS = 24
MAX_LONG_HISTORY_RANGE_MONTHS = 24


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def validate_season_analysis_options(
    *,
    start_date: str | None,
    end_date: str | None,
    metric: str,
    group_by: str,
    api_source: bool = False,
    entity_code: str = "PL",
) -> tuple[str | None, str | None]:
    analysis_start_date = validate_date_string(start_date, "start_date")
    analysis_end_date = validate_date_string(end_date, "end_date")
    if analysis_start_date and analysis_end_date and analysis_start_date > analysis_end_date:
        raise HTTPException(status_code=400, detail="분석 시작일은 종료일보다 늦을 수 없습니다.")
    normalized_entity_code = str(entity_code or "PL").strip().upper()
    has_long_history_api = api_source and normalized_entity_code in {"HQ", "USA"}
    min_date = SEASON_SOURCE_API_MIN_DATE if api_source else SEASON_DATA_MIN_DATE
    if not has_long_history_api and analysis_start_date and analysis_start_date < min_date:
        raise HTTPException(status_code=400, detail=f"분석 시작일은 {min_date} 이후로 선택해 주세요.")
    if analysis_start_date and analysis_end_date:
        parsed_start = datetime.strptime(analysis_start_date, "%Y-%m-%d").date()
        parsed_end = datetime.strptime(analysis_end_date, "%Y-%m-%d").date()
        max_range_months = (
            MAX_LONG_HISTORY_RANGE_MONTHS
            if has_long_history_api
            else MAX_DIRECT_RANGE_MONTHS
        )
        if parsed_end > add_months(parsed_start, max_range_months):
            if has_long_history_api:
                raise HTTPException(
                    status_code=400,
                    detail="본사·미주 판매이력은 한 번에 최대 24개월까지 조회할 수 있습니다.",
                )
            raise HTTPException(
                status_code=400,
                detail="직접 선택 분석 기간은 최대 24개월까지 가능합니다.",
            )
    if metric not in {"qty", "amount"}:
        raise HTTPException(status_code=400, detail="metric은 qty 또는 amount만 사용할 수 있습니다.")
    if group_by not in {"month", "quarter", "year"}:
        raise HTTPException(status_code=400, detail="group_by는 month, quarter, year만 사용할 수 있습니다.")
    return analysis_start_date, analysis_end_date


__all__ = [
    "MAX_DIRECT_RANGE_MONTHS",
    "MAX_LONG_HISTORY_RANGE_MONTHS",
    "SEASON_DATA_MIN_DATE",
    "SEASON_SOURCE_API_MIN_DATE",
    "add_months",
    "validate_season_analysis_options",
]
