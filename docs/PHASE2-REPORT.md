# CampusHub — Phase 2 Implementation Report

Phase 2 closed the gap between "the data exists" and "the workflow is usable":
documents now have a real lifecycle, progress is computed from those documents
rather than stored as a number, and Minor Specialisation has a complete,
auditable allocation round.

The Phase 1 elective-capacity work was **not** touched, and is re-verified below.

---

## 1. Files changed

### New files

| File | Lines | Purpose |
|---|---:|---|
| `backend/app/services/documents.py` | 467 | Expected-vs-actual documents, review workflow, document-driven progress, protected file URLs, per-file authorisation |
| `backend/app/services/minors.py` | 219 | Minor ranking policy + allocation round |
| `backend/app/api/v1/roles.py` | — | Coordinator role matrix, assign, revoke |
| `backend/app/tests/test_documents.py` | — | 19 tests |
| `backend/app/tests/test_progress.py` | — | 14 tests |
| `backend/app/tests/test_minor_ranking.py` | — | 12 tests |
| `frontend/src/components/documents/DocumentGroups.tsx` | 316 | Shared expected/actual document panel + progress, used by both the student page and the faculty drawer |
| `frontend/src/features/admin/MinorAllocationTab.tsx` | 232 | Coordinator allocation round screen |
| `frontend/src/features/admin/RoleAssignmentsPage.tsx` | — | Which faculty holds which coordinator role |

### Modified — backend

`app/models/enums.py` · `app/models/internships.py` · `app/models/identity.py` ·
`app/models/academics.py` · `app/api/v1/internships.py` · `app/api/v1/minors.py` ·
`app/api/v1/files.py` · `app/api/v1/dashboard.py` · `app/api/v1/electives.py` ·
`app/api/v1/roles.py` · `app/api/v1/admin.py` · `app/schemas/internships.py` ·
`app/schemas/minors.py` · `app/services/scope.py` · `app/services/sections.py` ·
`app/core/rbac.py` · `app/seed/data.py` · `app/seed/run.py`

### Modified — frontend

`features/internships/InternshipRecordPage.tsx` ·
`features/internships/StudentDetailDrawer.tsx` ·
`features/internships/MyStudentsPage.tsx` ·
`features/admin/MinorAdminPage.tsx` · `features/admin/ElectiveAdminPage.tsx` ·
`components/ui/Badge.tsx` · `components/layout/AppShell.tsx` ·
`lib/api.ts` · `lib/format.ts` · `lib/navigation.ts` · `types/index.ts`

---

## 2. Migrations added

| Revision | What it does |
|---|---|
| `0002_faculty_role_assignments` | `faculty_role_assignments` table — coordination scoped by (domain × department) |
| `0003_elective_sections` | `course_sections`; per-family capacity columns on `course_offerings`; `section_id` on `elective_allocations` |
| `0004_document_lifecycle` | `week_number`, `submitted_at`, `reviewed_by_user_id`, `reviewed_at`, `review_comment`, `revision` on `internship_documents`; `revision` on `internship_reports`; FK to `users` |

`alembic downgrade base && alembic upgrade head` round-trips cleanly and
`alembic check` reports **no drift**.

`MinorApplicationStatus.WAITLISTED` needed **no migration**: enums are stored as
`VARCHAR + CHECK` with `native_enum=False`, and this column carries no CHECK
constraint, so a new value is a pure Python change.

---

## 3. API routes added / changed

### Added

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/internships/enrollments/{id}/documents/expected` | Every EXPECTED document, including `NOT_SUBMITTED` |
| `POST` | `/internships/documents/{id}/review` | `start_review` / `verify` / `reject` |
| `GET` | `/internships/enrollments/{id}/progress` | Document-driven progress + named blockers |
| `GET` | `/minors/ranking-fields` | Fields a minor may rank on |
| `PUT` | `/minors/{id}/ranking-policy` | Declare this minor's ranking criteria |
| `GET` | `/minors/{id}/allocation/preview` | Dry run — nothing written |
| `POST` | `/minors/{id}/allocation/run` | Commit seats in rank order |
| `GET/POST/DELETE` | `/admin/roles/*` | Coordinator role matrix, assign, revoke |
| `GET/POST` | `/electives/admin/viability`, `/offerings/{id}/sections`, `/distribute`, `/sections/move` | Section planning |

### Changed

- `GET /files/{id}/download` — **security fix.** Previously any staff role
  (including `CLUB_ADMIN`) could download any file. Now resolved back to the
  owning enrolment and scoped to the student, their mentor, and the coordinators
  of that programme.
- `POST /internships/enrollments/{id}/documents` — resubmission replaces the
  existing row, increments `revision`, clears the previous reviewer.
- `GET /internships/enrollments/{id}` — now returns `document_groups` and
  `progress`.
- `GET /dashboard/student` — action items and progress now come from real
  document state.
- `GET /admin/roles` → renamed `GET /admin/permissions` (route collision).

**141 operations across 114 paths.**

---

## 4. UI changes

**Document panel (shared).** One component renders every expected document for
the programme, grouped into Weekly Reports / Required Documents / Final Report /
Other. A missing mandatory item stays visible as a dashed `Not submitted` card —
it is never silently absent, and it never carries a placeholder link.

- **Student:** sees status, the reviewer's rejection reason and timestamp, and an
  `Upload` / `Replace file` button. Weekly reports route to the Reports tab with
  the week number pre-filled, because a report carries a written summary too.
- **Faculty / coordinator:** same panel with `Start review`, `Verify`, `Reject`.
  Rejection opens a modal that **requires** a reason. `View PDF` fetches through
  the authenticated API and opens a blob — the storage path is never exposed.
- **Progress** shows `n of m stages complete` with the specific blockers listed
  ("Week 3 outstanding", "Certificate: document is rejected"), replacing the
  stored percentage.
- The Proof of Work / Documents tab badge counts **outstanding required items**,
  so missing work is visible before the tab is opened.

**Minor allocation round.** New coordinator tab showing the declared ranking
criteria as an explicit chain, the seat arithmetic, and the full ranked list with
the cut-off marked. Preview is a dry run; running the round is confirmed in a
modal and notifies every applicant.

**Elective admin.** Viability & sections tab: per-division breakdown, whether a
course runs, and the planned section split.

---

## 5. Tests

| File | Tests | Covers |
|---|---:|---|
| `test_documents.py` | 19 | `NOT_SUBMITTED` as a first-class state, satisfying vs pending statuses, review transitions, resubmission guards, protected URLs, the 4 × 25 summer rubric |
| `test_progress.py` | 14 | Missing/unverified documents blocking their stage, one missing week keeping the reporting stage open, aggregate counting |
| `test_minor_ranking.py` | 12 | Unconfigured programme refuses to rank, unknown field/direction rejected, declared criteria actually order applicants, missing CPI never outranks a recorded one, determinism |
| **New total** | **45** | |
| Pre-existing (unchanged) | 99 | allocation 13, eligibility 18, internship engine 10, rbac 20, scope 11, sections 19, security 8 |

### Final test count: **144 passing, 0 failing**

Beyond the unit suite, four live-API scripts were run against the containerised
stack with the full 814-student seed:

| Suite | Result |
|---|---|
| Document lifecycle (upload → review → reject → resubmit → verify, access control, file protection) | all checks passed |
| Minor workflow (policy, preview, commit, access control) | 11 / 11 |
| Role & scope smoke (9 roles × dashboards, module × department isolation, audit isolation) | 23 / 23 |
| Do-not-regress (elective capacity + no CPI in electives) | 12 / 12 |

Also audited in the browser: WCAG AA contrast across 8 views × 2 themes (0
failures), horizontal overflow at 375 px across the changed routes (0 failures),
0 application console errors.

---

## 6. Policies that remain intentionally configurable

These are **deliberately not decided in code**. CampusHub records the
institute's rule; it does not invent one.

| Policy | Where it lives | Default shipped |
|---|---|---|
| Minor ranking formula | `MinorProgram.rules["ranking"]["criteria"]` | **None.** An unconfigured minor refuses to run a round rather than guessing. The seed carries a worked example clearly labelled as demo. |
| Minor eligibility thresholds | `MinorProgram.min_cpi`, `max_backlogs`, `eligible_from_semester`, `excluded_department_ids` | Per-programme rows |
| Summer / CSSI rubric | `evaluation_criteria` rows | Summer = Final Report 25 + Presentation 25 + Weekly Submissions 25 + Industry Mentor 25 |
| Which stages require a document | `InternshipStage.requires_document` + `document_type` | Per-programme config |
| Report cadence and count | `InternshipProgram.report_frequency`, `expected_report_count` | Per-programme config |
| Elective minimum to run / section capacity | `CourseOffering.min_students_to_run`, `section_capacity`, `allow_multiple_sections` | OE 40 / 75 per section / multiple; Core 40 combined / no ceiling / single class |
| Elective allocation strategy | strategy registry | `preference_order`; `merit` registered but `is_available=False` |
| Storage backend | `StorageBackend` ABC | `LocalStorage` in dev, `S3Storage` in production |

**CPI/CGPA is used only by Minor Specialisation.** Verified by AST walk across
all elective allocation and section-planning modules: zero executable references.

---

## 7. Corrections applied after the first build

### 7.1 CSSI runs on a semester window

CSSI carried `target_semester = 1`, which is only a *floor* — every student from
Semester I upward could see it. It is now a window with three phases:

| Student | Phase | What they can do |
|---|---|---|
| Semester I | `HIDDEN` | CSSI does not appear at all |
| Semester II | `ANNOUNCED` | Sees it, can line up an NGO over the break. Enrolment and every submission are refused with an explanation. |
| Semester III | `ACTIVE` | Certificate and all submissions open. Once the certificate is verified, the coordinator allocates a presentation slot. |
| Semester IV+ | `CONCLUDED` | No longer open to them |

The presentation slot is refused (409) until the certificate is verified.

### 7.2 Coordinator and Mentor are separately assignable

A scoped assignment is now `faculty → role → module → department`. The two roles
are independent grants: neither implies the other, one person may hold several,
and permissions resolve as the **union** so revoking one never removes another.

**Security fix — cross-module scope leak.** `assert_coordinates` short-circuited
on the coarse permission, and `Role.INTERNSHIP_COORDINATOR` carries
institution-wide `internships:manage`. The ICT *Summer Internship* coordinator
could therefore manage ICT's *CSSI*. Only genuinely institution-wide roles now
bypass; everyone else needs a matching assignment.

### 7.3 Minor coordinator scope stays a policy decision

An earlier draft read "Minor coordinator for ICT" as *the minors ICT offers*,
and added an ICT Data Science minor to make that reading work. Both were wrong:
the reading was an assumption, and the minor was an invented offering. The minor
has been removed, the demo catalogue is labelled as demo data in the seed, and
the interpretation is now configuration:

| `MINOR_COORDINATOR_SCOPE` | Means |
|---|---|
| `OFFERING` | The minors the coordinator's department offers — its seats, ranking policy, allocation rounds |
| `APPLICANT` | Applications from students of the coordinator's department, whichever department offers the minor |
| `EITHER` **(default)** | A match on either side is enough |

All three are covered by `test_minor_scope.py`. **No minor is added to the
catalogue unless the university confirms it.**

### 7.4 Seven dead links produced a 404

Dashboard action items, stat cards, calendar deadlines, elective notifications
and a seeded announcement all pointed at `/academics/electives` — a path that has
not existed since Open and Core were split into separate screens. Each now
resolves the correct screen from the component's own type
(`services/serializers.elective_path`), and the old path redirects.

### 7.5 An expired session stranded the user

The fetch wrapper only ended a session on 401 *if a refresh token existed*. With
none, the 401 fell through and the app rendered its full shell with
"Authentication credentials were not provided" in the middle and no way out. Any
unrecoverable 401 now clears the session and redirects to sign-in.

---

## 8. Known limitations

1. **Industry mentor marks have no external portal.** The rubric component is
   marked `is_external` and the student is blocked from entering it (403), but
   the marks are currently recorded by faculty on the mentor's behalf. A
   token-based external form is not built.
2. **`View PDF` fetches the whole file into memory** as a blob before opening it.
   Fine for reports and certificates; a large video would want a streamed
   short-lived signed URL instead.
3. **No virus scanning or content sniffing on upload.** Extension and size are
   checked; the bytes are not.
4. **Minor waitlist does not auto-promote.** If an allocated student withdraws,
   the seat is freed but the next waitlisted applicant is not promoted
   automatically — a coordinator re-runs the round.
5. **Notifications are in-app only.** 27 real events emit them; there is no
   email or push transport.
6. **`docker-compose.yml` bakes the code into the images.** Bind mounts fail with
   `EDEADLK` under iCloud-synced folders such as `~/Desktop`. Live reload is the
   opt-in `docker-compose.dev.yml` overlay.
7. **Progress counts stages equally.** A stage is complete or it is not; there is
   no weighting, because no weighting has been specified.
8. **Seed data is demo-only** — fake names, `campushub.example.com` addresses,
   generated PDFs.
