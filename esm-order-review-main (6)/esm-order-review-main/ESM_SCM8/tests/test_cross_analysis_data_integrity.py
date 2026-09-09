import pandas as pd

from backend.analysis import build_season_ingredient_analysis
from backend.routers import season as season_router
from core.season_calendar import (
    AMOUNT_COL,
    BRAND_COL,
    COUNTRY_COL,
    PRODUCT_CODE_COL,
    QTY_COL,
    merge_sales_with_product_master,
)


def _product_master(sku_codes: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "prod_cd": sku,
                "prod_nm": f"Item {sku}",
                "brand_nm": "Brand",
                "class1_nm": "스킨케어",
                "class2_nm": "토너",
            }
            for sku in sku_codes
        ]
    )


def test_mixed_transaction_currencies_use_normalized_eur_amount_when_available():
    sales = pd.DataFrame(
        [
            {"ship_dt": "2026-01-01", "prod_cd": "EUR-SKU", "qty": 1, "amount": 100, "amount_krw": 100, "curr": "EUR"},
            {"ship_dt": "2026-01-01", "prod_cd": "GBP-SKU", "qty": 1, "amount": 100, "amount_krw": 115, "curr": "GBP"},
        ]
    )

    merged = merge_sales_with_product_master(sales, _product_master(["EUR-SKU", "GBP-SKU"]))

    assert merged[AMOUNT_COL].sum() == 215


def test_true_krw_scale_conversion_field_is_not_mistaken_for_eur():
    sales = pd.DataFrame(
        [
            {"ship_dt": "2026-01-01", "prod_cd": "SKU", "qty": 1, "amount": 100, "amount_krw": 170_000, "curr": "EUR"},
        ]
    )

    merged = merge_sales_with_product_master(sales, _product_master(["SKU"]))

    assert merged[AMOUNT_COL].sum() == 100


def test_country_sku_monthly_keeps_skus_outside_top_sku_response_limit():
    sku_codes = [f"SKU-{index:03d}" for index in range(81)]
    sales = pd.DataFrame(
        [
            {
                "ship_dt": "2026-01-15",
                "prod_cd": sku,
                "prod_nm": f"Item {sku}",
                "brand_nm": "Brand",
                "country": "France",
                "qty": 81 - index,
                "amount": (81 - index) * 10,
            }
            for index, sku in enumerate(sku_codes)
        ]
    )

    result = build_season_ingredient_analysis(
        {"sales_history": sales, "prod_list": _product_master(sku_codes)},
        {"start_date": "2026-01-01", "end_date": "2026-01-31", "exclude_partial_months": False},
    )["season_analysis"]

    assert result["crossAnalysisComplete"] is True
    top_sku_codes = {str(row[PRODUCT_CODE_COL]) for row in result["topSku"]}
    compact_monthly_codes = {str(row[PRODUCT_CODE_COL]) for row in result["skuMonthly"]}
    country_monthly_codes = {str(row[PRODUCT_CODE_COL]) for row in result["countrySkuMonthly"]}

    assert len(top_sku_codes) == 80
    assert len(compact_monthly_codes) == 80
    assert country_monthly_codes == set(sku_codes)
    assert {str(row[COUNTRY_COL]) for row in result["countrySkuMonthly"]} == {"France"}
    assert sum(float(row[AMOUNT_COL]) for row in result["countrySkuMonthly"]) == sales["amount"].sum()
    assert result["dataMonths"] == ["2026-01"]


def test_data_months_exposes_a_missing_calendar_month_without_filling_it_as_zero():
    sales = pd.DataFrame(
        [
            {"ship_dt": "2026-04-15", "prod_cd": "SKU", "country": "France", "qty": 1, "amount": 100},
            {"ship_dt": "2026-06-15", "prod_cd": "SKU", "country": "France", "qty": 1, "amount": 120},
        ]
    )

    result = build_season_ingredient_analysis(
        {"sales_history": sales, "prod_list": _product_master(["SKU"])},
        {"start_date": "2026-04-01", "end_date": "2026-06-30", "exclude_partial_months": False},
    )["season_analysis"]

    assert result["dataMonths"] == ["2026-04", "2026-06"]
    coverage = {row["month"]: row for row in result["monthCoverage"]}
    assert coverage["2026-04"]["status"] == "partial"
    assert coverage["2026-05"]["status"] == "missing"
    assert coverage["2026-06"]["status"] == "partial"


def test_month_coverage_separates_complete_partial_and_missing_months():
    complete_may = [
        {
            "ship_dt": day.strftime("%Y-%m-%d"),
            "prod_cd": "SKU",
            "country": "France",
            "qty": 1,
            "amount": 10,
        }
        for day in pd.date_range("2026-05-01", "2026-05-31", freq="B")
    ]
    partial_june = [
        {
            "ship_dt": day.strftime("%Y-%m-%d"),
            "prod_cd": "SKU",
            "country": "France",
            "qty": 1,
            "amount": 10,
        }
        for day in pd.date_range("2026-06-01", "2026-06-08", freq="B")
    ]
    sales = pd.DataFrame(complete_may + partial_june)

    result = build_season_ingredient_analysis(
        {"sales_history": sales, "prod_list": _product_master(["SKU"])},
        {"start_date": "2026-05-01", "end_date": "2026-07-31", "exclude_partial_months": False},
    )["season_analysis"]

    coverage = {row["month"]: row for row in result["monthCoverage"]}
    assert coverage["2026-05"]["status"] == "complete"
    assert coverage["2026-05"]["activeDays"] == coverage["2026-05"]["expectedBusinessDays"]
    assert coverage["2026-06"]["status"] == "partial"
    assert "월말 데이터 범위 부족" in coverage["2026-06"]["reason"]
    assert coverage["2026-07"]["status"] == "missing"


def test_month_coverage_reconciles_to_the_filtered_cross_analysis_population():
    sales = pd.DataFrame(
        [
            {"ship_dt": "2026-05-01", "prod_cd": "SKU", "country": "France", "qty": 10, "amount": 100},
            {"ship_dt": "2026-05-04", "prod_cd": "SKU", "country": None, "qty": -2, "amount": -25},
        ]
    )

    result = build_season_ingredient_analysis(
        {"sales_history": sales, "prod_list": _product_master(["SKU"])},
        {"start_date": "2026-05-01", "end_date": "2026-05-31", "exclude_partial_months": False},
    )["season_analysis"]

    coverage = result["monthCoverage"][0]
    monthly_amount = sum(float(row[AMOUNT_COL]) for row in result["countrySkuMonthly"])
    monthly_qty = sum(float(row[QTY_COL]) for row in result["countrySkuMonthly"])

    assert coverage["totalAmount"] == monthly_amount == 100
    assert coverage["totalQty"] == monthly_qty == 10
    assert coverage["rowCount"] == 1


def test_ingredient_monthly_cross_sources_preserve_dimensions_beyond_top_ten():
    sku_codes = [f"HYAL-{index:02d}" for index in range(12)]
    sales = pd.DataFrame(
        [
            {
                "ship_dt": "2026-01-15",
                "prod_cd": sku,
                "prod_nm": f"히알루론산 세럼 {index}",
                "brand_nm": f"Brand-{index:02d}",
                "country": "France",
                "qty": index + 1,
                "amount": (index + 1) * 100,
            }
            for index, sku in enumerate(sku_codes)
        ]
    )
    product_master = pd.DataFrame(
        [
            {
                "prod_cd": sku,
                "prod_nm": f"히알루론산 세럼 {index}",
                "brand_nm": f"Brand-{index:02d}",
                "class1_nm": "스킨케어",
                "class2_nm": "세럼",
            }
            for index, sku in enumerate(sku_codes)
        ]
    )

    ingredient = build_season_ingredient_analysis(
        {"sales_history": sales, "prod_list": product_master},
        {
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "exclude_partial_months": False,
            "include_ingredient": True,
        },
    )["ingredient_analysis"]

    def rows_for(table: str) -> list[dict[str, object]]:
        return [row for row in ingredient[table] if row.get("ingredient") == "히알루론산"]

    brand_monthly = rows_for("brandMonthlyTrend")
    sku_monthly = rows_for("skuMonthlyTrend")
    country_summary = rows_for("countrySummary")
    country_monthly = rows_for("countryMonthlyTrend")

    assert len({str(row[BRAND_COL]) for row in brand_monthly}) == 12
    assert len({str(row[PRODUCT_CODE_COL]) for row in sku_monthly}) == 12
    assert sum(float(row[AMOUNT_COL]) for row in brand_monthly) == sales["amount"].sum()
    assert sum(float(row[QTY_COL]) for row in sku_monthly) == sales["qty"].sum()
    assert sum(float(row[AMOUNT_COL]) for row in country_summary) == sales["amount"].sum()
    assert sum(float(row[AMOUNT_COL]) for row in country_monthly) == sales["amount"].sum()

    # Ranking tables remain intentionally compact and therefore must never be
    # selected as the complete cross-analysis cube when monthly tables exist.
    assert len(rows_for("topBrand")) == 10
    assert len(rows_for("topSku")) == 10


def test_hq_history_joins_product_master_and_builds_krw_insight_tables():
    sales = pd.DataFrame(
        [
            {
                "ship_dt": "2026-06-01",
                "prod_cd": "HQ-SKU",
                "prod_nm": "HQ Item",
                "brand_nm": "HQ Brand",
                "country": "Korea",
                "cust_nm": "Customer",
                "cust_snm": "C",
                "qty": 2,
                "amount_krw": "120000",
                "biz_type": "KR-DOMESTIC",
                "invc_no": "INV-1",
            }
        ]
    )
    products = pd.DataFrame(
        [
            {
                "prod_cd": "HQ-SKU",
                "prod_nm": "HQ Item",
                "brand_nm": "HQ Brand",
                "class1_nm": "스킨케어",
                "class2_nm": "토너",
            }
        ]
    )

    season = build_season_ingredient_analysis(
        {"sales_history": sales, "prod_list": products},
        {
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
            "exclude_partial_months": False,
            "entity_code": "HQ",
            "eu_local": False,
        },
    )["season_analysis"]

    assert season["topSku"][0][PRODUCT_CODE_COL] == "HQ-SKU"
    assert season["topSku"][0][AMOUNT_COL] == 120000
    assert season["countrySkuSummary"][0][COUNTRY_COL] == "Korea"
    assert season["category1Monthly"][0][AMOUNT_COL] == 120000


def test_cross_analysis_cache_rejects_pre_full_cube_schema(monkeypatch):
    options = {
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "metric": "qty",
        "group_by": "month",
        "eu_local": True,
        "include_ingredient": False,
        "exclude_partial_months": True,
        "lead_time_air": 15,
        "lead_time_sea": 70,
        "lead_time_rail": 30,
        "lead_time_truck": 30,
    }
    payload = {
        "data_source": "source_api",
        "analysis_schema_version": season_router.SEASON_ANALYSIS_SCHEMA_VERSION,
        # 기간(~2025-12-31)이 끝난 뒤에 계산된 결과이므로 신선도 규칙상 무기한
        # 재사용 대상이다. 이 테스트는 스키마 검증만 확인한다.
        "computed_date": "2026-01-05",
        "analysis_options": options,
        "source_meta": {"sales_history": {"path": season_router.EU_SALES_ENDPOINT}},
        "season_analysis": {
            "crossAnalysisComplete": True,
            "sourceDataQuality": {
                "status": "ok",
                "recommendationBlocked": False,
            },
            "monthCoverage": [
                {
                    "month": "2025-01",
                    "status": "complete",
                    "totalAmount": 100,
                    "totalQty": 10,
                }
            ],
            "countrySkuSummary": [{PRODUCT_CODE_COL: "SKU", AMOUNT_COL: 100, QTY_COL: 10}],
            "countrySkuMonthly": [{PRODUCT_CODE_COL: "SKU", AMOUNT_COL: 100, QTY_COL: 10}],
        },
    }

    monkeypatch.setattr(season_router, "load_latest_season_trend_result", lambda: payload)
    assert season_router._latest_api_analysis_matches(options) is not None

    richer_payload = {
        **payload,
        "analysis_options": {**options, "include_ingredient": True},
        "ingredient_analysis": {"summary": [{"ingredient": "PDRN"}]},
    }
    monkeypatch.setattr(season_router, "load_latest_season_trend_result", lambda: richer_payload)
    reused_without_ingredient = season_router._latest_api_analysis_matches(options)
    assert reused_without_ingredient is not None
    assert reused_without_ingredient["analysis_options"]["include_ingredient"] is False
    assert reused_without_ingredient["ingredient_analysis"]["summary"] == []

    stale_payload = {
        **payload,
        "analysis_schema_version": season_router.SEASON_ANALYSIS_SCHEMA_VERSION - 1,
    }
    monkeypatch.setattr(season_router, "load_latest_season_trend_result", lambda: stale_payload)
    assert season_router._latest_api_analysis_matches(options) is None
