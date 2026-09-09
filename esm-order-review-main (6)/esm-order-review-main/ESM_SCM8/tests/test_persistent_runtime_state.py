"""Database-backed runtime state survives a process-local store reset."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from backend import database
from backend.auth.models import UserAccount
from backend.database import Base
from backend.services import auth, cms_analysis_jobs, season_trend_jobs
from backend.services.order_review_store import load_latest_order_review_result, save_latest_order_review_result
from backend.services.season_trend_store import load_latest_season_trend_result, save_latest_season_trend_result


@pytest.fixture()
def persistent_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    previous_url = database.DATABASE_URL
    database.get_engine.cache_clear()
    database.get_session_factory.cache_clear()
    monkeypatch.setattr(database, "DATABASE_URL", f"sqlite:///{tmp_path / 'runtime-state.db'}")
    Base.metadata.create_all(database.get_engine())
    try:
        yield
    finally:
        database.get_engine.cache_clear()
        database.get_session_factory.cache_clear()
        monkeypatch.setattr(database, "DATABASE_URL", previous_url)


def test_database_session_survives_memory_store_lifecycle(persistent_database):
    account = UserAccount("persisted", "", "role", ("PL",), True, "Persisted", "TEAM")
    token, _ = auth.create_session(account)

    assert auth.session_record(token) is not None
    auth.revoke_session(token)
    assert auth.session_record(token) is None


def test_jobs_and_latest_results_are_database_backed(persistent_database):
    cms_job = cms_analysis_jobs.create_cms_analysis_job("user__PL", {"as_of": "2026-07-23"})
    cms_analysis_jobs.update_cms_analysis_job(cms_job, status="succeeded", result={"ok": True})
    job = cms_analysis_jobs.get_cms_analysis_job(cms_job)
    assert job is not None
    assert job["job_id"] == cms_job
    assert job["status"] == "succeeded"
    assert job["client_id"] == "user__PL"
    assert job["request_body"] == {"as_of": "2026-07-23"}
    assert job["result"] == {"ok": True}

    first = season_trend_jobs.create_season_trend_job({"month": 1}, "user__PL")
    second = season_trend_jobs.create_season_trend_job({"month": 2}, "user__PL")
    assert not season_trend_jobs.is_latest_season_trend_job(first, "user__PL")
    assert season_trend_jobs.is_latest_season_trend_job(second, "user__PL")

    save_latest_order_review_result("user__PL", cms_job, {"tables": {"order_review": [{"sku": "A"}]}}, "test")
    assert load_latest_order_review_result("user__PL")["rows"] == [{"sku": "A"}]
    save_latest_season_trend_result({"series": [{"month": "2026-07"}]}, "user__PL")
    assert load_latest_season_trend_result("user__PL")["series"] == [{"month": "2026-07"}]


def test_persistent_job_retention_handles_sqlite_timestamps(persistent_database):
    job_id = cms_analysis_jobs.create_cms_analysis_job("user__PL", {})
    cms_analysis_jobs.update_cms_analysis_job(job_id, status="succeeded")
    with database.get_session_factory()() as session:
        from backend.models.persistence import AnalysisJob

        session.get(AnalysisJob, job_id).updated_at = datetime.now(timezone.utc) - timedelta(hours=48)
        session.commit()

    assert cms_analysis_jobs.prune_cms_analysis_jobs() == 1
    assert cms_analysis_jobs.get_cms_analysis_job(job_id) is None


def test_persistent_cancelled_job_rejects_late_success(persistent_database):
    job_id = cms_analysis_jobs.create_cms_analysis_job("user__PL", {})

    cancelled = cms_analysis_jobs.cancel_cms_analysis_job(job_id)
    cms_analysis_jobs.update_cms_analysis_job(
        job_id,
        status="succeeded",
        result={"late": True},
    )

    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
    job = cms_analysis_jobs.get_cms_analysis_job(job_id)
    assert job is not None
    assert job["status"] == "cancelled"
    assert "result" not in job
