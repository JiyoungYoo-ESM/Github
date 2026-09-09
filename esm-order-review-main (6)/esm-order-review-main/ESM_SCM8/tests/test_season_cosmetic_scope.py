import pandas as pd
import pytest
from fastapi import HTTPException

from backend.services import season_api_analysis_service
from backend.services import season_ingredient_analysis
from backend.services.season_ingredient_analysis import (
    CosmeticScopeValidationError,
    build_season_ingredient_analysis,
)
from core.season_calendar import CATEGORY1_COL, PRODUCT_CODE_COL


def _sales(*sku_codes: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ship_dt": "2026-06-15",
                "prod_cd": sku,
                "prod_nm": f"Item {sku}",
                "brand_nm": "Brand",
                "country": "France",
                "qty": index + 1,
                "amount": (index + 1) * 100,
                "amount_krw_actual": (index + 1) * 160_000,
                "xrate_source": "DAILY_RATE",
            }
            for index, sku in enumerate(sku_codes)
        ]
    )


def _product(
    sku: str,
    class1: str,
    class1_name: str,
    class2_name: str = "토너",
) -> dict[str, object]:
    return {
        "prod_cd": sku,
        "prod_nm": f"Item {sku}",
        "brand_nm": "Brand",
        "class1": class1,
        "class1_nm": class1_name,
        "class2_nm": class2_name,
    }


def _options() -> dict[str, object]:
    return {
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        "exclude_partial_months": False,
        "strict_cosmetic_scope": True,
    }


def test_season_calendar_aggregates_only_master_designated_cosmetic_skus():
    sku_codes = ("COS", "COSMETIC-TOOL", "DEVICE", "SCARF", "STICKER", "DRINK", "WALLET")
    products = pd.DataFrame(
        [
            _product("COS", "01", "스킨케어"),
            _product("COSMETIC-TOOL", "15", "화장소품", "브러쉬"),
            _product("DEVICE", "60", "디바이스", "미용기기"),
            _product("SCARF", "18", "스카프", "패션잡화"),
            _product("STICKER", "47", "스티커", "문구"),
            _product("DRINK", "14", "음료", "음료"),
            _product("WALLET", "34", "지갑, 가방", "가방"),
        ]
    )

    season = build_season_ingredient_analysis(
        {"sales_history": _sales(*sku_codes), "prod_list": products},
        _options(),
    )["season_analysis"]

    assert {row[CATEGORY1_COL] for row in season["category1Monthly"]} == {
        "스킨케어",
        "화장소품",
        "디바이스",
    }
    assert {row[PRODUCT_CODE_COL] for row in season["countrySkuSummary"]} == {
        "COS",
        "COSMETIC-TOOL",
        "DEVICE",
    }
    assert sum(row["판매수량"] for row in season["category1Monthly"]) == 1 + 2 + 3
    assert season["uncategorizedSku"] == []


def test_unmatched_and_invalid_master_categories_go_to_diagnostics_without_correction_bypass():
    sales = _sales("COS", "UNMATCHED", "MISSING-C1", "UNKNOWN-C1")
    products = pd.DataFrame(
        [
            _product("COS", "01", "스킨케어"),
            _product("MISSING-C1", "", "", ""),
            _product("UNKNOWN-C1", "99", "알수없는분류", ""),
        ]
    )
    corrections = pd.DataFrame(
        [
            {"상품코드": "UNMATCHED", "기능구분1": "스킨케어", "기능구분2": "토너"},
            {"상품코드": "MISSING-C1", "기능구분1": "스킨케어", "기능구분2": "토너"},
        ]
    )

    season = build_season_ingredient_analysis(
        {
            "sales_history": sales,
            "prod_list": products,
            "category_correction": corrections,
        },
        _options(),
    )["season_analysis"]

    assert {row[PRODUCT_CODE_COL] for row in season["countrySkuSummary"]} == {"COS"}
    diagnostics = {row[PRODUCT_CODE_COL]: row for row in season["uncategorizedSku"]}
    assert diagnostics["UNMATCHED"]["진단사유"] == "상품마스터 미매칭"
    assert diagnostics["MISSING-C1"]["진단사유"] == "상품마스터 대분류 누락"
    assert diagnostics["UNKNOWN-C1"]["진단사유"] == "상품마스터 대분류 확인 필요"
    assert diagnostics["UNMATCHED"]["수정가능"] is False
    assert diagnostics["MISSING-C1"]["수정가능"] is False


def test_cosmetic_middle_category_correction_can_restore_eligible_sku():
    products = pd.DataFrame([_product("COS-MISSING-C2", "01", "스킨케어", "")])
    corrections = pd.DataFrame(
        [{"상품코드": "COS-MISSING-C2", "기능구분1": "스킨케어", "기능구분2": "토너"}]
    )

    season = build_season_ingredient_analysis(
        {
            "sales_history": _sales("COS-MISSING-C2"),
            "prod_list": products,
            "category_correction": corrections,
        },
        _options(),
    )["season_analysis"]

    assert {row[PRODUCT_CODE_COL] for row in season["countrySkuSummary"]} == {"COS-MISSING-C2"}
    assert season["uncategorizedSku"] == []


def test_default_cms_category_override_can_restore_missing_product_master_skus(monkeypatch):
    corrections = pd.DataFrame(
        [
            {
                "\uc0c1\ud488\ucf54\ub4dc": "TKBSM05-Cstick",
                "\uae30\ub2a5\uad6c\ubd841": "\uc36c\ucf00\uc5b4",
                "\uae30\ub2a5\uad6c\ubd842": "\ud06c\ub9bc",
            },
            {
                "\uc0c1\ud488\ucf54\ub4dc": "JSMS01-SG",
                "\uae30\ub2a5\uad6c\ubd841": "\uc2a4\ud0a8\ucf00\uc5b4",
                "\uae30\ub2a5\uad6c\ubd842": "\uc138\ub7fc",
            },
            {
                "\uc0c1\ud488\ucf54\ub4dc": "DRAS01-Gseu",
                "\uae30\ub2a5\uad6c\ubd841": "\uc2a4\ud0a8\ucf00\uc5b4",
                "\uae30\ub2a5\uad6c\ubd842": "\uc138\ub7fc",
            },
        ]
    )
    monkeypatch.setattr(season_ingredient_analysis, "read_default_category_corrections", lambda: corrections)

    season = build_season_ingredient_analysis(
        {
            "sales_history": _sales("TKBSM05-Cstick", "JSMS01-SG", "DRAS01-Gseu"),
            "prod_list": pd.DataFrame(),
        },
        _options(),
    )["season_analysis"]

    assert {row[PRODUCT_CODE_COL] for row in season["countrySkuSummary"]} == {
        "TKBSM05-Cstick",
        "JSMS01-SG",
        "DRAS01-Gseu",
    }
    assert season["uncategorizedSku"] == []


def test_strict_scope_rejects_zero_eligible_cosmetic_skus():
    with pytest.raises(CosmeticScopeValidationError, match="Cosmetic SKU가 0건"):
        build_season_ingredient_analysis(
            {
                "sales_history": _sales("SCARF"),
                "prod_list": pd.DataFrame([_product("SCARF", "18", "스카프", "패션잡화")]),
            },
            _options(),
        )


def test_api_analysis_blocks_when_product_master_response_is_empty(monkeypatch):
    monkeypatch.setattr(
        season_api_analysis_service,
        "exchange_rate_analysis_options",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        season_api_analysis_service,
        "fetch_cached_season_trend_source_data",
        lambda **_kwargs: (
            {
                "sales_history": _sales("COS").to_dict("records"),
                "prod_list": [],
            },
            {},
        ),
    )

    with pytest.raises(HTTPException) as error:
        season_api_analysis_service.run_api_analysis_with_options(
            {
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "entity_code": "PL",
            },
            save_result=False,
        )

    assert error.value.status_code == 502
    assert "상품마스터 API 응답이 비어" in str(error.value.detail)


def test_api_analysis_returns_cause_check_error_when_cosmetic_population_is_zero(monkeypatch):
    monkeypatch.setattr(
        season_api_analysis_service,
        "exchange_rate_analysis_options",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        season_api_analysis_service,
        "fetch_cached_season_trend_source_data",
        lambda **_kwargs: (
            {
                "sales_history": _sales("SCARF").to_dict("records"),
                "prod_list": [_product("SCARF", "18", "스카프", "패션잡화")],
            },
            {},
        ),
    )

    with pytest.raises(HTTPException) as error:
        season_api_analysis_service.run_api_analysis_with_options(
            {
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "entity_code": "PL",
            },
            save_result=False,
        )

    assert error.value.status_code == 422
    assert "Cosmetic SKU가 0건" in str(error.value.detail)
