from __future__ import annotations

from datetime import date

import pytest

from backend.services import order_logic_v3_hq_fetch as hq_fetch
from backend.services.order_logic_v3_unreceived_window import (
    V3_UNRECEIVED_LOOKBACK_DAYS,
    merge_open_po_unreceived_window,
    unreceived_cache_scope,
    unreceived_po_window,
    unreceived_po_window_audit,
    zero_stale_hq_unreceived_quantities,
)


def test_window_is_thirty_calendar_days_including_the_analysis_date() -> None:
    start, end = unreceived_po_window("2026-09-04")

    assert V3_UNRECEIVED_LOOKBACK_DAYS == 30
    assert end == date(2026, 9, 4)
    assert start == date(2026, 8, 6)
    assert (end - start).days + 1 == V3_UNRECEIVED_LOOKBACK_DAYS


def test_window_audit_records_the_basis_and_the_quantity_only_scope() -> None:
    audit = unreceived_po_window_audit(date(2026, 9, 4))

    assert audit["basis"] == "PO_REGISTRATION_DATE"
    assert audit["scope"] == "UNRECEIVED_OPEN_PO_QUANTITY_ONLY"
    assert audit["date_from"] == "2026-08-06"
    assert audit["date_to"] == "2026-09-04"
    assert audit["calendar_days"] == 30


# --- HQ: zero the ① quantity, never drop the row ---------------------------


def test_hq_boundary_days_are_inclusive_and_stale_quantities_are_zeroed() -> None:
    rows = [
        {"sku": "IN-START", "created_date": "2026-08-06", "remaining_qty": 1},
        {"sku": "IN-END", "created_date": "2026-09-04", "remaining_qty": 2},
        {"sku": "OLD", "created_date": "2026-08-05", "remaining_qty": 30},
        {"sku": "STALE", "created_date": "2026-01-02", "remaining_qty": 400},
    ]

    kept, audit = zero_stale_hq_unreceived_quantities(rows, as_of="2026-09-04")

    assert [row["remaining_qty"] for row in kept] == [1, 2, 0, 0]
    # Row count is unchanged so inbound-source presence and identity evidence
    # survive; only the quantity this decision covers changes.
    assert [row["sku"] for row in kept] == ["IN-START", "IN-END", "OLD", "STALE"]
    assert audit["source_rows"] == 4
    assert audit["rows_in_window"] == 2
    assert audit["zeroed_rows"] == 2
    assert audit["zeroed_quantity"] == 430
    assert audit["unparsable_date_rows"] == 0


@pytest.mark.parametrize("value", [None, "", "2026-09", "not-a-date"])
def test_hq_unparsable_registration_dates_are_zeroed_and_counted(value) -> None:
    kept, audit = zero_stale_hq_unreceived_quantities(
        [{"sku": "NO-DATE", "created_date": value, "remaining_qty": 5}],
        as_of="2026-09-04",
    )

    assert [row["remaining_qty"] for row in kept] == [0]
    assert audit["unparsable_date_rows"] == 1
    assert audit["zeroed_quantity"] == 5


def test_hq_source_rows_are_not_mutated_in_place() -> None:
    rows = [{"sku": "STALE", "created_date": "2026-01-02", "remaining_qty": 400}]

    zero_stale_hq_unreceived_quantities(rows, as_of="2026-09-04")

    assert rows[0]["remaining_qty"] == 400


def test_hq_fetch_zeroes_stale_open_po_and_leaves_confirmed_inbound_intact(monkeypatch) -> None:
    inbound_confirmed = [
        # ② PNFM확정·③ 입고진행중은 오래된 PO에 딸려 있어도 확실히 들어올 물량이다.
        {"sku": "SKU-A", "ship_date": "2026-02-01", "remaining_qty": 7,
         "pnfm_confirmed_qty": 7, "inbound_in_progress_qty": 0, "completed_qty": 0},
    ]
    inventory = {
        "inventory": [{"sku": "SKU-A", "available_qty": 0, "unit_cost": "0"}],
        "open_po": [
            {"sku": "SKU-A", "created_date": "2026-09-01", "remaining_qty": 10},
            {"sku": "SKU-A", "created_date": "2026-01-02", "remaining_qty": 900},
        ],
        "inbound_confirmed": inbound_confirmed,
        "leadtime_stats": {},
    }
    monkeypatch.setattr(
        hq_fetch, "_cached_inventory", lambda **_: (inventory, {"source": "test"}),
    )
    monkeypatch.setattr(
        hq_fetch,
        "fetch_cached_season_trend_source_data",
        lambda **_: ({"sales_history": [], "prod_list": []}, {}),
    )

    raw, meta = hq_fetch.fetch_cached_hq_opo_raw_data(
        as_of="2026-09-04", date_from="2026-06-06", date_to="2026-09-04",
    )

    assert [row["remaining_qty"] for row in raw["open_po"]] == [10, 0]
    assert raw["inbound_confirmed"] == inbound_confirmed
    assert meta["unreceived_window"]["date_from"] == "2026-08-06"
    assert meta["unreceived_window"]["zeroed_rows"] == 1
    assert meta["unreceived_window"]["zeroed_quantity"] == 900
    # 캐시에 담긴 원천 스냅샷은 창 적용 전 수량을 그대로 유지한다.
    assert [row["remaining_qty"] for row in inventory["open_po"]] == [10, 900]


# --- PL/USA: take ① from the recent query, everything else from the full one ---


def _full_row(sku, **overrides):
    row = {
        "prod_cd": sku, "prod_nm": f"{sku} name", "bar_code": "0012345678905",
        "brand_nm": "TEST", "biz_gbn": "COSMETIC",
        "po_qty": 100, "pnfm_qty": 0, "open_qty": 100, "open_amt": 1000.0,
        "pnfm_confirmed_qty": 0, "inbound_in_progress_qty": 0,
        "completed_qty": 0, "trouble_qty": 0,
    }
    row.update(overrides)
    return row


def test_pl_usa_merge_takes_unreceived_from_recent_and_keeps_inbound_goods() -> None:
    full = [
        # 오래된 PO의 잔량은 빠지지만, 그 PO의 ②③은 이미 들어오는 중이라 남는다.
        _full_row("STALE", open_qty=900, po_qty=1000, pnfm_qty=100, open_amt=9000.0,
                  pnfm_confirmed_qty=60, inbound_in_progress_qty=40, completed_qty=25),
        _full_row("RECENT", open_qty=50, po_qty=50, open_amt=500.0,
                  pnfm_confirmed_qty=5, inbound_in_progress_qty=3),
    ]
    recent = [_full_row("RECENT", open_qty=50, po_qty=50, open_amt=500.0)]

    merged, audit = merge_open_po_unreceived_window(full, recent, as_of="2026-09-04")

    stale = next(row for row in merged if row["prod_cd"] == "STALE")
    assert stale["open_qty"] == 0 and stale["open_amt"] == 0
    # PO 단위 총계는 창을 따르지 않는다. 30일 값으로 바꾸면
    # `po_qty < completed_qty`인 물리적으로 불가능한 행이 남는다.
    assert stale["po_qty"] == 1000 and stale["pnfm_qty"] == 100
    assert stale["po_qty"] >= stale["completed_qty"]
    # ②③④와 식별 정보는 전체 창 값을 그대로 유지한다.
    assert stale["pnfm_confirmed_qty"] == 60
    assert stale["inbound_in_progress_qty"] == 40
    assert stale["completed_qty"] == 25
    assert stale["prod_nm"] == "STALE name" and stale["brand_nm"] == "TEST"

    recent_row = next(row for row in merged if row["prod_cd"] == "RECENT")
    assert recent_row["open_qty"] == 50
    assert recent_row["pnfm_confirmed_qty"] == 5

    assert audit["scope"] == "UNRECEIVED_OPEN_PO_QUANTITY_ONLY"
    assert audit["full_window_rows"] == 2
    assert audit["recent_window_rows"] == 1
    assert audit["merged_rows"] == 2
    assert audit["changed_rows"] == 1
    assert audit["recent_only_rows"] == 0


def test_pl_usa_merge_keeps_every_sku_row_so_presence_is_unchanged() -> None:
    full = [_full_row("A"), _full_row("B"), _full_row("C")]

    merged, _ = merge_open_po_unreceived_window(full, [], as_of="2026-09-04")

    assert [row["prod_cd"] for row in merged] == ["A", "B", "C"]
    assert all(row["open_qty"] == 0 for row in merged)


def test_pl_usa_merge_does_not_repeat_a_recent_total_across_duplicate_rows() -> None:
    full = [_full_row("DUP", open_qty=10), _full_row("DUP", open_qty=20)]
    recent = [_full_row("DUP", open_qty=7)]

    merged, _ = merge_open_po_unreceived_window(full, recent, as_of="2026-09-04")

    assert [row["open_qty"] for row in merged] == [7, 0]


def test_pl_usa_merge_sums_multiple_recent_rows_for_one_sku() -> None:
    recent = [_full_row("A", open_qty=4), _full_row("A", open_qty=6)]

    merged, _ = merge_open_po_unreceived_window([_full_row("A")], recent, as_of="2026-09-04")

    assert merged[0]["open_qty"] == 10


def test_pl_usa_merge_keeps_a_recent_only_sku_instead_of_losing_its_quantity() -> None:
    recent = [_full_row("ONLY-RECENT", open_qty=12)]

    merged, audit = merge_open_po_unreceived_window([], recent, as_of="2026-09-04")

    assert [row["prod_cd"] for row in merged] == ["ONLY-RECENT"]
    assert merged[0]["open_qty"] == 12
    assert audit["recent_only_rows"] == 1


def test_pl_usa_merge_links_a_case_only_code_difference() -> None:
    """CMS가 같은 상품을 두 조회에서 다른 대소문자로 돌려준 실제 사례."""

    full = [_full_row("KOEP05-FP", open_qty=612, po_qty=612,
                      pnfm_confirmed_qty=9, inbound_in_progress_qty=4)]
    recent = [_full_row("KoeP05-FP", open_qty=612, po_qty=612)]

    merged, audit = merge_open_po_unreceived_window(full, recent, as_of="2026-09-04")

    assert len(merged) == 1
    assert merged[0]["prod_cd"] == "KOEP05-FP"
    assert merged[0]["open_qty"] == 612
    assert merged[0]["pnfm_confirmed_qty"] == 9
    assert audit["case_only_code_matches"] == 1
    assert audit["recent_only_rows"] == 0


def test_pl_usa_merge_refuses_an_ambiguous_case_fold() -> None:
    """대소문자만 다른 코드가 한쪽에 둘 이상이면 추측해서 묶지 않는다."""

    full = [
        _full_row("ABC-1", open_qty=10, pnfm_confirmed_qty=60, inbound_in_progress_qty=40),
        _full_row("abc-1", open_qty=20, pnfm_confirmed_qty=9, inbound_in_progress_qty=4),
    ]
    recent = [_full_row("Abc-1", open_qty=7, pnfm_confirmed_qty=9, inbound_in_progress_qty=4)]

    merged, audit = merge_open_po_unreceived_window(full, recent, as_of="2026-09-04")

    assert [row["open_qty"] for row in merged] == [0, 0, 7]
    assert audit["case_only_code_matches"] == 0
    assert audit["recent_only_rows"] == 1
    # 구조 회귀: 구제 행이 ②③을 다시 들고 오면 전체 창 합계가 이중계상된다.
    assert sum(float(r["pnfm_confirmed_qty"]) for r in merged) == 69
    assert sum(float(r["inbound_in_progress_qty"]) for r in merged) == 44
    assert audit["rescued_rows_with_preserved_fields_zeroed"] == 1


def test_pl_usa_merge_does_not_double_count_inbound_on_a_mixed_case_duplicate() -> None:
    """회귀: 모호한 fold가 뒤따르는 정확일치를 막고 ②③을 이중계상하던 버그.

    full 피드에 대소문자만 다른 두 철자가 있고 recent에는 그중 하나만 있는 경우,
    정확일치가 성립하는 행이 반드시 그 값을 받아야 한다. 그러지 못하면 recent
    행이 별도 행으로 append되어 ②PNFM확정·③입고진행중이 두 번 더해진다.
    """

    full = [
        _full_row("KoeP05-FP", open_qty=900, pnfm_confirmed_qty=60, inbound_in_progress_qty=40),
        _full_row("KOEP05-FP", open_qty=100, pnfm_confirmed_qty=9, inbound_in_progress_qty=4),
    ]
    recent = [_full_row("KOEP05-FP", open_qty=100, pnfm_confirmed_qty=9, inbound_in_progress_qty=4)]

    merged, audit = merge_open_po_unreceived_window(full, recent, as_of="2026-09-04")

    assert len(merged) == 2, "recent 행이 중복 append되면 안 된다"
    assert audit["recent_only_rows"] == 0
    by_code = {row["prod_cd"]: row for row in merged}
    # 오래된 철자는 최근 발주가 없으므로 ①=0, 정확일치 철자는 100을 받는다.
    assert by_code["KoeP05-FP"]["open_qty"] == 0
    assert by_code["KOEP05-FP"]["open_qty"] == 100
    # ②③은 전체 창 값 그대로여야 한다 (60/9, 40/4 — 합계 69/44).
    assert sum(float(r["pnfm_confirmed_qty"]) for r in merged) == 69
    assert sum(float(r["inbound_in_progress_qty"]) for r in merged) == 44


def test_pl_usa_merge_keeps_a_negative_unreceived_so_v2_still_blocks() -> None:
    """음수 미입고는 PO 등록일과 무관하게 계속 차단돼야 한다.

    CMS는 PNFM 수량 > PO 수량인 행에서 음수 미입고를 반환한다(실측 PL
    IUS04-CEU -80, USA ANP10-MPH -200). V2는 이 SKU를 INCOMING_QTY_NEGATIVE로
    차단하므로, 창을 좁힌 결과로 0이 되어 검증이 사라지면 안 된다.
    사용자 결정 2026-09-04.
    """

    full = [_full_row("NEG", open_qty=-80, open_amt=-456000, po_qty=1000, pnfm_qty=1080)]

    merged, audit = merge_open_po_unreceived_window(full, [], as_of="2026-09-04")

    assert merged[0]["open_qty"] == -80, "음수가 0으로 덮이면 V2 차단이 사라진다"
    assert merged[0]["open_amt"] == -456000
    assert audit["blocked_negative_rows"] == 1
    assert audit["blocked_negative_quantity"] == -80


def test_pl_usa_negative_unreceived_still_blocks_through_the_real_adapter() -> None:
    """병합 결과가 V2 adapter를 통과할 때 실제로 차단되는지 확인한다."""

    from backend.services.order_logic_v2_source import (
        build_order_logic_inventory_position_source,
    )

    full = [_full_row("NEG", open_qty=-80, po_qty=1000, pnfm_qty=1080,
                      inbound_in_progress_qty=1080)]
    merged, _ = merge_open_po_unreceived_window(full, [], as_of="2026-09-04")

    prepared = build_order_logic_inventory_position_source(
        {
            "stock_local": [{"prod_cd": "NEG", "avbl_qty": 300}],
            "stock_hq": [{"prod_cd": "NEG", "avbl_qty": 0}],
            "shipping": [],
            "open_po": merged,
            "sales_local": [], "sales_hq": [],
        },
        entity_code="PL",
    )
    row = next(r for r in prepared.rows if r["sku_code"] == "NEG")
    assert "INCOMING_QTY_NEGATIVE" in row["warnings"]
    assert row["validation_error"] is not None


def test_hq_negative_unreceived_is_not_zeroed_either() -> None:
    """HQ도 창 밖 음수 ①을 0으로 만들지 않는다."""

    rows = [
        {"sku": "NEG", "created_date": "2026-01-02", "remaining_qty": -80},
        {"sku": "STALE", "created_date": "2026-01-02", "remaining_qty": 400},
    ]

    kept, audit = zero_stale_hq_unreceived_quantities(rows, as_of="2026-09-04")

    assert [row["remaining_qty"] for row in kept] == [-80, 400 - 400]
    assert audit["blocked_negative_rows"] == 1
    assert audit["blocked_negative_quantity"] == -80
    # 음수 행은 0 처리 집계에 포함되지 않는다.
    assert audit["zeroed_rows"] == 1
    assert audit["zeroed_quantity"] == 400
    assert audit["rows_in_window"] == 0


def test_cache_scope_changes_with_the_window_length(monkeypatch) -> None:
    """창 길이를 바꾸면 이전 창으로 받아둔 스냅샷이 재사용되지 않아야 한다."""

    from backend.services import order_logic_v3_unreceived_window as window

    scope_30 = unreceived_cache_scope()
    assert "30d" in scope_30
    monkeypatch.setattr(window, "V3_UNRECEIVED_LOOKBACK_DAYS", 45)
    assert window.unreceived_cache_scope() != scope_30
    assert "45d" in window.unreceived_cache_scope()
