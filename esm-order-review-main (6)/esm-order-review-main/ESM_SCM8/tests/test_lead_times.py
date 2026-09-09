from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta

import pytest

from core import lead_times


EXPECTED_LEAD_TIMES: dict[str, dict[str, int]] = {
    "HQ": {},
    "PL": {
        "OCEAN": 70,
        "TRUCKING": 30,
        "RAIL": 30,
        "AIR": 15,
    },
    "UK": {
        "OCEAN": 75,
        "AIR_DIR": 5,
        "AIR_TS": 12,
    },
    "USA": {
        "OCEAN": 30,
        "AIR": 5,
    },
    "ME": {
        "OCEAN": 50,
        "AIR": 6,
    },
    "MX": {
        "OCEAN": 40,
        "AIR": 16,
    },
    "MY": {
        "OCEAN": 21,
        "AIR": 6,
    },
    "VN": {
        "OCEAN": 20,
        "AIR": 6,
    },
}


def _method_getter():
    for name in (
        "get_lead_time_methods",
        "lead_time_methods",
        "get_entity_lead_time_methods",
        "get_entity_lead_times",
        "list_lead_time_methods",
    ):
        candidate = getattr(lead_times, name, None)
        if callable(candidate):
            return candidate
    raise AssertionError(
        "core.lead_times must expose a public entity-method lookup function "
        "(preferably get_lead_time_methods)."
    )


def _field(value: object, *names: str) -> object | None:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return None
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _normalize_methods(entity_code: str) -> dict[str, int]:
    raw = _method_getter()(entity_code)
    if raw is None:
        return {}

    if not isinstance(raw, Mapping):
        wrapped = _field(raw, "methods", "lead_times", "leadTimes")
        if wrapped is not None:
            raw = wrapped

    keyed_entries: list[tuple[str | None, object]]
    if isinstance(raw, Mapping):
        wrapped = _field(raw, "methods", "lead_times", "leadTimes")
        if wrapped is not None:
            raw = wrapped

    if isinstance(raw, Mapping):
        keyed_entries = [(str(key), value) for key, value in raw.items()]
    else:
        keyed_entries = [(None, value) for value in raw]

    normalized: dict[str, int] = {}
    for fallback_code, method in keyed_entries:
        if isinstance(method, int) and not isinstance(method, bool):
            code = fallback_code
            days = method
        else:
            code = _field(method, "code", "transport_code", "transportCode")
            days = _field(method, "lead_time_days", "leadTimeDays", "days")
            if code is None:
                code = fallback_code

        assert isinstance(code, str) and code, f"Missing transport code in {method!r}"
        assert type(days) is int, f"{entity_code}/{code} days must be stored as an integer"
        assert code not in normalized, f"Duplicate transport code for {entity_code}: {code}"
        normalized[code] = days

    return normalized


SUPPORTED_CASES = [
    pytest.param(entity_code, transport_code, days, id=f"{entity_code}-{transport_code}")
    for entity_code, methods in EXPECTED_LEAD_TIMES.items()
    for transport_code, days in methods.items()
]


@pytest.mark.parametrize("entity_code,transport_code,expected_days", SUPPORTED_CASES)
def test_resolve_lead_time_returns_exact_entity_transport_default(
    entity_code: str,
    transport_code: str,
    expected_days: int,
):
    actual = lead_times.resolve_lead_time(entity_code, transport_code)

    assert type(actual) is int
    assert actual == expected_days


@pytest.mark.parametrize(
    "entity_code,expected",
    [
        pytest.param(entity_code, expected, id=entity_code)
        for entity_code, expected in EXPECTED_LEAD_TIMES.items()
    ],
)
def test_entity_method_lookup_has_exact_supported_codes_and_integer_days(
    entity_code: str,
    expected: dict[str, int],
):
    assert _normalize_methods(entity_code) == expected


@pytest.mark.parametrize(
    "entity_code,transport_code",
    [
        ("USA", "RAIL"),
        ("VN", "TRUCKING"),
        ("MX", "AIR_DIR"),
        ("HQ", "OCEAN"),
        ("UK", "TRUCKING"),
        ("UK", "RAIL"),
    ],
)
def test_resolve_lead_time_returns_none_for_unsupported_combinations(
    entity_code: str,
    transport_code: str,
):
    assert lead_times.resolve_lead_time(entity_code, transport_code) is None


def test_user_override_wins_for_current_supported_combination_without_mutating_default():
    assert lead_times.resolve_lead_time("PL", "OCEAN", optional_user_override=42) == 42
    assert lead_times.resolve_lead_time("PL", "OCEAN") == 70


def test_uk_direct_and_transshipment_are_distinct_and_seven_days_apart():
    direct_days = lead_times.resolve_lead_time("UK", "AIR_DIR")
    transshipment_days = lead_times.resolve_lead_time("UK", "AIR_TS")

    assert direct_days == 5
    assert transshipment_days == 12
    ship_date = date(2026, 7, 23)
    assert (ship_date + timedelta(days=transshipment_days)) - (
        ship_date + timedelta(days=direct_days)
    ) == timedelta(days=7)


def test_hq_has_no_overseas_transport_methods_or_default():
    assert _normalize_methods("HQ") == {}
    for transport_code in ("OCEAN", "TRUCKING", "RAIL", "AIR", "AIR_DIR", "AIR_TS"):
        assert lead_times.resolve_lead_time("HQ", transport_code) is None
