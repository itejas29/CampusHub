"""project teams and guide preferences (Semester VII / VIII)

Revision ID: 0014_project_teams
Revises: 0013_enrollment_track
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_project_teams"
down_revision = "0013_enrollment_track"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_teams",
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("leader_enrollment_id", sa.Integer(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["program_id"], ["internship_programs.id"],
                                name="fk_project_teams_program_id_internship_programs",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["leader_enrollment_id"], ["internship_enrollments.id"],
                                name="fk_project_teams_leader_enrollment_id", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_project_teams"),
    )
    op.create_index("ix_project_teams_program_id", "project_teams", ["program_id"])
    op.add_column("internship_enrollments", sa.Column("team_id", sa.Integer(), nullable=True))
    op.create_index("ix_internship_enrollments_team_id", "internship_enrollments", ["team_id"])
    op.create_foreign_key("fk_internship_enrollments_team_id_project_teams",
                          "internship_enrollments", "project_teams", ["team_id"], ["id"],
                          ondelete="SET NULL")
    op.add_column("internship_enrollments",
                  sa.Column("guide_preferences", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("internship_enrollments", "guide_preferences")
    op.drop_constraint("fk_internship_enrollments_team_id_project_teams", "internship_enrollments",
                       type_="foreignkey")
    op.drop_index("ix_internship_enrollments_team_id", table_name="internship_enrollments")
    op.drop_column("internship_enrollments", "team_id")
    op.drop_index("ix_project_teams_program_id", table_name="project_teams")
    op.drop_table("project_teams")
