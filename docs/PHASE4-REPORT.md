# CampusHub — Phase 4 Implementation Report

Phase 4 was scoped as "turn CampusHub into a polished, deployable MVP". This
report says what was actually done, and — more usefully — what was **not**.

Every claim is labelled:

| Label | Meaning |
|---|---|
| **IMPLEMENTED** | In the codebase and working |
| **VERIFIED** | Exercised end to end and observed working |
| **CONFIGURABLE** | Supported; the values are an operator or faculty decision |
| **REQUIRES FACULTY CONFIRMATION** | A university policy question, not a code question |
| **FUTURE INFRASTRUCTURE** | Deliberately not built |

**Tests: 296 → 405, all passing.** That is a quality signal, not a
production-readiness claim. See [§11](#11-honest-status).

---

## 1. Features completed

### Elective registration rounds — **VERIFIED**

The largest gap. Elective registration was a pair of dates on each course
offering, which cannot express *"this round covers Semester IV of these
programmes, opens Monday, closes Friday, and is locked by the coordinator once
demand is in"*.

A round is now a first-class row (`elective_registration_windows`) and it is the
**authority**:

```
DRAFT → OPEN → LOCKED → ALLOCATED → PUBLISHED → CLOSED
          |       |          |            |
    may submit  frozen  run allocation  results visible
```

The student-facing state — `NOT_OPEN · OPEN · SUBMITTED · LOCKED · ALLOCATED ·
CLOSED` — is **derived**, never stored, from the round, the clock and the
student's own rows, so it cannot drift out of step with them.

**The backend decides.** Every write calls `assert_can_submit()`. A stale tab, a
clock skewed by a day, or a hand-written request is refused with the real
reason. Verified against the seeded database:

```
OE3 state=LOCKED · Preferences are locked while allocation is prepared.
POST /electives/preferences → 409: Preferences are locked while allocation is prepared.
```

Eligibility is narrowed by programme, semester and division — the same
vocabulary the curriculum uses — so a round can span an Open Elective basket
across programmes or narrow to a few divisions of one, with nothing hard-coded.

Publishing notifies **every** student in the round, including those who were not
allocated a seat: silence after a deadline is its own kind of failure.

### Unified student profile — **VERIFIED**

One authorised view assembling Personal · Academic · Internship · Documents ·
Evaluation · Mentor. Verified against the seeded data:

```
Aarav Desai · 22BIT001 · B.TECH-ICT · SoT · Sem 6 · Div A
curriculum 2022-R1 (PUBLISHED) · CPI 8.42
internships: Summer Internship, COMPLETED, 88%
documents: 12 expected, 1 not submitted
evaluation: FACULTY_MENTOR 87.2/100
```

Authorisation is per **section**, not per endpoint. "Staff" is far too wide a
rule: a club administrator has no business reading an internship evaluation.
Observed:

| Viewer | Result |
|---|---|
| The student themselves, their mentor, their department admin, super admin | full profile |
| An ICT **Open Elective** coordinator | `personal` + `academic` only — no evaluation, no mentor |
| A **CSE** Summer Internship coordinator | 403 |
| Club admin, another student | 403 |

The response carries `visible_sections`, so the UI hides a tab the caller may
not see rather than rendering an empty one that looks like missing data.

### Internship variants — **IMPLEMENTED**

The 16 internship programmes generated in Phase 3B (CSSI ×6, **Rural
Internship** ×1 for Petroleum, Summer ×7, **Industrial Training** ×2 for the
2020-scheme cohorts) all run through the one engine and are reachable through
the existing student and faculty screens. No department has its own code path.
Rural Internship keeps its own name, as required.

---

## 2. Remaining limitations

Things a demo will not show, stated plainly:

1. **Event discovery page (§17) was not rebuilt.** The existing events list,
   registration, waitlist and auto-promotion all work and are now covered by
   tests, but the polished discovery surface — Upcoming / This Week / Registered
   / Interested / Past with filters — was not built.
2. **Verification queues (§26) were not built** as dedicated screens. The
   underlying review endpoints exist and work; the consolidated "Pending
   Certificates" queue does not.
3. **Audit log filters (§27)** were not added. The audit log is written to
   correctly and is permission-gated; its UI still lacks actor/action/date-range
   filtering.
4. **The coordinator round-management UI was not built.** The API is complete
   and tested; a coordinator currently drives rounds through it, not through a
   screen. The student side of rounds *is* wired into the UI.
5. **Responsive and accessibility passes (§36–37) were not systematically
   done.** New pages follow the existing patterns (scroll containers on tables,
   `aria-label` on progress bars, semantic headings), but no breakpoint-by-
   breakpoint audit at 375/768/1024/1440 was performed and no screen-reader
   testing was done. **Do not claim WCAG AA.**
6. **No browser-based testing.** Everything was verified through the API and the
   test suite. The build compiles and types check; the rendered UI was not
   clicked through.
7. **Rate limiting on login** does not exist. **FUTURE INFRASTRUCTURE.**
8. **Upload malware scanning** does not exist. **FUTURE INFRASTRUCTURE** —
   documented in `docs/DEPLOYMENT.md` §4 with two concrete options.

---

## 3. Database changes

Migration **`0008_registration_windows`**. Applied, and verified to
**round-trip** (downgrade → upgrade) against the live database.

**New table `elective_registration_windows`** — code, title, component type,
status, opens/closes, eligibility (semesters, programmes, divisions), preference
limits, lifecycle timestamps, department scope.

**`course_offerings.registration_window_id`** — links an offering to its round.

### Indexes: six were drafted and all six removed

The draft added composite indexes for the dashboard queries. Checking `0001`
first showed every one of them was redundant:

| Drafted | Why it was dropped |
|---|---|
| `ix_events_status_start` | **already exists verbatim** |
| `notifications(user_id, is_read)` | exists as `ix_notifications_user_read` |
| `students.user_id` | already unique-indexed by the column's constraint |
| `elective_preferences(student_id, component_id)` | leading column already indexed |
| `elective_allocations(offering_id, status)` | leading column already indexed |
| `students(department_id, division)` | leading column already indexed |

Redundant indexes cost write throughput and buy nothing. **No new indexes were
added** beyond the new table's own and its foreign key.

---

## 4. API changes

| Route | Purpose |
|---|---|
| `GET /electives/admin/windows` | rounds visible to the caller, with live demand counts |
| `POST /electives/admin/windows` | create a round (always DRAFT) |
| `PATCH /electives/admin/windows/{id}` | edit — refused once allocated or published |
| `POST /electives/admin/windows/{id}/offerings` | attach courses — draft only |
| `POST /electives/admin/windows/{id}/status` | drive the lifecycle; publishing notifies students |
| `GET /student-profile/{id}` | the unified profile, authorised per section |

`GET /electives/components/{id}/workspace` now returns `registration_state`,
`registration_label`, `registration_reason`, `opens_at` and `window_title`.

**New dependency `require_permission_or_coordination`.** Only department admins
held `electives:manage`, so a *scoped* elective coordinator — plain faculty with
a coordinator grant — was locked out of the module they run. The guard admits
either, and the handler still narrows to the caller's own department.

---

## 5. Frontend changes

- **`StudentProfilePage`** (409 lines) — tabbed profile; tabs are driven by the
  backend's `visible_sections`, never by the role held in the browser.
- **Students list** now links each row to the profile.
- **`ElectiveWorkspacePage`** reports the backend's registration decision and
  its reason, rather than computing its own from a countdown.
- **Types** — `RegistrationWindow`, `StudentRegistrationState`,
  `StudentProfile` and its section shapes; `ElectiveWorkspace` extended.

`tsc -b` clean · `vite build` succeeds (567 kB / 150 kB gzipped).

---

## 6. Security improvements

A review of the file-access path found **two real vulnerabilities**, both fixed.

### Unauthenticated document exposure — **FIXED**

Uploads were served from a public `/media` static mount. **Every stored
document — internship certificates, offer letters, weekly reports — was
readable by anyone who knew or guessed its object key, with no login at all.**
The mount is gone.

### IDOR on file metadata — **FIXED**

`GET /files/{id}` had **no authorisation check** and returned that public URL.
Any signed-in user could walk the id space and collect other students'
certificates. It now authorises exactly as a download does. Verified:

```
intruder → GET /files/{id}  → 403
owner    → GET /files/{id}  → 200, and the storage key is absent from the body
```

### Also hardened

- **Magic-byte validation.** `Content-Type` comes from the browser and is
  trivially forged; a "PDF" starting with `<script>` is now rejected.
- **Filename sanitisation.** Names are stripped of path separators, quotes,
  newlines and control characters before storage and before being echoed in a
  `Content-Disposition` header (header-injection vector).
- **Signed, expiring links** (HMAC, 15 min) replace storage URLs — issued only
  after the caller passes the same authorisation check.
- `X-Content-Type-Options: nosniff` and `Cache-Control: private, no-store` on
  downloads.

### Authorisation flaw found by a test

The first draft of the student profile granted access to anyone holding a
**mentor grant for the department**. A test asserting that a mentor of student A
cannot read student B's record failed — correctly. Mentor access is now earned
**per student**: a mentorship assignment, or being the mentor recorded on that
student's own internship.

### Verified by 30 API-level security tests

Anonymous access · forged tokens · refresh-token-as-access-token · login user
enumeration · password hash leakage · cross-student IDOR · audit-log
permissions · mass assignment (a student cannot promote themselves by posting
`cpi`, `current_semester` or `roll_number`) · SQL injection · clean 404s with no
stack traces · and the scoped-role pairs: Summer ≠ CSSI, ICT ≠ CSE, mentor ≠
coordinator.

---

## 7. Performance improvements

Measured against the seeded dataset (1,682 students, 526 courses, 12 curriculum
versions), counting SQL statements per request.

| Endpoint | Before | After |
|---|---|---|
| **Elective components** (student) | 95 ms · **221 queries** | 84 ms · **39 queries** |
| **Curriculum explorer** (admin) | 97 ms · **70 queries** | 18 ms · **37 queries** |
| Student dashboard | 51 ms · 57 | 41 ms · 57 |
| Student profile | — | 40 ms · 39 |
| Student list (paginated) | 33 ms · 56 | 30 ms · 56 |
| Notifications | 4 ms · 4 | 6 ms · 4 |

Two real N+1s fixed:

1. **Scope resolution** re-fetched the same departments and programmes for every
   offering in a student's elective list. Memoised per session — 82% fewer
   queries.
2. **The curriculum list** loaded every component row of every curriculum just
   to count them. Replaced with a filtered `COUNT` — 81% faster.

A third was caught before it shipped: the round summary loaded every covered
student to call `len()` on them, which timed out on ICT's cohort. Counting moved
into SQL.

No Redis. No caching layer. The queries were the problem.

---

## 8. AWS readiness

Documented in **`docs/DEPLOYMENT.md`** and **`.env.production.example`**.
Architecture: CloudFront + S3 (frontend), ALB + EC2 (backend), RDS PostgreSQL,
S3 (documents), CloudWatch. No Kubernetes, no microservices, no Redis.

| Concern | State |
|---|---|
| Storage abstraction local ⇄ S3 | **IMPLEMENTED** — one env var |
| Environment-driven config | **IMPLEMENTED** |
| Migrations | **VERIFIED** — 8 revisions, round-trips |
| Health endpoint for the ALB | **VERIFIED** — `GET /health` → 200 |
| Authorised file access | **VERIFIED** |
| TLS, secrets, backups, alarms | **CONFIGURABLE** — operator decisions |
| Autoscaling, malware scanning, login rate limiting | **FUTURE INFRASTRUCTURE** |

One deployment trap is called out explicitly: `S3_PUBLIC_BASE_URL` must be
**empty** for the documents bucket. Setting it makes the backend hand out a
CloudFront path instead of an authorised download — re-opening the exact hole
Phase 4 closed.

---

## 9. Tests added

**109 new tests, 296 → 405.**

| File | Tests | Covers |
|---|---:|---|
| `test_api_security.py` | 30 | the §28 review, driven through HTTP |
| `test_file_security.py` | 29 | magic bytes, filename sanitisation, signed tokens |
| `test_registration_windows.py` | 24 | state machine, deadline enforcement, eligibility |
| `test_student_profile.py` | 13 | per-section authorisation |
| `test_e2e_scenarios.py` | 13 | the §41 scenarios |

Scenarios verified: Open Elective 90 → `[75,15]`, 150 → `[75,75]`,
151 → `[75,75,1]`; the round driving a student through open → submitted →
locked → allocated with **no result leaking before publication**; Core Elective
10+10+10+10 = 40 running as one class with no 75 ceiling, and the same total
across two divisions; event waitlist → cancellation → **auto-promotion with a
notification**; and the RBAC boundary pairs.

---

## 10. Demo accounts

Unchanged, password `Campus@123`:

| Role | Email |
|---|---|
| `SUPER_ADMIN` | `admin@campushub.example.com` |
| `DEPARTMENT_ADMIN` + Minor/Elective coordinator (ICT) | `rakesh.bhatt@campushub.example.com` |
| Summer Internship coordinator (ICT) | `priya.nair@campushub.example.com` |
| CSSI coordinator (ICT) | `sneha.iyer@campushub.example.com` |
| NPTEL coordinator (ICT) | `meera.krishnan@campushub.example.com` |
| Summer coordinator (**CSE**) — same module, different department | `kunal.shah@campushub.example.com` |
| Mentor only, no coordination | `anand.mehta@campushub.example.com` |
| `CLUB_ADMIN` | `clubs@campushub.example.com` |
| Student, Sem VI | `aarav.desai.001@campushub.example.com` |
| Student, Sem IV — live Open Elective round | `ananya.menon.011@campushub.example.com` |

Seeded rounds span the lifecycle so a demo shows every state without waiting for
a clock: **OE1 open** (202 of 203 submitted), **OE3 locked**, **OE4 published**
(203 allocated), **PCE1 open**.

---

## 11. Honest status

**Do not present this as production-ready.** It is a credible MVP with two real
vulnerabilities closed and measured performance, and it is not yet a system to
put in front of a thousand students.

Before real use, in order:

1. **Rate limiting on `/auth/login`** — nothing throttles password attempts.
2. **Malware scanning on uploads.**
3. **A real password policy and reset flow** — seeded accounts share one
   password by design; that is a demo affordance.
4. **A browser and accessibility pass** — not done; no WCAG claim is made.
5. **A backup restore rehearsal** and CloudWatch alarms.
6. **A load test at real concurrency** — the dataset has been exercised, hundreds
   of simultaneous users have not.

### University policies still requiring faculty confirmation

Carried forward from Phase 3B, unchanged and still flagged in the database:

- **Biotechnology Sem III–VIII** — official structure stops at Sem II; the
  curriculum stays a DRAFT and reaches no student.
- **Electrical 2024-28** — no published structure exists; none was invented.
- **Climate Science & Sustainable Engineering** — admits students, has no
  curriculum; the programme was not created.
- **Chemical "Program Elective 3" printed twice** — imported verbatim with a
  conflict note.
- **Minor allocation "pro rata basis"** — the denominator is never defined;
  CPI ranking is implemented, pro-rata is left unset.
- **Division counts** — no official source; derived from seat intake and
  labelled as derived.
- **Open Elective 40-minimum / 75-per-section** — departmental, not public;
  unchanged.
