import pandas as pd

from backend.services.season_data_quality import build_source_data_quality


def test_source_quality_flags_exact_duplicate_candidates_without_removing_them():
    rows = pd.DataFrame(
        [
            {
                "invc_no": "INV-1",
                "ship_dt": "2026-01-10",
                "prod_cd": "SKU-1",
                "qty": 10,
                "amount": 100,
                "amount_krw": 100,
                "curr": "EUR",
                "biz_type": "EU-OVERSEAS",
            },
            {
                "invc_no": "INV-1",
                "ship_dt": "2026-01-10",
                "prod_cd": "SKU-1",
                "qty": 10,
                "amount": 100,
                "amount_krw": 100,
                "curr": "EUR",
                "biz_type": "EU-OVERSEAS",
            },
            {
                "invc_no": "INV-2",
                "ship_dt": "2026-01-11",
                "prod_cd": "SKU-2",
                "qty": 5,
                "amount": 800,
                "amount_krw": 800,
                "curr": "EUR",
                "biz_type": "EU-OVERSEAS",
            },
        ]
    )

    quality = build_source_data_quality(
        rows,
        start_date=pd.Timestamp("2026-01-01"),
        end_date=pd.Timestamp("2026-01-31 23:59:59"),
        eu_local=True,
    )

    assert quality["sourceRows"] == 3
    assert quality["duplicateCandidateGroups"] == 1
    assert quality["duplicateCandidateRows"] == 2
    assert quality["duplicateCandidateExcessRows"] == 1
    assert quality["duplicateCandidateAmountEur"] == 100.0
    assert quality["duplicateCandidateAmountSharePct"] == 10.0
    assert quality["stableIdColumn"] is None
    assert quality["status"] == "blocked"
    assert quality["recommendationBlocked"] is True


def test_source_quality_tracks_free_gifts_and_stable_line_id():
    rows = pd.DataFrame(
        [
            {
                "sales_line_id": "LINE-1",
                "ship_dt": "2026-01-10",
                "prod_cd": "SKU-1",
                "qty": 10,
                "amount": 1000,
                "curr": "EUR",
                "biz_type": "EU-OVERSEAS",
            },
            {
                "sales_line_id": "LINE-2",
                "ship_dt": "2026-01-11",
                "prod_cd": "GIFT",
                "qty": 25,
                "amount": 0,
                "curr": "EUR",
                "biz_type": "EU-OVERSEAS",
            },
        ]
    )

    quality = build_source_data_quality(rows, eu_local=True)

    assert quality["stableIdColumn"] == "sales_line_id"
    assert quality["freeOfChargeRowsExcluded"] == 1
    assert quality["freeOfChargeQtyExcluded"] == 25.0
    assert quality["duplicateCandidateGroups"] == 0
    assert quality["status"] == "ok"
    assert quality["recommendationBlocked"] is False
