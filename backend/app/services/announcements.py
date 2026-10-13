"""Who an announcement is for.

One rule, evaluated server-side, for every screen that lists announcements. The
dashboard panel used to run its own query with no audience filter at all, so a
notice addressed to one mentor's mentees — or to Semester VI — reached every
account that opened a dashboard, while the Announcements page beside it hid the
same notice correctly. Keeping the rule here is what stops the two drifting.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.engagement import Announcement, MentorAssignment
from app.models.enums import AudienceType
from app.models.identity import Faculty, Student, User
from app.models.internships import InternshipEnrollment


def visible_to(db: Session, user: User, now: dt.datetime | None = None):
    """A select of the published, unexpired announcements addressed to `user`."""
    now = now or dt.datetime.now(dt.timezone.utc)
    student = db.scalar(select(Student).where(Student.user_id == user.id))
    faculty = db.scalar(select(Faculty).where(Faculty.user_id == user.id))

    conditions = [Announcement.audience_type == AudienceType.ALL]
    for role in user.roles:
        conditions.append(
            (Announcement.audience_type == AudienceType.ROLE)
            & (Announcement.audience_ref_value == role.value)
        )
    if student:
        conditions.append(
            (Announcement.audience_type == AudienceType.DEPARTMENT)
            & (Announcement.audience_ref_id == student.department_id)
        )
        conditions.append(
            (Announcement.audience_type == AudienceType.PROGRAM)
            & (Announcement.audience_ref_id == student.program_id)
        )
        conditions.append(
            (Announcement.audience_type == AudienceType.SEMESTER)
            & (Announcement.audience_ref_id == student.current_semester)
        )
        mentor_ids = list(db.scalars(
            select(MentorAssignment.faculty_id).where(
                MentorAssignment.student_id == student.id,
                MentorAssignment.is_active.is_(True),
            )
        ))
        if mentor_ids:
            conditions.append(
                (Announcement.audience_type == AudienceType.MENTEES)
                & (Announcement.audience_ref_id.in_(mentor_ids))
            )
        # A notice to an internship programme is for the students on it. Being
        # in the semester the programme usually runs in is not enrolment.
        program_ids = list(db.scalars(
            select(InternshipEnrollment.program_id).where(
                InternshipEnrollment.student_id == student.id
            )
        ))
        if program_ids:
            conditions.append(
                (Announcement.audience_type == AudienceType.INTERNSHIP_PROGRAM)
                & (Announcement.audience_ref_id.in_(program_ids))
            )
    if faculty:
        conditions.append(
            (Announcement.audience_type == AudienceType.DEPARTMENT)
            & (Announcement.audience_ref_id == faculty.department_id)
        )
        conditions.append(
            (Announcement.audience_type == AudienceType.MENTEES)
            & (Announcement.audience_ref_id == faculty.id)
        )

    return select(Announcement).where(
        Announcement.is_published.is_(True),
        or_(Announcement.expires_at.is_(None), Announcement.expires_at > now),
        or_(*conditions),
    )
