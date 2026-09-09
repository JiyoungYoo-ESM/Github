"""Durable, page-addressable V3 result storage for multi-worker delivery."""

from __future__ import annotations

import gzip
import json
import os
import shutil
from typing import Mapping

from backend.config import OUTPUT_DIR
from backend.services import object_storage
from backend.services.object_storage import ObjectStorageUnavailable


PAGE_SIZE = 250  # Transport/storage bound; never used by the calculation.
_MARKER = "_order_logic_v3_paged_result"
_VERSION = 1
LOCAL_RESULT_ROOT = OUTPUT_DIR / "order-v3"


class OrderLogicV3ResultUnavailable(RuntimeError):
    pass


def is_paged_result(value: object) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get(_MARKER), dict)
        and value[_MARKER].get("version") == _VERSION
    )


def _object_name(job_id: str, page_start: int) -> str:
    return f"outputs/order-v3/{job_id}/pages/{page_start:09d}.json.gz"


def _local_page_path(job_id: str, page_start: int):
    if not job_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in job_id):
        raise ValueError("Unsafe V3 job id.")
    return LOCAL_RESULT_ROOT / job_id / "pages" / f"{page_start:09d}.json.gz"


def _put_page(job_id: str, page_start: int, value: bytes, storage: str) -> None:
    if storage == "object":
        object_storage.put_bytes(
            value, _object_name(job_id, page_start), content_type="application/gzip",
        )
        return
    path = _local_page_path(job_id, page_start)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _get_page(job_id: str, page_start: int, storage: str) -> bytes | None:
    if storage == "object":
        return object_storage.get_bytes(_object_name(job_id, page_start))
    path = _local_page_path(job_id, page_start)
    return path.read_bytes() if path.is_file() else None


def delete_local_result(job_id: str) -> None:
    """Delete only the validated local page directory for one expired V3 job."""
    path = _local_page_path(job_id, 0).parents[1]
    if path.parent == LOCAL_RESULT_ROOT and path.is_dir():
        shutil.rmtree(path)


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), default=str,
    ).encode("utf-8")


def store_result(job_id: str, result: dict[str, object]) -> dict[str, object]:
    """Store large row arrays as compressed objects and return a small manifest.

    Production uses object storage. Development uses the same page contract on
    local disk so a 47k-SKU HQ result is not retained as a multi-GB Python
    object after calculation finishes.
    """
    storage = "object" if object_storage.enabled() else "local"

    scenarios = result.get("scenarios") or {}
    if not isinstance(scenarios, dict):
        raise ObjectStorageUnavailable("V3 scenarios are not page-addressable.")
    scenario_rows = {
        key: ((scenarios.get(key) or {}).get("rows") or [])
        for key in ("CASH", "SHORTAGE")
    }
    primary_rows = result.get("rows") or []
    if not isinstance(primary_rows, list) or any(
        not isinstance(rows, list) for rows in scenario_rows.values()
    ):
        raise ObjectStorageUnavailable("V3 result rows are not page-addressable.")

    collections = {"rows": primary_rows, **scenario_rows}
    counts = {key: len(rows) for key, rows in collections.items()}
    row_alias = next(
        (key for key in ("SHORTAGE", "CASH") if primary_rows is collections[key]),
        None,
    )
    total = max(counts.values(), default=0)
    for page_start in range(0, total, PAGE_SIZE):
        page_end = min(page_start + PAGE_SIZE, total)
        page = {
            "start": page_start,
            "end": page_end,
            "rows": [] if row_alias else primary_rows[page_start:page_end],
            "scenarios": {
                key: {"rows": rows[page_start:page_end]}
                for key, rows in scenario_rows.items()
            },
        }
        _put_page(
            job_id, page_start,
            gzip.compress(_json_bytes(page), compresslevel=6), storage,
        )

    base_result = {
        **{key: value for key, value in result.items() if key not in {"rows", "scenarios"}},
        "rows": [],
        "scenarios": {
            key: {
                **{
                    name: value
                    for name, value in scenario.items()
                    if name != "rows"
                },
                "rows": [],
            }
            for key, scenario in scenarios.items()
            if isinstance(scenario, dict)
        },
    }
    return {
        _MARKER: {
            "version": _VERSION,
            "storage": storage,
            "page_size": PAGE_SIZE,
            "total": total,
            "counts": counts,
            "row_alias": row_alias,
            "entity_code": result.get("entity_code"),
            "snapshot_id": result.get("source_snapshot_id"),
            "result": base_result,
        }
    }


def _manifest(stored_result: Mapping[str, object]) -> dict[str, object]:
    manifest = stored_result.get(_MARKER)
    if not isinstance(manifest, dict) or manifest.get("version") != _VERSION:
        raise OrderLogicV3ResultUnavailable("V3 result manifest is invalid.")
    return manifest


def _load_object_page(job_id: str, page_start: int, storage: str) -> dict[str, object]:
    try:
        raw = _get_page(job_id, page_start, storage)
        if raw is None:
            raise OrderLogicV3ResultUnavailable("V3 result page has expired.")
        page = json.loads(gzip.decompress(raw).decode("utf-8"))
    except OrderLogicV3ResultUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise OrderLogicV3ResultUnavailable("V3 result page is unavailable.") from exc
    if not isinstance(page, dict) or page.get("start") != page_start:
        raise OrderLogicV3ResultUnavailable("V3 result page is invalid.")
    return page


def result_page(
    job_id: str,
    stored_result: Mapping[str, object],
    *,
    offset: int,
    limit: int,
) -> dict[str, object]:
    manifest = _manifest(stored_result)
    total = int(manifest.get("total") or 0)
    page_size = int(manifest.get("page_size") or 0)
    counts = manifest.get("counts")
    if page_size <= 0 or not isinstance(counts, dict):
        raise OrderLogicV3ResultUnavailable("V3 result manifest bounds are invalid.")
    if offset > total:
        raise ValueError("offset")
    end = min(offset + limit, total)
    row_alias = manifest.get("row_alias")
    storage = str(manifest.get("storage") or ("object" if object_storage.enabled() else "local"))
    if storage not in {"object", "local"}:
        raise OrderLogicV3ResultUnavailable("V3 result storage is invalid.")
    assembled: dict[str, list[object]] = {"rows": [], "CASH": [], "SHORTAGE": []}

    if end > offset:
        first_page = (offset // page_size) * page_size
        for page_start in range(first_page, end, page_size):
            page = _load_object_page(job_id, page_start, storage)
            page_end = int(page.get("end") or page_start)
            take_start = max(offset, page_start)
            take_end = min(end, page_end)
            local_start = take_start - page_start
            local_end = take_end - page_start
            page_scenarios = page.get("scenarios") or {}
            if not isinstance(page_scenarios, dict):
                raise OrderLogicV3ResultUnavailable("V3 result page scenarios are invalid.")
            arrays = {
                "rows": page.get("rows") or [],
                "CASH": ((page_scenarios.get("CASH") or {}).get("rows") or []),
                "SHORTAGE": ((page_scenarios.get("SHORTAGE") or {}).get("rows") or []),
            }
            for key, values in arrays.items():
                if not isinstance(values, list):
                    raise OrderLogicV3ResultUnavailable("V3 result page rows are invalid.")
                available_end = min(local_end, max(0, int(counts.get(key) or 0) - page_start))
                if available_end > local_start:
                    assembled[key].extend(values[local_start:available_end])

    payload: dict[str, object] = {
        "job_id": job_id,
        "entity_code": manifest.get("entity_code"),
        "snapshot_id": manifest.get("snapshot_id"),
        "offset": offset,
        "next_offset": end if end < total else None,
        "total": total,
        "counts": counts,
        "row_alias": row_alias,
        "rows": [] if row_alias else assembled["rows"],
        "scenarios": {
            "CASH": {"rows": assembled["CASH"]},
            "SHORTAGE": {"rows": assembled["SHORTAGE"]},
        },
    }
    if offset == 0:
        payload["result"] = manifest.get("result")
    return payload


__all__ = [
    "PAGE_SIZE",
    "OrderLogicV3ResultUnavailable",
    "delete_local_result",
    "is_paged_result",
    "result_page",
    "store_result",
]
