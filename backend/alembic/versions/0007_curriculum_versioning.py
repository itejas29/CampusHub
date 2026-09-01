"""multi-programme curriculum: versioning, source traceability, divisions

Phase 3B turns the curriculum from "the ICT structure" into versioned,
source-traceable university policy data covering every B.Tech programme.

Four things change:

* **Curriculum versions get a batch window and a lifecycle.** ``effective_to_year``
  bounds a version so a 2022 ECE student keeps the 2020-24 structure while a
  2024 ECE student gets 2024-28 — they are genuinely different curricula, not
  revisions of one another. ``status`` (DRAFT/PUBLISHED/ARCHIVED) stops a
  published structure being edited underneath a cohort already studying it.

* **Every curriculum records where it came from.** Curriculum data is university
  policy data, so an administrator must be able to see the document, the date it
  was retrieved and how confident the import was before trusting a rule.

* **Components gain declarative cross-programme eligibility.** The official Open
  Elective rule is written in schools and programmes — "offered to the students
  enrolled in B.Tech. programs of School of Technology other than Electrical
  Engineering" — which ``course.department_id`` alone cannot express.

* **Divisions become data.** A/B/C/D is ICT's shape, not a constant; CSBS runs
  one division and Computer Engineering four.

Existing rows backfill so ICT keeps working unchanged: every current curriculum
becomes PUBLISHED with an open-ended batch window.

Revision ID: 0007_curriculum_versioning
Revises: 0006_assigned_roles
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_curriculum_versioning"
down_revision = "0006_assigned_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── curriculum versioning + lifecycle ─────────────────────────────────
    op.add_column("curriculums", sa.Column("effective_to_year", sa.Integer(), nullable=True))
    op.add_column(
        "curriculums",
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="PUBLISHED"),
    )
    op.add_column("curriculums",
                  sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("curriculums", sa.Column("published_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_curriculums_published_by_user_id", "curriculums",
                          "users", ["published_by_user_id"], ["id"], ondelete="SET NULL")

    # ── source traceability ───────────────────────────────────────────────
    for name, column in [
        ("source_url", sa.String(length=500)),
        ("source_title", sa.String(length=300)),
        ("source_publisher", sa.String(length=180)),
        ("academic_year_label", sa.String(length=20)),
        ("source_confidence", sa.String(length=40)),
    ]:
        op.add_column("curriculums", sa.Column(name, column, nullable=True))
    op.add_column("curriculums", sa.Column("source_date", sa.Date(), nullable=True))
    op.add_column("curriculums", sa.Column("retrieved_at", sa.Date(), nullable=True))
    op.add_column("curriculums", sa.Column("verified_at", sa.DateTime(timezone=True),
                                           nullable=True))
    op.add_column("curriculums", sa.Column("verified_by_user_id", sa.Integer(), nullable=True))
    op.add_column("curriculums", sa.Column("review_notes", sa.Text(), nullable=True))
    op.create_foreign_key("fk_curriculums_verified_by_user_id", "curriculums",
                          "users", ["verified_by_user_id"], ["id"], ondelete="SET NULL")
    # Existing curricula predate the import pipeline; they stay PUBLISHED but
    # are honestly marked as lacking a recorded source.
    op.alter_column("curriculums", "status", server_default=None)

    # ── components: fixed course link, eligibility rules, provenance ───────
    op.add_column("curriculum_components", sa.Column("course_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_curriculum_components_course_id", "curriculum_components",
                          "courses", ["course_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_curriculum_components_course_id", "curriculum_components",
                    ["course_id"])
    op.add_column("curriculum_components",
                  sa.Column("selection_mode", sa.String(length=20), nullable=True))
    op.add_column(
        "curriculum_components",
        sa.Column("eligibility", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.alter_column("curriculum_components", "eligibility", server_default=None)
    op.add_column("curriculum_components",
                  sa.Column("source_confidence", sa.String(length=40), nullable=True))
    op.add_column("curriculum_components", sa.Column("source_note", sa.Text(), nullable=True))

    # ── course classification ─────────────────────────────────────────────
    op.add_column("courses", sa.Column("category", sa.String(length=12), nullable=True))
    op.create_index("ix_courses_category", "courses", ["category"])
    op.add_column(
        "courses",
        sa.Column("delivery_mode", sa.String(length=24), nullable=False,
                  server_default="THEORY"),
    )
    op.alter_column("courses", "delivery_mode", server_default=None)
    op.add_column(
        "courses",
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("courses", "is_shared", server_default=None)

    # ── programme short name ──────────────────────────────────────────────
    op.add_column("programs", sa.Column("short_name", sa.String(length=60), nullable=True))

    # ── divisions as programme × batch data ───────────────────────────────
    op.create_table(
        "program_divisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("admission_year", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=10), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("program_id", "admission_year", "name",
                            name="uq_program_divisions_program_year_name"),
    )
    op.create_index("ix_program_divisions_program_id", "program_divisions", ["program_id"])
    op.create_index("ix_program_divisions_program_year", "program_divisions",
                    ["program_id", "admission_year"])


def downgrade() -> None:
    op.drop_index("ix_program_divisions_program_year", table_name="program_divisions")
    op.drop_index("ix_program_divisions_program_id", table_name="program_divisions")
    op.drop_table("program_divisions")

    op.drop_column("programs", "short_name")

    op.drop_column("courses", "is_shared")
    op.drop_column("courses", "delivery_mode")
    op.drop_index("ix_courses_category", table_name="courses")
    op.drop_column("courses", "category")

    op.drop_column("curriculum_components", "source_note")
    op.drop_column("curriculum_components", "source_confidence")
    op.drop_column("curriculum_components", "eligibility")
    op.drop_column("curriculum_components", "selection_mode")
    op.drop_index("ix_curriculum_components_course_id", table_name="curriculum_components")
    op.drop_constraint("fk_curriculum_components_course_id", "curriculum_components",
                       type_="foreignkey")
    op.drop_column("curriculum_components", "course_id")

    op.drop_constraint("fk_curriculums_verified_by_user_id", "curriculums",
                       type_="foreignkey")
    op.drop_constraint("fk_curriculums_published_by_user_id", "curriculums",
                       type_="foreignkey")
    for name in ("review_notes", "verified_by_user_id", "verified_at", "retrieved_at",
                 "source_date", "source_confidence", "academic_year_label",
                 "source_publisher", "source_title", "source_url",
                 "published_by_user_id", "published_at", "status", "effective_to_year"):
        op.drop_column("curriculums", name)
