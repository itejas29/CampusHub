"""Where a student stands on one slot of their current semester.

The dashboard shows the semester the curriculum places the student in, slot by
slot, and counts the ones still waiting on them. That count is only honest if
each slot is judged by the record that actually settles it:

* a compulsory slot (core course, internship, project) is never "pending" —
  there is nothing for the student to choose;
* an Open or Program Core Elective is settled by an ``ElectiveAllocation``, and
  is out of the student's hands from the moment they submit preferences — the
  next move is the coordinator's, so it is not "pending" on the student either;
* a MOOC/NPTEL slot is settled by a ``MoocRegistration`` — it never receives an
  allocation, so judging it by one left every Semester V student permanently
  "Action needed" even after their certificate was verified.

Nothing here names a programme or a semester: which slots exist, and when, is
the curriculum's business.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import ComponentType, MoocStatus


@dataclass(frozen=True, slots=True)
class RequirementState:
    #: Shown to the student; drawn from vocabularies the UI already styles.
    label: str
    #: True while the slot is waiting on the student to do something.
    needs_action: bool


CORE = RequirementState("Core", False)
ALLOCATED = RequirementState("Allocated", False)
PREFERENCES_SUBMITTED = RequirementState("Preferences submitted", False)
ACTION_NEEDED = RequirementState("Action needed", True)


def requirement_state(component, *, allocated: bool,
                      preferences_submitted: bool = False,
                      mooc_registration=None) -> RequirementState:
    """State of one curriculum slot for one student.

    ``allocated`` — the student holds a live elective allocation for the slot.
    ``preferences_submitted`` — they have ranked courses for it and await a seat.
    ``mooc_registration`` — their current MOOC registration for it, if any.
    """
    if not component.is_elective:
        return CORE
    if component.component_type == ComponentType.MOOC:
        if mooc_registration is None:
            return ACTION_NEEDED
        status = MoocStatus(mooc_registration.status)
        if status == MoocStatus.FAILED:
            # Nothing to do now: the slot carries over when the semester closes.
            return RequirementState("Not passed — carries over", False)
        # A rejected certificate puts the slot back in the student's hands.
        return RequirementState(status.value, status == MoocStatus.REJECTED)
    if allocated:
        return ALLOCATED
    return PREFERENCES_SUBMITTED if preferences_submitted else ACTION_NEEDED


def current_mooc_registration(registrations):
    """The registration that speaks for a slot when a student has several.

    A student may register again after a rejection. The live attempt wins over
    the rejected one, and among equals the most recent wins.
    """
    rows = list(registrations)
    if not rows:
        return None
    return max(rows, key=lambda r: (
        MoocStatus(r.status) != MoocStatus.REJECTED, r.created_at,
    ))
