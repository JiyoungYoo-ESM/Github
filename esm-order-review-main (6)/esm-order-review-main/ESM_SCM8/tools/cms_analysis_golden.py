"""Generate a stable golden hash from a cached CMS raw payload.

This is intentionally local-data driven: it reads one
``backend/storage/cms_fetch_cache/*.json`` file, maps the raw CMS payload through
the same analysis path as ``/api/analyze/cms``, and serializes only
``summary``/``tables`` for before/after optimization comparisons.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.order_analysis_workflow import run_core_analysis_from_uploaded_data
from backend.cms_mapping import build_cms_classifications, build_uploaded_data_from_cms
from backend.services.request_validation import cms_date_settings


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stable(item) for item in value]
    if isinstance(value, tuple):
        return [_stable(item) for item in value]
    if isinstance(value, float):
        return round(value, 12)
    return value


def _load_raw(cache_path: Path) -> dict[str, object]:
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    raw = payload.get("raw")
    if not isinstance(raw, dict):
        raise ValueError(f"{cache_path} does not contain a raw CMS payload")
    return raw


def generate_snapshot(cache_path: Path, as_of: str, eur_krw_rate: float) -> dict[str, object]:
    raw = _load_raw(cache_path)
    uploaded_data = build_uploaded_data_from_cms(raw)
    classifications = build_cms_classifications(uploaded_data, as_of)
    with TemporaryDirectory() as temp_dir:
        result = run_core_analysis_from_uploaded_data(
            uploaded_data,
            classifications,
            Path(temp_dir) / "golden.xlsx",
            eur_krw_rate=eur_krw_rate,
            settings_overrides=cms_date_settings(as_of),
            defer_excel=True,
        )
    return _stable(
        {
            "summary": result["summary"],
            "tables": result["tables"],
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--eur-krw-rate", type=float, default=1768.75)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    snapshot = generate_snapshot(args.cache, args.as_of, args.eur_krw_rate)
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(digest)


if __name__ == "__main__":
    main()
