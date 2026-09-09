from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.services import storage


def test_download_token_is_bound_to_account_and_entity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(storage, "OUTPUT_DIR", tmp_path)
    job_id = "owned-job"
    output_dir = tmp_path / job_id
    output_dir.mkdir()
    (output_dir / f"ESM_order_review_{job_id}.xlsx").write_bytes(b"xlsx")
    token = storage.create_download_token(
        output_dir,
        job_id,
        owner_username="adminmaster",
        entity_code="PL",
    )

    storage.verify_download_token(
        job_id,
        token,
        expected_username="adminmaster",
        expected_entity_code="PL",
    )
    with pytest.raises(HTTPException) as wrong_user:
        storage.verify_download_token(
            job_id,
            token,
            expected_username="my_team",
            expected_entity_code="PL",
        )
    assert wrong_user.value.status_code == 403
    with pytest.raises(HTTPException) as wrong_entity:
        storage.verify_download_token(
            job_id,
            token,
            expected_username="adminmaster",
            expected_entity_code="MY",
        )
    assert wrong_entity.value.status_code == 403
