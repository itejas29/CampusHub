"""Pluggable allocation engine.

Phase 1 deliberately ships **no institutional merit formula**. The remaining
faculty rules (category reservation, pro-rata seat splits, tie-breaks) are not
yet confirmed, so this module defines the *contract* they will be implemented
against, plus two policy-free strategies that are safe to run today:

**CPI/CGPA is never an input to elective selection.** Academic merit governs
Minor Specialisation only (`services/eligibility.check_minor_eligibility`).
Elective viability is a headcount question — 40 to run — and capacity is a
room question, handled in `services/sections.py`.

* ``manual``           — rank nothing; a coordinator assigns seats by hand.
* ``preference_order`` — honour the student's own ranking, tie-broken by
  submission time. Pure mechanics, no institutional judgement.

Adding the real rule in Phase 2 means writing one ``AllocationStrategy``
subclass and registering it; no route, model or screen changes.
"""
from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Candidate:
    """One student competing for one offering."""

    student_id: int
    course_offering_id: int
    preference_order: int
    submitted_at: dt.datetime | None = None
    #: Division, for reporting the composition of a combined Core Elective
    #: class. Deliberately NOT a selection input, and never CPI.
    division: str | None = None
    #: Extension point for future non-academic rules (category, quota).
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SeatPool:
    course_offering_id: int
    capacity: int
    seats_taken: int = 0

    @property
    def remaining(self) -> int:
        return max(self.capacity - self.seats_taken, 0)


@dataclass(slots=True)
class Award:
    student_id: int
    course_offering_id: int
    #: None when the seat was not one of the student's choices — a student
    #: who never submitted, placed at random.
    preference_order_granted: int | None
    score: float | None = None
    waitlisted: bool = False
    reason: str = ""


@dataclass(slots=True)
class AllocationOutcome:
    strategy: str
    awards: list[Award] = field(default_factory=list)
    unallocated_student_ids: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def allocated_count(self) -> int:
        return sum(1 for a in self.awards if not a.waitlisted)


class AllocationStrategy(abc.ABC):
    """Contract every allocation rule must satisfy."""

    #: registry key used in ``CourseOffering.eligibility`` / admin UI
    key: str = "abstract"
    #: shown to coordinators when picking a strategy
    label: str = "Abstract strategy"
    description: str = ""
    #: False until faculty sign off on the underlying policy
    is_available: bool = False

    @abc.abstractmethod
    def allocate(
        self, candidates: list[Candidate], pools: dict[int, SeatPool],
        *, config: dict[str, Any] | None = None,
    ) -> AllocationOutcome:
        """Assign candidates to seats. Must not mutate ``pools`` capacities."""


# ── registry ──────────────────────────────────────────────────────────────
_REGISTRY: dict[str, AllocationStrategy] = {}


def register(strategy: "AllocationStrategy | type[AllocationStrategy]"):
    """Register a strategy. Usable as a class decorator or with an instance."""
    instance = strategy() if isinstance(strategy, type) else strategy
    _REGISTRY[instance.key] = instance
    return strategy


def get_strategy(key: str) -> AllocationStrategy:
    from app.core.errors import ValidationError

    try:
        return _REGISTRY[key]
    except KeyError:
        available = ", ".join(sorted(_REGISTRY)) or "none"
        raise ValidationError(
            f"Unknown allocation strategy '{key}'. Available: {available}."
        ) from None


def available_strategies() -> list[AllocationStrategy]:
    return sorted(_REGISTRY.values(), key=lambda s: s.key)
