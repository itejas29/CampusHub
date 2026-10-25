from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

def engine_options(url: str, *, statement_timeout_ms: int | None = None) -> dict:
    """Pool and per-connection limits (QA-18). On PostgreSQL every connection
    carries `statement_timeout`, so a runaway query is cancelled by the server
    rather than holding a connection while requests queue behind it."""
    options: dict = {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20,
                     "pool_timeout": settings.DB_POOL_TIMEOUT_S, "echo": False}
    timeout = (settings.DB_STATEMENT_TIMEOUT_MS if statement_timeout_ms is None
               else statement_timeout_ms)
    if url.startswith("postgresql") and timeout:
        options["connect_args"] = {"options": f"-c statement_timeout={int(timeout)}"}
    return options


engine = create_engine(settings.sqlalchemy_url, **engine_options(settings.sqlalchemy_url))

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                            expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
