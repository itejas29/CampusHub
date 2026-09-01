# CampusHub — Architecture Notes

Companion to [README.md](README.md). This document explains *why* the code is
shaped the way it is, and where Phase 2 work attaches.

---

## 1. The curriculum is data

The single most important decision. A naive portal hard-codes screens:

```tsx
// What we deliberately did NOT build
if (student.department === "ICT" && student.semester === 4) {
  return <OpenElective1FromOtherSchool />;
}
```

That approach makes every new department a frontend project. Instead the
structure lives in the database:

```
Program -> Curriculum (scoped to a range of admission batches)
             |- status            DRAFT | PUBLISHED | ARCHIVED
             |- effective_from_year / effective_to_year
             |- source_url, source_title, retrieved_at, source_confidence
             `- CurriculumComponent   one requirement slot in one semester
                  |- component_type   OPEN_ELECTIVE | PROGRAM_CORE_ELECTIVE |
                  |                   MOOC | MINOR | INTERNSHIP | PROJECT | CORE
                  |- source_scope     OTHER_SCHOOL | OTHER_DEPARTMENT_FOET |
                  |                   SAME_DEPARTMENT | EXTERNAL_PLATFORM | ANY
                  |- eligibility      declarative schools/departments/programmes
                  |- course_id        for a fixed (non-choice) slot
                  |- scope_label      the human sentence students read
                  `- config (JSON)    extension point, no migration needed
```

### The batch is part of the key

Ten B.Tech programmes are modelled from official PDEU documents
([research report](docs/PHASE3B-RESEARCH.md)), and they do **not** share a
shape. The clearest case is ECE, which has two published curricula:

| | ECE 2020-24 | ECE 2024-28 |
|---|---|---|
| Open Electives | Sem **III, IV, V, VI** | Sem **IV, V, VI, VII** |
| MOOC / NPTEL slot | **none** | OE-2, Sem V |
| Elective family | Core Elective x7 | Program Elective x5 |
| CSSI | **absent** | Sem III |
| Final internship | Industrial Training, Sem VI | Summer Internship, Sem VII |

Two ECE students in the same lecture hall can therefore be governed by
different rules. That is why resolution goes through the *batch window*:

```
Student -> Program -> Curriculum.governs_batch(admission_year) -> Semester -> Component
```

`services/curriculum.resolve_curriculum()` is the only place that answers it,
and it considers only `PUBLISHED` versions. Keying on
`student.department + semester` would have been wrong for six of the eleven
curricula.

### Programmes differ in ways that matter

| Programme | Deviation from ICT's shape |
|---|---|
| Mechanical | Program Electives distributed **1 / 1 / 3** across Sem V/VI/VII, not 1 / 2 / 2 |
| CSBS | Open Electives are **prescribed named courses**, not a cross-school basket; one division |
| Petroleum | **Rural Internship** in Sem III instead of CSSI |
| ECE / Electrical (2020) | Open Electives start in Sem III; **no MOOC component at all** |
| Biotechnology | Social internship in **Sem II**; official structure stops at Sem II, so it stays a draft |

**Consequences.** `/electives/components` returns whatever the student's
curriculum defines; `ElectiveListPage` renders that list without knowing what
"OE3" is. Adding the tenth programme required no frontend change and no new
endpoint - only a JSON document under `backend/curriculum/`.

### Cross-programme Open Electives are a *school* rule

The official rule, quoted verbatim in the Electrical course structure, is not
expressible as `course.department_id == X`:

> "This open elective will be offered to the students enrolled in B.Tech.
> programs of School of Technology **other than Electrical Engineering**."
> "Student of Electrical Engineering will have a choice ... from the basket of
> open electives announced by **the other departments of School of Technology /
> other schools of university**."

So `CurriculumComponent.eligibility` carries it declaratively -
`eligible_schools`, `eligible_departments`, `eligible_programs`,
`excluded_*`, `exclude_own_department` - and
`services/curriculum.offering_matches_component()` evaluates the rules first,
falling back to `source_scope`. A department-only check would wrongly offer a
Mechanical course to an ICT student for a "From Other School" slot: different
department, *same* school.

### Divisions are data, not A/B/C/D

`ProgramDivision` is keyed on programme x admission batch. Computer Engineering
runs four divisions (300 seats), ICT three (180), CSBS one (60). The Core
Elective allocator reads these rows; no divisions configured means "no division
restriction", never a silent fallback to ICT's four.

### Curriculum data is policy data, so it carries its source

Every imported version records `source_url`, `source_title`, `retrieved_at` and
a `source_confidence`. Where two official documents disagree - Chemical prints
"Program Elective 3" twice; Biotechnology places its social internship a
semester earlier than every other programme - the component is flagged
`REQUIRES_FACULTY_CONFIRMATION` with the reason, and **publication is refused
until a person clears it**. Nothing uncertain becomes a rule a student is held
to. The import pipeline is:

```
research -> extract -> normalize -> review -> import -> verify -> publish
                                      ^                             ^
                        docs/PHASE3B-RESEARCH.md      a deliberate, audited act
```

`app/seed/curriculum_import.py` never publishes on its own, and refuses to
publish anything whose source was not fully confirmed even when asked.

---

## 2. One internship engine

CSSI and Summer Internship differ in policy, not in mechanics. Both are rows in
`internship_programs`:

| | CSSI | Summer Internship |
|---|---|---|
| `requires_group` | `true` (`default_group_size` 10) | `false` |
| `report_frequency` | `NONE` | `WEEKLY`, 8 expected |
| `requires_industry_mentor` | `false` | `true` |
| `allowed_organization_types` | `["NGO"]` | company / startup / research lab |
| Stages | 8, ending in a poster + presentation | 8, ending in a final report + viva |
| Rubric | 5 criteria, 50 marks | 5 criteria, 100 marks |

Everything downstream is generic:

- `internship_stages` rows *are* the progress stepper. The UI renders whatever
  sequence exists, with each stage's `owner_role` deciding who can advance it.
- `evaluation_criteria` rows *are* the evaluation form. `StudentDetailDrawer`
  builds inputs from the rubric — no criterion name appears in the frontend.
- `internship_projects.extra` and `enrollment_stage_progress.data` are JSON bags
  so new per-programme fields need no migration.

Adding "Research Internship" in Phase 2 means inserting one programme row plus
its stages and criteria.

### Stage lifecycle

```
PENDING → IN_PROGRESS → SUBMITTED → APPROVED
                            └────→ REJECTED → (student resubmits)
```

`services/internships.review_stage()` advances `current_stage_id` on approval,
flips the enrollment to `UNDER_EVALUATION` when every stage clears, and notifies
the other party at each transition.

---

## 3. Elective capacity is two different rules, not one number

The most common way to get this wrong is a single `capacity` column shared by
both elective families. Phase 1 originally did exactly that; it was corrected.

```
CourseOffering
  min_students_to_run      40   — viability, BOTH families
  section_capacity         75   — Open Elective: per SECTION
                          NULL  — Core Elective: no ceiling at all
  allow_multiple_sections  True — Open Elective spawns Section A, B, C…
                          False — Core Elective stays one combined class
  eligible_divisions       [A,B,C,D] — Core Elective division scope
```

`services/sections.plan_section_sizes()` is the whole rule, and it fills each
section before opening the next — 90 students is 75 + 15, not 45 + 45:

| Demand | Open Elective (75/section) | Core Elective (no cap) |
|---|---|---|
| 38 | does not run (2 short of 40) | does not run |
| 60 | one section of 60 | one class of 60 |
| 90 | **75 + 15** | one class of 90 |
| 150 | **75 + 75** | one class of 150 |
| 151 | **75 + 75 + 1** | one class of 151 |

Two consequences the code has to honour:

- **The 40 minimum is never applied per division.** A Core Elective taken by
  10 students in each of four divisions runs as one class of 40. The check is on
  the combined total; `division_breakdown()` reports the composition for the
  coordinator without ever gating on it.
- **An Open Elective can never be "full".** Allocation passes an effectively
  unlimited seat pool for multi-section courses and lets `sections.distribute()`
  do the splitting afterwards, so surplus demand opens a section instead of
  rejecting students.

**CPI is not an input to elective selection anywhere in this path.** Viability is
a headcount question and capacity is a room question. Academic merit belongs to
`check_minor_eligibility` alone.

## 4. Policy is pluggable, never guessed

`app/services/allocation/` defines the contract every allocation rule satisfies:

```python
class AllocationStrategy(abc.ABC):
    key: str
    label: str
    is_available: bool          # False until faculty sign off on the policy

    @abc.abstractmethod
    def allocate(self, candidates: list[Candidate],
                 pools: dict[int, SeatPool], *,
                 config: dict | None = None) -> AllocationOutcome: ...
```

Three strategies are registered:

| Key | Available | Behaviour |
|---|---|---|
| `manual` | yes | Ranks nothing; a coordinator assigns seats by hand. |
| `preference_order` | yes | Round-based: in round *N* every student is considered for their *N*th choice, earliest submission first. Pure mechanics — no institutional judgement. |
| `merit` | **no** | Declared so it appears in the UI as "not configured", but `allocate()` raises `BusinessRuleError`. |

`merit` is deliberately inert. Implementing a plausible-looking CPI formula
would quietly become the university's de-facto admission policy for electives.
When the department supplies the real weighting, implement `allocate()` and flip
`is_available` — no route, model or screen changes.

The same restraint applies elsewhere: `compute_totals()` returns weighted marks
and never derives a letter grade, and `MinorProgram` exposes `min_cpi`,
`max_backlogs`, `capacity` and an `allocation_strategy` field rather than
encoding a ranking rule.

---

## 5. Access control

Three layers that must agree, with the server authoritative.

**Role** answers *what kind* of action. **Scope** answers *over which slice*.
Both are checked; neither is sufficient alone.

```
Role (coarse)            INTERNSHIP_COORDINATOR  →  internships:manage
      ×
Coordination (scoped)    faculty_role_assignments: domain × department
      ↓
can_manage_program(user, programme)
      = coordinates(domain_for(programme), programme.department_id)
```

`faculty_role_assignments` is the table that makes "Summer Internship
coordinator for ICT" a different authority from "Summer Internship coordinator
for CSE", and different again from "CSSI coordinator for ICT". A NULL
`department_id` means institution-wide.

The matching rule lives in one pure function, `models.identity.scope_matches`,
so it is unit-testable without a session and cannot drift between the model
method and the service layer.

Two consequences worth noting:

- **Coordination can substitute for a coarse permission, within scope.**
  `scope.assert_coordinates(...)` admits either the institution-wide permission
  (`mooc:verify`) *or* a matching scoped assignment. That is how a plain-FACULTY
  NPTEL coordinator approves their own department's certificates without being
  handed the global permission — and their queue is filtered to those
  departments rather than merely gated.
- **Navigation is driven by earned state, not granted state.** The CSSI and SI
  student screens appear only when `/auth/me` reports the faculty actually
  mentors students on that programme (`mentors_programs`), computed from real
  mentor assignments and group ownership. Being made a coordinator does not
  conjure a personal mentee list, and being a mentor does not imply coordination.

### The original two layers

```
Role  ──ROLE_PERMISSIONS──►  permission strings  ──►  route dependency
  │                                   │
  │                                   └──► GET /auth/me → frontend `can()`
  └──────────────────────────────────────► sidebar + route guards
```

- `app/core/rbac.py` holds the matrix; `permissions_for()` expands `SUPER_ADMIN`'s
  `*` to every permission.
- Routes declare `Depends(require_permission(P["ELECTIVE_ALLOCATE"]))`.
- Ownership checks go further than permissions: `_assert_can_view()` in the
  internships router lets a student see only their own record and a faculty
  member only their mentees — verified by test, and by the smoke run where a
  faculty account receives `403` for another mentor's student.
- The frontend consumes the *same* permission strings from `/auth/me`, so the
  sidebar cannot drift from what the server allows.
- **Permissions that gate a screen must be no wider than the narrowest data on
  it.** `reports:view` guards the admin dashboard, whose activity panel is drawn
  from the audit log. Granting `reports:view` to `FACULTY` therefore leaked
  audit rows to a role explicitly denied `audit:view` — caught by driving the
  API with a faculty token rather than by reading the matrix. Fixed on both
  sides: `FACULTY` no longer holds `reports:view`, and the dashboard builds the
  activity panel only for callers who also hold `audit:view`, so a coordinator
  (who legitimately needs `reports:view`) receives zero audit rows.

JWT access tokens last 60 minutes; refresh tokens 14 days. The API client
refreshes once on a `401`, retries the original request, and emits a
`campushub:signed-out` event if that fails.

---

## 6. Storage abstraction

Business tables reference `files.id` — never a path or a bucket.

```
app/storage/base.py     StorageBackend ABC: save / url / delete / open
app/storage/local.py    LocalStorage — dev; served at /media, path-traversal guarded
app/storage/s3.py       S3Storage — lazily imports boto3, prefers IAM roles,
                        pre-signs URLs when no CloudFront base URL is set
```

`get_storage()` picks one from `STORAGE_BACKEND`. Moving to S3 in production
touches no business code. `services/files.save_upload()` centrally validates
content type and size and records a SHA-256 checksum.

---

## 7. Backend layering

```
api/v1/*.py     HTTP only: parse, authorise, delegate, serialise
services/*.py   Business logic; framework-agnostic and unit-testable
models/*.py     SQLAlchemy 2.0 typed mappings
schemas/*.py    Pydantic contracts (never expose a model directly)
```

Conventions worth knowing:

- **Enums as `VARCHAR` + `CHECK`** (`native_enum=False`). Adding a value is a
  plain migration rather than `ALTER TYPE`, which matters because most of these
  vocabularies will grow.
- **One error envelope.** `core/errors.py` maps domain exceptions
  (`NotFoundError`, `BusinessRuleError`, `PermissionDeniedError`, …) plus
  validation and integrity errors to `{"error": {code, message, details}}`.
- **Audit at the call site.** `services/audit.record()` stages a row in the
  caller's transaction, so the audit entry and the change it describes commit or
  roll back together. Mentor overrides, allocation runs and evaluations all
  carry structured `meta`.
- **Explicit constraint naming** via `NAMING_CONVENTION`, so Alembic
  autogenerate stays stable across revisions.

One migration quirk is documented in `0001_initial_schema.py`:
`departments.hod_faculty_id` ↔ `faculty.department_id` is a cycle, so that
foreign key is added with `op.create_foreign_key()` after both tables exist.

---

## 8. Frontend structure

```
components/ui/       44 exported primitives — the whole visual vocabulary
components/layout/   AppShell, Sidebar, Topbar, route guards
features/<domain>/   Screens; compose primitives, never restyle from scratch
lib/                 api (fetch + refresh) · auth · theme · navigation · format
types/               Hand-written mirrors of the API contracts
```

- **Design tokens, not hex values.** `styles/index.css` defines semantic tokens
  as RGB triples; `tailwind.config.js` maps them to utilities so
  `<alpha-value>` works. `.dark` redefines the same names. A component writes
  `bg-surface text-ink`, never `#0F172A`.
- **Status colour is centralised.** `StatusBadge` maps every backend status
  vocabulary to a tone, so one status never renders two colours on two screens.
- **Every list has four states.** Loading (skeleton), error (with retry), empty
  (explaining what would appear), and content.
- **`min-w-0` on `Card` and scroll wrappers.** As grid/flex children, the default
  `min-width: auto` lets a wide table stretch its container instead of scrolling
  inside it. This was a real bug found by measuring `scrollWidth` on every route
  at 375px.
- **One quoting gotcha, documented in the Tailwind config.** A family name
  containing a digit must stay quoted — unquoted `Source Sans 3` is invalid CSS
  and the browser drops the entire `font-family` declaration.

---

## 9. Notifications

`services/notifications.notify()` is the only way a notification is created.
Phase 1 writes rows that the topbar bell polls; an email or SMS transport
subscribes to the same function without touching a single call site.
Announcement fan-out resolves its audience server-side
(`ALL`, `DEPARTMENT`, `PROGRAM`, `SEMESTER`, `MENTEES`, `ROLE`) so audience
scoping is never client-trusted.

---

## 10. What Phase 2 attaches to

| Work | Attachment point |
|---|---|
| Merit allocation | Implement `MeritAllocation.allocate()`, set `is_available = True` |
| Grade boundaries | Extend `compute_totals()`; `final_grade` columns already exist |
| Minor ranking | `MinorProgram.rules` JSON + a registered strategy |
| Real-time chat | `mentor_meetings.thread_key`; add a WebSocket route |
| Email / SMS | Subscribe a transport to `services/notifications.notify()` |
| S3 + CloudFront | `STORAGE_BACKEND=s3`; no business-code change |
| Bulk import | `services/` + a router; models already carry the needed uniqueness |
| SSO | Replace `_authenticate()` in `api/v1/auth.py`; RBAC is unaffected |
