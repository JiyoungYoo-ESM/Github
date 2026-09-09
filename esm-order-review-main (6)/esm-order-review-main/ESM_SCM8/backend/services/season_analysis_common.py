"""Shared policies and small helpers for season analysis pipelines."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


MONTH_COVERAGE_BOUNDARY_TOLERANCE_DAYS = 6
MONTH_COVERAGE_MIN_BUSINESS_DAY_RATIO = 0.35


@dataclass(frozen=True)
class SeasonAnalysisOptions:
    """Validated date and feature options used by every season pipeline."""

    eu_local: bool
    start_date_value: str
    end_date_value: str
    start_date: pd.Timestamp | None
    end_date: pd.Timestamp | None
    effective_start_date: pd.Timestamp | None
    effective_end_date: pd.Timestamp | None
    include_ingredient: bool
    entity_code: str


def parse_season_analysis_options(options: dict[str, object] | None) -> SeasonAnalysisOptions:
    values = options or {}
    start_date_value = str(values.get("start_date") or "").strip()
    end_date_value = str(values.get("end_date") or "").strip()
    start_date = pd.to_datetime(start_date_value, errors="raise") if start_date_value else None
    end_date = (
        pd.to_datetime(end_date_value, errors="raise") + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        if end_date_value
        else None
    )
    effective_start_date = start_date
    effective_end_date = end_date
    if bool(values.get("exclude_partial_months", True)):
        if start_date is not None and start_date.day != 1:
            effective_start_date = start_date + pd.offsets.MonthBegin(1)
        if end_date is not None and end_date.normalize() != end_date.normalize() + pd.offsets.MonthEnd(0):
            effective_end_date = pd.Timestamp(year=end_date.year, month=end_date.month, day=1) - pd.Timedelta(
                microseconds=1
            )

    return SeasonAnalysisOptions(
        eu_local=bool(values.get("eu_local", False)),
        start_date_value=start_date_value,
        end_date_value=end_date_value,
        start_date=start_date,
        end_date=end_date,
        effective_start_date=effective_start_date,
        effective_end_date=effective_end_date,
        include_ingredient=bool(values.get("include_ingredient")),
        entity_code=str(values.get("entity_code") or "").strip().upper(),
    )


def empty_season_ingredient_analysis() -> dict[str, dict[str, object]]:
    """Create a fresh response skeleton so callers never share mutable lists."""
    return {
        "season_analysis": {
            "sourceDataQuality": {
                "status": "blocked",
                "sourceRows": 0,
                "recommendationBlocked": True,
                "notes": ["분석 가능한 판매 원천 데이터가 없습니다."],
            },
            "category1Monthly": [],
            "category2Monthly": [],
            "category1Share": [],
            "category2Share": [],
            "ytdComparison": [],
            "topSku": [],
            "skuMonthly": [],
            "mappingQuality": [],
            "uncategorizedSku": [],
            "countryCategoryMonthly": [],
            "countryCategory2Monthly": [],
            "countryTopSku": [],
            "countrySkuSummary": [],
            "countrySkuMonthly": [],
            "dataMonths": [],
            "monthCoverage": [],
            "countryCustomerSummary": [],
            "countryCategoryCustomerSummary": [],
            "customerSalesSummary": [],
        },
        "ingredient_analysis": {
            "keywordMap": [],
            "skuTags": [],
            "monthlyTrend": [],
            "summary": [],
            "growth3m": [],
            "ytdComparison": [],
            "topSku": [],
            "topBrand": [],
            "brandMonthlyTrend": [],
            "skuMonthlyTrend": [],
            "unmatchedSku": [],
            "coverage": [],
            "countryCoverage": [],
            "countryMonthlyTrend": [],
            "countrySummary": [],
            "countryGrowth3m": [],
            "countryYtdComparison": [],
            "countryTopSku": [],
            "countryTopBrand": [],
        },
    }


def exclude_non_revenue_unknown_country_rows(
    frame: pd.DataFrame,
    country_col: str,
    amount_col: str,
) -> tuple[pd.DataFrame, int]:
    """Remove non-revenue rows that cannot be assigned to a country."""
    if frame.empty or country_col not in frame.columns or amount_col not in frame.columns:
        return frame, 0
    raw_country = frame[country_col]
    country = raw_country.fillna("").astype(str).str.normalize("NFKC").str.strip().str.casefold()
    missing_country = raw_country.isna() | country.isin({"", "-", "미상", "unknown", "nan", "none", "n/a", "<na>"})
    amount = pd.to_numeric(frame[amount_col], errors="coerce").fillna(0)
    excluded = missing_country & amount.le(0)
    if not excluded.any():
        return frame, 0
    return frame.loc[~excluded].copy(), int(excluded.sum())


def build_month_coverage(
    frame: pd.DataFrame,
    date_col: str,
    start_date: pd.Timestamp | None = None,
    end_date: pd.Timestamp | None = None,
    amount_col: str | None = None,
    qty_col: str | None = None,
) -> list[dict[str, object]]:
    """Return conservative month-level source coverage for growth calculations."""
    if frame.empty or date_col not in frame.columns:
        return []
    normalized_dates = pd.to_datetime(frame[date_col], errors="coerce").dt.normalize()
    valid_dates = normalized_dates[normalized_dates.notna()]
    if valid_dates.empty:
        return []

    range_start = pd.Timestamp(start_date).normalize() if start_date is not None else valid_dates.min()
    range_end = pd.Timestamp(end_date).normalize() if end_date is not None else valid_dates.max()
    if range_start > range_end:
        return []

    periods = pd.period_range(range_start.to_period("M"), range_end.to_period("M"), freq="M")
    coverage: list[dict[str, object]] = []
    for period in periods:
        month_start = period.start_time.normalize()
        month_end = period.end_time.normalize()
        selected_start = max(month_start, range_start)
        selected_end = min(month_end, range_end)
        in_month = normalized_dates.dt.to_period("M").eq(period)
        month_dates = normalized_dates[in_month & normalized_dates.notna()]
        expected_business_days = len(pd.bdate_range(selected_start, selected_end))

        if month_dates.empty:
            coverage.append(
                {
                    "month": str(period),
                    "status": "missing",
                    "reason": "월 데이터 없음",
                    "rowCount": 0,
                    "activeDays": 0,
                    "expectedBusinessDays": expected_business_days,
                    "activityRatio": 0.0,
                    "firstDate": None,
                    "lastDate": None,
                    "totalAmount": 0.0,
                    "totalQty": 0.0,
                }
            )
            continue

        unique_days = pd.DatetimeIndex(month_dates.unique()).sort_values()
        first_date = pd.Timestamp(unique_days[0])
        last_date = pd.Timestamp(unique_days[-1])
        active_business_days = sum(timestamp.weekday() < 5 for timestamp in unique_days)
        activity_ratio = active_business_days / expected_business_days if expected_business_days > 0 else 0.0
        reasons: list[str] = []
        if selected_start > month_start or selected_end < month_end:
            reasons.append("분석 기간이 월 전체를 포함하지 않음")
        if first_date > month_start + pd.Timedelta(days=MONTH_COVERAGE_BOUNDARY_TOLERANCE_DAYS):
            reasons.append("월초 데이터 범위 부족")
        if last_date < month_end - pd.Timedelta(days=MONTH_COVERAGE_BOUNDARY_TOLERANCE_DAYS):
            reasons.append("월말 데이터 범위 부족")
        if activity_ratio < MONTH_COVERAGE_MIN_BUSINESS_DAY_RATIO:
            reasons.append("활동일 비율 부족")

        month_rows = frame.loc[in_month]
        total_amount = (
            float(pd.to_numeric(month_rows[amount_col], errors="coerce").fillna(0).sum())
            if amount_col and amount_col in month_rows.columns
            else 0.0
        )
        total_qty = (
            float(pd.to_numeric(month_rows[qty_col], errors="coerce").fillna(0).sum())
            if qty_col and qty_col in month_rows.columns
            else 0.0
        )
        coverage.append(
            {
                "month": str(period),
                "status": "partial" if reasons else "complete",
                "reason": " · ".join(reasons),
                "rowCount": int(in_month.sum()),
                "activeDays": int(active_business_days),
                "expectedBusinessDays": expected_business_days,
                "activityRatio": round(activity_ratio, 4),
                "firstDate": first_date.strftime("%Y-%m-%d"),
                "lastDate": last_date.strftime("%Y-%m-%d"),
                "totalAmount": total_amount,
                "totalQty": total_qty,
            }
        )
    return coverage


def top_rows_per_group(
    df: pd.DataFrame,
    group_columns: list[str],
    sort_columns: list[str],
    limit: int,
) -> pd.DataFrame:
    frame = pd.DataFrame(df)
    if frame.empty or limit <= 0:
        return frame
    missing = [column for column in [*group_columns, *sort_columns] if column not in frame.columns]
    if missing:
        return frame.head(limit)
    sorted_frame = frame.sort_values(sort_columns, ascending=[False] * len(sort_columns))
    return sorted_frame.groupby(group_columns, dropna=False, group_keys=False).head(limit).reset_index(drop=True)


def filter_rows_by_values(df: pd.DataFrame, column: str, values: set[str]) -> pd.DataFrame:
    frame = pd.DataFrame(df)
    if frame.empty or column not in frame.columns or not values:
        return frame
    return frame[frame[column].astype(str).isin(values)].copy()


__all__ = [
    "SeasonAnalysisOptions",
    "build_month_coverage",
    "empty_season_ingredient_analysis",
    "exclude_non_revenue_unknown_country_rows",
    "filter_rows_by_values",
    "parse_season_analysis_options",
    "top_rows_per_group",
]
