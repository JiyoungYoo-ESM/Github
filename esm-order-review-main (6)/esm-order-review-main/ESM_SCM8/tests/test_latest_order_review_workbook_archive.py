from __future__ import annotations

from pathlib import Path

from backend.services import order_review_store, storage


def test_latest_order_review_workbook_is_archived_per_client(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(order_review_store, "LATEST_ORDER_REVIEW_DIR", tmp_path / "latest")
    source = tmp_path / "ESM_order_review_job-1.xlsx"
    source.write_bytes(b"full-esm-workbook")

    archived = order_review_store.save_latest_order_review_workbook("client/one", source)

    assert archived == tmp_path / "latest" / "client_one.xlsx"
    assert archived.read_bytes() == b"full-esm-workbook"


def test_expired_job_download_is_rehydrated_from_archive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage, "OUTPUT_DIR", tmp_path / "outputs")
    archive = tmp_path / "latest.xlsx"
    archive.write_bytes(b"full-esm-workbook")
    job_id = "20260714_031853_28553258"

    download_url = storage.restore_download_url_from_archive(job_id, archive)

    assert download_url and download_url.startswith(f"/api/download/{job_id}?token=")
    restored = tmp_path / "outputs" / job_id / f"ESM_order_review_{job_id}.xlsx"
    assert restored.read_bytes() == b"full-esm-workbook"
    token = download_url.split("token=", 1)[1]
    storage.verify_download_token(job_id, token)
