"""mark demo personas apart from real faculty

The ICT roster is now PDEU's published faculty list. Demo accounts — the
fictional coordinators and HoD that sign-in shortcuts use — stay, but must
never be mistaken for real people, so they carry a flag the screens show.

Revision ID: 0010_faculty_is_demo
Revises: 0009_internship_windows
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_faculty_is_demo"
down_revision = "0009_internship_windows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("faculty", sa.Column("is_demo", sa.Boolean(), nullable=False,
                                       server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("faculty", "is_demo")
