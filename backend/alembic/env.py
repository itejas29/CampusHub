from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import JSON, engine_from_config, pool

from app.core.config import settings
from app.models import Base  # noqa: F401  (registers every table on the metadata)

config = context.config
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _compare_server_default(context, inspected_column, metadata_column,
                            inspected_default, metadata_default, rendered_metadata_default):
    """PostgreSQL's `json` has no `=`, so Alembic's own comparison (a SELECT
    of the two defaults) fails on JSON columns. Compare their text instead:
    `'[]'::json` in the database against `'[]'` in the model. Every other type
    keeps Alembic's comparison (None)."""
    if not isinstance(metadata_column.type, JSON):
        return None
    strip = lambda d: (d or "").split("::")[0].strip("'\"")  # noqa: E731
    return strip(inspected_default) != strip(rendered_metadata_default)


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=_compare_server_default,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
