"""Review or apply the ESM-managed S3 lifecycle rules.

Use ``--apply`` only with deployment credentials that have
``s3:PutLifecycleConfiguration`` (or the equivalent provider permission).
"""

from __future__ import annotations

import argparse
import json
import sys

from backend.services.object_storage import ObjectStorageUnavailable, apply_lifecycle_rules, lifecycle_rules


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the managed lifecycle rules")
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps({"mode": "dry_run", "rules": lifecycle_rules()}, ensure_ascii=False, indent=2))
        return 0
    try:
        print(json.dumps({"mode": "applied", **apply_lifecycle_rules()}, ensure_ascii=False, indent=2))
    except ObjectStorageUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
