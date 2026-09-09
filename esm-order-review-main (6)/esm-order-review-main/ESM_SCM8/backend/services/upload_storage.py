"""Bounded, chunked persistence for user-supplied Excel uploads."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import anyio
from fastapi import HTTPException, UploadFile

from backend.config import (
    MAX_UPLOAD_FILE_BYTES,
    MAX_UPLOAD_FILES,
    MAX_UPLOAD_TOTAL_BYTES,
    UPLOAD_CHUNK_BYTES,
)
from backend.services.request_validation import (
    format_bytes,
    sanitize_filename,
    upload_display_name,
    validate_excel_file,
)


@dataclass(frozen=True)
class StoredUpload:
    original_name: str
    safe_name: str
    saved_name: str
    path: Path
    size_bytes: int


def validate_upload_count(files: Sequence[UploadFile]) -> None:
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"한 요청에 업로드할 수 있는 파일은 최대 {MAX_UPLOAD_FILES}개입니다.",
        )


def validate_excel_signature(path: Path, filename: str) -> None:
    """Reject extensions whose payload cannot be handled by the Excel loaders.

    Legacy ``.xls`` exports from CMS may be OLE workbooks, HTML tables or
    tab-delimited text, all of which the existing loader intentionally accepts.
    Open XML formats must be ZIP containers.
    """

    extension = Path(filename).suffix.lower()
    with path.open("rb") as source:
        sample = source.read(4096)
    stripped = sample.lstrip().lower()
    if extension in {".xlsx", ".xlsm"}:
        valid = sample.startswith(b"PK\x03\x04")
    else:
        valid = (
            sample.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
            or stripped.startswith((b"<html", b"<!doctype html", b"<table"))
            or b"<table" in stripped
            or b"schemas-microsoft-com:office" in stripped
            or b"\t" in sample
        )
    if not valid:
        raise HTTPException(
            status_code=400,
            detail=f"'{upload_display_name(filename)}' 파일의 내용이 Excel 형식과 일치하지 않습니다.",
        )


async def store_upload_files(
    files: Sequence[UploadFile],
    destination_dir: Path,
    saved_name_factory: Callable[[int, str], str],
) -> tuple[list[StoredUpload], int]:
    """Persist uploads without materializing request bodies as one bytes object."""

    validate_upload_count(files)
    destination_dir.mkdir(parents=True, exist_ok=True)
    stored: list[StoredUpload] = []
    total_bytes = 0

    for index, upload in enumerate(files, start=1):
        original_name = upload_display_name(upload.filename)
        safe_name = sanitize_filename(upload.filename)
        validate_excel_file(safe_name)
        saved_name = saved_name_factory(index, safe_name)
        destination = destination_dir / saved_name
        file_size = 0

        try:
            async with await anyio.open_file(destination, "wb") as output:
                while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                    file_size += len(chunk)
                    if file_size > MAX_UPLOAD_FILE_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=(
                                f"파일 1개 최대 용량은 {format_bytes(MAX_UPLOAD_FILE_BYTES)}입니다. "
                                f"'{original_name}' 파일이 제한을 초과했습니다."
                            ),
                        )
                    if total_bytes + file_size > MAX_UPLOAD_TOTAL_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=(
                                f"전체 업로드 최대 용량은 {format_bytes(MAX_UPLOAD_TOTAL_BYTES)}입니다. "
                                "현재 요청이 제한을 초과했습니다."
                            ),
                        )
                    await output.write(chunk)

            validate_excel_signature(destination, safe_name)
            total_bytes += file_size
            stored.append(
                StoredUpload(
                    original_name=original_name,
                    safe_name=safe_name,
                    saved_name=saved_name,
                    path=destination,
                    size_bytes=file_size,
                )
            )
        except BaseException:
            destination.unlink(missing_ok=True)
            for item in stored:
                item.path.unlink(missing_ok=True)
            for pending_upload in files[index:]:
                await pending_upload.close()
            raise
        finally:
            await upload.close()

    return stored, total_bytes
