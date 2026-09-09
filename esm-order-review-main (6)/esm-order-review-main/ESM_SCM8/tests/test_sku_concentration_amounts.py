import pandas as pd

from backend.analysis import build_sku_concentration_df, enrich_order_review_amounts


def test_cms_actual_krw_sales_and_stock_are_not_converted_again():
    sales_detail = pd.DataFrame(
        {
            "sku": ["A-001"],
            "qty": [10],
            "amount_krw_actual": [64_000],
        }
    )
    eu_stock = pd.DataFrame(
        {
            "sku": ["A-001"],
            "euAvailableStock": [10],
            "unit_cost_krw": [6_400],
            "stock_amount_krw": [64_000],
        }
    )

    row = build_sku_concentration_df(
        {"sales_detail": sales_detail, "eu_stock": eu_stock},
        eur_krw_rate=9_999,
    ).iloc[0]

    assert row["최근 3개월 판매금액(KRW)"] == 64_000
    assert row["재고 평가액(KRW)"] == 64_000


def test_enrich_order_review_amounts_matches_sku_with_trimmed_spaces_only():
    report = pd.DataFrame(
        {
            "SKU": ["ABC-001", "XYZ-002"],
            "EU unit price": [2.0, 3.0],
            "EU available stock": [10, 5],
        }
    )
    sales_detail = pd.DataFrame(
        {
            "sku": [" ABC-001 ", "abc-001", "XYZ-002"],
            "amount_krw": [1000, 2500, 4000],
        }
    )

    result = enrich_order_review_amounts(report, {"sales_detail": sales_detail}, eur_krw_rate=1500)
    sales_column = next(column for column in result.columns if "KRW" in str(column))

    # 판매상세 금액은 EUR 기준이므로 KRW 컬럼은 환율을 곱한 값이어야 한다.
    assert result.loc[0, sales_column] == 1000 * 1500
    assert result.loc[1, sales_column] == 4000 * 1500


def test_build_sku_concentration_uses_case_sensitive_raw_sales_and_stock_union():
    sales_detail = pd.DataFrame(
        {
            "sku": ["A-001", "a-001", "B-002"],
            "qty": [2, 3, 4],
            "amount_krw": [1000, 1500, 9000],
        }
    )
    eu_stock = pd.DataFrame(
        {
            "sku": ["A-001", "C-003"],
            "productName": ["A Cream", "C Toner"],
            "brand": ["Brand A", "Brand C"],
            "euAvailableStock": [10, 20],
            "unitPrice": [2, 3],
        }
    )

    result = build_sku_concentration_df({"sales_detail": sales_detail, "eu_stock": eu_stock}, eur_krw_rate=1500)
    by_sku = result.set_index("SKU")
    qty_col = result.columns[3]
    sales_amount_col = result.columns[5]
    stock_amount_col = result.columns[6]

    assert set(by_sku.index) == {"A-001", "a-001", "B-002", "C-003"}
    assert by_sku.loc["A-001", qty_col] == 2
    assert by_sku.loc["a-001", qty_col] == 3
    assert by_sku.loc["A-001", sales_amount_col] == 1000 * 1500
    assert by_sku.loc["a-001", sales_amount_col] == 1500 * 1500
    assert by_sku.loc["A-001", stock_amount_col] == 30000
    assert by_sku.loc["B-002", sales_amount_col] == 9000 * 1500
    assert by_sku.loc["C-003", stock_amount_col] == 90000


def test_recent_three_month_amounts_filter_sales_to_configured_period():
    sales_detail = pd.DataFrame(
        {
            "sku": ["A-001", "A-001", "A-001", "A-001"],
            "판매일": ["2026-01-31", "2026-02-01", "2026-04-30", "2026-05-01"],
            "qty": [100, 2, 3, 200],
            "amount_krw": [10_000, 200, 300, 20_000],
        }
    )
    eu_stock = pd.DataFrame(
        {
            "sku": ["A-001"],
            "productName": ["A Cream"],
            "brand": ["Brand A"],
            "euAvailableStock": [10],
            "unitPrice": [2],
        }
    )
    settings = {"period_start": "2026-02-01", "period_end": "2026-04-30"}

    concentration = build_sku_concentration_df(
        {"sales_detail": sales_detail, "eu_stock": eu_stock},
        eur_krw_rate=1500,
        settings=settings,
    ).set_index("SKU")
    enriched = enrich_order_review_amounts(
        pd.DataFrame({"SKU": ["A-001"]}),
        {"sales_detail": sales_detail},
        eur_krw_rate=1500,
        settings=settings,
    )

    assert concentration.loc["A-001", "최근 3개월 판매수량"] == 5
    assert concentration.loc["A-001", "최근 3개월 판매금액(KRW)"] == 500 * 1500
    assert enriched.loc[0, "최근 3개월 판매금액(KRW)"] == 500 * 1500


def test_sales_and_stock_amounts_share_one_currency():
    """판매금액과 재고 평가액이 같은 통화여야 두 카드를 나란히 비교할 수 있다.

    CMS ``amount_krw``(=환산금액)는 이름과 달리 EUR 정규화 값이다. 환율을 곱하지 않으면
    EUR 판매금액과 KRW 재고 평가액이 같은 ₩ 라벨로 나란히 표시된다.
    """
    rate = 1500
    unit_price = 4
    # 재고 1개, 3개월 동안 그 재고와 같은 수량을 원가로 판 SKU. 두 금액이 같아야 한다.
    sales_detail = pd.DataFrame({"sku": ["A-001"], "qty": [10], "amount_krw": [10 * unit_price]})
    eu_stock = pd.DataFrame(
        {
            "sku": ["A-001"],
            "productName": ["A Cream"],
            "brand": ["Brand A"],
            "euAvailableStock": [10],
            "unitPrice": [unit_price],
        }
    )

    row = build_sku_concentration_df(
        {"sales_detail": sales_detail, "eu_stock": eu_stock}, eur_krw_rate=rate
    ).iloc[0]

    assert row["최근 3개월 판매금액(KRW)"] == 10 * unit_price * rate
    assert row["재고 평가액(KRW)"] == 10 * unit_price * rate
    assert row["최근 3개월 판매금액(KRW)"] == row["재고 평가액(KRW)"]

    enriched = enrich_order_review_amounts(
        pd.DataFrame({"SKU": ["A-001"], "EU 입고단가": [unit_price], "EU 현지 재고": [10]}),
        {"sales_detail": sales_detail},
        eur_krw_rate=rate,
    )
    assert enriched.loc[0, "최근 3개월 판매금액(KRW)"] == enriched.loc[0, "재고 평가액(KRW)"]


def test_amounts_are_blank_without_an_exchange_rate():
    """환율이 없으면 두 금액 모두 비워 둔다. 한쪽만 남으면 통화가 섞인다."""
    sales_detail = pd.DataFrame({"sku": ["A-001"], "qty": [10], "amount_krw": [40]})
    eu_stock = pd.DataFrame({"sku": ["A-001"], "euAvailableStock": [10], "unitPrice": [4]})

    row = build_sku_concentration_df(
        {"sales_detail": sales_detail, "eu_stock": eu_stock}, eur_krw_rate=None
    ).iloc[0]

    assert row["최근 3개월 판매금액(KRW)"] == 0
    assert row["재고 평가액(KRW)"] == 0

    enriched = enrich_order_review_amounts(
        pd.DataFrame({"SKU": ["A-001"], "EU 입고단가": [4], "EU 현지 재고": [10]}),
        {"sales_detail": sales_detail},
        eur_krw_rate=None,
    )
    assert "최근 3개월 판매금액(KRW)" not in enriched.columns
    assert "재고 평가액(KRW)" not in enriched.columns


def test_sku_concentration_does_not_render_missing_identity_as_nan():
    sales_detail = pd.DataFrame({"sku": ["A-001"], "qty": [1], "amount_krw": [100]})
    eu_stock = pd.DataFrame(
        {
            "sku": ["A-001"],
            "productName": [float("nan")],
            "brand": [pd.NA],
            "euAvailableStock": [10],
            "unitPrice": [2],
        }
    )

    result = build_sku_concentration_df({"sales_detail": sales_detail, "eu_stock": eu_stock}, eur_krw_rate=1500)

    assert result.loc[0, "상품명"] == "-"
    assert result.loc[0, "브랜드"] == "-"
