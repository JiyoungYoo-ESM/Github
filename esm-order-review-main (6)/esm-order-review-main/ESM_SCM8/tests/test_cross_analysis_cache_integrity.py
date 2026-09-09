from backend.routers.season import SEASON_ANALYSIS_SCHEMA_VERSION, _cached_cross_analysis_complete
from backend.services.season_cache_service import ingredient_analysis_from_cached_season


def _payload(monthly_amount: float = 100.0, monthly_qty: float = 10.0, monthly_sku: str = "SKU"):
    return {
        "analysis_schema_version": SEASON_ANALYSIS_SCHEMA_VERSION,
        "season_analysis": {
            "crossAnalysisComplete": True,
            "sourceDataQuality": {
                "status": "ok",
                "recommendationBlocked": False,
            },
            "monthCoverage": [
                {
                    "month": "2026-01",
                    "status": "complete",
                    "totalAmount": monthly_amount,
                    "totalQty": monthly_qty,
                }
            ],
            "countrySkuSummary": [
                {"상품코드": "SKU", "판매금액": 100.0, "판매수량": 10.0},
            ],
            "countrySkuMonthly": [
                {"상품코드": monthly_sku, "판매금액": monthly_amount, "판매수량": monthly_qty},
            ],
        },
    }


def test_current_cross_analysis_cache_requires_matching_full_monthly_cube():
    assert _cached_cross_analysis_complete(_payload()) is True
    assert _cached_cross_analysis_complete(_payload(monthly_amount=90.0)) is False
    assert _cached_cross_analysis_complete(_payload(monthly_qty=9.0)) is False
    assert _cached_cross_analysis_complete(_payload(monthly_sku="TRUNCATED-SKU")) is False


def test_cross_analysis_cache_requires_month_coverage_metadata():
    payload = _payload()
    del payload["season_analysis"]["monthCoverage"]
    assert _cached_cross_analysis_complete(payload) is False


def test_cross_analysis_cache_requires_complete_cube_marker():
    payload = _payload()
    del payload["season_analysis"]["crossAnalysisComplete"]
    assert _cached_cross_analysis_complete(payload) is False


def test_cross_analysis_cache_requires_source_quality_status():
    payload = _payload()
    del payload["season_analysis"]["sourceDataQuality"]
    assert _cached_cross_analysis_complete(payload) is False


def test_cross_analysis_cache_rejects_coverage_from_a_different_population():
    payload = _payload()
    payload["season_analysis"]["monthCoverage"][0]["totalAmount"] = 110.0
    assert _cached_cross_analysis_complete(payload) is False


def test_cross_analysis_cache_rejects_duplicate_coverage_months():
    payload = _payload()
    payload["season_analysis"]["monthCoverage"].append(
        dict(payload["season_analysis"]["monthCoverage"][0])
    )
    assert _cached_cross_analysis_complete(payload) is False


def test_cached_monthly_sku_cube_rebuilds_ingredient_dimensions():
    payload = {
        "season_analysis": {
            "countrySkuMonthly": [
                {
                    "year": 2026,
                    "month": 1,
                    "year_month": "2026-01",
                    "국가": "France",
                    "상품코드": "HYAL-1",
                    "상품명": "히알루론산 세럼",
                    "브랜드": "Brand",
                    "판매금액": 100.0,
                    "판매수량": 10.0,
                }
            ]
        }
    }

    ingredient = ingredient_analysis_from_cached_season(payload)

    assert ingredient["summary"][0]["ingredient"] == "히알루론산"
    assert ingredient["brandMonthlyTrend"][0]["브랜드"] == "Brand"
    assert ingredient["skuMonthlyTrend"][0]["상품코드"] == "HYAL-1"
    assert ingredient["countryMonthlyTrend"][0]["국가"] == "France"
