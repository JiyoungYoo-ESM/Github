"""CMS API 응답 → 분석 엔진 입력 변환.

CMS API JSON을 분석 엔진이 기대하는 한글 컬럼 DataFrame 6개로 변환한다.
필드 매핑은 docs/CMS_API_GUIDE.md "1-1 필드 매핑" 표를 따른다.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from backend.services.upload_classification import (
    UPLOAD_KEY_TO_RESPONSE_ROLE,
    column_names_for_preview,
    matched_required_columns,
    missing_required_columns,
)
from core.common import (
    LOCAL_STOCK_UNIT_PRICE_CURRENCY_BY_ENTITY,
    TRANSPORT_REVIEW_REQUIRED,
)
from core.transport import normalize_transport_code

# stock/local → eu_stock
LOCAL_STOCK_FIELD_MAP = {
    "prod_cd": "상품코드",
    "prod_nm": "상품명",
    "bar_code": "바코드",
    "brand_nm": "브랜드",
    "stock_ucost": "현지 입고단가",
    "unit_cost_krw": "CMS 원화 입고단가",
    "stock_amount_krw": "CMS 재고금액(KRW)",
    "xrate": "적용 환율",
    "xrate_dt": "환율 기준일",
    "xrate_source": "환율 출처",
    "stock_qty": "재고수량",
    "hold_qty": "Hold수량",
    "avbl_qty": "EU 현지 가용수량",
    "sales_qty_3m": "최근 3개월 판매수량",
}

# stock/hq → hq_eu_stock
HQ_STOCK_FIELD_MAP = {
    **LOCAL_STOCK_FIELD_MAP,
    "avbl_qty": "본사 EU창고 가용수량",
}

# sales/local → sales_detail, sales/hq-to-eu → hq_to_eu_sales_detail
SALES_FIELD_MAP = {
    "prod_cd": "상품코드",
    "prod_nm": "상품명",
    "brand_nm": "브랜드",
    "qty": "수량",
    "amount": "금액",
    # CMS의 기존 amount_krw는 법인 기준통화 환산액이며 원화가 아니다.
    # 실제 원화 매출은 거래일 환율을 반영한 amount_krw_actual만 사용한다.
    "amount_krw": "법인 기준통화 환산금액",
    "amount_krw_actual": "실제 원화 환산금액",
    "xrate": "적용 환율",
    "xrate_dt": "환율 기준일",
    "xrate_source": "환율 출처",
    "curr": "Curr",
    "ship_dt": "출고일",
    "invc_no": "Invoice No",
    "biz_type": "Biz Type",
    "site": "Site",
}

# shipping/containers → shipping
SHIPPING_FIELD_MAP = {
    "prod_cd": "상품코드",
    "prod_nm": "상품명",
    "brand_nm": "브랜드",
    "cust_nm": "거래처",
    "qty": "수량",
    "amount": "금액",
    "amount_krw": "CMS 원화 환산금액",
    "xrate": "적용 환율",
    "xrate_dt": "환율 기준일",
    "xrate_source": "환율 출처",
    "curr": "Curr",
    "remark": "Invoice 비고",  # 여기서 운송수단(해운/항공/철송)을 자동 추출
    "invc_no": "Invoice No",
    "pckg_no": "Packing No",
}

# open-po → open_po
OPEN_PO_FIELD_MAP = {
    "prod_cd": "상품코드",
    "prod_nm": "상품명",
    "bar_code": "바코드",
    "brand_nm": "브랜드",
    "open_qty": "미입고 수량",
    "open_amt": "미입고 금액",
    "po_qty": "PO 수량",
    "pnfm_qty": "PNFM 수량",
    "pnfm_confirmed_qty": "PNFM확정 수량",
    "inbound_in_progress_qty": "입고진행중 수량",
    "completed_qty": "입고완료 수량",
}

CMS_KEY_TO_ANALYSIS_KEY = {
    "stock_local": "eu_stock",
    "stock_hq": "hq_eu_stock",
    "sales_local": "sales_detail",
    "sales_hq": "hq_to_eu_sales_detail",
    "shipping": "shipping",
    "open_po": "open_po",
}


def _mapped_frame(rows: list[dict[str, object]] | None, field_map: dict[str, str]) -> pd.DataFrame:
    df = pd.DataFrame(rows or [])
    out = pd.DataFrame(index=df.index)
    for source, dest in field_map.items():
        out[dest] = df[source] if source in df.columns else None
    return out


def _stock_frame(
    rows: list[dict[str, object]] | None,
    *,
    hq: bool = False,
    entity_code: str = "PL",
) -> pd.DataFrame:
    # 전부 NaN인 컬럼이 분석 내부에서 .str accessor 에러를 내므로 문자열화 (가이드 규칙 3)
    field_map = HQ_STOCK_FIELD_MAP if hq else LOCAL_STOCK_FIELD_MAP
    out = _mapped_frame(rows, field_map)
    df = pd.DataFrame(rows or [])
    if "현지 입고단가" in out.columns and "unit_cost" in df.columns:
        out["현지 입고단가"] = out["현지 입고단가"].where(
            out["현지 입고단가"].notna() & (out["현지 입고단가"].astype(str).str.strip() != ""),
            df["unit_cost"],
        )
    code = str(entity_code or "PL").strip().upper()
    currency_code = LOCAL_STOCK_UNIT_PRICE_CURRENCY_BY_ENTITY.get(code)
    if currency_code is None:
        raise ValueError(f"지원하지 않는 법인 코드입니다: {code}")
    rate_source = (
        out["환율 출처"].fillna("").astype(str).str.strip().str.upper()
        if "환율 출처" in out.columns
        else pd.Series("", index=out.index, dtype=object)
    )
    # stock/hq는 본사 원화 원천(BASE_KRW)이고, stock/local만 법인 기준통화다.
    # 최신 API 메타가 없는 업로드 호환 경로에서는 기존 entity 기본통화를 유지한다.
    out["현지 입고단가 통화"] = np.where(
        rate_source.eq("BASE_KRW"),
        "KRW",
        currency_code,
    )
    # 기존 V1/V2 및 과거 저장 결과와의 입력 호환을 위한 별칭이다. 신규 계산은
    # 반드시 현지 입고단가/현지 입고단가 통화를 우선 사용한다.
    out["EU 입고단가"] = out["현지 입고단가"]
    out["EU 입고단가 통화"] = out["현지 입고단가 통화"]
    return out.fillna("").astype(str)


_USA_REMARK_ETA_PATTERN = re.compile(
    r"\bETA\s*[:(\- ]*\s*(?P<month>\d{1,2})\s*/\s*(?P<day>\d{1,2})",
    flags=re.IGNORECASE,
)


def _usa_remark_eta(ship: pd.Series, remark: pd.Series) -> pd.Series:
    """Extract a strict ``ETA M/D`` using the row's shipment year.

    A remark without the literal ETA marker, an invalid calendar date, or an
    ETA earlier than its shipment date is left blank for manual review.  This
    avoids inventing a year or treating unrelated numbers as an arrival date.
    """

    shipped_at = pd.to_datetime(ship, errors="coerce")
    extracted = remark.fillna("").astype(str).str.extract(_USA_REMARK_ETA_PATTERN)
    parsed: list[pd.Timestamp | pd.NaTType] = []
    for row_index, shipped_value in shipped_at.items():
        month = pd.to_numeric(extracted.at[row_index, "month"], errors="coerce")
        day = pd.to_numeric(extracted.at[row_index, "day"], errors="coerce")
        if pd.isna(shipped_value) or pd.isna(month) or pd.isna(day):
            parsed.append(pd.NaT)
            continue
        try:
            candidate = pd.Timestamp(
                year=int(shipped_value.year),
                month=int(month),
                day=int(day),
            )
        except ValueError:
            parsed.append(pd.NaT)
            continue
        parsed.append(candidate if candidate >= shipped_value.normalize() else pd.NaT)
    return pd.Series(parsed, index=ship.index, dtype="datetime64[ns]")


_USA_CONTAINER_VOYAGE_PATTERN = re.compile(
    r"^[A-Za-z]{2,4}\s*\d+\s*(?:st|nd|rd|th)\b",
    re.IGNORECASE,
)


def _usa_unmatched_transport_mode(remark: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Classify USA rows that have no matching lead-time API shipment.

    Explicit AIR/OCEAN text wins. A numbered voyage on the CMS ocean-container
    source is ocean. Anything else remains unclassified for manual review.
    """

    text = remark.fillna("").astype(str).str.strip()
    code = text.map(lambda value: normalize_transport_code(value, "USA"))
    explicit = code.map({"OCEAN": "해운", "AIR": "항공"}).fillna("")
    voyage = text.str.match(_USA_CONTAINER_VOYAGE_PATTERN).fillna(False).astype(bool)
    mode = explicit.where(explicit.ne(""), np.where(voyage, "해운", ""))
    source = pd.Series(
        np.where(
            explicit.ne(""),
            "Invoice 비고",
            np.where(voyage, "해상컨테이너 원천", "운송수단 원천 확인필요"),
        ),
        index=remark.index,
        dtype=object,
    )
    return pd.Series(mode, index=remark.index, dtype=object), source


def _lead_time_transport_values(
    lead_time_rows: list[dict[str, object]] | None,
) -> tuple[
    dict[str, tuple[str, str]],
    dict[str, tuple[str, str]],
    set[str],
    set[str],
]:
    """Index the lead-time feed's ship-via and resolved mode by shipment id.

    The feed reports ``ship_via`` (carrier) together with ``transport_mode``
    (해운/항공). Both are retained so undefined mappings can be sent to manual
    review instead of being guessed from another source.
    """

    package_values: dict[str, set[tuple[str, str]]] = {}
    invoice_values: dict[str, set[tuple[str, str]]] = {}
    for row in lead_time_rows or []:
        if not isinstance(row, dict):
            continue
        ship_via = str(row.get("ship_via") or "").strip()
        mode = str(row.get("transport_mode") or "").strip()
        value = (ship_via, mode)
        package_no = str(row.get("pckg_no") or "").strip()
        invoice_no = str(row.get("invc_no") or "").strip()
        if package_no:
            package_values.setdefault(package_no, set()).add(value)
        if invoice_no:
            invoice_values.setdefault(invoice_no, set()).add(value)

    # A conflicting identifier is not safe to classify automatically.  Keep it
    # out of the index so the existing confirmation-required path remains
    # visible instead of selecting whichever API row happened to arrive first.
    by_package = {
        identifier: next(iter(values))
        for identifier, values in package_values.items()
        if len(values) == 1
    }
    by_invoice = {
        identifier: next(iter(values))
        for identifier, values in invoice_values.items()
        if len(values) == 1
    }
    return by_package, by_invoice, set(package_values), set(invoice_values)


def _shipping_frame(
    rows: list[dict[str, object]] | None,
    *,
    entity_code: str = "PL",
    lead_time_rows: list[dict[str, object]] | None = None,
) -> pd.DataFrame:
    df = pd.DataFrame(rows or [])
    out = _mapped_frame(rows, SHIPPING_FIELD_MAP)
    ship = df["ship_dt"] if "ship_dt" in df.columns else pd.Series(None, index=df.index, dtype=object)
    eta = df["eta_dt"] if "eta_dt" in df.columns else pd.Series(None, index=df.index, dtype=object)
    eta_source = pd.Series("", index=df.index, dtype=object)
    explicit_eta = pd.to_datetime(eta, errors="coerce")
    eta_source.loc[explicit_eta.notna()] = "CMS eta_dt"
    if str(entity_code or "").strip().upper() == "USA":
        remark_eta = _usa_remark_eta(ship, out.get("Invoice 비고", pd.Series("", index=df.index)))
        fallback_mask = explicit_eta.isna() & remark_eta.notna()
        eta = pd.Series(eta, index=df.index).where(~fallback_mask, remark_eta.dt.strftime("%Y-%m-%d"))
        eta_source.loc[fallback_mask] = "Invoice 비고 ETA"
    out["출고일"] = ship
    out["ETA"] = eta
    out["ETA 출처"] = eta_source

    # Resolve lead-time API rows first. A matched but undefined ship_via stays
    # in manual review; only shipments absent from that API may use the shipping
    # source's explicit AIR/OCEAN or numbered ocean-voyage fallback.
    by_package, by_invoice, package_seen, invoice_seen = _lead_time_transport_values(
        lead_time_rows
    )

    def identifier(column: str) -> pd.Series:
        if column not in df.columns:
            return pd.Series([""] * len(df), index=df.index, dtype=object)
        return df[column].fillna("").astype(str).str.strip()

    package_id = identifier("pckg_no")
    invoice_id = identifier("invc_no")
    resolved = package_id.map(by_package)
    resolved = resolved.where(resolved.notna(), invoice_id.map(by_invoice))
    api_matched = package_id.isin(package_seen) | invoice_id.isin(invoice_seen)
    if str(entity_code or "").strip().upper() == "USA":
        ship_via = resolved.map(
            lambda value: value[0] if isinstance(value, tuple) else ""
        ).astype(str)
        mode = resolved.map(
            lambda value: value[1] if isinstance(value, tuple) else ""
        ).astype(str)
        api_defined = api_matched & ship_via.str.strip().ne("") & mode.str.strip().ne("")
        fallback_mode, fallback_source = _usa_unmatched_transport_mode(
            out.get("Invoice 비고", pd.Series("", index=df.index))
        )
        fallback_defined = ~api_matched & fallback_mode.str.strip().ne("")
        out["운송수단"] = np.select(
            [api_defined, fallback_defined],
            [mode, fallback_mode],
            default=TRANSPORT_REVIEW_REQUIRED,
        )
        out["운송수단 API 원본값"] = ship_via
        out["운송수단 출처"] = np.select(
            [api_defined, api_matched, fallback_defined],
            ["CMS lead-time ship_via", "CMS lead-time ship_via 확인필요", fallback_source],
            default="운송수단 원천 확인필요",
        )
    elif by_package or by_invoice:
        mode = resolved.map(
            lambda value: value[1] if isinstance(value, tuple) else ""
        )
        out["운송수단"] = mode.fillna("")
        out["운송수단 출처"] = resolved.notna().map(
            {True: "CMS lead-time", False: ""}
        )
    return out


def build_uploaded_data_from_cms(
    raw: dict[str, list[dict[str, object]]],
    *,
    entity_code: str = "PL",
) -> dict[str, pd.DataFrame]:
    code = str(entity_code or "").strip().upper()
    sales_local = _mapped_frame(raw.get("sales_local"), SALES_FIELD_MAP)
    sales_hq = _mapped_frame(raw.get("sales_hq"), SALES_FIELD_MAP)
    open_po = _mapped_frame(raw.get("open_po"), OPEN_PO_FIELD_MAP)

    for sales_frame in (sales_local, sales_hq):
        # 기존 내부 소비자가 사용하는 환산금액 별칭도 이제 실제 KRW만 가리킨다.
        # 원통화 단가 계산은 명시적으로 금액 컬럼을 사용한다.
        sales_frame["환산금액"] = sales_frame["실제 원화 환산금액"]

    if code == "USA":
        # US open-po amount is KRW, not local USD.  Keep the source value for
        # audit/inspection but do not feed it into a local-currency unit-price
        # fallback. Quantity fields remain fully usable.
        if "미입고 금액" in open_po.columns:
            open_po["미입고 금액(KRW)"] = open_po["미입고 금액"]
            open_po["미입고 금액"] = None

    return {
        "eu_stock": _stock_frame(raw.get("stock_local"), entity_code=code),
        "hq_eu_stock": _stock_frame(raw.get("stock_hq"), hq=True, entity_code=code),
        "sales_detail": sales_local,
        "hq_to_eu_sales_detail": sales_hq,
        "shipping": _shipping_frame(
            raw.get("shipping"),
            entity_code=code,
            lead_time_rows=raw.get("lead_time"),
        ),
        "open_po": open_po,
    }


def build_cms_classifications(uploaded_data: dict[str, pd.DataFrame], as_of: str) -> list[dict[str, object]]:
    """run_core_analysis_from_uploaded_data가 기대하는 classifications 메타데이터 생성."""
    endpoint_by_key = {analysis_key: cms_key for cms_key, analysis_key in CMS_KEY_TO_ANALYSIS_KEY.items()}
    classifications: list[dict[str, object]] = []
    for key, df in uploaded_data.items():
        classifications.append(
            {
                "key": key,
                "role": UPLOAD_KEY_TO_RESPONSE_ROLE.get(key, key),
                "original_name": f"CMS API: {endpoint_by_key.get(key, key)} (as_of={as_of})",
                "saved_name": "",
                "source": "cms_api",
                "score": None,
                "rows": int(len(df)),
                "columns": int(len(df.columns)),
                "detected_columns": column_names_for_preview(df),
                "matched_required_columns": matched_required_columns(df, key),
                "missing_required_columns": missing_required_columns(df, key),
            }
        )
    return classifications
