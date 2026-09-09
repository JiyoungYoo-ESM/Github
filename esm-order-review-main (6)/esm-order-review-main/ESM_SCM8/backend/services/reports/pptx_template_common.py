"""Shared helpers for branded report PPTX template sections."""

from __future__ import annotations

from backend.services.reports.pptx_prims import delete_shape_by_id, set_shape_text
from backend.services.reports.report_chrome import audience_badge


def set_section_data_title(
    slide,
    shape_id: int,
    base_title: str,
    *,
    page_index: int,
    page_count: int,
) -> None:
    suffix = f" ({page_index + 1}/{page_count})" if page_count > 1 else ""
    set_shape_text(slide, shape_id, base_title + suffix)


def set_template_badge(slide, shape_id: int, audience: str) -> None:
    badge_icon_ids = {
        130: 131,
        189: 190,
        256: 261,
        293: 294,
        328: 329,
    }
    icon_id = badge_icon_ids.get(shape_id)
    if icon_id:
        delete_shape_by_id(slide, icon_id)
    set_shape_text(slide, shape_id, audience_badge(audience))


__all__ = ["set_section_data_title", "set_template_badge"]
