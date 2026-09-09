"""Order-review table shaping, SKU concentration, and review-required metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.inbound import build_master_unregistered_sku_df
from core.order_review_report import (
    _strip_check_required_internal_columns,
    build_check_required_sheet_df,
    build_excluded_order_review_df,
    build_human_data_issue_df,
)
from core.session import SessionContext
from core.transport import unrecognized_transport_report_df
from core.validation import apply_order_review_filters

from backend.services.category_corrections import normalize_sku_key
from backend.services.dataframe_utils import first_existing_column


def order_template_review_basis(combined_review: pd.DataFrame, filtered_review: pd.DataFrame, settings: dict[str, object]) -> pd.DataFrame:
    """Return the row basis used by the ESM reference order template.

    The reference workbook calculates 재고 ETA/발주/보고서 from every row in the
    SKO stock file, so excluded SKUs (zero unit price, low sales, unregistered
    codes) stay in the population and keep their stock-adequacy signals. Their
    order quantity stays zero - see ``ORDER_EXCLUDED_REVIEW_STATUSES`` - so the
    table, the summary totals and the dashboard SKU counts share one basis.
    """
    base = pd.DataFrame(combined_review).copy()
    if base.empty:
        return pd.DataFrame(filtered_review).copy()
    if "재고파일 존재여부" in base.columns:
        stock_file_rows = base["재고파일 존재여부"].astype(str).str.strip().eq("Y")
        if bool(stock_file_rows.any()):
            return apply_order_review_filters(base[stock_file_rows].copy(), settings)
    return pd.DataFrame(filtered_review).copy()


def _eur_krw_rate(eur_krw_rate: float | None) -> float:
    try:
        rate = float(eur_krw_rate or 0)
    except (TypeError, ValueError):
        return 0.0
    return rate if rate > 0 else 0.0


def _sales_amount_krw(sales_amount: pd.Series) -> pd.Series:
    """Return authoritative per-transaction KRW sales without re-conversion."""
    return pd.to_numeric(sales_amount, errors="coerce").fillna(0)


def _numeric_series(df: pd.DataFrame, candidates: list[str], default: float = 0.0) -> pd.Series:
    column = first_existing_column(df, candidates)
    if column is None:
        return pd.Series(default, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce").fillna(default)


def _sales_detail_within_period(
    uploaded_data: dict[str, pd.DataFrame],
    settings: dict[str, object] | None = None,
) -> pd.DataFrame:
    """Return sales detail restricted to the configured analytical period.

    Some integrations already provide a period extract and therefore omit a date
    column. In that case the extract is preserved. When dates are available, the
    period contract is enforced here so every "최근 3개월" amount/quantity uses
    the same inclusive boundaries as the order-review calculation.
    """
    sales_detail = pd.DataFrame(uploaded_data.get("sales_detail", pd.DataFrame())).copy()
    if sales_detail.empty or not settings:
        return sales_detail

    date_col = first_existing_column(
        sales_detail,
        ["판매일", "판매일자", "출고일", "출고일자", "출고 일자", "일자", "date", "Date"],
    )
    if date_col is None:
        return sales_detail

    period_start = pd.to_datetime(settings.get("period_start"), errors="coerce")
    period_end = pd.to_datetime(settings.get("period_end"), errors="coerce")
    if pd.isna(period_start) or pd.isna(period_end):
        return sales_detail

    sold_at = pd.to_datetime(sales_detail[date_col], errors="coerce").dt.normalize()
    start_at = pd.Timestamp(period_start).normalize()
    end_at = pd.Timestamp(period_end).normalize()
    if start_at > end_at:
        return sales_detail.iloc[0:0].copy()
    return sales_detail[sold_at.between(start_at, end_at, inclusive="both")].copy()


def enrich_order_review_amounts(
    report_df: pd.DataFrame,
    uploaded_data: dict[str, pd.DataFrame],
    eur_krw_rate: float | None,
    settings: dict[str, object] | None = None,
) -> pd.DataFrame:
    """Attach actual KRW sales and stock valuation for SKU concentration screens."""
    out = pd.DataFrame(report_df).copy()
    if out.empty:
        return out

    report_sku_col = first_existing_column(out, ["상품코드", "SKU", "sku"])
    if report_sku_col is None:
        return out

    rate = _eur_krw_rate(eur_krw_rate)
    report_sku = out[report_sku_col].map(normalize_sku_key)
    sales_detail = _sales_detail_within_period(uploaded_data, settings)
    if not sales_detail.empty:
        sales_sku_col = first_existing_column(sales_detail, ["상품코드", "SKU", "prod_cd", "sku"])
        actual_krw_col = first_existing_column(
            sales_detail,
            ["실제 원화 환산금액", "amount_krw_actual"],
        )
        legacy_amount_col = first_existing_column(
            sales_detail,
            ["환산금액", "amount_krw", "금액", "amount"],
        )
        sales_amount_col = actual_krw_col or legacy_amount_col
        if sales_sku_col and sales_amount_col and (actual_krw_col is not None or rate > 0):
            sales_key = sales_detail[sales_sku_col].map(normalize_sku_key)
            sales_amount = pd.to_numeric(sales_detail[sales_amount_col], errors="coerce").fillna(0)
            if actual_krw_col is None:
                sales_amount = sales_amount * rate
            sales_by_sku = sales_amount.groupby(sales_key).sum()
            out["최근 3개월 판매금액(KRW)"] = _sales_amount_krw(report_sku.map(sales_by_sku))

    stock_amount_col = first_existing_column(out, ["CMS 재고금액(KRW)"])
    if stock_amount_col is not None:
        out["재고 평가액(KRW)"] = pd.to_numeric(out[stock_amount_col], errors="coerce").fillna(0)
    elif rate > 0:
        available_qty = _numeric_series(out, ["EU 현지 재고", "유럽 가용재고", "EU 현지 가용수량", "EU 가용재고"])
        unit_price_eur = _numeric_series(out, ["EU 입고단가(EUR)", "EU 입고단가", "입고단가"])
        out["재고 평가액(KRW)"] = available_qty * unit_price_eur * rate

    return out


def _first_text_by_sku(df: pd.DataFrame, sku_col: str, value_col: str | None) -> dict[str, str]:
    if value_col is None:
        return {}
    frame = pd.DataFrame(df)
    if frame.empty:
        return {}
    keyed = frame.assign(_sku_key=frame[sku_col].map(normalize_sku_key))
    values: dict[str, str] = {}
    for key, value in zip(keyed["_sku_key"], keyed[value_col], strict=False):
        try:
            is_missing = bool(pd.isna(value))
        except (TypeError, ValueError):
            is_missing = False
        if is_missing:
            continue
        text = str(value).strip()
        if text.lower() in {"nan", "none", "<na>"}:
            continue
        if key and text and key not in values:
            values[str(key)] = text
    return values


def build_sku_concentration_df(
    uploaded_data: dict[str, pd.DataFrame],
    eur_krw_rate: float | None,
    settings: dict[str, object] | None = None,
) -> pd.DataFrame:
    """Build SKU concentration rows from raw sales detail and EU stock data, not order-review rows."""
    sales_detail = _sales_detail_within_period(uploaded_data, settings)
    eu_stock = pd.DataFrame(uploaded_data.get("eu_stock", pd.DataFrame()))
    prod_list = pd.DataFrame(uploaded_data.get("prod_list", pd.DataFrame()))
    rate = _eur_krw_rate(eur_krw_rate)

    sales_by_sku = pd.DataFrame(columns=["_sku_key", "recentSalesQty", "salesAmount"])
    if not sales_detail.empty:
        sales_sku_col = first_existing_column(sales_detail, ["상품코드", "SKU", "품목코드", "prod_cd", "sku"])
        sales_qty_col = first_existing_column(sales_detail, ["판매수량", "수량", "qty", "recentSalesQty"])
        actual_krw_col = first_existing_column(
            sales_detail,
            ["실제 원화 환산금액", "amount_krw_actual"],
        )
        legacy_amount_col = first_existing_column(
            sales_detail,
            ["환산금액", "amount_krw", "금액", "amount"],
        )
        sales_amount_col = actual_krw_col or legacy_amount_col
        if sales_sku_col and (sales_qty_col or sales_amount_col):
            sales_amount = (
                _sales_amount_krw(sales_detail[sales_amount_col])
                if sales_amount_col
                else pd.Series(0, index=sales_detail.index, dtype="float64")
            )
            if sales_amount_col and actual_krw_col is None:
                sales_amount = sales_amount * rate
            sales_frame = pd.DataFrame(
                {
                    "_sku_key": sales_detail[sales_sku_col].map(normalize_sku_key),
                    "recentSalesQty": pd.to_numeric(sales_detail[sales_qty_col], errors="coerce").fillna(0) if sales_qty_col else 0,
                    "salesAmount": sales_amount,
                }
            )
            sales_by_sku = sales_frame[sales_frame["_sku_key"] != ""].groupby("_sku_key", as_index=False).sum()

    stock_by_sku = pd.DataFrame(columns=["_sku_key", "euAvailableStock", "unitPrice", "stockAmount"])
    stock_names: dict[str, str] = {}
    stock_brands: dict[str, str] = {}
    if not eu_stock.empty:
        stock_sku_col = first_existing_column(eu_stock, ["상품코드", "SKU", "품목코드", "prod_cd", "sku"])
        stock_qty_col = first_existing_column(eu_stock, ["EU 현지 가용수량", "EU 가용재고", "유럽 가용재고", "가용수량", "재고수량", "stock_qty", "avbl_qty", "euAvailableStock"])
        unit_price_krw_col = first_existing_column(eu_stock, ["CMS 원화 입고단가", "unit_cost_krw"])
        legacy_unit_price_col = first_existing_column(
            eu_stock,
            ["현지 입고단가", "EU 입고단가", "unitPrice", "stock_ucost"],
        )
        stock_amount_col = first_existing_column(eu_stock, ["CMS 재고금액(KRW)", "stock_amount_krw"])
        name_col = first_existing_column(eu_stock, ["상품명", "품목명", "prod_nm", "productName", "name"])
        brand_col = first_existing_column(eu_stock, ["브랜드", "브랜드명", "brand_nm", "brand"])
        if stock_sku_col:
            stock_qty = pd.to_numeric(eu_stock[stock_qty_col], errors="coerce").fillna(0) if stock_qty_col else pd.Series(0, index=eu_stock.index)
            if unit_price_krw_col:
                unit_price = pd.to_numeric(eu_stock[unit_price_krw_col], errors="coerce").fillna(0)
            elif legacy_unit_price_col and rate > 0:
                unit_price = pd.to_numeric(eu_stock[legacy_unit_price_col], errors="coerce").fillna(0) * rate
            else:
                unit_price = pd.Series(0, index=eu_stock.index, dtype="float64")
            stock_amount = pd.to_numeric(eu_stock[stock_amount_col], errors="coerce").fillna(0) if stock_amount_col else stock_qty * unit_price
            stock_frame = pd.DataFrame(
                {
                    "_sku_key": eu_stock[stock_sku_col].map(normalize_sku_key),
                    "euAvailableStock": stock_qty,
                    "unitPriceWeighted": unit_price * stock_qty,
                    "stockAmount": stock_amount,
                }
            )
            grouped_stock = stock_frame[stock_frame["_sku_key"] != ""].groupby("_sku_key", as_index=False).sum()
            grouped_stock["unitPrice"] = grouped_stock.apply(
                lambda row: row["unitPriceWeighted"] / row["euAvailableStock"] if row["euAvailableStock"] else 0,
                axis=1,
            )
            stock_by_sku = grouped_stock.drop(columns=["unitPriceWeighted"])
            stock_names = _first_text_by_sku(eu_stock, stock_sku_col, name_col)
            stock_brands = _first_text_by_sku(eu_stock, stock_sku_col, brand_col)

    master_names: dict[str, str] = {}
    master_brands: dict[str, str] = {}
    if not prod_list.empty:
        master_sku_col = first_existing_column(prod_list, ["상품코드", "SKU", "품목코드", "prod_cd", "sku"])
        if master_sku_col:
            master_name_col = first_existing_column(prod_list, ["상품명", "품목명", "prod_nm", "productName", "name"])
            master_brand_col = first_existing_column(prod_list, ["브랜드", "브랜드명", "brand_nm", "brand"])
            master_names = _first_text_by_sku(prod_list, master_sku_col, master_name_col)
            master_brands = _first_text_by_sku(prod_list, master_sku_col, master_brand_col)

    merged = pd.merge(sales_by_sku, stock_by_sku, on="_sku_key", how="outer").fillna(0)
    if merged.empty:
        return pd.DataFrame()

    records = []
    for row in merged.to_dict(orient="records"):
        sku = str(row["_sku_key"])
        records.append(
            {
                "SKU": sku,
                "상품명": stock_names.get(sku) or master_names.get(sku) or "-",
                "브랜드": stock_brands.get(sku) or master_brands.get(sku) or "-",
                "최근 3개월 판매수량": float(row.get("recentSalesQty") or 0),
                "EU 현지 가용수량": float(row.get("euAvailableStock") or 0),
                "최근 3개월 판매금액(KRW)": float(row.get("salesAmount") or 0),
                "재고 평가액(KRW)": float(row.get("stockAmount") or 0),
                "EU 입고단가": float(row.get("unitPrice") or 0),
            }
        )
    return pd.DataFrame(records).sort_values("최근 3개월 판매금액(KRW)", ascending=False)


def check_required_sku_count(check_required_df: pd.DataFrame) -> int:
    if check_required_df.empty:
        return 0
    for column in ("SKU", "상품코드"):
        if column in check_required_df.columns:
            sku_count = int(check_required_df[column].dropna().astype(str).str.strip().replace("", np.nan).dropna().nunique())
            return sku_count if sku_count > 0 else int(len(check_required_df))
    return int(len(check_required_df))


def build_check_required_df(
    settings: dict[str, object],
    review: pd.DataFrame,
    excluded_review: pd.DataFrame,
    context: SessionContext | None = None,
) -> pd.DataFrame:
    excluded_df = build_excluded_order_review_df(excluded_review, settings)
    master_unregistered_df = build_master_unregistered_sku_df(settings, context)
    return _strip_check_required_internal_columns(
        build_check_required_sheet_df(
            pd.DataFrame(),
            unrecognized_transport_report_df(settings, context),
            excluded_df,
            master_unregistered_df,
            pd.DataFrame(),
            build_human_data_issue_df(settings, context),
        )
    )

__all__ = [
    "build_check_required_df",
    "build_sku_concentration_df",
    "check_required_sku_count",
    "enrich_order_review_amounts",
    "order_template_review_basis",
]

