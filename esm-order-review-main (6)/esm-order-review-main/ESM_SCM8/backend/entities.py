"""Canonical legal-entity definitions used by authentication and data APIs.

Permission checks always use the stable short codes below.  External API
identifiers are deliberately separate from the application-facing codes.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException


@dataclass(frozen=True, slots=True)
class EntityDefinition:
    code: str
    display_name: str
    legal_name: str
    integrated: bool
    external_api_code: str | None = None


ENTITY_DEFINITIONS: tuple[EntityDefinition, ...] = (
    EntityDefinition("HQ", "본사", "Silicon2 Co., Ltd.", True, "HQ"),
    EntityDefinition("PL", "폴란드", "SKO Sp. z o.o.", True, "EU"),
    EntityDefinition("UK", "영국", "STYLEKOREAN UK LIMITED", False),
    EntityDefinition("USA", "미국", "Stylekorean Inc.", True, "US"),
    EntityDefinition("ME", "중동·두바이", "STYLEKOREAN MIDDLE EAST TRADING FZE", False),
    EntityDefinition("MX", "멕시코", "STYLEKOREAN MX S. DE R.L. DE C.V.", False),
    EntityDefinition("MY", "말레이시아", "STYLEKOREAN MY SDN. BHD.", False),
    EntityDefinition("VN", "베트남", "STYLEKOREAN VIETNAM", False),
)

ENTITY_BY_CODE = {entity.code: entity for entity in ENTITY_DEFINITIONS}
ENTITY_CODES = tuple(entity.code for entity in ENTITY_DEFINITIONS)
INTEGRATED_ENTITY_CODES = frozenset(
    entity.code for entity in ENTITY_DEFINITIONS if entity.integrated
)
ORDER_INTEGRATED_ENTITY_CODES = frozenset({"PL", "USA"})
INSIGHT_INTEGRATED_ENTITY_CODES = frozenset({"HQ", "PL", "USA"})


def normalize_entity_code(value: str | None) -> str:
    """Return a validated canonical entity code or a stable 400 response."""

    code = (value or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="법인 코드를 선택해 주세요.")
    if code not in ENTITY_BY_CODE:
        raise HTTPException(status_code=400, detail="유효하지 않은 법인 코드입니다.")
    return code


def public_entity_definitions(codes: tuple[str, ...]) -> list[dict[str, object]]:
    return [
        {
            "code": definition.code,
            "display_name": definition.display_name,
            "legal_name": definition.legal_name,
            "integrated": definition.integrated,
            "order_integrated": definition.code in ORDER_INTEGRATED_ENTITY_CODES,
            "insight_integrated": definition.code in INSIGHT_INTEGRATED_ENTITY_CODES,
        }
        for code in codes
        if (definition := ENTITY_BY_CODE.get(code)) is not None
    ]
