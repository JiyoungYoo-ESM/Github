"""PPTX 보고서 렌더러(템플릿 + 동적 생성).

report_template_export 분해(IMPROVEMENT_PLAN.md 2단계)의 마지막·최대 조각. 장바구니 PPTX
템플릿을 채우거나(write_template_report_pptx), 템플릿이 없으면 코드로 덱을 생성한다
(write_dynamic_report_pptx). 국가/브랜드/SKU/교차/시즌 슬라이드 빌더를 포함한다. python-pptx
타입은 함수 내부에서 지연 import하거나 인자로 주입받는다. 계산·포맷·마스킹·프리미티브 base
계층에만 의존한다(cards⇄template 순환은 이 모듈 내부 호출로 흡수)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from backend.config import REPORT_CART_TEMPLATE_PPTX
from backend.services.reports.models import *  # noqa: F401,F403
from backend.services.reports.formatting import *  # noqa: F401,F403
from backend.services.reports.report_data import *  # noqa: F401,F403
from backend.services.reports.compute_cross import *  # noqa: F401,F403
from backend.services.reports.compute_snapshot import *  # noqa: F401,F403
from backend.services.reports.compute_series import *  # noqa: F401,F403
from backend.services.reports.report_chrome import *  # noqa: F401,F403
from backend.services.reports.pptx_prims import *  # noqa: F401,F403
from backend.services.reports.pptx_template_common import *  # noqa: F401,F403
from backend.services.reports.pptx_template_rankings import *  # noqa: F401,F403
from backend.services.reports.pptx_template_sections import *  # noqa: F401,F403
from backend.services.reports.pptx_dynamic_cards import *  # noqa: F401,F403


def write_template_report_pptx(
    output_path: Path,
    *,
    audience: str,
    blocks: list[ReportBlockPayload],
    title: str | None,
    masking_summary: MaskingSummary | None = None,
) -> None:
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="python-pptx is required to generate report cart PPTX files. Run pip install -r requirements.txt.",
        ) from exc

    prs = Presentation(str(REPORT_CART_TEMPLATE_PPTX))
    template_slides = capture_template_section_slides(prs)
    # 마지막 Thank You 슬라이드 참조(추가 섹션 슬라이드 삽입 위치 계산용).
    thanks_slide = prs.slides[10] if len(prs.slides) > 10 else prs.slides[len(prs.slides) - 1]
    sections = group_blocks_by_section(blocks)
    generated_at = datetime.now().strftime("%Y-%m-%d")
    include_cross_or_share = should_include_template_cross_or_share(audience, sections)
    include_appendix = should_include_template_appendix(audience)
    use_cart_ordered_sections = bool(blocks)

    fill_template_cover(prs, audience=audience, blocks=blocks, title=title, generated_at=generated_at)
    fill_template_contents(prs, audience=audience, sections=sections)
    region_spec = None if use_cart_ordered_sections else fill_template_region(prs, audience=audience, blocks=sections.get("region", []))
    brand_spec = None if use_cart_ordered_sections else fill_template_brand(prs, audience=audience, blocks=sections.get("brand", []))
    sku_spec = None if use_cart_ordered_sections else fill_template_sku(prs, audience=audience, blocks=sections.get("sku", []))
    cross_slide = None
    if include_cross_or_share:
        if not (use_cart_ordered_sections and sections.get("cross")):
            cross_slide = fill_template_cross_or_share(prs, audience=audience, blocks=sections.get("cross", []), masking_summary=masking_summary)
    if include_appendix:
        fill_template_appendix(prs, audience=audience, masking_summary=masking_summary)
    fill_template_thanks(prs, audience=audience, title=title)
    # 한 장의 최대 행 수를 넘기면 슬라이드를 복제해 전량 출력한다.
    for spec in (region_spec, brand_spec, sku_spec):
        if spec:
            expand_section_pages(prs, base_slide=spec["base_slide"], page_count=spec["page_count"], render_page=spec["render_page"])
    if cross_slide is not None and sections.get("cross"):
        expand_template_cross_slides(prs, base_slide=cross_slide, blocks=sections["cross"], audience=audience)
    # 슬라이드 추가는 삭제(remove_unused)보다 먼저 수행해 partname 충돌을 피한다.
    # 목차 바로 다음에 핵심 지표 요약 슬라이드를 생성해 삽입한다.
    fill_template_summary(prs, audience=audience, blocks=sections.get("summary", []), after_slide=prs.slides[1])
    # 전용 템플릿 슬라이드는 섹션 요약대로 채우고, 담긴 카드의 상세 순서는
    # 별도 페이지 묶음으로 다시 출력해 사용자 선택 순서를 손실 없이 보존한다.
    extra_anchor = (template_slides.get("appendix") or (None,))[0] if include_appendix else thanks_slide
    fill_template_ordered_cart_blocks(
        prs,
        audience=audience,
        blocks=blocks,
        anchor_slide=extra_anchor or thanks_slide,
    )
    remove_unused_template_section_slides(
        prs,
        sections,
        include_cross_or_share=include_cross_or_share,
        include_appendix=include_appendix,
        template_slides=template_slides,
        remove_cart_summary_sections=use_cart_ordered_sections,
    )
    add_slide_numbers(prs, period_label=report_period_label(blocks))
    prs.save(output_path)


def fill_template_ordered_cart_blocks(
    prs,
    *,
    audience: str,
    blocks: list[ReportBlockPayload],
    anchor_slide,
) -> None:
    """Append a lossless, cart-ordered detail sequence to the branded template.

    The fixed template pages are useful section summaries, but they intentionally fold
    several cards into one table.  Those summaries cannot prove that every selected
    card, row, column, or cross-section reorder survived export.  This sequence is the
    canonical card-level representation: one paginated group per cart item, in the
    exact incoming order.
    """
    if not blocks or anchor_slide is None:
        return
    try:
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches
    except ImportError:
        return

    for block_index, block in enumerate(blocks, start=1):
        created_slides = add_structured_block_pages(
            prs,
            block=block,
            block_index=block_index,
            audience=audience,
            Inches=Inches,
            RGBColor=RGBColor,
            MSO_SHAPE=MSO_SHAPE,
        )
        for slide in created_slides:
            move_slide_before(prs, slide, anchor_slide)




def fill_template_contents(prs, *, audience: str, sections: dict[str, list[ReportBlockPayload]]) -> None:
    slide = prs.slides[1]
    items = template_contents_items(sections, audience)
    number_ids = (104, 106, 108, 110)
    text_ids = (105, 107, 109, 111)
    for index, shape_id in enumerate(number_ids, start=1):
        set_shape_text(slide, shape_id, f"{index:02d}" if index <= len(items) else "")
    for index, shape_id in enumerate(text_ids):
        set_shape_text(slide, shape_id, items[index] if index < len(items) else "")
    # 섹션이 네 개를 넘으면 템플릿 스타일을 복제해 목차 항목을 이어 붙인다.
    if len(items) > 4:
        add_extra_contents_items(slide, items[4:], number_ids=number_ids, text_ids=text_ids)


def add_extra_contents_items(
    slide,
    extra_items: list[str],
    *,
    number_ids: tuple[int, ...],
    text_ids: tuple[int, ...],
) -> None:
    first_number = find_shape(slide, number_ids[0])
    second_number = find_shape(slide, number_ids[1])
    last_number = find_shape(slide, number_ids[-1])
    last_text = find_shape(slide, text_ids[-1])
    if not (first_number and second_number and last_number and last_text):
        return
    spacing = second_number.top - first_number.top
    for offset, item in enumerate(extra_items, start=1):
        # 번호가 좁은 박스에서 세로로 쪼개지지 않도록 wrap을 끈다.
        clone_textbox_below(slide, last_number, spacing * offset, f"{len(number_ids) + offset:02d}", wrap=False)
        clone_textbox_below(slide, last_text, spacing * offset, item, wrap=True)


def section_contents_title(blocks: list[ReportBlockPayload], fallback: str) -> str:
    if not blocks:
        return fallback
    title = clamp_text(blocks[0].title or fallback, 24)
    if len(blocks) == 1:
        return title
    return f"{title} 외 {len(blocks) - 1}건"


def should_include_template_cross_or_share(audience: str, sections: dict[str, list[ReportBlockPayload]]) -> bool:
    if sections.get("cross"):
        return True
    return audience != "internal"


def should_include_template_appendix(audience: str) -> bool:
    return audience != "internal"


def capture_template_section_slides(prs) -> dict[str, tuple[object, ...]]:
    section_indices = {
        "region": (2, 3),
        "brand": (4, 5),
        "sku": (6, 7),
        "cross": (8,),
        "appendix": (9,),
    }
    captured: dict[str, tuple[object, ...]] = {}
    for section, indices in section_indices.items():
        captured[section] = tuple(prs.slides[index] for index in indices if index < len(prs.slides))
    return captured


def remove_unused_template_section_slides(
    prs,
    sections: dict[str, list[ReportBlockPayload]],
    *,
    include_cross_or_share: bool,
    include_appendix: bool,
    template_slides: dict[str, tuple[object, ...]] | None = None,
    remove_cart_summary_sections: bool = False,
) -> None:
    template_slides = template_slides or capture_template_section_slides(prs)
    remove_slides: list[object] = []
    for section in ("region", "brand", "sku"):
        if remove_cart_summary_sections or not sections.get(section):
            remove_slides.extend(template_slides.get(section, ()))
    if not include_cross_or_share or (remove_cart_summary_sections and sections.get("cross")):
        remove_slides.extend(template_slides.get("cross", ()))
    if not include_appendix:
        remove_slides.extend(template_slides.get("appendix", ()))
    for slide in remove_slides:
        delete_slide_by_ref(prs, slide)


def fill_template_summary(prs, *, audience: str, blocks: list[ReportBlockPayload], after_slide) -> None:
    """summary/kpi 블록을 개요 슬라이드로 렌더링해 목차 다음에 삽입한다.

    템플릿에는 요약 슬라이드가 없어 이전에는 PPT/PDF에서 누락되었다.
    """
    if not blocks:
        return
    try:
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches
    except ImportError:
        return
    # 원화 병기는 내부용에만 노출한다.
    pairs = summary_metric_pairs(blocks, include_sub=audience == "internal")
    if not pairs:
        return
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_slide_background(slide, prs, RGBColor(255, 255, 255), RGBColor, MSO_SHAPE)
    add_slide_accent(slide, prs, Inches, RGBColor, MSO_SHAPE, width=0.14)
    add_textbox(slide, Inches(0.72), Inches(0.62), Inches(6.0), Inches(0.3), "SILICON2 ESM ANALYTICS", 10, RGBColor(233, 0, 53), bold=True)
    add_textbox(slide, Inches(0.72), Inches(1.02), Inches(9.0), Inches(0.6), "핵심 지표 요약", 26, RGBColor(5, 6, 10), bold=True)
    add_textbox(slide, Inches(0.74), Inches(1.8), Inches(9.0), Inches(0.3), f"{AUDIENCE_LABELS.get(audience, audience)} · 담긴 핵심 지표", 10, RGBColor(105, 112, 127), bold=True)
    tile_w, tile_h, gap = 2.78, 1.02, 0.24
    start_x, start_y = 0.74, 2.36
    for index, (label, value) in enumerate(pairs[:12]):
        col = index % 4
        row_i = index // 4
        x = start_x + col * (tile_w + gap)
        y = start_y + row_i * (tile_h + gap)
        add_metric_tile(slide, Inches(x), Inches(y), Inches(tile_w), Inches(tile_h), label, value, Inches, RGBColor, MSO_SHAPE)
    mark_data_slide(slide)
    move_slide_after(prs, slide, after_slide)


def fill_template_extra_sections(prs, *, audience: str, sections: dict[str, list[ReportBlockPayload]], anchor_slide) -> None:
    """전용 슬라이드가 없는 섹션을 generic 블록 슬라이드로 렌더링해 anchor 앞에 삽입한다.

    슬라이드 삭제보다 먼저 호출해야 partname 충돌이 없다.
    """
    blocks = [block for section in TEMPLATE_EXTRA_SECTIONS for block in sections.get(section, [])]
    if not blocks or anchor_slide is None:
        return
    try:
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches
    except ImportError:
        return
    for section in TEMPLATE_EXTRA_SECTIONS:
        for block in sections.get(section, []):
            slide = add_structured_block_slide(
                prs,
                section=section,
                block=block,
                audience=audience,
                Inches=Inches,
                RGBColor=RGBColor,
                MSO_SHAPE=MSO_SHAPE,
            )
            mark_data_slide(slide)
            move_slide_before(prs, slide, anchor_slide)


def write_dynamic_report_pptx(
    output_path: Path,
    *,
    audience: str,
    blocks: list[ReportBlockPayload],
    title: str | None,
    masking_summary: MaskingSummary | None = None,
) -> None:
    try:
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="python-pptx is required to generate report cart PPTX files. Run pip install -r requirements.txt.",
        ) from exc

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    prepared_for = AUDIENCE_LABELS.get(audience, audience)
    normalized_blocks = blocks or [
        ReportBlockPayload(
            id="empty",
            title="선택한 보고서 블록 없음",
            subtitle="분석 화면에서 + 담기를 눌러 보고서 블록을 추가하세요.",
            meta="Report Cart",
            kind="kpi",
            section="summary",
            size="full",
            snapshot={"columns": [], "rows": []},
        )
    ]
    include_appendix = audience != "internal"

    add_structured_cover_slide(
        prs,
        title=title or "보고서 장바구니",
        prepared_for=prepared_for,
        generated_at=generated_at,
        block_count=len(blocks),
        audience=audience,
        Inches=Inches,
        RGBColor=RGBColor,
        MSO_SHAPE=MSO_SHAPE,
    )
    add_ordered_agenda_slides(
        prs,
        blocks=normalized_blocks,
        include_appendix=include_appendix,
        Inches=Inches,
        RGBColor=RGBColor,
        MSO_SHAPE=MSO_SHAPE,
    )
    add_kpi_summary_slide(
        prs,
        blocks=normalized_blocks,
        audience=audience,
        Inches=Inches,
        RGBColor=RGBColor,
        MSO_SHAPE=MSO_SHAPE,
    )

    for block_index, block in enumerate(normalized_blocks, start=1):
        add_structured_block_pages(
            prs,
            block=block,
            block_index=block_index,
            audience=audience,
            Inches=Inches,
            RGBColor=RGBColor,
            MSO_SHAPE=MSO_SHAPE,
        )

    if include_appendix:
        add_masking_appendix_slide(
            prs,
            audience=audience,
            masking_summary=masking_summary,
            Inches=Inches,
            RGBColor=RGBColor,
            MSO_SHAPE=MSO_SHAPE,
        )

    add_slide_numbers(prs, period_label=report_period_label(blocks), period_scope="data")
    prs.save(output_path)


def add_ordered_agenda_slides(
    prs,
    *,
    blocks: list[ReportBlockPayload],
    include_appendix: bool,
    Inches,
    RGBColor,
    MSO_SHAPE,
) -> None:
    """장바구니 순서를 유지해 목차를 만들고 10개 단위로 페이지를 나눈다."""
    items = [(block.title or "분석 블록", SECTION_LABELS.get(block.section or "summary", block.section or "요약")) for block in blocks]
    if include_appendix:
        items.append(("공유 및 마스킹 기준", "부록"))
    pages = chunk_rows(items, 10)
    for page_index, page in enumerate(pages):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        add_slide_background(slide, prs, RGBColor(255, 255, 255), RGBColor, MSO_SHAPE)
        add_slide_accent(slide, prs, Inches, RGBColor, MSO_SHAPE, width=0.12)
        add_textbox(slide, Inches(0.72), Inches(0.55), Inches(2.6), Inches(0.3), "CONTENTS", 11, RGBColor(233, 0, 53), bold=True)
        title = "보고서 구성" if len(pages) == 1 else f"보고서 구성 ({page_index + 1}/{len(pages)})"
        add_textbox(slide, Inches(0.72), Inches(0.98), Inches(7.0), Inches(0.55), title, 25, RGBColor(5, 6, 10), bold=True)
        for row_index, (item_title, section_label) in enumerate(page):
            absolute_index = page_index * 10 + row_index + 1
            top = Inches(1.68 + row_index * 0.48)
            add_textbox(slide, Inches(0.82), top, Inches(0.48), Inches(0.22), f"{absolute_index:02d}", 10, RGBColor(233, 0, 53), bold=True)
            add_textbox(slide, Inches(1.38), top, Inches(1.2), Inches(0.22), section_label, 9, RGBColor(105, 112, 127), bold=True)
            add_textbox(slide, Inches(2.62), top, Inches(9.6), Inches(0.25), clamp_text(item_title, 72), 11, RGBColor(5, 6, 10), bold=True)


def add_structured_block_pages(
    prs,
    *,
    block: ReportBlockPayload,
    block_index: int,
    audience: str,
    Inches,
    RGBColor,
    MSO_SHAPE,
) -> list:
    """프론트엔드 보고서 카드와 동일한 카드 슬라이드만 출력한다."""
    columns, rows = report_snapshot_rows_and_columns(block, audience)
    created_slides: list = []
    if str(block.type or "").strip().lower() == "season_calendar":
        season_rows = report_card_season_calendar_rows(block, columns, rows, limit=None)
        pages = chunk_rows(season_rows, 5) if season_rows else []
        for page_index, page_rows in enumerate(pages, start=1):
            card_slide = add_structured_report_card_slide(
                prs,
                block=block,
                block_index=block_index,
                columns=columns,
                rows=rows,
                audience=audience,
                Inches=Inches,
                RGBColor=RGBColor,
                MSO_SHAPE=MSO_SHAPE,
                season_rows_override=page_rows,
                card_page_index=page_index,
                card_page_count=len(pages),
            )
            if card_slide is not None:
                created_slides.append(card_slide)
        return created_slides

    if should_paginate_ranking_card(block, rows):
        pages = chunk_rows(rows, 5)
        for page_index, page_rows in enumerate(pages, start=1):
            card_slide = add_structured_report_card_slide(
                prs,
                block=block,
                block_index=block_index,
                columns=columns,
                rows=page_rows,
                audience=audience,
                Inches=Inches,
                RGBColor=RGBColor,
                MSO_SHAPE=MSO_SHAPE,
                card_page_index=page_index,
                card_page_count=len(pages),
            )
            if card_slide is not None:
                created_slides.append(card_slide)
        return created_slides

    card_slide = add_structured_report_card_slide(
        prs,
        block=block,
        block_index=block_index,
        columns=columns,
        rows=rows,
        audience=audience,
        Inches=Inches,
        RGBColor=RGBColor,
        MSO_SHAPE=MSO_SHAPE,
    )
    if card_slide is not None:
        created_slides.append(card_slide)
    return created_slides


def add_structured_report_card_slide(
    prs,
    *,
    block: ReportBlockPayload,
    block_index: int,
    columns: list[str],
    rows: list[dict[str, object]],
    audience: str,
    Inches,
    RGBColor,
    MSO_SHAPE,
    season_rows_override: list[dict[str, object]] | None = None,
    card_page_index: int | None = None,
    card_page_count: int | None = None,
):
    season_rows = season_rows_override if season_rows_override is not None else report_card_season_calendar_rows(block, columns, rows, limit=None)
    card_rows = report_card_rows(block, columns, rows)
    if not card_rows and not season_rows:
        return None
    try:
        from pptx.enum.text import PP_ALIGN
        from pptx.util import Pt
    except ImportError:
        return None

    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_slide_background(slide, prs, RGBColor(250, 250, 251), RGBColor, MSO_SHAPE)
    add_slide_accent(slide, prs, Inches, RGBColor, MSO_SHAPE, width=0.12)
    add_slide_header(
        slide,
        f"CARD {block_index:02d} · {block_type_label(block.type or 'summary')}",
        clamp_text(report_card_slide_title(block, card_page_index, card_page_count), 92),
        report_card_header_subtitle(block),
        audience,
        Inches,
        RGBColor,
        MSO_SHAPE,
    )

    card_left = Inches(1.04)
    card_top = Inches(1.82)
    card_width = Inches(11.25)
    card_height = Inches(4.48)
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, card_left, card_top, card_width, card_height)
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(255, 255, 255)
    card.line.color.rgb = RGBColor(226, 228, 232)

    add_brand_chart_text(
        slide,
        card_left + Inches(0.32),
        card_top + Inches(0.28),
        card_width - Inches(0.64),
        Inches(0.32),
        clamp_text(report_card_title(block), 92),
        11.5,
        RGBColor(5, 6, 10),
        bold=True,
        Pt=Pt,
        PP_ALIGN=PP_ALIGN,
    )
    add_brand_chart_text(
        slide,
        card_left + Inches(0.32),
        card_top + Inches(0.62),
        Inches(8.7),
        Inches(0.24),
        report_card_body_subtitle(block, card_rows, card_page_index, card_page_count),
        8.5,
        RGBColor(143, 149, 161),
        bold=True,
        Pt=Pt,
        PP_ALIGN=PP_ALIGN,
    )
    if str(block.type or "").strip().lower() in {"country_growth", "brand_growth"}:
        add_report_card_growth_split(
            slide,
            rows=rows,
            block_type=str(block.type or "").strip().lower(),
            card_left=card_left,
            card_top=card_top,
            card_width=card_width,
            Inches=Inches,
            RGBColor=RGBColor,
            MSO_SHAPE=MSO_SHAPE,
            PP_ALIGN=PP_ALIGN,
            Pt=Pt,
        )
        add_report_footer(slide, audience, Inches, RGBColor)
        mark_data_slide(slide)
        return slide

    if is_sku_order_reference_block(block, rows):
        add_report_card_sku_order_reference(
            slide,
            rows=rows,
            block=block,
            card_left=card_left,
            card_top=card_top,
            card_width=card_width,
            Inches=Inches,
            RGBColor=RGBColor,
            MSO_SHAPE=MSO_SHAPE,
            PP_ALIGN=PP_ALIGN,
            Pt=Pt,
        )
        add_report_footer(slide, audience, Inches, RGBColor)
        mark_data_slide(slide)
        return slide

    if str(block.type or "").strip().lower() == "country_detail":
        add_report_card_country_detail(
            slide,
            rows=rows,
            block=block,
            card_left=card_left,
            card_top=card_top,
            card_width=card_width,
            Inches=Inches,
            RGBColor=RGBColor,
            MSO_SHAPE=MSO_SHAPE,
            PP_ALIGN=PP_ALIGN,
            Pt=Pt,
        )
        add_report_footer(slide, audience, Inches, RGBColor)
        mark_data_slide(slide)
        return slide

    if str(block.type or "").strip().lower() == "cross_matrix":
        add_report_card_cross_matrix(
            slide,
            block=block,
            rows=rows,
            audience=audience,
            card_left=card_left,
            card_top=card_top,
            card_width=card_width,
            Inches=Inches,
            RGBColor=RGBColor,
            MSO_SHAPE=MSO_SHAPE,
            PP_ALIGN=PP_ALIGN,
            Pt=Pt,
        )
        add_report_footer(slide, audience, Inches, RGBColor)
        mark_data_slide(slide)
        return slide

    if str(block.type or "").strip().lower() == "brand_overview":
        add_report_card_brand_overview(
            slide,
            rows=rows,
            card_left=card_left,
            card_top=card_top,
            card_width=card_width,
            Inches=Inches,
            RGBColor=RGBColor,
            MSO_SHAPE=MSO_SHAPE,
            PP_ALIGN=PP_ALIGN,
            Pt=Pt,
        )
        add_report_footer(slide, audience, Inches, RGBColor)
        mark_data_slide(slide)
        return slide

    if season_rows:
        add_report_card_season_calendar(
            slide,
            season_rows=season_rows,
            card_left=card_left,
            card_top=card_top,
            card_width=card_width,
            Inches=Inches,
            RGBColor=RGBColor,
            MSO_SHAPE=MSO_SHAPE,
            PP_ALIGN=PP_ALIGN,
            Pt=Pt,
        )
        add_report_footer(slide, audience, Inches, RGBColor)
        mark_data_slide(slide)
        return slide

    trend_series = report_card_trend_series(block, rows)
    if trend_series:
        add_report_card_trend_chart(
            slide,
            series=trend_series,
            card_left=card_left,
            card_top=card_top,
            card_width=card_width,
            Inches=Inches,
            RGBColor=RGBColor,
            MSO_SHAPE=MSO_SHAPE,
            PP_ALIGN=PP_ALIGN,
            Pt=Pt,
        )
        add_report_footer(slide, audience, Inches, RGBColor)
        mark_data_slide(slide)
        return slide

    bar_left = card_left + Inches(0.34)
    bar_width = card_width - Inches(0.68)
    row_top = card_top + Inches(1.04)
    row_gap = 0.66
    for index, row in enumerate(card_rows[:5]):
        y = row_top + Inches(index * row_gap)
        add_brand_chart_text(
            slide,
            bar_left,
            y,
            bar_width - Inches(1.2),
            Inches(0.22),
            clamp_text(row["label"], 48),
            9.0,
            RGBColor(5, 6, 10),
            bold=True,
            Pt=Pt,
            PP_ALIGN=PP_ALIGN,
        )
        if row.get("tag"):
            tag_width = Inches(1.05)
            tag_left = card_left + Inches(6.85)
            tag = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, tag_left, y + Inches(0.01), tag_width, Inches(0.18))
            tag.fill.solid()
            tag.fill.fore_color.rgb = RGBColor(244, 246, 250)
            tag.line.fill.background()
            add_brand_chart_text(
                slide,
                tag_left + Inches(0.06),
                y + Inches(0.03),
                tag_width - Inches(0.12),
                Inches(0.12),
                clamp_text(row["tag"], 16),
                5.8,
                RGBColor(143, 149, 161),
                bold=True,
                align=PP_ALIGN.CENTER,
                Pt=Pt,
                PP_ALIGN=PP_ALIGN,
            )
        add_brand_chart_text(
            slide,
            card_left + card_width - Inches(1.42),
            y,
            Inches(1.08),
            Inches(0.22),
            row["value"],
            9.0,
            RGBColor(5, 6, 10),
            bold=True,
            align=PP_ALIGN.RIGHT,
            Pt=Pt,
            PP_ALIGN=PP_ALIGN,
        )
        track = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, bar_left, y + Inches(0.31), bar_width, Inches(0.055))
        track.name = "Silicon2 Report Card Bar Track"
        track.fill.solid()
        track.fill.fore_color.rgb = RGBColor(242, 243, 245)
        track.line.fill.background()
        ratio = min(max(float(row.get("ratio", 0)), 0.04), 1.0)
        bar = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, bar_left, y + Inches(0.31), int(bar_width * ratio), Inches(0.055))
        bar.name = "Silicon2 Report Card Value Bar"
        bar.fill.solid()
        bar.fill.fore_color.rgb = RGBColor(233, 0, 53)
        bar.line.fill.background()

    add_report_footer(slide, audience, Inches, RGBColor)
    mark_data_slide(slide)
    return slide


def add_structured_cover_slide(
    prs,
    *,
    title: str,
    prepared_for: str,
    generated_at: str,
    block_count: int,
    audience: str,
    Inches,
    RGBColor,
    MSO_SHAPE,
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_slide_background(slide, prs, RGBColor(255, 255, 255), RGBColor, MSO_SHAPE)
    add_slide_accent(slide, prs, Inches, RGBColor, MSO_SHAPE, width=0.14)

    display_title = normalize_report_title(title)
    add_textbox(slide, Inches(0.72), Inches(0.62), Inches(4.8), Inches(0.28), "SILICON2 SCM ANALYTICS", 10, RGBColor(233, 0, 53), bold=True)
    add_textbox(slide, Inches(0.72), Inches(1.18), Inches(7.5), Inches(0.7), display_title, 32, RGBColor(5, 6, 10), bold=True)
    add_textbox(slide, Inches(0.74), Inches(2.05), Inches(7.0), Inches(0.36), "Report Cart Export", 13, RGBColor(105, 112, 127), bold=True)
    add_audience_badge(slide, Inches(0.74), Inches(2.66), Inches(2.95), Inches(0.38), audience, Inches, RGBColor, MSO_SHAPE)

    for index, (label, value) in enumerate(
        [
            ("보고 대상", prepared_for),
            ("생성일", generated_at),
            ("담긴 블록", f"{block_count}개"),
        ]
    ):
        x = 0.74 + index * 2.52
        add_metric_tile(slide, Inches(x), Inches(3.62), Inches(2.22), Inches(0.88), label, value, Inches, RGBColor, MSO_SHAPE)

    side_panel = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(9.2), 0, Inches(4.13), prs.slide_height)
    side_panel.fill.solid()
    side_panel.fill.fore_color.rgb = RGBColor(233, 0, 53)
    side_panel.line.fill.background()
    add_textbox(slide, Inches(9.72), Inches(1.45), Inches(2.8), Inches(1.3), "SCM\nREPORT", 30, RGBColor(255, 255, 255), bold=True)
    add_textbox(slide, Inches(9.76), Inches(5.92), Inches(2.7), Inches(0.58), security_notice(audience), 9, RGBColor(255, 225, 232), bold=True)


def add_structured_agenda_slide(
    prs,
    *,
    section_keys: list[str],
    include_appendix: bool,
    Inches,
    RGBColor,
    MSO_SHAPE,
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_slide_background(slide, prs, RGBColor(255, 255, 255), RGBColor, MSO_SHAPE)
    add_slide_accent(slide, prs, Inches, RGBColor, MSO_SHAPE, width=0.12)
    add_textbox(slide, Inches(0.72), Inches(0.55), Inches(2.6), Inches(0.3), "CONTENTS", 11, RGBColor(233, 0, 53), bold=True)
    add_textbox(slide, Inches(0.72), Inches(0.98), Inches(7.0), Inches(0.55), "보고서 구성", 25, RGBColor(5, 6, 10), bold=True)
    agenda_items = ["핵심요약", *[SECTION_LABELS[section] for section in section_keys]]
    if include_appendix:
        agenda_items.append("부록 · 공유 및 마스킹 기준")
    for index, label in enumerate(agenda_items, start=1):
        top = Inches(1.78 + (index - 1) * 0.58)
        add_textbox(slide, Inches(0.82), top, Inches(0.46), Inches(0.24), f"{index:02d}", 11, RGBColor(233, 0, 53), bold=True)
        add_textbox(slide, Inches(1.38), top, Inches(6.2), Inches(0.28), label, 13, RGBColor(5, 6, 10), bold=True)


def add_kpi_summary_slide(
    prs,
    *,
    blocks: list[ReportBlockPayload],
    audience: str,
    Inches,
    RGBColor,
    MSO_SHAPE,
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_slide_background(slide, prs, RGBColor(250, 250, 251), RGBColor, MSO_SHAPE)
    add_slide_accent(slide, prs, Inches, RGBColor, MSO_SHAPE, width=0.12)
    add_slide_header(slide, "SUMMARY", "핵심요약", "선택된 분석 데이터를 기준으로 산출했습니다.", audience, Inches, RGBColor, MSO_SHAPE)

    metrics = build_kpi_metrics(blocks)
    for index, (label, value, sub) in enumerate(metrics[:4]):
        x = 0.74 + index * 3.02
        add_metric_tile(slide, Inches(x), Inches(1.92), Inches(2.62), Inches(1.12), label, value, Inches, RGBColor, MSO_SHAPE)
        add_textbox(slide, Inches(x + 0.16), Inches(2.77), Inches(2.25), Inches(0.18), sub, 8, RGBColor(105, 112, 127), bold=True)

    ordered_preview = " → ".join(clamp_text(block.title, 14) for block in blocks[:3]) or "선택 데이터 없음"
    remaining_note = f" (이후 {len(blocks) - 3}개)" if len(blocks) > 3 else ""
    narrative = [
        f"블록 순서: {ordered_preview}{remaining_note}",
        "표시 인사이트 문장은 dataset 레이어에서 마스킹된 값만 사용합니다.",
        f"공유 기준: {audience_badge(audience)}",
    ]
    add_textbox(slide, Inches(0.82), Inches(3.72), Inches(10.7), Inches(1.15), "\n".join(narrative), 13, RGBColor(5, 6, 10), bold=True)
    add_report_footer(slide, audience, Inches, RGBColor)


def add_section_index_slide(
    prs,
    *,
    section: str,
    blocks: list[ReportBlockPayload],
    audience: str,
    Inches,
    RGBColor,
    MSO_SHAPE,
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_slide_background(slide, prs, RGBColor(255, 255, 255), RGBColor, MSO_SHAPE)
    add_slide_accent(slide, prs, Inches, RGBColor, MSO_SHAPE, width=0.12)
    add_slide_header(slide, "SECTION INDEX", SECTION_LABELS.get(section, section), f"{len(blocks)}개 블록", audience, Inches, RGBColor, MSO_SHAPE)
    for index, block in enumerate(blocks[:12], start=1):
        top = Inches(1.82 + (index - 1) * 0.35)
        add_textbox(slide, Inches(0.86), top, Inches(0.5), Inches(0.2), f"{index:02d}", 9, RGBColor(233, 0, 53), bold=True)
        add_textbox(slide, Inches(1.42), top, Inches(7.4), Inches(0.22), block.title, 10, RGBColor(5, 6, 10), bold=True)
    add_report_footer(slide, audience, Inches, RGBColor)


def add_structured_block_slide(
    prs,
    *,
    section: str,
    block: ReportBlockPayload,
    audience: str,
    Inches,
    RGBColor,
    MSO_SHAPE,
):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_slide_background(slide, prs, RGBColor(250, 250, 251), RGBColor, MSO_SHAPE)
    add_slide_accent(slide, prs, Inches, RGBColor, MSO_SHAPE, width=0.12)
    add_slide_header(
        slide,
        SECTION_LABELS.get(section, section).upper(),
        block.title,
        block.subtitle or block.meta,
        audience,
        Inches,
        RGBColor,
        MSO_SHAPE,
    )
    add_snapshot_table(slide, block, audience, Inches, RGBColor, MSO_SHAPE)
    add_textbox(slide, Inches(0.78), Inches(6.42), Inches(8.8), Inches(0.24), render_block_insight(block, audience), 9, RGBColor(105, 112, 127), bold=True)
    add_report_footer(slide, audience, Inches, RGBColor)
    return slide


def add_masking_appendix_slide(
    prs,
    *,
    audience: str,
    masking_summary: MaskingSummary | None,
    Inches,
    RGBColor,
    MSO_SHAPE,
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_slide_background(slide, prs, RGBColor(255, 255, 255), RGBColor, MSO_SHAPE)
    add_slide_accent(slide, prs, Inches, RGBColor, MSO_SHAPE, width=0.12)
    add_slide_header(slide, "APPENDIX", "공유 및 마스킹 기준", "실제 적용한 데이터 처리 기준입니다.", audience, Inches, RGBColor, MSO_SHAPE)
    removed_columns = ", ".join(masking_summary.removed_columns) if masking_summary and masking_summary.removed_columns else "없음"
    anonymized_count = masking_summary.anonymized_competitor_count if masking_summary else 0
    policy = masking_summary.client_identity_policy if masking_summary else client_identity_policy(audience)
    rows = [
        ("공유 기준", audience_badge(audience)),
        ("제거된 민감 컬럼", removed_columns),
        ("익명화된 경쟁사", f"{anonymized_count}개"),
        ("거래처·고객명 처리", policy),
    ]
    for index, (label, value) in enumerate(rows):
        top = Inches(1.85 + index * 0.7)
        add_textbox(slide, Inches(0.86), top, Inches(2.1), Inches(0.24), label, 11, RGBColor(105, 112, 127), bold=True)
        add_textbox(slide, Inches(3.05), top, Inches(7.6), Inches(0.3), value, 13, RGBColor(5, 6, 10), bold=True)
    add_textbox(slide, Inches(0.86), Inches(5.35), Inches(10.4), Inches(0.52), security_notice(audience), 11, RGBColor(105, 112, 127), bold=True)
    add_report_footer(slide, audience, Inches, RGBColor)




def add_audience_badge(slide, left, top, width, height, audience: str, Inches, RGBColor, MSO_SHAPE) -> None:
    color = RGBColor(233, 0, 53) if audience == "internal" else RGBColor(105, 112, 127)
    shape = add_textbox(slide, left, top, width, height, audience_badge(audience), 8, color, bold=True)
    shape.name = "Silicon2 Audience Label"


def add_snapshot_table(slide, block: ReportBlockPayload, audience: str, Inches, RGBColor, MSO_SHAPE) -> None:
    columns, rows = report_snapshot_rows_and_columns(block, audience)
    add_snapshot_table_page(
        slide,
        columns=columns[:6],
        rows=rows[:14],
        Inches=Inches,
        RGBColor=RGBColor,
        MSO_SHAPE=MSO_SHAPE,
    )


def add_report_cover_slide(
    prs,
    *,
    title: str,
    prepared_for: str,
    generated_at: str,
    block_count: int,
    Inches,
    RGBColor,
    MSO_SHAPE,
    PP_ALIGN,
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_slide_background(slide, prs, RGBColor(255, 255, 255), RGBColor, MSO_SHAPE)

    display_title = normalize_report_title(title)

    side_panel = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(9.35), 0, Inches(3.98), prs.slide_height)
    side_panel.fill.solid()
    side_panel.fill.fore_color.rgb = RGBColor(233, 0, 53)
    side_panel.line.fill.background()

    bottom_rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.72), Inches(6.98), Inches(7.95), Inches(0.03))
    bottom_rule.fill.solid()
    bottom_rule.fill.fore_color.rgb = RGBColor(5, 6, 10)
    bottom_rule.line.fill.background()

    add_textbox(slide, Inches(0.72), Inches(0.62), Inches(5.8), Inches(0.35), "SILICON2 SCM ANALYTICS", 11, RGBColor(233, 0, 53), bold=True)
    add_textbox(slide, Inches(0.72), Inches(1.3), Inches(7.7), Inches(0.92), display_title, 36, RGBColor(5, 6, 10), bold=True)
    add_textbox(slide, Inches(0.76), Inches(3.26), Inches(2.2), Inches(0.24), "REPORT SUMMARY", 9, RGBColor(233, 0, 53), bold=True)
    for index, (label, value) in enumerate(
        [
            ("보고 대상", prepared_for),
            ("담당자", ""),
            ("생성일", generated_at),
        ]
    ):
        x = 0.76 + index * 2.42
        add_metric_tile(slide, Inches(x), Inches(3.66), Inches(2.12), Inches(0.88), label, value, Inches, RGBColor, MSO_SHAPE)

    add_textbox(slide, Inches(9.82), Inches(1.82), Inches(2.65), Inches(1.45), "SCM\nANALYTICS", 26, RGBColor(255, 255, 255), bold=True)
    add_textbox(slide, Inches(9.86), Inches(5.88), Inches(2.7), Inches(0.62), "Market signal\nreport export", 12, RGBColor(255, 225, 232), bold=True)


def add_report_agenda_slide(
    prs,
    *,
    blocks: list[ReportBlockPayload],
    Inches,
    RGBColor,
    MSO_SHAPE,
    PP_ALIGN,
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_slide_background(slide, prs, RGBColor(255, 255, 255), RGBColor, MSO_SHAPE)
    add_slide_accent(slide, prs, Inches, RGBColor, MSO_SHAPE, width=0.12)
    add_textbox(slide, Inches(0.72), Inches(0.55), Inches(2.5), Inches(0.3), "CONTENTS", 11, RGBColor(233, 0, 53), bold=True)
    add_textbox(slide, Inches(0.72), Inches(0.98), Inches(7.5), Inches(0.55), "보고서 구성", 25, RGBColor(5, 6, 10), bold=True)

    for index, block in enumerate(blocks[:8], start=1):
        top = Inches(1.7 + (index - 1) * 0.55)
        add_textbox(slide, Inches(0.82), top, Inches(0.45), Inches(0.24), f"{index:02d}", 11, RGBColor(233, 0, 53), bold=True)
        add_textbox(slide, Inches(1.35), top, Inches(5.6), Inches(0.28), block.title, 12, RGBColor(5, 6, 10), bold=True)

    if len(blocks) > 8:
        add_textbox(slide, Inches(0.82), Inches(6.35), Inches(6.0), Inches(0.3), f"외 {len(blocks) - 8}개 블록은 이어지는 슬라이드에 포함됩니다.", 10, RGBColor(105, 112, 127))


def add_report_block_slide(
    prs,
    *,
    index: int,
    block: ReportBlockPayload,
    audience: str,
    Inches,
    RGBColor,
    MSO_SHAPE,
    PP_ALIGN,
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_slide_background(slide, prs, RGBColor(250, 250, 251), RGBColor, MSO_SHAPE)
    add_slide_accent(slide, prs, Inches, RGBColor, MSO_SHAPE, width=0.12)

    add_textbox(slide, Inches(0.62), Inches(0.42), Inches(1.3), Inches(0.28), f"BLOCK {index:02d}", 9, RGBColor(233, 0, 53), bold=True)
    add_textbox(slide, Inches(0.62), Inches(0.82), Inches(8.0), Inches(0.5), block.title, 23, RGBColor(5, 6, 10), bold=True)
    add_textbox(slide, Inches(0.64), Inches(1.42), Inches(9.0), Inches(0.35), block.subtitle or block.meta or block.type, 11, RGBColor(105, 112, 127))

    add_block_content_panel(slide, block, audience, Inches, RGBColor, MSO_SHAPE)

    add_textbox(slide, Inches(0.65), Inches(6.86), Inches(7.2), Inches(0.22), f"{block.type or 'summary'} | {block.id}", 8, RGBColor(154, 161, 173))


def add_block_content_panel(slide, block: ReportBlockPayload, audience: str, Inches, RGBColor, MSO_SHAPE) -> None:
    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.62), Inches(2.0), Inches(11.65), Inches(4.6))
    panel.fill.solid()
    panel.fill.fore_color.rgb = RGBColor(255, 255, 255)
    panel.line.color.rgb = RGBColor(226, 228, 232)

    add_textbox(slide, Inches(0.9), Inches(2.28), Inches(2.2), Inches(0.24), "핵심 요약", 10, RGBColor(233, 0, 53), bold=True)
    add_textbox(slide, Inches(0.9), Inches(2.68), Inches(4.75), Inches(1.0), render_block_insight(block, audience), 15, RGBColor(5, 6, 10), bold=True)

    info_text = " · ".join(f"{key}: {value}" for key, value in block_to_rows(block)[:3])
    add_textbox(slide, Inches(0.9), Inches(3.95), Inches(4.9), Inches(0.3), info_text, 9, RGBColor(105, 112, 127), bold=True)

    divider = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6.12), Inches(2.36), Inches(0.01), Inches(3.72))
    divider.fill.solid()
    divider.fill.fore_color.rgb = RGBColor(226, 228, 232)
    divider.line.fill.background()

    add_textbox(slide, Inches(6.42), Inches(2.28), Inches(4.8), Inches(0.24), "데이터 미리보기", 10, RGBColor(105, 112, 127), bold=True)
    preview_rows = snapshot_preview_rows(block)
    if not preview_rows:
        add_textbox(slide, Inches(6.42), Inches(3.36), Inches(4.9), Inches(0.45), "표시할 데이터 미리보기가 없습니다.", 12, RGBColor(105, 112, 127))
        return

    headers = list(preview_rows[0].keys())[:4]
    x_positions = [6.42, 8.08, 9.35, 10.55]
    widths = [1.48, 1.08, 1.0, 1.0]
    for index, header in enumerate(headers):
        add_textbox(slide, Inches(x_positions[index]), Inches(2.74), Inches(widths[index]), Inches(0.2), header, 8, RGBColor(105, 112, 127), bold=True)
    for row_index, row in enumerate(preview_rows[:7]):
        y = Inches(3.08 + row_index * 0.34)
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6.42), y - Inches(0.06), Inches(5.2), Inches(0.01))
        line.fill.solid()
        line.fill.fore_color.rgb = RGBColor(237, 240, 243)
        line.line.fill.background()
        for col_index, header in enumerate(headers):
            add_textbox(slide, Inches(x_positions[col_index]), y, Inches(widths[col_index]), Inches(0.2), stringify_report_value(row.get(header, "")), 8, RGBColor(5, 6, 10), bold=col_index == 0)


def add_insight_panel(slide, block: ReportBlockPayload, audience: str, Inches, RGBColor, MSO_SHAPE) -> None:
    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.62), Inches(2.0), Inches(5.55), Inches(2.0))
    panel.fill.solid()
    panel.fill.fore_color.rgb = RGBColor(255, 255, 255)
    panel.line.color.rgb = RGBColor(226, 228, 232)
    add_textbox(slide, Inches(0.9), Inches(2.26), Inches(4.8), Inches(0.24), "핵심 요약", 10, RGBColor(233, 0, 53), bold=True)
    add_textbox(slide, Inches(0.9), Inches(2.66), Inches(4.75), Inches(0.9), render_block_insight(block, audience), 15, RGBColor(5, 6, 10), bold=True)


def add_detail_panel(slide, block: ReportBlockPayload, Inches, RGBColor, MSO_SHAPE) -> None:
    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.62), Inches(4.28), Inches(5.55), Inches(1.88))
    panel.fill.solid()
    panel.fill.fore_color.rgb = RGBColor(255, 255, 255)
    panel.line.color.rgb = RGBColor(226, 228, 232)
    add_textbox(slide, Inches(0.9), Inches(4.52), Inches(4.8), Inches(0.24), "블록 정보", 10, RGBColor(105, 112, 127), bold=True)
    for row_index, (key, value) in enumerate(block_to_rows(block)[:4]):
        y = Inches(4.88 + row_index * 0.28)
        add_textbox(slide, Inches(0.9), y, Inches(1.2), Inches(0.18), key, 8, RGBColor(105, 112, 127), bold=True)
        add_textbox(slide, Inches(2.12), y, Inches(3.45), Inches(0.18), value, 9, RGBColor(5, 6, 10))


def add_snapshot_panel(slide, block: ReportBlockPayload, Inches, RGBColor, MSO_SHAPE) -> None:
    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.42), Inches(2.0), Inches(5.85), Inches(4.16))
    panel.fill.solid()
    panel.fill.fore_color.rgb = RGBColor(255, 255, 255)
    panel.line.color.rgb = RGBColor(226, 228, 232)
    add_textbox(slide, Inches(6.72), Inches(2.26), Inches(4.8), Inches(0.24), "데이터 미리보기", 10, RGBColor(105, 112, 127), bold=True)

    preview_rows = snapshot_preview_rows(block)
    if not preview_rows:
        add_textbox(slide, Inches(6.72), Inches(3.2), Inches(4.8), Inches(0.45), "상세 데이터는 report_dataset.xlsx에서 확인할 수 있습니다.", 12, RGBColor(105, 112, 127))
        return

    headers = list(preview_rows[0].keys())[:4]
    x_positions = [6.72, 8.35, 9.65, 10.85]
    widths = [1.45, 1.1, 1.0, 1.0]
    for index, header in enumerate(headers):
        add_textbox(slide, Inches(x_positions[index]), Inches(2.72), Inches(widths[index]), Inches(0.2), header, 8, RGBColor(105, 112, 127), bold=True)
    for row_index, row in enumerate(preview_rows[:6]):
        y = Inches(3.08 + row_index * 0.38)
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6.72), y - Inches(0.06), Inches(5.1), Inches(0.01))
        line.fill.solid()
        line.fill.fore_color.rgb = RGBColor(237, 240, 243)
        line.line.fill.background()
        for col_index, header in enumerate(headers):
            add_textbox(slide, Inches(x_positions[col_index]), y, Inches(widths[col_index]), Inches(0.2), stringify_report_value(row.get(header, "")), 8, RGBColor(5, 6, 10), bold=col_index == 0)


def fill_template_cover(prs, *, audience: str, blocks: list[ReportBlockPayload], title: str | None, generated_at: str) -> None:
    slide = prs.slides[0]
    for shape_id in (91, 92, 93):
        delete_shape_by_id(slide, shape_id)
    cover_title = normalize_report_title(title)
    set_shape_text(slide, 86, "SILICON2 ESM ANALYTICS")
    set_shape_text(slide, 87, cover_title)
    set_shape_text(slide, 88, "")
    set_shape_text(slide, 89, "")
    set_shape_text(slide, 90, f"생성일 {generated_at}  |  {audience_badge(audience)}")


def add_report_footer(slide, audience: str, Inches, RGBColor) -> None:
    add_textbox(slide, Inches(0.74), Inches(6.95), Inches(6.2), Inches(0.18), f"Silicon2 SCM Analytics \u00b7 {audience_badge(audience)}", 8, RGBColor(154, 161, 173), bold=True)




def template_contents_items(sections: dict[str, list[ReportBlockPayload]], audience: str) -> list[str]:
    items: list[str] = []
    definitions = [
        ("region", "\uad6d\uac00 \u00b7 \uad8c\uc5ed", "\uad6d\uac00\ubcc4 \ud310\ub9e4 \uc21c\uc704"),
        ("brand", "\ube0c\ub79c\ub4dc", "\ube0c\ub79c\ub4dc\ubcc4 \ud310\ub9e4 \uc21c\uc704"),
        ("sku", "SKU", "\uc0c1\uc704 SKU \ubc0f \ub9e4\ucd9c \uad6c\uc131"),
        ("cross", "\uad50\ucc28 \ubd84\uc11d", "\uc120\ud0dd \ucd95 \uae30\uc900 \ub9e4\ud2b8\ub9ad\uc2a4"),
        ("season", "\uc2dc\uc98c \uce98\ub9b0\ub354", "\uc6d4\ubcc4 \uc218\uc694 \uc9c0\uc218"),
        ("ingredient", "\uc131\ubd84", "\uc131\ubd84\ubcc4 \ud310\ub9e4 \ubd84\uc11d"),
    ]
    for section, label, fallback in definitions:
        blocks = sections.get(section) or []
        if not blocks:
            continue
        count = len(blocks)
        suffix = f" \uc678 {count - 1}\uac74" if count > 1 else ""
        items.append(clamp_text(f"{label} \u2014 {fallback}{suffix}", 30))
    if not items and audience != "internal":
        items.append("\uacf5\uc720 \uae30\uc900 \u2014 \ub9c8\uc2a4\ud0b9 \ubc0f \ubc94\uc704")
    return items[:6]






__all__ = [
    "add_audience_badge",
    "add_block_content_panel",
    "add_detail_panel",
    "add_extra_contents_items",
    "add_insight_panel",
    "add_kpi_summary_slide",
    "add_masking_appendix_slide",
    "add_ordered_agenda_slides",
    "add_report_agenda_slide",
    "add_report_block_slide",
    "add_report_card_brand_overview",
    "add_report_card_country_detail",
    "add_report_card_cross_matrix",
    "add_report_card_growth_split",
    "add_report_card_season_calendar",
    "add_report_card_sku_order_reference",
    "add_report_card_trend_chart",
    "add_report_cover_slide",
    "add_report_footer",
    "add_season_calendar_detail_page",
    "add_section_index_slide",
    "add_snapshot_panel",
    "add_snapshot_table",
    "add_snapshot_table_page",
    "add_structured_agenda_slide",
    "add_structured_block_pages",
    "add_structured_block_slide",
    "add_structured_cover_slide",
    "add_structured_report_card_slide",
    "apply_region_table_cell",
    "brand_growth_metric_header",
    "brand_growth_period_label",
    "build_brand_table_rows",
    "build_region_insights",
    "build_region_table_rows",
    "capture_template_section_slides",
    "clear_cross_dynamic_shapes",
    "compute_sku_summaries",
    "expand_template_cross_slides",
    "fill_region_insights",
    "fill_template_appendix",
    "fill_template_brand",
    "fill_template_contents",
    "fill_template_cover",
    "fill_template_cross_or_share",
    "fill_template_extra_sections",
    "fill_template_ordered_cart_blocks",
    "fill_template_region",
    "fill_template_sku",
    "fill_template_summary",
    "fill_template_thanks",
    "format_report_month",
    "growth_metric_header",
    "growth_metric_label_for_key",
    "growth_metric_sentence_label",
    "growth_metric_value",
    "growth_period_note",
    "has_growth_metric",
    "region_page_descriptors",
    "region_section_rows",
    "region_share_display",
    "remove_unused_template_section_slides",
    "replace_brand_chart",
    "replace_brand_table",
    "replace_cross_matrix_content",
    "replace_region_table",
    "replace_sku_slide_content",
    "section_contents_title",
    "select_growth_metric",
    "set_section_data_title",
    "set_template_badge",
    "should_include_template_appendix",
    "should_include_template_cross_or_share",
    "should_paginate_ranking_card",
    "sku_block_summary",
    "template_contents_items",
    "write_dynamic_report_pptx",
    "write_template_report_pptx",
]
