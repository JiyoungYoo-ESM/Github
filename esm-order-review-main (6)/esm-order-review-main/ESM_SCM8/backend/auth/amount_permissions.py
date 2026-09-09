"""Central monetary-data authorization and response sanitization.

Ratios, shares, percentages, ranks and quantities are intentionally not
classified as amount data.  Unknown or unauthenticated users fail closed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from backend.auth.models import UserAccount


AMOUNT_DATA_ALLOWED_USERS = frozenset({"adminmaster", "ia"})
ORDER_LOGIC_V2_SETTINGS_ALLOWED_USERS = frozenset({"adminmaster", "ia"})

_NON_AMOUNT_TOKENS = (
    "ratio",
    "share",
    "percentage",
    "percent",
    "contribution",
    "marketshare",
    "growthrate",
    "rank",
    "점유율",
    "비중",
    "구성비",
    "증감률",
    "순위",
)
_AMOUNT_TOKENS = (
    "amount",
    "revenue",
    "salesvalue",
    "inventoryvalue",
    "inventorycost",
    "stockvalue",
    "orderamount",
    "purchaseamount",
    "totalamount",
    "unitprice",
    "averageprice",
    "avgprice",
    "currencyamount",
    "krwamount",
    "salesprice",
    "purchaseprice",
    "매출액",
    "판매금액",
    "발주금액",
    "구매금액",
    "재고금액",
    "금액",
    "총매출",
    "재고자본",
    "매입단가",
    "판매단가",
    "평균단가",
    "평균판매단가",
    "원화환산",
    "환산금액",
    "합계금액",
    "총액",
)
_EXACT_AMOUNT_KEYS = {
    "amount",
    "revenue",
    "sales",
    "price",
    "cost",
    "매출",
    "금액",
    "단가",
    "원화",
}
_CONTEXT_LABEL_KEYS = {
    "metric",
    "metricname",
    "metriclabel",
    "measure",
    "basis",
    "기준",
    "지표",
    "항목",
}
_CONTEXT_VALUE_KEYS = {
    "value",
    "값",
    "current",
    "previous",
    "현재",
    "이전",
    "display",
    "표시값",
}
_CURRENCY_VALUE_PATTERN = re.compile(
    r"(?:(?:KRW|EUR|USD|GBP|PLN)\s*)?[₩€$£]\s*-?[\d,.]+(?:\s*(?:억|만|천))?"
    r"|-?[\d,.]+\s*(?:원|억원|만원)"
)


def normalize_username(username: str | None) -> str:
    return (username or "").strip().lower()


def can_view_amount_data(user_or_username: UserAccount | str | None) -> bool:
    username = user_or_username.username if isinstance(user_or_username, UserAccount) else user_or_username
    return normalize_username(username) in AMOUNT_DATA_ALLOWED_USERS


def can_manage_order_logic_v2_settings(
    user_or_username: UserAccount | str | None,
) -> bool:
    username = (
        user_or_username.username
        if isinstance(user_or_username, UserAccount)
        else user_or_username
    )
    return normalize_username(username) in ORDER_LOGIC_V2_SETTINGS_ALLOWED_USERS


def _normalize_field_name(value: object) -> str:
    return re.sub(r"[\s_\-./()\[\]]+", "", str(value or "")).lower()


def is_amount_field(field_name: object) -> bool:
    normalized = _normalize_field_name(field_name)
    if not normalized or any(token in normalized for token in _NON_AMOUNT_TOKENS):
        return False
    return normalized in _EXACT_AMOUNT_KEYS or any(token in normalized for token in _AMOUNT_TOKENS)


def _mapping_has_amount_context(value: Mapping[object, object]) -> bool:
    for key, item in value.items():
        if _normalize_field_name(key) in _CONTEXT_LABEL_KEYS and isinstance(item, str) and is_amount_field(item):
            return True
    return False


def redact_amount_text(value: str) -> str:
    """Remove direct currency values while retaining non-amount narrative."""

    return _CURRENCY_VALUE_PATTERN.sub("[금액 제한]", value)


def sanitize_amount_data(value: Any) -> Any:
    """Recursively remove monetary fields without removing ratios or ranks."""

    if isinstance(value, Mapping):
        amount_context = _mapping_has_amount_context(value)
        sanitized: dict[Any, Any] = {}
        for key, item in value.items():
            normalized_key = _normalize_field_name(key)
            if is_amount_field(key):
                continue
            if amount_context and normalized_key in _CONTEXT_VALUE_KEYS:
                continue
            if normalized_key in {"htmlsnapshot", "__htmlsnapshot"}:
                sanitized[key] = None
                continue
            sanitized[key] = sanitize_amount_data(item)
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_amount_data(item) for item in value]
    if isinstance(value, str):
        return redact_amount_text(value)
    return value


__all__ = [
    "AMOUNT_DATA_ALLOWED_USERS",
    "ORDER_LOGIC_V2_SETTINGS_ALLOWED_USERS",
    "can_manage_order_logic_v2_settings",
    "can_view_amount_data",
    "is_amount_field",
    "normalize_username",
    "redact_amount_text",
    "sanitize_amount_data",
]
