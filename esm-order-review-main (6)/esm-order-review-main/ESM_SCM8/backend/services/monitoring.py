"""Optional external error and performance monitoring.

Sentry is initialized only when a DSN is configured.  This keeps local
development dependency-free while production fails fast on a missing DSN via
``backend.config.validate_config``.  The SDK sends asynchronously, so an
outage at the monitoring provider never becomes a request dependency.
"""

from __future__ import annotations

from typing import Any

from backend.config import APP_ENV, SENTRY_DSN, SENTRY_RELEASE, SENTRY_TRACES_SAMPLE_RATE
from backend.services.observability import log_event

_configured = False
_SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-client-id",
    "x-forwarded-for",
}


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Remove credentials and request content before an event leaves our network."""
    del hint  # Required callback parameter; intentionally not inspected.
    sanitized = dict(event)
    request = sanitized.get("request")
    if isinstance(request, dict):
        safe_request = dict(request)
        headers = safe_request.get("headers")
        if isinstance(headers, dict):
            safe_request["headers"] = {
                key: "[Filtered]" if str(key).lower() in _SENSITIVE_HEADERS else value
                for key, value in headers.items()
            }
        # Query parameters and bodies can contain access tokens or business data.
        safe_request.pop("cookies", None)
        safe_request.pop("data", None)
        safe_request.pop("query_string", None)
        sanitized["request"] = safe_request
    # This service uses cookie sessions, so no account identity is needed for triage.
    sanitized.pop("user", None)
    return sanitized


def configure_monitoring() -> None:
    """Initialize Sentry once, with PII disabled and an explicit scrubber."""
    global _configured
    if _configured or not SENTRY_DSN:
        return
    try:
        import sentry_sdk
    except ImportError as exc:  # pragma: no cover - dependency is installed in deployments
        raise RuntimeError("sentry-sdk must be installed when SENTRY_DSN is configured.") from exc

    init_options: dict[str, Any] = {
        "dsn": SENTRY_DSN,
        "environment": APP_ENV,
        "traces_sample_rate": SENTRY_TRACES_SAMPLE_RATE,
        "send_default_pii": False,
        "before_send": _before_send,
    }
    if SENTRY_RELEASE:
        init_options["release"] = SENTRY_RELEASE
    sentry_sdk.init(**init_options)
    _configured = True
    log_event(
        20,
        "external_monitoring_configured",
        provider="sentry",
        environment=APP_ENV,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        release=SENTRY_RELEASE or None,
    )


def monitoring_status() -> dict[str, str]:
    return {
        "provider": "sentry",
        "status": "configured" if _configured else "disabled",
        "environment": APP_ENV,
    }


def capture_client_performance(name: str, duration_ms: float, screen: str | None = None) -> None:
    """Send privacy-safe browser timing to the configured external monitor."""
    log_event(20, "client_performance_measure", name=name, duration_ms=duration_ms, screen=screen)
    if not _configured:
        return
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            scope.set_tag("performance.name", name)
            if screen:
                scope.set_tag("performance.screen", screen)
            scope.set_extra("duration_ms", duration_ms)
            sentry_sdk.capture_message("client_performance_measure", level="info")
    except Exception:  # pragma: no cover - monitoring must never affect requests
        return
