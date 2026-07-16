"""Per-client insight rule thresholds (from client profile_json.thresholds)."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import and_, func

# Industry-standard agency floors: problems need ~1k impr/30d; opportunities ~250.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "position_min": 11,
    "position_max": 20,
    "wow_impression_growth": 0.20,
    # Fraction below expected CTR: 0.40 = problem bar; opportunity uses ctr_gap_pct_opp
    "ctr_gap_pct": 0.40,
    "ctr_gap_pct_opp": 0.30,
    "pagespeed_urgent": 50,
    "pagespeed_improve": 70,
    "decline_wow": -0.20,
    # 30d volume floors (industry-standard actionable bar)
    "min_impressions_30d": 1000,
    "min_impressions_30d_opp": 250,
    # Weekly floors for WoW content growth (derived from opp bar â‰ˆ 250/30d)
    "min_query_impressions_week": 60,
    "min_query_impressions_prev": 40,
    "min_query_impressions_ctr": 1000,
    "min_site_clicks_decline": 50,
    "min_site_impressions_decline": 500,
    "min_landing_sessions_30d": 250,
    "bounce_rate_high": 0.70,
    "max_insights_per_rule": 8,
    "max_open_problems": 8,
    "max_open_opportunities": 10,
    "max_open_noisy_insights": 10,
    # Site-level thin traffic (7d) â€” auto-tighten rules + soften portfolio risk
    "thin_traffic_clicks": 25,
    "thin_traffic_sessions": 50,
    # Zero-click specific: cap at 3 per run to avoid spam
    "max_zero_click_per_rule": 3,
}


def merge_thresholds(overrides: dict[str, Any] | None = None) -> dict[str, float]:
    merged = dict(DEFAULT_THRESHOLDS)
    if not overrides:
        return merged
    for key, val in overrides.items():
        if key in merged and val is not None:
            try:
                merged[key] = float(val)
            except (TypeError, ValueError):
                continue
    return merged


def _site_traffic_7d(db, client_id: int) -> tuple[float, float]:
    from app.models import MetricDaily
    from app.dimensions import SITE_TOTAL_DIMENSION

    today = date.today()
    start = today - timedelta(days=7)

    gsc_dim = SITE_TOTAL_DIMENSION.get("gsc")
    clicks = (
        db.query(func.sum(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name == "clicks",
                MetricDaily.dimension_type == gsc_dim,
                MetricDaily.date >= start,
            )
        )
        .scalar()
        or 0
    )
    # Fallback: if preferred dimension returns 0, try site-level totals
    # (data may exist at site level even if dimension-specific sync is partial).
    if not clicks:
        clicks = (
            db.query(func.sum(MetricDaily.value))
            .filter(
                and_(
                    MetricDaily.client_id == client_id,
                    MetricDaily.source == "gsc",
                    MetricDaily.metric_name == "clicks",
                    MetricDaily.dimension_type == "",
                    MetricDaily.date >= start,
                )
            )
            .scalar()
            or 0
        )
    ga4_dim = SITE_TOTAL_DIMENSION.get("ga4")
    sessions = (
        db.query(func.sum(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "ga4",
                MetricDaily.metric_name == "sessions",
                MetricDaily.dimension_type == ga4_dim,
                MetricDaily.date >= start,
            )
        )
        .scalar()
        or 0
    )
    if not sessions:
        sessions = (
            db.query(func.sum(MetricDaily.value))
            .filter(
                and_(
                    MetricDaily.client_id == client_id,
                    MetricDaily.source == "ga4",
                    MetricDaily.metric_name == "sessions",
                    MetricDaily.date >= start,
                )
            )
            .scalar()
            or 0
        )
    return float(clicks), float(sessions)


def thresholds_for_client(db, client_id: int) -> dict[str, float]:
    from app.models import Client

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client or not client.profile_json:
        merged = dict(DEFAULT_THRESHOLDS)
    else:
        try:
            profile = json.loads(client.profile_json or "{}")
        except json.JSONDecodeError:
            profile = {}
        raw = profile.get("thresholds") if isinstance(profile, dict) else None
        merged = merge_thresholds(raw if isinstance(raw, dict) else None)

    clicks, sessions = _site_traffic_7d(db, client_id)
    merged["site_clicks_7d"] = clicks
    merged["site_sessions_7d"] = sessions
    thin = (
        clicks < merged["thin_traffic_clicks"]
        and sessions < merged["thin_traffic_sessions"]
    )
    merged["thin_traffic"] = 1.0 if thin else 0.0

    # Low sample â†’ demand clearer signal before creating insights
    if thin:
        merged["wow_impression_growth"] = max(merged["wow_impression_growth"], 0.50)
        merged["min_query_impressions_week"] = max(merged["min_query_impressions_week"], 80)
        merged["min_query_impressions_prev"] = max(merged["min_query_impressions_prev"], 50)
        merged["min_impressions_30d"] = max(merged["min_impressions_30d"], 500)
        merged["min_impressions_30d_opp"] = max(merged["min_impressions_30d_opp"], 150)
        merged["min_query_impressions_ctr"] = max(
            merged["min_query_impressions_ctr"], merged["min_impressions_30d"]
        )
        merged["max_insights_per_rule"] = min(merged["max_insights_per_rule"], 5)
        merged["decline_wow"] = min(merged["decline_wow"], -0.35)
        merged["min_landing_sessions_30d"] = max(merged["min_landing_sessions_30d"], 100)

    return merged


def cap_insights(insights: list[dict], thr: dict[str, float] | None = None) -> list[dict]:
    """Keep the highest-impact insights per rule batch."""
    if not insights:
        return insights
    limit = int((thr or DEFAULT_THRESHOLDS).get("max_insights_per_rule", 8))
    ranked = sorted(
        insights,
        key=lambda i: float(i.get("impact_weight") or 0),
        reverse=True,
    )
    return ranked[: max(1, limit)]

