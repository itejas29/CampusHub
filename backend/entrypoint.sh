#!/usr/bin/env bash
# Applies migrations (and optionally seeds) before the API starts.
set -euo pipefail

echo "==> Waiting for PostgreSQL at ${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}"
python - <<'PY'
import os, socket, sys, time

host = os.getenv("POSTGRES_HOST", "postgres")
port = int(os.getenv("POSTGRES_PORT", "5432"))
for attempt in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            print("    database is accepting connections")
            sys.exit(0)
    except OSError:
        time.sleep(1)
print("    database did not become ready in time", file=sys.stderr)
sys.exit(1)
PY

echo "==> Applying database migrations"
alembic upgrade head

if [ "${SEED_ON_START:-false}" = "true" ]; then
  echo "==> Seeding demo data"
  python -m app.seed.run || echo "    seed skipped (data already present)"
fi

echo "==> Starting API"
exec "$@"
