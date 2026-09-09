"""Application service for season analysis based on uploaded workbooks."""

from __future__ import annotations

import time
import traceback
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from backend.config import UPLOAD_DIR
from backend.services.audit import audit_uploads, write_audit_event
from backend.auth.permissions import security_scope_from_request
from backend.services.season_trend_store import save_latest_season_trend_result
from backend.services.season_ingredient_analysis import build_season_ingredient_analysis
from backend.services.storage import cleanup_job_uploads
from backend.services.upload_storage import store_upload_files
from backend.services.upload_models import SavedUpload
from backend.services.upload_classification import prepare_explicit_role_uploaded_data


async def run_uploaded_season_analysis(
    *, request: Request, files: list[UploadFile], normalized_roles: list[str],
    analysis_options: dict[str, object], schema_version: int,
) -> dict[str, object]:
    """Persist, parse and analyze season workbooks, then publish the latest result."""
    saved_uploads: list[SavedUpload] = []
    total_upload_bytes = 0
    upload_dir = UPLOAD_DIR / f"season_{uuid4().hex}"
    try:
        stored_uploads, total_upload_bytes = await store_upload_files(
            files, upload_dir,
            lambda index, safe_name: f"season_trend_{index}_{uuid4().hex}{Path(safe_name).suffix.lower()}",
        )
        saved_uploads = [SavedUpload(
            original_name=item.original_name, saved_name=item.saved_name, path=item.path,
            size_bytes=item.size_bytes, role=normalized_roles[index],
        ) for index, item in enumerate(stored_uploads)]
    except HTTPException as exc:
        write_audit_event(
            "season_trend_analysis_failed", request, files=audit_uploads(saved_uploads),
            requested_roles=normalized_roles, total_upload_bytes=total_upload_bytes,
            status_code=exc.status_code, detail=exc.detail,
        )
        cleanup_job_uploads(upload_dir)
        raise

    try:
        prepare_started_at = time.perf_counter()
        uploaded_data, _uploaded_files, classifications = await run_in_threadpool(
            prepare_explicit_role_uploaded_data, saved_uploads,
        )
        prepare_duration_seconds = time.perf_counter() - prepare_started_at
        print(f"[season_trend] prepare uploads: {prepare_duration_seconds:.2f}s", flush=True)
        analysis_started_at = time.perf_counter()
        result = await run_in_threadpool(build_season_ingredient_analysis, uploaded_data, analysis_options)
        analysis_duration_seconds = time.perf_counter() - analysis_started_at
        print(f"[season_trend] analysis: {analysis_duration_seconds:.2f}s", flush=True)
    except ValueError as exc:
        write_audit_event(
            "season_trend_analysis_failed", request, files=audit_uploads(saved_uploads),
            requested_roles=normalized_roles, error=str(exc),
        )
        cleanup_job_uploads(upload_dir)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        traceback.print_exc()
        write_audit_event(
            "season_trend_analysis_failed", request, files=audit_uploads(saved_uploads),
            requested_roles=normalized_roles, error=str(exc),
        )
        cleanup_job_uploads(upload_dir)
        raise HTTPException(status_code=500, detail=f"시즌/트렌드 분석 중 오류가 발생했습니다: {exc}") from exc

    write_audit_event(
        "season_trend_analysis_succeeded", request, files=classifications,
        file_count=len(saved_uploads), total_upload_bytes=total_upload_bytes,
        prepare_duration_seconds=round(prepare_duration_seconds, 3),
        analysis_duration_seconds=round(analysis_duration_seconds, 3),
    )
    response_payload = {
        "status": "success", "analysis_schema_version": schema_version,
        "uploaded_files": classifications, "analysis_options": analysis_options, **result,
    }
    save_latest_season_trend_result(response_payload, security_scope_from_request(request))
    cleanup_job_uploads(upload_dir)
    return response_payload
