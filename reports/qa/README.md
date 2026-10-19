# CampusHub QA — 19 October 2026

Start with **`CampusHub_QA_Report.pdf`** — every report below in one document (27 pages).
Rebuild it with `python tools/build_pdf.py && node tools/render_pdf.mjs .` from this folder.

| File | What it is |
|---|---|
| `CampusHub_QA_Executive_Report.md` | Scope, results, recommendation |
| `CampusHub_Test_Case_Matrix.csv` | Executed tests per module, SQLite and PostgreSQL |
| `CampusHub_Load_Test_Report.md` | Query profiles, load, spike, recovery, race conditions |
| `CampusHub_Security_Report.md` | Authorisation sweeps, token, injection, timing, headers |
| `CampusHub_Defect_Register.csv` | Every finding: root cause, evidence, fix, regression test, status |
| `CampusHub_Production_Readiness_Checklist.md` | What is done, open, or blocked |
| `qa_summary.json` | Machine-readable summary |
| `evidence/` | Logs, JUnit XML, probe outputs, load runs (sanitised: no tokens, no real data) |
| `tools/` | Every harness used — they refuse production URLs |

Run the backend suite on PostgreSQL (use a database that holds nothing else):

```bash
cd backend
CAMPUSHUB_TEST_DATABASE_URL=postgresql://<user>:<password>@localhost:55432/<db> ../.venv/bin/pytest -q
```

The race, security and load tools target an isolated server (`QA_BASE_URL`, default
`http://127.0.0.1:8201/api/v1`) and a disposable Dockerised PostgreSQL (`QA_PG_CONTAINER`,
`QA_PG_DB`). See the load report §7 for the full setup.
