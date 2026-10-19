"""A list costs the same number of queries whatever its length.

Measured on the 10,000-student QA dataset (reports/qa/evidence/query_profile_*):
a mentor's mentee list ran 4,676 queries (4.3 s) for 1,900 mentees, ~2.4 per
mentee; the Mentorship coordinator's dashboard loaded every assignment in the
department to take two counts. Both are now fixed, and these tests keep them so:
the count for 25 rows must equal the count for 5.
"""
from __future__ import annotations

from sqlalchemy import event

from app.models.engagement import MentorAssignment
from app.tests.test_internship_windows import _student


def _queries(db, call) -> int:
    count = [0]

    def tick(*_):
        count[0] += 1
    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", tick)
    try:
        response = call()
        assert response.status_code == 200, response.text
    finally:
        event.remove(engine, "before_cursor_execute", tick)
    return count[0]


def _mentees(db, world, start, n):
    for i in range(start, start + n):
        student = _student(db, world, f"24BIT{700 + i}", semester=4)
        db.add(MentorAssignment(student_id=student.id, faculty_id=world.mentor_ict.faculty.id, is_active=True))
    db.flush()


def test_the_mentee_list_does_not_grow_a_query_per_mentee(api, db, world, login):
    headers = login(world.mentor_ict.email)
    _mentees(db, world, 0, 5)
    small = _queries(db, lambda: api.get("/api/v1/mentorship/my-mentees", headers=headers))
    _mentees(db, world, 5, 20)
    large = _queries(db, lambda: api.get("/api/v1/mentorship/my-mentees", headers=headers))
    assert large == small


def test_the_internship_student_list_does_not_grow_a_query_per_row(api, db, world, login):
    from app.models.enums import InternshipType
    from app.models.internships import InternshipEnrollment, InternshipProgram

    program = InternshipProgram(code="SI-Q", name="Summer", type=InternshipType.SUMMER,
                                department_id=world.departments["ICT"].id, target_semester=6)
    db.add(program)
    db.flush()

    def enrol(start, n):
        for i in range(start, start + n):
            student = _student(db, world, f"22BIT{800 + i}", semester=6)
            db.add(InternshipEnrollment(program_id=program.id, student_id=student.id))
        db.flush()

    headers = login(world.admin.email)
    enrol(0, 5)
    small = _queries(db, lambda: api.get("/api/v1/internships/enrollments", headers=headers))
    enrol(5, 20)
    large = _queries(db, lambda: api.get("/api/v1/internships/enrollments", headers=headers))
    assert large == small
