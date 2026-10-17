"""record when a mentor answers a meeting request

The faculty performance score counts how quickly mentors answer meeting
requests. The request time was stored; the answer time was not.

Revision ID: 0011_meeting_responded_at
Revises: 0010_faculty_is_demo
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_meeting_responded_at"
down_revision = "0010_faculty_is_demo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mentor_meetings", sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("mentor_meetings", "responded_at")
