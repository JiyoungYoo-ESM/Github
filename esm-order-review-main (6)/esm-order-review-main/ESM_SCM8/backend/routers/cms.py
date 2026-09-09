"""HTTP routes for analysis driven directly from the CMS API."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from backend.auth.permissions import require_order_integration
from backend.schemas import (
    AnalysisJobStartResponse,
    AnalysisJobStatusResponse,
    AnalysisResponse,
    CmsAnalyzeRequest,
)
from backend.services.cms_analysis_service import (
    cancel_local_cms_analysis,
    cms_analysis_job_result,
    queue_cms_analysis,
    run_cms_analysis,
)
from backend.services.cms_analysis_jobs import cancel_cms_analysis_job
from backend.services.audit import client_id_from_request
from backend.services import task_queue
from backend.services.task_queue import TaskQueueUnavailable

router = APIRouter()


@router.post("/api/analyze/cms/jobs", response_model=AnalysisJobStartResponse)
async def start_cms_analysis_job(
    request: Request,
    body: CmsAnalyzeRequest,
) -> dict[str, object]:
    require_order_integration(request)
    return await queue_cms_analysis(request, body)


@router.get("/api/analyze/cms/jobs/{job_id}", response_model=AnalysisJobStatusResponse)
async def cms_analysis_job_status(job_id: str, request: Request) -> dict[str, object]:
    return cms_analysis_job_result(job_id, client_id_from_request(request))


@router.delete("/api/analyze/cms/jobs/{job_id}")
async def cancel_cms_analysis(job_id: str, request: Request) -> dict[str, object]:
    client_id = client_id_from_request(request)
    current = cms_analysis_job_result(job_id, client_id)
    if current.get("status") in {"succeeded", "failed", "cancelled"}:
        return current
    cancelled = cancel_cms_analysis_job(job_id)
    if cancelled is None:
        raise HTTPException(status_code=404, detail="분석 작업을 찾을 수 없습니다.")
    cancel_local_cms_analysis(job_id)
    if task_queue.enabled():
        try:
            task_queue.cancel_cms(job_id)
        except TaskQueueUnavailable as exc:
            raise HTTPException(status_code=503, detail="분석 작업 중단 신호를 보내지 못했습니다.") from exc
    return cancelled


@router.post("/api/analyze/cms", response_model=AnalysisResponse)
async def analyze_from_cms(
    request: Request,
    body: CmsAnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, object]:
    require_order_integration(request)
    return await run_cms_analysis(
        request=request,
        body=body,
        background_tasks=background_tasks,
    )
