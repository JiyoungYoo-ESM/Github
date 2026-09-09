from __future__ import annotations

import pandas as pd

from core.common import MASTER_UNREGISTERED_REASON
from core.session import SessionContext
from core import export_excel_util as export_excel_util_mod, inventory as inventory_mod, kpi as kpi_mod, loaders as loaders_mod, preprocess as preprocess_mod, sales as sales_mod, transport as transport_mod

def prepare_open_po(open_po_df: pd.DataFrame) -> pd.DataFrame:
    df = open_po_df.copy()

    if "SKU" not in df.columns:
        sku_col = kpi_mod.find_column(df, ["SKU", "상품코드", "품목코드", "아이템코드", "itemcode"])
        if sku_col is not None:
            df = df.rename(columns={sku_col: "SKU"})

    if "미입고수량" not in df.columns:
        qty_col = kpi_mod.find_column(df, ["미입고수량", "미입고 수량", "미입고", "수량", "잔량", "openqty"])
        if qty_col is not None:
            df = df.rename(columns={qty_col: "미입고수량"})
    if "미입고수량" not in df.columns:
        po_col = kpi_mod.find_column(df, ["PO 수량", "발주수량", "poqty", "orderqty"])
        received_col = kpi_mod.find_column(df, ["입고 수량", "입고수량", "receivedqty"])
        if po_col is not None and received_col is not None:
            df["미입고수량"] = kpi_mod.to_number_series(df[po_col]) - kpi_mod.to_number_series(df[received_col])

    if "SKU" not in df.columns:
        return pd.DataFrame(columns=["SKU", "미입고수량"])
    if "미입고수량" not in df.columns:
        df["미입고수량"] = 0
    df["SKU"] = preprocess_mod.clean_identifier_series(df["SKU"])
    df = df[preprocess_mod.product_sku_mask(df["SKU"])].copy()
    df["미입고수량"] = kpi_mod.to_number_series(df["미입고수량"])
    df["미입고수량"] = df["미입고수량"].clip(lower=0)
    df["_sku_key"] = preprocess_mod.sku_group_key_series(df["SKU"])
    sku_rep = preprocess_mod.representative_sku_by_key(df["SKU"]).rename("SKU").reset_index()
    grouped = df.groupby("_sku_key", as_index=False).agg(미입고수량=("미입고수량", "sum")).merge(sku_rep, on="_sku_key", how="left")
    grouped["미입고금액"] = 0
    grouped["미입고 단가"] = 0
    return grouped[["SKU", "미입고수량", "미입고금액", "미입고 단가"]]


def get_open_po(context: SessionContext | None = None) -> pd.DataFrame:
    return prepare_open_po(loaders_mod.get_data_or_sample("open_po", loaders_mod.sample_open_po, context))


def first_non_empty(values: pd.Series) -> str:
    for value in values:
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "-"}:
            return export_excel_util_mod.excel_text_identifier(text)
    return ""


def first_non_empty_map(df: pd.DataFrame, group_col: str, value_col: str) -> dict[str, str]:
    if df.empty or group_col not in df.columns or value_col not in df.columns:
        return {}
    text = df[value_col].astype(str).str.strip()
    valid = text.ne("") & ~text.str.lower().isin({"nan", "none", "-"})
    grouped = (
        pd.DataFrame({group_col: df[group_col], "값": text.where(valid)})
        .groupby(group_col, sort=True)["값"]
        .first()
        .fillna("")
    )
    return grouped.map(export_excel_util_mod.excel_text_identifier).to_dict()


def raw_product_name_map(df: pd.DataFrame, sku_candidates: list[str]) -> dict[str, str]:
    sku_col = kpi_mod.find_column(df, sku_candidates)
    name_col = kpi_mod.find_column(df, ["상품명", "제품명", "품목명", "prod_nm", "productname", "productName", "itemname", "Item Name"])
    if sku_col is None or name_col is None:
        return {}
    names = pd.DataFrame(
        {
            "SKU": preprocess_mod.clean_identifier_series(df[sku_col]),
            "상품명": df[name_col].astype(str),
        }
    )
    names = names[preprocess_mod.product_sku_mask(names["SKU"])]
    if names.empty:
        return {}
    return first_non_empty_map(names, "SKU", "상품명")


def raw_product_attr_map(df: pd.DataFrame, sku_candidates: list[str], value_candidates: list[str]) -> dict[str, str]:
    sku_col = kpi_mod.find_column(df, sku_candidates)
    value_col = kpi_mod.find_column(df, value_candidates)
    if sku_col is None or value_col is None:
        return {}
    values = pd.DataFrame(
        {
            "SKU": preprocess_mod.clean_identifier_series(df[sku_col]),
            "값": df[value_col].astype(str),
        }
    )
    values = values[preprocess_mod.product_sku_mask(values["SKU"])]
    if values.empty:
        return {}
    return first_non_empty_map(values, "SKU", "값")


def sales_detail_validation_name_map(settings: dict, context: SessionContext | None = None) -> dict[str, str]:
    validation_settings = {
        **settings,
        "include_eu_pl_sales": True,
        "include_etc_sales": False,
    }
    sales = sales_mod.filtered_sales_detail_for_period(validation_settings, context)
    return raw_product_name_map(sales, ["SKU", "상품코드", "품목코드", "itemcode"])


def to_float_value(value: object, default: float = 0.0) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    return default if pd.isna(parsed) else float(parsed)


def classify_inventory_operation(available_qty: object, recent_sales_qty: object, shipping_qty: object, open_po_qty: object) -> str:
    available = to_float_value(available_qty)
    sales = to_float_value(recent_sales_qty)
    shipping = to_float_value(shipping_qty)
    open_po = to_float_value(open_po_qty)
    if available > 0:
        return "가용재고 있음"
    if sales > 0 and shipping > 0:
        return "가용재고 0 / 운송중 도착 대기"
    if sales > 0 and shipping <= 0:
        return "가용재고 0 / 발주 필요"
    if sales <= 0 and shipping > 0:
        return "가용재고 0 / 입고 예정"
    if open_po > 0:
        return "가용재고 0 / 미입고 대기"
    return "가용재고 0 / 관찰 SKU"


def build_inventory_decision_memo(row: pd.Series) -> str:
    registration = str(row.get("SKU등록상태", ""))
    available = to_float_value(row.get("EU 현지 가용수량", 0))
    recent_sales = to_float_value(row.get("분류용 최근판매수량", row.get("최근 3개월 판매수량", 0)))
    shipping_qty = to_float_value(row.get("운송중 수량", 0))
    open_po_qty = to_float_value(row.get("미입고수량", 0))
    if registration != "정상등록":
        return "재고 파일에는 없으나 운송중/판매 이력이 있어 상품코드 확인 필요"
    if available > 0:
        return "정상등록 SKU이며 가용재고가 있어 일반 발주검토 대상"
    if recent_sales > 0 and shipping_qty > 0:
        return "정상등록 SKU이나 현재 가용재고 0. 최근 판매이력과 운송중 물량이 있어 쇼티지/ETA 검토 대상"
    if recent_sales > 0 and shipping_qty <= 0:
        return "정상등록 SKU이나 현재 가용재고 0. 최근 판매이력은 있으나 운송중 물량이 없어 발주 필요"
    if shipping_qty > 0:
        return "정상등록 SKU이나 현재 가용재고 0. 판매이력은 없지만 운송중 물량이 있어 입고 예정 SKU로 모니터링"
    if open_po_qty > 0:
        return "정상등록 SKU이나 현재 가용재고 0. 미입고 발주가 있어 입고 확정 여부 확인 필요"
    return "정상등록 SKU이나 현재 가용재고 0. 판매/운송/미입고 이력이 없어 관찰 SKU"


def build_inventory_decision_short_memo(row: pd.Series) -> str:
    registration = str(row.get("SKU등록상태", ""))
    if registration != "정상등록":
        return "상품코드 확인필요"
    operation = str(row.get("재고운영상태", ""))
    if "가용재고 있음" in operation:
        return "정상"
    if "운송중 도착 대기" in operation:
        return "가용0 / ETA대기"
    if "발주 필요" in operation or "추가 발주 검토" in operation:
        return "가용0 / 발주검토"
    if "입고 예정" in operation:
        return "가용0 / 입고예정"
    if "미입고 대기" in operation:
        return "가용0 / 미입고대기"
    if "관찰 SKU" in operation:
        return "가용0 / 관찰"
    return operation or "-"


def build_master_unregistered_sku_df(settings: dict, context: SessionContext | None = None) -> pd.DataFrame:
    master = preprocess_mod.prepare_eu_stock(
        inventory_mod.get_eu_stock(context),
        pa_ca_sales_col=settings.get("pa_ca_sales_column_override"),
    )
    master_codes = set(master["상품코드"].astype(str).str.strip()) if "상품코드" in master.columns else set()
    master_codes.discard("")
    shipping = transport_mod.get_shipping(settings, context)
    shipping = shipping[transport_mod.recognized_transport_mask(shipping)].copy()
    def first_sorted_unique(values: pd.Series) -> str:
        unique_values = sorted({str(value).strip() for value in values if str(value).strip() and str(value).strip().lower() != "nan"})
        return unique_values[0] if unique_values else ""

    def joined_unique(values: pd.Series) -> str:
        unique_values = sorted({str(value).strip() for value in values if str(value).strip() and str(value).strip().lower() != "nan"})
        return ", ".join(unique_values)

    if shipping.empty:
        shipping_qty = pd.Series(dtype=float)
        shipping_names: dict[str, str] = {}
        shipping_brands: dict[str, str] = {}
        shipping_dates: dict[str, str] = {}
        shipping_etas: dict[str, str] = {}
        shipping_modes: dict[str, str] = {}
    else:
        shipping = shipping[preprocess_mod.product_sku_mask(shipping["SKU"])].copy()
        shipping_qty = pd.to_numeric(shipping["수량"], errors="coerce").fillna(0).groupby(shipping["SKU"]).sum()
        shipping_names = first_non_empty_map(shipping, "SKU", "상품명") if "상품명" in shipping.columns else {}
        shipping_brands = first_non_empty_map(shipping, "SKU", "브랜드") if "브랜드" in shipping.columns else {}
        shipping_dates = shipping.groupby("SKU")["출고일"].agg(first_sorted_unique).to_dict() if "출고일" in shipping.columns else {}
        shipping_etas = shipping.groupby("SKU")["ETA"].agg(first_sorted_unique).to_dict() if "ETA" in shipping.columns else {}
        shipping_modes = shipping.groupby("SKU")["운송수단"].agg(joined_unique).to_dict() if "운송수단" in shipping.columns else {}

    open_po = prepare_open_po(loaders_mod.get_order_review_data_or_empty("open_po", loaders_mod.sample_open_po, context))
    if open_po.empty:
        open_po_qty = pd.Series(dtype=float)
    else:
        open_po = open_po[preprocess_mod.product_sku_mask(open_po["SKU"])].copy()
        open_po_qty = pd.to_numeric(open_po["미입고수량"], errors="coerce").fillna(0).groupby(open_po["SKU"]).sum()
    open_po_names = raw_product_name_map(
        loaders_mod.get_data_or_sample("open_po", loaders_mod.sample_open_po, context),
        ["SKU", "상품코드", "품목코드", "아이템코드", "itemcode"],
    )
    open_po_brands = raw_product_attr_map(
        loaders_mod.get_data_or_sample("open_po", loaders_mod.sample_open_po, context),
        ["SKU", "상품코드", "품목코드", "아이템코드", "itemcode"],
        ["브랜드", "brand"],
    )

    sales_qty_df = sales_mod.sales_detail_validation_qty_by_sku(settings, context)
    if sales_qty_df.empty:
        sales_qty = pd.Series(dtype=float)
    else:
        sales_qty_df = sales_qty_df[preprocess_mod.product_sku_mask(sales_qty_df["SKU"])].copy()
        sales_qty = pd.to_numeric(sales_qty_df["판매내역상세_3M_판매수량"], errors="coerce").fillna(0).groupby(sales_qty_df["SKU"]).sum()
    sales_names = sales_detail_validation_name_map(settings, context)
    sales_brands = raw_product_attr_map(
        sales_mod.filtered_sales_detail_by_biz(
            {**settings, "include_eu_pl_sales": True, "include_etc_sales": False},
            context,
            source="data",
        ),
        ["SKU", "상품코드", "품목코드", "itemcode"],
        ["브랜드", "brand"],
    )

    source_codes = set(shipping_qty.index.astype(str)) | set(open_po_qty.index.astype(str)) | set(sales_qty.index.astype(str))
    missing_codes = sorted(code for code in source_codes if code and code not in master_codes)

    rows: list[dict[str, object]] = []
    for code in missing_codes:
        has_shipping = code in shipping_qty.index
        has_open_po = code in open_po_qty.index
        has_sales = code in sales_qty.index
        name = shipping_names.get(code) or open_po_names.get(code) or sales_names.get(code) or ""
        brand = shipping_brands.get(code) or open_po_brands.get(code) or sales_brands.get(code) or ""
        sales_value = float(sales_qty.get(code, 0))
        shipping_value = float(shipping_qty.get(code, 0))
        open_po_value = float(open_po_qty.get(code, 0))
        ship_date = shipping_dates.get(code, "") if has_shipping else ""
        ship_eta = shipping_etas.get(code, "") if has_shipping else ""
        ship_mode = shipping_modes.get(code, "") if has_shipping else ""
        source_labels = []
        if has_sales:
            source_labels.append("판매내역")
        if has_shipping:
            source_labels.append("운송중")
        if has_open_po:
            source_labels.append("미입고")
        source_text = "/".join(source_labels)
        source_phrase = "판매내역에 존재" if source_text == "판매내역" else f"{source_text} 내역에 존재"
        reason = f"현지 재고 목록 미존재 / {source_phrase}" if source_text else MASTER_UNREGISTERED_REASON
        if has_shipping:
            check_type = "입고 예정 SKU"
        elif has_open_po:
            check_type = "미입고 발주 SKU"
        else:
            check_type = "판매이력 SKU"
        rows.append(
            {
                "상품코드": code,
                "상품명": name,
                "브랜드": brand,
                "발견 원본": source_text,
                "최근 판매수량": sales_value,
                "운송중 수량": shipping_value,
                "미입고 수량": open_po_value,
                "출고일": ship_date,
                "예상 입고일": ship_eta,
                "운송수단": ship_mode,
                "확인 구분": check_type,
                "확인필요 사유": reason,
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "상품코드", "상품명", "브랜드", "발견 원본", "최근 판매수량", "운송중 수량",
            "미입고 수량", "출고일", "예상 입고일", "운송수단", "확인 구분", "확인필요 사유",
        ],
    )

