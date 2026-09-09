"""Health/readiness payload: storage writability, disk and process metrics."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone

from backend.config import (
    ANALYSIS_TIMEOUT_SECONDS,
    AUDIT_DIR,
    AUDIT_RETENTION_DAYS,
    BACKEND_ROOT,
    DATABASE_URL,
    JOB_MAX_RETAINED,
    JOB_RETENTION_HOURS,
    MAX_ANALYSES_PER_CLIENT,
    MAX_CONCURRENT_ANALYSES,
    MAX_CONCURRENT_REPORT_EXPORTS,
    MAX_UPLOAD_FILE_BYTES,
    MAX_UPLOAD_FILES,
    MAX_UPLOAD_TOTAL_BYTES,
    OUTPUT_DIR,
    REPORT_EXPORT_TIMEOUT_SECONDS,
    REPORT_MAX_OUTPUT_BYTES,
    REPORT_MAX_REQUEST_BYTES,
    SEASON_ANALYSIS_TIMEOUT_SECONDS,
    SLOW_REQUEST_THRESHOLD_MS,
    STORAGE_MAX_AGE_HOURS,
    STORAGE_CLEANUP_INTERVAL_SECONDS,
    UPLOAD_DIR,
)
from backend.services.concurrency import active_analysis_snapshot
from backend.services.report_resources import report_resource_snapshot
from backend.services.storage import storage_directory_status
from backend.services.observability import request_metrics_snapshot
from backend.services.shared_redis import status as redis_status
from backend.services.monitoring import monitoring_status
from backend.services.object_storage import lifecycle_status as object_storage_lifecycle_status
from backend.services.object_storage import status as object_storage_status


def liveness_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "ESM SCM Backend",
    }


def _database_status() -> str:
    if not DATABASE_URL:
        return "not_configured"
    try:
        from sqlalchemy import text

        from backend.database import get_engine

        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return "unavailable"
    return "ok"


def readiness_payload() -> dict[str, object]:
    disk_usage = shutil.disk_usage(BACKEND_ROOT)
    storage = {
        "uploads": storage_directory_status(UPLOAD_DIR),
        "outputs": storage_directory_status(OUTPUT_DIR),
        "audit": storage_directory_status(AUDIT_DIR),
    }
    storage_ok = all(item["exists"] and item["writable"] for item in storage.values())
    database = _database_status()
    redis = redis_status()
    object_storage = object_storage_status()
    object_storage_ok = object_storage in {"ok", "not_configured"}
    object_storage_lifecycle = object_storage_lifecycle_status()
    lifecycle_ok = object_storage_lifecycle in {"ok", "not_configured"}
    status = "ok" if storage_ok and database == "ok" and redis == "ok" and object_storage_ok and lifecycle_ok and disk_usage.free > 0 else "degraded"
    return {
        **liveness_payload(),
        "status": status,
        "checks": {
            "storage": "ok" if storage_ok else "unavailable",
            "database": database,
            "redis": redis,
            "object_storage": object_storage,
            "object_storage_lifecycle": object_storage_lifecycle,
            "disk": "ok" if disk_usage.free > 0 else "unavailable",
        },
    }


def health_payload() -> dict[str, object]:
    disk_usage = shutil.disk_usage(BACKEND_ROOT)
    system: dict[str, object] = {"psutil_available": False}
    try:
        import psutil  # type: ignore

        memory = psutil.virtual_memory()
        system = {
            "psutil_available": True,
            "cpu_percent": psutil.cpu_percent(interval=0),
            "memory_total_bytes": int(memory.total),
            "memory_available_bytes": int(memory.available),
            "memory_percent": float(memory.percent),
        }
    except Exception:
        system = {"psutil_available": False}
    storage = {
        "uploads": storage_directory_status(UPLOAD_DIR),
        "outputs": storage_directory_status(OUTPUT_DIR),
        "audit": storage_directory_status(AUDIT_DIR),
    }
    storage_ok = all(item["exists"] and item["writable"] for item in storage.values())
    status = "ok" if storage_ok and disk_usage.free > 0 else "degraded"
    return {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "ESM SCM Backend",
        "storage": storage,
        "retention": {
            "output_hours": STORAGE_MAX_AGE_HOURS,
            "audit_days": AUDIT_RETENTION_DAYS,
            "job_hours": JOB_RETENTION_HOURS,
            "max_retained_jobs": JOB_MAX_RETAINED,
            "cleanup_interval_seconds": STORAGE_CLEANUP_INTERVAL_SECONDS,
        },
        "limits": {
            "max_concurrent_analyses": MAX_CONCURRENT_ANALYSES,
            "max_analyses_per_client": MAX_ANALYSES_PER_CLIENT,
            "max_upload_file_bytes": MAX_UPLOAD_FILE_BYTES,
            "max_upload_files": MAX_UPLOAD_FILES,
            "max_upload_total_bytes": MAX_UPLOAD_TOTAL_BYTES,
            "analysis_timeout_seconds": ANALYSIS_TIMEOUT_SECONDS,
            "season_analysis_timeout_seconds": SEASON_ANALYSIS_TIMEOUT_SECONDS,
            "max_concurrent_report_exports": MAX_CONCURRENT_REPORT_EXPORTS,
            "report_export_timeout_seconds": REPORT_EXPORT_TIMEOUT_SECONDS,
            "report_max_request_bytes": REPORT_MAX_REQUEST_BYTES,
            "report_max_output_bytes": REPORT_MAX_OUTPUT_BYTES,
            "slow_request_threshold_ms": SLOW_REQUEST_THRESHOLD_MS,
        },
        "analysis": active_analysis_snapshot(),
        "reports": report_resource_snapshot(),
        "redis": {"status": redis_status()},
        "object_storage": {
            "status": object_storage_status(),
            "lifecycle": object_storage_lifecycle_status(),
        },
        "monitoring": monitoring_status(),
        "requests": request_metrics_snapshot(),
        "disk": {
            "total_bytes": disk_usage.total,
            "used_bytes": disk_usage.used,
            "free_bytes": disk_usage.free,
        },
        "system": system,
    }
