from __future__ import annotations

from datetime import date
import math

import pytest

from backend.services.order_logic_v2_lead_time import (
    aggregate_hq_po_sku_lead_time_rows,
    aggregate_lead_time_rows,
    lead_time_query_window,
)


def test_hq_lead_time_uses_equal_weight_po_sku_receipts_and_stdev_s() -> None:
    rows = [
        {
            "po_number": "PO-1",
            "sku_code": "SKU-A",
            "po_created_at": "2026-06-01",
            "actual_received_at": "2026-06-11",
            "actual_received_qty": 1,
        },
        {
            "po_number": "PO-2",
            "sku_code": "SKU-B",
            "po_created_at": "2026-06-01",
            "actual_received_at": "2026-06-21",
            "actual_received_qty": 10000,
        },
    ]

    result = aggregate_hq_po_sku_lead_time_rows(rows, as_of="2026-08-04")

    assert result.sample_size == 2
    assert result.mean_days == 15
    assert result.stdev_days == pytest.approx(math.sqrt(50))


def test_hq_lead_time_fails_closed_below_two_valid_po_sku_receipts() -> None:
    with pytest.raises(ValueError, match="at least two valid observations"):
        aggregate_hq_po_sku_lead_time_rows(
            [
                {
                    "po_number": "PO-1",
                    "sku_code": "SKU-A",
                    "po_created_at": "2026-06-01",
                    "actual_received_at": "2026-06-11",
                },
                {
                    "po_number": "PO-BAD",
                    "sku_code": "SKU-B",
                    "po_created_at": "2026-06-12",
                    "actual_received_at": "2026-06-11",
                },
            ],
            as_of="2026-08-04",
        )


def _row(
    packing: str | None,
    mode: str,
    days: int,
    *,
    shipped: str = "2026-06-01",
    completed: str = "2026-06-10",
) -> dict[str, object]:
    return {
        "pckg_no": packing,
        "transport_mode": mode,
        "ow_dt": shipped,
        "iw_dt": completed,
        "ow_to_iw_days": days,
    }


def test_lead_time_query_looks_back_twelve_calendar_months_plus_180_days() -> None:
    completion_from, completion_to, api_from = lead_time_query_window("2026-08-04")

    assert completion_from == date(2025, 8, 4)
    assert completion_to == date(2026, 8, 4)
    assert (completion_from - api_from).days == 180


def test_lead_time_aggregation_uses_unique_consistent_packings_and_stdev_s() -> None:
    rows = [
        _row("AIR-1", "항공", 5),
        _row("AIR-1", "항공", 5),  # product-level duplicate in one packing
        _row("AIR-2", "AIR", 7),
        _row("SEA-1", "해운", 20),
        _row("SEA-2", "SEA", 24),
        _row(None, "항공", 9),
        _row("BAD-0", "항공", 0),
        _row("CONFLICT", "항공", 8),
        _row("CONFLICT", "항공", 9),
        _row("OLD", "항공", 10, completed="2025-07-31"),
    ]

    result = aggregate_lead_time_rows(rows, as_of="2026-08-04")

    assert result.fetched_row_count == 10
    assert result.completed_row_count == 9
    assert result.packing_count == 4
    assert result.excluded_missing_packing_rows == 1
    assert result.excluded_invalid_rows == 1
    assert result.excluded_conflicting_packings == 1
    assert result.modes["AIR"].sample_size == 2
    assert result.modes["AIR"].mean_days == 6
    assert result.modes["AIR"].stdev_days == pytest.approx(math.sqrt(2))
    assert result.modes["AIR"].sigma_weeks == pytest.approx(math.sqrt(2) / 7)
    assert result.modes["SEA"].sample_size == 2
    assert result.modes["SEA"].mean_days == 22


def test_lead_time_aggregation_fails_closed_when_a_mode_has_less_than_two_samples() -> None:
    with pytest.raises(ValueError, match="SEA completed packing sample"):
        aggregate_lead_time_rows(
            [
                _row("AIR-1", "AIR", 5),
                _row("AIR-2", "AIR", 7),
                _row("SEA-1", "SEA", 20),
            ],
            as_of="2026-08-04",
        )


def test_lead_time_response_hash_is_independent_of_api_row_order() -> None:
    rows = [
        _row("AIR-1", "AIR", 5),
        _row("AIR-2", "AIR", 7),
        _row("SEA-1", "SEA", 20),
        _row("SEA-2", "SEA", 24),
    ]

    first = aggregate_lead_time_rows(rows, as_of="2026-08-04")
    second = aggregate_lead_time_rows(reversed(rows), as_of="2026-08-04")

    assert first.response_hash == second.response_hash


def test_lead_time_aggregation_supports_rail_mode_for_eu() -> None:
    rows = [
        _row("RAIL-1", "철송", 30),
        _row("RAIL-2", "RAIL", 40),
        _row("SEA-1", "해운", 70),
        _row("SEA-2", "SEA", 74),
        # AIR rows are ignored when RAIL/SEA are the required modes.
        _row("AIR-1", "항공", 5),
    ]

    result = aggregate_lead_time_rows(
        rows,
        as_of="2026-08-04",
        required_modes=("RAIL", "SEA"),
    )

    assert set(result.modes) == {"RAIL", "SEA"}
    assert result.modes["RAIL"].sample_size == 2
    assert result.modes["RAIL"].mean_days == 35
    assert result.modes["SEA"].sample_size == 2
    assert result.modes["SEA"].mean_days == 72


def test_lead_time_rail_requirement_fails_closed_without_two_samples() -> None:
    with pytest.raises(ValueError, match="RAIL completed packing sample"):
        aggregate_lead_time_rows(
            [
                _row("RAIL-1", "RAIL", 30),
                _row("SEA-1", "SEA", 70),
                _row("SEA-2", "SEA", 74),
            ],
            as_of="2026-08-04",
            required_modes=("RAIL", "SEA"),
        )
