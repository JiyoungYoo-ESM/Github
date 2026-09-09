"""PPTX 드로잉·슬라이드 조작 프리미티브.

report_template_export 분해(IMPROVEMENT_PLAN.md 2단계)의 PPTX 저수준 계층. 슬라이드/
도형 생성·복제·삭제·이동, 텍스트박스·표 셀 기록 등 python-pptx 위의 얇은 헬퍼만 담는다.
python-pptx 타입(Pt/Inches/RGBColor/MSO_*/PP_ALIGN)은 각 함수가 인자로 주입받거나 함수
내부에서 지연 import하므로 이 모듈에는 pptx 최상위 import가 없다. 값 포맷은 reports.
formatting에만 의존한다(순환 없음). 도메인/렌더링 로직은 여기에 두지 않는다."""

from __future__ import annotations

from backend.services.reports.formatting import (
    clamp_text,
    disable_spellcheck,
    stringify_report_value,
)

def clone_textbox_below(slide, source_shape, dy: int, text: str, *, wrap: bool | None = None):
    """source_shape의 위치와 스타일을 복제해 텍스트박스를 dy만큼 아래에 만든다."""
    style = capture_text_style(source_shape.text_frame)
    box = slide.shapes.add_textbox(source_shape.left, source_shape.top + dy, source_shape.width, source_shape.height)
    text_frame = box.text_frame
    text_frame.clear()
    if wrap is not None:
        text_frame.word_wrap = wrap
    else:
        try:
            text_frame.word_wrap = source_shape.text_frame.word_wrap
        except Exception:
            text_frame.word_wrap = True
    try:
        text_frame.vertical_anchor = source_shape.text_frame.vertical_anchor
    except Exception:
        pass
    paragraph = text_frame.paragraphs[0]
    try:
        paragraph.alignment = source_shape.text_frame.paragraphs[0].alignment
    except Exception:
        pass
    run = paragraph.add_run()
    run.text = text
    apply_text_style(run, style)
    disable_spellcheck(run)
    return box




def add_brand_chart_text(slide, left, top, width, height, text: object, size: float, color, *, bold: bool = False, align=None, Pt, PP_ALIGN):
    shape = slide.shapes.add_textbox(left, top, width, height)
    text_frame = shape.text_frame
    text_frame.clear()
    text_frame.margin_left = 0
    text_frame.margin_right = 0
    text_frame.margin_top = 0
    text_frame.margin_bottom = 0
    text_frame.word_wrap = True
    paragraph = text_frame.paragraphs[0]
    paragraph.space_after = Pt(0)
    paragraph.alignment = align or PP_ALIGN.LEFT
    run = paragraph.add_run()
    run.text = stringify_report_value(text)
    run.font.name = "Malgun Gothic"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    disable_spellcheck(run)
    return shape


def mark_data_slide(slide) -> None:
    """분석 기간 라벨 표시 대상인 데이터 슬라이드를 도형 이름으로 표시한다."""
    if len(slide.shapes):
        slide.shapes[0].name = "Silicon2 Data Slide"


def slide_has_dynamic_data(slide) -> bool:
    """동적 데이터가 실제로 렌더링된 슬라이드인지 도형 이름으로 판별한다."""
    for shape in slide.shapes:
        name = str(getattr(shape, "name", ""))
        if name.startswith("Silicon2") and ("Dynamic" in name or "Data Slide" in name):
            return True
    return False


def add_slide_numbers(prs, *, period_label: str = "", period_scope: str = "data") -> None:
    """모든 슬라이드에 페이지 번호를, scope에 따라 분석 기간 라벨을 표시한다.

    period_scope="data": 데이터 슬라이드에만 표시한다.
    period_scope="body": 첫 장과 마지막 장을 제외한 본문 슬라이드에 표시한다.
    """
    try:
        from pptx.dml.color import RGBColor
        from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
        from pptx.util import Inches, Pt
    except ImportError:
        return

    total = len(prs.slides)
    if total <= 0:
        return
    page_width = Inches(1.05)
    page_height = Inches(0.18)
    page_left = int((prs.slide_width - page_width) / 2)
    page_top = int(prs.slide_height - Inches(0.55))
    # 분석 기간 라벨은 footer와 겹치지 않도록 위로 분리하고,
    # 본문 메타데이터로 읽히도록 페이지 번호보다 크게 표시한다.
    period_width = Inches(5.6)
    period_height = Inches(0.28)
    period_left = int((prs.slide_width - period_width) / 2)
    period_top = int(prs.slide_height - Inches(1.08))
    period_text = f"분석 기간: {period_label}" if period_label else ""
    for index, slide in enumerate(prs.slides, start=1):
        for shape in list(slide.shapes):
            if getattr(shape, "name", "") in {"Silicon2 Slide Number", "Silicon2 Analysis Period"}:
                shape.element.getparent().remove(shape.element)
        # 분석 기간 라벨은 선택한 scope에 해당하는 본문 데이터 슬라이드에만 표시한다.
        show_period = bool(period_text) and (
            slide_has_dynamic_data(slide) if period_scope == "data" else 1 < index < total
        )
        if show_period:
            period_shape = slide.shapes.add_textbox(period_left, period_top, period_width, period_height)
            period_shape.name = "Silicon2 Analysis Period"
            period_frame = period_shape.text_frame
            period_frame.clear()
            period_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
            period_frame.margin_left = 0
            period_frame.margin_right = 0
            period_frame.margin_top = 0
            period_frame.margin_bottom = 0
            period_paragraph = period_frame.paragraphs[0]
            period_paragraph.alignment = PP_ALIGN.CENTER
            period_paragraph.space_after = Pt(0)
            period_run = period_paragraph.add_run()
            period_run.text = period_text
            period_run.font.name = "Malgun Gothic"
            period_run.font.size = Pt(10.5)
            period_run.font.bold = True
            period_run.font.color.rgb = RGBColor(51, 65, 85)
            disable_spellcheck(period_run)
        shape = slide.shapes.add_textbox(page_left, page_top, page_width, page_height)
        shape.name = "Silicon2 Slide Number"
        text_frame = shape.text_frame
        text_frame.clear()
        text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        text_frame.margin_left = 0
        text_frame.margin_right = 0
        text_frame.margin_top = 0
        text_frame.margin_bottom = 0
        paragraph = text_frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.CENTER
        paragraph.space_after = Pt(0)
        run = paragraph.add_run()
        run.text = f"{index:02d} / {total:02d}"
        run.font.name = "Malgun Gothic"
        run.font.size = Pt(7.5)
        run.font.bold = True
        run.font.color.rgb = RGBColor(154, 161, 173)
        disable_spellcheck(run)


def set_shape_text(slide, shape_id: int, text: object) -> None:
    shape = find_shape(slide, shape_id)
    if not shape or not hasattr(shape, "text_frame"):
        return
    text_frame = shape.text_frame
    style = capture_text_style(text_frame)
    text_frame.clear()
    lines = str(text or "").splitlines() or [""]
    for index, line in enumerate(lines):
        paragraph = text_frame.paragraphs[0] if index == 0 else text_frame.add_paragraph()
        run = paragraph.add_run()
        run.text = line
        apply_text_style(run, style)


def find_shape(slide, shape_id: int):
    for shape in slide.shapes:
        if shape.shape_id == shape_id:
            return shape
    return None


def delete_shape_by_id(slide, shape_id: int) -> None:
    shape = find_shape(slide, shape_id)
    if not shape:
        return
    shape.element.getparent().remove(shape.element)


def delete_slide(prs, slide_index: int) -> None:
    if slide_index < 0 or slide_index >= len(prs.slides):
        return
    slide_id_list = prs.slides._sldIdLst
    slide_id = list(slide_id_list)[slide_index]
    prs.part.drop_rel(slide_id.rId)
    slide_id_list.remove(slide_id)


def delete_slide_by_ref(prs, slide) -> None:
    index = slide_index(prs, slide)
    if index >= 0:
        delete_slide(prs, index)


def slide_index(prs, target_slide) -> int:
    for index, slide in enumerate(prs.slides):
        if slide.part == target_slide.part:
            return index
    return -1


def duplicate_slide_after(prs, source_slide, after_index: int):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    for shape in list(slide.shapes):
        shape.element.getparent().remove(shape.element)

    rel_id_map: dict[str, str] = {}
    for rel_id, rel in source_slide.part.rels.items():
        if "notesSlide" in rel.reltype or "slideLayout" in rel.reltype:
            continue
        try:
            rel_id_map[rel_id] = slide.part.rels._add_relationship(rel.reltype, rel._target, getattr(rel, "is_external", False))
        except ValueError:
            pass
    for shape in source_slide.shapes:
        element = deepcopy(shape.element)
        for child in element.iter():
            for attr_name, attr_value in list(child.attrib.items()):
                if attr_value in rel_id_map:
                    child.attrib[attr_name] = rel_id_map[attr_value]
        slide.shapes._spTree.insert_element_before(element, "p:extLst")

    slide_id_list = prs.slides._sldIdLst
    new_slide_id = list(slide_id_list)[-1]
    slide_id_list.remove(new_slide_id)
    slide_id_list.insert(after_index + 1, new_slide_id)
    return prs.slides[after_index + 1]


def chunk_rows(rows: list, size: int) -> list[list]:
    if size <= 0:
        return [list(rows)]
    return [list(rows[start : start + size]) for start in range(0, len(rows), size)] or [[]]


def clear_named_dynamic_shapes(slide, prefix: str) -> None:
    """복제된 슬라이드에 남은 이전 페이지의 동적 도형을 이름 prefix로 제거한다."""
    for shape in list(slide.shapes):
        if str(getattr(shape, "name", "")).startswith(prefix):
            shape.element.getparent().remove(shape.element)


def expand_section_pages(prs, *, base_slide, page_count: int, render_page) -> None:
    """base_slide에 0페이지를 채운 뒤 나머지를 복제 슬라이드로 이어 붙인다.

    render_page(slide, page_index)가 각 슬라이드의 해당 페이지를 렌더링한다.
    슬라이드 참조를 기준으로 위치를 찾아 다른 섹션 삽입의 영향을 받지 않는다.
    """
    if base_slide is None or page_count <= 1:
        return
    insert_after = slide_index(prs, base_slide)
    if insert_after < 0:
        return
    for page_index in range(1, page_count):
        new_slide = duplicate_slide_after(prs, base_slide, insert_after)
        render_page(new_slide, page_index)
        insert_after += 1


def move_slide_after(prs, slide, ref_slide) -> None:
    """이미 추가된 slide를 ref_slide 바로 뒤로 이동한다."""
    ref_index = slide_index(prs, ref_slide)
    slide_idx = slide_index(prs, slide)
    if ref_index < 0 or slide_idx < 0 or slide_idx == ref_index + 1:
        return
    slide_id_list = prs.slides._sldIdLst
    element = list(slide_id_list)[slide_idx]
    slide_id_list.remove(element)
    insert_at = ref_index + 1 if slide_idx > ref_index else ref_index
    slide_id_list.insert(insert_at, element)


def move_slide_before(prs, slide, ref_slide) -> None:
    """이미 추가된 slide를 ref_slide 바로 앞으로 이동한다."""
    ref_index = slide_index(prs, ref_slide)
    slide_idx = slide_index(prs, slide)
    if ref_index < 0 or slide_idx < 0 or slide_idx == ref_index - 1:
        return
    slide_id_list = prs.slides._sldIdLst
    element = list(slide_id_list)[slide_idx]
    slide_id_list.remove(element)
    insert_at = ref_index if slide_idx > ref_index else ref_index - 1
    slide_id_list.insert(insert_at, element)


def fill_table_by_shape_id(slide, shape_id: int, headers: list[str], rows: list[list[object]]) -> None:
    shape = find_shape(slide, shape_id)
    if not shape or not getattr(shape, "has_table", False):
        return
    table = shape.table
    column_count = len(table.columns)
    for column_index in range(column_count):
        set_cell_text(table.cell(0, column_index), headers[column_index] if column_index < len(headers) else "")
    for row_index in range(1, len(table.rows)):
        source = rows[row_index - 1] if row_index - 1 < len(rows) else []
        for column_index in range(column_count):
            set_cell_text(table.cell(row_index, column_index), source[column_index] if column_index < len(source) else "")


def set_cell_text(cell, text: object) -> None:
    style = capture_text_style(cell.text_frame)
    cell.text = clamp_text(stringify_report_value(text), 48)
    for paragraph in cell.text_frame.paragraphs:
        for run in paragraph.runs:
            apply_text_style(run, style)


def capture_text_style(text_frame) -> dict[str, object]:
    for paragraph in text_frame.paragraphs:
        for run in paragraph.runs:
            font = run.font
            style: dict[str, object] = {
                "name": font.name,
                "size": font.size,
                "bold": font.bold,
                "italic": font.italic,
            }
            try:
                style["rgb"] = font.color.rgb
            except Exception:
                style["rgb"] = None
            return style
    return {"name": "Malgun Gothic", "size": None, "bold": None, "italic": None, "rgb": None}


def apply_text_style(run, style: dict[str, object]) -> None:
    font = run.font
    try:
        font.name = str(style.get("name") or "Malgun Gothic")
    except Exception:
        pass
    if style.get("size") is not None:
        font.size = style["size"]
    if style.get("bold") is not None:
        font.bold = bool(style["bold"])
    if style.get("italic") is not None:
        font.italic = bool(style["italic"])
    if style.get("rgb") is not None:
        try:
            font.color.rgb = style["rgb"]
        except Exception:
            pass


def add_cross_cell_box(slide, x, y, w, h, fill, line_color, RGBColor, MSO_SHAPE, Pt) -> None:
    box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    box.name = "Silicon2 Cross Matrix Cell"
    box.fill.solid()
    box.fill.fore_color.rgb = fill
    box.line.color.rgb = line_color
    box.line.width = Pt(0.35)


def add_metric_tile(slide, left, top, width, height, label: str, value: str, Inches, RGBColor, MSO_SHAPE) -> None:
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(255, 255, 255)
    shape.line.color.rgb = RGBColor(226, 228, 232)
    add_textbox(slide, left + Inches(0.16), top + Inches(0.12), width - Inches(0.32), Inches(0.22), label, 9, RGBColor(105, 112, 127), bold=True)
    add_textbox(slide, left + Inches(0.16), top + Inches(0.43), width - Inches(0.32), Inches(0.28), value, 13, RGBColor(5, 6, 10), bold=True)


def add_slide_background(slide, prs, color, RGBColor, MSO_SHAPE) -> None:
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = color
    bg.line.fill.background()


def add_slide_accent(slide, prs, Inches, RGBColor, MSO_SHAPE, *, width: float = 0.12) -> None:
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(width), prs.slide_height)
    bar.fill.solid()
    bar.fill.fore_color.rgb = RGBColor(233, 0, 53)
    bar.line.fill.background()


def add_textbox(slide, left, top, width, height, text: object, size: int, color, *, bold: bool = False) -> None:
    from pptx.util import Pt

    shape = slide.shapes.add_textbox(left, top, width, height)
    text_frame = shape.text_frame
    text_frame.clear()
    text_frame.margin_left = 0
    text_frame.margin_right = 0
    text_frame.margin_top = 0
    text_frame.margin_bottom = 0
    lines = clamp_text(text).splitlines() or [""]
    for index, line in enumerate(lines):
        paragraph = text_frame.paragraphs[0] if index == 0 else text_frame.add_paragraph()
        paragraph.space_after = Pt(0)
        run = paragraph.add_run()
        run.text = line
        run.font.name = "Malgun Gothic"
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        disable_spellcheck(run)
    return shape


def add_slide_header(slide, eyebrow: str, title: str, subtitle: str, audience: str, Inches, RGBColor, MSO_SHAPE) -> None:
    add_textbox(slide, Inches(0.72), Inches(0.45), Inches(2.8), Inches(0.25), clamp_text(eyebrow, 34), 9, RGBColor(233, 0, 53), bold=True)
    add_textbox(slide, Inches(0.72), Inches(0.78), Inches(8.0), Inches(0.46), clamp_text(title, 52), 22, RGBColor(5, 6, 10), bold=True)
    add_textbox(slide, Inches(0.74), Inches(1.32), Inches(8.7), Inches(0.24), clamp_text(subtitle, 76), 10, RGBColor(105, 112, 127), bold=True)




# Final overrides for report-card rendering. Some legacy literals above were
# introduced through a bad encoding pass; these definitions keep runtime behavior
# tied to the normal Korean/English snapshot keys sent by the frontend.


__all__ = [
    "clone_textbox_below",
    "add_brand_chart_text",
    "mark_data_slide",
    "slide_has_dynamic_data",
    "add_slide_numbers",
    "set_shape_text",
    "find_shape",
    "delete_shape_by_id",
    "delete_slide",
    "delete_slide_by_ref",
    "slide_index",
    "duplicate_slide_after",
    "chunk_rows",
    "clear_named_dynamic_shapes",
    "expand_section_pages",
    "move_slide_after",
    "move_slide_before",
    "fill_table_by_shape_id",
    "set_cell_text",
    "capture_text_style",
    "apply_text_style",
    "add_cross_cell_box",
    "add_metric_tile",
    "add_slide_background",
    "add_slide_accent",
    "add_textbox",
    "add_slide_header",
]
