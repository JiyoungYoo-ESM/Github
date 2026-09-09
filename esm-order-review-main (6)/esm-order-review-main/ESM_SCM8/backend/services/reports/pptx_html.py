"""PPTX → HTML 변환 렌더러.

생성된 .pptx를 슬라이드 PNG(soffice/PowerPoint) 또는 도형 단위 HTML로 변환한다.
report_template_export 분해(IMPROVEMENT_PLAN.md 2단계)에서 의존성 그래프상 leaf로
확인된 클러스터(out=0) — 값 포맷 프리미티브(html_text)에만 의존하고 다른 렌더러/계산
계층에 의존하지 않아 독립 추출된다."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from base64 import b64encode
from pathlib import Path

from backend.services.reports.formatting import html_text

def convert_pptx_to_html(pptx_path: Path, output_path: Path) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        image_paths = render_pptx_slides_to_png(pptx_path, Path(tmp))
        slides = pptx_slide_images_to_html(image_paths)

    title = html_text(pptx_path.stem)
    html = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
{pptx_image_html_css()}
  </style>
</head>
<body>
  <main class="ppt-deck" aria-label="PPT HTML preview">
    {slides}
  </main>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    return output_path


def render_pptx_slides_to_png(pptx_path: Path, output_dir: Path) -> list[Path]:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        raise_html_renderer_error("PowerShell was not found.")

    pptx_path = pptx_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        render_dir = Path(tmp)
        temp_pptx_path = render_dir / "source.pptx"
        shutil.copy2(pptx_path, temp_pptx_path)
        with PDF_CONVERSION_LOCK:
            run_powerpoint_png_export(powershell, temp_pptx_path, render_dir)

        rendered_paths = sorted(render_dir.glob("slide_*.png"))
        if not rendered_paths:
            raise_html_renderer_error("PowerPoint did not create slide images.")

        image_paths: list[Path] = []
        for rendered_path in rendered_paths:
            output_path = output_dir / rendered_path.name
            shutil.copy2(rendered_path, output_path)
            image_paths.append(output_path)
        return image_paths


def run_powerpoint_png_export(powershell: str, pptx_path: Path, output_dir: Path) -> None:
    script = f"""
$ErrorActionPreference = "Stop"
$pptxPath = {json.dumps(str(pptx_path))}
$outputDir = {json.dumps(str(output_dir))}
$powerPoint = $null
$presentation = $null
try {{
  $powerPoint = New-Object -ComObject PowerPoint.Application
  $presentation = $powerPoint.Presentations.Open($pptxPath, $true, $true, $false)
  $slideWidth = [double]$presentation.PageSetup.SlideWidth
  $slideHeight = [double]$presentation.PageSetup.SlideHeight
  $exportWidth = 1600
  if ($slideWidth -gt 0) {{
    $exportHeight = [int][Math]::Round($exportWidth * $slideHeight / $slideWidth)
  }} else {{
    $exportHeight = 900
  }}
  for ($i = 1; $i -le $presentation.Slides.Count; $i++) {{
    $path = Join-Path $outputDir ("slide_{{0:D3}}.png" -f $i)
    $presentation.Slides.Item($i).Export($path, "PNG", $exportWidth, $exportHeight)
  }}
}} finally {{
  if ($presentation -ne $null) {{ $presentation.Close() | Out-Null }}
  if ($powerPoint -ne $null) {{ $powerPoint.Quit() | Out-Null }}
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}}
"""
    attempts = 3
    last_error = ""
    for attempt in range(1, attempts + 1):
        completed = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode == 0:
            return
        last_error = completed.stderr.strip()
        print(f"[perf][report_html] powerpoint_png_retry attempt={attempt}/{attempts} error={last_error[:160]}", flush=True)
        if attempt < attempts:
            time.sleep(2 * attempt)
    raise_html_renderer_error(last_error)


def pptx_slide_images_to_html(image_paths: list[Path]) -> str:
    slides: list[str] = []
    for index, image_path in enumerate(image_paths, start=1):
        data = b64encode(image_path.read_bytes()).decode("ascii")
        slides.append(
            f"""
    <section class="ppt-slide" aria-label="slide {index}">
      <img class="ppt-slide-image" src="data:image/png;base64,{data}" alt="slide {index}" />
    </section>
            """
        )
    return "\n".join(slides)


def pptx_image_html_css() -> str:
    return """
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #e5e7eb;
      color: #111827;
      font-family: Arial, sans-serif;
    }
    .ppt-deck {
      width: min(100vw, 1600px);
      margin: 0 auto;
      padding: 24px 0;
    }
    .ppt-slide {
      width: 100%;
      margin: 0 auto 24px;
      background: #fff;
      box-shadow: 0 1px 3px rgba(15, 23, 42, 0.18);
    }
    .ppt-slide-image {
      display: block;
      width: 100%;
      height: auto;
    }
    @media print {
      body { background: #fff; }
      .ppt-deck { width: 100%; padding: 0; }
      .ppt-slide { margin: 0; box-shadow: none; page-break-after: always; }
    }
    """


def raise_html_renderer_error(detail: str | None = None) -> None:
    message = "HTML export failed because the backend could not render the generated PowerPoint slides."
    if detail:
        message = f"{message} ({detail})"
    raise HTTPException(status_code=501, detail=message)


def pptx_slide_to_html(slide, *, slide_index: int, scale: float, width: float, height: float) -> str:
    shapes = "\n".join(
        pptx_shape_to_html(shape, scale=scale, z_index=index + 1)
        for index, shape in enumerate(slide.shapes)
    )
    return f"""
    <section class="ppt-slide" style="width:{width}px;height:{height}px" aria-label="slide {slide_index}">
      {shapes}
      <span class="ppt-slide-number">{slide_index:02d}</span>
    </section>
    """


def pptx_shape_to_html(shape, *, scale: float, z_index: int) -> str:
    try:
        if getattr(shape, "has_table", False):
            return pptx_table_to_html(shape, scale=scale, z_index=z_index)
        if is_pptx_picture(shape):
            return pptx_picture_to_html(shape, scale=scale, z_index=z_index)
        if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
            return pptx_text_shape_to_html(shape, scale=scale, z_index=z_index)
        return pptx_box_shape_to_html(shape, scale=scale, z_index=z_index)
    except Exception as exc:
        return f'<div class="ppt-shape ppt-shape-error" style="{pptx_shape_style(shape, scale, z_index)}">shape render skipped: {html_text(exc)}</div>'


def pptx_text_shape_to_html(shape, *, scale: float, z_index: int) -> str:
    text_frame = shape.text_frame
    runs = list(iter_pptx_runs(text_frame))
    font_size = first_pptx_font_size(runs, default=12)
    color = first_pptx_font_color(runs) or "#111827"
    weight = "900" if any(bool(run.font.bold) for run in runs if getattr(run, "font", None)) else "700"
    font_style = "italic" if any(bool(run.font.italic) for run in runs if getattr(run, "font", None)) else "normal"
    align = pptx_paragraph_align(text_frame.paragraphs[0] if text_frame.paragraphs else None)
    style = pptx_shape_style(shape, scale, z_index)
    style += f"color:{color};font-size:{round(font_size * scale, 2)}px;font-weight:{weight};font-style:{font_style};text-align:{align};"
    html = "<br />".join(html_text(line) for line in text_frame.text.splitlines()) or "&nbsp;"
    return f'<div class="ppt-shape ppt-text" style="{style}">{html}</div>'


def pptx_table_to_html(shape, *, scale: float, z_index: int) -> str:
    table = shape.table
    col_widths = [round(int(column.width) * scale, 2) for column in table.columns]
    colgroup = "".join(f'<col style="width:{width}px" />' for width in col_widths)
    rows: list[str] = []
    for row_index, row in enumerate(table.rows):
        cells = []
        tag = "th" if row_index == 0 else "td"
        for cell in row.cells:
            text = "<br />".join(html_text(line) for line in cell.text.splitlines()) or "&nbsp;"
            cells.append(f"<{tag}>{text}</{tag}>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"""
    <div class="ppt-shape ppt-table-wrap" style="{pptx_shape_style(shape, scale, z_index)}">
      <table>{colgroup}<tbody>{''.join(rows)}</tbody></table>
    </div>
    """


def pptx_picture_to_html(shape, *, scale: float, z_index: int) -> str:
    image = shape.image
    data = b64encode(image.blob).decode("ascii")
    return f'<img class="ppt-shape ppt-picture" style="{pptx_shape_style(shape, scale, z_index)}" src="data:{image.content_type};base64,{data}" alt="" />'


def pptx_box_shape_to_html(shape, *, scale: float, z_index: int) -> str:
    fill = pptx_fill_color(shape)
    border = pptx_line_color(shape)
    if fill == "transparent" and border == "transparent":
        return ""
    return f'<div class="ppt-shape ppt-box" style="{pptx_shape_style(shape, scale, z_index)}"></div>'


def pptx_shape_style(shape, scale: float, z_index: int) -> str:
    left = round(int(getattr(shape, "left", 0)) * scale, 2)
    top = round(int(getattr(shape, "top", 0)) * scale, 2)
    width = round(int(getattr(shape, "width", 0)) * scale, 2)
    height = round(int(getattr(shape, "height", 0)) * scale, 2)
    fill = pptx_fill_color(shape)
    border = pptx_line_color(shape)
    rotation = float(getattr(shape, "rotation", 0) or 0)
    transform = f"transform:rotate({rotation}deg);" if rotation else ""
    return (
        f"left:{left}px;top:{top}px;width:{width}px;height:{height}px;"
        f"z-index:{z_index};background:{fill};border:1px solid {border};{transform}"
    )


def is_pptx_picture(shape) -> bool:
    return hasattr(shape, "image")


def iter_pptx_runs(text_frame):
    for paragraph in text_frame.paragraphs:
        for run in paragraph.runs:
            yield run


def first_pptx_font_size(runs: list[object], *, default: float) -> float:
    for run in runs:
        size = getattr(getattr(run, "font", None), "size", None)
        if size is not None:
            return float(size.pt)
    return default


def first_pptx_font_color(runs: list[object]) -> str | None:
    for run in runs:
        font = getattr(run, "font", None)
        if font is None:
            continue
        color = pptx_color_to_css(getattr(font, "color", None))
        if color:
            return color
    return None


def pptx_paragraph_align(paragraph) -> str:
    value = getattr(paragraph, "alignment", None)
    if value is None:
        return "left"
    text = str(value).lower()
    if "center" in text or text == "center (2)":
        return "center"
    if "right" in text:
        return "right"
    return "left"


def pptx_fill_color(shape) -> str:
    fill = getattr(shape, "fill", None)
    if fill is None:
        return "transparent"
    try:
        color = fill.fore_color
    except Exception:
        return "transparent"
    return pptx_color_to_css(color) or "transparent"


def pptx_line_color(shape) -> str:
    line = getattr(shape, "line", None)
    if line is None:
        return "transparent"
    try:
        color = line.color
    except Exception:
        return "transparent"
    return pptx_color_to_css(color) or "transparent"


def pptx_color_to_css(color) -> str | None:
    if color is None:
        return None
    try:
        rgb = color.rgb
    except Exception:
        return None
    if rgb is None:
        return None
    return f"#{str(rgb)}"


def pptx_html_css(page_width: float, page_height: float) -> str:
    return f"""
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: #eef0f3;
      color: #111827;
      font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", Arial, sans-serif;
    }}
    .ppt-deck {{
      display: grid;
      gap: 24px;
      padding: 24px;
      justify-content: center;
    }}
    .ppt-slide {{
      position: relative;
      overflow: hidden;
      background: #fff;
      box-shadow: 0 18px 50px rgba(15, 23, 42, .16);
      transform-origin: top center;
    }}
    .ppt-shape {{
      position: absolute;
      overflow: hidden;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      line-height: 1.18;
    }}
    .ppt-text {{
      display: flex;
      flex-direction: column;
      justify-content: flex-start;
      padding: 0;
    }}
    .ppt-picture {{
      object-fit: contain;
      border: 0 !important;
    }}
    .ppt-table-wrap {{
      background: transparent !important;
      border: 0 !important;
    }}
    .ppt-table-wrap table {{
      width: 100%;
      height: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 12px;
    }}
    .ppt-table-wrap th,
    .ppt-table-wrap td {{
      border: 1px solid #e5e7eb;
      padding: 5px 6px;
      vertical-align: middle;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .ppt-table-wrap th {{
      color: #fff;
      background: #e90035;
      font-weight: 900;
    }}
    .ppt-slide-number {{
      position: absolute;
      right: 16px;
      bottom: 10px;
      color: #a1a8b3;
      font-size: 11px;
      font-weight: 800;
      z-index: 9999;
    }}
    .ppt-shape-error {{
      color: #e90035;
      font-size: 10px;
      background: #fff1f4;
      padding: 4px;
    }}
    @media (max-width: {page_width + 48}px) {{
      .ppt-deck {{
        padding: 12px;
      }}
      .ppt-slide {{
        width: {page_width}px !important;
        height: {page_height}px !important;
        transform: scale(calc((100vw - 24px) / {page_width}));
        margin-bottom: calc({page_height}px * ((100vw - 24px) / {page_width}) - {page_height}px);
      }}
    }}
    @media print {{
      body {{ background: #fff; }}
      .ppt-deck {{ display: block; padding: 0; }}
      .ppt-slide {{
        box-shadow: none;
        page-break-after: always;
        margin: 0;
      }}
    }}
    """




__all__ = [
    "convert_pptx_to_html",
    "render_pptx_slides_to_png",
    "run_powerpoint_png_export",
    "pptx_slide_images_to_html",
    "pptx_image_html_css",
    "raise_html_renderer_error",
    "pptx_slide_to_html",
    "pptx_shape_to_html",
    "pptx_text_shape_to_html",
    "pptx_table_to_html",
    "pptx_picture_to_html",
    "pptx_box_shape_to_html",
    "pptx_shape_style",
    "is_pptx_picture",
    "iter_pptx_runs",
    "first_pptx_font_size",
    "first_pptx_font_color",
    "pptx_paragraph_align",
    "pptx_fill_color",
    "pptx_line_color",
    "pptx_color_to_css",
    "pptx_html_css",
]
