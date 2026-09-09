from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.services.order_logic_v2_source import (
    COMPLETED_WEEK_COUNT,
    build_order_logic_inventory_position_source,
    build_order_logic_v2_source,
    completed_week_window,
)
from core.order_logic_v2 import OrderLogicConfig


def test_completed_week_window_uses_previous_monday_sunday_weeks() -> None:
    window = completed_week_window("2026-07-27")

    assert window.period_start == date(2026, 4, 27)
    assert window.period_end == date(2026, 7, 26)
    assert len(window.week_starts) == COMPLETED_WEEK_COUNT
    assert window.week_starts[0] == window.period_start
    assert window.week_starts[-1] == date(2026, 7, 20)


def _raw_source() -> dict[str, list[dict[str, object]]]:
    start = date(2026, 4, 27)
    sales = [
        {
            "prod_cd": "SKU-A",
            "prod_nm": "상품 A",
            "brand_nm": "브랜드",
            "qty": index + 1,
            "amount_krw_actual": (index + 1) * 1000,
            "ship_dt": (start + timedelta(weeks=index)).isoformat(),
        }
        for index in range(COMPLETED_WEEK_COUNT)
    ]
    return {
        "stock_local": [
            {
                "prod_cd": "SKU-A",
                "prod_nm": "상품 A",
                "brand_nm": "브랜드",
                "bar_code": "8800000000001",
                "avbl_qty": 7,
                "stock_ucost": 2.5,
                "unit_cost_krw": 4_000.0,
            },
            {
                "prod_cd": "SKU-ZERO",
                "prod_nm": "무판매 상품",
                "brand_nm": "브랜드",
                "avbl_qty": 2,
                "stock_ucost": None,
            },
        ],
        "stock_hq": [{"prod_cd": "SKU-A", "avbl_qty": 3}],
        "sales_local": sales,
        "sales_hq": [],
        "shipping": [
            {
                "prod_cd": "SKU-A",
                "qty": 4,
                "eta_dt": "2026-08-10",
                "cust_nm": "SKO Sp. z o.o.",
            }
        ],
        "open_po": [
            {
                "prod_cd": "SKU-A",
                "open_qty": 5,
                "pnfm_qty": 2,
                "pnfm_confirmed_qty": 2,
                "inbound_in_progress_qty": 3,
                "completed_qty": 10,
            }
        ],
    }


def test_build_source_aggregates_inventory_and_marks_absent_sales_as_insufficient() -> None:
    prepared = build_order_logic_v2_source(_raw_source(), as_of="2026-07-27")
    by_sku = {str(row["sku_code"]): row for row in prepared.rows}

    sku = by_sku["SKU-A"]
    assert sku["weekly_sales"] == [float(value) for value in range(1, 14)]
    assert sku["open_qty"] == 5
    assert sku["inbound_status_source_present"] is True
    assert sku["incoming_qty"] == 10
    assert sku["pnfm_qty"] == 2
    assert sku["inbound_progress_qty"] == 3
    assert sku["inbound_completed_qty"] == 10
    assert sku["eu_available_qty"] == 3
    assert sku["transit_qty"] == 4
    assert sku["local_available_qty"] == 7
    assert sku["next_eta"] == "2026-08-10"
    assert sku["next_eta_status"] == "원천 ETA"
    assert sku["barcode"] == "8800000000001"
    assert sku["sales_13w_qty"] == sum(range(1, 14))
    assert sku["shipping_schedule"] == [{"eta": "2026-08-10", "qty": 4.0}]
    assert sku["eta_actual_qty"] == 4
    assert sku["eta_estimated_qty"] == 0
    assert sku["eta_missing_qty"] == 0
    assert sku["unit_price_local"] == 2.5
    assert sku["unit_price_eur"] == 2.5

    assert by_sku["SKU-ZERO"]["weekly_sales"] is None
    assert by_sku["SKU-ZERO"]["inbound_status_source_present"] is False
    assert by_sku["SKU-ZERO"]["sales_13w_qty"] == 0
    assert "HQ_STOCK_MISSING" in by_sku["SKU-ZERO"]["warnings"]
    assert by_sku["SKU-ZERO"]["unit_price_eur"] is None
    assert prepared.period_start.isoformat() == "2026-04-27"
    assert prepared.period_end.isoformat() == "2026-07-26"


def test_inventory_position_adapter_matches_v2_ip_operands_without_sales_detail() -> None:
    raw = _raw_source()
    v2_rows = {
        str(row["sku_code"]): row
        for row in build_order_logic_v2_source(raw, as_of="2026-07-27").rows
    }

    # V3 receives its demand from the dedicated 24-month source.  This adapter
    # must therefore keep the V2-approved IP mapping while accepting a raw
    # snapshot with no V2 sales detail at all.
    inventory_raw = dict(raw)
    inventory_raw.pop("sales_local")
    inventory_raw.pop("sales_hq")
    inventory_rows = {
        str(row["sku_code"]): row
        for row in build_order_logic_inventory_position_source(
            inventory_raw,
            entity_code="PL",
        ).rows
    }

    fields = (
        "inbound_status_source_present",
        "open_qty",
        "incoming_qty",
        "pnfm_qty",
        "inbound_progress_qty",
        "inbound_completed_qty",
        "eu_available_qty",
        "transit_qty",
        "local_available_qty",
        "unit_price_local",
        "unit_price_krw",
    )
    assert inventory_rows.keys() <= v2_rows.keys()
    for sku_code, inventory_row in inventory_rows.items():
        for field in fields:
            assert inventory_row[field] == v2_rows[sku_code][field]


def test_pl_uses_open_po_123_and_only_sko_shipping_for_ip_and_eta() -> None:
    raw = _raw_source()
    raw["shipping"] = [
        {
            "prod_cd": "SKU-A",
            "qty": 4,
            "eta_dt": "2026-08-10",
            "cust_nm": "SKO Sp. z o.o.",
        },
        {
            "prod_cd": "SKU-A",
            "qty": 6,
            "eta_dt": "2026-08-03",
            "cust_nm": "STYLEKOREAN UK LIMITED",
        },
        {
            "prod_cd": "SKU-A",
            "qty": 8,
            "eta_dt": "2026-08-01",
            "cust_nm": None,
        },
    ]

    prepared = build_order_logic_v2_source(raw, as_of="2026-07-27")
    sku = next(row for row in prepared.rows if row["sku_code"] == "SKU-A")

    assert sku["incoming_qty"] == 10
    assert sku["transit_qty"] == 4
    assert (
        sku["incoming_qty"]
        + sku["eu_available_qty"]
        + sku["transit_qty"]
        + sku["local_available_qty"]
    ) == 24
    assert sku["next_eta"] == "2026-08-10"
    assert sku["shipping_schedule"] == [{"eta": "2026-08-10", "qty": 4.0}]
    assert prepared.source_counts["shipping"] == 1


def test_usa_uses_open_po_123_and_actual_shipping_quantity_for_ip() -> None:
    raw = _raw_source()
    raw["shipping"] = [
        {
            "prod_cd": "SKU-A",
            "qty": 40,
            "eta_dt": "2026-08-10",
            "cust_nm": "USA destination",
        }
    ]
    raw["open_po"] = [
        {
            "prod_cd": "SKU-A",
            "open_qty": 5,
            "pnfm_qty": 90,
            "pnfm_confirmed_qty": 20,
            "inbound_in_progress_qty": 30,
            "completed_qty": 10,
        }
    ]

    prepared = build_order_logic_v2_source(
        raw,
        as_of="2026-07-27",
        entity_code="USA",
    )
    sku = next(row for row in prepared.rows if row["sku_code"] == "SKU-A")

    assert sku["open_qty"] == 5
    assert sku["incoming_qty"] == 55
    assert sku["pnfm_qty"] == 20
    assert sku["inbound_progress_qty"] == 30
    assert sku["inbound_completed_qty"] == 10
    assert sku["transit_qty"] == 40
    assert sku["shipping_schedule"] == [{"eta": "2026-08-10", "qty": 40.0}]
    assert (
        sku["incoming_qty"]
        + sku["eu_available_qty"]
        + sku["transit_qty"]
        + sku["local_available_qty"]
    ) == 105


def test_build_source_fails_closed_for_missing_endpoint_or_revenue_field() -> None:
    raw = _raw_source()
    raw.pop("stock_hq")
    with pytest.raises(ValueError, match="stock_hq"):
        build_order_logic_v2_source(raw, as_of="2026-07-27")

    raw = _raw_source()
    for row in raw["sales_local"]:
        row.pop("amount_krw_actual")
    with pytest.raises(ValueError, match="amount_krw_actual"):
        build_order_logic_v2_source(raw, as_of="2026-07-27")


def test_build_source_fails_closed_for_null_population_revenue() -> None:
    raw = _raw_source()
    raw["sales_local"][0]["amount_krw_actual"] = None
    with pytest.raises(ValueError, match="실제 원화 매출"):
        build_order_logic_v2_source(raw, as_of="2026-07-27")


def test_build_source_fails_closed_for_old_open_po_status_contract() -> None:
    raw = _raw_source()
    for row in raw["open_po"]:
        row.pop("pnfm_confirmed_qty")
        row.pop("inbound_in_progress_qty")
        row.pop("completed_qty")

    with pytest.raises(ValueError, match="최신 open-po 상태"):
        build_order_logic_v2_source(raw, as_of="2026-07-27")


def test_build_source_blocks_when_a_completed_week_is_missing_globally() -> None:
    raw = _raw_source()
    raw["sales_local"] = raw["sales_local"][:-1]

    with pytest.raises(ValueError, match="누락 주"):
        build_order_logic_v2_source(raw, as_of="2026-07-27")


def test_null_inventory_is_zero_with_warning_but_negative_is_invalid() -> None:
    raw = _raw_source()
    raw["open_po"] = [
        {
            "prod_cd": "SKU-A",
            "open_qty": None,
            "pnfm_confirmed_qty": 0,
            "inbound_in_progress_qty": 0,
            "completed_qty": 0,
        },
        {
            "prod_cd": "SKU-ZERO",
            "open_qty": -1,
            "pnfm_confirmed_qty": 0,
            "inbound_in_progress_qty": 0,
            "completed_qty": 0,
        },
    ]

    prepared = build_order_logic_v2_source(raw, as_of="2026-07-27")
    by_sku = {str(row["sku_code"]): row for row in prepared.rows}

    assert by_sku["SKU-A"]["incoming_qty"] == 0
    assert "INCOMING_QTY_NULL_AS_ZERO" in by_sku["SKU-A"]["warnings"]
    assert by_sku["SKU-ZERO"]["validation_error"]


def test_next_eta_ignores_zero_quantity_shipping_rows() -> None:
    raw = _raw_source()
    raw["shipping"] = [
        {"prod_cd": "SKU-A", "qty": 0, "eta_dt": "2026-08-01", "cust_nm": "SKO Sp. z o.o."},
        {"prod_cd": "SKU-A", "qty": 4, "eta_dt": "2026-08-10", "cust_nm": "SKO Sp. z o.o."},
    ]

    prepared = build_order_logic_v2_source(raw, as_of="2026-07-27")
    by_sku = {str(row["sku_code"]): row for row in prepared.rows}

    assert by_sku["SKU-A"]["next_eta"] == "2026-08-10"


def test_shipping_without_eta_is_reconciled_without_inventing_a_week() -> None:
    raw = _raw_source()
    raw["shipping"] = [
        {"prod_cd": "SKU-A", "qty": 4, "eta_dt": "2026-08-10", "cust_nm": "SKO Sp. z o.o."},
        {"prod_cd": "SKU-A", "qty": 6, "eta_dt": None, "cust_nm": "SKO Sp. z o.o."},
    ]

    prepared = build_order_logic_v2_source(raw, as_of="2026-07-27")
    by_sku = {str(row["sku_code"]): row for row in prepared.rows}

    assert by_sku["SKU-A"]["transit_qty"] == 10
    assert by_sku["SKU-A"]["shipping_schedule"] == [
        {"eta": "2026-08-10", "qty": 4.0}
    ]
    assert by_sku["SKU-A"]["eta_missing_qty"] == 6


def test_shipping_without_eta_uses_remark_mode_and_v2_lead_time() -> None:
    raw = _raw_source()
    raw["shipping"] = [
        {
            "prod_cd": "SKU-A",
            "qty": 4,
            "eta_dt": None,
            "ship_dt": "2026-07-27",
            "remark": "철송 RAIL",
            "cust_nm": "SKO Sp. z o.o.",
        },
        {
            "prod_cd": "SKU-A",
            "qty": 6,
            "eta_dt": None,
            "ship_dt": "2026-07-27",
            "remark": "해운 SEA",
            "cust_nm": "SKO Sp. z o.o.",
        },
        {
            "prod_cd": "SKU-A",
            "qty": 2,
            "eta_dt": None,
            "ship_dt": "2026-07-27",
            "remark": "운송수단 확인",
            "cust_nm": "SKO Sp. z o.o.",
        },
    ]
    config = OrderLogicConfig(
        lt_air_days=9.5,
        lt_rail_days=14.0,
        lt_sea_days=21.0,
    )

    prepared = build_order_logic_v2_source(
        raw,
        as_of="2026-07-27",
        config=config,
    )
    sku = next(row for row in prepared.rows if row["sku_code"] == "SKU-A")

    assert sku["shipping_schedule"] == [
        {"eta": "2026-08-10", "qty": 4.0},
        {"eta": "2026-08-17", "qty": 6.0},
    ]
    assert sku["eta_actual_qty"] == 0
    assert sku["eta_estimated_qty"] == 10
    assert sku["eta_missing_qty"] == 2
    assert sku["next_eta_status"] == "출고일 추정 ETA"
    assert [item["eta_status"] for item in sku["shipping_eta_details"]] == [
        "출고일 추정 ETA",
        "출고일 추정 ETA",
        "ETA 미확인",
    ]
    assert [item["transport_mode"] for item in sku["shipping_eta_details"]] == [
        "RAIL",
        "SEA",
        None,
    ]


def test_default_v2_transport_lead_times_drive_estimated_eta_dates() -> None:
    raw = _raw_source()
    raw["shipping"] = [
        {
            "prod_cd": "SKU-A",
            "qty": 1,
            "ship_dt": "2026-07-27",
            "remark": remark,
            "cust_nm": "SKO Sp. z o.o.",
        }
        for remark in ("항공 AIR", "철송 RAIL", "해운 SEA")
    ]

    prepared = build_order_logic_v2_source(raw, as_of="2026-07-27")
    sku = next(row for row in prepared.rows if row["sku_code"] == "SKU-A")

    assert sku["shipping_schedule"] == [
        {"eta": "2026-08-12", "qty": 1.0},
        {"eta": "2026-09-01", "qty": 1.0},
        {"eta": "2026-10-07", "qty": 1.0},
    ]
    assert [
        item["lead_time_days"] for item in sku["shipping_eta_details"]
    ] == [16.4, 36.6, 72.9]


def test_actual_eta_wins_even_when_transport_mode_is_unknown() -> None:
    raw = _raw_source()
    raw["shipping"] = [
        {
            "prod_cd": "SKU-A",
            "qty": 7,
            "eta_dt": "2026-08-05",
            "ship_dt": "2026-07-27",
            "remark": "운송수단 확인",
            "cust_nm": "SKO Sp. z o.o.",
        }
    ]

    prepared = build_order_logic_v2_source(raw, as_of="2026-07-27")
    sku = next(row for row in prepared.rows if row["sku_code"] == "SKU-A")

    assert sku["shipping_schedule"] == [
        {"eta": "2026-08-05", "qty": 7.0}
    ]
    assert sku["eta_actual_qty"] == 7
    assert sku["eta_estimated_qty"] == 0
    assert sku["eta_missing_qty"] == 0
    assert sku["shipping_eta_details"][0]["eta_status"] == "원천 ETA"
    assert sku["shipping_eta_details"][0]["lead_time_days"] is None
    assert sku["next_eta_status"] == "원천 ETA"


def test_delivery_charge_is_excluded_from_order_items() -> None:
    raw = _raw_source()
    raw["stock_local"].append(
        {
            "prod_cd": "Delivery Charge",
            "prod_nm": "Delivery Charge",
            "avbl_qty": 0,
        }
    )
    raw["sales_local"].extend(
        {
            "prod_cd": "Delivery Charge",
            "prod_nm": "Delivery Charge",
            "qty": 1,
            "amount_krw_actual": 0,
            "ship_dt": (date(2026, 4, 27) + timedelta(weeks=index)).isoformat(),
        }
        for index in range(COMPLETED_WEEK_COUNT)
    )

    prepared = build_order_logic_v2_source(raw, as_of="2026-07-27")

    assert "Delivery Charge" not in {
        str(row["sku_code"]) for row in prepared.rows
    }


def _raw_source_with_biz(entity_code: str) -> dict[str, list[dict[str, object]]]:
    start = date(2026, 4, 27)
    net_biz = "US-DOMESTIC" if entity_code == "USA" else "EU-OVERSEAS"
    excluded_biz = "US-STAFF" if entity_code == "USA" else "EU-STAFFSALES"

    def week(index: int) -> str:
        return (start + timedelta(weeks=index)).isoformat()

    sales: list[dict[str, object]] = []
    # SKU-A: clean 13-week positive sales.
    for index in range(COMPLETED_WEEK_COUNT):
        sales.append(
            {
                "prod_cd": "SKU-A",
                "qty": index + 1,
                "amount": (index + 1) * 10.0,
                "amount_krw_actual": (index + 1) * 1000,
                "ship_dt": week(index),
                "biz_type": net_biz,
            }
        )
    # SKU-B: positive sales plus one negative amount row inside the same net
    # sales biz type; the per-SKU revenue sum stays positive.
    for index in range(COMPLETED_WEEK_COUNT):
        sales.append(
            {
                "prod_cd": "SKU-B",
                "qty": index + 1,
                "amount": (index + 1) * 10.0,
                "amount_krw_actual": (index + 1) * 1000,
                "ship_dt": week(index),
                "biz_type": net_biz,
            }
        )
    sales.append(
        {
            "prod_cd": "SKU-B",
            "qty": 3,
            "amount": -50.0,
            "amount_krw_actual": -5000,
            "ship_dt": week(5),
            "biz_type": net_biz,
        }
    )
    # SKU-C: an excluded biz type (staff/return); must not reach demand.
    sales.append(
        {
            "prod_cd": "SKU-C",
            "qty": 2,
            "amount": 100.0,
            "amount_krw_actual": 10000,
            "ship_dt": week(2),
            "biz_type": excluded_biz,
        }
    )
    # SKU-D: residual-negative revenue sum; isolated, not a global abort.
    sales.append(
        {
            "prod_cd": "SKU-D",
            "qty": 1,
            "amount": 10.0,
            "amount_krw_actual": 1000,
            "ship_dt": week(1),
            "biz_type": net_biz,
        }
    )
    sales.append(
        {
            "prod_cd": "SKU-D",
            "qty": 1,
            "amount": -999.0,
            "amount_krw_actual": -99900,
            "ship_dt": week(1),
            "biz_type": net_biz,
        }
    )
    return {
        "stock_local": [
            {"prod_cd": "SKU-A", "avbl_qty": 7, "stock_ucost": 2.5, "unit_cost_krw": 4_000.0},
            {"prod_cd": "SKU-B", "avbl_qty": 5, "stock_ucost": 3.0, "unit_cost_krw": 4_800.0},
        ],
        "stock_hq": [{"prod_cd": "SKU-A", "avbl_qty": 3}],
        "sales_local": sales,
        "sales_hq": [],
        "shipping": [
            {
                "prod_cd": "SKU-A",
                "qty": 4,
                "eta_dt": "2026-08-10",
                "cust_nm": "SKO Sp. z o.o.",
            }
        ],
        "open_po": [
            {
                "prod_cd": "SKU-A",
                "open_qty": 5,
                "pnfm_confirmed_qty": 0,
                "inbound_in_progress_qty": 0,
                "completed_qty": 0,
            }
        ],
    }


@pytest.mark.parametrize("entity_code", ["USA", "PL"])
def test_v1_biz_type_filter_and_revenue_net_off(entity_code: str) -> None:
    prepared = build_order_logic_v2_source(
        _raw_source_with_biz(entity_code),
        as_of="2026-07-27",
        entity_code=entity_code,
    )
    by_sku = {str(row["sku_code"]): row for row in prepared.rows}

    # Excluded biz type never enters the population.
    assert "SKU-C" not in by_sku

    # Clean SKU is unaffected.
    assert by_sku["SKU-A"]["validation_error"] is None

    # All PL/USA demand paths treat a negative-amount, positive-quantity row as
    # an incident adjustment rather than physical demand.
    sku_b = by_sku["SKU-B"]
    assert sku_b["validation_error"] is None
    if entity_code == "PL":
        assert sku_b["revenue"] == pytest.approx(91000.0)
        assert sku_b["weekly_sales"][5] == 6.0
        assert "NEGATIVE_AMOUNT_POSITIVE_QTY_EXCLUDED" in sku_b["warnings"]
        assert prepared.source_counts["sales_demand_excluded_rows"] == 2
        exclusion = prepared.source_audit["sales_demand_exclusion"]
        assert exclusion["sales_demand_excluded_qty"] == 4
        assert exclusion["sales_demand_excluded_amount"] == -104900
    else:
        assert sku_b["revenue"] == pytest.approx(91000.0)
        assert sku_b["weekly_sales"][5] == 6.0
        assert "NEGATIVE_AMOUNT_POSITIVE_QTY_EXCLUDED" in sku_b["warnings"]
        assert prepared.source_counts["sales_demand_excluded_rows"] == 2
        exclusion = prepared.source_audit["sales_demand_exclusion"]
        assert exclusion["sales_demand_excluded_qty"] == 4
        assert exclusion["sales_demand_excluded_amount"] == -104900

    sku_d = by_sku["SKU-D"]
    # Excluding the incident amount leaves a positive graded revenue, so the
    # SKU is no longer isolated for residual-negative review.
    assert sku_d["validation_error"] is None
    assert sku_d["revenue"] == pytest.approx(1000.0)
    assert sku_d["weekly_sales"][1] == 1.0
    assert "SALES_REVENUE_NET_NEGATIVE" not in sku_d["warnings"]


def test_pl_v2_includes_kr_overseas_in_sales_population() -> None:
    raw = _raw_source_with_biz("PL")
    raw["sales_local"].append(
        {
            "prod_cd": "SKU-A",
            "qty": 8,
            "amount": 80.0,
            "amount_krw_actual": 8000,
            "ship_dt": "2026-05-04",
            "biz_type": "KR-OVERSEAS",
        }
    )

    prepared = build_order_logic_v2_source(
        raw,
        as_of="2026-07-27",
        entity_code="PL",
    )
    sku_a = next(row for row in prepared.rows if row["sku_code"] == "SKU-A")

    assert sum(sku_a["weekly_sales"]) == 99.0


def test_usa_v2_includes_kr_overseas_and_intercompany_in_sales_population() -> None:
    raw = _raw_source_with_biz("USA")
    raw["sales_local"].extend(
        [
            {
                "prod_cd": "SKU-A",
                "qty": 8,
                "amount": 80.0,
                "amount_krw_actual": 8000,
                "ship_dt": "2026-05-04",
                "biz_type": "KR-OVERSEAS",
            },
            {
                "prod_cd": "SKU-A",
                "qty": 4,
                "amount": 40.0,
                "amount_krw_actual": 4000,
                "ship_dt": "2026-05-11",
                "biz_type": "자사간거래",
            },
        ]
    )

    prepared = build_order_logic_v2_source(
        raw,
        as_of="2026-07-27",
        entity_code="USA",
    )
    sku_a = next(row for row in prepared.rows if row["sku_code"] == "SKU-A")

    assert sum(sku_a["weekly_sales"]) == 103.0


def test_sku_absent_from_both_stock_masters_is_flagged_check_required() -> None:
    raw = _raw_source()
    # A SKU present only in shipping/open-po (non-stock sources), absent from
    # both local and HQ stock masters.
    raw["shipping"].append(
        {
            "prod_cd": "SKU-GHOST",
            "qty": 5,
            "eta_dt": "2026-08-12",
            "cust_nm": "SKO Sp. z o.o.",
        }
    )
    raw["open_po"].append({"prod_cd": "SKU-GHOST", "open_qty": 3})

    prepared = build_order_logic_v2_source(raw, as_of="2026-07-27")
    by_sku = {str(row["sku_code"]): row for row in prepared.rows}

    ghost = by_sku["SKU-GHOST"]
    assert ghost["check_required"] is True
    assert ghost["check_required_reason"]
    assert "MASTER_STOCK_UNREGISTERED" in ghost["warnings"]

    # A SKU that exists in the stock masters must NOT be flagged.
    assert by_sku["SKU-A"]["check_required"] is False
    assert by_sku["SKU-A"]["check_required_reason"] is None
