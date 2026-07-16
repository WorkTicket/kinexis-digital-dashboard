"""Add client_baselines.period_days (model column missing from older DBs).

Revision ID: 003_baseline_period_days
Revises: 002_task_dedupe
Create Date: 2026-07-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_baseline_period_days"
down_revision: Union[str, None] = "002_task_dedupe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMN_PATCHES = [
    ("client_baselines", "period_days", "INTEGER"),
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


def downgrade() -> None:
    pass
