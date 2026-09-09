from __future__ import annotations

from pathlib import Path

from backend.auth.user_store import ACCOUNT_SPECS


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_production_environment_template_covers_required_runtime_settings():
    template = (PROJECT_ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
    keys = {
        line.split("=", 1)[0]
        for line in template.splitlines()
        if line and not line.startswith("#") and "=" in line
    }

    assert {"APP_ENV", "FRONTEND_ORIGIN", "DATABASE_URL", "REDIS_URL", "SENTRY_DSN", "OBJECT_STORAGE_BUCKET", "SCM_STORAGE_DIR"} <= keys
    assert {spec.password_hash_env for spec in ACCOUNT_SPECS} <= keys


def test_production_deploy_keeps_two_one_process_analysis_workers():
    repository_root = PROJECT_ROOT.parent
    deploy_script = (repository_root / ".github" / "deploy.sh").read_text(encoding="utf-8")
    stack = (repository_root / "infra" / "lib" / "esm-stack.ts").read_text(encoding="utf-8")

    assert 'if [ "$ENVIRONMENT" = "prd" ] && [[ "$SERVICE" == *-worker-esm ]]' in deploy_script
    assert "update_args+=(--desired-count 2)" in deploy_script
    assert "'--loglevel=info', '--concurrency=1'" in stack
    assert "desiredCount: isProd ? 2 : 1" in stack
