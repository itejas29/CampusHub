"""Programme semester windows.

CSSI is *floated* by the coordinator during Semester II so students can line up
an NGO over the break, and carried out in Semester III. Announcing a programme
and opening it for submission are two different moments.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.errors import BusinessRuleError
from app.models.enums import ProgramPhase
from app.services.internships import (
    assert_submissions_open, phase_note, program_phase,
)


def cssi():
    """Announced in Semester II, carried out in III, hidden afterwards."""
    return SimpleNamespace(
        name="Community and Social Service Internship",
        target_semester=3, announce_from_semester=2, visible_to_semester=3,
    )


def summer():
    """Announced and opened in Semester VI, still visible in VII and beyond."""
    return SimpleNamespace(
        name="Summer Internship",
        target_semester=6, announce_from_semester=6, visible_to_semester=None,
    )


# ── who sees CSSI ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("semester,expected", [
    (1, ProgramPhase.HIDDEN),
    (2, ProgramPhase.ANNOUNCED),
    (3, ProgramPhase.ACTIVE),
    (4, ProgramPhase.CONCLUDED),
    (7, ProgramPhase.CONCLUDED),
])
def test_cssi_phase_per_semester(semester, expected):
    assert program_phase(cssi(), semester) is expected


def test_cssi_is_not_shown_to_first_year_students():
    """The requirement is that CSSI belongs to Semester III, not to everyone."""
    assert program_phase(cssi(), 1) is ProgramPhase.HIDDEN


def test_cssi_is_announced_a_semester_early():
    assert program_phase(cssi(), 2) is ProgramPhase.ANNOUNCED


def test_a_student_with_no_semester_sees_nothing():
    assert program_phase(cssi(), None) is ProgramPhase.HIDDEN


# ── submissions follow the phase, not merely visibility ───────────────────
def test_submissions_open_only_in_the_target_semester():
    assert_submissions_open(cssi(), 3)          # does not raise


def test_an_announced_programme_accepts_nothing():
    with pytest.raises(BusinessRuleError) as excinfo:
        assert_submissions_open(cssi(), 2)
    message = str(excinfo.value)
    assert "announced" in message.lower()
    assert "Semester 3" in message


def test_a_concluded_programme_accepts_nothing():
    with pytest.raises(BusinessRuleError):
        assert_submissions_open(cssi(), 4)


def test_a_hidden_programme_accepts_nothing():
    with pytest.raises(BusinessRuleError):
        assert_submissions_open(cssi(), 1)


# ── the note explains the phase to the student ────────────────────────────
def test_announced_note_tells_the_student_what_to_do_now():
    note = phase_note(cssi(), ProgramPhase.ANNOUNCED, 2)
    assert "Semester 3" in note and "host organisation" in note


def test_active_phase_needs_no_explanation():
    assert phase_note(cssi(), ProgramPhase.ACTIVE, 3) is None


# ── Summer keeps its open-ended upper bound ───────────────────────────────
def test_summer_stays_visible_after_its_target_semester():
    """Semester VII students are still being assessed, so it must not vanish."""
    assert program_phase(summer(), 7) is ProgramPhase.ACTIVE
    assert program_phase(summer(), 8) is ProgramPhase.ACTIVE


def test_summer_is_hidden_before_its_semester():
    assert program_phase(summer(), 4) is ProgramPhase.HIDDEN


def test_a_programme_without_a_window_is_open():
    """No configuration means no gate — the rule must be opt-in."""
    unbounded = SimpleNamespace(name="Ad-hoc", target_semester=None,
                                announce_from_semester=None,
                                visible_to_semester=None)
    assert program_phase(unbounded, 5) is ProgramPhase.ACTIVE


def test_announce_defaults_to_the_target_semester():
    """Omitting the announce semester means no early-visibility phase."""
    plain = SimpleNamespace(name="Plain", target_semester=5,
                            announce_from_semester=None, visible_to_semester=None)
    assert program_phase(plain, 4) is ProgramPhase.HIDDEN
    assert program_phase(plain, 5) is ProgramPhase.ACTIVE
