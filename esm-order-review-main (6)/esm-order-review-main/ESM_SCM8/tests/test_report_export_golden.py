"""Golden-file characterization of the HTML report output.

Safety net for the report_template_export decomposition (IMPROVEMENT_PLAN.md
step 2). Renders a fixed, multi-section report for each audience and compares
the full HTML — with the only non-deterministic part (the generated-at
timestamp) normalized away — against a committed snapshot.

Any behavioral drift while splitting the 7k-line module into a package (a
number formatted differently, a masked name leaking, a section dropped) changes
the HTML and fails here immediately.

Block fixtures are imported from ``test_report_export_masking`` so there is a
single source of truth for the sample report shapes. Regenerate the goldens
intentionally with ``SCM_UPDATE_REPORT_GOLDEN=1 pytest tests/test_report_export_golden.py``
after a *reviewed* output change."""

from __future__ import annotations

import os
import re
from pathlib import Path

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

GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "report_html"
# "2026-07-21 01:23" 또는 "2026-07-21" 형태의 생성 시각을 자리표시자로 치환한다.
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?")
_UPDATE = os.environ.get("SCM_UPDATE_REPORT_GOLDEN") == "1"

AUDIENCES = ["internal", "partner", "sales"]


def sample_blocks():
    """Representative report spanning region/brand/sku/cross sections."""
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


def render_html(audience: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(export_service, "OUTPUT_DIR", tmp_path)
    output_path = build_report_export(
        audience=audience,
        export_format="html",
        blocks=sample_blocks(),
        title="골든 스냅샷 리포트",
    )
    html = output_path.read_text(encoding="utf-8")
    return _TIMESTAMP.sub("<GENERATED_AT>", html)


@pytest.mark.parametrize("audience", AUDIENCES)
def test_html_report_matches_golden(audience, tmp_path, monkeypatch):
    rendered = render_html(audience, tmp_path, monkeypatch)
    golden_path = GOLDEN_DIR / f"{audience}.html"

    if _UPDATE or not golden_path.exists():
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(rendered, encoding="utf-8")
        pytest.skip(f"golden written: {golden_path.name} (재실행 시 비교)")

    expected = golden_path.read_text(encoding="utf-8")
    assert rendered == expected, (
        f"HTML 보고서 출력이 골든 스냅샷과 다릅니다 (audience={audience}). "
        "의도된 변경이면 SCM_UPDATE_REPORT_GOLDEN=1 로 재생성 후 diff를 검토하세요."
    )


def test_html_render_is_deterministic(tmp_path, monkeypatch):
    """Two renders of the same input must be byte-identical after timestamp
    normalization — otherwise the golden comparison would be flaky."""
    first = render_html("internal", tmp_path / "a", monkeypatch)
    second = render_html("internal", tmp_path / "b", monkeypatch)
    assert first == second
