"""Brand vs non-brand query classification for GSC query dimensions."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Literal, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Client, MetricDaily

BrandScope = Literal["all", "brand", "non_brand"]


def _tokenize_name(name: str) -> list[str]:
    parts = re.split(r"[\s\-_|/&.]+", (name or "").lower())
    return [p for p in parts if len(p) >= 3 and p not in {"the", "and", "llc", "inc", "ltd", "co"}]


def brand_terms_for_client(client: Client) -> list[str]:
    """Explicit profile terms + tokens from client name."""
    terms: list[str] = []
    try:
        profile = json.loads(client.profile_json or "{}")
    except (json.JSONDecodeError, TypeError):
        profile = {}
    raw = profile.get("brand_terms") if isinstance(profile, dict) else None
    if isinstance(raw, str):
        terms.extend(t.strip() for t in re.split(r"[,;\n]+", raw) if t.strip())
    elif isinstance(raw, list):
        terms.extend(str(t).strip() for t in raw if str(t).strip())
    terms.extend(_tokenize_name(client.name or ""))
    # Dedupe case-insensitively, keep longest first for matching quality
    seen: set[str] = set()
    out: list[str] = []
    for t in sorted(terms, key=len, reverse=True):
        key = t.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(t)
    return out


def is_brand_query(query: str, terms: list[str]) -> bool:
    if not query or not terms:
        return False
    q = query.lower()
    for term in terms:
        t = term.lower().strip()
        if not t:
            continue
        if " " in t:
            # Multi-word terms: raw substring match is safe
            # ("chase bank" won't false-match "steeplechase bank hours")
            if t in q:
                return True
        else:
            # Single-token terms (any length): word-boundary regex to prevent
            # substring false positives (e.g. "Chase" must not match "steeplechase")
            if re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", q):
                return True
    return False


def filter_query_scope(
    query: str,
    terms: list[str],
    scope: BrandScope = "all",
) -> bool:
    """Return True if query should be kept for the given scope."""
    if scope == "all" or not terms:
        return True
    branded = is_brand_query(query, terms)
    if scope == "brand":
        return branded
    return not branded


def brand_split_totals(
    db: Session,
    client_id: int,
    *,
    days: int = 28,
) -> dict:
    """Sum GSC query-dimension clicks/impressions split by brand vs non-brand."""
    client = db.query(Client).filter(Client.id == client_id).first()
    terms = brand_terms_for_client(client) if client else []
    today = date.today()
    start = today - timedelta(days=days - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    def _period(p_start: date, p_end: date) -> dict[str, float]:
        rows = (
            db.query(
                MetricDaily.dimension_value,
                MetricDaily.metric_name,
                func.sum(MetricDaily.value).label("total"),
            )
            .filter(
                and_(
                    MetricDaily.client_id == client_id,
                    MetricDaily.source == "gsc",
                    MetricDaily.dimension_type == "query",
                    MetricDaily.metric_name.in_(["clicks", "impressions"]),
                    MetricDaily.date >= p_start,
                    MetricDaily.date <= p_end,
                    MetricDaily.dimension_value.isnot(None),
                )
            )
            .group_by(MetricDaily.dimension_value, MetricDaily.metric_name)
            .all()
        )
        brand_clicks = brand_impr = non_clicks = non_impr = 0.0
        for r in rows:
            q = r.dimension_value or ""
            val = float(r.total or 0)
            branded = is_brand_query(q, terms) if terms else False
            if r.metric_name == "clicks":
                if branded:
                    brand_clicks += val
                else:
                    non_clicks += val
            elif r.metric_name == "impressions":
                if branded:
                    brand_impr += val
                else:
                    non_impr += val
        return {
            "brand_clicks": brand_clicks,
            "non_brand_clicks": non_clicks,
            "brand_impressions": brand_impr,
            "non_brand_impressions": non_impr,
        }

    cur = _period(start, today)
    prev = _period(prev_start, prev_end)

    def _pct(c: float, p: float) -> Optional[float]:
        if p is None or p <= 0:
            return None
        return round(((c - p) / p) * 100, 1)

    return {
        "days": days,
        "brand_terms": terms,
        "has_brand_terms": bool(terms),
        "current": {k: round(v, 1) for k, v in cur.items()},
        "previous": {k: round(v, 1) for k, v in prev.items()},
        "change_pct": {
            "brand_clicks": _pct(cur["brand_clicks"], prev["brand_clicks"]),
            "non_brand_clicks": _pct(cur["non_brand_clicks"], prev["non_brand_clicks"]),
            "brand_impressions": _pct(cur["brand_impressions"], prev["brand_impressions"]),
            "non_brand_impressions": _pct(
                cur["non_brand_impressions"], prev["non_brand_impressions"]
            ),
        },
    }
