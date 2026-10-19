# CampusHub — QA, Production Readiness and Stress Testing: Executive Report

**Testing performed:** 19 October 2026 · **Code under test:** `master` @ `44ccc2c` (baseline) →
branch `qa-mission` (fixes, not merged, not deployed) · **Environment:** local, isolated
(details in §A). Production was not touched: no deploys, no live data changes, no load or
security tests against Railway or Vercel.

## A. Executive summary

**Scope.** Every API route (237, of which 137 write data), the full backend test suite on
SQLite **and for the first time on PostgreSQL**, database migrations, browser journeys,
concurrency on the operations that hand out limited places, authorisation across all roles,
and load from 5 to 250 aggressive virtual users on a 10,000-student synthetic dataset.

**Environment.** Apple M2 (8 cores, 8 GB); PostgreSQL 16 in Docker; API run exactly as
production runs it (one uvicorn process, pool 10 + 20). Synthetic data only — the private
real-student lists were excluded from every QA database.

**Overall status: CONDITIONAL PASS.** The functional and security behaviour holds; seven
confirmed defects that mattered (one high-severity data-integrity race, two medium races,
one high and two medium performance problems, one medium security leak) were reproduced, fixed
and verified with regression evidence. What keeps this from a full pass is operational, not
functional: one process saturates around 50–100 very active users, there are no backups
verified, no monitoring, and university-level approvals and real-data setup are outstanding.

**Recommendation: READY FOR CONTROLLED PILOT** (one department, supervised, after the
`qa-mission` fixes are merged and deployed). **Not yet ready for university-wide production.**

**Critical blockers for production** (detail in the readiness checklist):
1. Database backups enabled on the hosting and one restore rehearsed.
2. Monitoring/alerting (errors, latency, failed sign-ins, DB connections).
3. Capacity for a whole-cohort burst: multiple workers with connection pooling (PgBouncer),
   re-measured on a staging copy of the real hosting against an agreed SLO.
4. Clean production database with real accounts, `DEMO_MODE=false`, `SEED_ON_START=false`.
5. PDEU approval for holding student data (DPDP Act 2023) and confirmation of the policies the
   portal flags as *requires faculty confirmation*.

## B. Test execution summary

| Suite | Baseline (before fixes) | Final (after fixes) |
|---|---|---|
| Backend, SQLite | 1,017 run · 1,017 passed · 0 failed · 0 skipped · 384 s | **1,026 run · 1,024 passed · 0 failed · 2 skipped** (PostgreSQL-only) · 367 s |
| Backend, PostgreSQL 16 | 1,017 run · 1,017 passed (first ever PostgreSQL run) · 422 s | **1,026 run · 1,026 passed · 0 failed · 0 skipped** · 424 s |
| Frontend type-check + build | pass (7.7 s + 8.3 s) | **pass** |
| Browser E2E (Playwright, isolated SQLite API) | 15 passed (2.1 min) | **15 passed** (2.0 min) |
| Page crawl, all roles (desktop) | Run earlier the same day in the demo pass (200 pages, 16 accounts); its 5 issues were fixed in `8656bb2`, which is part of this baseline | not repeated at desktop width in this cycle |

| Page crawl at 390 px + basic accessibility | — | **67 pages, 4 roles: 0 overflow, 0 script errors, 0 unlabelled controls/inputs/images** |
| Migrations on PostgreSQL | — | clean install ✓, downgrade to base and back ✓, repeat no-op ✓ |
| Race-condition probes (6) | **3 FAIL** (RACE-1, -2, -6), 1 intermittent 500 (RACE-4), 2 pass | **6/6 PASS** |
| Security probes (SEC-1..9) | **3 FAIL** (SEC-4 NUL, SEC-6 headers, SEC-9 timing) | **all PASS** (frontend headers open) |
| Load (see load report) | 250-VU burst: 90% failed, 153 s recovery | 28% failed, 88 s recovery; steady 50 VU p95 0.37–0.61 s, 0 server errors |

New automated tests added this cycle: `test_pg_concurrency.py` (2, PostgreSQL), `test_query_counts.py`
(2), `test_hardening.py` (3), 3 in `test_account_security.py`. Each fix-guarding test was shown to
**fail with the fix removed** where noted in the defect register. Coverage percentages were not
collected (no coverage tool in the environment).

## C. Module coverage matrix

Full per-module counts (both databases) are in `CampusHub_Test_Case_Matrix.csv`. Summary:

| Module | Automated tests (each DB) | DB integration | Concurrency | Status |
|---|---:|---|---|---|
| Authentication, sessions, accounts | 54 | SQLite + PostgreSQL | sign-in bursts (load) | PASS |
| Authorisation & scope | 117 + SEC sweeps (230 / 92 routes) | both | — | PASS |
| Curriculum (data-driven, batch-scoped) | 212 | both | — | PASS |
| Electives (rounds, preferences, allocation, sections) | 209 | both | RACE-4, RACE-5 | PASS |
| NPTEL / NCC | 35 | both | — | PASS |
| Minor specialisation | 20 | both | **RACE-6 (fixed)** | PASS |
| Internship engine (CSSI, Summer, projects) | 96 | both | **RACE-2 (fixed)**, RACE-3 | PASS |
| Mentor allocation & mentoring | 33 | both | query profile | PASS |
| Faculty performance score | 25 | both | query profile | PASS |
| Uploads / documents / progress | 62 | both | — | PASS |
| Input validation & CSV safety | 39 | both | — | PASS |
| Dashboards, profiles, announcements, chatbot | 63 | both | load journeys | PASS |
| Events & clubs | in cross-module + security | both | **RACE-1 (fixed)** | PASS |
| Cross-module journeys | 57 | both | — | PASS |

**Gaps (honest):** no new Playwright specs were written per module this cycle — UI coverage is
the existing 15 journeys plus the all-role crawls; RACE-2 and RACE-4 are guarded by scripts, not
pytest; keyboard-only navigation and colour contrast were not tested; dependency audits were not
run.

## D. Performance results (headline)

- **N+1 found and fixed:** mentee list 4,676 → 24 queries (4.3 s → 0.25 s at ~1,900 mentees);
  faculty score 276 → 19; Mentorship coordinator dashboard 303 → 52 ms. Lists now hold a fixed
  query count as data grows (regression tests).
- **Steady load, one process, 10k students:** 50 aggressive VUs for 5 minutes — 14,249 requests,
  43 req/s, p50 42 ms, p95 366 ms, p99 707 ms, 0.007% errors, memory stable.
- **Saturation:** between 50 and 100 aggressive VUs (~40–55 req/s). 4 workers gave 4× the work
  but needed 131 DB connections.
- **Burst:** 200 sign-ins in 5 s — failures cut from 90% to 28% and recovery from 153 s to 88 s by
  queuing sign-ins; the rest needs more processes/CPU (infrastructure).

## E. Security findings (headline)

No authorisation bypass in 230 anonymous probes, 92 student-vs-guarded probes, 44 cross-scope
probes, token forgery and mass assignment. Fixed: login timing enumeration (Medium), missing API
security headers (Medium), NUL-byte 500s (Low), public API docs in production (Low). Open: frontend
security headers/CSP (Medium), malware scanning, dependency audit, non-login rate limits.

## F. Defect register (summary)

23 entries in `CampusHub_Defect_Register.csv`:
- **13 fixed** — 10 verified by reproducing before and after (QA-01, -02, -03, -04, -06, -07,
  -08, -09, -11, and QA-23, a regression introduced during QA and fixed); QA-12 verified for the
  API (frontend part is QA-19); QA-13 and QA-14 fixed and confirmed by inspection / static scan.
- **1 fixed preventively** (QA-05, same pattern, not reproduced) · **1 mitigated** (QA-10, capacity).
- **7 open** — mentor-assignment NULL uniqueness (QA-15), pagination (QA-16), score
  recomputation (QA-17), request timeouts (QA-18), frontend headers (QA-19), PostgreSQL in CI
  (QA-20), chatbot button overlap on phones (QA-22).
- **1 informational** (QA-21).

Code changed (branch `qa-mission`, 18 modified + 5 new backend files, ~270 lines): row locks for
limits (`app/db/locking.py`), request hardening (`app/core/hardening.py`), sign-in queue and
timing fix, N+1 fixes, audit gaps, opt-in PostgreSQL test fixture, fully synthetic seed switch.

## G. Production-readiness checklist

See `CampusHub_Production_Readiness_Checklist.md`.

## H. Final recommendation

**READY FOR CONTROLLED PILOT** — subject to merging and deploying the `qa-mission` fixes, which
close real data-integrity and security defects present in production today (Minor and event
oversubscription, mentor cap, login enumeration).

A passing suite is not production readiness. Before university-wide use: backups with a tested
restore, monitoring, capacity for cohort bursts measured on the real hosting, a clean real-data
database with demo accounts off, and PDEU's approvals.

## Evidence index

`reports/qa/evidence/` — test logs and JUnit XML (baseline and final, both databases), migration
logs, `api_routes.csv` (route inventory), race-test outputs (`race*`), security probe outputs
(`security_*`), query profiles (`query_profile_*`), load runs (`load/*.json`), mobile crawl.
`reports/qa/tools/` — every probe, harness and dataset script used (all refuse production URLs).
Screenshots containing synthetic data are kept outside the repository.
