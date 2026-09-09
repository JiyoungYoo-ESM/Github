from __future__ import annotations

import logging
import os
from datetime import date

LEGACY_DEFAULT_EUR_KRW_RATE = 1726.89
DEFAULT_EUR_KRW_RATE_AS_OF = os.environ.get("DEFAULT_EUR_KRW_RATE_AS_OF", "unknown").strip() or "unknown"
DEFAULT_EUR_KRW_RATE_SOURCE = (
    os.environ.get("DEFAULT_EUR_KRW_RATE_SOURCE", "legacy hardcoded fallback").strip()
    or "legacy hardcoded fallback"
)
FALLBACK_RATE_WARNING_DAYS = 30
FALLBACK_RATE_RESULT_WARNING_DAYS = 90


def configured_default_eur_krw_rate() -> float:
    raw_rate = os.environ.get("DEFAULT_EUR_KRW_RATE", "").strip()
    if not raw_rate:
        return LEGACY_DEFAULT_EUR_KRW_RATE
    try:
        rate = float(raw_rate.replace(",", ""))
    except ValueError:
        return LEGACY_DEFAULT_EUR_KRW_RATE
    return rate if rate > 0 else LEGACY_DEFAULT_EUR_KRW_RATE


DEFAULT_EUR_KRW_RATE = configured_default_eur_krw_rate()


def fallback_rate_age_days(
    as_of: str = DEFAULT_EUR_KRW_RATE_AS_OF,
    today: date | None = None,
) -> int | None:
    if not as_of or as_of == "unknown":
        return None
    try:
        as_of_date = date.fromisoformat(as_of)
    except ValueError:
        return None
    return ((today or date.today()) - as_of_date).days


def fallback_rate_warning(
    as_of: str = DEFAULT_EUR_KRW_RATE_AS_OF,
    today: date | None = None,
) -> str:
    days_old = fallback_rate_age_days(as_of, today)
    if days_old is None:
        return "EUR/KRW fallback rate as-of date is unknown."
    if days_old > FALLBACK_RATE_RESULT_WARNING_DAYS:
        return f"EUR/KRW fallback rate is {days_old} days old."
    if days_old > FALLBACK_RATE_WARNING_DAYS:
        return f"EUR/KRW fallback rate is {days_old} days old."
    return ""


def fallback_rate_metadata(today: date | None = None) -> dict[str, object]:
    warning = fallback_rate_warning(today=today)
    metadata: dict[str, object] = {
        "fallback_rate": DEFAULT_EUR_KRW_RATE,
        "fallback_rate_as_of": DEFAULT_EUR_KRW_RATE_AS_OF,
        "fallback_rate_source": DEFAULT_EUR_KRW_RATE_SOURCE,
        "fallback_rate_age_days": fallback_rate_age_days(today=today),
    }
    if warning:
        metadata["rate_warning"] = warning
    return metadata


def warn_if_fallback_rate_stale(logger: logging.Logger, today: date | None = None) -> None:
    warning = fallback_rate_warning(today=today)
    if warning:
        logger.warning(warning)

