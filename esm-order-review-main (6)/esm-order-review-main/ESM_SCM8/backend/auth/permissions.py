"""Reusable request-level entity authorization dependencies."""

from __future__ import annotations

from fastapi import HTTPException, Request

from backend.auth.models import UserAccount
from backend.entities import ENTITY_BY_CODE, ORDER_INTEGRATED_ENTITY_CODES, normalize_entity_code
from backend.services.audit import write_audit_event
from backend.services.auth import require_authenticated_user


ENTITY_HEADER = "x-entity-code"
ORDER_ANALYSIS_BLOCKED_USERNAMES = frozenset({"sales_team"})
# 전사 재고는 현 시점에 역할(MASTER) 전체가 아니라, 업무 오너가 지정한
# adminmaster 한 계정만 접근할 수 있다. 금액 열람 권한이나 is_admin과는 별개다.
CORPORATE_INVENTORY_ALLOWED_USERNAMES = frozenset({"adminmaster"})


def can_access_order_analysis(user: UserAccount | str | None) -> bool:
    """Return whether an account may use order-analysis features."""

    username = user.username if isinstance(user, UserAccount) else str(user or "")
    return username.strip().lower() not in ORDER_ANALYSIS_BLOCKED_USERNAMES


def require_order_analysis_access(request: Request) -> UserAccount:
    """Reject accounts that are limited to sales/insight workflows."""

    user = require_authenticated_user(request)
    if can_access_order_analysis(user):
        return user
    write_audit_event(
        "order_analysis_access_denied",
        request,
        username=user.username,
        result="forbidden",
    )
    raise HTTPException(status_code=403, detail="발주 분석 접근 권한이 없습니다.")


def can_access_corporate_inventory(user: UserAccount | str | None) -> bool:
    """Return whether the user may view the corporate inventory dashboard."""

    username = user.username if isinstance(user, UserAccount) else str(user or "")
    return username.strip().lower() in CORPORATE_INVENTORY_ALLOWED_USERNAMES


def require_corporate_inventory_access(request: Request) -> UserAccount:
    """Allow only the explicitly approved corporate-inventory account."""

    user = require_authenticated_user(request)
    if can_access_corporate_inventory(user):
        return user
    write_audit_event(
        "corporate_inventory_access_denied",
        request,
        username=user.username,
        result="forbidden",
    )
    raise HTTPException(status_code=403, detail="전사 재고 현황 접근 권한이 없습니다.")


def security_scope_from_request(request: Request) -> str:
    user = require_authenticated_user(request)
    entity_code = str(getattr(request.state, "entity_code", "") or "")
    if not entity_code:
        entity_code = authorize_entity(user, request.headers.get(ENTITY_HEADER, ""), request)
        request.state.entity_code = entity_code
    return f"{user.username}__{entity_code}"


def authorize_entity(user: UserAccount, requested_entity: str, request: Request | None = None) -> str:
    try:
        entity_code = normalize_entity_code(requested_entity)
    except HTTPException:
        write_audit_event(
            "invalid_entity_requested",
            request,
            username=user.username,
            requested_entity=(requested_entity or "").strip(),
        )
        raise
    if entity_code not in user.allowed_entities:
        write_audit_event(
            "entity_access_denied",
            request,
            username=user.username,
            requested_entity=entity_code,
            result="forbidden",
        )
        raise HTTPException(status_code=403, detail="해당 법인에 접근할 권한이 없습니다.")
    return entity_code


def require_entity_access(request: Request) -> UserAccount:
    """Authenticate, authorize the selected entity, then guard integration.

    Only entities with a confirmed CMS adapter may reach data APIs.
    Other allowed entities remain selectable but return a distinct 409 before
    any cache, external API, analysis or download code is reached.
    """

    user = require_authenticated_user(request)
    requested_entity = (
        request.headers.get(ENTITY_HEADER, "")
        or request.query_params.get("entity_code", "")
        or request.query_params.get("entity", "")
    )
    entity_code = authorize_entity(user, requested_entity, request)
    request.state.entity_code = entity_code
    entity = ENTITY_BY_CODE[entity_code]
    if not entity.integrated:
        write_audit_event(
            "entity_integration_unavailable",
            request,
            username=user.username,
            requested_entity=entity_code,
        )
        raise HTTPException(
            status_code=409,
            detail="해당 법인의 데이터 연동을 준비 중입니다.",
        )
    return user


def require_order_integration(request: Request) -> None:
    """Reject CMS-backed order analysis for insight-only entities."""

    entity_code = str(getattr(request.state, "entity_code", "") or "").strip().upper()
    if entity_code in ORDER_INTEGRATED_ENTITY_CODES:
        return
    raise HTTPException(
        status_code=409,
        detail="본사는 판매 분석 API만 연동되어 발주 분석을 제공하지 않습니다. 분석 탭을 이용해 주세요.",
    )
