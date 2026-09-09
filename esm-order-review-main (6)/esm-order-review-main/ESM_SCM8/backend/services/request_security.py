"""Browser-origin and reverse-proxy trust boundaries."""

from __future__ import annotations

from ipaddress import ip_address

from fastapi import HTTPException, Request

from backend import config


def peer_is_trusted_proxy(request: Request) -> bool:
    """Only accept forwarded headers from explicitly configured proxy CIDRs."""
    if not request.client or not config.TRUSTED_PROXY_CIDRS:
        return False
    try:
        peer = ip_address(request.client.host)
    except ValueError:
        return False
    return any(peer in network for network in config.TRUSTED_PROXY_CIDRS)


def client_ip_from_request(request: Request) -> str:
    if peer_is_trusted_proxy(request):
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            try:
                return str(ip_address(first))
            except ValueError:
                pass
    return request.client.host if request.client else "unknown"


def require_safe_browser_origin(request: Request) -> None:
    """Reject cross-site writes even when a browser somehow sends a cookie."""
    origin = request.headers.get("origin", "").strip()
    fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
    if fetch_site == "cross-site" or (origin and not config.is_allowed_browser_origin(origin)):
        from backend.services.audit import write_audit_event

        write_audit_event("cross_site_request_blocked", request, origin=origin, fetch_site=fetch_site)
        raise HTTPException(status_code=403, detail="Cross-site requests are not allowed.")
