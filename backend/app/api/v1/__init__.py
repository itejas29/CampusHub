"""API v1 router assembly."""
from fastapi import APIRouter

from app.api.v1 import (admin, announcements, auth, calendar, chatbot, clubs,
    courses, curriculum, dashboard, electives, events, faculty_scores, files, internships,
    mentorship, minors, mooc, notifications, people, roles, student_profile
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(people.me_router)
api_router.include_router(dashboard.router)
api_router.include_router(chatbot.router)

# Academics
api_router.include_router(curriculum.router)
api_router.include_router(courses.router)
api_router.include_router(courses.offerings_router)
api_router.include_router(electives.router)
api_router.include_router(mooc.router)
api_router.include_router(minors.router)

# Internships
api_router.include_router(internships.router)
api_router.include_router(internships.org_router)

# Community
api_router.include_router(clubs.router)
api_router.include_router(events.router)
api_router.include_router(calendar.router)

# People & engagement
api_router.include_router(people.students_router)
api_router.include_router(people.faculty_router)
api_router.include_router(people.departments_router)
api_router.include_router(people.academic_router)
api_router.include_router(student_profile.router)
api_router.include_router(mentorship.router)
api_router.include_router(faculty_scores.router)
api_router.include_router(announcements.router)
api_router.include_router(notifications.router)

# Platform
api_router.include_router(files.router)
api_router.include_router(admin.router)
api_router.include_router(roles.router)

__all__ = ["api_router"]
