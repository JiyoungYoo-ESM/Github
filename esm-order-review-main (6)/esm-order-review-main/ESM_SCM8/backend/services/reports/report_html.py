"""HTML 보고서 렌더러.

report_template_export 분해(IMPROVEMENT_PLAN.md 2단계). 마스킹된 블록을 최종 HTML 문서로
렌더링한다(PowerPoint/COM 비의존, Linux에서도 동일 산출). 계산·포맷·마스킹·공통텍스트
base 계층에만 의존한다."""

from __future__ import annotations

from datetime import datetime

from backend.services.reports.compute_cross import (
    cross_axis_labels,
    cross_metric_label,
    cross_scale_label,
    filter_valid_cross_rows,
    report_card_cross_matrix_rows,
)
from backend.services.reports.compute_series import (
    country_growth_amount_flow,
    format_season_calendar_value,
    is_sku_order_reference_block,
    report_card_growth_groups,
    report_card_season_calendar_rows,
    report_card_trend_series,
)
from backend.services.reports.compute_snapshot import (
    block_type_label,
    build_kpi_metrics,
    country_detail_display_amount,
    country_detail_display_krw,
    country_detail_groups,
    country_detail_item_label,
    display_table_header,
    normalize_structured_snapshot_rows,
    report_card_all_rows,
    report_card_rows,
    report_snapshot_rows_and_columns,
    structured_row_groups,
    structured_table_cell,
)
from backend.services.reports.formatting import (
    clamp_text,
    clean_metric_display,
    escape_attr,
    first_value,
    format_integer_like,
    html_text,
    row_sales_value,
    stringify_report_value,
)
from backend.services.reports.models import (
    AUDIENCE_LABELS,
    MaskingSummary,
    ReportBlockPayload,
    SECTION_LABELS,
)
from backend.services.reports.report_chrome import audience_badge, security_notice
from backend.services.reports.report_data import replace_report_block



def write_report_html(
    output_path: Path,
    *,
    audience: str,
    blocks: list[ReportBlockPayload],
    title: str | None,
    masking_summary: MaskingSummary | None = None,
) -> None:
    display_title = "분석 리포트" if (title or "").strip() in {"보고서 장바구니", "Report Cart"} else title or "분석 리포트"
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    block_nav = [
        f'<a href="#block-{index}"><span>{index:02d}</span>{html_text(clamp_text(block.title or "분석 블록", 42))}</a>'
        for index, block in enumerate(blocks, start=1)
    ]
    block_markup = "\n".join(
        report_html_block(block, index, audience)
        for index, block in enumerate(blocks, start=1)
    )
    summary_rows = "\n".join(
        f"""
        <div class="metric-card">
          <div class="metric-label">{html_text(label)}</div>
          <div class="metric-value">{html_text(value)}</div>
          <div class="metric-sub">{html_text(sub)}</div>
        </div>
        """
        for label, value, sub in build_kpi_metrics(blocks)[:4]
    )
    watermark = f'<div class="watermark">{html_text(audience_badge(audience))}</div>' if audience != "internal" else ""
    html = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html_text(display_title)}</title>
  <style>
{report_html_css()}
  </style>
</head>
<body>
  {watermark}
  <main class="report-shell">
    <section class="cover">
      <div>
        <p class="eyebrow">SILICON2 SCM ANALYTICS</p>
        <h1>{html_text(display_title)}</h1>
        <p class="lead">Report Cart Export</p>
      </div>
      <div class="cover-meta">
        <div><span>보고 대상</span><strong>{html_text(AUDIENCE_LABELS.get(audience, audience))}</strong></div>
        <div><span>생성일</span><strong>{html_text(generated_at)}</strong></div>
        <div><span>담긴 블록</span><strong>{len(blocks)}개</strong></div>
      </div>
      <p class="badge">{html_text(audience_badge(audience))}</p>
      <p class="security">{html_text(security_notice(audience))}</p>
    </section>

    <section class="summary">
      <p class="eyebrow">REPORT SUMMARY</p>
      <h2>보고서 구성</h2>
      <p class="section-lead">{len(blocks)}개 분석 블록을 선택한 용도 기준으로 마스킹해 HTML 파일로 생성했습니다.</p>
      <div class="metric-grid">{summary_rows}</div>
      <nav class="section-nav">{''.join(block_nav)}</nav>
    </section>

    <section class="section ordered-blocks">
      <p class="eyebrow">REPORT BLOCKS</p>
      <h2>담긴 순서대로 보는 분석</h2>
      <p class="section-lead">장바구니에 올려둔 순서와 동일합니다.</p>
      <div class="block-list">{block_markup}</div>
    </section>
  </main>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")


def report_html_section(section: str, blocks: list[ReportBlockPayload], audience: str) -> str:
    cards = "\n".join(report_html_block(block, index, audience) for index, block in enumerate(blocks, start=1))
    return f"""
    <section class="section" id="section-{escape_attr(section)}">
      <p class="eyebrow">{html_text(SECTION_LABELS.get(section, section).upper())}</p>
      <h2>{html_text(SECTION_LABELS.get(section, section))}</h2>
      <p class="section-lead">{len(blocks)}개 블록</p>
      <div class="block-list">{cards}</div>
    </section>
    """


def report_html_block(block: ReportBlockPayload, index: int, audience: str) -> str:
    card_visual = report_html_card_visual(block, audience)
    return f"""
    <article class="block-card" id="block-{index}">
      <header class="block-header">
        <span>BLOCK {index:02d} · {html_text(SECTION_LABELS.get(block.section or "summary", block.section or "요약"))}</span>
        <h3>{html_text(block.title or "분석 블록")}</h3>
        <p>{html_text(block.subtitle or block.meta or block.type)}</p>
      </header>
      {card_visual}
    </article>
    """


def report_html_card_visual(block: ReportBlockPayload, audience: str) -> str:
    html_snapshot = block.html_snapshot or stringify_report_value((block.params or {}).get("__html_snapshot", ""))
    if False and audience == "internal" and html_snapshot:
        return f'<div class="report-card-visual web-dom-snapshot">{html_snapshot}</div>'
    columns, rows = report_snapshot_rows_and_columns(block, audience)
    rows = normalize_structured_snapshot_rows(block, rows)
    block_type = str(block.type or "").strip().lower()
    if block_type in {"country_growth", "brand_growth"}:
        rising, declining = report_card_growth_groups(rows, block_type)
        return report_html_growth_card(rising, declining)
    if block_type == "brand_overview":
        row = rows[0] if rows else {}
        metrics = [
            ("매출", clean_metric_display(first_value(row, ("매출표시", "매출액"), ""))),
            ("원화 환산", clean_metric_display(row.get("원화표시", ""))),
            ("판매수량", format_integer_like(row.get("판매수량", ""))),
            ("SKU", f"{format_integer_like(row.get('SKU수', ''))}개" if clean_metric_display(row.get("SKU수", "")) != "-" else "-"),
        ]
        return report_html_metric_tiles(metrics)
    if block_type == "country_detail":
        return report_html_country_detail_card(block, rows)
    if is_sku_order_reference_block(block, rows):
        metrics = [
            (
                clean_metric_display(first_value(row, ("항목", "label"), "")),
                clean_metric_display(first_value(row, ("값", "value"), "")),
                clean_metric_display(first_value(row, ("보조값", "subValue", "원화표시", "비고"), "")),
            )
            for row in rows
        ]
        return report_html_metric_tiles([(label, f"{value} {sub}".strip()) for label, value, sub in metrics if label and label != "-"])
    if is_metric_tile_rows(rows):
        return report_html_metric_tiles(metric_tiles_from_rows(rows))
    if block_type == "cross_matrix":
        return report_html_cross_matrix(block, rows)
    if block_type == "season_calendar":
        return report_html_season_calendar(block, columns, rows)
    if block_type in {"sku_detail", "brand_top_sku_seasonality", "country_sku_season", "brand_comparison"}:
        return report_html_trend_card(block, rows)
    if should_html_show_full_ranking(block, rows):
        return report_html_full_ranking_card(block, columns, rows)
    card_rows = report_card_rows(block, columns, rows)
    return report_html_bar_card(card_rows)


def report_html_metric_tiles(metrics: list[tuple[str, str]]) -> str:
    items = "".join(
        f'<div class="web-card-tile"><span>{html_text(label)}</span><strong>{html_text(value or "-")}</strong></div>'
        for label, value in metrics
    )
    return f'<div class="report-card-visual web-card-tiles">{items}</div>'


def is_metric_tile_rows(rows: list[dict[str, object]]) -> bool:
    if not rows:
        return False
    sample = rows[: min(4, len(rows))]
    return all(
        clean_metric_display(first_value(row, ("항목", "label", "구분"), "")) not in {"", "-"}
        and clean_metric_display(first_value(row, ("값", "value", "매출표시", "매출액"), "")) not in {"", "-"}
        for row in sample
    ) and any(any(key in row for key in ("값", "보조값", "비고")) for row in sample)


def metric_tiles_from_rows(rows: list[dict[str, object]]) -> list[tuple[str, str]]:
    tiles: list[tuple[str, str]] = []
    for row in rows[:8]:
        label = clean_metric_display(first_value(row, ("항목", "label", "구분"), ""))
        value = clean_metric_display(first_value(row, ("값", "value", "매출표시", "매출액"), ""))
        sub = clean_metric_display(first_value(row, ("보조값", "원화표시", "비고"), ""))
        if label and label != "-":
            tiles.append((label, f"{value} {sub}".strip()))
    return tiles


def report_html_bar_card(card_rows: list[dict[str, object]]) -> str:
    if not card_rows:
        return '<div class="report-card-visual empty-state">카드로 표시할 데이터가 없습니다.</div>'
    items = "".join(
        f"""
        <div class="web-card-row">
          <div class="web-card-row-copy">
            <strong>{html_text(row.get("label", "-"))}</strong>
            {f'<span>{html_text(row.get("tag", ""))}</span>' if row.get("tag") else ""}
            {f'<small>{html_text(row.get("sub", ""))}</small>' if row.get("sub") else ""}
          </div>
          <em>{html_text(row.get("value", "-"))}</em>
          <div class="web-card-track"><i style="--w:{max(0, min(100, float(row.get("ratio", 0) or 0) * 100)):.1f}%"></i></div>
        </div>
        """
        for row in card_rows
    )
    return f'<div class="report-card-visual web-card-bars">{items}</div>'


def should_html_show_full_ranking(block: ReportBlockPayload, rows: list[dict[str, object]]) -> bool:
    if len(rows) <= 5:
        return False
    block_type = str(block.type or "").strip().lower()
    if block_type in {"country_detail", "country_growth", "brand_growth", "cross_matrix", "season_calendar"}:
        return False
    return str(block.kind or "").strip().lower() == "ranking"


def report_html_full_ranking_card(block: ReportBlockPayload, columns: list[str], rows: list[dict[str, object]]) -> str:
    ranked_rows = report_card_all_rows(block, columns, rows)
    body = "".join(
        f"""
        <tr>
          <td class="rank">{index}</td>
          <td><strong>{html_text(row.get("label", "-"))}</strong>{f'<small>{html_text(row.get("tag", ""))}</small>' if row.get("tag") else ""}</td>
          <td class="amount">{html_text(row.get("value", "-"))}{f'<small>{html_text(row.get("sub", ""))}</small>' if row.get("sub") else ""}</td>
        </tr>
        """
        for index, row in enumerate(ranked_rows, start=1)
    )
    return f"""
    <div class="report-card-visual web-full-ranking">
      <div class="web-ranking-summary">전체 {len(ranked_rows)}개 항목 · 매출 기준</div>
      <table><tbody>{body}</tbody></table>
    </div>
    """


def report_html_growth_card(rising: list[dict[str, object]], declining: list[dict[str, object]]) -> str:
    def group_markup(title: str, rows: list[dict[str, object]], tone: str) -> str:
        body = "".join(
            f"""
            <div class="growth-row {tone}">
              <strong>{html_text(row.get("country", "-"))}</strong>
              <span>{html_text(row.get("growth", "-"))}</span>
              <em>{html_text(country_growth_amount_flow(row))}</em>
            </div>
            """
            for row in rows[:5]
        ) or '<p class="empty-state">표시할 데이터가 없습니다.</p>'
        return f'<div class="growth-panel"><h4>{html_text(title)}</h4>{body}</div>'

    return f'<div class="report-card-visual web-growth-card">{group_markup("성장 상위", rising, "up")}{group_markup("감소 상위", declining, "down")}</div>'


def report_html_country_detail_card(block: ReportBlockPayload, rows: list[dict[str, object]]) -> str:
    groups = country_detail_groups(rows)
    summary = (groups.get("국가 요약") or [{}])[0]
    peak = (groups.get("월 최고 매출") or [{}])[0]
    brand_rows = groups.get("상위 브랜드", [])[:5]
    category_rows = groups.get("Top 5 카테고리", [])[:5]
    summary_markup = report_html_metric_tiles(
        [
            ("선택 국가", country_detail_item_label(summary) or stringify_report_value((block.params or {}).get("country", "-"))),
            ("총 매출", " · ".join(part for part in (country_detail_display_amount(summary), country_detail_display_krw(summary)) if part and part != "-")),
            ("점유율", clean_metric_display(first_value(summary, ("비고", "점유율"), ""))),
            ("월 최고 매출", " · ".join(part for part in (country_detail_item_label(peak), country_detail_display_amount(peak), country_detail_display_krw(peak)) if part and part != "-")),
        ]
    )
    brand_bars = report_html_bar_card(
        [
            {
                "label": country_detail_item_label(row),
                "tag": country_detail_display_krw(row),
                "value": country_detail_display_amount(row),
                "ratio": row_sales_value(row) / (max((row_sales_value(item) for item in brand_rows), default=0) or 1),
            }
            for row in brand_rows
        ]
    )
    categories = "".join(f'<span class="web-pill">{html_text(country_detail_item_label(row))}</span>' for row in category_rows if country_detail_item_label(row))
    category_markup = categories or '<span class="web-pill">데이터 없음</span>'
    return f'<div class="report-card-visual web-country-detail-card">{summary_markup}<section class="web-card-section"><h4>상위 브랜드 · 미리보기</h4>{brand_bars}</section><section class="web-card-section"><h4>Top 5 카테고리</h4><div class="web-pill-list">{category_markup}</div></section></div>'


def report_html_cross_matrix(block: ReportBlockPayload, rows: list[dict[str, object]]) -> str:
    row_label, column_label = cross_axis_labels(block, rows)
    metric_label = cross_metric_label(block, rows)
    scale_label = cross_scale_label(block, rows)
    matrix_rows = filter_valid_cross_rows(rows, row_label, column_label)
    matrix = report_card_cross_matrix_rows(block, matrix_rows, row_label, column_label, metric_label, scale_label)
    if not matrix.get("rows") or not matrix.get("columns"):
        return '<div class="report-card-visual empty-state">교차분석 데이터가 없습니다.</div>'
    headers = "".join(f'<span>{html_text(label)}</span>' for label in matrix["columns"])
    def cell_markup(row_label: str, column_label: str) -> str:
        display = stringify_report_value(matrix["displays"].get((row_label, column_label), "-"))
        krw_display = stringify_report_value(matrix.get("krw_displays", {}).get((row_label, column_label), ""))
        value = abs(float(matrix.get("display_values", {}).get((row_label, column_label), 0) or 0))
        max_value = float(matrix.get("max_abs", 0) or 0) or 1
        sub = f"<small>{html_text(krw_display)}</small>" if krw_display and krw_display != "-" else ""
        return f'<div class="matrix-cell" style="--a:{min(1, value / max_value):.2f}"><strong>{html_text(display)}</strong>{sub}</div>'

    body = "".join(
        f'<div class="matrix-label">{html_text(row_label)}</div>'
        + "".join(cell_markup(row_label, column_label) for column_label in matrix["columns"])
        + f'<div class="matrix-total">{html_text(matrix.get("row_totals", {}).get(row_label, "-"))}</div>'
        for row_label in matrix["rows"]
    )
    return f'<div class="report-card-visual web-matrix" style="--cols:{len(matrix["columns"])}"><div></div>{headers}{body}</div>'


def report_html_season_calendar(block: ReportBlockPayload, columns: list[str], rows: list[dict[str, object]]) -> str:
    season_rows = report_card_season_calendar_rows(block, columns, rows, limit=None)
    if not season_rows:
        return '<div class="report-card-visual empty-state">시즌 캘린더 데이터가 없습니다.</div>'
    month_header = "".join(f"<span>{month}월</span>" for month in range(1, 13))
    body = "".join(
        f"""
        <div class="season-web-row-label">
          <span class="season-expand">›</span>
          <span class="season-level">기능1</span>
          <strong>{html_text(row["label"])}</strong>
          <small>{html_text(row.get("sku_count", "1"))}개</small>
        </div>
        """
        + "".join(
            f'<i class="season-cell {"peak" if int(row.get("peak_month") or 0) == int(cell.get("month") or 0) else ""}" style="--a:{(float(cell.get("value", 0) or 0) / (float(row.get("max_value", 0) or 0) or 1)):.2f}">{html_text(format_season_calendar_value(float(cell.get("value", 0) or 0), float(row.get("max_value", 0) or 0), is_peak=int(row.get("peak_month") or 0) == int(cell.get("month") or 0)))}</i>'
            for cell in row.get("values", [])[:12]
        )
        + f'<em class="season-peak-label">{html_text(row.get("peak", "-"))}</em>'
        for row in season_rows[:13]
    )
    return f"""
    <div class="report-card-visual season-web-card">
      <section class="season-web-panel">
        <header class="season-web-head">
          <div>
            <h4>기능군 × 월별 수요 지수</h4>
            <p>기능군을 클릭하면 하위 기능이 펼쳐집니다</p>
          </div>
          <div class="season-web-actions">
            <div class="season-web-legend"><span>낮음</span><i></i><span>높음</span><b></b><span>피크월</span></div>
            <span class="season-check">✓</span>
          </div>
        </header>
        <div class="season-web-grid">
          <b>기능군</b><div class="season-month-head">{month_header}</div><b>피크</b>
          {body}
        </div>
      </section>
    </div>
    """


def report_html_trend_card(block: ReportBlockPayload, rows: list[dict[str, object]]) -> str:
    grouped = structured_row_groups(block, list(rows[0].keys()) if rows else [], rows)
    if len(grouped) > 1:
        sections = []
        for group_label, group_columns, group_rows in grouped:
            group_block = replace_report_block(block, snapshot={"columns": group_columns, "rows": group_rows})
            group_series = report_card_trend_series(group_block, group_rows)
            if group_series:
                body = report_html_single_trend_series(group_series)
            else:
                body = report_html_bar_card(report_card_rows(group_block, group_columns, group_rows))
            sections.append(
                f'<section class="web-card-section"><h4>{html_text(group_label or block_type_label(block.type or "summary"))}</h4>{body}</section>'
            )
        return f'<div class="report-card-visual web-composite-card">{"".join(sections)}</div>'

    series = report_card_trend_series(block, rows)
    if not series:
        return report_html_bar_card(report_card_rows(block, list(rows[0].keys()) if rows else [], rows))
    return f'<div class="report-card-visual web-trend-card">{report_html_single_trend_series(series)}</div>'


def report_html_single_trend_series(series: list[dict[str, object]]) -> str:
    labels = sorted({point["label"] for item in series for point in item.get("points", [])}, key=report_card_month_number)
    max_value = max((float(point.get("value", 0) or 0) for item in series for point in item.get("points", [])), default=1) or 1
    return "".join(
        f'<div class="trend-series"><strong>{html_text(item.get("name", "-"))}</strong>'
        + "".join(
            f'<span style="--h:{max(4, float(point.get("value", 0) or 0) / max_value * 100):.1f}%"><i></i><em>{html_text(point.get("label", ""))}</em></span>'
            for point in item.get("points", [])
        )
        + "</div>"
        for item in series[:4]
    )


def report_html_snapshot_table(block: ReportBlockPayload, audience: str) -> str:
    columns, rows = report_snapshot_rows_and_columns(block, audience)
    if not rows or not columns:
        return '<p class="empty-state">표시할 snapshot 데이터가 없습니다. 상세 값은 report_dataset.xlsx에서 확인할 수 있습니다.</p>'

    groups = structured_row_groups(block, columns, rows)
    if len(groups) > 1:
        return "\n".join(
            f"""
    <div class="snapshot-group">
      <h4>{html_text(group_label)}</h4>
      {report_html_table_for_rows(group_columns, group_rows)}
    </div>
    """
            for group_label, group_columns, group_rows in groups
        )
    return report_html_table_for_rows(columns, rows)


def report_html_table_for_rows(columns: list[str], rows: list[dict[str, object]]) -> str:
    header_cells = "".join(f"<th>{html_text(display_table_header(column))}</th>" for column in columns)
    body_rows = "\n".join(
        "<tr>"
        + "".join(f"<td>{html_text(structured_table_cell(column, row.get(column, '')))}</td>" for column in columns)
        + "</tr>"
        for row in rows
    )
    return f"""
    <div class="table-wrap">
      <table>
        <thead><tr>{header_cells}</tr></thead>
        <tbody>{body_rows}</tbody>
      </table>
    </div>
    """


def report_html_appendix(audience: str, masking_summary: MaskingSummary | None) -> str:
    if not masking_summary:
        return ""
    removed_columns = ", ".join(masking_summary.removed_columns) or "없음"
    rows = [
        ("공유 기준", audience_badge(audience)),
        ("제거된 민감 컬럼", removed_columns),
        ("익명화된 경쟁사", f"{masking_summary.anonymized_competitor_count}개"),
        ("거래처·고객 처리", masking_summary.client_identity_policy),
    ]
    items = "".join(f"<li><span>{html_text(label)}</span><strong>{html_text(value)}</strong></li>" for label, value in rows)
    return f"""
    <section class="section appendix">
      <p class="eyebrow">APPENDIX</p>
      <h2>공유 및 마스킹 기준</h2>
      <ul class="detail-list">{items}</ul>
      <p class="security">{html_text(security_notice(audience))}</p>
    </section>
    """


def report_html_css() -> str:
    return """
    :root {
      --brand: #e90035;
      --ink: #111827;
      --muted: #6b7280;
      --line: #e5e7eb;
      --soft: #f8fafc;
      --row: #fafafb;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #f3f4f6;
      color: var(--ink);
      font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", Arial, sans-serif;
      line-height: 1.55;
    }
    .report-shell {
      width: min(1180px, calc(100% - 40px));
      margin: 24px auto;
      background: #fff;
      border-left: 8px solid var(--brand);
      box-shadow: 0 20px 60px rgba(15, 23, 42, .12);
    }
    section { padding: 36px 48px; border-bottom: 1px solid var(--line); page-break-inside: avoid; }
    .cover { min-height: 520px; display: grid; align-content: center; gap: 22px; }
    .eyebrow { margin: 0 0 8px; color: var(--brand); font-size: 12px; font-weight: 900; letter-spacing: 0; }
    h1, h2, h3 { margin: 0; line-height: 1.15; letter-spacing: 0; }
    h1 { font-size: 44px; }
    h2 { font-size: 28px; }
    h3 { font-size: 20px; }
    .lead, .section-lead, .security, .block-header p, .metric-sub { color: var(--muted); font-weight: 700; }
    .cover-meta, .metric-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
    .cover-meta div, .metric-card, .block-card {
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 10px;
      padding: 16px;
    }
    .cover-meta span, .metric-label { display: block; color: var(--muted); font-size: 12px; font-weight: 900; }
    .cover-meta strong, .metric-value { display: block; margin-top: 6px; font-size: 20px; font-weight: 900; }
    .badge {
      display: inline-block;
      width: fit-content;
      margin: 0;
      border: 1px solid rgba(233, 0, 53, .25);
      border-radius: 999px;
      background: #fff1f4;
      color: var(--brand);
      padding: 8px 12px;
      font-size: 12px;
      font-weight: 900;
    }
    .section-nav { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
    .section-nav a {
      display: inline-flex;
      gap: 8px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--ink);
      padding: 8px 12px;
      text-decoration: none;
      font-size: 13px;
      font-weight: 900;
    }
    .section-nav span { color: var(--brand); }
    .block-list { display: grid; gap: 22px; margin-top: 18px; }
    .ordered-blocks { page-break-inside: auto; }
    .block-card { break-inside: avoid-page; page-break-inside: avoid; }
    .block-header { display: grid; gap: 6px; }
    .block-header span { color: var(--brand); font-size: 12px; font-weight: 900; }
    .insight {
      border-left: 3px solid var(--brand);
      background: var(--soft);
      padding: 12px 14px;
      font-weight: 800;
    }
    .report-card-visual {
      margin: 18px 0 0;
      border: 1px solid var(--line);
      border-radius: 24px;
      background: #fff;
      padding: 24px;
      box-shadow: 0 8px 18px rgba(15, 23, 42, .08);
    }
    .web-dom-snapshot {
      overflow: auto;
      border: 0;
      border-radius: 0;
      background: transparent;
      padding: 0;
      box-shadow: none;
    }
    .web-dom-snapshot [data-exported-web-card="true"] {
      max-width: 100%;
    }
    .web-card-tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
    .web-card-tile { border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #fff; }
    .web-card-tile span, .web-card-row span { display: block; color: var(--muted); font-size: 11px; font-weight: 900; }
    .web-card-row small { position: relative; z-index: 1; display: block; margin-top: 4px; color: var(--muted); font-size: 11px; font-weight: 800; }
    .web-card-tile strong { display: block; margin-top: 8px; font-size: 22px; font-weight: 900; }
    .web-card-bars, .web-growth-card { display: grid; gap: 14px; }
    .web-card-row { position: relative; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px 18px; overflow: visible; border: 0; border-radius: 0; padding: 0 0 8px; background: transparent; }
    .web-card-row-copy { min-width: 0; }
    .web-card-row strong, .growth-row strong { position: relative; z-index: 1; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink); font-weight: 900; }
    .web-card-row em, .growth-row span { position: relative; z-index: 1; color: #05060a; font-style: normal; font-weight: 900; white-space: nowrap; }
    .web-card-track { grid-column: 1 / -1; height: 6px; overflow: hidden; border-radius: 999px; background: #f0f0f0; box-shadow: inset 0 -1px 2px rgba(15,23,42,.16); }
    .web-card-track i { display: block; width: var(--w); height: 100%; border-radius: inherit; background: var(--brand); }
    .web-full-ranking { overflow: auto; }
    .web-ranking-summary { margin-bottom: 12px; color: var(--muted); font-size: 12px; font-weight: 900; }
    .web-full-ranking table { width: 100%; border-collapse: collapse; }
    .web-full-ranking td { border-bottom: 1px solid var(--line); padding: 10px 8px; vertical-align: middle; font-size: 13px; }
    .web-full-ranking tr:last-child td { border-bottom: 0; }
    .web-full-ranking .rank { width: 44px; color: var(--muted); font-weight: 900; }
    .web-full-ranking strong { display: block; font-weight: 900; }
    .web-full-ranking small { display: block; margin-top: 3px; color: var(--muted); font-size: 11px; font-weight: 800; }
    .web-full-ranking .amount { text-align: right; white-space: nowrap; font-weight: 900; }
    .web-growth-card { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .growth-panel { border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fff; }
    .growth-panel h4 { margin: 0 0 10px; font-size: 14px; }
    .growth-row { display: grid; grid-template-columns: 1fr auto; gap: 8px; padding: 9px 0; border-top: 1px solid var(--line); }
    .growth-row:first-of-type { border-top: 0; }
    .growth-row em { grid-column: 1 / -1; color: var(--muted); font-style: normal; font-size: 12px; }
    .growth-row.down span { color: #b42318; }
    .web-matrix { display: grid; grid-template-columns: minmax(120px, 1.1fr) repeat(var(--cols), minmax(70px, 1fr)); gap: 6px; align-items: stretch; }
    .web-matrix span, .matrix-label { color: var(--muted); font-size: 11px; font-weight: 900; }
    .matrix-cell { border-radius: 6px; background: rgba(233, 0, 53, calc(.08 + var(--a) * .6)); padding: 9px; text-align: right; font-size: 12px; font-weight: 900; }
    .season-web-card { display: block; border: 0; background: transparent; padding: 0; }
    .season-web-summary > .report-card-visual { margin: 0; border: 0; padding: 0; background: transparent; }
    .season-web-panel { overflow: hidden; border: 1px solid var(--line); border-radius: 8px; background: #fff; box-shadow: 0 6px 16px rgba(15,23,42,.06); }
    .season-web-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--line); padding: 18px 20px; }
    .season-web-head h4 { margin: 0; font-size: 15px; font-weight: 900; color: var(--ink); }
    .season-web-head p { display: inline; margin: 0 0 0 7px; color: var(--muted); font-size: 12px; font-weight: 800; }
    .season-web-head > div:first-child { display: flex; align-items: baseline; gap: 0; }
    .season-web-actions { display: flex; align-items: center; gap: 14px; }
    .season-web-legend { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; font-weight: 800; white-space: nowrap; }
    .season-web-legend i { display: inline-flex; width: 54px; height: 8px; border-radius: 999px; background: linear-gradient(90deg, rgba(233,0,53,.35), rgba(233,0,53,.6), rgba(233,0,53,.8), rgba(233,0,53,1)); }
    .season-web-legend b { display: inline-flex; width: 10px; height: 10px; border-radius: 3px; border: 2px solid var(--ink); background: var(--brand); }
    .season-check { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 8px; background: var(--brand); color: #fff; font-size: 18px; font-weight: 900; }
    .season-web-grid { display: grid; grid-template-columns: 420px 1fr 92px; align-items: center; }
    .season-web-grid > b { background: var(--soft); color: var(--muted); font-size: 12px; font-weight: 900; padding: 11px 16px; }
    .season-month-head { display: grid; grid-template-columns: repeat(12, minmax(32px, 1fr)); gap: 8px; background: var(--soft); color: var(--muted); padding: 11px 10px; text-align: center; font-size: 12px; font-weight: 900; }
    .season-web-row-label { display: flex; align-items: center; gap: 8px; min-height: 41px; border-top: 1px solid var(--line); padding: 8px 16px; }
    .season-web-row-label strong { font-size: 13px; font-weight: 900; }
    .season-web-row-label small { color: var(--muted); font-size: 11px; font-weight: 800; }
    .season-expand { display: grid; place-items: center; width: 24px; height: 24px; border: 1px solid var(--line); border-radius: 6px; color: var(--muted); font-size: 18px; font-weight: 700; line-height: 1; }
    .season-level { border: 1px solid var(--line); border-radius: 6px; background: var(--soft); color: var(--muted); padding: 3px 7px; font-size: 11px; font-weight: 900; }
    .season-cell { display: grid; place-items: center; min-height: 34px; margin: 5px 4px; border-radius: 6px; background: rgba(233, 0, 53, calc(.18 + var(--a) * .68)); color: var(--ink); border: 1px solid transparent; font-size: 10px; font-style: normal; font-weight: 900; }
    .season-cell.peak { border: 2px solid var(--ink); background: var(--brand); color: #fff; }
    .season-peak-label { display: grid; place-items: center; min-height: 41px; border-top: 1px solid var(--line); color: var(--ink); font-size: 13px; font-style: normal; font-weight: 900; }
    .web-trend-card { display: grid; gap: 14px; }
    .web-composite-card { display: grid; gap: 16px; }
    .web-card-section { border: 1px solid var(--line); border-radius: 8px; background: #fff; padding: 14px; }
    .web-card-section h4 { margin: 0 0 12px; font-size: 14px; font-weight: 900; }
    .trend-series { display: grid; grid-template-columns: 150px repeat(12, minmax(34px, 1fr)); gap: 6px; align-items: end; min-height: 120px; }
    .trend-series strong { align-self: center; font-size: 12px; }
    .trend-series span { display: grid; align-items: end; gap: 4px; height: 100px; }
    .trend-series i { display: block; min-height: 4px; height: var(--h); border-radius: 5px 5px 0 0; background: var(--brand); }
    .trend-series em { color: var(--muted); font-size: 10px; font-style: normal; text-align: center; }
    .snapshot-details { margin-top: 10px; }
    .snapshot-details summary { cursor: pointer; color: var(--muted); font-size: 12px; font-weight: 900; }
    .table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; }
    table { width: 100%; border-collapse: collapse; min-width: 720px; }
    th {
      background: var(--brand);
      color: #fff;
      text-align: left;
      font-size: 12px;
      padding: 10px;
      white-space: nowrap;
    }
    td {
      border-top: 1px solid var(--line);
      padding: 9px 10px;
      font-size: 12px;
      vertical-align: top;
    }
    tr:nth-child(even) td { background: var(--row); }
    .detail-list { display: grid; gap: 0; margin: 12px 0 0; padding: 0; list-style: none; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
    .detail-list li { display: grid; grid-template-columns: 180px 1fr; gap: 12px; padding: 10px 12px; border-top: 1px solid var(--line); }
    .detail-list li:first-child { border-top: 0; }
    .detail-list span { color: var(--muted); font-size: 12px; font-weight: 900; }
    .detail-list strong { font-size: 13px; }
    .empty-state { margin: 12px 0; border: 1px solid var(--line); border-radius: 10px; background: var(--soft); color: var(--muted); padding: 18px; font-weight: 800; }
    .watermark {
      position: fixed;
      inset: 42% auto auto 22%;
      transform: rotate(-28deg);
      color: rgba(233, 0, 53, .08);
      font-size: 76px;
      font-weight: 900;
      pointer-events: none;
      z-index: 0;
      white-space: nowrap;
    }
    @media print {
      body { background: #fff; }
      .report-shell { width: 100%; margin: 0; box-shadow: none; }
      section { page-break-inside: avoid; }
      .table-wrap { overflow: visible; }
    }
    @media (max-width: 760px) {
      .report-shell { width: 100%; margin: 0; border-left-width: 5px; }
      section { padding: 24px 18px; }
      h1 { font-size: 32px; }
      .cover-meta, .metric-grid { grid-template-columns: 1fr; }
      .detail-list li { grid-template-columns: 1fr; }
    }
    """


__all__ = [
    "write_report_html",
    "report_html_section",
    "report_html_block",
    "report_html_card_visual",
    "report_html_metric_tiles",
    "is_metric_tile_rows",
    "metric_tiles_from_rows",
    "report_html_bar_card",
    "should_html_show_full_ranking",
    "report_html_full_ranking_card",
    "report_html_growth_card",
    "report_html_country_detail_card",
    "report_html_cross_matrix",
    "report_html_season_calendar",
    "report_html_trend_card",
    "report_html_single_trend_series",
    "report_html_snapshot_table",
    "report_html_table_for_rows",
    "report_html_appendix",
    "report_html_css",
]
