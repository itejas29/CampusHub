# CampusHub — Load, Concurrency and Database Performance Report

Every number below was measured during this QA cycle (19 Oct 2026). Raw output is in
`reports/qa/evidence/load/*.json`, `evidence/query_profile_*.json` and `evidence/race*`;
the tools that produced them are in `reports/qa/tools/`. Nothing here was run against
production.

## 1. Environment

| Item | Value |
|---|---|
| Host | Apple M2, 8 cores, 8 GB RAM (one laptop runs the API, PostgreSQL **and** the load generator — numbers are conservative and CPU-contended) |
| Database | PostgreSQL 16.15 in Docker (`postgres:16-alpine`, `max_connections=200`, `shared_buffers=256MB`), 4 GB / 8 vCPU Docker VM |
| API | uvicorn, **one process** — the production `Dockerfile` command (`uvicorn app.main:app`, no `--workers`). SQLAlchemy pool 10 + 20 overflow (production setting). One comparison run with `--workers 4`. |
| Dataset | Demo seed with private real-student lists excluded (`CAMPUSHUB_SEED_SKIP_PRIVATE=1`), scaled with `tools/scale_dataset.sql` to **10,000 students**, 9,334 mentor assignments, 2,699 internship enrolments, 21,574 stage-progress rows. All synthetic. A 1,685-student copy was kept for comparisons. |
| Load generator | `tools/loadtest.py` (Python asyncio + httpx; no load tool was installed). Each virtual user (VU) signs in once, then loops realistic journeys with an exponential think time (mean 1 s). Mix: 85% students, 10% mentors, 4% coordinators, 1% registrar; ~8% of student iterations write (elective preferences, event registration). |

**How to read VU counts.** A VU waits ~1 s between actions; a real student waits 10–30 s.
So 100 VUs here generate the load of very roughly 500–1,500 people *actively clicking at the
same moment* — not 100 students. No service-level objective has been agreed; the figures are
measurements, not a pass/fail against a target (see §6 for a proposed one).

## 2. Database query profile (PostgreSQL, in-process)

Measured with `tools/query_profile.py` at 1,685 and 10,000 students. An endpoint whose query
count grows with the data has an N+1.

| Endpoint | Queries 1.7k | Queries 10k | ms 10k | Outcome |
|---|---:|---:|---:|---|
| `GET /mentorship/my-mentees` (mentor with ~1,900 mentees) | 518 | **4,676** | **4,325** | **N+1 — fixed: 24 queries, 255 ms** (QA-06) |
| `GET /dashboard/faculty` (Mentorship coordinator) | 52 | 52 | **303** | Loaded every assignment to count — **fixed: 52 ms** (QA-07) |
| `GET /faculty-scores/me` | 276 | 276 | 386 | Per-item lazy loads — **fixed: 19 queries** (~240 ms remains, QA-17) |
| `GET /faculty-scores/department` | 349 | 349 | 421 | **fixed: 78 queries** |
| `GET /internships/enrollments` (2,699 rows) | 59 | 71 | 987 | Fixed query count, but **unpaginated: 1.45 MB** (QA-16, open) |
| Student dashboard / notifications / events / announcements | 4–45 | same | 8–49 | Constant — OK |
| `GET /students?page=1&size=50`, `/dashboard/admin`, `/dashboard/hod` | 31–57 | same | 34–36 | Constant — OK |

Earlier in this cycle the internship list itself was fixed from **6,243 queries for 683 rows to
24** (`documents.progress_many`); it now stays constant as rows grow (regression test
`test_query_counts.py`).

Schema: 46 foreign-key columns have no index (`evidence/pg_unindexed_foreign_keys.txt`). The
timing analysis showed none of them on a hot path today (they are "who did this" columns);
they matter for deletes of referenced rows and future filters. No lock waits or deadlocks
were observed in any run (`pg_lock_waits_max` 0–1).

## 3. Load results

Builds: **A** = race-condition and N+1 fixes; **B** = A + faculty-score fix + DB connection
released during password hashing; **C** = B + thread semaphore on hashing; **D (final)** = B +
sign-ins queued in the event loop. "5xx/timeout %" counts server errors and 30 s client
timeouts; "4xx" are expected business refusals (already registered 409, preference rules 422,
a coordinator persona opening a screen that is not theirs 403).

| Run | Build | VUs | Ramp / duration | Requests | RPS | p50 | p95 | p99 | 5xx/timeout | CPU max | PG conns |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| smoke-5 | A | 5 | 5 s / 30 s | 170 | 4.0 | 46 ms | 353 ms | 446 ms | 0% | 56% | 5 |
| ramp-10 | A | 10 | 10 s / 60 s | 676 | 8.6 | 31 ms | 137 ms | 297 ms | 0% | 78% | 6 |
| ramp-25 | A | 25 | 10 s / 60 s | 1,546 | 20.7 | 32 ms | 236 ms | 462 ms | 0% | 93% | 10 |
| ramp-50 | A | 50 | 10 s / 60 s | 2,976 | 37.9 | 78 ms | 483 ms | 1.8 s | 0% | 215% | 23 |
| ramp-100 | A | 100 | 10 s / 60 s | 4,251 | 53.6 | 445 ms | 1.4 s | 5.2 s | 0% | 379% | 31 |
| ramp-250 | A | 250 | 10 s / 60 s | 718 | 3.7 | 30 s | 30 s | 30 s | **71%** | 571% | 31 (pool cap) |
| stress-250-original | original | 250 | 10 s / 60 s | 624 | 3.3 | 30 s | 30 s | 30 s | **76%** | 551% | 32 |
| stress-250 | B | 250 | 10 s / 60 s | 638 | 3.8 | 30 s | 30 s | 30 s | **75%** | 504% | 31 |
| stress-250 slow arrival | B | 250 | 120 s / 120 s | 3,635 | 10.6 | 489 ms | 30 s | 30 s | **27%** | 535% | 31 |
| stress-250 slow arrival, **4 workers** | B | 250 | 120 s / 120 s | 15,135 | 55.7 | 453 ms | 6.3 s | 31 s | 3% | — | **131** |
| **sustained 5 min** | B | 50 | 15 s / 300 s | 14,249 | 43.4 | 42 ms | 366 ms | 707 ms | **0.007%** (1 reset) | 144% | 30 |
| **final-50** | **D** | 50 | 10 s / 60 s | 2,891 | 37.7 | 110 ms | 613 ms | 1.2 s | **0%** | 208% | 21 |
| **final-100** | **D** | 100 | 10 s / 60 s | 4,083 | 51.7 | 545 ms | 1.8 s | 3.2 s | **0%** | 293% | 31 |

Final build vs build A at the same load: no meaningful steady-state change (50 VU p95 483 → 613 ms,
100 VU p95 1.4 → 1.8 s but p99 5.2 → 3.2 s) — within the run-to-run noise of a shared laptop. At
100 VU, sign-in p95 is 3.9 s because sign-ins now queue instead of starving other requests; the
gain of build D is under bursts (spike table below), not in steady state.

Sustained run: memory stable (RSS 156 → 120 MB, max 269 MB) — no leak; 184 event registrations
and 65 preference lists saved with no integrity errors.

### Spike and recovery (20 steady users; 200 more arrive in 5 s for 40 s)

| | Build B (before) | Build C (semaphore) | **Build D (final)** |
|---|---:|---:|---:|
| Spike users: requests completed | 273 | 314 | **1,174** |
| Spike users: 5xx/timeouts | 90% | 84% | **28%** |
| Steady users: 5xx/timeouts | 11.5% | 10.7% | **7.6%** |
| Time to recover after the spike | 153 s | 118 s | **88 s** |

## 4. Findings

1. **Capacity of one process is the ceiling (QA-10, partly mitigated).** Saturation begins
   between 50 and 100 aggressive VUs (~40–55 requests/s). Above that, requests queue for the
   40 worker threads and the 30-connection pool and time out after 30 s.
2. **Sign-in bursts were the worst case.** bcrypt (~0.25 s CPU) ran unbounded and held a
   database connection; 250 sign-ins in 10 s took >5 cores. Fixed: the connection is released
   before hashing and sign-ins queue in the event loop (≤ cores/2 at once, 503 after 15 s).
3. **Scaling out works.** Four workers completed 4× the requests with 3% errors — but opened
   **131 PostgreSQL connections**. Managed PostgreSQL plans often allow ~100: more workers
   need a smaller per-worker pool or a pooler (PgBouncer).
4. **Recovery is slow (QA-18).** There is no server-side request timeout or load shedding;
   work for clients that already gave up is still done, so recovery took 88–153 s.
5. **No integrity loss under load.** No duplicate registrations, no oversubscription, no lock
   waits/deadlocks in any run after the race fixes (§5).

## 5. Concurrency and race conditions (PostgreSQL, real concurrent requests)

| Test | Scenario | Before | After |
|---|---|---|---|
| RACE-1 | 40 students register at once for an event with 5 places | **9/10 trials oversubscribed (7–9 confirmed)** | 10/10 exactly 5 |
| RACE-2 | Coordinator assigns 15 students to a mentor capped at 10, at once | **8/8 trials over cap (13–15)** | 6/6 exactly 10 + 5 × 409 |
| RACE-3 | Same student clicks Register 10× | 1 enrolment, 9 × 409, no 5xx — PASS | PASS |
| RACE-4 | Same student submits 2 different preference lists 4× at once | data correct; **2/30 trials returned a 500** | 30/30, 120 × 200 |
| RACE-5 | Coordinator triggers the same real allocation run 3× | 1 run, 2 × 409; no double seats; counters exact — PASS | PASS |
| RACE-6 | 10 Minor allocations at once, 3 seats free | **6/6: 11 enrolled vs capacity 4; counter lost 9 updates** | 6/6 exactly 3 + 7 × 409; counter exact |

Permanent regression tests (PostgreSQL only): `app/tests/test_pg_concurrency.py` — both verified
to **fail** with the lock removed and pass with it.

## 6. Limitations and proposed objective

- Single laptop; load generator competes with the API and database for CPU. Railway's CPU,
  network latency and connection limits were **not** measured (no staging environment exists;
  production load testing was out of scope and not authorised).
- Think time of 1 s over-represents activity per user; 500 and 1,000 VU runs were not attempted
  because 250 already saturated this host.
- **Proposed SLO for owner approval:** at the expected peak (e.g. one cohort of ~250 students
  signing in within 2 minutes and filling preferences within 10 minutes), p95 < 1 s for page
  loads, p95 < 2 s for sign-in, < 0.5% server errors. On one process this is **not** met for a
  250-user burst; it needs multiple workers with a pooler, or a larger instance — to be
  re-measured on a staging copy of the real hosting.

## 7. Reproduce

```bash
docker run -d --name campushub-qa-pg -e POSTGRES_USER=qa -e POSTGRES_PASSWORD=<choose-one> \
  -e POSTGRES_DB=campushub_qa -p 127.0.0.1:55432:5432 postgres:16-alpine -c max_connections=200
cd backend
DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:55432/campushub_qa ../.venv/bin/alembic upgrade head
DATABASE_URL=… CAMPUSHUB_SEED_SKIP_PRIVATE=1 ../.venv/bin/python -m app.seed.run
# 10k copy: createdb -T campushub_qa campushub_qa_10k; psql … < ../reports/qa/tools/scale_dataset.sql
DATABASE_URL=…/campushub_qa_10k ../.venv/bin/uvicorn app.main:app --port 8201
cd ../reports/qa/tools && ../../../.venv/bin/python loadtest.py --users 50 --duration 300 --think 1 --label sustained
```
