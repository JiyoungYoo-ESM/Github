from datetime import date

from backend.services import season_api_analysis_service


def test_exchange_rate_options_describe_per_transaction_actual_krw(monkeypatch):
    monkeypatch.setattr(
        season_api_analysis_service,
        "korea_today",
        lambda: date(2026, 7, 23),
    )

    options = season_api_analysis_service.exchange_rate_analysis_options(
        "2024-04-01",
        "2024-12-31",
    )

    assert options["average_eur_krw_rate"] == 0.0
    assert options["currency_code"] == "KRW"
    assert options["currency_krw_rate"] == 1.0
    assert options["exchange_rate_source"] == "per_transaction"
    assert options["exchange_rate_date"] is None
    assert options["exchange_rate_checked_date"] == "2026-07-23"
    assert "거래일 고시환율" in options["exchange_rate_basis"]
    assert options["sales_amount_field"] == "amount_krw_actual"


def test_us_exchange_rate_options_use_actual_krw_amount():
    options = season_api_analysis_service.exchange_rate_analysis_options(
        "2025-07-01",
        "2026-07-01",
        entity_code="USA",
    )

    assert options["currency_code"] == "KRW"
    assert options["currency_krw_rate"] == 1.0
    assert options["exchange_rate_source"] == "per_transaction"
    assert options["sales_amount_field"] == "amount_krw_actual"


def test_hq_exchange_rate_options_keep_native_krw_amount():
    options = season_api_analysis_service.exchange_rate_analysis_options(
        "2025-07-01",
        "2026-07-01",
        entity_code="HQ",
    )

    assert options["currency_code"] == "KRW"
    assert options["currency_krw_rate"] == 1.0
    assert options["average_eur_krw_rate"] == 0.0
    assert options["exchange_rate_source"] == "native"
    assert "amount_krw" in options["exchange_rate_basis"]
