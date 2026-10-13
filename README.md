# CampusHub — PDEU Centralised Student Portal

**Phase 1: foundation.** A working, production-oriented skeleton of the PDEU
student portal — authentication, role-based access control, a
configuration-driven curriculum, elective/NPTEL/minor workflows, a reusable
internship engine (CSSI **and** Summer Internship), clubs and events,
mentor–mentee support, notifications, file storage and an audit trail.

Institutional business rules that have not yet been confirmed by faculty —
elective allocation formulas, merit weighting, grade boundaries — are
**deliberately not implemented**. They plug into defined extension points
(see [Deliberate omissions](#deliberate-omissions)).

---

## Quick start

Requires Docker Desktop (or Docker Engine + Compose v2).

```bash
git clone <your-repo-url> CampusHub && cd CampusHub
cp .env.example .env          # optional: the compose file has sane defaults
docker compose up --build
```

That single command starts PostgreSQL, applies migrations, seeds demo data and
serves both tiers:

| Service | URL |
|---|---|
| Frontend | <http://localhost:5173> |
| API | <http://localhost:8000/api/v1> |
| Interactive API docs | <http://localhost:8000/docs> |
| Health check | <http://localhost:8000/health> |

### Demo accounts

Every demo account uses the password **`Campus@123`**. The sign-in page lists
them and fills the form on click.

| Role | Email | What it demonstrates |
|---|---|---|
| `STUDENT (Sem I)` | `devansh.joshi.091@campushub.example.com` | Sem I — 1st Year Induction & Foundation Core courses |
| `STUDENT (Sem II)` | `ishaan.bhatt.041@campushub.example.com` | Sem II — 1st Year CSSI Exploration & Announcement phase |
| `STUDENT (Sem III)` | `riya.chauhan.031@campushub.example.com` | Sem III — 2nd Year CSSI Live & Faculty Mentor mapped |
| `STUDENT (Sem IV)` | `ananya.menon.011@campushub.example.com` | Sem IV — 2nd Year Open Elective 1 (OE1) Bidding |
| `STUDENT (Sem V)` | `kavya.patel.051@campushub.example.com` | Sem V — 3rd Year NPTEL/MOOC & PCE1 Track credits |
| `STUDENT (Sem VI)` | `aarav.desai.001@campushub.example.com` | Sem VI — 3rd Year Allocated OE3, Minor Specialization active |
| `STUDENT (Sem VII)` | `arjun.verma.021@campushub.example.com` | Sem VII — 4th Year Summer Industry Internship & OE4 |
| `STUDENT (Sem VIII)` | `pooja.shah.081@campushub.example.com` | Sem VIII — 4th Year Capstone Project & Degree Completion |
| `FACULTY` | `anand.mehta@campushub.example.com` | Mentor + CSSI Group 1, submissions awaiting review |
| `FACULTY` + `INTERNSHIP_COORDINATOR` | `priya.nair@campushub.example.com` | Programme configuration, mentor override |
| `FACULTY` + `DEPARTMENT_ADMIN` | `rakesh.bhatt@campushub.example.com` | Department-level academic administration |
| `CLUB_ADMIN` | `clubs@campushub.example.com` | Club and event management |
| `SUPER_ADMIN` | `admin@campushub.example.com` | Everything, including the audit log |

All seeded people, organisations and records are fictional. Emails use the
IANA-reserved `example.com` domain so nothing can be mistaken for real data.

### Live-reload development

The default stack runs the code baked into the images. To edit source with hot
reload, overlay the dev file:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

> **macOS caveat.** The overlay bind-mounts your working tree. If the project
> sits in an iCloud-synced folder (`~/Desktop` or `~/Documents` with
> "Desktop & Documents" sync enabled), Docker reads fail with
> `OSError: [Errno 35] Resource deadlock avoided`. Move the project somewhere
> like `~/dev/CampusHub`, or use the base stack.

### Running without Docker

```bash
# Database
docker run -d --name campushub-pg -p 5432:5432 \
  -e POSTGRES_USER=campushub -e POSTGRES_PASSWORD=campushub_dev_password \
  -e POSTGRES_DB=campushub postgres:16-alpine

# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
cp ../.env.example ../.env   # then set POSTGRES_HOST=localhost
alembic upgrade head
python -m app.seed.run
uvicorn app.main:app --reload

# Frontend (second terminal)
cd frontend && npm install && npm run dev
```

### Make targets

```
make up         Build and start the stack        make migrate    Apply migrations
make down       Stop (keeps data)                make revision   Autogenerate a migration
make clean      Stop and delete volumes          make seed       Load demo data
make logs       Tail logs                        make reset-db   Rebuild schema + reseed
make shell-api  Shell in the API container       make shell-db   psql in the database
```

---

## Architecture

```
Browser
  │
  ├── React 18 + TypeScript (Vite)         one app, role-based navigation
  │     TanStack Query · React Router · Tailwind design tokens
  │
  ▼  /api/v1
FastAPI
  │   routers → services → SQLAlchemy models
  │   JWT auth · RBAC dependencies · centralised error envelope
  │
  ├── Storage abstraction  ──►  local disk (dev)  |  S3 (production)
  │
  ▼
PostgreSQL 16  (45 tables, Alembic migrations)
```

Four ideas carry most of the design:

1. **The curriculum is data, not code.** A programme's semester structure lives
   in `curriculum_components` rows. Whether a student sees "Open Elective 1 —
   From Other School" comes from their curriculum, never from a hard-coded list
   in a React component. Ten B.Tech programmes are modelled this way, and they
   genuinely differ.
2. **The admission batch is part of the key.** Curriculum versions are scoped to
   a range of admission years, so two ECE students in the same lecture hall can
   be governed by two different structures — the 2020-24 scheme has no NPTEL
   component at all. Resolution goes through `Curriculum.governs_batch()`, never
   through `department + semester`.
3. **One internship engine.** CSSI, Rural Internship, Industrial Training and
   Summer Internship are `internship_programs` rows differing only in
   configuration — stages, group size, report cadence, evaluation rubric. They
   share every route, service and screen.
4. **Policy is pluggable, and unconfirmed policy stays unconfirmed.** Allocation
   strategies implement a documented interface and register themselves. Imported
   curriculum components whose official source was ambiguous are flagged, and a
   version cannot be published until a person clears them.

More detail in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Programmes

Ten B.Tech programmes, verified against the university's own course catalogue
and the B.Tech. Admission Rules A.Y. 2026-27. Every curriculum is transcribed
from an official PDEU document and carries a link back to it — see the
[research report](docs/PHASE3B-RESEARCH.md).

| School | Programme | Seats | Curriculum version(s) | Divisions |
|---|---|---|---|---|
| SoT | Information & Communication Technology | 180 | 2024-28 | A–C |
| SoT | Computer Engineering | 300 | 2024-28 | A–D |
| SoT | Computer Science & Business Systems | 60 | 2024-28 | A |
| SoT | Electronics & Communication Engineering | 120 | **2020-24 and 2024-28** | A, B |
| SoT | Mechanical Engineering | 120 | 2024-28 | A, B |
| SoT | Civil Engineering | 120 | 2024-28 | A, B |
| SoET | Chemical Engineering | 120 | 2024 onward | A, B |
| SoET | Electrical Engineering | 120 | 2020-24 | A, B |
| SoET | Petroleum Engineering | 120 | 2024-28 | A, B |
| SoET | Biotechnology | 120 | 2023 *(draft — source incomplete)* | A, B |

Three things the research corrected, which the portal would otherwise have got
wrong:

- **There is no B.Tech "Computer Science & Engineering".** CSE is the
  *department*; the programme it runs is **Computer Engineering**. The
  department also runs **CSBS**, a programme with a different structure again.
- **Automobile Engineering is not offered.** It survives only as `24ME437T`, a
  Program Elective 5 option inside Mechanical Engineering.
- **Electrical and Chemical are School of Energy Technology**, not School of
  Technology — which matters, because Open Elective eligibility is written in
  schools.

**Climate Science & Sustainable Engineering** admits 60 students for 2026-27 per
the admission policy but has no published curriculum. It is deliberately **not**
created rather than invented.

### Curriculum import

Researched curricula live as reviewable JSON under
`backend/curriculum/<programme>/<version>.json`, with a shared course catalogue
in `courses.json` (454 courses, 60 of them shared across departments rather than
duplicated).

```bash
cd backend && python -c "
from app.db.session import SessionLocal
from app.seed import curriculum_import
db = SessionLocal(); print(curriculum_import.run_import(db).summary()); db.commit()"
```

The importer **never publishes on its own** — everything lands as `DRAFT` unless
publication is explicitly requested, and even then it refuses any version whose
source was not fully confirmed. Publishing is done from
**Administration → Curriculum**, and is blocked while any component is flagged
as needing faculty confirmation.

---

## Project structure

```
CampusHub/
├── docker-compose.yml            Base stack (code baked into images)
├── docker-compose.dev.yml        Live-reload overlay
├── Makefile                      Common commands
├── .env.example                  Every environment variable, documented
│
├── backend/
│   ├── Dockerfile  entrypoint.sh alembic.ini
│   ├── alembic/versions/         0001_initial_schema.py
│   └── app/
│       ├── main.py               App assembly, CORS, static media, health
│       ├── core/                 config · security · deps · rbac · errors
│       ├── db/                   Declarative base, session factory
│       ├── models/               45 tables across 7 domain modules
│       ├── schemas/              Pydantic request/response contracts
│       ├── api/v1/               17 routers
│       ├── services/             Business logic (allocation, internships, …)
│       ├── storage/              Backend-agnostic file storage
│       ├── seed/                 Demo dataset
│       └── tests/                pytest suite
│
├── frontend/
│   ├── Dockerfile  nginx.conf  tailwind.config.js
│   └── src/
│       ├── components/ui/        Design system (44 exported primitives)
│       ├── components/layout/    Shell, sidebar, topbar, route guards
│       ├── features/             Screens grouped by domain
│       ├── lib/                  api · auth · theme · navigation · format
│       └── types/                Mirrors of the API contracts
│
└── design-system/campushub/      MASTER.md — tokens, style, checklist
```

---

## Database schema

45 tables. Enumerations are stored as `VARCHAR` with a `CHECK` constraint rather
than native PostgreSQL enums, so new values arrive in a plain migration instead
of `ALTER TYPE`.

| Area | Tables |
|---|---|
| Identity & access | `users`, `user_roles`, `faculty_role_assignments`, `students`, `faculty`, `departments` |
| Sections | `course_sections` (per-section capacity, division composition) |
| Academic calendar | `academic_years`, `semesters`, `programs` |
| Curriculum | `curriculums`, `curriculum_components`, `elective_types` |
| Courses | `courses`, `course_offerings` |
| Electives | `elective_preferences`, `elective_allocations` |
| MOOC | `mooc_registrations` |
| Minors | `minor_programs`, `minor_courses`, `minor_applications`, `minor_enrollments` |
| Internships | `internship_programs`, `internship_stages`, `internship_groups`, `internship_enrollments`, `enrollment_stage_progress`, `internship_projects`, `internship_documents`, `internship_reports`, `organizations` |
| Evaluation | `evaluation_criteria`, `internship_evaluations`, `internship_evaluation_scores` |
| Community | `clubs`, `club_members`, `events`, `event_registrations`, `event_interests` |
| Engagement | `mentor_assignments`, `mentor_meetings`, `announcements`, `notifications` |
| Platform | `files`, `audit_logs` |

```bash
make migrate                       # apply migrations
make revision m="add x"            # autogenerate a new revision
make reset-db                      # drop → migrate → reseed
docker compose exec backend alembic downgrade base   # full rollback
```

---

## API overview

All routes are under `/api/v1`. Full interactive reference at `/docs`.

| Group | Highlights |
|---|---|
| `/auth` | `login`, `refresh`, `me`, `change-password`, `logout` |
| `/dashboard` | `student`, `faculty`, `admin` — role-specific aggregates |
| `/curriculum` | `me` (annotated with the student's progress), `programs`, `elective-types` |
| `/courses`, `/course-offerings` | Catalogue and per-semester offerings |
| `/electives` | `components`, `components/{id}/workspace`, `preferences`, `allocations/me`, `strategies`, `admin/allocate`, `admin/allocations/manual` |
| `/electives/admin` | `viability` (runs? how many sections?), `offerings/{id}/sections`, `offerings/{id}/distribute`, `sections/move` (rebalance) |
| `/mooc` | `eligibility`, `catalogue`, `register`, `{id}/certificate`, `admin/{id}/verify` |
| `/minors` | `workspace`, `apply`, `applications`, `applications/{id}/decide` |
| `/internships` | `programs`, `programs/{id}/groups`, `enroll`, `enrollments`, stage submit/review, documents, reports, evaluation, mentor override |
| `/organizations` | NGO / company directory |
| `/clubs`, `/events`, `/calendar` | Membership, registration, interest, unified calendar feed |
| `/students`, `/faculty`, `/departments`, `/academic` | Directory and administration |
| `/mentorship` | `my-mentor`, `my-mentees`, `meetings`, `assignments` |
| `/announcements`, `/notifications` | Audience-scoped publishing, read state |
| `/files` | Upload, metadata, access-checked download |
| `/admin/roles` | `matrix` (who coordinates what, incl. gaps), assign, revoke, `domains` |
| `/admin` | `audit-logs`, `permissions` (the enforced role→permission matrix) |

Errors use one envelope, so the client renders them uniformly:

```json
{ "error": { "code": "rule_violation",
             "message": "Select at least 3 preference(s).",
             "details": [{ "field": "preferences", "message": "…" }] } }
```

---

## Roles and permissions

Six roles, one application. Navigation adapts to the signed-in user, and **the
backend independently enforces the same matrix** — hiding a button is never the
only control. `GET /api/v1/admin/permissions` returns the live matrix.

| Role | Can |
|---|---|
| `STUDENT` | Own academics, elective/MOOC/minor applications, internship submissions, event registration, own mentor |
| `FACULTY` | Assigned students, mentorship, internship review and evaluation, announcements to mentees. Deliberately **not** institution-wide reporting or the audit log |
| `DEPARTMENT_ADMIN` | Everything faculty can, plus academic configuration, elective allocation, MOOC verification, minor decisions, student/faculty management |
| `INTERNSHIP_COORDINATOR` | Internship programmes, groups, mentor assignment and override, evaluation oversight |
| `CLUB_ADMIN` | Clubs, events, registrations, event announcements |
| `SUPER_ADMIN` | System-wide configuration and the audit log |

A user may hold several roles — the seeded internship coordinator is also
faculty, and sees both surfaces.

### Coordination is scoped, not global

A coarse `Role` says *what kind* of thing you may do. **Coordinator
assignments** say *over which slice*: one module, for one department.

```
faculty_role_assignments:  faculty × domain × department
  domain ∈ CSSI | SUMMER_INTERNSHIP | MINOR | MOOC
           | OPEN_ELECTIVE | CORE_ELECTIVE | MENTORSHIP
  department = NULL means institution-wide
```

So "Summer Internship coordinator for ICT" and "Summer Internship coordinator
for CSE" are two different people with no authority over each other's
programme, and CSSI has a different coordinator again. As seeded:

| Module | ICT | CSE | MEC |
|---|---|---|---|
| CSSI | Prof. Sneha Iyer | Dr. Farah Ansari | — |
| Summer Internship | Dr. Priya Nair | Dr. Kunal Shah | Dr. Suresh Pillai |
| NPTEL / MOOC | Dr. Meera Krishnan | Dr. Farah Ansari | — |
| Minor · Open/Core Electives | Dr. Rakesh Bhatt | — | — |
| Mentor–Mentee | Dr. Anand Mehta | — | — |

**Only an administrator grants coordination** (Administration → Role
Assignments), which shows who holds what, per department, and which cells have
nobody. Coordinators then work *inside* their scope — assigning mentors to
groups, approving submissions, verifying certificates. Every grant and revoke
is audit-logged.

Scoping is enforced server-side, verified:

| Action | Priya (SI·ICT) | Sneha (CSSI·ICT) | Kunal (SI·CSE) |
|---|---|---|---|
| Configure Summer Internship (ICT) | 200 | 403 | 403 |
| Configure CSSI (ICT) | 403 | 200 | 403 |
| Create a CSSI group (ICT) | 403 | 201 | 403 |

A plain-faculty NPTEL coordinator can approve their department's certificates
without being handed institution-wide `mooc:verify`; the queue itself is
narrowed to the departments they coordinate.

### Mentor lists are earned, not granted

`My Students` was replaced by two screens — **CSSI Students** and
**SI Students** — and each appears only for faculty who actually mentor
students on that programme. A faculty member who was never made a mentor sees
neither. Coordinators additionally get **All Students**, scoped to the
programmes they coordinate.

| Faculty | Coordinates | Mentors | Screens shown |
|---|---|---|---|
| Dr. Anand Mehta | Mentorship · ICT | CSSI, Summer | CSSI Students + SI Students |
| Prof. Sneha Iyer | CSSI · ICT | CSSI, Summer | both + All Students |
| Dr. Priya Nair | Summer · ICT | Summer | SI Students + All Students |
| Dr. Meera Krishnan | NPTEL · ICT | — | *no student screens* |

---

## Modules

- **Academics** — curriculum viewer, Open Electives, Program Core Electives
  (four specialisation tracks), NPTEL/SWAYAM, minor specialisation.
- **Internships** — one engine; CSSI (faculty groups, NGO placement, poster and
  presentation), Summer Internship (industry mentor, weekly reports), Rural
  Internship (Petroleum) and Industrial Training (the 2020-scheme cohorts) are
  all configurations of it.
- **Clubs & events** — directory, membership, publishing, registration with
  waitlist and automatic promotion, "Interested" tracking, calendar.
- **Support** — mentor–mentee profiles and meeting requests, faculty directory,
  audience-scoped announcements, in-app notifications.
- **Administration** — dashboards over real queries, student/faculty/department
  management, curriculum versions and divisions, allocation console,
  verification queues, audit log.

---

## Elective capacity rules

The two elective families have genuinely different rules and are modelled
separately — neither inherits the other's numbers.

**Open Elective** (across schools/branches)
- Runs only with at least **40** students
- **75 per class section** — *not* a course-wide maximum
- Demand above one section opens another: 90 → Section A 75 + Section B 15;
  150 → 75 + 75; 151–225 → three sections
- Coordinators can review and rebalance students between sections

**Program Core Elective** (division-based; divisions come from the programme)
- Same **40** minimum, but counted **across all participating divisions
  combined**, never per division — 10+10+10+10 runs as one class
- **No 75 ceiling**; runs as a single combined class however large
- Divisions are `program_divisions` rows keyed on programme × admission batch,
  so a two-division programme reaching 40 combined runs exactly as ICT does

Seeded demo makes both observable: `MEC301` draws 81 students and splits
75 + 6, `CIV301` falls 2 short of 40 and does not run, while Core Elective
`ICT301` runs with 55 students spread A:12 B:12 C:21 D:10 — no division near 40.

**CPI/CGPA is never an input to elective selection.** Academic merit governs
Minor Specialisation eligibility only.

## Deliberate omissions

Phase 1 stops short of inventing university policy. Each gap has a defined
extension point:

| Not implemented | Where it plugs in |
|---|---|
| Merit / pro-rata elective allocation | `MeritAllocation` in `app/services/allocation/strategies.py` — declared, `is_available = False`, refuses to run |
| Minor selection formula | `MinorProgram.allocation_strategy` + `rules` JSON; decisions are recorded and audited today |
| Letter-grade derivation | `compute_totals()` returns marks only; grade boundaries are not guessed |
| Real-time chat | `mentor_meetings.thread_key` reserves the anchor |
| Email / SMS delivery | `app/services/notifications.py` — one `notify()` entry point to subscribe a transport to |
| AWS infrastructure | Storage is already abstracted; see below |

Also out of scope for this phase: mobile apps, microservices, and complete
production infrastructure.

The confirmed Phase 2 scope — end-to-end document submission and faculty review
— is specified in [PHASE2.md](PHASE2.md), with a gap analysis of what Phase 1
already provides.

---

## Future AWS deployment

The application is written so this becomes configuration, not a rewrite:

```
Route 53 → CloudFront ──► S3            (frontend bundle)
                     └──► ALB → EC2/ECS (FastAPI containers)
                                  ├──► RDS PostgreSQL (Multi-AZ)
                                  ├──► S3              (uploaded documents)
                                  ├──► Secrets Manager (SECRET_KEY, DB creds)
                                  └──► CloudWatch      (logs, metrics, alarms)
```

Switching file storage to S3 is `STORAGE_BACKEND=s3` plus `S3_BUCKET_NAME` —
business code references `files.id`, never a filesystem path. Prefer an
instance/task IAM role over static keys; the S3 backend already falls back to
the role when no keys are set.

---

## Environment variables

See [.env.example](.env.example) for the annotated list. The ones that matter:

| Variable | Default | Notes |
|---|---|---|
| `SECRET_KEY` | dev placeholder | **Must** be changed outside local dev (`openssl rand -hex 32`) |
| `DATABASE_URL` | assembled from parts | Overrides the individual `POSTGRES_*` values |
| `BACKEND_CORS_ORIGINS` | localhost origins | Comma-separated |
| `STORAGE_BACKEND` | `local` | `local` or `s3` |
| `MAX_UPLOAD_SIZE_MB` | `15` | Enforced server-side |
| `SEED_ON_START` | `true` | Compose only; skips if data exists |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Refresh tokens last 14 days |

`.env` is git-ignored; only `.env.example` is committed.

---

## Tests

```bash
make test                            # or: cd backend && pytest -q
```

287 tests. They cover password hashing and JWT handling, the RBAC matrix,
curriculum eligibility and source-scope rules, and the allocation strategies
(including that the unconfigured merit rule refuses to run).

Phase 3B added coverage for the multi-programme behaviour specifically:

- **Batch resolution** — a 2022 ECE student gets the 2020-24 structure and a
  2024 ECE student the 2024-28 one; batch windows never overlap.
- **Cross-programme isolation** — an ICT student never receives ECE's
  curriculum, and a programme with no curriculum gets nothing rather than
  someone else's.
- **Per-programme structure** — each of the eleven curricula is asserted against
  its official document: Open Elective semesters, MOOC applicability, internship
  type, project credits.
- **School-level Open Elective scope** — including the specific regression that
  a department-only check would allow a Mechanical course into an ICT student's
  "From Other School" slot.
- **Publication gating** — a draft reaches no student, and a partially-sourced
  curriculum is never published even when publication is requested.

---

## Design system

Generated with the `ui-ux-pro-max` skill and recorded in
[design-system/campushub/MASTER.md](design-system/campushub/MASTER.md):
Minimalism/Swiss style, dense dashboard spacing, institutional navy `#1E3A5F`
with action blue `#2563EB`, Lexend + Source Sans 3 + JetBrains Mono, Lucide
icons. Light and dark themes share one token set; components reference semantic
token names only. Every route was checked for horizontal overflow at 375px.
