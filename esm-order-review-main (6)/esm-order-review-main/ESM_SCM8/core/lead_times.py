"""Canonical legal-entity transport lead-time reference data.

The attached workbook is a controlled source document, not a runtime
dependency.  Values are kept here so every API, analysis, cache key and export
can consume one reviewed configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


LEAD_TIME_EFFECTIVE_DATE = "2026-07-23"
LEAD_TIME_SOURCE = "해외법인 리드타임 260723ver.xlsx"


@dataclass(frozen=True, slots=True)
class LeadTimeMethod:
    entity_code: str
    transport_code: str
    transport_group: str
    service_type: str | None
    display_name: str
    lead_time_days: int
    source: str = LEAD_TIME_SOURCE
    effective_date: str = LEAD_TIME_EFFECTIVE_DATE

    def as_dict(
        self,
        *,
        lead_time_days: int | None = None,
        user_override: bool = False,
    ) -> dict[str, object]:
        resolved_days = self.lead_time_days if lead_time_days is None else int(lead_time_days)
        return {
            "entity_code": self.entity_code,
            "transport_code": self.transport_code,
            "transport_group": self.transport_group,
            "service_type": self.service_type,
            "display_name": self.display_name,
            "lead_time_days": resolved_days,
            "source": self.source,
            "effective_date": self.effective_date,
            # Concise aliases used by the reference API and frontend.
            "code": self.transport_code,
            "label": self.display_name,
            "default_lead_time_days": self.lead_time_days,
            "user_override": user_override,
        }


def _method(
    entity_code: str,
    transport_code: str,
    transport_group: str,
    display_name: str,
    lead_time_days: int,
    service_type: str | None = None,
) -> LeadTimeMethod:
    return LeadTimeMethod(
        entity_code=entity_code,
        transport_code=transport_code,
        transport_group=transport_group,
        service_type=service_type,
        display_name=display_name,
        lead_time_days=lead_time_days,
    )


LEAD_TIME_CONFIG: dict[str, tuple[LeadTimeMethod, ...]] = {
    "HQ": (),
    "PL": (
        _method("PL", "OCEAN", "OCEAN", "해운", 70),
        _method("PL", "TRUCKING", "TRUCKING", "트럭킹", 30),
        _method("PL", "RAIL", "RAIL", "철송", 30),
        _method("PL", "AIR", "AIR", "항공", 15),
    ),
    "UK": (
        _method("UK", "OCEAN", "OCEAN", "해운", 75),
        _method("UK", "AIR_DIR", "AIR", "항공(DIR·직항)", 5, "DIR"),
        _method("UK", "AIR_TS", "AIR", "항공(T/S·환적)", 12, "T/S"),
    ),
    "USA": (
        _method("USA", "OCEAN", "OCEAN", "해운", 30),
        _method("USA", "AIR", "AIR", "항공", 5),
    ),
    "ME": (
        _method("ME", "OCEAN", "OCEAN", "해운", 50),
        _method("ME", "AIR", "AIR", "항공", 6),
    ),
    "MX": (
        _method("MX", "OCEAN", "OCEAN", "해운", 40),
        _method("MX", "AIR", "AIR", "항공", 16),
    ),
    "MY": (
        _method("MY", "OCEAN", "OCEAN", "해운", 21),
        _method("MY", "AIR", "AIR", "항공", 6),
    ),
    "VN": (
        _method("VN", "OCEAN", "OCEAN", "해운", 20),
        _method("VN", "AIR", "AIR", "항공", 6),
    ),
}

# Descriptive alias for callers that prefer an entity-qualified name.
ENTITY_LEAD_TIME_METHODS = LEAD_TIME_CONFIG

TRANSPORT_GROUP_DISPLAY_NAMES = {
    "OCEAN": "해운",
    "TRUCKING": "트럭",
    "RAIL": "철송",
    "AIR": "항공",
}


def _canonical_entity_code(entity_code: object) -> str:
    return str(entity_code or "").strip().upper()


def _canonical_transport_code(transport_code: object) -> str:
    return str(transport_code or "").strip().upper().replace("-", "_")


def lead_time_methods(entity_code: object) -> tuple[LeadTimeMethod, ...]:
    """Return the configured methods for an entity, or an empty tuple."""

    return LEAD_TIME_CONFIG.get(_canonical_entity_code(entity_code), ())


def lead_time_method(entity_code: object, transport_code: object) -> LeadTimeMethod | None:
    code = _canonical_transport_code(transport_code)
    return next(
        (method for method in lead_time_methods(entity_code) if method.transport_code == code),
        None,
    )


def resolve_lead_time(
    entity_code: object,
    transport_code: object,
    optional_user_override: int | None = None,
    *,
    user_override: int | None = None,
) -> int | None:
    """Resolve an exact supported entity/method pair without fallback.

    An override can replace a supported method's default for one analysis.  It
    cannot create an unsupported method for an entity.
    """

    if optional_user_override is not None and user_override is not None:
        raise ValueError("provide only one lead-time override")
    override = user_override if user_override is not None else optional_user_override
    method = lead_time_method(entity_code, transport_code)
    if method is None:
        return None
    if override is None:
        return method.lead_time_days
    if isinstance(override, bool) or not isinstance(override, int) or override <= 0:
        raise ValueError("lead-time overrides must be positive integers")
    return override


def normalize_lead_time_overrides(
    entity_code: object,
    overrides: Mapping[str, object] | None,
) -> dict[str, int]:
    """Validate and normalize a code-to-days override mapping."""

    if not overrides:
        return {}
    if not isinstance(overrides, Mapping):
        raise ValueError("lead_time_overrides must be an object mapping transport codes to days")

    normalized: dict[str, int] = {}
    for raw_code, raw_days in overrides.items():
        code = _canonical_transport_code(raw_code)
        if lead_time_method(entity_code, code) is None:
            raise ValueError(
                f"{_canonical_entity_code(entity_code)} does not support transport method {code or raw_code}"
            )
        if isinstance(raw_days, bool):
            raise ValueError(f"lead_time_overrides.{code} must be a positive integer")
        if isinstance(raw_days, int):
            days = raw_days
        elif isinstance(raw_days, str) and raw_days.strip().isdigit():
            days = int(raw_days.strip())
        else:
            raise ValueError(f"lead_time_overrides.{code} must be a positive integer")
        if days <= 0:
            raise ValueError(f"lead_time_overrides.{code} must be a positive integer")
        normalized[code] = days
    return normalized


def lead_time_reference_payload(entity_code: object) -> dict[str, object]:
    code = _canonical_entity_code(entity_code)
    return {
        "entity_code": code,
        "effective_date": LEAD_TIME_EFFECTIVE_DATE,
        "source": LEAD_TIME_SOURCE,
        "methods": [method.as_dict() for method in lead_time_methods(code)],
    }


def get_lead_time_methods(entity_code: object) -> tuple[LeadTimeMethod, ...]:
    """Public compatibility name for entity-scoped method lookup."""

    return lead_time_methods(entity_code)


def analysis_lead_time_settings(
    entity_code: object,
    overrides: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the entity-scoped settings consumed by the existing core.

    ``lead_times`` retains the core's Korean transport-group keys only when the
    entity has one unambiguous method for that group.  UK generic AIR is
    deliberately omitted because AIR_DIR and AIR_TS must be selected
    explicitly.
    """

    code = _canonical_entity_code(entity_code)
    normalized_overrides = normalize_lead_time_overrides(code, overrides)
    methods = lead_time_methods(code)
    by_code = {
        method.transport_code: resolve_lead_time(
            code,
            method.transport_code,
            optional_user_override=normalized_overrides.get(method.transport_code),
        )
        for method in methods
    }

    methods_by_group: dict[str, list[LeadTimeMethod]] = {}
    for method in methods:
        methods_by_group.setdefault(method.transport_group, []).append(method)

    legacy_lead_times: dict[str, int] = {}
    for group, group_methods in methods_by_group.items():
        if len(group_methods) != 1:
            continue
        method = group_methods[0]
        display_group = TRANSPORT_GROUP_DISPLAY_NAMES[group]
        legacy_lead_times[display_group] = int(by_code[method.transport_code])

    return {
        "entity_code": code,
        "lead_time_effective_date": LEAD_TIME_EFFECTIVE_DATE,
        "lead_time_source": LEAD_TIME_SOURCE,
        "lead_time_overrides": normalized_overrides,
        "lead_times_by_code": {key: int(value) for key, value in by_code.items()},
        "lead_time_methods": [
            method.as_dict(
                lead_time_days=int(by_code[method.transport_code]),
                user_override=method.transport_code in normalized_overrides,
            )
            for method in methods
        ],
        "lead_times": legacy_lead_times,
        "modes": [
            TRANSPORT_GROUP_DISPLAY_NAMES[group]
            for group in ("OCEAN", "RAIL", "AIR", "TRUCKING")
            if group in methods_by_group
        ],
    }


def pl_default_lead_times() -> dict[str, int]:
    """Return the legacy-shaped official PL defaults from the central source."""

    return dict(analysis_lead_time_settings("PL")["lead_times"])


__all__ = [
    "ENTITY_LEAD_TIME_METHODS",
    "LEAD_TIME_CONFIG",
    "LEAD_TIME_EFFECTIVE_DATE",
    "LEAD_TIME_SOURCE",
    "LeadTimeMethod",
    "TRANSPORT_GROUP_DISPLAY_NAMES",
    "analysis_lead_time_settings",
    "get_lead_time_methods",
    "lead_time_method",
    "lead_time_methods",
    "lead_time_reference_payload",
    "normalize_lead_time_overrides",
    "pl_default_lead_times",
    "resolve_lead_time",
]
