import pandas as pd
import os
from core import inbound, loaders, order_review_report, validation
from core.session import SessionContext

FIX_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name: str) -> pd.DataFrame:
    path = os.path.join(FIX_DIR, f"{name}.csv")
    return pd.read_csv(path)


def test_dras01_goodie_bag_regression(tmp_path, monkeypatch):
    # Load fixtures
    uploaded = {
        "shipping": load_fixture("shipping"),
        "eu_stock": load_fixture("eu_stock"),
        "sales_detail": load_fixture("sales_detail"),
        "open_po": load_fixture("open_po"),
    }
    context = SessionContext(uploaded_data=uploaded)

    shipping = loaders.get_data_or_sample("shipping", loaders.sample_shipping, context)
    assert int(shipping["수량"].sum()) == 18019

    settings = validation.default_settings_for_validation()
    master_unregistered = inbound.build_master_unregistered_sku_df(settings, context)

    # Expect the DRAS01-M60EU to be separated
    assert len(master_unregistered) == 1
    row = master_unregistered.iloc[0]
    assert row["상품코드"] == "DRAS01-M60EU"
    assert int(row["운송중 수량"]) == 800

    # Master-missing SKU is not a human data-entry error, so it no longer appears
    # on the check-required sheet.
    check_df = order_review_report.build_check_required_sheet_df(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), master_unregistered)
    assert check_df.empty

    # Remaining normal shipping sum
    normal_shipping_sum = shipping[shipping["SKU"] != "DRAS01-M60EU"]["수량"].sum()
    assert normal_shipping_sum == 17219
