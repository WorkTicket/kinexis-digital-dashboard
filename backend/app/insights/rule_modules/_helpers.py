"""Insight rule helper functions — shared query utils used by all rules.

Extracted from rules.py to keep the main module focused on rule logic.
"""

import logging
from datetime import date, timedelta
from sqlalchemy import func, and_
from sqlalchemy.orm import Session
from app.models import MetricDaily

logger = logging.getLogger(__name__)


def expected_ctr(pos: float) -> float:
    EXPECTED_CTR_BY_POS = {
        range(1, 2): 0.30,
        range(2, 3): 0.15,
        range(3, 4): 0.10,
        range(4, 5): 0.07,
        range(5, 6): 0.05,
        range(6, 8): 0.03,
        range(8, 11): 0.02,
        range(11, 21): 0.01,
    }
    pos_int = round(pos)
    for rng, ctr in EXPECTED_CTR_BY_POS.items():
        if pos_int in rng:
            return ctr
    return 0.01


def avg_position_30d(db, client_id: int, query: str, start: date) -> float | None:
    row = (
        db.query(func.avg(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name == "position",
                MetricDaily.dimension_type == "query",
                MetricDaily.dimension_value == query,
                MetricDaily.date >= start,
            )
        )
        .scalar()
    )
    return float(row) if row is not None else None


def brand_terms(db, client_id: int) -> list[str]:
    from app.brand_queries import brand_terms_for_client
    from app.models import Client

    client = db.query(Client).filter(Client.id == client_id).first()
    return brand_terms_for_client(client) if client else []


def skip_geo_growth_query(db, client_id: int, query: str) -> bool:
    from app.models import Client
    from app.service_area import is_growth_eligible_query, parse_service_area

    client = db.query(Client).filter(Client.id == client_id).first()
    return not is_growth_eligible_query(query, parse_service_area(client))


def fmt_url_list(urls: list[str], n: int = 3) -> str:
    clean = [u for u in urls if u][:n]
    if not clean:
        return ""
    return ", ".join(f'"{u}"' for u in clean)


def top_gsc_pages_by_clicks(db, client_id: int, *, days: int = 28, limit: int = 5) -> list[str]:
    today = date.today()
    start = today - timedelta(days=days)
    rows = (
        db.query(MetricDaily.dimension_value, func.sum(MetricDaily.value).label("clicks"))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name == "clicks",
                MetricDaily.dimension_type == "page",
                MetricDaily.date >= start,
                MetricDaily.dimension_value.isnot(None),
            )
        )
        .group_by(MetricDaily.dimension_value)
        .order_by(func.sum(MetricDaily.value).desc())
        .limit(limit)
        .all()
    )
    return [r.dimension_value for r in rows if r.dimension_value]


def top_dropped_gsc_pages(
    db,
    client_id: int,
    metric_name: str,
    this_start: date,
    prev_start: date,
    prev_end: date,
    *,
    limit: int = 5,
) -> list[tuple[str, float, float, float]]:
    this_rows = (
        db.query(MetricDaily.dimension_value, func.sum(MetricDaily.value).label("total"))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name == metric_name,
                MetricDaily.dimension_type == "page",
                MetricDaily.date >= this_start,
                MetricDaily.dimension_value.isnot(None),
            )
        )
        .group_by(MetricDaily.dimension_value)
        .all()
    )
    prev_rows = (
        db.query(MetricDaily.dimension_value, func.sum(MetricDaily.value).label("total"))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name == metric_name,
                MetricDaily.dimension_type == "page",
                MetricDaily.date >= prev_start,
                MetricDaily.date <= prev_end,
                MetricDaily.dimension_value.isnot(None),
            )
        )
        .group_by(MetricDaily.dimension_value)
        .all()
    )
    this_map = {r.dimension_value: float(r.total or 0) for r in this_rows if r.dimension_value}
    prev_map = {r.dimension_value: float(r.total or 0) for r in prev_rows if r.dimension_value}
    dropped: list[tuple[str, float, float, float, float]] = []
    for url, prev_val in prev_map.items():
        if prev_val < 3:
            continue
        cur = this_map.get(url, 0.0)
        delta = prev_val - cur
        if delta <= 0:
            continue
        change_pct = (cur - prev_val) / prev_val
        dropped.append((url, prev_val, cur, change_pct, delta))
    dropped.sort(key=lambda x: x[4], reverse=True)
    return [(u, p, c, ch) for u, p, c, ch, _ in dropped[:limit]]


def top_ga4_landing_pages(db, client_id: int, *, days: int = 28, limit: int = 5) -> list[str]:
    today = date.today()
    start = today - timedelta(days=days)
    rows = (
        db.query(MetricDaily.dimension_value, func.sum(MetricDaily.value).label("sessions"))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "ga4",
                MetricDaily.metric_name == "sessions",
                MetricDaily.dimension_type == "landing_page",
                MetricDaily.date >= start,
                MetricDaily.dimension_value.isnot(None),
            )
        )
        .group_by(MetricDaily.dimension_value)
        .order_by(func.sum(MetricDaily.value).desc())
        .limit(limit)
        .all()
    )
    return [r.dimension_value for r in rows if r.dimension_value]


def bing_datasource_connected(db, client_id: int) -> bool:
    from app.models import DataSource

    return (
        db.query(DataSource)
        .filter(
            DataSource.client_id == client_id,
            DataSource.type == "bing",
            DataSource.status == "active",
        )
        .first()
        is not None
    )


def sum_metric(
    db, client_id: int, source: str, metric: str,
    start: date, end: date, dim: str | None = None,
) -> float:
    filters = [
        MetricDaily.client_id == client_id,
        MetricDaily.source == source,
        MetricDaily.metric_name == metric,
        MetricDaily.date >= start,
        MetricDaily.date <= end,
    ]
    if dim is not None:
        filters.append(MetricDaily.dimension_type == dim)
    row = db.query(func.sum(MetricDaily.value)).filter(and_(*filters)).scalar()
    return float(row) if row is not None else 0.0


def has_ever_had_conversions(db, client_id: int, *, lookback_days: int = 90) -> tuple[bool, float]:
    """Check if a client has ever recorded any conversion events in the lookback window.

    Returns (has_conversions, total_conversions). Used by insight rules to distinguish
    "tracking is broken" from "CTAs need work" — if zero conversions have ever been
    recorded, the insight should be about verifying tracking, not fixing CTAs.
    """
    today = date.today()
    start = today - timedelta(days=lookback_days)
    total = (
        db.query(func.sum(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "ga4",
                MetricDaily.metric_name == "key_events",
                MetricDaily.date >= start,
            )
        )
        .scalar() or 0
    )
    if float(total) > 0:
        return True, float(total)
    # Also check HubSpot for any leads (proxy for any conversion activity)
    hubspot_total = (
        db.query(func.sum(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "hubspot",
                MetricDaily.metric_name.in_(["leads", "revenue"]),
                MetricDaily.date >= start,
            )
        )
        .scalar() or 0
    )
    has_any = float(total) > 0 or float(hubspot_total) > 0
    return has_any, float(total)
