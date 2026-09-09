"""Upload classification preview and user category corrections."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from core.season_calendar import OFFICIAL_CATEGORY1_VALUES, OFFICIAL_CATEGORY2_BY_CATEGORY1

from backend.config import UPLOAD_DIR
from backend.schemas import (
    CategoryCorrectionOptionsResponse,
    CategoryCorrectionRequest,
    CategoryCorrectionSaveResponse,
    ClassificationResponse,
)
from backend.services.audit import audit_uploads, write_audit_event
from backend.services.category_corrections import save_user_category_corrections
from backend.services.season_trend_store import clear_latest_season_trend_result
from backend.auth.permissions import security_scope_from_request
from backend.services.storage import cleanup_job_uploads
from backend.services.upload_models import SavedUpload
from backend.services.upload_classification import classify_uploads_for_preview
from backend.services.upload_storage import store_upload_files

router = APIRouter()


@router.post("/api/classify", response_model=ClassificationResponse)
async def classify_uploads(
    request: Request,
    files: Annotated[list[UploadFile], File(description="Excel files to classify")],
) -> dict[str, object]:
    if not files:
        write_audit_event("classify_preview_failed", request, reason="no_files")
        raise HTTPException(status_code=400, detail="엑셀 파일을 1개 이상 선택해 주세요.")

    saved_uploads: list[SavedUpload] = []
    total_upload_bytes = 0
    upload_dir = UPLOAD_DIR / f"classify_{uuid4().hex}"
    try:
        stored_uploads, total_upload_bytes = await store_upload_files(
            files,
            upload_dir,
            lambda index, safe_name: f"preview_{index}_{uuid4().hex}{Path(safe_name).suffix.lower()}",
        )
        saved_uploads = [
            SavedUpload(
                original_name=item.original_name,
                saved_name=item.saved_name,
                path=item.path,
                size_bytes=item.size_bytes,
            )
            for item in stored_uploads
        ]
    except HTTPException as exc:
        write_audit_event(
            "classify_preview_failed",
            request,
            files=audit_uploads(saved_uploads),
            total_upload_bytes=total_upload_bytes,
            status_code=exc.status_code,
            detail=exc.detail,
        )
        cleanup_job_uploads(upload_dir)
        raise

    try:
        classifications = await run_in_threadpool(classify_uploads_for_preview, saved_uploads)
    except Exception as exc:
        write_audit_event(
            "classify_preview_failed",
            request,
            files=audit_uploads(saved_uploads),
            error=str(exc),
        )
        cleanup_job_uploads(upload_dir)
        raise HTTPException(status_code=500, detail=f"파일 자동 분류 중 오류가 발생했습니다: {exc}") from exc

    write_audit_event(
        "classify_preview_succeeded",
        request,
        files=audit_uploads(saved_uploads),
        total_upload_bytes=total_upload_bytes,
        classifications=[
            {
                "original_name": item.get("original_name"),
                "suggested_role": item.get("suggested_role"),
                "confidence": item.get("confidence"),
                "rows": item.get("rows"),
                "columns": item.get("columns"),
            }
            for item in classifications
        ],
    )
    cleanup_job_uploads(upload_dir)

    return {
        "status": "success",
        "files": classifications,
        "required_roles": [
            "eu_stock",
            "hq_eu_stock",
            "sales_detail",
            "hq_to_eu_sales_detail",
            "shipping",
            "inbound",
        ],
    }


@router.get("/api/category-corrections/options", response_model=CategoryCorrectionOptionsResponse)
async def category_correction_options():
    return {
        "category1": OFFICIAL_CATEGORY1_VALUES,
        "category2ByCategory1": OFFICIAL_CATEGORY2_BY_CATEGORY1,
    }


@router.post("/api/category-corrections", response_model=CategoryCorrectionSaveResponse)
async def save_category_corrections(body: CategoryCorrectionRequest, request: Request):
    saved = save_user_category_corrections([item.model_dump() for item in body.items])
    clear_latest_season_trend_result(security_scope_from_request(request))
    return {
        "status": "success",
        "saved_count": len(body.items),
        "total_count": int(len(saved)),
    }
