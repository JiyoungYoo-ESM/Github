"""Synthetic hand-calculation checks for local proposal amounts."""

import pytest

from core.order_logic_v3_amount import calculate_v3_local_order_amount


@pytest.mark.parametrize("quantity,price,expected", [
    (100, 6.10, 610), (10.25, 0.75, 7.6875), (2.5, 0.75, 1.875),
    (0, 6.10, 0), (100, 0, 0),
    (None, 6.10, None), (100, None, None), (0, None, None),
    (float("nan"), 1, None), (1, float("inf"), None), (1e308, 1e308, None),
])
def test_local_amount_preserves_raw_precision_and_missing_values(quantity, price, expected):
    assert calculate_v3_local_order_amount(quantity, price) == expected
