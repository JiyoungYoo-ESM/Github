"""Pure V3 local-currency valuation; multiplies a quantity by a unit price, no FX."""

from math import isfinite


def calculate_v3_local_order_amount(
    order_quantity: float | None, unit_price_local: float | None,
) -> float | None:
    """Value the supplied order quantity, preserving missing inputs separately from zero."""
    if order_quantity is None or unit_price_local is None:
        return None
    if not isfinite(order_quantity) or not isfinite(unit_price_local):
        return None
    amount = order_quantity * unit_price_local
    return amount if isfinite(amount) else None
