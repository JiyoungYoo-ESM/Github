from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_production_entrypoint_migrates_and_verifies_before_serving():
    source = (PROJECT_ROOT / "backend" / "scripts" / "start_production.sh").read_text(encoding="utf-8")

    migration_index = source.index("python -m alembic upgrade head")
    verification_index = source.index("python -m backend.scripts.verify_runtime")
    server_index = source.index("exec python -m uvicorn")
    assert migration_index < verification_index < server_index
