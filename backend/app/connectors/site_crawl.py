"""
Sitewide technical SEO crawl MVP.

Seeds from client domain / GSC top pages, BFS same-host links via page snapshots,
capped for safety. Issues become insight dicts via rules._page_content_issues.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Optional
from urllib.parse import urlparse, urljoin

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.connectors.page_content import fetch_page_snapshot
from app.models import Client, MetricDaily, PageSnapshot
from app.url_safety import assert_safe_fetch_url

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 25


def _profile_domains(client: Client) -> list[str]:
    try:
        profile = json.loads(client.profile_json or "{}")
    except (json.JSONDecodeError, TypeError):
        profile = {}
    raw = profile.get("domains") or profile.get("aliases") or []
    if isinstance(raw, str):
        raw = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
    out: list[str] = []
    if isinstance(raw, list):
        for d in raw:
            if isinstance(d, str) and d.strip():
                host = d.strip().lower().removeprefix("https://").removeprefix("http://")
                host = host.split("/")[0]
                if host:
                    out.append(host)
    return out


def _seed_urls(db: Session, client_id: int, *, limit: int = 10) -> list[str]:
    """Seed crawl from GSC top pages + profile domains."""
    client = db.query(Client).filter(Client.id == client_id).first()
    seeds: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        u = (url or "").strip()
        if not u.startswith(("http://", "https://")):
            if u and "." in u:
                u = f"https://{u.rstrip('/')}/"
            else:
                return
        key = u.rstrip("/").lower()
        if key in seen:
            return
        if assert_safe_fetch_url(u):
            return
        seen.add(key)
        seeds.append(u)

    if client:
        for host in _profile_domains(client):
            add(f"https://{host}/")

    start = date.today() - timedelta(days=28)
    page_rows = (
        db.query(MetricDaily.dimension_value, func.sum(MetricDaily.value).label("clicks"))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.metric_name == "clicks",
                MetricDaily.dimension_type == "page",
                MetricDaily.date >= start,
            )
        )
        .group_by(MetricDaily.dimension_value)
        .order_by(func.sum(MetricDaily.value).desc())
        .limit(limit)
        .all()
    )
    for page, _ in page_rows:
        if page:
            add(str(page))

    return seeds[:limit]


def _same_host(seed_host: str, url: str) -> bool:
    host = urlparse(url).netloc.lower()
    seed = seed_host.lower()
    if host == seed:
        return True
    # www vs bare
    return host.removeprefix("www.") == seed.removeprefix("www.")


def crawl_site(
    db: Session,
    client_id: int,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    seed_url: Optional[str] = None,
) -> dict:
    """
    BFS crawl same-host pages. Returns {crawled, seeds, errors, urls}.
    """
    max_pages = max(1, min(100, int(max_pages or DEFAULT_MAX_PAGES)))
    seeds = [seed_url] if seed_url else _seed_urls(db, client_id)
    seeds = [s for s in seeds if s]
    if not seeds:
        return {"crawled": 0, "seeds": [], "errors": ["no_seed_urls"], "urls": []}

    seed_host = urlparse(seeds[0]).netloc
    queue: list[str] = list(seeds)
    visited: set[str] = set()
    crawled_urls: list[str] = []
    errors = 0

    while queue and len(crawled_urls) < max_pages:
        url = queue.pop(0)
        key = url.split("#")[0].rstrip("/").lower()
        if key in visited:
            continue
        visited.add(key)
        if not _same_host(seed_host, url):
            continue
        if assert_safe_fetch_url(url):
            continue

        snap = fetch_page_snapshot(db, client_id, url)
        if not snap:
            errors += 1
            continue
        crawled_urls.append(snap.url or url)

        try:
            links = json.loads(snap.internal_links_json or "[]")
        except (json.JSONDecodeError, TypeError):
            links = []
        for link in links:
            if not isinstance(link, dict):
                continue
            href = (link.get("href") or "").strip()
            if not href:
                continue
            abs_url = urljoin(url, href).split("#")[0]
            if not abs_url.startswith(("http://", "https://")):
                continue
            if not _same_host(seed_host, abs_url):
                continue
            nkey = abs_url.rstrip("/").lower()
            if nkey not in visited:
                queue.append(abs_url)

    logger.info(
        "Site crawl client %s: %s pages (%s errors) from %s seeds",
        client_id,
        len(crawled_urls),
        errors,
        len(seeds),
    )
    return {
        "crawled": len(crawled_urls),
        "seeds": seeds,
        "errors": errors,
        "urls": crawled_urls,
    }


def ensure_crawl_for_client(
    db: Session, client_id: int, *, max_pages: int = DEFAULT_MAX_PAGES
) -> dict:
    """Run crawl if client has few recent snapshots (lazy daily budget)."""
    from datetime import datetime, timedelta

    recent_cutoff = datetime.utcnow() - timedelta(days=30)
    cutoff_count = (
        db.query(PageSnapshot)
        .filter(
            PageSnapshot.client_id == client_id,
            PageSnapshot.fetched_at >= recent_cutoff,
        )
        .count()
    )
    # Always refresh a small crawl when under budget of recent snapshots
    if cutoff_count >= max_pages * 2:
        return {"crawled": 0, "skipped": True, "reason": "snapshot_budget"}
    return crawl_site(db, client_id, max_pages=max_pages)
