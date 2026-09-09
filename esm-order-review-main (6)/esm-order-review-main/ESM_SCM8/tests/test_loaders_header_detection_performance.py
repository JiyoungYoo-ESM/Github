"""Regression guard for the header-detection perf fix in core/loaders.py.

2026-07-22: excel_dataframe_candidates() used to re-read the whole sheet once per
header-row candidate (up to max_header_rows times) to score it. On a 1.79M-row/
97MB upload this took 20+ minutes and made the server unresponsive to every other
request (see OPERATIONS.md 3-3). The fix scores a nrows-limited preview per
candidate and only performs one full read for the winning header row. This test
pins that behavior so the O(max_header_rows) full-sheet re-read can't silently
come back.
"""

from __future__ import annotations

from io import BytesIO

import openpyxl
import pandas as pd
import pytest

from core import loaders as loaders_mod


def _make_xlsx_bytes(columns: list[str], rows: list[list[object]]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(columns)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@pytest.fixture()
def full_read_counter(monkeypatch: pytest.MonkeyPatch):
    calls = {"full": 0, "preview": 0}
    real_read_excel = pd.read_excel

    def counting_read_excel(*args, **kwargs):
        if "nrows" in kwargs:
            calls["preview"] += 1
        else:
            calls["full"] += 1
        return real_read_excel(*args, **kwargs)

    monkeypatch.setattr(pd, "read_excel", counting_read_excel)
    return calls


def test_header_detection_does_not_read_full_sheet_per_candidate(full_read_counter) -> None:
    data = _make_xlsx_bytes(
        ["상품코드", "상품명", "브랜드", "수량"],
        [
            ["SKU001", "테스트 상품", "브랜드A", 10],
            ["SKU002", "테스트 상품2", "브랜드B", 20],
        ],
    )

    # eu_stock은 fast-path 대상(sales_history/prod_list)이 아니라 header_row 0~5 전체를
    # 스캔하는 경로를 그대로 탄다 - 이번 회귀의 실제 발생 경로.
    candidates = loaders_mod.excel_dataframe_candidates(data, engine="openpyxl", key="eu_stock")

    assert candidates
    # max_header_rows 기본값(6)만큼 시트 전체를 다시 읽으면 회귀다. 승자 header_row에
    # 대해서만 전체를 읽어야 하므로(동점이면 그 이상일 수 있으나 6회 전부는 아니다) 엄격히
    # 6보다 작아야 한다.
    assert full_read_counter["full"] < 6
    assert full_read_counter["full"] >= 1
    # 후보 판별 자체는 여전히 header_row 0~5를 미리보기로 확인해야 한다.
    assert full_read_counter["preview"] >= 6


def test_header_detection_still_picks_the_correct_header_row(full_read_counter) -> None:
    # 0행에 안내 문구가 끼어 있어 진짜 헤더는 1행부터 시작하는 흔한 CMS 엑셀 패턴.
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["※ 본 파일은 자동 생성되었습니다"])
    sheet.append(["상품코드", "상품명", "브랜드", "수량"])
    sheet.append(["SKU001", "테스트 상품", "브랜드A", 10])
    sheet.append(["SKU002", "테스트 상품2", "브랜드B", 20])
    buffer = BytesIO()
    workbook.save(buffer)

    candidates = loaders_mod.excel_dataframe_candidates(buffer.getvalue(), engine="openpyxl", key="eu_stock")
    best = loaders_mod.best_uploaded_dataframe(candidates, key="eu_stock")

    assert not best.empty
    assert "상품코드" in best.columns
    assert len(best) == 2
