from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


DOWNLOADS = Path.home() / "Downloads"
WORKDIR = Path(__file__).resolve().parents[1]
FINAL_CANDIDATES = [
    DOWNLOADS / "ESM_발주검토_20260514 (1).xlsx",
    DOWNLOADS / "ESM_발주검토_20260514.xlsx",
    WORKDIR / "ESM_발주검토_20260514.xlsx",
]

BASE_DATE = pd.Timestamp("2026-05-14")
PERIOD_START = pd.Timestamp("2026-02-12")
PERIOD_END = pd.Timestamp("2026-05-13")
SAFETY_MONTHS = 3.0
EUR_KRW_RATE = 1726.89

LEAD_A = {"항공": 15, "트럭": 30, "철송": 30, "해운": 80}
LEAD_B = {"항공": 17, "트럭": 33, "철송": 35, "해운": 87}

NON_PRODUCT_SKU_TOKENS = {
    "total",
    "subtotal",
    "grandtotal",
    "sum",
    "deliverycharge",
    "deliveryfee",
    "shippingcharge",
    "shippingfee",
    "freight",
    "freightcharge",
    "합계",
    "총계",
    "소계",
    "배송비",
    "운송비",
    "운임",
    "운임비",
}


def clean_code(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none"}:
        return ""
    return re.sub(r"\.0$", "", text)


def compact_code(value: object) -> str:
    return re.sub(r"[\s_\-()/]+", "", clean_code(value)).lower()


def is_product_sku(value: object) -> bool:
    text = clean_code(value)
    if not text:
        return False
    return compact_code(text) not in NON_PRODUCT_SKU_TOKENS


def is_probable_cos_sku(value: object) -> bool:
    text = clean_code(value)
    return bool(re.match(r"^cos", text, flags=re.IGNORECASE))


def to_num(series_or_value: object) -> pd.Series | float:
    if isinstance(series_or_value, pd.Series):
        return pd.to_numeric(
            series_or_value.astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        ).fillna(0)
    if series_or_value is None or (isinstance(series_or_value, float) and math.isnan(series_or_value)):
        return 0.0
    return float(pd.to_numeric(str(series_or_value).replace(",", "").strip(), errors="coerce") or 0)


def norm_col(value: object) -> str:
    return re.sub(r"[\s_\-()/]+", "", str(value)).lower()


def find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cmap = {norm_col(col): col for col in df.columns}
    for candidate in candidates:
        key = norm_col(candidate)
        if key in cmap:
            return cmap[key]
    for candidate in candidates:
        key = norm_col(candidate)
        for compact, original in cmap.items():
            if key and (key in compact or compact in key):
                return original
    return None


def read_html_xls(path: Path) -> pd.DataFrame:
    with path.open("rb") as handle:
        df = pd.read_html(handle, header=0)[0]
    if df.empty:
        return df
    first = [str(x).strip() for x in df.iloc[0].tolist()]
    if any(x in first for x in ["No.", "No", "상품코드"]) or sum(str(c).startswith("Unnamed") for c in df.columns) > len(df.columns) // 2:
        df.columns = [str(x).strip() for x in df.iloc[0].tolist()]
        df = df.iloc[1:].reset_index(drop=True)
    df.columns = [str(col).strip() for col in df.columns]
    return df


def read_raw_file(name: str) -> pd.DataFrame:
    path = DOWNLOADS / name
    if not path.exists():
        return pd.DataFrame()
    return read_html_xls(path)


def aggregate(df: pd.DataFrame, code_col: str, value_cols: dict[str, str], name_col: str | None = None) -> pd.DataFrame:
    if df.empty or code_col not in df.columns:
        return pd.DataFrame(columns=["상품코드", "상품명", *value_cols.keys()])
    out = pd.DataFrame({"상품코드": df[code_col].map(clean_code)})
    out = out[out["상품코드"].ne("")]
    if name_col and name_col in df.columns:
        out["상품명"] = df.loc[out.index, name_col].astype(str)
    else:
        out["상품명"] = ""
    for label, col in value_cols.items():
        out[label] = to_num(df.loc[out.index, col]) if col in df.columns else 0
    agg_spec = {label: "sum" for label in value_cols}
    agg_spec["상품명"] = "first"
    return out.groupby("상품코드", as_index=False).agg(agg_spec)


def normalize_biz_type(value: object) -> str:
    text = str(value).strip().upper()
    text = re.sub(r"[\s_-]+", "", text)
    if text in {"EUOVERSEAS", "EUOVERSAES", "EUOVERSEA"}:
        return "EU-OVERSEAS"
    if text in {"EUPL", "EU-POLAND", "POLAND"}:
        return "EU-PL"
    if text in {"ETC", "기타"}:
        return "ETC"
    return str(value).strip().upper()


def filter_sales_main(sales: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    code_col = find_col(sales, ["상품코드", "SKU"])
    biz_col = find_col(sales, ["Biz Type", "BizType", "비즈타입"])
    date_col = find_col(sales, ["출고일", "판매일", "일자", "date"])
    qty_col = find_col(sales, ["수량", "판매수량", "qty"])
    amount_col = find_col(sales, ["환산금액", "금액", "매출", "amount"])

    work = sales.copy()
    work["SKU"] = work[code_col].map(clean_code) if code_col else ""
    work["BizType_정규화"] = work[biz_col].map(normalize_biz_type) if biz_col else ""
    work["수량_NUM"] = to_num(work[qty_col]) if qty_col else 0
    work["환산금액_NUM"] = to_num(work[amount_col]) if amount_col else 0
    if date_col:
        dates = pd.to_datetime(work[date_col], errors="coerce")
        date_mask = (dates >= PERIOD_START) & (dates <= PERIOD_END)
    else:
        date_mask = pd.Series([True] * len(work), index=work.index)

    accounting_keywords = [
        "TP ADJUST",
        "TP-ADJUSTMENT",
        "ADVANCE_TO_RELATED_PARTY",
        "ADVANCE TO RELATED PARTY",
        "CUM",
        "기타제조사",
    ]
    biz = work["BizType_정규화"]
    excluded_biz = biz.isin({"자사간거래", "STAFFSALES", "FREE SAMPLE", "반품"})
    excluded_biz = excluded_biz | biz.astype(str).str.contains("STAFFSALES|FREE\\s*SAMPLE|반품|자사간거래|추후상계", regex=True, na=False)
    for keyword in accounting_keywords:
        excluded_biz = excluded_biz | biz.astype(str).str.contains(keyword, regex=False, na=False)
    allowed_biz = biz.isin({"EU-OVERSEAS", "EU-PL"})
    product_mask = work["SKU"].map(is_product_sku)
    valid_cos_mask = work["SKU"].map(is_probable_cos_sku)
    non_sku = work[~product_mask | ~valid_cos_mask].copy()
    reflected = work[date_mask & allowed_biz & ~excluded_biz & product_mask].copy()
    excluded = work[~(date_mask & allowed_biz & ~excluded_biz & product_mask)].copy()
    return reflected, excluded, non_sku


def normalize_transport_mode(value: object) -> str:
    text = str(value).strip()
    upper = text.upper()
    if any(token in upper for token in ["AIR", "AIRPLANE", "항공", "항공운송"]):
        return "항공"
    if any(token in upper for token in ["RAIL", "TRAIN", "철송", "RAILWAY"]):
        return "철송"
    if any(token in upper for token in ["TRUCK", "TRUCKING", "트럭", "트럭킹"]):
        return "트럭"
    if any(token in upper for token in ["SEA", "OCEAN", "해상", "해운", "선박", "VESSEL"]):
        return "해운"
    return text or "해운"


def prepare_shipping(shipping: pd.DataFrame) -> pd.DataFrame:
    code_col = find_col(shipping, ["상품코드", "SKU"])
    name_col = find_col(shipping, ["상품명"])
    qty_col = find_col(shipping, ["수량", "운송수량", "qty"])
    amount_col = find_col(shipping, ["금액", "amount"])
    date_col = find_col(shipping, ["출고일", "선적일", "shipdate"])
    mode_col = find_col(shipping, ["Invoice 비고", "비고", "운송수단", "배송수단"])
    out = shipping.copy()
    out["SKU"] = out[code_col].map(clean_code) if code_col else ""
    out["상품명_정리"] = out[name_col].astype(str) if name_col else ""
    out["수량_NUM"] = to_num(out[qty_col]) if qty_col else 0
    out["금액_EUR"] = to_num(out[amount_col]) if amount_col else 0
    out["출고일_DT"] = pd.to_datetime(out[date_col], errors="coerce") if date_col else pd.NaT
    out["운송수단_정규화"] = out[mode_col].map(normalize_transport_mode) if mode_col else "해운"
    out["ETA_A"] = out.apply(lambda r: r["출고일_DT"] + pd.Timedelta(days=LEAD_A.get(r["운송수단_정규화"], 80)) if pd.notna(r["출고일_DT"]) else pd.NaT, axis=1)
    out["ETA_B"] = out.apply(lambda r: r["출고일_DT"] + pd.Timedelta(days=LEAD_B.get(r["운송수단_정규화"], 87)) if pd.notna(r["출고일_DT"]) else pd.NaT, axis=1)
    return out


def make_compare_rows(raw_agg: pd.DataFrame, final_agg: pd.DataFrame, raw_value: str, final_value: str, item: str, source: str) -> pd.DataFrame:
    left = raw_agg[["상품코드", "상품명", raw_value]].rename(columns={raw_value: "원본 집계값"})
    right_cols = ["상품코드", final_value]
    if "상품명" in final_agg.columns:
        right_cols.append("상품명")
    right = final_agg[right_cols].rename(columns={final_value: "최종 산출값", "상품명": "최종 상품명"})
    merged = left.merge(right, on="상품코드", how="outer")
    merged["상품명"] = merged["상품명"].fillna(merged.get("최종 상품명", ""))
    merged["원본 집계값"] = pd.to_numeric(merged["원본 집계값"], errors="coerce").fillna(0)
    merged["최종 산출값"] = pd.to_numeric(merged["최종 산출값"], errors="coerce").fillna(0)
    merged["차이"] = merged["최종 산출값"] - merged["원본 집계값"]
    merged["차이율"] = np.where(merged["원본 집계값"].abs() > 0, merged["차이"] / merged["원본 집계값"], np.nan)
    merged["비교항목"] = item
    merged["원본 파일명"] = source
    merged["매칭 방식"] = "상품코드 exact"
    merged["일치 여부"] = np.select(
        [
            merged["차이"].abs() <= 0.5,
            (merged["차이"].abs() <= 1.0) & (merged["차이"].abs() > 0.5),
            merged["원본 집계값"].ne(0) & merged["최종 산출값"].eq(0),
            merged["원본 집계값"].eq(0) & merged["최종 산출값"].ne(0),
        ],
        ["일치", "반올림차이", "산출누락", "원본매칭확인필요"],
        default="불일치",
    )
    merged["차이 원인 추정"] = np.select(
        [
            merged["일치 여부"].eq("일치"),
            merged["일치 여부"].eq("반올림차이"),
            merged["일치 여부"].eq("산출누락"),
            merged["일치 여부"].eq("원본매칭확인필요"),
        ],
        ["-", "반올림 차이", "원본에는 있으나 최종 산출 파일에 없음", "최종 산출 파일에는 있으나 원본 집계에 없음"],
        default="확인 필요",
    )
    return merged[["상품코드", "상품명", "비교항목", "원본 파일명", "원본 집계값", "최종 산출값", "차이", "차이율", "일치 여부", "매칭 방식", "차이 원인 추정"]]


def read_final_table(path: Path, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name)
    for col in df.columns:
        if "상품코드" in str(col) or str(col).strip() in {"SKU", "상품코드"}:
            df[col] = df[col].map(clean_code)
    return df


def date_from_eta_header(header: str) -> pd.Timestamp | None:
    match = re.search(r"ETA\s+(\d{2})/(\d{2})", str(header))
    if not match:
        return None
    month, day = map(int, match.groups())
    return pd.Timestamp(date(2026, month, day))


def main() -> None:
    final_path = next((p for p in FINAL_CANDIDATES if p.exists()), None)
    if final_path is None:
        raise FileNotFoundError("최종 산출 파일을 찾지 못했습니다.")

    files = {
        "산출": final_path,
        "재고": DOWNLOADS / "재고.xls",
        "본사 EU창고 재고": DOWNLOADS / "재고 (1).xls",
        "판매내역상세": DOWNLOADS / "판매내역상세.xls",
        "판매내역상세 자사간거래": DOWNLOADS / "판매내역상세 (1).xls",
        "해상/운송중": DOWNLOADS / "해상컨테이너상세내역.xls",
        "미입고": DOWNLOADS / "미입고현황.xls",
    }

    eu_stock = read_raw_file("재고.xls")
    hq_stock = read_raw_file("재고 (1).xls")
    sales_main = read_raw_file("판매내역상세.xls")
    sales_related = read_raw_file("판매내역상세 (1).xls")
    shipping_raw = read_raw_file("해상컨테이너상세내역.xls")
    open_po = read_raw_file("미입고현황.xls")

    final_review = read_final_table(final_path, "발주 검토")
    final_internal = read_final_table(final_path, "ESM 내부 검토")
    final_raw = read_final_table(final_path, "상세 RAW")
    final_eta = read_final_table(final_path, "ETA 타임라인_검토")
    final_stockout = read_final_table(final_path, "재고 소진 캘린더")
    final_sku_check = read_final_table(final_path, "SKU 확인필요")
    final_excluded = read_final_table(final_path, "샘플_단종 참고")

    # Raw total summaries.
    eu_code, eu_name = find_col(eu_stock, ["상품코드"]), find_col(eu_stock, ["상품명"])
    hq_code, hq_name = find_col(hq_stock, ["상품코드"]), find_col(hq_stock, ["상품명"])
    sales_code = find_col(sales_main, ["상품코드"])
    shipping = prepare_shipping(shipping_raw)
    po_code = find_col(open_po, ["상품코드"])

    stock_cols = {
        "재고수량": find_col(eu_stock, ["재고 수량", "재고수량"]),
        "Hold수량": find_col(eu_stock, ["Hold 수량", "Hold수량"]),
        "가용수량": find_col(eu_stock, ["가용 수량", "가용수량"]),
        "재고금액": find_col(eu_stock, ["재고 금액"]),
        "Hold금액": find_col(eu_stock, ["Hold 금액"]),
        "가용금액": find_col(eu_stock, ["가용 금액"]),
        "PA_CA_판매수량": find_col(eu_stock, ["판매 수량 (3개월내 PA+CA)", "최근 3개월 판매수량"]),
    }
    hq_cols = {
        "재고수량": find_col(hq_stock, ["재고 수량", "재고수량"]),
        "Hold수량": find_col(hq_stock, ["Hold 수량", "Hold수량"]),
        "가용수량": find_col(hq_stock, ["가용 수량", "가용수량"]),
        "재고금액": find_col(hq_stock, ["재고 금액"]),
        "Hold금액": find_col(hq_stock, ["Hold 금액"]),
        "가용금액": find_col(hq_stock, ["가용 금액"]),
    }
    stock_agg = aggregate(eu_stock, eu_code, stock_cols, eu_name)
    hq_agg = aggregate(hq_stock, hq_code, hq_cols, hq_name)

    sales_reflected, sales_excluded, non_sku_sales = filter_sales_main(sales_main)
    sales_name = find_col(sales_reflected, ["상품명"])
    sales_agg = aggregate(
        sales_reflected,
        "SKU",
        {"판매수량": "수량_NUM", "환산금액": "환산금액_NUM"},
        sales_name if sales_name in sales_reflected.columns else None,
    )

    shipping_product = shipping[shipping["SKU"].map(is_product_sku)].copy()
    shipping_agg = aggregate(shipping_product, "SKU", {"운송중수량": "수량_NUM", "금액_EUR": "금액_EUR"}, "상품명_정리")
    po_qty_col = find_col(open_po, ["미입고 수량", "미입고수량", "수량"])
    po_amount_col = find_col(open_po, ["미입고 금액", "미입고금액"])
    po_name = find_col(open_po, ["상품명"])
    po = open_po.copy()
    po["SKU"] = po[po_code].map(clean_code) if po_code else ""
    po_agg = aggregate(po, "SKU", {"미입고수량": po_qty_col, "미입고금액": po_amount_col}, po_name)

    final_by_sku = final_raw.rename(columns={"상품코드": "상품코드"}).copy()
    final_by_sku["상품코드"] = final_by_sku["상품코드"].map(clean_code)
    final_internal_sku = final_internal.copy()
    final_internal_sku["상품코드"] = final_internal_sku["상품코드"].map(clean_code)

    total_rows = []

    def add_total(source: str, metric: str, raw_value: object, final_value: object = "", note: str = "") -> None:
        raw_num = pd.to_numeric(raw_value, errors="coerce")
        final_num = pd.to_numeric(final_value, errors="coerce")
        diff = "" if pd.isna(final_num) or pd.isna(raw_num) else float(final_num - raw_num)
        total_rows.append(
            {
                "구분": source,
                "항목": metric,
                "원본값": raw_value,
                "최종산출값": final_value,
                "차이": diff,
                "비고": note,
            }
        )

    add_total("재고", "원본 전체 행 수", len(eu_stock))
    add_total("재고", "상품코드 수", stock_agg["상품코드"].nunique())
    for col in ["재고수량", "Hold수량", "가용수량", "재고금액", "Hold금액", "가용금액"]:
        add_total("재고", col + " 합계", stock_agg[col].sum(), final_by_sku.get("EU 현지 가용수량", pd.Series(dtype=float)).sum() if col == "가용수량" else "", "최종 산출은 정상 본품/필터 적용 결과라 원본 전체와 차이 가능")

    add_total("본사 EU창고 재고", "원본 전체 행 수", len(hq_stock))
    add_total("본사 EU창고 재고", "상품코드 수", hq_agg["상품코드"].nunique())
    for col in ["재고수량", "Hold수량", "가용수량", "재고금액", "Hold금액", "가용금액"]:
        final_col = "본사 EU창고 가용수량" if col == "가용수량" else ""
        add_total("본사 EU창고 재고", col + " 합계", hq_agg[col].sum(), final_by_sku.get(final_col, pd.Series(dtype=float)).sum() if final_col else "", "본사 EU창고 단독 SKU는 별도 시트 확인")

    add_total("판매", "원본 전체 행 수", len(sales_main))
    add_total("판매", "상품코드 수", sales_main[sales_code].map(clean_code).nunique() if sales_code else "")
    add_total("판매", "판매수량 합계", to_num(sales_main[find_col(sales_main, ["수량"])]).sum())
    add_total("판매", "환산금액 합계", to_num(sales_main[find_col(sales_main, ["환산금액"])]).sum())
    add_total("판매", "최종 반영 판매수량 합계", sales_reflected["수량_NUM"].sum(), final_by_sku.get("판매내역상세_3M_판매수량", pd.Series(dtype=float)).sum())
    add_total("판매", "최종 반영 환산금액 합계", sales_reflected["환산금액_NUM"].sum())
    add_total("판매", "Delivery Charge 등 비-SKU 제외 행 수", len(non_sku_sales))
    add_total("판매", "Delivery Charge 등 비-SKU 제외 수량", non_sku_sales["수량_NUM"].sum() if "수량_NUM" in non_sku_sales else 0)
    add_total("판매", "Delivery Charge 등 비-SKU 제외 금액", non_sku_sales["환산금액_NUM"].sum() if "환산금액_NUM" in non_sku_sales else 0)

    add_total("판매내역상세 자사간거래", "원본 전체 행 수", len(sales_related), "", "현재 산식 미반영, 향후 ETA 연결 검증용 참고")
    if not sales_related.empty:
        qty_col = find_col(sales_related, ["수량"])
        amt_col = find_col(sales_related, ["환산금액"])
        code_col = find_col(sales_related, ["상품코드"])
        add_total("판매내역상세 자사간거래", "수량 합계", to_num(sales_related[qty_col]).sum() if qty_col else 0)
        add_total("판매내역상세 자사간거래", "환산금액 합계", to_num(sales_related[amt_col]).sum() if amt_col else 0)
        add_total("판매내역상세 자사간거래", "상품코드 수", sales_related[code_col].map(clean_code).nunique() if code_col else 0)

    add_total("해상/운송중", "원본 전체 행 수", len(shipping_raw), note="Total 합계행 포함")
    add_total("해상/운송중", "집계 대상 SKU 행 수", len(shipping_product), note="Total 합계행/비SKU 행 제외")
    add_total("해상/운송중", "상품코드 수", shipping_product["SKU"].nunique())
    add_total("해상/운송중", "Total 합계행/비SKU 제외 행 수", len(shipping) - len(shipping_product))
    add_total("해상/운송중", "전체 운송중 수량 합계", shipping_product["수량_NUM"].sum(), final_by_sku.get("운송중 수량", pd.Series(dtype=float)).sum())
    for mode in ["해운", "항공", "철송", "트럭"]:
        add_total("해상/운송중", f"{mode} 수량 합계", shipping_product.loc[shipping_product["운송수단_정규화"].eq(mode), "수량_NUM"].sum())
    add_total("해상/운송중", "출고일이 있는 행 수", int(shipping_product["출고일_DT"].notna().sum()))
    add_total("해상/운송중", "ETA 계산 가능 행 수", int(shipping_product["ETA_B"].notna().sum()))
    add_total("해상/운송중", "ETA 계산 불가 행 수", int(shipping_product["ETA_B"].isna().sum()))

    add_total("미입고", "원본 전체 행 수", len(open_po))
    add_total("미입고", "상품코드 수", po_agg["상품코드"].nunique())
    add_total("미입고", "미입고 수량 합계", po_agg["미입고수량"].sum(), final_by_sku.get("미입고수량", pd.Series(dtype=float)).sum(), "현 로직은 발주필요수량 산정 미반영, 참고값 표시")
    add_total("미입고", "미입고 금액 합계", po_agg["미입고금액"].sum())

    compare_frames = [
        make_compare_rows(stock_agg, final_by_sku, "가용수량", "EU 현지 가용수량", "EU 현지 가용재고", files["재고"].name),
        make_compare_rows(stock_agg, final_internal_sku, "재고수량", "유럽 현재 재고", "EU 현지 현재재고", files["재고"].name),
        make_compare_rows(stock_agg, final_internal_sku, "PA_CA_판매수량", "기준 3개월 판매수량(재고 PA+CA)", "재고 PA+CA 3개월 판매수량", files["재고"].name),
        make_compare_rows(sales_agg, final_internal_sku, "판매수량", "검증용 3개월 판매수량(판매내역상세)", "판매내역상세 3개월 판매수량", files["판매내역상세"].name),
        make_compare_rows(shipping_agg, final_internal_sku, "운송중수량", "운송중 수량", "운송중 수량", files["해상/운송중"].name),
        make_compare_rows(po_agg, final_internal_sku, "미입고수량", "미입고 수량", "미입고 수량", files["미입고"].name),
    ]
    sku_compare = pd.concat(compare_frames, ignore_index=True)

    # Case-only variant detection without merging.
    source_sets = []
    for name, agg_df in [("재고", stock_agg), ("본사 EU창고 재고", hq_agg), ("판매", sales_agg), ("운송중", shipping_agg), ("미입고", po_agg), ("최종산출", final_internal_sku)]:
        if agg_df.empty or "상품코드" not in agg_df.columns:
            continue
        tmp = agg_df.copy()
        tmp["출처"] = name
        source_sets.append(tmp)
    all_codes = pd.concat(source_sets, ignore_index=True, sort=False)
    all_codes["lower_key"] = all_codes["상품코드"].astype(str).str.lower()
    variant_keys = all_codes.groupby("lower_key")["상품코드"].nunique()
    variant_keys = set(variant_keys[variant_keys > 1].index)
    case_variants = all_codes[all_codes["lower_key"].isin(variant_keys)].copy()
    if not case_variants.empty:
        case_variants = case_variants.sort_values(["lower_key", "상품코드", "출처"])
        case_variants["분류"] = "리뉴얼/코드전환 확인필요"
        case_variants["처리 기준"] = "대소문자 차이 SKU는 자동 병합하지 않음"
        case_variant_codes = set(case_variants["상품코드"])
        sku_compare.loc[sku_compare["상품코드"].isin(case_variant_codes), "일치 여부"] = "리뉴얼/코드전환 확인필요"
        sku_compare.loc[sku_compare["상품코드"].isin(case_variant_codes), "차이 원인 추정"] = "대소문자 차이 / 리뉴얼 코드전환 의심"

    # Matching coverage.
    final_codes = set(final_internal_sku["상품코드"].dropna().astype(str))
    eu_codes = set(stock_agg["상품코드"])
    hq_codes = set(hq_agg["상품코드"])
    sales_codes = set(sales_agg["상품코드"])
    ship_codes = set(shipping_agg["상품코드"])
    po_codes = set(po_agg["상품코드"])
    all_union = sorted(eu_codes | hq_codes | sales_codes | ship_codes | po_codes | final_codes)
    sku_name_map = {}
    for df in [stock_agg, hq_agg, sales_agg, shipping_agg, po_agg, final_internal_sku]:
        if "상품코드" in df.columns and "상품명" in df.columns:
            sku_name_map.update(df.dropna(subset=["상품코드"]).set_index("상품코드")["상품명"].astype(str).to_dict())
    missing_rows = []
    excluded_codes = set(final_excluded.get("상품코드", pd.Series(dtype=str)).map(clean_code)) if "상품코드" in final_excluded.columns else set()
    non_sku_codes = set(non_sku_sales.get("SKU", pd.Series(dtype=str)).map(clean_code))
    for code in all_union:
        reasons = []
        if code in hq_codes and code not in eu_codes:
            reasons.append("본사 EU창고 단독 존재 SKU")
        if code.lower() in variant_keys:
            reasons.append("리뉴얼/코드전환 의심")
        if code in non_sku_codes or not is_product_sku(code) or not is_probable_cos_sku(code):
            reasons.append("비-SKU 여부 확인")
        if code not in final_codes and (code in eu_codes or code in hq_codes or code in sales_codes or code in ship_codes or code in po_codes):
            reasons.append("원본에는 있으나 최종 산출 파일에 없음")
        if code in final_codes and code not in (eu_codes | hq_codes | sales_codes | ship_codes | po_codes):
            reasons.append("최종 산출 파일에는 있으나 원본 매칭 없음")
        missing_rows.append(
            {
                "상품코드": code,
                "상품명": sku_name_map.get(code, ""),
                "재고 원본 존재 여부": "Y" if code in eu_codes else "",
                "본사 EU창고 존재 여부": "Y" if code in hq_codes else "",
                "판매 원본 존재 여부": "Y" if code in sales_codes else "",
                "운송중 원본 존재 여부": "Y" if code in ship_codes else "",
                "미입고 원본 존재 여부": "Y" if code in po_codes else "",
                "최종 산출 파일 존재 여부": "Y" if code in final_codes else "",
                "제외 여부": "Y" if code in excluded_codes else "",
                "제외 사유": "샘플/단종 참고 시트" if code in excluded_codes else "",
                "확인 필요 사유": " / ".join(reasons),
                "리뉴얼/코드전환 의심 여부": "Y" if code.lower() in variant_keys else "",
                "비-SKU 여부": "Y" if code in non_sku_codes or not is_product_sku(code) or not is_probable_cos_sku(code) else "",
            }
        )
    missing_df = pd.DataFrame(missing_rows)
    hq_only = missing_df[missing_df["확인 필요 사유"].str.contains("본사 EU창고 단독", na=False)].copy()

    # Formula verification.
    selected = []
    selected += final_raw.sort_values("PA+CA 판매수량", ascending=False).get("상품코드", pd.Series(dtype=str)).head(5).tolist()
    selected += final_raw.sort_values(["부족금액_KRW", "발주필요수량"], ascending=False).get("상품코드", pd.Series(dtype=str)).head(5).tolist()
    selected += final_stockout[final_stockout.get("입고 전 품절 여부", "").astype(str).eq("Y")].get("상품코드", pd.Series(dtype=str)).head(5).tolist()
    selected += final_raw[final_raw.get("발주검토여부", "").astype(str).eq("불필요")].get("상품코드", pd.Series(dtype=str)).head(5).tolist()
    selected_unique = []
    for code in map(clean_code, selected):
        if code and code not in selected_unique:
            selected_unique.append(code)
    formula_rows = []
    final_index = final_raw.set_index("상품코드", drop=False)
    for code in selected_unique[:20]:
        if code not in final_index.index:
            continue
        row = final_index.loc[code]
        recent = float(row.get("최근 3개월 판매수량", row.get("PA+CA 판매수량", 0)) or 0)
        monthly_calc = recent / 3 if recent else 0
        daily_calc = monthly_calc / 30 if monthly_calc else 0
        eu_avail = float(row.get("EU 현지 가용수량", row.get("유럽 가용재고", 0)) or 0)
        shipping_qty = float(row.get("운송중 수량", 0) or 0)
        transport_included = eu_avail + shipping_qty
        cover_calc = 99 if monthly_calc <= 0 else transport_included / monthly_calc
        safety_calc = monthly_calc * SAFETY_MONTHS
        shortage_calc = max(0, safety_calc - transport_included)
        order_calc = shortage_calc
        stockout_calc = "판매없음" if daily_calc <= 0 else (BASE_DATE + pd.Timedelta(days=eu_avail / daily_calc)).date().isoformat()
        checks = [
            ("월평균 판매량", row.get("월평균 판매수량", 0), monthly_calc),
            ("일평균 판매량", row.get("일평균 판매수량", 0), daily_calc),
            ("운송 포함 수량", row.get("유럽+운송 수량", 0), transport_included),
            ("운송 포함 보유개월", row.get("운송 포함 보유개월수", 0), cover_calc),
            ("안전재고 필요 수량", row.get("안전재고 목표수량", 0), safety_calc),
            ("부족수량", row.get("최종 부족수량", 0), shortage_calc),
            ("발주필요수량", row.get("발주필요수량", 0), order_calc),
        ]
        for item, final_value, calc_value in checks:
            final_num = float(pd.to_numeric(final_value, errors="coerce") or 0)
            diff = final_num - calc_value
            tolerance = 1.0 if "수량" in item or item == "월평균 판매량" else 0.05
            formula_rows.append(
                {
                    "상품코드": code,
                    "상품명": row.get("상품명", ""),
                    "검증항목": item,
                    "최종 산출 파일 값": final_num,
                    "재계산 값": calc_value,
                    "차이": diff,
                    "일치 여부": "통과" if abs(diff) <= tolerance else "실패",
                }
            )
        formula_rows.append(
            {
                "상품코드": code,
                "상품명": row.get("상품명", ""),
                "검증항목": "예상 소진일",
                "최종 산출 파일 값": str(row.get("고갈 예상일", ""))[:10],
                "재계산 값": stockout_calc,
                "차이": "",
                "일치 여부": "참고",
            }
        )
    formula_df = pd.DataFrame(formula_rows)

    # ETA validation.
    eta_cols = [col for col in final_eta.columns if str(col).startswith("ETA ")]
    final_eta_long = []
    for _, row in final_eta.iterrows():
        sku = clean_code(row.get("SKU", row.get("상품코드", "")))
        for col in eta_cols:
            eta_date = date_from_eta_header(str(col))
            qty = pd.to_numeric(row.get(col), errors="coerce")
            if sku and eta_date is not None and pd.notna(qty) and float(qty) != 0:
                final_eta_long.append({"상품코드": sku, "최종 산출 파일 ETA": eta_date, "최종 ETA 수량": float(qty)})
    final_eta_long_df = pd.DataFrame(final_eta_long)
    final_eta_dates_by_sku = final_eta_long_df.groupby("상품코드")["최종 산출 파일 ETA"].apply(list).to_dict() if not final_eta_long_df.empty else {}
    eta_rows = []
    for _, row in shipping_product.iterrows():
        sku = row["SKU"]
        final_dates = final_eta_dates_by_sku.get(sku, [])
        eta_a, eta_b = row["ETA_A"], row["ETA_B"]
        match_a = any(pd.notna(eta_a) and d.date() == eta_a.date() for d in final_dates)
        match_b = any(pd.notna(eta_b) and d.date() == eta_b.date() for d in final_dates)
        if match_b:
            status = "B안 일치"
            reason = "리드타임 + 준비버퍼 적용"
        elif match_a:
            status = "A안 일치"
            reason = "리드타임만 적용"
        elif sku not in final_codes:
            status = "미반영"
            reason = "미등록 SKU 제외 또는 ETA 표시 대상 차이"
        else:
            status = "불일치"
            reason = "동일 SKU 복수 출고건 처리 방식 차이 또는 확인 필요"
        first_final = min(final_dates).date().isoformat() if final_dates else ""
        eta_rows.append(
            {
                "상품코드": sku,
                "상품명": row.get("상품명_정리", ""),
                "운송수단": row["운송수단_정규화"],
                "출고일": row["출고일_DT"].date().isoformat() if pd.notna(row["출고일_DT"]) else "",
                "원본 수량": row["수량_NUM"],
                "A안 재계산 ETA": eta_a.date().isoformat() if pd.notna(eta_a) else "",
                "B안 재계산 ETA": eta_b.date().isoformat() if pd.notna(eta_b) else "",
                "최종 산출 파일 ETA": first_final,
                "A안 차이 일수": (pd.Timestamp(first_final) - eta_a).days if first_final and pd.notna(eta_a) else "",
                "B안 차이 일수": (pd.Timestamp(first_final) - eta_b).days if first_final and pd.notna(eta_b) else "",
                "일치 여부": status,
                "차이 원인 추정": reason,
            }
        )
    eta_df = pd.DataFrame(eta_rows)

    # Difference Top 20 sheets.
    top_frames = []
    for item in ["EU 현지 가용재고", "EU 현지 현재재고", "재고 PA+CA 3개월 판매수량", "판매내역상세 3개월 판매수량", "운송중 수량", "미입고 수량"]:
        sub = sku_compare[sku_compare["비교항목"].eq(item)].copy()
        if not sub.empty:
            sub["차이_abs"] = sub["차이"].abs()
            sub = sub.sort_values("차이_abs", ascending=False).head(20).drop(columns=["차이_abs"])
            sub.insert(0, "TOP구분", item)
            top_frames.append(sub)
    if not eta_df.empty:
        eta_top = eta_df.copy()
        eta_top["ETA차이_abs"] = pd.to_numeric(eta_top["B안 차이 일수"], errors="coerce").abs().fillna(9999)
        eta_top = eta_top.sort_values("ETA차이_abs", ascending=False).head(20).drop(columns=["ETA차이_abs"])
        eta_top.insert(0, "TOP구분", "ETA 차이")
    else:
        eta_top = pd.DataFrame()
    diff_top20 = pd.concat(top_frames, ignore_index=True) if top_frames else pd.DataFrame()

    # Logs.
    logs = []

    def log(level: str, item: str, detail: str, count: object = "") -> None:
        logs.append({"구분": level, "항목": item, "내용": detail, "건수/값": count})

    log("정보", "검증일", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log("정보", "산출 파일명", final_path.name)
    log("정보", "사용 원본 파일명", ", ".join(f"{k}: {v.name}" for k, v in files.items() if k != "산출" and v.exists()))
    log("정보", "기준일", BASE_DATE.date().isoformat())
    log("정보", "안전재고 기준 개월 수", SAFETY_MONTHS)
    log("정보", "리드타임 기준", "A안 항공15/트럭30/철송30/해운80, B안 항공17/트럭33/철송35/해운87")
    log("정보", "준비 버퍼 기준", "항공2/트럭3/철송5/해운7")
    log("정보", "ETA 산정 기준", "A안과 B안을 모두 비교, 현 Streamlit prepare_shipping은 리드타임+준비버퍼를 ETA 날짜에 포함")
    log("정보", "추천 판단 기준", "기존 산출 파일 기준 유지")
    log("정보", "미입고 반영 기준", "미입고 수량은 현재 발주필요수량 산정에는 직접 반영하지 않고 참고값으로만 표시함.")
    log("정보", "자사간거래 파일 반영 여부", "자사간거래 판매내역상세 파일은 현재 발주 산식에는 직접 반영하지 않고, 향후 ETA 연결 검증용 참고 데이터로만 분류함.")
    log("정보", "비-SKU 거래 행 제외 기준", "Delivery Charge 등 비-SKU 거래 행은 발주 산식에서 제외하며, 제외 행 수와 금액은 검증로그에 기록함.")
    log("정보", "대소문자 차이 SKU 처리 기준", "대소문자 차이 SKU는 리뉴얼/코드전환 가능성이 있으므로 자동 병합하지 않고 확인필요 대상으로 분류함.")
    log("정보", "리뉴얼/코드전환 확인필요 SKU 수", case_variants["상품코드"].nunique() if not case_variants.empty else 0)
    log("정보", "본사 EU창고 단독 존재 SKU 수", hq_only["상품코드"].nunique() if not hq_only.empty else 0)
    matching_reason = missing_df["확인 필요 사유"].fillna("").astype(str).str.strip()
    log("정보", "매칭 누락 SKU 수", int(matching_reason.ne("").sum()))
    log("정보", "산식 검증 통과 건수", int(formula_df["일치 여부"].eq("통과").sum()) if not formula_df.empty else 0)
    log("정보", "산식 검증 실패 건수", int(formula_df["일치 여부"].eq("실패").sum()) if not formula_df.empty else 0)
    log("정보", "ETA B안 일치 건수", int(eta_df["일치 여부"].eq("B안 일치").sum()) if not eta_df.empty else 0)
    log("정보", "ETA 실패/미반영 건수", int((~eta_df["일치 여부"].isin(["B안 일치", "A안 일치"])).sum()) if not eta_df.empty else 0)
    log("정보", "기존 로직 변경 여부", "변경 없음")
    log("확인필요", "다음 확인 필요사항", "대소문자 차이 SKU, 본사 EU창고 단독 존재 SKU, 비-SKU 거래 행, ETA 표시 대상 차이 확인")

    log_df = pd.DataFrame(logs)

    non_sku_log = non_sku_sales.copy()
    if not non_sku_log.empty:
        non_sku_log["제외 사유"] = np.where(non_sku_log["SKU"].map(is_product_sku), "cos SKU 패턴 확인필요", "Delivery Charge 등 비-SKU 거래 행")

    output = WORKDIR / f"SCM_정합성검증_{BASE_DATE:%Y%m%d}.xlsx"
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        log_df.to_excel(writer, sheet_name="검증로그", index=False)
        pd.DataFrame(total_rows).to_excel(writer, sheet_name="원본총합검증", index=False)
        sku_compare.to_excel(writer, sheet_name="SKU별검증", index=False)
        missing_df.to_excel(writer, sheet_name="매칭누락SKU", index=False)
        case_variants.to_excel(writer, sheet_name="리뉴얼코드전환확인", index=False)
        hq_only.to_excel(writer, sheet_name="본사EU창고단독SKU", index=False)
        non_sku_log.to_excel(writer, sheet_name="비SKU제외로그", index=False)
        formula_df.to_excel(writer, sheet_name="산식검증", index=False)
        eta_df.to_excel(writer, sheet_name="ETA검증", index=False)
        diff_top20.to_excel(writer, sheet_name="차이TOP20", index=False)
        eta_top.to_excel(writer, sheet_name="ETA차이TOP20", index=False)
        pd.DataFrame(
            [{"역할": key, "파일명": path.name, "경로": str(path), "존재": path.exists()} for key, path in files.items()]
        ).to_excel(writer, sheet_name="사용파일", index=False)

    summary = {
        "output": str(output),
        "stock_rows": len(eu_stock),
        "hq_rows": len(hq_stock),
        "sales_rows": len(sales_main),
        "shipping_rows": len(shipping_raw),
        "open_po_rows": len(open_po),
        "sku_compare_rows": len(sku_compare),
        "sku_compare_match": int(sku_compare["일치 여부"].eq("일치").sum()),
        "sku_compare_mismatch": int(sku_compare["일치 여부"].isin(["불일치", "산출누락", "원본매칭확인필요", "리뉴얼/코드전환 확인필요"]).sum()),
        "case_variant_skus": int(case_variants["상품코드"].nunique()) if not case_variants.empty else 0,
        "hq_only_skus": int(hq_only["상품코드"].nunique()) if not hq_only.empty else 0,
        "non_sku_rows": len(non_sku_log),
        "formula_pass": int(formula_df["일치 여부"].eq("통과").sum()) if not formula_df.empty else 0,
        "formula_fail": int(formula_df["일치 여부"].eq("실패").sum()) if not formula_df.empty else 0,
        "eta_rows": len(eta_df),
        "eta_b_match": int(eta_df["일치 여부"].eq("B안 일치").sum()) if not eta_df.empty else 0,
        "eta_a_match": int(eta_df["일치 여부"].eq("A안 일치").sum()) if not eta_df.empty else 0,
        "eta_unmatched": int((~eta_df["일치 여부"].isin(["B안 일치", "A안 일치"])).sum()) if not eta_df.empty else 0,
    }
    print(pd.Series(summary).to_string())


if __name__ == "__main__":
    main()
