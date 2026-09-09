"""Fail fast if a production process cannot serve traffic safely.

Run inside the deployed backend service after migrations and volume mounting:
``python -m backend.scripts.verify_runtime``.
"""

from __future__ import annotations

import json
import sys

from backend.auth.user_store import get_user_store, validate_user_store
from backend.config import IS_PRODUCTION, validate_config
from backend.services.health import readiness_payload
from backend.services.storage import ensure_storage_dirs


def main() -> int:
    validate_config()
    validate_user_store(get_user_store(), require_all_hashes=IS_PRODUCTION)
    ensure_storage_dirs()
    readiness = readiness_payload()
    print(json.dumps(readiness, ensure_ascii=False, default=str))
    if readiness["status"] != "ok":
        print("Runtime readiness check failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
