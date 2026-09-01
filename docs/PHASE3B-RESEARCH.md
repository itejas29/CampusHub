# Phase 3B — PDEU Curriculum Research Report

**Researched:** 28 August 2026 · **Researcher:** automated retrieval of official
PDEU sources · **Status:** complete, pending faculty confirmation on the items
listed in [§8](#8-uncertain--requires-faculty-confirmation).

This report is the evidence base for the Phase 3B database changes. Nothing was
imported into the database that is not traceable to a source listed here. Where
a rule could not be confirmed it is recorded as *NOT FOUND* and left
configurable rather than invented.

---

## 1. Method

Retrieval was restricted to `pdeu.ac.in`, `api.pdeu.ac.in` (the university's own
document host) and `iqac.pdpu.ac.in`. No third-party college aggregator was used
as a source of truth.

The programme list was taken from the university's own course catalogue API
payload (`pdeu.ac.in/courses/<school>/undergraduate`), which is what the public
site itself renders — not from a static page that may be stale. It was then
cross-checked against the current **B.Tech. Admission Rules A.Y. 2026-27** seat
matrix.

---

## 2. Programmes — verified current state

### 2.1 What is actually offered

| # | Programme (official name) | School | Department | Seats (A.Y. 2026-27) | Status |
|---|---|---|---|---|---|
| 1 | B.Tech. Information and Communication Technology (ICT) | SoT | ICT | 180 | **CONFIRMED** |
| 2 | B.Tech. Computer Engineering | SoT | Computer Science and Engineering | 300 | **CONFIRMED** |
| 3 | B.Tech. Computer Science and Business Systems (CSBS) | SoT | Computer Science and Engineering | 60 | **CONFIRMED** |
| 4 | B.Tech. Electronics and Communications Engineering (ECE) | SoT | ECE | 120 | **CONFIRMED** |
| 5 | B.Tech. Mechanical Engineering | SoT | Mechanical | 120 | **CONFIRMED** |
| 6 | B.Tech. Civil Engineering | SoT | Civil | 120 | **CONFIRMED** |
| 7 | B.Tech. Chemical Engineering | SoET | Chemical | 120 | **CONFIRMED** |
| 8 | B.Tech. Electrical Engineering | SoET | Electrical | 120 | **CONFIRMED** |
| 9 | B.Tech. Petroleum Engineering | SoET | Petroleum Engineering | 120 | **CONFIRMED** |
| 10 | B.Tech. Biotechnology | SoET | Biotechnology | 120 | **CONFIRMED** |
| 11 | B.Tech. Climate Science & Sustainable Engineering | *not stated* | *not stated* | 60 | **ADMITTING — CURRICULUM NOT FOUND** |

Total: 1,440 seats, matching the admission policy's own total.

### 2.2 Corrections to the assumptions in the Phase 3B brief

These matter, because building to the brief's list verbatim would have created
obsolete or non-existent programmes.

| Brief assumed | Verified reality |
|---|---|
| "Computer Science & Engineering" is a B.Tech programme | **No.** *Computer Science and Engineering* is the **department**. The B.Tech programme it runs is **Computer Engineering**. There is no B.Tech CSE. |
| "Computer Engineering" and "CSE" are two programmes | **One programme**, plus a second CSE-department programme the brief did not list: **Computer Science and Business Systems (CSBS)**. |
| Automobile Engineering is a programme | **Not offered.** Zero occurrences in the current admission policy. It survives only as *Automobile Engineering* (`24ME437T`), a Program Elective 5 option inside Mechanical Engineering. |
| Electrical / Chemical are School of Technology | **No** — both sit under the **School of Energy Technology**. |
| All listed programmes are SoT | Two more SoET B.Tech programmes exist that the brief omitted: **Petroleum Engineering** and **Biotechnology**. |
| — | A new programme is admitting for 2026-27 that appears in no curriculum document: **Climate Science & Sustainable Engineering**. |

The existing seed's `B.TECH-CSE — "B.Tech in Computer Science and Engineering"`
is therefore **not a real PDEU programme name** and is corrected in this phase.

---

## 3. Curriculum versions discovered

Two genuinely different, both-official ECE curricula were found. They are not a
revision of each other — the elective *semesters* differ, and the older one has
no CSSI and no MOOC component at all. This is the case that makes curriculum
versioning load-bearing rather than decorative.

| Programme | Version | Batch years | Source | Status |
|---|---|---|---|---|
| ICT | 2024-28 | 2024 → | `btech-ict-syllabus-2024.pdf` | CONFIRMED |
| Computer Engineering | 2024-28 | 2024 → | `btech-computer-course-structure.pdf` | CONFIRMED |
| CSBS | 2024-28 | 2024 → | `btech-csbs-course-structure.pdf` | CONFIRMED |
| **ECE** | **2024-28** | 2024 → | `ece-syllabus-2024-2028.pdf` | CONFIRMED |
| **ECE** | **2020-24** | 2020–2023 | `ece-syllabus-2020-2024.pdf` | CONFIRMED (historical) |
| Civil | 2024-28 | 2024 → | `btech-civil-course-structure-2024.pdf` | CONFIRMED |
| Mechanical | 2024-28 | 2024 → | `btech-mechanical-course-structure-2024.pdf` | CONFIRMED |
| Chemical | 2024 onwards | 2024 → | `btech-chemical-course-structure.pdf` | CONFIRMED |
| Petroleum | 2024-28 | 2024 → | `btech-petroleum-syllabus-2024.pdf` | CONFIRMED |
| Electrical | 2020-24 | 2020–2023 | `btech-electrical-course-structure.pdf` | CONFIRMED (only version published) |
| Biotechnology | 2023 onwards | 2023 → | `btech-biotechnology-course-structure.pdf` | **PARTIAL — Sem I–II only** |

### ECE 2020-24 vs ECE 2024-28 — the structural difference

| | 2020-24 | 2024-28 |
|---|---|---|
| Open Electives | 4, in Sem **III, IV, V, VI** | 4, in Sem **IV, V, VI, VII** |
| MOOC / NPTEL slot | **none** | OE-2, Sem V |
| Elective family name | **Core Elective (CE)** ×7 | **Program Elective (PE)** ×5 |
| Elective semesters | CE1–2 Sem V, CE3–4 Sem VI, CE5–7 Sem VII | PE1 Sem V, PE2–3 Sem VI, PE4–5 Sem VII |
| CSSI | **absent** | Sem III |
| Summer Internship | Industrial Training / IEP, Sem VI | Summer Internship, Sem VII |
| Sem VII project | Mini Project (3 cr) | Seminar (1 cr) |
| Final project | Comprehensive/Major Project, 10 cr | Major/Comprehensive Project, 12 cr |

A 2022-admission ECE student and a 2024-admission ECE student must therefore see
different components in the same calendar semester. This drives the
`effective_from_year` / `effective_to_year` batch-window resolution.

---

## 4. Elective structure per programme

Semester in which each component falls. "OS" = From Other School,
"FoET" = From Other Department of FoET, "IS" = Inter-School,
"ID" = Inter-department.

| Programme (version) | OE1 | MOOC/OE2 | OE3 | OE4 | Prog. Electives | Internship | Project |
|---|---|---|---|---|---|---|---|
| ICT 2024-28 | IV (OS) | V | VI (FoET) | VII (FoET) | PE1 V · PE2,3 VI · PE4,5 VII | CSSI III · Summer VII | VIII (12) |
| Computer Engg 2024-28 | IV (OS) | V | VI (FoET) | VII (FoET) | PE1 V · PE2,3 VI · PE4,5 VII | CSSI III · Summer VII | VIII (12) |
| CSBS 2024-28 | IV *(prescribed)* | V | VI *(prescribed)* | VII *(prescribed)* | PE1 V · PE2,3 VI · PE4,5 VII | CSSI III · Summer VII | VIII (12) |
| ECE 2024-28 | IV (OS) | V | VI (FoET) | VII (FoET) | PE1 V · PE2,3 VI · PE4,5 VII | CSSI III · Summer VII | VIII (12) |
| **ECE 2020-24** | **III** | **— none —** | **V** | **VI** | **CE1,2 V · CE3,4 VI · CE5,6,7 VII** | **Ind. Training VI** | **VIII (10)** |
| Civil 2024-28 | IV (OS) | V | VI (FoET) | VII (FoET) | PE1 V · PE2,3 VI · PE4,5 VII | CSSI III · Summer VII | VIII (12) |
| Mechanical 2024-28 | IV *(named)* | V | VI (FoET) | VII (FoET) | **PE1 V · PE2 VI · PE3,4,5 VII** | CSSI III · Summer VII | VIII (12) |
| Chemical 2024→ | IV (IS) | V | VI (ID/FoET) | VII (ID/FoET) | PE1 V · PE2,3 VI · PE4,5 VII | CSSI III · Summer VII | VIII (13) |
| Petroleum 2024-28 | IV (OS) | V | VI (FoET) | VII (FoET) | paired options V, VI, VII | **Rural III** · Summer VII | VIII (12) |
| Electrical 2020-24 | **III** | **— none —** | **V** | **VI** | **PE1 V · PE2,3 VI · PE4,5 VII** | **Ind. Training VI** | VIII (13) |

**Three structural families emerged, and they are not interchangeable:**

1. **2024-onward SoT/SoET model** — OE at IV/V/VI/VII, MOOC at V, CSSI at III,
   Summer Internship at VII, Seminar at VII, Project at VIII.
2. **2020-model** (ECE 2020-24, Electrical) — OE at III/IV/V/VI, no MOOC slot,
   no CSSI, Industrial Training at VI, Industrial Orientation at IV.
3. **CSBS** — the AICTE/TCS model curriculum. Its "Open Elective" slots are
   **prescribed named courses** (Financial Management, Business Communication &
   Value Science IV, Marketing Research & Marketing Management), not a free
   choice from another school.

Mechanical's PE distribution (1 / 1 / 3) differs from every other programme's
(1 / 2 / 2). Hard-coding ICT's pattern would have been wrong for Mechanical.

### 4.1 Official cross-programme Open Elective rule — **CONFIRMED**

Stated verbatim and repeated in the Electrical course structure:

> "Department will offer Open Elective based on availability of expertise/faculty.
> This open elective will be offered to the students enrolled in B.Tech. programs
> of School of Technology **other than Electrical Engineering**."
>
> "Student of Electrical Engineering will have a choice for one open elective
> course from the basket of open electives announced by **the other departments
> of School of Technology / other schools of university**."

This is exactly the rule the brief asked for: a basket, contributed to by
departments, with the **contributing department's own students excluded**, and
eligibility expressed at school/department level rather than
`course.department = X`. Verified contributed courses include
`20EE204T Climate Change: Impact and Solutions`,
`20EE209T Energy and Water Nexus` (Electrical) and
`24ME221T Renewable Energy` (Mechanical).

---

## 5. NPTEL / SWAYAM / MOOC — per programme

| Programme | MOOC component | Semester | Credits | Status |
|---|---|---|---|---|
| ICT 2024-28 | "Open Elective 2 (NPTEL/SWAYAM/MOOC)" | V | 3 | CONFIRMED |
| Computer Engg 2024-28 | "Open Elective 2 ((NPTEL/SWAYAM/MOOC))" | V | 3 | CONFIRMED |
| CSBS 2024-28 | "Open Elective II ((NPTEL/SWAYAM/MOOC))" | V | 3 | CONFIRMED |
| ECE 2024-28 | "Open Elective 2 ((NPTEL/SWAYAM/MOOC))" | V | 3 | CONFIRMED |
| Civil 2024-28 | "Open Elective 2 ((NPTEL/SWAYAM/MOOC))" | V | 3 | CONFIRMED |
| Mechanical 2024-28 | "NPTEL / SWAYAM / MOOC Course" (code `MOOC`) | V | 3 | CONFIRMED |
| Chemical 2024→ | "Open Elective 2 (NPTEL/SWAYAM/MOOC)" | V | 3 | CONFIRMED |
| Petroleum 2024-28 | "Open Elective 2 (NPTEL/SWAYAM/MOOC)" (code `MOOC`) | V | 3 | CONFIRMED |
| **ECE 2020-24** | **none** | — | — | CONFIRMED ABSENT |
| **Electrical 2020-24** | **none** | — | — | CONFIRMED ABSENT |
| Biotechnology | unknown (document truncated) | — | — | NOT FOUND |

Semester V is correct for every 2024-model programme — but it is correct
*because the curriculum says so*, and it is genuinely absent from the two
2020-model curricula. The brief's warning ("do not assume Sem V for every
programme") is borne out.

---

## 6. Internships — per programme

Authoritative source: **B.Tech. Academic Rules (batch 2024 onward), §8**.

> **CSSI** — "A student is required to undergo **3 weeks of Civic & Social
> Service Internship at the end of the second semester**."
>
> **Rural Internship** — "3 weeks … generally at the end of the first year."
>
> **Industry Orientation** — "3 weeks … distributed along the **4th and 5th**
> Semesters."
>
> **Industrial Training** — "**6 to 8 weeks** in the non-teaching period of the
> **Third year**."
>
> "The internships … will be held generally at the end of II, IV & VI Semester
> respectively. **Report submission & Viva examination will be held at the start
> of the subsequent odd semester.**"

**This confirms the existing CSSI semester-window model exactly** — carried out
over the break after Semester II, submitted and evaluated in Semester III. The
implemented `HIDDEN → ANNOUNCED (II) → ACTIVE (III) → CONCLUDED` window is
correct and is **not** being changed.

The same "carried out end of even semester N, evaluated start of odd semester
N+1" rule generalises to Summer Internship (end of VI → evaluated in VII).

| Programme | Sem III social internship | Mid-programme | Final internship |
|---|---|---|---|
| ICT / Computer / CSBS / ECE 2024 / Civil / Mechanical / Chemical | **CSSI** (1 cr) | Industrial Orientation (0 cr, Sem IV) | Summer Internship, Sem VII (2 cr) |
| **Petroleum** | **Rural Internship** (`24INT152T`, 1 cr) | Industrial Orientation Sem IV–V | Summer Internship, Sem VII (2 cr) |
| **Biotechnology** | **"Civic Services & Social Internship" in Semester II** (`20TP110`) | unknown | unknown |
| **ECE 2020-24 / Electrical 2020-24** | **none** | Industrial Orientation, Sem IV | **Industrial Training / IEP, Sem VI** |

CSSI applicability is therefore genuinely **not** universal — three of the
eleven cases differ. It is modelled as configuration, not as a constant.

The official CSSI NGO list (`cssi-info-and-industry.pdf`) confirms the programme
runs against approved NGOs, which matches the existing
`allowed_organization_types = ["NGO"]` configuration.

---

## 7. Minor Specialisation — **fully confirmed**

Source: **B.Tech. Academic Rules 2024, Annexure II**. Every eligibility knob the
existing Minor module exposes is answered by an explicit official statement, so
nothing here is invented.

### 7.1 The six official minors

| # | Minor Specialisation | Offering department | School | Credits | Open to |
|---|---|---|---|---|---|
| 1 | Computational Data Science | Computer Engineering **+ Mathematics** (jointly) | SoT | 18 | All branches except CSE |
| 2 | Smart and Sustainable Infrastructure | Civil Engineering | SoT | 18 | All except Civil |
| 3 | Internet of Things | ICT | SoT | 18 | All except ICT |
| 4 | Robotics | Mechanical Engineering | SoT | 18 | All except Mechanical |
| 5 | Sustainability Engineering | Chemical Engineering | SoET | 18 | All except Chemical |
| 6 | Coastal & Offshore Engineering | Petroleum Engineering | SoET | 18 | All except Petroleum |

### 7.2 Official eligibility rules

| Rule | Official text | Maps to |
|---|---|---|
| Entry semester | "The **III semester** student of any Department of SoT and SoET can apply" | `eligible_from_semester = 3` |
| Own department barred | "…of **other** Department … except Mechanical Engineering" | already enforced |
| Minimum merit | "minimum **CPI of 7.5** at the end of second semester" | `min_cpi = 7.5` |
| Backlogs | "**without any course backlog** pending at the time of applying" | `max_backlogs = 0` |
| Seats | "maximum intake of **75 students in a division** per minor specialisation" | `capacity = 75` |
| Ranking | "admission … will be as per **merit based on latest CPI** and on pro rata basis" | CPI ranking **confirmed** |
| Duration | "offered during **semester III to semester VII**" | one course per semester |
| Continuation | "must maintain a minimum CPI of 7.5 throughout … if the CPI falls below 7.5 … registration … shall stand cancelled" | continuation rule |
| Credits | 18 additional credits (rules text says the AICTE range is 18–20) | `total_credits = 18` |

**CPI is confirmed as a Minor input and only a Minor input.** No source in any of
the eleven curricula or the academic rules makes CPI an input to Open Elective or
Program Elective allocation. The existing separation is correct and is preserved.

---

## 8. Uncertain / requires faculty confirmation

Recorded, flagged, and **not** turned into database rules.

| # | Item | Why uncertain | Handling |
|---|---|---|---|
| 1 | **Climate Science & Sustainable Engineering** curriculum | Admitting 60 students for 2026-27 per the admission policy, but absent from the course catalogue and no curriculum document published. | Programme **not** created. No invented curriculum. |
| 2 | **Biotechnology** Sem III–VIII | Published course structure covers Semester I–II only. | Curriculum imported as **DRAFT**, Sem I–II only, flagged incomplete. |
| 3 | Biotechnology social internship placement | Its "Civic Services & Social Internship" (`20TP110`) sits in **Sem II**, unlike every other programme's Sem III. | Recorded as-is from source; flagged as a conflict against the Academic Rules' general statement. |
| 4 | Chemical PE numbering | The official structure labels **"Program Elective 3" twice** — once in Sem VI and again in Sem VII. Almost certainly a document typo for PE4. | Imported verbatim as PE3/PE4 with a `source_conflict` note. Not silently "fixed". |
| 5 | Minor allocation "pro rata basis" | Official text says merit by CPI "and on **pro rata basis**" but never defines pro-rata across *what* (departments? applicants per branch?). | CPI ranking implemented; pro-rata quota left **configurable and unset**. |
| 6 | Mechanical / Chemical Sem IV OE | Listed as a **named departmental course** (`24ME221T Renewable Energy`; Chemical "Inter-School") in the student's own semester table, while the Electrical note says the department's OE goes to *other* departments. | Modelled as the department's **basket contribution**; student slot scope taken from the label. Flagged. |
| 7 | CSBS Open Elective slots | Prescribed named courses rather than a cross-school basket. | Imported as prescribed, `selection_mode = DIRECT`. Flagged. |
| 8 | Electrical curriculum currency | Only the `20EE` (2020-24) structure is published; no 2024-28 document exists on the university host. | Imported as the 2020-24 version only. **No 2024 curriculum invented.** |
| 9 | Division structure per programme | **No official source found** for how many divisions any programme runs. | Derived from official **seat intake** as a documented, clearly-labelled assumption; fully editable. |
| 10 | Open Elective 40-minimum / 75-per-section | Not in any public document; supplied by the department in Phase 1. | **Unchanged** — preserved exactly as verified. |

### Division assumption (item 9)

No PDEU document states division counts, so divisions are **derived from
official seat intake** at roughly 60–75 students per division and stored as
editable programme data, never hard-coded:

| Programme | Seats | Divisions |
|---|---|---|
| Computer Engineering | 300 | A, B, C, D |
| ICT | 180 | A, B, C |
| ECE / Mechanical / Civil / Chemical / Electrical / Petroleum / Biotechnology | 120 | A, B |
| CSBS | 60 | A |

This is labelled `DERIVED_FROM_INTAKE` in the source metadata so an
administrator can see it is an assumption, not a citation.

---

## 9. Sources

All retrieved 28 August 2026 from university-controlled hosts.

**Policy**
- [B.Tech. Academic Rules (batch 2024 onward)](https://api.pdeu.ac.in/pdpu/resources/btech-academic-rules-2024.pdf) — internships §8, Minor Specialisation Annexure II
- [B.Tech. Admission Rules A.Y. 2026-27](https://api.pdeu.ac.in/pdpu/resources/btech-admission-policy.pdf) — programme list, seat matrix
- [CSSI — NGO list](https://api.pdeu.ac.in/pdpu/resources/cssi-info-and-industry.pdf)

**Programme catalogue**
- [School of Technology — undergraduate](https://pdeu.ac.in/courses/sot/undergraduate)
- [School of Energy Technology — undergraduate](https://pdeu.ac.in/courses/soet/undergraduate)

**Curricula**
- [ICT 2024-28](https://api.pdeu.ac.in/pdpu/resources/btech-ict-syllabus-2024.pdf)
- [Computer Engineering](https://api.pdeu.ac.in/pdpu/resources/btech-computer-course-structure.pdf)
- [CSBS](https://api.pdeu.ac.in/pdpu/resources/btech-csbs-course-structure.pdf)
- [ECE 2024-28](https://api.pdeu.ac.in/pdpu/resources/ece-syllabus-2024-2028.pdf)
- [ECE 2020-24](https://api.pdeu.ac.in/pdpu/resources/ece-syllabus-2020-2024.pdf)
- [Civil 2024-28](https://api.pdeu.ac.in/pdpu/resources/btech-civil-course-structure-2024.pdf)
- [Mechanical 2024-28](https://api.pdeu.ac.in/pdpu/resources/btech-mechanical-course-structure-2024.pdf)
- [Chemical (2024 onwards)](https://api.pdeu.ac.in/pdpu/resources/btech-chemical-course-structure.pdf)
- [Petroleum 2024-28](https://api.pdeu.ac.in/pdpu/resources/btech-petroleum-syllabus-2024.pdf)
- [Electrical 2020-24](https://api.pdeu.ac.in/pdpu/resources/btech-electrical-course-structure.pdf)
- [Biotechnology (partial)](https://api.pdeu.ac.in/pdpu/resources/btech-biotechnology-course-structure.pdf)
