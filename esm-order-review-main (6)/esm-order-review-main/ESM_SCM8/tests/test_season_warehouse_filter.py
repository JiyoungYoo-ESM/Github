import pandas as pd
from fastapi import HTTPException
import pytest

from backend.services import season_api_analysis_service as service
from backend.services.season_api_analysis_service import (
    filter_sales_history_by_warehouse,
    filter_sales_history_rows_by_warehouse,
)


def test_filter_sales_history_by_warehouse_matches_whouse_name_case_insensitively():
    sales = pd.DataFrame(
        [
            {"prod_cd": "A", "whouse_nm": "OPO", "qty": 10},
            {"prod_cd": "B", "whouse_nm": "BR-US", "qty": 20},
            {"prod_cd": "C", "whouse_nm": " opo ", "qty": 30},
        ]
    )

    filtered, metadata = filter_sales_history_by_warehouse(sales, "opo")

    assert filtered["prod_cd"].tolist() == ["A", "C"]
    assert metadata == {
        "field": "whouse_nm",
        "selected": "OPO",
        "rows_before": 3,
        "rows_after": 2,
    }


def test_filter_sales_history_by_warehouse_keeps_all_rows_without_selection():
    sales = pd.DataFrame([{"prod_cd": "A", "whouse_nm": "OPO", "qty": 10}])

    filtered, metadata = filter_sales_history_by_warehouse(sales, None)

    assert filtered is sales
    assert metadata is None


def test_filter_sales_history_by_warehouse_rejects_empty_result():
    sales = pd.DataFrame([{"prod_cd": "A", "whouse_nm": "OPO", "qty": 10}])

    with pytest.raises(HTTPException) as caught:
        filter_sales_history_by_warehouse(sales, "BR-US")

    assert caught.value.status_code == 400
    assert "판매이력" in caught.value.detail


def test_raw_hq_filter_preserves_rows_and_metadata_before_dataframe_creation():
    sales = [
        {"prod_cd": "A", "whouse_nm": "OPO", "amount_krw": 100},
        {"prod_cd": "B", "whouse_nm": "BR-US", "amount_krw": 200},
        {"prod_cd": "C", "whouse_nm": " opo ", "amount_krw": 300},
    ]

    filtered, metadata = filter_sales_history_rows_by_warehouse(sales, "opo")

    assert filtered == [sales[0], sales[2]]
    assert filtered[0] is sales[0]
    assert metadata == {
        "field": "whouse_nm",
        "selected": "OPO",
        "rows_before": 3,
        "rows_after": 2,
    }


def test_hq_analysis_builds_dataframe_from_only_selected_rows(monkeypatch):
    raw = {
        "sales_history": [
            {"prod_cd": "A", "whouse_nm": "OPO", "amount_krw": 100},
            {"prod_cd": "B", "whouse_nm": "BR-US", "amount_krw": 200},
        ],
        "prod_list": [{"prod_cd": "A"}],
    }
    source_meta = {
        "sales_history": {"path": "/us/sales/history", "rows": 2},
        "prod_list": {"path": "/eu/products", "rows": 1},
    }
    captured: dict[str, pd.DataFrame] = {}
    monkeypatch.setattr(
        service,
        "fetch_cached_season_trend_source_data",
        lambda **kwargs: (raw, source_meta),
    )

    def build(uploaded_data, analysis_options):
        del analysis_options
        captured.update(uploaded_data)
        return {}

    monkeypatch.setattr(service, "build_season_ingredient_analysis", build)

    result = service.run_api_analysis_with_options(
        {
            "start_date": "2026-09-01",
            "end_date": "2026-09-04",
            "entity_code": "HQ",
            "warehouse": "OPO",
        },
        save_result=False,
    )

    assert captured["sales_history"]["prod_cd"].tolist() == ["A"]
    assert result["source_meta"]["warehouse_filter"] == {
        "field": "whouse_nm",
        "selected": "OPO",
        "rows_before": 2,
        "rows_after": 1,
    }


def test_hq_analysis_still_validates_excluded_warehouse_rows(monkeypatch):
    monkeypatch.setattr(
        service,
        "fetch_cached_season_trend_source_data",
        lambda **kwargs: (
            {
                "sales_history": [
                    {"prod_cd": "A", "whouse_nm": "OPO", "amount_krw": 100},
                    {"prod_cd": "B", "whouse_nm": "BR-US", "amount_krw": None},
                ],
                "prod_list": [{"prod_cd": "A"}],
            },
            {},
        ),
    )

    with pytest.raises(HTTPException) as caught:
        service.run_api_analysis_with_options(
            {
                "start_date": "2026-09-01",
                "end_date": "2026-09-04",
                "entity_code": "HQ",
                "warehouse": "OPO",
            },
            save_result=False,
        )

    assert caught.value.status_code == 502
