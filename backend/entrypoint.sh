#!/usr/bin/env bash
# Applies migrations (and optionally seeds) before the API starts.
set -euo pipefail

echo "==> Waiting for PostgreSQL"
python - <<'PY'
import os, socket, sys, time
from urllib.parse import urlparse

db_url = os.getenv("DATABASE_URL")
if db_url:
    clean = db_url.replace("postgresql+psycopg://", "http://").replace("postgresql://", "http://").replace("postgres://", "http://")
    parsed = urlparse(clean)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
else:
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = int(os.getenv("POSTGRES_PORT", "5432"))

print(f"    checking connectivity to {host}:{port}")
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
if [ -n "${PORT:-}" ]; then
  new_args=()
  replace_next=0
  for arg in "$@"; do
    if [ "$replace_next" -eq 1 ]; then
      new_args+=("$PORT")
      replace_next=0
    elif [ "$arg" = "--port" ]; then
      new_args+=("$arg")
      replace_next=1
    else
      new_args+=("$arg")
    fi
  done
  set -- "${new_args[@]}"
fi

exec "$@"
