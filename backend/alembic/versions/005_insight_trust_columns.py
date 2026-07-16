"""Add diagnostic trust columns to insights table.

Revision ID: 005_insight_trust_columns
Revises: 004_foundation_uniqueness
Create Date: 2026-07-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_insight_trust_columns"
down_revision: Union[str, None] = "004_foundation_uniqueness"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    _add_col_if_missing(bind, "insights", "confidence_tier", "VARCHAR(20)")
    _add_col_if_missing(bind, "insights", "sample_size", "INTEGER")
    _add_col_if_missing(bind, "insights", "trend_cv", "FLOAT")
    _add_col_if_missing(bind, "insights", "algorithmic_caveat", "BOOLEAN DEFAULT 0")


def _add_col_if_missing(bind, table: str, column: str, col_type: str) -> None:
    rows = bind.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    existing = {r[1] for r in rows}
    if column not in existing:
        bind.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))


def downgrade() -> None:
    pass
