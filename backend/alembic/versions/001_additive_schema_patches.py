"""Additive SQLite column/index patches (replaces schema_migrate).

Idempotent: safe on DBs that already received the old ensure_schema() patches,
and on fresh DBs where create_all already materialized the full model schema.

Revision ID: 001_additive
Revises:
Create Date: 2026-07-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_additive"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMN_PATCHES = [
    ("clients", "profile_json", "TEXT DEFAULT '{}'"),
    ("clients", "owner", "TEXT DEFAULT ''"),
    ("clients", "priority", "INTEGER DEFAULT 1"),
    ("clients", "archived", "BOOLEAN DEFAULT 0"),
    ("insights", "priority_score", "FLOAT DEFAULT 50.0"),
    ("insights", "kind", "TEXT DEFAULT 'opportunity'"),
    ("tasks", "action_plan_id", "INTEGER"),
    ("data_sources", "last_error", "TEXT"),
    ("tasks", "impact_outcome", "TEXT"),
    ("tasks", "brief_id", "INTEGER"),
    ("tasks", "lever_id", "INTEGER"),
    ("tasks", "playbook_pattern", "TEXT"),
]

_INDEX_PATCHES = [
    (
        "ix_metric_daily_lookup",
        "CREATE INDEX IF NOT EXISTS ix_metric_daily_lookup ON metric_daily "
        "(client_id, source, date, metric_name, dimension_type, dimension_value)",
    ),
    (
        "ix_insight_resolved_kind",
        "CREATE INDEX IF NOT EXISTS ix_insight_resolved_kind ON insights "
        "(resolved, kind)",
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
    # Additive-only migration; SQLite cannot drop columns portably without rebuild.
    pass
