"""Add experiments registry table.

Revision ID: 009_experiments
Revises: 008_pulse_share
Create Date: 2026-07-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_experiments"
down_revision: Union[str, None] = "008_pulse_share"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    rows = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name='experiments'")
    ).fetchall()
    if rows:
        return
    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "recommendation_id",
            sa.Integer(),
            sa.ForeignKey("recommendations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("control", sa.Text(), nullable=True),
        sa.Column("treatment", sa.Text(), nullable=True),
        sa.Column("success_metric", sa.String(100), nullable=True),
        sa.Column("status", sa.String(30), server_default="draft"),
        sa.Column("start_at", sa.DateTime(), nullable=True),
        sa.Column("end_at", sa.DateTime(), nullable=True),
        sa.Column("outcome_lift_pct", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_experiments_client_id", "experiments", ["client_id"])
    op.create_index("ix_experiments_status", "experiments", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return
    op.drop_index("ix_experiments_status", table_name="experiments")
    op.drop_index("ix_experiments_client_id", table_name="experiments")
    op.drop_table("experiments")
