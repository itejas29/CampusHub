"""semester windows and presentation slots

Two rules from the department, made explicit:

* A programme is *floated* a semester before it is carried out. CSSI is
  announced during Semester II so students can find an NGO over the break, and
  opens for submission when Semester III begins.
* The presentation slot is allocated by the coordinator once the completion
  certificate has been verified.

Revision ID: 0005_semester_windows
Revises: 0004_document_lifecycle
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_semester_windows"
down_revision = "0004_document_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("internship_programs",
                  sa.Column("announce_from_semester", sa.Integer(), nullable=True))
    op.add_column("internship_programs",
                  sa.Column("visible_to_semester", sa.Integer(), nullable=True))
    op.add_column("internship_enrollments",
                  sa.Column("presentation_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("internship_enrollments",
                  sa.Column("presentation_venue", sa.String(length=120), nullable=True))
    op.add_column("internship_enrollments",
                  sa.Column("presentation_panel", sa.String(length=180), nullable=True))


def downgrade() -> None:
    op.drop_column("internship_enrollments", "presentation_panel")
    op.drop_column("internship_enrollments", "presentation_venue")
    op.drop_column("internship_enrollments", "presentation_at")
    op.drop_column("internship_programs", "visible_to_semester")
    op.drop_column("internship_programs", "announce_from_semester")
