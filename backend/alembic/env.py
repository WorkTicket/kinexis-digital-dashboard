"""Alembic environment — URL comes from app.database (DATABASE_URL / Electron)."""

from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context

from app.database import Base, engine
import app.models  # noqa: F401 — register metadata

config = context.config

# Skip fileConfig when the app already configured logging (uvicorn lifespan).
# Re-running fileConfig on Windows can deadlock and hang startup forever.
if config.config_file_name is not None and not logging.root.handlers:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = str(engine.url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
