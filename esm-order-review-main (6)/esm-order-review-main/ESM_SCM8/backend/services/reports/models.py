"""보고서 도메인 모델과 상수.

``report_template_export`` 패키지 분해(IMPROVEMENT_PLAN.md 2단계)의 최하위 리프
모듈. 순환 의존이 없는 순수 데이터/열거 상수만 담는다. ``ReportBlockPayload`` /
``MaskingSummary`` 는 반드시 이 모듈에서만 정의되어야 한다(다른 곳 재정의 금지 —
isinstance/pydantic 동일성 보장)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

REPORT_AUDIENCES = {"internal", "partner", "sales"}
REPORT_FORMATS = {"ppt", "pdf", "html", "xlsx"}
REPORT_BLOCK_KINDS = {"kpi", "share", "ranking", "trend", "matrix"}
REPORT_BLOCK_SECTIONS = {"summary", "region", "brand", "sku", "cross", "season", "ingredient"}
REPORT_BLOCK_SIZES = {"full", "half"}
PDF_CONVERSION_LOCK = threading.Lock()
# 섹션 슬라이드 한 장에 담기는 최대 행 수. 이를 넘으면 슬라이드를 자동 복제해
# 담긴 항목을 전량 출력한다(상위 N개 잘림 방지).
REGION_ROWS_PER_SLIDE = 7
STRUCTURED_TABLE_ROWS_PER_SLIDE = 9
BRAND_ROWS_PER_SLIDE = 7
SKU_ROWS_PER_SLIDE = 6
REGION_GROWTH_METRICS = (("YoY", "YoY"), ("MoM", "MoM"), ("성장률MoM", "MoM"), ("성장률", "MoM"))
BRAND_GROWTH_METRICS = (("성장률MoM", "MoM"), ("YoY", "YoY"), ("MoM", "MoM"), ("성장률", "MoM"))
SECTION_ORDER = ["summary", "region", "brand", "sku", "cross", "season", "ingredient"]
SECTION_LABELS = {
    "summary": "핵심요약",
    "region": "국가 · 권역",
    "brand": "브랜드",
    "sku": "SKU",
    "cross": "교차분석",
    "season": "시즌 캘린더",
    "ingredient": "성분 분석",
}
# 템플릿 PPTX에 전용 슬라이드가 없어 generic 블록 슬라이드로 렌더링하는 섹션.
TEMPLATE_EXTRA_SECTIONS = ("season", "ingredient")

AUDIENCE_LABELS = {
    "internal": "내부용",
    "partner": "거래처용",
    "sales": "판매용",
}

AUDIENCE_BADGES = {
    "internal": "INTERNAL ONLY · 대외비",
    "partner": "PARTNER VIEW · 민감정보 제외",
    "sales": "공개용",
}

CONFIDENTIAL_FIELD_TOKENS = ("원가", "마진", "매입단가", "기여이익", "이익률", "cost", "margin", "profit", "purchase_price")
CLIENT_FIELD_TOKENS = ("거래처", "고객", "수신처", "client", "customer", "account", "partner")
BRAND_FIELD_TOKENS = ("브랜드", "brand", "brand_original", "display_brand")
TECHNICAL_SNAPSHOT_FIELDS = {"brand_role", "is_self", "brand_original", "display_brand"}


@dataclass(frozen=True)
class ReportBlockPayload:
    id: str
    title: str
    subtitle: str
    meta: str
    type: str = "summary"
    kind: str = ""
    section: str = ""
    size: str = "full"
    params: dict[str, Any] | None = None
    snapshot: dict[str, Any] | None = None
    html_snapshot: str | None = None


@dataclass(frozen=True)
class MaskingSummary:
    audience: str
    removed_columns: tuple[str, ...]
    anonymized_competitor_count: int
    competitor_aliases: dict[str, str]
    client_identity_policy: str

def normalize_audience(value: str) -> str:
    audience = value.strip().lower()
    if audience not in REPORT_AUDIENCES:
        raise HTTPException(status_code=422, detail="지원하지 않는 보고서 수신 대상입니다.")
    return audience

def normalize_format(value: str) -> str:
    export_format = value.strip().lower()
    if export_format not in REPORT_FORMATS:
        raise HTTPException(status_code=422, detail="지원하지 않는 보고서 형식입니다.")
    return export_format


__all__ = [
    "REPORT_AUDIENCES",
    "REPORT_FORMATS",
    "REPORT_BLOCK_KINDS",
    "REPORT_BLOCK_SECTIONS",
    "REPORT_BLOCK_SIZES",
    "PDF_CONVERSION_LOCK",
    "REGION_ROWS_PER_SLIDE",
    "STRUCTURED_TABLE_ROWS_PER_SLIDE",
    "BRAND_ROWS_PER_SLIDE",
    "SKU_ROWS_PER_SLIDE",
    "REGION_GROWTH_METRICS",
    "BRAND_GROWTH_METRICS",
    "SECTION_ORDER",
    "SECTION_LABELS",
    "TEMPLATE_EXTRA_SECTIONS",
    "AUDIENCE_LABELS",
    "AUDIENCE_BADGES",
    "CONFIDENTIAL_FIELD_TOKENS",
    "CLIENT_FIELD_TOKENS",
    "BRAND_FIELD_TOKENS",
    "TECHNICAL_SNAPSHOT_FIELDS",
    "ReportBlockPayload",
    "MaskingSummary",
    "normalize_audience",
    "normalize_format",
]
