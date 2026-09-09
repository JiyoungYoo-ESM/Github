"""스냅샷·표·카드 행/열 계산 계층.

report_template_export 분해(IMPROVEMENT_PLAN.md 2단계) — 순수 계산 base 계층의 두 번째
조각. 블록 스냅샷을 표 행/열로 변환, 카드 행 값·정렬·태그 산출, 구조화 표 페이지네이션/
정렬, KPI·요약 지표 계산, 브랜드/국가 상세 행 계산을 담는다. 컨테이너(html/pptx) 렌더링은
하지 않으며 formatting/models/report_data/compute_cross/pptx_prims(chunk_rows)에만 의존한다."""

from __future__ import annotations

import re

from backend.services.reports.compute_cross import (
    block_exchange_rate,
    build_cross_table_rows,
    compact_cross_text,
    cross_axis_labels,
    cross_metric_label,
    cross_scale_label,
    filter_valid_cross_rows,
    infer_eur_krw_rate_from_cross_rows,
)
from backend.services.reports.formatting import (
    clamp_text,
    clean_metric_display,
    display_amount,
    display_krw_amount,
    first_value,
    format_large_amount,
    format_percent_value,
    is_number,
    normalize_brand_name,
    numeric_value,
    percent_numeric_value,
    row_sales_value,
    stringify_report_value,
    top_rows_by_sales,
)
from backend.services.reports.models import (
    REPORT_BLOCK_SECTIONS,
    ReportBlockPayload,
    SECTION_ORDER,
    STRUCTURED_TABLE_ROWS_PER_SLIDE,
    TECHNICAL_SNAPSHOT_FIELDS,
)
from backend.services.reports.pptx_prims import chunk_rows
from backend.services.reports.report_data import (
    block_sales_value,
    is_confidential_key,
    snapshot_preview_rows,
)

def report_card_all_rows(block: ReportBlockPayload, columns: list[str], rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped = structured_row_groups(block, columns, rows)
    candidate_rows: list[dict[str, object]] = []
    for group_label, _group_columns, group_rows in grouped:
        if str(block.type or "").lower() == "country_detail" and group_label in {"국가 요약", "월 최고 매출"}:
            continue
        candidate_rows.extend(group_rows)
    if not candidate_rows:
        candidate_rows = rows
    use_percent_metric = any(row_card_has_percent_metric(row) for row in candidate_rows)
    sort_value = row_card_percent_sort_value if use_percent_metric else row_card_sort_value
    ranked = sorted(candidate_rows, key=sort_value, reverse=True)
    max_card_value = max((sort_value(row) for row in ranked), default=0) or 1
    card_rows: list[dict[str, object]] = []
    for row in ranked:
        label = report_card_row_label(row, columns)
        if not label or label == "-":
            continue
        value, ratio = report_card_row_value_and_ratio(row, max_card_value)
        card_rows.append(
            {
                "label": label,
                "tag": report_card_row_tag(row, columns),
                "value": value,
                "sub": report_card_row_subtext(row),
                "ratio": ratio,
            }
        )
    return card_rows


def country_detail_groups(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        group = stringify_report_value(row.get("구분", "")).strip() or "상세"
        groups.setdefault(group, []).append(row)
    return groups


def country_detail_display_amount(row: dict[str, object]) -> str:
    return clean_metric_display(first_value(row, ("매출표시", "매출액", "값"), ""))


def country_detail_display_krw(row: dict[str, object]) -> str:
    return clean_metric_display(first_value(row, ("원화표시", "보조값"), ""))


def country_detail_item_label(row: dict[str, object]) -> str:
    return clean_metric_display(first_value(row, ("항목", "국가", "브랜드", "카테고리"), ""))


def summary_metric_pairs(blocks: list[ReportBlockPayload], *, include_sub: bool = False) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for block in blocks:
        for row in snapshot_preview_rows(block):
            label = stringify_report_value(first_value(row, ("지표", "항목", "label", "metric", "구분", "name"), "")).strip()
            value = stringify_report_value(first_value(row, ("값", "value", "금액", "amount", "display", "매출표시"), "")).strip()
            if not (label or value):
                continue
            if include_sub:
                sub = stringify_report_value(first_value(row, ("보조", "sub", "비고"), "")).strip()
                if sub and sub != "-":
                    value = f"{value} ({sub})" if value else sub
            pairs.append((label or "-", value or "-"))
    return pairs


def section_rows(blocks: list[ReportBlockPayload]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for block in blocks:
        rows.extend(snapshot_preview_rows(block))
    return top_rows_by_sales(rows, len(rows))


def brand_section_rows(blocks: list[ReportBlockPayload]) -> list[dict[str, object]]:
    ranked_rows: dict[str, dict[str, object]] = {}
    growth_rows: dict[str, dict[str, object]] = {}

    def upsert_ranked(row: dict[str, object]) -> None:
        labels = row_brand_labels(row)
        if not labels:
            return
        key = normalize_brand_name(labels[0])
        if not key:
            return
        candidate = dict(row)
        current = ranked_rows.get(key)
        if current is None:
            ranked_rows[key] = candidate
            return
        # 브랜드 순위·요약처럼 매출 근거가 있는 행을 기준으로 삼되,
        # 다른 카드에만 존재하는 SKU·국가·성장 필드는 함께 보존한다.
        if row_sales_value(candidate) > row_sales_value(current):
            merged = candidate
            secondary = current
        else:
            merged = current
            secondary = candidate
        for field, value in secondary.items():
            existing = merged.get(field)
            if (existing is None or existing == "" or existing == "-") and not (value is None or value == "" or value == "-"):
                merged[field] = value
        ranked_rows[key] = merged

    for block in blocks:
        rows = snapshot_preview_rows(block)
        block_type = str(block.type or "").strip().lower()

        if block_type == "brand_growth":
            basis = str((block.params or {}).get("comparison_basis") or "").lower()
            growth_key = "YoY" if basis == "yoy" else "성장률MoM" if basis == "mom" else "성장률"
            for row in rows:
                labels = row_brand_labels(row)
                if not labels:
                    continue
                key = normalize_brand_name(labels[0])
                growth_value = first_value(row, ("성장률", "성장률MoM", "MoM", "YoY"), "")
                growth_rows[key] = {
                    **row,
                    growth_key: growth_value,
                }
            continue

        if block_type == "brand_comparison":
            # 월별 추이 행은 브랜드별 선택 기간 매출 합계로 묶어 순위 표시용으로 사용한다.
            # 카드 제목 자체를 브랜드명으로 보지 않는다.
            grouped: dict[str, dict[str, object]] = {}
            for row in rows:
                labels = row_brand_labels(row)
                if not labels:
                    continue
                key = normalize_brand_name(labels[0])
                aggregate = grouped.get(key)
                if aggregate is None:
                    aggregate = dict(row)
                    aggregate["매출액"] = row_sales_value(row)
                    grouped[key] = aggregate
                else:
                    aggregate["매출액"] = row_sales_value(aggregate) + row_sales_value(row)
            for row in grouped.values():
                upsert_ranked(row)
            continue

        if block_type == "brand_rank":
            scope = str((block.params or {}).get("scope") or "").lower()
            if scope in {"all", "all_brands"} or not selected_brand_labels(block):
                for row in rows:
                    upsert_ranked(row)
            else:
                selected = selected_brand_row(block)
                if selected:
                    upsert_ranked(selected)
            continue

        if block_type == "brand_overview":
            for row in rows:
                upsert_ranked(row)
            continue

        # 이후 추가되는 브랜드 카드도 실제 브랜드 필드와 매출 근거가 있을 때만
        # 순위 데이터로 사용한다. 카드 제목 추론은 금지한다.
        for row in rows:
            if row_brand_labels(row) and row_sales_value(row) > 0:
                upsert_ranked(row)

    for key, growth_row in growth_rows.items():
        current = ranked_rows.get(key)
        if current is None:
            continue
        for field in ("성장률MoM", "YoY", "MoM", "성장률", "비교기간"):
            value = growth_row.get(field)
            if value not in {None, "", "-"}:
                current[field] = value

    # 성장 카드만 담긴 경우에도 카드 제목 대신 실제 브랜드 목록을 보여준다.
    if not ranked_rows:
        for row in growth_rows.values():
            upsert_ranked(row)

    return top_rows_by_sales(list(ranked_rows.values()), len(ranked_rows))


def selected_brand_row(block: ReportBlockPayload) -> dict[str, object]:
    rows = snapshot_preview_rows(block)
    labels = selected_brand_labels(block)
    if labels:
        matched_rows = [
            row
            for row in rows
            if any(normalize_brand_name(row_label) in labels for row_label in row_brand_labels(row))
        ]
        if matched_rows:
            return top_rows_by_sales(matched_rows, 1)[0]
    if len(rows) == 1:
        return rows[0]
    if labels:
        label = sorted(labels)[0]
        return {
            "브랜드명": label,
            "매출액": first_value(block.params or {}, ("매출액", "amount", "sales", "revenue"), ""),
            "매출표시": first_value(block.params or {}, ("매출표시", "amount_display", "sales_display"), ""),
            "원화표시": first_value(block.params or {}, ("원화표시", "krw_display", "sales_krw_display", "amount_krw_display"), ""),
            "성장률MoM": first_value(block.params or {}, ("성장률MoM", "MoM", "mom"), ""),
            "YoY": first_value(block.params or {}, ("YoY", "yoy"), ""),
            "마진율": first_value(block.params or {}, ("마진율", "원가율", "공유지표"), ""),
        }
    return {}


def selected_brand_labels(block: ReportBlockPayload) -> set[str]:
    labels: set[str] = set()
    params = block.params or {}
    for key in ("display_brand", "brand", "브랜드명", "브랜드", "brand_name"):
        value = params.get(key)
        if value not in {None, "", "-"}:
            labels.add(normalize_brand_name(stringify_report_value(value)))
    title_label = brand_label_from_title(block.title)
    if title_label:
        labels.add(normalize_brand_name(title_label))
    return {label for label in labels if label}


def brand_label_from_title(title: str) -> str:
    label = str(title or "").strip()
    for suffix in ("브랜드 판매 순위", "브랜드별 판매 순위", "판매 순위", "브랜드 기준 분석", "브랜드 분석"):
        if label.endswith(suffix):
            label = label[: -len(suffix)].strip()
    return label


def row_brand_labels(row: dict[str, object]) -> list[str]:
    labels: list[str] = []
    for key in ("브랜드명", "브랜드", "brand", "display_brand", "brand_original"):
        value = row.get(key)
        if value not in {None, "", "-"}:
            labels.append(stringify_report_value(value))
    return labels


def unique_rows_by_label(rows: list[dict[str, object]], label_keys: tuple[str, ...]) -> list[dict[str, object]]:
    unique: dict[str, dict[str, object]] = {}
    fallback_index = 0
    for row in top_rows_by_sales(rows, len(rows)):
        label = stringify_report_value(first_value(row, label_keys, "")).strip()
        if label:
            key = normalize_brand_name(label)
        else:
            key = f"__row_{fallback_index}"
            fallback_index += 1
        if key not in unique:
            unique[key] = row
    return list(unique.values())


def report_card_title(block: ReportBlockPayload) -> str:
    block_type = str(block.type or "").strip().lower()
    title = stringify_report_value(block.title or block_type_label(block.type or "summary"))
    subtitle = stringify_report_value(block.subtitle or "").strip()
    if block_type == "cross_matrix":
        base = compact_cross_text(title, max_len=54)
        if subtitle:
            return compact_cross_text(f"{base} · {subtitle}", max_len=68)
        return base
    if subtitle:
        return f"{title} · {clamp_text(subtitle, 46)}"
    return title


def report_card_slide_title(block: ReportBlockPayload, page_index: int | None = None, page_count: int | None = None) -> str:
    block_type = str(block.type or "").strip().lower()
    title = stringify_report_value(block.title or "보고서 카드")
    if block_type == "cross_matrix":
        title = compact_cross_text(title, max_len=52)
    if page_index and page_count and page_count > 1:
        return f"{title} ({page_index}/{page_count})"
    return title




def report_card_rows(block: ReportBlockPayload, columns: list[str], rows: list[dict[str, object]]) -> list[dict[str, object]]:
    if not rows:
        return []
    grouped = structured_row_groups(block, columns, rows)
    candidate_rows: list[dict[str, object]] = []
    for group_label, group_columns, group_rows in grouped:
        if str(block.type or "").lower() == "country_detail" and group_label in {"국가 요약", "월 최고 매출"}:
            continue
        candidate_rows.extend(group_rows)
    if not candidate_rows:
        candidate_rows = rows

    use_percent_metric = any(row_card_has_percent_metric(row) for row in candidate_rows)
    sort_value = row_card_percent_sort_value if use_percent_metric else row_card_sort_value
    ranked = sorted(candidate_rows, key=sort_value, reverse=True)
    max_card_value = max((sort_value(row) for row in ranked), default=0) or 1
    card_rows: list[dict[str, object]] = []
    for row in ranked[:5]:
        label = report_card_row_label(row, columns)
        if not label or label == "-":
            continue
        value, ratio = report_card_row_value_and_ratio(row, max_card_value)
        card_rows.append(
            {
                "label": label,
                "tag": report_card_row_tag(row, columns),
                "value": value,
                "sub": report_card_row_subtext(row),
                "ratio": ratio,
            }
        )
    return card_rows


def report_card_row_subtext(row: dict[str, object]) -> str:
    parts: list[str] = []
    krw = display_krw_amount(row)
    if krw and krw != "-" and krw != display_amount(row):
        parts.append(krw)
    note = clean_metric_display(first_value(row, ("비고", "보조값", "description", "note"), ""))
    if note and note != "-" and note not in parts:
        parts.append(note)
    return " · ".join(parts[:2])


def row_card_has_percent_metric(row: dict[str, object]) -> bool:
    return any(clean_metric_display(row.get(key)) not in {"", "-"} for key in ("점유율", "비중", "매출비중", "성장률", "YoY", "MoM"))


def row_card_percent_sort_value(row: dict[str, object]) -> float:
    for key in ("점유율", "비중", "매출비중", "성장률", "YoY", "MoM"):
        text = clean_metric_display(row.get(key))
        if text not in {"", "-"}:
            return percent_metric_numeric_value(row.get(key))
    return 0.0


def row_card_sort_value(row: dict[str, object]) -> float:
    for key in ("점유율", "비중", "매출비중", "성장률", "YoY", "MoM"):
        value = percent_metric_numeric_value(row.get(key))
        if value:
            return value
    return row_sales_value(row)


def report_card_row_value_and_ratio(row: dict[str, object], max_card_value: float) -> tuple[str, float]:
    for key in ("점유율", "비중", "매출비중", "성장률", "YoY", "MoM"):
        raw = row.get(key)
        text = clean_metric_display(raw)
        if text not in {"", "-"} and ("%" in text or is_number(raw) or numeric_value(text) > 0):
            value = percent_metric_numeric_value(raw)
            ratio = value / max_card_value if value and max_card_value else 0
            display = text if "%" in text else format_percent_value(value)
            return display, ratio
    amount = row_sales_value(row)
    return display_amount(row), amount / max_card_value if max_card_value else 0

def percent_metric_numeric_value(value: object) -> float:
    percent_value = percent_numeric_value(value)
    if percent_value:
        return percent_value
    text = clean_metric_display(value)
    if text in {"", "-"}:
        return 0.0
    return numeric_value(text)


def report_card_row_label(row: dict[str, object], columns: list[str]) -> str:
    preferred = ("항목", "상품명", "SKU", "sku", "브랜드명", "브랜드", "국가", "권역", "성분", "카테고리")
    for key in preferred:
        value = stringify_report_value(row.get(key, "")).strip()
        if value and value != "-":
            return value
    for column in columns:
        normalized = normalized_table_column(column)
        if normalized in {"구분", "순위", "매출액", "매출표시", "원화표시", "비고"}:
            continue
        value = stringify_report_value(row.get(column, "")).strip()
        if value and value != "-":
            return value
    return "-"


def report_card_row_tag(row: dict[str, object], columns: list[str]) -> str:
    for key in ("상품코드", "SKU코드", "sku_code", "code", "브랜드", "브랜드명", "권역"):
        value = stringify_report_value(row.get(key, "")).strip()
        if value and value != "-" and value != report_card_row_label(row, columns):
            return value
    return ""

def structured_block_page_specs(block: ReportBlockPayload, columns: list[str], rows: list[dict[str, object]]) -> list[dict[str, object]]:
    if str(block.type or "").strip().lower() == "season_calendar":
        row_pages = chunk_rows(rows, 5) if rows else [[]]
        return [{"columns": columns, "rows": page_rows, "group": ""} for page_rows in row_pages]
    grouped = structured_row_groups(block, columns, rows)
    specs: list[dict[str, object]] = []
    for group_label, group_columns, group_rows in grouped:
        column_pages = paginate_table_columns(group_columns, max_columns=6)
        row_pages = chunk_rows(group_rows, STRUCTURED_TABLE_ROWS_PER_SLIDE) if group_rows else [[]]
        for page_columns in column_pages:
            for page_rows in row_pages:
                specs.append({"columns": page_columns, "rows": page_rows, "group": group_label})
    return specs


def structured_row_groups(
    block: ReportBlockPayload,
    columns: list[str],
    rows: list[dict[str, object]],
) -> list[tuple[str, list[str], list[dict[str, object]]]]:
    group_column = next((column for column in columns if normalized_table_column(column) == "구분"), "")
    grouped_detail_types = {"country_detail", "brand_top_sku_seasonality"}
    if str(block.type or "").strip().lower() not in grouped_detail_types or not group_column or not rows:
        return [("", columns, rows)]

    group_order: list[str] = []
    grouped_rows: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        label = stringify_report_value(row.get(group_column, "")).strip() or "기타"
        if label not in grouped_rows:
            grouped_rows[label] = []
            group_order.append(label)
        grouped_rows[label].append(row)

    if len(group_order) <= 1:
        return [("", columns, rows)]

    result: list[tuple[str, list[str], list[dict[str, object]]]] = []
    block_type = str(block.type or "").strip().lower()
    for label in group_order:
        group_rows = grouped_rows[label]
        group_columns = meaningful_structured_columns(columns, group_rows, skip_column=group_column)
        group_columns = semantic_structured_group_columns(block_type, label, group_columns)
        result.append((label, group_columns, group_rows))
    return result


def semantic_structured_group_columns(block_type: str, group_label: str, columns: list[str]) -> list[str]:
    if block_type != "brand_top_sku_seasonality":
        return columns
    normalized_label = group_label.replace(" ", "")
    if "월별" in normalized_label:
        allowed = {"관측완료월수", "매출액", "매출표시", "매출규모", "원화표시", "월", "매출비중"}
    elif "상위SKU" in normalized_label:
        allowed = {"순위", "SKU", "상품명", "카테고리", "매출액", "매출표시", "매출규모", "원화표시", "판매수량"}
    else:
        return columns
    filtered = [column for column in columns if normalized_table_column(column) in allowed or str(column).replace(" ", "") in allowed]
    return filtered or columns


def meaningful_structured_columns(columns: list[str], rows: list[dict[str, object]], *, skip_column: str = "") -> list[str]:
    def has_value(column: str) -> bool:
        return any(clean_metric_display(row.get(column)) not in {"", "-"} for row in rows)

    filtered = [column for column in columns if column != skip_column and has_value(column)]
    if filtered:
        return filtered
    return [column for column in columns if column != skip_column]


def group_blocks_by_section(blocks: list[ReportBlockPayload]) -> dict[str, list[ReportBlockPayload]]:
    grouped: dict[str, list[ReportBlockPayload]] = {section: [] for section in SECTION_ORDER}
    for block in blocks:
        section = block.section if block.section in REPORT_BLOCK_SECTIONS else "summary"
        grouped.setdefault(section, []).append(block)
    return grouped


def structured_table_alignment(column: object, column_index: int, value: object, PP_ALIGN):
    normalized = normalized_table_column(column)
    if column_index == 0 or normalized in {
        "브랜드",
        "브랜드명",
        "국가",
        "국가권역",
        "권역",
        "항목",
        "상품",
        "상품명",
        "sku",
        "sku명",
        "카테고리",
        "성분",
        "구분",
        "비고",
        "비교기간",
    }:
        return PP_ALIGN.LEFT
    if normalized in {
        "순위",
        "sku수",
        "국가수",
        "월",
        "판매수량",
        "수량",
        "점유율",
        "비중",
        "매출비중",
        "성장률",
        "성장률mom",
        "성장률yoy",
        "mom",
        "yoy",
        "매출액",
        "매출액eur",
        "매출규모",
        "매출표시",
        "원화표시",
        "원화환산",
        "기준월매출",
        "비교월금액",
        "월평균매출액",
        "브랜드내월매출비중",
    }:
        return PP_ALIGN.RIGHT
    return PP_ALIGN.RIGHT if is_numeric_display(value) else PP_ALIGN.LEFT


def is_numeric_display(value: object) -> bool:
    text = stringify_report_value(value).strip()
    if not text or text == "-":
        return False
    return bool(re.fullmatch(r"[+-]?\s*(?:[€$₩])?\s*\d[\d,]*(?:\.\d+)?\s*(?:%|개|건|억|원|m|M|k|K)?", text))


def report_snapshot_rows_and_columns(block: ReportBlockPayload, audience: str) -> tuple[list[str], list[dict[str, object]]]:
    """보고서에 표시할 블록별 열·행을 반환한다.

    교차분석은 화면과 동일하게 원화 환산과 비중을 보강하고, 나머지 블록은
    마스킹된 snapshot 전체 열을 손실 없이 유지한다.
    """
    rows = normalize_structured_snapshot_rows(block, snapshot_preview_rows(block))
    if block.section == "brand" and (block.params or {}).get("brand"):
        labels = selected_brand_labels(block)
        matching_rows = [row for row in rows if any(normalize_brand_name(label) in labels for label in row_brand_labels(row))]
        if matching_rows:
            rows = matching_rows
    if block.type == "cross_matrix":
        row_label, column_label = cross_axis_labels(block, rows)
        metric_label = cross_metric_label(block, rows)
        scale_label = cross_scale_label(block, rows)
        valid_rows = filter_valid_cross_rows(rows, row_label, column_label)
        eur_krw_rate = block_exchange_rate(block) or infer_eur_krw_rate_from_cross_rows(valid_rows, metric_label)
        include_krw = audience == "internal" and "매출" in metric_label and scale_label == "금액"
        values = build_cross_table_rows(
            valid_rows,
            row_label,
            column_label,
            metric_label,
            include_krw=include_krw,
            eur_krw_rate=eur_krw_rate,
            infer_share=len(valid_rows) > 1,
        )
        columns = [row_label, column_label, metric_label, *(["원화 환산"] if include_krw else []), "비중"]
        return columns, [dict(zip(columns, row_values)) for row_values in values]
    return table_columns(block, rows, audience), rows


def paginate_table_columns(columns: list[str], *, max_columns: int) -> list[list[str]]:
    if not columns:
        return [[]]
    if len(columns) <= max_columns:
        return [columns]
    identity_columns = structured_identity_columns(columns, max_columns=max_columns)
    metric_columns = [column for column in columns if column not in identity_columns]
    chunk_size = max(max_columns - len(identity_columns), 1)
    order = {column: index for index, column in enumerate(columns)}
    pages: list[list[str]] = []
    for index in range(0, len(metric_columns), chunk_size):
        page = [*identity_columns, *metric_columns[index : index + chunk_size]]
        pages.append(sorted(dict.fromkeys(page), key=lambda column: order[column]))
    return pages or [identity_columns]


def normalized_table_column(column: object) -> str:
    return re.sub(r"[\s_·/()\-]+", "", stringify_report_value(column)).lower()


def structured_identity_columns(columns: list[str], *, max_columns: int) -> list[str]:
    """Repeat key identity columns on horizontally paginated table pages."""
    if not columns:
        return []
    identity = [columns[0]]
    preferred = {
        "항목",
        "sku",
        "sku명",
        "상품",
        "상품명",
        "브랜드",
        "브랜드명",
        "국가",
        "국가권역",
        "권역",
    }
    capacity = min(3, max(max_columns - 2, 1))
    for column in columns[1:]:
        if len(identity) >= capacity:
            break
        if normalized_table_column(column) in preferred:
            identity.append(column)
    return identity


def normalize_structured_snapshot_rows(block: ReportBlockPayload, rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Normalize ambiguous display rows before detail PPT/HTML rendering."""
    normalized_rows: list[dict[str, object]] = []
    for source_row in rows:
        row = dict(source_row)
        if str(block.type or "").lower() == "country_sku_season" and str(row.get("구분") or "").strip() == "국가 시즌성":
            if row.get("브랜드명") in {None, "", "-"}:
                row["브랜드명"] = "전체 브랜드"
        normalized_rows.append(row)
    return normalized_rows


def table_columns(block: ReportBlockPayload, rows: list[dict[str, object]], audience: str) -> list[str]:
    snapshot = block.snapshot or {}
    raw_columns = snapshot.get("columns")
    columns = [str(column) for column in raw_columns if str(column).strip()] if isinstance(raw_columns, list) else []
    if not columns and rows:
        columns = [str(key) for key in rows[0].keys()]
    return [
        column
        for column in columns
        if column not in TECHNICAL_SNAPSHOT_FIELDS and (audience == "internal" or not is_confidential_key(column))
    ]


def display_table_header(column: object) -> str:
    text = stringify_report_value(column).strip()
    normalized = re.sub(r"[\s_·/-]+", "", text).lower()
    if normalized in {"성장률mom", "mom성장률", "mom", "growthmom", "momgrowth"}:
        return "성장률(MoM)" if normalized != "mom" else "MoM"
    if normalized in {"성장률yoy", "yoy성장률", "yoy", "growthyoy", "yoygrowth"}:
        return "성장률(YoY)" if normalized != "yoy" else "YoY"
    if normalized in {"성장률", "growth", "growthrate"}:
        return "성장률(MoM)"
    if normalized in {"원화표시", "원화환산", "krw", "krwdisplay"}:
        return "원화 환산"
    if normalized in {"매출액", "amount", "sales", "revenue"}:
        return "매출액(EUR)"
    if normalized in {"매출표시", "amountdisplay", "salesdisplay"}:
        return "매출 규모"
    if normalized in {"매출비중", "salesshare"}:
        return "매출 비중"
    return text


def column_widths(columns: list[str]) -> list[float]:
    if not columns:
        return []
    weights: list[float] = []
    for column in columns:
        normalized = normalized_table_column(column)
        if normalized in {"항목", "sku", "sku명", "상품", "상품명"}:
            weights.append(3.4)
        elif normalized in {"브랜드", "브랜드명", "국가", "국가권역", "권역"}:
            weights.append(1.8)
        elif normalized in {"순위", "월"}:
            weights.append(0.75)
        else:
            weights.append(1.25)
    total = sum(weights) or 1
    return [max(0.62, weight / total * 10.9) for weight in weights]

def structured_table_cell(column: object, value: object) -> str:
    """Format numeric and empty cells for detail PPT/HTML tables."""
    if value in {None, "", "None", "nan"}:
        return "-"
    normalized = normalized_table_column(column)
    numeric = numeric_value(value)
    if normalized in {"매출액", "amount", "sales", "revenue"} and numeric:
        return f"€{numeric:,.2f}"
    if normalized in {"판매수량", "수량", "qty", "quantity", "sku수", "국가수"} and numeric:
        return f"{numeric:,.0f}"
    return table_cell(value)



def build_kpi_metrics(blocks: list[ReportBlockPayload]) -> list[tuple[str, str, str]]:
    # Prefer explicit KPI summary blocks; otherwise derive a compact cover summary.
    summary_blocks = [block for block in blocks if (block.section or "") == "summary"]
    summary_pairs = summary_metric_pairs(summary_blocks)
    if summary_pairs:
        return [(label, value, "담긴 핵심 지표 블록 기준") for label, value in summary_pairs[:4]]
    total_sales = max((block_sales_value(block) for block in blocks), default=0)
    countries = unique_values_for_tokens(blocks, ("국가", "country"))
    brands = unique_values_for_tokens(blocks, ("브랜드", "brand"))
    data_rows = sum(len(snapshot_preview_rows(block)) for block in blocks)
    return [
        ("전체 매출", format_large_amount(total_sales), "담긴 블록 기준 최대 매출"),
        ("매출 발생 국가", f"{len(countries)}개국" if countries else "-", "snapshot 국가 필드 기준"),
        ("브랜드 수", f"{len(brands)}개" if brands else "-", "마스킹 후 표시 기준"),
        ("데이터 행", f"{data_rows}행", "PPT/XLSX 반영 rows"),
    ]

def unique_values_for_tokens(blocks: list[ReportBlockPayload], tokens: tuple[str, ...]) -> set[str]:
    values: set[str] = set()
    for block in blocks:
        for row in snapshot_preview_rows(block):
            for key, value in row.items():
                key_text = str(key)
                if any(token.lower() in key_text.lower() for token in tokens) and value not in {None, "", "-"}:
                    values.add(str(value))
    return values


def block_to_rows(block: ReportBlockPayload) -> list[tuple[str, str]]:
    params = block.params or {}
    rows = [
        ("유형", block_type_label(block.type or "summary")),
        ("출처", block.meta or "-"),
    ]
    for key, value in list(params.items())[:2]:
        rows.append((param_label(str(key)), stringify_report_value(value)))
    if block.snapshot:
        rows.append(("데이터", "미리보기 포함"))
    return rows

def render_block_insight(block: ReportBlockPayload, audience: str) -> str:
    parts = [block.title, block.subtitle]
    params = block.params or {}
    if params.get("scope") == "all":
        parts.append("선택한 섹션의 전체 항목을 하나의 보고서 블록으로 요약합니다.")
    elif params:
        parts.append(" / ".join(f"{param_label(str(key))}: {stringify_report_value(value)}" for key, value in list(params.items())[:2]))
    if audience != "internal":
        parts.append("민감 정보 마스킹 기준 적용")
    return "\n".join(clamp_text(part, 150) for part in parts if part)


def block_type_label(value: str) -> str:
    labels = {
        "season_calendar": "시즌 캘린더",
        "region_share": "권역 비중",
        "country_rank": "국가 순위",
        "country_detail": "국가 판매 상세",
        "country_growth": "국가 성장 변화",
        "country_sku_season": "국가 상위 SKU·시즌성",
        "brand_rank": "브랜드 순위",
        "brand_growth": "브랜드 성장 변화",
        "brand_overview": "브랜드 개요",
        "brand_sku_concentration": "SKU 집중도",
        "brand_country_distribution": "브랜드 국가 분포",
        "brand_line_composition": "제품군·라인 구성비",
        "brand_comparison": "브랜드 월별 추이 비교",
        "brand_top_sku_seasonality": "브랜드 상위 SKU 시즌성",
        "sku_detail": "SKU 상세",
        "cross_matrix": "교차 분석",
        "summary": "요약",
    }
    return labels.get(value, value)

def param_label(value: str) -> str:
    labels = {
        "scope": "범위",
        "countryCount": "국가 수",
        "totalAmount": "총 매출",
        "country": "국가",
        "region": "권역",
        "brand": "브랜드",
        "sku": "SKU",
        "rank": "순위",
        "metric": "기준",
        "share": "점유율",
        "yoy": "YoY",
        "mom": "MoM",
    }
    return labels.get(value, value)




__all__ = [
    "block_to_rows",
    "block_type_label",
    "brand_label_from_title",
    "brand_section_rows",
    "build_kpi_metrics",
    "column_widths",
    "country_detail_display_amount",
    "country_detail_display_krw",
    "country_detail_groups",
    "country_detail_item_label",
    "display_table_header",
    "group_blocks_by_section",
    "is_numeric_display",
    "meaningful_structured_columns",
    "normalize_structured_snapshot_rows",
    "normalized_table_column",
    "paginate_table_columns",
    "param_label",
    "percent_metric_numeric_value",
    "render_block_insight",
    "report_card_all_rows",
    "report_card_row_label",
    "report_card_row_subtext",
    "report_card_row_tag",
    "report_card_row_value_and_ratio",
    "report_card_rows",
    "report_card_slide_title",
    "report_card_title",
    "report_snapshot_rows_and_columns",
    "row_brand_labels",
    "row_card_has_percent_metric",
    "row_card_percent_sort_value",
    "row_card_sort_value",
    "section_rows",
    "selected_brand_labels",
    "selected_brand_row",
    "semantic_structured_group_columns",
    "structured_block_page_specs",
    "structured_identity_columns",
    "structured_row_groups",
    "structured_table_alignment",
    "structured_table_cell",
    "summary_metric_pairs",
    "table_columns",
    "unique_rows_by_label",
    "unique_values_for_tokens",
]
