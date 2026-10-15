from __future__ import annotations

import datetime as dt
import random
from typing import Any

from app.core.errors import BusinessRuleError
from app.services.allocation.base import (
    AllocationOutcome, AllocationStrategy, Award, Candidate, SeatPool, register,
)

_FAR_FUTURE = dt.datetime.max.replace(tzinfo=dt.timezone.utc)


@register
class ManualAllocation(AllocationStrategy):
    key = "manual"
    label = "Manual (coordinator assigns)"
    description = (
        "No automatic ranking. Preferences are collected and the coordinator "
        "allocates seats by hand. Every assignment is audit-logged."
    )
    is_available = True

    def allocate(self, candidates: list[Candidate], pools: dict[int, SeatPool],
                 *, config: dict[str, Any] | None = None) -> AllocationOutcome:
        return AllocationOutcome(
            strategy=self.key,
            unallocated_student_ids=sorted({c.student_id for c in candidates}),
            notes=["Manual strategy: no seats were assigned automatically."],
        )


@register
class PreferenceOrderAllocation(AllocationStrategy):
    key = "preference_order"
    label = "Preference order (first-submitted wins ties)"
    description = (
        "Round-based: in round N every student is considered for their Nth "
        "choice, earliest submission first. Contains no institutional merit "
        "judgement — it only honours the ordering students supplied."
    )
    is_available = True

    def allocate(self, candidates: list[Candidate], pools: dict[int, SeatPool],
                 *, config: dict[str, Any] | None = None) -> AllocationOutcome:
        config = config or {}
        waitlist = bool(config.get("waitlist_unallocated", True))
        outcome = AllocationOutcome(strategy=self.key)

        remaining = {pid: pool.remaining for pid, pool in pools.items()}
        settled: set[int] = set()
        max_round = max((c.preference_order for c in candidates), default=0)

        for round_no in range(1, max_round + 1):
            wave = sorted(
                (c for c in candidates
                 if c.preference_order == round_no and c.student_id not in settled),
                key=lambda c: (c.submitted_at or _FAR_FUTURE, c.student_id),
            )
            for cand in wave:
                if remaining.get(cand.course_offering_id, 0) > 0:
                    remaining[cand.course_offering_id] -= 1
                    settled.add(cand.student_id)
                    outcome.awards.append(Award(
                        student_id=cand.student_id,
                        course_offering_id=cand.course_offering_id,
                        preference_order_granted=round_no,
                        reason=f"Granted preference #{round_no}",
                    ))
            outcome.notes.append(
                f"Round {round_no}: {len(wave)} considered, "
                f"{sum(1 for a in outcome.awards if a.preference_order_granted == round_no)} seated."
            )

        leftover = sorted({c.student_id for c in candidates} - settled)
        if waitlist:
            for student_id in leftover:
                first = min(
                    (c for c in candidates if c.student_id == student_id),
                    key=lambda c: c.preference_order,
                )
                outcome.awards.append(Award(
                    student_id=student_id,
                    course_offering_id=first.course_offering_id,
                    preference_order_granted=first.preference_order,
                    waitlisted=True,
                    reason="All preferred offerings were full",
                ))
        outcome.unallocated_student_ids = leftover
        return outcome


@register
class FirstComeFirstServedAllocation(AllocationStrategy):
    """Seats go in the order preference lists were submitted.

    The earliest submission is seated first, in the highest choice that still
    has a seat; then the next, and so on. A student who submitted later can
    lose a full course to one who submitted earlier, whatever either ranked.

    Students the round covered who never submitted are not left without an
    elective: once every submitted list has been served they are placed at
    random in the seats that remain. So is a submitter whose every choice
    filled up. The draw is seeded, so a dry run shows exactly what the real
    run will do.

    Server-supplied config (never taken from the client):
      ``non_submitter_ids`` — covered students with no submitted list
      ``seed``              — makes the random draw repeatable
    """

    key = "first_come_first_served"
    label = "First come, first served (non-submitters placed at random)"
    description = (
        "Students are seated in the order they submitted, each in their "
        "highest choice that still has a seat. Students who did not submit "
        "before the round was locked are placed at random in the remaining "
        "seats. Set a seat limit per course for the order to matter."
    )
    is_available = True

    def allocate(self, candidates: list[Candidate], pools: dict[int, SeatPool],
                 *, config: dict[str, Any] | None = None) -> AllocationOutcome:
        config = config or {}
        rng = random.Random(str(config.get("seed", "")))
        outcome = AllocationOutcome(strategy=self.key)
        remaining = {pid: pool.remaining for pid, pool in pools.items()}

        lists: dict[int, list[Candidate]] = {}
        for cand in candidates:
            lists.setdefault(cand.student_id, []).append(cand)
        # A student's list is submitted at once; the earliest row stands for it.
        queue = sorted(lists, key=lambda sid: (
            min((c.submitted_at or _FAR_FUTURE) for c in lists[sid]), sid))

        unseated: list[int] = []
        for student_id in queue:
            for cand in sorted(lists[student_id], key=lambda c: c.preference_order):
                if remaining.get(cand.course_offering_id, 0) > 0:
                    remaining[cand.course_offering_id] -= 1
                    outcome.awards.append(Award(
                        student_id=student_id,
                        course_offering_id=cand.course_offering_id,
                        preference_order_granted=cand.preference_order,
                        reason=f"Granted preference #{cand.preference_order}",
                    ))
                    break
            else:
                unseated.append(student_id)
        outcome.notes.append(
            f"{len(queue)} submitted list(s) served in submission order; "
            f"{len(queue) - len(unseated)} seated from their choices."
        )

        def place_at_random(student_id: int, reason: str) -> bool:
            open_courses = sorted(pid for pid, left in remaining.items() if left > 0)
            if not open_courses:
                return False
            chosen = rng.choice(open_courses)
            remaining[chosen] -= 1
            outcome.awards.append(Award(
                student_id=student_id, course_offering_id=chosen,
                preference_order_granted=None, reason=reason,
            ))
            return True

        left_out: list[int] = []
        for student_id in unseated:
            if not place_at_random(
                    student_id, "Every course you chose was full; placed at random"):
                left_out.append(student_id)

        non_submitters = sorted(set(config.get("non_submitter_ids") or []) - set(lists))
        rng.shuffle(non_submitters)
        placed = 0
        for student_id in non_submitters:
            if place_at_random(student_id,
                               "No preferences submitted; placed at random"):
                placed += 1
            else:
                left_out.append(student_id)
        if non_submitters:
            outcome.notes.append(
                f"{len(non_submitters)} student(s) did not submit; "
                f"{placed} placed at random."
            )
        if left_out:
            outcome.notes.append(
                f"{len(left_out)} student(s) could not be seated: every course "
                "is full. Raise the seat limit or allocate them by hand."
            )
        outcome.unallocated_student_ids = sorted(left_out)
        return outcome


@register
class MeritAllocation(AllocationStrategy):
    """Reserved for the institutional merit / pro-rata rule.

    Declared so coordinators can see it exists, but ``is_available`` is False so
    it can never be executed: the weighting of category, quota and tie-breaks
    has not been supplied by the faculty, and implementing a guess here would
    silently become the university's de-facto policy.

    Note that **CPI must not be a factor for electives** — that rule belongs to
    Minor Specialisation alone.
    """

    key = "merit"
    label = "Merit / pro-rata (awaiting faculty rules)"
    description = (
        "Not yet configured. Implement `allocate()` with the official rule "
        "supplied by the department, then flip `is_available` to True. "
        "CPI is not a permitted input for electives."
    )
    is_available = False

    def allocate(self, candidates: list[Candidate], pools: dict[int, SeatPool],
                 *, config: dict[str, Any] | None = None) -> AllocationOutcome:
        raise BusinessRuleError(
            "The merit-based allocation rule has not been configured yet. "
            "Use 'manual' or 'preference_order' until the official formula is "
            "supplied by the department."
        )
