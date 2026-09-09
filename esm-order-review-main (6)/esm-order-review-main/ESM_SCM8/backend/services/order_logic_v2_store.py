"""Keep only the latest BETA order-logic result per account/entity/browser.

The filesystem fallback is intentionally bounded to one JSON file per client.
It is not presented as a durable audit history; PostgreSQL-backed snapshots
take over automatically when ``DATABASE_URL`` is configured.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from backend.config import LATEST_ORDER_LOGIC_V2_DIR
from backend.services import persistent_state


SNAPSHOT_KIND = "order_logic_v2"


def _safe_client_id(client_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", client_id)[:80] or "default"


def _safe_entity_code(entity_code: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", entity_code.strip().upper())[:32] or "PL"


def _snapshot_key(client_id: str, entity_code: str) -> str:
    return f"{SNAPSHOT_KIND}:{_safe_client_id(client_id)}:{_safe_entity_code(entity_code)}"


def _latest_path(client_id: str, entity_code: str) -> Path:
    return (
        LATEST_ORDER_LOGIC_V2_DIR
        / f"{_safe_client_id(client_id)}--{_safe_entity_code(entity_code)}.json"
    )


def save_latest_order_logic_v2_result(
    client_id: str,
    entity_code: str,
    result: dict[str, object],
) -> None:
    if persistent_state.enabled():
        persistent_state.save_snapshot(
            _snapshot_key(client_id, entity_code),
            SNAPSHOT_KIND,
            result,
        )
        return

    LATEST_ORDER_LOGIC_V2_DIR.mkdir(parents=True, exist_ok=True)
    target = _latest_path(client_id, entity_code)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=target.parent,
        suffix=".tmp",
        delete=False,
    ) as temporary:
        json.dump(result, temporary, ensure_ascii=False, default=str)
        temporary_path = Path(temporary.name)
    temporary_path.replace(target)


def load_latest_order_logic_v2_result(
    client_id: str,
    entity_code: str,
) -> dict[str, object] | None:
    if persistent_state.enabled():
        return persistent_state.load_snapshot(_snapshot_key(client_id, entity_code))

    target = _latest_path(client_id, entity_code)
    if not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


__all__ = [
    "load_latest_order_logic_v2_result",
    "save_latest_order_logic_v2_result",
]
