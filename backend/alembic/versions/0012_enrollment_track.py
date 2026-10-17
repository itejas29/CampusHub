"""record the track a student chose (Semester VIII project or industry)

Revision ID: 0012_enrollment_track
Revises: 0011_meeting_responded_at
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_enrollment_track"
down_revision = "0011_meeting_responded_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("internship_enrollments", sa.Column("track", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("internship_enrollments", "track")
