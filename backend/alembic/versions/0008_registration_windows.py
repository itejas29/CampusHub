"""elective registration rounds, and the indexes the real queries need

Two things Phase 4 adds.

**Registration rounds.** Elective registration was a pair of dates on each
course offering, which cannot express "this round covers Semester IV of these
three programmes, opens Monday, closes Friday, and is locked by the coordinator
once demand is in". A round is now a row, and it is the authority: every student
write is checked against it server-side, so a stale browser tab or a skewed
clock cannot get past the deadline.

**Indexes.** Only the two the new table and its foreign key actually need.

Six further composite indexes were drafted for the dashboard queries and then
removed after checking the initial schema: every one of them duplicated an
existing index, or led with a column already indexed. `ix_events_status_start`
existed verbatim; `notifications(user_id, is_read)` existed as
`ix_notifications_user_read`; `students.user_id` is already unique-indexed;
and the elective preference and allocation lookups lead with columns that
`0001` indexes. Redundant indexes cost write throughput and buy nothing, so
none were added.

Revision ID: 0008_registration_windows
Revises: 0007_curriculum_versioning
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_registration_windows"
down_revision = "0007_curriculum_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "elective_registration_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("component_type", sa.String(length=40), nullable=False),
        sa.Column("academic_year_id", sa.Integer(), nullable=True),
        sa.Column("semester_id", sa.Integer(), nullable=True),
        sa.Column("department_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="DRAFT"),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eligible_semesters", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("eligible_program_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("eligible_divisions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("min_preferences", sa.Integer(), nullable=True),
        sa.Column("max_preferences", sa.Integer(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["academic_year_id"], ["academic_years.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["semester_id"], ["semesters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"],
                                ondelete="SET NULL"),
        sa.UniqueConstraint("code", name="uq_elective_registration_windows_code"),
    )
    op.create_index("ix_elective_registration_windows_academic_year_id",
                    "elective_registration_windows", ["academic_year_id"])
    op.create_index("ix_elective_registration_windows_department_id",
                    "elective_registration_windows", ["department_id"])
    op.create_index("ix_elective_windows_status", "elective_registration_windows",
                    ["status"])
    op.create_index("ix_elective_windows_dept_type", "elective_registration_windows",
                    ["department_id", "component_type"])

    op.add_column("course_offerings",
                  sa.Column("registration_window_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_course_offerings_registration_window_id", "course_offerings",
        "elective_registration_windows", ["registration_window_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_course_offerings_registration_window_id", "course_offerings",
                    ["registration_window_id"])


def downgrade() -> None:
    op.drop_index("ix_course_offerings_registration_window_id",
                  table_name="course_offerings")
    op.drop_constraint("fk_course_offerings_registration_window_id",
                       "course_offerings", type_="foreignkey")
    op.drop_column("course_offerings", "registration_window_id")

    op.drop_index("ix_elective_windows_dept_type",
                  table_name="elective_registration_windows")
    op.drop_index("ix_elective_windows_status",
                  table_name="elective_registration_windows")
    op.drop_index("ix_elective_registration_windows_department_id",
                  table_name="elective_registration_windows")
    op.drop_index("ix_elective_registration_windows_academic_year_id",
                  table_name="elective_registration_windows")
    op.drop_table("elective_registration_windows")
