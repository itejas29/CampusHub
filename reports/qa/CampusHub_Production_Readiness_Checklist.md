# CampusHub — Production Readiness Checklist

Status as of 19 Oct 2026, after this QA cycle. ✅ verified in this cycle · 🟡 partly / conditions ·
❌ not done · ⛔ blocked (needs a decision, data or access the team does not have).
Evidence references point into `reports/qa/`.

## Functional correctness
| Item | Status | Evidence / note |
|---|---|---|
| Full backend suite passes (SQLite) | ✅ | 1,026 tests, 0 failed (2 PostgreSQL-only skipped) |
| Full backend suite passes on **PostgreSQL** | ✅ | 1,026 tests, 0 failed — first time ever run on PostgreSQL |
| Frontend type-check and production build | ✅ | `tsc -b`, `vite build` |
| Browser end-to-end journeys | ✅ | Playwright 15/15 (sign in → allocate → review; CSSI windows; roles; tools) |
| Every page loads for every role without errors | ✅ | 200 pages (desktop, 16 accounts) + 67 pages at 390 px (4 roles) |
| Summer Internship coordinator ↔ student ↔ mentor journey | ✅ | 12-step side-by-side run (window → notify → validated registration → mentor → upload → one-click approval) |
| Academic policy regressions (OE 40/75 & splits, Core combined minimum, CPI only for Minor, Minor 7.5/0/75, batch-scoped curriculum) | ✅ | Existing suites `test_sections`, `test_allocation`, `test_minor_ranking`, `test_curriculum_versioning`, `test_eligibility` — all pass on both databases |
| Policies still marked *requires faculty confirmation* (mentor cap 10, stages, rubrics, score weights, Minor Project credits) | ⛔ | Needs the department; the portal flags them, does not invent them |

## Data integrity
| Item | Status | Evidence / note |
|---|---|---|
| Duplicate submissions cannot create duplicates | ✅ | RACE-3, RACE-4, RACE-5; unique constraints verified on PostgreSQL |
| Capacity limits hold under simultaneous requests | ✅ | RACE-1, -2, -6 fixed with row locks; `test_pg_concurrency.py` |
| Seat counters stay exact | ✅ | RACE-5, RACE-6 |
| Migrations: clean install, full downgrade/upgrade, repeat | ✅ | `evidence/pg_migrate_*.txt` (18 migrations) |
| Schema vs models | 🟡 | Only server-default differences (QA-21) |
| Duplicate active mentor assignment when `academic_year_id` is NULL | ❌ | QA-15 — add a partial unique index |
| Every mutation audited | ✅ | Static scan of 137 write routes; 6 documented exceptions |

## Security
| Item | Status | Evidence / note |
|---|---|---|
| Authorisation sweep (anonymous, student, cross-student, cross-department, cross-domain) | ✅ | SEC-1, -2, -7, -8 |
| Token tampering, session revocation, throttling, password policy, one-time passwords | ✅ | SEC-3; `test_account_security.py` |
| Login enumeration by timing | ✅ | QA-09 fixed (gap 215 → 5 ms) |
| API security headers; NUL bytes; docs hidden in production | ✅ | QA-11, -12, -13 |
| Frontend security headers / CSP | ❌ | QA-19 |
| Upload malware scanning | ❌ | No scanner integrated |
| Dependency audit (pip-audit / npm audit) | ❌ | Not run in this cycle |
| Demo accounts off (`DEMO_MODE=false`), `SEED_ON_START=false`, real `SECRET_KEY` | ⛔ | Mechanisms exist and were tested locally; switching them needs a clean production database with real accounts |

## Performance & capacity
| Item | Status | Evidence / note |
|---|---|---|
| No N+1 on main lists at 10,000 students | ✅ | Query profile; `test_query_counts.py` |
| Sustained moderate load (50 aggressive users, 5 min) | ✅ | p95 366 ms, 0.007% errors, memory stable |
| Burst of a whole cohort signing in at once | 🟡 | Mitigated (QA-10) but one process saturates; spike still 28% failures for the burst |
| Agreed service-level objective | ❌ | Proposed in the load report; needs owner approval |
| Lists paginated | ❌ | QA-16 |
| Measured on the real hosting | ⛔ | No staging copy of Railway exists |

## Operations
| Item | Status | Evidence / note |
|---|---|---|
| Health check | ✅ | `/health` (used by Railway) |
| Database backups configured and a restore tested | ⛔ | Not visible from the repository; owner must enable on Railway and rehearse a restore |
| Monitoring and alerting (errors, latency, failed sign-ins, DB connections) | ❌ | None |
| Request timeouts / load shedding | ❌ | QA-18 |
| Multiple workers with connection pooling | ❌ | 4 workers need 131 connections; needs PgBouncer or smaller pools |
| Email service (password reset, notifications) | ⛔ | Needs provider credentials |
| CI runs PostgreSQL and migrations | ❌ | QA-20 — supported now via `CAMPUSHUB_TEST_DATABASE_URL`; add a CI job |

## Governance & privacy
| Item | Status | Evidence / note |
|---|---|---|
| University approval to hold student data (DPDP Act 2023), hosting location, retention | ⛔ | Needs PDEU |
| Clean production database with real records only | ⛔ | Needs real emails, roster, confirmed coordinators |
| Named owner for support after the project team | ⛔ | Needs PDEU |
