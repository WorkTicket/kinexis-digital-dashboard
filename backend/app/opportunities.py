"""
Period-aware opportunity tables — rising queries, CTR gaps, landing pages.
Shared by metrics router and success reports.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import MetricDaily, Client
from app.brand_queries import brand_terms_for_client, filter_query_scope, BrandScope


def _aggregate(
    db: Session,
    client_id: int,
    source: str,
    dim_type: str,
    metric_names: list[str],
    start: date,
    end: date,
) -> dict[str, dict[str, float]]:
    rows = (
        db.query(
            MetricDaily.dimension_value,
            MetricDaily.metric_name,
            func.sum(MetricDaily.value).label("total"),
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == source,
                MetricDaily.dimension_type == dim_type,
                MetricDaily.metric_name.in_(metric_names),
                MetricDaily.date >= start,
                MetricDaily.date <= end,
                MetricDaily.dimension_value.isnot(None),
            )
        )
        .group_by(MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )
    by_dim: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        by_dim[r.dimension_value][r.metric_name] = float(r.total or 0)
    return by_dim


def build_opportunities(
    db: Session,
    client_id: int,
    *,
    days: Optional[int] = None,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    limit: int = 25,
    brand_scope: BrandScope = "non_brand",
) -> dict:
    """
    Build opportunity tables for a rolling window or an explicit date range.

    Rolling mode (days): compares second half of the window vs first half.
    Explicit range: compares the period vs an equal-length prior period.
    """
    if period_start is not None and period_end is not None:
        this_start = period_start
        this_end = period_end
        span = (period_end - period_start).days + 1
        prev_end = period_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span - 1)
        days_label = span
        half_days = max(1, span)
    else:
        d = days or 28
        today = date.today()
        this_start = today - timedelta(days=d // 2)
        this_end = today
        prev_start = today - timedelta(days=d)
        prev_end = this_start - timedelta(days=1)
        days_label = d
        half_days = max(1, d // 2)

    client = db.query(Client).filter(Client.id == client_id).first()
    brand_terms = brand_terms_for_client(client) if client else []
    from app.service_area import is_growth_eligible_query, parse_service_area

    sa = parse_service_area(client)

    q_this = _aggregate(
        db, client_id, "gsc", "query",
        ["impressions", "clicks", "position", "ctr"], this_start, this_end,
    )
    q_prev = _aggregate(
        db, client_id, "gsc", "query",
        ["impressions", "clicks", "position", "ctr"], prev_start, prev_end,
    )
    rising_queries = []
    for query, metrics in q_this.items():
        if not filter_query_scope(query, brand_terms, brand_scope):
            continue
        # Keep GSC noise visible elsewhere; do not surface as growth opportunities
        if not is_growth_eligible_query(query, sa):
            continue
        prev = q_prev.get(query, {})
        imp = metrics.get("impressions", 0)
        prev_imp = prev.get("impressions", 0)
        pos = metrics.get("position", 0)
        if prev_imp <= 0 or imp < 60:
            continue
        growth = ((imp - prev_imp) / prev_imp) * 100
        if growth < 20:
            continue
        rising_queries.append({
            "query": query,
            "impressions": round(imp, 1),
            "prev_impressions": round(prev_imp, 1),
            "growth_pct": round(growth, 1),
            "clicks": round(metrics.get("clicks", 0), 1),
            "position": round(pos, 1) if pos < 100 else 100,
            "ctr": round(metrics.get("ctr", 0), 4),
            "is_brand": bool(brand_terms) and not filter_query_scope(query, brand_terms, "non_brand"),
        })
    rising_queries.sort(key=lambda x: x["growth_pct"], reverse=True)
    # Prefer striking-distance (11–20); fall back to broader 8–25 band
    rising_queries = (
        [r for r in rising_queries if 11 <= r["position"] <= 20][:limit]
        or [r for r in rising_queries if 8 <= r["position"] <= 25][:limit]
        or rising_queries[:limit]
    )

    p_this = _aggregate(
        db, client_id, "gsc", "page",
        ["impressions", "clicks", "ctr", "position"], this_start, this_end,
    )
    ctr_under = []
    for page, metrics in p_this.items():
        imp = metrics.get("impressions", 0)
        clicks = metrics.get("clicks", 0)
        # Align with opportunity volume floor (~250/30d; half-window ≈ 125 for 28d)
        if imp < 125:
            continue
        ctr = (clicks / imp) if imp else 0
        pos = metrics.get("position", 0)
        if pos > 100:
            pos = min(pos, 100)
        expected = max(0.01, 0.28 * (0.75 ** max(0, pos - 1)))
        if ctr >= expected * 0.7:
            continue
        ctr_under.append({
            "page": page,
            "impressions": round(imp, 1),
            "clicks": round(clicks, 1),
            "ctr": round(ctr, 4),
            "expected_ctr": round(expected, 4),
            "gap_pct": round((expected - ctr) / expected * 100, 1) if expected else 0,
            "position": round(pos, 1),
        })
    ctr_under.sort(key=lambda x: x["gap_pct"], reverse=True)
    ctr_under = ctr_under[:limit]

    lp_sessions = _aggregate(
        db, client_id, "ga4", "landing_page",
        ["sessions", "key_events"], this_start, this_end,
    )
    landing = []
    for page, metrics in lp_sessions.items():
        sessions = metrics.get("sessions", 0)
        conversions = metrics.get("key_events", 0)
        if sessions < 50:
            continue
        cvr = (conversions / sessions * 100) if sessions else 0
        landing.append({
            "page": page,
            "sessions": round(sessions, 1),
            "conversions": round(conversions, 1),
            "cvr": round(cvr, 2),
        })
    landing.sort(key=lambda x: x["sessions"], reverse=True)
    total_sessions = sum(x["sessions"] for x in landing) or 1
    avg_cvr = sum(x["cvr"] * x["sessions"] for x in landing) / total_sessions
    for row in landing:
        row["vs_avg"] = round(row["cvr"] - avg_cvr, 2)
    landing = landing[:limit]

    return {
        "client_id": client_id,
        "days": days_label,
        "period": {"start": this_start.isoformat(), "end": this_end.isoformat()},
        "brand_scope": brand_scope,
        "rising_queries": rising_queries,
        "ctr_underperformers": ctr_under,
        "landing_pages": landing,
    }


def campaign_performance(
    db: Session,
    client_id: int,
    period_start: date,
    period_end: date,
    limit: int = 15,
) -> list[dict]:
    """Ads campaign rollup for the period (ads_csv + future live sources)."""
    rows = (
        db.query(
            MetricDaily.source,
            MetricDaily.dimension_value,
            MetricDaily.metric_name,
            func.sum(MetricDaily.value).label("total"),
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source.in_(["ads_csv", "google_ads", "meta_ads"]),
                MetricDaily.dimension_type == "campaign",
                MetricDaily.metric_name.in_(
                    ["impressions", "clicks", "cost", "conversions", "conversion_value"]
                ),
                MetricDaily.date >= period_start,
                MetricDaily.date <= period_end,
                MetricDaily.dimension_value.isnot(None),
            )
        )
        .group_by(MetricDaily.source, MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )
    by_campaign: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        key = r.dimension_value
        by_campaign[key][r.metric_name] += float(r.total or 0)

    campaigns = []
    for name, metrics in by_campaign.items():
        impressions = metrics.get("impressions", 0)
        clicks = metrics.get("clicks", 0)
        cost = metrics.get("cost", 0)
        conversions = metrics.get("conversions", 0)
        value = metrics.get("conversion_value", 0)
        if impressions == 0 and clicks == 0 and cost == 0:
            continue
        campaigns.append({
            "campaign": name,
            "impressions": round(impressions, 1),
            "clicks": round(clicks, 1),
            "cost": round(cost, 2),
            "conversions": round(conversions, 2),
            "conversion_value": round(value, 2),
            "ctr": round((clicks / impressions * 100) if impressions else 0, 2),
            "cpc": round((cost / clicks) if clicks else 0, 2),
        })
    campaigns.sort(key=lambda c: c["cost"] or c["clicks"], reverse=True)
    return campaigns[:limit]
