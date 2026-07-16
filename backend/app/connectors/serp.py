"""
SERP snapshot connector — licensed API only (SerpApi / DataForSEO / Google CSE).

Disabled when SERP_PROVIDER is empty. Only fetch for queries already flagged by
insight rules to control cost.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

import app.config as cfg
from app.models import Insight, SerpSnapshot
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

_QUOTED_QUERY_RE = re.compile(r'["\u201c\u201d]([^"\u201c\u201d]{2,80})["\u201c\u201d]')


def serp_enabled() -> bool:
    provider = (getattr(cfg, "SERP_PROVIDER", "") or "").strip().lower()
    key = (getattr(cfg, "SERP_API_KEY", "") or "").strip()
    return bool(provider and key)


def _cache_hours() -> int:
    return int(getattr(cfg, "SERP_CACHE_HOURS", 72) or 72)


def get_cached_serp(
    db: Session, client_id: int, query: str
) -> Optional[SerpSnapshot]:
    cutoff = utcnow() - timedelta(hours=_cache_hours())
    return (
        db.query(SerpSnapshot)
        .filter(
            SerpSnapshot.client_id == client_id,
            SerpSnapshot.query == query,
            SerpSnapshot.fetched_at >= cutoff,
        )
        .order_by(SerpSnapshot.fetched_at.desc())
        .first()
    )


def _fetch_serpapi(query: str) -> list[dict[str, Any]]:
    key = cfg.SERP_API_KEY
    with httpx.Client(timeout=30.0) as client:
        res = client.get(
            "https://serpapi.com/search.json",
            params={"q": query, "engine": "google", "api_key": key, "num": 10},
        )
        res.raise_for_status()
        data = res.json()
    organic = data.get("organic_results") or []
    out = []
    for row in organic[:10]:
        out.append(
            {
                "position": row.get("position"),
                "url": row.get("link") or row.get("url") or "",
                "title": row.get("title") or "",
                "snippet": row.get("snippet") or "",
            }
        )
    return out


def _fetch_google_cse(query: str) -> list[dict[str, Any]]:
    """Google Custom Search JSON API — organic only, cheaper, limited rank guarantees."""
    key = cfg.SERP_API_KEY
    cx = (getattr(cfg, "SERP_GOOGLE_CSE_ID", "") or "").strip()
    if not cx:
        raise ValueError("SERP_GOOGLE_CSE_ID required for google_cse provider")
    with httpx.Client(timeout=30.0) as client:
        res = client.get(
            "https://www.googleapis.com/customsearch/v1",
            params={"q": query, "key": key, "cx": cx, "num": 10},
        )
        res.raise_for_status()
        data = res.json()
    items = data.get("items") or []
    out = []
    for i, row in enumerate(items[:10], start=1):
        out.append(
            {
                "position": i,
                "url": row.get("link") or "",
                "title": row.get("title") or "",
                "snippet": row.get("snippet") or "",
            }
        )
    return out


def _fetch_dataforseo(query: str) -> list[dict[str, Any]]:
    """DataForSEO live organic — expects SERP_API_KEY as 'login:password' base64-ready pair."""
    raw = cfg.SERP_API_KEY
    colon = raw.find(":")
    if colon <= 0 or colon >= len(raw) - 1:
        raise ValueError("DataForSEO SERP_API_KEY must be 'login:password'")
    login = raw[:colon]
    password = raw[colon + 1:]
    payload = [
        {
            "keyword": query,
            "location_code": 2840,
            "language_code": "en",
            "depth": 10,
        }
    ]
    with httpx.Client(timeout=60.0) as client:
        res = client.post(
            "https://api.dataforseo.com/v3/serp/google/organic/live/regular",
            auth=(login, password),
            json=payload,
        )
        res.raise_for_status()
        data = res.json()
    tasks = data.get("tasks") or []
    items = []
    if tasks and isinstance(tasks[0], dict):
        result = (tasks[0].get("result") or [{}])[0]
        items = result.get("items") or []
    out = []
    for row in items[:10]:
        if (row.get("type") or "") != "organic":
            continue
        out.append(
            {
                "position": row.get("rank_absolute") or row.get("rank_group"),
                "url": row.get("url") or "",
                "title": row.get("title") or "",
                "snippet": row.get("description") or "",
            }
        )
    return out


def fetch_serp_results(query: str) -> list[dict[str, Any]]:
    provider = (cfg.SERP_PROVIDER or "").strip().lower()
    if provider == "serpapi":
        return _fetch_serpapi(query)
    if provider in ("google_cse", "cse"):
        return _fetch_google_cse(query)
    if provider == "dataforseo":
        return _fetch_dataforseo(query)
    raise ValueError(f"Unknown SERP_PROVIDER: {provider}")


def fetch_serp_snapshot(
    db: Session, client_id: int, query: str
) -> Optional[SerpSnapshot]:
    query = (query or "").strip()
    if not query or not serp_enabled():
        return None
    cached = get_cached_serp(db, client_id, query)
    if cached:
        return cached
    try:
        results = fetch_serp_results(query)
    except Exception as e:
        logger.warning("SERP fetch failed for %r: %s", query[:80], e)
        return None
    snap = SerpSnapshot(
        client_id=client_id,
        query=query[:500],
        results_json=json.dumps(results),
        provider=(cfg.SERP_PROVIDER or "").strip().lower(),
        fetched_at=utcnow(),
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def flagged_queries_for_client(db: Session, client_id: int, *, limit: int = 10) -> list[str]:
    """Queries from open SEO insights + declining GSC queries + tracked keywords."""
    types = (
        "content_opportunity",
        "ctr_opportunity",
        "ctr_gap",
        "zero_click_alert",
        "decline_alert",
        "mobile_desktop_gap",
    )
    rows = (
        db.query(Insight)
        .filter(
            Insight.client_id == client_id,
            Insight.resolved == False,  # noqa: E712
            Insight.type.in_(types),
        )
        .order_by(Insight.priority_score.desc())
        .limit(limit * 3)
        .all()
    )
    queries: list[str] = []
    seen: set[str] = set()

    def _add(q: str) -> bool:
        q_clean = (q or "").strip()
        if not q_clean:
            return False
        key = q_clean.lower()
        if key in seen:
            return False
        seen.add(key)
        queries.append(q_clean)
        return len(queries) >= limit

    for ins in rows:
        text = f"{ins.message or ''} {ins.recommended_action or ''}"
        for m in _QUOTED_QUERY_RE.findall(text):
            if _add(m):
                return queries

    # Declining / losing queries from GSC (WoW click drop) — feeds decline_alert SERP
    for q in _declining_gsc_queries(db, client_id, limit=limit):
        if _add(q):
            return queries

    # Tracked keyword watchlist
    try:
        from app.models import TrackedKeyword

        tracked = (
            db.query(TrackedKeyword)
            .filter(TrackedKeyword.client_id == client_id)
            .order_by(TrackedKeyword.created_at.desc())
            .limit(limit)
            .all()
        )
        for t in tracked:
            if _add(t.keyword):
                return queries
    except Exception:
        pass

    return queries[:limit]


def _declining_gsc_queries(db: Session, client_id: int, *, limit: int = 5) -> list[str]:
    """Top queries by prior-week clicks that lost clicks WoW."""
    from datetime import date, timedelta
    from sqlalchemy import and_, func

    from app.models import MetricDaily

    today = date.today()
    this_start = today - timedelta(days=7)
    prev_start = today - timedelta(days=14)

    this_rows = (
        db.query(
            MetricDaily.dimension_value,
            func.sum(MetricDaily.value).label("clicks"),
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name == "clicks",
                MetricDaily.dimension_type == "query",
                MetricDaily.date >= this_start,
            )
        )
        .group_by(MetricDaily.dimension_value)
        .all()
    )
    this_map = {r[0]: float(r[1] or 0) for r in this_rows if r[0]}

    prev_rows = (
        db.query(
            MetricDaily.dimension_value,
            func.sum(MetricDaily.value).label("clicks"),
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name == "clicks",
                MetricDaily.dimension_type == "query",
                MetricDaily.date >= prev_start,
                MetricDaily.date < this_start,
            )
        )
        .group_by(MetricDaily.dimension_value)
        .all()
    )

    dropped: list[tuple[float, str]] = []
    for query, prev_clicks in prev_rows:
        if not query or prev_clicks < 5:
            continue
        cur = this_map.get(query, 0.0)
        if cur < prev_clicks * 0.7:
            dropped.append((prev_clicks - cur, str(query)))
    dropped.sort(key=lambda x: x[0], reverse=True)
    return [q for _, q in dropped[:limit]]


def ensure_serp_for_flagged_queries(
    db: Session, client_id: int, *, limit: Optional[int] = None
) -> list[SerpSnapshot]:
    if not serp_enabled():
        return []
    max_q = limit or int(getattr(cfg, "SERP_MAX_QUERIES_PER_SYNC", 10) or 10)
    snaps: list[SerpSnapshot] = []
    for q in flagged_queries_for_client(db, client_id, limit=max_q):
        snap = fetch_serp_snapshot(db, client_id, q)
        if snap:
            snaps.append(snap)
    return snaps


def format_serp_snapshot(
    snap: Optional[SerpSnapshot],
    *,
    competitor_domains: Optional[list[str]] = None,
    client_domains: Optional[list[str]] = None,
) -> list[str]:
    if not snap:
        return []
    try:
        results = json.loads(snap.results_json or "[]")
    except (json.JSONDecodeError, TypeError):
        results = []
    if not results:
        return []
    comps = [d.lower().removeprefix("www.") for d in (competitor_domains or []) if d]
    owns = [d.lower().removeprefix("www.") for d in (client_domains or []) if d]
    lines = [f"=== LIVE SERP (top results for \"{snap.query}\") ==="]
    for row in results[:10]:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "")
        host = ""
        try:
            from urllib.parse import urlparse

            host = urlparse(url).netloc.lower().removeprefix("www.")
        except Exception:
            pass
        tag = ""
        if host and any(host == d or host.endswith("." + d) for d in owns):
            tag = " [CLIENT]"
        elif host and any(host == d or host.endswith("." + d) for d in comps):
            tag = " [COMPETITOR]"
        lines.append(
            f"#{row.get('position')}: {row.get('title') or '—'} — {url}{tag}"
        )
        if row.get("snippet"):
            lines.append(f"   snippet: {str(row['snippet'])[:160]}")
    return lines


def serp_snapshot_payload(snap: SerpSnapshot) -> dict[str, Any]:
    try:
        results = json.loads(snap.results_json or "[]")
    except (json.JSONDecodeError, TypeError):
        results = []
    return {
        "id": snap.id,
        "query": snap.query,
        "provider": snap.provider,
        "fetched_at": snap.fetched_at.isoformat() if snap.fetched_at else None,
        "results": results if isinstance(results, list) else [],
    }