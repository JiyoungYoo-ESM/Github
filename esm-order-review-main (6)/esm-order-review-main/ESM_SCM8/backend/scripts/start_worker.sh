#!/usr/bin/env sh
set -eu

if [ "${APP_ENV:-}" != "production" ] && [ "${APP_ENV:-}" != "prod" ]; then
  echo "APP_ENV must be production when using start_worker.sh" >&2
  exit 1
fi

exec python -m celery -A backend.worker.celery_app.celery_app worker \
  --loglevel=INFO \
  --queues="${CELERY_WORKER_QUEUES:-analysis}" \
  --concurrency="${CELERY_WORKER_CONCURRENCY:-1}"
