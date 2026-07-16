"""MetricDaily uniqueness, DataSource uniqueness, Insight fingerprint, JobRun.

Revision ID: 004_foundation_uniqueness
Revises: 003_baseline_period_days
Create Date: 2026-07-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_foundation_uniqueness"
down_revision: Union[str, None] = "003_baseline_period_days"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    # --- Normalize NULL dimensions so UNIQUE works on SQLite ---
    bind.execute(
        sa.text(
            "UPDATE metric_daily SET dimension_type = '' WHERE dimension_type IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE metric_daily SET dimension_value = '' WHERE dimension_value IS NULL"
        )
    )

    # --- Deduplicate MetricDaily (keep lowest id) ---
    bind.execute(
        sa.text(
            """
            DELETE FROM metric_daily
            WHERE id NOT IN (
                SELECT MIN(id) FROM metric_daily
                GROUP BY client_id, source, date, metric_name,
                         COALESCE(dimension_type, ''), COALESCE(dimension_value, '')
            )
            """
        )
    )

    # --- Deduplicate DataSources (keep lowest id) ---
    bind.execute(
        sa.text(
            """
            DELETE FROM data_sources
            WHERE id NOT IN (
                SELECT MIN(id) FROM data_sources GROUP BY client_id, type
            )
            """
        )
    )

    # Insight fingerprint / resolve_reason / targets
    _add_col_if_missing(bind, "insights", "fingerprint", "VARCHAR(64)")
    _add_col_if_missing(bind, "insights", "target_query", "VARCHAR(500)")
    _add_col_if_missing(bind, "insights", "target_url", "VARCHAR(1000)")
    _add_col_if_missing(bind, "insights", "evidence_json", "TEXT")
    _add_col_if_missing(bind, "insights", "resolve_reason", "VARCHAR(40)")

    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_metric_daily_identity "
            "ON metric_daily (client_id, source, date, metric_name, "
            "dimension_type, dimension_value)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_datasource_client_type "
            "ON data_sources (client_id, type)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_insight_fingerprint "
            "ON insights (client_id, fingerprint)"
        )
    )

    # JobRun table
    bind.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS job_runs (
                id INTEGER NOT NULL PRIMARY KEY,
                job_type VARCHAR(100) NOT NULL,
                started_at DATETIME NOT NULL,
                finished_at DATETIME,
                ok BOOLEAN,
                error TEXT,
                summary_json TEXT DEFAULT '{}'
            )
            """
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_job_runs_job_type ON job_runs (job_type)"
        )
    )


def _add_col_if_missing(bind, table: str, column: str, col_type: str) -> None:
    rows = bind.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    existing = {r[1] for r in rows}
    if column not in existing:
        bind.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))


def downgrade() -> None:
    pass
