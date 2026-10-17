"""Import every model so Alembic autogenerate and mapper configuration see them."""
from app.db.base import Base
from app.models.academics import (
    Course, CourseOffering, CourseSection, Curriculum, CurriculumComponent,
    ElectiveAllocation, ElectivePreference, ElectiveRegistrationWindow,
    ElectiveType, MoocRegistration, Program, ProgramDivision,
)
from app.models.community import (
    Club, ClubMember, Event, EventInterest, EventRegistration,
)
from app.models.engagement import (
    Announcement, MentorAssignment, MentorMeeting, Notification,
)
from app.models.identity import (
    AcademicYear, Department, Faculty, FacultyRoleAssignment, Semester, Student,
    User, UserRole,
)
from app.models.internships import (
    EnrollmentStageProgress, EvaluationCriteria, EvaluationScore, InternshipDocument,
    InternshipEnrollment, InternshipEvaluation, InternshipGroup, InternshipProgram,
    InternshipWindow,
    InternshipProject, InternshipReport, InternshipStage, Organization,
)
from app.models.minors import (
    MinorApplication, MinorCourse, MinorEnrollment, MinorProgram,
)
from app.models.system import AuditLog, StoredFile

__all__ = [
    "Base",
    # identity
    "User", "UserRole", "Department", "AcademicYear", "Semester", "Student", "Faculty",
    "FacultyRoleAssignment",
    # academics
    "Program", "ProgramDivision", "ElectiveType", "Curriculum", "CurriculumComponent",
    "Course",
    "CourseOffering", "CourseSection", "ElectivePreference", "ElectiveAllocation",
    "ElectiveRegistrationWindow",
    "MoocRegistration",
    # minors
    "MinorProgram", "MinorCourse", "MinorApplication", "MinorEnrollment",
    # internships
    "Organization", "InternshipProgram", "InternshipStage", "InternshipGroup",
    "InternshipWindow",
    "InternshipEnrollment", "EnrollmentStageProgress", "InternshipProject",
    "InternshipDocument", "InternshipReport", "EvaluationCriteria",
    "InternshipEvaluation", "EvaluationScore",
    # community
    "Club", "ClubMember", "Event", "EventRegistration", "EventInterest",
    # engagement
    "MentorAssignment", "MentorMeeting", "Announcement", "Notification",
    # system
    "StoredFile", "AuditLog",
]
