"""HTTP routes for the V3 textbook calculation workflow."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from backend.services.order_logic_v3_delivery import PAGE_SIZE, result_page_response, status_response
from backend.services.order_logic_v3_result_store import is_paged_result

from backend.schemas_order_logic_v3 import (
    OrderLogicV3JobRequest,
    OrderLogicV3JobStartResponse,
)
from backend.services.audit import client_id_from_request, write_audit_event
from backend.services.order_logic_v3_service import (
    cancel_order_logic_v3_job,
    owned_order_logic_v3_job,
    payload_visible_to_user,
    queue_order_logic_v3_job,
)
from backend.services.order_logic_v3_season_factor_jobs import queue_refresh, refresh_status
from backend.services.order_logic_v3_season_factor_store import (
    SeasonFactorArtifactError,
    load_active_artifact,
)
from core.common import korea_today


router = APIRouter(prefix="/api/order-logic-v3", tags=["order-logic-v3"])


@router.post("/jobs", response_model=OrderLogicV3JobStartResponse, status_code=202)
async def start_order_logic_v3_job(
    request: Request,
    body: OrderLogicV3JobRequest,
) -> dict[str, object]:
    client_id = client_id_from_request(request)
    request_body = body.model_dump(mode="json")
    request_body["entity_code"] = str(request.state.entity_code)
    job_id = queue_order_logic_v3_job(client_id, request_body)
    write_audit_event(
        "order_logic_v3_job_queued",
        request,
        job_id=job_id,
        client_id=client_id,
        as_of=request_body["as_of"],
        entity_code=request_body["entity_code"],
        preview=True,
    )
    return {"job_id": job_id, "status": "queued"}


@router.get("/jobs/{job_id}", response_model=None)
async def order_logic_v3_job_status(
    job_id: str,
    request: Request,
    include_result: bool = True,
) -> dict[str, object] | JSONResponse:
    client_id = client_id_from_request(request)
    if not include_result:
        return await run_in_threadpool(
            status_response, job_id, client_id, str(request.state.entity_code), request.state.current_user,
        )
    job = await run_in_threadpool(owned_order_logic_v3_job, job_id, client_id)
    if is_paged_result(job.get("result")):
        return await run_in_threadpool(
            status_response, job_id, client_id, str(request.state.entity_code), request.state.current_user,
        )
    return payload_visible_to_user(job, request.state.current_user, already_isolated=True)


@router.get("/jobs/{job_id}/result")
async def order_logic_v3_result_page(
    job_id: str, request: Request,
    offset: int = Query(0, ge=0), limit: int = Query(PAGE_SIZE, ge=1, le=PAGE_SIZE),
) -> JSONResponse:
    return await run_in_threadpool(
        result_page_response, job_id, client_id_from_request(request), str(request.state.entity_code),
        request.state.current_user, offset, limit,
    )


@router.delete("/jobs/{job_id}")
async def stop_order_logic_v3_job(job_id: str, request: Request) -> dict[str, object]:
    client_id = client_id_from_request(request)
    entity_code = str(request.state.entity_code)
    job = await run_in_threadpool(cancel_order_logic_v3_job, job_id, client_id, entity_code)
    write_audit_event(
        "order_logic_v3_job_stop_requested", request,
        job_id=job_id, client_id=client_id, entity_code=entity_code, status=job["status"],
    )
    return {"job_id": job_id, "status": job["status"]}


@router.get("/season-factors/active")
async def active_order_logic_v3_season_factors(
    request: Request,
) -> dict[str, object]:
    try:
        return await run_in_threadpool(
            load_active_artifact,
            str(request.state.entity_code),
        )
    except SeasonFactorArtifactError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.reason_code, "message": str(exc)},
        ) from exc


@router.get("/season-factors/refresh/status")
async def season_factor_refresh_status(request: Request) -> dict[str, object]:
    return refresh_status(str(request.state.entity_code))


@router.post("/season-factors/refresh", status_code=202)
async def refresh_order_logic_v3_season_factor_artifact(
    request: Request,
) -> dict[str, object]:
    if not request.state.current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="시즌팩터 운영 artifact 갱신은 관리자만 실행할 수 있습니다.",
        )
    entity_code = str(request.state.entity_code)
    job = queue_refresh(
        as_of=korea_today().isoformat(),
        entity_code=entity_code,
        force_refresh=True,
    )
    write_audit_event(
        "order_logic_v3_season_factor_manual_refresh_queued",
        request,
        entity_code=entity_code,
        job_id=job.get("job_id"),
        status=job.get("status"),
    )
    return job


__all__ = ["router"]
