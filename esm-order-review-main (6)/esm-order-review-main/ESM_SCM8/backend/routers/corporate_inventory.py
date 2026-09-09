"""Master-only corporate inventory dashboard API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.auth.models import UserAccount
from backend.auth.permissions import require_corporate_inventory_access
from backend.services.corporate_inventory import corporate_inventory_payload


router = APIRouter(prefix="/api/corporate-inventory", tags=["corporate-inventory"])


@router.get("")
def get_corporate_inventory(
    _: Annotated[UserAccount, Depends(require_corporate_inventory_access)],
) -> dict[str, object]:
    """Return today's KST corporate inventory with explicit source statuses."""

    return corporate_inventory_payload()
