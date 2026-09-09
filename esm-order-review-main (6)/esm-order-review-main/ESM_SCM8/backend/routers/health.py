"""Health checks and exchange-rate lookup."""

from __future__ import annotations

import threading
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from core.exchange_rate import fallback_rate_metadata
from core.kpi import get_currency_krw_rate, get_eur_krw_rate
from core.common import korea_today

from backend.services.health import health_payload, liveness_payload, readiness_payload
from backend.services.monitoring import capture_client_performance
from backend.schemas import ExchangeRateResponse, HealthResponse, LivenessResponse, ReadinessResponse

router = APIRouter()
_exchange_rate_cache: dict[str, tuple[object, dict[str, object]]] = {}
_exchange_rate_cache_lock = threading.Lock()


def _exchange_rate_payload(currency: Literal["EUR", "USD"]) -> dict[str, object]:
    today = korea_today()
    with _exchange_rate_cache_lock:
        cached = _exchange_rate_cache.get(currency)
        if cached is not None and cached[0] == today:
            return dict(cached[1])

        if currency == "EUR":
            rate, rate_date, success = get_eur_krw_rate()
        else:
            rate, rate_date, success = get_currency_krw_rate("USD", 0.0)
        if currency == "USD" and not success:
            raise HTTPException(
                status_code=503,
                detail="USD/KRW 환율을 조회하지 못했습니다. 현재 환율을 직접 입력해 주세요.",
            )

        result: dict[str, object] = {
            "eur_krw_rate": float(rate),
            "currency_code": currency,
            "currency_krw_rate": float(rate),
            "rate_source": "api" if success else "default",
            "rate_date": rate_date,
        }
        if not success and currency == "EUR":
            result.update(fallback_rate_metadata())
        _exchange_rate_cache[currency] = (today, dict(result))
        return result


@router.post("/api/health/client-performance", status_code=202)
async def client_performance(request: Request) -> dict[str, str]:
    """Accept only small, anonymous browser timing measurements."""
    try:
        payload = await request.json()
        name = str(payload.get("name") or "")
        duration_ms = float(payload.get("duration_ms"))
        screen = str(payload.get("screen") or "") or None
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid client performance payload.") from None
    if not name.startswith(("workspace.", "report.")) or len(name) > 80 or not 0 <= duration_ms <= 60_000:
        raise HTTPException(status_code=422, detail="Invalid client performance measurement.")
    if screen and len(screen) > 40:
        raise HTTPException(status_code=422, detail="Invalid client performance screen.")
    capture_client_performance(name, round(duration_ms, 2), screen)
    return {"status": "accepted"}


@router.post("/api/health", response_model=HealthResponse)
async def health() -> dict[str, object]:
    return await run_in_threadpool(health_payload)


@router.get("/api/health", response_model=HealthResponse)
async def health_get() -> dict[str, object]:
    return await run_in_threadpool(health_payload)


@router.get("/api/health/live", response_model=LivenessResponse)
async def health_live() -> dict[str, object]:
    return liveness_payload()


@router.get("/api/health/ready", response_model=ReadinessResponse)
async def health_ready() -> JSONResponse:
    payload = await run_in_threadpool(readiness_payload)
    status_code = 200 if payload["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/api/exchange-rate", response_model=ExchangeRateResponse)
async def exchange_rate(
    currency: Annotated[Literal["EUR", "USD"], Query()] = "EUR",
) -> dict[str, object]:
    return await run_in_threadpool(_exchange_rate_payload, currency)
