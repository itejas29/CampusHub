#!/bin/sh
# Starts the API for the browser tests on its own, freshly seeded database.
#
# The tests allocate mentors and approve submissions, so they must never run
# against a database someone is using. Each run rebuilds a throwaway SQLite
# file from the demo seed — the same data `make seed` loads.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$HERE/../../backend"
PYTHON="${CAMPUSHUB_PYTHON:-$HERE/../../.venv/bin/python}"
WORK="${E2E_WORK_DIR:-${TMPDIR:-/tmp}/campushub-e2e}"
PORT="${E2E_API_PORT:-8100}"

rm -rf "$WORK" && mkdir -p "$WORK/uploads"
export DATABASE_URL="sqlite:///$WORK/campushub.db"
export LOCAL_STORAGE_DIR="$WORK/uploads"

cd "$BACKEND"
"$PYTHON" -c "import app.models; from app.db.base import Base; from app.db.session import engine; Base.metadata.create_all(engine)"
"$PYTHON" -m app.seed.run > "$WORK/seed.log" 2>&1
exec "$PYTHON" -m uvicorn app.main:app --port "$PORT"
