"""structured course syllabus (units, outcomes, references) with its revision date

Revision ID: 0016_course_syllabus
Revises: 0015_minor_results_and_fees
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_course_syllabus"
down_revision = "0015_minor_results_and_fees"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("syllabus", sa.JSON(), nullable=True))
    op.add_column("courses", sa.Column("syllabus_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("courses", "syllabus_updated_at")
    op.drop_column("courses", "syllabus")
