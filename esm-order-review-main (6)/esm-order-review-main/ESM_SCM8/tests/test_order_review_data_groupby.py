import pandas as pd

from core import export_excel_util, inbound, order_review_data


def test_aggregate_eu_stock_for_order_preserves_first_value_rules():
    eu_stock = pd.DataFrame(
        [
            {
                "상품코드": "SKU_A",
                "브랜드": "-",
                "상품명": "상품명 미확인",
                "제품상태": "",
                "바코드": "nan",
                "재고수량": 3,
                "Hold수량": 1,
                "EU 현지 가용수량": 2,
                "EU 입고단가": 0,
                "PA+CA 판매수량": None,
                "최근 3개월 판매수량": -5,
                "EU 입고단가 원본컬럼": "",
                "EU 입고단가 통화": "-",
            },
            {
                "상품코드": "SKU_A",
                "브랜드": "BRAND_A",
                "상품명": "Name A",
                "제품상태": "정상",
                "바코드": "8800000000001",
                "재고수량": 4,
                "Hold수량": 2,
                "EU 현지 가용수량": 3,
                "EU 입고단가": 7,
                "PA+CA 판매수량": -2,
                "최근 3개월 판매수량": 0,
                "EU 입고단가 원본컬럼": "EU 입고단가",
                "EU 입고단가 통화": "EUR",
            },
        ]
    )

    result = order_review_data.aggregate_eu_stock_for_order(eu_stock)
    row = result.iloc[0]

    assert row["브랜드"] == "BRAND_A"
    assert row["상품명"] == "Name A"
    assert row["제품상태"] == "정상"
    assert row["바코드"] == "8800000000001"
    assert row["재고수량"] == 7
    assert row["Hold수량"] == 3
    assert row["EU 현지 가용수량"] == 5
    assert row["EU 입고단가"] == 7.0
    assert row["PA+CA 판매수량"] == 0.0
    assert row["최근 3개월 판매수량"] == -5.0
    assert row["EU 입고단가 원본컬럼"] == "EU 입고단가"
    assert row["EU 입고단가 통화"] == "EUR"


def test_aggregate_eu_stock_for_order_merges_case_variant_skus_to_master_display():
    eu_stock = pd.DataFrame(
        [
            {
                "상품코드": "DRAS01-CASReu",
                "브랜드": "닥터엘시아",
                "상품명": "Renew inbound",
                "제품상태": "정상",
                "바코드": "8809447256795",
                "재고수량": 0,
                "Hold수량": 0,
                "EU 현지 가용수량": 0,
                "EU 입고단가": 0,
                "PA+CA 판매수량": 273560,
                "최근 3개월 판매수량": 273560,
                "EU 입고단가 원본컬럼": "EU 입고단가",
                "EU 입고단가 통화": "EUR",
            },
            {
                "상품코드": "DRAS01-CASReu",
                "브랜드": "닥터엘시아",
                "상품명": "Renew inbound 2",
                "제품상태": "정상",
                "바코드": "8809447256795",
                "재고수량": 1,
                "Hold수량": 0,
                "EU 현지 가용수량": 1,
                "EU 입고단가": 0,
                "PA+CA 판매수량": 0,
                "최근 3개월 판매수량": 0,
                "EU 입고단가 원본컬럼": "EU 입고단가",
                "EU 입고단가 통화": "EUR",
            },
            {
                "상품코드": "DRAS01-CASreu",
                "브랜드": "닥터엘시아",
                "상품명": "Renew current",
                "제품상태": "정상",
                "바코드": "8809447256795",
                "재고수량": 57499,
                "Hold수량": 0,
                "EU 현지 가용수량": 57499,
                "EU 입고단가": 1,
                "PA+CA 판매수량": 56724,
                "최근 3개월 판매수량": 56724,
                "EU 입고단가 원본컬럼": "EU 입고단가",
                "EU 입고단가 통화": "EUR",
            },
        ]
    )

    result = order_review_data.aggregate_eu_stock_for_order(eu_stock)

    assert result["상품코드"].tolist() == ["DRAS01-CASReu"]
    row = result.iloc[0]
    assert int(row["EU 현지 가용수량"]) == 57500
    assert int(row["재고수량"]) == 57500
    assert int(row["최근 3개월 판매수량"]) == 273560


def test_aggregate_eu_stock_for_order_keeps_non_exception_case_variants_separate():
    eu_stock = pd.DataFrame(
        [
            {
                "상품코드": "SKU-CaseA",
                "브랜드": "BRAND",
                "상품명": "Case A",
                "제품상태": "정상",
                "바코드": "A",
                "재고수량": 1,
                "Hold수량": 0,
                "EU 현지 가용수량": 1,
                "EU 입고단가": 1,
                "PA+CA 판매수량": 1,
                "최근 3개월 판매수량": 1,
                "EU 입고단가 원본컬럼": "EU 입고단가",
                "EU 입고단가 통화": "EUR",
            },
            {
                "상품코드": "SKU-CASEA",
                "브랜드": "BRAND",
                "상품명": "Case B",
                "제품상태": "정상",
                "바코드": "B",
                "재고수량": 2,
                "Hold수량": 0,
                "EU 현지 가용수량": 2,
                "EU 입고단가": 1,
                "PA+CA 판매수량": 2,
                "최근 3개월 판매수량": 2,
                "EU 입고단가 원본컬럼": "EU 입고단가",
                "EU 입고단가 통화": "EUR",
            },
        ]
    )

    result = order_review_data.aggregate_eu_stock_for_order(eu_stock)

    assert set(result["상품코드"]) == {"SKU-CaseA", "SKU-CASEA"}


def test_excel_exact_index_formula_uses_case_sensitive_exact_match():
    formula = export_excel_util.excel_exact_index_formula("A2", "'재고'!$B$2:$B$100", "'재고'!$M$2:$M$100", default="0")

    assert formula == '=IFERROR(INDEX(\'재고\'!$M$2:$M$100,MATCH(TRUE,EXACT(A2,\'재고\'!$B$2:$B$100),0)),0)'


def test_first_non_empty_map_preserves_excel_text_identifier_rule():
    values = pd.DataFrame(
        [
            {"SKU": "SKU_A", "값": "-"},
            {"SKU": "SKU_A", "값": "123.0"},
            {"SKU": "SKU_B", "값": "none"},
        ]
    )

    result = inbound.first_non_empty_map(values, "SKU", "값")

    assert result["SKU_A"] == "123"
    assert result["SKU_B"] == ""
