from __future__ import annotations

import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException

from backend.services import upload_storage


class FakeUpload:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self._source = BytesIO(content)
        self.read_sizes: list[int] = []
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self._source.read(size)

    async def close(self) -> None:
        self.closed = True


def store(files, destination):
    return asyncio.run(
        upload_storage.store_upload_files(
            files,
            destination,
            lambda index, safe_name: f"{index}_{safe_name}",
        )
    )


def test_store_upload_files_streams_in_bounded_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_storage, "UPLOAD_CHUNK_BYTES", 4)
    upload = FakeUpload("sample.xlsx", b"PK\x03\x04abcdefgh")

    stored, total = store([upload], tmp_path)

    assert total == 12
    assert stored[0].path.read_bytes() == b"PK\x03\x04abcdefgh"
    assert upload.read_sizes == [4, 4, 4, 4]
    assert upload.closed is True


def test_store_upload_files_removes_all_files_when_total_limit_is_exceeded(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_storage, "UPLOAD_CHUNK_BYTES", 4)
    monkeypatch.setattr(upload_storage, "MAX_UPLOAD_FILE_BYTES", 100)
    monkeypatch.setattr(upload_storage, "MAX_UPLOAD_TOTAL_BYTES", 11)
    first = FakeUpload("first.xlsx", b"PK\x03\x04aa")
    second = FakeUpload("second.xlsx", b"PK\x03\x04bb")

    with pytest.raises(HTTPException) as error:
        store([first, second], tmp_path)

    assert error.value.status_code == 413
    assert list(tmp_path.iterdir()) == []
    assert first.closed is True
    assert second.closed is True


def test_store_upload_files_rejects_invalid_excel_signature(tmp_path):
    upload = FakeUpload("fake.xlsx", b"this is not an Excel workbook")

    with pytest.raises(HTTPException) as error:
        store([upload], tmp_path)

    assert error.value.status_code == 400
    assert list(tmp_path.iterdir()) == []
    assert upload.closed is True


def test_store_upload_files_rejects_too_many_files_before_reading(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_storage, "MAX_UPLOAD_FILES", 1)
    files = [FakeUpload("one.xlsx", b"PK\x03\x04"), FakeUpload("two.xlsx", b"PK\x03\x04")]

    with pytest.raises(HTTPException) as error:
        store(files, tmp_path)

    assert error.value.status_code == 413
    assert list(tmp_path.iterdir()) == []
    assert all(upload.read_sizes == [] for upload in files)


def test_legacy_xls_html_export_is_accepted(tmp_path):
    upload = FakeUpload("legacy.xls", b"<html><table><tr><td>value</td></tr></table></html>")

    stored, total = store([upload], tmp_path)

    assert total == stored[0].size_bytes
