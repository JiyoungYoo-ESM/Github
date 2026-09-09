"""보고서 공통 텍스트(요약·범위·수신대상 배지·보안 고지) 계산.

report_template_export 분해(IMPROVEMENT_PLAN.md 2단계) — 렌더러(html/pptx)가 공통으로
쓰는 순수 텍스트 헬퍼. 모델에만 의존하는 base 계층이라 렌더러들이 여기로만 아래를 향해
의존한다(렌더러 간 순환 방지)."""

from __future__ import annotations

import re

from backend.services.reports.models import AUDIENCE_BADGES, AUDIENCE_LABELS, ReportBlockPayload

def summarize_blocks(blocks: list[ReportBlockPayload]) -> list[str]:
    if not blocks:
        return [
            "선택된 분석 데이터를 기준으로 주요 시장과 성장 포인트를 요약합니다.",
            "선택한 브랜드·국가·SKU 블록을 템플릿 구조에 맞춰 재배치합니다.",
            "상세 데이터 스냅샷이 포함되면 표와 수치 영역까지 자동 반영됩니다.",
        ]

    summaries = [f"{block.title}: {block.subtitle or block.meta}" for block in blocks[:3]]
    while len(summaries) < 3:
        summaries.append(summaries[-1])
    return summaries


def summary_or_default(blocks: list[ReportBlockPayload], default: str) -> str:
    if not blocks:
        return default
    return " / ".join(block.title for block in blocks[:2])


def infer_report_subject(blocks: list[ReportBlockPayload]) -> str:
    for block in blocks:
        title = block.title.strip()
        if title:
            return title[:28]
    return "ESM 데이터 분석 리포트"


def infer_scope(blocks: list[ReportBlockPayload]) -> str:
    scopes: list[str] = []
    for block in blocks:
        for token in re.split(r"[·,/\s]+", f"{block.title} {block.subtitle}"):
            if token and token.endswith(("권역", "국가")):
                scopes.append(token)
    return " · ".join(dict.fromkeys(scopes[:3])) or "사용자 선택 블록"


def security_notice(audience: str) -> str:
    if audience == "internal":
        return "본 보고서는 실리콘투 내부 검토용이며 경쟁사 실명과 민감 지표를 포함할 수 있습니다."
    return "본 보고서는 외부 공유 기준에 따라 원가, 마진, 거래처 집계값 및 경쟁사 실명 정보를 마스킹해 생성했습니다."


def audience_badge(audience: str) -> str:
    return AUDIENCE_BADGES.get(audience, AUDIENCE_LABELS.get(audience, audience))




__all__ = [
    "summarize_blocks",
    "summary_or_default",
    "infer_report_subject",
    "infer_scope",
    "security_notice",
    "audience_badge",
]
