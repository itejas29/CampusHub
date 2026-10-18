"""two-stage elective rounds: an interest round, a shortlist, a final round

The ICT department chooses its Semester VII electives in two rounds: students
first tick the subjects they are interested in, the coordinator shortlists from
the votes, and students then tick the shortlisted subjects they will take. The
numbers involved (how many to tick, the minimum strength, the section size)
change year to year, so each round carries its own.

Existing rounds become RANKED, which is how they already behave.

Revision ID: 0012_two_stage_rounds
Revises: 0011_meeting_responded_at
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_two_stage_rounds"
down_revision = "0011_meeting_responded_at"
branch_labels = None
depends_on = None

WINDOWS = "elective_registration_windows"


def upgrade() -> None:
    op.add_column(WINDOWS, sa.Column("selection_mode", sa.String(20), nullable=False,
                                     server_default="RANKED"))
    op.add_column(WINDOWS, sa.Column("stage", sa.String(20), nullable=True))
    op.add_column(WINDOWS, sa.Column("interest_pick_count", sa.Integer(), nullable=True))
    op.add_column(WINDOWS, sa.Column("final_pick_count", sa.Integer(), nullable=True))
    op.add_column(WINDOWS, sa.Column("min_students_to_run", sa.Integer(), nullable=True))
    op.add_column(WINDOWS, sa.Column("section_capacity", sa.Integer(), nullable=True))
    op.add_column(WINDOWS, sa.Column("interest_closed_at", sa.DateTime(timezone=True),
                                     nullable=True))

    op.create_table(
        "elective_round_choices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("registration_window_id", sa.Integer(),
                  sa.ForeignKey(f"{WINDOWS}.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("student_id", sa.Integer(),
                  sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(),
                  sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("registration_window_id", "stage", "student_id", "course_id",
                            name="uq_elective_round_choices_window_stage_student_course"),
    )
    op.create_index("ix_elective_round_choices_window_stage", "elective_round_choices",
                    ["registration_window_id", "stage"])
    op.create_index("ix_elective_round_choices_student_id", "elective_round_choices",
                    ["student_id"])
    op.create_index("ix_elective_round_choices_course_id", "elective_round_choices",
                    ["course_id"])


def downgrade() -> None:
    op.drop_table("elective_round_choices")
    for column in ("interest_closed_at", "section_capacity", "min_students_to_run",
                   "final_pick_count", "interest_pick_count", "stage", "selection_mode"):
        op.drop_column(WINDOWS, column)
