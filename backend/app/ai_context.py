"""
Shared rich context for AI prompts — top queries/pages, WoW deltas, client profile.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models import Client, MetricDaily, PageSnapshot, PageSpeedFinding
from app.dimensions import SITE_TOTAL_DIMENSION


def format_client_profile(client: Client) -> list[str]:
    """Agency memory lines for prompts."""
    from app.service_area import format_service_area_for_prompt
    from app.success_contract import format_contract_for_prompt

    lines: list[str] = []
    try:
        profile = json.loads(client.profile_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return lines
    if not isinstance(profile, dict) or not profile:
        # Still emit service-area block if somehow only nested elsewhere
        lines.extend(format_service_area_for_prompt(client))
        return lines
    lines.append("=== CLIENT PROFILE (agency memory) ===")
    for key in ("goals", "brand_voice", "do_not_touch", "notes", "competitors", "target_audience"):
        if profile.get(key):
            lines.append(f"  {key}: {profile[key]}")
    if profile.get("brand_terms"):
        lines.append(f"  brand_terms: {profile['brand_terms']}")
    lines.append("")
    lines.extend(format_service_area_for_prompt(client))
    lines.extend(format_contract_for_prompt(client))
    return lines


def _period_totals(
    db: Session,
    client_id: int,
    source: str,
    metric_names: list[str],
    start: date,
    end: date,
    *,
    dimension_type: Optional[str] = None,
) -> dict[str, float]:
    """Site-level totals (exclude dimensional rows when dimension_type is None)."""
    filters = [
        MetricDaily.client_id == client_id,
        MetricDaily.source == source,
        MetricDaily.metric_name.in_(metric_names),
        MetricDaily.date >= start,
        MetricDaily.date <= end,
    ]
    if dimension_type is None:
        # Prefer site-wide rows; fall back to any if none exist
        filters.append(
            or_(
                MetricDaily.dimension_type.is_(None),
                MetricDaily.dimension_value.is_(None),
                MetricDaily.dimension_type == "",
            )
        )
    else:
        filters.append(MetricDaily.dimension_type == dimension_type)

    rows = (
        db.query(MetricDaily.metric_name, func.sum(MetricDaily.value).label("total"))
        .filter(and_(*filters))
        .group_by(MetricDaily.metric_name)
        .all()
    )
    return {r.metric_name: float(r.total or 0) for r in rows}


def _avg_metrics(
    db: Session,
    client_id: int,
    source: str,
    metric_names: list[str],
    start: date,
    end: date,
) -> dict[str, float]:
    filters = [
        MetricDaily.client_id == client_id,
        MetricDaily.source == source,
        MetricDaily.metric_name.in_(metric_names),
        MetricDaily.date >= start,
        MetricDaily.date <= end,
        or_(
            MetricDaily.dimension_type.is_(None),
            MetricDaily.dimension_value.is_(None),
            MetricDaily.dimension_type == "",
        ),
    ]
    rows = (
        db.query(MetricDaily.metric_name, func.avg(MetricDaily.value).label("avg_val"))
        .filter(and_(*filters))
        .group_by(MetricDaily.metric_name)
        .all()
    )
    return {r.metric_name: float(r.avg_val or 0) for r in rows}


def format_metric_totals_with_wow(
    db: Session, client_id: int, *, days: int = 30
) -> list[str]:
    """30-day totals plus prior-period % change for core metrics."""
    today = date.today()
    cur_start = today - timedelta(days=days)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    sum_metrics = {
        "gsc": ["clicks", "impressions"],
        "ga4": ["sessions", "key_events"],
        "bing": ["clicks", "impressions"],
    }
    avg_metrics = {
        "gsc": ["ctr", "position"],
        "ga4": ["cvr", "bounce_rate"],
    }

    lines = [f"=== {days}-DAY METRICS (vs prior {days} days) ==="]
    for source, names in sum_metrics.items():
        # Prefer the same site-total dimension used by portfolio scoring
        preferred_dim = SITE_TOTAL_DIMENSION.get(source)
        cur = _period_totals(
            db, client_id, source, names, cur_start, today, dimension_type=preferred_dim
        )
        prev = _period_totals(
            db, client_id, source, names, prev_start, prev_end, dimension_type=preferred_dim
        )
        # Fallbacks if preferred dim empty
        if not cur:
            cur = _period_totals(db, client_id, source, names, cur_start, today)
            if not cur:
                cur = _period_totals(
                    db, client_id, source, names, cur_start, today, dimension_type="query"
                ) or _period_totals(
                    db, client_id, source, names, cur_start, today, dimension_type="page"
                )
            prev = _period_totals(db, client_id, source, names, prev_start, prev_end)
            if not prev:
                prev = _period_totals(
                    db, client_id, source, names, prev_start, prev_end, dimension_type="query"
                ) or _period_totals(
                    db, client_id, source, names, prev_start, prev_end, dimension_type="page"
                )
        for name in names:
            c = cur.get(name, 0)
            p = prev.get(name, 0)
            if c == 0 and p == 0:
                continue
            if p > 0:
                delta = ((c - p) / p) * 100
                lines.append(f"  {source}.{name}: {c:,.1f} ({delta:+.1f}% WoW/period)")
            else:
                lines.append(f"  {source}.{name}: {c:,.1f} (new)")

    for source, names in avg_metrics.items():
        cur = _avg_metrics(db, client_id, source, names, cur_start, today)
        prev = _avg_metrics(db, client_id, source, names, prev_start, prev_end)
        for name in names:
            c = cur.get(name, 0)
            p = prev.get(name, 0)
            if c == 0 and p == 0:
                continue
            if p > 0:
                delta = ((c - p) / p) * 100
                lines.append(f"  {source}.{name} (avg): {c:.4f} ({delta:+.1f}% vs prior)")
            else:
                lines.append(f"  {source}.{name} (avg): {c:.4f}")

    if len(lines) == 1:
        lines.append("  (no metric totals available)")
    lines.append("")
    return lines


def _top_dimensions(
    db: Session,
    client_id: int,
    *,
    source: str,
    dimension_type: str,
    metric_name: str,
    start: date,
    end: date,
    limit: int = 10,
) -> list[tuple[str, float]]:
    rows = (
        db.query(
            MetricDaily.dimension_value,
            func.sum(MetricDaily.value).label("total"),
        )
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == source,
                MetricDaily.dimension_type == dimension_type,
                MetricDaily.metric_name == metric_name,
                MetricDaily.date >= start,
                MetricDaily.date <= end,
                MetricDaily.dimension_value.isnot(None),
            )
        )
        .group_by(MetricDaily.dimension_value)
        .order_by(func.sum(MetricDaily.value).desc())
        .limit(limit)
        .all()
    )
    return [(r.dimension_value, float(r.total or 0)) for r in rows if r.dimension_value]


def _dim_metric_map(
    db: Session,
    client_id: int,
    *,
    source: str,
    dimension_type: str,
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
                MetricDaily.dimension_type == dimension_type,
                MetricDaily.metric_name.in_(metric_names),
                MetricDaily.date >= start,
                MetricDaily.date <= end,
                MetricDaily.dimension_value.isnot(None),
            )
        )
        .group_by(MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        out[r.dimension_value][r.metric_name] = float(r.total or 0)
    return out


def format_top_queries_and_pages(
    db: Session, client_id: int, *, days: int = 28, limit: int = 12
) -> list[str]:
    """Top GSC queries/pages with clicks, impressions, approx position."""
    from app.models import Client as ClientModel
    from app.service_area import (
        annotate_query_line,
        is_growth_eligible_query,
        parse_service_area,
    )

    today = date.today()
    start = today - timedelta(days=days)
    half = days // 2
    this_start = today - timedelta(days=half)
    prev_start = today - timedelta(days=days)
    prev_end = this_start - timedelta(days=1)

    client_row = db.query(ClientModel).filter(ClientModel.id == client_id).first()
    sa = parse_service_area(client_row)

    lines: list[str] = []

    q_this = _dim_metric_map(
        db, client_id,
        source="gsc", dimension_type="query",
        metric_names=["clicks", "impressions", "position", "ctr"],
        start=this_start, end=today,
    )
    q_prev = _dim_metric_map(
        db, client_id,
        source="gsc", dimension_type="query",
        metric_names=["impressions", "clicks"],
        start=prev_start, end=prev_end,
    )

    # Rank by clicks then impressions
    ranked = sorted(
        q_this.items(),
        key=lambda kv: (kv[1].get("clicks", 0), kv[1].get("impressions", 0)),
        reverse=True,
    )[:limit]

    if ranked:
        lines.append(f"=== TOP GSC QUERIES (last {half} days) ===")
        for query, m in ranked:
            prev_imp = q_prev.get(query, {}).get("impressions", 0)
            cur_imp = m.get("impressions", 0)
            growth = ""
            if prev_imp > 0:
                growth = f", impressions {((cur_imp - prev_imp) / prev_imp) * 100:+.0f}% vs prior"
            # position is stored as an average across days — use as-is
            pos_raw = m.get("position", 0)
            pos = pos_raw
            base = (
                f"  \"{query}\": clicks={m.get('clicks', 0):.0f}, "
                f"impressions={cur_imp:.0f}, ~pos={pos:.1f}{growth}"
            )
            annotated = annotate_query_line(query, sa, base)
            if annotated:
                lines.append(annotated)
        lines.append("")

    # Rising opportunity queries (impressions up sharply) — drop out-of-area
    rising: list[tuple[str, float, float, float]] = []
    for query, m in q_this.items():
        if not is_growth_eligible_query(query, sa):
            continue
        prev_imp = q_prev.get(query, {}).get("impressions", 0)
        cur_imp = m.get("impressions", 0)
        if prev_imp <= 0 or cur_imp < 20:
            continue
        growth = ((cur_imp - prev_imp) / prev_imp) * 100
        if growth < 25:
            continue
        pos_raw = m.get("position", 0)
        pos = pos_raw / max(1, half) if pos_raw > 100 else pos_raw
        rising.append((query, growth, cur_imp, pos))
    rising.sort(key=lambda x: x[1], reverse=True)
    if rising:
        lines.append("=== RISING QUERY OPPORTUNITIES (in-service-area only) ===")
        for query, growth, imp, pos in rising[:8]:
            base = (
                f"  \"{query}\": impressions {growth:+.0f}%, "
                f"imp={imp:.0f}, ~pos={pos:.1f}"
            )
            annotated = annotate_query_line(query, sa, base)
            if annotated:
                lines.append(annotated)
        lines.append("")

    pages = _top_dimensions(
        db, client_id,
        source="gsc", dimension_type="page", metric_name="clicks",
        start=start, end=today, limit=limit,
    )
    if pages:
        p_map = _dim_metric_map(
            db, client_id,
            source="gsc", dimension_type="page",
            metric_names=["clicks", "impressions", "ctr", "position"],
            start=start, end=today,
        )
        lines.append(f"=== TOP GSC PAGES (last {days} days by clicks) ===")
        for page, _ in pages:
            m = p_map.get(page, {})
            pos_raw = m.get("position", 0)
            pos = pos_raw
            lines.append(
                f"  {page}: clicks={m.get('clicks', 0):.0f}, "
                f"impressions={m.get('impressions', 0):.0f}, ~pos={pos:.1f}"
            )
        lines.append("")

    # Low-converting landing pages
    lp = _dim_metric_map(
        db, client_id,
        source="ga4", dimension_type="landing_page",
        metric_names=["sessions", "key_events"],
        start=start, end=today,
    )
    weak: list[tuple[str, float, float, float]] = []
    for page, m in lp.items():
        sessions = m.get("sessions", 0)
        events = m.get("key_events", 0)
        if sessions < 50:
            continue
        cvr = (events / sessions) if sessions else 0
        if cvr < 0.01:
            weak.append((page, sessions, events, cvr))
    weak.sort(key=lambda x: x[1], reverse=True)
    if weak:
        lines.append("=== HIGH-TRAFFIC LOW-CONVERTING LANDING PAGES ===")
        for page, sessions, events, cvr in weak[:8]:
            lines.append(
                f"  {page}: sessions={sessions:.0f}, key_events={events:.0f}, "
                f"cvr={cvr:.2%}"
            )
        lines.append("")

    return lines


def format_keyword_context(
    db: Session, client_id: int, keyword_hint: str, *, days: int = 28
) -> list[str]:
    """Pull GSC stats for a keyword (and close matches) for content briefs."""
    if not keyword_hint or not keyword_hint.strip():
        return []
    today = date.today()
    start = today - timedelta(days=days)
    hint = keyword_hint.strip().lower()

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
                MetricDaily.metric_name.in_(["clicks", "impressions", "position", "ctr"]),
                MetricDaily.date >= start,
                MetricDaily.date <= today,
                MetricDaily.dimension_value.isnot(None),
            )
        )
        .group_by(MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )
    by_q: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        by_q[r.dimension_value][r.metric_name] = float(r.total or 0)

    matches: list[tuple[str, dict[str, float], int]] = []
    for q, m in by_q.items():
        ql = q.lower()
        score = 0
        if ql == hint:
            score = 100
        elif hint in ql or ql in hint:
            score = 80
        else:
            hint_words = set(hint.split())
            q_words = set(ql.split())
            overlap = len(hint_words & q_words)
            if overlap >= max(1, len(hint_words) - 1):
                score = 40 + overlap * 10
        if score:
            matches.append((q, m, score))
    matches.sort(key=lambda x: (x[2], x[1].get("impressions", 0)), reverse=True)

    if not matches:
        return []

    lines = [f"=== GSC KEYWORD DATA (last {days} days) ==="]
    for q, m, _ in matches[:10]:
        pos_raw = m.get("position", 0)
        pos = pos_raw
        lines.append(
            f"  \"{q}\": clicks={m.get('clicks', 0):.0f}, "
            f"impressions={m.get('impressions', 0):.0f}, "
            f"~pos={pos:.1f}, ctr_sum={m.get('ctr', 0):.3f}"
        )
    lines.append("")
    return lines


def format_page_snapshot(snap: Optional[PageSnapshot], *, url: str = "") -> list[str]:
    """Render a PageSnapshot as prompt lines for AI planners/briefs."""
    if not snap:
        return []
    lines = ["=== CURRENT PAGE STATE ==="]
    lines.append(f"  url: {snap.url or url}")
    if snap.status_code:
        lines.append(f"  status_code: {snap.status_code}")
    if snap.title:
        lines.append(f"  title: {snap.title}")
    if snap.meta_description:
        lines.append(f"  meta_description: {snap.meta_description}")
    if snap.h1:
        lines.append(f"  h1: {snap.h1}")
    if snap.word_count is not None:
        lines.append(f"  word_count: {snap.word_count}")
        if snap.word_count < 40 and not (snap.h1 or "").strip():
            lines.append(
                "  warning: page looks like an empty/JS shell — "
                "static fetch cannot execute JavaScript; treat title/meta/H1 as unreliable"
            )
    if snap.canonical_url:
        lines.append(f"  canonical: {snap.canonical_url}")
    try:
        headings = json.loads(snap.headings_json or "[]")
    except (json.JSONDecodeError, TypeError):
        headings = []
    if headings:
        lines.append("  headings:")
        for h in headings[:15]:
            lines.append(f"    - {h}")
    try:
        schemas = json.loads(snap.schema_types or "[]")
    except (json.JSONDecodeError, TypeError):
        schemas = []
    if schemas:
        lines.append(f"  schema_types: {', '.join(str(s) for s in schemas[:10])}")
    try:
        links = json.loads(snap.internal_links_json or "[]")
    except (json.JSONDecodeError, TypeError):
        links = []
    if links:
        lines.append(f"  internal_links_sample ({min(8, len(links))} of {len(links)}):")
        for link in links[:8]:
            if isinstance(link, dict):
                lines.append(
                    f"    - \"{link.get('anchor_text', '')}\" → {link.get('href', '')}"
                )
    lines.append("")
    return lines


def ensure_page_snapshots_for_urls(
    db: Session, client_id: int, urls: list[str], *, limit: int = 5
) -> list[PageSnapshot]:
    """On-demand fetch for up to `limit` unique URLs; soft-fails per URL."""
    from app.connectors.page_content import fetch_page_snapshot

    seen: set[str] = set()
    snaps: list[PageSnapshot] = []
    for raw in urls:
        url = (raw or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        snap = fetch_page_snapshot(db, client_id, url)
        if snap:
            snaps.append(snap)
        if len(snaps) >= limit or len(seen) >= limit:
            break
    return snaps


def format_pagespeed_findings(
    db: Session, client_id: int, urls: list[str] | None = None, *, limit: int = 5
) -> list[str]:
    """Top Lighthouse opportunity findings for URLs (by savings_ms)."""
    urls = urls or []
    rows = []
    if urls:
        rows = (
            db.query(PageSpeedFinding)
            .filter(
                PageSpeedFinding.client_id == client_id,
                PageSpeedFinding.url.in_(urls[:10]),
            )
            .order_by(func.coalesce(PageSpeedFinding.savings_ms, 0).desc())
            .limit(limit * 2)
            .all()
        )
    if not rows:
        rows = (
            db.query(PageSpeedFinding)
            .filter(PageSpeedFinding.client_id == client_id)
            .order_by(
                PageSpeedFinding.fetched_at.desc(),
                func.coalesce(PageSpeedFinding.savings_ms, 0).desc(),
            )
            .limit(limit)
            .all()
        )
    if not rows:
        return []

    lines = ["=== PAGESPEED OPPORTUNITIES (from Lighthouse audits) ==="]
    for f in rows[:limit]:
        savings_bits = []
        if f.savings_ms:
            savings_bits.append(f"~{f.savings_ms:.0f}ms")
        if f.savings_bytes:
            kb = f.savings_bytes / 1024
            savings_bits.append(f"~{kb:.0f}KB" if kb < 1024 else f"~{kb/1024:.1f}MB")
        savings = ", ".join(savings_bits) if savings_bits else "impact unknown"
        try:
            offenders = json.loads(f.top_offenders_json or "[]")
        except (json.JSONDecodeError, TypeError):
            offenders = []
        offender_urls = []
        for o in offenders[:3]:
            if isinstance(o, dict) and o.get("url"):
                offender_urls.append(str(o["url"]))
            elif isinstance(o, str):
                offender_urls.append(o)
        offender_bit = f" — {', '.join(offender_urls)}" if offender_urls else ""
        lines.append(
            f"  [{f.strategy}] {f.title or f.audit_id} ({savings}){offender_bit}"
        )
    lines.append("")
    return lines


def build_client_ai_context(
    db: Session,
    client: Client,
    *,
    days: int = 30,
    include_dimensions: bool = True,
) -> str:
    """Full grounded context block for action plans / weekly briefs."""
    parts: list[str] = [
        f"Client: {client.name}",
        f"Industry: {client.industry or 'Unknown'}",
        "",
    ]
    parts.extend(format_client_profile(client))
    parts.extend(format_metric_totals_with_wow(db, client.id, days=days))
    if include_dimensions:
        parts.extend(format_top_queries_and_pages(db, client.id, days=min(days, 28)))
    return "\n".join(parts).rstrip() + "\n"
