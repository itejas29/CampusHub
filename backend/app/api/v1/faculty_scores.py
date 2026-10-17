"""Faculty performance scores — who sees what.

* A faculty member sees their own score, with every scored item.
* A Head of Department sees their department; the registrar sees any.
* Nobody else — not students, not other faculty — sees anyone's score.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, get_optional_faculty
from app.core.errors import NotFoundError, PermissionDeniedError
from app.models.enums import Role
from app.models.identity import Department, Faculty
from app.services import faculty_scoring as scoring
from app.services import scope

router = APIRouter(prefix="/faculty-scores", tags=["faculty scores"])


class ScoreEntryOut(BaseModel):
    when: str
    category: str
    label: str
    outcome: str
    points: int
    days: float | None = None


class FacultyScoreOut(BaseModel):
    faculty_id: int
    name: str
    designation: str | None = None
    is_demo: bool = False
    #: False for real faculty until SCORE_REAL_FACULTY is switched on.
    is_scored: bool = True
    points: int
    on_time: int
    late: int
    overdue: int
    missed: int
    pending: int
    scored: int
    on_time_rate: float | None
    band: str
    by_category: dict[str, int]
    entries: list[ScoreEntryOut] = []


class ScorePolicyOut(BaseModel):
    policy: dict[str, int]
    scores_real_faculty: bool
    note: str = ("Weights are set by the department, not by a PDEU rule, and apply to the "
                 "last period_days days.")


class DepartmentScoresOut(BaseModel):
    department_code: str
    department_name: str
    policy: dict[str, int]
    scores_real_faculty: bool
    faculty: list[FacultyScoreOut]


def _out(db, score: scoring.Score, *, with_entries: bool) -> FacultyScoreOut:
    f = db.get(Faculty, score.faculty_id)
    is_scored = scoring.is_scorable(f)
    entries = sorted(score.entries, key=lambda e: e.when, reverse=True)[:40] if with_entries else []
    return FacultyScoreOut(
        faculty_id=f.id, name=f.user.full_name, designation=f.designation, is_demo=f.is_demo,
        points=score.points, on_time=score.on_time, late=score.late, overdue=score.overdue,
        missed=score.missed, pending=score.pending, scored=score.scored,
        on_time_rate=round(score.on_time_rate, 3) if score.on_time_rate is not None else None,
        is_scored=is_scored, band=score.band if is_scored else "Not scored yet",
        by_category=dict(score.by_category),
        entries=[ScoreEntryOut(when=e.when.isoformat(), category=e.category, label=e.label,
                               outcome=e.outcome, points=e.points, days=e.days) for e in entries],
    )


@router.get("/me", response_model=FacultyScoreOut)
def my_score(db: DbSession, user: CurrentUser,
             faculty=Depends(get_optional_faculty)) -> FacultyScoreOut:
    if faculty is None:
        raise PermissionDeniedError("Only faculty have a performance score.")
    return _out(db, scoring.faculty_score(db, faculty), with_entries=True)


@router.get("/policy", response_model=ScorePolicyOut)
def policy(_: CurrentUser) -> ScorePolicyOut:
    return ScorePolicyOut(policy=scoring.POLICY, scores_real_faculty=settings.SCORE_REAL_FACULTY)


def _department_for(db, user, department_id: int | None) -> Department:
    if user.has_role(Role.SUPER_ADMIN):
        dept = db.get(Department, department_id) if department_id else \
            db.scalar(select(Department).where(Department.code == "ICT"))
        if dept is None:
            raise NotFoundError("Department not found.")
        return dept
    headed = scope.hod_department(db, user)
    if headed is None or (department_id and department_id != headed.id):
        raise PermissionDeniedError("Only the Head of Department sees the department's scores.")
    return headed


@router.get("/department", response_model=DepartmentScoresOut)
def department_scores(db: DbSession, user: CurrentUser,
                      department_id: int | None = None) -> DepartmentScoresOut:
    dept = _department_for(db, user, department_id)
    scores = scoring.department_scores(db, dept.id)
    members = db.scalars(select(Faculty).where(Faculty.department_id == dept.id,
                                               Faculty.is_active.is_(True)))
    rows = [_out(db, scores.get(f.id) or scoring.Score(faculty_id=f.id), with_entries=False)
            for f in members if f.id != dept.hod_faculty_id and not scoring.is_office(f)]
    rows.sort(key=lambda r: (not r.is_scored, r.scored == 0, -(r.on_time_rate or 0),
                             -r.points, r.name))
    return DepartmentScoresOut(department_code=dept.code, department_name=dept.name,
                               policy=scoring.POLICY,
                               scores_real_faculty=settings.SCORE_REAL_FACULTY, faculty=rows)


@router.get("/faculty/{faculty_id}", response_model=FacultyScoreOut)
def one_faculty(faculty_id: int, db: DbSession, user: CurrentUser,
                faculty=Depends(get_optional_faculty)) -> FacultyScoreOut:
    target = db.get(Faculty, faculty_id)
    if target is None:
        raise NotFoundError("Faculty member not found.")
    if not (faculty is not None and faculty.id == target.id):
        _department_for(db, user, target.department_id)
    return _out(db, scoring.faculty_score(db, target), with_entries=True)
