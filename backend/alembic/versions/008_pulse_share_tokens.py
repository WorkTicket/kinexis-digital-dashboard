"""Add pulse_share_tokens for read-only Success Pulse links.

Revision ID: 008_pulse_share
Revises: 007_site_relaunch
Create Date: 2026-07-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_pulse_share"
down_revision: Union[str, None] = "007_site_relaunch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    rows = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name='pulse_share_tokens'")
    ).fetchall()
    if rows:
        return
    op.create_table(
        "pulse_share_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked", sa.Boolean(), server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_pulse_share_tokens_client_id", "pulse_share_tokens", ["client_id"])
    op.create_index("ix_pulse_share_tokens_token", "pulse_share_tokens", ["token"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    op.drop_table("pulse_share_tokens")
