"""Golden-file characterization of the PPTX report output.

Companion to test_report_export_golden.py (which covers HTML). PPTX is a binary
zip and not byte-deterministic, so instead of comparing bytes we extract a
deterministic *text digest* — every drawing text run (``a:t``) and chart value
(``c:v``) per slide/chart part, in document order — and snapshot that (with the
generated-at date normalized).

This guards the PPTX rendering path while report_template_export.py is split
into a package (IMPROVEMENT_PLAN.md step 2), in particular the PPTX drawing
primitives (add_textbox, set_shape_text, replace_*_table, add_brand_chart_text …)
that the HTML golden does not exercise. Both render paths are covered:
  - template path  → write_template_report_pptx (default, template present)
  - dynamic path   → write_dynamic_report_pptx (template forced missing)

Regenerate intentionally after a *reviewed* change:
  SCM_UPDATE_REPORT_GOLDEN=1 pytest tests/test_report_export_pptx_golden.py
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from backend.services import report_template_export as export_service
from backend.services.report_template_export import build_report_export

from test_report_export_masking import (
    brand_ranking_block,
    country_detail_card_block,
    country_ranking_block,
    cross_matrix_block,
    ingredient_country_cross_block,
    region_share_block,
    sku_detail_block,
    sku_order_reference_block,
)

GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "report_pptx"
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?")
_UPDATE = os.environ.get("SCM_UPDATE_REPORT_GOLDEN") == "1"

AUDIENCES = ["internal", "partner", "sales"]


def sample_blocks():
    """Same representative report as the HTML golden (region/brand/sku/cross)."""
    return [
        country_ranking_block(),
        region_share_block(),
        country_detail_card_block(),
        brand_ranking_block(),
        sku_detail_block(),
        sku_order_reference_block(),
        cross_matrix_block(),
        ingredient_country_cross_block(),
    ]


def pptx_text_digest(path: Path) -> str:
    """Deterministic text content of a .pptx: all drawing-text runs and chart
    values per slide/chart part, in document order, timestamps normalized."""
    sections: list[str] = []
    with ZipFile(path) as archive:
        slide_parts = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        chart_parts = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/charts/") and name.endswith(".xml")
        )
        for name in slide_parts + chart_parts:
            root = ET.fromstring(archive.read(name))
            texts = [
                element.text
                for element in root.iter()
                if element.tag.split("}")[-1] in {"t", "v"} and element.text
            ]
            sections.append(name + "\n" + "\n".join(texts))
    return _TIMESTAMP.sub("<DATE>", "\n===\n".join(sections))


def render_pptx_digest(audience: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(export_service, "OUTPUT_DIR", tmp_path)
    output_path = build_report_export(
        audience=audience,
        export_format="ppt",
        blocks=sample_blocks(),
        title="골든 스냅샷 리포트",
    )
    return pptx_text_digest(output_path)


def _check_golden(name: str, digest: str) -> None:
    golden_path = GOLDEN_DIR / f"{name}.txt"
    if _UPDATE or not golden_path.exists():
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(digest, encoding="utf-8")
        pytest.skip(f"golden written: {golden_path.name} (재실행 시 비교)")
    expected = golden_path.read_text(encoding="utf-8")
    assert digest == expected, (
        f"PPTX 보고서 텍스트가 골든 스냅샷과 다릅니다 ({name}). "
        "의도된 변경이면 SCM_UPDATE_REPORT_GOLDEN=1 로 재생성 후 diff를 검토하세요."
    )


@pytest.mark.parametrize("audience", AUDIENCES)
def test_pptx_template_path_matches_golden(audience, tmp_path, monkeypatch):
    """Template render path (write_template_report_pptx)."""
    digest = render_pptx_digest(audience, tmp_path, monkeypatch)
    _check_golden(f"template_{audience}", digest)


def test_pptx_dynamic_path_matches_golden(tmp_path, monkeypatch):
    """Dynamic render path (write_dynamic_report_pptx) — template forced missing."""
    monkeypatch.setattr(
        export_service, "REPORT_CART_TEMPLATE_PPTX", tmp_path / "does_not_exist.pptx"
    )
    digest = render_pptx_digest("internal", tmp_path, monkeypatch)
    _check_golden("dynamic_internal", digest)


def test_pptx_digest_is_deterministic(tmp_path, monkeypatch):
    """Two renders of the same input must yield the same digest."""
    first = render_pptx_digest("internal", tmp_path / "a", monkeypatch)
    second = render_pptx_digest("internal", tmp_path / "b", monkeypatch)
    assert first == second
