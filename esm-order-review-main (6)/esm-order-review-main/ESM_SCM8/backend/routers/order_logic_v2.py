"""HTTP routes for the HQ/PL/USA order-logic v2 workflow."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from backend.auth.amount_permissions import can_manage_order_logic_v2_settings
from backend.schemas_order_logic_v2 import (
    OrderLogicV2ExportRequest,
    OrderLogicV2JobRequest,
    OrderLogicV2JobStartResponse,
    OrderLogicV2Settings,
)
from backend.services.audit import client_id_from_request, write_audit_event
from backend.services.order_logic_v2_service import (
    OrderLogicV2DecisionError,
    build_order_logic_v2_export,
    cancel_order_logic_v2_job,
    latest_order_logic_v2_result,
    owned_order_logic_v2_job,
    payload_visible_to_user,
    queue_order_logic_v2_job,
)


router = APIRouter(prefix="/api/order-logic-v2", tags=["order-logic-v2"])


def _require_v2_policy_configuration(request: Request) -> None:
    entity_code = str(request.state.entity_code)
    if entity_code not in {"HQ", "PL", "USA"}:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{entity_code} 법인의 신규 발주 로직 V2 정책값이 아직 확정되지 않았습니다. "
                "PL 리드타임·시그마를 대체 적용하지 않고 계산을 차단합니다."
            ),
        )


def _require_advanced_settings_permission(
    request: Request,
    body: OrderLogicV2JobRequest,
) -> None:
    if can_manage_order_logic_v2_settings(request.state.current_user):
        return
    if body.settings != OrderLogicV2Settings():
        raise HTTPException(
            status_code=403,
            detail=(
                "일반계정은 적용 시나리오만 선택할 수 있습니다. "
                "서비스 수준·재고 기준·운송 리드타임 설정은 기본값을 사용해 주세요."
            ),
        )


@router.post(
    "/jobs",
    response_model=OrderLogicV2JobStartResponse,
    status_code=202,
)
async def start_order_logic_v2_job(
    request: Request,
    body: OrderLogicV2JobRequest,
) -> dict[str, object]:
    _require_v2_policy_configuration(request)
    _require_advanced_settings_permission(request, body)
    client_id = client_id_from_request(request)
    request_body = body.model_dump(mode="json")
    request_body["entity_code"] = str(request.state.entity_code)
    job_id = queue_order_logic_v2_job(client_id, request_body)
    write_audit_event(
        "order_logic_v2_job_queued",
        request,
        job_id=job_id,
        client_id=client_id,
        as_of=request_body["as_of"],
        applied_mode=request_body["applied_mode"],
        preview=request_body["preview"],
        settings=request_body["settings"],
    )
    return {"job_id": job_id, "status": "queued"}


@router.get("/jobs/{job_id}")
async def order_logic_v2_job_status(
    job_id: str,
    request: Request,
) -> dict[str, object]:
    _require_v2_policy_configuration(request)
    client_id = client_id_from_request(request)
    job = await run_in_threadpool(
        owned_order_logic_v2_job,
        job_id,
        client_id,
    )
    return payload_visible_to_user(job, request.state.current_user)


@router.delete("/jobs/{job_id}")
async def cancel_order_logic_v2_job_api(job_id: str, request: Request) -> dict[str, object]:
    _require_v2_policy_configuration(request)
    client_id = client_id_from_request(request)
    cancelled = await run_in_threadpool(cancel_order_logic_v2_job, job_id, client_id)
    return payload_visible_to_user(cancelled, request.state.current_user)


@router.get("/latest")
async def latest_order_logic_v2(
    request: Request,
) -> dict[str, object]:
    _require_v2_policy_configuration(request)
    client_id = client_id_from_request(request)
    payload = await run_in_threadpool(
        latest_order_logic_v2_result,
        client_id,
        str(request.state.entity_code),
    )
    if payload is None:
        return {
            "status": "empty",
            "applied_mode": None,
            "summary": {},
            "rows": [],
            "scenarios": {},
        }
    return payload_visible_to_user(payload, request.state.current_user)


@router.post("/export", response_model=None)
async def export_order_logic_v2(
    request: Request,
    body: OrderLogicV2ExportRequest,
) -> Response:
    _require_v2_policy_configuration(request)
    client_id = client_id_from_request(request)
    overrides = [
        override.model_dump(mode="json")
        for override in body.overrides
    ]
    try:
        content, filename = await run_in_threadpool(
            build_order_logic_v2_export,
            job_id=body.job_id,
            client_id=client_id,
            user=request.state.current_user,
            overrides=overrides,
            export_mode=body.export_mode,
            row_ids=body.row_ids,
            entity_code=str(request.state.entity_code),
        )
    except OrderLogicV2DecisionError as exc:
        write_audit_event(
            "order_logic_v2_export_rejected",
            request,
            job_id=body.job_id,
            reason="invalid_decision_override",
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    write_audit_event(
        "order_logic_v2_export_succeeded",
        request,
        job_id=body.job_id,
        export_mode=body.export_mode,
        override_count=len(overrides),
        row_count=(len(body.row_ids) if body.row_ids is not None else None),
        filename=filename,
    )
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


__all__ = ["router"]
