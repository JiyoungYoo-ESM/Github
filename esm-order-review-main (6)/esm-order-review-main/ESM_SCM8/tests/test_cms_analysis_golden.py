import hashlib
import json
from pathlib import Path

import pytest

from tools.cms_analysis_golden import generate_snapshot


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CMS_CACHE = PROJECT_ROOT / "backend" / "storage" / "cms_fetch_cache" / (
    "38a7a11f60009e8836aaa6bafd2f72a8f67bf9df20cd3e5383de993e0d9970b1.json"
)
EXPECTED_HASH = "5528774ed8417cc5156467686089fc56808c401233605a9219e737f61db3c882"


def test_cached_cms_analysis_matches_golden_hash():
    if not CMS_CACHE.exists():
        pytest.skip("CMS raw cache fixture is not available in this environment")

    snapshot = generate_snapshot(CMS_CACHE, "2026-07-02", 1768.75)
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    assert hashlib.sha256(encoded.encode("utf-8")).hexdigest() == EXPECTED_HASH
