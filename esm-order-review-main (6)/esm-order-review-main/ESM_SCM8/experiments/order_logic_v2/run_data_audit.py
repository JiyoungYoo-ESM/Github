from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.cms_client import fetch_cms_data
from backend.cms_mapping import build_uploaded_data_from_cms

try:
    from .utils import (
        aggregate_monthly_sales,
        aggregate_weekly_sales,
        calculate_data_quality_flags,
        detect_available_fields,
        filter_raw_to_skus,
        find_column,
        normalize_sku,
        raw_endpoint_summary,
        resolve_output_dir,
        safe_numeric,
        select_skus_from_raw,
        timestamped_output_path,
        to_jsonable,
        write_excel_report,
    )
except ImportError:
    from utils import (
        aggregate_monthly_sales,
        aggregate_weekly_sales,
        calculate_data_quality_flags,
        detect_available_fields,
        filter_raw_to_skus,
        find_column,
        normalize_sku,
        raw_endpoint_summary,
        resolve_output_dir,
        safe_numeric,
        select_skus_from_raw,
        timestamped_output_path,
        to_jsonable,
        write_excel_report,
    )


DEFAULT_OUTPUT_DIR = "experiments/order_logic_v2/outputs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read CMS API data and audit whether the isolated EU order logic v2 PoC has enough fields.",
    )
    parser.add_argument("--as-of", required=True, help="Inventory snapshot date, YYYY-MM-DD")
    parser.add_argument("--date-from", required=True, help="Sales/logistics query start date, YYYY-MM-DD")
    parser.add_argument("--date-to", required=True, help="Sales/logistics query end date, YYYY-MM-DD")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"Output directory under {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("--limit-skus", type=int, default=None, help="Optional number of SKUs to keep after CMS fetch")
    parser.add_argument(
        "--no-api-cache",
        action="store_true",
        help="Accepted for explicitness. This experiment calls fetch_cms_data directly and does not write API cache.",
    )
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


def stock_quality(uploaded_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    specs = [
        ("SKO 현지재고", "eu_stock", ["EU 현지 가용수량", "avbl_qty"], "EU 현지 가용수량"),
        ("본사 EU창고", "hq_eu_stock", ["본사 EU창고 가용수량", "EU 현지 가용수량", "avbl_qty"], "본사 EU창고 가용수량"),
    ]
    for label, key, available_candidates, preferred_available in specs:
        df = pd.DataFrame(uploaded_data.get(key, pd.DataFrame()))
        sku_col = find_column(df, ["상품코드", "SKU", "prod_cd"])
        stock_col = find_column(df, ["재고수량", "stock_qty"])
        hold_col = find_column(df, ["Hold수량", "hold_qty"])
        available_col = find_column(df, available_candidates)
        rows.append(
            {
                "scope": label,
                "rows": int(len(df)),
                "sku_count": int(df[sku_col].map(normalize_sku).nunique()) if sku_col else 0,
                "stock_qty_sum": float(safe_numeric(df[stock_col]).sum()) if stock_col else 0.0,
                "hold_qty_sum": float(safe_numeric(df[hold_col]).sum()) if hold_col else 0.0,
                "available_qty_sum": float(safe_numeric(df[available_col]).sum()) if available_col else 0.0,
                "preferred_available_column": preferred_available,
                "matched_available_column": available_col or "",
                "has_available": "Y" if available_col else "N",
            }
        )
    return pd.DataFrame(rows)


def weekly_quality(weekly_sales: pd.DataFrame) -> pd.DataFrame:
    if weekly_sales.empty:
        return pd.DataFrame(
            columns=[
                "SKU",
                "판매 주 수",
                "유효 판매 주 수",
                "첫 판매주",
                "마지막 판매주",
                "주평균 판매수량",
                "총 판매수량",
            ]
        )
    grouped = weekly_sales.groupby("SKU", as_index=False).agg(
        **{
            "판매 주 수": ("week_start", "nunique"),
            "유효 판매 주 수": ("sales_qty", lambda s: int(pd.to_numeric(s, errors="coerce").fillna(0).ne(0).sum())),
            "첫 판매주": ("week_start", "min"),
            "마지막 판매주": ("week_start", "max"),
            "주평균 판매수량": ("sales_qty", "mean"),
            "총 판매수량": ("sales_qty", "sum"),
        }
    )
    return grouped.sort_values(["유효 판매 주 수", "총 판매수량"], ascending=[False, False])


def transport_quality(raw: dict[str, list[dict[str, object]]], uploaded_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    raw_shipping = pd.DataFrame(raw.get("shipping") or [])
    mapped = pd.DataFrame(uploaded_data.get("shipping", pd.DataFrame()))
    rows = [
        {
            "metric": "raw rows",
            "value": int(len(raw_shipping)),
            "notes": "",
        },
        {
            "metric": "mapped rows",
            "value": int(len(mapped)),
            "notes": "",
        },
        {
            "metric": "shipping qty field",
            "value": "Y" if find_column(raw_shipping, ["qty"]) or find_column(mapped, ["수량"]) else "N",
            "notes": "운송중 수량 계산",
        },
        {
            "metric": "ship_date field",
            "value": "Y" if find_column(raw_shipping, ["ship_dt"]) or find_column(mapped, ["출고일"]) else "N",
            "notes": "ETA가 없을 때 리드타임 계산 후보",
        },
        {
            "metric": "ETA field",
            "value": "Y" if find_column(raw_shipping, ["eta_dt", "ETA"]) or (find_column(mapped, ["ETA"]) and mapped["ETA"].astype(str).str.strip().ne("").any()) else "N",
            "notes": "실제 ETA가 없으면 출고일+운송수단 L/T 추정",
        },
        {
            "metric": "mode/remark field",
            "value": "Y" if find_column(raw_shipping, ["mode", "remark"]) or find_column(mapped, ["운송수단", "Invoice 비고"]) else "N",
            "notes": "해운/항공/철송 파싱",
        },
        {
            "metric": "arrival_date field",
            "value": "Y" if find_column(raw_shipping, ["arrival_date", "arrival_dt", "actual_arrival_date"]) else "N",
            "notes": "리드타임 백테스트 핵심",
        },
    ]
    return pd.DataFrame(rows)


def po_quality(raw: dict[str, list[dict[str, object]]], uploaded_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    raw_po = pd.DataFrame(raw.get("open_po") or [])
    mapped = pd.DataFrame(uploaded_data.get("open_po", pd.DataFrame()))
    rows = [
        {"metric": "raw rows", "value": int(len(raw_po)), "notes": ""},
        {"metric": "mapped rows", "value": int(len(mapped)), "notes": ""},
        {
            "metric": "open PO qty",
            "value": "Y" if find_column(raw_po, ["open_qty", "po_qty"]) or find_column(mapped, ["미입고 수량", "PO 수량"]) else "N",
            "notes": "미입고 수량 계산",
        },
        {
            "metric": "order_date",
            "value": "Y" if find_column(raw_po, ["order_date", "po_dt", "po_date", "등록일"]) else "N",
            "notes": "PO 시점 백테스트",
        },
        {
            "metric": "expected_in_date",
            "value": "Y" if find_column(raw_po, ["expected_in_date", "납품예정일"]) else "N",
            "notes": "납품 예정 보정",
        },
        {
            "metric": "warehouse_in_date",
            "value": "Y" if find_column(raw_po, ["warehouse_in_date", "입고일"]) else "N",
            "notes": "실제 입고일 백테스트",
        },
    ]
    return pd.DataFrame(rows)


def missing_top10(field_availability: pd.DataFrame) -> pd.DataFrame:
    priority = {
        "sellable_days 계산 필드": 1,
        "promo_flag 또는 bulk deal 식별 필드": 2,
        "SKU alias mapping": 3,
        "실제 도착일 arrival_date": 4,
        "ETA": 5,
        "PO 등록일/order_date": 6,
        "실제 EU창고 입고일 warehouse_in_date": 7,
        "MOQ": 8,
        "유통기한/FR Date": 9,
        "반품 식별 가능": 10,
    }
    missing = field_availability[field_availability["availability"].ne("Y")].copy()
    missing["priority"] = missing["item"].map(priority).fillna(99).astype(int)
    return missing.sort_values(["priority", "category", "item"]).head(10)[
        ["priority", "category", "item", "availability", "matched_fields", "notes"]
    ]


def feasibility(
    field_availability: pd.DataFrame,
    monthly_sales: pd.DataFrame,
    weekly_sales: pd.DataFrame,
    stock_df: pd.DataFrame,
    transport_df: pd.DataFrame,
) -> dict[str, object]:
    by_item = field_availability.set_index("item")["availability"].to_dict()
    monthly_quality = "불가"
    if not monthly_sales.empty:
        months = pd.PeriodIndex(monthly_sales["sales_month"].astype(str), freq="M")
        span = int(months.max().ordinal - months.min().ordinal + 1)
        if span >= 12:
            monthly_quality = "가능" if span >= 18 else "부분 가능"
        elif span >= 6:
            monthly_quality = "부분 가능"
    current_weekly = "가능" if (
        not stock_df.empty
        and stock_df["has_available"].eq("Y").any()
        and not transport_df.empty
        and transport_df.loc[transport_df["metric"].eq("shipping qty field"), "value"].eq("Y").any()
    ) else "부분 가능" if not stock_df.empty else "불가"
    true_weekly = "가능" if not weekly_sales.empty and weekly_sales["week_start"].nunique() >= 8 else "부분 가능" if not weekly_sales.empty else "불가"
    complete_backtest = "가능"
    required_for_backtest = [
        "sellable_days 계산 필드",
        "실제 도착일 arrival_date",
        "PO 등록일/order_date",
        "실제 EU창고 입고일 warehouse_in_date",
    ]
    missing_backtest = [item for item in required_for_backtest if by_item.get(item) != "Y"]
    if missing_backtest:
        complete_backtest = "불가" if len(missing_backtest) >= 2 else "부분 가능"
    critical_missing = missing_top10(field_availability)
    if monthly_quality == "가능" and current_weekly in {"가능", "부분 가능"}:
        new_formula = "부분 가능" if not critical_missing.empty else "가능"
    elif monthly_quality == "부분 가능":
        new_formula = "부분 가능"
    else:
        new_formula = "불가"
    return {
        "신규 산식 테스트 가능 여부": new_formula,
        "월별 예측 테스트 가능 여부": monthly_quality,
        "현재 주차 재고전망 테스트 가능 여부": current_weekly,
        "진짜 주차별 수요예측 테스트 가능 여부": true_weekly,
        "완전한 백테스트 가능 여부": complete_backtest,
        "부족한 핵심 필드 Top 10": ", ".join(critical_missing["item"].astype(str).head(10)) if not critical_missing.empty else "없음",
    }


def recommendation_sheet(conclusions: dict[str, object], missing: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {
            "area": "실험 범위",
            "recommendation": "운영 로직 변경 없이 CMS 읽기 전용 데이터로 PoC 리포트만 생성",
            "reason": "이번 작업은 격리된 검증 환경 구축",
        },
        {
            "area": "월별 예측",
            "recommendation": "12개월 이상 월별 판매가 잡히는 SKU부터 후보 산식 비교",
            "reason": conclusions.get("월별 예측 테스트 가능 여부", ""),
        },
        {
            "area": "주차 재고전망",
            "recommendation": "IP와 OH_t를 분리하고 ETA 도착 주차에만 운송중 수량을 가산",
            "reason": "운송중 재고는 즉시 판매 가능 재고가 아님",
        },
        {
            "area": "데이터 보강",
            "recommendation": "sellable_days, promo/bulk, SKU alias, actual arrival 필드를 우선 확보",
            "reason": ", ".join(missing["item"].astype(str).head(5)) if not missing.empty else "핵심 결측 없음",
        },
    ]
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    validate_yyyy_mm_dd(args.as_of, "--as-of")
    validate_yyyy_mm_dd(args.date_from, "--date-from")
    validate_yyyy_mm_dd(args.date_to, "--date-to")
    output_dir = resolve_output_dir(args.output_dir)

    raw_full = fetch_read_only_cms(args)
    selected_skus = select_skus_from_raw(raw_full, args.limit_skus)
    raw = filter_raw_to_skus(raw_full, selected_skus) if selected_skus else raw_full
    uploaded_data = build_uploaded_data_from_cms(raw)

    sales_detail = pd.DataFrame(uploaded_data.get("sales_detail", pd.DataFrame()))
    monthly_sales = aggregate_monthly_sales(sales_detail)
    weekly_sales = aggregate_weekly_sales(sales_detail)
    field_availability = detect_available_fields(raw, uploaded_data, monthly_sales, weekly_sales)
    monthly_quality = calculate_data_quality_flags(monthly_sales, args.as_of)
    weekly_quality_df = weekly_quality(weekly_sales)
    stock_quality_df = stock_quality(uploaded_data)
    transport_quality_df = transport_quality(raw, uploaded_data)
    po_quality_df = po_quality(raw, uploaded_data)
    missing = missing_top10(field_availability)
    conclusions = feasibility(field_availability, monthly_sales, weekly_sales, stock_quality_df, transport_quality_df)

    summary_rows = [{"항목": key, "결론": value} for key, value in conclusions.items()]
    summary_rows.extend(
        [
            {"항목": "as_of", "결론": args.as_of},
            {"항목": "date_from", "결론": args.date_from},
            {"항목": "date_to", "결론": args.date_to},
            {"항목": "실험 API cache 사용", "결론": "사용 안 함"},
            {"항목": "선택 SKU 수", "결론": len(selected_skus) if selected_skus else "전체"},
            {"항목": "출력 경로", "결론": str(output_dir)},
        ]
    )
    summary = pd.DataFrame(summary_rows)

    endpoint_summary = raw_endpoint_summary(raw)
    if selected_skus:
        full_counts = raw_endpoint_summary(raw_full)[["cms_key", "rows"]].rename(columns={"rows": "rows_before_limit"})
        endpoint_summary = endpoint_summary.merge(full_counts, on="cms_key", how="left")
        endpoint_summary["limit_skus"] = len(selected_skus)

    sheets = {
        "summary": summary,
        "api_endpoints": endpoint_summary,
        "field_availability": field_availability,
        "sales_monthly_quality": monthly_quality,
        "sales_weekly_quality": weekly_quality_df,
        "stock_quality": stock_quality_df,
        "transport_quality": transport_quality_df,
        "po_quality": po_quality_df,
        "missing_fields": missing,
        "recommendation": recommendation_sheet(conclusions, missing),
    }
    now = datetime.now()
    excel_path = timestamped_output_path(output_dir, "data_audit", ".xlsx", now=now)
    json_path = timestamped_output_path(output_dir, "raw_field_report", ".json", now=now)
    write_excel_report(sheets, excel_path)

    json_report = {
        "generated_at": now.isoformat(timespec="seconds"),
        "params": {
            "as_of": args.as_of,
            "date_from": args.date_from,
            "date_to": args.date_to,
            "limit_skus": args.limit_skus,
            "no_api_cache": bool(args.no_api_cache),
            "cache_policy": "direct fetch_cms_data call; no experiment cache written",
        },
        "conclusions": conclusions,
        "api_endpoints": endpoint_summary,
        "field_availability": field_availability,
        "missing_fields_top10": missing,
    }
    json_path.write_text(json.dumps(to_jsonable(json_report), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Excel report: {excel_path}")
    print(f"JSON report: {json_path}")


if __name__ == "__main__":
    main()
