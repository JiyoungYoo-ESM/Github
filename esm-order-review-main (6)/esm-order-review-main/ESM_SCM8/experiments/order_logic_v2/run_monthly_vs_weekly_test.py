from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.cms_client import fetch_cms_data
from backend.cms_mapping import build_uploaded_data_from_cms
from core.transport import prepare_shipping

try:
    from .utils import (
        aggregate_monthly_sales,
        aggregate_weekly_sales,
        detect_available_fields,
        filter_raw_to_skus,
        find_column,
        first_non_empty,
        normalize_sku,
        resolve_output_dir,
        safe_numeric,
        select_skus_from_raw,
        simple_holt_forecast,
        timestamped_output_path,
        write_excel_report,
    )
except ImportError:
    from utils import (
        aggregate_monthly_sales,
        aggregate_weekly_sales,
        detect_available_fields,
        filter_raw_to_skus,
        find_column,
        first_non_empty,
        normalize_sku,
        resolve_output_dir,
        safe_numeric,
        select_skus_from_raw,
        simple_holt_forecast,
        timestamped_output_path,
        write_excel_report,
    )


DEFAULT_OUTPUT_DIR = "experiments/order_logic_v2/outputs"
TARGET_MONTHS = 3.0
WEEKLY_HORIZON_WEEKS = 8
WEEKS_PER_MONTH = 4.33


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare existing 3-month average, monthly forecast, and current weekly inventory projection.",
    )
    parser.add_argument("--as-of", required=True, help="Inventory snapshot date, YYYY-MM-DD")
    parser.add_argument("--date-from", required=True, help="Sales/logistics query start date, YYYY-MM-DD")
    parser.add_argument("--date-to", required=True, help="Sales/logistics query end date, YYYY-MM-DD")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"Output directory under {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("--limit-skus", type=int, default=None, help="Optional number of SKUs to keep after CMS fetch")
    parser.add_argument("--sample-sku", action="append", default=[], help="Optional SKU to include. Repeatable.")
    return parser.parse_args()


def validate_yyyy_mm_dd(value: str, name: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit(f"{name} must be YYYY-MM-DD: {value}") from exc


def fetch_read_only_cms(args: argparse.Namespace) -> dict[str, list[dict[str, object]]]:
    return fetch_cms_data(
        args.as_of,
        date_from=args.date_from,
        date_to=args.date_to,
        shipping_date_from=args.date_from,
        open_po_date_from=args.date_from,
        include_sales_detail=True,
    )


def build_stock_table(uploaded_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = pd.DataFrame(uploaded_data.get("eu_stock", pd.DataFrame()))
    columns = [
        "SKU",
        "상품명",
        "브랜드",
        "현재 SKO 재고",
        "현재 SKO Hold",
        "현재 SKO 가용재고",
        "stock_sales_qty_3m",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)
    sku_col = find_column(df, ["상품코드", "SKU", "prod_cd"])
    if sku_col is None:
        return pd.DataFrame(columns=columns)
    name_col = find_column(df, ["상품명", "prod_nm", "제품명"])
    brand_col = find_column(df, ["브랜드", "brand_nm", "brand"])
    stock_col = find_column(df, ["재고수량", "stock_qty"])
    hold_col = find_column(df, ["Hold수량", "hold_qty"])
    available_col = find_column(df, ["EU 현지 가용수량", "가용수량", "avbl_qty"])
    sales_3m_col = find_column(df, ["최근 3개월 판매수량", "sales_qty_3m"])
    work = pd.DataFrame(
        {
            "SKU": df[sku_col].map(normalize_sku),
            "상품명": df[name_col].astype(str) if name_col else "",
            "브랜드": df[brand_col].astype(str) if brand_col else "",
            "현재 SKO 재고": safe_numeric(df[stock_col]) if stock_col else 0.0,
            "현재 SKO Hold": safe_numeric(df[hold_col]) if hold_col else 0.0,
            "현재 SKO 가용재고": safe_numeric(df[available_col]) if available_col else 0.0,
            "stock_sales_qty_3m": safe_numeric(df[sales_3m_col]) if sales_3m_col else 0.0,
        }
    )
    work = work[work["SKU"].ne("")]
    if work.empty:
        return pd.DataFrame(columns=columns)
    grouped = work.groupby("SKU", as_index=False).agg(
        상품명=("상품명", first_non_empty),
        브랜드=("브랜드", first_non_empty),
        **{
            "현재 SKO 재고": ("현재 SKO 재고", "sum"),
            "현재 SKO Hold": ("현재 SKO Hold", "sum"),
            "현재 SKO 가용재고": ("현재 SKO 가용재고", "sum"),
            "stock_sales_qty_3m": ("stock_sales_qty_3m", "sum"),
        },
    )
    return grouped[columns]


def build_shipping_tables(uploaded_data: dict[str, pd.DataFrame], as_of: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw_shipping = pd.DataFrame(uploaded_data.get("shipping", pd.DataFrame()))
    detail_columns = ["SKU", "ETA", "eta_week_start", "수량", "운송수단", "출고일", "ETA 구분"]
    summary_columns = ["SKU", "운송중 재고", "유효 ETA 운송중 재고", "첫 ETA 주차", "8주 내 입고합", "ETA 미확인 수량"]
    if raw_shipping.empty:
        return pd.DataFrame(columns=summary_columns), pd.DataFrame(columns=detail_columns)
    prepared = prepare_shipping(raw_shipping, settings=None)
    if "SKU" not in prepared.columns:
        return pd.DataFrame(columns=summary_columns), pd.DataFrame(columns=detail_columns)
    as_of_ts = pd.to_datetime(as_of)
    horizon_end = as_of_ts + pd.Timedelta(weeks=WEEKLY_HORIZON_WEEKS)
    detail = pd.DataFrame(
        {
            "SKU": prepared["SKU"].map(normalize_sku),
            "ETA": pd.to_datetime(prepared.get("ETA", ""), errors="coerce"),
            "수량": safe_numeric(prepared.get("수량", 0)),
            "운송수단": prepared.get("운송수단", ""),
            "출고일": prepared.get("출고일", ""),
            "ETA 구분": prepared.get("ETA 구분", ""),
        }
    )
    detail = detail[detail["SKU"].ne("")].copy()
    if detail.empty:
        return pd.DataFrame(columns=summary_columns), pd.DataFrame(columns=detail_columns)
    detail["eta_week_start"] = (detail["ETA"] - pd.to_timedelta(detail["ETA"].dt.weekday, unit="D")).dt.normalize()
    valid_eta = detail["ETA"].notna() & detail["ETA"].ge(as_of_ts)
    in_8w = valid_eta & detail["ETA"].lt(horizon_end)
    grouped_all = detail.groupby("SKU")["수량"].sum()
    grouped_valid = detail.loc[valid_eta].groupby("SKU")["수량"].sum()
    grouped_8w = detail.loc[in_8w].groupby("SKU")["수량"].sum()
    eta_missing = detail.loc[detail["ETA"].isna()].groupby("SKU")["수량"].sum()
    first_eta = detail.loc[valid_eta].sort_values("ETA").groupby("SKU")["eta_week_start"].first()
    summary = pd.DataFrame({"SKU": sorted(set(grouped_all.index.astype(str)))})
    summary["운송중 재고"] = summary["SKU"].map(grouped_all).fillna(0.0)
    summary["유효 ETA 운송중 재고"] = summary["SKU"].map(grouped_valid).fillna(0.0)
    first_eta_values = pd.to_datetime(summary["SKU"].map(first_eta.to_dict()), errors="coerce")
    summary["첫 ETA 주차"] = first_eta_values.dt.strftime("%Y-%m-%d").fillna("")
    summary["8주 내 입고합"] = summary["SKU"].map(grouped_8w).fillna(0.0)
    summary["ETA 미확인 수량"] = summary["SKU"].map(eta_missing).fillna(0.0)
    detail["ETA"] = detail["ETA"].dt.strftime("%Y-%m-%d").fillna("")
    detail["eta_week_start"] = detail["eta_week_start"].dt.strftime("%Y-%m-%d").fillna("")
    return summary[summary_columns], detail[detail_columns]


def monthly_forecast_table(monthly_sales: pd.DataFrame, as_of: str) -> pd.DataFrame:
    columns = [
        "SKU",
        "history_months",
        "active_months",
        "recent_3_month_avg",
        "recent_12_month_avg",
        "recent_24_month_avg",
        "holt_forecast",
        "월별 예측값",
        "forecast_method",
        "forecast_warning",
    ]
    if monthly_sales.empty:
        return pd.DataFrame(columns=columns)
    as_of_period = pd.Period(pd.to_datetime(as_of).date(), freq="M")
    rows: list[dict[str, object]] = []
    for sku, group in monthly_sales.groupby("SKU"):
        group = group.copy()
        group["period"] = pd.PeriodIndex(group["sales_month"].astype(str), freq="M")
        group = group[group["period"] <= as_of_period].sort_values("period")
        if group.empty:
            continue
        full_periods = pd.period_range(max(group["period"].min(), as_of_period - 23), as_of_period, freq="M")
        series = group.set_index("period")["sales_qty"].reindex(full_periods, fill_value=0.0).astype(float)
        recent_3 = float(series.tail(3).mean()) if len(series) else 0.0
        recent_12 = float(series.tail(12).mean()) if len(series) else 0.0
        recent_24 = float(series.tail(24).mean()) if len(series) else 0.0
        holt = simple_holt_forecast(series.tail(24))
        history_months = int(len(series))
        active_months = int(series.ne(0).sum())
        if active_months >= 6:
            forecast = float(holt["forecast"])
            method = str(holt["method"])
            warning = str(holt["warning"])
        elif active_months >= 3:
            forecast = recent_3
            method = "recent_3_month_avg"
            warning = "less than 6 active months"
        else:
            forecast = recent_12 if active_months else 0.0
            method = "limited_history_avg"
            warning = "less than 3 active months"
        rows.append(
            {
                "SKU": sku,
                "history_months": history_months,
                "active_months": active_months,
                "recent_3_month_avg": recent_3,
                "recent_12_month_avg": recent_12,
                "recent_24_month_avg": recent_24,
                "holt_forecast": float(holt["forecast"]),
                "월별 예측값": max(float(forecast), 0.0),
                "forecast_method": method,
                "forecast_warning": warning,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def recent_weekly_average_table(weekly_sales: pd.DataFrame, as_of: str, weeks: int = 12) -> pd.DataFrame:
    columns = ["SKU", "true_weekly_avg_12w", "weekly_history_weeks", "true_weekly_possible"]
    if weekly_sales.empty:
        return pd.DataFrame(columns=columns)
    as_of_week = pd.to_datetime(as_of)
    as_of_week = as_of_week - pd.to_timedelta(as_of_week.weekday(), unit="D")
    since = as_of_week - pd.Timedelta(weeks=weeks - 1)
    rows: list[dict[str, object]] = []
    for sku, group in weekly_sales.groupby("SKU"):
        recent = group[pd.to_datetime(group["week_start"]) >= since]
        rows.append(
            {
                "SKU": sku,
                "true_weekly_avg_12w": float(pd.to_numeric(recent["sales_qty"], errors="coerce").fillna(0).mean()) if not recent.empty else 0.0,
                "weekly_history_weeks": int(group["week_start"].nunique()),
                "true_weekly_possible": "Y" if int(group["week_start"].nunique()) >= 8 else "N",
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_weekly_projection(
    comparison: pd.DataFrame,
    shipping_detail: pd.DataFrame,
    as_of: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    projection_columns = [
        "SKU",
        "week_no",
        "week_start",
        "opening_stock",
        "eta_arrival_qty",
        "weekly_demand",
        "ending_stock",
        "target_4w_cover_qty",
        "below_zero",
        "below_target",
    ]
    risk_columns = ["SKU", "소진주차", "목표 미달 주차", "8주 최소 예상재고", "stockout_risk"]
    as_of_ts = pd.to_datetime(as_of)
    first_week = as_of_ts - pd.to_timedelta(as_of_ts.weekday(), unit="D")
    shipping = shipping_detail.copy()
    if not shipping.empty:
        shipping["eta_week_start"] = pd.to_datetime(shipping["eta_week_start"], errors="coerce")
        shipping["수량"] = safe_numeric(shipping["수량"])
    rows: list[dict[str, object]] = []
    risk_rows: list[dict[str, object]] = []
    for _, item in comparison.iterrows():
        sku = item["SKU"]
        weekly_demand = float(item.get("주평균 환산값") or 0.0)
        stock = float(item.get("현재 SKO 가용재고") or 0.0)
        min_ending = stock
        depletion_week = ""
        target_miss_week = ""
        for idx in range(WEEKLY_HORIZON_WEEKS):
            week_start = first_week + pd.Timedelta(weeks=idx)
            arrivals = 0.0
            if not shipping.empty:
                mask = shipping["SKU"].eq(sku) & shipping["eta_week_start"].eq(week_start.normalize())
                arrivals = float(shipping.loc[mask, "수량"].sum())
            opening = stock
            ending = opening + arrivals - weekly_demand
            target_qty = weekly_demand * 4
            if not depletion_week and ending < 0:
                depletion_week = week_start.strftime("%Y-%m-%d")
            if not target_miss_week and weekly_demand > 0 and ending < target_qty:
                target_miss_week = week_start.strftime("%Y-%m-%d")
            min_ending = min(min_ending, ending)
            rows.append(
                {
                    "SKU": sku,
                    "week_no": idx + 1,
                    "week_start": week_start.strftime("%Y-%m-%d"),
                    "opening_stock": opening,
                    "eta_arrival_qty": arrivals,
                    "weekly_demand": weekly_demand,
                    "ending_stock": ending,
                    "target_4w_cover_qty": target_qty,
                    "below_zero": "Y" if ending < 0 else "N",
                    "below_target": "Y" if weekly_demand > 0 and ending < target_qty else "N",
                }
            )
            stock = ending
        risk_rows.append(
            {
                "SKU": sku,
                "소진주차": depletion_week,
                "목표 미달 주차": target_miss_week,
                "8주 최소 예상재고": min_ending,
                "stockout_risk": "Y" if depletion_week else "N",
            }
        )
    return pd.DataFrame(rows, columns=projection_columns), pd.DataFrame(risk_rows, columns=risk_columns)


def build_comparison(
    stock: pd.DataFrame,
    monthly_forecast: pd.DataFrame,
    weekly_avg: pd.DataFrame,
    shipping_summary: pd.DataFrame,
    monthly_sales: pd.DataFrame,
) -> pd.DataFrame:
    sku_source = set(stock["SKU"].astype(str)) | set(monthly_forecast["SKU"].astype(str)) | set(shipping_summary["SKU"].astype(str))
    comparison = pd.DataFrame({"SKU": sorted(sku for sku in sku_source if sku)})
    comparison = comparison.merge(stock, on="SKU", how="left")
    comparison = comparison.merge(monthly_forecast, on="SKU", how="left")
    comparison = comparison.merge(weekly_avg, on="SKU", how="left")
    comparison = comparison.merge(shipping_summary, on="SKU", how="left")
    monthly_identity = (
        monthly_sales.groupby("SKU", as_index=False)
        .agg(상품명_sales=("상품명", first_non_empty), 브랜드_sales=("브랜드", first_non_empty))
        if not monthly_sales.empty
        else pd.DataFrame(columns=["SKU", "상품명_sales", "브랜드_sales"])
    )
    comparison = comparison.merge(monthly_identity, on="SKU", how="left")
    comparison["상품명"] = comparison["상품명"].fillna("").astype(str)
    comparison["브랜드"] = comparison["브랜드"].fillna("").astype(str)
    comparison["상품명"] = comparison["상품명"].where(comparison["상품명"].str.strip().ne(""), comparison.get("상품명_sales", ""))
    comparison["브랜드"] = comparison["브랜드"].where(comparison["브랜드"].str.strip().ne(""), comparison.get("브랜드_sales", ""))
    for col in [
        "현재 SKO 가용재고",
        "stock_sales_qty_3m",
        "recent_3_month_avg",
        "월별 예측값",
        "운송중 재고",
        "유효 ETA 운송중 재고",
        "8주 내 입고합",
        "ETA 미확인 수량",
        "true_weekly_avg_12w",
    ]:
        if col not in comparison.columns:
            comparison[col] = 0.0
        comparison[col] = safe_numeric(comparison[col])
    comparison["기존 3개월 월평균"] = comparison["recent_3_month_avg"]
    fallback_mask = comparison["기존 3개월 월평균"].le(0) & comparison["stock_sales_qty_3m"].gt(0)
    comparison.loc[fallback_mask, "기존 3개월 월평균"] = comparison.loc[fallback_mask, "stock_sales_qty_3m"] / 3.0
    comparison["주평균 환산값"] = comparison["기존 3개월 월평균"] / WEEKS_PER_MONTH
    comparison["기존 방식 추천 발주량"] = np.ceil(
        (comparison["기존 3개월 월평균"] * TARGET_MONTHS - comparison["현재 SKO 가용재고"] - comparison["유효 ETA 운송중 재고"]).clip(lower=0)
    )
    comparison["월별 방식 추천 발주량"] = np.ceil(
        (comparison["월별 예측값"] * TARGET_MONTHS - comparison["현재 SKO 가용재고"] - comparison["유효 ETA 운송중 재고"]).clip(lower=0)
    )
    comparison["주차 재고전망 기준 추천 발주량"] = np.ceil(
        (comparison["주평균 환산값"] * WEEKLY_HORIZON_WEEKS - comparison["현재 SKO 가용재고"] - comparison["8주 내 입고합"]).clip(lower=0)
    )
    comparison["차이: 월별 - 기존"] = comparison["월별 방식 추천 발주량"] - comparison["기존 방식 추천 발주량"]
    comparison["차이: 주차 - 기존"] = comparison["주차 재고전망 기준 추천 발주량"] - comparison["기존 방식 추천 발주량"]
    comparison["차이: 주차 - 월별"] = comparison["주차 재고전망 기준 추천 발주량"] - comparison["월별 방식 추천 발주량"]
    flags: list[str] = []
    for _, row in comparison.iterrows():
        row_flags: list[str] = []
        if float(row.get("active_months") or 0) < 6:
            row_flags.append("판매이력 부족")
        if float(row.get("ETA 미확인 수량") or 0) > 0:
            row_flags.append("ETA 미확인")
        if abs(float(row.get("차이: 월별 - 기존") or 0)) >= max(float(row.get("기존 방식 추천 발주량") or 0) * 0.3, 100):
            row_flags.append("월별 차이 큼")
        if abs(float(row.get("차이: 주차 - 기존") or 0)) >= max(float(row.get("기존 방식 추천 발주량") or 0) * 0.3, 100):
            row_flags.append("주차 차이 큼")
        flags.append(", ".join(row_flags) if row_flags else "정상")
    comparison["상태 플래그"] = flags
    return comparison


def data_limitations(field_availability: pd.DataFrame, weekly_avg: pd.DataFrame) -> pd.DataFrame:
    by_item = field_availability.set_index("item")["availability"].to_dict()
    rows = [
        {
            "limit": "완성 산식 아님",
            "impact": "이 스크립트는 PoC 비교용이며 운영 발주 로직을 대체하지 않음",
            "status": "의도된 제한",
        },
        {
            "limit": "과거 as_of 재고",
            "impact": "과거 재고 스냅샷이 없으면 완전한 백테스트 불가",
            "status": "CMS 현재 조회 구조만 확인",
        },
        {
            "limit": "sellable_days",
            "impact": "품절로 눌린 판매량 보정 불가",
            "status": by_item.get("sellable_days 계산 필드", "N"),
        },
        {
            "limit": "promo/bulk flag",
            "impact": "프로모션/대량거래 월의 일반 수요 왜곡 가능",
            "status": by_item.get("promo_flag 또는 bulk deal 식별 필드", "N"),
        },
        {
            "limit": "SKU alias",
            "impact": "코드 변경으로 판매 이력이 끊긴 SKU를 연결하기 어려움",
            "status": by_item.get("SKU alias mapping", "N"),
        },
        {
            "limit": "actual arrival_date",
            "impact": "실제 리드타임 보정 및 운송 ETA 백테스트 불가",
            "status": by_item.get("실제 도착일 arrival_date", "N"),
        },
        {
            "limit": "진짜 주차 수요예측",
            "impact": "주차 평균은 가능하지만 재고>0 일별 로그가 없으면 품절 보정된 주차 수요는 제한됨",
            "status": "가능" if not weekly_avg.empty and weekly_avg["true_weekly_possible"].eq("Y").any() else "부분 가능/불가",
        },
    ]
    return pd.DataFrame(rows)


def summary_sheet(comparison: pd.DataFrame, weekly_projection: pd.DataFrame, limitations: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    stockout_skus = int(weekly_projection.groupby("SKU")["below_zero"].apply(lambda s: s.eq("Y").any()).sum()) if not weekly_projection.empty else 0
    rows = [
        {"metric": "as_of", "value": args.as_of},
        {"metric": "date_from", "value": args.date_from},
        {"metric": "date_to", "value": args.date_to},
        {"metric": "SKU count", "value": int(len(comparison))},
        {"metric": "8주 내 소진 위험 SKU", "value": stockout_skus},
        {"metric": "기존 방식 추천 발주량 합계", "value": float(comparison["기존 방식 추천 발주량"].sum()) if not comparison.empty else 0.0},
        {"metric": "월별 방식 추천 발주량 합계", "value": float(comparison["월별 방식 추천 발주량"].sum()) if not comparison.empty else 0.0},
        {"metric": "주차 재고전망 추천 발주량 합계", "value": float(comparison["주차 재고전망 기준 추천 발주량"].sum()) if not comparison.empty else 0.0},
        {"metric": "운영 반영 여부", "value": "반영 안 함"},
        {"metric": "출력 위치", "value": DEFAULT_OUTPUT_DIR},
        {"metric": "핵심 한계", "value": "; ".join(limitations["limit"].astype(str).head(5)) if not limitations.empty else ""},
    ]
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    validate_yyyy_mm_dd(args.as_of, "--as-of")
    validate_yyyy_mm_dd(args.date_from, "--date-from")
    validate_yyyy_mm_dd(args.date_to, "--date-to")
    output_dir = resolve_output_dir(args.output_dir)
    sample_skus = [normalize_sku(sku) for sku in args.sample_sku if normalize_sku(sku)]

    raw_full = fetch_read_only_cms(args)
    selected_skus = select_skus_from_raw(raw_full, args.limit_skus, sample_skus)
    raw = filter_raw_to_skus(raw_full, selected_skus) if selected_skus else raw_full
    uploaded_data = build_uploaded_data_from_cms(raw)

    sales_detail = pd.DataFrame(uploaded_data.get("sales_detail", pd.DataFrame()))
    monthly_sales = aggregate_monthly_sales(sales_detail)
    weekly_sales = aggregate_weekly_sales(sales_detail)
    stock = build_stock_table(uploaded_data)
    shipping_summary, shipping_detail = build_shipping_tables(uploaded_data, args.as_of)
    monthly_forecast = monthly_forecast_table(monthly_sales, args.as_of)
    weekly_avg = recent_weekly_average_table(weekly_sales, args.as_of)
    comparison = build_comparison(stock, monthly_forecast, weekly_avg, shipping_summary, monthly_sales)
    weekly_projection, risk = build_weekly_projection(comparison, shipping_detail, args.as_of)
    comparison = comparison.merge(risk, on="SKU", how="left")
    comparison["소진주차"] = comparison["소진주차"].fillna("")
    comparison["목표 미달 주차"] = comparison["목표 미달 주차"].fillna("")
    comparison["상태 플래그"] = np.where(
        comparison["소진주차"].astype(str).str.strip().ne(""),
        comparison["상태 플래그"].astype(str) + ", 주차 소진 위험",
        comparison["상태 플래그"],
    )

    field_availability = detect_available_fields(raw, uploaded_data, monthly_sales, weekly_sales)
    limitations = data_limitations(field_availability, weekly_avg)
    method_differences = comparison.copy()
    method_differences["max_abs_difference"] = method_differences[
        ["차이: 월별 - 기존", "차이: 주차 - 기존", "차이: 주차 - 월별"]
    ].abs().max(axis=1)
    method_differences = method_differences.sort_values("max_abs_difference", ascending=False)
    stockout_risk = comparison[
        comparison["소진주차"].astype(str).str.strip().ne("") | comparison["목표 미달 주차"].astype(str).str.strip().ne("")
    ].copy()

    sku_columns = [
        "SKU",
        "상품명",
        "브랜드",
        "기존 3개월 월평균",
        "월별 예측값",
        "주평균 환산값",
        "현재 SKO 가용재고",
        "운송중 재고",
        "첫 ETA 주차",
        "8주 내 입고합",
        "기존 방식 추천 발주량",
        "월별 방식 추천 발주량",
        "주차 재고전망 기준 추천 발주량",
        "소진주차",
        "목표 미달 주차",
        "차이: 월별 - 기존",
        "차이: 주차 - 기존",
        "차이: 주차 - 월별",
        "상태 플래그",
    ]
    for col in sku_columns:
        if col not in comparison.columns:
            comparison[col] = ""
    sheets = {
        "summary": summary_sheet(comparison, weekly_projection, limitations, args),
        "sku_comparison": comparison[sku_columns],
        "monthly_forecast": monthly_forecast,
        "weekly_projection": weekly_projection,
        "stockout_risk": stockout_risk[sku_columns] if not stockout_risk.empty else stockout_risk,
        "method_differences": method_differences[sku_columns + ["max_abs_difference"]],
        "data_limitations": limitations,
    }
    path = timestamped_output_path(output_dir, "monthly_vs_weekly", ".xlsx", now=datetime.now())
    write_excel_report(sheets, path)
    print(f"Excel report: {path}")


if __name__ == "__main__":
    main()
