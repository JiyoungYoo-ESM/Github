from __future__ import annotations

from ipaddress import ip_network

from starlette.requests import Request

import backend.config as config
from backend.services.request_security import client_ip_from_request


def request_with_peer(peer: str, forwarded_for: str = "") -> Request:
    headers = [(b"x-forwarded-for", forwarded_for.encode())] if forwarded_for else []
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 1234),
        }
    )


def test_forwarded_for_is_ignored_from_untrusted_peer(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXY_CIDRS", ())
    assert client_ip_from_request(request_with_peer("203.0.113.10", "198.51.100.5")) == "203.0.113.10"


def test_forwarded_for_is_used_only_from_trusted_proxy(monkeypatch):
    monkeypatch.setattr(config, "TRUSTED_PROXY_CIDRS", (ip_network("10.0.0.0/8"),))
    assert client_ip_from_request(request_with_peer("10.1.2.3", "198.51.100.5, 10.1.2.3")) == "198.51.100.5"
    assert client_ip_from_request(request_with_peer("203.0.113.10", "198.51.100.5")) == "203.0.113.10"
