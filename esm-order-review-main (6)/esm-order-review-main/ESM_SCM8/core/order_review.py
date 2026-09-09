from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from core.session import SessionContext, ensure_session_context

from core.common import (
    _DEFAULT_EUR_KRW_RATE,
    _HQ_STOCK_EUR_VALUE_CANDIDATES,
    _HQ_STOCK_EXPLICIT_EUR_VALUE_CANDIDATES,
    _HQ_STOCK_HOLD_CANDIDATES,
    _HQ_STOCK_PRICE_CANDIDATES,
    _HQ_STOCK_QTY_CANDIDATES,
    _SEA_CONTAINER_EUR_CANDIDATES,
    DEFAULT_LEAD_TIME_DAYS,
    korea_today,
    ORDER_NEEDED_ACTIONS,
    ORDER_REVIEW_STATUS_SORT,
    PRE_ARRIVAL_HQ_STOCK_CANDIDATES,
    SALES_QTY_DIFF_ALERT_RATE,
    STANDARD_TRANSPORT_MODES,
    TRANSPORT_REVIEW_REQUIRED,
)
from core import export_excel as export_excel_mod, inbound as inbound_mod, kpi as kpi_mod, loaders as loaders_mod, order_review_data as order_review_data_mod, preprocess as preprocess_mod, sales as sales_mod, transport as transport_mod, validation as validation_mod


PL_SHIPPING_CUSTOMER_NAME = "SKO Sp. z o.o."


def _shipping_rows_for_entity(
    shipping_df: pd.DataFrame,
    *,
    entity_code: str,
) -> pd.DataFrame:
    """Keep only the shipping rows used by the selected V1 entity."""

    if str(entity_code or "").strip().upper() != "PL":
        return shipping_df.copy()

    customer_col = kpi_mod.find_column(
        shipping_df,
        ["거래처", "거래처명", "cust_nm"],
    )
    if customer_col is None:
        return shipping_df.iloc[0:0].copy()

    customer = shipping_df[customer_col].fillna("").astype(str).str.strip()
    return shipping_df.loc[customer.eq(PL_SHIPPING_CUSTOMER_NAME)].copy()


def _rough_transport_lead_time_policy(
    settings: dict,
) -> tuple[int | None, int | None, bool, bool]:
    """Return rough-allocation inputs without choosing among air services."""

    by_code = settings.get("lead_times_by_code")
    if isinstance(by_code, dict):
        air_candidates = [
            int(by_code[code])
            for code in ("AIR_DIR", "AIR_TS", "AIR")
            if code in by_code
        ]
        air_service_selection_required = len(air_candidates) > 1
        air_days = air_candidates[0] if len(air_candidates) == 1 else None
        rail_days = int(by_code["RAIL"]) if "RAIL" in by_code else None
        return (
            air_days,
            rail_days,
            "OCEAN" in by_code,
            air_service_selection_required,
        )

    legacy = settings.get("lead_times")
    if legacy is None:
        legacy = DEFAULT_LEAD_TIME_DAYS
    return (
        int(legacy["항공"]) if "항공" in legacy else None,
        int(legacy["철송"]) if "철송" in legacy else None,
        "해운" in legacy,
        False,
    )


def order_review_df(
    settings: dict,
    safety_months: float | None = None,
    excluded_only: bool | None = False,
    context: SessionContext | None = None,
) -> pd.DataFrame:
    context = ensure_session_context(context)
    safety_months = settings.get("safety_months", 3.0) if safety_months is None else safety_months
    # 안전재고 개월 수를 발주 목표의 단일 기준으로 사용한다.
    safety_months = float(safety_months)
    entity_code = str(settings.get("entity_code") or "PL").strip().upper()
    local_currency_code = str(
        settings.get("currency_code") or ("USD" if entity_code == "USA" else "EUR")
    ).strip().upper()
    if local_currency_code not in {"EUR", "USD"}:
        local_currency_code = "USD" if entity_code == "USA" else "EUR"
    local_krw_rate = float(
        settings.get("currency_krw_rate", settings.get("eur_krw_rate", _DEFAULT_EUR_KRW_RATE))
    )
    eu_stock_df = preprocess_mod.prepare_eu_stock(
        loaders_mod.get_order_review_data_or_empty("eu_stock", loaders_mod.sample_eu_stock, context),
        pa_ca_sales_col=settings.get("pa_ca_sales_column_override"),
        currency_code=local_currency_code,
    )
    cms_krw_unit_cost_available = "CMS 원화 입고단가" in eu_stock_df.columns
    eu_stock_df = order_review_data_mod.aggregate_eu_stock_for_order(eu_stock_df)
    hq_eu_stock_df = preprocess_mod.prepare_hq_eu_stock(loaders_mod.get_order_review_data_or_empty("hq_eu_stock", loaders_mod.sample_hq_eu_stock, context))
    raw_shipping = _shipping_rows_for_entity(
        loaders_mod.get_order_review_data_or_empty(
            "shipping",
            loaders_mod.sample_shipping,
            context,
        ),
        entity_code=entity_code,
    )
    shipping_df = transport_mod.prepare_shipping(raw_shipping, settings, context)
    recognized_shipping_df = shipping_df[transport_mod.recognized_transport_mask(shipping_df)].copy()
    if "금액" not in shipping_df.columns:
        shipping_df["금액"] = 0
    open_po = inbound_mod.get_open_po(context)
    demand_source = "재고파일 PA+CA 판매수량 기준"
    sales_detail_validation = sales_mod.sales_detail_validation_qty_by_sku(settings, context)
    sales_detail_identity = sales_mod.get_sales_detail(context)
    raw_open_po = loaders_mod.get_order_review_data_or_empty("open_po", loaders_mod.sample_open_po, context)
    raw_hq_eu_stock = loaders_mod.get_order_review_data_or_empty("hq_eu_stock", loaders_mod.sample_hq_eu_stock, context)
    raw_hq_to_eu_sales = loaders_mod.get_order_review_data_or_empty("hq_to_eu_sales_detail", loaders_mod.sample_hq_to_eu_sales_detail, context)
    filtered_sales_detail = sales_mod.filtered_sales_detail_by_biz(
        {**settings, "include_eu_pl_sales": True, "include_etc_sales": False},
        context,
    )
    hq_to_eu_unit_price = order_review_data_mod.sku_unit_price_from_amount_qty(
        raw_hq_to_eu_sales,
        ["SKU", "상품코드", "품목코드", "itemcode"],
        ["수량", "출고수량", "판매수량", "qty"],
        ["금액", "출고금액", "amount"],
        "본사→유럽 판매상세 단가_EUR",
    )
    sales_unit_price = order_review_data_mod.sku_unit_price_from_amount_qty(
        filtered_sales_detail,
        ["SKU", "상품코드", "품목코드", "itemcode"],
        ["판매 기준기간 판매량", "기준기간 판매량", "최근 판매량", "판매수량", "수량", "qty"],
        ["금액", "판매금액", "출고금액", "amount"],
        "EU 판매상세 단가_EUR",
    )
    hq_stock_unit_price = order_review_data_mod.hq_stock_unit_price_eur_df(raw_hq_eu_stock, local_krw_rate)
    product_name_maps = [
        inbound_mod.raw_product_name_map(raw_shipping, ["SKU", "상품코드", "품목코드", "아이템코드", "itemcode"]),
        inbound_mod.raw_product_name_map(raw_open_po, ["SKU", "상품코드", "품목코드", "아이템코드", "itemcode"]),
        inbound_mod.raw_product_name_map(raw_hq_eu_stock, ["SKU", "상품코드", "품목코드", "아이템코드", "itemcode"]),
        inbound_mod.raw_product_name_map(filtered_sales_detail, ["SKU", "상품코드", "품목코드", "itemcode"]),
        inbound_mod.sales_detail_validation_name_map(settings, context),
    ]
    brand_maps = [
        inbound_mod.raw_product_attr_map(raw_shipping, ["SKU", "상품코드", "품목코드", "아이템코드", "itemcode"], ["브랜드", "브랜드명", "brand"]),
        inbound_mod.raw_product_attr_map(raw_open_po, ["SKU", "상품코드", "품목코드", "아이템코드", "itemcode"], ["브랜드", "브랜드명", "brand"]),
        inbound_mod.raw_product_attr_map(raw_hq_eu_stock, ["SKU", "상품코드", "품목코드", "아이템코드", "itemcode"], ["브랜드", "브랜드명", "brand"]),
        inbound_mod.raw_product_attr_map(filtered_sales_detail, ["SKU", "상품코드", "품목코드", "itemcode"], ["브랜드", "브랜드명", "brand"]),
    ]

    master_skus = order_review_data_mod.build_order_master_skus(eu_stock_df, hq_eu_stock_df, shipping_df, open_po, sales_detail_validation, sales_detail_identity)
    master_sku_map = master_skus.assign(_sku_key=preprocess_mod.sku_group_key_series(master_skus["상품코드"])).set_index("_sku_key")["상품코드"].to_dict()

    def apply_master_sku(frame: pd.DataFrame, column: str) -> pd.DataFrame:
        if frame.empty or column not in frame.columns:
            return frame
        out = frame.copy()
        keys = preprocess_mod.sku_group_key_series(out[column])
        out[column] = keys.map(master_sku_map).fillna(out[column])
        return out

    eu_stock_df = apply_master_sku(eu_stock_df, "상품코드")
    hq_eu_stock_df = apply_master_sku(hq_eu_stock_df, "상품코드")
    shipping_df = apply_master_sku(shipping_df, "SKU")
    recognized_shipping_df = apply_master_sku(recognized_shipping_df, "SKU")
    open_po = apply_master_sku(open_po, "SKU")
    sales_detail_validation = apply_master_sku(sales_detail_validation, "SKU")
    hq_to_eu_unit_price = apply_master_sku(hq_to_eu_unit_price, "SKU")
    sales_unit_price = apply_master_sku(sales_unit_price, "SKU")
    hq_stock_unit_price = apply_master_sku(hq_stock_unit_price, "SKU")
    if not open_po.empty and {"SKU", "미입고수량"}.issubset(open_po.columns):
        open_po = open_po.groupby("SKU", as_index=False).agg(
            미입고수량=("미입고수량", "sum"),
            미입고금액=("미입고금액", "sum") if "미입고금액" in open_po.columns else ("미입고수량", lambda _: 0),
            **{"미입고 단가": ("미입고 단가", "first") if "미입고 단가" in open_po.columns else ("미입고수량", lambda _: 0)},
        )
    if not sales_detail_validation.empty and {"SKU", "판매내역상세_3M_판매수량"}.issubset(sales_detail_validation.columns):
        sales_detail_validation = sales_detail_validation.groupby("SKU", as_index=False)["판매내역상세_3M_판매수량"].sum()
    if not hq_to_eu_unit_price.empty and {"SKU", "본사→유럽 판매상세 단가_EUR"}.issubset(hq_to_eu_unit_price.columns):
        hq_to_eu_unit_price = order_review_data_mod._first_positive_by_group(hq_to_eu_unit_price, "SKU", "본사→유럽 판매상세 단가_EUR")
    if not sales_unit_price.empty and {"SKU", "EU 판매상세 단가_EUR"}.issubset(sales_unit_price.columns):
        sales_unit_price = order_review_data_mod._first_positive_by_group(sales_unit_price, "SKU", "EU 판매상세 단가_EUR")
    if not hq_stock_unit_price.empty and {"SKU", "본사창고 단가_EUR"}.issubset(hq_stock_unit_price.columns):
        hq_stock_unit_price = order_review_data_mod._first_positive_by_group(hq_stock_unit_price, "SKU", "본사창고 단가_EUR")

    shipping_qty = shipping_df.groupby("SKU", as_index=False)["수량"].sum().rename(columns={"수량": "운송중 수량"})
    shipping_amount = shipping_df.groupby("SKU", as_index=False)["금액"].sum().rename(columns={"금액": "컨테이너 금액"})
    shipping_fallback = shipping_qty.merge(shipping_amount, on="SKU", how="left")
    shipping_fallback["컨테이너 단가"] = np.where(
        pd.to_numeric(shipping_fallback["운송중 수량"], errors="coerce").fillna(0) > 0,
        pd.to_numeric(shipping_fallback["컨테이너 금액"], errors="coerce").fillna(0)
        / pd.to_numeric(shipping_fallback["운송중 수량"], errors="coerce").replace(0, np.nan),
        0,
    )
    shipping_fallback["컨테이너 단가"] = pd.to_numeric(shipping_fallback["컨테이너 단가"], errors="coerce").fillna(0)
    first_eta = recognized_shipping_df.groupby("SKU", as_index=False)["ETA"].min().rename(columns={"ETA": "최초 ETA"})
    first_eta_qty = recognized_shipping_df.sort_values("ETA").groupby("SKU", as_index=False).first()[["SKU", "수량"]].rename(columns={"수량": "최초 ETA 수량"})
    df = master_skus.merge(eu_stock_df, on="상품코드", how="left", suffixes=("_원천", ""))
    for col in ["브랜드", "상품명"]:
        source_col = f"{col}_원천"
        if source_col in df.columns:
            df[col] = export_excel_mod._first_non_blank(df[col], df[source_col])
            df = df.drop(columns=[source_col])
    df = df.merge(hq_eu_stock_df, on="상품코드", how="left")
    df = df.merge(shipping_qty, left_on="상품코드", right_on="SKU", how="left").drop(columns=["SKU"])
    df = df.merge(shipping_fallback[["SKU", "컨테이너 금액", "컨테이너 단가"]], left_on="상품코드", right_on="SKU", how="left").drop(columns=["SKU"])
    df = df.merge(hq_to_eu_unit_price, left_on="상품코드", right_on="SKU", how="left").drop(columns=["SKU"], errors="ignore")
    df = df.merge(hq_stock_unit_price, left_on="상품코드", right_on="SKU", how="left").drop(columns=["SKU"], errors="ignore")
    df = df.merge(sales_unit_price, left_on="상품코드", right_on="SKU", how="left").drop(columns=["SKU"], errors="ignore")
    df = df.merge(first_eta, left_on="상품코드", right_on="SKU", how="left").drop(columns=["SKU"])
    df = df.merge(first_eta_qty, left_on="상품코드", right_on="SKU", how="left").drop(columns=["SKU"])
    df = df.merge(open_po, left_on="상품코드", right_on="SKU", how="left").drop(columns=["SKU"])
    df = df.merge(sales_detail_validation, left_on="상품코드", right_on="SKU", how="left").drop(columns=["SKU"], errors="ignore")
    for col, default in {
        "브랜드": "-",
        "상품명": "-",
        "제품상태": "",
        "바코드": "-",
        "재고수량": 0,
        "Hold수량": 0,
        "EU 현지 가용수량": 0,
        "EU 입고단가": 0,
        "CMS 원화 입고단가": 0,
        "CMS 재고금액(KRW)": 0,
        "PA+CA 판매수량": 0,
        "최근 3개월 판매수량": 0,
        "재고파일 존재여부": "",
        "SKU등록상태": "",
        "미입고금액": 0,
        "미입고 단가": 0,
        "컨테이너 금액": 0,
        "컨테이너 단가": 0,
        "본사→유럽 판매상세 단가_EUR": 0,
        "본사창고 단가_EUR": 0,
        "EU 판매상세 단가_EUR": 0,
    }.items():
        if col not in df.columns:
            df[col] = default
        else:
            df[col] = df[col].fillna(default)
    df["브랜드"] = order_review_data_mod.fill_blank_text_from_maps(df, "브랜드", brand_maps, fallback="-")
    df["상품명"] = order_review_data_mod.fill_blank_text_from_maps(df, "상품명", product_name_maps, fallback="상품명 미확인")
    for col in ["재고수량", "Hold수량", "EU 현지 가용수량", "EU 입고단가", "CMS 원화 입고단가", "CMS 재고금액(KRW)", "PA+CA 판매수량", "최근 3개월 판매수량"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["PA_CA_3M_판매수량"] = pd.to_numeric(df.get("PA+CA 판매수량", df.get("최근 3개월 판매수량", 0)), errors="coerce").fillna(0)
    df["PA+CA 판매수량"] = df["PA_CA_3M_판매수량"]
    df["판매내역상세_3M_판매수량"] = pd.to_numeric(df.get("판매내역상세_3M_판매수량", 0), errors="coerce").fillna(0)
    # The stock API aggregate is retained for reconciliation, but row-level
    # incident handling requires the detailed sales population. When CMS
    # detail is present, use its normalized demand quantity as the V1 source.
    has_sales_detail_source = (
        "sales_detail" in context.uploaded_data
        and not sales_detail_validation.empty
    )
    if has_sales_detail_source:
        demand_source = "판매내역상세 사고처리 제외 기준"
        df["기준_3M_판매수량"] = df["판매내역상세_3M_판매수량"]
    else:
        df["기준_3M_판매수량"] = df["PA_CA_3M_판매수량"]
    df["최근 3개월 판매수량"] = df["기준_3M_판매수량"]
    df["판매수량 기준"] = demand_source
    df["보조 검증 기준"] = "판매내역상세 EU-OVERSEAS + EU-PL + KR-OVERSEAS + 자사간거래 3개월 판매수량"
    # Always compare detail demand with the raw CMS stock aggregate, even when
    # the corrected detail demand is the actual V1 calculation basis.
    df["판매수량 차이"] = df["판매내역상세_3M_판매수량"] - df["PA_CA_3M_판매수량"]
    base_sales = df["PA_CA_3M_판매수량"].abs()
    detail_sales = df["판매내역상세_3M_판매수량"].abs()
    df["판매수량 차이율"] = np.where(
        base_sales > 0,
        df["판매수량 차이"].abs() / base_sales * 100,
        np.where(detail_sales > 0, 100.0, 0.0),
    )
    df["판매수량 기준 확인 필요"] = np.where(df["판매수량 차이율"] >= SALES_QTY_DIFF_ALERT_RATE, "Y", "")
    df = validation_mod.add_sku_exclusion_flags(df, settings)

    for col in ["본사 EU창고 가용수량", "운송중 수량", "미입고수량", "최초 ETA 수량"]:
        df[col] = df[col].fillna(0).astype(int)
    for col in ["미입고금액", "미입고 단가", "컨테이너 금액", "컨테이너 단가", "본사→유럽 판매상세 단가_EUR", "본사창고 단가_EUR", "EU 판매상세 단가_EUR"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df["재고파일 존재여부"] = np.where(df["재고파일 존재여부"].astype(str).eq("Y"), "Y", "")
    df["SKU등록상태"] = np.where(
        df["재고파일 존재여부"].eq("Y"),
        "정상등록",
        np.where(preprocess_mod.product_sku_mask(df["상품코드"]), "현지 재고 마스터 미등록", "상품코드 확인필요"),
    )
    df["분류용 최근판매수량"] = df["기준_3M_판매수량"]
    df["판매이력여부"] = np.where(df["분류용 최근판매수량"] > 0, "Y", "")
    df["운송중여부"] = np.where(df["운송중 수량"] > 0, "Y", "")
    df["미입고여부"] = np.where(df["미입고수량"] > 0, "Y", "")
    df["재고운영상태"] = [
        inbound_mod.classify_inventory_operation(available, sales_qty, shipping_qty, open_po_qty)
        for available, sales_qty, shipping_qty, open_po_qty in zip(
            df["EU 현지 가용수량"], df["분류용 최근판매수량"], df["운송중 수량"], df["미입고수량"]
        )
    ]
    df["판단메모"] = df.apply(inbound_mod.build_inventory_decision_short_memo, axis=1)

    df["월평균 판매수량"] = df["최근 3개월 판매수량"] / 3
    df["일평균 판매수량"] = df["최근 3개월 판매수량"] / 90
    df["유럽+운송 수량"] = df["EU 현지 가용수량"] + df["운송중 수량"]
    df["안전재고 개월 수"] = safety_months
    df["안전재고 목표수량"] = (df["월평균 판매수량"] * safety_months).round(0).astype(int)
    df["미래 소비 예상수량"] = df["안전재고 목표수량"]
    df["계산 반영 수량"] = (df["EU 현지 가용수량"] - df["미래 소비 예상수량"] + df["운송중 수량"]).round(0).astype(int)
    df["EU 현지 커버일수"] = np.where(df["일평균 판매수량"] > 0, df["EU 현지 가용수량"] / df["일평균 판매수량"], 999)
    df["커버가능 개월수"] = np.where(df["월평균 판매수량"] > 0, df["EU 현지 가용수량"] / df["월평균 판매수량"], 99)
    df["운송 포함 보유개월수"] = np.where(df["월평균 판매수량"] > 0, df["유럽+운송 수량"] / df["월평균 판매수량"], 99)
    df["계산 반영 보유개월수"] = np.where(df["월평균 판매수량"] > 0, df["계산 반영 수량"] / df["월평균 판매수량"], 99)
    df["고갈 예상일"] = df["EU 현지 커버일수"].apply(lambda x: settings["base_date"] + timedelta(days=int(min(x, 999))) if x < 999 else "판매없음")
    df["안전재고수량"] = df["안전재고 목표수량"]
    df["부족수량 산정 기준 보유량"] = df["유럽+운송 수량"]
    df["1차 부족수량"] = (df["안전재고 목표수량"] - df["유럽+운송 수량"]).clip(lower=0).round(0).astype(int)
    df["본사 이동 수량"] = 0
    df["추가 발주 필요 수량"] = df["1차 부족수량"]
    df["최종 부족수량"] = df["추가 발주 필요 수량"]
    df["원본 현지 입고단가"] = pd.to_numeric(
        report_col(df, ["현지 입고단가", "EU 입고단가"], 0), errors="coerce"
    ).fillna(0)
    price_currency = report_col(
        df,
        ["현지 입고단가 통화", "EU 입고단가 통화"],
        local_currency_code,
    ).astype(str).str.upper()
    price_currency = price_currency.where(
        price_currency.isin([local_currency_code, "KRW"]), local_currency_code
    )
    df["원본 현지 입고단가 통화"] = price_currency
    df["EU 입고단가 확인필요 플래그"] = ""
    raw_local_unit_price = df["원본 현지 입고단가"].clip(lower=0).fillna(0)
    converted_local_unit_price = np.where(
        price_currency.eq("KRW") & (local_krw_rate > 0),
        raw_local_unit_price / local_krw_rate,
        raw_local_unit_price,
    )
    df[f"적용 단가_{local_currency_code}"] = converted_local_unit_price
    api_krw_unit_cost_available = cms_krw_unit_cost_available
    api_krw_unit_cost = pd.to_numeric(df.get("CMS 원화 입고단가", 0), errors="coerce").fillna(0)
    if api_krw_unit_cost_available:
        # CMS stock/local의 조회 기준일 고시환율이 이미 반영된 authoritative KRW 단가다.
        df["현지 입고단가_KRW"] = api_krw_unit_cost
    else:
        # 파일 업로드 호환 경로만 기존 사용자가 지정한 환율을 유지한다.
        df["현지 입고단가_KRW"] = np.where(
            price_currency.eq("KRW"),
            raw_local_unit_price,
            raw_local_unit_price * local_krw_rate,
        )
    df[f"현지 입고단가_{local_currency_code}"] = converted_local_unit_price
    df["현지 입고단가"] = converted_local_unit_price
    price_source_label = (
        "CMS 조회 기준일 원화 단가"
        if api_krw_unit_cost_available
        else np.where(
            price_currency.eq("KRW"),
            f"현지 재고 평균단가 KRW ÷ {local_currency_code}/KRW 환율",
            f"현지 재고 평균단가 {local_currency_code}",
        )
    )
    df["단가 출처"] = pd.Series(
        np.where(
            df["원본 현지 입고단가"].gt(0),
            price_source_label,
            "0단가 제외",
        ),
        index=df.index,
    )
    df["단가 미등록 플래그"] = ""
    zero_price_excluded = (
        df["재고파일 존재여부"].astype(str).eq("Y")
        & df["원본 현지 입고단가"].le(0)
        & preprocess_mod.product_sku_mask(df["상품코드"])
    )
    if zero_price_excluded.any():
        existing_type = df.loc[zero_price_excluded, "제외유형"].astype(str).str.strip()
        df.loc[zero_price_excluded, "제외유형"] = np.where(
            existing_type.str.contains("0단가", na=False),
            existing_type,
            np.where(existing_type.ne(""), existing_type + "/0단가", "0단가/무상"),
        )
        zero_price_reason = "입고단가 0, 무상제공/FOC성 SKU로 발주 검토 제외"
        existing_reason = df.loc[zero_price_excluded, "제외사유"].astype(str).str.strip()
        df.loc[zero_price_excluded, "제외사유"] = np.where(
            existing_reason.str.contains("입고단가 0", na=False),
            existing_reason,
            np.where(existing_reason.ne(""), existing_reason + " / " + zero_price_reason, zero_price_reason),
        )
        df.loc[zero_price_excluded, "제외 SKU"] = True
    df[f"부족금액_{local_currency_code}"] = (
        df["추가 발주 필요 수량"] * df[f"현지 입고단가_{local_currency_code}"]
    )
    df["추가 발주 필요 금액"] = df["추가 발주 필요 수량"] * df["현지 입고단가_KRW"]
    df["부족금액_KRW"] = df["추가 발주 필요 금액"]
    df["현지 통화"] = local_currency_code
    # 구형 PL 보고서와 저장 결과를 읽는 코드가 사용하는 호환 별칭이다.
    df["원본 EU 입고단가"] = df["원본 현지 입고단가"]
    df["원본 EU 입고단가 통화"] = df["원본 현지 입고단가 통화"]
    df["EU 입고단가"] = df["현지 입고단가"]
    df["EU 입고단가_KRW"] = df["현지 입고단가_KRW"]
    df["적용 단가_EUR"] = df[f"적용 단가_{local_currency_code}"]
    df["EU 입고단가_EUR"] = df[f"현지 입고단가_{local_currency_code}"]
    df["부족금액_EUR"] = df[f"부족금액_{local_currency_code}"]
    df["유럽 가용재고"] = df["EU 현지 가용수량"]
    df["발주필요수량"] = df["추가 발주 필요 수량"]
    df["발주필요금액"] = df["추가 발주 필요 금액"]
    local_available = pd.to_numeric(df["EU 현지 가용수량"], errors="coerce").fillna(0)
    order_required_qty = pd.to_numeric(df["발주필요수량"], errors="coerce").fillna(0)
    is_oos = local_available.le(0)
    is_order_needed = order_required_qty.gt(0)
    df["재고 ETA 상태"] = np.select(
        [
            is_oos,
            is_order_needed,
        ],
        [
            "OOS",
            "발주필요",
        ],
        default="-",
    )
    df["FOC SKU"] = df["제외유형"].astype(str).str.contains("샘플|FOC|무상", na=False)
    df["최초 ETA"] = pd.to_datetime(df["최초 ETA"], errors="coerce").dt.date

    review_lead_times = settings.get("applied_lead_times", transport_mod.applied_lead_times(settings))
    review_lead_times_by_code = settings.get("lead_times_by_code")
    review_entity_code = str(settings.get("entity_code") or "PL")
    base_date = settings["base_date"]
    if isinstance(base_date, datetime):
        base_date = base_date.date()

    def transport_review(row: pd.Series) -> tuple[str, int, date | str]:
        monthly_sales = pd.to_numeric(row.get("월평균 판매수량", 0), errors="coerce")
        order_qty = pd.to_numeric(row.get("추가 발주 필요 수량", 0), errors="coerce")
        order_needed = (
            (0.0 if pd.isna(monthly_sales) else float(monthly_sales)) > 0
            and (0.0 if pd.isna(order_qty) else float(order_qty)) > 0
        )
        depletion_date = row["고갈 예상일"]
        if isinstance(depletion_date, pd.Timestamp):
            depletion_date = depletion_date.date()
        if not isinstance(depletion_date, date):
            label, lead_days, _reason = transport_mod.transport_recommendation_by_depletion_days(
                np.nan,
                review_lead_times,
                order_needed=order_needed,
                lead_times_by_code=review_lead_times_by_code,
                entity_code=review_entity_code,
            )
            return label, lead_days, "-"
        depletion_days = (depletion_date - base_date).days
        label, lead_days, _reason = transport_mod.transport_recommendation_by_depletion_days(
            depletion_days,
            review_lead_times,
            order_needed=order_needed,
            lead_times_by_code=review_lead_times_by_code,
            entity_code=review_entity_code,
        )
        arrival_date = base_date + timedelta(days=lead_days) if lead_days > 0 else "-"
        return label, lead_days, arrival_date

    transport = df.apply(transport_review, axis=1, result_type="expand")
    df["운송수단 검토안"] = transport[0]
    df["적용 리드타임"] = transport[1]
    df["예상 도착 가능일"] = transport[2]

    def decide_order_status(row: pd.Series) -> tuple[str, str, str, str, str, str, str]:
        exception_reasons = []
        sku_status = str(row.get("SKU등록상태", "")).strip()
        if pd.to_numeric(row.get("Hold수량", 0), errors="coerce") > pd.to_numeric(row.get("재고수량", 0), errors="coerce"):
            exception_reasons.append("데이터 오류 가능성")

        eta_delayed = (
            row.get("운송중 수량", 0) > 0
            and pd.notna(row.get("최초 ETA"))
            and isinstance(row.get("고갈 예상일"), date)
            and row.get("최초 ETA") > row.get("고갈 예상일")
        )
        eta_delay_flag = "Y" if eta_delayed else ""

        min_monthly = float(settings.get("min_monthly_sales_for_order_review", 1.0))
        excluded_reasons = []
        if bool(row.get("제외 SKU", False)):
            excluded_reasons.append(str(row.get("제외사유", "") or str(row.get("제외유형", "") or "발주 검토 제외 대상")))
        if sku_status != "정상등록":
            excluded_reasons.append("상품코드/마스터 기준 발주 제외")
        if str(row.get("단가 미등록 플래그", "")).strip() == "Y":
            excluded_reasons.append("0단가/무상 추정")
        if row.get("월평균 판매수량", 0) <= 0:
            excluded_reasons.append("최근 3개월 판매 없음")
        elif row.get("월평균 판매수량", 0) < min_monthly:
            excluded_reasons.append("저판매 기준 미만")

        order_needed = row.get("추가 발주 필요 수량", 0) > 0

        if excluded_reasons:
            status = "발주제외"
            final_action = "발주 필요 없음"
            basis = " / ".join(dict.fromkeys([reason for reason in excluded_reasons if reason]))
            summary = "발주 검토 제외"
            exception_flag = ""
            exception_reason = ""
        elif exception_reasons:
            status = "확인필요"
            final_action = "발주 필요 없음"
            basis = " / ".join(dict.fromkeys(exception_reasons))
            summary = "원본 데이터 확인 필요"
            exception_flag = "Y"
            exception_reason = basis
        elif order_needed:
            status = "정상"
            final_action = "발주 필요"
            order_qty = int(row.get("추가 발주 필요 수량", 0))
            basis = "안전재고 목표수량 대비 현지 가용수량+운송중 수량 부족"
            summary = f"신규 발주 {order_qty:,}개"
            exception_flag = ""
            exception_reason = ""
        else:
            status = "정상"
            final_action = "발주 필요 없음"
            basis = "현지 가용수량+운송중 수량으로 안전재고 목표수량 충족"
            summary = "발주 필요 없음"
            exception_flag = ""
            exception_reason = ""
        return final_action, status, summary, basis, exception_flag, exception_reason, eta_delay_flag

    decisions = df.apply(decide_order_status, axis=1, result_type="expand")
    df["최종 액션"] = decisions[0]
    df["상태"] = decisions[1]
    df["조치 요약"] = decisions[2]
    df["근거"] = decisions[3]
    df["예외 플래그"] = decisions[4]
    df["예외 사유"] = decisions[5]
    df["ETA 지연 플래그"] = decisions[6]
    df["우선 액션"] = df["최종 액션"]
    df["판단 사유"] = df["근거"]
    no_order_mask = df["최종 액션"].eq("발주 필요 없음")
    df.loc[no_order_mask, ["추가 발주 필요 수량", "최종 부족수량", "발주필요수량"]] = 0
    zero_amount_columns = list(
        dict.fromkeys(
            [
                "추가 발주 필요 금액",
                f"부족금액_{local_currency_code}",
                "부족금액_EUR",
                "부족금액_KRW",
                "발주필요금액",
            ]
        )
    )
    df.loc[no_order_mask, zero_amount_columns] = 0
    df["논의필요"] = np.where(df["최종 액션"].eq("발주 필요") | df["상태"].isin(["확인필요"]), "Y", "")
    df["발주검토여부"] = np.where(df["최종 액션"].eq("발주 필요"), "필요", "불필요")
    df["기준일"] = settings["base_date"]
    df = apply_pre_arrival_shortage_risk(df, settings)

    (
        air_lead_days,
        rail_lead_days,
        sea_supported,
        air_service_selection_required,
    ) = _rough_transport_lead_time_policy(settings)
    eta_qty_by_sku = {
        sku: eta_group.groupby("ETA")["수량"].sum().to_dict()
        for sku, eta_group in shipping_df.groupby("SKU")
    }
    rough_flow_date_keys = [
        (settings["base_date"] + timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(1, 91)
    ]
    # SKU별 90일 입고 델타를 행 반복 전에 한 번만 배열로 만들어 둔다. 행 단위로 90일
    # 파이썬 루프를 돌리면(과거 구현) 대용량 업로드에서 GIL을 오래 점유해 이벤트 루프가
    # 멈추는 문제가 있었다 - numpy cumsum으로 대체해 같은 연산 순서(각 스텝마다
    # -daily_sales 후 해당일 입고분 가산)를 유지하면서 파이썬 레벨 반복을 없앤다.
    eta_delta_by_sku = {
        sku: np.array([eta_map.get(day, 0.0) for day in rough_flow_date_keys], dtype=float)
        for sku, eta_map in eta_qty_by_sku.items()
    }
    zero_eta_delta = np.zeros(len(rough_flow_date_keys), dtype=float)

    def time_based_rough_distribution(row: pd.Series) -> tuple[int, int, int]:
        daily_sales = float(pd.to_numeric(row.get("일평균 판매수량", 0), errors="coerce"))
        order_qty = float(pd.to_numeric(row.get("발주필요수량", 0), errors="coerce"))
        if pd.isna(daily_sales) or pd.isna(order_qty) or daily_sales <= 0 or order_qty <= 0:
            return 0, 0, 0

        order_qty_int = max(int(round(order_qty)), 0)
        if order_qty_int <= 0:
            return 0, 0, 0
        if air_service_selection_required:
            # The fixed three-bucket legacy output cannot distinguish UK DIR
            # and T/S.  Do not choose either service implicitly.
            return 0, 0, 0

        current_stock = float(pd.to_numeric(row.get("EU 현지 가용수량", 0), errors="coerce"))
        if pd.isna(current_stock):
            current_stock = 0.0
        eta_deltas = eta_delta_by_sku.get(row.get("상품코드"), zero_eta_delta)
        stock_flow = current_stock + np.cumsum(eta_deltas - daily_sales)

        air_window_days = (
            max(min(air_lead_days, len(stock_flow)), 0)
            if air_lead_days is not None
            else 0
        )
        min_air_stock = float(stock_flow[:air_window_days].min()) if air_window_days > 0 else 0
        air_qty = (
            min(abs(min_air_stock) if min_air_stock < 0 else 0, order_qty)
            if air_lead_days is not None
            else 0
        )

        remaining_qty = max(order_qty - air_qty, 0)
        if rail_lead_days is not None:
            air_boundary = air_lead_days or 0
            rail_cover_days = max(rail_lead_days - air_boundary, 0)
            rail_theory_qty = max(rail_cover_days * daily_sales, 0)
            rail_qty = min(remaining_qty, rail_theory_qty)
        else:
            rail_qty = 0
        sea_qty = (
            max(order_qty - air_qty - rail_qty, 0)
            if sea_supported
            else 0
        )

        air_int = max(int(round(air_qty)), 0)
        rail_int = max(int(round(rail_qty)), 0)
        sea_int = max(int(round(sea_qty)), 0)
        overflow = air_int + rail_int + sea_int - order_qty_int
        if overflow > 0:
            deduction = min(sea_int, overflow)
            sea_int -= deduction
            overflow -= deduction
        if overflow > 0:
            deduction = min(rail_int, overflow)
            rail_int -= deduction
            overflow -= deduction
        if overflow > 0:
            air_int = max(air_int - overflow, 0)
        return air_int, rail_int, sea_int

    if df.empty:
        df["시간기준_항공필요수량"] = pd.Series(dtype=int)
        df["시간기준_철송필요수량"] = pd.Series(dtype=int)
        df["시간기준_해운필요수량"] = pd.Series(dtype=int)
    else:
        rough_distribution = df.apply(time_based_rough_distribution, axis=1, result_type="expand")
        df["시간기준_항공필요수량"] = rough_distribution[0]
        df["시간기준_철송필요수량"] = rough_distribution[1]
        df["시간기준_해운필요수량"] = rough_distribution[2]

    def time_based_qty_value(value: object) -> float:
        qty = pd.to_numeric(value, errors="coerce")
        return 0.0 if pd.isna(qty) else float(qty)

    def time_based_transport_title(row: pd.Series) -> str:
        if (
            air_service_selection_required
            and time_based_qty_value(row.get("발주필요수량", 0)) > 0
        ):
            return "항공 서비스 선택 필요"
        modes = [
            ("항공", row.get("시간기준_항공필요수량", 0)),
            ("철송", row.get("시간기준_철송필요수량", 0)),
            ("해운", row.get("시간기준_해운필요수량", 0)),
        ]
        selected_modes = [mode for mode, qty in modes if time_based_qty_value(qty) > 0]
        return "+".join(selected_modes) if selected_modes else "추가 운송 불필요"

    def time_based_qty_summary(row: pd.Series) -> str:
        if (
            air_service_selection_required
            and time_based_qty_value(row.get("발주필요수량", 0)) > 0
        ):
            return "항공 서비스 선택 필요"
        parts = []
        for mode, col in [
            ("항공", "시간기준_항공필요수량"),
            ("철송", "시간기준_철송필요수량"),
            ("해운", "시간기준_해운필요수량"),
        ]:
            qty = time_based_qty_value(row.get(col, 0))
            if qty > 0:
                parts.append(f"{mode} {int(round(qty)):,.0f}")
        return " / ".join(parts) if parts else "추가 운송 불필요"

    df["시간기준_권장운송안"] = df.apply(time_based_transport_title, axis=1)
    df["시간기준_권장수량요약"] = df.apply(time_based_qty_summary, axis=1)
    no_extra_transport_mask = (
        df["최종 액션"].astype(str).eq("발주 필요 없음")
        | (pd.to_numeric(df["발주필요수량"], errors="coerce").fillna(0) <= 0)
    )
    df.loc[no_extra_transport_mask, "운송수단 검토안"] = "● 발주불필요"
    df.loc[no_extra_transport_mask, "적용 리드타임"] = 0
    df.loc[no_extra_transport_mask, "예상 도착 가능일"] = "-"

    if excluded_only is not None:
        df = df[df["제외 SKU"] if excluded_only else ~df["제외 SKU"]]
    for display_col, candidates, default in [
        ("브랜드", ["브랜드", "브랜드_x", "브랜드_y", "브랜드명", "brand", "brandname"], "-"),
        ("상품명", ["상품명", "상품명_x", "상품명_y", "제품명", "품목명", "itemname", "productname"], "-"),
        ("제품상태", ["제품상태", "상품상태", "상태", "판매상태", "사용여부", "status"], ""),
        ("바코드", ["바코드", "바코드_x", "바코드_y", "barcode", "ean", "jan"], "-"),
    ]:
        if display_col not in df.columns:
            source_col = kpi_mod.find_column(df, candidates)
            df[display_col] = df[source_col] if source_col is not None else default
    cols = [
        "발주검토여부", "최종 액션", "상태", "조치 요약", "근거", "예외 플래그", "예외 사유", "우선 액션", "SKU등록상태", "재고운영상태", "판매이력여부", "운송중여부", "미입고여부", "판단메모",
        "판매수량 기준", "보조 검증 기준", "판매수량 기준 확인 필요", "재고파일 존재여부", "제외 SKU", "제외유형", "제외사유", "단가 미등록 플래그", "EU 입고단가 확인필요 플래그", "단가 출처", "커버가능 개월수", "기준일", "브랜드", "상품명", "제품상태", "바코드", "상품코드",
        "기준_3M_판매수량", "PA_CA_3M_판매수량", "PA+CA 판매수량", "판매내역상세_3M_판매수량", "판매수량 차이", "판매수량 차이율",
        "EU 현지 가용수량", "유럽 가용재고", "본사 EU창고 가용수량", "운송중 수량", "입고 전 예상 결품량", "미입고수량", "유럽+운송 수량", "재고 ETA 상태", "미래 소비 예상수량", "계산 반영 수량", "부족수량 산정 기준 보유량",
        "최근 3개월 판매수량", "월평균 판매수량", "일평균 판매수량", "EU 현지 커버일수", "고갈 예상일",
        "최초 ETA", "최초 ETA 수량",
        "운송 포함 보유개월수", "계산 반영 보유개월수", "안전재고 개월 수", "안전재고 목표수량", "안전재고수량", "1차 부족수량", "본사 이동 수량", "추가 발주 필요 수량", "최종 부족수량", "발주필요수량", "긴급 보충 필요 수량", "입고 전 결품 위험 여부", "권장 긴급 액션", "원본 현지 입고단가", "원본 현지 입고단가 통화", "현지 입고단가", "현지 입고단가_KRW", f"현지 입고단가_{local_currency_code}", f"적용 단가_{local_currency_code}", f"부족금액_{local_currency_code}", "현지 통화", "원본 EU 입고단가", "원본 EU 입고단가 통화", "EU 입고단가", "EU 입고단가_KRW", "부족금액_EUR", "부족금액_KRW", "추가 발주 필요 금액", "발주필요금액", "ETA 지연 플래그", "운송수단 검토안",
        "적용 리드타임", "예상 도착 가능일", "판단 사유",
        "논의필요",
        "시간기준_권장운송안", "시간기준_권장수량요약", "시간기준_항공필요수량", "시간기준_철송필요수량", "시간기준_해운필요수량",
    ]
    cols = list(dict.fromkeys(cols))
    # 시간기준 러프분배는 참고값이며 CBM/운송비/MOQ는 반영하지 않는다.
    return validation_mod.apply_common_filters(df[cols], settings, include_brand=False, include_transport=False)


def excluded_order_review_df(
    settings: dict,
    safety_months: float | None = None,
    context: SessionContext | None = None,
) -> pd.DataFrame:
    return order_review_df(settings, safety_months=safety_months, excluded_only=True, context=context)


def first_existing_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    return kpi_mod.find_column(df, candidates)


def report_col(df: pd.DataFrame, candidates: list[str], default: object = "") -> pd.Series:
    col = first_existing_col(df, candidates)
    if col is None:
        return pd.Series([default] * len(df), index=df.index)
    return df[col]


def order_needed_action_mask(action: pd.Series) -> pd.Series:
    return action.fillna("").astype(str).str.strip().isin(ORDER_NEEDED_ACTIONS)


def hq_eu_stock_column_status(df: pd.DataFrame) -> tuple[str | None, str]:
    col = first_existing_col(df, PRE_ARRIVAL_HQ_STOCK_CANDIDATES)
    if col is None:
        return None, "본사 EU창고 재고 컬럼 미확인으로 본사 이동 검토 조건 미적용"
    return col, f"본사 EU창고 재고 컬럼 확인: {col}"


def apply_pre_arrival_shortage_risk(df: pd.DataFrame, settings: dict) -> pd.DataFrame:
    """Add a time-gap risk signal without changing the existing order quantity formula.

    This first version uses the earliest SKU ETA already calculated in the review.
    A later version can expand this to an ETA-by-ETA cumulative stock simulation.
    """
    out = df.copy()
    if out.empty:
        out["입고 전 예상 결품량"] = pd.Series(dtype=int)
        out["긴급 보충 필요 수량"] = pd.Series(dtype=int)
        out["입고 전 결품 위험 여부"] = pd.Series(dtype=object)
        out["권장 긴급 액션"] = pd.Series(dtype=object)
        return out

    base_value = settings.get("base_date", korea_today())
    base_ts = pd.to_datetime(base_value, errors="coerce")
    daily_sales = pd.to_numeric(report_col(out, ["일평균 판매수량", "일평균 판매"], 0), errors="coerce").fillna(0)
    eu_available = pd.to_numeric(
        report_col(out, ["EU 현지 가용수량", "EU 가용재고", "유럽 가용재고", "유럽 재고"], 0),
        errors="coerce",
    ).fillna(0)
    earliest_arrival = kpi_mod.parse_date_series(report_col(out, ["최초 ETA", "예상 입고일", "첫 입고 예정일"], ""))
    days_until_arrival = (earliest_arrival - base_ts).dt.days
    valid_gap = earliest_arrival.notna() & daily_sales.gt(0) & days_until_arrival.gt(0)
    gap_days = days_until_arrival.clip(lower=0).fillna(0)
    expected_gap_qty = (daily_sales * gap_days - eu_available).clip(lower=0)
    urgent_qty = pd.Series(np.where(valid_gap, np.ceil(expected_gap_qty), 0), index=out.index)
    urgent_qty = pd.to_numeric(urgent_qty, errors="coerce").fillna(0).astype(int)

    out["입고 전 예상 결품량"] = urgent_qty
    out["긴급 보충 필요 수량"] = urgent_qty
    out["입고 전 결품 위험 여부"] = np.where(valid_gap & urgent_qty.gt(0), "Y", "N")

    hq_col, _ = hq_eu_stock_column_status(out)
    hq_stock = pd.to_numeric(out[hq_col], errors="coerce").fillna(0) if hq_col else pd.Series(0, index=out.index)
    shipping_qty = pd.to_numeric(report_col(out, ["운송중 수량", "운송중"], 0), errors="coerce").fillna(0)
    urgent_mask = urgent_qty.gt(0)
    urgent_action = pd.Series("", index=out.index, dtype=object)
    if hq_col is not None:
        hq_cover_mask = urgent_mask & hq_stock.ge(urgent_qty)
        urgent_action.loc[hq_cover_mask] = "본사 EU창고 이동 검토"
    remaining = urgent_mask & urgent_action.eq("")
    urgent_action.loc[remaining & shipping_qty.gt(0)] = "기존 운송건 일부 항공 전환/ETA 앞당김 검토"
    urgent_action.loc[remaining & shipping_qty.le(0)] = "신규 긴급 발주 검토"
    out["권장 긴급 액션"] = urgent_action

    order_qty = pd.to_numeric(report_col(out, ["발주필요수량", "추가 발주 필요 수량", "발주 필요 수량"], 0), errors="coerce").fillna(0)
    order_mask = order_qty.gt(0)
    out["우선 액션"] = np.where(order_mask, "발주 필요", "발주 불필요")

    action_for_reason = out["권장 긴급 액션"].fillna("").astype(str).str.strip()
    action_for_reason = action_for_reason.where(action_for_reason.ne(""), "긴급 보충 검토")
    urgent_only = urgent_mask & ~order_mask
    urgent_combo = urgent_mask & order_mask
    out.loc[urgent_only, "판단 사유"] = "운송 도착 전 결품 진행 / " + action_for_reason.loc[urgent_only]
    out.loc[urgent_combo, "판단 사유"] = "안전재고 부족 + 입고 전 결품 진행 / " + action_for_reason.loc[urgent_combo] + " 병행"
    out.loc[urgent_mask, "논의필요"] = "Y"
    out.loc[urgent_mask, "발주검토여부"] = "필요"
    return out


def sort_order_review_output(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    action = report_col(out, ["우선 액션", "최종 액션"]).astype(str)
    out["_정렬_발주필요"] = order_needed_action_mask(action).astype(int)
    out["_정렬_금액"] = pd.to_numeric(report_col(out, ["추가 발주 필요 금액", "발주필요금액_KRW", "발주필요금액", "부족금액_KRW"], 0), errors="coerce").fillna(0)
    out["_정렬_수량"] = pd.to_numeric(report_col(out, ["추가 발주 필요 수량", "발주필요수량", "부족수량"], 0), errors="coerce").fillna(0)
    out["_정렬_상태"] = report_col(out, ["상태"], "정상").astype(str).map(ORDER_REVIEW_STATUS_SORT).fillna(9)
    out["_정렬_본사이동"] = pd.to_numeric(report_col(out, ["본사 이동 수량"], 0), errors="coerce").fillna(0)
    out = out.sort_values(
        ["_정렬_발주필요", "_정렬_금액", "_정렬_수량", "_정렬_상태", "_정렬_본사이동"],
        ascending=[False, False, False, True, False],
        kind="mergesort",
    )
    return out.drop(columns=["_정렬_발주필요", "_정렬_금액", "_정렬_수량", "_정렬_상태", "_정렬_본사이동"], errors="ignore")


def describe_transport_recommendation(row: pd.Series) -> str:
    action = str(row.get("우선 액션", "") or "")
    status = str(row.get("상태", "") or "")
    recommendation = str(row.get("운송 검토안", row.get("추천 운송수단", "")) or "")
    base_reason = str(row.get("판단 사유", "") or "").strip()
    urgent_action = str(row.get("권장 긴급 액션", "") or "").strip()

    if str(row.get("입고 전 결품 위험 여부", "")).strip() == "Y":
        return urgent_action or "긴급 보충 검토"
    if status == "운송대기":
        return "운송중 반영 시 충분"
    elif str(row.get("ETA 지연 플래그", "")).strip() == "Y":
        return "ETA 전 고갈 위험"
    elif status == "본사이동" or pd.to_numeric(row.get("본사 이동 수량", 0), errors="coerce") > 0:
        return "본사 재고 보완 필요"
    elif action == "발주 필요":
        if "항공" in recommendation or "이미 늦음" in recommendation or "긴급" in recommendation:
            return "항공 포함 긴급 검토"
        elif "해운" in recommendation:
            return "해운 L/T 내 보충 가능"
        elif recommendation and recommendation != "-":
            return f"{recommendation} 필요"
        return "안전재고 부족"
    elif "발주 불필요" in action:
        return "안전재고 충족"
    elif "판매없음" in action or "저판매" in action:
        return "판매 기준 제외"
    elif "운송 도착 후 검토" in action:
        return "도착 후에도 부족 가능"
    elif "미입고 반영 후 모니터링" in action:
        return "부족 없음, 모니터링"
    if "안전재고 목표 대비 부족" in base_reason:
        return "안전재고 부족"
    if "운송중 반영 시 충분" in base_reason:
        return "운송중 반영 시 충분"
    if "ETA 지연" in base_reason:
        return "ETA 전 고갈 위험"
    return base_reason or "기준 확인"


def recommended_response_from_action(action: object, recommendation: object = "") -> str:
    action_text = str(action or "")
    recommendation_text = str(recommendation or "")
    if action_text == "발주 필요 없음" or "운송중 도착 대기" in action_text or "발주 불필요" in action_text or "판매없음" in action_text or "저판매" in action_text:
        return "대기"
    if "본사 EU창고" in action_text or "본사 일부 이동" in action_text:
        return "본사 이동"
    if "ETA 지연 위험" in action_text or "항공" in recommendation_text or "긴급" in recommendation_text or "이미 늦음" in recommendation_text:
        return "항공 검토"
    if action_text == "발주 필요":
        return "발주 필요"
    return "대기"


def apply_order_review_reference_flags(df: pd.DataFrame, base_date: date | None = None) -> pd.DataFrame:
    out = df.copy()
    action = report_col(out, ["우선 액션", "최종 액션"]).astype(str)
    order_needed = order_needed_action_mask(action)
    sales_3m = pd.to_numeric(
        report_col(out, ["기준 3개월 판매수량", "기준_3M_판매수량", "최근 3개월 수요", "최근 3개월 판매수량"], 0),
        errors="coerce",
    ).fillna(0)
    order_qty = pd.to_numeric(
        report_col(out, ["발주 필요 수량", "추가 발주 필요 수량", "발주필요수량", "부족수량"], 0),
        errors="coerce",
    ).fillna(0)
    open_po_qty = pd.to_numeric(report_col(out, ["미입고 수량", "미입고", "미입고수량"], 0), errors="coerce").fillna(0)
    eu_available = pd.to_numeric(
        report_col(out, ["EU 가용재고", "EU 현지 재고", "유럽 가용재고", "유럽 재고"], 0),
        errors="coerce",
    ).fillna(0)

    flag = pd.Series("-", index=out.index, dtype=object)
    reason = report_col(out, ["판단 사유", "근거"], "").astype(str)
    urgent_action = report_col(out, ["권장 긴급 액션"], "").fillna("").astype(str).str.strip()
    urgent_action = urgent_action.where(urgent_action.ne(""), "긴급 보충 검토")
    pre_arrival_risk = report_col(out, ["입고 전 결품 위험 여부"], "N").astype(str).eq("Y")
    urgent_only = pre_arrival_risk & ~order_needed
    urgent_combo = pre_arrival_risk & order_needed

    priority_1 = order_needed & ~(urgent_only | urgent_combo) & sales_3m.le(0) & order_qty.gt(0)
    priority_2 = order_needed & ~(urgent_only | urgent_combo | priority_1) & eu_available.le(0) & sales_3m.gt(0)
    priority_3 = order_needed & ~(urgent_only | urgent_combo | priority_1 | priority_2)

    flag.loc[urgent_only | urgent_combo] = "입고 전 결품 위험"
    reason.loc[urgent_only] = "운송 도착 전 결품 진행 / " + urgent_action.loc[urgent_only]
    reason.loc[urgent_combo] = "안전재고 부족 + 입고 전 결품 진행 / " + urgent_action.loc[urgent_combo] + " 병행"
    flag.loc[priority_1] = "판매 기준 확인"
    reason.loc[priority_1] = "판매 이력 부족 / 신상·단종 여부 수동 확인"
    flag.loc[priority_2] = "현지 재고 부족"
    reason.loc[priority_2] = "현지 OOS 또는 현지 가용재고 부족 / 안전재고 목표수량 부족분 발주 필요"
    flag.loc[priority_3] = "-"
    reason.loc[priority_3] = "안전재고 목표수량 대비 현지 가용수량+운송중 수량 부족"

    out["참고 플래그"] = flag
    out["판단 사유"] = reason

    shortage_days = pd.to_numeric(
        report_col(out, ["쇼티지 예상일수", "쇼티지 예상 일수"], np.nan),
        errors="coerce",
    )
    depletion = kpi_mod.parse_date_series(report_col(out, ["예상 소진일", "고갈 예정일", "고갈 예상일"], ""))
    arrival = kpi_mod.parse_date_series(report_col(out, ["예상 입고일", "첫 입고 예정일", "최초 ETA"], ""))
    if base_date is None:
        base_series = kpi_mod.parse_date_series(report_col(out, ["기준일", "검토일"], korea_today()))
    else:
        base_series = pd.Series(pd.to_datetime(base_date), index=out.index)

    immediate_oos = shortage_days.eq(0) | (depletion.notna() & base_series.notna() & (depletion <= base_series))
    arrival_delay = arrival.notna() & depletion.notna() & (arrival > depletion)
    # 미입고 물량이 있는데 도착 근거(운송 ETA)가 전혀 없는 상태를 표시하는 데이터 완결성
    # 신호다. 원래는 발주가 필요한 행에만 붙어서, 발주는 불필요하지만 미입고 도착 시점을
    # 모르는 행이 아무 표시 없이 지나갔다. 발주 검토용 부분집합은
    # "ETA미확인 = Y && 우선 액션 = 발주 필요"로 그대로 뽑을 수 있다.
    eta_missing = open_po_qty.gt(0) & arrival.isna()

    out["즉시OOS여부"] = np.where(immediate_oos, "Y", "N")
    out["입고지연위험"] = np.where(arrival_delay, "Y", "N")
    out["ETA미확인"] = np.where(eta_missing, "Y", "N")
    return out
