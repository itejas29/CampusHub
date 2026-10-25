# CampusHub — Post-QA Review

Continuation of the 19 October 2026 QA cycle (`CampusHub_QA_Report.pdf`). This
document records what was verified, what changed, and the evidence, phase by
phase. Every result names its environment and date. Nothing here touched the
live Railway database, production environment variables or real records.

---

## Phase A — Repository and branch recovery (24 Oct 2026)

Environment: local clone, Windows 11, `git` against `github.com/itejas29/CampusHub`.

### A.1 State of the repository

| Item | Finding |
|---|---|
| Production branch | `master`. Pushes touching `backend/**` deploy the API to Railway (`.github/workflows/deploy-backend.yml`, tests first); every push to `master` deploys the frontend on Vercel. |
| `master` head at the start of this phase | `0c297a2` — merge of PR #19 (Phase B evidence), on top of `9d6e54c` |
| Branch `qa-mission` (named by the QA report) | **Does not exist** locally or on GitHub. Its work was committed straight to `master`. |
| QA fix commits | `501372c` "QA cycle: race-condition, performance and security fixes, with reports" and `9d6e54c` "QA report: all reports in one PDF", both 19 Oct, by itejas29, pushed directly to `master` (no PR) |
| Deployed? | **Yes.** The backend workflow ran tests and deployed `8656bb2`, `44ccc2c` and `9d6e54c` to Railway successfully on 19 Oct. The QA fixes are live. |
| Duplicated elsewhere? | No. `qa/phase-b-baseline` (Phase B) built on `9d6e54c`; it held reports and the `campushub-qa` skill only, merged as PR #19. |
| Uncommitted user work preserved | `Claude outputs/`, `docs/CampusHub-SRS.docx` (untracked, untouched); stash `sign-out-on-network-error fix` kept. |

### A.2 Baseline `44ccc2c` against the QA fixes

`git diff 44ccc2c 501372c -- backend frontend`: **23 files, +621 / −28**.

* Application code: **18 files, +291 / −27** (the report's "~270 lines" is in
  line with this).
* Tests: **5 files, +330 / −1**.
* Frontend: **no change** (QA-19, QA-22 untouched, as the report says).

| File | Role in the fixes |
|---|---|
| `app/db/locking.py` (new) | Row locks (`SELECT … FOR UPDATE`) for seat counters and caps — QA-01…QA-05, QA-23 |
| `app/core/hardening.py` (new) | API security headers, NUL-byte rejection — QA-11, QA-12 |
| `app/main.py` | Wires the hardening middleware; hides `/docs` in production — QA-12, QA-13 |
| `app/services/accounts.py`, `api/v1/auth.py` | Equal-time login and the sign-in limiter — QA-09, QA-10 |
| `api/v1/events.py`, `minors.py`/`services/minors.py`, `mentorship.py`, `electives.py`, `mooc.py`, `services/sections.py`, `services/internships.py` | Locked capacity checks and counters — QA-01…QA-05 |
| `api/v1/dashboard.py`, `services/faculty_scoring.py` | Query batching — QA-06…QA-08 |
| `api/v1/clubs.py`, `files.py` | Audit rows — QA-14 |
| `app/tests/test_pg_concurrency.py`, `test_query_counts.py`, `test_hardening.py`, `test_account_security.py`, `conftest.py` | Regression tests; `conftest.py` runs the suite on PostgreSQL when `CAMPUSHUB_TEST_DATABASE_URL` is set |

All of these files are present on `master` and unchanged since `9d6e54c`
(no later commit touches backend or frontend code).

### A.3 Compatibility with the current code

Phase B (itejas29, 22 Oct, commit `9d6e54c`, evidence in `phase_b/`):
SQLite 1,024 passed + 2 PostgreSQL-only skipped; PostgreSQL 16 1,026 passed;
frontend build passed; Playwright 15/15. That run includes the NPTEL / NCC
module merged on 18 Oct, so the fixes are compatible with the current code.
**These numbers are Phase B's evidence; they are re-run in Phase I.**

### A.4 Open findings checked against the code

| ID | What the code shows (24 Oct) |
|---|---|
| QA-15 | `mentor_assignments` is unique on `(student_id, academic_year_id)`. Two ways to two active mentors: a NULL year (NULLs never collide), and a new academic year — `assign_mentor` looks only for the current year's row, so last year's assignment stays active beside the new one. |
| QA-16 | `GET /internships/enrollments` loads every matching row, then filters the search text in Python. 53 list endpoints in `api/v1`; only audit logs, courses, announcements, events and notifications are bounded. A `Page[T]` schema and `page`/`page_size` pattern already exist (`schemas/common.py`, `admin.py`). |
| QA-17 | Not yet profiled in this cycle. |
| QA-18 | No request timeout or load shedding beyond the sign-in limiter. |
| QA-19 | Both `vercel.json` files hold only SPA rewrites; no headers. |
| QA-20 | CI (`deploy-backend.yml`) runs `pytest -q` on SQLite only; no PostgreSQL job, migration check, Playwright or dependency audit. |
| QA-21 | Not yet re-examined. |
| QA-22 | Not yet reproduced in this cycle. |

### A.5 Change plan

Each batch is a reviewable commit on `qa/remediation`, with its own tests, the
full backend suite re-run, and a PR for the owner to merge. Nothing is merged
or deployed without the owner's go-ahead, and nothing touches production data.

| Batch | Findings | Why this order | Needs owner decision |
|---|---|---|---|
| C1 | **QA-15** one active mentor per student (partial unique index + migration that reports, not deletes, existing duplicates; `assign_mentor` retires the old assignment) | Data integrity; a schema change | Confirm the rule: **one active faculty mentor per student, regardless of academic year** |
| C2 | **QA-16** pagination of the internship list (SQL-side search, stable order, bounded `page_size`, backward-compatible) and a review of the other student-returning lists | Unbounded payloads under load | — |
| C3 | **QA-20** PostgreSQL CI job: clean migrations, full suite on PostgreSQL 16, concurrency tests, JUnit artifacts | Protects every later batch on PostgreSQL | — |
| C4 | **QA-22** chatbot button on phones, with a Playwright layout test | Low risk, visible in demos | — |
| C5 | **QA-19** frontend security headers — Report-Only CSP first | Changes the live site's headers | **Approval before merge**; check on a Vercel preview first |
| C6 | **QA-17** faculty-score recomputation; **QA-18** timeouts / overload; **QA-21** server defaults | Lower severity; QA-18 is partly infrastructure | QA-18 limits (worker count, pool size) |

Phases D–I (re-verifying QA-01…QA-23, wider regression tests, staging load
tests, operational readiness, CI release gates, the release decision) follow
Phase C. Staging load tests (Phase F) and backups/monitoring (Phase G) need an
isolated staging environment, which does not exist yet: those items are
**BLOCKED** until the owner provides one.
