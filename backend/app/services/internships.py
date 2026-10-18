"""Internship engine — one implementation, configured per programme.

CSSI and Summer Internship both run through these functions; the differences
(stages, groups, report cadence, rubric) live in ``InternshipProgram`` rows.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError
from app.models.enums import (
    AuditAction, EnrollmentStatus, EvaluationStatus, NotificationType, OrganizationType,
    ProgramPhase, ReportFrequency, ReportType, StageStatus, SubmissionStatus,
)
from app.models.identity import Faculty, Student, User
from app.models.internships import (
    EnrollmentStageProgress, EvaluationCriteria, InternshipEnrollment,
    InternshipEvaluation, InternshipGroup, InternshipProgram, InternshipReport,
    InternshipStage,
)
from app.services import audit, notifications

_FREQUENCY_DAYS = {
    ReportFrequency.DAILY: 1,
    ReportFrequency.WEEKLY: 7,
    ReportFrequency.FORTNIGHTLY: 14,
    ReportFrequency.MONTHLY: 30,
}
_FREQUENCY_REPORT_TYPE = {
    ReportFrequency.DAILY: ReportType.DAILY,
    ReportFrequency.WEEKLY: ReportType.WEEKLY,
    ReportFrequency.FORTNIGHTLY: ReportType.FORTNIGHTLY,
    ReportFrequency.MONTHLY: ReportType.MONTHLY,
}


@dataclass(slots=True)
class StageView:
    stage: InternshipStage
    progress: EnrollmentStageProgress | None

    @property
    def status(self) -> StageStatus:
        return self.progress.status if self.progress else StageStatus.PENDING


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ── enrolment ─────────────────────────────────────────────────────────────
# ── admission batches and tracks (programme configuration) ───────────────
def governs_batch(program: InternshipProgram, admission_year: int | None) -> bool:
    """Whether this programme applies to a student admitted in that year.

    `config["admission_years"] = {"from": 2024}` / `{"to": 2023}`. Two
    Semester VII programmes can then run side by side — the Minor Project for
    the earlier schemes, the Seminar for the 2024-28 scheme — the way
    curriculum versions are scoped to batches. No setting means every batch.
    """
    years = (program.config or {}).get("admission_years") or {}
    if admission_year is None or not years:
        return True
    low, high = years.get("from"), years.get("to")
    return (low is None or admission_year >= low) and (high is None or admission_year <= high)


def batch_note(program: InternshipProgram) -> str:
    years = (program.config or {}).get("admission_years") or {}
    if years.get("from") and years.get("to"):
        return f"for students admitted {years['from']}–{years['to']}"
    if years.get("from"):
        return f"for students admitted in {years['from']} or later"
    if years.get("to"):
        return f"for students admitted in {years['to']} or earlier"
    return ""


def program_tracks(program: InternshipProgram) -> list[dict]:
    """The tracks a programme offers, as configured; empty for most."""
    return list((program.config or {}).get("tracks") or [])


def track_for(program: InternshipProgram, key: str | None) -> dict | None:
    """The chosen track, validated. None for a programme without tracks."""
    from app.core.errors import ValidationError

    tracks = program_tracks(program)
    if not tracks:
        return None
    chosen = next((t for t in tracks if t.get("key") == key), None)
    if chosen is None:
        labels = " or ".join(t.get("label", t.get("key", "")) for t in tracks)
        raise ValidationError(f"Choose how you will take {program.name}: {labels}.")
    return chosen


def registration_requirements(program: InternshipProgram, track: dict | None) -> dict:
    """What registering asks for: a host organisation, its kinds, a supervisor.

    A track overrides the programme — the Semester VIII project track needs no
    host, the industry track needs a company and its supervisor.
    """
    track = track or {}
    return {
        "requires_organization": track.get("requires_organization", program.requires_organization),
        "organization_types": track.get("organization_types",
                                        program.allowed_organization_types or []),
        "requires_supervisor": track.get("requires_industry_mentor",
                                         program.requires_industry_mentor),
    }


def assert_registration_organisation(db: Session, program: InternshipProgram, *,
                                     organization_id: int | None,
                                     new_type: OrganizationType | None,
                                     track: dict | None = None) -> None:
    """A programme that needs a host organisation gets one of the kinds it accepts.

    Both rules were stored on the programme and shown on the form, but nothing
    enforced them: a CSSI registration went through with no NGO at all, or with
    a company in place of one.
    """
    from app.core.errors import ValidationError
    from app.models.internships import Organization

    needs = registration_requirements(program, track)
    allowed = set(needs["organization_types"])
    if organization_id is not None:
        org = db.get(Organization, organization_id)
        if org is None:
            raise ValidationError("That organisation is not on the list.")
        kind = org.type
    elif new_type is not None:
        kind = new_type
    else:
        if needs["requires_organization"]:
            raise ValidationError(
                f"Name the organisation you will work with for {program.name}.")
        return
    if allowed and kind.value not in allowed:
        names = ", ".join(sorted(t.replace("_", " ").lower() for t in allowed))
        raise ValidationError(f"{program.name} accepts only: {names}.")


def enroll_student(
    db: Session, *, program: InternshipProgram, student: Student,
    actor: User | None = None, track: str | None = None,
) -> InternshipEnrollment:
    existing = db.scalar(
        select(InternshipEnrollment).where(
            InternshipEnrollment.program_id == program.id,
            InternshipEnrollment.student_id == student.id,
        )
    )
    if existing:
        return existing

    enrollment = InternshipEnrollment(
        program_id=program.id, student_id=student.id,
        status=EnrollmentStatus.REGISTERED, registered_at=utcnow(),
        start_date=program.start_date, end_date=program.end_date, track=track,
    )
    db.add(enrollment)
    db.flush()

    if program.requires_group:
        group = assign_to_group(db, program=program, enrollment=enrollment)
        if group and group.faculty_id:
            enrollment.mentor_faculty_id = group.faculty_id
            enrollment.status = EnrollmentStatus.MENTOR_ASSIGNED

    initialise_stage_progress(db, enrollment=enrollment, program=program)
    audit.record(
        db, action=AuditAction.CREATE, entity_type="internship_enrollment",
        entity_id=enrollment.id, actor=actor,
        description=f"Enrolled in {program.name}",
        meta={"program": program.code, "student_id": student.id},
    )
    return enrollment


def assign_to_group(
    db: Session, *, program: InternshipProgram, enrollment: InternshipEnrollment
) -> InternshipGroup | None:
    """Balance students across groups — fill the emptiest group with capacity."""
    counts = dict(
        db.execute(
            select(InternshipEnrollment.group_id, func.count(InternshipEnrollment.id))
            .where(InternshipEnrollment.program_id == program.id)
            .group_by(InternshipEnrollment.group_id)
        ).all()
    )
    groups = list(db.scalars(
        select(InternshipGroup).where(InternshipGroup.program_id == program.id)
        .order_by(InternshipGroup.name)
    ))
    open_groups = [g for g in groups if counts.get(g.id, 0) < g.capacity]
    if not open_groups:
        return None
    chosen = min(open_groups, key=lambda g: (counts.get(g.id, 0), g.id))
    enrollment.group_id = chosen.id
    return chosen


def initialise_stage_progress(
    db: Session, *, enrollment: InternshipEnrollment, program: InternshipProgram
) -> list[EnrollmentStageProgress]:
    stages = list(db.scalars(
        select(InternshipStage).where(InternshipStage.program_id == program.id)
        .order_by(InternshipStage.sequence)
    ))
    existing = {p.stage_id for p in enrollment.stage_progress}
    # A track lists the stage codes it runs; the rest do not apply to this
    # student and are recorded as SKIPPED (an industry offer letter for an
    # in-house project, say), so progress counts only what is theirs to do.
    track = next((t for t in program_tracks(program) if t.get("key") == enrollment.track), None)
    applies = set(track["stages"]) if track and track.get("stages") else None
    created: list[EnrollmentStageProgress] = []
    first = True
    for stage in stages:
        if stage.id in existing:
            continue
        skipped = applies is not None and stage.code not in applies
        progress = EnrollmentStageProgress(
            enrollment_id=enrollment.id, stage_id=stage.id,
            status=(StageStatus.SKIPPED if skipped
                    else StageStatus.IN_PROGRESS if first else StageStatus.PENDING),
        )
        db.add(progress)
        created.append(progress)
        if not skipped and first:
            enrollment.current_stage_id = stage.id
            first = False
    db.flush()
    return created


def stage_timeline(db: Session, enrollment: InternshipEnrollment) -> list[StageView]:
    stages = list(db.scalars(
        select(InternshipStage)
        .where(InternshipStage.program_id == enrollment.program_id)
        .order_by(InternshipStage.sequence)
    ))
    progress_by_stage = {p.stage_id: p for p in enrollment.stage_progress}
    return [StageView(stage=s, progress=progress_by_stage.get(s.id)) for s in stages]


def completion_percent(db: Session, enrollment: InternshipEnrollment) -> int:
    timeline = stage_timeline(db, enrollment)
    if not timeline:
        return 0
    done = sum(1 for v in timeline
               if v.status in (StageStatus.APPROVED, StageStatus.SKIPPED))
    return round(done * 100 / len(timeline))


# ── stage transitions ─────────────────────────────────────────────────────
def submit_stage(
    db: Session, *, enrollment: InternshipEnrollment, stage_id: int,
    actor: User | None = None, data: dict | None = None,
) -> EnrollmentStageProgress:
    progress = db.scalar(
        select(EnrollmentStageProgress).where(
            EnrollmentStageProgress.enrollment_id == enrollment.id,
            EnrollmentStageProgress.stage_id == stage_id,
        )
    )
    if progress is None:
        raise NotFoundError("That stage is not part of this internship.")
    if progress.status == StageStatus.APPROVED:
        raise BusinessRuleError("This stage has already been approved.")

    progress.status = StageStatus.SUBMITTED
    progress.submitted_at = utcnow()
    if data:
        progress.data = {**progress.data, **data}
    if enrollment.status in (EnrollmentStatus.REGISTERED, EnrollmentStatus.MENTOR_ASSIGNED):
        enrollment.status = EnrollmentStatus.IN_PROGRESS

    if enrollment.mentor_faculty_id:
        mentor = db.get(Faculty, enrollment.mentor_faculty_id)
        if mentor:
            notifications.notify(
                db, user_id=mentor.user_id,
                type=NotificationType.INTERNSHIP_SUBMISSION,
                title="Internship stage submitted",
                message=f"{progress.stage.name} was submitted for review.",
                link=f"/internships/{enrollment.program_id}/students/{enrollment.id}",
            )
    audit.record(
        db, action=AuditAction.STATUS_CHANGE, entity_type="internship_stage_progress",
        entity_id=progress.id, actor=actor,
        description=f"Submitted stage '{progress.stage.name}'",
    )
    return progress


def review_stage(
    db: Session, *, enrollment: InternshipEnrollment, stage_id: int, approve: bool,
    remarks: str | None = None, actor: User | None = None,
) -> EnrollmentStageProgress:
    progress = db.scalar(
        select(EnrollmentStageProgress).where(
            EnrollmentStageProgress.enrollment_id == enrollment.id,
            EnrollmentStageProgress.stage_id == stage_id,
        )
    )
    if progress is None:
        raise NotFoundError("That stage is not part of this internship.")

    progress.status = StageStatus.APPROVED if approve else StageStatus.REJECTED
    progress.reviewed_at = utcnow()
    progress.reviewed_by_user_id = actor.id if actor else None
    progress.remarks = remarks

    if approve:
        _advance_current_stage(db, enrollment)

    student = db.get(Student, enrollment.student_id)
    if student:
        notifications.notify(
            db, user_id=student.user_id, type=NotificationType.INTERNSHIP_STAGE,
            title=f"Stage {'approved' if approve else 'sent back'}",
            message=f"{progress.stage.name}: "
                    f"{remarks or ('Approved by your faculty mentor.' if approve else 'Revision requested.')}",
            link=f"/internships/{enrollment.program_id}",
        )
    audit.record(
        db, action=AuditAction.STATUS_CHANGE, entity_type="internship_stage_progress",
        entity_id=progress.id, actor=actor,
        description=f"{'Approved' if approve else 'Rejected'} stage "
                    f"'{progress.stage.name}'",
        meta={"remarks": remarks},
    )
    return progress


def _advance_current_stage(db: Session, enrollment: InternshipEnrollment) -> None:
    timeline = stage_timeline(db, enrollment)
    for view in timeline:
        if view.status not in (StageStatus.APPROVED, StageStatus.SKIPPED):
            enrollment.current_stage_id = view.stage.id
            if view.progress and view.progress.status == StageStatus.PENDING:
                view.progress.status = StageStatus.IN_PROGRESS
            return
    # Everything approved.
    enrollment.current_stage_id = None
    if enrollment.status != EnrollmentStatus.COMPLETED:
        enrollment.status = EnrollmentStatus.UNDER_EVALUATION


# ── reports ───────────────────────────────────────────────────────────────
def expected_report_schedule(program: InternshipProgram) -> list[dict]:
    """Derive the periodic report calendar from the programme configuration."""
    if program.report_frequency == ReportFrequency.NONE or not program.start_date:
        return []
    step = _FREQUENCY_DAYS[program.report_frequency]
    count = program.expected_report_count or 0
    if not count and program.end_date:
        count = max((program.end_date - program.start_date).days // step, 1)
    schedule = []
    for i in range(count):
        period_start = program.start_date + dt.timedelta(days=i * step)
        schedule.append({
            "sequence_number": i + 1,
            "report_type": _FREQUENCY_REPORT_TYPE[program.report_frequency].value,
            "period_start": period_start,
            "period_end": period_start + dt.timedelta(days=step - 1),
        })
    return schedule


#: A review decides one of these; anything else (back to SUBMITTED, or the
#: synthetic NOT_SUBMITTED) is not a decision.
REPORT_REVIEW_OUTCOMES = (SubmissionStatus.UNDER_REVIEW, SubmissionStatus.APPROVED,
                          SubmissionStatus.VERIFIED, SubmissionStatus.REJECTED)


def assert_report_in_schedule(program: InternshipProgram, report_type: ReportType,
                              sequence_number: int) -> None:
    """A periodic report's number falls inside the programme's schedule.

    Report #50 of a programme that expects 8 weekly reports used to be accepted.
    The final report is not numbered against the schedule.
    """
    from app.core.errors import ValidationError

    if report_type == ReportType.FINAL:
        return
    if program.report_frequency == ReportFrequency.NONE:
        raise ValidationError(f"{program.name} does not use periodic reports.")
    count = program.expected_report_count or 0
    if count and sequence_number > count:
        raise ValidationError(
            f"{program.name} expects {count} {report_type.value.lower()} reports; "
            f"there is no report #{sequence_number}.")


def assert_report_review(report, status: SubmissionStatus, feedback: str | None) -> None:
    from app.core.errors import ValidationError

    if status not in REPORT_REVIEW_OUTCOMES:
        raise ValidationError("Approve, verify, send back or start reviewing — "
                              f"'{status.value}' is not a review decision.")
    if status == SubmissionStatus.REJECTED and not (feedback or "").strip():
        raise ValidationError("Say what needs to change when sending a report back.")
    if report.status in (SubmissionStatus.APPROVED, SubmissionStatus.VERIFIED) \
            and status == SubmissionStatus.UNDER_REVIEW:
        raise ValidationError("This report has already been approved.")


def report_progress(db: Session, enrollment: InternshipEnrollment) -> dict:
    program = enrollment.program
    expected = expected_report_schedule(program)
    submitted = db.scalar(
        select(func.count(InternshipReport.id)).where(
            InternshipReport.enrollment_id == enrollment.id,
            InternshipReport.report_type != ReportType.FINAL,
            InternshipReport.status != "DRAFT",
        )
    ) or 0
    return {
        "expected": len(expected),
        "submitted": int(submitted),
        "frequency": program.report_frequency.value,
    }


# ── evaluation ────────────────────────────────────────────────────────────
def rubric_for(db: Session, program_id: int) -> list[EvaluationCriteria]:
    return list(db.scalars(
        select(EvaluationCriteria)
        .where(EvaluationCriteria.program_id == program_id,
               EvaluationCriteria.is_active.is_(True))
        .order_by(EvaluationCriteria.sequence)
    ))


def compute_totals(
    criteria: list[EvaluationCriteria], scores: dict[int, float | None],
    *, is_absent: bool = False,
) -> tuple[float, float]:
    """Weighted total and maximum. Grading *letters* are deliberately not derived
    here — the institutional grade boundaries have not been supplied."""
    if is_absent:
        return 0.0, float(sum(float(c.max_marks) * float(c.weight) for c in criteria))
    total = 0.0
    maximum = 0.0
    for c in criteria:
        weight = float(c.weight)
        maximum += float(c.max_marks) * weight
        mark = scores.get(c.id)
        if mark is not None:
            total += float(mark) * weight
    return round(total, 2), round(maximum, 2)


def can_review(enrollment: InternshipEnrollment, faculty: Faculty | None) -> bool:
    """Whether this faculty member reviews and marks this student.

    The student's own mentor does. A group lead used to as well, so after a
    roll-number allocation two people could mark the same CSSI student and the
    later save won. A programme may still opt group leads in
    (`config["group_lead_reviews"]`); none does by default. Group leads keep
    read access either way.
    """
    if faculty is None:
        return False
    if enrollment.mentor_faculty_id == faculty.id:
        return True
    leads_review = bool((enrollment.program.config or {}).get("group_lead_reviews"))
    return leads_review and enrollment.group is not None and enrollment.group.faculty_id == faculty.id


def finalise_blockers(db: Session, enrollment: InternshipEnrollment) -> list[str]:
    """What must be approved and verified before marks can be finalised.

    Every mandatory stage of the student's track except the marking stage
    itself (owned by faculty, no document): approved, with its document
    verified where it needs one. A mentor could finalise before, say, the CSSI
    certificate had been checked.
    """
    from app.services.documents import stage_requirements_met

    missing = []
    for view in stage_timeline(db, enrollment):
        stage = view.stage
        if view.status == StageStatus.SKIPPED or not stage.is_mandatory:
            continue
        if stage.owner_role == "FACULTY" and not stage.requires_document:
            continue
        met, _reason = stage_requirements_met(db, enrollment, stage)
        if view.status != StageStatus.APPROVED or not met:
            missing.append(stage.name)
    return missing


def finalise_enrollment(
    db: Session, *, enrollment: InternshipEnrollment, evaluation: InternshipEvaluation,
    actor: User | None = None,
) -> None:
    enrollment.final_marks = evaluation.total_marks
    enrollment.final_grade = evaluation.grade
    enrollment.status = EnrollmentStatus.COMPLETED
    evaluation.status = EvaluationStatus.FINALISED

    student = db.get(Student, enrollment.student_id)
    if student:
        notifications.notify(
            db, user_id=student.user_id, type=NotificationType.EVALUATION_UPDATE,
            title="Internship evaluation published",
            message=f"Your {enrollment.program.name} evaluation has been finalised.",
            link=f"/internships/{enrollment.program_id}",
        )
    audit.record(
        db, action=AuditAction.EVALUATION_UPDATE, entity_type="internship_enrollment",
        entity_id=enrollment.id, actor=actor,
        description="Evaluation finalised",
        meta={"total_marks": float(evaluation.total_marks or 0), "grade": evaluation.grade},
    )


#: Students one faculty mentor carries in one programme when the programme's
#: `config["mentor_capacity"]` does not say. 10 is the figure the portal has
#: used since mentor allocation was built; it is NOT from a written PDEU rule
#: and REQUIRES_FACULTY_CONFIRMATION. Set it per programme rather than here.
DEFAULT_MENTOR_CAPACITY = 10


def mentor_capacity(program: InternshipProgram) -> int:
    """How many students one mentor may carry in this programme."""
    value = (program.config or {}).get("mentor_capacity")
    try:
        return max(1, int(value)) if value is not None else DEFAULT_MENTOR_CAPACITY
    except (TypeError, ValueError):
        return DEFAULT_MENTOR_CAPACITY


def mentor_capacity_confirmed(program: InternshipProgram) -> bool:
    """Has someone set this programme's cap, or is it still the portal default?

    The default is not a PDEU rule, so screens must say so until a coordinator
    records the figure their department actually uses.
    """
    return (program.config or {}).get("mentor_capacity") is not None


def eligible_mentors(db: Session, program: InternshipProgram) -> list[Faculty]:
    """Faculty who may mentor this programme's students, in name order.

    A programme belongs to one department, so its mentors come from that
    department. A Head of Department takes no mentees, so they are never in the
    pool — leaving them in made a bulk run fail part-way when it reached them.
    """
    from app.models.identity import Department

    hods = select(Department.hod_faculty_id).where(Department.hod_faculty_id.is_not(None))
    stmt = (
        select(Faculty).join(Faculty.user)
        # `is_mentor` is false for the HoD and for office accounts, which are
        # not people who can take students.
        .where(Faculty.is_active.is_(True), Faculty.is_mentor.is_(True),
               Faculty.id.not_in(hods))
        .order_by(User.full_name)
    )
    if program.department_id is not None:
        stmt = stmt.where(Faculty.department_id == program.department_id)
    return list(db.scalars(stmt))


def assert_eligible_mentor(db: Session, program: InternshipProgram | None,
                           faculty: Faculty) -> None:
    from app.services import scope

    scope.assert_can_mentor(db, faculty)
    if (program is not None and program.department_id is not None
            and faculty.department_id != program.department_id):
        raise BusinessRuleError(
            f"{faculty.user.full_name} is not in this programme's department, "
            "so cannot mentor its students."
        )


def split_by_roll(total: int, mentors: int, capacity: int) -> list[int]:
    """Contiguous roll-number blocks, as even as possible, none above capacity.

    Uses only as many mentors as the cohort needs. Students beyond
    `mentors × capacity` are left for the coordinator, never piled onto the
    last mentor.
    """
    if total <= 0 or mentors <= 0:
        return []
    used = min(mentors, -(-total // capacity))
    seated = min(total, used * capacity)
    base, extra = divmod(seated, used)
    return [base + (1 if i < extra else 0) for i in range(used)]


def _sync_allocation_stage(db: Session, enrollment: InternshipEnrollment, *,
                           assigned: bool, actor: User | None) -> None:
    """The coordinator's allocation stage follows the allocation itself.

    A stage the coordinator owns and that needs no document ("Mentor
    Allocation", "Guide Allocation") is done by allocating. Nothing completed
    it before, so a student sat at that step after being given a mentor until
    someone approved the stage by hand. Taking the mentor away reopens it.
    """
    changed = False
    for progress in enrollment.stage_progress:
        stage = progress.stage
        if stage.owner_role != "COORDINATOR" or stage.requires_document:
            continue
        if assigned and progress.status in (StageStatus.PENDING, StageStatus.IN_PROGRESS,
                                            StageStatus.SUBMITTED):
            progress.status = StageStatus.APPROVED
            progress.reviewed_at = utcnow()
            progress.reviewed_by_user_id = actor.id if actor else None
            changed = True
        elif not assigned and progress.status == StageStatus.APPROVED:
            progress.status = StageStatus.PENDING
            changed = True
    if changed:
        db.flush()
        _advance_current_stage(db, enrollment)


def override_mentor(
    db: Session, *, enrollment: InternshipEnrollment, new_faculty_id: int | None,
    reason: str | None, actor: User | None = None, enforce_capacity: bool = True,
) -> InternshipEnrollment:
    """Coordinator override — always audited, per the Phase 1 requirement."""
    if new_faculty_id == enrollment.mentor_faculty_id:
        # Nothing changes, so nothing is audited and nobody is notified. A bulk
        # rebalance used to re-send "mentor updated" to every unchanged student.
        return enrollment
    if new_faculty_id is not None:
        mentor = db.get(Faculty, new_faculty_id)
        if mentor is None:
            raise NotFoundError("Faculty member not found.")
        program = getattr(enrollment, "program", None)
        assert_eligible_mentor(db, program, mentor)
    if new_faculty_id is not None and enforce_capacity:
        program = getattr(enrollment, "program", None)
        capacity = mentor_capacity(program) if program else DEFAULT_MENTOR_CAPACITY
        current_count = db.scalar(
            select(func.count(InternshipEnrollment.id)).where(
                InternshipEnrollment.program_id == enrollment.program_id,
                InternshipEnrollment.mentor_faculty_id == new_faculty_id,
                InternshipEnrollment.id != enrollment.id,
            )
        ) or 0
        if current_count >= capacity:
            raise BusinessRuleError(
                f"{mentor.user.full_name} already has {current_count} students "
                f"(this programme allows {capacity} per mentor)."
            )

    previous = enrollment.mentor_faculty_id
    enrollment.mentor_faculty_id = new_faculty_id
    if new_faculty_id and enrollment.status == EnrollmentStatus.REGISTERED:
        enrollment.status = EnrollmentStatus.MENTOR_ASSIGNED
    elif not new_faculty_id and enrollment.status == EnrollmentStatus.MENTOR_ASSIGNED:
        enrollment.status = EnrollmentStatus.REGISTERED
    _sync_allocation_stage(db, enrollment, assigned=new_faculty_id is not None, actor=actor)

    audit.record(
        db, action=AuditAction.MENTOR_OVERRIDE, entity_type="internship_enrollment",
        entity_id=enrollment.id, actor=actor,
        description="Faculty mentor changed manually",
        meta={"from_faculty_id": previous, "to_faculty_id": new_faculty_id,
              "reason": reason},
    )
    if new_faculty_id:
        mentor = db.get(Faculty, new_faculty_id)
        student = db.get(Student, enrollment.student_id)
        for user_id in filter(None, [mentor.user_id if mentor else None,
                                     student.user_id if student else None]):
            notifications.notify(
                db, user_id=user_id, type=NotificationType.INTERNSHIP_STAGE,
                title="Internship mentor updated",
                message=reason or "The faculty mentor for this internship was changed.",
                link=f"/internships/{enrollment.program_id}",
            )
    return enrollment


# ── semester windows ──────────────────────────────────────────────────────
def program_phase(program, current_semester: int | None) -> ProgramPhase:
    """Where a student stands relative to a programme's semester window.

    CSSI is *floated* by the coordinator during Semester II so students can find
    an NGO over the break, then carried out in Semester III — announcing it and
    opening it are two different moments, and this is what separates them.

    Kept free of ORM and session dependencies so the rule can be tested directly.
    """
    if current_semester is None:
        return ProgramPhase.HIDDEN

    target = program.target_semester
    announce = program.announce_from_semester or target
    visible_to = program.visible_to_semester

    if visible_to is not None and current_semester > visible_to:
        return ProgramPhase.CONCLUDED
    if target is None:
        # No window configured — the programme is open to whoever can see it.
        return ProgramPhase.ACTIVE
    if announce is not None and current_semester < announce:
        return ProgramPhase.HIDDEN
    if current_semester < target:
        return ProgramPhase.ANNOUNCED
    return ProgramPhase.ACTIVE


def phase_note(program, phase: ProgramPhase, current_semester: int | None) -> str | None:
    """One sentence explaining the phase to the student, or None when active."""
    if phase is ProgramPhase.ANNOUNCED and registers_early(program, current_semester):
        return (
            f"Runs in Semester {program.target_semester}. Registration is open now, "
            "so you can arrange your project or host company ahead; work is "
            "submitted once the semester begins."
        )
    if phase is ProgramPhase.ANNOUNCED:
        return (
            f"Announced for Semester {program.target_semester}. You are in "
            f"Semester {current_semester} — use this time to find and confirm a "
            "host organisation. Submissions open when the semester begins."
        )
    if phase is ProgramPhase.CONCLUDED:
        return (
            f"This programme runs in Semester {program.target_semester} and is no "
            "longer open to you."
        )
    if phase is ProgramPhase.HIDDEN:
        return f"Opens in Semester {program.target_semester}."
    return None


def student_can_see_program(program, current_semester: int | None, *,
                            has_enrollment: bool) -> bool:
    """Whether a programme belongs in a student's own view at all.

    HIDDEN means exactly that. A programme whose window has not been announced
    yet is not the student's business, so it must not be listed *or* fetchable
    by id — withholding it in the UI while the API still serves its stages,
    criteria, dates and coordinator is not visibility control, it is decoration.

    A concluded programme stays readable only for a student who actually took
    it, so their own record survives the window closing. A student who never
    enrolled has nothing to look at and should not be shown a programme that ran
    before their time.

    Kept next to program_phase() and free of ORM/session dependencies so the
    rule can be tested directly.
    """
    if has_enrollment:
        # Never hide a student's own record from them, whatever the phase.
        return True
    phase = program_phase(program, current_semester)
    return phase not in (ProgramPhase.HIDDEN, ProgramPhase.CONCLUDED)


def registers_early(program, current_semester: int | None) -> bool:
    """Whether an announced programme already takes registrations.

    `config["register_from_semester"] = 7` on the Semester VIII project lets a
    Semester VII student register (and an industry-track student line up a
    company) a semester ahead. Work is still submitted only from the
    programme's own semester — see assert_submissions_open.
    """
    early = (getattr(program, "config", None) or {}).get("register_from_semester")
    return (early is not None and current_semester is not None
            and program_phase(program, current_semester) is ProgramPhase.ANNOUNCED
            and current_semester >= early)


def assert_can_register_now(program, current_semester: int | None) -> None:
    """Registration (not submission) for a programme without coordinator windows."""
    if registers_early(program, current_semester):
        return
    assert_submissions_open(program, current_semester)


def assert_submissions_open(program, current_semester: int | None) -> None:
    """Guard every student-side write behind the programme's semester window."""
    phase = program_phase(program, current_semester)
    if phase is ProgramPhase.ACTIVE:
        return
    if phase is ProgramPhase.ANNOUNCED:
        raise BusinessRuleError(
            f"{program.name} has been announced but submissions do not open until "
            f"Semester {program.target_semester}. You are in Semester "
            f"{current_semester}."
        )
    if phase is ProgramPhase.CONCLUDED:
        raise BusinessRuleError(
            f"{program.name} ran in Semester {program.target_semester} and is closed "
            "to you."
        )
    raise BusinessRuleError(
        f"{program.name} opens in Semester {program.target_semester}."
    )
