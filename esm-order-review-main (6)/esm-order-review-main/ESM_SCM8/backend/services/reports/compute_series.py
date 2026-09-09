"""추이·시즌캘린더·성장·소제목 계산 계층.

report_template_export 분해(IMPROVEMENT_PLAN.md 2단계) — 순수 계산 base 계층의 마지막
조각. 월별 추이 시리즈, 시즌 캘린더 셀 값/색 산출, 성장 그룹, 기간 라벨, 카드 소제목
계산을 담는다. 컨테이너 렌더링은 하지 않으며 아래 계산/포맷 계층에만 의존한다."""

from __future__ import annotations

import re

from backend.services.reports.compute_cross import clean_cross_metric_summary
from backend.services.reports.compute_snapshot import percent_metric_numeric_value
from backend.services.reports.formatting import (
    clamp_text,
    clean_metric_display,
    first_value,
    format_integer_like,
    format_percent,
    numeric_value,
    percent_numeric_value,
    stringify_report_value,
)
from backend.services.reports.models import ReportBlockPayload

def report_period_label(blocks: list[ReportBlockPayload]) -> str:
    labels: list[str] = []
    for block in blocks:
        params = block.params or {}
        for key in ("analysis_period_label", "analysisPeriod", "period_label", "period"):
            value = stringify_report_value(params.get(key, "")).strip()
            if value and "미설정" not in value:
                labels.append(value)
                break
        else:
            start = stringify_report_value(first_value(params, ("analysis_start_date", "start_date", "date_from"), "")).strip()
            end = stringify_report_value(first_value(params, ("analysis_end_date", "end_date", "date_to"), "")).strip()
            if start and end:
                labels.append(f"{start} ~ {end}")
    unique_labels = list(dict.fromkeys(labels))
    if not unique_labels:
        return ""
    if len(unique_labels) == 1:
        return unique_labels[0]
    return f"여러 기간 혼합: {unique_labels[0]} 외 {len(unique_labels) - 1}개"


def report_card_month_number(label: object) -> int:
    match = re.search(r"(\d{1,2})", stringify_report_value(label))
    return int(match.group(1)) if match else 99




def is_sku_order_reference_block(block: ReportBlockPayload, rows: list[dict[str, object]]) -> bool:
    if str(block.type or "").strip().lower() != "sku_detail":
        return False
    text = " ".join(
        stringify_report_value(value)
        for value in (block.id, block.title, block.subtitle, block.meta, str(block.params or ""))
    )
    if "발주 참고" in text or "order-reference" in text:
        return True
    if str(block.kind or "").strip().lower() == "kpi":
        labels = {stringify_report_value(first_value(row, ("항목", "label"), "")).strip() for row in rows}
        return bool(labels & {"매출 순위", "판매수량 순위", "피크 3개월 전 준비월", "판매 국가", "피크월 매출"})
    if rows and all(any(key in row for key in ("항목", "값")) for row in rows[:3]):
        labels = {stringify_report_value(first_value(row, ("항목", "label"), "")).strip() for row in rows}
        return bool(labels & {"매출 순위", "판매수량 순위", "피크 3개월 전 준비월", "판매 국가", "피크월 매출"})
    return False


def report_card_season_calendar_rows(
    block: ReportBlockPayload,
    columns: list[str],
    rows: list[dict[str, object]],
    *,
    limit: int | None = 5,
) -> list[dict[str, object]]:
    """시즌 캘린더 웹 카드의 월×기능군 구조를 PPT 카드용으로 정규화한다."""
    block_type = str(block.type or "").strip().lower()
    if block_type != "season_calendar":
        return []
    month_columns = sorted(
        [(report_card_month_number(column), column) for column in columns if report_card_month_number(column) <= 12],
        key=lambda item: item[0],
    )
    if len(month_columns) < 2:
        return []
    label_column = next(
        (
            column
            for column in ("기능군", "기능1", "카테고리", "카테고리1", "항목", "구분")
            if column in columns or any(column in row for row in rows)
        ),
        "",
    )
    if not label_column:
        label_column = next((column for column in columns if report_card_month_number(column) > 12), "")
    normalized_rows: list[dict[str, object]] = []
    for row in rows:
        label = stringify_report_value(row.get(label_column, "")).strip()
        if not label or label == "-":
            continue
        values: list[dict[str, object]] = []
        numeric_values: list[float] = []
        for month_number, column in month_columns:
            raw = row.get(column)
            text = clean_metric_display(raw)
            value = numeric_value(raw)
            has_value = text not in {"", "-"} and (value > 0 or stringify_report_value(raw).strip() in {"0", "0.0"})
            values.append({"month": month_number, "label": f"{month_number}월", "value": value, "has_value": has_value})
            if has_value:
                numeric_values.append(value)
        if not numeric_values:
            continue
        peak_text = stringify_report_value(row.get("피크", "")).strip()
        peak_month = report_card_month_number(peak_text) if peak_text else int(max(values, key=lambda item: float(item["value"]))["month"])
        sku_count = first_value(row, ("SKU수", "sku_count", "SKU Count"), "")
        normalized_rows.append(
            {
                "label": label,
                "peak_month": peak_month if 1 <= peak_month <= 12 else "",
                "peak": peak_text if peak_text and peak_text != "-" else (f"{peak_month}월" if 1 <= peak_month <= 12 else "-"),
                "sku_count": format_integer_like(sku_count) if clean_metric_display(sku_count) != "-" else "1",
                "values": values,
                "max_value": max(numeric_values),
                "avg_value": sum(numeric_values) / len(numeric_values),
            }
        )
    # 화면의 행 순서를 유지하되 빈 행은 제외하고 카드에 필요한 수만 제한한다.
    return normalized_rows[:limit] if limit is not None else normalized_rows


def season_calendar_cell_color(value: float, max_value: float, has_value: bool, RGBColor):
    if not has_value:
        return RGBColor(248, 250, 252)
    ratio = min(max(value / max_value if max_value else 0, 0), 1)
    if ratio >= 0.82:
        return RGBColor(233, 0, 53)
    if ratio >= 0.64:
        return RGBColor(246, 74, 113)
    if ratio >= 0.46:
        return RGBColor(255, 145, 166)
    return RGBColor(255, 214, 224)


def season_calendar_cell_is_dark(value: float, max_value: float) -> bool:
    ratio = min(max(value / max_value if max_value else 0, 0), 1)
    return ratio >= 0.64


def format_season_calendar_value(value: float, peak_value: float, *, is_peak: bool = True) -> str:
    if value <= 0 or peak_value <= 0:
        return "-"
    ratio = min(max(value / peak_value, 0), 1)
    if ratio >= 0.995 and not is_peak:
        ratio = 0.99
    return format_percent(ratio)


def report_card_trend_series(block: ReportBlockPayload, rows: list[dict[str, object]]) -> list[dict[str, object]]:
    block_type = str(block.type or "").strip().lower()
    if str(block.kind or "").strip().lower() != "trend":
        return []

    if block_type == "brand_comparison":
        grouped: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            name = stringify_report_value(
                first_value(row, ("브랜드명", "브랜드", "brand", "display_brand"), "")
            ).strip()
            label = report_card_month_label(row)
            value = report_card_trend_value(row, prefer_share=False)
            if not name or name == "-" or not label or value is None:
                continue
            grouped.setdefault(name, []).append({"label": label, "value": value})
        return [
            {"name": name, "points": sorted(points, key=lambda point: report_card_month_number(point["label"]))}
            for name, points in grouped.items()
            if len(points) >= 2
        ][:6]

    wanted_group = {
        "sku_detail": "월별 추이",
        "brand_top_sku_seasonality": "월별 매출 비중",
        "country_sku_season": "국가 시즌성",
    }.get(block_type)
    if wanted_group is None:
        return []

    points: list[dict[str, object]] = []
    for row in rows:
        group_label = stringify_report_value(first_value(row, ("구분", "group", "category"), "")).strip()
        if group_label != wanted_group:
            continue
        label = report_card_month_label(row)
        value = report_card_trend_value(row, prefer_share=True)
        if not label or value is None:
            continue
        points.append({"label": label, "value": value})
    points.sort(key=lambda point: report_card_month_number(point["label"]))
    return [{"name": wanted_group, "points": points}] if len(points) >= 2 else []


def report_card_month_label(row: dict[str, object]) -> str:
    for key in ("월", "month", "월명", "항목"):
        text = stringify_report_value(row.get(key, "")).strip()
        if text and text != "-" and ("월" in text or text.isdigit()):
            return text if "월" in text else f"{text}월"
    return ""


def report_card_trend_value(row: dict[str, object], *, prefer_share: bool) -> float | None:
    if prefer_share:
        for key in ("브랜드 내 월평균 매출 비중", "매출비중", "점유율", "비중", "share", "ratio"):
            text = clean_metric_display(row.get(key))
            if text not in {"", "-"}:
                return percent_numeric_value(row.get(key))
    for key in ("월평균 매출액", "매출액", "매출", "판매수량", "amount", "sales", "revenue", "quantity", "value", "값"):
        raw = row.get(key)
        value = numeric_value(raw)
        if value or stringify_report_value(raw).strip() in {"0", "0.0"}:
            return value
    return None


def report_card_subtitle(block: ReportBlockPayload, rows: list[dict[str, object]]) -> str:
    if str(block.type or "").strip().lower() == "cross_matrix":
        return clean_cross_metric_summary(block)
    if str(block.type or "").strip().lower() == "brand_overview":
        return stringify_report_value(block.meta or "\uc120\ud0dd \ube0c\ub79c\ub4dc \ud575\uc2ec \uc9c0\ud45c")
    if str(block.type or "").strip().lower() in {"country_growth", "brand_growth"}:
        return stringify_report_value(block.subtitle or block.meta or "\uc131\uc7a5\u00b7\uac10\uc18c \uc0c1\uc704")
    if percent_rows := [row for row in rows if str(row.get("value", "")).strip().endswith("%")]:
        top = percent_rows[0]
        return f"TOP {min(len(rows), 5)} \uc9d1\uacc4 \u00b7 {top['value']} \uae30\uc900"
    if block.meta:
        return stringify_report_value(block.meta)
    return f"TOP {min(len(rows), 5)}"


def report_card_body_subtitle(
    block: ReportBlockPayload,
    rows: list[dict[str, object]],
    page_index: int | None = None,
    page_count: int | None = None,
) -> str:
    if page_index and page_count and page_count > 1 and str(block.kind or "").strip().lower() == "ranking":
        basis = "매출 기준"
        meta = stringify_report_value(block.meta or block.subtitle or "")
        if "비중" in meta:
            basis = "비중 기준"
        elif "성장" in meta:
            basis = "성장률 기준"
        return f"전체 순위 {page_index}/{page_count} · {basis}"
    return report_card_subtitle(block, rows)


def country_growth_amount_flow(row: dict[str, object]) -> str:
    previous = clean_metric_display(first_value(row, ("비교기간 금액", "이전 금액", "previous_amount", "비교기간 매출"), ""))
    current = clean_metric_display(first_value(row, ("기준기간 매출", "현재 금액", "current_amount", "매출표시", "매출액", "amount", "sales"), ""))
    flow = f"{previous} \u2192 {current}" if previous != "-" and current != "-" else (current if current != "-" else previous)
    krw = clean_metric_display(first_value(row, ("원화표시", "KRW표시", "krw_display", "sales_krw_display", "amount_krw_display", "원화 환산"), ""))
    if krw and krw != "-" and krw not in flow:
        return f"{flow} \u00b7 {krw}" if flow and flow != "-" else krw
    return flow


def report_card_growth_groups(rows: list[dict[str, object]], block_type: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rising: list[dict[str, object]] = []
    declining: list[dict[str, object]] = []
    for row in rows:
        group = stringify_report_value(first_value(row, ("구분", "group", "category"), "")).strip()
        name = stringify_report_value(first_value(row, ("국가", "country", "브랜드명", "브랜드", "brand", "항목"), "")).strip()
        sub = stringify_report_value(first_value(row, ("권역", "region"), "")).strip() if block_type == "country_growth" else stringify_report_value(first_value(row, ("비교기간", "period"), "")).strip()
        growth = clean_metric_display(first_value(row, ("성장률", "YoY", "MoM", "성장률MoM", "growth"), ""))
        normalized = {
            "country": name,
            "sub": sub or "-",
            "growth": growth,
            "amount_flow": country_growth_amount_flow(row),
            "sort": abs(percent_metric_numeric_value(growth)),
            "vanished": "소멸" in stringify_report_value(row),
        }
        if not normalized["country"]:
            continue
        if "감소" in group or "하락" in group or str(growth).startswith("-") or normalized["vanished"]:
            declining.append(normalized)
        elif "성장" in group or "상승" in group or percent_metric_numeric_value(growth) > 0:
            rising.append(normalized)
    rising.sort(key=lambda item: item["sort"], reverse=True)
    declining.sort(key=lambda item: item["sort"], reverse=True)
    return rising, declining


def report_card_header_subtitle(block: ReportBlockPayload) -> str:
    if str(block.type or "").strip().lower() == "cross_matrix":
        return clean_cross_metric_summary(block)
    return clamp_text(stringify_report_value(block.subtitle or block.meta or block.type), 118)



__all__ = [
    "country_growth_amount_flow",
    "format_season_calendar_value",
    "is_sku_order_reference_block",
    "report_card_body_subtitle",
    "report_card_growth_groups",
    "report_card_header_subtitle",
    "report_card_month_label",
    "report_card_month_number",
    "report_card_season_calendar_rows",
    "report_card_subtitle",
    "report_card_trend_series",
    "report_card_trend_value",
    "report_period_label",
    "season_calendar_cell_color",
    "season_calendar_cell_is_dark",
]
