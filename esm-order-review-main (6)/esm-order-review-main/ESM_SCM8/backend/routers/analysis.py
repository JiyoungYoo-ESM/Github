"""Excel-upload analysis, latest order-review lookup and result download."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, RedirectResponse, Response

from backend.schemas import AnalysisResponse
from backend.config import DOWNLOAD_WAIT_FOR_OUTPUT_SECONDS
from backend.services.audit import client_id_from_request, write_audit_event
from backend.services.order_review_store import (
    load_latest_order_review_result,
    latest_order_review_workbook_path,
)
from backend.services.storage import (
    ensure_storage_dirs,
    object_download_url,
    output_path_for_job_async,
    recover_download_url,
    restore_download_url_from_archive,
    verify_download_token,
)
from backend.services.uploaded_analysis_service import run_uploaded_analysis
from core.export_excel_sheets import render_order_review_workbook_for_scenario

router = APIRouter()


@router.post("/api/analyze", response_model=AnalysisResponse)
async def analyze(
    request: Request,
    files: Annotated[list[UploadFile], File(description="Excel files to upload")],
    roles: Annotated[
        list[str] | None,
        Form(description="Optional file roles in the same order as files. Recommended for comparison runs."),
    ] = None,
    eur_krw_rate: Annotated[
        float | None,
        Form(description="Optional fixed EUR/KRW rate for this analysis job."),
    ] = None,
    safety_months: Annotated[
        float | None,
        Form(description="Optional safety stock target in months."),
    ] = None,
    sku_shortage_threshold_pct: Annotated[
        float | None,
        Form(description="Optional SKU concentration shortage threshold in percentage points."),
    ] = None,
    sku_overstock_threshold_pct: Annotated[
        float | None,
        Form(description="Optional SKU concentration overstock threshold in percentage points."),
    ] = None,
    lead_time_air: Annotated[
        int | None,
        Form(description="Optional air lead time in days."),
    ] = None,
    lead_time_sea: Annotated[
        int | None,
        Form(description="Optional sea lead time in days."),
    ] = None,
    lead_time_rail: Annotated[
        int | None,
        Form(description="Optional rail lead time in days."),
    ] = None,
    lead_time_truck: Annotated[
        int | None,
        Form(description="Optional truck lead time in days."),
    ] = None,
    lead_time_overrides: Annotated[
        str | None,
        Form(
            description=(
                "Optional JSON object mapping entity transport codes to lead-time days, "
                'for example {"OCEAN": 70, "AIR": 15}.'
            )
        ),
    ] = None,
) -> dict[str, object]:
    return await run_uploaded_analysis(
        request=request,
        files=files,
        roles=roles,
        eur_krw_rate=eur_krw_rate,
        safety_months=safety_months,
        sku_shortage_threshold_pct=sku_shortage_threshold_pct,
        sku_overstock_threshold_pct=sku_overstock_threshold_pct,
        lead_time_air=lead_time_air,
        lead_time_sea=lead_time_sea,
        lead_time_rail=lead_time_rail,
        lead_time_truck=lead_time_truck,
        lead_time_overrides=lead_time_overrides,
    )


@router.get("/api/analysis/latest-order-review")
async def latest_order_review(request: Request) -> dict[str, object]:
    await run_in_threadpool(ensure_storage_dirs)
    client_id = client_id_from_request(request)
    payload = await run_in_threadpool(load_latest_order_review_result, client_id)
    if payload is None:
        return {
            "status": "empty",
            "client_id": client_id,
            "row_count": 0,
            "rows": [],
            "eta_row_count": 0,
            "eta_rows": [],
        }
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = []
    eta_rows = payload.get("eta_rows")
    if not isinstance(eta_rows, list):
        eta_rows = []
    job_id = str(payload.get("job_id") or "")
    username = request.state.current_user.username
    entity_code = str(request.state.entity_code)
    download_url = (
        await run_in_threadpool(
            recover_download_url,
            job_id,
            expected_username=username,
            expected_entity_code=entity_code,
        )
        if job_id
        else None
    )
    if job_id and not download_url:
        download_url = await run_in_threadpool(
            restore_download_url_from_archive,
            job_id,
            latest_order_review_workbook_path(client_id),
            owner_username=username,
            entity_code=entity_code,
        )
    return {
        "status": "success" if rows else "empty",
        "client_id": client_id,
        "job_id": job_id or None,
        "download_url": download_url,
        "source": payload.get("source"),
        "saved_at": payload.get("saved_at"),
        "row_count": len(rows),
        "rows": rows,
        # 세션 복구 시 재고공백 화면이 ETA 상세와 타임라인 입고 지점을 그리는 데 쓴다.
        "eta_row_count": len(eta_rows),
        "eta_rows": eta_rows,
    }


@router.get("/api/download/{job_id}", response_model=None)
async def download(
    job_id: str,
    request: Request,
    token: Annotated[str, Query(min_length=1)],
    scenario: Annotated[str | None, Query(pattern="^(before|after)$")] = None,
) -> FileResponse | RedirectResponse | Response:
    await run_in_threadpool(ensure_storage_dirs)
    try:
        await run_in_threadpool(
            verify_download_token,
            job_id,
            token,
            expected_username=request.state.current_user.username,
            expected_entity_code=str(request.state.entity_code),
        )
        object_url = await run_in_threadpool(object_download_url, job_id)
        if object_url and scenario is None:
            write_audit_event("download_succeeded", request, job_id=job_id, output_storage="object")
            return RedirectResponse(object_url, status_code=307)
        output_path = await output_path_for_job_async(job_id, wait_seconds=DOWNLOAD_WAIT_FOR_OUTPUT_SECONDS)
        scenario_workbook = (
            await run_in_threadpool(render_order_review_workbook_for_scenario, output_path, scenario)
            if scenario is not None
            else None
        )
    except HTTPException as exc:
        write_audit_event(
            "download_failed",
            request,
            job_id=job_id,
            status_code=exc.status_code,
            detail=exc.detail,
        )
        raise

    write_audit_event(
        "download_succeeded",
        request,
        job_id=job_id,
        output_filename=output_path.name,
        output_storage="scenario-rendered" if scenario_workbook is not None else None,
    )

    # 발주 탭 접근 권한이 있는 계정은 일반 계정이라도 발주 금액을 볼 수 있다.
    # 금액 조회 제한은 분석 화면과 리포트 내보내기에만 적용한다.
    entity_code = str(request.state.entity_code).strip().upper() or "PL"
    download_filename = f"{entity_code}_order_review_{job_id}.xlsx"
    if scenario_workbook is not None:
        return Response(
            content=scenario_workbook,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
        )
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=download_filename,
    )
