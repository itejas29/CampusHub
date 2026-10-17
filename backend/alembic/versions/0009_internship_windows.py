"""coordinator-run windows on internship programmes

A programme's steps used to be gated by the semester alone: CSSI was visible in
Semester II and writable in Semester III, with no dates a coordinator could set.
The department runs it in windows the coordinator opens — registration of the
NGO and its supervisor before the break, then posters, presentations and marks
in Semester III — each with a deadline the server must enforce.

One row per window kind per programme. Which kinds a programme uses is its
configuration (`internship_programs.config["windows"]`), so no column is added
there and other programmes are unaffected.

`notifications.type` and the new `kind` column are VARCHAR (native_enum=False),
so the new values need no ALTER TYPE.

Revision ID: 0009_internship_windows
Revises: 0008_registration_windows
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_internship_windows"
down_revision = "0008_registration_windows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "internship_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cohort_semester", sa.Integer(), nullable=True),
        sa.Column("submission_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("presentation_from", sa.Date(), nullable=True),
        sa.Column("presentation_to", sa.Date(), nullable=True),
        sa.Column("closed_early_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["program_id"], ["internship_programs.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opened_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("program_id", "kind", name="uq_internship_windows_program_id_kind"),
    )
    op.create_index("ix_internship_windows_program_id", "internship_windows", ["program_id"])


def downgrade() -> None:
    op.drop_index("ix_internship_windows_program_id", table_name="internship_windows")
    op.drop_table("internship_windows")
