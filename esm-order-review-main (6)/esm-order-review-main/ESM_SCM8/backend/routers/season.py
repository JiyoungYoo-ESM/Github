"""HTTP endpoints for uploaded and CMS-backed season analysis."""

from __future__ import annotations

import asyncio
import time
import traceback
from collections.abc import Awaitable
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from backend.season_trend_api_client import (
    EU_SALES_ENDPOINT,
    SEASON_SALES_ENDPOINTS,
    SeasonTrendSourceApiError,
)
from backend.services.audit import client_id_from_request, write_audit_event
from backend.config import SEASON_ANALYSIS_TIMEOUT_SECONDS
from backend.services import analysis_cancel
from backend.services.analysis_tasks import (
    create_analysis_task,
    defer_slot_release,
    wait_without_cancelling,
)
from backend.services.concurrency import (
    acquire_analysis_slot,
    active_analysis_snapshot,
    release_analysis_slot,
)
from backend.auth.permissions import security_scope_from_request
from backend.services.request_validation import normalize_roles, validate_lead_time
from backend.services.season_analysis_options import (
    MAX_DIRECT_RANGE_MONTHS,
    SEASON_DATA_MIN_DATE,
    SEASON_SOURCE_API_MIN_DATE,
    add_months as _add_months,
    validate_season_analysis_options as _validate_options,
)
from backend.services.season_api_analysis_service import (
    exchange_rate_analysis_options,
    run_api_analysis_job,
    run_api_analysis_with_options,
)
from backend.services.season_cache_service import (
    API_ANALYSIS_CACHE_KEYS,
    SEASON_ANALYSIS_SCHEMA_VERSION,
    cached_cross_analysis_complete,
    empty_ingredient_analysis,
    ingredient_analysis_from_cached_season,
    latest_api_analysis_matches,
    with_cached_ingredient_monthly_fields,
)
from backend.services.season_trend_jobs import (
    cancel_season_trend_job,
    create_season_trend_job,
    get_season_trend_job,
    supersede_running_season_trend_jobs,
    update_season_trend_job,
)
from backend.services.season_trend_store import (
    load_latest_season_trend_result,
    save_latest_season_trend_result,
)
from backend.services.season_upload_service import run_uploaded_season_analysis
from backend.services.brand_report_summary import (
    brand_report_summaries_match_source,
    build_brand_report_summaries,
)
from backend.services import task_queue
from backend.services.task_queue import TaskQueueUnavailable
from core.common import korea_today

router = APIRouter()
_season_analysis_tasks: dict[str, asyncio.Task[None]] = {}


async def _acquire_season_analysis_slot(request: Request) -> str:
    client_id = client_id_from_request(request)
    if await acquire_analysis_slot(client_id):
        return client_id
    write_audit_event(
        "season_trend_analysis_rejected",
        request,
        client_id=client_id,
        reason="concurrency_limit",
        active_analysis=active_analysis_snapshot(),
    )
    raise HTTPException(
        status_code=429,
        detail=(
            "이전 분석이 아직 정리되는 중입니다. "
            "잠시 후 다시 시작할 수 있으니 버튼을 반복해서 누르지 않아도 됩니다."
        ),
    )


def _exchange_rate_analysis_options(
    start_date: str | None,
    end_date: str | None,
    entity_code: str = "PL",
) -> dict[str, object]:
    return exchange_rate_analysis_options(start_date, end_date, entity_code=entity_code)


def _validate_season_analysis_options(
    *,
    start_date: str | None,
    end_date: str | None,
    metric: str,
    group_by: str,
    api_source: bool = False,
    entity_code: str = "PL",
) -> tuple[str | None, str | None]:
    return _validate_options(
        start_date=start_date,
        end_date=end_date,
        metric=metric,
        group_by=group_by,
        api_source=api_source,
        entity_code=entity_code,
    )


def _empty_ingredient_analysis() -> dict[str, list[dict[str, object]]]:
    return empty_ingredient_analysis()


def _ingredient_analysis_from_cached_season(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    return ingredient_analysis_from_cached_season(payload)


def _cached_cross_analysis_complete(payload: dict[str, object]) -> bool:
    return cached_cross_analysis_complete(payload)


def _latest_api_analysis_matches(
    analysis_options: dict[str, object],
    security_scope: str = "default",
) -> dict[str, object] | None:
    load_latest = (
        load_latest_season_trend_result
        if security_scope == "default"
        else lambda: load_latest_season_trend_result(security_scope)
    )
    save_latest = (
        save_latest_season_trend_result
        if security_scope == "default"
        else lambda payload: save_latest_season_trend_result(payload, security_scope)
    )
    entity_code = str(analysis_options.get("entity_code") or "PL").strip().upper()
    return latest_api_analysis_matches(
        analysis_options,
        load_latest=load_latest,
        save_latest=save_latest,
        sales_endpoint=SEASON_SALES_ENDPOINTS.get(entity_code, EU_SALES_ENDPOINT),
        schema_version=SEASON_ANALYSIS_SCHEMA_VERSION,
    )


def _with_cached_ingredient_monthly_fields(
    payload: dict[str, object],
    security_scope: str = "default",
) -> dict[str, object]:
    save_latest = (
        save_latest_season_trend_result
        if security_scope == "default"
        else lambda result: save_latest_season_trend_result(result, security_scope)
    )
    return with_cached_ingredient_monthly_fields(
        payload,
        save_latest=save_latest,
    )


def _run_api_analysis_with_options(
    analysis_options: dict[str, object],
    *,
    save_result: bool = True,
) -> dict[str, object]:
    return run_api_analysis_with_options(
        analysis_options,
        save_result=save_result,
        schema_version=SEASON_ANALYSIS_SCHEMA_VERSION,
    )

class SeasonTrendApiAnalyzeRequest(BaseModel):
    start_date: str
    end_date: str
    metric: str = "qty"
    group_by: str = "month"
    include_ingredient: bool = True
    exclude_partial_months: bool = True
    lead_time_air: int | None = None
    lead_time_sea: int | None = None
    lead_time_rail: int | None = None
    lead_time_truck: int | None = None
    warehouse: str | None = None


class SeasonTrendApiJobStartResponse(BaseModel):
    job_id: str | None = None
    status: str
    result: dict[str, object] | None = None

def _api_analysis_options_from_body(
    body: SeasonTrendApiAnalyzeRequest,
    *,
    entity_code: str = "PL",
) -> dict[str, object]:
    analysis_start_date, analysis_end_date = _validate_season_analysis_options(
        start_date=body.start_date,
        end_date=body.end_date,
        metric=body.metric,
        group_by=body.group_by,
        api_source=True,
        entity_code=entity_code,
    )
    if not analysis_start_date or not analysis_end_date:
        raise HTTPException(status_code=400, detail="분석 시작일과 종료일을 선택해 주세요.")

    warehouse = str(body.warehouse or "").strip().upper() or None
    if warehouse and entity_code != "HQ":
        raise HTTPException(status_code=400, detail="창고별 분석은 본사에서만 사용할 수 있습니다.")
    if warehouse and (len(warehouse) > 40 or not all(character.isalnum() or character in {"-", "_"} for character in warehouse)):
        raise HTTPException(status_code=400, detail="올바른 창고 코드를 선택해 주세요.")

    return {
        "start_date": analysis_start_date,
        "end_date": analysis_end_date,
        "metric": body.metric,
        "group_by": body.group_by,
        # 실제 법인별 필터는 request의 entity_code를 확인하는
        # _scope_analysis_options에서 확정한다.
        "eu_local": True,
        "include_ingredient": body.include_ingredient,
        "exclude_partial_months": body.exclude_partial_months,
        "lead_time_air": validate_lead_time(body.lead_time_air, "lead_time_air"),
        "lead_time_sea": validate_lead_time(body.lead_time_sea, "lead_time_sea"),
        "lead_time_rail": validate_lead_time(body.lead_time_rail, "lead_time_rail"),
        "lead_time_truck": validate_lead_time(body.lead_time_truck, "lead_time_truck"),
        "warehouse": warehouse,
    }


def _api_analysis_options_for_request(
    request: Request,
    body: SeasonTrendApiAnalyzeRequest,
) -> dict[str, object]:
    entity_code = str(
        getattr(getattr(request, "state", None), "entity_code", "PL") or "PL"
    ).strip().upper()
    if entity_code == "PL":
        return _api_analysis_options_from_body(body)
    return _api_analysis_options_from_body(body, entity_code=entity_code)


def _scope_analysis_options(request: Request, options: dict[str, object]) -> tuple[str, dict[str, object]]:
    security_scope = security_scope_from_request(request)
    entity_code = str(request.state.entity_code).strip().upper()
    return security_scope, {
        **options,
        "entity_code": entity_code,
        # PL/USA endpoints are local subsidiaries; HQ history uses the
        # existing headquarters KR transaction-type policy.
        "eu_local": entity_code in {"PL", "USA"},
        "security_scope": security_scope,
    }

async def _run_api_analysis_job(job_id: str, analysis_options: dict[str, object], client_id: str) -> None:
    try:
        await run_api_analysis_job(job_id, analysis_options)
    finally:
        await release_analysis_slot(client_id)


async def _run_limited_season_analysis(
    request: Request,
    operation: Awaitable[dict[str, object]],
) -> dict[str, object]:
    client_id = await _acquire_season_analysis_slot(request)
    analysis_task = create_analysis_task(operation)
    deferred_release = False
    try:
        completed, result = await wait_without_cancelling(analysis_task, SEASON_ANALYSIS_TIMEOUT_SECONDS)
        if not completed:
            defer_slot_release(analysis_task, client_id, lambda: None)
            deferred_release = True
            write_audit_event(
                "season_trend_analysis_timeout",
                request,
                client_id=client_id,
                timeout_seconds=SEASON_ANALYSIS_TIMEOUT_SECONDS,
            )
            raise HTTPException(
                status_code=504,
                detail=f"Analysis exceeded {SEASON_ANALYSIS_TIMEOUT_SECONDS} seconds. Please try again later.",
            )
        assert result is not None
        return result
    finally:
        if not deferred_release:
            await release_analysis_slot(client_id)


async def _run_limited_api_analysis(request: Request, analysis_options: dict[str, object]) -> dict[str, object]:
    return await _run_limited_season_analysis(
        request,
        run_in_threadpool(_run_api_analysis_with_options, analysis_options),
    )


@router.get("/api/season-trend/latest")
async def latest_season_trend(request: Request) -> dict[str, object]:
    security_scope = security_scope_from_request(request)
    payload = load_latest_season_trend_result(security_scope)
    if payload is None:
        raise HTTPException(status_code=404, detail="최근 시즌/수요 분석 결과가 없습니다.")
    if (
        payload.get("analysis_schema_version") != SEASON_ANALYSIS_SCHEMA_VERSION
        or not _cached_cross_analysis_complete(payload)
    ):
        raise HTTPException(status_code=409, detail="교차분석 데이터 구조가 변경되었습니다. 분석을 다시 실행해 주세요.")
    return await run_in_threadpool(_with_cached_ingredient_monthly_fields, payload, security_scope)


@router.get("/api/season-trend/brand-reports")
async def latest_brand_reports(request: Request) -> dict[str, object]:
    """Return only the bounded aggregates needed by the brand-report screen."""
    security_scope = security_scope_from_request(request)
    payload = load_latest_season_trend_result(security_scope)
    if payload is None:
        raise HTTPException(status_code=404, detail="No recent season analysis result.")
    if payload.get("analysis_schema_version") != SEASON_ANALYSIS_SCHEMA_VERSION or not _cached_cross_analysis_complete(payload):
        raise HTTPException(status_code=409, detail="Analysis result must be regenerated.")
    season = payload.get("season_analysis")
    if not isinstance(season, dict):
        raise HTTPException(status_code=409, detail="Analysis result is incomplete.")
    reports = season.get("brandReports")
    if not brand_report_summaries_match_source(season, reports):
        reports = await run_in_threadpool(build_brand_report_summaries, season)
        season["brandReports"] = reports
        save_latest_season_trend_result(payload, security_scope)
    analysis_options = payload.get("analysis_options")
    if not isinstance(analysis_options, dict):
        analysis_options = {}
    today = korea_today().isoformat()
    if analysis_options.get("exchange_rate_checked_date") != today:
        current_exchange = await run_in_threadpool(
            _exchange_rate_analysis_options,
            analysis_options.get("start_date"),
            analysis_options.get("end_date"),
            analysis_options.get("entity_code", "PL"),
        )
        analysis_options = {**analysis_options, **current_exchange}
        payload["analysis_options"] = analysis_options
        save_latest_season_trend_result(payload, security_scope)
    return {
        "brandReports": reports,
        "monthCoverage": season.get("monthCoverage", []),
        "dataQuality": season.get("sourceDataQuality", {}),
        "analysisOptions": analysis_options,
    }


@router.post("/api/season-trend/analyze-api/jobs", response_model=SeasonTrendApiJobStartResponse)
async def start_season_trend_api_job(request: Request, body: SeasonTrendApiAnalyzeRequest) -> SeasonTrendApiJobStartResponse:
    security_scope, analysis_options = _scope_analysis_options(
        request,
        _api_analysis_options_for_request(request, body),
    )
    cached_payload = _latest_api_analysis_matches(analysis_options, security_scope)
    if cached_payload is not None:
        supersede_running_season_trend_jobs(security_scope)
        cached_options = cached_payload.get("analysis_options") if isinstance(cached_payload, dict) else None
        if (
            isinstance(cached_options, dict)
            and not cached_options.get("currency_code")
            and not cached_options.get("average_eur_krw_rate")
        ):
            exchange_options = await run_in_threadpool(
                _exchange_rate_analysis_options,
                analysis_options["start_date"],
                analysis_options["end_date"],
                analysis_options.get("entity_code", "PL"),
            )
            cached_payload = {
                **cached_payload,
                "analysis_options": {**cached_options, **exchange_options},
            }
        write_audit_event("season_trend_api_analysis_cache_hit", request, analysis_options=analysis_options)
        return SeasonTrendApiJobStartResponse(status="succeeded", result=cached_payload)

    # A production request is queued first and consumes a concurrency slot only
    # when a worker actually starts it. Reserving the slot here used to leave a
    # browser blocked for the full lease TTL when Redis accepted a message but
    # no worker consumed it. Local development still acquires here because it
    # starts the in-process task immediately below.
    client_id = client_id_from_request(request)
    local_slot_acquired = False
    if not task_queue.enabled():
        client_id = await _acquire_season_analysis_slot(request)
        local_slot_acquired = True
    try:
        job_id = create_season_trend_job(analysis_options, security_scope)
    except Exception:
        if local_slot_acquired:
            await release_analysis_slot(client_id)
        raise
    write_audit_event("season_trend_api_analysis_job_queued", request, job_id=job_id, analysis_options=analysis_options)
    if task_queue.enabled():
        try:
            task_queue.enqueue_season(job_id, analysis_options, client_id)
        except TaskQueueUnavailable as exc:
            update_season_trend_job(
                job_id,
                status="failed",
                status_code=503,
                error="분석 작업을 대기열에 등록하지 못했습니다.",
            )
            raise HTTPException(status_code=503, detail="Analysis worker queue is unavailable.") from exc
    else:
        # Local development remains runnable without a worker service.
        task = asyncio.create_task(_run_api_analysis_job(job_id, analysis_options, client_id))
        _season_analysis_tasks[job_id] = task
        task.add_done_callback(
            lambda completed, current_job_id=job_id: _season_analysis_tasks.pop(current_job_id, None)
        )
    return SeasonTrendApiJobStartResponse(job_id=job_id, status="queued")


@router.get("/api/season-trend/analyze-api/jobs/{job_id}")
async def season_trend_api_job_status(job_id: str, request: Request) -> dict[str, object]:
    job = get_season_trend_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="분석 작업을 찾을 수 없습니다. 다시 분석을 시작해 주세요.")
    if job.get("security_scope") != security_scope_from_request(request):
        raise HTTPException(status_code=403, detail="다른 계정의 분석 작업에는 접근할 수 없습니다.")
    return job


@router.delete("/api/season-trend/analyze-api/jobs/{job_id}")
async def cancel_season_trend_api_job(job_id: str, request: Request) -> dict[str, object]:
    job = get_season_trend_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="분석 작업을 찾을 수 없습니다.")
    if job.get("security_scope") != security_scope_from_request(request):
        raise HTTPException(status_code=403, detail="다른 계정의 분석 작업에는 접근할 수 없습니다.")
    if job.get("status") in {"succeeded", "failed", "cancelled"}:
        return job
    # Signal the CMS page loops before cancelling the task so queued pages stop
    # hitting CMS instead of competing with the user's next analysis.
    analysis_cancel.cancel(job_id)
    cancelled = cancel_season_trend_job(job_id)
    task = _season_analysis_tasks.get(job_id)
    if task is not None and not task.done():
        task.cancel()
    assert cancelled is not None
    return cancelled


@router.post("/api/season-trend/analyze-api")
async def analyze_season_trend_from_api(request: Request, body: SeasonTrendApiAnalyzeRequest) -> dict[str, object]:
    security_scope, analysis_options = _scope_analysis_options(
        request,
        _api_analysis_options_for_request(request, body),
    )
    supersede_running_season_trend_jobs(security_scope)

    cached_payload = _latest_api_analysis_matches(analysis_options, security_scope)
    if cached_payload is not None:
        cached_options = cached_payload.get("analysis_options") if isinstance(cached_payload, dict) else None
        if (
            isinstance(cached_options, dict)
            and not cached_options.get("currency_code")
            and not cached_options.get("average_eur_krw_rate")
        ):
            exchange_options = await run_in_threadpool(
                _exchange_rate_analysis_options,
                analysis_options["start_date"],
                analysis_options["end_date"],
                analysis_options.get("entity_code", "PL"),
            )
            cached_payload = {
                **cached_payload,
                "analysis_options": {**cached_options, **exchange_options},
            }
        write_audit_event("season_trend_api_analysis_cache_hit", request, analysis_options=analysis_options)
        return cached_payload

    started_at = time.perf_counter()
    write_audit_event("season_trend_api_analysis_started", request, analysis_options=analysis_options)
    try:
        response_payload = await _run_limited_api_analysis(request, analysis_options)
    except HTTPException as exc:
        write_audit_event(
            "season_trend_api_analysis_failed",
            request,
            status_code=exc.status_code,
            detail=exc.detail,
            analysis_options=analysis_options,
        )
        raise
    except SeasonTrendSourceApiError as exc:
        write_audit_event(
            "season_trend_api_analysis_failed",
            request,
            error_type=type(exc).__name__,
            error=str(exc),
            analysis_options=analysis_options,
        )
        raise HTTPException(status_code=502, detail=f"CMS 시즌 분석 API 호출에 실패했습니다: {exc}") from exc
    except ValueError as exc:
        write_audit_event(
            "season_trend_api_analysis_failed",
            request,
            error_type=type(exc).__name__,
            error=str(exc),
            analysis_options=analysis_options,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        traceback.print_exc()
        write_audit_event(
            "season_trend_api_analysis_failed",
            request,
            error_type=type(exc).__name__,
            error=str(exc),
            analysis_options=analysis_options,
        )
        raise HTTPException(status_code=500, detail=f"시즌/수요 분석 중 오류가 발생했습니다: {exc}") from exc

    write_audit_event(
        "season_trend_api_analysis_succeeded",
        request,
        files=response_payload.get("uploaded_files"),
        source_meta=response_payload.get("source_meta"),
        analysis_options=response_payload.get("analysis_options"),
        duration_seconds=round(time.perf_counter() - started_at, 3),
    )
    return response_payload


@router.post("/api/season-trend/analyze")
async def analyze_season_trend(
    request: Request,
    files: Annotated[list[UploadFile], File(description="Season/trend Excel files to upload")],
    roles: Annotated[
        list[str] | None,
        Form(description="File roles in the same order as files. Allowed: sales_history, prod_list, category_correction."),
    ] = None,
    start_date: Annotated[
        str | None,
        Form(description="Optional analysis start date in YYYY-MM-DD format."),
    ] = None,
    end_date: Annotated[
        str | None,
        Form(description="Optional analysis end date in YYYY-MM-DD format."),
    ] = None,
    metric: Annotated[
        str,
        Form(description="Analysis metric. Allowed: qty, amount."),
    ] = "qty",
    group_by: Annotated[
        str,
        Form(description="Analysis grain. Allowed: month, quarter, year."),
    ] = "month",
    include_ingredient: Annotated[
        bool,
        Form(description="Whether to include slower ingredient trend tables."),
    ] = False,
    exclude_partial_months: Annotated[
        bool,
        Form(description="Whether to exclude incomplete first/last months from seasonality calculations."),
    ] = True,
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
) -> dict[str, object]:
    if not files:
        write_audit_event("season_trend_analysis_failed", request, reason="no_files")
        raise HTTPException(status_code=400, detail="시즌/트렌드 분석용 파일을 1개 이상 선택해 주세요.")

    try:
        normalized_roles = normalize_roles(roles, len(files))
    except HTTPException as exc:
        write_audit_event(
            "season_trend_analysis_failed",
            request,
            reason="invalid_roles",
            status_code=exc.status_code,
            detail=exc.detail,
        )
        raise

    if not normalized_roles:
        raise HTTPException(status_code=400, detail="시즌/트렌드 전용 업로드는 파일 role 지정이 필요합니다.")

    allowed_roles = {"sales_history", "prod_list", "category_correction"}
    invalid_roles = sorted(set(normalized_roles) - allowed_roles)
    if invalid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"시즌/트렌드 업로드에는 sales_history, prod_list만 사용할 수 있습니다: {', '.join(invalid_roles)}",
        )
    if "sales_history" not in normalized_roles:
        raise HTTPException(status_code=400, detail="장기 판매이력 파일은 필수입니다.")

    analysis_start_date, analysis_end_date = _validate_season_analysis_options(
        start_date=start_date,
        end_date=end_date,
        metric=metric,
        group_by=group_by,
    )
    analysis_options = {
        "start_date": analysis_start_date,
        "end_date": analysis_end_date,
        "metric": metric,
        "group_by": group_by,
        "include_ingredient": include_ingredient,
        "exclude_partial_months": exclude_partial_months,
        "lead_time_air": validate_lead_time(lead_time_air, "lead_time_air"),
        "lead_time_sea": validate_lead_time(lead_time_sea, "lead_time_sea"),
        "lead_time_rail": validate_lead_time(lead_time_rail, "lead_time_rail"),
        "lead_time_truck": validate_lead_time(lead_time_truck, "lead_time_truck"),
    }
    exchange_options = await run_in_threadpool(
        _exchange_rate_analysis_options,
        analysis_start_date,
        analysis_end_date,
        str(request.state.entity_code),
    )
    analysis_options = {**analysis_options, **exchange_options}
    _, analysis_options = _scope_analysis_options(request, analysis_options)

    return await _run_limited_season_analysis(
        request,
        run_uploaded_season_analysis(
            request=request,
            files=files,
            normalized_roles=normalized_roles,
            analysis_options=analysis_options,
            schema_version=SEASON_ANALYSIS_SCHEMA_VERSION,
        ),
    )
