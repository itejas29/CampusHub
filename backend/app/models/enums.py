"""All domain enumerations.

Stored as VARCHAR + CHECK constraint (``native_enum=False``) rather than native
PostgreSQL ENUM types: new values can then be added in a plain migration instead
of requiring ``ALTER TYPE``, which matters because most of these vocabularies
will grow in later phases.
"""
from __future__ import annotations

import enum


class StrEnum(str, enum.Enum):
    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.value


# ─────────────────────────── identity & access ────────────────────────────
class Role(StrEnum):
    STUDENT = "STUDENT"
    FACULTY = "FACULTY"
    DEPARTMENT_ADMIN = "DEPARTMENT_ADMIN"
    INTERNSHIP_COORDINATOR = "INTERNSHIP_COORDINATOR"
    CLUB_ADMIN = "CLUB_ADMIN"
    #: Head of Department. Appoints the department's coordinators and oversees
    #: its modules read-only; never a coordinator or a mentor themselves. Which
    #: department is `departments.hod_faculty_id`, not this flag.
    HOD = "HOD"
    SUPER_ADMIN = "SUPER_ADMIN"


class AssignedRole(StrEnum):
    """A role an administrator can grant over a scope.

    Separate from ``Role``, which is the coarse account type. These are the
    roles that only mean something *within a scope*: coordinating the Summer
    Internship for ICT is a different grant from coordinating it for CSE, and a
    different grant again from mentoring CSSI students in ICT.

    Coordinator and Mentor are independent. Holding one never implies the other:
    a coordinator who was never assigned as a mentor has no mentee screens, and
    a mentor has no administrative control over the module.
    """

    COORDINATOR = "COORDINATOR"
    MENTOR = "MENTOR"


#: What each assignable role is allowed to do inside its scope.
ASSIGNED_ROLE_CAPABILITIES = {
    AssignedRole.COORDINATOR: (
        "Configure the module, allocate mentors and sections, review any "
        "submission and run allocations — within this scope only."
    ),
    AssignedRole.MENTOR: (
        "See and review the students assigned to them, and record evaluations "
        "the programme allows. No administrative control over the module."
    ),
}


class CoordinationDomain(StrEnum):
    """A module a faculty member can be made coordinator *of*.

    Coordination is always scoped: a faculty member coordinates one domain for
    one department (or institution-wide when the department is left unset).
    This is what makes "Summer Internship coordinator for ICT" different from
    "Summer Internship coordinator for Mechanical".
    """

    CSSI = "CSSI"
    SUMMER_INTERNSHIP = "SUMMER_INTERNSHIP"
    MINOR = "MINOR"
    MOOC = "MOOC"
    OPEN_ELECTIVE = "OPEN_ELECTIVE"
    CORE_ELECTIVE = "CORE_ELECTIVE"
    MENTORSHIP = "MENTORSHIP"


#: Which internship programme type each coordination domain governs.
INTERNSHIP_DOMAIN_FOR_TYPE = {
    "CSSI": CoordinationDomain.CSSI,
    "SUMMER": CoordinationDomain.SUMMER_INTERNSHIP,
}


class StudentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    GRADUATED = "GRADUATED"
    ON_LEAVE = "ON_LEAVE"
    WITHDRAWN = "WITHDRAWN"


class SemesterTerm(StrEnum):
    ODD = "ODD"
    EVEN = "EVEN"
    SUMMER = "SUMMER"


# ───────────────────────────── academics ──────────────────────────────────
class ComponentType(StrEnum):
    """What a slot in a curriculum semester represents."""

    CORE = "CORE"
    OPEN_ELECTIVE = "OPEN_ELECTIVE"
    PROGRAM_CORE_ELECTIVE = "PROGRAM_CORE_ELECTIVE"
    MOOC = "MOOC"
    MINOR = "MINOR"
    INTERNSHIP = "INTERNSHIP"
    PROJECT = "PROJECT"


class CurriculumStatus(StrEnum):
    """Publication lifecycle of one curriculum version.

    A published curriculum is what students are actually served. Editing one in
    place would silently rewrite the rules a cohort is already studying under,
    so the admin API refuses structural edits once published — the way forward
    is a new revision, which is why versions are batch-scoped rather than
    mutable.
    """

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class SourceConfidence(StrEnum):
    """How well an imported curriculum is backed by an official document."""

    #: Transcribed from a current, official PDEU document.
    CONFIRMED_OFFICIAL_SOURCE = "CONFIRMED_OFFICIAL_SOURCE"
    #: The official document exists but does not cover the whole programme.
    PARTIAL_SOURCE = "PARTIAL_SOURCE"
    #: Inferred from official data (e.g. divisions from seat intake), not cited.
    DERIVED_FROM_INTAKE = "DERIVED_FROM_INTAKE"
    #: Sources disagree, or the rule is ambiguous. Never becomes a hard rule.
    REQUIRES_FACULTY_CONFIRMATION = "REQUIRES_FACULTY_CONFIRMATION"


class CourseCategory(StrEnum):
    """The category codes the PDEU course structures print in their tables."""

    BSC = "BSC"      # basic science
    ESC = "ESC"      # engineering science
    HSC = "HSC"      # humanities / social science
    PC = "PC"        # program core
    PE = "PE"        # program / professional elective
    OE = "OE"        # open elective
    PRO = "Pro"      # project, internship, seminar
    IND = "IND"      # Industry 4.0 and department-specific blocks
    OTHER = "OTHER"


class DeliveryMode(StrEnum):
    """Theory / practical / project classification of a course."""

    THEORY = "THEORY"
    PRACTICAL = "PRACTICAL"
    THEORY_PRACTICAL = "THEORY_PRACTICAL"
    PROJECT = "PROJECT"


class SourceScope(StrEnum):
    """Where the course backing a curriculum component may come from."""

    SAME_DEPARTMENT = "SAME_DEPARTMENT"
    OTHER_DEPARTMENT_FOET = "OTHER_DEPARTMENT_FOET"
    OTHER_SCHOOL = "OTHER_SCHOOL"
    EXTERNAL_PLATFORM = "EXTERNAL_PLATFORM"
    ANY = "ANY"


class RegistrationWindowStatus(StrEnum):
    """Where a registration round stands, as the coordinator drives it.

    The round is the authority on whether a student may act, not the clock alone
    and never the browser: a coordinator can lock early, and a window left OPEN
    past its closing time is still closed to students because the backend
    compares the time itself.

        DRAFT -> OPEN -> LOCKED -> ALLOCATED -> PUBLISHED -> CLOSED
    """

    DRAFT = "DRAFT"
    OPEN = "OPEN"
    #: Preferences frozen; allocation not yet run.
    LOCKED = "LOCKED"
    #: Allocation has run but results are not visible to students yet.
    ALLOCATED = "ALLOCATED"
    #: Results released. Students see their seat.
    PUBLISHED = "PUBLISHED"
    CLOSED = "CLOSED"


class StudentRegistrationState(StrEnum):
    """What one student may do in a round right now.

    Derived, never stored — it is a function of the window, the clock and the
    student's own rows, so it can never drift out of step with them.
    """

    NOT_OPEN = "NOT_OPEN"
    OPEN = "OPEN"
    SUBMITTED = "SUBMITTED"
    LOCKED = "LOCKED"
    ALLOCATED = "ALLOCATED"
    CLOSED = "CLOSED"


#: What the student is told, per state. Kept beside the enum so the API and the
#: UI never invent their own wording for the same situation.
REGISTRATION_STATE_LABEL = {
    StudentRegistrationState.NOT_OPEN: "Not open yet",
    StudentRegistrationState.OPEN: "Open — select your preferences",
    StudentRegistrationState.SUBMITTED: "Preferences submitted",
    StudentRegistrationState.LOCKED: "Locked — preferences can no longer be changed",
    StudentRegistrationState.ALLOCATED: "Allocated",
    StudentRegistrationState.CLOSED: "Closed",
}


class OfferingStatus(StrEnum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    ALLOCATED = "ALLOCATED"
    ARCHIVED = "ARCHIVED"


class PreferenceStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    WITHDRAWN = "WITHDRAWN"


class AllocationStatus(StrEnum):
    WAITLISTED = "WAITLISTED"
    ALLOCATED = "ALLOCATED"
    CONFIRMED = "CONFIRMED"
    DROPPED = "DROPPED"
    REJECTED = "REJECTED"


class MoocPlatform(StrEnum):
    NPTEL = "NPTEL"
    SWAYAM = "SWAYAM"
    COURSERA = "COURSERA"
    EDX = "EDX"
    OTHER = "OTHER"


class MoocStatus(StrEnum):
    REGISTERED = "REGISTERED"
    EXAM_SCHEDULED = "EXAM_SCHEDULED"
    CERTIFICATE_UPLOADED = "CERTIFICATE_UPLOADED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


class VerificationStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class MinorApplicationStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    ALLOCATED = "ALLOCATED"
    # Ranked below the seat cut-off in an allocation round. Stored as plain
    # VARCHAR (native_enum=False), so no ALTER TYPE / CHECK migration is needed.
    WAITLISTED = "WAITLISTED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class MinorEnrollmentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    DISCONTINUED = "DISCONTINUED"


# ──────────────────────────── internships ─────────────────────────────────
class InternshipType(StrEnum):
    CSSI = "CSSI"
    SUMMER = "SUMMER"
    RESEARCH = "RESEARCH"
    OTHER = "OTHER"


class ProgramStatus(StrEnum):
    DRAFT = "DRAFT"
    REGISTRATION_OPEN = "REGISTRATION_OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    EVALUATION = "EVALUATION"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class ProgramPhase(StrEnum):
    """Where one student stands relative to a programme's semester window.

    A programme is *floated* by the coordinator a semester before it is carried
    out — CSSI is announced during Semester II so students can find an NGO over
    the break, but nothing may be submitted until Semester III begins.

        sem < announce_from        HIDDEN
        announce_from .. target-1  ANNOUNCED   information only
        target                     ACTIVE      submissions open
        > visible_to               CONCLUDED
    """

    HIDDEN = "HIDDEN"
    ANNOUNCED = "ANNOUNCED"
    ACTIVE = "ACTIVE"
    CONCLUDED = "CONCLUDED"


class EnrollmentStatus(StrEnum):
    REGISTERED = "REGISTERED"
    MENTOR_ASSIGNED = "MENTOR_ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    UNDER_EVALUATION = "UNDER_EVALUATION"
    COMPLETED = "COMPLETED"
    WITHDRAWN = "WITHDRAWN"


class InternshipWindowKind(StrEnum):
    """A dated window a coordinator opens on an internship programme.

    Which windows a programme runs is its configuration (``config["windows"]``),
    not code: CSSI runs REGISTRATION then PRESENTATION; a programme that lists
    none keeps the older semester-only rules.

        REGISTRATION  students record their organisation and its supervisor
        PRESENTATION  posters are submitted to the faculty mentor, presented,
                      and marked — marks lock when the window closes
    """

    REGISTRATION = "REGISTRATION"
    PRESENTATION = "PRESENTATION"


class StageStatus(StrEnum):
    LOCKED = "LOCKED"
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


class OrganizationType(StrEnum):
    NGO = "NGO"
    COMPANY = "COMPANY"
    STARTUP = "STARTUP"
    RESEARCH_LAB = "RESEARCH_LAB"
    GOVERNMENT = "GOVERNMENT"
    ACADEMIC = "ACADEMIC"


class DocumentType(StrEnum):
    OFFER_LETTER = "OFFER_LETTER"
    CERTIFICATE = "CERTIFICATE"
    REPORT = "REPORT"
    POSTER = "POSTER"
    PRESENTATION = "PRESENTATION"
    PHOTO = "PHOTO"
    JOINING_LETTER = "JOINING_LETTER"
    COMPLETION_LETTER = "COMPLETION_LETTER"
    SYLLABUS = "SYLLABUS"
    OTHER = "OTHER"


class ReportType(StrEnum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    FORTNIGHTLY = "FORTNIGHTLY"
    MONTHLY = "MONTHLY"
    FINAL = "FINAL"


class ReportFrequency(StrEnum):
    NONE = "NONE"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    FORTNIGHTLY = "FORTNIGHTLY"
    MONTHLY = "MONTHLY"


class SubmissionStatus(StrEnum):
    """Lifecycle of one submitted artefact (document or periodic report).

    NOT_SUBMITTED never appears in the database — a row simply does not exist
    yet. It is synthesised by `services/documents.expected_documents()` so a
    missing mandatory item stays *visible* on the student profile instead of
    silently disappearing.

        (no row) NOT_SUBMITTED → SUBMITTED → UNDER_REVIEW → VERIFIED
                                                         ↘ REJECTED → resubmit
    """

    NOT_SUBMITTED = "NOT_SUBMITTED"
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    # Retained so historical rows keep meaning; treated as VERIFIED.
    APPROVED = "APPROVED"
    REVISION_REQUESTED = "REVISION_REQUESTED"


#: Statuses that satisfy a mandatory requirement.
SATISFYING_STATUSES = frozenset({SubmissionStatus.VERIFIED, SubmissionStatus.APPROVED})
#: Statuses awaiting a reviewer decision.
PENDING_REVIEW_STATUSES = frozenset({
    SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW,
})


class EvaluationStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    FINALISED = "FINALISED"


class EvaluatorRole(StrEnum):
    FACULTY_MENTOR = "FACULTY_MENTOR"
    INDUSTRY_MENTOR = "INDUSTRY_MENTOR"
    COORDINATOR = "COORDINATOR"
    PANEL = "PANEL"


# ────────────────────────── clubs & events ────────────────────────────────
class ClubCategory(StrEnum):
    TECHNICAL = "TECHNICAL"
    CULTURAL = "CULTURAL"
    SPORTS = "SPORTS"
    SOCIAL = "SOCIAL"
    ENTREPRENEURSHIP = "ENTREPRENEURSHIP"
    LITERARY = "LITERARY"
    OTHER = "OTHER"


class ClubMemberRole(StrEnum):
    MEMBER = "MEMBER"
    CORE = "CORE"
    SECRETARY = "SECRETARY"
    HEAD = "HEAD"


class EventType(StrEnum):
    EVENT = "EVENT"
    SEMINAR = "SEMINAR"
    WORKSHOP = "WORKSHOP"
    COMPETITION = "COMPETITION"
    MEETUP = "MEETUP"
    GUEST_LECTURE = "GUEST_LECTURE"


class EventMode(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    HYBRID = "HYBRID"


class EventStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class RegistrationStatus(StrEnum):
    REGISTERED = "REGISTERED"
    WAITLISTED = "WAITLISTED"
    CANCELLED = "CANCELLED"
    ATTENDED = "ATTENDED"
    NO_SHOW = "NO_SHOW"


# ─────────────────── mentorship, announcements, alerts ────────────────────
class MeetingStatus(StrEnum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    RESCHEDULED = "RESCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class MeetingMode(StrEnum):
    IN_PERSON = "IN_PERSON"
    ONLINE = "ONLINE"
    PHONE = "PHONE"


class AudienceType(StrEnum):
    ALL = "ALL"
    ROLE = "ROLE"
    DEPARTMENT = "DEPARTMENT"
    PROGRAM = "PROGRAM"
    SEMESTER = "SEMESTER"
    CLUB = "CLUB"
    MENTEES = "MENTEES"
    INTERNSHIP_PROGRAM = "INTERNSHIP_PROGRAM"


class AnnouncementCategory(StrEnum):
    GENERAL = "GENERAL"
    ACADEMIC = "ACADEMIC"
    EXAMINATION = "EXAMINATION"
    INTERNSHIP = "INTERNSHIP"
    EVENT = "EVENT"
    MENTORSHIP = "MENTORSHIP"
    URGENT = "URGENT"


class Priority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class NotificationType(StrEnum):
    ELECTIVE_DEADLINE = "ELECTIVE_DEADLINE"
    ELECTIVE_ALLOCATION = "ELECTIVE_ALLOCATION"
    REGISTRATION_CONFIRMED = "REGISTRATION_CONFIRMED"
    INTERNSHIP_SUBMISSION = "INTERNSHIP_SUBMISSION"
    INTERNSHIP_STAGE = "INTERNSHIP_STAGE"
    EVALUATION_UPDATE = "EVALUATION_UPDATE"
    EVENT_ANNOUNCEMENT = "EVENT_ANNOUNCEMENT"
    MENTOR_ANNOUNCEMENT = "MENTOR_ANNOUNCEMENT"
    MEETING_UPDATE = "MEETING_UPDATE"
    MINOR_APPLICATION = "MINOR_APPLICATION"
    INTERNSHIP_WINDOW = "INTERNSHIP_WINDOW"
    SYSTEM = "SYSTEM"


class FileCategory(StrEnum):
    CERTIFICATE = "CERTIFICATE"
    REPORT = "REPORT"
    OFFER_LETTER = "OFFER_LETTER"
    POSTER = "POSTER"
    PHOTO = "PHOTO"
    SYLLABUS = "SYLLABUS"
    AVATAR = "AVATAR"
    OTHER = "OTHER"


class AuditAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    LOGIN = "LOGIN"
    ALLOCATION_RUN = "ALLOCATION_RUN"
    ALLOCATION_OVERRIDE = "ALLOCATION_OVERRIDE"
    MENTOR_ASSIGN = "MENTOR_ASSIGN"
    MENTOR_OVERRIDE = "MENTOR_OVERRIDE"
    EVALUATION_SUBMIT = "EVALUATION_SUBMIT"
    EVALUATION_UPDATE = "EVALUATION_UPDATE"
    STATUS_CHANGE = "STATUS_CHANGE"
    PUBLISH = "PUBLISH"
    UPLOAD = "UPLOAD"
