from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


EXPERIMENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXPERIMENT_DIR.parents[1]
OUTPUT_ROOT = EXPERIMENT_DIR / "outputs"


def resolve_output_dir(output_dir: str | Path | None = None) -> Path:
    """Return an output directory under this experiment's outputs folder only."""
    candidate = Path(output_dir) if output_dir else OUTPUT_ROOT
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    resolved = candidate.resolve()
    allowed = OUTPUT_ROOT.resolve()
    if resolved != allowed and allowed not in resolved.parents:
        raise ValueError(f"Output path must be under {allowed}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def timestamped_output_path(
    output_dir: str | Path | None,
    prefix: str,
    suffix: str,
    now: datetime | None = None,
) -> Path:
    output_path = resolve_output_dir(output_dir)
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    return output_path / f"{prefix}_{stamp}{suffix}"


def safe_numeric(value: Any, default: float = 0.0) -> Any:
    if isinstance(value, pd.Series):
        return pd.to_numeric(value, errors="coerce").fillna(default)
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return default if pd.isna(parsed) else float(parsed)


def normalize_sku(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "null"}:
        return ""
    return text.upper()


def normalized_column_name(value: Any) -> str:
    return "".join(ch for ch in str(value).strip().lower() if ch.isalnum())


def find_column(df: pd.DataFrame | None, candidates: list[str] | tuple[str, ...]) -> str | None:
    if df is None or df.empty:
        return None
    columns = [str(column) for column in df.columns]
    for candidate in candidates:
        if candidate in columns:
            return candidate
    normalized = {normalized_column_name(column): column for column in columns}
    for candidate in candidates:
        found = normalized.get(normalized_column_name(candidate))
        if found is not None:
            return found
    return None


def first_non_empty(values: pd.Series) -> str:
    for value in values:
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "null", "-"}:
            return text
    return ""


def frame_from_raw(raw: dict[str, list[dict[str, object]]], key: str) -> pd.DataFrame:
    return pd.DataFrame(raw.get(key) or [])


def raw_endpoint_summary(raw: dict[str, list[dict[str, object]]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    endpoint_paths = {
        "stock_local": "/eu/stock/local",
        "stock_hq": "/eu/stock/hq",
        "sales_local": "/eu/sales/local",
        "sales_hq": "/eu/sales/hq-to-eu",
        "shipping": "/eu/shipping/containers",
        "open_po": "/eu/open-po",
    }
    for key, path in endpoint_paths.items():
        frame = frame_from_raw(raw, key)
        rows.append(
            {
                "cms_key": key,
                "endpoint": path,
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "fields": ", ".join(str(column) for column in frame.columns),
            }
        )
    return pd.DataFrame(rows)


def row_sku(row: dict[str, object]) -> str:
    for field in ("prod_cd", "상품코드", "SKU", "sku", "itemcode", "Item Code"):
        value = row.get(field)
        sku = normalize_sku(value)
        if sku:
            return sku
    return ""


def select_skus_from_raw(
    raw: dict[str, list[dict[str, object]]],
    limit_skus: int | None = None,
    sample_skus: list[str] | None = None,
) -> set[str]:
    selected = {normalize_sku(sku) for sku in (sample_skus or []) if normalize_sku(sku)}
    if limit_skus is None or limit_skus <= 0:
        return selected
    for key in ("stock_local", "sales_local", "shipping", "open_po", "stock_hq", "sales_hq"):
        for row in raw.get(key) or []:
            sku = row_sku(row)
            if sku:
                selected.add(sku)
            if len(selected) >= limit_skus:
                return selected
    return selected


def filter_raw_to_skus(raw: dict[str, list[dict[str, object]]], skus: set[str]) -> dict[str, list[dict[str, object]]]:
    if not skus:
        return raw
    filtered: dict[str, list[dict[str, object]]] = {}
    for key, rows in raw.items():
        filtered[key] = [row for row in (rows or []) if row_sku(row) in skus]
    return filtered


def _sales_work_frame(
    sales_df: pd.DataFrame,
    date_col: str | None = None,
    sku_col: str | None = None,
    qty_col: str | None = None,
    amount_col: str | None = None,
) -> pd.DataFrame:
    if sales_df is None or sales_df.empty:
        return pd.DataFrame()
    df = pd.DataFrame(sales_df).copy()
    sku_col = sku_col or find_column(df, ["상품코드", "SKU", "prod_cd", "sku", "itemcode", "Item Code"])
    date_col = date_col or find_column(df, ["출고일", "ship_dt", "판매일자", "sales_date", "date", "Date"])
    qty_col = qty_col or find_column(df, ["수량", "판매수량", "판매 수량", "qty", "quantity", "sales_qty"])
    amount_col = amount_col or find_column(df, ["환산금액", "판매금액", "금액", "amount_krw", "amount", "sales_amount"])
    if sku_col is None or date_col is None or qty_col is None:
        return pd.DataFrame()
    name_col = find_column(df, ["상품명", "제품명", "품목명", "prod_nm", "productName", "itemname"])
    brand_col = find_column(df, ["브랜드", "브랜드명", "brand_nm", "brand"])
    work = pd.DataFrame(
        {
            "SKU": df[sku_col].map(normalize_sku),
            "sale_date": pd.to_datetime(df[date_col], errors="coerce"),
            "sales_qty": safe_numeric(df[qty_col]),
            "sales_amount": safe_numeric(df[amount_col]) if amount_col else 0.0,
            "상품명": df[name_col].astype(str) if name_col else "",
            "브랜드": df[brand_col].astype(str) if brand_col else "",
        }
    )
    work = work[work["SKU"].ne("") & work["sale_date"].notna()].copy()
    return work


def aggregate_monthly_sales(
    sales_df: pd.DataFrame,
    date_col: str | None = None,
    sku_col: str | None = None,
    qty_col: str | None = None,
    amount_col: str | None = None,
) -> pd.DataFrame:
    work = _sales_work_frame(sales_df, date_col=date_col, sku_col=sku_col, qty_col=qty_col, amount_col=amount_col)
    columns = [
        "SKU",
        "sales_month",
        "month_start",
        "sales_qty",
        "sales_amount",
        "rows",
        "first_sale_date",
        "last_sale_date",
        "상품명",
        "브랜드",
    ]
    if work.empty:
        return pd.DataFrame(columns=columns)
    work["sales_month"] = work["sale_date"].dt.to_period("M").astype(str)
    grouped = (
        work.groupby(["SKU", "sales_month"], as_index=False)
        .agg(
            sales_qty=("sales_qty", "sum"),
            sales_amount=("sales_amount", "sum"),
            rows=("sales_qty", "size"),
            first_sale_date=("sale_date", "min"),
            last_sale_date=("sale_date", "max"),
            상품명=("상품명", first_non_empty),
            브랜드=("브랜드", first_non_empty),
        )
        .sort_values(["SKU", "sales_month"])
    )
    grouped["month_start"] = pd.to_datetime(grouped["sales_month"] + "-01", errors="coerce")
    return grouped[columns]


def aggregate_weekly_sales(
    sales_df: pd.DataFrame,
    date_col: str | None = None,
    sku_col: str | None = None,
    qty_col: str | None = None,
    amount_col: str | None = None,
) -> pd.DataFrame:
    work = _sales_work_frame(sales_df, date_col=date_col, sku_col=sku_col, qty_col=qty_col, amount_col=amount_col)
    columns = [
        "SKU",
        "week_start",
        "iso_year_week",
        "sales_qty",
        "sales_amount",
        "rows",
        "first_sale_date",
        "last_sale_date",
        "상품명",
        "브랜드",
    ]
    if work.empty:
        return pd.DataFrame(columns=columns)
    week_start = work["sale_date"] - pd.to_timedelta(work["sale_date"].dt.weekday, unit="D")
    work["week_start"] = week_start.dt.normalize()
    iso = work["sale_date"].dt.isocalendar()
    work["iso_year_week"] = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
    grouped = (
        work.groupby(["SKU", "week_start", "iso_year_week"], as_index=False)
        .agg(
            sales_qty=("sales_qty", "sum"),
            sales_amount=("sales_amount", "sum"),
            rows=("sales_qty", "size"),
            first_sale_date=("sale_date", "min"),
            last_sale_date=("sale_date", "max"),
            상품명=("상품명", first_non_empty),
            브랜드=("브랜드", first_non_empty),
        )
        .sort_values(["SKU", "week_start"])
    )
    return grouped[columns]


def _non_empty_ratio(df: pd.DataFrame, fields: list[str]) -> float:
    if df.empty:
        return 0.0
    matched = [field for field in fields if field in df.columns]
    if not matched:
        return 0.0
    values = df[matched].astype(str).replace({"nan": "", "None": "", "NaT": ""})
    non_empty = values.apply(lambda col: col.str.strip().ne("")).any(axis=1)
    return float(non_empty.mean()) if len(non_empty) else 0.0


def detect_available_fields(
    raw: dict[str, list[dict[str, object]]],
    uploaded_data: dict[str, pd.DataFrame],
    monthly_sales: pd.DataFrame | None = None,
    weekly_sales: pd.DataFrame | None = None,
) -> pd.DataFrame:
    raw_frames = {key: frame_from_raw(raw, key) for key in raw}
    mapped_frames = {key: pd.DataFrame(value) for key, value in uploaded_data.items()}
    specs = [
        ("판매", "24개월 판매 이력 조회 가능", ["sales_local"], ["ship_dt", "출고일"], "월 span 기준으로 별도 판정"),
        ("판매", "SKU별 월별 판매 집계 가능", ["sales_local", "sales_detail"], ["prod_cd", "상품코드", "ship_dt", "출고일", "qty", "수량"], ""),
        ("판매", "SKU별 주별 또는 일별 판매 집계 가능", ["sales_local", "sales_detail"], ["prod_cd", "상품코드", "ship_dt", "출고일", "qty", "수량"], ""),
        ("판매", "판매일자 필드", ["sales_local", "sales_detail"], ["ship_dt", "출고일", "sales_date", "판매일자"], ""),
        ("판매", "판매수량 필드", ["sales_local", "sales_detail"], ["qty", "수량", "판매수량"], ""),
        ("판매", "판매금액 필드", ["sales_local", "sales_detail"], ["amount", "amount_krw", "금액", "환산금액"], ""),
        ("판매", "Biz Type / Site / 창고 / 거래처 필드", ["sales_local", "sales_detail", "shipping"], ["biz_type", "Biz Type", "site", "Site", "whouse_nm", "cust_nm"], ""),
        ("판매보정", "FOC 제외 가능", ["sales_local", "sales_detail"], ["biz_type", "Biz Type"], "FREE SAMPLE 등 biz_type 값 확인 필요"),
        ("판매보정", "반품 식별 가능", ["sales_local", "sales_detail"], ["return_flag", "return_yn", "반품", "qty", "수량"], "음수 수량은 보조 신호일 뿐 전용 반품 필드가 더 안전"),
        ("판매보정", "sellable_days 계산 필드", ["sales_local", "stock_local", "eu_stock"], ["sellable_days", "daily_stock_qty", "stock_positive_days", "재고>0"], ""),
        ("판매보정", "promo_flag 또는 bulk deal 식별 필드", ["sales_local", "sales_detail"], ["promo_flag", "bulk_deal", "promotion", "deal_type", "promo"], ""),
        ("재고", "SKO 현재 재고/Hold/가용재고", ["stock_local", "eu_stock"], ["stock_qty", "hold_qty", "avbl_qty", "재고수량", "Hold수량", "EU 현지 가용수량"], ""),
        ("재고", "본사/EU창고 재고/Hold/가용재고", ["stock_hq", "hq_eu_stock"], ["stock_qty", "hold_qty", "avbl_qty", "재고수량", "Hold수량", "본사 EU창고 가용수량"], ""),
        ("운송", "운송중 수량", ["shipping"], ["qty", "수량"], ""),
        ("운송", "운송수단 mode", ["shipping"], ["mode", "운송수단", "remark", "Invoice 비고"], "remark에서 해운/항공/철송 파싱 가능"),
        ("운송", "출고일 ship_date", ["shipping"], ["ship_dt", "출고일"], ""),
        ("운송", "ETA", ["shipping"], ["eta_dt", "ETA", "expected_arrival_date"], "없으면 출고일+리드타임 추정만 가능"),
        ("운송", "실제 도착일 arrival_date", ["shipping"], ["arrival_date", "arrival_dt", "actual_arrival_date"], ""),
        ("PO", "미입고 PO 수량", ["open_po"], ["open_qty", "미입고 수량", "PO 수량", "po_qty"], ""),
        ("PO", "PO 등록일/order_date", ["open_po"], ["order_date", "po_dt", "po_date", "등록일"], ""),
        ("PO", "브랜드 납품 예정일 expected_in_date", ["open_po"], ["expected_in_date", "납품예정일"], ""),
        ("PO", "실제 EU창고 입고일 warehouse_in_date", ["open_po"], ["warehouse_in_date", "입고일"], ""),
        ("상품", "MOQ", ["stock_local", "stock_hq", "eu_stock", "hq_eu_stock"], ["moq", "MOQ"], ""),
        ("상품", "유통기한/FR Date", ["stock_local", "stock_hq", "eu_stock", "hq_eu_stock"], ["fr_date", "FR Date", "expiration_date", "유통기한"], ""),
        ("상품", "SKU alias mapping", ["stock_local", "sales_local", "eu_stock", "sales_detail"], ["alias", "old_sku", "new_sku", "sku_alias", "대체코드"], ""),
    ]
    rows: list[dict[str, object]] = []
    for category, item, sources, candidates, note in specs:
        matched_sources: list[str] = []
        matched_fields: list[str] = []
        ratios: list[float] = []
        row_count = 0
        for source in sources:
            frame = raw_frames.get(source)
            if frame is None:
                frame = mapped_frames.get(source, pd.DataFrame())
            row_count += len(frame)
            fields = [field for field in candidates if field in frame.columns]
            if fields:
                matched_sources.append(source)
                matched_fields.extend(fields)
                ratios.append(_non_empty_ratio(frame, fields))
        availability = "Y" if matched_fields and max(ratios or [0]) > 0 else "N"
        if item == "24개월 판매 이력 조회 가능" and monthly_sales is not None and not monthly_sales.empty:
            months = pd.PeriodIndex(monthly_sales["sales_month"].astype(str), freq="M")
            span = int(months.max().ordinal - months.min().ordinal + 1)
            availability = "Y" if span >= 24 else "Partial" if span >= 12 else "N"
            note = f"관측 월 span={span}개월"
        if item == "SKU별 월별 판매 집계 가능" and monthly_sales is not None:
            availability = "Y" if not monthly_sales.empty else "N"
        if item == "SKU별 주별 또는 일별 판매 집계 가능" and weekly_sales is not None:
            availability = "Y" if not weekly_sales.empty else "N"
        rows.append(
            {
                "category": category,
                "item": item,
                "availability": availability,
                "matched_sources": ", ".join(dict.fromkeys(matched_sources)),
                "matched_fields": ", ".join(dict.fromkeys(matched_fields)),
                "non_empty_ratio": round(max(ratios or [0.0]), 4),
                "row_count": int(row_count),
                "notes": note,
            }
        )
    return pd.DataFrame(rows)


def calculate_data_quality_flags(monthly_sales: pd.DataFrame, as_of: str | date | datetime) -> pd.DataFrame:
    columns = [
        "SKU",
        "총 판매월 수",
        "유효 판매월 수",
        "최근 6개월 판매 존재",
        "최근 12개월 판매 존재",
        "최근 24개월 판매 존재",
        "월별 판매 모두 0",
        "판매이력 구간",
        "월별 판매 급변",
        "월평균",
        "월별 CV",
        "총 판매수량",
    ]
    if monthly_sales is None or monthly_sales.empty:
        return pd.DataFrame(columns=columns)
    as_of_period = pd.Period(pd.to_datetime(as_of).date(), freq="M")
    rows: list[dict[str, object]] = []
    for sku, group in monthly_sales.groupby("SKU"):
        periods = pd.PeriodIndex(group["sales_month"].astype(str), freq="M")
        qty = pd.to_numeric(group["sales_qty"], errors="coerce").fillna(0)
        active_months = int(qty.ne(0).sum())
        total_months = int(len(group))
        recent_6 = qty[periods >= as_of_period - 5].sum()
        recent_12 = qty[periods >= as_of_period - 11].sum()
        recent_24 = qty[periods >= as_of_period - 23].sum()
        positive_qty = qty[qty > 0]
        if active_months < 6:
            bucket = "6개월 미만"
        elif active_months < 12:
            bucket = "6~11개월"
        else:
            bucket = "12개월 이상"
        sorted_qty = qty.iloc[np.argsort(periods.asi8)]
        prev = sorted_qty.shift(1).replace(0, np.nan)
        jump_ratio = (sorted_qty / prev).replace([np.inf, -np.inf], np.nan)
        volatile = bool(((jump_ratio >= 3.0) & (sorted_qty - sorted_qty.shift(1).fillna(0) >= 10)).any())
        mean = float(qty.mean()) if len(qty) else 0.0
        std = float(qty.std(ddof=0)) if len(qty) else 0.0
        rows.append(
            {
                "SKU": sku,
                "총 판매월 수": total_months,
                "유효 판매월 수": active_months,
                "최근 6개월 판매 존재": "Y" if recent_6 != 0 else "N",
                "최근 12개월 판매 존재": "Y" if recent_12 != 0 else "N",
                "최근 24개월 판매 존재": "Y" if recent_24 != 0 else "N",
                "월별 판매 모두 0": "Y" if float(qty.sum()) == 0.0 else "N",
                "판매이력 구간": bucket,
                "월별 판매 급변": "Y" if volatile else "N",
                "월평균": mean,
                "월별 CV": std / mean if mean else np.nan,
                "총 판매수량": float(qty.sum()),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def simple_holt_forecast(values: pd.Series | list[float], horizon: int = 1, alpha: float = 0.5, beta: float = 0.3) -> dict[str, object]:
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna().astype(float)
    if series.empty:
        return {"forecast": 0.0, "method": "holt_unavailable", "warning": "no numeric history"}
    if len(series) < 3:
        return {"forecast": max(float(series.mean()), 0.0), "method": "mean_fallback", "warning": "less than 3 periods"}
    level = float(series.iloc[0])
    trend = float(series.iloc[1] - series.iloc[0])
    for value in series.iloc[1:]:
        previous_level = level
        level = alpha * float(value) + (1 - alpha) * (level + trend)
        trend = beta * (level - previous_level) + (1 - beta) * trend
    forecast = level + horizon * trend
    return {"forecast": max(float(forecast), 0.0), "method": "simple_holt", "warning": ""}


def write_excel_report(sheets: dict[str, pd.DataFrame | list[dict[str, object]] | dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for raw_name, payload in sheets.items():
            sheet_name = str(raw_name)[:31]
            if isinstance(payload, pd.DataFrame):
                frame = payload.copy()
            elif isinstance(payload, list):
                frame = pd.DataFrame(payload)
            elif isinstance(payload, dict):
                frame = pd.DataFrame([payload])
            else:
                frame = pd.DataFrame({"value": [payload]})
            if frame.empty:
                frame = pd.DataFrame({"message": ["no rows"]})
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
            worksheet = writer.sheets[sheet_name]
            for column_cells in worksheet.columns:
                header = str(column_cells[0].value or "")
                max_len = min(max([len(str(cell.value or "")) for cell in column_cells] + [len(header)]) + 2, 60)
                worksheet.column_dimensions[column_cells[0].column_letter].width = max_len
            worksheet.freeze_panes = "A2"


def to_jsonable(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return [to_jsonable(row) for row in value.to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return [to_jsonable(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if np.isnan(value) else float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value
