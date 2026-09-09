from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from backend.services import cms_analysis_jobs, season_trend_jobs, storage
from backend.services.job_retention import prune_jobs


def job(status: str, updated_at: datetime) -> dict[str, object]:
    return {"status": status, "updated_at": updated_at.isoformat()}


def test_prune_jobs_removes_expired_and_caps_completed_results():
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    jobs = {
        "expired-success": job("succeeded", now - timedelta(hours=25)),
        "abandoned-running": job("running", now - timedelta(hours=25)),
        "recent-success": job("succeeded", now - timedelta(hours=1)),
        "newest-failure": job("failed", now),
        "active": job("running", now - timedelta(hours=2)),
    }

    removed = prune_jobs(jobs, now=now, retention_hours=24, max_retained=1)

    assert removed == {"expired-success", "abandoned-running", "recent-success"}
    assert set(jobs) == {"newest-failure", "active"}


def test_job_registries_prune_expired_entries_and_clear_latest_pointer():
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    cms_analysis_jobs._JOBS.clear()
    cms_analysis_jobs._JOBS["old-cms"] = {"status": "succeeded", "updated_at": old}
    assert cms_analysis_jobs.get_cms_analysis_job("old-cms") is None

    season_trend_jobs._JOBS.clear()
    season_trend_jobs._JOBS["old-season"] = {"status": "failed", "updated_at": old}
    season_trend_jobs._LATEST_JOB_IDS.clear()
    season_trend_jobs._LATEST_JOB_IDS["default"] = "old-season"
    assert season_trend_jobs.get_season_trend_job("old-season") is None
    assert "default" not in season_trend_jobs._LATEST_JOB_IDS


def test_cleanup_old_temp_files_only_removes_expired_tmp_files(tmp_path):
    old_tmp = tmp_path / "old.xlsx.tmp"
    recent_tmp = tmp_path / "recent.xlsx.tmp"
    permanent = tmp_path / "result.xlsx"
    for path in (old_tmp, recent_tmp, permanent):
        path.write_bytes(b"data")
    old_timestamp = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
    os.utime(old_tmp, (old_timestamp, old_timestamp))

    removed = storage._cleanup_old_temp_files(tmp_path, max_age_hours=1)

    assert removed == 1
    assert not old_tmp.exists()
    assert recent_tmp.exists()
    assert permanent.exists()
