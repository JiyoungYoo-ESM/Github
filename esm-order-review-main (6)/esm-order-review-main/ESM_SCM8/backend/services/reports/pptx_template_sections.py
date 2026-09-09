"""SKU, cross-analysis, and appendix sections for the branded PPTX template."""

from __future__ import annotations

from backend.services.reports.models import *  # noqa: F401,F403
from backend.services.reports.formatting import *  # noqa: F401,F403
from backend.services.reports.report_data import *  # noqa: F401,F403
from backend.services.reports.compute_cross import *  # noqa: F401,F403
from backend.services.reports.compute_snapshot import *  # noqa: F401,F403
from backend.services.reports.compute_series import *  # noqa: F401,F403
from backend.services.reports.report_chrome import *  # noqa: F401,F403
from backend.services.reports.pptx_prims import *  # noqa: F401,F403
from backend.services.reports.pptx_template_common import *  # noqa: F401,F403
from backend.services.reports.pptx_template_rankings import apply_region_table_cell

def fill_template_sku(prs, *, audience: str, blocks: list[ReportBlockPayload]) -> dict | None:
    intro = prs.slides[6]
    data = prs.slides[7]
    summaries = compute_sku_summaries(blocks)
    pages = chunk_rows(summaries, SKU_ROWS_PER_SLIDE)
    page_count = len(pages)
    base_title = "03 SKU별 판매 추이 및 국가 분포"
    set_shape_text(intro, 234, "SKU 판매 추이 분석")
    set_shape_text(intro, 235, "선택한 SKU의 매출 규모, 피크 시점, 국가별 판매 분포를 실제 데이터 기준으로 정리합니다.")
    set_section_data_title(data, 253, base_title, page_index=0, page_count=page_count)
    set_template_badge(data, 256, audience)
    replace_sku_slide_content(data, pages[0], summaries, audience, render_panel=True)
    if page_count <= 1:
        return None

    def render_page(slide, page_index: int) -> None:
        set_section_data_title(slide, 253, base_title, page_index=page_index, page_count=page_count)
        replace_sku_slide_content(slide, pages[page_index], summaries, audience, render_panel=False)

    return {"base_slide": data, "page_count": page_count, "render_page": render_page}


def compute_sku_summaries(blocks: list[ReportBlockPayload]) -> list[dict]:
    summaries = [sku_block_summary(block) for block in blocks]
    summaries = [summary for summary in summaries if summary["sku"] != "-"]
    return sorted(summaries, key=lambda summary: float(summary["sales_value"]), reverse=True)


def replace_sku_slide_content(slide, page_summaries: list[dict], all_summaries: list[dict], audience: str, *, render_panel: bool = True) -> None:
    try:
        from pptx.dml.color import RGBColor
        from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches, Pt
    except ImportError:
        return

    clear_named_dynamic_shapes(slide, "Silicon2 Sku Dynamic Table")
    for shape_id in (*range(244, 253), *range(257, 281), 281):
        delete_shape_by_id(slide, shape_id)

    include_krw = audience == "internal"
    headers = ["SKU", "매출 규모", "원화 환산", "피크/최고월", "상위 국가", "국가 비중"] if include_krw else ["SKU", "매출 규모", "피크/최고월", "상위 국가", "국가 비중"]
    table_rows = [
        [
            clamp_text(summary["sku"], 72),
            summary["sales_display"],
            *([summary["sales_krw_display"] or "-"] if include_krw else []),
            summary["peak_label_with_krw"] if include_krw else summary["peak_label"],
            summary["top_country"],
            summary["country_share"],
        ]
        for summary in page_summaries
    ]
    if not table_rows:
        table_rows = [["표시할 SKU 데이터 없음", "-", "-", "-", "-", "-"]] if include_krw else [["표시할 SKU 데이터 없음", "-", "-", "-", "-"]]

    row_count = len(table_rows) + 1
    table_shape = slide.shapes.add_table(row_count, len(headers), Inches(0.78), Inches(2.08), Inches(7.1), Inches(0.44 + 0.48 * len(table_rows)))
    table_shape.name = "Silicon2 Sku Dynamic Table"
    table = table_shape.table
    column_widths = [1.92, 0.93, 1.05, 1.48, 0.98, 0.74] if include_krw else [2.45, 1.18, 1.12, 1.36, 0.99]
    for index, column_width in enumerate(column_widths):
        table.columns[index].width = Inches(column_width)
    table.rows[0].height = Inches(0.44)
    for row_index in range(1, row_count):
        table.rows[row_index].height = Inches(0.48)
    for column_index, header in enumerate(headers):
        apply_region_table_cell(
            table.cell(0, column_index),
            header,
            RGBColor(191, 24, 28),
            RGBColor(255, 255, 255),
            bold=True,
            align=PP_ALIGN.CENTER,
            font_size=7.8 if include_krw else 8.5,
            MSO_ANCHOR=MSO_ANCHOR,
            Pt=Pt,
        )
    for row_index, values in enumerate(table_rows, start=1):
        fill_color = RGBColor(247, 249, 252) if row_index % 2 else RGBColor(255, 255, 255)
        for column_index, value in enumerate(values):
            right_columns = {1, 2} if include_krw else {1}
            center_start = 3 if include_krw else 2
            align = PP_ALIGN.RIGHT if column_index in right_columns else PP_ALIGN.CENTER if column_index >= center_start else PP_ALIGN.LEFT
            apply_region_table_cell(
                table.cell(row_index, column_index),
                value,
                fill_color,
                RGBColor(38, 49, 68),
                bold=column_index == 0,
                align=align,
                font_size=7.2 if include_krw else 7.8,
                MSO_ANCHOR=MSO_ANCHOR,
                Pt=Pt,
            )

    if not render_panel:
        return

    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.12), Inches(2.08), Inches(3.88), Inches(2.52))
    panel.fill.solid()
    panel.fill.fore_color.rgb = RGBColor(248, 250, 252)
    panel.line.color.rgb = RGBColor(226, 232, 240)
    panel.line.width = Pt(0.75)
    try:
        panel.adjustments[0] = 0.06
        panel.shadow.inherit = False
    except Exception:
        pass

    add_brand_chart_text(slide, Inches(8.38), Inches(2.38), Inches(3.32), Inches(0.22), "핵심 요약", 9.5, RGBColor(15, 23, 42), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
    divider = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(8.38), Inches(2.68), Inches(3.32), Inches(0.01))
    divider.fill.solid()
    divider.fill.fore_color.rgb = RGBColor(191, 24, 28)
    divider.line.fill.background()

    if all_summaries:
        top = all_summaries[0]
        top_amount = top["sales_display"]
        if audience == "internal" and top["sales_krw_display"] not in {"", "-"}:
            top_amount = f"{top['sales_display']} / {top['sales_krw_display']}"
        summary_lines = []
        if len(all_summaries) == 1:
            summary_lines.append(f"{top['sku']} 매출 규모는 {top_amount}입니다.")
        else:
            summary_lines.append(f"{top['sku']}가 비교 SKU 중 가장 큰 매출 규모({top_amount})입니다.")
        if top["top_country"] != "-":
            summary_lines.append(f"상위 국가는 {top['top_country']}이며 비중은 {top['country_share']}입니다.")
        peak_label = top["peak_label_with_krw"] if audience == "internal" else top["peak_label"]
        if peak_label != "-":
            summary_lines.append(f"피크/최고월은 {peak_label}입니다.")
        summary_text = "\n".join(summary_lines)
    else:
        summary_text = "선택된 SKU 블록이 없습니다."
    add_brand_chart_text(slide, Inches(8.38), Inches(2.94), Inches(3.32), Inches(1.18), clamp_text(summary_text, 170), 8.1, RGBColor(51, 65, 85), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)


def sku_block_summary(block: ReportBlockPayload) -> dict[str, object]:
    rows = snapshot_preview_rows(block)
    monthly_rows = [row for row in rows if stringify_report_value(first_value(row, ("구분", "type"), "")) == "월별 추이"]
    country_rows = [row for row in rows if stringify_report_value(first_value(row, ("구분", "type"), "")) == "국가 분포"]
    sku_name = clamp_text(block.title.replace(" SKU 분석", "").strip() or stringify_report_value(first_value(block.params or {}, ("sku",), "-")), 64)

    subtitle_amount = first_amount_display_from_text(block.subtitle)
    country_total = sum(max(row_sales_value(row), 0) for row in country_rows)
    monthly_total = sum(max(row_sales_value(row), 0) for row in monthly_rows)
    sales_value = numeric_value(subtitle_amount) or country_total or monthly_total or block_sales_value(block)
    sales_display = subtitle_amount or (format_large_amount(sales_value) if sales_value > 0 else "-")
    eur_krw_rate = block_exchange_rate(block) or infer_eur_krw_rate_from_rows(rows)
    sales_krw_display = first_krw_display_from_text(block.subtitle) or format_krw_amount(sales_value, eur_krw_rate)

    peak_candidates = [row for row in monthly_rows if stringify_report_value(first_value(row, ("비고", "note"), "")).strip()]
    peak = top_rows_by_sales(peak_candidates or monthly_rows, 1)[0] if (peak_candidates or monthly_rows) else {}
    peak_label = stringify_report_value(first_value(peak, ("항목", "월", "month"), "-"))
    peak_label_with_krw = peak_label
    if peak_label != "-" and display_amount(peak) != "-":
        peak_label = f"{peak_label} · {display_amount(peak)}"
        peak_label_with_krw = f"{peak_label_with_krw} · {amount_with_krw(peak, eur_krw_rate=eur_krw_rate)}"

    top_country = top_rows_by_sales(country_rows, 1)[0] if country_rows else {}
    top_country_name = stringify_report_value(first_value(top_country, ("항목", "국가", "country"), "-"))
    country_share = clean_metric_display(first_value(top_country, ("점유율", "share", "percent"), "-"))

    return {
        "sku": sku_name or "-",
        "sales_value": sales_value,
        "sales_display": sales_display,
        "sales_krw_display": sales_krw_display,
        "peak_label": peak_label,
        "peak_label_with_krw": peak_label_with_krw,
        "top_country": top_country_name,
        "country_share": country_share,
        "monthly_count": len(monthly_rows),
        "country_count": len(country_rows),
    }


def fill_template_cross_or_share(
    prs,
    *,
    audience: str,
    blocks: list[ReportBlockPayload],
    masking_summary: MaskingSummary | None,
) -> object | None:
    slide = prs.slides[8]
    set_template_badge(slide, 293, audience)
    if blocks:
        first_block = blocks[0]
        rows = section_rows([first_block])
        replace_cross_matrix_content(slide, [first_block], rows, audience)
        return slide

    removed = ", ".join(masking_summary.removed_columns) if masking_summary and masking_summary.removed_columns else "없음"
    count = masking_summary.anonymized_competitor_count if masking_summary else 0
    if audience == "internal":
        set_shape_text(slide, 290, "04 데이터 기준 · 내부 원본 데이터 취급 기준")
        fill_table_by_shape_id(
            slide,
            295,
            ["항목", "내부 기준", "적용 결과", "비고"],
            [
                ["경쟁사 실명", "표시", "원본 브랜드명 유지", "대외비"],
                ["원가·마진", "표시", "내부 지표 포함", "권한 관리"],
                ["거래처·고객명", "실명 유지", client_identity_policy(audience), "외부 공유 금지"],
            ],
        )
        set_shape_text(slide, 300, "내부 데이터 기준")
        set_shape_text(slide, 301, audience_badge(audience))
        set_shape_text(slide, 302, "원본")
        set_shape_text(slide, 303, "포함")
        set_shape_text(slide, 304, "대외비")
        return slide

    set_shape_text(slide, 290, "04 공유 전용 데이터 처리 기준")
    fill_table_by_shape_id(
        slide,
        295,
        ["처리 항목", "공개 범위", "적용 결과", "비고"],
        [
            ["경쟁사 실명", "익명화", f"{count}개 별칭", "경쟁사 A/B/C"],
            ["원가·마진", "제외", removed, "데이터 레이어 제거"],
            ["거래처·고객명", "대체", client_identity_policy(audience), "외부 필수 차단"],
        ],
    )
    set_shape_text(slide, 300, "필수 차단 기준")
    set_shape_text(slide, 301, audience_badge(audience))
    set_shape_text(slide, 302, f"{count}개")
    set_shape_text(slide, 303, "제거")
    set_shape_text(slide, 304, "검토")
    return slide


def expand_template_cross_slides(prs, *, base_slide, blocks: list[ReportBlockPayload], audience: str) -> None:
    if len(blocks) <= 1:
        return
    base_index = slide_index(prs, base_slide)
    if base_index < 0:
        return
    insert_after = base_index
    for block in blocks[1:]:
        slide = duplicate_slide_after(prs, base_slide, insert_after)
        replace_cross_matrix_content(slide, [block], section_rows([block]), audience)
        insert_after += 1


def replace_cross_matrix_content(slide, blocks: list[ReportBlockPayload], rows: list[dict[str, object]], audience: str) -> None:
    try:
        from pptx.dml.color import RGBColor
        from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches, Pt
    except ImportError:
        return

    clear_cross_dynamic_shapes(slide)
    for shape_id in (288, 289, *range(295, 317)):
        delete_shape_by_id(slide, shape_id)

    primary_block = blocks[0] if blocks else None
    row_label, column_label = cross_axis_labels(primary_block, rows)
    axis_label = f"{row_label} × {column_label}"
    metric_label = cross_metric_label(primary_block, rows)
    scale_label = cross_scale_label(primary_block, rows)
    valid_rows = filter_valid_cross_rows(rows, row_label, column_label)
    eur_krw_rate = blocks_exchange_rate(blocks) or infer_eur_krw_rate_from_cross_rows(valid_rows, metric_label)
    include_krw = audience == "internal" and "매출" in metric_label and scale_label == "금액"
    infer_share_from_rows = len(valid_rows) > 1
    table_rows = build_cross_table_rows(
        valid_rows,
        row_label,
        column_label,
        metric_label,
        include_krw=include_krw,
        eur_krw_rate=eur_krw_rate,
        infer_share=infer_share_from_rows,
    )

    set_shape_text(slide, 290, f"04 {axis_label} 교차분석")

    headers = [row_label, column_label, metric_label, "원화 환산", "비중"] if include_krw else [row_label, column_label, metric_label, "비중"]
    row_count = max(2, len(table_rows) + 1)
    table_shape = slide.shapes.add_table(row_count, len(headers), Inches(0.72), Inches(2.55), Inches(6.95), Inches(0.46 + 0.48 * (row_count - 1)))
    table_shape.name = "Silicon2 Cross Dynamic Table"
    table = table_shape.table
    # SKU 상품명이 들어가는 두 번째 열을 넓게 배정한다.
    column_widths = [1.30, 2.55, 1.00, 1.20, 0.90] if include_krw else [1.55, 2.85, 1.35, 1.20]
    for index, column_width in enumerate(column_widths):
        table.columns[index].width = Inches(column_width)
    table.rows[0].height = Inches(0.46)
    for row_index in range(1, row_count):
        table.rows[row_index].height = Inches(0.48)

    for column_index, header in enumerate(headers):
        apply_region_table_cell(
            table.cell(0, column_index),
            header,
            RGBColor(191, 24, 28),
            RGBColor(255, 255, 255),
            bold=True,
            align=PP_ALIGN.CENTER,
            font_size=7.8 if include_krw else 8.4,
            MSO_ANCHOR=MSO_ANCHOR,
            Pt=Pt,
        )

    if not table_rows:
        table_rows = [["표시할 교차 데이터 없음", "-", "-", "-", "-"]] if include_krw else [["표시할 교차 데이터 없음", "-", "-", "-"]]
    for row_index, values in enumerate(table_rows, start=1):
        fill_color = RGBColor(252, 239, 240) if row_index == 1 else RGBColor(247, 249, 252) if row_index % 2 else RGBColor(255, 255, 255)
        for column_index, value in enumerate(values):
            right_columns = {2, 3} if include_krw else {2}
            share_column = 4 if include_krw else 3
            align = PP_ALIGN.RIGHT if column_index in right_columns else PP_ALIGN.CENTER if column_index == share_column else PP_ALIGN.LEFT
            font_color = RGBColor(191, 24, 28) if row_index == 1 and column_index in right_columns else RGBColor(38, 49, 68)
            apply_region_table_cell(
                table.cell(row_index, column_index),
                value,
                fill_color,
                font_color,
                bold=row_index == 1 or column_index in (0, 1),
                align=align,
                font_size=7.0 if include_krw else 7.7,
                MSO_ANCHOR=MSO_ANCHOR,
                Pt=Pt,
            )

    top = top_rows_by_sales(valid_rows, 1)[0] if valid_rows else {}
    top_row_label = cross_dimension_value(top, row_label, row_axis_fallback_keys(row_label))
    top_column_label = cross_dimension_value(top, column_label, column_axis_fallback_keys(column_label))
    top_value = cross_metric_display(top, metric_label)
    top_krw_value = cross_krw_display(top, metric_label, eur_krw_rate=eur_krw_rate) if include_krw else ""
    top_value_with_krw = f"{top_value} / {top_krw_value}" if top_krw_value and top_krw_value != "-" else top_value
    total_metric_value = sum(cross_metric_numeric_value(row, metric_label) for row in valid_rows) if infer_share_from_rows else None
    top_share = cross_share_display(top, metric_label=metric_label, total_metric_value=total_metric_value)
    row_count_label = len(unique_cross_values(valid_rows, row_label, row_axis_fallback_keys(row_label)))
    column_count_label = len(unique_cross_values(valid_rows, column_label, column_axis_fallback_keys(column_label)))

    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.05), Inches(2.55), Inches(4.22), Inches(2.62))
    panel.name = "Silicon2 Cross Dynamic Panel"
    panel.fill.solid()
    panel.fill.fore_color.rgb = RGBColor(248, 250, 252)
    panel.line.color.rgb = RGBColor(226, 232, 240)
    panel.line.width = Pt(0.75)
    try:
        panel.adjustments[0] = 0.06
        panel.shadow.inherit = False
    except Exception:
        pass

    title_shape = add_brand_chart_text(slide, Inches(8.34), Inches(2.90), Inches(3.62), Inches(0.22), "교차분석 핵심 조합", 9.5, RGBColor(15, 23, 42), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
    title_shape.name = "Silicon2 Cross Dynamic Text"
    divider = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(8.34), Inches(3.20), Inches(3.62), Inches(0.01))
    divider.name = "Silicon2 Cross Dynamic Divider"
    divider.fill.solid()
    divider.fill.fore_color.rgb = RGBColor(191, 24, 28)
    divider.line.fill.background()

    headline = f"{top_row_label} 횞 {top_column_label}" if top else "-"
    # 긴 SKU 상품명은 길이에 따라 글자 크기를 줄여 전체를 표시한다.
    headline_text = clamp_text(headline, 76)
    headline_size = 17 if len(headline_text) <= 26 else 13 if len(headline_text) <= 44 else 11 if len(headline_text) <= 60 else 9.5
    headline_shape = add_brand_chart_text(slide, Inches(8.34), Inches(3.36), Inches(3.62), Inches(0.58), headline_text, headline_size, RGBColor(191, 24, 28), bold=True, align=PP_ALIGN.CENTER, Pt=Pt, PP_ALIGN=PP_ALIGN)
    headline_shape.name = "Silicon2 Cross Dynamic Text"
    metric_shape = add_brand_chart_text(slide, Inches(8.34), Inches(4.03), Inches(3.62), Inches(0.24), f"{metric_label} 기준: {top_value_with_krw}", 9.1, RGBColor(38, 49, 68), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
    metric_shape.name = "Silicon2 Cross Dynamic Text"
    share_text = f"비중 {top_share}" if top_share != "-" else f"{row_label} {row_count_label}개 · {column_label} {column_count_label}개 조합"
    share_shape = add_brand_chart_text(slide, Inches(8.34), Inches(4.35), Inches(3.62), Inches(0.24), share_text, 8.4, RGBColor(71, 85, 105), bold=True, Pt=Pt, PP_ALIGN=PP_ALIGN)
    share_shape.name = "Silicon2 Cross Dynamic Text"
    month_warning = stringify_report_value(primary_block.params.get("mom_month_warning", "") if primary_block else "").strip()
    growth_warning = stringify_report_value(primary_block.params.get("growth_period_warning", "") if primary_block else "").strip()
    scope_warning = stringify_report_value(primary_block.params.get("data_scope_warning", "") if primary_block else "").strip()
    warning = " · ".join(value for value in (month_warning, growth_warning, scope_warning) if value)
    basis_text = f"주의: {warning}" if warning else f"분석 기준: {metric_label} · {scale_label}"
    basis_color = RGBColor(191, 24, 28) if warning else RGBColor(100, 116, 139)
    basis_size = 6.6 if warning else 8.1
    basis_shape = add_brand_chart_text(slide, Inches(8.34), Inches(4.55), Inches(3.62), Inches(0.50), basis_text, basis_size, basis_color, bold=bool(warning), Pt=Pt, PP_ALIGN=PP_ALIGN)
    basis_shape.name = "Silicon2 Cross Dynamic Text"


def clear_cross_dynamic_shapes(slide) -> None:
    for shape in list(slide.shapes):
        if getattr(shape, "name", "").startswith("Silicon2 Cross Dynamic"):
            shape.element.getparent().remove(shape.element)


def fill_template_appendix(prs, *, audience: str, masking_summary: MaskingSummary | None) -> None:
    slide = prs.slides[9]
    set_template_badge(slide, 328, audience)
    set_shape_text(slide, 337, "· 데이터 기준: 보고서 생성 시점의 분석 데이터 기준")
    set_shape_text(slide, 338, "· 집계 구성 단위: 국가·권역, 브랜드, SKU, 교차분석 블록")
    set_shape_text(slide, 339, "· 통화 환산 기준: 화면에서 전달된 표시값 및 원본 수치 병행")
    removed = ", ".join(masking_summary.removed_columns) if masking_summary and masking_summary.removed_columns else "없음"
    set_shape_text(slide, 334, security_notice(audience))
    if audience == "internal":
        set_shape_text(slide, 340, "· 내부용 범위: 경쟁사 실명, 원가·마진, 거래처 집계값 포함 가능")
        set_shape_text(slide, 335, "데이터 취급 기준:\n내부 검토 목적을 위해 원본 집계값과 수익성 지표를 사용합니다. 외부 공유 시 별도 공유용 버전이 필요합니다.")
    else:
        set_shape_text(slide, 340, f"· 마스킹 적용: 제거 컬럼 {removed}, 경쟁사 익명화 {masking_summary.anonymized_competitor_count if masking_summary else 0}개")
        set_shape_text(slide, 335, f"공유 정책:\n{client_identity_policy(audience)}. 이후 표, 차트, 텍스트는 마스킹된 데이터만 사용합니다.")


def fill_template_thanks(prs, *, audience: str, title: str | None) -> None:
    slide = prs.slides[10]
    for shape_id in (346, 349, 350, 351):
        delete_shape_by_id(slide, shape_id)

__all__ = [
    "fill_template_sku",
    "compute_sku_summaries",
    "replace_sku_slide_content",
    "sku_block_summary",
    "fill_template_cross_or_share",
    "expand_template_cross_slides",
    "replace_cross_matrix_content",
    "clear_cross_dynamic_shapes",
    "fill_template_appendix",
    "fill_template_thanks",
]


