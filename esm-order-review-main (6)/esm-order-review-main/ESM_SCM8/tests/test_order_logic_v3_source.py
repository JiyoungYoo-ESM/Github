from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.services import order_logic_v3_source
from core.order_logic_v3 import INVENTORY_POLICY_SHORTAGE, V3ReplenishmentPolicy
from core.season_calendar import AMOUNT_COL, DATE_COL, PRODUCT_CODE_COL


def test_product_pack_quantities_maps_inbox_and_outbox_and_ignores_invalid():
    rows = [
        {"prod_cd": "SKU-A", "inbox_cnt": 20, "outbox_cnt": 160},
        {"prod_cd": "SKU-B", "inbox_cnt": None, "outbox_cnt": None},
        {"prod_cd": "SKU-C", "inbox_cnt": 0, "outbox_cnt": -4},
        {"prod_cd": "SKU-D", "inbox_cnt": "24", "outbox_cnt": "abc"},
        {"prod_cd": "SKU-E.0", "inbox_cnt": 6, "outbox_cnt": 36},
        {"prod_cd": "", "inbox_cnt": 5, "outbox_cnt": 50},
    ]
    packs = order_logic_v3_source._product_pack_quantities(rows, entity_code="PL")
    assert packs["SKU-A"] == (20.0, 160.0)
    assert packs["SKU-B"] == (None, None)
    # Zero and negative pack sizes are unset, matching the CMS null policy.
    assert packs["SKU-C"] == (None, None)
    assert packs["SKU-D"] == (24.0, None)
    # V3 preserves the .0 code suffix in its master identity policy.
    assert packs["SKU-E.0"] == (6.0, 36.0)
    assert "" not in packs


def test_usa_pack_quantities_use_only_the_us_specific_inbox():
    # User decision 2026-09-08: real USA packs differ in both directions
    # (1->6, 50->5), so shared inbox_cnt is never a USA substitute.
    rows = [
        {"prod_cd": "SNC08-GP", "inbox_cnt": 50, "inbox_cnt_usa": 5, "outbox_cnt": 160},
        {"prod_cd": "ECM96-Cr", "inbox_cnt": 1, "inbox_cnt_usa": 6, "outbox_cnt": None},
        {"prod_cd": "NO-USA", "inbox_cnt": 10, "inbox_cnt_usa": None, "outbox_cnt": 36},
    ]
    usa = order_logic_v3_source._product_pack_quantities(rows, entity_code="USA")
    assert usa["SNC08-GP"] == (5.0, 160.0)
    assert usa["ECM96-Cr"] == (6.0, None)
    # Missing USA inbox falls through to the ladder's 10-unit step, not inbox_cnt.
    assert usa["NO-USA"] == (None, 36.0)
    for entity in ("HQ", "PL"):
        shared = order_logic_v3_source._product_pack_quantities(rows, entity_code=entity)
        assert shared["SNC08-GP"] == (50.0, 160.0)
        assert shared["ECM96-Cr"] == (1.0, None)
        assert shared["NO-USA"] == (10.0, 36.0)


def test_hq_inventory_validation_does_not_import_v2_demand_errors():
    error, warnings = order_logic_v3_source._inventory_validation_state({
        "validation_error": "Synthetic shared V2 error",
        "warnings": ["SALES_QTY_NEGATIVE", "INCOMING_QTY_NULL_AS_ZERO"],
    }, entity_code="HQ")
    assert error is None
    assert warnings == ("INCOMING_QTY_NULL_AS_ZERO",)
    error, warnings = order_logic_v3_source._inventory_validation_state({
        "validation_error": "Synthetic shared V2 error",
        "warnings": ["SALES_QTY_NEGATIVE", "INCOMING_QTY_NEGATIVE"],
    }, entity_code="HQ")
    assert error == "Synthetic shared V2 error"
    assert warnings == ("INCOMING_QTY_NEGATIVE",)


@pytest.mark.parametrize("entity", ["PL", "USA"])
def test_missing_open_po_row_is_not_fabricated_as_null_warning(entity):
    rows, _, _ = order_logic_v3_source._inventory_rows({
        "stock_local": [{"prod_cd": "SYNTHETIC", "avbl_qty": 100}],
        "stock_hq": [{"prod_cd": "SYNTHETIC", "avbl_qty": 0}],
        "shipping": [], "open_po": [], "sales_local": [], "sales_hq": [],
    }, as_of="2026-08-31", entity_code=entity)
    row = rows["SYNTHETIC"]
    assert row["inbound_status_source_present"] is False
    assert row["incoming_qty"] == 0
    assert row["pnfm_qty"] is row["inbound_progress_qty"] is row["inbound_completed_qty"] is None
    assert order_logic_v3_source._inventory_validation_state(row, entity_code=entity) == (None, ())


@pytest.mark.parametrize("entity", ["PL", "USA"])
@pytest.mark.parametrize("qty", [0, 10, None])
def test_inbound_source_presence_does_not_depend_on_quantity(entity, qty):
    rows, _, _ = order_logic_v3_source._inventory_rows({
        "stock_local": [{"prod_cd": "SYNTHETIC", "avbl_qty": 100}],
        "stock_hq": [{"prod_cd": "SYNTHETIC", "avbl_qty": 0}],
        "shipping": [], "sales_local": [], "sales_hq": [],
        "open_po": [{"prod_cd": "SYNTHETIC", "open_qty": qty,
                     "pnfm_confirmed_qty": qty, "inbound_in_progress_qty": qty,
                     "completed_qty": qty}],
    }, as_of="2026-08-31", entity_code=entity)
    assert rows["SYNTHETIC"]["inbound_status_source_present"] is True
    assert rows["SYNTHETIC"]["incoming_qty"] == (qty or 0) * 3


def test_v3_seasonal_window_ends_before_the_sales_cutoff_month() -> None:
    start, end, months = order_logic_v3_source.completed_month_window(date(2026, 8, 23))

    assert start == date(2024, 8, 1)
    assert end == date(2026, 7, 31)
    assert months[0] == date(2024, 8, 1)
    assert months[-1] == date(2026, 7, 1)
    assert len(months) == 24


def test_missing_function_class_2_uses_same_entity_function_class_1_factor() -> None:
    months = tuple(
        month.date() for month in pd.date_range("2024-08-01", periods=24, freq="MS")
    )
    rows: list[dict[str, object]] = []
    for month in months:
        rows.extend(
            [
                {
                    order_logic_v3_source.PRODUCT_CODE_COL: "SKU-CLASS2",
                    order_logic_v3_source.PRODUCT_NAME_COL: "분류된 선케어",
                    order_logic_v3_source.BRAND_COL: "TEST",
                    order_logic_v3_source.DATE_COL: pd.Timestamp(month),
                    order_logic_v3_source.CATEGORY1_COL: "선케어",
                    order_logic_v3_source.CATEGORY2_COL: "자외선차단",
                    order_logic_v3_source.QTY_COL: 40.0 if month.month == 7 else 10.0,
                },
                {
                    order_logic_v3_source.PRODUCT_CODE_COL: "SKU-MISSING-CLASS2",
                    order_logic_v3_source.PRODUCT_NAME_COL: "미분류 선케어",
                    order_logic_v3_source.BRAND_COL: "TEST",
                    order_logic_v3_source.DATE_COL: pd.Timestamp(month),
                    order_logic_v3_source.CATEGORY1_COL: "선케어",
                    order_logic_v3_source.CATEGORY2_COL: order_logic_v3_source.UNMAPPED,
                    order_logic_v3_source.QTY_COL: 10.0,
                },
            ]
        )

    catalog = order_logic_v3_source._profiles(
        pd.DataFrame(rows),
        months,
        entity_code="USA",
    )
    selection = order_logic_v3_source._select_seasonal_profile(
        catalog,
        entity_code="USA",
        function_class_1_code="선케어",
        function_class_2_code=order_logic_v3_source.UNMAPPED,
    )

    assert ("선케어", order_logic_v3_source.UNMAPPED) not in catalog.by_class_1_and_2
    assert selection.profile == catalog.by_class_1["선케어"]
    assert selection.profile.entity_code == "USA"
    assert selection.scope == order_logic_v3_source.SEASON_FACTOR_SCOPE_CLASS_1
    assert (
        selection.application_reason_code
        == order_logic_v3_source.CLASS2_MISSING_USE_CLASS1_FACTOR
    )
    assert selection.profile.factors_by_month[7] > selection.profile.factors_by_month[1]


def test_missing_function_class_2_stays_blocked_when_class_1_factor_failed() -> None:
    catalog = order_logic_v3_source._SeasonalProfileCatalog(
        by_class_1_and_2={},
        by_class_1={},
        class_1_and_2_errors={},
        class_1_errors={"선케어": "all-zero monthly sales"},
        identities={},
    )

    selection = order_logic_v3_source._select_seasonal_profile(
        catalog,
        entity_code="USA",
        function_class_1_code="선케어",
        function_class_2_code=order_logic_v3_source.UNMAPPED,
    )

    assert selection.application_reason_code is None
    assert selection.blocking_reason_code == "SEASON_FACTOR_CALC_FAILED"
    assert "기능구분1 팩터를 적용할 수 없습니다" in str(selection.blocking_message)


def test_v3_source_uses_the_earliest_paid_sale_date_returned_by_the_api() -> None:
    demand = pd.DataFrame(
        {
            order_logic_v3_source.PRODUCT_CODE_COL: ["SKU-A", "SKU-A", "SKU-B"],
            order_logic_v3_source.DATE_COL: pd.to_datetime(
                ["2026-08-23", "2026-03-08", "2026-08-22"]
            ),
        }
    )

    first_sale_dates = order_logic_v3_source._first_paid_sale_dates(demand)

    assert first_sale_dates == {
        "SKU-A": date(2026, 3, 8),
        "SKU-B": date(2026, 8, 22),
    }


def test_pl_replenishment_policies_use_v2_completed_packing_measurements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "pckg_no": f"R-{index}",
            "ow_dt": "2026-06-01",
            "iw_dt": f"2026-07-{index + 1:02d}",
            "transport_mode": "RAIL",
            "ow_to_iw_days": 34 + index,
        }
        for index in range(1, 11)
    ] + [
        {
            "pckg_no": f"S-{index}",
            "ow_dt": "2026-05-01",
            "iw_dt": f"2026-07-{index + 10:02d}",
            "transport_mode": "SEA",
            "ow_to_iw_days": 70 + index,
        }
        for index in range(1, 11)
    ]
    captured: dict[str, object] = {}

    def fake_fetch(entity_code: str, **kwargs: object) -> list[dict[str, object]]:
        captured["entity_code"] = entity_code
        captured.update(kwargs)
        return rows

    monkeypatch.setattr(order_logic_v3_source, "fetch_cms_lead_time", fake_fetch)

    cash, shortage, audit = order_logic_v3_source._measured_replenishment_policies(
        as_of=date(2026, 8, 28),
        entity_code="PL",
        hq_lead_time=None,
    )

    assert captured["entity_code"] == "PL"
    assert captured["include_in_transit"] is False
    assert cash.lead_time_days == pytest.approx(39.5)
    assert cash.sigma_lead_time_periods == pytest.approx(3.027650354 / 7.0)
    # 2026-09-08 user decision: PL orders both scenarios by RAIL.
    assert shortage.lead_time_days == pytest.approx(39.5)
    assert shortage.sigma_lead_time_periods == pytest.approx(3.027650354 / 7.0)
    assert cash.review_days == shortage.review_days == 28.0
    assert cash.safety_stock_floor_periods == shortage.safety_stock_floor_periods == 2.0
    # 1 period = 7 calendar days = 1 week, so PL's approved 2~10 week fence.
    assert cash.safety_stock_cap_periods == shortage.safety_stock_cap_periods == 10.0
    assert audit["source"]["completion_months"] == 6  # type: ignore[index]
    assert audit["source"]["minimum_sample_size"] == 10  # type: ignore[index]
    assert audit["scenarios"]["CASH"]["transport_mode"] == "RAIL"  # type: ignore[index]
    assert audit["scenarios"]["SHORTAGE"]["transport_mode"] == "RAIL"  # type: ignore[index]
    # SEA stays measured for the V2-parity ETA resolver of sea shipments.
    assert audit["source"]["modes"]["SEA"]["sample_size"] == 10  # type: ignore[index]
    assert audit["source"]["modes"]["SEA"]["mean_days"] == pytest.approx(75.5)  # type: ignore[index]


def test_hq_replenishment_policies_share_six_month_domestic_lead_time() -> None:
    cash, shortage, audit = order_logic_v3_source._measured_replenishment_policies(
        as_of=date(2026, 8, 28),
        entity_code="HQ",
        hq_lead_time={
            "sample_size": 10,
            "mean_days": 42.5,
            "stdev_days": 3.5,
            "basis": "PO 생성일 → 실입고일",
        },
    )

    assert cash == shortage
    assert cash.lead_time_days == pytest.approx(42.5)
    assert cash.sigma_lead_time_periods == pytest.approx(3.5 / 7.0)
    assert cash.safety_stock_floor_periods == pytest.approx(1.0)
    assert cash.safety_stock_cap_periods == pytest.approx(2.0)
    assert audit["source"]["observation_months"] == 6  # type: ignore[index]
    assert audit["scenarios"]["CASH"]["transport_mode"] == "DOMESTIC_COMMON"  # type: ignore[index]


def test_hq_replenishment_blocks_when_six_month_sample_is_under_ten() -> None:
    with pytest.raises(ValueError, match="10건 미만"):
        order_logic_v3_source._measured_replenishment_policies(
            as_of=date(2026, 8, 28),
            entity_code="HQ",
            hq_lead_time={
                "sample_size": 9,
                "mean_days": 42.5,
                "stdev_days": 3.5,
            },
        )


@pytest.mark.parametrize("inventory_error,inventory_warnings", [
    (None, []),
    (None, ["INCOMING_QTY_NULL_AS_ZERO"]),
    ("Synthetic V2 inventory error", ["INCOMING_QTY_NEGATIVE"]),
])
@pytest.mark.parametrize("inbound_source_present", [True, False, None])
def test_v3_source_uses_shared_inventory_position_components_without_double_holding(
    monkeypatch: pytest.MonkeyPatch,
    inventory_error, inventory_warnings, inbound_source_present,
) -> None:
    policy = V3ReplenishmentPolicy(
        lead_time_days=28,
        review_days=28,
        sigma_lead_time_periods=0.1,
        safety_stock_floor_periods=0.5,
        safety_stock_cap_periods=3.25,
    )
    v2_row = {
        "sku_code": "SKU-A",
        "product_name": "Adapter SKU",
        "brand": "TEST",
        "barcode": "0012345678905",
        "local_available_qty": 55,
        "eu_available_qty": 20,
        "transit_qty": 15,
        "incoming_qty": 10,
        "inbound_status_source_present": inbound_source_present,
        "hold_qty": 999,
        "validation_error": inventory_error,
        "warnings": inventory_warnings,
    }

    monkeypatch.setattr(
        order_logic_v3_source,
        "fetch_cached_cms_inventory_raw_data",
        lambda **_: ({}, {"source": "test"}, ()),
    )
    monkeypatch.setattr(
        order_logic_v3_source,
        "fetch_cached_season_trend_source_data",
        lambda **_: ({
            "sales_history": [],
            "prod_list": [
                {
                    "prod_cd": "SKU-A",
                    "prod_nm": "Adapter SKU",
                    "brand_nm": "TEST",
                    "bar_code": "0099999999999",
                },
                {
                    "prod_cd": "SKU-SALES-ONLY",
                    "prod_nm": "Sales-only SKU",
                    "brand_nm": "TEST",
                    "bar_code": "0088000000002",
                },
            ],
        }, {"source": "test"}),
    )
    monkeypatch.setattr(
        order_logic_v3_source,
        "_paid_demand",
        lambda *_, **__: SimpleNamespace(empty=False),
    )
    monkeypatch.setattr(order_logic_v3_source, "fetch_v3_ledger_sales", lambda **_: ([], {"sha256": "synthetic"}))
    monkeypatch.setattr(order_logic_v3_source, "_ledger_demand", lambda *_, **__: SimpleNamespace(empty=False))
    monkeypatch.setattr(
        order_logic_v3_source,
        "_load_active_profile_catalog",
        lambda *_: (
            order_logic_v3_source._SeasonalProfileCatalog(
                by_class_1_and_2={},
                by_class_1={},
                class_1_and_2_errors={},
                class_1_errors={},
                identities={},
            ),
            {"status": "active", "version": "test-active"},
        ),
    )
    monkeypatch.setattr(order_logic_v3_source, "_identities", lambda *_: {})
    monkeypatch.setattr(
        order_logic_v3_source,
        "_profiles",
        lambda *_, **__: pytest.fail("V3 request path must not recalculate season factors"),
    )
    monkeypatch.setattr(
        order_logic_v3_source,
        "_daily_sales",
        lambda *_, **__: {"SKU-A": {date(2026, 8, 23): 1.0}, "SKU-SALES-ONLY": {date(2026, 8, 23): 1.0}},
    )
    monkeypatch.setattr(
        order_logic_v3_source,
        "_first_paid_sale_dates",
        lambda *_, **__: pytest.fail(
            "91-day web history must not be mislabeled as lifetime first sale"
        ),
    )
    monkeypatch.setattr(order_logic_v3_source, "_grades", lambda *_, **__: {"SKU-A": "GENERAL"})
    monkeypatch.setattr(
        order_logic_v3_source,
        "_inventory_rows",
        lambda *_, **__: ({"SKU-A": v2_row}, {"v2_rows": 1}, None),
    )
    monkeypatch.setattr(
        order_logic_v3_source,
        "_measured_replenishment_policies",
        lambda **_: (policy, policy, {
            "basis": "test",
            "source": {},
            "scenarios": {
                "CASH": {"transport_mode": "RAIL"},
                "SHORTAGE": {"transport_mode": "SEA"},
            },
        }),
    )

    rows, meta = order_logic_v3_source.build_order_logic_v3_source(
        as_of="2026-08-28",
        entity_code="PL",
    )

    replenishment = rows[0]["replenishment"]
    assert rows[0]["inventory_validation_error"] == inventory_error
    assert rows[0]["inventory_warnings"] == tuple(inventory_warnings)
    assert rows[0]["inbound_status_source_present"] is inbound_source_present
    assert rows[1]["sku_code"] == "SKU-SALES-ONLY"
    assert rows[1]["inbound_status_source_present"] is False
    # Keep the inventory barcode when present; fill a sales-only SKU from the
    # product master so the V3 UI/Excel does not show it as unidentified.
    assert rows[0]["barcode"] == "0012345678905"
    assert rows[1]["barcode"] == "0088000000002"
    assert replenishment.on_hand_qty == 55  # type: ignore[union-attr]
    assert replenishment.upstream_available_qty == 20  # type: ignore[union-attr]
    assert replenishment.in_transit_qty == 15  # type: ignore[union-attr]
    assert replenishment.unreceived_qty == 10  # type: ignore[union-attr]
    assert replenishment.holding_qty == 0  # type: ignore[union-attr]
    assert rows[0]["first_sale_date"] is None
    assert rows[0]["cash_transport_mode"] == "RAIL"
    assert rows[0]["shortage_transport_mode"] == "SEA"
    shortage_replenishment = replenishment.for_policy(  # type: ignore[union-attr]
        INVENTORY_POLICY_SHORTAGE,
        1.68,
    )
    assert shortage_replenishment.inventory_position == 100
    assert "completed receipts excluded" in str(meta["inventory_position_policy"])
    assert "PL/USA trust V2 avbl_qty" in str(meta["inventory_position_policy"])
    assert "HQ excludes stock_status=trouble" in str(meta["inventory_position_policy"])
    assert meta["date_basis"] == "SOURCE_CALENDAR_DATE"
    assert "trace is omitted" in str(meta["new_sku_rule"])
    assert "no undocumented recent-sales hold" in str(meta["recent_demand_guard"])


def _grade_demand(revenue_by_sku: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            PRODUCT_CODE_COL: sku,
            DATE_COL: pd.Timestamp("2026-08-23"),
            AMOUNT_COL: revenue,
        }
        for sku, revenue in revenue_by_sku.items()
    ])


def test_v3_grade_cutoff_keeps_core_until_cumulative_revenue_reaches_ninety_percent() -> None:
    # Cumulative revenue before each SKU: A=0%, B=60%, C=89%, D=95%.
    grades = order_logic_v3_source._grades(
        _grade_demand({"SKU-A": 60.0, "SKU-B": 29.0, "SKU-C": 6.0, "SKU-D": 5.0}),
        period_end=date(2026, 8, 23),
    )

    assert order_logic_v3_source.GRADE_CUTOFF == 0.90
    assert grades == {
        "SKU-A": "CORE",
        "SKU-B": "CORE",
        "SKU-C": "CORE",
        "SKU-D": "GENERAL",
    }


def test_v3_safety_stock_fence_periods_match_approved_weekly_policy() -> None:
    # 1 period = 7 calendar days = 1 week (docs/TIME_UNIT_CONTRACT.md).
    assert order_logic_v3_source._V3_SAFETY_STOCK_FENCE_PERIODS == {
        "PL": (2.0, 10.0),
        "USA": (2.0, 8.0),
        "HQ": (1.0, 2.0),
    }
