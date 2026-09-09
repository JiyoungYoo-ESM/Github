from __future__ import annotations

from pathlib import Path

import pytest

from backend.services import object_storage, storage


def test_object_key_is_prefixed_and_rejects_traversal(monkeypatch):
    monkeypatch.setattr(object_storage, "OBJECT_STORAGE_PREFIX", "esm-scm")

    assert object_storage.key("outputs/job/report.xlsx") == "esm-scm/outputs/job/report.xlsx"
    with pytest.raises(ValueError):
        object_storage.key("../secrets.txt")


def test_completed_workbook_is_published_and_download_url_is_presigned(tmp_path: Path, monkeypatch):
    job_id = "20260723_123456_abcdef12"
    workbook = tmp_path / f"ESM_order_review_{job_id}.xlsx"
    workbook.write_bytes(b"workbook")
    uploads: list[tuple[Path, str, str | None]] = []

    monkeypatch.setattr(storage.object_storage, "enabled", lambda: True)
    monkeypatch.setattr(
        storage.object_storage,
        "upload_file",
        lambda path, name, content_type=None: uploads.append((path, name, content_type)) or name,
    )
    monkeypatch.setattr(
        storage.object_storage,
        "presigned_download_url",
        lambda name, download_name: f"https://objects.example/{name}?expires=300",
    )
    monkeypatch.setattr(storage.object_storage, "exists", lambda name: True)

    storage.publish_job_output(job_id, workbook)

    assert uploads == [
        (
            workbook,
            f"outputs/{job_id}/{workbook.name}",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    ]
    assert storage.object_download_url(job_id) == (
        f"https://objects.example/outputs/{job_id}/{workbook.name}?expires=300"
    )


def test_lifecycle_apply_replaces_only_esm_managed_rules(monkeypatch):
    class FakeClient:
        def __init__(self) -> None:
            self.applied: dict[str, object] | None = None

        def get_bucket_lifecycle_configuration(self, **_: object) -> dict[str, object]:
            return {"Rules": [{"ID": "external-keep", "Status": "Enabled"}, {"ID": object_storage._lifecycle_rule_id("outputs"), "Status": "Disabled"}]}

        def put_bucket_lifecycle_configuration(self, **kwargs: object) -> None:
            self.applied = kwargs

    fake = FakeClient()
    monkeypatch.setattr(object_storage, "OBJECT_STORAGE_BUCKET", "esm-scm")
    monkeypatch.setattr(object_storage, "OBJECT_STORAGE_PREFIX", "esm-scm")
    monkeypatch.setattr(object_storage, "client", lambda: fake)

    applied = object_storage.apply_lifecycle_rules()

    rules = applied["rules"]
    assert {rule["ID"] for rule in rules} == {
        object_storage._lifecycle_rule_id("outputs"),
        object_storage._lifecycle_rule_id("support"),
    }
    assert fake.applied is not None
    applied_rules = fake.applied["LifecycleConfiguration"]["Rules"]  # type: ignore[index]
    assert any(rule["ID"] == "external-keep" for rule in applied_rules)  # type: ignore[index]
