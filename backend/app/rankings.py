"""
Google ranking tracker — GSC query positions with period-over-period change.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import MetricDaily, TrackedKeyword, Client
from app.brand_queries import brand_terms_for_client, filter_query_scope, is_brand_query, BrandScope


def _bucket_for(position: float | None) -> str:
    if position is None:
        return "unknown"
    if position <= 3:
        return "top3"
    if position <= 10:
        return "top10"
    if position <= 20:
        return "page2"
    return "deeper"


def _period_query_metrics(
    db: Session,
    client_id: int,
    start: date,
    end: date,
) -> dict[str, dict[str, float]]:
    """Sum clicks/impressions and average position per query for a date range."""
    rows = (
        db.query(
            MetricDaily.dimension_value,
            MetricDaily.metric_name,
            func.sum(MetricDaily.value).label("total"),
            func.avg(MetricDaily.value).label("avg_val"),
            func.count(MetricDaily.id).label("n"),
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.dimension_type == "query",
                MetricDaily.metric_name.in_(["impressions", "clicks", "position", "ctr"]),
                MetricDaily.date >= start,
                MetricDaily.date <= end,
                MetricDaily.dimension_value.isnot(None),
            )
        )
        .group_by(MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )
    by_query: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        q = r.dimension_value
        if not q:
            continue
        if r.metric_name in ("impressions", "clicks"):
            by_query[q][r.metric_name] = float(r.total or 0)
        elif r.metric_name in ("position", "ctr"):
            by_query[q][r.metric_name] = float(r.avg_val or 0)
    return by_query


def build_rankings(
    db: Session,
    client_id: int,
    *,
    days: int = 28,
    bucket: Optional[str] = None,
    search: Optional[str] = None,
    tracked_only: bool = False,
    brand_scope: BrandScope = "all",
    limit: int = 200,
) -> dict:
    today = date.today()
    this_end = today
    this_start = today - timedelta(days=days - 1)
    prev_end = this_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    this = _period_query_metrics(db, client_id, this_start, this_end)
    prev = _period_query_metrics(db, client_id, prev_start, prev_end)

    client = db.query(Client).filter(Client.id == client_id).first()
    brand_terms = brand_terms_for_client(client) if client else []

    # Case-insensitive lookup so pinned keywords match GSC query casing
    this_by_lower = {k.lower(): (k, v) for k, v in this.items()}
    prev_by_lower = {k.lower(): (k, v) for k, v in prev.items()}

    tracked_rows = (
        db.query(TrackedKeyword)
        .filter(TrackedKeyword.client_id == client_id)
        .order_by(TrackedKeyword.created_at.desc())
        .all()
    )
    tracked_map = {t.keyword.lower(): t for t in tracked_rows}
    tracked_ids = {t.keyword.lower(): t.id for t in tracked_rows}

    # Prefer GSC casing when available; otherwise use tracked keyword text
    display_queries: dict[str, str] = {}
    for q in this.keys():
        display_queries[q.lower()] = q
    for t in tracked_rows:
        display_queries.setdefault(t.keyword.lower(), t.keyword)

    rankings: list[dict] = []
    for key_l, query in display_queries.items():
        cur = this_by_lower.get(key_l, (query, {}))[1]
        prv = prev_by_lower.get(key_l, (query, {}))[1]
        # Prefer canonical GSC query string when present
        if key_l in this_by_lower:
            query = this_by_lower[key_l][0]
        position = cur.get("position")
        prev_position = prv.get("position")
        impressions = cur.get("impressions", 0)
        clicks = cur.get("clicks", 0)
        ctr = cur.get("ctr")
        if ctr is None and impressions > 0:
            ctr = clicks / impressions
        elif ctr is None:
            ctr = 0.0

        change = None
        if position is not None and prev_position is not None:
            # Negative change = improved (moved up)
            change = round(position - prev_position, 1)

        tracked = key_l in tracked_map
        tracked_row = tracked_map.get(key_l)

        # Skip zero-signal untracked queries
        if not tracked and impressions <= 0 and position is None:
            continue

        b = _bucket_for(position)
        rankings.append({
            "query": query,
            "position": round(position, 1) if position is not None else None,
            "prev_position": round(prev_position, 1) if prev_position is not None else None,
            "change": change,
            "impressions": round(impressions, 1),
            "clicks": round(clicks, 1),
            "ctr": round(float(ctr), 4),
            "bucket": b,
            "tracked": tracked,
            "tracked_id": tracked_ids.get(key_l),
            "target_url": tracked_row.target_url if tracked_row else None,
            "is_brand": is_brand_query(query, brand_terms) if brand_terms else False,
        })

    # Filters
    if tracked_only:
        rankings = [r for r in rankings if r["tracked"]]
    if bucket and bucket != "all":
        rankings = [r for r in rankings if r["bucket"] == bucket]
    if search:
        needle = search.strip().lower()
        rankings = [r for r in rankings if needle in r["query"].lower()]
    if brand_scope and brand_scope != "all":
        rankings = [
            r for r in rankings
            if filter_query_scope(r["query"], brand_terms, brand_scope)
        ]

    # Sort: tracked first, then by impressions desc, then position asc
    rankings.sort(
        key=lambda r: (
            0 if r["tracked"] else 1,
            -(r["impressions"] or 0),
            r["position"] if r["position"] is not None else 999,
        )
    )
    rankings = rankings[:limit]

    # Summary from full (unfiltered by search/bucket) set for KPI cards
    all_with_pos = []
    for key_l, (canon, m) in this_by_lower.items():
        pos = m.get("position")
        if pos is None:
            continue
        prev_m = prev_by_lower.get(key_l, (canon, {}))[1]
        all_with_pos.append({
            "position": pos,
            "prev_position": prev_m.get("position"),
            "impressions": m.get("impressions", 0),
            "tracked": key_l in tracked_map,
        })
    for t in tracked_rows:
        key_l = t.keyword.lower()
        if key_l in this_by_lower:
            continue
        # Tracked with no GSC data yet — skip from position summary
        pass
    improved = sum(
        1
        for r in all_with_pos
        if r["prev_position"] is not None and r["position"] < r["prev_position"] - 0.3
    )
    declined = sum(
        1
        for r in all_with_pos
        if r["prev_position"] is not None and r["position"] > r["prev_position"] + 0.3
    )
    top10 = sum(1 for r in all_with_pos if r["position"] <= 10)
    striking = sum(1 for r in all_with_pos if 11 <= r["position"] <= 20)

    weighted_num = 0.0
    weighted_den = 0.0
    for q, m in this.items():
        pos = m.get("position")
        imp = m.get("impressions", 0)
        if pos is not None and imp > 0:
            weighted_num += pos * imp
            weighted_den += imp
    avg_position = round(weighted_num / weighted_den, 1) if weighted_den else None

    buckets = {
        "top3": sum(1 for r in all_with_pos if r["position"] <= 3),
        "top10": sum(1 for r in all_with_pos if 3 < r["position"] <= 10),
        "page2": sum(1 for r in all_with_pos if 11 <= r["position"] <= 20),
        "deeper": sum(1 for r in all_with_pos if r["position"] > 20),
    }

    return {
        "client_id": client_id,
        "days": days,
        "brand_scope": brand_scope,
        "brand_terms": brand_terms,
        "period": {
            "start": this_start.isoformat(),
            "end": this_end.isoformat(),
            "prev_start": prev_start.isoformat(),
            "prev_end": prev_end.isoformat(),
        },
        "summary": {
            "avg_position": avg_position,
            "queries_ranked": len(all_with_pos),
            "top10": top10,
            "striking_distance": striking,
            "improved": improved,
            "declined": declined,
            "tracked_count": len(tracked_rows),
            "buckets": buckets,
        },
        "rankings": rankings,
        "tracked": [
            {
                "id": t.id,
                "keyword": t.keyword,
                "target_url": t.target_url,
                "notes": t.notes,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tracked_rows
        ],
    }


def keyword_history(
    db: Session,
    client_id: int,
    keyword: str,
    *,
    days: int = 90,
) -> dict:
    today = date.today()
    start = today - timedelta(days=days - 1)

    # Resolve GSC casing if present
    match = (
        db.query(MetricDaily.dimension_value)
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.dimension_type == "query",
                func.lower(MetricDaily.dimension_value) == keyword.lower(),
            )
        )
        .first()
    )
    resolved = match[0] if match else keyword

    rows = (
        db.query(
            MetricDaily.date,
            MetricDaily.metric_name,
            MetricDaily.value,
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.dimension_type == "query",
                MetricDaily.dimension_value == resolved,
                MetricDaily.metric_name.in_(["position", "impressions", "clicks"]),
                MetricDaily.date >= start,
                MetricDaily.date <= today,
            )
        )
        .order_by(MetricDaily.date.asc())
        .all()
    )
    by_date: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        by_date[r.date.isoformat()][r.metric_name] = float(r.value)

    history = [
        {
            "date": d,
            "position": round(m["position"], 1) if "position" in m else None,
            "impressions": round(m.get("impressions", 0), 1),
            "clicks": round(m.get("clicks", 0), 1),
        }
        for d, m in sorted(by_date.items())
    ]
    return {
        "client_id": client_id,
        "keyword": resolved,
        "days": days,
        "history": history,
    }
