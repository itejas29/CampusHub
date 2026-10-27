"""one active faculty mentor per student (QA-15)

The unique constraint on (student_id, academic_year_id) let a student hold two
active mentors: NULL academic years never collide, and a new academic year
left last year's assignment active beside the new one. The rule, confirmed by
the project owner on 24 Oct 2026, is one active mentor per student in any year.

Existing duplicates are resolved, not hidden: for each student the most recent
active assignment (assigned_at, then id) stays active, the others become
inactive history — nothing is deleted — and every row changed gets an audit
entry. Preview what would change with:

    python -m app.seed.report_mentor_duplicates

Then the partial unique index enforces it from here on.

Revision ID: 0019_one_active_mentor
Revises: 0018_account_security
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0019_one_active_mentor"
down_revision = "0018_account_security"
branch_labels = None
depends_on = None

INDEX = "uq_mentor_assignments_one_active_per_student"


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, student_id, faculty_id, assigned_at FROM mentor_assignments "
        "WHERE is_active ORDER BY student_id")).mappings().all()
    by_student: dict[int, list] = {}
    for row in rows:
        by_student.setdefault(row["student_id"], []).append(row)
    retired = 0
    for student_id, active in by_student.items():
        if len(active) < 2:
            continue
        # Most recent first; a missing assigned_at counts as oldest.
        active = sorted(active, key=lambda r: (r["assigned_at"] is not None,
                                               str(r["assigned_at"] or ""), r["id"]),
                        reverse=True)
        kept, extras = active[0], active[1:]
        for extra in extras:
            bind.execute(sa.text(
                "UPDATE mentor_assignments SET is_active = :f WHERE id = :id"),
                {"f": False, "id": extra["id"]})
            bind.execute(sa.text(
                "INSERT INTO audit_logs (actor_user_id, actor_label, action, entity_type, "
                "entity_id, description, meta) VALUES (NULL, :label, :action, "
                ":etype, :eid, :desc, :meta)"),
                {"label": "migration 0019", "action": "MENTOR_OVERRIDE",
                 "etype": "mentor_assignment", "eid": extra["id"],
                 "desc": (f"Retired duplicate active mentor assignment {extra['id']} "
                          f"for student {student_id}; kept {kept['id']}"),
                 "meta": json.dumps({"student_id": student_id, "kept": kept["id"],
                                     "retired_faculty_id": extra["faculty_id"],
                                     "kept_faculty_id": kept["faculty_id"]})})
            retired += 1
    if retired:
        print(f"0019: retired {retired} duplicate active mentor assignment(s) "
              f"for {sum(1 for a in by_student.values() if len(a) > 1)} student(s); "
              "see audit_logs (actor_label 'migration 0019').")

    op.create_index(INDEX, "mentor_assignments", ["student_id"], unique=True,
                    postgresql_where=sa.text("is_active"),
                    sqlite_where=sa.text("is_active = 1"))


def downgrade() -> None:
    # The retired rows stay inactive: which mentor was "real" was decided by
    # the department's rule, and undoing it would bring the duplicates back.
    op.drop_index(INDEX, table_name="mentor_assignments")
