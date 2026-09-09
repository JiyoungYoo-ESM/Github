from datetime import date

import pandas as pd

from core import kpi, loaders, order_review, validation
from core import sales as sales_mod


def _settings() -> dict:
    settings = validation.default_settings_for_validation()
    settings.update(
        {
            "base_date": date(2026, 5, 19),
            "period_start": date(2026, 2, 18),
            "period_end": date(2026, 5, 18),
            "safety_months": 3.0,
            "include_hq_eu_in_order_coverage": True,
            "eur_krw_rate": 1500,
        }
    )
    return settings


def test_usa_default_settings_keep_entity_and_currency_context() -> None:
    settings = validation.default_settings_for_validation("USA")

    assert settings["entity_code"] == "USA"
    assert settings["currency_code"] == "USD"


def _install_uploaded_data(monkeypatch, eu_stock: pd.DataFrame) -> None:
    empty = pd.DataFrame()
    uploaded = {
        "eu_stock": eu_stock,
        "hq_eu_stock": empty,
        "shipping": empty,
        "open_po": empty,
        "sales_detail": empty,
    }

    def data_for_key(key: str, sample_func, context=None) -> pd.DataFrame:
        return uploaded.get(key, empty).copy()

    monkeypatch.setattr(loaders, "get_order_review_data_or_empty", data_for_key)
    monkeypatch.setattr(loaders, "get_data_or_sample", data_for_key)


def test_unit_price_decimal_comma_is_not_read_as_thousands() -> None:
    prices = kpi.to_unit_price_number_series(pd.Series(["7,338", "12,50", 7338, 4500]))
    quantities = kpi.to_number_series(pd.Series(["1,006", "12,141,127"]))

    assert round(float(prices.iloc[0]), 3) == 7.338
    assert float(prices.iloc[1]) == 12.5
    assert round(float(prices.iloc[2]), 3) == 7.338
    assert float(prices.iloc[3]) == 4.5
    assert int(quantities.iloc[0]) == 1006
    assert int(quantities.iloc[1]) == 12141127


def test_to_number_series_numeric_dtype_fast_path_matches_legacy_missing_rule() -> None:
    values = kpi.to_number_series(pd.Series([1, 2.5, None, float("nan")]))

    assert values.tolist() == [1.0, 2.5, 0.0, 0.0]


def test_to_number_series_bool_dtype_uses_text_path() -> None:
    values = kpi.to_number_series(pd.Series([True, False]))

    assert values.tolist() == [0.0, 0.0]


def test_upload_price_parsing_uses_file_currency_context() -> None:
    raw = pd.DataFrame({"상품코드": ["SKU_A"], "입고단가": ["8,000"]})

    eu_stock = loaders.clean_uploaded_dataframe(raw, key="eu_stock")
    hq_stock = loaders.clean_uploaded_dataframe(raw, key="hq_eu_stock")

    assert float(eu_stock["EU 입고단가"].iloc[0]) == 8
    assert float(hq_stock["EU 입고단가"].iloc[0]) == 8000


def test_eu_local_stock_unit_price_is_always_treated_as_eur(monkeypatch) -> None:
    eu_stock = pd.DataFrame(
        [
            {
                "브랜드": "BRAND",
                "상품코드": "SKU_EUR_HIGH",
                "상품명": "EUR priced item",
                "바코드": "8800000000001",
                "재고수량": 0,
                "Hold수량": 0,
                "EU 입고단가": 8000,
                "최근 3개월 판매수량": 90,
            }
        ]
    )
    _install_uploaded_data(monkeypatch, eu_stock)

    review = order_review.order_review_df(_settings())
    row = review.loc[review["상품코드"].eq("SKU_EUR_HIGH")].iloc[0]

    assert row["원본 EU 입고단가 통화"] == "EUR"
    assert row["EU 입고단가 확인필요 플래그"] == ""
    assert row["발주필요수량"] == 90
    assert row["발주필요금액"] == 90 * 8 * 1500
    assert row["원본 EU 입고단가"] == 8
    assert row["EU 입고단가"] == 8


def test_explicit_eur_unit_price_still_uses_fx_conversion(monkeypatch) -> None:
    eu_stock = pd.DataFrame(
        [
            {
                "브랜드": "BRAND",
                "상품코드": "SKU_EUR",
                "상품명": "EUR priced item",
                "바코드": "8800000000002",
                "재고수량": 0,
                "Hold수량": 0,
                "EU 입고단가": 8,
                "EU 입고단가 통화": "EUR",
                "최근 3개월 판매수량": 90,
            }
        ]
    )
    _install_uploaded_data(monkeypatch, eu_stock)

    review = order_review.order_review_df(_settings())
    row = review.loc[review["상품코드"].eq("SKU_EUR")].iloc[0]

    assert row["원본 EU 입고단가 통화"] == "EUR"
    assert row["발주필요수량"] == 90
    assert row["발주필요금액"] == 90 * 8 * 1500
    assert row["EU 입고단가"] == 8


def test_cms_krw_unit_price_drives_v1_order_amount_without_current_fx(monkeypatch) -> None:
    eu_stock = pd.DataFrame(
        [
            {
                "브랜드": "BRAND",
                "상품코드": "SKU_CMS_KRW",
                "상품명": "CMS KRW priced item",
                "바코드": "8800000000010",
                "재고수량": 0,
                "Hold수량": 0,
                "EU 입고단가": 8,
                "CMS 원화 입고단가": 12_345,
                "최근 3개월 판매수량": 90,
            }
        ]
    )
    _install_uploaded_data(monkeypatch, eu_stock)

    review = order_review.order_review_df(_settings())
    row = review.loc[review["상품코드"].eq("SKU_CMS_KRW")].iloc[0]

    assert row["발주필요수량"] == 90
    assert row["현지 입고단가_KRW"] == 12_345
    assert row["발주필요금액"] == 90 * 12_345
    assert row["단가 출처"] == "CMS 조회 기준일 원화 단가"


def test_usa_unit_price_and_order_amount_use_usd_rate(monkeypatch) -> None:
    local_stock = pd.DataFrame(
        [
            {
                "브랜드": "BRAND",
                "상품코드": "SKU_USD",
                "상품명": "USD priced item",
                "바코드": "8800000000099",
                "재고수량": 0,
                "Hold수량": 0,
                "현지 입고단가": 8,
                "현지 입고단가 통화": "USD",
                "최근 3개월 판매수량": 90,
            }
        ]
    )
    _install_uploaded_data(monkeypatch, local_stock)
    settings = _settings()
    settings.update(
        {
            "entity_code": "USA",
            "currency_code": "USD",
            "currency_krw_rate": 1450,
            "eur_krw_rate": 1450,
        }
    )

    review = order_review.order_review_df(settings)
    row = review.loc[review["상품코드"].eq("SKU_USD")].iloc[0]

    assert row["원본 현지 입고단가 통화"] == "USD"
    assert row["현지 통화"] == "USD"
    assert row["현지 입고단가_USD"] == 8
    assert row["발주필요수량"] == 90
    assert row["부족금액_USD"] == 90 * 8
    assert row["부족금액_KRW"] == 90 * 8 * 1450


def test_decimal_comma_eur_unit_price_drives_order_amount(monkeypatch) -> None:
    eu_stock = pd.DataFrame(
        [
            {
                "브랜드": "BRAND",
                "상품코드": "SKU_DECIMAL",
                "상품명": "Decimal EUR priced item",
                "바코드": "8800000000003",
                "재고수량": 0,
                "Hold수량": 0,
                "EU 입고단가": 7338,
                "최근 3개월 판매수량": 90,
            }
        ]
    )
    _install_uploaded_data(monkeypatch, eu_stock)

    review = order_review.order_review_df(_settings())
    row = review.loc[review["상품코드"].eq("SKU_DECIMAL")].iloc[0]

    assert round(float(row["EU 입고단가"]), 3) == 7.338
    assert round(float(row["발주필요금액"]), 3) == round(90 * 7.338 * 1500, 3)


def test_zero_eu_unit_price_is_excluded_from_order_review_even_with_other_price_sources(monkeypatch) -> None:
    eu_stock = pd.DataFrame(
        [
            {
                "브랜드": "BRAND",
                "상품코드": "SKU_ZERO",
                "상품명": "Zero priced item",
                "바코드": "8800000000004",
                "재고수량": 0,
                "Hold수량": 0,
                "EU 입고단가": 0,
                "최근 3개월 판매수량": 90,
            }
        ]
    )
    shipping = pd.DataFrame(
        [
            {
                "운송수단": "해운",
                "SKU": "SKU_ZERO",
                "브랜드": "BRAND",
                "상품명": "Zero priced item",
                "수량": 100,
                "금액": 1000,
                "출고일": "2026-05-01",
            }
        ]
    )
    hq_stock = pd.DataFrame(
        [
            {
                "상품코드": "SKU_ZERO",
                "재고수량": 0,
                "Hold수량": 0,
                "평균단가": 9000,
            }
        ]
    )
    hq_to_eu_sales = pd.DataFrame([{"SKU": "SKU_ZERO", "수량": 10, "금액": 100}])
    sales_detail = pd.DataFrame([{"SKU": "SKU_ZERO", "판매수량": 90, "금액": 900}])
    empty = pd.DataFrame()
    uploaded = {
        "eu_stock": eu_stock,
        "hq_eu_stock": hq_stock,
        "shipping": shipping,
        "open_po": empty,
        "sales_detail": sales_detail,
        "hq_to_eu_sales_detail": hq_to_eu_sales,
    }

    def data_for_key(key: str, sample_func, context=None) -> pd.DataFrame:
        return uploaded.get(key, empty).copy()

    monkeypatch.setattr(loaders, "get_order_review_data_or_empty", data_for_key)
    monkeypatch.setattr(loaders, "get_data_or_sample", data_for_key)

    review = order_review.order_review_df(_settings())
    assert review.loc[review["상품코드"].eq("SKU_ZERO")].empty

    excluded = order_review.order_review_df(_settings(), excluded_only=True)
    row = excluded.loc[excluded["상품코드"].eq("SKU_ZERO")].iloc[0]

    assert row["발주필요금액"] == 0
    assert row["부족금액_EUR"] == 0
    assert row["단가 출처"] == "0단가 제외"
    assert row["단가 미등록 플래그"] == ""
    assert bool(row["제외 SKU"]) is True
    assert "0단가" in row["제외유형"]


def test_hq_stock_amount_infers_krw_unit_price_without_currency_label() -> None:
    hq_stock = pd.DataFrame(
        [
            {
                "상품코드": "SKU_HQ_KRW",
                "재고수량": 10,
                "Hold수량": 0,
                "입고단가": 8000,
            }
        ]
    )

    amount_million, source = kpi.hq_eu_stock_amount_for_df_with_source(hq_stock, 1500)

    assert amount_million == 0.08
    assert "평균단가 KRW" in source


def test_hq_to_eu_sales_detail_amount_is_converted_from_eur(monkeypatch) -> None:
    sales = pd.DataFrame(
        [
            {"브랜드": "BRAND", "SKU": "SKU_A", "출고일": "2026-05-10", "환산금액": 100},
            {"브랜드": "BRAND", "SKU": "SKU_B", "출고일": "2026-04-10", "환산금액": 50},
        ]
    )

    monkeypatch.setattr(sales_mod, "get_hq_to_eu_sales_detail", lambda context=None: sales)

    amount_krw = kpi.hq_to_eu_shipment_amount(date(2026, 5, 19), settings=_settings())
    amount_eur = kpi.hq_to_eu_shipment_amount_eur(date(2026, 5, 19), settings=_settings())

    assert amount_eur == 100
    assert amount_krw == 100 * 1500
