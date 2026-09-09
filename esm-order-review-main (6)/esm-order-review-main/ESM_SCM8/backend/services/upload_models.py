"""Upload value objects shared by routers and analysis services."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path


@dataclass(frozen=True)
class SavedUpload:
    original_name: str
    saved_name: str
    path: Path
    size_bytes: int
    content: bytes | None = None
    role: str | None = None

    def read_bytes(self) -> bytes:
        if self.content is not None:
            return self.content
        return self.path.read_bytes()

    def sha256(self) -> str:
        digest = hashlib.sha256()
        if self.content is not None:
            digest.update(self.content)
            return digest.hexdigest()
        with self.path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()


class UploadedFileAdapter:
    """Adapt a disk-backed or in-memory upload to the core loader interface."""

    def __init__(self, name: str, *, content: bytes | None = None, path: Path | None = None) -> None:
        if content is None and path is None:
            raise ValueError("content or path is required")
        self.name = name
        self._content = content
        self.path = path
        self.size = len(content) if content is not None else int(path.stat().st_size)  # type: ignore[union-attr]

    def getvalue(self) -> bytes:
        if self._content is not None:
            return self._content
        return self.path.read_bytes()  # type: ignore[union-attr]

    def get_source(self) -> bytes | Path:
        return self._content if self._content is not None else self.path  # type: ignore[return-value]

    def read_sample(self, size: int = 4096) -> bytes:
        if self._content is not None:
            return self._content[:size]
        with self.path.open("rb") as source:  # type: ignore[union-attr]
            return source.read(size)


def reader_filename(filename: str) -> str:
    if Path(filename).suffix.lower() == ".xlsm":
        return f"{Path(filename).stem}.xlsx"
    return filename


def uploaded_file_adapter(upload: SavedUpload) -> UploadedFileAdapter:
    return UploadedFileAdapter(
        reader_filename(upload.original_name),
        content=upload.content,
        path=upload.path if upload.content is None else None,
    )


__all__ = ["SavedUpload", "UploadedFileAdapter", "reader_filename", "uploaded_file_adapter"]
