#!/usr/bin/env sh
# Railway backend entrypoint. Fail closed before accepting any traffic.
set -eu

if [ "${APP_ENV:-}" != "production" ] && [ "${APP_ENV:-}" != "prod" ]; then
  echo "APP_ENV must be production when using start_production.sh" >&2
  exit 1
fi

python -m alembic upgrade head
python -m backend.scripts.verify_runtime

exec python -m uvicorn backend.main:app --host :: --port "${PORT:-8002}"
