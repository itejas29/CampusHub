# Phase C — remediation batches

Every run below: local Docker stack, 24 Oct 2026. PostgreSQL runs use a
disposable `postgres:16-alpine` container (`campushub_pytest`, port 55432) that
holds nothing else. The live Railway database was not touched.

## C1 — QA-15, one active mentor per student

| Check | Environment | Result | Evidence |
|---|---|---|---|
| QA-15 tests | SQLite | 12 passed, 2 skipped (PostgreSQL-only) | — |
| QA-15 tests | PostgreSQL 16 | 14 passed (incl. 8 simultaneous assignments; migration on planted duplicates, down and up) | — |
| Full backend suite | SQLite | 1,035 passed, 4 skipped, 1 failed | `c1_backend_sqlite.log`, `c1_backend_sqlite_junit.xml` |
| Full backend suite | PostgreSQL 16 | 1,039 passed, 1 failed | `c1_backend_pg.log`, `c1_backend_pg_junit.xml` |
| `test_chatbot_answers.py` after copying `frontend/src` into the container | SQLite | 6 passed | — |
| Migration 0019 on the local demo database | PostgreSQL 16 (compose) | applied; 0 duplicates, 0 rows retired | `report_mentor_duplicates` output |

The one failure in both full runs is `test_every_link_the_assistant_gives_is_a_page_the_app_has`:
it reads `frontend/src/App.tsx`, which the backend container does not mount. It
is an environment artefact, not a defect (Phase B ran outside Docker and passed
it); with the frontend copied in it passes.
