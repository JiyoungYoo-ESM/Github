"""Startup configuration validation (IMPROVEMENT_PLAN.md item 1 / 11)."""

from __future__ import annotations

import pytest

import backend.config as config


def test_dev_defaults_pass_validation():
    """The shipped development defaults must not raise."""
    config.validate_config()


def test_production_requires_real_frontend_origin(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "_extra_origins", [])
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", config._DEFAULT_ALLOWED_ORIGINS)
    with pytest.raises(config.ConfigError, match="FRONTEND_ORIGIN"):
        config.validate_config()


def test_wildcard_origin_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["*"])
    with pytest.raises(config.ConfigError, match="와일드카드"):
        config.validate_config()


def test_malformed_origin_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["not-a-url", "https://ok.example.com"])
    with pytest.raises(config.ConfigError, match="CORS 오리진"):
        config.validate_config()


def test_origin_with_path_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["https://ok.example.com/app"])
    with pytest.raises(config.ConfigError):
        config.validate_config()


def test_production_valid_config_passes(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setattr(config, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(config, "CELERY_BROKER_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(config, "SENTRY_DSN", "https://public@example.ingest.sentry.io/1")
    monkeypatch.setattr(config, "OBJECT_STORAGE_BUCKET", "esm-scm-test")
    monkeypatch.setattr(config, "_storage_root_env", "/persistent-data")
    monkeypatch.setattr(config, "_extra_origins", ["https://esm.example.com"])
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["https://esm.example.com"])
    config.validate_config()


def test_invalid_app_env_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "productionn")
    with pytest.raises(config.ConfigError, match="APP_ENV"):
        config.validate_config()


def test_production_requires_database_url(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(config, "_extra_origins", ["https://esm.example.com"])
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["https://esm.example.com"])
    with pytest.raises(config.ConfigError, match="DATABASE_URL"):
        config.validate_config()


def test_production_requires_persistent_storage_volume(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setattr(config, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(config, "CELERY_BROKER_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(config, "SENTRY_DSN", "https://public@example.ingest.sentry.io/1")
    monkeypatch.setattr(config, "OBJECT_STORAGE_BUCKET", "esm-scm-test")
    monkeypatch.setattr(config, "_storage_root_env", "")
    monkeypatch.setattr(config, "_extra_origins", ["https://esm.example.com"])
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["https://esm.example.com"])

    with pytest.raises(config.ConfigError, match="SCM_STORAGE_DIR"):
        config.validate_config()


def test_production_allows_missing_redis_and_sentry(monkeypatch):
    # Redis/Celery/Sentry are optional in production (in-memory fallbacks); the
    # app must still validate when they are unset.
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setattr(config, "REDIS_URL", "")
    monkeypatch.setattr(config, "CELERY_BROKER_URL", "")
    monkeypatch.setattr(config, "SENTRY_DSN", "")
    monkeypatch.setattr(config, "OBJECT_STORAGE_BUCKET", "esm-scm-test")
    monkeypatch.setattr(config, "_storage_root_env", "/persistent-data")
    monkeypatch.setattr(config, "_extra_origins", ["https://esm.example.com"])
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["https://esm.example.com"])

    config.validate_config()


def test_production_requires_object_storage_bucket(monkeypatch):
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    monkeypatch.setattr(config, "DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setattr(config, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(config, "SENTRY_DSN", "https://public@example.ingest.sentry.io/1")
    monkeypatch.setattr(config, "OBJECT_STORAGE_BUCKET", "")
    monkeypatch.setattr(config, "_storage_root_env", "/persistent-data")
    monkeypatch.setattr(config, "_extra_origins", ["https://esm.example.com"])
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["https://esm.example.com"])

    with pytest.raises(config.ConfigError, match="OBJECT_STORAGE_BUCKET"):
        config.validate_config()


def test_invalid_sentry_dsn_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "SENTRY_DSN", "not-a-dsn")
    with pytest.raises(config.ConfigError, match="SENTRY_DSN"):
        config.validate_config()


def test_analysis_slot_lease_must_outlast_analysis_timeouts(monkeypatch):
    monkeypatch.setattr(config, "ANALYSIS_SLOT_TTL_SECONDS", config.SEASON_ANALYSIS_TIMEOUT_SECONDS)

    with pytest.raises(config.ConfigError, match="Redis lease"):
        config.validate_config()


def test_queued_analysis_timeout_keeps_worker_shutdown_grace(monkeypatch):
    monkeypatch.setattr(config, "CELERY_BROKER_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(config, "CELERY_TASK_TIME_LIMIT_SECONDS", 1800)
    monkeypatch.setattr(config, "ANALYSIS_WORKER_GRACE_SECONDS", 60)

    assert config.bounded_worker_timeout_seconds(1800) == 1740


def test_worker_shutdown_grace_must_be_shorter_than_hard_limit(monkeypatch):
    monkeypatch.setattr(config, "ANALYSIS_WORKER_GRACE_SECONDS", 2100)

    with pytest.raises(config.ConfigError, match="WORKER_GRACE"):
        config.validate_config()


def test_stale_job_boundary_must_outlast_worker_limit(monkeypatch):
    monkeypatch.setattr(
        config,
        "ANALYSIS_JOB_STALE_SECONDS",
        config.CELERY_TASK_TIME_LIMIT_SECONDS,
    )

    with pytest.raises(config.ConfigError, match="JOB_STALE"):
        config.validate_config()


def test_monthly_season_factor_scheduler_requires_explicit_close_schedule(monkeypatch):
    monkeypatch.setattr(config, "SCM_V3_SEASON_FACTOR_MONTHLY_ENABLED", True)
    monkeypatch.setattr(config, "SCM_V3_SEASON_FACTOR_MONTHLY_DAY", None)
    monkeypatch.setattr(config, "SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST", None)

    with pytest.raises(config.ConfigError, match="SCM_V3_SEASON_FACTOR_MONTHLY_DAY"):
        config.validate_config()


def test_monthly_season_factor_scheduler_accepts_explicit_schedule(monkeypatch):
    monkeypatch.setattr(config, "SCM_V3_SEASON_FACTOR_MONTHLY_ENABLED", True)
    monkeypatch.setattr(config, "SCM_V3_SEASON_FACTOR_MONTHLY_DAY", 5)
    monkeypatch.setattr(config, "SCM_V3_SEASON_FACTOR_MONTHLY_HOUR_KST", 3)

    config.validate_config()
