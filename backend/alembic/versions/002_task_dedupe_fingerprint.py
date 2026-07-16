"""Add task dedupe columns: target_query, target_url, fingerprint.

Revision ID: 002_task_dedupe
Revises: 001_additive
Create Date: 2026-07-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_task_dedupe"
down_revision: Union[str, None] = "001_additive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMN_PATCHES = [
    ("tasks", "target_query", "VARCHAR(500)"),
    ("tasks", "target_url", "VARCHAR(2000)"),
    ("tasks", "fingerprint", "VARCHAR(100)"),
]

_INDEX_PATCHES = [
    (
        "ix_task_dedupe_fingerprint",
        "CREATE INDEX IF NOT EXISTS ix_task_dedupe_fingerprint ON tasks "
        "(client_id, fingerprint)",
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    for table, column, col_type in _COLUMN_PATCHES:
        rows = bind.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
        existing = {r[1] for r in rows}
        if column not in existing:
            bind.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
    for _index_name, ddl in _INDEX_PATCHES:
        bind.execute(sa.text(ddl))


def downgrade() -> None:
    pass
