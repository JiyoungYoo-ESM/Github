"""Persistence for the most recent season/trend analysis result.

Season trend screens are often opened from both localhost and LAN addresses.
Browser storage is origin-scoped, so keeping the latest successful result on
the backend gives both origins the same read path.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from backend.config import LATEST_SEASON_TREND_DIR
from backend.services import persistent_state


LATEST_SEASON_TREND_FILENAME = "latest.json"


def _safe_scope(scope: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", scope)[:80] or "default"


def latest_season_trend_path(scope: str = "default") -> Path:
    if scope == "default":
        return LATEST_SEASON_TREND_DIR / LATEST_SEASON_TREND_FILENAME
    return LATEST_SEASON_TREND_DIR / f"latest_{_safe_scope(scope)}.json"


def save_latest_season_trend_result(payload: dict[str, object], scope: str = "default") -> None:
    latest_payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    if persistent_state.enabled():
        persistent_state.save_snapshot(
            f"season_trend:{_safe_scope(scope)}", "season_trend", latest_payload
        )
        return
    try:
        LATEST_SEASON_TREND_DIR.mkdir(parents=True, exist_ok=True)
        latest_season_trend_path(scope).write_text(
            json.dumps(latest_payload, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except Exception:
        return


def load_latest_season_trend_result(scope: str = "default") -> dict[str, object] | None:
    if persistent_state.enabled():
        return persistent_state.load_snapshot(f"season_trend:{_safe_scope(scope)}")
    path = latest_season_trend_path(scope)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def clear_latest_season_trend_result(scope: str = "default") -> None:
    if persistent_state.enabled():
        persistent_state.delete_snapshot(f"season_trend:{_safe_scope(scope)}")
        return
    try:
        latest_season_trend_path(scope).unlink(missing_ok=True)
    except Exception:
        return
