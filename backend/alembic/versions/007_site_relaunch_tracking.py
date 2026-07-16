"""Add site_relaunched_at column to clients table.

Revision ID: 007_site_relaunch
Revises: 006_model_coverage
Create Date: 2026-07-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_site_relaunch"
down_revision: Union[str, None] = "006_model_coverage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    rows = bind.execute(sa.text("PRAGMA table_info(clients)")).fetchall()
    existing = {r[1] for r in rows}
    if "site_relaunched_at" not in existing:
        bind.execute(sa.text("ALTER TABLE clients ADD COLUMN site_relaunched_at TIMESTAMP"))


def downgrade() -> None:
    pass
