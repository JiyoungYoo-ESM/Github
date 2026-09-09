from __future__ import annotations

import pandas as pd
from core.session import SessionContext
from core import loaders as loaders_mod, preprocess as preprocess_mod

def get_eu_stock(context: SessionContext | None = None) -> pd.DataFrame:
    eu_stock_df = loaders_mod.get_data_or_sample("eu_stock", loaders_mod.sample_eu_stock, context)
    return eu_stock_df


def get_hq_eu_stock(context: SessionContext | None = None) -> pd.DataFrame:
    hq_eu_stock_df = loaders_mod.get_data_or_sample("hq_eu_stock", loaders_mod.sample_hq_eu_stock, context)
    return hq_eu_stock_df


def get_inventory(context: SessionContext | None = None) -> pd.DataFrame:
    """이전 탭 호환용: EU 현지 재고를 기본 재고로 사용한다."""
    return preprocess_mod.prepare_eu_stock(get_eu_stock(context)).rename(columns={"EU 현지 가용수량": "현재 가용수량"})

