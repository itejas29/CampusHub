---
name: campushub-qa
description: "CampusHub-specific testing, security-audit and load-test conventions — which tools to run, where results go, and which systems must never be touched. Load this alongside the rigorous-engineering skill (same three tiers: per-change tests, per-feature adversarial audit, pre-release full regression/security/load) whenever working in this repo. Reach for it for 'run the tests', 'QA pass', 'security audit', 'load test', 'is this ready to deploy' on CampusHub."
---

# CampusHub QA — project specifics

This fills in *how* for this repo. The tiers, the report-before-fix rule, and
the "never fabricate a result" discipline all come from the `rigorous-engineering`
skill — read that first if it isn't already loaded. This file only covers
what's specific to CampusHub: which commands, which databases, which systems
are off-limits.

## Hard boundaries — these override everything else

- **Never** run load tests, destructive security probes, or failure-injection
  against production (`campushub-production-f100.up.railway.app`) or the
  Vercel frontend. All of that runs against a local/staging stack.
- **Never** modify the live Railway PostgreSQL database, production env vars,
  or real student records without the user's explicit, in-the-moment
  approval — a past approval doesn't carry forward.
- **Never** push to `master` as a way of "finishing" QA work. `master` auto-
  deploys backend (Railway, via `.github/workflows/deploy-backend.yml`) and
  frontend (Vercel) on push. Land QA/report work on a branch and let the user
  decide when (or whether) to merge it.
- Real students get no fabricated test activity (`demo_students` in
  `seed/run.py` excludes them already — don't work around that).
- Don't invent university policy to fill a gap in a test; flag the gap
  instead (see `CLAUDE.md`'s "Before you claim something works").

## Tier 1 — every change

```bash
cd backend && ../.venv/bin/pytest -q          # backend, SQLite (default, fast)
cd frontend && npm run build                  # tsc -b && vite build
```

Add/update tests under `backend/app/tests/` (named for the behaviour, per
`CLAUDE.md` conventions) or the relevant frontend test. Run the full backend
suite, not just the new test file — it's fast enough that there's no excuse.

## Tier 2 — a completed feature

The adversarial pass can reuse the probes in `reports/qa/tools/` rather than
writing new ones from scratch:

- `security_probe.py` — unauthenticated access, permission bypass as a
  student, token tampering, injection strings in search, oversized/nested
  payloads, response headers.
- `horizontal_probe.py` — cross-scope/cross-student access pattern (model a
  new feature's probe on this one: victim + several wrong-scope attackers,
  reads and writes, asserting refusal).
- `query_profile.py` — N+1 / query-count regressions (PostgreSQL only; see
  below).
- `race_*.py` (in the same folder) — concurrent-request races against a
  capacity or uniqueness constraint.

These run against the **isolated QA stack**, never production:

```bash
docker start campushub-qa-pg       # local PostgreSQL 16, port 55432
                                    # databases: campushub_qa (demo-sized),
                                    # campushub_qa_10k (scale test),
                                    # campushub_pytest (disposable — dropped
                                    # and rebuilt by the test suite itself)
```

Report findings the way `rigorous-engineering` tier 2 specifies — do not fix
anything in this pass. Findings this project already tracks by number
(QA-1, QA-2, …) belong in the same numbering if they extend the 19 Oct 2026
QA report; a genuinely new finding gets its own short name.

## Tier 3 — before a release

- **Full regression**, both databases:
  ```bash
  cd backend && ../.venv/bin/pytest -q --junitxml=../reports/qa/<run>/backend_sqlite_junit.xml
  CAMPUSHUB_TEST_DATABASE_URL="postgresql://qa:<pw>@localhost:55432/campushub_pytest" \
    ../.venv/bin/pytest -q --junitxml=../reports/qa/<run>/backend_pg_junit.xml
  cd frontend && npm run build && npm run test:e2e
  ```
  `npm run test:e2e` brings up its own seeded SQLite API (:8100) and Vite
  (:5180) — it doesn't touch the Docker Postgres or anything live.
- **Security audit**: the probes above, plus `reports/qa/tools/build_matrix.py`
  to fold JUnit + probe results into `CampusHub_Test_Case_Matrix.csv`, and
  `build_pdf.py` if a formal report is wanted.
- **Load test**: `reports/qa/tools/loadtest.py` and `scale_dataset.sql` (loads
  `campushub_qa_10k` to a realistic size first). Run against the local/staging
  stack only — see the hard boundaries above. Report real p50/p95/p99,
  throughput, and error rate; don't round up to "handles 1,000 users" if the
  environment only supports a smaller verified number.
- Put run output under `reports/qa/<dated-folder>/`, matching the layout
  already in `reports/qa/` (a `README.md` summary + the raw logs/JUnit/CSV
  the summary cites) — this repo already has the convention, reuse it rather
  than inventing a new report format per run.
- Known still-open findings as of the 19 Oct 2026 QA report: QA-15 through
  QA-22 (see `docs/PHASE4-REPORT.md` and the defect register CSV in
  `reports/qa/`). Check whether a release candidate has addressed them before
  calling a release ready; don't re-discover them from scratch each time.

## Reseeding

A reseed (`docker compose exec backend python -m app.seed.run --reset`)
wipes anything added by hand. Fine for the local/QA stack; needs explicit
user approval if it would ever target anything connected to live data.
