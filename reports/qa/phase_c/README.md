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

## C2 — QA-16, the internship student list a page at a time

* `GET /internships/enrollments/page` → `Page[EnrollmentSummary]` (`items`,
  `total`, `page`, `page_size`). `page_size` 1–200 (default 50); filters
  (programme, group, status, programme types, mine) and the search (name, roll
  number, organisation; `%` and `_` literal) all run in SQL; ordered by id, so a
  page is stable and rows added meanwhile land at the end.
* `GET /internships/enrollments` keeps returning the full list (the mentor
  allocation screen needs the whole cohort), but its search now runs in SQL
  instead of Python over every row.
* The **My Students / Internship students** screens use the paged endpoint:
  server-side search (debounced), Previous / Next, "Showing 51–100 of 409".

| Check | Environment | Result |
|---|---|---|
| `test_internship_pagination.py` (15) + `test_mentor_allocation.py` | SQLite | 39 passed |
| Browser: Priya Nair (Summer Internship coordinator, 409 students) | local stack | 50 rows, "Showing 1–50 of 409"; Next → "51–100 of 409"; search "meera" → 12 from the server |
| Full backend suite | SQLite | **1,051 passed, 4 skipped** (PostgreSQL-only tests) — `c2_backend_sqlite.log` |
| Full backend suite | isolated PostgreSQL 16 | **1,055 passed** — `c2_backend_pg.log` |

A page costs the same number of queries for 5 rows as for 20 (the test gives
every row the same mentor: a mentor's details are loaded once per mentor, which
the probe showed is the only thing that varied).

### Other unpaginated lists that return students (reviewed, not changed)

| Endpoint | Bounded by | Note |
|---|---|---|
| `GET /mentorship/my-mentees`, `/mentorship/assignments` | one mentor / one department | batched (QA-06) |
| `GET /electives/admin/preferences`, `/admin/allocations` | one slot | slot cohort (~200) |
| `GET /mooc/admin/registrations` | **all departments, then filtered in Python** | candidate for paging + SQL scoping (Phase E) |
| `GET /mooc/admin/rounds/{id}/students` | one round | round cohort |
| `GET /minors/applications` | one coordinator's minors | |
| `GET /events/{id}/registrations` | one event's capacity | |
| `GET /internships/programs/{id}/mentor-roster` | one programme | needs the whole cohort |

## C3 — QA-20, PostgreSQL in CI

New workflow `.github/workflows/ci.yml`, on every pull request and every push
to a branch other than `master` (master is already gated by
`deploy-backend.yml`, which is unchanged). It deploys nothing, reads no secrets
and has `contents: read` only.

| Job | What it proves |
|---|---|
| `backend-sqlite` | full suite on SQLite (the deploy gate's database), JUnit artifact |
| `backend-postgres` | PostgreSQL 16 service container: `alembic upgrade head` from an empty database; latest migration down and up again; `alembic check` (informational until QA-21); full suite with `CAMPUSHUB_TEST_DATABASE_URL`; the concurrency and mentor tests again on their own; JUnit and migration logs as artifacts |
| `frontend` | `npm ci`, `tsc -b && vite build` |

The databases are throwaway service containers (`ci`/`ci`), never a deployed
one. The workflow runs on GitHub for the first time when this branch's pull
request is opened; its result is recorded there.

## C4 — QA-22, the chatbot button on phones

* Below the `sm` breakpoint the button is 48 px (was 56) and sits 16 px from
  the corner, above the home indicator (`env(safe-area-inset-bottom)`).
* The page body gets `pb-24` on phones, so the last card — and the new pager's
  **Next** button — scrolls clear of the button; the footer text stops short of it.
* Desktop is unchanged (`sm:` restores the old size and offsets).

| Check | Result |
|---|---|
| `e2e/9-mobile-chatbot.spec.ts` at 390 × 844, student dashboard and coordinator's Internship students, scrolled to the bottom: no link, button or field under the chatbot; no sideways scroll | 2 passed (`c4_e2e_junit.xml`) |
| Same test on the code before the fix | coordinator **failed**: the chatbot covered `button "Next"` (`c4_screens/before_coordinator_390px.png`) |
| Screens after | `c4_screens/after_*_390px.png` |
| `npm run build` | passed |

Run locally against the Docker API (read-only test), because `e2e/start-api.sh`
expects a POSIX virtualenv this Windows machine does not have; in the normal
harness the spec runs with the other eight.

## C5 — QA-19, security headers on the frontend (owner approval before merge)

Both `vercel.json` files (repo root, which the live project builds from, and
`frontend/`) now send, on every path:

| Header | Value | Mode |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | enforced |
| `X-Frame-Options` | `DENY` | enforced |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | enforced |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | enforced |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (no `preload`) | enforced |
| `Content-Security-Policy-Report-Only` | `default-src 'self'`; scripts `'self'` only; styles `'self' 'unsafe-inline'` + Google Fonts; fonts `'self'` + gstatic; images and API calls `'self'` + the Railway API and `api.campushub.pdeu.ac.in`; `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'` | **report only** |

`'unsafe-inline'` for styles is needed by the animation library's inline
`style` attributes; scripts need no exception (the build has no inline script).

| Check | Result |
|---|---|
| Production build served by `vite preview` with these headers and the CSP **enforced**; student, CSSI coordinator and registrar signed in, 10 pages and the chatbot visited, every `securitypolicyviolation` collected | 3 / 3 accounts, **0 violations** |
| Same check with Google Fonts removed from the policy (to prove the check sees violations) | failed as expected: `style-src-elem fonts.googleapis.com` |

Not checked locally: calls to the Railway origin (the local preview proxies
`/api`, so they are same-origin). **Before merging**, the owner opens a Vercel
*preview* deployment of this branch, signs in, and confirms the browser console
shows no `Content-Security-Policy-Report-Only` warnings. Only after a clean
preview — and the owner's say-so — should the header be renamed to the
enforcing `Content-Security-Policy`.

## C6 — QA-17, QA-18, QA-21

### QA-17 — a faculty score without recomputing the institution

`department_scores` read every enrollment, every student's name and every
stage, report and document row **in the institution** on each call, then ran a
query per student for each closed presentation window; `/faculty-scores/me`
scored the whole department to return one row. Now:

* only rows that can credit someone being scored are read — records they
  mentor or whose group they lead, and anything they reviewed; every other row
  was skipped anyway;
* the mentors' evaluations and programme codes are loaded once;
* `faculty_score` scores one person (`faculty_ids={id}`), still placing each
  review against the whole department — work reviewed by an *unscored* person
  falls to the mentor, so the reviewer lookup must know every scored colleague.
  (The first version missed this; the equivalence test below caught it.)

| Check | Result |
|---|---|
| `test_one_faculty_score_is_their_row_of_the_department` — reviews by the mentor and by a colleague, a pending stage, a closed presentation window, a meeting request | one-person score = department row, field by field and entry by entry |
| `test_a_score_costs_the_same_queries_however_many_students` | 16 queries for 2 or 12 mentees; the old code **failed** it (16 → 26) |
| Demo database, all 19 demo faculty, old vs new | ~190 ms → 22–35 ms per score; **identical** scores (539 scored items) |
| `test_faculty_scoring.py`, `test_query_counts.py`, `test_hod.py` | 60 passed |

### QA-18 — overload is refused quickly, not queued (`core/overload.py`)

Mechanisms, each a setting; **the limits are the owner's to choose from the
staging load test** (Phase F, blocked until staging exists):

| Setting | Default | Effect |
|---|---|---|
| `DB_STATEMENT_TIMEOUT_MS` | 30 000 | PostgreSQL cancels a longer statement (set on every app connection; migrations use their own engine and are not limited) |
| `DB_POOL_TIMEOUT_S` | 30 (unchanged) | longest wait for a connection |
| `MAX_IN_FLIGHT_REQUESTS` | **0 = no limit** (unchanged behaviour) | beyond it, new requests get 503 at once; `/health` is never refused |

A pool timeout or a cancelled statement is now **503 + `Retry-After: 5`**
(`service_busy`), not a 500. A shed request still carries CORS and security
headers, so the browser can read it. Other database failures are unchanged.

`test_overload.py` (9, one PostgreSQL-only): shedding at the limit and the slot
given back; health never shed; no limit by default; both timeouts → 503; other
failures still 500; connection options; PostgreSQL really cancels
`pg_sleep(2)` under a 200 ms timeout and it is recognised as a timeout.

Not addressed in code (infrastructure, owner decision): one Uvicorn process,
worker count, and Railway's own request timeout.

### QA-21 — the models now declare the 12 server defaults

The 12 columns `alembic check` reported (each given a server default by a
migration, to back-fill rows) now declare the same `server_default` in the
model — no migration, no change to any database. PostgreSQL `json` has no `=`,
so Alembic could not compare JSON defaults at all; `alembic/env.py` compares
those as text (other types keep Alembic's comparison).

| Check | Result |
|---|---|
| `alembic check` on a freshly migrated PostgreSQL 16 database, before | 12 `modify_default` operations (same list as the QA report) |
| after | `No new upgrade operations detected.` |
| a JSON default changed by hand in that database (negative control) | detected |
| `test_schema_matches_models.py` (PostgreSQL) | passed; CI's `alembic check` step is now enforcing |

## Phase C — final verification (whole branch, C1–C6)

| Check | Environment | Result |
|---|---|---|
| Full backend suite | SQLite | **1,060 passed, 6 skipped** (the PostgreSQL-only tests) — `final_backend_sqlite.log` / `_junit.xml` |
| Full backend suite | isolated PostgreSQL 16 | **1,066 passed** — `final_backend_pg.log` / `_junit.xml` |
| Frontend `tsc -b && vite build` | local | passed |
| `e2e/9-mobile-chatbot.spec.ts` | local Chrome, 390 px | 2 passed |

No production system, database or setting was touched. Still with the owner:
the live duplicate-mentor report before 0019 deploys (QA-15), the Vercel
preview check of the headers (QA-19), and the QA-18 limits (staging needed).
