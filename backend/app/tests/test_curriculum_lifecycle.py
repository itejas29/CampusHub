"""Publication lifecycle: a published curriculum is not casually editable.

A published version is the rule a cohort is actually studying under. Editing it
in place, unpublishing it, or archiving it while students depend on it would all
rewrite history underneath them. The supported move is a *revision*, which
closes the old batch window and leaves the old structure intact.
"""
from __future__ import annotations

import pytest

from app.api.v1.curriculum import (
    _batch_label, _governed_student_count, _require_editable,
)
from app.core.errors import BusinessRuleError
from app.models.enums import CurriculumStatus

COMPONENTS = [
    (4, "OE1", "Open Elective 1", "OPEN_ELECTIVE", "OTHER_SCHOOL"),
    (5, "OE2-MOOC", "Open Elective 2 (MOOC)", "MOOC", "EXTERNAL_PLATFORM"),
]


def test_published_curriculum_refuses_structural_edits(make_curriculum):
    published = make_curriculum("B.TECH-ICT", "2024-28", 2024, None, COMPONENTS)
    with pytest.raises(BusinessRuleError) as excinfo:
        _require_editable(published)
    message = str(excinfo.value)
    assert "published" in message
    assert "new revision" in message           # tells the admin what to do instead


def test_draft_curriculum_is_editable(make_curriculum):
    draft = make_curriculum("B.TECH-ICT", "2026-30", 2026, None, COMPONENTS,
                            status=CurriculumStatus.DRAFT)
    _require_editable(draft)                    # does not raise


def test_archived_curriculum_is_editable(make_curriculum):
    """Archived versions are out of service, so correcting one harms nobody."""
    archived = make_curriculum("B.TECH-ICT", "2020-23", 2020, 2023, COMPONENTS,
                               status=CurriculumStatus.ARCHIVED)
    _require_editable(archived)


@pytest.mark.parametrize("from_year,to_year,expected", [
    (2024, None, "2024 batch onward"),
    (2020, 2023, "2020–2023 batches"),
    (2022, 2022, "2022 batch"),
])
def test_batch_label_reads_as_a_sentence(make_curriculum, from_year, to_year, expected):
    curriculum = make_curriculum("B.TECH-ICT", f"v{from_year}", from_year, to_year)
    assert _batch_label(curriculum) == expected


def test_governed_student_count_counts_only_the_resolving_cohort(
    db, make_curriculum, make_student
):
    old = make_curriculum("B.TECH-ECE", "2020-24", 2020, 2023, COMPONENTS)
    new = make_curriculum("B.TECH-ECE", "2024-28", 2024, None, COMPONENTS)

    make_student("B.TECH-ECE", 2021, semester=8)
    make_student("B.TECH-ECE", 2022, semester=7)
    make_student("B.TECH-ECE", 2024, semester=4)
    # A different programme's students never count towards either.
    make_student("B.TECH-ICT", 2024, semester=4)

    assert _governed_student_count(db, old) == 2
    assert _governed_student_count(db, new) == 1


def test_a_version_nobody_is_on_can_be_retired(db, make_curriculum, make_student):
    """The counterpart rule: once the cohort has graduated out of a version,
    archiving it is safe — which is exactly when the endpoint permits it.

    Note the closed window is *not* used as a fallback for the 2024 student: a
    superseded structure is never served to a batch it does not cover.
    """
    retired = make_curriculum("B.TECH-ECE", "2016-19", 2016, 2019, COMPONENTS)
    current = make_curriculum("B.TECH-ECE", "2024-28", 2024, None, COMPONENTS)
    make_student("B.TECH-ECE", 2024, semester=4)

    assert _governed_student_count(db, retired) == 0
    assert _governed_student_count(db, current) == 1
