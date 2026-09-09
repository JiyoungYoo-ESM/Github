"""Filesystem storage: job directories, retention cleanup, download tokens
and per-job output resolution."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from backend.config import (
    AUDIT_DIR,
    AUDIT_RETENTION_DAYS,
    CMS_FETCH_CACHE_DIR,
    DOWNLOAD_META_FILENAME,
    JOB_ID_PATTERN,
    LATEST_ORDER_LOGIC_V2_DIR,
    LATEST_ORDER_REVIEW_DIR,
    LATEST_SEASON_TREND_DIR,
    ORDER_LOGIC_V3_SEASON_FACTOR_DIR,
    OUTPUT_DIR,
    SUPPORT_ATTACHMENT_DIR,
    STORAGE_MAX_AGE_HOURS,
    UPLOAD_DIR,
)
from backend.services import object_storage
from backend.services.object_storage import ObjectStorageUnavailable


def _job_object_name(job_id: str, filename: str) -> str:
    return f"outputs/{job_id}/{filename}"


def _path_latest_mtime(path: Path) -> float:
    if path.is_file():
        return path.stat().st_mtime
    latest = path.stat().st_mtime
    for child in path.rglob("*"):
        try:
            latest = max(latest, child.stat().st_mtime)
        except FileNotFoundError:
            continue
    return latest


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def _cleanup_old_paths(directory: Path, max_age_hours: int = STORAGE_MAX_AGE_HOURS) -> int:
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_hours * 3600
    removed = 0
    for path in directory.glob("*"):
        try:
            if _path_latest_mtime(path) < cutoff:
                remove_path(path)
                removed += 1
        except FileNotFoundError:
            continue
    return removed


def _cleanup_old_temp_files(directory: Path, max_age_hours: int = STORAGE_MAX_AGE_HOURS) -> int:
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_hours * 3600
    removed = 0
    for path in directory.rglob("*.tmp"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        except FileNotFoundError:
            continue
    return removed


def ensure_storage_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    CMS_FETCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_ORDER_LOGIC_V2_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_ORDER_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_SEASON_TREND_DIR.mkdir(parents=True, exist_ok=True)
    ORDER_LOGIC_V3_SEASON_FACTOR_DIR.mkdir(parents=True, exist_ok=True)
    SUPPORT_ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_old_paths(UPLOAD_DIR)
    _cleanup_old_paths(OUTPUT_DIR)
    _cleanup_old_paths(AUDIT_DIR, max_age_hours=AUDIT_RETENTION_DAYS * 24)
    _cleanup_old_temp_files(LATEST_ORDER_REVIEW_DIR)
    _cleanup_old_temp_files(LATEST_SEASON_TREND_DIR)
    _cleanup_old_temp_files(ORDER_LOGIC_V3_SEASON_FACTOR_DIR)


def storage_directory_status(path: Path) -> dict[str, object]:
    exists = path.is_dir()
    writable = exists and path.exists() and path.is_dir() and os.access(path, os.W_OK)
    return {
        "path": str(path),
        "exists": exists,
        "writable": writable,
    }


def output_dir_for_job(job_id: str) -> Path:
    if not JOB_ID_PATTERN.fullmatch(job_id):
        raise HTTPException(status_code=404, detail="결과 파일을 찾을 수 없습니다.")
    output_dir = OUTPUT_DIR / job_id
    if not output_dir.is_dir():
        raise HTTPException(status_code=404, detail="결과 파일을 찾을 수 없습니다.")
    return output_dir


def output_path_for_job(job_id: str, wait_seconds: float = 0) -> Path:
    output_path = output_dir_for_job(job_id) / f"ESM_order_review_{job_id}.xlsx"
    deadline = time.monotonic() + max(wait_seconds, 0)
    while not output_path.is_file() and time.monotonic() < deadline:
        time.sleep(0.25)
    if not output_path.is_file():
        raise HTTPException(status_code=404, detail="결과 파일을 찾을 수 없습니다.")
    return output_path


async def output_path_for_job_async(job_id: str, wait_seconds: float = 0) -> Path:
    """output_path_for_job과 같은 계약이되 대기 중 이벤트 루프를 블로킹하지 않는다.

    async 라우트에서 wait_seconds > 0으로 호출할 때는 반드시 이 변형을 쓸 것 —
    동기 버전의 time.sleep 폴링은 서버 전체 요청을 멈춘다.
    """

    def _check() -> Path | None:
        output_path = output_dir_for_job(job_id) / f"ESM_order_review_{job_id}.xlsx"
        return output_path if output_path.is_file() else None

    deadline = time.monotonic() + max(wait_seconds, 0)
    while True:
        found = await run_in_threadpool(_check)
        if found is not None:
            return found
        if time.monotonic() >= deadline:
            raise HTTPException(status_code=404, detail="결과 파일을 찾을 수 없습니다.")
        await asyncio.sleep(0.25)


def create_download_token(
    output_dir: Path,
    job_id: str,
    *,
    owner_username: str | None = None,
    entity_code: str | None = None,
) -> str:
    token = secrets.token_urlsafe(32)
    metadata = {
        "job_id": job_id,
        "token": token,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "max_age_hours": STORAGE_MAX_AGE_HOURS,
        "owner_username": owner_username,
        "entity_code": entity_code,
    }
    metadata_bytes = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    (output_dir / DOWNLOAD_META_FILENAME).write_bytes(metadata_bytes)
    if object_storage.enabled():
        try:
            object_storage.put_bytes(metadata_bytes, _job_object_name(job_id, DOWNLOAD_META_FILENAME), content_type="application/json")
        except ObjectStorageUnavailable as exc:
            raise HTTPException(status_code=503, detail="Result object storage is unavailable.") from exc
    return token


def publish_job_output(job_id: str, output_path: Path) -> None:
    if not object_storage.enabled():
        return
    if not output_path.is_file():
        raise HTTPException(status_code=503, detail="Result workbook is not ready for durable storage.")
    try:
        object_storage.upload_file(output_path, _job_object_name(job_id, output_path.name), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except ObjectStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail="Result object storage is unavailable.") from exc


def object_download_url(job_id: str) -> str | None:
    if not object_storage.enabled() or not JOB_ID_PATTERN.fullmatch(job_id):
        return None
    filename = f"ESM_order_review_{job_id}.xlsx"
    try:
        if not object_storage.exists(_job_object_name(job_id, filename)):
            return None
        return object_storage.presigned_download_url(_job_object_name(job_id, filename), download_name=filename)
    except ObjectStorageUnavailable as exc:
        raise HTTPException(status_code=503, detail="Result object storage is unavailable.") from exc


def verify_download_token(
    job_id: str,
    token: str,
    *,
    expected_username: str | None = None,
    expected_entity_code: str | None = None,
) -> None:
    metadata_path = OUTPUT_DIR / job_id / DOWNLOAD_META_FILENAME
    if not metadata_path.is_file() and object_storage.enabled():
        try:
            metadata_bytes = object_storage.get_bytes(_job_object_name(job_id, DOWNLOAD_META_FILENAME))
        except ObjectStorageUnavailable as exc:
            raise HTTPException(status_code=503, detail="Result object storage is unavailable.") from exc
        if metadata_bytes:
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_bytes(metadata_bytes)
    if not metadata_path.is_file():
        raise HTTPException(status_code=403, detail="다운로드 접근 토큰이 없습니다. 다시 분석해 주세요.")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=403, detail="다운로드 접근 토큰이 올바르지 않습니다.") from exc
    expected = str(metadata.get("token", ""))
    if not expected or not secrets.compare_digest(expected, token):
        raise HTTPException(status_code=403, detail="다운로드 접근 토큰이 올바르지 않습니다.")
    if expected_username is not None and metadata.get("owner_username") != expected_username:
        raise HTTPException(status_code=403, detail="다른 계정이 생성한 다운로드에는 접근할 수 없습니다.")
    if expected_entity_code is not None and metadata.get("entity_code") != expected_entity_code:
        raise HTTPException(status_code=403, detail="다른 법인의 다운로드에는 접근할 수 없습니다.")


def recover_download_url(
    job_id: str,
    *,
    expected_username: str | None = None,
    expected_entity_code: str | None = None,
) -> str | None:
    """Return the still-retained workbook URL for a completed analysis job."""
    try:
        output_dir = output_dir_for_job(job_id)
        output_path_for_job(job_id)
        metadata_path = output_dir / DOWNLOAD_META_FILENAME
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        token = str(metadata.get("token") or "")
        if str(metadata.get("job_id") or "") != job_id or not token:
            return None
        verify_download_token(
            job_id,
            token,
            expected_username=expected_username,
            expected_entity_code=expected_entity_code,
        )
    except (FileNotFoundError, json.JSONDecodeError, HTTPException):
        return None
    return f"/api/download/{job_id}?token={token}"


def restore_download_url_from_archive(
    job_id: str,
    archive_path: Path,
    *,
    owner_username: str | None = None,
    entity_code: str | None = None,
) -> str | None:
    """Rehydrate an expired job download from the persistent latest-workbook archive."""
    recovered = recover_download_url(
        job_id,
        expected_username=owner_username,
        expected_entity_code=entity_code,
    )
    if recovered:
        return recovered
    archive = Path(archive_path)
    if not archive.is_file() or not JOB_ID_PATTERN.fullmatch(job_id):
        return None
    output_dir = OUTPUT_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"ESM_order_review_{job_id}.xlsx"
    temporary = output_path.with_suffix(".xlsx.tmp")
    shutil.copy2(archive, temporary)
    temporary.replace(output_path)
    token = create_download_token(
        output_dir,
        job_id,
        owner_username=owner_username,
        entity_code=entity_code,
    )
    publish_job_output(job_id, output_path)
    return f"/api/download/{job_id}?token={token}"


def cleanup_job_uploads(upload_dir: Path) -> None:
    if upload_dir.is_dir() and upload_dir.parent == UPLOAD_DIR:
        shutil.rmtree(upload_dir, ignore_errors=True)
