"""Template-based report cart export endpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from backend.config import OUTPUT_DIR, REPORT_EXPORT_TIMEOUT_SECONDS, REPORT_MAX_OUTPUT_BYTES, REPORT_MAX_REQUEST_BYTES
from backend.services.analysis_tasks import create_analysis_task, wait_without_cancelling
from backend.services.report_resources import acquire_report_slot, defer_report_release, release_report_slot
from backend.services.report_template_export import ReportBlockPayload, build_report_export
from backend.services.request_validation import format_bytes
from backend.services.storage import remove_path
from backend.auth.amount_permissions import can_view_amount_data, sanitize_amount_data

router = APIRouter()


def build_report_export_with_cleanup(**kwargs) -> Path:
    """Remove a newly-created report directory when generation raises."""

    existing = set(OUTPUT_DIR.glob("report_*"))
    try:
        return build_report_export(**kwargs)
    except BaseException:
        for path in set(OUTPUT_DIR.glob("report_*")) - existing:
            remove_path(path)
        raise


class ReportBlockRequest(BaseModel):
    id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=240)
    subtitle: str = Field(default="", max_length=500)
    meta: str = Field(default="", max_length=240)
    type: str = Field(default="summary", min_length=1, max_length=80)
    kind: Literal["kpi", "share", "ranking", "trend", "matrix"] | None = None
    section: Literal["summary", "region", "brand", "sku", "cross", "season", "ingredient"] | None = None
    size: Literal["full", "half"] | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any] | None = None
    htmlSnapshot: str | None = Field(default=None, max_length=2_000_000)


class ReportExportRequest(BaseModel):
    audience: Literal["internal", "partner", "sales"] = "partner"
    format: Literal["ppt", "pdf", "html", "xlsx"] = "ppt"
    title: str | None = Field(default=None, max_length=120)
    blocks: list[ReportBlockRequest] = Field(default_factory=list, max_length=30)


@router.post("/api/reports/export")
async def export_report(payload: ReportExportRequest, request: Request = None) -> Response:
    request_size = len(payload.model_dump_json().encode("utf-8"))
    if request_size > REPORT_MAX_REQUEST_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"보고서 요청 데이터는 최대 {format_bytes(REPORT_MAX_REQUEST_BYTES)}까지 허용됩니다.",
        )
    if not await acquire_report_slot():
        raise HTTPException(status_code=429, detail="다른 보고서를 생성 중입니다. 잠시 후 다시 시도해 주세요.")

    # ``request`` is always supplied by FastAPI. The default preserves direct
    # unit-level calls to this generator without manufacturing an ASGI request.
    amount_allowed = request is None or can_view_amount_data(request.state.current_user)
    blocks: list[ReportBlockPayload] = []
    for block in payload.blocks:
        block_data = block.model_dump()
        if not amount_allowed:
            block_data = sanitize_amount_data(block_data)
        blocks.append(
            ReportBlockPayload(
                id=str(block_data.get("id") or block.id),
                title=str(block_data.get("title") or block.title),
                subtitle=str(block_data.get("subtitle") or ""),
                meta=str(block_data.get("meta") or ""),
                type=str(block_data.get("type") or "summary"),
                kind=str(block_data.get("kind") or ""),
                section=str(block_data.get("section") or ""),
                size=str(block_data.get("size") or "full"),
                params=dict(block_data.get("params") or {}),
                snapshot=block_data.get("snapshot") if isinstance(block_data.get("snapshot"), dict) else None,
                html_snapshot=block_data.get("htmlSnapshot") if amount_allowed else None,
            )
        )
    export_task = create_analysis_task(
        run_in_threadpool(
            build_report_export_with_cleanup,
            audience=payload.audience,
            export_format=payload.format,
            title=payload.title,
            blocks=blocks,
        )
    )
    deferred_release = False
    try:
        completed, output_path = await wait_without_cancelling(export_task, REPORT_EXPORT_TIMEOUT_SECONDS)
        if not completed:
            defer_report_release(export_task)
            deferred_release = True
            raise HTTPException(
                status_code=504,
                detail=f"보고서 생성 시간이 {REPORT_EXPORT_TIMEOUT_SECONDS}초를 초과했습니다.",
            )
        assert output_path is not None
        output_size = output_path.stat().st_size
        if output_size > REPORT_MAX_OUTPUT_BYTES:
            remove_path(output_path.parent)
            raise HTTPException(
                status_code=413,
                detail=f"생성된 보고서는 최대 {format_bytes(REPORT_MAX_OUTPUT_BYTES)}까지 다운로드할 수 있습니다.",
            )
    except asyncio.CancelledError:
        defer_report_release(export_task)
        deferred_release = True
        raise
    finally:
        if not deferred_release:
            await release_report_slot()

    filename = output_path.name
    return FileResponse(
        path=output_path,
        filename=filename,
        media_type=media_type_for_report_file(output_path.suffix.lower()),
        headers={"Access-Control-Expose-Headers": "Content-Disposition"},
        background=BackgroundTask(remove_path, output_path.parent),
    )


def media_type_for_report_file(suffix: str) -> str:
    if suffix == ".html":
        return "text/html; charset=utf-8"
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
