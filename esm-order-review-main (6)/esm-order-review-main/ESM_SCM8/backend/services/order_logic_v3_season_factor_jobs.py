"""Entity-scoped refresh jobs shared by scheduled and manual refreshes.

HTTP requests never wait for a 24-month CMS fetch. One worker preserves the
existing serialization; repeated clicks attach to the same unfinished job.
Only progress and aggregate artifact metadata are returned to the browser.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import threading
import traceback
from uuid import uuid4

from backend.services.order_logic_v3_season_factor_service import refresh_order_logic_v3_season_factors
from backend.services.audit import write_audit_event
from backend.services.order_logic_v3_ledger import LedgerSourceError

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="v3-season-refresh")
_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, object]] = {}


def _entity(code: str) -> str:
    if code not in {"HQ", "PL", "USA"}:
        raise ValueError("Unsupported V3 entity")
    return code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def refresh_status(entity_code: str) -> dict[str, object]:
    code = _entity(entity_code)
    with _LOCK:
        job = dict(_JOBS.get(code) or {"entity_code": code, "status": "idle"})
        if job["status"] == "queued":
            job["waiting_for_entity"] = next((key for key, value in _JOBS.items()
                                              if value["status"] == "running"), None)
        return job


def _update(code: str, job_id: str, **fields: object) -> None:
    with _LOCK:
        if _JOBS.get(code, {}).get("job_id") == job_id:
            _JOBS[code].update(fields, updated_at=_now())


def _run(code: str, job_id: str, as_of: str, force_refresh: bool) -> None:
    _update(code, job_id, status="running", stage="starting")
    try:
        artifact = refresh_order_logic_v3_season_factors(
            entity_code=code, as_of=as_of, force_refresh=force_refresh,
            progress=lambda details: _update(code, job_id, **details),
        )
        valid = artifact.get("status") == "active" and bool((artifact.get("validation") or {}).get("passed"))
        _update(code, job_id, status="succeeded" if valid else "failed", stage="complete",
                version=artifact.get("version"), window_end=artifact.get("window_end"),
                error=None if valid else "계절지수 검증을 통과하지 못했습니다. 기존 버전은 유지됩니다.")
        write_audit_event("order_logic_v3_season_factor_refresh_completed", None,
                          entity_code=code, job_id=job_id, version=artifact.get("version"), validated=valid)
    except Exception as exc:
        traceback.print_exc()
        if isinstance(exc, LedgerSourceError):
            month = refresh_status(code).get("month")
            location = f"{month} 판매 데이터 확인 중: " if month else ""
            error = f"계절지수 갱신에 실패했습니다. {location}{exc} 기존 버전은 유지됩니다."
        else:
            error = f"계절지수 갱신에 실패했습니다 ({type(exc).__name__}). 다시 시도해 주세요."
        _update(code, job_id, status="failed", stage="failed",
                error=error)


def queue_refresh(*, entity_code: str, as_of: str, force_refresh: bool = True,
                  trigger: str = "manual") -> dict[str, object]:
    code = _entity(entity_code)
    date.fromisoformat(as_of)
    with _LOCK:
        if _JOBS.get(code, {}).get("status") in {"queued", "running"}:
            return refresh_status(code)
        job_id = f"season3_{uuid4().hex}"
        _JOBS[code] = {"job_id": job_id, "entity_code": code, "as_of": as_of,
                       "status": "queued", "stage": "queued", "trigger": trigger,
                       "created_at": _now(), "updated_at": _now()}
        try:
            _POOL.submit(_run, code, job_id, as_of, force_refresh)
        except Exception:
            _JOBS.pop(code, None)
            raise
        return refresh_status(code)
