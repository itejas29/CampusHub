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
cd frontend && npm run test:e2e  # browser tests: sign in → allocate → review
                                 # (own seeded SQLite API on :8100, Vite on :5180,
                                 #  installed Chrome; needs the repo-root .venv)
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
`~/.campushub-modules/frontend/node_modules`, outside the synced tree, where
iCloud cannot touch it. Run `npm ci` normally — it installs through the symlink.
If the symlink is ever lost, recreate it before installing:

```bash
cd frontend
rm -rf node_modules
mkdir -p ~/.campushub-modules/frontend/node_modules
ln -s ~/.campushub-modules/frontend/node_modules node_modules
npm ci
```

The target **must itself be named `node_modules`.** TypeScript and Node resolve
a package's own imports from its *real* path, walking up looking for a
`node_modules` folder. Point the link at `~/.campushub-modules/frontend` and that
walk finds none until `~/node_modules` — any stray packages in your home folder —
and `tsc` fails with "no exported member" errors from the wrong React types.

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
| CSSI window | Sem I hidden · II announced · III active · IV+ concluded — **except** that the coordinator's registration window lets the Sem II cohort register early (below) | `services/internships.py`, `services/internship_windows.py` |
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

## Who appoints whom, and who runs a round

Scope for now is **the ICT department, end to end**; other departments keep
their data but are not being built out yet. ICT runs on **the 2024-28 scheme
alone** — the old hand-built 2022 scheme was removed. Every ICT batch in the
demo resolves to 2024-28, and the Program Elective courses are the subjects the
handbook lists (`backend/curriculum/ict/2024-28.json`), not invented ones. Three rules came out of that work,
and each is enforced in one place.

### The Head of Department (`services/scope.py`)

- *Which* department someone heads is `departments.hod_faculty_id`.
  `Role.HOD` only carries the permissions. `scope.set_hod` is the single writer
  and keeps the pointer, the role and `is_mentor` in step — never set one alone.
- **Only a department's own HoD appoints into it** (`roles:assign`,
  `scope.assert_can_assign_roles`): the scope granted *and* the person appointed
  must both be theirs. The registrar (super admin) can act anywhere. Internship
  coordinators and Department Admin cannot appoint — `faculty:manage` is for
  faculty *records* only.
- **The HoD holds no scoped role and has no mentees.** Every place that makes
  someone a coordinator, a mentor, a group lead or a student's mentor asks
  `scope.assert_can_hold_scoped_role` / `scope.assert_can_mentor` first. A new
  route that assigns a mentor must ask too.
- **The HoD reads their department and changes nothing** (`scope.oversees`).
  Read routes may admit them; a write route must still ask `coordinates()`,
  which an HoD never satisfies.

### One elective family, one department

Open Electives and Program Core Electives have separate coordinators. Every
elective admin route — rounds, preferences, allocation, sections — is scoped by
the **slot** (`_assert_manages_component` / `_assert_manages_window` in
`api/v1/electives.py`), not by the coarse `electives:manage` permission. Holding
that permission alone must never open another department's students; being an
appointed coordinator without it must never lock someone out of their own slot.

### A round, not the semester, opens registration early

Choice filling for a Semester N elective starts mid-way through Semester N−1,
so the timetable can be built over the vacation. (This is how the ICT department
described its practice to the project team; it is not from a written rule.)

- The curriculum alone still says "opens in semester N". What lets the earlier
  student in is a registration round the coordinator has opened for *their
  current* semester — `registration.access_for`. **No round, no early access.**
  Do not relax `student_can_access_component`; route through `access_for`.
- A round covers one family and the slots of one semester, and may be aimed at
  Semester N−1 or N only (`registration.validate_round`). A course belongs to one
  round at a time, and a student sees only the courses of the round that covers
  them — so two cohorts can be choosing for the same slot at once. The next
  cohort's courses are next year's offerings (a course is offered once per slot
  per term).
- The coordinator sets and moves the deadline; the server enforces it. A live
  round's deadline cannot be moved into the past — that is Lock, which has its
  own audit entry. Opening, reopening and moving a deadline notify the students.
- The student's sidebar, dashboard and elective list follow the round
  (`registration.early_rounds`), so they are never told to choose without a
  screen to do it on.
- **A round can be deleted until allocation has run** (Draft, Open, Locked —
  `registration.delete_round`, `DELETE /electives/admin/windows/{id}`), by the
  same coordinator who may run it. Its courses go back to no round, the choices
  filled in it are removed, and students who were told it opened are told it
  was withdrawn. From Allocated on — or once a run has committed seats — it is
  refused: students hold seats from it.

### Allocation is per round, and first come, first served

- **A run allocates one round**, never the whole slot (`registration_window_id`
  on `POST /electives/admin/allocate`; inferred only when exactly one round
  has the slot's courses). Two cohorts can share a slot, and a slot-wide run
  used to seat and notify both. Only the round's courses and the students it
  covers are touched. A real run needs the round **LOCKED**; a dry run does not.
- **Students hear on Publish, not at run time.** A run for a round sends no
  notification; `_notify_allocation_published` tells exactly the covered students.
- `first_come_first_served` (`services/allocation/strategies.py`): lists are
  served in submission order, each student seated in their highest choice with
  a seat left. Covered students who never submitted, and submitters whose every
  choice filled, are placed **at random** in the seats that remain. The draw is
  seeded by round and slot, so the preview equals the run. Who did not submit
  is computed by the server; a client-sent `non_submitter_ids` is overwritten.
- With no seat limit every course is unlimited (Open Electives add sections,
  Core Electives have no cap), so the order would not matter. The coordinator
  sets `seats_per_course` for the run; the screen suggests an even split. That
  number is the coordinator's call, not a university rule.

---

## CSSI runs in coordinator-opened windows

How the ICT department runs CSSI, as described to the project team (not from a
written rule). It is configuration on the one internship engine —
`internship_programs.config["windows"] = ["REGISTRATION", "PRESENTATION"]` — and
a programme that lists no windows keeps the semester-only rules. Enforced in
`services/internship_windows.py`.

1. The HoD appoints the CSSI coordinator.
2. The coordinator opens **registration** with a message, an opening date and a
   deadline, aimed at the Semester II cohort. Opening it notifies those
   students. While it is open they record the NGO and their **NGO supervisor's
   name and phone number** (required). **No window, no early access** — the
   Sem II "announced" phase is still view-only otherwise.
3. **Mentor allocation needs registration to have started** (`assert_can_allocate_mentors`).
4. In Semester III the coordinator opens **presentations** with the poster
   deadline, presentation day(s) and the process deadline. It needs
   registration closed and every registered student to have a mentor; opening
   it tells each student their mentor (with the full roll-range list) and each
   mentor their students.
5. Posters are accepted until the poster deadline; **marks lock when the window
   closes** — for the coordinator too.
6. The coordinator may extend, reschedule or reopen a window (audited, notifies);
   nobody else can.

## Faculty performance score

Requested by the department (not a PDEU rule — weights are flagged as
department-set). `services/faculty_scoring.py` holds the policy and the rules;
the screens read them from `/faculty-scores/policy` and never restate them.

- Points come only from dated records: review turnaround (stages, reports,
  documents), marks entered by a presentation window's deadline, and how fast
  meeting requests are answered (`mentor_meetings.responded_at`).
- Work is credited to whoever reviewed it; waiting work is the mentor's.
- Compare by **on-time rate**, not points — workloads differ.
- A faculty member sees their own; the HoD their department (not themselves);
  the registrar any. Students and colleagues see none.
- **Real faculty are not scored until `SCORE_REAL_FACULTY` is on.** While the
  portal runs on seeded activity, their score would be a judgement about a real
  person made of demo data. Department office accounts are never scored.

### Locking the mentor allocation (`services/mentor_allocation.py`)

Asked for by the department (not from a written rule). One click of
**Auto-allocate** picks the mentors the cohort needs (name order, as many as the
cap requires) and allocates by roll number. Once every student has a mentor the
coordinator may **lock** it; the mentors carrying students become the
allocation (`config["mentor_allocation"]`). While locked, no run, auto-distribute
or Reset all is accepted, and a student can be moved only to a mentor in the
allocation. Changes are one step at a time — add a mentor, remove one (their
students move within the cap, or wait), replace one (the whole block moves) —
each audited and notified. Unlocking is audited.

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
  tests/         620+ tests
backend/curriculum/<programme>/<version>.json   researched curricula, reviewable
frontend/src/
  features/      one folder per module
  components/ui/ the design system  — use it, don't hand-roll
docs/            phase reports, curriculum research, deployment
```

## Demo data

**ICT faculty are real** — PDEU's published list (`backend/app/seed/sources/pdeu_ict_faculty.json`,
source URL and retrieval date inside). Only published fields are used; real
faculty cannot sign in (unusable password, non-routable login address) and hold
no coordinator/HoD role until the department confirms who does. Sign-in uses the
**demo personas** (`faculty.is_demo`, labelled "Demo account"). Students are
still generated.

The seed is the demo. After pulling a change to `seed/`, reseed — the database
keeps its old rows otherwise, and new demo logins will not exist:

```bash
docker compose exec backend python -m app.seed.run --reset
```

This rebuilds everything, so anything changed by hand in the app is lost.
Generated (non-named) student names can shift when the seed changes; check the
sign-in shortcuts in `frontend/src/features/auth/LoginPage.tsx` afterwards.

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
