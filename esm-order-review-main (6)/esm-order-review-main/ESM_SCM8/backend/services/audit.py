"""Audit logging and per-request client identification."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from fastapi import Request

from backend.config import AUDIT_DIR
from backend.services.request_security import client_ip_from_request
from backend.services.upload_models import SavedUpload


def request_audit_context(request: Request | None) -> dict[str, str]:
    if request is None:
        return {}
    client_ip = client_ip_from_request(request)
    user = getattr(request.state, "current_user", None)
    entity_code = str(getattr(request.state, "entity_code", "") or "")
    return {
        "request_id": str(getattr(request.state, "request_id", "") or ""),
        "client_ip": client_ip,
        "user_agent": request.headers.get("user-agent", ""),
        "path": request.url.path,
        "method": request.method,
        "username": str(getattr(user, "username", "") or ""),
        "entity_code": entity_code,
    }


def client_id_from_request(request: Request) -> str:
    explicit = request.headers.get("x-client-id", "").strip()
    if explicit:
        browser_id = re.sub(r"[^A-Za-z0-9._-]+", "_", explicit)[:48]
    else:
        context = request_audit_context(request)
        raw = f"{context.get('client_ip', '')}|{context.get('user_agent', '')}"
        browser_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    user = getattr(request.state, "current_user", None)
    username = re.sub(r"[^A-Za-z0-9._-]+", "_", str(getattr(user, "username", "anonymous")))[:24]
    entity = re.sub(r"[^A-Za-z0-9._-]+", "_", str(getattr(request.state, "entity_code", "none")))[:8]
    # Browser-supplied IDs can no longer collide across users/entities.
    return f"{username}__{entity}__{browser_id}"[:80]


def write_audit_event(event: str, request: Request | None = None, **details: object) -> None:
    try:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        record = {
            "timestamp": now.isoformat(),
            "event": event,
            "request": request_audit_context(request),
            "details": details,
        }
        audit_path = AUDIT_DIR / f"audit_{now:%Y%m%d}.jsonl"
        with audit_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # 감사 로그 실패가 사용자 분석 흐름을 막지는 않도록 한다.
        return


def audit_uploads(saved_uploads: list[SavedUpload]) -> list[dict[str, object]]:
    return [
        {
            "original_name": upload.original_name,
            "saved_name": upload.saved_name,
            "size_bytes": upload.size_bytes,
            "role": upload.role,
        }
        for upload in saved_uploads
    ]
