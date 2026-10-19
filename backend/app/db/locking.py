"""Row locks for limits that are checked, then written.

A capacity check ("are there seats left?") followed by an insert or a counter
update is only correct if nobody else can do the same in between. Under
concurrent requests on PostgreSQL they could: a Minor with 3 free seats took
10 students at once, and its seat counter lost 9 of the increments (the QA
race tests in reports/qa/tools reproduce it).

`locked` loads the row that owns the limit with SELECT ... FOR UPDATE and
re-reads it, so the second request waits for the first to commit and then sees
the current count. Hold the lock for the shortest stretch: take it right before
the check, in the request that writes. SQLite ignores FOR UPDATE, which is fine
for its single-writer test database.
"""
from __future__ import annotations

from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

T = TypeVar("T")


def locked(db: Session, model: type[T], ident: int | None) -> T | None:
    """The row, locked until this transaction ends, with its current values."""
    if ident is None:
        return None
    # OF <table>: models that eager-load a relationship add an outer join, and
    # PostgreSQL refuses to lock the nullable side of one. Only this row is held.
    return db.execute(
        select(model).where(model.id == ident).with_for_update(of=model)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()

