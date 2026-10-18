"""NPTEL / NCC rounds: approved list, choice, outcome, carry-over

How the ICT department runs the Semester V Open Elective: the coordinator
circulates an approved NPTEL list (12-week courses), each student picks one
course or NCC, and submits the certificate at the end of the semester — or
says they did not pass. A slot not cleared carries over to the next semester;
not cleared then, it is a backlog.

Revision ID: 0017_nptel_ncc_rounds
Revises: 0016_course_syllabus
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_nptel_ncc_rounds"
down_revision = "0016_course_syllabus"
branch_labels = None
depends_on = None


def _stamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.add_column("courses", sa.Column("provider_details", sa.JSON(), nullable=True))

    op.create_table(
        "mooc_rounds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("department_id", sa.Integer(),
                  sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("curriculum_component_id", sa.Integer(),
                  sa.ForeignKey("curriculum_components.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("eligible_semesters", sa.JSON(), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("platform_deadline", sa.Date(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps(),
    )
    op.create_index("ix_mooc_rounds_department_id", "mooc_rounds", ["department_id"])
    op.create_index("ix_mooc_rounds_curriculum_component_id", "mooc_rounds",
                    ["curriculum_component_id"])

    op.create_table(
        "mooc_round_courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mooc_round_id", sa.Integer(),
                  sa.ForeignKey("mooc_rounds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(),
                  sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        *_stamps(),
        sa.UniqueConstraint("mooc_round_id", "course_id",
                            name="uq_mooc_round_courses_round_course"),
    )
    op.create_index("ix_mooc_round_courses_mooc_round_id", "mooc_round_courses",
                    ["mooc_round_id"])
    op.create_index("ix_mooc_round_courses_course_id", "mooc_round_courses", ["course_id"])

    op.create_table(
        "mooc_round_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mooc_round_id", sa.Integer(),
                  sa.ForeignKey("mooc_rounds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(),
                  sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("curriculum_component_id", sa.Integer(),
                  sa.ForeignKey("curriculum_components.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("semester_at_close", sa.Integer(), nullable=True),
        *_stamps(),
        sa.UniqueConstraint("mooc_round_id", "student_id",
                            name="uq_mooc_round_outcomes_round_student"),
    )
    for column in ("mooc_round_id", "student_id", "curriculum_component_id"):
        op.create_index(f"ix_mooc_round_outcomes_{column}", "mooc_round_outcomes", [column])

    with op.batch_alter_table("mooc_registrations") as batch:
        batch.alter_column("course_offering_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("mooc_round_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("option", sa.String(10), nullable=False,
                                   server_default="NPTEL"))
        batch.add_column(sa.Column("course_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_mooc_registrations_mooc_round_id_mooc_rounds",
                                 "mooc_rounds", ["mooc_round_id"], ["id"],
                                 ondelete="CASCADE")
        batch.create_foreign_key("fk_mooc_registrations_course_id_courses",
                                 "courses", ["course_id"], ["id"], ondelete="SET NULL")
        batch.create_unique_constraint("uq_mooc_registrations_round_student",
                                       ["mooc_round_id", "student_id"])
    op.create_index("ix_mooc_registrations_mooc_round_id", "mooc_registrations",
                    ["mooc_round_id"])
    op.create_index("ix_mooc_registrations_course_id", "mooc_registrations", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_mooc_registrations_course_id", "mooc_registrations")
    op.drop_index("ix_mooc_registrations_mooc_round_id", "mooc_registrations")
    with op.batch_alter_table("mooc_registrations") as batch:
        batch.drop_constraint("uq_mooc_registrations_round_student", type_="unique")
        batch.drop_constraint("fk_mooc_registrations_course_id_courses", type_="foreignkey")
        batch.drop_constraint("fk_mooc_registrations_mooc_round_id_mooc_rounds",
                              type_="foreignkey")
        batch.drop_column("course_id")
        batch.drop_column("option")
        batch.drop_column("mooc_round_id")
    op.drop_table("mooc_round_outcomes")
    op.drop_table("mooc_round_courses")
    op.drop_table("mooc_rounds")
    op.drop_column("courses", "provider_details")
