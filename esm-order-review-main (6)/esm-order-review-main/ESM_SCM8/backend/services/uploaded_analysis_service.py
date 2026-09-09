"""Application service for uploaded-file analysis workflows."""

from __future__ import annotations

import asyncio
import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from backend.services.order_analysis_workflow import run_core_analysis
from backend.config import (
    ANALYSIS_TIMEOUT_SECONDS,
    MAX_ANALYSES_PER_CLIENT,
    MAX_CONCURRENT_ANALYSES,
    OUTPUT_DIR,
    STORAGE_MAX_AGE_HOURS,
    UPLOAD_DIR,
)
from backend.services.audit import (
    audit_uploads,
    client_id_from_request,
    write_audit_event,
)
from backend.services.upload_models import SavedUpload
from backend.services.analysis_tasks import create_analysis_task, defer_slot_release, wait_without_cancelling
from backend.services.concurrency import (
    acquire_analysis_slot,
    active_analysis_snapshot,
    release_analysis_slot,
)
from backend.services.order_review_store import (
    save_latest_order_review_result,
    save_latest_order_review_workbook,
)
from backend.services.request_validation import (
    compact_optional_settings,
    normalize_roles,
    validate_eur_krw_rate,
    validate_lead_time,
    validate_lead_time_overrides,
    validate_month_setting,
    validate_percent_threshold,
)
from backend.services.storage import (
    cleanup_job_uploads,
    create_download_token,
    ensure_storage_dirs,
    publish_job_output,
    remove_path,
)
from backend.services.upload_storage import store_upload_files


async def run_uploaded_analysis(
    *,
    request: Request,
    files: list[UploadFile],
    roles: list[str] | None = None,
    eur_krw_rate: float | None = None,
    safety_months: float | None = None,
    sku_shortage_threshold_pct: float | None = None,
    sku_overstock_threshold_pct: float | None = None,
    lead_time_air: int | None = None,
    lead_time_sea: int | None = None,
    lead_time_rail: int | None = None,
    lead_time_truck: int | None = None,
    lead_time_overrides: object = None,
) -> dict[str, object]:
    await run_in_threadpool(ensure_storage_dirs)
    if not files:
        write_audit_event("analysis_failed", request, reason="no_files")
        raise HTTPException(status_code=400, detail="엑셀 파일을 1개 이상 선택해 주세요.")
    entity_code = str(request.state.entity_code)
    try:
        normalized_roles = normalize_roles(roles, len(files))
        fixed_eur_krw_rate = validate_eur_krw_rate(eur_krw_rate)
        analysis_settings = compact_optional_settings(
            {
                "safety_months": validate_month_setting(safety_months, "safety_months"),
                "sku_shortage_threshold_pct": validate_percent_threshold(
                    sku_shortage_threshold_pct,
                    "sku_shortage_threshold_pct",
                ),
                "sku_overstock_threshold_pct": validate_percent_threshold(
                    sku_overstock_threshold_pct,
                    "sku_overstock_threshold_pct",
                ),
                "lead_time_air": validate_lead_time(lead_time_air, "lead_time_air"),
                "lead_time_sea": validate_lead_time(lead_time_sea, "lead_time_sea"),
                "lead_time_rail": validate_lead_time(lead_time_rail, "lead_time_rail"),
                "lead_time_truck": validate_lead_time(lead_time_truck, "lead_time_truck"),
            }
        )
        dynamic_lead_time_overrides = validate_lead_time_overrides(
            lead_time_overrides,
            entity_code,
        )
        analysis_settings["entity_code"] = entity_code
        if dynamic_lead_time_overrides:
            analysis_settings["lead_time_overrides"] = dynamic_lead_time_overrides
    except HTTPException as exc:
        write_audit_event(
            "analysis_failed",
            request,
            reason="invalid_request",
            status_code=exc.status_code,
            detail=exc.detail,
        )
        raise

    client_id = client_id_from_request(request)
    job_id = f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    upload_dir = UPLOAD_DIR / job_id
    output_dir = OUTPUT_DIR / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_uploads: list[SavedUpload] = []
    total_upload_bytes = 0
    try:
        stored_uploads, total_upload_bytes = await store_upload_files(
            files,
            upload_dir,
            lambda index, safe_name: (
                f"{index:02d}_{uuid4().hex}{Path(safe_name).suffix.lower()}"
            ),
        )
        saved_uploads = [
            SavedUpload(
                original_name=item.original_name,
                saved_name=item.saved_name,
                path=item.path,
                size_bytes=item.size_bytes,
                role=normalized_roles[index] if normalized_roles else None,
            )
            for index, item in enumerate(stored_uploads)
        ]
    except HTTPException as exc:
        write_audit_event(
            "analysis_failed",
            request,
            job_id=job_id,
            files=audit_uploads(saved_uploads),
            requested_roles=normalized_roles,
            settings=analysis_settings,
            client_id=client_id,
            total_upload_bytes=total_upload_bytes,
            status_code=exc.status_code,
            detail=exc.detail,
        )
        cleanup_job_uploads(upload_dir)
        remove_path(output_dir)
        raise

    if not await acquire_analysis_slot(client_id):
        write_audit_event(
            "analysis_rejected",
            request,
            job_id=job_id,
            client_id=client_id,
            files=audit_uploads(saved_uploads),
            total_upload_bytes=total_upload_bytes,
            reason="concurrency_limit",
            active_analysis=active_analysis_snapshot(),
        )
        cleanup_job_uploads(upload_dir)
        remove_path(output_dir)
        raise HTTPException(
            status_code=429,
            detail=(
                "현재 다른 분석이 진행 중입니다. 잠시 후 다시 시도해 주세요. "
                f"서버 전체 동시 분석은 최대 {MAX_CONCURRENT_ANALYSES}개, 사용자당 {MAX_ANALYSES_PER_CLIENT}개로 제한됩니다."
            ),
        )

    output_path = output_dir / f"ESM_order_review_{job_id}.xlsx"
    analysis_started_at = time.perf_counter()
    write_audit_event(
        "analysis_started",
        request,
        job_id=job_id,
        client_id=client_id,
        files=audit_uploads(saved_uploads),
        file_count=len(saved_uploads),
        total_upload_bytes=total_upload_bytes,
        requested_roles=normalized_roles,
        settings=analysis_settings,
        fixed_eur_krw_rate=fixed_eur_krw_rate,
        timeout_seconds=ANALYSIS_TIMEOUT_SECONDS,
        active_analysis=active_analysis_snapshot(),
    )
    analysis_task = create_analysis_task(
        run_in_threadpool(
            run_core_analysis,
            saved_uploads,
            output_path,
            fixed_eur_krw_rate,
            analysis_settings,
            entity_code,
        )
    )
    deferred_release = False
    try:
        completed, result = await wait_without_cancelling(analysis_task, ANALYSIS_TIMEOUT_SECONDS)
        if not completed:
            defer_slot_release(
                analysis_task,
                client_id,
                lambda: (cleanup_job_uploads(upload_dir), remove_path(output_dir)),
            )
            deferred_release = True
            raise asyncio.TimeoutError
        assert result is not None
    except asyncio.TimeoutError as exc:
        duration_seconds = time.perf_counter() - analysis_started_at
        write_audit_event(
            "analysis_failed",
            request,
            job_id=job_id,
            client_id=client_id,
            files=audit_uploads(saved_uploads),
            file_count=len(saved_uploads),
            total_upload_bytes=total_upload_bytes,
            requested_roles=normalized_roles,
            settings=analysis_settings,
            duration_seconds=round(duration_seconds, 3),
            error_type="timeout",
            error=f"Analysis exceeded {ANALYSIS_TIMEOUT_SECONDS} seconds.",
        )
        raise HTTPException(
            status_code=504,
            detail=f"분석 시간이 {ANALYSIS_TIMEOUT_SECONDS}초를 초과했습니다. 파일 용량을 줄이거나 잠시 후 다시 시도해 주세요.",
        ) from exc
    except ValueError as exc:
        duration_seconds = time.perf_counter() - analysis_started_at
        write_audit_event(
            "analysis_failed",
            request,
            job_id=job_id,
            client_id=client_id,
            files=audit_uploads(saved_uploads),
            file_count=len(saved_uploads),
            total_upload_bytes=total_upload_bytes,
            requested_roles=normalized_roles,
            settings=analysis_settings,
            duration_seconds=round(duration_seconds, 3),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        remove_path(output_dir)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        traceback.print_exc()
        duration_seconds = time.perf_counter() - analysis_started_at
        write_audit_event(
            "analysis_failed",
            request,
            job_id=job_id,
            client_id=client_id,
            files=audit_uploads(saved_uploads),
            file_count=len(saved_uploads),
            total_upload_bytes=total_upload_bytes,
            requested_roles=normalized_roles,
            settings=analysis_settings,
            duration_seconds=round(duration_seconds, 3),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        remove_path(output_dir)
        raise HTTPException(status_code=500, detail=f"분석 중 오류가 발생했습니다: {exc}") from exc
    except asyncio.CancelledError:
        defer_slot_release(
            analysis_task,
            client_id,
            lambda: (cleanup_job_uploads(upload_dir), remove_path(output_dir)),
        )
        deferred_release = True
        raise
    finally:
        if not deferred_release:
            cleanup_job_uploads(upload_dir)
            await release_analysis_slot(client_id)

    current_user = request.state.current_user
    download_token = create_download_token(
        output_dir,
        job_id,
        owner_username=current_user.username,
        entity_code=entity_code,
    )
    publish_job_output(job_id, output_path)
    save_latest_order_review_result(client_id, job_id, result, "upload")
    save_latest_order_review_workbook(client_id, output_path)
    duration_seconds = time.perf_counter() - analysis_started_at
    write_audit_event(
        "analysis_succeeded",
        request,
        job_id=job_id,
        client_id=client_id,
        files=result["uploaded_files"],
        file_count=len(saved_uploads),
        total_upload_bytes=total_upload_bytes,
        file_mapping=result["file_mapping"],
        settings=result["settings"],
        summary=result["summary"],
        duration_seconds=round(duration_seconds, 3),
        output_filename=output_path.name,
        output_retention_hours=STORAGE_MAX_AGE_HOURS,
    )

    return {
        "job_id": job_id,
        "status": "success",
        "summary": result["summary"],
        "tables": result["tables"],
        "download_url": f"/api/download/{job_id}?token={download_token}",
        "settings": result["settings"],
        "file_mapping": result["file_mapping"],
        "uploaded_files": result["uploaded_files"],
        "season_analysis": result.get("season_analysis"),
        "ingredient_analysis": result.get("ingredient_analysis"),
        "entity_code": entity_code,
    }
