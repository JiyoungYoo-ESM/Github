import pandas as pd

from core.eta import add_shipping_arrival_amount_columns


def test_cms_contract_krw_amount_is_used_without_current_rate_conversion() -> None:
    shipping = pd.DataFrame(
        {
            "수량": [2],
            "금액": [100],
            "CMS 원화 환산금액": [150_000],
        }
    )

    result = add_shipping_arrival_amount_columns(
        shipping,
        {"eur_krw_rate": 9_999},
    )

    assert result.loc[0, "도착 예정 금액_KRW"] == 150_000


def test_missing_cms_contract_amount_does_not_fall_back_to_current_rate() -> None:
    shipping = pd.DataFrame(
        {
            "수량": [2],
            "금액": [100],
            "CMS 원화 환산금액": [None],
        }
    )

    result = add_shipping_arrival_amount_columns(
        shipping,
        {"eur_krw_rate": 9_999},
    )

    assert result.loc[0, "도착 예정 금액_KRW"] == 0
