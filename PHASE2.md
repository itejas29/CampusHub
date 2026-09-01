# CampusHub — Phase 2 Specification

Requirements confirmed after the Phase 1 build. Each section states the rule,
then what already exists in Phase 1 versus what still has to be built, so the
remaining work is visible rather than implied.

> **Status: implemented.** Every requirement below is built and verified.
> See [`docs/PHASE2-REPORT.md`](docs/PHASE2-REPORT.md) for what changed, the
> migrations added, the routes added, the tests, and the policies that remain
> deliberately configurable.

---

## 1. Document submission and faculty review

**The requirement.** Students upload their internship documents as files (PDFs).
This is *not* only a student-side upload feature: every submitted document must
also be visible from that student's faculty/coordinator profile. A faculty
member must never have to open a separate documents page to understand a
student's progress. Clicking a student shows what was submitted, what is
pending, the current status, and a way to view or download the file where
authorised.

### 1.1 Summer Internship documents

| Document | Upload | Notes |
|---|---|---|
| Weekly Report | PDF, one submission **per week** | week number, timestamp, status |
| Final Report | PDF | timestamp, status |
| Certificate | PDF | timestamp, verification status |
| Presentation | submission/status visible on the profile | configured format |
| Industry mentor evaluation | mentor side | feeds the Evaluation tab |
| Any additional configured document | PDF | driven by programme config |

Faculty **Student Details** must render:

```
Weekly Reports
    Week 1    [View PDF]  [Status]
    Week 2    [View PDF]  [Status]
    Week 3    [View PDF]  [Status]
    ...
Final Report
    [View PDF]  [Status]
Certificate
    [View PDF]  [Verification Status]
Presentation
    [Submitted / Pending]
```

### 1.2 CSSI documents

At minimum: Certificate (PDF), Poster (upload), Presentation (status visible),
plus any other configured proof-of-work document. The faculty Student Details
screen must show all of them.

### 1.3 Faculty student profile — required shape

```
Student Details
  [Personal] [NGO / Internship] [Project] [Documents / Proof of Work] [Evaluation]
```

The Documents section shows **actual uploaded files**:

```
Certificate      ✓ Submitted    [View PDF] [Download]
Week 1 Report    ✓ Submitted    [View PDF] [Download]
Week 2 Report    ✓ Submitted    [View PDF] [Download]
Week 3 Report    ⚠ Pending
Final Report     ✓ Submitted    [View PDF] [Download]
Presentation     ✓ Submitted
Poster           ⚠ Pending
```

**Never show fake document links.** Not submitted → render "Not submitted".
Submitted → render the real stored file and its metadata.

### 1.4 Document status

Backend-driven, never frontend-only:

```
NOT_SUBMITTED → SUBMITTED → UNDER_REVIEW → VERIFIED
                                        ↘ REJECTED → (student resubmits)
```

A rejected document must expose its status and reason to the student, who can
then resubmit.

### 1.5 Storage architecture

Use the existing storage abstraction. Local disk in development, **AWS S3 in
production**. Never store PDF binaries in PostgreSQL. The database holds
metadata only:

```
document_id · student_id · internship_id · document_type · week_number (nullable)
file_name · file_size · storage_key · mime_type · uploaded_at
status · reviewed_by · reviewed_at · review_comment
```

### 1.6 Access control

| Actor | May see |
|---|---|
| Student | upload/update their own allowed documents; view their own submissions |
| Faculty | documents of students assigned to them |
| Coordinator | documents within their module + department scope |
| Admin | per admin permissions |

Anyone else gets **403**. Storage URLs must never be exposed without
authorisation — use protected backend download endpoints, or short-lived signed
URLs in production.

### 1.7 Progress must be document-driven

The stepper reflects real submission state, not arbitrary percentages:

- Certificate submitted → Certificate stage complete
- Week 3 report missing → Weekly Reports stage remains incomplete

---

## 2. Gap analysis — Phase 1 versus what remains

### Already in place

| Capability | Where |
|---|---|
| Storage abstraction (local / S3, IAM-role aware, pre-signed URLs) | `app/storage/` |
| `internship_documents` table with type, file, status, remarks | `models/internships.py` |
| `files` table: filename, content type, size, storage key, checksum, uploader | `models/system.py` |
| Upload pipeline with content-type and size validation | `services/files.save_upload` |
| Student upload endpoint, typed per stage | `POST /internships/enrollments/{id}/documents` |
| Access-checked download (never a raw storage URL) | `GET /files/{id}/download` |
| Weekly reports as separate numbered submissions with review + feedback | `internship_reports`, `POST .../reports` |
| Faculty student modal with a Proof of Work tab listing real uploads | `StudentDetailDrawer.tsx` |
| Scoped visibility (own / mentee / coordinated department) | `services/scope.py` |

### Still to build

1. **`NOT_SUBMITTED` as a first-class state.** Today a missing document is an
   absent row. The profile must render the *expected* document set for the
   programme — every configured stage document plus every expected week — and
   mark the gaps. Derive the expectation from `internship_stages` and
   `expected_report_schedule()`, which already exist.
2. **`UNDER_REVIEW` and `VERIFIED`.** `SubmissionStatus` currently has
   `DRAFT / SUBMITTED / APPROVED / REVISION_REQUESTED / REJECTED`. Align it to
   the five states above and migrate existing rows.
3. **`review_comment` on documents.** Reports carry `feedback`; documents carry
   only `remarks` with no reviewer or timestamp. Add `reviewed_by`,
   `reviewed_at`, `review_comment` to `internship_documents`.
4. **`week_number` on documents.** Weekly reports are `internship_reports`
   today. Either attach documents to a report, or add `week_number` to
   `internship_documents` so a week's PDF is addressable directly.
5. **Resubmission flow.** A rejected document must be replaceable, keeping the
   rejection reason visible to the student until they resubmit.
6. **Document-driven progress.** `completion_percent()` counts approved stages.
   It must instead require every *mandatory* document of a stage to be present
   and verified — so a missing Week 3 report holds the Weekly Reports stage open.
7. **Unified Documents tab.** Merge the current Proof of Work and Reports tabs
   into one Documents view showing the full expected set with per-item status
   and View/Download, for both CSSI and Summer.
8. **Summer evaluation rubric change.** Currently five criteria totalling 100.
   The confirmed rubric is four components of 25 each:
   Report /25 · Presentation /25 · Weekly Reports /25 · Industry Mentor /25.
   This is a seed/config change — the rubric is already data-driven.
9. **Industry mentor input.** `industry_mentor_feedback` is free text on the
   enrolment. Phase 2 needs it to feed the Industry Mentor /25 component.

---

## 3. Other Phase 2 items carried forward

| Item | Attachment point |
|---|---|
| Merit / pro-rata elective allocation | `MeritAllocation.allocate()` — declared, `is_available = False`. **CPI is not a permitted input for electives.** |
| Minor ranking formula | `MinorProgram.rules` JSON + a registered strategy. CPI *is* permitted here. |
| Letter grade derivation | `compute_totals()` returns marks only; boundaries not guessed |
| Real-time chat | `mentor_meetings.thread_key` |
| Email / SMS delivery | subscribe a transport to `services/notifications.notify()` |
| AWS deployment | `STORAGE_BACKEND=s3`; no business-code change |
| Bulk student/faculty import | `services/` + a router |
| SSO | replace `_authenticate()` in `api/v1/auth.py` |

---

## 4. Rules settled in Phase 1 (do not re-litigate)

- **Open Elective** — 40 minimum to run; **75 per class section**, not
  course-wide; extra sections open on demand (90 → 75 + 15); coordinator can
  rebalance between sections.
- **Program Core Elective** — 40 minimum counted **across participating
  divisions combined**, never per division; **no 75 ceiling**; runs as one
  combined class.
- **CPI/CGPA is never used for elective selection.** It governs Minor
  Specialisation eligibility only.
- **Coordination is scoped** to (module × department); only an administrator
  grants it.
