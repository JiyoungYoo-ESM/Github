"""보고서 데이터 정규화 + 익명화(마스킹) 계층.

report_template_export 분해(IMPROVEMENT_PLAN.md 2단계). 블록 정규화/추론/정렬,
수신 대상별 마스킹(경쟁사 익명화·기밀 필드 제거·자사 식별), 스냅샷 행 미리보기를
담는다. 렌더러/계산 계층보다 아래(base)에 위치해 formatting·models에만 의존한다.
masking⇄normalize 상호 의존을 한 모듈로 병치해 순환을 없앤다. snapshot_preview_rows/
legacy_region_rows_from_block_metadata는 마스킹이 호출하므로 여기(base)에 둔다."""

from __future__ import annotations

import re
from typing import Any

from backend.services.reports.formatting import (
    first_amount_display_from_text,
    first_krw_display_from_text,
    is_self_brand,
    is_truthy,
    normalize_key,
    numeric_value,
    row_sales_value,
    stringify_report_value,
)
from backend.services.reports.models import (
    BRAND_FIELD_TOKENS,
    CLIENT_FIELD_TOKENS,
    CONFIDENTIAL_FIELD_TOKENS,
    MaskingSummary,
    REPORT_BLOCK_KINDS,
    REPORT_BLOCK_SECTIONS,
    REPORT_BLOCK_SIZES,
    ReportBlockPayload,
    SECTION_ORDER,
    TECHNICAL_SNAPSHOT_FIELDS,
    normalize_audience,
)

def normalize_report_block(block: ReportBlockPayload) -> ReportBlockPayload:
    kind = block.kind if block.kind in REPORT_BLOCK_KINDS else infer_block_kind(block)
    section = block.section if block.section in REPORT_BLOCK_SECTIONS else infer_block_section(block)
    size = block.size if block.size in REPORT_BLOCK_SIZES else "full"
    return ReportBlockPayload(
        id=block.id,
        title=block.title,
        subtitle=block.subtitle,
        meta=block.meta,
        type=block.type or infer_block_type(kind),
        kind=kind,
        section=section,
        size=size,
        params=dict(block.params or {}),
        snapshot=normalize_snapshot(block.snapshot),
        html_snapshot=block.html_snapshot,
    )


def normalize_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {"columns": [], "rows": []}
    raw_rows = snapshot.get("rows")
    rows = [dict(row) for row in raw_rows if isinstance(row, dict)] if isinstance(raw_rows, list) else []
    raw_columns = snapshot.get("columns")
    if isinstance(raw_columns, list):
        columns = [str(column) for column in raw_columns if str(column).strip()]
    elif rows:
        columns = [str(key) for key in rows[0].keys()]
    else:
        columns = []
    return {"columns": columns, "rows": rows}


def infer_block_kind(block: ReportBlockPayload) -> str:
    value = f"{block.kind} {block.type} {block.id}".lower()
    if "kpi" in value:
        return "kpi"
    if "share" in value or "region" in value:
        return "share"
    if "sku" in value or "trend" in value:
        return "trend"
    if "cross" in value or "matrix" in value:
        return "matrix"
    return "ranking"


def infer_block_section(block: ReportBlockPayload) -> str:
    value = f"{block.section} {block.type} {block.id} {block.title}".lower()
    if "season" in value or "시즌" in value:
        return "season"
    if "ingredient" in value or "성분" in value:
        return "ingredient"
    if "region" in value or "country" in value or "국가" in value or "권역" in value:
        return "region"
    if "brand" in value or "브랜드" in value:
        return "brand"
    if "sku" in value:
        return "sku"
    if "cross" in value or "matrix" in value or "교차" in value:
        return "cross"
    if "kpi" in value or "summary" in value or "요약" in value:
        return "summary"
    return "summary"


def infer_block_type(kind: str) -> str:
    return {
        "kpi": "summary",
        "share": "region_share",
        "ranking": "ranking",
        "trend": "sku_detail",
        "matrix": "cross_matrix",
    }.get(kind, "summary")


def arrange_report_blocks(blocks: list[ReportBlockPayload]) -> list[ReportBlockPayload]:
    return [sort_block_snapshot_rows(block) for block in blocks]


def sort_block_snapshot_rows(block: ReportBlockPayload) -> ReportBlockPayload:
    if block.kind not in {"ranking", "share", "matrix"}:
        return block
    snapshot = normalize_snapshot(block.snapshot)
    rows = list(snapshot.get("rows") or [])
    if not rows or max((row_sales_value(row) for row in rows), default=0) <= 0:
        return block
    snapshot["rows"] = sorted(rows, key=row_sales_value, reverse=True)
    return replace_report_block(block, snapshot=snapshot)


def section_index(section: str) -> int:
    try:
        return SECTION_ORDER.index(section)
    except ValueError:
        return len(SECTION_ORDER)


def mask_blocks(blocks: list[ReportBlockPayload], audience: str) -> tuple[list[ReportBlockPayload], MaskingSummary]:
    audience = normalize_audience(audience)
    alias_map = {} if audience == "internal" else build_competitor_alias_map(blocks)
    removed_columns: set[str] = set()
    masked_blocks = [
        mask_report_block(block, audience=audience, alias_map=alias_map, removed_columns=removed_columns)
        for block in blocks
    ]
    summary = MaskingSummary(
        audience=audience,
        removed_columns=tuple(sorted(removed_columns)),
        anonymized_competitor_count=len(set(alias_map.values())),
        competitor_aliases=alias_map,
        client_identity_policy=client_identity_policy(audience),
    )
    return masked_blocks, summary


def build_competitor_alias_map(blocks: list[ReportBlockPayload]) -> dict[str, str]:
    groups: list[dict[str, Any]] = []
    for block in blocks:
        for row in snapshot_preview_rows(block):
            names: set[str] = set()
            for key, value in row.items():
                if str(key) in TECHNICAL_SNAPSHOT_FIELDS:
                    continue
                if not is_brand_key(key) or not isinstance(value, str):
                    continue
                if is_self_brand(value, row):
                    continue
                normalized = value.strip()
                if not normalized or normalized in {"-", "미상"}:
                    continue
                names.add(normalized)
            if names:
                merge_competitor_group(groups, names, row_sales_value(row))

    sorted_groups = sorted(groups, key=lambda group: (-float(group["sales"]), sorted(group["names"])[0].lower()))
    aliases: dict[str, str] = {}
    for index, group in enumerate(sorted_groups):
        alias = competitor_alias(index)
        for name in group["names"]:
            aliases[str(name)] = alias
    return aliases


def merge_competitor_group(groups: list[dict[str, Any]], names: set[str], sales: float) -> None:
    matched = [group for group in groups if group["names"] & names]
    if not matched:
        groups.append({"names": set(names), "sales": sales})
        return
    base = matched[0]
    base["names"].update(names)
    base["sales"] = max(float(base["sales"]), sales)
    for extra in matched[1:]:
        base["names"].update(extra["names"])
        base["sales"] = max(float(base["sales"]), float(extra["sales"]))
        groups.remove(extra)


def competitor_alias(index: int) -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if index < len(letters):
        return f"경쟁사 {letters[index]}"
    first = letters[(index // len(letters)) - 1]
    second = letters[index % len(letters)]
    return f"경쟁사 {first}{second}"

def mask_report_block(
    block: ReportBlockPayload,
    *,
    audience: str,
    alias_map: dict[str, str],
    removed_columns: set[str],
) -> ReportBlockPayload:
    params = mask_mapping(block.params or {}, audience=audience, alias_map=alias_map, removed_columns=removed_columns)
    snapshot = mask_snapshot(block.snapshot, audience=audience, alias_map=alias_map, removed_columns=removed_columns)
    return ReportBlockPayload(
        id=block.id,
        title=mask_text(block.title, alias_map),
        subtitle=mask_text(block.subtitle, alias_map),
        meta=mask_text(block.meta, alias_map),
        type=block.type,
        kind=block.kind,
        section=block.section,
        size=block.size,
        params=params,
        snapshot=snapshot,
        html_snapshot=block.html_snapshot,
    )


def mask_snapshot(
    snapshot: dict[str, Any] | None,
    *,
    audience: str,
    alias_map: dict[str, str],
    removed_columns: set[str],
) -> dict[str, Any]:
    normalized = normalize_snapshot(snapshot)
    columns = [
        column
        for column in normalized.get("columns", [])
        if not should_hide_field(column, audience) and column not in TECHNICAL_SNAPSHOT_FIELDS
    ]
    for column in normalized.get("columns", []):
        if should_hide_field(column, audience):
            removed_columns.add(column)
    rows = [
        mask_mapping(row, audience=audience, alias_map=alias_map, removed_columns=removed_columns, visible_columns=columns)
        for row in normalized.get("rows", [])
    ]
    return {"columns": columns, "rows": rows}


def mask_mapping(
    mapping: dict[str, Any],
    *,
    audience: str,
    alias_map: dict[str, str],
    removed_columns: set[str],
    visible_columns: list[str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    source_is_self = is_truthy(mapping.get("is_self")) or str(mapping.get("brand_role") or "").lower() == "self"
    for key, value in mapping.items():
        key_text = str(key)
        if should_hide_field(key_text, audience):
            removed_columns.add(key_text)
            continue
        if key_text in TECHNICAL_SNAPSHOT_FIELDS:
            continue
        if visible_columns is not None and visible_columns and key_text not in visible_columns and not is_display_helper_key(key_text):
            result[key_text] = mask_value(key_text, value, audience=audience, alias_map=alias_map, source_is_self=source_is_self)
            continue
        result[key_text] = mask_value(key_text, value, audience=audience, alias_map=alias_map, source_is_self=source_is_self)
    return result


def mask_value(
    key: str,
    value: Any,
    *,
    audience: str,
    alias_map: dict[str, str],
    source_is_self: bool,
) -> Any:
    if isinstance(value, dict):
        return mask_mapping(value, audience=audience, alias_map=alias_map, removed_columns=set())
    if isinstance(value, list):
        return [mask_value(key, item, audience=audience, alias_map=alias_map, source_is_self=source_is_self) for item in value]
    if audience == "internal":
        return value
    if is_client_key(key):
        return "수신처 본인" if audience == "partner" else "집계"
    if is_brand_key(key) and isinstance(value, str) and not source_is_self:
        return alias_map.get(value.strip(), value)
    if isinstance(value, str):
        return mask_text(value, alias_map)
    return value


def mask_text(text: str, alias_map: dict[str, str]) -> str:
    masked = str(text or "")
    for original, alias in sorted(alias_map.items(), key=lambda item: len(item[0]), reverse=True):
        masked = masked.replace(original, alias)
    return masked


def should_hide_field(key: str, audience: str) -> bool:
    return audience != "internal" and is_confidential_key(key)


def is_confidential_key(key: str) -> bool:
    normalized = normalize_key(key)
    return any(token in normalized for token in CONFIDENTIAL_FIELD_TOKENS)


def is_client_key(key: str) -> bool:
    normalized = normalize_key(key)
    return any(token in normalized for token in CLIENT_FIELD_TOKENS)


def is_brand_key(key: str) -> bool:
    normalized = normalize_key(key)
    return any(token in normalized for token in BRAND_FIELD_TOKENS)


def is_display_helper_key(key: str) -> bool:
    normalized = normalize_key(key)
    return normalized in {"매출표시", "원화표시", "표시값", "amountdisplay", "salesdisplay", "krwdisplay"}


def client_identity_policy(audience: str) -> str:
    if audience == "internal":
        return "실명 유지"
    if audience == "partner":
        return "수신처 본인 외 거래처·고객명 익명화"
    return "거래처·고객명 집계 대체"


def block_sales_value(block: ReportBlockPayload) -> float:
    rows = snapshot_preview_rows(block)
    if rows:
        return max((row_sales_value(row) for row in rows), default=0)
    params = block.params or {}
    return max((numeric_value(value) for value in params.values()), default=0)


def replace_report_block(block: ReportBlockPayload, **changes: Any) -> ReportBlockPayload:
    values = {
        "id": block.id,
        "title": block.title,
        "subtitle": block.subtitle,
        "meta": block.meta,
        "type": block.type,
        "kind": block.kind,
        "section": block.section,
        "size": block.size,
        "params": block.params,
        "snapshot": block.snapshot,
    }
    values.update(changes)
    return ReportBlockPayload(**values)

def snapshot_preview_rows(block: ReportBlockPayload) -> list[dict[str, object]]:
    snapshot = block.snapshot or {}
    rows = snapshot.get("rows")
    if isinstance(rows, list):
        normalized_rows = [row for row in rows if isinstance(row, dict)]
        if normalized_rows:
            return normalized_rows
    return legacy_region_rows_from_block_metadata(block)


def legacy_region_rows_from_block_metadata(block: ReportBlockPayload) -> list[dict[str, object]]:
    if infer_block_section(block) != "region":
        return []

    text = " · ".join(part for part in (block.title, block.subtitle, block.meta) if part)
    params = block.params or {}
    row: dict[str, object] = {}
    if block.id.startswith("region:"):
        region = stringify_report_value(params.get("region") or block.id.split(":", 1)[1] or block.title).strip()
        row["권역"] = region.replace(" 권역 매출 비중", "").strip() or region
    else:
        country = stringify_report_value(params.get("country") or block.title).strip()
        row["국가"] = country.replace(" 판매 순위", "").strip() or country
        region = stringify_report_value(params.get("region") or "").strip()
        if not region and block.subtitle:
            first_part = str(block.subtitle).split("·", 1)[0].strip()
            if first_part and "점유율" not in first_part:
                region = first_part
        if region:
            row["권역"] = region

    amount_display = first_amount_display_from_text(text)
    if amount_display:
        row["매출표시"] = amount_display
        row["매출액"] = numeric_value(amount_display)
    krw_display = first_krw_display_from_text(text)
    if krw_display:
        row["원화표시"] = krw_display
    share_match = re.search(r"(?:점유율\s*)?([+-]?\d+(?:\.\d+)?%)", text)
    if share_match:
        row["점유율"] = share_match.group(1)

    return [row] if row else []




__all__ = [
    "normalize_report_block",
    "normalize_snapshot",
    "infer_block_kind",
    "infer_block_section",
    "infer_block_type",
    "arrange_report_blocks",
    "sort_block_snapshot_rows",
    "section_index",
    "mask_blocks",
    "build_competitor_alias_map",
    "merge_competitor_group",
    "competitor_alias",
    "mask_report_block",
    "mask_snapshot",
    "mask_mapping",
    "mask_value",
    "mask_text",
    "should_hide_field",
    "is_confidential_key",
    "is_client_key",
    "is_brand_key",
    "is_display_helper_key",
    "client_identity_policy",
    "block_sales_value",
    "replace_report_block",
    "snapshot_preview_rows",
    "legacy_region_rows_from_block_metadata",
]
