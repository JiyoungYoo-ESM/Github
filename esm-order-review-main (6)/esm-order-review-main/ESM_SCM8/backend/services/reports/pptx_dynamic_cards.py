"""Dynamic report-card renderers for generated PPTX decks."""

from __future__ import annotations

from backend.services.reports.models import *  # noqa: F401,F403
from backend.services.reports.formatting import *  # noqa: F401,F403
from backend.services.reports.report_data import *  # noqa: F401,F403
from backend.services.reports.compute_cross import *  # noqa: F401,F403
from backend.services.reports.compute_snapshot import *  # noqa: F401,F403
from backend.services.reports.compute_series import *  # noqa: F401,F403
from backend.services.reports.report_chrome import *  # noqa: F401,F403
from backend.services.reports.pptx_prims import *  # noqa: F401,F403

def should_paginate_ranking_card(block: ReportBlockPayload, rows: list[dict[str, object]]) -> bool:
    if len(rows) <= 5:
        return False
    block_type = str(block.type or "").strip().lower()
    if block_type in {"season_calendar", "country_detail", "country_growth", "brand_growth", "cross_matrix", "sku_detail"}:
        return False
    if str(block.kind or "").strip().lower() == "ranking":
        return True
    text = f"{block.id} {block.title} {block.subtitle} {block.meta}".lower()
    return any(token in text for token in ("순위", "ranking", "국가", "country", "브랜드", "brand", "sku"))






def add_report_card_growth_split(
    slide,
    *,
    rows: list[dict[str, object]],
    block_type: str,
    card_left,
    card_top,
    card_width,
    Inches,
    RGBColor,
    MSO_SHAPE,
    PP_ALIGN,
    Pt,
) -> None:
    rising, declining = report_card_growth_groups(rows, block_type)
    groups = [
        ("성장 상위", "금액 증가순", "상승", rising, RGBColor(0, 166, 83), RGBColor(229, 249, 237)),
        ("감소 상위", "금액 감소순", "하락", declining, RGBColor(233, 0, 53), RGBColor(255, 238, 243)),
    ]
    groups = [
        ("성장 상위", "금액 증가순", "상승", rising, RGBColor(0, 166, 83), RGBColor(229, 249, 237)),
        ("감소 상위", "금액 감소순", "하락", declining, RGBColor(233, 0, 53), RGBColor(255, 238, 243)),
    ]
    panel_gap = Inches(0.24)
    panel_width = int((card_width - Inches(0.68) - panel_gap) / 2)
    panel_top = card_top + Inches(1.02)
    panel_height = Inches(3.10)
    for group_index, (title, subtitle, badge, group_rows, accent, badge_fill) in enumerate(groups):
        left = card_left + Inches(0.34) + group_index * (panel_width + panel_gap)
        if group_index == 1:
            divider = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left - int(panel_gap / 2), panel_top, Inches(0.01), panel_height)
            divider.fill.solid()
            divider.fill.fore_color.rgb = RGBColor(226, 228, 232)
            divider.line.fill.background()
        add_brand_chart_text(
            slide,
            left,
            panel_top,
            panel_width - Inches(0.76),
            Inches(0.22),
            title,
            9.0,
            RGBColor(5, 6, 10),
            bold=True,
            Pt=Pt,
            PP_ALIGN=PP_ALIGN,
        )
        add_brand_chart_text(
            slide,
            left + Inches(0.64),
            panel_top + Inches(0.015),
            Inches(1.12),
            Inches(0.16),
            f"· {subtitle}",
            7.2,
            RGBColor(143, 149, 161),
            bold=True,
            Pt=Pt,
            PP_ALIGN=PP_ALIGN,
        )
        subtitle_cover = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left + Inches(0.58), panel_top - Inches(0.01), Inches(1.34), Inches(0.24))
        subtitle_cover.name = "Silicon2 Growth Subtitle Cover"
        subtitle_cover.fill.solid()
        subtitle_cover.fill.fore_color.rgb = RGBColor(255, 255, 255)
        subtitle_cover.line.fill.background()
        add_brand_chart_text(
            slide,
            left + Inches(0.64),
            panel_top + Inches(0.015),
            Inches(1.12),
            Inches(0.16),
            subtitle,
            7.2,
            RGBColor(143, 149, 161),
            bold=True,
            Pt=Pt,
            PP_ALIGN=PP_ALIGN,
        )
        badge_shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left + panel_width - Inches(0.54), panel_top - Inches(0.02), Inches(0.46), Inches(0.23))
        badge_shape.fill.solid()
        badge_shape.fill.fore_color.rgb = badge_fill
        badge_shape.line.fill.background()
        add_brand_chart_text(
            slide,
            left + panel_width - Inches(0.49),
            panel_top + Inches(0.025),
            Inches(0.36),
            Inches(0.12),
            badge,
            6.5,
            accent,
            bold=True,
            align=PP_ALIGN.CENTER,
            Pt=Pt,
            PP_ALIGN=PP_ALIGN,
        )
        if not group_rows:
            add_brand_chart_text(
                slide,
                left,
                panel_top + Inches(1.14),
                panel_width,
                Inches(0.24),
                "표시할 국가가 없습니다.",
                8.5,
                RGBColor(143, 149, 161),
                bold=True,
                align=PP_ALIGN.CENTER,
                Pt=Pt,
                PP_ALIGN=PP_ALIGN,
            )
            continue
        for index, row in enumerate(group_rows[:5]):
            y = panel_top + Inches(0.42 + index * 0.50)
            if index > 0:
                rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, y - Inches(0.06), panel_width, Inches(0.006))
                rule.fill.solid()
                rule.fill.fore_color.rgb = RGBColor(237, 240, 243)
                rule.line.fill.background()
            add_brand_chart_text(slide, left, y + Inches(0.06), Inches(0.20), Inches(0.16), str(index + 1), 7.6, RGBColor(154, 161, 173), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
            add_brand_chart_text(slide, left + Inches(0.34), y, panel_width - Inches(1.72), Inches(0.18), clamp_text(row["country"], 26), 8.3, RGBColor(5, 6, 10), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
            add_brand_chart_text(slide, left + Inches(0.34), y + Inches(0.20), panel_width - Inches(1.72), Inches(0.15), row["sub"], 6.7, RGBColor(143, 149, 161), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
            growth_text = "판매 소멸" if row.get("vanished") else row["growth"]
            add_brand_chart_text(slide, left + panel_width - Inches(1.28), y, Inches(1.20), Inches(0.18), growth_text, 8.5, accent, bold=True, align=PP_ALIGN.RIGHT, Pt=Pt, PP_ALIGN=PP_ALIGN)
            if row["amount_flow"]:
                add_brand_chart_text(slide, left + panel_width - Inches(1.72), y + Inches(0.20), Inches(1.64), Inches(0.15), row["amount_flow"], 6.5, RGBColor(154, 161, 173), bold=True, align=PP_ALIGN.RIGHT, Pt=Pt, PP_ALIGN=PP_ALIGN)






def add_report_card_country_detail(
    slide,
    *,
    rows: list[dict[str, object]],
    block: ReportBlockPayload,
    card_left,
    card_top,
    card_width,
    Inches,
    RGBColor,
    MSO_SHAPE,
    PP_ALIGN,
    Pt,
) -> None:
    groups = country_detail_groups(rows)
    summary = (groups.get("국가 요약") or [{}])[0]
    peak = (groups.get("월 최고 매출") or [{}])[0]
    brand_rows = groups.get("상위 브랜드", [])[:5]
    category_rows = groups.get("Top 5 카테고리", [])[:5]
    country = country_detail_item_label(summary) or stringify_report_value((block.params or {}).get("country", "-"))
    summary_amount = country_detail_display_amount(summary)
    summary_krw = country_detail_display_krw(summary)
    share = clean_metric_display(first_value(summary, ("비고", "점유율"), ""))
    peak_label = country_detail_item_label(peak)
    peak_amount = country_detail_display_amount(peak)
    peak_krw = country_detail_display_krw(peak)

    left = card_left + Inches(0.34)
    top = card_top + Inches(0.98)
    summary_gap = Inches(0.16)
    tile_w = int((card_width - Inches(0.68) - summary_gap * 2) / 3)
    tile_h = Inches(0.72)
    tiles = [
        ("선택 국가", country, share),
        ("총 매출", summary_amount, summary_krw),
        ("월 최고 매출", peak_amount, " · ".join(part for part in (peak_label, peak_krw) if part and part != "-")),
    ]
    for index, (label, value, sub) in enumerate(tiles):
        x = left + (tile_w + summary_gap) * index
        tile = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, top, tile_w, tile_h)
        tile.name = "Silicon2 Country Detail Summary Tile"
        tile.fill.solid()
        tile.fill.fore_color.rgb = RGBColor(248, 250, 252)
        tile.line.color.rgb = RGBColor(226, 228, 232)
        add_brand_chart_text(slide, x + Inches(0.14), top + Inches(0.12), tile_w - Inches(0.28), Inches(0.14), label, 6.9, RGBColor(105, 112, 127), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
        add_brand_chart_text(slide, x + Inches(0.14), top + Inches(0.31), tile_w - Inches(0.28), Inches(0.20), value or "-", 10.2, RGBColor(5, 6, 10), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
        if sub and sub != "-":
            add_brand_chart_text(slide, x + Inches(0.14), top + Inches(0.53), tile_w - Inches(0.28), Inches(0.12), clamp_text(sub, 32), 5.8, RGBColor(233, 0, 53) if "점유율" in sub else RGBColor(143, 149, 161), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)

    brand_top = card_top + Inches(1.74)
    add_brand_chart_text(slide, left, brand_top, Inches(3.0), Inches(0.18), "상위 브랜드 · 미리보기", 8.0, RGBColor(5, 6, 10), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
    max_brand = max((row_sales_value(row) for row in brand_rows), default=0) or 1
    bar_left = left
    bar_width = card_width - Inches(0.68)
    brand_step = 0.30 if len(brand_rows) >= 5 else 0.35
    for index, row in enumerate(brand_rows):
        y = brand_top + Inches(0.28 + index * brand_step)
        label = country_detail_item_label(row)
        amount = country_detail_display_amount(row)
        krw = country_detail_display_krw(row)
        add_brand_chart_text(slide, bar_left, y, bar_width - Inches(1.55), Inches(0.15), clamp_text(label, 44), 6.8, RGBColor(5, 6, 10), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
        add_brand_chart_text(slide, bar_left + bar_width - Inches(1.35), y, Inches(1.35), Inches(0.15), amount, 6.8, RGBColor(5, 6, 10), bold=True, align=PP_ALIGN.RIGHT, Pt=Pt, PP_ALIGN=PP_ALIGN)
        if krw and krw != "-":
            add_brand_chart_text(slide, bar_left + bar_width - Inches(1.35), y + Inches(0.14), Inches(1.35), Inches(0.12), krw, 5.4, RGBColor(143, 149, 161), bold=True, align=PP_ALIGN.RIGHT, Pt=Pt, PP_ALIGN=PP_ALIGN)
        track = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, bar_left, y + Inches(0.22), bar_width, Inches(0.045))
        track.name = "Silicon2 Country Detail Brand Track"
        track.fill.solid()
        track.fill.fore_color.rgb = RGBColor(242, 243, 245)
        track.line.fill.background()
        ratio = min(max(row_sales_value(row) / max_brand, 0.04), 1.0)
        bar = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, bar_left, y + Inches(0.22), int(bar_width * ratio), Inches(0.045))
        bar.name = "Silicon2 Country Detail Brand Bar"
        bar.fill.solid()
        bar.fill.fore_color.rgb = RGBColor(233, 0, 53)
        bar.line.fill.background()

    category_top = card_top + Inches(3.92)
    add_brand_chart_text(slide, left, category_top, Inches(3.0), Inches(0.17), "Top 5 카테고리", 8.0, RGBColor(5, 6, 10), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
    pill_x = left
    pill_y = category_top + Inches(0.18)
    for row in category_rows or [{"항목": "데이터 없음"}]:
        label = clamp_text(country_detail_item_label(row), 18)
        pill_w = Inches(max(0.72, min(1.62, 0.28 + len(label) * 0.075)))
        if pill_x + pill_w > left + card_width - Inches(0.68):
            pill_x = left
            pill_y += Inches(0.22)
        pill = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, pill_x, pill_y, pill_w, Inches(0.22))
        pill.name = "Silicon2 Country Detail Category Pill"
        pill.fill.solid()
        pill.fill.fore_color.rgb = RGBColor(248, 250, 252)
        pill.line.color.rgb = RGBColor(226, 228, 232)
        add_brand_chart_text(slide, pill_x + Inches(0.06), pill_y + Inches(0.035), pill_w - Inches(0.12), Inches(0.12), label, 5.8, RGBColor(38, 49, 68), bold=True, align=PP_ALIGN.CENTER, Pt=Pt, PP_ALIGN=PP_ALIGN)
        pill_x += pill_w + Inches(0.08)


def add_report_card_brand_overview(
    slide,
    *,
    rows: list[dict[str, object]],
    card_left,
    card_top,
    card_width,
    Inches,
    RGBColor,
    MSO_SHAPE,
    PP_ALIGN,
    Pt,
) -> None:
    row = rows[0] if rows else {}
    metrics = [
        ("매출", clean_metric_display(first_value(row, ("매출표시", "매출액"), ""))),
        ("원화 환산", clean_metric_display(row.get("원화표시", ""))),
        ("판매수량", format_integer_like(row.get("판매수량", ""))),
        ("SKU", f"{format_integer_like(row.get('SKU수', ''))}개" if clean_metric_display(row.get("SKU수", "")) != "-" else "-"),
        ("판매 국가", f"{format_integer_like(row.get('국가수', ''))}개국" if clean_metric_display(row.get("국가수", "")) != "-" else "-"),
        ("점유율", clean_metric_display(row.get("점유율", ""))),
    ]
    tile_left = card_left + Inches(0.34)
    tile_top = card_top + Inches(1.08)
    tile_gap = Inches(0.18)
    tile_w = int((card_width - Inches(0.68) - tile_gap * 2) / 3)
    tile_h = Inches(0.92)
    for index, (label, value) in enumerate(metrics):
        x = tile_left + (tile_w + tile_gap) * (index % 3)
        y = tile_top + Inches(1.10) * (index // 3)
        tile = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, tile_w, tile_h)
        tile.fill.solid()
        tile.fill.fore_color.rgb = RGBColor(248, 250, 252)
        tile.line.color.rgb = RGBColor(226, 228, 232)
        add_brand_chart_text(slide, x + Inches(0.16), y + Inches(0.16), tile_w - Inches(0.32), Inches(0.16), label, 7.4, RGBColor(105, 112, 127), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
        add_brand_chart_text(slide, x + Inches(0.16), y + Inches(0.43), tile_w - Inches(0.32), Inches(0.24), value, 12.0, RGBColor(5, 6, 10), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)


def add_report_card_sku_order_reference(
    slide,
    *,
    rows: list[dict[str, object]],
    block: ReportBlockPayload,
    card_left,
    card_top,
    card_width,
    Inches,
    RGBColor,
    MSO_SHAPE,
    PP_ALIGN,
    Pt,
) -> None:
    items: list[tuple[str, str, str, str]] = []
    for row in rows:
        label = clean_metric_display(first_value(row, ("항목", "label"), ""))
        value = clean_metric_display(first_value(row, ("값", "value"), ""))
        sub = clean_metric_display(first_value(row, ("보조값", "subValue", "원화표시"), ""))
        note = clean_metric_display(first_value(row, ("비고", "note"), ""))
        if label and label != "-":
            items.append((label, value, sub if sub != "-" else "", note if note != "-" else ""))

    if not items:
        columns = list(rows[0].keys()) if rows else []
        items = [(row["label"], row["value"], "", "") for row in report_card_rows(block, columns, rows)[:6]]

    tile_left = card_left + Inches(0.34)
    tile_top = card_top + Inches(1.02)
    tile_gap_x = Inches(0.22)
    tile_gap_y = Inches(0.20)
    tile_w = int((card_width - Inches(0.68) - tile_gap_x) / 2)
    tile_h = Inches(0.78)
    for index, (label, value, sub, note) in enumerate(items[:6]):
        x = tile_left + (tile_w + tile_gap_x) * (index % 2)
        y = tile_top + (tile_h + tile_gap_y) * (index // 2)
        tile = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, tile_w, tile_h)
        tile.name = "Silicon2 SKU Order Reference Tile"
        tile.fill.solid()
        tile.fill.fore_color.rgb = RGBColor(248, 250, 252)
        tile.line.color.rgb = RGBColor(226, 228, 232)
        value_color = RGBColor(233, 0, 53) if "준비월" in label or "피크" in label else RGBColor(5, 6, 10)
        add_brand_chart_text(slide, x + Inches(0.16), y + Inches(0.13), tile_w - Inches(0.32), Inches(0.16), label, 7.4, RGBColor(105, 112, 127), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
        add_brand_chart_text(slide, x + Inches(0.16), y + Inches(0.34), tile_w - Inches(0.32), Inches(0.22), value, 11.0, value_color, bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
        helper = sub or note
        if helper:
            add_brand_chart_text(slide, x + Inches(0.16), y + Inches(0.57), tile_w - Inches(0.32), Inches(0.13), clamp_text(helper, 46), 6.2, RGBColor(143, 149, 161), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)

    prep_row = next((item for item in items if "준비월" in item[0] or "준비" in item[0]), None)
    peak_month = stringify_report_value((block.params or {}).get("peakMonth", "")).strip()
    warning = ""
    if prep_row and prep_row[1] and prep_row[1] != "-":
        warning = f"{peak_month}월 피크 기준 약 3개월 전인 {prep_row[1]}부터 판매/발주 준비가 필요합니다." if peak_month else f"{prep_row[1]}부터 판매/발주 준비가 필요합니다."
    elif prep_row and prep_row[3]:
        warning = prep_row[3]
    if warning:
        box_top = card_top + Inches(3.98)
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, tile_left, box_top, card_width - Inches(0.68), Inches(0.38))
        box.name = "Silicon2 SKU Order Reference Notice"
        box.fill.solid()
        box.fill.fore_color.rgb = RGBColor(255, 247, 237)
        box.line.color.rgb = RGBColor(253, 186, 116)
        add_brand_chart_text(slide, tile_left + Inches(0.18), box_top + Inches(0.10), card_width - Inches(1.04), Inches(0.16), warning, 7.2, RGBColor(233, 0, 53), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)


def add_report_card_season_calendar(
    slide,
    *,
    season_rows: list[dict[str, object]],
    card_left,
    card_top,
    card_width,
    Inches,
    RGBColor,
    MSO_SHAPE,
    PP_ALIGN,
    Pt,
) -> None:
    label_w = Inches(1.58)
    peak_w = Inches(0.58)
    gap = Inches(0.065)
    grid_left = card_left + Inches(0.34)
    grid_top = card_top + Inches(1.08)
    grid_width = card_width - Inches(0.68)
    cell_w = int((grid_width - label_w - peak_w - gap * 13) / 12)
    row_count = max(len(season_rows), 1)
    compact = row_count > 7
    cell_h = Inches(0.30 if not compact else 0.18)
    row_gap = Inches(0.16 if not compact else 0.045)
    label_font = 7.5 if not compact else 5.7
    value_font = 6.2 if not compact else 4.4
    peak_font = 7.0 if not compact else 5.2
    header_y = grid_top
    muted = RGBColor(143, 149, 161)

    add_brand_chart_text(
        slide,
        grid_left,
        header_y,
        label_w,
        Inches(0.18),
        "기능군",
        7.0,
        muted,
        bold=True,
        Pt=Pt,
        PP_ALIGN=PP_ALIGN,
    )

    for index in range(12):
        x = grid_left + label_w + gap + (cell_w + gap) * index
        add_brand_chart_text(
            slide,
            x,
            header_y,
            cell_w,
            Inches(0.18),
            f"{index + 1}월",
            6.6,
            muted,
            bold=True,
            align=PP_ALIGN.CENTER,
            Pt=Pt,
            PP_ALIGN=PP_ALIGN,
        )
    add_brand_chart_text(
        slide,
        grid_left + label_w + gap + (cell_w + gap) * 12,
        header_y,
        peak_w,
        Inches(0.18),
        "피크",
        6.6,
        muted,
        bold=True,
        align=PP_ALIGN.CENTER,
        Pt=Pt,
        PP_ALIGN=PP_ALIGN,
    )

    for row_index, row in enumerate(season_rows):
        y = grid_top + Inches(0.38) + (cell_h + row_gap) * row_index
        add_brand_chart_text(
            slide,
            grid_left,
            y + Inches(0.06),
            label_w - Inches(0.08),
            Inches(0.18),
            clamp_text(row["label"], 20),
            label_font,
            RGBColor(5, 6, 10),
            bold=True,
            Pt=Pt,
            PP_ALIGN=PP_ALIGN,
        )
        row_max_value = float(row.get("max_value", 0) or 0) or max(
            [
                float(cell.get("value", 0) or 0)
                for cell in row.get("values", [])
                if cell.get("has_value")
            ],
            default=0,
        )
        for cell_index, cell in enumerate(row.get("values", [])[:12]):
            x = grid_left + label_w + gap + (cell_w + gap) * cell_index
            value = float(cell.get("value", 0) or 0)
            has_value = bool(cell.get("has_value"))
            is_peak = int(row.get("peak_month") or 0) == int(cell.get("month") or 0)
            tile = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, cell_w, cell_h)
            tile.name = "Silicon2 Season Calendar Cell"
            tile.fill.solid()
            tile.fill.fore_color.rgb = season_calendar_cell_color(value, row_max_value, has_value, RGBColor)
            if is_peak:
                tile.line.color.rgb = RGBColor(5, 6, 10)
                tile.line.width = Pt(1.2)
            else:
                tile.line.fill.background()
            if has_value:
                text_color = RGBColor(255, 255, 255) if season_calendar_cell_is_dark(value, row_max_value) else RGBColor(5, 6, 10)
                add_brand_chart_text(
                    slide,
                    x,
                    y + Inches(0.075),
                    cell_w,
                    Inches(0.13),
                    format_season_calendar_value(value, row_max_value, is_peak=is_peak),
                    value_font,
                    text_color,
                    bold=True,
                    align=PP_ALIGN.CENTER,
                    Pt=Pt,
                    PP_ALIGN=PP_ALIGN,
                )
        add_brand_chart_text(
            slide,
            grid_left + label_w + gap + (cell_w + gap) * 12,
            y + Inches(0.06),
            peak_w,
            Inches(0.18),
            row.get("peak", "-"),
            peak_font,
            RGBColor(5, 6, 10),
            bold=True,
            align=PP_ALIGN.CENTER,
            Pt=Pt,
            PP_ALIGN=PP_ALIGN,
        )

    legend_top = card_top + Inches(4.02)
    add_brand_chart_text(
        slide,
        grid_left,
        legend_top,
        Inches(0.46),
        Inches(0.16),
        "낮음",
        6.5,
        muted,
        bold=True,
        Pt=Pt,
        PP_ALIGN=PP_ALIGN,
    )
    for index, color in enumerate(
        [
            RGBColor(255, 214, 224),
            RGBColor(255, 145, 166),
            RGBColor(246, 74, 113),
            RGBColor(233, 0, 53),
        ]
    ):
        chip = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            grid_left + Inches(0.50) + Inches(index * 0.18),
            legend_top + Inches(0.035),
            Inches(0.14),
            Inches(0.07),
        )
        chip.fill.solid()
        chip.fill.fore_color.rgb = color
        chip.line.fill.background()
    add_brand_chart_text(
        slide,
        grid_left + Inches(1.26),
        legend_top,
        Inches(0.46),
        Inches(0.16),
        "높음",
        6.5,
        muted,
        bold=True,
        Pt=Pt,
        PP_ALIGN=PP_ALIGN,
    )
    peak_sample = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        grid_left + Inches(1.86),
        legend_top + Inches(0.015),
        Inches(0.12),
        Inches(0.10),
    )
    peak_sample.fill.solid()
    peak_sample.fill.fore_color.rgb = RGBColor(233, 0, 53)
    peak_sample.line.color.rgb = RGBColor(5, 6, 10)
    peak_sample.line.width = Pt(1.0)
    add_brand_chart_text(
        slide,
        grid_left + Inches(2.04),
        legend_top,
        Inches(0.72),
        Inches(0.16),
        "피크월",
        6.5,
        muted,
        bold=True,
        Pt=Pt,
        PP_ALIGN=PP_ALIGN,
    )

    # 깨진 레거시 범례 라벨을 덮고 정상 한국어 범례를 다시 그린다.
    legend_cover = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        grid_left - Inches(0.02),
        legend_top - Inches(0.02),
        Inches(2.86),
        Inches(0.24),
    )
    legend_cover.name = "Silicon2 Season Legend Cover"
    legend_cover.fill.solid()
    legend_cover.fill.fore_color.rgb = RGBColor(255, 255, 255)
    legend_cover.line.fill.background()
    add_brand_chart_text(
        slide,
        grid_left,
        legend_top,
        Inches(0.46),
        Inches(0.16),
        "낮음",
        6.5,
        muted,
        bold=True,
        Pt=Pt,
        PP_ALIGN=PP_ALIGN,
    )
    for index, color in enumerate(
        [
            RGBColor(255, 214, 224),
            RGBColor(255, 145, 166),
            RGBColor(246, 74, 113),
            RGBColor(233, 0, 53),
        ]
    ):
        chip = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            grid_left + Inches(0.50) + Inches(index * 0.18),
            legend_top + Inches(0.035),
            Inches(0.14),
            Inches(0.07),
        )
        chip.fill.solid()
        chip.fill.fore_color.rgb = color
        chip.line.fill.background()
    add_brand_chart_text(
        slide,
        grid_left + Inches(1.26),
        legend_top,
        Inches(0.46),
        Inches(0.16),
        "높음",
        6.5,
        muted,
        bold=True,
        Pt=Pt,
        PP_ALIGN=PP_ALIGN,
    )
    peak_sample = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        grid_left + Inches(1.86),
        legend_top + Inches(0.015),
        Inches(0.12),
        Inches(0.10),
    )
    peak_sample.fill.solid()
    peak_sample.fill.fore_color.rgb = RGBColor(233, 0, 53)
    peak_sample.line.color.rgb = RGBColor(5, 6, 10)
    peak_sample.line.width = Pt(1.0)
    add_brand_chart_text(
        slide,
        grid_left + Inches(2.04),
        legend_top,
        Inches(0.72),
        Inches(0.16),
        "피크월",
        6.5,
        muted,
        bold=True,
        Pt=Pt,
        PP_ALIGN=PP_ALIGN,
    )


def add_season_calendar_detail_page(
    slide,
    *,
    block: ReportBlockPayload,
    columns: list[str],
    rows: list[dict[str, object]],
    Inches,
    RGBColor,
    MSO_SHAPE,
) -> None:
    try:
        from pptx.enum.text import PP_ALIGN
        from pptx.util import Pt
    except ImportError:
        return
    season_rows = report_card_season_calendar_rows(block, columns, rows, limit=None)
    if not season_rows:
        add_snapshot_table_page(
            slide,
            columns=columns,
            rows=rows,
            Inches=Inches,
            RGBColor=RGBColor,
            MSO_SHAPE=MSO_SHAPE,
        )
        return

    card_left = Inches(0.78)
    card_top = Inches(1.72)
    card_width = Inches(11.78)
    card_height = Inches(4.50)
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, card_left, card_top, card_width, card_height)
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(255, 255, 255)
    card.line.color.rgb = RGBColor(226, 228, 232)

    add_brand_chart_text(
        slide,
        card_left + Inches(0.34),
        card_top + Inches(0.24),
        card_width - Inches(0.68),
        Inches(0.24),
        "기능군 × 월별 피크 대비 비중",
        10.0,
        RGBColor(5, 6, 10),
        bold=True,
        Pt=Pt,
        PP_ALIGN=PP_ALIGN,
    )
    add_brand_chart_text(
        slide,
        card_left + Inches(0.34),
        card_top + Inches(0.54),
        card_width - Inches(0.68),
        Inches(0.20),
        "1월부터 12월까지 한 행에서 비교합니다. 숫자는 피크월 대비 비중이며, 검은 테두리는 피크월입니다.",
        7.5,
        RGBColor(105, 112, 127),
        bold=True,
        Pt=Pt,
        PP_ALIGN=PP_ALIGN,
    )
    add_report_card_season_calendar(
        slide,
        season_rows=season_rows,
        card_left=card_left,
        card_top=card_top + Inches(0.16),
        card_width=card_width,
        Inches=Inches,
        RGBColor=RGBColor,
        MSO_SHAPE=MSO_SHAPE,
        PP_ALIGN=PP_ALIGN,
        Pt=Pt,
    )


def add_report_card_trend_chart(
    slide,
    *,
    series: list[dict[str, object]],
    card_left,
    card_top,
    card_width,
    Inches,
    RGBColor,
    MSO_SHAPE,
    PP_ALIGN,
    Pt,
) -> None:
    from pptx.enum.shapes import MSO_CONNECTOR

    colors = [
        RGBColor(233, 0, 53),
        RGBColor(39, 76, 119),
        RGBColor(26, 127, 100),
        RGBColor(230, 126, 34),
        RGBColor(126, 87, 194),
        RGBColor(0, 137, 123),
    ]
    all_points = [point for item in series for point in item.get("points", [])]
    if not all_points:
        return
    labels = []
    for item in series:
        for point in item.get("points", []):
            if point["label"] not in labels:
                labels.append(point["label"])
    labels.sort(key=report_card_month_number)
    values = [max(0.0, float(point.get("value", 0))) for point in all_points]
    max_value = max(values, default=0) or 1
    axis_max = max_value * 1.16

    plot_left = card_left + Inches(0.62)
    plot_top = card_top + Inches(1.28)
    plot_width = card_width - Inches(1.02)
    plot_height = Inches(2.44)
    guide_color = RGBColor(226, 228, 232)
    muted = RGBColor(143, 149, 161)

    for guide_index in range(3):
        y = plot_top + int(plot_height * guide_index / 2)
        guide = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, plot_left, y, plot_width, Inches(0.008))
        guide.fill.solid()
        guide.fill.fore_color.rgb = guide_color
        guide.line.fill.background()
        guide_value = axis_max * (1 - guide_index / 2)
        add_brand_chart_text(
            slide,
            card_left + Inches(0.10),
            y - Inches(0.08),
            Inches(0.46),
            Inches(0.16),
            f"{guide_value:.0f}%",
            6.5,
            muted,
            bold=True,
            align=PP_ALIGN.RIGHT,
            Pt=Pt,
            PP_ALIGN=PP_ALIGN,
        )

    if len(series) > 1:
        legend_left = card_left + Inches(0.36)
        for index, item in enumerate(series):
            x = legend_left + Inches((index % 3) * 2.72)
            y = card_top + Inches(0.91 + (index // 3) * 0.22)
            dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y + Inches(0.035), Inches(0.08), Inches(0.08))
            dot.fill.solid()
            dot.fill.fore_color.rgb = colors[index % len(colors)]
            dot.line.fill.background()
            peak = max((float(point.get("value", 0)) for point in item.get("points", [])), default=0)
            legend_text = f"{clamp_text(item['name'], 18)} · 최고 {peak:.1f}%"
            add_brand_chart_text(slide, x + Inches(0.12), y, Inches(2.45), Inches(0.16), legend_text, 6.8, RGBColor(45, 51, 63), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)

    x_by_label = {
        label: plot_left + int(plot_width * index / max(len(labels) - 1, 1))
        for index, label in enumerate(labels)
    }
    for index, item in enumerate(series):
        color = colors[index % len(colors)]
        points = item.get("points", [])
        positioned = []
        for point in points:
            value = max(0.0, float(point.get("value", 0)))
            x = x_by_label[point["label"]]
            y = plot_top + int(plot_height * (1 - value / axis_max))
            positioned.append((x, y, value))
        for start, end in zip(positioned, positioned[1:]):
            connector = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, start[0], start[1], end[0], end[1])
            connector.line.color.rgb = color
            connector.line.width = Pt(1.8)
        peak_value = max((point[2] for point in positioned), default=0)
        for x, y, value in positioned:
            marker = slide.shapes.add_shape(MSO_SHAPE.OVAL, x - Inches(0.045), y - Inches(0.045), Inches(0.09), Inches(0.09))
            marker.fill.solid()
            marker.fill.fore_color.rgb = RGBColor(255, 255, 255) if value != peak_value else color
            marker.line.color.rgb = color
            marker.line.width = Pt(1.1)
            if len(series) == 1:
                add_brand_chart_text(slide, x - Inches(0.32), y - Inches(0.24), Inches(0.64), Inches(0.15), f"{value:.1f}%", 6.8, color, bold=True, align=PP_ALIGN.CENTER, Pt=Pt, PP_ALIGN=PP_ALIGN)

    for label in labels:
        x = x_by_label[label]
        add_brand_chart_text(slide, x - Inches(0.25), plot_top + plot_height + Inches(0.12), Inches(0.5), Inches(0.16), label, 6.5, muted, bold=True, align=PP_ALIGN.CENTER, Pt=Pt, PP_ALIGN=PP_ALIGN)

def add_snapshot_table_page(slide, *, columns: list[str], rows: list[dict[str, object]], Inches, RGBColor, MSO_SHAPE) -> None:
    try:
        from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
        from pptx.util import Pt
    except ImportError:
        return
    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.72), Inches(1.82), Inches(11.85), Inches(4.18))
    panel.fill.solid()
    panel.fill.fore_color.rgb = RGBColor(255, 255, 255)
    panel.line.color.rgb = RGBColor(226, 228, 232)
    if not rows or not columns:
        add_textbox(slide, Inches(1.02), Inches(3.5), Inches(9.5), Inches(0.35), "표시할 snapshot 데이터가 없습니다.", 13, RGBColor(105, 112, 127), bold=True)
        return

    widths = column_widths(columns)
    row_height = min(0.36, 3.60 / max(len(rows) + 1, 1))
    table_shape = slide.shapes.add_table(
        len(rows) + 1,
        len(columns),
        Inches(0.98),
        Inches(2.08),
        Inches(10.9),
        Inches(row_height * (len(rows) + 1)),
    )
    table_shape.name = "Silicon2 Data Slide Table"
    table = table_shape.table
    for index, width in enumerate(widths):
        table.columns[index].width = Inches(width)
    for row in table.rows:
        row.height = Inches(row_height)
    for column_index, column in enumerate(columns):
        apply_region_table_cell(
            table.cell(0, column_index),
            display_table_header(column),
            RGBColor(191, 24, 28),
            RGBColor(255, 255, 255),
            bold=True,
            align=PP_ALIGN.CENTER,
            font_size=8.1,
            MSO_ANCHOR=MSO_ANCHOR,
            Pt=Pt,
        )
    for row_index, row in enumerate(rows, start=1):
        fill_color = RGBColor(247, 249, 252) if row_index % 2 else RGBColor(255, 255, 255)
        for column_index, column in enumerate(columns):
            value = structured_table_cell(column, row.get(column, ""))
            align = structured_table_alignment(column, column_index, value, PP_ALIGN)
            apply_region_table_cell(
                table.cell(row_index, column_index),
                value,
                fill_color,
                RGBColor(5, 6, 10),
                bold=column_index == 0,
                align=align,
                font_size=7.5,
                MSO_ANCHOR=MSO_ANCHOR,
                Pt=Pt,
            )

def add_report_card_cross_matrix(
    slide,
    *,
    block: ReportBlockPayload,
    rows: list[dict[str, object]],
    audience: str,
    card_left,
    card_top,
    card_width,
    Inches,
    RGBColor,
    MSO_SHAPE,
    PP_ALIGN,
    Pt,
) -> None:
    row_label, column_label = cross_axis_labels(block, rows)
    metric_label = cross_metric_label(block, rows)
    scale_label = cross_scale_label(block, rows)
    valid_rows = filter_valid_cross_rows(rows, row_label, column_label)
    matrix = report_card_cross_matrix_rows(block, valid_rows, row_label, column_label, metric_label, scale_label)
    source_krw_lookup = cross_matrix_source_krw_lookup(valid_rows, row_label, column_label)
    matrix_rows = list(matrix["rows"])[:5]
    matrix_columns = list(matrix["columns"])[:3]
    if not matrix_rows or not matrix_columns:
        add_brand_chart_text(slide, card_left + Inches(0.34), card_top + Inches(1.34), card_width - Inches(0.68), Inches(0.32), "\ud45c\uc2dc\ud560 \uad50\ucc28\ubd84\uc11d \ub370\uc774\ud130\uac00 \uc5c6\uc2b5\ub2c8\ub2e4.", 10.0, RGBColor(143, 149, 161), bold=True, align=PP_ALIGN.CENTER, Pt=Pt, PP_ALIGN=PP_ALIGN)
        return

    grid_left = card_left + Inches(0.34)
    grid_top = card_top + Inches(1.08)
    grid_width = card_width - Inches(0.68)
    row_header_w = Inches(1.78)
    total_w = Inches(1.18)
    gap = Inches(0.02)
    cell_w = int((grid_width - row_header_w - total_w - gap * (len(matrix_columns) + 1)) / max(len(matrix_columns), 1))
    header_h = Inches(0.34)
    row_h = Inches(0.48 if len(matrix_rows) <= 4 else 0.42)
    max_value = float(matrix["max_abs"] or 0) or 1
    muted = RGBColor(143, 149, 161)
    header_fill = RGBColor(248, 249, 251)
    line_color = RGBColor(226, 228, 232)

    add_brand_chart_text(slide, grid_left, grid_top + Inches(0.08), row_header_w, Inches(0.16), f"{clean_cross_axis_name(row_label, block=block, role='row')} / {clean_cross_axis_name(column_label, block=block, role='column')}", 6.8, muted, bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
    for col_index, column in enumerate(matrix_columns):
        x = grid_left + row_header_w + gap + (cell_w + gap) * col_index
        add_cross_cell_box(slide, x, grid_top, cell_w, header_h, header_fill, line_color, RGBColor, MSO_SHAPE, Pt)
        add_brand_chart_text(slide, x + Inches(0.03), grid_top + Inches(0.08), cell_w - Inches(0.06), Inches(0.16), clamp_text(str(column), 18), 6.1, muted, bold=True, align=PP_ALIGN.RIGHT, Pt=Pt, PP_ALIGN=PP_ALIGN)
    total_x = grid_left + row_header_w + gap + (cell_w + gap) * len(matrix_columns)
    add_cross_cell_box(slide, total_x, grid_top, total_w, header_h, header_fill, line_color, RGBColor, MSO_SHAPE, Pt)
    total_header = "\ube44\uc911 \ud569\uacc4" if matrix["is_share"] else "\ucd1d\ud569"
    add_brand_chart_text(slide, total_x + Inches(0.04), grid_top + Inches(0.08), total_w - Inches(0.08), Inches(0.16), total_header, 6.2, muted, bold=True, align=PP_ALIGN.RIGHT, Pt=Pt, PP_ALIGN=PP_ALIGN)

    for row_index, row_name in enumerate(matrix_rows):
        y = grid_top + header_h + gap + (row_h + gap) * row_index
        add_cross_cell_box(slide, grid_left, y, row_header_w, row_h, RGBColor(255, 255, 255), line_color, RGBColor, MSO_SHAPE, Pt)
        add_brand_chart_text(slide, grid_left + Inches(0.07), y + Inches(0.14), row_header_w - Inches(0.14), Inches(0.16), clamp_text(str(row_name), 24), 7.0, RGBColor(5, 6, 10), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
        for col_index, column in enumerate(matrix_columns):
            x = grid_left + row_header_w + gap + (cell_w + gap) * col_index
            raw_value = float(matrix["display_values"].get((row_name, column), 0) or 0)
            display = matrix["displays"].get((row_name, column), "-")
            fill = cross_matrix_cell_color(raw_value, max_value, bool(display and display != "-"), bool(matrix["is_growth"]), RGBColor)
            add_cross_cell_box(slide, x, y, cell_w, row_h, fill, line_color, RGBColor, MSO_SHAPE, Pt)
            text_color = cross_matrix_text_color(raw_value, max_value, bool(matrix["is_growth"]), RGBColor)
            krw_display = ""
            if audience == "internal":
                krw_display = source_krw_lookup.get((row_name, column), "") or matrix["krw_displays"].get((row_name, column), "")
            add_brand_chart_text(slide, x + Inches(0.04), y + Inches(0.09 if krw_display else 0.13), cell_w - Inches(0.08), Inches(0.15), display, 6.0 if krw_display else 6.2, text_color, bold=True, align=PP_ALIGN.RIGHT, Pt=Pt, PP_ALIGN=PP_ALIGN)
            if krw_display:
                krw_color = RGBColor(255, 255, 255) if text_color == RGBColor(255, 255, 255) else RGBColor(100, 116, 139)
                add_brand_chart_text(slide, x + Inches(0.04), y + Inches(0.25), cell_w - Inches(0.08), Inches(0.13), krw_display, 5.1, krw_color, bold=True, align=PP_ALIGN.RIGHT, Pt=Pt, PP_ALIGN=PP_ALIGN)
        total_display = matrix["row_totals"].get(row_name, "-")
        total_krw_display = matrix["row_total_krw"].get(row_name, "") if audience == "internal" else ""
        add_cross_cell_box(slide, total_x, y, total_w, row_h, header_fill, line_color, RGBColor, MSO_SHAPE, Pt)
        add_brand_chart_text(slide, total_x + Inches(0.04), y + Inches(0.09 if total_krw_display else 0.13), total_w - Inches(0.08), Inches(0.16), total_display, 6.2 if total_krw_display else 6.4, RGBColor(5, 6, 10), bold=True, align=PP_ALIGN.RIGHT, Pt=Pt, PP_ALIGN=PP_ALIGN)
        if total_krw_display:
            add_brand_chart_text(slide, total_x + Inches(0.04), y + Inches(0.25), total_w - Inches(0.08), Inches(0.13), total_krw_display, 5.1, RGBColor(100, 116, 139), bold=True, align=PP_ALIGN.RIGHT, Pt=Pt, PP_ALIGN=PP_ALIGN)

    note = "\uc0c1\uc704 \uc870\ud569 \uae30\uc900\uc73c\ub85c \ud45c\uc2dc\ud558\uba70, \uac12\uc774 \uc791\uac70\ub098 \ub370\uc774\ud130\uac00 \uc5c6\ub294 \uc870\ud569\uc740 \uc5f0\ud558\uac8c \ud45c\uc2dc\ub429\ub2c8\ub2e4."
    add_brand_chart_text(slide, grid_left, card_top + Inches(4.10), grid_width, Inches(0.18), note, 6.5, muted, Pt=Pt, PP_ALIGN=PP_ALIGN)

__all__ = [
    "should_paginate_ranking_card",
    "add_report_card_growth_split",
    "add_report_card_country_detail",
    "add_report_card_brand_overview",
    "add_report_card_sku_order_reference",
    "add_report_card_season_calendar",
    "add_season_calendar_detail_page",
    "add_report_card_trend_chart",
    "add_snapshot_table_page",
    "add_report_card_cross_matrix",
]


