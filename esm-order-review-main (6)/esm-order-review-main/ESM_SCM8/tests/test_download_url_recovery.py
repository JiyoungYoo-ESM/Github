from __future__ import annotations

from pathlib import Path

from backend.services import storage


def test_recover_download_url_for_retained_order_workbook(tmp_path: Path, monkeypatch) -> None:
    job_id = "20260714_012154_cbc7cbba"
    monkeypatch.setattr(storage, "OUTPUT_DIR", tmp_path)
    output_dir = tmp_path / job_id
    output_dir.mkdir()
    (output_dir / f"ESM_order_review_{job_id}.xlsx").write_bytes(b"xlsx")

    token = storage.create_download_token(output_dir, job_id)

    assert storage.recover_download_url(job_id) == f"/api/download/{job_id}?token={token}"


def test_recover_download_url_returns_none_when_workbook_is_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage, "OUTPUT_DIR", tmp_path)

    assert storage.recover_download_url("20260714_012154_cbc7cbba") is None
