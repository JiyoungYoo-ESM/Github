from datetime import date

from core.exchange_rate import (
    DEFAULT_EUR_KRW_RATE,
    fallback_rate_age_days,
    fallback_rate_metadata,
    fallback_rate_warning,
)
from core import kpi as kpi_module
from core.kpi import get_cached_eur_krw_rate, get_eur_krw_rate
from backend.routers import health as health_router


def test_default_eur_krw_fallback_has_metadata():
    metadata = fallback_rate_metadata()

    assert metadata["fallback_rate"] == DEFAULT_EUR_KRW_RATE
    assert "fallback_rate_as_of" in metadata
    assert "fallback_rate_source" in metadata


def test_fallback_rate_warning_thresholds():
    today = date(2026, 5, 28)

    assert fallback_rate_age_days("2026-05-01", today) == 27
    assert fallback_rate_warning("2026-05-01", today) == ""
    assert "40 days old" in fallback_rate_warning("2026-04-18", today)
    assert "unknown" in fallback_rate_warning("unknown", today)


def test_get_eur_krw_rate_uses_fallback_without_api_key(monkeypatch):
    monkeypatch.delenv("KOREAEXIM_API_KEY", raising=False)

    rate, rate_date, success = get_eur_krw_rate(default_rate=1234.5)

    assert rate == 1234.5
    assert rate_date == ""
    assert success is False


def test_exchange_rate_payload_is_cached_for_the_day(monkeypatch):
    health_router._exchange_rate_cache.clear()
    calls = []

    def fake_rate():
        calls.append(True)
        return 1666.16, "2026-07-29", True

    monkeypatch.setattr(health_router, "get_eur_krw_rate", fake_rate)

    first = health_router._exchange_rate_payload("EUR")
    second = health_router._exchange_rate_payload("EUR")

    assert first == second
    assert len(calls) == 1
    health_router._exchange_rate_cache.clear()


def test_get_cached_eur_krw_rate_reuses_result_for_the_day(monkeypatch):
    kpi_module._rate_lookup_cache.clear()
    calls = []

    def fake_rate(currency_code, default_rate=0.0):
        calls.append(currency_code)
        return 1666.16, "2026-07-29", True

    monkeypatch.setattr(kpi_module, "get_currency_krw_rate", fake_rate)

    first = get_cached_eur_krw_rate()
    second = get_cached_eur_krw_rate()

    assert first == second == (1666.16, "2026-07-29", True)
    assert calls == ["EUR"]
    kpi_module._rate_lookup_cache.clear()


def test_get_cached_eur_krw_rate_caches_failure_too(monkeypatch):
    kpi_module._rate_lookup_cache.clear()
    calls = []

    def fake_rate(currency_code, default_rate=0.0):
        calls.append(currency_code)
        return default_rate, "", False

    monkeypatch.setattr(kpi_module, "get_currency_krw_rate", fake_rate)

    first = get_cached_eur_krw_rate(default_rate=1234.5)
    second = get_cached_eur_krw_rate(default_rate=1234.5)

    assert first == second == (1234.5, "", False)
    assert calls == ["EUR"]
    kpi_module._rate_lookup_cache.clear()

