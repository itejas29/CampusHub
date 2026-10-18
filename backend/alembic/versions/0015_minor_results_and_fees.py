"""minor course results and semester fee payments

Revision ID: 0015_minor_results_and_fees
Revises: 0014_project_teams
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_minor_results_and_fees"
down_revision = "0014_project_teams"
branch_labels = None
depends_on = None


def _stamps():
    return [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "minor_course_results",
        sa.Column("enrollment_id", sa.Integer(), nullable=False),
        sa.Column("minor_course_id", sa.Integer(), nullable=False),
        sa.Column("marks", sa.Numeric(5, 2), nullable=True),
        sa.Column("grade", sa.String(length=4), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        *_stamps(),
        sa.ForeignKeyConstraint(["enrollment_id"], ["minor_enrollments.id"],
                                name="fk_minor_course_results_enrollment_id_minor_enrollments",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["minor_course_id"], ["minor_courses.id"],
                                name="fk_minor_course_results_minor_course_id_minor_courses",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"],
                                name="fk_minor_course_results_recorded_by_user_id_users",
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_minor_course_results"),
        sa.UniqueConstraint("enrollment_id", "minor_course_id",
                            name="uq_minor_course_results_enrollment_course"),
    )
    op.create_index("ix_minor_course_results_enrollment_id", "minor_course_results", ["enrollment_id"])
    op.create_table(
        "minor_fee_payments",
        sa.Column("enrollment_id", sa.Integer(), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("amount_paid", sa.Numeric(10, 2), nullable=False),
        sa.Column("reference", sa.String(length=80), nullable=True),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), nullable=True),
        *_stamps(),
        sa.ForeignKeyConstraint(["enrollment_id"], ["minor_enrollments.id"],
                                name="fk_minor_fee_payments_enrollment_id_minor_enrollments",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"],
                                name="fk_minor_fee_payments_recorded_by_user_id_users",
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_minor_fee_payments"),
        sa.UniqueConstraint("enrollment_id", "semester",
                            name="uq_minor_fee_payments_enrollment_semester"),
    )
    op.create_index("ix_minor_fee_payments_enrollment_id", "minor_fee_payments", ["enrollment_id"])


def downgrade() -> None:
    op.drop_index("ix_minor_fee_payments_enrollment_id", table_name="minor_fee_payments")
    op.drop_table("minor_fee_payments")
    op.drop_index("ix_minor_course_results_enrollment_id", table_name="minor_course_results")
    op.drop_table("minor_course_results")
