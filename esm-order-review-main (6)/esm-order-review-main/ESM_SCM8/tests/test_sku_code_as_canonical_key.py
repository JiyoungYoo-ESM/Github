import pandas as pd

from core.eta import eta_detail_display_df
from core.export_excel import build_order_sheet_top_sales_df


def test_eta_detail_groups_by_sku_not_product_name():
    detail = pd.DataFrame(
        {
            "SKU": ["SKU-1", "SKU-1", "SKU-2"],
            "상품명": ["Name A", "Name A renewal", "Name A"],
            "수량": [10, 15, 20],
            "금액(EUR)": [1, 2, 3],
            "도착 예정 금액(M원)": [100, 200, 300],
            "운송수단": ["해운", "해운", "해운"],
            "출고일": ["2026-05-01", "2026-05-02", "2026-05-03"],
            "리드타임": [80, 80, 80],
            "위험도": ["정상", "정상", "정상"],
        }
    )

    result = eta_detail_display_df(detail)

    assert result["SKU"].tolist() == ["SKU-1", "SKU-2"]
    assert result.loc[result["SKU"].eq("SKU-1"), "수량"].iloc[0] == 25
    assert result.loc[result["SKU"].eq("SKU-2"), "수량"].iloc[0] == 20


def test_order_sheet_top_sales_uses_product_code_when_names_match():
    report = pd.DataFrame(
        {
            "상품코드": ["SKU-OLD", "SKU-NEW"],
            "상품명": ["Same Cream", "Same Cream"],
            "브랜드": ["Brand", "Brand"],
            "PA+CA 판매수량": [100, 80],
        }
    )

    result = build_order_sheet_top_sales_df(report)

    assert result["SKU"].head(2).tolist() == ["SKU-OLD", "SKU-NEW"]
