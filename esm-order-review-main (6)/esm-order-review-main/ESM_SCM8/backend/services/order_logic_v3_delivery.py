"""Bounded, ownership-checked V3 result delivery. No calculation changes."""

from copy import deepcopy

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from backend.auth.models import UserAccount
from backend.services.order_logic_v3_jobs import get_order_logic_v3_job, get_order_logic_v3_job_metadata
from backend.services.order_logic_v3_result_store import (
    PAGE_SIZE,
    OrderLogicV3ResultUnavailable,
    is_paged_result,
    result_page,
)



def _owned_metadata(job_id: str, client_id: str, entity_code: str) -> dict:
    job = get_order_logic_v3_job_metadata(job_id)
    if job is None:
        raise HTTPException(404, "분석 작업이 만료되었거나 서버가 재시작되었습니다. 새로 분석해 주세요.")
    if job.get("client_id") != client_id or (job.get("analysis_options") or {}).get("entity_code") != entity_code:
        raise HTTPException(403, "다른 사용자 또는 법인의 분석 결과에는 접근할 수 없습니다.")
    return job


def _response(payload: dict, user: UserAccount) -> JSONResponse:
    # Called entirely in the route's thread pool, including JSON encoding.
    # The order-analysis workspace is the approved exception to the global
    # insight/report amount restriction, matching V2. Authentication, entity
    # authorization and job ownership are enforced before this delivery layer.
    _ = user
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


def status_response(job_id: str, client_id: str, entity_code: str, user: UserAccount) -> JSONResponse:
    job = _owned_metadata(job_id, client_id, entity_code)
    return _response({
        "job_id": job_id, "status": job["status"],
        "status_code": job.get("status_code"), "error": job.get("error"),
        "result_delivery": "paged-v1" if job["status"] == "succeeded" else None,
    }, user)


def result_page_response(
    job_id: str, client_id: str, entity_code: str, user: UserAccount,
    offset: int = 0, limit: int = PAGE_SIZE,
) -> JSONResponse:
    metadata = _owned_metadata(job_id, client_id, entity_code)
    if metadata["status"] != "succeeded":
        raise HTTPException(409, "분석 결과가 아직 준비되지 않았습니다.")
    if offset < 0 or not 1 <= limit <= PAGE_SIZE:
        raise HTTPException(422, "결과 조회 범위를 확인해 주세요.")
    job = get_order_logic_v3_job(job_id)
    if job is None:
        raise HTTPException(404, "분석 결과가 만료되었습니다. 새로 분석해 주세요.")
    result = job.get("result")
    if not isinstance(result, dict):
        raise HTTPException(409, "분석 결과의 법인을 확인할 수 없습니다.")
    if is_paged_result(result):
        try:
            payload = result_page(job_id, result, offset=offset, limit=limit)
        except ValueError as exc:
            raise HTTPException(422, "결과 조회 범위를 벗어났습니다.") from exc
        except OrderLogicV3ResultUnavailable as exc:
            raise HTTPException(
                503, "분석 결과 저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."
            ) from exc
        if payload.get("entity_code") != entity_code:
            raise HTTPException(409, "분석 결과의 법인을 확인할 수 없습니다.")
        return _response(payload, user)
    if result.get("entity_code") != entity_code:
        raise HTTPException(409, "분석 결과의 법인을 확인할 수 없습니다.")
    scenarios = result.get("scenarios") or {}
    collections = {"rows": result.get("rows") or [], **{
        key: (scenarios.get(key) or {}).get("rows") or [] for key in ("CASH", "SHORTAGE")
    }}
    counts = {key: len(rows) for key, rows in collections.items()}
    # The current calculator aliases the primary rows to SHORTAGE. Advertise
    # this only when object identity proves it; never infer equal quantities.
    row_alias = next((key for key in ("SHORTAGE", "CASH") if collections["rows"] is collections[key]), None)
    total = max(counts.values())
    if offset > total:
        raise HTTPException(422, "결과 조회 범위를 벗어났습니다.")
    end = min(offset + limit, total)
    payload = {
        "job_id": job_id, "entity_code": entity_code,
        "snapshot_id": result.get("source_snapshot_id"),
        "offset": offset, "next_offset": end if end < total else None,
        "total": total, "counts": counts,
        "row_alias": row_alias,
        "rows": [] if row_alias else collections["rows"][offset:end],
        "scenarios": {key: {"rows": collections[key][offset:end]} for key in ("CASH", "SHORTAGE")},
    }
    if offset == 0:
        # Preserve every result field, including scenario metadata. Only row
        # arrays are transferred in pages; they are never filtered/deduplicated.
        payload["result"] = {
            **{key: value for key, value in result.items() if key not in {"rows", "scenarios"}},
            "rows": [], "scenarios": {
                key: {**{name: value for name, value in scenario.items() if name != "rows"}, "rows": []}
                for key, scenario in scenarios.items()
            },
        }
    return _response(deepcopy(payload), user)
