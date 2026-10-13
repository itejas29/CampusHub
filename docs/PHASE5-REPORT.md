# CampusHub — Phase 5 Implementation Report

Phase 5 narrowed the target to **the ICT department, working end to end**, on
faculty guidance, and built the two things that were blocking that: a Head of
Department who appoints the coordinators, and registration rounds a coordinator
can actually run. **Allocation after a round locks is not part of this phase.**

Every claim is labelled the same way as the Phase 4 report:

| Label | Meaning |
|---|---|
| **IMPLEMENTED** | In the codebase and working |
| **VERIFIED** | Exercised end to end and observed working |
| **AS DESCRIBED BY THE DEPARTMENT** | A practice the project team was told about, not a written rule |
| **NOT BUILT** | Deliberately left for later |

**Tests: 532 → 624, all passing.**

---

## 1. Head of Department — **VERIFIED**

There was no HoD. `departments.hod_faculty_id` existed and nothing read it, and
coordinator assignment hung off `faculty:manage` with no department check, so
any internship coordinator could appoint anyone in any department.

- New `Role.HOD` and `roles:assign` permission. *Which* department a person
  heads is `departments.hod_faculty_id`; `services/scope.set_hod` keeps that, the
  role and the mentor flag in step.
- The HoD appoints and removes coordinators and mentors **inside their own
  department, from its own faculty**. Institution-wide grants and other
  departments are refused. The registrar's office (super admin) can act anywhere.
- Internship coordinators and Department Admin **can no longer appoint**.
- The HoD **holds no coordinator or mentor role and has no mentees**. Refused on
  role assignment, academic mentor assignment, internship mentor override, group
  lead, and on switching the faculty mentor flag back on.
- The HoD **reads** every module of their department and **changes none**.
- HoD dashboard: who runs each of the seven modules, which have nobody, and the
  department's elective rounds.
- The registrar appoints the HoD from Administration → Departments. A faculty
  member who still has mentees or a scoped role must hand those over first.

Seeded: Dr. Rakesh Bhatt is Head of ICT. Open Electives → Dr. Vikram Joshi, Core
Electives → Prof. Leena Nambiar, Minors → Dr. Priya Nair.
`ict.office@campushub.example.com` holds Department Admin.

## 2. Registration rounds a coordinator can run — **VERIFIED**

The round backend from Phase 4 could not be used by a coordinator: every round
route called `scope.assert_coordinates` without its required arguments, so
anyone but the super admin got a **500**. There was also no screen for it.

- Round routes work for the coordinator of **that elective family in that
  department**, and answer everyone else with a 403.
- **Administration → Registration Rounds**: create a round (slot, student
  semester, courses, dates, preference limits, divisions), open it, change the
  deadline, lock, reopen. The HoD sees the same table read-only.
- A round is refused if it mixes elective families or semesters, is aimed more
  than one semester ahead of the slot, has no courses or programme, or has a
  deadline already past. A course belongs to one round at a time — attaching it
  elsewhere used to pull it silently out of the round students were choosing in.
- Students are notified when a round opens, reopens, or its deadline moves. A
  live round's deadline cannot be moved into the past; that is what Lock is for.

## 3. Early choice filling — **VERIFIED**, **AS DESCRIBED BY THE DEPARTMENT**

Choice filling for a Semester N elective starts mid-way through Semester N−1, so
the timetable can be built over the vacation. The portal refused that student
before the round was even consulted ("opens in semester N").

- `registration.access_for`: a student reaches a slot once the curriculum
  unlocks it, **or** while a round the coordinator has opened covers their
  current semester. With no round there is no early access.
- The coordinator chooses the student semester: N−1 (choosing ahead) or N.
- The student's sidebar, dashboard and elective list follow the round.

Walked through in the browser for both families:

| Family | Coordinator | Slot | Opened to | Result |
|---|---|---|---|---|
| Open Elective | Dr. Vikram Joshi | Open Elective 1, Sem IV | Semester III (203 students) | Notified; a student submitted; deadline moved; locked; reopened |
| Core Elective | Prof. Leena Nambiar | Program Elective 1, Sem V | Semester IV (203 students) | Notified; a student submitted; the Semester V cohort kept its own round and courses |

## 4. Elective Allocation screen scoped — **VERIFIED**

Found while checking the coordinator's view. The slot picker listed every
programme's electives to everyone, and the endpoints behind it asked only for the
coarse `electives:manage` permission. An appointed coordinator was refused on
their own slot, while a Department Admin could read and run allocation for
another department. The picker and every endpoint (preferences, allocations,
viability, run, manual, sections) are now scoped by the slot.

## 5. Fixes made along the way

- **Sign-in tokens tolerate five seconds of clock skew.** A token was rejected
  as "issued in the future" whenever the host clock stepped back between sign-in
  and the next request — observed as an intermittent 401 under Docker Desktop.
- Seeded announcements and notifications are addressed to the students they
  concern (done in the preceding dashboard work, relied on here).

---

## 6. What is not built

| Item | Status |
|---|---|
| Allocation after a round locks, and publishing results | **NOT BUILT** — next |
| Creating a new course offering from the coordinator's screen | **NOT BUILT** — courses are seeded |
| Deleting a draft round | **NOT BUILT** — no endpoint |
| NPTEL / MOOC rounds | **NOT BUILT** — NPTEL keeps its own registration screen |
| Semester promotion | **NOT BUILT** — a round aimed at Semester III stops covering those students once they are in Semester IV |
| HoD and rounds for departments other than ICT | **NOT BUILT** — the code is not ICT-specific, but only ICT is seeded with an HoD and the new coordinators |

## 7. Honest status

- **ICT runs on the 2024-28 scheme alone.** The hand-built 2022 scheme was
  removed from the demo data, so every ICT batch — whatever its admission year —
  is governed by 2024-28 and sees its full semester. The Program Elective
  courses are the subjects the handbook lists per semester; the handbook gives
  one basket for Semester VI and one for Semester VII, so Program Elective 2/3
  share the first and 4/5 the second.
- Two cohorts can be choosing for one slot at once (Semester IV in their own
  round, Semester III ahead). Each sees only its own round's courses; the next
  cohort's are seeded as 2026-27 offerings and left for the coordinator to open.
- The ICT office account is stored as a faculty row, because the existing
  Department Admin logic resolves its department through one. It appears in the
  Faculty Directory as a result.
- The ICT office (Department Admin) can manage rounds as well as the
  coordinators can. That is the pre-existing Department Admin rule, left as is.
- "Mid-way through the semester before" is the department's practice as told to
  the project team. Nothing in the code encodes "mid-semester": the coordinator
  picks the dates.

## 8. Verification

```bash
docker compose exec backend python -m pytest -q        # 624 passed
cd frontend && npx tsc -b && npx vite build
docker compose exec backend python -m app.seed.run --reset
```

Then sign in (password `Campus@123`, all `@campushub.example.com`):

| As | Check |
|---|---|
| `rakesh.bhatt` | HoD dashboard; appoint and revoke a coordinator; rounds are view-only |
| `vikram.joshi` | Create and open an Open Elective round for Semester III |
| `riya.chauhan.031` | Before the round: no Open Electives. After: notified, can choose |
| `leena.nambiar` | Sees only Core Elective rounds and slots |
| `priya.nair` | No "Coordinators & Mentors" screen |
