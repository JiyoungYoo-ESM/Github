from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.services.reports.compute_snapshot import (
    brand_label_from_title,
    is_numeric_display,
)
from backend.services.reports.report_chrome import summarize_blocks
from backend.services.reports.report_data import mask_value


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_SOURCES = [
    PROJECT_ROOT / "backend" / "services" / "report_template_export.py",
    *(PROJECT_ROOT / "backend" / "services" / "reports").glob("*.py"),
]
MOJIBAKE_HAN_PATTERN = re.compile(r"[\u4e00-\u9fff\uf900-\ufaff]")


@pytest.mark.parametrize("source_path", REPORT_SOURCES, ids=lambda path: path.name)
def test_report_source_is_utf8_without_mojibake(source_path: Path) -> None:
    """Korean source corrupted by a legacy code page usually contains Han glyphs."""

    source = source_path.read_text(encoding="utf-8", errors="strict")

    assert not MOJIBAKE_HAN_PATTERN.search(source), source_path
    assert "쨌" not in source, source_path


def test_report_user_facing_korean_contracts() -> None:
    assert summarize_blocks([]) == [
        "선택된 분석 데이터를 기준으로 주요 시장과 성장 포인트를 요약합니다.",
        "선택한 브랜드·국가·SKU 블록을 템플릿 구조에 맞춰 재배치합니다.",
        "상세 데이터 스냅샷이 포함되면 표와 수치 영역까지 자동 반영됩니다.",
    ]
    assert brand_label_from_title("아누아 브랜드별 판매 순위") == "아누아"
    assert is_numeric_display("₩1,234억")
    assert is_numeric_display("42.5%")
    assert not is_numeric_display("분석 필요")


def test_external_report_client_identity_is_masked() -> None:
    kwargs = {"key": "거래처", "value": "실제 거래처", "alias_map": {}, "source_is_self": False}

    assert mask_value(audience="partner", **kwargs) == "수신처 본인"
    assert mask_value(audience="sales", **kwargs) == "집계"
