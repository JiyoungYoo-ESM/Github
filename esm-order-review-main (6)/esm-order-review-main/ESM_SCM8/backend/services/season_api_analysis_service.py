"""Application service for CMS-backed season analysis."""

from __future__ import annotations

import asyncio
import time
import traceback

import pandas as pd
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from backend.config import (
    SEASON_ANALYSIS_TIMEOUT_SECONDS,
    bounded_worker_timeout_seconds,
)
from backend.season_trend_api_client import (
    EU_PRODUCTS_ENDPOINT,
    SeasonTrendSourceApiError,
    fetch_cached_season_trend_source_data,
)
from backend.services.audit import write_audit_event
from backend.services import analysis_cancel
from backend.services.analysis_tasks import create_analysis_task, wait_without_cancelling
from backend.services.season_cache_service import SEASON_ANALYSIS_SCHEMA_VERSION
from backend.services.season_ingredient_analysis import (
    CosmeticScopeValidationError,
    build_season_ingredient_analysis,
)
from backend.services.season_trend_jobs import (
    claim_season_trend_job,
    finish_season_trend_job,
    get_season_trend_job,
    is_latest_season_trend_job,
    update_season_trend_job,
)
from backend.services.season_trend_store import save_latest_season_trend_result
from core.common import korea_today


def exchange_rate_analysis_options(
    start_date: str | None,
    end_date: str | None,
    *,
    entity_code: str = "PL",
) -> dict[str, object]:
    """Return the current display conversion metadata for an analysis response."""
    del start_date, end_date
    code = str(entity_code or "").strip().upper()
    if code == "HQ":
        return {
            # HQ sales/history already returns amount_krw. Keep the legacy
            # display-rate field at zero so clients do not convert KRW twice.
            "average_eur_krw_rate": 0.0,
            "currency_code": "KRW",
            "currency_krw_rate": 1.0,
            "exchange_rate_basis": "본사 판매금액은 CMS 원화 환산금액(amount_krw) 기준입니다.",
            "exchange_rate_source": "native",
            "exchange_rate_date": None,
            "exchange_rate_checked_date": korea_today().isoformat(),
            "sales_amount_currency_code": "KRW",
            "sales_amount_field": "amount_krw",
        }
    return {
        # 분석 금액 자체가 건별 실제 KRW이므로 화면에서 현재환율을 다시 곱하지 않는다.
        "average_eur_krw_rate": 0.0,
        "currency_code": "KRW",
        "currency_krw_rate": 1.0,
        "exchange_rate_basis": "거래일 고시환율을 건별 적용한 실제 원화 매출입니다.",
        "exchange_rate_source": "per_transaction",
        "exchange_rate_date": None,
        "exchange_rate_checked_date": korea_today().isoformat(),
        "sales_amount_currency_code": "KRW",
        "sales_amount_field": "amount_krw_actual",
    }


def _validate_api_sales_krw(rows: object, *, entity_code: str) -> None:
    """Fail closed when the current CMS KRW sales contract is unavailable."""
    if not isinstance(rows, list):
        raise HTTPException(status_code=502, detail="CMS 판매 원천 응답 형식이 올바르지 않습니다.")
    code = str(entity_code or "").strip().upper()
    amount_field = "amount_krw" if code == "HQ" else "amount_krw_actual"
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise HTTPException(status_code=502, detail="CMS 판매 원천 행 형식이 올바르지 않습니다.")
        value = pd.to_numeric(row.get(amount_field), errors="coerce")
        if pd.isna(value):
            raise HTTPException(
                status_code=502,
                detail=f"CMS 판매 원천 {index + 1}행의 실제 원화 금액({amount_field})을 확인할 수 없습니다.",
            )
        if code in {"PL", "USA"} and str(row.get("xrate_source") or "").strip().upper() == "UNRESOLVED":
            raise HTTPException(status_code=502, detail="CMS 판매 원천에 환율 미확인 행이 있어 분석을 중단했습니다.")


def season_source_classifications(
    uploaded_data: dict[str, pd.DataFrame],
    source_meta: dict[str, object],
) -> list[dict[str, object]]:
    sales_meta = source_meta.get("sales_history")
    sales_path = (
        str(sales_meta.get("path"))
        if isinstance(sales_meta, dict) and sales_meta.get("path")
        else "sales/local"
    )
    labels = {
        "sales_history": f"CMS {sales_path}",
        "prod_list": f"CMS {EU_PRODUCTS_ENDPOINT}",
    }
    classifications: list[dict[str, object]] = []
    for key in ("sales_history", "prod_list"):
        frame = pd.DataFrame(uploaded_data.get(key, pd.DataFrame()))
        meta = source_meta.get(key) if isinstance(source_meta.get(key), dict) else {}
        classifications.append(
            {
                "key": key,
                "role": key,
                "original_name": labels[key],
                "saved_name": labels[key],
                "source": "source_api",
                "score": None,
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "detected_columns": [str(column) for column in frame.columns],
                "matched_required_columns": [],
                "missing_required_columns": [],
                "api_total": int(meta.get("api_total") or len(frame)) if isinstance(meta, dict) else len(frame),
                "pages": int(meta.get("pages") or 1) if isinstance(meta, dict) else 1,
            }
        )
    return classifications


def filter_sales_history_by_warehouse(
    sales_history: pd.DataFrame,
    warehouse: str | None,
) -> tuple[pd.DataFrame, dict[str, object] | None]:
    """Scope HQ history to the selected CMS ``whouse_nm`` value."""
    selected = str(warehouse or "").strip().upper()
    if not selected:
        return sales_history, None
    if "whouse_nm" not in sales_history.columns:
        raise HTTPException(
            status_code=400,
            detail="CMS 본사 판매이력에 창고 정보(whouse_nm)가 없어 창고별 분석을 할 수 없습니다.",
        )

    normalized = sales_history["whouse_nm"].fillna("").astype(str).str.strip().str.upper()
    filtered = sales_history.loc[normalized.eq(selected)].copy()
    if filtered.empty:
        raise HTTPException(
            status_code=400,
            detail=f"선택한 창고({selected})의 판매이력이 조회 기간에 없습니다.",
        )
    return filtered, {
        "field": "whouse_nm",
        "selected": selected,
        "rows_before": int(len(sales_history)),
        "rows_after": int(len(filtered)),
    }


def filter_sales_history_rows_by_warehouse(
    sales_history: list[dict[str, object]],
    warehouse: str | None,
) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    """Filter raw HQ rows before pandas duplicates the headquarters dataset."""

    selected = str(warehouse or "").strip().upper()
    if not selected:
        return sales_history, None
    if not any("whouse_nm" in row for row in sales_history):
        raise HTTPException(
            status_code=400,
            detail="CMS 본사 판매이력에 창고 정보(whouse_nm)가 없어 창고별 분석을 할 수 없습니다.",
        )
    filtered = [
        row
        for row in sales_history
        if str(row.get("whouse_nm") or "").strip().upper() == selected
    ]
    if not filtered:
        raise HTTPException(
            status_code=400,
            detail=f"선택한 창고({selected})의 판매이력이 조회 기간에 없습니다.",
        )
    return filtered, {
        "field": "whouse_nm",
        "selected": selected,
        "rows_before": len(sales_history),
        "rows_after": len(filtered),
    }


def run_api_analysis_with_options(
    analysis_options: dict[str, object],
    *,
    save_result: bool = True,
    schema_version: int = SEASON_ANALYSIS_SCHEMA_VERSION,
) -> dict[str, object]:
    """Fetch CMS sources, run season analysis, and optionally publish the result."""
    analysis_start_date = str(analysis_options.get("start_date") or "")
    analysis_end_date = str(analysis_options.get("end_date") or "")
    entity_code = str(analysis_options.get("entity_code") or "PL").strip().upper()
    analysis_options = {
        **analysis_options,
        "strict_cosmetic_scope": True,
        **exchange_rate_analysis_options(
            analysis_start_date,
            analysis_end_date,
            entity_code=entity_code,
        ),
    }
    raw_data, source_meta = fetch_cached_season_trend_source_data(
        date_from=analysis_start_date,
        date_to=analysis_end_date,
        eu_sold_only=True,
        entity_code=entity_code,
    )
    sales_rows = raw_data.get("sales_history", [])
    _validate_api_sales_krw(sales_rows, entity_code=entity_code)
    warehouse_filter = None
    if entity_code == "HQ":
        sales_rows, warehouse_filter = filter_sales_history_rows_by_warehouse(
            sales_rows,
            str(analysis_options.get("warehouse") or "") or None,
        )
        if warehouse_filter is not None:
            source_meta = {**source_meta, "warehouse_filter": warehouse_filter}
    uploaded_data = {
        "sales_history": pd.DataFrame(sales_rows),
        "prod_list": pd.DataFrame(raw_data.get("prod_list", [])),
    }
    if uploaded_data["sales_history"].empty:
        raise HTTPException(status_code=400, detail="선택한 기간의 CMS 판매이력 데이터가 없습니다.")
    if uploaded_data["prod_list"].empty:
        raise HTTPException(
            status_code=502,
            detail="CMS 상품마스터 API 응답이 비어 있어 시즌 캘린더 계산을 중단했습니다.",
        )

    try:
        result = build_season_ingredient_analysis(uploaded_data, analysis_options)
    except CosmeticScopeValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    response_payload: dict[str, object] = {
        "status": "success",
        "analysis_schema_version": schema_version,
        "data_source": "source_api",
        # 결과 재사용 판정의 기준. 기간이 오늘을 포함한 채 계산된 결과는
        # 마지막 하루가 미완성이므로 날짜가 바뀌면 재계산해야 한다.
        "computed_date": korea_today().isoformat(),
        "uploaded_files": season_source_classifications(uploaded_data, source_meta),
        "analysis_options": analysis_options,
        "source_meta": source_meta,
        **result,
    }
    if save_result:
        save_latest_season_trend_result(
            response_payload,
            str(analysis_options.get("security_scope") or "default"),
        )
    return response_payload


def _discard_abandoned_result(finished_task: asyncio.Task[object]) -> None:
    # Marks the outcome retrieved so asyncio doesn't log "exception was never retrieved".
    if finished_task.cancelled():
        return
    finished_task.exception()


async def run_api_analysis_job(job_id: str, analysis_options: dict[str, object]) -> None:
    """Execute and publish one queued CMS season-analysis job."""
    if not claim_season_trend_job(job_id):
        return
    current_job = get_season_trend_job(job_id)
    if current_job is None or current_job.get("status") != "running":
        return
    started_at = time.perf_counter()
    write_audit_event("season_trend_api_analysis_job_started", None, job_id=job_id, analysis_options=analysis_options)
    # Bound to this task's context so the CMS page loops can stop themselves.
    analysis_cancel.register(job_id)
    analysis_task = create_analysis_task(
        run_in_threadpool(run_api_analysis_with_options, analysis_options, save_result=False)
    )
    timeout_seconds = bounded_worker_timeout_seconds(SEASON_ANALYSIS_TIMEOUT_SECONDS)
    try:
        completed, result = await wait_without_cancelling(analysis_task, timeout_seconds)
        if not completed:
            finish_season_trend_job(
                job_id,
                status="failed",
                status_code=504,
                error=f"Analysis exceeded {timeout_seconds:g} seconds.",
            )
            write_audit_event(
                "season_trend_api_analysis_job_failed",
                None,
                job_id=job_id,
                error_type="timeout",
                analysis_options=analysis_options,
                duration_seconds=round(time.perf_counter() - started_at, 3),
            )
            try:
                await analysis_task
            except Exception:
                pass
            return
        assert result is not None
    except asyncio.CancelledError:
        # Do not await analysis_task here: the CMS fetch keeps running in its
        # worker thread regardless, and blocking would hold the caller's
        # concurrency slot until that fetch finishes (defeating "중단"). Let it
        # finish on its own; its result is already discarded (save_result=False)
        # since we return before publishing.
        if not analysis_task.done():
            analysis_task.add_done_callback(_discard_abandoned_result)
        else:
            _discard_abandoned_result(analysis_task)
        write_audit_event(
            "season_trend_api_analysis_job_cancelled",
            None,
            job_id=job_id,
            analysis_options=analysis_options,
            duration_seconds=round(time.perf_counter() - started_at, 3),
        )
        return
    except analysis_cancel.AnalysisCancelled:
        # The fetch stopped itself between pages. Nothing to publish, and the
        # partial pages were discarded inside the fetch, not returned.
        write_audit_event(
            "season_trend_api_analysis_job_cancelled",
            None,
            job_id=job_id,
            analysis_options=analysis_options,
            duration_seconds=round(time.perf_counter() - started_at, 3),
            stopped_fetch=True,
        )
        return
    except HTTPException as exc:
        update_season_trend_job(job_id, status="failed", status_code=exc.status_code, error=str(exc.detail))
        write_audit_event(
            "season_trend_api_analysis_job_failed",
            None,
            job_id=job_id,
            status_code=exc.status_code,
            detail=exc.detail,
            analysis_options=analysis_options,
        )
    except SeasonTrendSourceApiError as exc:
        message = f"CMS 시즌 분석 API 호출에 실패했습니다: {exc}"
        update_season_trend_job(job_id, status="failed", status_code=502, error=message)
        write_audit_event(
            "season_trend_api_analysis_job_failed",
            None,
            job_id=job_id,
            error_type=type(exc).__name__,
            error=str(exc),
            analysis_options=analysis_options,
        )
    except ValueError as exc:
        update_season_trend_job(job_id, status="failed", status_code=400, error=str(exc))
        write_audit_event(
            "season_trend_api_analysis_job_failed",
            None,
            job_id=job_id,
            error_type=type(exc).__name__,
            error=str(exc),
            analysis_options=analysis_options,
        )
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        message = f"시즌/수요 분석 중 오류가 발생했습니다: {exc}"
        update_season_trend_job(job_id, status="failed", status_code=500, error=message)
        write_audit_event(
            "season_trend_api_analysis_job_failed",
            None,
            job_id=job_id,
            error_type=type(exc).__name__,
            error=str(exc),
            analysis_options=analysis_options,
        )
    else:
        # Exceptions raised in a try/else are not handled by the preceding
        # except clauses. Production persists results in PostgreSQL, so a
        # storage failure here must also terminate the polling job.
        try:
            current_job = get_season_trend_job(job_id)
            if current_job is None or current_job.get("status") != "running":
                return
            security_scope = str(analysis_options.get("security_scope") or "default")
            published_as_latest = is_latest_season_trend_job(job_id, security_scope)
            if published_as_latest:
                await run_in_threadpool(
                    save_latest_season_trend_result,
                    result,
                    security_scope,
                )
            if not finish_season_trend_job(job_id, status="succeeded", result=result):
                return
        except Exception as exc:  # noqa: BLE001
            # Database exceptions can include the complete result as SQL
            # parameters. Expose only a safe message and the exception type.
            marked_failed = finish_season_trend_job(
                job_id,
                status="failed",
                status_code=500,
                error="분석 결과를 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.",
            )
            if marked_failed:
                write_audit_event(
                    "season_trend_api_analysis_job_failed",
                    None,
                    job_id=job_id,
                    phase="result_persistence",
                    error_type=type(exc).__name__,
                    duration_seconds=round(time.perf_counter() - started_at, 3),
                )
            return
        write_audit_event(
            "season_trend_api_analysis_job_succeeded",
            None,
            job_id=job_id,
            source_meta=result.get("source_meta"),
            analysis_options=result.get("analysis_options"),
            duration_seconds=round(time.perf_counter() - started_at, 3),
            published_as_latest=published_as_latest,
        )
    finally:
        analysis_cancel.unregister(job_id)


__all__ = [
    "exchange_rate_analysis_options",
    "filter_sales_history_rows_by_warehouse",
    "run_api_analysis_job",
    "run_api_analysis_with_options",
    "season_source_classifications",
]
