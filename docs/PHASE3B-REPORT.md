# CampusHub — Phase 3B Implementation Report

**Official PDEU SoT/SoET curriculum expansion.** The portal was already
curriculum-driven for ICT. Phase 3B made that architecture carry ten verified
B.Tech programmes across two schools — without letting any of them inherit
ICT's shape by default.

The Phase 1 elective-capacity rules and the Phase 2 document lifecycle were
**not** touched, and are re-verified in [§15](#15-cross-programme-regression).

Research evidence: **[PHASE3B-RESEARCH.md](PHASE3B-RESEARCH.md)**.

---

## 1. Programmes researched

Ten currently-offered B.Tech programmes, verified against the university's own
course-catalogue payload and the *B.Tech. Admission Rules A.Y. 2026-27* seat
matrix (1,440 seats, total reconciled).

| School | Programme | Seats | Status |
|---|---|---:|---|
| SoT | Information & Communication Technology | 180 | CONFIRMED |
| SoT | Computer Engineering | 300 | CONFIRMED |
| SoT | Computer Science & Business Systems | 60 | CONFIRMED |
| SoT | Electronics & Communication Engineering | 120 | CONFIRMED |
| SoT | Mechanical Engineering | 120 | CONFIRMED |
| SoT | Civil Engineering | 120 | CONFIRMED |
| SoET | Chemical Engineering | 120 | CONFIRMED |
| SoET | Electrical Engineering | 120 | CONFIRMED |
| SoET | Petroleum Engineering | 120 | CONFIRMED |
| SoET | Biotechnology | 120 | CONFIRMED (curriculum partial) |
| — | Climate Science & Sustainable Engineering | 60 | **Admitting, no curriculum published — not created** |

### Three corrections to the brief's assumptions

Building the brief's list verbatim would have created programmes PDEU does not
run:

1. **There is no B.Tech "Computer Science & Engineering."** CSE is the
   *department*; the programme it runs is **Computer Engineering**. The same
   department also runs **CSBS**, which the brief did not list and which has a
   materially different structure.
2. **Automobile Engineering is not offered.** Zero occurrences in the current
   admission policy. It survives only as `24ME437T`, a Program Elective 5 option
   inside Mechanical Engineering.
3. **Electrical and Chemical are School of Energy Technology**, not School of
   Technology — which matters, because Open Elective eligibility is written in
   schools. Two further SoET programmes the brief omitted (Petroleum,
   Biotechnology) were added.

The pre-existing seed's `B.TECH-CSE — "B.Tech in Computer Science and
Engineering"` was therefore not a real programme name, and has been replaced.

---

## 2. Official sources used

All retrieved 28 Aug 2026 from university-controlled hosts (`pdeu.ac.in`,
`api.pdeu.ac.in`). No third-party aggregator was used as a source of truth.

**Policy**
- [B.Tech. Academic Rules (batch 2024 onward)](https://api.pdeu.ac.in/pdpu/resources/btech-academic-rules-2024.pdf) — internships §8, Minor Specialisation Annexure II
- [B.Tech. Admission Rules A.Y. 2026-27](https://api.pdeu.ac.in/pdpu/resources/btech-admission-policy.pdf) — programme list, seat matrix
- [CSSI NGO list](https://api.pdeu.ac.in/pdpu/resources/cssi-info-and-industry.pdf)

**Curricula** — one document per version: ICT 2024-28, Computer Engineering,
CSBS, ECE 2024-28, ECE 2020-24, Civil 2024-28, Mechanical 2024-28, Chemical
2024→, Petroleum 2024-28, Electrical 2020-24, Biotechnology (partial). Full URLs
in the research report §9; every URL is also stored on the `curriculums` row and
surfaced in the UI.

---

## 3. Curriculum versions imported

**11 versions across 10 programmes** — 10 published, 1 held as draft.

| Programme | Version | Batches | Status |
|---|---|---|---|
| ICT | 2024-28 | 2024 onward | PUBLISHED |
| ICT | *2022-R1 (pre-existing)* | 2021–2023 | PUBLISHED, flagged: no public source |
| Computer Engineering | 2024-28 | 2024 onward | PUBLISHED |
| CSBS | 2024-28 | 2024 onward | PUBLISHED |
| **ECE** | **2020-24** | **2020–2023** | PUBLISHED |
| **ECE** | **2024-28** | **2024 onward** | PUBLISHED |
| Civil | 2024-28 | 2024 onward | PUBLISHED |
| Mechanical | 2024-28 | 2024 onward | PUBLISHED |
| Chemical | 2024 | 2024 onward | PUBLISHED |
| Electrical | 2020-24 | 2020–2023 | PUBLISHED |
| Petroleum | 2024-28 | 2024 onward | PUBLISHED |
| Biotechnology | 2023 | 2023 onward | **DRAFT** — source covers Sem I–II only |

ECE's two versions are the load-bearing case: they are not revisions of one
another. Open Electives sit in different semesters, the 2020 scheme has **no
MOOC component at all**, uses Core Electives ×7 rather than Program Electives
×5, has no CSSI, and ends in a 10-credit project rather than 12.

The existing ICT cohort keeps working because its Phase 1 curriculum was given a
bounded window (2021–2023) rather than being overwritten; the 2024/2025 ICT
batches move onto the official 2024-28 structure.

---

## 4. Courses imported

**454 courses** from the researched documents (526 in the database including the
pre-existing ICT elective and MOOC catalogue), of which **60 are shared** across
departments rather than duplicated per programme — Mathematics-1, Environment
Science, Engineering Graphics and similar. A shared course has no owning
department and one row.

Every course carries: code, title, credits, L–T–P split, category
(BSC/ESC/HSC/PC/PE/OE/Pro), theory-practical-project classification, owning
department or `is_shared`, offering school, and specialisation area for
track-based electives.

**659 curriculum components** in total: 511 core, 57 Program/Core Electives,
35 Open Electives, 9 MOOC, 27 internship, 20 project.

---

## 5. Elective rules per programme

| Programme (version) | OE1 | MOOC | OE3 | OE4 | Program Electives | Project |
|---|---|---|---|---|---|---|
| ICT 2024-28 | IV | V | VI | VII | 1 V · 2,3 VI · 4,5 VII | VIII (12) |
| Computer Engg 2024-28 | IV | V | VI | VII | 1 V · 2,3 VI · 4,5 VII | VIII (12) |
| CSBS 2024-28 | IV* | V | VI* | VII* | 1 V · 2,3 VI · 4,5 VII | VIII (12) |
| ECE 2024-28 | IV | V | VI | VII | 1 V · 2,3 VI · 4,5 VII | VIII (12) |
| **ECE 2020-24** | **III** | **none** | **V** | **VI** | **CE 1,2 V · 3,4 VI · 5,6,7 VII** | VIII (10) |
| Civil 2024-28 | IV | V | VI | VII | 1 V · 2,3 VI · 4,5 VII | VIII (12) |
| **Mechanical 2024-28** | IV | V | VI | VII | **1 V · 2 VI · 3,4,5 VII** | VIII (12) |
| Chemical 2024 | IV | V | VI | VII | 1 V · 2,3 VI · 4,5 VII | VIII (13) |
| Petroleum 2024-28 | IV | V | VI | VII | 1 V · 2,3 VI · 4,5 VII | VIII (12) |
| **Electrical 2020-24** | **III** | **none** | **V** | **VI** | 1 V · 2,3 VI · 4,5 VII | VIII (13) |

\* CSBS Open Electives are **prescribed named courses** (Financial Management;
Business Communication & Value Science IV; Marketing Research & Marketing
Management), not a cross-school basket — modelled as `selection_mode = DIRECT`
and flagged.

Mechanical's 1 / 1 / 3 distribution is the specific case a test now pins, because
flattening it to ICT's 1 / 2 / 2 is the most likely future regression.

### Cross-programme Open Elective eligibility — CONFIRMED

Quoted verbatim from the Electrical course structure:

> "This open elective will be offered to the students enrolled in B.Tech.
> programs of School of Technology **other than Electrical Engineering**."
> "Student of Electrical Engineering will have a choice for one open elective
> course from the basket of open electives announced by **the other departments
> of School of Technology / other schools of university**."

Stored declaratively on each component:

```json
"eligibility": {
  "eligible_schools": ["SoET", "SLS", "SoM", "SoL"],
  "exclude_own_department": true,
  "rule_source": "B.Tech. Electrical Engineering course structure: …"
}
```

`course.department_id == X` cannot express this. A Mechanical course has a
different department id from ICT, so a department-only check would wrongly offer
it for an ICT "From Other School" slot — same school. That exact regression is a
test.

---

## 6. NPTEL / MOOC rules

| Programme | MOOC component | Semester |
|---|---|---|
| ICT, Computer Engg, CSBS, ECE 2024-28, Civil, Mechanical, Chemical, Petroleum | "Open Elective 2 (NPTEL/SWAYAM/MOOC)", 3 credits | **V** |
| **ECE 2020-24, Electrical 2020-24** | **none — confirmed absent** | — |
| Biotechnology | unknown (document truncated) | — |

Semester V is right for the 2024-model programmes — but *because the curriculum
says so*. Two of eleven curricula have no MOOC slot at all, so the brief's
warning against assuming Sem V was well founded.

---

## 7. Internship rules

Authoritative source: **Academic Rules §8**.

> "**Civic & Social Service Internship (CSSI):** A student is required to undergo
> 3 weeks … **at the end of the second semester**." · "Report submission & Viva
> examination will be held **at the start of the subsequent odd semester**."

This *confirms* the existing CSSI window model. `HIDDEN → ANNOUNCED (II) →
ACTIVE (III) → CONCLUDED` is unchanged, and now verified against policy rather
than assumed.

| Programme | Sem III social internship | Final internship |
|---|---|---|
| ICT, Computer Engg, CSBS, ECE 2024-28, Civil, Mechanical, Chemical | CSSI (1 cr) | Summer Internship, Sem VII |
| **Petroleum** | **Rural Internship** (`24INT152T`) | Summer Internship, Sem VII |
| **Biotechnology** | **Sem II** (`20TP110`) — source conflict | unknown |
| **ECE 2020-24, Electrical 2020-24** | **none** | **Industrial Training / IEP, Sem VI** |

**16 internship programmes** are now generated from the curricula — one engine,
configuration only. No department got its own code path:

```
CSSI × 6 departments · Rural Internship × 1 (Petroleum)
Summer Internship × 7 · Industrial Training × 2 (the 2020-scheme cohorts)
```

Biotechnology gets none, because its curriculum is a draft. Summer Internship
keeps the confirmed 4 × 25 = 100 rubric.

---

## 8. Minor rules — fully confirmed

**Academic Rules Annexure II** answers every knob the module already exposed, so
nothing was invented. The four illustrative demo minors were replaced by the six
PDEU actually offers.

| Minor | Offering department | School |
|---|---|---|
| Computational Data Science | Computer Engineering + Mathematics (jointly) | SoT |
| Smart and Sustainable Infrastructure | Civil Engineering | SoT |
| Internet of Things | ICT | SoT |
| Robotics | Mechanical Engineering | SoT |
| Sustainability Engineering | Chemical Engineering | SoET |
| Coastal & Offshore Engineering | Petroleum Engineering | SoET |

| Rule | Official text | Configured |
|---|---|---|
| Entry semester | "The **III semester** student of any Department of SoT and SoET" | `eligible_from_semester = 3` |
| Minimum merit | "minimum **CPI of 7.5** at the end of second semester" | `min_cpi = 7.5` |
| Backlogs | "**without any course backlog** pending" | `max_backlogs = 0` |
| Seats | "maximum intake of **75 students in a division**" | `capacity = 75` |
| Ranking | "as per **merit based on latest CPI** and on pro rata basis" | CPI ranking, cited |
| Credits | 18 additional credits, Sem III–VII | `total_credits = 18`, courses mapped per semester |

**CPI appears here and nowhere else.** No source in any of the eleven curricula
makes CPI an input to elective allocation; the existing separation is preserved
and re-verified.

---

## 9. Uncertain items requiring faculty confirmation

Recorded and flagged in the database — never converted into rules. Six
components carry `REQUIRES_FACULTY_CONFIRMATION`, and **a curriculum version
cannot be published while any remain**.

| # | Item | Handling |
|---|---|---|
| 1 | **Climate Science & Sustainable Engineering** — admitting 60 students, no curriculum published | Programme **not created** |
| 2 | **Biotechnology Sem III–VIII** — official structure stops at Sem II | Imported as **DRAFT**; reaches no student |
| 3 | Biotechnology's social internship in **Sem II**, unlike every other programme | Recorded from source, flagged as a conflict |
| 4 | Chemical prints **"Program Elective 3" twice** (Sem VI and VII) | Imported verbatim as PE3/PE4 with a conflict note — not silently "fixed" |
| 5 | Minor allocation **"pro rata basis"** — denominator never defined | CPI ranking implemented; pro-rata left configurable and **unset** |
| 6 | Mechanical / Chemical **Sem IV Open Elective** listed as a named departmental course | Modelled as basket contribution, flagged |
| 7 | **CSBS Open Electives** prescribed rather than a basket | `DIRECT` selection, flagged |
| 8 | **Electrical** has no published 2024-28 structure | Only 2020-24 imported. **No 2024 curriculum invented** |
| 9 | **Division counts** — no official source | Derived from seat intake, labelled `DERIVED_FROM_INTAKE`, editable |
| 10 | Open Elective **40-minimum / 75-per-section** — departmental, not public | **Unchanged** |
| 11 | The pre-existing **ICT 2022-R1** curriculum has no public document | Retained for its cohort, flagged with review notes |

---

## 10. Database changes

Migration **`0007_curriculum_versioning`** (additive; existing rows backfill to
`PUBLISHED` with an open-ended window, so ICT keeps working unchanged).

**`curriculums`** — `effective_to_year`, `status` (DRAFT/PUBLISHED/ARCHIVED),
`published_at`, `published_by_user_id`, plus source traceability:
`source_url`, `source_title`, `source_publisher`, `source_date`, `retrieved_at`,
`academic_year_label`, `source_confidence`, `verified_by_user_id`,
`verified_at`, `review_notes`.

**`curriculum_components`** — `course_id` (fixed slots), `selection_mode`,
`eligibility` (JSON: schools/departments/programmes, inclusions and exclusions),
`source_confidence`, `source_note`.

**`courses`** — `category`, `delivery_mode`, `is_shared`.

**`programs`** — `short_name`.

**`program_divisions`** *(new table)* — programme × admission batch × division
name, with capacity and notes.

New enums: `CurriculumStatus`, `SourceConfidence`, `CourseCategory`,
`DeliveryMode`.

---

## 11. API changes

| Method | Route | Purpose |
|---|---|---|
| GET | `/curriculum` | now returns status, batch label, source provenance, flagged count; `?status=`, `?include_semesters=false` |
| GET | `/curriculum/me` | resolves through the **batch window**, published versions only |
| GET | `/curriculum/programs` | now includes `school`, `short_name` |
| GET | `/curriculum/programs/{id}/divisions` | divisions by batch, with student counts |
| POST | `/curriculum/divisions` · DELETE `/curriculum/divisions/{id}` | manage divisions (delete refused while students are assigned) |
| POST | `/curriculum/versions` | create a version — always DRAFT |
| POST | `/curriculum/{id}/revise` | copy into a new draft revision; closes the previous batch window |
| POST | `/curriculum/{id}/publish` | **refused** while any component needs faculty confirmation, or with no components |
| POST | `/curriculum/{id}/unpublish` | **refused** while students are governed by it |
| POST | `/curriculum/{id}/archive` | **refused** while students are governed by it |
| POST | `/curriculum/{id}/components` · DELETE `/curriculum/components/{id}` | **refused** on a published version |
| POST | `/curriculum/components/{id}/confirm` | clear a flag — deliberate, audited, by a named person |

All management routes require `academics:manage`; every mutation writes an audit
row.

`services/eligibility.offering_matches_scope` gained a session-aware sibling,
`offering_allowed`, which evaluates the declarative rules before falling back to
`source_scope`. `/electives/components` now uses it.

---

## 12. Frontend changes

- **`CurriculumExplorerPage`** — rewritten: programmes grouped by school,
  version and batch label, publication status, a **source panel** linking the
  official PDF with its confidence badge, per-component eligibility ("Open to:
  SoET, SLS, SoM, SoL"), and amber highlighting for components awaiting faculty
  confirmation.
- **`CurriculumAdminPage`** *(new, 295 lines)* — version table with
  publish / unpublish / archive, publication blocked while flags remain, source
  provenance per row, and a divisions panel by admission batch.
- **Navigation / routes** — Administration → Curriculum, gated on
  `academics:manage`.
- **Types** — `Program`, `ProgramDivision`, `CurriculumSource`,
  `CurriculumStatus`; `Curriculum` and `CurriculumComponent` extended.

No page needed a per-programme branch. The tenth programme required no frontend
change at all.

---

## 13. Tests added

**111 new tests**, in five files:

| File | Tests | Covers |
|---|---:|---|
| `test_program_curricula.py` | 62 | Every programme asserted against its official document — elective semesters, MOOC applicability, internship type, project credits, source traceability, flagged uncertainty, shared-course catalogue |
| `test_curriculum_versioning.py` | 15 | Batch-window resolution, ECE 2020 vs 2024 isolation, cross-programme isolation, draft/archived visibility, window boundaries |
| `test_curriculum_import.py` | 15 | Import correctness, idempotence, non-overlapping windows, source traceability, publication gating |
| `test_divisions_and_scope.py` | 11 | Divisions per programme and batch; school-level Open Elective eligibility, including the department-id trap |
| `test_curriculum_lifecycle.py` | 8 | Published versions refuse edits; governed-cohort counting |

Notable assertions:

- A 2022 ECE student gets the 2020-24 structure; a 2024 ECE student the 2024-28
  one — **and the 2022 student never sees a MOOC component**.
- An ICT student never receives ECE's curriculum; a programme with no curriculum
  gets **nothing**, not someone else's.
- A Mechanical course is **rejected** for an ICT "From Other School" slot,
  though a naive department comparison would allow it.
- Publishing Biotechnology is refused even when explicitly requested.
- CPI is not consulted anywhere in Open Elective scope, for a 4.1-CPI student or
  a 9.8-CPI one.

**One real defect was found by these tests and fixed:** `resolve_curriculum`
would fall back to *any* newest version when a student's batch matched no
window — which could hand a 2024 student a closed 2016-19 structure. It now
falls back only to a version whose window is still open-ended, and returns
`None` otherwise.

---

## 14. Final test count

```
185 pre-existing  →  296 total, all passing
```

Frontend: `tsc -b` clean, `vite build` succeeds.

---

## 15. Cross-programme regression

Every Phase 1/2 rule the brief pinned, re-verified after the expansion:

| Rule | Result |
|---|---|
| Open Elective 90 | `[75, 15]` ✓ |
| Open Elective 150 | `[75, 75]` ✓ |
| Open Elective 151 | `[75, 75, 1]` ✓ |
| Core Elective 40 combined (10+10+10+10) | runs, one class ✓ |
| Core Elective 39 combined | does not run ✓ |
| CSSI semester window | `I HIDDEN · II ANNOUNCED · III ACTIVE · IV CONCLUDED` ✓ |
| Summer Internship rubric | `25 + 25 + 25 + 25 = 100` ✓ |
| CPI in elective allocation | zero executable references ✓ |
| CPI in Minor eligibility/ranking | present, and now officially cited ✓ |
| RBAC module × department isolation | 185 pre-existing tests pass unchanged ✓ |
| ICT 814-student cohort | intact; keeps its own curriculum version ✓ |

---

## 16. Seeded result

```
12 departments · 10 programmes · 12 curriculum versions (11 published, 1 draft)
659 curriculum components · 526 courses (60 shared) · 92 divisions
1,682 students · 16 internship programmes · 6 minor specialisations
11 of 12 versions carry a source URL · 6 components flagged for confirmation
```

Verified live: ICT 2021–2023 → `2022-R1` (611 students), ICT 2024–2025 →
`2024-28` (405); ECE 2022 → `2020-24` (41), ECE 2024 → `2024-28` (71);
Biotechnology draft → 0 students. Divisions: Computer Engineering A–D, ICT A–C,
CSBS A.

---

## 17. Remaining limitations

1. **Biotechnology is incomplete.** Only Semesters I–II exist publicly. It stays
   a draft and serves no student until the department supplies the rest.
2. **No Electrical 2024-28 curriculum.** Only the 2020-24 structure is
   published, so Electrical's 2024+ batches have no curriculum. Deliberate — the
   alternative was inventing one.
3. **Climate Science & Sustainable Engineering is absent** despite admitting
   students, for the same reason.
4. **Division counts are derived, not cited.** Labelled as such and editable.
5. **No Sem V+ cohort on a 2024-28 curriculum.** Those curricula begin with the
   2024 batch, which is genuinely only in Semester IV in AY 2025-26. Later-
   semester screens are exercised by the ICT and 2020-scheme cohorts instead;
   the alternative would have been placing students on curricula that do not
   cover them.
6. **Industrial Orientation** is modelled as a curriculum component but gets no
   internship programme — no official source describes a document lifecycle for
   a 3-week, zero-credit orientation.
7. **The running Docker backend image is stale.** `docker compose up --build` is
   needed to serve this code; the database is already migrated and seeded.
