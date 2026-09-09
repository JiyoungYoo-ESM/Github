from __future__ import annotations

import os
import time

from backend.services import cms_fetch_cache


def _make_cache_file(directory, name: str, age_days: float) -> None:
    path = directory / name
    path.write_text("{}", encoding="utf-8")
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))


def test_prune_removes_only_old_files(monkeypatch, tmp_path):
    monkeypatch.setattr(cms_fetch_cache, "CMS_FETCH_CACHE_DIR", tmp_path)
    _make_cache_file(tmp_path, "old.json", age_days=8)
    _make_cache_file(tmp_path, "fresh.json", age_days=1)

    result = cms_fetch_cache.prune_disk_cache(max_age_days=7)

    assert result["removed"] == 1
    assert result["kept"] == 1
    assert not (tmp_path / "old.json").exists()
    assert (tmp_path / "fresh.json").exists()


def test_prune_disabled_with_zero_days(monkeypatch, tmp_path):
    monkeypatch.setattr(cms_fetch_cache, "CMS_FETCH_CACHE_DIR", tmp_path)
    _make_cache_file(tmp_path, "old.json", age_days=30)

    result = cms_fetch_cache.prune_disk_cache(max_age_days=0)

    assert result["skipped"] is True
    assert (tmp_path / "old.json").exists()
