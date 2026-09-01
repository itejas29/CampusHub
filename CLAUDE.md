# CampusHub — context for Claude Code

PDEU centralised student portal. FastAPI + React/TypeScript + PostgreSQL.

**Read this before changing anything.** Several rules here look like details and
are actually load-bearing university policy; a "tidy-up" that flattens them
breaks the thing the portal exists to do.

---

## Commands

```bash
make up          # build + start the whole stack (Docker)
make reset-db    # rebuild schema + reseed
make seed        # load demo data
make test        # backend tests            (or: cd backend && pytest -q)
make migrate     # alembic upgrade head
make revision    # autogenerate a migration

cd frontend && npm run dev     # vite dev server
cd frontend && npm run build   # tsc -b && vite build
```

Demo password for every seeded account: `Campus@123`.
Accounts are listed in [README.md](README.md#demo-accounts).

### iCloud, and why builds fail here

The project sits in an iCloud-synced `~/Desktop` folder. iCloud **evicts** file
contents to save space, leaving zero-byte "dataless" placeholders. Reading one
triggers a download, and for a directory of thousands of small files that
download times out:

```
[plugin:vite:css] Failed to load PostCSS config:
Error: Loading PostCSS Plugin failed: ETIMEDOUT: connection timed out, read
```

That error is not a PostCSS problem. It means `node_modules` was evicted.

**`frontend/node_modules` is therefore a symlink** to
`~/.campushub-modules/frontend`, outside the synced tree, where iCloud cannot
touch it. Run `npm ci` normally — it installs through the symlink. If the
symlink is ever lost, recreate it before installing:

```bash
cd frontend
rm -rf node_modules
mkdir -p ~/.campushub-modules/frontend
ln -s ~/.campushub-modules/frontend node_modules
npm ci
```

`backend/.venv` has the same disease and has not been moved — it is why Python
commands here take minutes. The same treatment fixes it, or recreate the venv
outside the synced tree. Either way: **run long commands in the background
rather than assuming they hung.**

---

## The four ideas the design rests on

### 1. The curriculum is data, not code

A programme's structure lives in `curriculum_components` rows. Never write:

```python
if student.department == "ICT" and student.semester == 4:   # NO
```

Ten B.Tech programmes are modelled and they genuinely differ — Mechanical
distributes Program Electives 1/1/3 where ICT does 1/2/2, CSBS prescribes its
Open Electives by name, Petroleum runs a Rural Internship instead of CSSI. If a
change requires a per-programme branch, the model is wrong, not the programme.

### 2. The admission batch is part of the key

Curriculum versions are scoped to a range of admission years. Two ECE students
in the same lecture hall can be governed by different structures — the 2020-24
scheme has **no NPTEL component at all**.

Resolution goes through `services/curriculum.resolve_curriculum()`, which uses
`Curriculum.governs_batch()`. Never `student.department + semester`.

### 3. One internship engine

CSSI, Rural Internship, Industrial Training and Summer Internship are all rows
in `internship_programs` differing only in configuration — stages, group size,
report cadence, evaluation rubric. They share every route, service and screen.
Adding a variant means inserting a row, never a new code path.

### 4. Policy is pluggable, and unconfirmed policy stays unconfirmed

Allocation strategies implement a documented interface (`services/allocation/`).
Curriculum components whose official source was ambiguous carry
`REQUIRES_FACULTY_CONFIRMATION`, and a curriculum **cannot be published** while
any remain.

---

## Rules that must not be "simplified"

These were verified against official PDEU documents. Changing one silently
changes university policy.

| Rule | Value | Where |
|---|---|---|
| Open Elective minimum to run | **40** | `services/sections.py` |
| Open Elective section capacity | **75 per section**, not course-wide | `services/sections.py` |
| Open Elective 90 / 150 / 151 | `[75,15]` / `[75,75]` / `[75,75,1]` | `test_sections.py` |
| Core Elective minimum | **40 combined across divisions**, never per division | `services/sections.py` |
| Core Elective ceiling | **none** — one combined class however large | `services/sections.py` |
| CSSI window | Sem I hidden · II announced · III active · IV+ concluded | `services/internships.py` |
| Summer Internship rubric | 25 + 25 + 25 + 25 = 100 | seeded `EvaluationCriteria` |
| Minor eligibility | CPI ≥ 7.5, 0 backlogs, 75 seats, from Sem III | `MinorProgram` rows |

### CPI belongs to Minor Specialisation and nowhere else

**CPI/CGPA is never an input to elective allocation.** Viability is a headcount
question; capacity is a room question. Academic merit governs Minor eligibility
and ranking only — and that is official policy (Academic Rules, Annexure II),
not an assumption. Tests assert zero CPI references in the elective path.

### Divisions are programme data

Not A/B/C/D. `program_divisions` is keyed on programme × admission batch:
Computer Engineering runs four, ICT three, CSBS one. No divisions configured
means "no division restriction", never a fallback to four.

---

## Security invariants

Phase 4 closed two real vulnerabilities. Do not undo them.

1. **Uploads are never served as static files.** They used to be, at `/media`,
   which made every stored document readable by anyone who guessed its object
   key — no login. Documents reach clients only via
   `GET /api/v1/files/{id}/download`, which authorises first.
2. **A storage key never crosses the API boundary.** The only URL returned is a
   short-lived HMAC-signed link back to the API (`services/files.signed_url`).
   In production, `S3_PUBLIC_BASE_URL` must stay **empty** for the documents
   bucket — setting it re-opens the hole.
3. **File metadata is authorised like a download.** Being signed in is not
   enough; `GET /files/{id}` calls `assert_can_read_file`.
4. **Uploads are validated on magic bytes**, not the browser's `Content-Type`.
5. **Scoped roles are exact.** Coordinating Summer Internship for ICT grants
   nothing over CSSI, and nothing over CSE. Mentor and Coordinator are
   independent grants; neither implies the other. Mentor access to a student
   record is earned **per student**, not per department.

---

## Layout

```
backend/app/
  api/v1/        routers            — thin; business logic lives in services
  services/      the rules          — curriculum, registration, sections,
                                      allocation, documents, scope, internships
  models/        SQLAlchemy         — enums.py holds every vocabulary
  schemas/       pydantic I/O
  seed/          demo data + curriculum importer
  tests/         405 tests
backend/curriculum/<programme>/<version>.json   researched curricula, reviewable
frontend/src/
  features/      one folder per module
  components/ui/ the design system  — use it, don't hand-roll
docs/            phase reports, curriculum research, deployment
```

## Conventions

- Business rules go in `services/`, not in routers and never in React.
- Every mutation writes an audit row (`services/audit.record`).
- New vocabularies go in `models/enums.py` as `StrEnum` with
  `native_enum=False`, so values can be added in a plain migration.
- Frontend tables live inside a scroll container; the page body never scrolls
  sideways.
- Tests are named for the behaviour they protect, not the function they call.

## Before you claim something works

Run `make test`. Then check the thing you changed against the seeded data —
`docs/PHASE4-REPORT.md` §7 shows how endpoints were measured, and
`docs/PHASE3B-RESEARCH.md` records which policies are confirmed versus still
awaiting faculty confirmation. Do not invent a university rule to fill a gap;
flag it instead.
