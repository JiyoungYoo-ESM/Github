import pandas as pd
import pytest

from backend.services.order_logic_v2_hq_source import is_hq_demand_row
from core.sales import filter_sales_by_biz_type


@pytest.mark.parametrize(
    ("entity_code", "allowed_biz_type"),
    [
        ("PL", "EU-OVERSEAS"),
        ("USA", "US-DOMESTIC"),
    ],
)
def test_v2_keeps_sample_and_sachet_products_but_drops_free_sample_transactions(
    entity_code: str,
    allowed_biz_type: str,
) -> None:
    sales = pd.DataFrame(
        [
            {
                "SKU": "SAMPLE-SKU",
                "상품명": "[샘플] 정상 보충 대상",
                "수량": 100,
                "금액": 0,
                "Biz Type": allowed_biz_type,
            },
            {
                "SKU": "SACHET-SKU",
                "상품명": "[샤쉐] 정상 보충 대상",
                "수량": 200,
                "금액": 0,
                "Biz Type": allowed_biz_type,
            },
            {
                "SKU": "SACHET-SKU",
                "상품명": "[사쉐] 무상 출고",
                "수량": 300,
                "금액": 0,
                "Biz Type": "FREE SAMPLE",
            },
        ]
    )

    filtered = filter_sales_by_biz_type(sales, {"entity_code": entity_code})

    assert filtered[["SKU", "수량"]].to_dict("records") == [
        {"SKU": "SAMPLE-SKU", "수량": 100},
        {"SKU": "SACHET-SKU", "수량": 200},
    ]


def test_hq_v2_uses_biz_type_not_sample_or_sachet_product_name() -> None:
    base_row = {
        "prod_cd": "SAMPLE-SACHET-SKU",
        "prod_nm": "[샘플/샤쉐] 정상 보충 대상",
        "whouse_nm": "OPO",
    }

    assert is_hq_demand_row({**base_row, "biz_type": "KR-DOMESTIC"})
    assert not is_hq_demand_row({**base_row, "biz_type": "FREE SAMPLE"})
