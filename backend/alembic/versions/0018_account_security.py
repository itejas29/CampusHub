"""account security: login throttling, forced password change, session revocation

Revision ID: 0018_account_security
Revises: 0017_nptel_ncc_rounds
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_account_security"
down_revision = "0017_nptel_ncc_rounds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), nullable=False,
                                     server_default=sa.false()))
    op.add_column("users", sa.Column("sessions_valid_after", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "login_throttle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(320), nullable=False, unique=True),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("login_throttle")
    op.drop_column("users", "sessions_valid_after")
    op.drop_column("users", "must_change_password")
