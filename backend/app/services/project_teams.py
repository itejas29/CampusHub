"""Project teams and guide preferences (Semester VII / VIII projects).

Configuration on the programme — and a track may switch either off:

* `config["team_size"] = {"min": 1, "max": 4}` — teams are allowed, of up to
  four; a student may also work alone. No setting, no teams.
* `config["guide_preferences"] = 3` — how many guides a student (or a team, by
  its leader) may rank. No setting, no preferences.

The rules:

* A team is formed by a registered student, who leads it, and grows by roll
  number. Every member is registered for the same programme and track and is
  in no other team. The leader removes members; a member may leave; a leader
  alone can dissolve the team.
* A team shares one guide. Once a guide is assigned, the team is fixed.
* Preferences name eligible guides of the programme's department; a team's are
  set by its leader and held by every member.
* Allocation by preference serves teams and solo students in the order they
  registered: each gets the highest-ranked guide with room for all of them.
  Whoever cannot be placed is left for the coordinator.

The team size and the number of preferences are the department's to confirm.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import BusinessRuleError, NotFoundError, ValidationError
from app.models.enums import AuditAction
from app.models.identity import Faculty, Student, User
from app.models.internships import InternshipEnrollment, InternshipProgram, ProjectTeam
from app.services import audit
from app.services import internships as engine


def _setting(program: InternshipProgram, enrollment: InternshipEnrollment | None, key: str):
    """A programme setting, unless the student's track switches it off."""
    track = next((t for t in engine.program_tracks(program)
                  if enrollment is not None and t.get("key") == enrollment.track), None)
    if track is not None and key in track:
        return track[key]
    return (program.config or {}).get(key)


def team_limits(program: InternshipProgram, enrollment: InternshipEnrollment | None) -> dict | None:
    size = _setting(program, enrollment, "team_size")
    return dict(size) if size else None


def preference_count(program: InternshipProgram, enrollment: InternshipEnrollment | None) -> int:
    return int(_setting(program, enrollment, "guide_preferences") or 0)


def members(db: Session, team: ProjectTeam) -> list[InternshipEnrollment]:
    return list(db.scalars(select(InternshipEnrollment).where(
        InternshipEnrollment.team_id == team.id).order_by(InternshipEnrollment.id)))


def _assert_open(db: Session, team: ProjectTeam) -> None:
    if any(m.mentor_faculty_id for m in members(db, team)):
        raise BusinessRuleError("Your team has a guide now, so its members are fixed. "
                                "Ask the coordinator for any change.")


def _assert_leader(team: ProjectTeam, enrollment: InternshipEnrollment) -> None:
    if team.leader_enrollment_id != enrollment.id:
        raise BusinessRuleError("Only the team leader can do this.")


def create_team(db: Session, enrollment: InternshipEnrollment, name: str, *, actor: User) -> ProjectTeam:
    program = enrollment.program
    if not team_limits(program, enrollment):
        raise BusinessRuleError(f"{program.name} is done individually"
                                + (" on this track." if enrollment.track else "."))
    if enrollment.team_id:
        raise BusinessRuleError("You are already in a team.")
    if enrollment.mentor_faculty_id:
        raise BusinessRuleError("You already have a guide; ask the coordinator to form a team.")
    team = ProjectTeam(program_id=program.id, name=(name or "").strip()[:120] or "Project team",
                       leader_enrollment_id=enrollment.id)
    db.add(team)
    db.flush()
    enrollment.team_id = team.id
    audit.record(db, action=AuditAction.CREATE, entity_type="project_team", entity_id=team.id,
                 actor=actor, description=f"Team “{team.name}” formed in {program.code}")
    db.flush()
    return team


def add_member(db: Session, team: ProjectTeam, leader: InternshipEnrollment, roll_number: str, *,
               actor: User) -> InternshipEnrollment:
    _assert_leader(team, leader)
    _assert_open(db, team)
    limits = team_limits(leader.program, leader) or {}
    current = members(db, team)
    if len(current) >= int(limits.get("max", 1)):
        raise BusinessRuleError(f"A team has at most {limits.get('max')} members.")
    student = db.scalar(select(Student).where(
        func.upper(Student.roll_number) == (roll_number or "").strip().upper()))
    if student is None:
        raise NotFoundError(f"No student with roll number {roll_number}.")
    joining = db.scalar(select(InternshipEnrollment).where(
        InternshipEnrollment.program_id == team.program_id,
        InternshipEnrollment.student_id == student.id))
    if joining is None:
        raise BusinessRuleError(f"{student.roll_number} has not registered for "
                                f"{leader.program.name} yet.")
    if joining.track != leader.track:
        raise BusinessRuleError(f"{student.roll_number} is on a different track.")
    if joining.team_id:
        raise BusinessRuleError(f"{student.roll_number} is already in a team.")
    if joining.mentor_faculty_id:
        raise BusinessRuleError(f"{student.roll_number} already has a guide.")
    joining.team_id = team.id
    # The team shares its leader's guide preferences.
    joining.guide_preferences = list(leader.guide_preferences or [])
    audit.record(db, action=AuditAction.UPDATE, entity_type="project_team", entity_id=team.id,
                 actor=actor, description=f"{student.roll_number} added to team “{team.name}”")
    db.flush()
    return joining


def remove_member(db: Session, team: ProjectTeam, acting: InternshipEnrollment,
                  leaving: InternshipEnrollment, *, actor: User) -> None:
    if leaving.team_id != team.id:
        raise ValidationError("That student is not in this team.")
    if acting.id != leaving.id:
        _assert_leader(team, acting)
    _assert_open(db, team)
    current = members(db, team)
    if leaving.id == team.leader_enrollment_id and len(current) > 1:
        raise BusinessRuleError("Remove the other members before leaving the team you lead.")
    leaving.team_id = None
    if len(current) == 1:
        db.delete(team)
    audit.record(db, action=AuditAction.UPDATE, entity_type="project_team", entity_id=team.id,
                 actor=actor, description=f"{leaving.student.roll_number} left team “{team.name}”")
    db.flush()


def set_preferences(db: Session, enrollment: InternshipEnrollment, faculty_ids: list[int], *,
                    actor: User) -> list[int]:
    program = enrollment.program
    allowed = preference_count(program, enrollment)
    if not allowed:
        raise BusinessRuleError(f"{program.name} does not take guide preferences.")
    if enrollment.mentor_faculty_id:
        raise BusinessRuleError("You already have a guide.")
    if len(faculty_ids) > allowed:
        raise ValidationError(f"Rank at most {allowed} guides.")
    if len(set(faculty_ids)) != len(faculty_ids):
        raise ValidationError("Each guide can be listed once.")
    eligible = {f.id for f in engine.eligible_mentors(db, program)}
    if any(fid not in eligible for fid in faculty_ids):
        raise ValidationError("Choose guides from the programme's department.")
    team = db.get(ProjectTeam, enrollment.team_id) if enrollment.team_id else None
    if team is not None:
        _assert_leader(team, enrollment)
    targets = members(db, team) if team else [enrollment]
    for member in targets:
        member.guide_preferences = list(faculty_ids)
    audit.record(db, action=AuditAction.UPDATE, entity_type="internship_enrollment",
                 entity_id=enrollment.id, actor=actor,
                 description=f"Guide preferences set ({len(faculty_ids)})",
                 meta={"faculty_ids": faculty_ids, "team_id": team.id if team else None})
    db.flush()
    return faculty_ids


def allocate_by_preference(db: Session, program: InternshipProgram, *, actor: User) -> dict:
    """Give each team or solo student without a guide their best-ranked guide with room."""
    capacity = engine.mentor_capacity(program)
    loads = dict(db.execute(
        select(InternshipEnrollment.mentor_faculty_id, func.count(InternshipEnrollment.id))
        .where(InternshipEnrollment.program_id == program.id,
               InternshipEnrollment.mentor_faculty_id.is_not(None))
        .group_by(InternshipEnrollment.mentor_faculty_id)).all())
    waiting = list(db.scalars(select(InternshipEnrollment).where(
        InternshipEnrollment.program_id == program.id,
        InternshipEnrollment.mentor_faculty_id.is_(None)).order_by(
        InternshipEnrollment.registered_at, InternshipEnrollment.id)))
    units, seen = [], set()
    for e in waiting:
        if e.team_id:
            if e.team_id in seen:
                continue
            seen.add(e.team_id)
            units.append([m for m in waiting if m.team_id == e.team_id])
        else:
            units.append([e])
    placed = left = 0
    for unit in units:
        prefs = unit[0].guide_preferences or []
        guide = next((fid for fid in prefs if loads.get(fid, 0) + len(unit) <= capacity), None)
        if guide is None:
            left += len(unit)
            continue
        for member in unit:
            engine.override_mentor(db, enrollment=member, new_faculty_id=guide,
                                   reason="Guide allocated by preference", actor=actor,
                                   enforce_capacity=False)
        loads[guide] = loads.get(guide, 0) + len(unit)
        placed += len(unit)
    audit.record(db, action=AuditAction.ALLOCATION_RUN, entity_type="internship_program",
                 entity_id=program.id, actor=actor,
                 description=f"Guides allocated by preference in {program.code}: "
                             f"{placed} placed, {left} left for the coordinator",
                 meta={"placed": placed, "left": left})
    db.flush()
    return {"placed": placed, "left": left}


def team_out(db: Session, enrollment: InternshipEnrollment) -> dict | None:
    if not enrollment.team_id:
        return None
    team = db.get(ProjectTeam, enrollment.team_id)
    if team is None:
        return None
    return {
        "id": team.id, "name": team.name,
        "leader_enrollment_id": team.leader_enrollment_id,
        "members": [{"enrollment_id": m.id, "name": m.student.user.full_name,
                     "roll_number": m.student.roll_number} for m in members(db, team)],
        "is_fixed": any(m.mentor_faculty_id for m in members(db, team)),
    }


def preference_names(db: Session, enrollment: InternshipEnrollment) -> list[dict]:
    out = []
    for fid in enrollment.guide_preferences or []:
        faculty = db.get(Faculty, fid)
        if faculty is not None:
            out.append({"faculty_id": fid, "name": faculty.user.full_name})
    return out
