"""Report cart export for PPTX, HTML, PDF and dataset XLSX outputs."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from html import escape
from base64 import b64encode
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from backend.config import OUTPUT_DIR, REPORT_CART_TEMPLATE_PPTX, SCM_REPORT_SELF_BRAND
from core.exchange_rate import DEFAULT_EUR_KRW_RATE

# 도메인 모델·상수는 reports.models로 분리됨(IMPROVEMENT_PLAN.md 2단계). 이 모듈은
# 하위 호환 shim으로 재수출하여 기존 import 경로(routers·tests)를 유지한다.
# reports.models.__all__ 이 재수출 대상을 명시한다(ReportBlockPayload, MaskingSummary,
# normalize_audience/format, AUDIENCE_LABELS, PDF_CONVERSION_LOCK, 각종 상수 등).
from backend.services.reports.models import *  # noqa: F401,F403
# 값·텍스트·숫자 포매팅 프리미티브(닫힌 리프 집합)도 reports.formatting로 분리됨.
from backend.services.reports.formatting import *  # noqa: F401,F403
# PPTX 드로잉·슬라이드 조작 프리미티브도 reports.pptx_prims로 분리됨.
from backend.services.reports.pptx_prims import *  # noqa: F401,F403
# PPTX→HTML 변환 렌더러(의존성 leaf)도 reports.pptx_html로 분리됨.
from backend.services.reports.pptx_html import *  # noqa: F401,F403
# 데이터 정규화 + 마스킹 계층(masking+normalize 병합)도 reports.report_data로 분리됨.
from backend.services.reports.report_data import *  # noqa: F401,F403
# 교차분석 계산 계층도 reports.compute_cross로 분리됨(계산 base, 렌더러 사이클 절단).
from backend.services.reports.compute_cross import *  # noqa: F401,F403
# 스냅샷·표·카드 행/열 계산 계층도 reports.compute_snapshot으로 분리됨.
from backend.services.reports.compute_snapshot import *  # noqa: F401,F403
# 추이·시즌·성장·소제목 계산 계층도 reports.compute_series로 분리됨(계산 base 완성).
from backend.services.reports.compute_series import *  # noqa: F401,F403
# 공통 텍스트(요약·배지·보안고지)도 reports.report_chrome로 분리됨.
from backend.services.reports.report_chrome import *  # noqa: F401,F403
# HTML 렌더러도 reports.report_html로 분리됨.
from backend.services.reports.report_html import *  # noqa: F401,F403
# PPTX→PDF 변환도 reports.report_pdf로 분리됨.
from backend.services.reports.report_pdf import *  # noqa: F401,F403
# 데이터셋 XLSX 입출력도 reports.report_dataset_xlsx로 분리됨.
from backend.services.reports.report_dataset_xlsx import *  # noqa: F401,F403
# PPTX 렌더러(템플릿+동적+슬라이드 빌더)도 reports.report_pptx로 분리됨.
from backend.services.reports.report_pptx import *  # noqa: F401,F403


def build_report_export(
    *,
    audience: str,
    export_format: str,
    blocks: list[ReportBlockPayload],
    title: str | None = None,
) -> Path:
    audience = normalize_audience(audience)
    export_format = normalize_format(export_format)
    display_title = normalize_report_title(title)

    output_dir = OUTPUT_DIR / f"report_{uuid4().hex}"
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = safe_filename(f"{AUDIENCE_LABELS[audience]}_{display_title}")
    dataset_path = output_dir / "report_dataset.xlsx"
    pptx_path = output_dir / f"{base_name}.pptx"
    html_path = output_dir / f"{base_name}.html"

    normalized_blocks = [normalize_report_block(block) for block in blocks]
    masked_blocks, masking_summary = mask_blocks(normalized_blocks, audience)
    # 장바구니에서 사용자가 정한 위→아래 순서를 보고서에서도 그대로 유지한다.
    # 행 정렬은 블록 내부에서만 적용하고 섹션 순서로 블록을 재배치하지 않는다.
    masked_blocks = [sort_block_snapshot_rows(block) for block in masked_blocks]

    write_report_dataset_xlsx(dataset_path, audience=audience, blocks=masked_blocks, title=display_title, masking_summary=masking_summary)

    if export_format == "xlsx":
        return dataset_path

    # PPT/HTML/PDF는 방금 계산한 블록을 그대로 사용한다. 중간 검증용 XLSX를 다시
    # 읽으면 일부 Windows/Excel 조합에서 한글 헤더가 깨져 카드 축/라벨 매칭이
    # 실패하고, 브랜드 월별 카드가 동일 브랜드 TOP 바처럼 fallback 렌더링되는
    # 문제가 있었다.
    dataset_blocks = masked_blocks

    if export_format == "html":
        # HTML은 PowerPoint/COM 렌더러에 의존하지 않는다. Railway/Linux에서도
        # 동일한 마스킹 데이터와 장바구니 순서로 직접 생성한다.
        write_report_html(
            html_path,
            audience=audience,
            blocks=masked_blocks,
            title=display_title,
            masking_summary=masking_summary,
        )
        return html_path

    # 저장소에 포함된 원본 PPT 템플릿의 표지·섹션 사진·좌우 카드 레이아웃을
    # 유지한다. 템플릿 파일이 없는 환경에서만 코드 생성형 덱으로 대체한다.
    if REPORT_CART_TEMPLATE_PPTX.is_file():
        write_template_report_pptx(
            pptx_path,
            audience=audience,
            blocks=dataset_blocks,
            title=display_title,
            masking_summary=masking_summary,
        )
    else:
        write_dynamic_report_pptx(
            pptx_path,
            audience=audience,
            blocks=dataset_blocks,
            title=display_title,
            masking_summary=masking_summary,
        )

    if export_format == "ppt":
        return pptx_path

    if export_format == "html":
        return convert_pptx_to_html(pptx_path, html_path)

    return convert_pptx_to_pdf(pptx_path, output_dir)

