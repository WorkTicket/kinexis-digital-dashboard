from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime, ForeignKey, Text, Boolean,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from app.database import Base
from app.timeutil import utcnow


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    industry = Column(String(255), default="")
    brand_color = Column(String(7), default="#3B82F6")
    # Agency memory: goals, do_not_touch, brand_voice, notes (JSON string)
    profile_json = Column(Text, default="{}")
    # Agency ops: account owner + priority weight (1=normal, 2=high, 3=vip)
    owner = Column(String(255), default="")
    priority = Column(Integer, default=1)
    archived = Column(Boolean, default=False)
    site_relaunched_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    data_sources = relationship("DataSource", back_populates="client", cascade="all, delete-orphan")
    metrics = relationship("MetricDaily", back_populates="client", cascade="all, delete-orphan")
    insights = relationship("Insight", back_populates="client", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="client", cascade="all, delete-orphan")
    weekly_summaries = relationship("WeeklySummary", back_populates="client", cascade="all, delete-orphan")
    action_plans = relationship("ActionPlan", back_populates="client", cascade="all, delete-orphan")
    impact_snapshots = relationship("ImpactSnapshot", back_populates="client", cascade="all, delete-orphan")
    content_briefs = relationship("ContentBrief", back_populates="client", cascade="all, delete-orphan")
    baseline = relationship("ClientBaseline", back_populates="client", uselist=False, cascade="all, delete-orphan")
    milestones = relationship("ClientMilestone", back_populates="client", cascade="all, delete-orphan")
    monthly_reports = relationship("MonthlyReport", back_populates="client", cascade="all, delete-orphan")
    tracked_keywords = relationship("TrackedKeyword", back_populates="client", cascade="all, delete-orphan")
    growth_levers = relationship("GrowthLeverThread", back_populates="client", cascade="all, delete-orphan")
    page_snapshots = relationship("PageSnapshot", back_populates="client", cascade="all, delete-orphan")
    pagespeed_findings = relationship("PageSpeedFinding", back_populates="client", cascade="all, delete-orphan")
    serp_snapshots = relationship("SerpSnapshot", back_populates="client", cascade="all, delete-orphan")
    backlink_snapshots = relationship("BacklinkSnapshot", back_populates="client", cascade="all, delete-orphan")
    seasonality = relationship("ClientSeasonality", back_populates="client", cascade="all, delete-orphan")
    crux_snapshots = relationship("CruxSnapshot", back_populates="client", cascade="all, delete-orphan")
    gbp_snapshots = relationship("GbpSnapshot", back_populates="client", cascade="all, delete-orphan")
    anomaly_notifications = relationship("AnomalyNotification", back_populates="client", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="client", cascade="all, delete-orphan")
    experiments = relationship("Experiment", back_populates="client", cascade="all, delete-orphan")
    ai_usage_logs = relationship("AiUsageLog", back_populates="client", cascade="all, delete-orphan")


class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = (
        UniqueConstraint("client_id", "type", name="uq_datasource_client_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True)  # gsc, ga4, cloudflare, …
    credentials_encrypted = Column(Text, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    # pending | active | error | partial | reauth_required
    status = Column(String(50), default="pending")
    last_error = Column(Text, nullable=True)

    client = relationship("Client", back_populates="data_sources")


class MetricDaily(Base):
    __tablename__ = "metric_daily"
    __table_args__ = (
        # dimension_type / dimension_value are normalized to "" (never NULL) so
        # SQLite UNIQUE treats site-total rows as duplicates correctly.
        UniqueConstraint(
            "client_id",
            "source",
            "date",
            "metric_name",
            "dimension_type",
            "dimension_value",
            name="uq_metric_daily_identity",
        ),
        Index(
            "ix_metric_daily_lookup",
            "client_id",
            "source",
            "date",
            "metric_name",
            "dimension_type",
            "dimension_value",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String(50), nullable=False, index=True)  # gsc, ga4, cloudflare, …
    date = Column(Date, nullable=False, index=True)
    metric_name = Column(String(100), nullable=False, index=True)
    value = Column(Float, nullable=False)
    dimension_type = Column(String(100), nullable=False, default="")
    dimension_value = Column(String(500), nullable=False, default="")

    client = relationship("Client", back_populates="metrics")


class JobRun(Base):
    """Persisted scheduler / sync job outcome for honesty + health."""

    __tablename__ = "job_runs"

    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(String(100), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, default=utcnow)
    finished_at = Column(DateTime, nullable=True)
    ok = Column(Boolean, nullable=True)
    error = Column(Text, nullable=True)
    summary_json = Column(Text, default="{}")


class Insight(Base):
    __tablename__ = "insights"
    __table_args__ = (
        Index("ix_insight_resolved_kind", "resolved", "kind"),
        Index("ix_insight_fingerprint", "client_id", "fingerprint"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=True)
    severity = Column(String(20), default="medium")  # low, medium, high
    # problem = must-fix; opportunity = growth play (never drives crisis risk)
    kind = Column(String(20), default="opportunity", index=True)
    priority_score = Column(Float, default=50.0)
    created_at = Column(DateTime, default=utcnow)
    resolved = Column(Boolean, default=False, index=True)
    # Stable identity: type + target hash (not message text)
    fingerprint = Column(String(64), nullable=True, index=True)
    target_query = Column(String(500), nullable=True)
    target_url = Column(String(1000), nullable=True)
    evidence_json = Column(Text, nullable=True)
    # user | pruned | stale | shipped — prune must not look like user fixed it
    resolve_reason = Column(String(40), nullable=True)
    # Diagnostic trust surface — sample size, confidence tier, volatility
    confidence_tier = Column(String(20), nullable=True)  # high | medium | low | insufficient
    sample_size = Column(Integer, nullable=True)  # impressions, sessions, or equiv count
    trend_cv = Column(Float, nullable=True)  # coefficient of variation — volatility signal
    algorithmic_caveat = Column(Boolean, default=False)  # true when Google update overlaps window

    client = relationship("Client", back_populates="insights")
    tasks = relationship("Task", back_populates="insight")
    content_briefs = relationship("ContentBrief", back_populates="insight")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_task_dedupe_fingerprint", "client_id", "fingerprint"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    insight_id = Column(Integer, ForeignKey("insights.id", ondelete="SET NULL"), nullable=True)
    assigned_to = Column(String(255), default="")
    status = Column(String(50), default="open")  # open, in_progress, done, skipped
    due_date = Column(Date, nullable=True)
    result_notes = Column(Text, nullable=True)
    impact_outcome = Column(String(20), nullable=True)  # win | loss | flat | None=auto
    brief_id = Column(Integer, ForeignKey("content_briefs.id", ondelete="SET NULL"), nullable=True)
    lever_id = Column(Integer, nullable=True, index=True)  # GrowthLeverThread.id (soft FK for migrate ease)
    playbook_pattern = Column(String(100), nullable=True)  # e.g. ctr_gap — outcome memory key
    target_query = Column(String(500), nullable=True)  # dedupe target
    target_url = Column(String(2000), nullable=True)  # dedupe target
    fingerprint = Column(String(100), nullable=True, index=True)  # (client, pattern, query/url) hash
    created_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="tasks")
    insight = relationship("Insight", back_populates="tasks")
    brief = relationship("ContentBrief", back_populates="tasks", foreign_keys="Task.brief_id")
    action_plan_id = Column(Integer, ForeignKey("action_plans.id", ondelete="SET NULL"), nullable=True)
    action_plan = relationship("ActionPlan", back_populates="tasks")
    impact_snapshots = relationship("ImpactSnapshot", back_populates="task", cascade="all, delete-orphan")


class GrowthLeverThread(Base):
    """Living Detect→Prescribe→Execute→Prove→Report thread per growth lever."""
    __tablename__ = "growth_lever_threads"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), default="detected", index=True)
    # detected | prescribed | in_progress | proving | proven | dismissed
    title = Column(String(500), nullable=False)
    stage = Column(String(100), default="")
    cause = Column(Text, nullable=True)
    fix = Column(Text, nullable=True)
    impact_score = Column(Float, default=50.0)
    source_insight_ids = Column(Text, default="[]")  # JSON list of insight ids
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    brief_id = Column(Integer, ForeignKey("content_briefs.id", ondelete="SET NULL"), nullable=True)
    impact_summary = Column(Text, nullable=True)
    confidence_label = Column(String(50), nullable=True)
    include_in_report = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow)
    resolved_at = Column(DateTime, nullable=True)

    client = relationship("Client", back_populates="growth_levers")
    task = relationship("Task", foreign_keys=[task_id])
    brief = relationship("ContentBrief", foreign_keys=[brief_id])


class WeeklySummary(Base):
    __tablename__ = "weekly_summaries"
    __table_args__ = (
        UniqueConstraint("client_id", "week_start", name="uq_weekly_summary_client_week"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    week_start = Column(Date, nullable=False)
    content = Column(Text, nullable=False)
    reviewed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="weekly_summaries")


class ActionPlan(Base):
    __tablename__ = "action_plans"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    priority_score = Column(Float, default=0.0)
    estimated_impact = Column(Text, nullable=True)
    estimated_effort = Column(String(50), default="medium")
    status = Column(String(50), default="draft")  # draft, active, completed, archived
    created_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="action_plans")
    tasks = relationship("Task", back_populates="action_plan")


class ImpactSnapshot(Base):
    __tablename__ = "impact_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_name = Column(String(100), nullable=False)
    source = Column(String(50), nullable=True)
    before_value = Column(Float, nullable=False)
    after_value = Column(Float, nullable=True)
    change_pct = Column(Float, nullable=True)
    snapshot_type = Column(String(20), default="baseline")  # baseline, recheck
    created_at = Column(DateTime, default=utcnow)

    task = relationship("Task", back_populates="impact_snapshots")
    client = relationship("Client", back_populates="impact_snapshots")


class ContentBrief(Base):
    __tablename__ = "content_briefs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    insight_id = Column(Integer, ForeignKey("insights.id", ondelete="SET NULL"), nullable=True)
    keyword = Column(String(255), nullable=False)
    title = Column(Text, nullable=True)
    outline = Column(Text, nullable=True)
    word_count = Column(Integer, nullable=True)
    related_keywords = Column(Text, nullable=True)
    status = Column(String(50), default="draft")
    created_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="content_briefs")
    insight = relationship("Insight", back_populates="content_briefs")
    tasks = relationship("Task", back_populates="brief")


class ClientMilestone(Base):
    """Per-client milestone events that affect data comparability — site relaunch,
    rebrand, platform migration, etc. Used by the discontinuity system to
    suppress WoW penalties during unstable periods."""
    __tablename__ = "client_milestones"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    milestone_type = Column(String(50), nullable=False)  # "site_relaunch", future: "rebrand", "platform_migration"
    occurred_at = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="milestones")


class ClientBaseline(Base):
    """Frozen engagement-start KPI snapshot for monthly client reports."""
    __tablename__ = "client_baselines"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    captured_at = Column(DateTime, default=utcnow)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    period_days = Column(Integer, nullable=True)
    kpis_json = Column(Text, nullable=False, default="{}")
    notes = Column(Text, nullable=True)

    client = relationship("Client", back_populates="baseline")


class MonthlyReport(Base):
    """Persisted calendar-month success reports."""
    __tablename__ = "monthly_reports"
    __table_args__ = (UniqueConstraint("client_id", "year", "month", name="uq_monthly_report_period"),)

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    payload_json = Column(Text, nullable=False)
    generated_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="monthly_reports")


class TrackedKeyword(Base):
    """Keywords the agency watches for Google ranking position (GSC-backed)."""
    __tablename__ = "tracked_keywords"
    __table_args__ = (
        UniqueConstraint("client_id", "keyword", name="uq_tracked_keyword_client"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    keyword = Column(String(500), nullable=False)
    target_url = Column(String(1000), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="tracked_keywords")


class PageSnapshot(Base):
    """Fetched HTML document structure for a client URL (not a time-series metric)."""
    __tablename__ = "page_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(1000), nullable=False, index=True)
    title = Column(String(500), nullable=True)
    meta_description = Column(String(500), nullable=True)
    h1 = Column(String(500), nullable=True)
    headings_json = Column(Text, nullable=True)
    word_count = Column(Integer, nullable=True)
    schema_types = Column(Text, nullable=True)
    internal_links_json = Column(Text, nullable=True)
    canonical_url = Column(String(1000), nullable=True)
    status_code = Column(Integer, nullable=True)
    fetched_at = Column(DateTime, default=utcnow)
    content_hash = Column(String(64), nullable=True)

    client = relationship("Client", back_populates="page_snapshots")


class PageSpeedFinding(Base):
    """Lighthouse opportunity audits with concrete offenders (from PSI details.items)."""
    __tablename__ = "pagespeed_findings"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(1000), nullable=False, index=True)
    strategy = Column(String(10), nullable=False)
    audit_id = Column(String(100), nullable=False)
    title = Column(String(255), nullable=True)
    savings_ms = Column(Float, nullable=True)
    savings_bytes = Column(Float, nullable=True)
    top_offenders_json = Column(Text, nullable=True)
    fetched_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="pagespeed_findings")


class SerpSnapshot(Base):
    """Licensed SERP API snapshot for a flagged query (not scraped google.com)."""
    __tablename__ = "serp_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    query = Column(String(500), nullable=False, index=True)
    results_json = Column(Text, nullable=False, default="[]")
    provider = Column(String(50), default="")
    fetched_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="serp_snapshots")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)


class AiUsageLog(Base):
    """Per-call AI usage for cost transparency."""
    __tablename__ = "ai_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(50), default="")
    model = Column(String(100), default="")
    purpose = Column(String(100), default="")
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="ai_usage_logs")


class AnomalyNotification(Base):
    """Queue for anomaly-triggered desktop / in-app alerts."""
    __tablename__ = "anomaly_notifications"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    insight_id = Column(Integer, ForeignKey("insights.id", ondelete="SET NULL"), nullable=True)
    severity = Column(String(20), default="high")
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    delivered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="anomaly_notifications")
    insight = relationship("Insight")


class Recommendation(Base):
    """Living recommendation — proposed fix tracked through execution, verification, and learning.

    Bridges the gap between insight generation and proven outcomes. Every time an agency
    accepts a recommendation, executes it, and measures the result, the recommendation
    lifecycle closes. Historical recommendations power cross-client effectiveness scoring.
    """
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    insight_id = Column(Integer, ForeignKey("insights.id", ondelete="SET NULL"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)

    status = Column(String(30), default="proposed", index=True)
    # proposed → accepted → scheduled → in_progress → completed → verified → archived

    fix_type = Column(String(100), nullable=True, index=True)
    title = Column(String(500), nullable=False)

    expected_lift_pct = Column(Float, nullable=True)
    expected_metric = Column(String(100), nullable=True)

    actual_lift_pct = Column(Float, nullable=True)
    outcome = Column(String(20), nullable=True)  # win | loss | flat

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)

    client = relationship("Client", back_populates="recommendations")
    insight = relationship("Insight")
    task = relationship("Task")


class BacklinkSnapshot(Base):
    """Per-domain backlink profile snapshot from imported data (Ahrefs/SEMrush CSV).

    Stores referring domains, domain rating, and toxic link counts so the insight
    engine can correlate backlink changes with ranking movements.
    """
    __tablename__ = "backlink_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    domain = Column(String(255), nullable=False, index=True)
    referring_domains = Column(Integer, default=0)
    total_backlinks = Column(Integer, default=0)
    domain_rating = Column(Float, nullable=True)
    toxic_score = Column(Integer, default=0)  # 0-100, higher = more toxic
    new_links_30d = Column(Integer, default=0)
    lost_links_30d = Column(Integer, default=0)
    dofollow_ratio = Column(Float, nullable=True)
    top_anchor_text = Column(Text, nullable=True)
    fetched_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="backlink_snapshots")


class ClientSeasonality(Base):
    """Rolling 52-week per-metric baseline for seasonal adjustment.

    Each row stores the expected weekly value for a metric based on historical
    data. Decline alerts use this to distinguish real drops from seasonal patterns.
    """
    __tablename__ = "client_seasonality"
    __table_args__ = (
        UniqueConstraint("client_id", "source", "metric_name", "iso_week", name="uq_seasonality_week"),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String(50), nullable=False)
    metric_name = Column(String(100), nullable=False)
    iso_week = Column(Integer, nullable=False)  # 1-53
    median_value = Column(Float, nullable=False)
    p25_value = Column(Float, nullable=True)
    p75_value = Column(Float, nullable=True)
    sample_years = Column(Integer, default=1)
    computed_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="seasonality")


class CruxSnapshot(Base):
    """Chrome UX Report (CrUX) field data — real-user Core Web Vitals.

    Google ranks on field data (28-day rolling), not lab scores. This model
    stores origin-level and URL-level CrUX metrics so the insight engine can
    distinguish lab-score-passing pages that users actually experience as slow.
    """
    __tablename__ = "crux_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(1000), nullable=False, index=True)
    form_factor = Column(String(10), default="PHONE")  # PHONE | DESKTOP
    lcp_p75 = Column(Float, nullable=True)  # Largest Contentful Paint (ms) — 75th percentile
    inp_p75 = Column(Float, nullable=True)  # Interaction to Next Paint (ms)
    cls_p75 = Column(Float, nullable=True)  # Cumulative Layout Shift
    lcp_good_pct = Column(Float, nullable=True)  # % of experiences in "good" range
    inp_good_pct = Column(Float, nullable=True)
    cls_good_pct = Column(Float, nullable=True)
    ttfb_p75 = Column(Float, nullable=True)  # Time to First Byte (ms)
    fetched_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="crux_snapshots")


class PulseShareToken(Base):
    """Tokenized read-only Success Pulse link for a client (shareable status)."""

    __tablename__ = "pulse_share_tokens"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=True)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    client = relationship("Client")


class ReportShareToken(Base):
    """Tokenized read-only success report link for a client (remote portal)."""

    __tablename__ = "report_share_tokens"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id = Column(
        Integer, ForeignKey("monthly_reports.id", ondelete="CASCADE"), nullable=True, index=True
    )
    token = Column(String(64), nullable=False, unique=True, index=True)
    period_start = Column(String(20), nullable=True)
    period_end = Column(String(20), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    client = relationship("Client")
    report = relationship("MonthlyReport")


class Experiment(Base):
    """Formal A/B / test registry — hypothesis → control/treatment → Prove metric."""

    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    recommendation_id = Column(
        Integer, ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True
    )

    hypothesis = Column(Text, nullable=False)
    control = Column(Text, nullable=True)
    treatment = Column(Text, nullable=True)
    success_metric = Column(String(100), nullable=True)
    status = Column(String(30), default="draft", index=True)
    # draft | running | won | lost | inconclusive | archived

    start_at = Column(DateTime, nullable=True)
    end_at = Column(DateTime, nullable=True)
    outcome_lift_pct = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="experiments")
    task = relationship("Task")
    recommendation = relationship("Recommendation")


class GbpSnapshot(Base):
    """Google Business Profile insights data — local SEO metrics.

    For the core ICP (roofers, plumbers, landscapers), GBP drives 40-60% of leads.
    This model stores GBP call, direction, website click, and search metrics.
    """
    __tablename__ = "gbp_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id = Column(String(255), nullable=False)
    location_name = Column(String(500), nullable=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    search_views = Column(Integer, default=0)  # appeared in search results
    map_views = Column(Integer, default=0)
    website_clicks = Column(Integer, default=0)
    direction_requests = Column(Integer, default=0)
    phone_calls = Column(Integer, default=0)
    total_actions = Column(Integer, default=0)
    direct_searches = Column(Integer, default=0)  # typed brand name
    discovery_searches = Column(Integer, default=0)  # category/product — non-brand
    fetched_at = Column(DateTime, default=utcnow)

    client = relationship("Client", back_populates="gbp_snapshots")
