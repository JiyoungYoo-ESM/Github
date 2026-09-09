"""Authenticated reference-data endpoints that do not require API integration."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from backend.auth.permissions import authorize_entity
from backend.services.auth import require_authenticated_user
from core.lead_times import lead_time_reference_payload


router = APIRouter()


@router.get("/api/reference/lead-times")
def entity_lead_times(
    request: Request,
    entity_code: Annotated[str, Query(min_length=1)],
) -> dict[str, object]:
    """Return lead-time metadata after account/entity authorization only."""

    user = require_authenticated_user(request)
    authorized_code = authorize_entity(user, entity_code, request)
    request.state.entity_code = authorized_code
    return lead_time_reference_payload(authorized_code)
