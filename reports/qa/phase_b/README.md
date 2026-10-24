# Phase B — baseline reproduction (22 Oct 2026)

Commit under test: `9d6e54c` (master). Run locally; nothing deployed, the live
Railway database was not touched.

| Check | Environment | Result | Evidence |
|---|---|---|---|
| Backend suite | SQLite (in memory) | 1,026 tests: **1,024 passed, 2 skipped, 0 failed** (the 2 are PostgreSQL-only) | `backend_sqlite.log`, `backend_sqlite_junit.xml` |
| Backend suite | PostgreSQL 16, disposable local container (`campushub_pytest`) | 1,026 tests: **1,026 passed, 0 failed**, including the concurrency tests | `backend_pg.log`, `backend_pg_junit.xml` |
| Frontend build | `tsc -b && vite build` | **passed** | `frontend_build.log` |
| Browser end-to-end | Playwright, own seeded SQLite API (:8100) + Vite (:5180) | **15 / 15 passed** | `frontend_e2e.log` |

Matches the 19 Oct QA report: no regressions since the QA fixes were merged.

Still open from that report (not addressed in this phase): QA-15 to QA-22.
QA-20 is confirmed: CI (`.github/workflows/deploy-backend.yml`) still runs the
backend suite on SQLite only — the PostgreSQL run above is manual.
