"""Client onboarding auto-detection — eliminates 30 minutes of manual JSON setup.

Detects brand terms, service areas, and industry from existing GSC query data
and suggests thresholds based on client size. Provides a guided wizard API
instead of requiring raw profile_json editing.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from collections import Counter
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Client, MetricDaily
from app.query_intent import _ALL_US_STATES
from app.insight_thresholds import DEFAULT_THRESHOLDS

# ── Brand Term Auto-Detection ────────────────────────────────────────────

def detect_brand_terms(db: Session, client_id: int, *, top_n: int = 10) -> list[str]:
    """Auto-detect brand terms from GSC queries that get exceptionally high CTR.

    Brand queries typically have 30-60% CTR vs 2-5% for non-brand. We identify
    queries with CTR >= 20% and high impression share as likely brand terms.
    """
    today = date.today()
    start = today - timedelta(days=90)

    rows = (
        db.query(
            MetricDaily.dimension_value,
            func.sum(MetricDaily.value).label("impressions"),
        )
        .filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == "gsc",
            MetricDaily.metric_name == "impressions",
            MetricDaily.dimension_type == "query",
            MetricDaily.dimension_value != "",
            MetricDaily.date >= start,
        )
        .group_by(MetricDaily.dimension_value)
        .order_by(func.sum(MetricDaily.value).desc())
        .limit(200)
        .all()
    )

    clicks_map: dict[str, float] = {}
    ctr_rows = (
        db.query(
            MetricDaily.dimension_value,
            func.sum(MetricDaily.value).label("clicks"),
        )
        .filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == "gsc",
            MetricDaily.metric_name == "clicks",
            MetricDaily.dimension_type == "query",
            MetricDaily.dimension_value != "",
            MetricDaily.date >= start,
        )
        .group_by(MetricDaily.dimension_value)
        .all()
    )
    for r in ctr_rows:
        clicks_map[r.dimension_value or ""] = float(r.clicks or 0)

    candidates = []
    for r in rows:
        q = r.dimension_value or ""
        imps = float(r.impressions or 0)
        clicks = clicks_map.get(q, 0)
        if imps < 50:
            continue
        ctr = clicks / imps if imps > 0 else 0
        if ctr >= 0.20:  # high CTR = likely branded
            candidates.append((q, imps, ctr))

    candidates.sort(key=lambda x: x[1], reverse=True)

    # Extract brand-like tokens from top candidates
    brand_tokens: list[str] = []
    client = db.query(Client).filter(Client.id == client_id).first()
    client_name = (client.name or "").lower() if client else ""

    for q, _, _ in candidates[:top_n]:
        q_lower = q.lower().strip()
        # Extract domain-like fragments
        words = re.findall(r"[a-z0-9]{3,}", q_lower)
        for w in words:
            if w in _STOP_WORDS:
                continue
            if w in client_name:
                brand_tokens.append(w)
            # If the word appears in multiple high-CTR queries, it's likely brand
            count = sum(1 for cq, _, _ in candidates if w in cq.lower())
            if count >= 2 and w not in brand_tokens:
                brand_tokens.append(w)

    # Dedupe and filter
    seen = set()
    out = []
    for t in brand_tokens:
        if t.lower() not in seen and len(t) >= 3:
            seen.add(t.lower())
            out.append(t)
    return out[:top_n]


_STOP_WORDS = frozenset({
    "the", "and", "for", "with", "from", "your", "our", "their",
    "that", "this", "best", "top", "near", "cost", "price",
    "near", "service", "services", "company", "companies",
    "repair", "replacement", "installation",
})


# ── Service Area Auto-Detection ──────────────────────────────────────────

def detect_service_area(db: Session, client_id: int) -> dict[str, Any]:
    """Detect primary service area from GSC geo-modified queries.

    Scans query data for location patterns (city names, state codes, "near me")
    and infers the client's primary location and service areas.
    """
    today = date.today()
    start = today - timedelta(days=90)

    rows = (
        db.query(MetricDaily.dimension_value, func.sum(MetricDaily.value).label("total"))
        .filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == "gsc",
            MetricDaily.metric_name == "impressions",
            MetricDaily.dimension_type == "query",
            MetricDaily.dimension_value != "",
            MetricDaily.date >= start,
        )
        .group_by(MetricDaily.dimension_value)
        .having(func.sum(MetricDaily.value) >= 20)
        .all()
    )

    # Count city references in query text
    location_counts: Counter = Counter()
    city_pattern = re.compile(r'(?:in|near|at)\s+([a-z\s]{3,30})', re.I)

    for r in rows:
        q = r.dimension_value or ""
        impressions = float(r.total or 0)

        # "near me" pattern
        if "near me" in q.lower():
            location_counts["near_me"] += impressions

        # "in {city}" pattern
        for m in city_pattern.finditer(q.lower()):
            city = m.group(1).strip()
            if city not in _STOP_WORDS and len(city) > 2:
                location_counts[city] += impressions

    # Top locations
    top_locations = location_counts.most_common(5)

    return {
        "primary_location": top_locations[0][0] if top_locations else "",
        "top_markets": [
            {"location": loc, "impression_share": int(imp)}
            for loc, imp in top_locations
        ],
        "total_geo_queries": len(location_counts),
    }


# ── Threshold Auto-Suggestion ─────────────────────────────────────────────

def suggest_thresholds(db: Session, client_id: int) -> dict[str, float]:
    """Suggest insight rule thresholds based on client traffic volume.

    Returns a dict of overrides mergeable with DEFAULT_THRESHOLDS.
    Larger clients can use standard defaults. Small clients auto-tighten.
    """
    today = date.today()
    start = today - timedelta(days=30)

    clicks = (
        db.query(func.sum(MetricDaily.value))
        .filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == "gsc",
            MetricDaily.metric_name == "clicks",
            MetricDaily.date >= start,
        )
        .scalar() or 0
    )
    impressions = (
        db.query(func.sum(MetricDaily.value))
        .filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == "gsc",
            MetricDaily.metric_name == "impressions",
            MetricDaily.date >= start,
        )
        .scalar() or 0
    )

    if clicks == 0 and impressions == 0:
        return dict(DEFAULT_THRESHOLDS)

    if clicks < 50:
        # Micro site — tighten everything
        return {
            "min_impressions_30d": 200,
            "min_impressions_30d_opp": 100,
            "min_landing_sessions_30d": 50,
            "ctr_gap_pct": 0.50,
            "ctr_gap_pct_opp": 0.40,
            "decline_wow": -0.35,
            "max_insights_per_rule": 4,
        }
    elif clicks < 500:
        # Small site
        return {
            "min_impressions_30d": 500,
            "min_impressions_30d_opp": 150,
            "min_landing_sessions_30d": 100,
            "ctr_gap_pct": 0.45,
            "ctr_gap_pct_opp": 0.35,
        }
    elif clicks < 2000:
        # Medium site — standard defaults are fine
        return dict(DEFAULT_THRESHOLDS)
    else:
        # Large site — can be more lenient
        return {
            "min_impressions_30d": 2000,
            "min_impressions_30d_opp": 500,
            "min_landing_sessions_30d": 500,
        }


# ── Full Onboarding Guide ─────────────────────────────────────────────────

def run_onboarding_wizard(db: Session, client_id: int) -> dict[str, Any]:
    """Run the full auto-detection onboarding wizard.

    Returns a complete profile_json ready to save to the client record.
    The UI can display these auto-detected values for confirmation before applying.
    """
    brand_terms = detect_brand_terms(db, client_id)
    service_area = detect_service_area(db, client_id)
    thresholds = suggest_thresholds(db, client_id)

    client = db.query(Client).filter(Client.id == client_id).first()
    client_name = client.name if client else ""

    # Build the suggested profile
    profile = {
        "brand_terms": brand_terms,
        "service_areas": service_area.get("primary_location", ""),
        "primary_location": service_area.get("primary_location", ""),
        "thresholds": thresholds,
        "_onboarding": {
            "auto_detected": True,
            "detected_at": date.today().isoformat(),
            "confidence": "auto" if len(brand_terms) >= 2 else "low",
        }
    }

    return {
        "client_name": client_name,
        "brand_terms": brand_terms,
        "brand_terms_confidence": "high" if len(brand_terms) >= 3 else "medium" if len(brand_terms) >= 1 else "low",
        "primary_location": service_area.get("primary_location", ""),
        "top_markets": service_area.get("top_markets", []),
        "suggested_thresholds": thresholds,
        "traffic_tier": (
            "enterprise" if thresholds.get("min_impressions_30d", 0) >= 2000
            else "growing" if thresholds.get("min_impressions_30d", 0) >= 500
            else "starter"
        ),
        "profile_json": json.dumps(profile),
        "next_step": (
            "Review and confirm auto-detected brand terms, then connect at minimum "
            "Google Search Console and GA4 to begin insight generation."
        ),
    }
