"""교차분석(cross-matrix) 계산 계층.

report_template_export 분해(IMPROVEMENT_PLAN.md 2단계) — 순수 계산 base 계층의 첫 조각.
교차 축/지표/스케일 라벨, 셀 값·원화·점유율 계산, 매트릭스 행 생성, 환율 추론을 담는다.
컨테이너(html/pptx) 렌더링은 하지 않으며 formatting·models에만 의존하므로, 여러 렌더러가
여기로만 아래를 향해 의존해 렌더러 간 순환을 끊는다."""

from __future__ import annotations

import re

from backend.services.reports.formatting import (
    clamp_text,
    clean_metric_display,
    display_krw_amount,
    first_value,
    format_krw_amount,
    format_large_amount,
    format_percent,
    format_percent_value,
    numeric_value,
    percent_numeric_value,
    row_sales_value,
    stringify_report_value,
    top_rows_by_sales,
)
from backend.services.reports.models import ReportBlockPayload

def cross_axis_labels(block: ReportBlockPayload | None, rows: list[dict[str, object]]) -> tuple[str, str]:
    params = block.params if block else {}
    row_label = stringify_report_value(params.get("rowLabel", "") if params else "").strip()
    column_label = stringify_report_value(params.get("columnLabel", "") if params else "").strip()
    if row_label and column_label:
        return row_label, column_label

    ignored = {"표시값", "값", "점유율", "metric", "scale", "brand_role", "is_self", "brand_original", "display_brand"}
    for row in rows:
        labels = [key for key in row.keys() if stringify_report_value(key) not in ignored]
        if not row_label and labels:
            row_label = stringify_report_value(labels[0])
        if not column_label and len(labels) > 1:
            column_label = stringify_report_value(labels[1])
        if row_label and column_label:
            break
    return row_label or "행", column_label or "열"


def cross_metric_label(block: ReportBlockPayload | None, rows: list[dict[str, object]]) -> str:
    params = block.params if block else {}
    metric = stringify_report_value(params.get("metric", "") if params else "").lower()
    if not metric and rows:
        metric = stringify_report_value(first_value(rows[0], ("metric",), "")).lower()
    metric_labels = {
        "sales": "매출액",
        "quantity": "판매량",
        "mom": "MoM 성장률",
        "yoy": "YoY 성장률",
    }
    if metric in metric_labels:
        return metric_labels[metric]
    meta = stringify_report_value(block.meta if block else "").split("·")[0].strip()
    return meta or "값"


def cross_scale_label(block: ReportBlockPayload | None, rows: list[dict[str, object]]) -> str:
    params = block.params if block else {}
    scale = stringify_report_value(params.get("scale", "") if params else "").lower()
    if not scale and rows:
        scale = stringify_report_value(first_value(rows[0], ("scale",), "")).lower()
    return "비중" if scale == "share" else "금액"


def build_cross_table_rows(
    rows: list[dict[str, object]],
    row_label: str,
    column_label: str,
    metric_label: str,
    *,
    include_krw: bool = False,
    eur_krw_rate: float | None = None,
    infer_share: bool = True,
) -> list[list[str]]:
    table_rows: list[list[str]] = []
    total_metric_value = sum(cross_metric_numeric_value(row, metric_label) for row in rows) if infer_share else None
    for row in top_rows_by_sales(rows, 5):
        # 긴 SKU 상품명이 잘리지 않도록 넉넉하게 자르고,
        # 실제 렌더러에서 줄바꿈과 동적 폰트 축소를 적용한다.
        values = [
            clamp_text(cross_dimension_value(row, row_label, row_axis_fallback_keys(row_label)), 40),
            clamp_text(cross_dimension_value(row, column_label, column_axis_fallback_keys(column_label)), 72),
            cross_metric_display(row, metric_label),
        ]
        if include_krw:
            values.append(cross_krw_display(row, metric_label, eur_krw_rate=eur_krw_rate) or "-")
        values.append(cross_share_display(row, metric_label=metric_label, total_metric_value=total_metric_value))
        table_rows.append(values)
    return table_rows


def filter_valid_cross_rows(rows: list[dict[str, object]], row_label: str, column_label: str) -> list[dict[str, object]]:
    row_keys = row_axis_fallback_keys(row_label)
    column_keys = column_axis_fallback_keys(column_label)
    return [
        row
        for row in rows
        if cross_dimension_raw_value(row, row_label, row_keys) and cross_dimension_raw_value(row, column_label, column_keys)
    ]


def cross_dimension_raw_value(row: dict[str, object], label: str, fallback_keys: tuple[str, ...]) -> str:
    value = first_value(row, (label, *fallback_keys), "")
    text = stringify_report_value(value).strip()
    if not text or text in {"-", "None", "nan"}:
        return ""
    return text


def cross_dimension_value(row: dict[str, object], label: str, fallback_keys: tuple[str, ...]) -> str:
    return cross_dimension_raw_value(row, label, fallback_keys) or "-"


def row_axis_fallback_keys(label: str) -> tuple[str, ...]:
    lowered = label.lower()
    if "국가" in label or "country" in lowered:
        return ("국가", "country", "권역", "region", "행", "row")
    if "브랜드" in label or "brand" in lowered:
        return ("브랜드", "브랜드명", "brand", "display_brand", "행", "row")
    if "sku" in lowered:
        return ("SKU", "sku", "상품", "상품명", "product", "행", "row")
    if "성분" in label or "ingredient" in lowered:
        return ("성분", "ingredient", "행", "row")
    return ("행", "row")


def column_axis_fallback_keys(label: str) -> tuple[str, ...]:
    lowered = label.lower()
    if "브랜드" in label or "brand" in lowered:
        return ("브랜드", "브랜드명", "brand", "display_brand", "열", "column")
    if "국가" in label or "country" in lowered:
        return ("국가", "country", "권역", "region", "열", "column")
    if "sku" in lowered:
        return ("SKU", "sku", "상품", "상품명", "product", "열", "column")
    if "성분" in label or "ingredient" in lowered:
        return ("성분", "ingredient", "열", "column")
    return ("열", "column")






def cross_krw_display(row: dict[str, object], metric_label: str, *, eur_krw_rate: float | None = None) -> str:
    if "매출" not in metric_label:
        return "-"
    display = first_value(row, ("원화표시", "KRW표시", "krw_display", "sales_krw_display", "amount_krw_display"), "")
    if display:
        return stringify_report_value(display)
    eur_value = cross_metric_numeric_value(row, metric_label)
    return format_krw_amount(eur_value, eur_krw_rate) or "-"


def infer_eur_krw_rate_from_cross_rows(rows: list[dict[str, object]], metric_label: str) -> float | None:
    for row in rows:
        eur_value = cross_metric_numeric_value(row, metric_label)
        krw_value = numeric_value(cross_krw_display(row, metric_label))
        if eur_value > 0 and krw_value > 0:
            return krw_value / eur_value
    return None


def cross_share_display(row: dict[str, object], *, metric_label: str | None = None, total_metric_value: float | None = None) -> str:
    share = clean_metric_display(first_value(row, ("점유율", "비중", "share"), "-"))
    if share not in {"", "-"}:
        return share
    if metric_label and total_metric_value and total_metric_value > 0:
        value = cross_metric_numeric_value(row, metric_label)
        if value > 0:
            return format_percent(value / total_metric_value)
    return "-"


def unique_cross_values(rows: list[dict[str, object]], label: str, fallback_keys: tuple[str, ...]) -> set[str]:
    values: set[str] = set()
    for row in rows:
        value = cross_dimension_value(row, label, fallback_keys)
        if value and value != "-":
            values.add(value)
    return values


def block_exchange_rate(block: ReportBlockPayload) -> float | None:
    params = block.params or {}
    for key in ("eur_krw_rate", "average_eur_krw_rate", "exchange_rate"):
        rate = numeric_value(params.get(key))
        if rate > 0:
            return rate
    return None


def blocks_exchange_rate(blocks: list[ReportBlockPayload]) -> float | None:
    for block in blocks:
        rate = block_exchange_rate(block)
        if rate:
            return rate
    return None


def infer_eur_krw_rate_from_rows(rows: list[dict[str, object]]) -> float | None:
    for row in rows:
        eur_value = row_sales_value(row)
        krw_value = numeric_value(display_krw_amount(row))
        if eur_value > 0 and krw_value > 0:
            return krw_value / eur_value
    return None


def report_card_cross_matrix_rows(
    block: ReportBlockPayload,
    rows: list[dict[str, object]],
    row_label: str,
    column_label: str,
    metric_label: str,
    scale_label: str,
) -> dict[str, object]:
    row_keys = row_axis_fallback_keys(row_label)
    column_keys = column_axis_fallback_keys(column_label)
    is_growth = "MoM" in metric_label or "YoY" in metric_label
    is_share = str(block.params.get("scale", "") if block.params else "").lower() == "share" and not is_growth
    show_krw = cross_matrix_should_show_krw(block, metric_label, scale_label, is_growth) or any(
        first_value(row, ("원화표시", "KRW표시", "krw_display", "sales_krw_display", "amount_krw_display"), "")
        for row in rows
    )
    eur_krw_rate = block_exchange_rate(block) or infer_eur_krw_rate_from_cross_rows(rows, metric_label)
    values: dict[tuple[str, str], float] = {}
    raw_values: dict[tuple[str, str], list[dict[str, object]]] = {}
    row_totals_numeric: dict[str, float] = {}
    column_totals_numeric: dict[str, float] = {}
    for row in rows:
        row_name = cross_dimension_value(row, row_label, row_keys)
        column_name = cross_dimension_value(row, column_label, column_keys)
        if row_name == "-" or column_name == "-":
            continue
        metric_value = cross_metric_numeric_value(row, metric_label)
        if metric_value == 0:
            metric_value = numeric_value(first_value(row, ("값", "value", "amount", "sales", "revenue"), 0))
        key = (row_name, column_name)
        values[key] = values.get(key, 0) + metric_value
        raw_values.setdefault(key, []).append(row)
        row_totals_numeric[row_name] = row_totals_numeric.get(row_name, 0) + metric_value
        column_totals_numeric[column_name] = column_totals_numeric.get(column_name, 0) + metric_value

    ordered_rows = sorted(row_totals_numeric, key=lambda item: row_totals_numeric[item], reverse=True)
    ordered_columns = sorted(column_totals_numeric, key=lambda item: column_totals_numeric[item], reverse=True)
    total = sum(row_totals_numeric.values())
    displays: dict[tuple[str, str], str] = {}
    krw_displays: dict[tuple[str, str], str] = {}
    display_values: dict[tuple[str, str], float] = {}
    for key, value in values.items():
        source = raw_values.get(key, [{}])[0]
        if is_share:
            share_text = cross_share_display(source, metric_label=metric_label, total_metric_value=total)
            if share_text in {"", "-"} and total > 0:
                share_text = format_percent(value / total)
            displays[key] = share_text or "-"
            display_values[key] = percent_numeric_value(share_text) or (value / total * 100 if total > 0 else 0)
        elif is_growth:
            text = clean_metric_display(cross_metric_display(source, metric_label))
            if text in {"", "-"}:
                text = format_percent_value(value)
            displays[key] = text
            display_values[key] = percent_numeric_value(text) or value
        else:
            displays[key] = cross_metric_display(source, metric_label)
            if show_krw:
                krw_display = cross_krw_display(source, metric_label, eur_krw_rate=eur_krw_rate)
                krw_displays[key] = krw_display if krw_display and krw_display != "-" else format_krw_amount(value, eur_krw_rate)
            display_values[key] = abs(value)

    row_totals: dict[str, str] = {}
    row_total_krw: dict[str, str] = {}
    for row_name, value in row_totals_numeric.items():
        if is_share:
            row_totals[row_name] = format_percent(value / total) if total > 0 else "-"
        elif is_growth:
            row_totals[row_name] = "-"
        else:
            row_totals[row_name] = format_large_amount(value)
            if show_krw:
                row_source_krw_values = [
                    krw
                    for (source_row, _source_column), krw in krw_displays.items()
                    if source_row == row_name and krw
                ]
                row_total_krw[row_name] = row_source_krw_values[0] if len(row_source_krw_values) == 1 else format_krw_amount(value, eur_krw_rate)
    return {
        "rows": ordered_rows,
        "columns": ordered_columns,
        "displays": displays,
        "krw_displays": krw_displays,
        "display_values": display_values,
        "row_totals": row_totals,
        "row_total_krw": row_total_krw,
        "max_abs": max((abs(value) for value in display_values.values()), default=0),
        "is_growth": is_growth,
        "is_share": is_share,
    }


def cross_matrix_should_show_krw(block: ReportBlockPayload, metric_label: str, scale_label: str, is_growth: bool) -> bool:
    if is_growth:
        return False
    params = block.params or {}
    metric = stringify_report_value(params.get("metric", "")).strip().lower()
    scale = stringify_report_value(params.get("scale", "")).strip().lower()
    if metric:
        return metric == "sales" and scale != "share"
    return "매출" in metric_label and scale_label != "비중"


def cross_matrix_source_krw_lookup(
    rows: list[dict[str, object]],
    row_label: str,
    column_label: str,
) -> dict[tuple[str, str], str]:
    row_keys = row_axis_fallback_keys(row_label)
    column_keys = column_axis_fallback_keys(column_label)
    lookup: dict[tuple[str, str], str] = {}
    for row in rows:
        row_name = cross_dimension_value(row, row_label, row_keys)
        column_name = cross_dimension_value(row, column_label, column_keys)
        display = first_value(row, ("원화표시", "KRW표시", "krw_display", "sales_krw_display", "amount_krw_display"), "")
        if row_name != "-" and column_name != "-" and display:
            lookup[(row_name, column_name)] = stringify_report_value(display)
    return lookup


def cross_matrix_source_krw_display(
    rows: list[dict[str, object]],
    row_label: str,
    column_label: str,
    row_name: str,
    column_name: str,
    metric_label: str,
) -> str:
    row_keys = row_axis_fallback_keys(row_label)
    column_keys = column_axis_fallback_keys(column_label)
    for row in rows:
        if cross_dimension_value(row, row_label, row_keys) != row_name:
            continue
        if cross_dimension_value(row, column_label, column_keys) != column_name:
            continue
        direct_display = first_value(row, ("원화표시", "KRW표시", "krw_display", "sales_krw_display", "amount_krw_display"), "")
        if direct_display:
            return stringify_report_value(direct_display)
        display = cross_krw_display(row, metric_label)
        if display and display != "-":
            return display
    return ""


def cross_matrix_cell_color(value: float, max_value: float, has_value: bool, is_growth: bool, RGBColor):
    if not has_value:
        return RGBColor(255, 255, 255)
    ratio = min(max(abs(value) / max_value if max_value else 0, 0), 1)
    if is_growth and value < 0:
        return RGBColor(255, 228, 236) if ratio >= 0.66 else RGBColor(255, 244, 247)
    if ratio >= 0.72:
        return RGBColor(233, 0, 53)
    if ratio >= 0.46:
        return RGBColor(255, 145, 166)
    if ratio >= 0.18:
        return RGBColor(255, 214, 224)
    return RGBColor(255, 242, 246)


def cross_matrix_text_color(value: float, max_value: float, is_growth: bool, RGBColor):
    ratio = min(max(abs(value) / max_value if max_value else 0, 0), 1)
    if is_growth and value < 0:
        return RGBColor(233, 0, 53)
    return RGBColor(255, 255, 255) if ratio >= 0.72 else RGBColor(5, 6, 10)


def compact_cross_text(text: object, *, max_len: int = 76) -> str:
    raw = stringify_report_value(text).strip()
    if not raw:
        return ""
    parts = [part.strip() for part in re.split(r"\s*[·,]\s*", raw) if part.strip()]
    sku_like = [part for part in parts if "[EU]" in part or "SKU" in part.upper() or "-" in part]
    if len(parts) >= 3 and sku_like:
        prefix = parts[0]
        shown = [clamp_text(part, 28) for part in parts[1:3]]
        remaining = max(len(parts) - 3, 0)
        suffix = f" 외 {remaining}건" if remaining else ""
        compact = f"{prefix} · {', '.join(shown)}{suffix}"
        return clamp_text(compact, max_len)
    return clamp_text(raw, max_len)




def cross_metric_display(row: dict[str, object], metric_label: str) -> str:
    is_growth = "MoM" in metric_label or "YoY" in metric_label
    if is_growth:
        keys = ("표시값", "display", "growth_display", "MoM", "mom", "YoY", "yoy", "성장률", "값", "value")
    else:
        keys = ("표시값", "매출표시", "amount_display", "sales_display")
    display = first_value(row, keys, "")
    if display not in {None, ""}:
        if is_growth and isinstance(display, (int, float)) and not isinstance(display, bool):
            return format_percent_value(float(display))
        text = stringify_report_value(display)
        if is_growth and text and "%" not in text and re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text.strip()):
            return format_percent_value(float(text))
        return text
    raw_value = first_value(row, ("값", "value", "매출액", "amount", "sales", "revenue"), "")
    numeric = numeric_value(raw_value)
    if numeric > 0 and "매출" in metric_label:
        return format_large_amount(numeric)
    return stringify_report_value(raw_value or "-")


def cross_metric_numeric_value(row: dict[str, object], metric_label: str) -> float:
    is_growth = "MoM" in metric_label or "YoY" in metric_label
    if is_growth:
        for key in ("값", "value", "MoM", "mom", "YoY", "yoy", "성장률", "표시값", "display"):
            if key not in row:
                continue
            raw = row.get(key)
            if raw in {None, ""}:
                continue
            percent = percent_numeric_value(raw)
            if percent or "%" in stringify_report_value(raw):
                return percent
            return numeric_value(raw)
        return 0.0
    display_value = numeric_value(cross_metric_display(row, metric_label))
    if display_value > 0:
        return display_value
    return row_sales_value(row)


# Final clean overrides for PPT text paths that previously inherited mojibake.
def clean_cross_axis_name(value: object, *, block: ReportBlockPayload | None = None, role: str = "row") -> str:
    text = stringify_report_value(value).strip()
    lower = text.lower()
    if text and not (set(text) <= {"?", " ", "/", "�"}):
        if "sku" in lower:
            return "SKU"
        if "brand" in lower or "브랜드" in text:
            return "브랜드"
        if "country" in lower or "국가" in text:
            return "국가"
        if "region" in lower or "권역" in text:
            return "권역"
        return clamp_text(text, 12)
    # 실제 축 값이 없을 때만(placeholder/빈값) 블록 id·제목 등에서 추정한다.
    # 값이 있는데도 블록 id에 우연히 "country" 같은 단어가 들어있다는 이유로
    # 엉뚱한 축 이름을 강제하면 안 된다(과거 회귀: 성분×국가 교차분석에서
    # id가 "cross:ingredient-country:..."라 행축이 "성분"인데도 "국가"로 표시됨).
    source = f"{getattr(block, 'id', '')} {getattr(block, 'title', '')} {getattr(block, 'subtitle', '')} {getattr(block, 'params', {})}".lower() if block else ""
    if role == "column" and "sku" in source:
        return "SKU"
    if "brand" in source:
        return "브랜드"
    if "country" in source:
        return "국가"
    return "국가" if role == "row" else "SKU"


def clean_cross_metric_summary(block: ReportBlockPayload) -> str:
    params = block.params or {}
    metric = stringify_report_value(params.get("metric", "")).lower()
    scale = stringify_report_value(params.get("scale", "")).lower()
    if metric in {"mom", "yoy", "growth"}:
        return "MoM \uc131\uc7a5\ub960" if metric != "yoy" else "YoY \uc131\uc7a5\ub960"
    if scale == "share":
        return "\ube44\uc911"
    return "\ub9e4\ucd9c\uc561 \u00b7 \uae08\uc561"




__all__ = [
    "block_exchange_rate",
    "blocks_exchange_rate",
    "build_cross_table_rows",
    "clean_cross_axis_name",
    "clean_cross_metric_summary",
    "column_axis_fallback_keys",
    "compact_cross_text",
    "cross_axis_labels",
    "cross_dimension_raw_value",
    "cross_dimension_value",
    "cross_krw_display",
    "cross_matrix_cell_color",
    "cross_matrix_should_show_krw",
    "cross_matrix_source_krw_display",
    "cross_matrix_source_krw_lookup",
    "cross_matrix_text_color",
    "cross_metric_display",
    "cross_metric_label",
    "cross_metric_numeric_value",
    "cross_scale_label",
    "cross_share_display",
    "filter_valid_cross_rows",
    "infer_eur_krw_rate_from_cross_rows",
    "infer_eur_krw_rate_from_rows",
    "report_card_cross_matrix_rows",
    "row_axis_fallback_keys",
    "unique_cross_values",
]
