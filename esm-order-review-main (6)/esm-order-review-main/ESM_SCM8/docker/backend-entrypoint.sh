#!/bin/sh
set -e

# A command override (e.g. the ECS celery worker) runs as-is — no migrations,
# the web container owns those (avoids two containers racing alembic).
if [ $# -gt 0 ]; then
  exec "$@"
fi

# Run migrations before serving. config.py assembles DATABASE_URL from the PG*
# env vars, so skip only when the DB isn't wired at all (pure local smoke).
if [ -n "${DATABASE_URL:-}" ] || [ -n "${PGHOST:-}" ]; then
  echo "Running alembic upgrade head..."
  alembic upgrade head
fi

exec uvicorn backend.main:app --host 0.0.0.0 --port 8002
