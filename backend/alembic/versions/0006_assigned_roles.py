"""coordinator and mentor as separately assignable scoped roles

Coordinator and Mentor are independent grants over the same scope shape
(role × module × department). Neither implies the other, and a user may hold
several at once — permissions are the union.

Existing rows all described coordinations, so they backfill to COORDINATOR.

Revision ID: 0006_assigned_roles
Revises: 0005_semester_windows
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_assigned_roles"
down_revision = "0005_semester_windows"
branch_labels = None
depends_on = None

_UNIQUE = "uq_faculty_role_assignments_faculty_domain_department"


def upgrade() -> None:
    # server_default backfills existing rows; dropped afterwards so the model
    # (which sets the value in Python) and the database agree.
    op.add_column(
        "faculty_role_assignments",
        sa.Column("role", sa.String(length=24), nullable=False,
                  server_default="COORDINATOR"),
    )
    op.alter_column("faculty_role_assignments", "role", server_default=None)
    op.add_column("faculty_role_assignments",
                  sa.Column("starts_on", sa.Date(), nullable=True))
    op.add_column("faculty_role_assignments",
                  sa.Column("ends_on", sa.Date(), nullable=True))

    # The same person may now be Mentor and Coordinator for one scope, so the
    # uniqueness rule has to include the role.
    op.drop_constraint(_UNIQUE, "faculty_role_assignments", type_="unique")
    op.create_unique_constraint(
        _UNIQUE, "faculty_role_assignments",
        ["faculty_id", "role", "domain", "department_id", "academic_year_id"],
    )
    op.create_index("ix_faculty_role_assignments_role", "faculty_role_assignments",
                    ["role", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_faculty_role_assignments_role",
                  table_name="faculty_role_assignments")
    op.drop_constraint(_UNIQUE, "faculty_role_assignments", type_="unique")
    op.create_unique_constraint(
        _UNIQUE, "faculty_role_assignments",
        ["faculty_id", "domain", "department_id", "academic_year_id"],
    )
    op.drop_column("faculty_role_assignments", "ends_on")
    op.drop_column("faculty_role_assignments", "starts_on")
    op.drop_column("faculty_role_assignments", "role")
