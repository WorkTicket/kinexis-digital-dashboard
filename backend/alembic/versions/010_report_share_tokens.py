"""Add report_share_tokens for remote client report portal.

Revision ID: 010_report_share
Revises: 009_experiments
Create Date: 2026-07-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_report_share"
down_revision: Union[str, None] = "009_experiments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    rows = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name='report_share_tokens'")
    ).fetchall()
    if rows:
        return
    op.create_table(
        "report_share_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "report_id",
            sa.Integer(),
            sa.ForeignKey("monthly_reports.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("period_start", sa.String(20), nullable=True),
        sa.Column("period_end", sa.String(20), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked", sa.Boolean(), server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_report_share_tokens_client_id", "report_share_tokens", ["client_id"])
    op.create_index("ix_report_share_tokens_token", "report_share_tokens", ["token"], unique=True)
    op.create_index("ix_report_share_tokens_report_id", "report_share_tokens", ["report_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    op.drop_index("ix_report_share_tokens_report_id", table_name="report_share_tokens")
    op.drop_index("ix_report_share_tokens_token", table_name="report_share_tokens")
    op.drop_index("ix_report_share_tokens_client_id", table_name="report_share_tokens")
    op.drop_table("report_share_tokens")
