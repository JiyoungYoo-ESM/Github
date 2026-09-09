"""PL/USA V3 shipment references using the approved V2 ETA resolver.

Only ETA is shared. V3 inventory, demand and replenishment remain independent.
"""

from dataclasses import replace
from math import isfinite
from typing import Mapping

from backend.cms_mapping import _shipping_frame
from backend.services.order_logic_v2_source import (
    _frame_rows, _shipping_rows_for_entity, _shipping_schedule_by_sku,
)
from core.order_logic_v2 import DEFAULT_CONFIG, OrderLogicConfig


def _v2_eta_config(
    entity_code: str, lead_time_audit: Mapping[str, object],
) -> OrderLogicConfig | None:
    """Use the same measured means as V2, retaining its unmeasured-mode defaults.

    V3 already fetched these measurements for its policies. Do not query them
    again or replace missing mandatory measurements with the V2 defaults.
    """
    means: dict[str, float] = {}
    def _record(mode: object, value: object) -> None:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) and value > 0:
            means[str(mode)] = float(value)

    for policy in dict(lead_time_audit.get("scenarios") or {}).values():
        _record(policy.get("transport_mode"), policy.get("lead_time_days"))
    # PL orders both scenarios by RAIL since 2026-09-08, so the SEA measurement
    # only appears in the aggregation source. ETA still follows the invoice
    # remark's actual mode, which keeps requiring the measured SEA mean.
    source = lead_time_audit.get("source")
    modes = source.get("modes") if isinstance(source, Mapping) else None
    for mode, stats in dict(modes or {}).items():
        if isinstance(stats, Mapping):
            _record(mode, stats.get("mean_days"))
    required = {"PL": {"RAIL", "SEA"}, "USA": {"AIR", "SEA"}}[entity_code]
    if not required.issubset(means):
        return None
    fields = {"AIR": "lt_air_days", "RAIL": "lt_rail_days", "SEA": "lt_sea_days"}
    return replace(DEFAULT_CONFIG, **{fields[mode]: means[mode] for mode in required})


def build_shipping_reference_source(
    raw: Mapping[str, object], *, entity_code: str, lead_time_audit: Mapping[str, object],
) -> tuple[dict[str, list[dict[str, object]]], set[str], str]:
    if entity_code == "HQ":
        # HQ's approved IP excludes the international shipping feed.
        return {}, set(), "NOT_APPLICABLE"
    raw_rows = raw.get("shipping")
    if not isinstance(raw_rows, list):
        return {}, set(), "UNAVAILABLE"
    selected = _shipping_rows_for_entity(raw_rows, entity_code=entity_code)
    frame = _shipping_frame(selected, entity_code=entity_code, lead_time_rows=raw.get("lead_time"))
    invalid: set[str] = set()
    has_positive_quantity = False
    for sku, _row, qty in _frame_rows(frame, sku_column="상품코드", quantity_column="수량"):
        if qty is None or qty < 0:
            invalid.add(sku)
        elif qty > 0:
            has_positive_quantity = True
    if not has_positive_quantity:
        return {}, invalid, "AVAILABLE"
    config = _v2_eta_config(entity_code, lead_time_audit)
    if config is None:
        return {}, invalid, "UNAVAILABLE"
    # V2 uses the Invoice remark's mode for date estimation, not the mapped
    # transport column or the currently selected order scenario. Its resolver
    # also owns explicit/USA-remark ETA priority and calendar-date conversion.
    summary = _shipping_schedule_by_sku(frame, config=config, entity_code=entity_code)
    keys = ("eta", "qty", "eta_status", "ship_date", "transport_mode", "lead_time_days")
    details = {
        sku: [{key: item[key] for key in keys} for item in items]
        for sku, items in summary.details.items()
    }
    return details, invalid, "AVAILABLE"
