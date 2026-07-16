"""Comprehensive model migration coverage — ensures every table/column exists.

Revision ID: 006_model_coverage
Revises: 005_insight_trust_columns
Create Date: 2026-07-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_model_coverage"
down_revision: Union[str, None] = "005_insight_trust_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    # --- Ensure all model tables exist (idempotent via IF NOT EXISTS) ---

    # clients table — foundation
    _ensure_table(bind, "clients", [
        "id", "name", "industry", "brand_color", "profile_json",
        "owner", "priority", "archived", "created_at",
    ])

    # data_sources
    _ensure_table(bind, "data_sources", [
        "id", "client_id", "type", "credentials_encrypted",
        "last_synced_at", "status", "last_error",
    ])

    # metric_daily
    _ensure_table(bind, "metric_daily", [
        "id", "client_id", "source", "date", "metric_name",
        "value", "dimension_type", "dimension_value",
    ])

    # insights
    _ensure_table(bind, "insights", [
        "id", "client_id", "type", "message", "recommended_action",
        "severity", "kind", "priority_score", "created_at",
        "resolved", "fingerprint", "target_query", "target_url",
        "evidence_json", "resolve_reason",
        "confidence_tier", "sample_size", "trend_cv", "algorithmic_caveat",
    ])

    # tasks
    _ensure_table(bind, "tasks", [
        "id", "client_id", "insight_id", "assigned_to", "status",
        "due_date", "result_notes", "impact_outcome", "brief_id",
        "lever_id", "playbook_pattern", "target_query", "target_url",
        "fingerprint", "created_at", "action_plan_id",
    ])

    # growth_lever_threads
    _ensure_table(bind, "growth_lever_threads", [
        "id", "client_id", "status", "title", "stage", "cause", "fix",
        "impact_score", "source_insight_ids", "task_id", "brief_id",
        "impact_summary", "confidence_label", "include_in_report",
        "created_at", "updated_at", "resolved_at",
    ])

    # weekly_summaries
    _ensure_table(bind, "weekly_summaries", [
        "id", "client_id", "week_start", "content",
        "reviewed", "created_at",
    ])

    # action_plans
    _ensure_table(bind, "action_plans", [
        "id", "client_id", "title", "content",
        "priority_score", "estimated_impact",
        "estimated_effort", "status", "created_at",
    ])

    # impact_snapshots
    _ensure_table(bind, "impact_snapshots", [
        "id", "task_id", "client_id", "metric_name", "source",
        "before_value", "after_value", "change_pct",
        "snapshot_type", "created_at",
    ])

    # content_briefs
    _ensure_table(bind, "content_briefs", [
        "id", "client_id", "insight_id", "keyword", "title",
        "outline", "word_count", "related_keywords", "status", "created_at",
    ])

    # client_baselines
    _ensure_table(bind, "client_baselines", [
        "id", "client_id", "captured_at", "period_start",
        "period_end", "period_days", "kpis_json", "notes",
    ])

    # monthly_reports
    _ensure_table(bind, "monthly_reports", [
        "id", "client_id", "year", "month", "payload_json",
        "generated_at",
    ])

    # tracked_keywords
    _ensure_table(bind, "tracked_keywords", [
        "id", "client_id", "keyword", "target_url",
        "notes", "created_at",
    ])

    # page_snapshots
    _ensure_table(bind, "page_snapshots", [
        "id", "client_id", "url", "title", "meta_description",
        "h1", "headings_json", "word_count", "schema_types",
        "internal_links_json", "canonical_url", "status_code",
        "fetched_at", "content_hash",
    ])

    # pagespeed_findings
    _ensure_table(bind, "pagespeed_findings", [
        "id", "client_id", "url", "strategy", "audit_id",
        "title", "savings_ms", "savings_bytes",
        "top_offenders_json", "fetched_at",
    ])

    # serp_snapshots
    _ensure_table(bind, "serp_snapshots", [
        "id", "client_id", "query", "results_json",
        "provider", "fetched_at",
    ])

    # app_settings
    _ensure_table(bind, "app_settings", [
        "key", "value",
    ])

    # ai_usage_logs
    _ensure_table(bind, "ai_usage_logs", [
        "id", "client_id", "provider", "model", "purpose",
        "input_tokens", "output_tokens", "estimated_cost_usd", "created_at",
    ])

    # anomaly_notifications
    _ensure_table(bind, "anomaly_notifications", [
        "id", "client_id", "insight_id", "severity", "title",
        "body", "delivered", "created_at",
    ])

    # job_runs
    _ensure_table(bind, "job_runs", [
        "id", "job_type", "started_at", "finished_at",
        "ok", "error", "summary_json",
    ])

    # backlink_snapshots
    _ensure_table(bind, "backlink_snapshots", [
        "id", "client_id", "domain", "referring_domains",
        "total_backlinks", "domain_rating", "toxic_score",
        "new_links_30d", "lost_links_30d", "dofollow_ratio",
        "top_anchor_text", "fetched_at",
    ])

    # client_seasonality
    _ensure_table(bind, "client_seasonality", [
        "id", "client_id", "source", "metric_name",
        "iso_week", "median_value", "p25_value",
        "p75_value", "sample_years", "computed_at",
    ])

    # crux_snapshots
    _ensure_table(bind, "crux_snapshots", [
        "id", "client_id", "url", "form_factor",
        "lcp_p75", "inp_p75", "cls_p75",
        "lcp_good_pct", "inp_good_pct", "cls_good_pct",
        "ttfb_p75", "fetched_at",
    ])

    # gbp_snapshots
    _ensure_table(bind, "gbp_snapshots", [
        "id", "client_id", "location_id", "location_name",
        "period_start", "period_end", "search_views",
        "map_views", "website_clicks", "direction_requests",
        "phone_calls", "total_actions", "direct_searches",
        "discovery_searches", "fetched_at",
    ])

    # recommendations
    _ensure_table(bind, "recommendations", [
        "id", "client_id", "insight_id", "task_id",
        "status", "fix_type", "title",
        "expected_lift_pct", "expected_metric",
        "actual_lift_pct", "outcome", "notes",
        "created_at", "completed_at", "verified_at",
    ])


def _ensure_table(bind, table_name: str, expected_columns: list[str]) -> None:
    rows = bind.execute(sa.text(f"PRAGMA table_info({table_name})")).fetchall()
    existing = {r[1] for r in rows}
    for col in expected_columns:
        if col not in existing:
            bind.execute(sa.text(f"ALTER TABLE {table_name} ADD COLUMN {col} TEXT"))


def downgrade() -> None:
    pass
