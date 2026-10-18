"""Put the ICT department's NPTEL / NCC round in place, as a draft.

    python -m app.seed.add_nptel_round            # make the changes
    python -m app.seed.add_nptel_round --dry-run  # only report

Adds, without touching anything else: a DRAFT round for the 2024-28 scheme's
Semester V NPTEL / MOOC slot, carrying the department's approved list for
2026-27 (``sources/nptel_ict_2026-27.json`` — the 15 courses the coordinator
circulated). The NPTEL coordinator opens it, with their own deadline, from
Administration → NPTEL / NCC. Nothing is sent to students until then.

The full seed calls ``ensure`` too, so a reseeded database has the same draft.
Safe to run twice: an existing round for the slot is left alone.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.academics import Curriculum, CurriculumComponent, MoocRound, Program
from app.models.enums import ComponentType, MoocRoundStatus
from app.services import mooc_rounds

SOURCE = Path(__file__).parent / "sources" / "nptel_ict_2026-27.json"
TITLE = "NPTEL / NCC — Semester V (2026-27)"
MESSAGE = (
    "For your Semester V Open Elective, opt for one NPTEL course from the approved "
    "list or NCC certification. Register for your course on the NPTEL portal "
    "yourself — only registered candidates can sit the NPTEL exam. At the end of "
    "the semester, after NPTEL results are declared, submit your completion "
    "certificate here (NCC students submit their NCC certificate).")


def approved_list() -> list[mooc_rounds.CourseRow]:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    return [mooc_rounds.CourseRow(**course) for course in data["courses"]]


def ict_mooc_slot(db) -> CurriculumComponent | None:
    return db.scalar(
        select(CurriculumComponent)
        .join(Curriculum, Curriculum.id == CurriculumComponent.curriculum_id)
        .join(Program, Program.id == Curriculum.program_id)
        .where(Program.code == "B.TECH-ICT", Curriculum.version == "2024-28",
               CurriculumComponent.component_type == ComponentType.MOOC))


def ensure(db, *, dry_run: bool = False) -> list[str]:
    slot = ict_mooc_slot(db)
    if slot is None:
        return ["skipped: the ICT 2024-28 curriculum has no NPTEL / MOOC slot"]
    if db.scalar(select(MoocRound.id).where(MoocRound.curriculum_component_id == slot.id)):
        return []
    rows = approved_list()
    done = [f"draft round: {TITLE} with {len(rows)} approved courses"]
    if dry_run:
        return done
    curriculum = db.get(Curriculum, slot.curriculum_id)
    program = db.get(Program, curriculum.program_id)
    round_ = MoocRound(
        title=TITLE, message=MESSAGE, curriculum_component_id=slot.id,
        department_id=program.department_id, eligible_semesters=[slot.semester_number],
        status=MoocRoundStatus.DRAFT,
        closes_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=10),
        platform_deadline=dt.date.today() + dt.timedelta(days=30))
    db.add(round_)
    db.flush()
    result = mooc_rounds.import_courses(db, round_, rows)
    done += [f"  • skipped {code}: {why}" for code, why in result.skipped]
    db.flush()
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        done = ensure(db, dry_run=args.dry_run)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    print("\n".join(done) if done else "Nothing to add: the round is already there.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
