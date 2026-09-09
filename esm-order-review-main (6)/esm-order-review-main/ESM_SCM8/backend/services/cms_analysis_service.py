"""CMS analysis application service.

Owns request validation, cached CMS acquisition, core-analysis orchestration,
background job lifecycle, audit events, and deferred workbook generation. HTTP
route declarations stay in backend.routers.cms.
"""

from __future__ import annotations

import asyncio
import time
import traceback
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import BackgroundTasks, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from backend.services.order_analysis_workflow import DeferredExcelExport, run_core_analysis_from_uploaded_data
from backend.cms_client import CmsAuthenticationError
from backend.cms_mapping import build_cms_classifications, build_uploaded_data_from_cms
from backend.config import (
    CMS_ANALYSIS_TIMEOUT_SECONDS,
    MAX_ANALYSES_PER_CLIENT,
    MAX_CONCURRENT_ANALYSES,
    OUTPUT_DIR,
    STORAGE_MAX_AGE_HOURS,
)
from backend.schemas import CmsAnalyzeRequest
from backend.services.analysis_memo import (
    analysis_memo_key,
    get_memoized_analysis,
    store_memoized_analysis,
)
from backend.services.analysis_tasks import create_analysis_task, defer_slot_release, wait_without_cancelling
from backend.services.audit import client_id_from_request, write_audit_event
from backend.services.cms_analysis_jobs import create_cms_analysis_job, get_cms_analysis_job, update_cms_analysis_job
from backend.services.concurrency import (
    acquire_analysis_slot,
    active_analysis_snapshot,
    release_analysis_slot,
)
from backend.services.cms_source import fetch_cached_cms_raw_data, resolve_cms_effective_dates
from backend.services.order_review_store import save_latest_order_review_result, save_latest_order_review_workbook
from backend.services.request_validation import (
    compact_optional_settings,
    validate_eur_krw_rate,
    validate_lead_time,
    validate_lead_time_overrides,
    validate_month_setting,
    validate_percent_threshold,
)
from backend.services.storage import create_download_token, ensure_storage_dirs, publish_job_output, remove_path
from backend.services import task_queue
from backend.services.task_queue import TaskQueueUnavailable

_cms_analysis_tasks: dict[str, asyncio.Task[None]] = {}


def cancel_local_cms_analysis(job_id: str) -> bool:
    task = _cms_analysis_tasks.get(job_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


def _perf_log(job_id: str, message: str, **fields: object) -> None:
    suffix = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    print(f"[perf][cms_analysis] job_id={job_id} {message}{(' ' + suffix) if suffix else ''}", flush=True)


def _write_deferred_excel_export(export: DeferredExcelExport, job_id: str, output_filename: str, client_id: str) -> None:
    try:
        export.write()
    except Exception as exc:
        traceback.print_exc()
        write_audit_event(
            "cms_excel_failed",
            None,
            job_id=job_id,
            output_filename=output_filename,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return
    save_latest_order_review_workbook(client_id, export.output_path)
    try:
        publish_job_output(job_id, export.output_path)
    except Exception as exc:  # noqa: BLE001
        write_audit_event(
            "cms_excel_object_storage_failed",
            None,
            job_id=job_id,
            output_filename=output_filename,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return
    write_audit_event(
        "cms_excel_succeeded",
        None,
        job_id=job_id,
        output_filename=output_filename,
    )


def _cms_request_payload(body: CmsAnalyzeRequest) -> dict[str, object]:
    return {
        "as_of": body.as_of,
        "date_from": body.date_from,
        "eur_krw_rate": body.eur_krw_rate,
        "safety_months": body.safety_months,
        "sku_shortage_threshold_pct": body.sku_shortage_threshold_pct,
        "sku_overstock_threshold_pct": body.sku_overstock_threshold_pct,
        "lead_time_air": body.lead_time_air,
        "lead_time_sea": body.lead_time_sea,
        "lead_time_rail": body.lead_time_rail,
        "lead_time_truck": body.lead_time_truck,
        "lead_time_overrides": body.lead_time_overrides,
    }


def _cms_analysis_context_from_body(
    body: CmsAnalyzeRequest,
    entity_code: str = "PL",
) -> dict[str, object]:
    fixed_eur_krw_rate = validate_eur_krw_rate(body.eur_krw_rate)
    analysis_settings = compact_optional_settings(
        {
            "safety_months": validate_month_setting(body.safety_months, "safety_months"),
            "sku_shortage_threshold_pct": validate_percent_threshold(
                body.sku_shortage_threshold_pct,
                "sku_shortage_threshold_pct",
            ),
            "sku_overstock_threshold_pct": validate_percent_threshold(
                body.sku_overstock_threshold_pct,
                "sku_overstock_threshold_pct",
            ),
            "lead_time_air": validate_lead_time(body.lead_time_air, "lead_time_air"),
            "lead_time_sea": validate_lead_time(body.lead_time_sea, "lead_time_sea"),
            "lead_time_rail": validate_lead_time(body.lead_time_rail, "lead_time_rail"),
            "lead_time_truck": validate_lead_time(body.lead_time_truck, "lead_time_truck"),
        }
    )
    analysis_settings["entity_code"] = entity_code
    dynamic_lead_time_overrides = validate_lead_time_overrides(
        body.lead_time_overrides,
        entity_code,
    )
    if dynamic_lead_time_overrides:
        analysis_settings["lead_time_overrides"] = dynamic_lead_time_overrides
    date_context = resolve_cms_effective_dates(body.as_of, body.date_from)
    analysis_settings.update(date_context.analysis_settings)
    return {
        "fixed_eur_krw_rate": fixed_eur_krw_rate,
        "analysis_settings": analysis_settings,
        "effective_date_from": date_context.date_from,
        "effective_logistics_date_from": date_context.logistics_date_from,
        "effective_date_to": date_context.date_to,
    }


def _fetch_and_analyze_from_cms(
    *,
    body: CmsAnalyzeRequest,
    job_id: str,
    output_path,
    fixed_eur_krw_rate: float | None,
    analysis_settings: dict[str, object],
    effective_date_from: str,
    security_scope: str,
    entity_code: str,
) -> dict[str, object]:
    fetch_started_at = time.perf_counter()
    raw, cms_fetch_cache, _ = fetch_cached_cms_raw_data(
        as_of=body.as_of,
        date_from=effective_date_from,
        entity_code=entity_code,
    )
    raw_counts = {key: len(value) for key, value in raw.items() if isinstance(value, list)}
    _perf_log(
        job_id,
        "raw_data_ready",
        seconds=round(time.perf_counter() - fetch_started_at, 3),
        cache_hit=cms_fetch_cache.get("hit"),
        cache_source=cms_fetch_cache.get("source"),
        rows=raw_counts,
    )
    # 동일 원본(created_at) + 동일 옵션이면 매핑·분류·핵심 분석(실측 7~10초)을 건너뛴다.
    memo_key = analysis_memo_key(
        security_scope=security_scope,
        as_of=body.as_of,
        date_from=effective_date_from,
        raw_created_at=cms_fetch_cache.get("created_at") if isinstance(cms_fetch_cache, dict) else None,
        eur_krw_rate=fixed_eur_krw_rate,
        settings=analysis_settings,
    )
    memo_entry = get_memoized_analysis(memo_key)
    if memo_entry is not None:
        _perf_log(job_id, "analysis_memo_hit", origin_job_id=memo_entry.get("origin_job_id"))
        return {"_memo_entry": memo_entry, "_cms_fetch_cache": cms_fetch_cache}
    mapping_started_at = time.perf_counter()
    uploaded_data = build_uploaded_data_from_cms(raw, entity_code=entity_code)
    mapped_counts = {key: len(value) for key, value in uploaded_data.items()}
    _perf_log(job_id, "mapping_done", seconds=round(time.perf_counter() - mapping_started_at, 3), rows=mapped_counts)
    classification_started_at = time.perf_counter()
    classifications = build_cms_classifications(uploaded_data, body.as_of)
    _perf_log(job_id, "classifications_done", seconds=round(time.perf_counter() - classification_started_at, 3))
    core_started_at = time.perf_counter()
    result = run_core_analysis_from_uploaded_data(
        uploaded_data,
        classifications,
        output_path,
        eur_krw_rate=fixed_eur_krw_rate,
        settings_overrides=analysis_settings,
        defer_excel=True,
        entity_code=entity_code,
    )
    _perf_log(job_id, "core_analysis_done", seconds=round(time.perf_counter() - core_started_at, 3))
    result["_cms_fetch_cache"] = cms_fetch_cache
    result["_memo_key"] = memo_key
    return result


def _queue_deferred_excel_export(
    background_tasks: BackgroundTasks | None,
    export: DeferredExcelExport,
    job_id: str,
    output_filename: str,
    client_id: str,
) -> None:
    if background_tasks is not None:
        background_tasks.add_task(_write_deferred_excel_export, export, job_id, output_filename, client_id)
        return
    # Worker execution has no FastAPI response lifecycle. Materialize the file
    # before the durable job is marked succeeded instead of leaving a task that
    # asyncio.run() would cancel when the Celery task returns.
    _write_deferred_excel_export(export, job_id, output_filename, client_id)


async def _analyze_from_cms_impl(
    *,
    request: Request | None,
    body: CmsAnalyzeRequest,
    background_tasks: BackgroundTasks | None,
    client_id: str | None = None,
    job_id: str | None = None,
    owner_username: str | None = None,
    entity_code: str | None = None,
) -> dict[str, object]:
    ensure_storage_dirs()
    if request is not None:
        owner_username = request.state.current_user.username
        entity_code = str(request.state.entity_code)
    if not owner_username or not entity_code:
        raise HTTPException(status_code=401, detail="분석 작업의 사용자 범위를 확인할 수 없습니다.")
    try:
        context = _cms_analysis_context_from_body(body, entity_code)
    except HTTPException as exc:
        write_audit_event(
            "cms_analysis_failed",
            request,
            reason="invalid_request",
            status_code=exc.status_code,
            detail=exc.detail,
        )
        raise

    fixed_eur_krw_rate = context["fixed_eur_krw_rate"]
    analysis_settings = context["analysis_settings"]
    effective_date_from = str(context["effective_date_from"])
    effective_logistics_date_from = str(context["effective_logistics_date_from"])
    effective_date_to = str(context["effective_date_to"])

    client_id = client_id or (client_id_from_request(request) if request is not None else "background")
    security_scope = f"{owner_username}:{entity_code}"
    job_id = job_id or f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    output_dir = OUTPUT_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    if not await acquire_analysis_slot(client_id):
        write_audit_event(
            "cms_analysis_rejected",
            request,
            job_id=job_id,
            client_id=client_id,
            reason="concurrency_limit",
            active_analysis=active_analysis_snapshot(),
        )
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
        "cms_analysis_started",
        request,
        job_id=job_id,
        client_id=client_id,
        as_of=body.as_of,
        date_from=body.date_from,
        settings=analysis_settings,
        fixed_eur_krw_rate=fixed_eur_krw_rate,
        effective_date_from=effective_date_from,
        effective_logistics_date_from=effective_logistics_date_from,
        effective_date_to=effective_date_to,
        timeout_seconds=CMS_ANALYSIS_TIMEOUT_SECONDS,
        active_analysis=active_analysis_snapshot(),
    )

    analysis_task = create_analysis_task(
        run_in_threadpool(
            _fetch_and_analyze_from_cms,
            body=body,
            job_id=job_id,
            output_path=output_path,
            fixed_eur_krw_rate=fixed_eur_krw_rate,
            analysis_settings=analysis_settings,
            effective_date_from=effective_date_from,
            security_scope=security_scope,
            entity_code=entity_code,
        )
    )
    deferred_release = False
    try:
        completed, result = await wait_without_cancelling(analysis_task, CMS_ANALYSIS_TIMEOUT_SECONDS)
        if not completed:
            defer_slot_release(analysis_task, client_id, lambda: remove_path(output_dir))
            deferred_release = True
            raise asyncio.TimeoutError
        assert result is not None
    except asyncio.TimeoutError as exc:
        duration_seconds = time.perf_counter() - analysis_started_at
        write_audit_event(
            "cms_analysis_failed",
            request,
            job_id=job_id,
            client_id=client_id,
            as_of=body.as_of,
            duration_seconds=round(duration_seconds, 3),
            error_type="timeout",
            error=f"Analysis exceeded {CMS_ANALYSIS_TIMEOUT_SECONDS} seconds.",
        )
        raise HTTPException(
            status_code=504,
            detail="서버 응답이 지연되었습니다. 잠시 후 다시 분석을 눌러주세요.",
        ) from exc
    except ValueError as exc:
        duration_seconds = time.perf_counter() - analysis_started_at
        write_audit_event(
            "cms_analysis_failed",
            request,
            job_id=job_id,
            client_id=client_id,
            as_of=body.as_of,
            duration_seconds=round(duration_seconds, 3),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        remove_path(output_dir)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CmsAuthenticationError as exc:
        duration_seconds = time.perf_counter() - analysis_started_at
        write_audit_event(
            "cms_analysis_failed",
            request,
            job_id=job_id,
            client_id=client_id,
            as_of=body.as_of,
            duration_seconds=round(duration_seconds, 3),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        remove_path(output_dir)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        traceback.print_exc()
        duration_seconds = time.perf_counter() - analysis_started_at
        write_audit_event(
            "cms_analysis_failed",
            request,
            job_id=job_id,
            client_id=client_id,
            as_of=body.as_of,
            duration_seconds=round(duration_seconds, 3),
            error_type=type(exc).__name__,
            error=str(exc),
        )
        remove_path(output_dir)
        raise HTTPException(status_code=502, detail=f"CMS 데이터 분석 중 오류가 발생했습니다: {exc}") from exc
    except asyncio.CancelledError:
        defer_slot_release(analysis_task, client_id, lambda: remove_path(output_dir))
        deferred_release = True
        raise
    finally:
        if not deferred_release:
            await release_analysis_slot(client_id)

    current_job = get_cms_analysis_job(job_id)
    if current_job is not None and current_job.get("status") == "cancelled":
        remove_path(output_dir)
        raise HTTPException(status_code=499, detail="사용자가 분석을 중단했습니다.")

    cms_fetch_cache = result.pop("_cms_fetch_cache", None)
    memo_entry = result.pop("_memo_entry", None)
    analysis_memo_meta: dict[str, object] | None = None
    if memo_entry is not None:
        # 메모 히트: 결과·Excel 모두 최초 계산 잡의 것을 재사용한다. result는 읽기 전용으로 취급.
        result = memo_entry["result"]
        download_url = memo_entry["download_url"]
        output_filename = memo_entry["output_filename"]
        analysis_memo_meta = {"hit": True, "origin_job_id": memo_entry.get("origin_job_id")}
        remove_path(output_dir)
    else:
        excel_export = result.pop("_deferred_excel_export", None)
        memo_key = result.pop("_memo_key", None)
        download_token = create_download_token(
            output_dir,
            job_id,
            owner_username=owner_username,
            entity_code=entity_code,
        )
        download_url = f"/api/download/{job_id}?token={download_token}"
        output_filename = output_path.name
        if isinstance(excel_export, DeferredExcelExport):
            _queue_deferred_excel_export(background_tasks, excel_export, job_id, output_path.name, client_id)
            _perf_log(job_id, "excel_queued", output_filename=output_path.name)
        else:
            write_audit_event(
                "cms_excel_failed",
                request,
                job_id=job_id,
                output_filename=output_path.name,
                error_type="MissingDeferredExcelExport",
                error="Deferred Excel export was not returned by analysis.",
            )
        store_memoized_analysis(
            memo_key,
            result=result,
            download_url=download_url,
            output_filename=output_filename,
            origin_job_id=job_id,
        )
    save_latest_order_review_result(client_id, job_id, result, "cms_api")
    duration_seconds = time.perf_counter() - analysis_started_at
    write_audit_event(
        "cms_analysis_succeeded",
        request,
        job_id=job_id,
        client_id=client_id,
        as_of=body.as_of,
        files=result["uploaded_files"],
        file_mapping=result["file_mapping"],
        settings=result["settings"],
        summary=result["summary"],
        duration_seconds=round(duration_seconds, 3),
        output_filename=output_filename,
        output_retention_hours=STORAGE_MAX_AGE_HOURS,
        cms_fetch_cache=cms_fetch_cache,
        analysis_memo=analysis_memo_meta,
        excel_generation="memoized" if analysis_memo_meta else "background",
    )

    return {
        "job_id": job_id,
        "status": "success",
        "data_source": "cms_api",
        "as_of": body.as_of,
        "date_from": effective_date_from,
        "logistics_date_from": effective_logistics_date_from,
        "date_to": effective_date_to,
        "summary": result["summary"],
        "tables": result["tables"],
        "download_url": download_url,
        "settings": result["settings"],
        "file_mapping": result["file_mapping"],
        "uploaded_files": result["uploaded_files"],
        "season_analysis": result.get("season_analysis"),
        "ingredient_analysis": result.get("ingredient_analysis"),
        # 프론트/운영자가 "캐시된 CMS 데이터로 분석했는지"를 확인할 수 있는 메타데이터.
        # hit(bool), source(memory|disk|cms_api), created_at, age_seconds, ttl_seconds
        "cms_fetch_cache": cms_fetch_cache,
        # 계산 결과 메모이제이션 여부(hit 시 origin_job_id의 결과·Excel 재사용).
        "analysis_memo": analysis_memo_meta,
        "entity_code": entity_code,
    }


async def _run_cms_analysis_job(
    job_id: str,
    body: CmsAnalyzeRequest,
    client_id: str,
    owner_username: str,
    entity_code: str,
) -> None:
    current_job = get_cms_analysis_job(job_id)
    if current_job is None or current_job.get("status") == "cancelled":
        return
    update_cms_analysis_job(job_id, status="running")
    current_job = get_cms_analysis_job(job_id)
    if current_job is None or current_job.get("status") == "cancelled":
        return
    started_at = time.perf_counter()
    write_audit_event("cms_analysis_job_started", None, job_id=job_id, client_id=client_id, request_body=_cms_request_payload(body))
    try:
        result = await _analyze_from_cms_impl(
            request=None,
            body=body,
            background_tasks=None,
            client_id=client_id,
            job_id=job_id,
            owner_username=owner_username,
            entity_code=entity_code,
        )
    except HTTPException as exc:
        current_job = get_cms_analysis_job(job_id)
        if current_job is not None and current_job.get("status") == "cancelled":
            write_audit_event(
                "cms_analysis_job_cancelled",
                None,
                job_id=job_id,
                client_id=client_id,
                duration_seconds=round(time.perf_counter() - started_at, 3),
            )
            return
        update_cms_analysis_job(job_id, status="failed", status_code=exc.status_code, error=str(exc.detail))
        write_audit_event(
            "cms_analysis_job_failed",
            None,
            job_id=job_id,
            client_id=client_id,
            status_code=exc.status_code,
            detail=exc.detail,
            duration_seconds=round(time.perf_counter() - started_at, 3),
        )
    except Exception as exc:
        traceback.print_exc()
        message = f"CMS 데이터 분석 중 오류가 발생했습니다: {exc}"
        update_cms_analysis_job(job_id, status="failed", status_code=500, error=message)
        write_audit_event(
            "cms_analysis_job_failed",
            None,
            job_id=job_id,
            client_id=client_id,
            error_type=type(exc).__name__,
            error=str(exc),
            duration_seconds=round(time.perf_counter() - started_at, 3),
        )
    except asyncio.CancelledError:
        write_audit_event(
            "cms_analysis_job_cancelled",
            None,
            job_id=job_id,
            client_id=client_id,
            duration_seconds=round(time.perf_counter() - started_at, 3),
        )
        raise
    else:
        current_job = get_cms_analysis_job(job_id)
        if current_job is None or current_job.get("status") == "cancelled":
            return
        update_cms_analysis_job(job_id, status="succeeded", result=result)
        write_audit_event(
            "cms_analysis_job_succeeded",
            None,
            job_id=job_id,
            client_id=client_id,
            duration_seconds=round(time.perf_counter() - started_at, 3),
            cms_fetch_cache=result.get("cms_fetch_cache"),
            analysis_memo=result.get("analysis_memo"),
        )


async def queue_cms_analysis(request: Request, body: CmsAnalyzeRequest) -> dict[str, object]:
    """Validate and enqueue a CMS analysis job."""
    entity_code = str(request.state.entity_code)
    try:
        _cms_analysis_context_from_body(body, entity_code)
    except HTTPException as exc:
        write_audit_event(
            "cms_analysis_job_failed",
            request,
            reason="invalid_request",
            status_code=exc.status_code,
            detail=exc.detail,
        )
        raise

    client_id = client_id_from_request(request)
    owner_username = request.state.current_user.username
    request_body = _cms_request_payload(body)
    job_id = create_cms_analysis_job(client_id, request_body)
    write_audit_event(
        "cms_analysis_job_queued",
        request,
        job_id=job_id,
        client_id=client_id,
        request_body=request_body,
    )
    if task_queue.enabled():
        try:
            task_queue.enqueue_cms(job_id, request_body, client_id, owner_username, entity_code)
        except TaskQueueUnavailable as exc:
            update_cms_analysis_job(job_id, status="failed", status_code=503, error="Analysis worker queue is unavailable.")
            raise HTTPException(status_code=503, detail="Analysis worker queue is unavailable.") from exc
    else:
        # Local development remains runnable without a worker service.
        task = asyncio.create_task(
            _run_cms_analysis_job(job_id, body, client_id, owner_username, entity_code)
        )
        _cms_analysis_tasks[job_id] = task
        task.add_done_callback(lambda completed, current_job_id=job_id: _cms_analysis_tasks.pop(current_job_id, None))
    return {"job_id": job_id, "status": "queued"}


def cms_analysis_job_result(job_id: str, client_id: str | None = None) -> dict[str, object]:
    """Return one job snapshot or a stable not-found API error."""
    job = get_cms_analysis_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail="분석 작업을 찾을 수 없습니다. 다시 분석을 시작해 주세요.",
        )
    if client_id is not None and job.get("client_id") != client_id:
        raise HTTPException(status_code=403, detail="다른 계정의 분석 작업에는 접근할 수 없습니다.")
    return job


async def run_cms_analysis(
    *,
    request: Request,
    body: CmsAnalyzeRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, object]:
    """Run a synchronous CMS analysis request through the shared workflow."""
    return await _analyze_from_cms_impl(
        request=request,
        body=body,
        background_tasks=background_tasks,
    )
