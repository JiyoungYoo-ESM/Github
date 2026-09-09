import pandas as pd

from core.sales import (
    exclude_negative_amount_positive_qty_for_demand,
    filter_sales_by_biz_type,
    filtered_sales_detail_by_biz,
    recent_sales_qty_by_sku,
    sales_biz_type_label,
    sales_biz_type_note,
)
from core.session import SessionContext


def test_usa_sales_filter_includes_commercial_sales_and_excludes_staff_and_samples():
    source = pd.DataFrame(
        [
            {"Biz Type": "US-DOMESTIC", "금액": 100},
            {"Biz Type": "US-OVERSEAS", "금액": -10},
            {"Biz Type": "KR-OVERSEAS", "금액": 50},
            {"Biz Type": "자사간거래", "금액": 40},
            {"Biz Type": "US-STAFF NJ", "금액": 20},
            {"Biz Type": "FREE SAMPLE", "금액": 0},
        ]
    )

    result = filter_sales_by_biz_type(source, {"entity_code": "USA"})

    assert result["Biz Type"].tolist() == [
        "US-DOMESTIC",
        "US-OVERSEAS",
        "KR-OVERSEAS",
        "자사간거래",
    ]


def test_usa_sales_filter_label_uses_us_business_types():
    label = sales_biz_type_label({"entity_code": "USA"})

    assert "US-DOMESTIC" in label
    assert "KR-OVERSEAS" in label
    assert "자사간거래" in label
    assert "EU-PL" not in label


def test_eu_sales_filter_includes_kr_overseas_in_the_eu_population():
    source = pd.DataFrame(
        [
            {"SKU": "EU_OVERSEAS", "amount": 100, "Biz Type": "EU-OVERSEAS"},
            {"SKU": "EU_PL", "amount": 100, "Biz Type": "EU-PL"},
            {"SKU": "KR_OVERSEAS", "amount": 100, "Biz Type": "KR-OVERSEAS"},
            {"SKU": "INTERCOMPANY", "amount": 100, "Biz Type": "자사간거래"},
            {"SKU": "STAFF", "amount": 100, "Biz Type": "EU-STAFFSALES"},
        ]
    )

    filtered = filter_sales_by_biz_type(
        source,
        {"include_eu_pl_sales": True, "include_etc_sales": False},
    )

    assert filtered["SKU"].tolist() == [
        "EU_OVERSEAS",
        "EU_PL",
        "KR_OVERSEAS",
        "INTERCOMPANY",
    ]
    assert "KR-OVERSEAS" in sales_biz_type_label({"include_eu_pl_sales": True})


def test_v1_demand_filter_excludes_negative_amount_positive_qty_rows():
    source = pd.DataFrame(
        [
            {"SKU": "KEEP", "qty": 10, "amount": 100},
            {"SKU": "INCIDENT", "qty": 3, "amount": -30},
            {"SKU": "NEGATIVE_QTY", "qty": -2, "amount": -20},
        ]
    )

    filtered = exclude_negative_amount_positive_qty_for_demand(source)

    assert filtered["SKU"].tolist() == ["KEEP", "NEGATIVE_QTY"]


def test_v1_demand_quantity_keeps_incident_only_sku_as_zero():
    context = SessionContext(
        uploaded_data={
            "sales_detail": pd.DataFrame(
                [
                    {"SKU": "KEEP", "수량": 10, "금액": 100, "Biz Type": "EU-OVERSEAS"},
                    {"SKU": "INCIDENT_ONLY", "수량": 3, "금액": -30, "Biz Type": "EU-OVERSEAS"},
                ]
            )
        }
    )

    result = recent_sales_qty_by_sku({}, context)
    quantities = result.set_index("SKU")["최근 3개월 판매수량"]

    assert quantities.to_dict() == {"KEEP": 10.0, "INCIDENT_ONLY": 0.0}


def test_sales_filter_includes_negative_eu_net_sales_and_excludes_other_adjustments():
    sales = pd.DataFrame(
        [
            {"SKU": "NORMAL", "수량": 10, "금액": 100, "Biz Type": "EU-OVERSEAS"},
            {"SKU": "INTERCOMPANY", "수량": 20, "금액": 200, "Biz Type": "자사간거래"},
            {"SKU": "RETURN_AS_OVERSEAS", "수량": 3, "금액": -30, "Biz Type": "EU-OVERSEAS"},
            {"SKU": "RETURN_AS_EU_PL", "수량": 3, "금액": -30, "Biz Type": "EU-PL"},
            {"SKU": "RETURN_AS_INTERCOMPANY", "수량": 4, "금액": -40, "Biz Type": "자사간거래"},
            {"SKU": "EXPLICIT_RETURN", "수량": 5, "금액": 50, "Biz Type": "반품 (Normal)"},
            {"SKU": "SETTLEMENT", "수량": 6, "금액": 60, "Biz Type": "추후상계"},
            {"SKU": "STAFF", "수량": 7, "금액": 70, "Biz Type": "EU-STAFFSALES"},
        ]
    )

    filtered = filter_sales_by_biz_type(
        sales,
        {"include_eu_pl_sales": True, "include_etc_sales": False},
    )

    assert filtered["SKU"].tolist() == [
        "NORMAL",
        "INTERCOMPANY",
        "RETURN_AS_OVERSEAS",
        "RETURN_AS_EU_PL",
    ]


def test_sales_filter_includes_negative_converted_amount_for_eu_overseas():
    sales = pd.DataFrame(
        [
            {"SKU": "KEEP", "수량": 10, "금액": 100, "환산금액": 100, "Biz Type": "EU-OVERSEAS"},
            {"SKU": "DROP", "수량": 10, "금액": 100, "환산금액": -100, "Biz Type": "EU-OVERSEAS"},
        ]
    )

    filtered = filter_sales_by_biz_type(sales, {"include_eu_pl_sales": True})

    assert filtered["SKU"].tolist() == ["KEEP", "DROP"]


def test_sales_filter_keeps_zero_amount_products_without_manual_sample_classification():
    sales = pd.DataFrame(
        [
            {"SKU": "ZERO_OVERSEAS", "수량": 500, "금액": 0, "Biz Type": "EU-OVERSEAS"},
            {"SKU": "ZERO_EU_PL", "수량": 500, "금액": 0, "Biz Type": "EU-PL"},
        ]
    )

    filtered = filter_sales_by_biz_type(sales, {"include_eu_pl_sales": True})

    assert filtered["SKU"].tolist() == ["ZERO_OVERSEAS", "ZERO_EU_PL"]


def test_sales_filter_policy_text_matches_net_sales_rule():
    label = sales_biz_type_label({"include_eu_pl_sales": True, "include_etc_sales": False})

    assert "EU-OVERSEAS·EU-PL 음수 금액은 순매출 포함" in label
    assert "음수 금액은 반품/상계성으로 제외" not in sales_biz_type_note()


def test_filtered_sales_detail_by_biz_reuses_session_cache(monkeypatch):
    sales = pd.DataFrame(
        [
            {"SKU": "KEEP", "수량": 10, "금액": 100, "Biz Type": "EU-OVERSEAS"},
            {"SKU": "DROP", "수량": 10, "금액": -100, "Biz Type": "EU-OVERSEAS"},
        ]
    )
    context = SessionContext(uploaded_data={"sales_detail": sales})
    calls = 0

    def fake_filter_sales_by_biz_type(sales_df: pd.DataFrame, settings: dict) -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return sales_df[sales_df["SKU"] == "KEEP"].copy()

    monkeypatch.setattr("core.sales.filter_sales_by_biz_type", fake_filter_sales_by_biz_type)

    settings = {"include_eu_pl_sales": True, "include_etc_sales": False}
    first = filtered_sales_detail_by_biz(settings, context)
    second = filtered_sales_detail_by_biz(settings, context)

    assert calls == 1
    assert first["SKU"].tolist() == ["KEEP"]
    assert second["SKU"].tolist() == ["KEEP"]
