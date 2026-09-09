"""Validation and enrichment policies for cached season-analysis payloads."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from backend.services.ingredient_analysis_pipeline import build_ingredient_analysis
from core.common import korea_today
from core.season_calendar import (
    AMOUNT_COL,
    BRAND_COL,
    COUNTRY_COL,
    DATE_COL,
    PRODUCT_CODE_COL,
    PRODUCT_NAME_COL,
    QTY_COL,
)


SEASON_ANALYSIS_SCHEMA_VERSION = 13
API_ANALYSIS_CACHE_KEYS = (
    "start_date",
    "end_date",
    "metric",
    "group_by",
    "eu_local",
    "include_ingredient",
    "exclude_partial_months",
    "lead_time_air",
    "lead_time_sea",
    "lead_time_rail",
    "lead_time_truck",
    "entity_code",
    "warehouse",
)

LoadLatestResult = Callable[[], dict[str, object] | None]
SaveLatestResult = Callable[[dict[str, object]], object]


def cached_result_is_current(
    *,
    computed_date: str | None,
    end_date: str | None,
    today: str,
) -> bool:
    """저장된 분석 결과를 재사용해도 되는지 판정한다.

    원칙: 그 결과가 만들어진 뒤로 원천 데이터가 더 변할 수 없을 때만 재사용한다.

    - 계산 시점에 분석 기간이 이미 끝나 있었다면(``computed_date > end_date``)
      해당 기간의 판매는 확정이므로 무기한 재사용한다. 예: 2025년 분석을
      2026년에 계산한 결과.
    - 계산한 날이 분석 기간 안에 있었다면 마지막 하루가 미완성 상태로 굳은
      결과다. 같은 날 안에서만 재사용하고, 날짜가 바뀌면 그 하루를 온전히
      담기 위해 한 번 재계산한다. 예: 07-30 11:33에 계산한
      ``~2026-07-30`` 결과는 07-30에만 재사용하고 07-31에는 재계산한다.

    날짜를 알 수 없는 과거 결과는 검증할 수 없으므로 재사용하지 않는다.
    """
    if not computed_date or not end_date:
        return False
    if computed_date > end_date:
        return True
    return computed_date == today


def empty_ingredient_analysis() -> dict[str, list[dict[str, object]]]:
    return {
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
    }


def ingredient_analysis_from_cached_season(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    """Rebuild ingredient tables from the complete cached monthly SKU cube."""
    season = payload.get("season_analysis")
    if not isinstance(season, dict):
        return empty_ingredient_analysis()
    source_rows = season.get("countrySkuMonthly") or season.get("skuMonthly") or []
    if not isinstance(source_rows, list) or not source_rows:
        return empty_ingredient_analysis()

    sales = pd.DataFrame(source_rows).copy()
    if sales.empty or PRODUCT_CODE_COL not in sales.columns:
        return empty_ingredient_analysis()
    if DATE_COL not in sales.columns:
        if "year_month" in sales.columns:
            sales[DATE_COL] = pd.to_datetime(sales["year_month"].astype(str) + "-01", errors="coerce")
        elif {"year", "month"}.issubset(sales.columns):
            sales[DATE_COL] = pd.to_datetime(
                sales["year"].astype(str) + "-" + sales["month"].astype(str).str.zfill(2) + "-01",
                errors="coerce",
            )
    for column in (QTY_COL, AMOUNT_COL):
        sales[column] = pd.to_numeric(sales[column], errors="coerce").fillna(0) if column in sales.columns else 0
    for column in (PRODUCT_NAME_COL, BRAND_COL, COUNTRY_COL):
        if column not in sales.columns:
            sales[column] = ""

    sku_columns = [column for column in (PRODUCT_CODE_COL, BRAND_COL, PRODUCT_NAME_COL) if column in sales.columns]
    sku_df = sales[sku_columns].drop_duplicates(subset=[PRODUCT_CODE_COL]) if sku_columns else pd.DataFrame()
    return build_ingredient_analysis(sales, sku_df)


def cached_cross_analysis_complete(payload: dict[str, object]) -> bool:
    """Reject incomplete or population-misaligned cached cross-analysis cubes."""
    season = payload.get("season_analysis")
    if (
        not isinstance(season, dict)
        or season.get("crossAnalysisComplete") is not True
        or not isinstance(season.get("monthCoverage"), list)
    ):
        return False
    source_quality = season.get("sourceDataQuality")
    if (
        not isinstance(source_quality, dict)
        or source_quality.get("status") not in {"ok", "warning", "blocked"}
        or not isinstance(source_quality.get("recommendationBlocked"), bool)
    ):
        return False
    coverage_rows = season.get("monthCoverage")
    if not coverage_rows:
        return False
    summary_rows = season.get("countrySkuSummary")
    monthly_rows = season.get("countrySkuMonthly")
    if not isinstance(summary_rows, list) or not summary_rows or not isinstance(monthly_rows, list) or not monthly_rows:
        return False

    summary = pd.DataFrame(summary_rows)
    monthly = pd.DataFrame(monthly_rows)
    coverage = pd.DataFrame(coverage_rows)
    if PRODUCT_CODE_COL not in summary.columns or PRODUCT_CODE_COL not in monthly.columns:
        return False
    required_coverage_columns = {"month", "status", "totalAmount", "totalQty"}
    if not required_coverage_columns.issubset(coverage.columns):
        return False
    coverage_months = coverage["month"].fillna("").astype(str).str.strip()
    if coverage_months.eq("").any() or coverage_months.duplicated().any():
        return False
    if not coverage["status"].isin({"complete", "partial", "missing"}).all():
        return False
    summary_skus = set(summary[PRODUCT_CODE_COL].dropna().astype(str))
    monthly_skus = set(monthly[PRODUCT_CODE_COL].dropna().astype(str))
    if summary_skus != monthly_skus:
        return False
    for column in (AMOUNT_COL, QTY_COL):
        if column not in summary.columns or column not in monthly.columns:
            return False
        summary_total = float(pd.to_numeric(summary[column], errors="coerce").fillna(0).sum())
        monthly_total = float(pd.to_numeric(monthly[column], errors="coerce").fillna(0).sum())
        tolerance = max(0.01, abs(summary_total) * 1e-9)
        if abs(summary_total - monthly_total) > tolerance:
            return False
        coverage_column = "totalAmount" if column == AMOUNT_COL else "totalQty"
        coverage_values = pd.to_numeric(coverage[coverage_column], errors="coerce")
        if coverage_values.isna().any():
            return False
        if abs(float(coverage_values.sum()) - monthly_total) > tolerance:
            return False
    return True


def _options_match(cached_options: dict[str, object], expected_options: dict[str, object]) -> bool:
    for key in (key for key in API_ANALYSIS_CACHE_KEYS if key != "include_ingredient"):
        cached_value = cached_options.get(key)
        expected_value = expected_options.get(key)
        if key == "eu_local" and cached_value is None and expected_value is True:
            continue
        if (
            key in {"start_date", "end_date"}
            and cached_options.get("exclude_partial_months") is True
            and expected_options.get("exclude_partial_months") is True
            and str(cached_value or "")[:7] == str(expected_value or "")[:7]
        ):
            continue
        if cached_value != expected_value:
            return False
    return True


def _enrich_cached_ingredient(
    payload: dict[str, object],
    source_meta: dict[str, object],
    save_latest: SaveLatestResult,
) -> dict[str, object]:
    ingredient_analysis = ingredient_analysis_from_cached_season(payload)
    if not ingredient_analysis.get("summary"):
        return payload
    response_payload = {**payload, "ingredient_analysis": ingredient_analysis}
    response_payload["source_meta"] = {**source_meta, "ingredient_source": "cached_season_analysis"}
    save_latest(response_payload)
    return response_payload


def latest_api_analysis_matches(
    analysis_options: dict[str, object],
    *,
    load_latest: LoadLatestResult,
    save_latest: SaveLatestResult,
    sales_endpoint: str,
    schema_version: int = SEASON_ANALYSIS_SCHEMA_VERSION,
) -> dict[str, object] | None:
    payload = load_latest()
    if (
        not payload
        or payload.get("data_source") != "source_api"
        or payload.get("analysis_schema_version") != schema_version
        or not cached_cross_analysis_complete(payload)
    ):
        return None
    cached_options = payload.get("analysis_options")
    if not isinstance(cached_options, dict) or not _options_match(cached_options, analysis_options):
        return None
    # 기간이 오늘을 포함한 채 계산된 결과는 마지막 하루가 미완성이므로
    # 날짜가 바뀌면 재사용하지 않는다.
    # ``saved_at``은 브랜드 리포트 보강 등으로 다시 저장될 때 갱신되므로
    # 계산 시각의 근거로 쓸 수 없다. 전용 필드만 신뢰한다.
    if not cached_result_is_current(
        computed_date=str(payload.get("computed_date") or "") or None,
        end_date=str(cached_options.get("end_date") or "") or None,
        today=korea_today().isoformat(),
    ):
        return None
    source_meta = payload.get("source_meta")
    if not isinstance(source_meta, dict):
        return None
    sales_meta = source_meta.get("sales_history")
    if not isinstance(sales_meta, dict) or sales_meta.get("path") != sales_endpoint:
        return None

    response_payload = dict(payload)
    response_payload["analysis_options"] = {
        **cached_options,
        **analysis_options,
        "eu_local": analysis_options.get("eu_local", True),
    }
    include_ingredient = bool(analysis_options.get("include_ingredient"))
    cached_ingredient = response_payload.get("ingredient_analysis")
    missing_monthly_fields = (
        not isinstance(cached_ingredient, dict)
        or not cached_ingredient.get("brandMonthlyTrend")
        or not cached_ingredient.get("skuMonthlyTrend")
    )
    if include_ingredient and (not cached_options.get("include_ingredient") or missing_monthly_fields):
        response_payload = _enrich_cached_ingredient(response_payload, source_meta, save_latest)
        enriched_options = response_payload.get("analysis_options")
        if isinstance(enriched_options, dict) and response_payload.get("ingredient_analysis"):
            response_payload["analysis_options"] = {**enriched_options, "include_ingredient": True}
    elif not include_ingredient and cached_options.get("include_ingredient") != include_ingredient:
        # A request that does not need the disabled ingredient tab can safely
        # reuse a richer cached analysis. Strip the optional high-cardinality
        # ingredient payload from the response instead of rebuilding the
        # 800k-row HQ season cube.
        response_payload["ingredient_analysis"] = empty_ingredient_analysis()
        response_payload["analysis_options"] = {
            **response_payload["analysis_options"],
            "include_ingredient": False,
        }

    return {
        **response_payload,
        "cache": {
            "hit": True,
            "source": "latest_season_trend",
            "saved_at": response_payload.get("saved_at"),
        },
    }


def with_cached_ingredient_monthly_fields(
    payload: dict[str, object],
    *,
    save_latest: SaveLatestResult,
) -> dict[str, object]:
    cached_ingredient = payload.get("ingredient_analysis")
    if not isinstance(cached_ingredient, dict):
        return payload
    if cached_ingredient.get("brandMonthlyTrend") and cached_ingredient.get("skuMonthlyTrend"):
        return payload
    source_meta = payload.get("source_meta")
    if not isinstance(source_meta, dict):
        source_meta = {}
    return _enrich_cached_ingredient(payload, source_meta, save_latest)


__all__ = [
    "API_ANALYSIS_CACHE_KEYS",
    "SEASON_ANALYSIS_SCHEMA_VERSION",
    "cached_cross_analysis_complete",
    "empty_ingredient_analysis",
    "ingredient_analysis_from_cached_season",
    "latest_api_analysis_matches",
    "with_cached_ingredient_monthly_fields",
]
