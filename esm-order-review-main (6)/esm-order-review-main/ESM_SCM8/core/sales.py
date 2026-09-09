from __future__ import annotations

import pandas as pd
from core.session import SessionContext, ensure_session_context

from core.common import (
    SALES_BIZ_ALWAYS_EXCLUDE,
    SALES_BIZ_ALWAYS_INCLUDE,
)
from core import kpi as kpi_mod, loaders as loaders_mod, preprocess as preprocess_mod

def prepare_sales_detail(sales_df: pd.DataFrame) -> pd.DataFrame:
    df = sales_df.copy()
    rename_candidates = {
        "브랜드": ["브랜드", "brand"],
        "SKU": ["SKU", "상품코드", "품목코드", "아이템코드", "itemcode"],
        "바코드": ["바코드", "barcode", "ean", "jan"],
        "상품명": ["상품명", "제품명", "품목명", "itemname"],
        "판매 기준기간 판매량": ["판매 기준기간 판매량", "기준기간 판매량", "판매수량", "수량", "qty"],
        "최근 판매량": ["최근 판매량", "최근판매수량", "최근 수량", "recentqty"],
        "매출": ["매출", "환산금액", "판매금액", "금액", "출고금액", "amount"],
    }

    rename_map = {}
    for target, candidates in rename_candidates.items():
        if target not in df.columns:
            source = kpi_mod.find_column(df, candidates)
            if source is not None:
                rename_map[source] = target
    if rename_map:
        df = df.rename(columns=rename_map)

    defaults = {
        "브랜드": "-",
        "SKU": "",
        "바코드": "",
        "상품명": "-",
        "판매 기준기간 판매량": 0,
        "최근 판매량": 0,
        "매출": 0,
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    df["SKU"] = preprocess_mod.clean_identifier_series(df["SKU"])
    df["바코드"] = preprocess_mod.clean_identifier_series(df["바코드"])
    for col in ["판매 기준기간 판매량", "최근 판매량", "매출"]:
        df[col] = kpi_mod.to_number_series(df[col])
    return df


def get_sales_detail(context: SessionContext | None = None) -> pd.DataFrame:
    return prepare_sales_detail(loaders_mod.get_data_or_sample("sales_detail", loaders_mod.sample_sales_detail, context))


def normalize_biz_type(value: object) -> str:
    return str(value).strip().upper()


def sales_biz_type_label(settings: dict) -> str:
    if str(settings.get("entity_code") or "PL").strip().upper() == "USA":
        return (
            "현재 산출 기준: US-DOMESTIC, US-OVERSEAS, KR-OVERSEAS, 자사간거래 포함 / "
            "US-STAFF, FREE SAMPLE 제외 / "
            "US-DOMESTIC·US-OVERSEAS 음수 금액은 순매출 포함"
        )
    included = ["EU-OVERSEAS"]
    net_sales_types = ["EU-OVERSEAS"]
    if settings.get("include_eu_pl_sales", True):
        included.append("EU-PL")
        net_sales_types.append("EU-PL")
    included.extend(["KR-OVERSEAS", "자사간거래"])
    if settings.get("include_etc_sales", False):
        included.append("ETC")
    excluded = ["STAFFSALES", "샘플", "반품", "추후상계"]
    if not settings.get("include_eu_pl_sales", True):
        excluded.insert(0, "EU-PL")
    if not settings.get("include_etc_sales", False):
        excluded.insert(0, "ETC")
    label = (
        f"현재 산출 기준: {', '.join(included)} 포함 / "
        f"{', '.join(excluded)} 제외"
    )
    return f"{label} / {'·'.join(net_sales_types)} 음수 금액은 순매출 포함"


def sales_biz_type_note() -> str:
    return (
        "※ EU-PL 제외/포함 여부는 설정에서 변경 가능, "
        "EU-OVERSEAS 및 포함 설정된 EU-PL의 음수 금액은 정상 매출과 상계하여 순매출에 포함"
    )


def filter_sales_by_biz_type(sales_df: pd.DataFrame, settings: dict) -> pd.DataFrame:
    df = sales_df.copy()
    biz_col = kpi_mod.find_column(df, ["Biz Type", "BizType", "비즈타입", "거래유형"])
    if biz_col is None:
        return df

    biz = df[biz_col].map(normalize_biz_type)
    entity_code = str(settings.get("entity_code") or "PL").strip().upper()
    if entity_code == "USA":
        allowed = {
            "US-DOMESTIC",
            "US-OVERSEAS",
            "KR-OVERSEAS",
            "자사간거래",
        }
    else:
        allowed = set(SALES_BIZ_ALWAYS_INCLUDE)
        if settings.get("include_eu_pl_sales", True):
            allowed.add("EU-PL")
        if settings.get("include_etc_sales", False):
            allowed.add("ETC")

    accounting_keywords = [
        "TP ADJUST",
        "TP-ADJUSTMENT",
        "ADVANCE_TO_RELATED_PARTY",
        "ADVANCE TO RELATED PARTY",
        "CUM",
        "기타제조사",
    ]
    excluded = biz.isin(SALES_BIZ_ALWAYS_EXCLUDE)
    excluded = excluded | biz.str.contains(
        "STAFF|FREE\\s*SAMPLE|반품|추후상계",
        regex=True,
        na=False,
    )
    for keyword in accounting_keywords:
        excluded = excluded | biz.str.contains(keyword, regex=False, na=False)

    amount_cols = [
        col
        for col in ["환산금액", "판매금액", "금액", "매출", "amount_krw", "amount"]
        if col in df.columns
    ]
    if amount_cols:
        negative_amount = pd.Series(False, index=df.index)
        for col in amount_cols:
            negative_amount = negative_amount | (kpi_mod.to_number_series(df[col]) < 0)
        include_as_net_sales = biz.isin(
            {"US-DOMESTIC", "US-OVERSEAS"}
            if entity_code == "USA"
            else {"EU-OVERSEAS", "EU-PL"}
        )
        excluded = excluded | (negative_amount & ~include_as_net_sales)

    return df[biz.isin(allowed) & ~excluded].copy()


def negative_amount_positive_qty_mask(
    amount: pd.Series,
    qty: pd.Series,
) -> pd.Series:
    """Identify incident-style rows that are not physical demand."""

    return (kpi_mod.to_number_series(amount) < 0) & (
        kpi_mod.to_number_series(qty) > 0
    )


def exclude_negative_amount_positive_qty_for_demand(
    sales_df: pd.DataFrame,
) -> pd.DataFrame:
    """Remove incident rows from demand quantities while keeping raw sales intact."""

    df = sales_df.copy()
    qty_col = kpi_mod.find_column(
        df,
        ["qty", "quantity", "\uc218\ub7c9", "\ud310\ub9e4\uc218\ub7c9"],
    )
    amount_col = kpi_mod.find_column(
        df,
        [
            "amount",
            "amount_krw",
            "\uae08\uc561",
            "\ud310\ub9e4\uae08\uc561",
            "\ud658\uc0b0\uae08\uc561",
            "\ub9e4\ucd9c",
        ],
    )
    if qty_col is None or amount_col is None:
        return df
    incident = negative_amount_positive_qty_mask(df[amount_col], df[qty_col])
    return df.loc[~incident].copy()


def _sales_filter_key(settings: dict) -> tuple[str, bool, bool]:
    return (
        str(settings.get("entity_code") or "PL").strip().upper(),
        bool(settings.get("include_eu_pl_sales", True)),
        bool(settings.get("include_etc_sales", False)),
    )


def _date_key(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _sales_source_df(source: str, context: SessionContext) -> pd.DataFrame:
    if source == "data":
        return loaders_mod.get_data_or_sample("sales_detail", loaders_mod.sample_sales_detail, context)
    return loaders_mod.get_order_review_data_or_empty("sales_detail", loaders_mod.sample_sales_detail, context)


def filtered_sales_detail_by_biz(
    settings: dict,
    context: SessionContext | None = None,
    *,
    source: str = "order_review",
) -> pd.DataFrame:
    context = ensure_session_context(context)
    cache_key = ("biz", source, *_sales_filter_key(settings))
    cached = context.sales_detail_cache.get(cache_key)
    if cached is None:
        cached = filter_sales_by_biz_type(_sales_source_df(source, context), settings)
        context.sales_detail_cache[cache_key] = cached
    return cached.copy(deep=False)


def filtered_sales_detail_for_period(
    settings: dict,
    context: SessionContext | None = None,
    *,
    source: str = "order_review",
) -> pd.DataFrame:
    context = ensure_session_context(context)
    cache_key = (
        "period",
        source,
        *_sales_filter_key(settings),
        _date_key(settings.get("period_start")),
        _date_key(settings.get("period_end")),
    )
    cached = context.sales_detail_cache.get(cache_key)
    if cached is None:
        sales = filtered_sales_detail_by_biz(settings, context, source=source)
        date_col = kpi_mod.find_column(sales, ["판매일", "판매일자", "출고일", "출고일자", "일자", "date"])
        if date_col is not None:
            sold_at = kpi_mod.parse_date_series(sales[date_col])
            start_at = pd.to_datetime(settings["period_start"])
            end_at = pd.to_datetime(settings["period_end"])
            sales = sales[(sold_at >= start_at) & (sold_at <= end_at)].copy()
        cached = sales
        context.sales_detail_cache[cache_key] = cached
    return cached.copy(deep=False)


def recent_sales_qty_by_sku(settings: dict, context: SessionContext | None = None) -> pd.DataFrame:
    context = ensure_session_context(context)
    has_uploaded_sales = "sales_detail" in context.uploaded_data
    source_sales = filtered_sales_detail_for_period(settings, context)
    sales = source_sales
    sku_col = kpi_mod.find_column(sales, ["SKU", "상품코드", "품목코드", "itemcode"])
    qty_col = next((col for col in sales.columns if kpi_mod.compact_column_name(col) == kpi_mod.compact_column_name("수량")), None)
    if qty_col is None:
        if has_uploaded_sales:
            return pd.DataFrame(columns=["SKU", "최근 3개월 판매수량"])
        qty_col = kpi_mod.find_column(sales, ["판매 기준기간 판매량", "기준기간 판매량", "최근 판매량", "판매수량", "qty"])
    if sku_col is None or qty_col is None:
        return pd.DataFrame(columns=["SKU", "최근 3개월 판매수량"])

    df = source_sales[[sku_col, qty_col]].copy()
    df["SKU"] = preprocess_mod.clean_identifier_series(df[sku_col])
    df["최근 3개월 판매수량"] = kpi_mod.to_number_series(df[qty_col])
    df = df[preprocess_mod.product_sku_mask(df["SKU"])]
    df["_sku_key"] = preprocess_mod.sku_group_key_series(df["SKU"])
    sku_rep = preprocess_mod.representative_sku_by_key(df["SKU"]).rename("SKU").reset_index()

    # Keep incident-only SKUs in the result with zero demand. Otherwise a
    # caller that falls back per SKU could accidentally reintroduce their raw
    # stock/API quantity after the incident row was excluded.
    demand_sales = exclude_negative_amount_positive_qty_for_demand(source_sales)
    demand = demand_sales[[sku_col, qty_col]].copy()
    demand["SKU"] = preprocess_mod.clean_identifier_series(demand[sku_col])
    demand["최근 3개월 판매수량"] = kpi_mod.to_number_series(demand[qty_col])
    demand = demand[preprocess_mod.product_sku_mask(demand["SKU"])]
    demand["_sku_key"] = preprocess_mod.sku_group_key_series(demand["SKU"])
    grouped = demand.groupby("_sku_key", as_index=False)["최근 3개월 판매수량"].sum()
    return (
        sku_rep.merge(grouped, on="_sku_key", how="left")
        .fillna({"최근 3개월 판매수량": 0.0})
        [["SKU", "최근 3개월 판매수량"]]
    )


def sales_detail_validation_qty_by_sku(settings: dict, context: SessionContext | None = None) -> pd.DataFrame:
    validation_settings = {
        **settings,
        "include_eu_pl_sales": True,
        "include_etc_sales": False,
    }
    out = recent_sales_qty_by_sku(validation_settings, context)
    if out.empty:
        return pd.DataFrame(columns=["SKU", "판매내역상세_3M_판매수량"])
    return out.rename(columns={"최근 3개월 판매수량": "판매내역상세_3M_판매수량"})


def get_hq_to_eu_sales_detail(context: SessionContext | None = None) -> pd.DataFrame:
    return loaders_mod.get_data_or_sample("hq_to_eu_sales_detail", loaders_mod.sample_hq_to_eu_sales_detail, context)

