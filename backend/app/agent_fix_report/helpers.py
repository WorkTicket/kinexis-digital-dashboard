"""Private helpers for building agent fix markdown reports."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.ai_context import format_page_snapshot
from app.models import Client, DataSource, MetricDaily, PageSpeedFinding

from .playbooks import (
    BOUNCE_RE,
    CTR_GAP_RE,
    CVR_RE,
    IMPR_RE,
    NUMERIC_PATH_RE,
    PATH_RE,
    PCT_RE,
    POS_RE,
    QUOTED_RE,
    SCORE_RE,
    URL_RE,
    _EXPECTED_CTR,
)

def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return s[:60] or "client"


def _parse_profile(client: Client) -> dict:
    try:
        profile = json.loads(client.profile_json or "{}")
        return profile if isinstance(profile, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _extract_targets(text: str, site_url: str = "") -> dict[str, list[str]]:
    blob = text or ""
    urls: list[str] = []
    for m in URL_RE.findall(blob):
        cleaned = m.rstrip(".,;:)")
        if cleaned not in urls:
            urls.append(cleaned)

    blob_no_urls = URL_RE.sub(" ", blob)
    paths: list[str] = []
    for m in PATH_RE.findall(blob_no_urls):
        if m.startswith("//") or NUMERIC_PATH_RE.match(m):
            continue
        first_seg = m.strip("/").split("/")[0]
        if "." in first_seg:
            continue
        if m not in paths and m not in ("/",):
            paths.append(m)

    queries: list[str] = []
    for m in QUOTED_RE.findall(blob):
        q = m.strip()
        if not q:
            continue
        if URL_RE.search(q):
            continue
        if q.startswith("/") and len(q) < 80:
            if (
                q not in paths
                and not NUMERIC_PATH_RE.match(q)
                and "." not in q.strip("/").split("/")[0]
            ):
                paths.append(q)
            continue
        if q not in queries:
            queries.append(q)

    absolute_from_paths: list[str] = []
    if site_url:
        base = site_url if site_url.endswith("/") else site_url + "/"
        for p in paths:
            abs_url = urljoin(base, p.lstrip("/"))
            if abs_url not in urls and abs_url not in absolute_from_paths:
                absolute_from_paths.append(abs_url)

    return {
        "urls": urls,
        "paths": paths,
        "queries": queries,
        "resolved_urls": absolute_from_paths,
    }


def _parse_finding_numbers(message: str) -> dict[str, float]:
    text = message or ""
    out: dict[str, float] = {}
    m = CTR_GAP_RE.search(text)
    if m:
        out["ctr_pct"] = float(m.group(1))
        out["expected_ctr_pct"] = float(m.group(2))
    m = IMPR_RE.search(text)
    if m:
        out["impressions"] = float(m.group(1).replace(",", ""))
    m = POS_RE.search(text)
    if m:
        out["position"] = float(m.group(1))
    m = SCORE_RE.search(text)
    if m:
        out["score_100"] = float(m.group(1))
    m = PCT_RE.search(text)
    if m:
        out["wow_pct"] = float(m.group(1))
    m = BOUNCE_RE.search(text)
    if m:
        out["bounce_pct"] = float(m.group(1))
    m = CVR_RE.search(text)
    if m:
        out["cvr_pct"] = float(m.group(1))
    return out


def _expected_ctr_for_position(pos: float) -> float:
    p = max(1, min(20, int(round(pos))))
    if p in _EXPECTED_CTR:
        return _EXPECTED_CTR[p]
    if p <= 20:
        return 0.01
    return 0.005


def _fmt_num(v: float, *, pct: bool = False) -> str:
    if pct:
        return f"{v:.2f}%"
    if abs(v) >= 100 or float(v).is_integer():
        return f"{v:,.0f}"
    return f"{v:,.2f}"


def _estimate_click_opportunity(
    insight_type: str,
    message: str,
    query_metrics: Optional[dict],
) -> Optional[dict[str, Any]]:
    """Estimate recoverable clicks from CTR gaps / rising queries."""
    parsed = _parse_finding_numbers(message)
    impr = None
    clicks = None
    ctr = None
    pos = parsed.get("position")
    expected = None

    if query_metrics:
        impr = query_metrics.get("impressions")
        clicks = query_metrics.get("clicks")
        ctr = query_metrics.get("ctr")
        if pos is None and query_metrics.get("position"):
            pos = query_metrics["position"]
            # position may be stored as sum — normalize if absurd
            if pos and pos > 100:
                pos = pos / 28.0

    if "impressions" in parsed:
        impr = parsed["impressions"]
    if "ctr_pct" in parsed:
        ctr = parsed["ctr_pct"] / 100.0
    if "expected_ctr_pct" in parsed:
        expected = parsed["expected_ctr_pct"] / 100.0

    if expected is None and pos is not None:
        expected = _expected_ctr_for_position(pos)

    if impr is None:
        return None

    if ctr is None and clicks is not None and impr > 0:
        ctr = clicks / impr
    if clicks is None and ctr is not None:
        clicks = impr * ctr
    if ctr is None:
        ctr = 0.0
    if clicks is None:
        clicks = 0.0

    result: dict[str, Any] = {
        "impressions": impr,
        "clicks": clicks,
        "ctr": ctr,
        "position": pos,
        "expected_ctr": expected,
    }

    if expected is not None and expected > ctr and impr > 0:
        gap = expected - ctr
        potential_extra = impr * gap
        result["ctr_gap"] = gap
        result["potential_extra_clicks_28d"] = potential_extra
        result["narrative"] = (
            f"At ~{_fmt_num(impr)} impressions with CTR {_fmt_num(ctr * 100, pct=True)} "
            f"vs expected ~{_fmt_num(expected * 100, pct=True)}, "
            f"closing the gap could unlock ~{_fmt_num(potential_extra)} additional clicks "
            f"over a similar ~28-day window."
        )
    elif insight_type == "content_opportunity" and impr > 0:
        # Conservative: +2 CTR points or +20% clicks if ranking improves
        lift = max(impr * 0.02, clicks * 0.2)
        result["potential_extra_clicks_28d"] = lift
        result["narrative"] = (
            f"Rising demand (~{_fmt_num(impr)} impr). Capturing intent + stronger SERP copy "
            f"could add on the order of ~{_fmt_num(lift)} clicks over a similar window "
            f"(illustrative; depends on position/CTR lift)."
        )
    elif insight_type in ("zero_click_alert",) and impr > 0:
        lift = impr * 0.015
        result["potential_extra_clicks_28d"] = lift
        result["narrative"] = (
            f"High visibility with near-zero clicks. Reaching even ~1.5% CTR would yield "
            f"~{_fmt_num(lift)} clicks on ~{_fmt_num(impr)} impressions."
        )
    else:
        return result if impr else None

    return result


def _connected_sources(db: Session, client_id: int) -> list[str]:
    rows = (
        db.query(DataSource.type, DataSource.status)
        .filter(DataSource.client_id == client_id)
        .all()
    )
    out = []
    for t, status in rows:
        label = f"{t} ({status})" if status else t
        if label not in out:
            out.append(label)
    return out


def _top_pages_for_query(db: Session, client_id: int, days: int = 28) -> list[dict]:
    today = date.today()
    start = today - timedelta(days=days)
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
                MetricDaily.metric_name.in_(["clicks", "impressions"]),
                MetricDaily.dimension_type == "page",
                MetricDaily.date >= start,
            )
        )
        .group_by(MetricDaily.dimension_value, MetricDaily.metric_name)
        .all()
    )
    by_page: dict[str, dict[str, float]] = {}
    for dim, metric, total in rows:
        if not dim:
            continue
        by_page.setdefault(dim, {"clicks": 0.0, "impressions": 0.0})
        by_page[dim][metric] = float(total or 0)
    ranked = sorted(by_page.items(), key=lambda kv: kv[1].get("clicks", 0), reverse=True)
    return [
        {"page": page, "clicks": vals["clicks"], "impressions": vals["impressions"]}
        for page, vals in ranked[:10]
    ]


def _query_metrics(db: Session, client_id: int, query: str, days: int = 28) -> Optional[dict]:
    today = date.today()
    start = today - timedelta(days=days)
    rows = (
        db.query(MetricDaily.metric_name, func.sum(MetricDaily.value), func.avg(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.dimension_type == "query",
                MetricDaily.dimension_value == query,
                MetricDaily.date >= start,
            )
        )
        .group_by(MetricDaily.metric_name)
        .all()
    )
    if not rows:
        return None
    out: dict[str, float] = {}
    for name, total, avg in rows:
        if name in ("clicks", "impressions"):
            out[name] = float(total or 0)
        elif name in ("ctr", "position"):
            out[name] = float(avg or 0)
    return out or None


def _page_metrics(db: Session, client_id: int, page: str, days: int = 28) -> Optional[dict]:
    today = date.today()
    start = today - timedelta(days=days)
    candidates = [page]
    if page.startswith("http"):
        parsed = urlparse(page)
        if parsed.path:
            candidates.append(parsed.path)
    rows = (
        db.query(MetricDaily.metric_name, func.sum(MetricDaily.value), func.avg(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source.in_(["gsc", "ga4", "pagespeed", "clarity"]),
                MetricDaily.dimension_value.in_(candidates),
                MetricDaily.date >= start,
            )
        )
        .group_by(MetricDaily.metric_name)
        .all()
    )
    if not rows:
        return None
    out: dict[str, float] = {}
    for name, total, avg in rows:
        if name in ("clicks", "impressions", "sessions", "key_events"):
            out[name] = float(total or 0)
        else:
            out[name] = float(avg or 0)
    return out or None


def _site_kpi_snapshot(db: Session, client_id: int, days: int = 28) -> dict[str, float]:
    today = date.today()
    start = today - timedelta(days=days)
    rows = (
        db.query(MetricDaily.source, MetricDaily.metric_name, func.sum(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.date >= start,
                MetricDaily.metric_name.in_(
                    ["clicks", "impressions", "sessions", "key_events", "leads", "revenue"]
                ),
            )
        )
        .group_by(MetricDaily.source, MetricDaily.metric_name)
        .all()
    )
    out: dict[str, float] = {}
    for source, name, total in rows:
        key = f"{source}.{name}"
        # Prefer device/query aggregates can double-count; keep max-ish by summing all — OK for direction
        out[key] = out.get(key, 0.0) + float(total or 0)
    return out


def _md_escape(text: str) -> str:
    return (text or "").replace("\r\n", "\n").strip()


def _bullet_list(items: list[str], empty: str = "_None identified._") -> str:
    cleaned = [i for i in items if i]
    if not cleaned:
        return empty
    return "\n".join(f"- {i}" for i in cleaned)


def _top_pagespeed_finding_lines(
    db: Session, client_id: int, urls: list[str], *, limit: int = 5
) -> list[str]:
    """Concrete Lighthouse opportunity lines for pagespeed playbooks."""
    from sqlalchemy import func

    q = db.query(PageSpeedFinding).filter(PageSpeedFinding.client_id == client_id)
    if urls:
        q = q.filter(PageSpeedFinding.url.in_(urls[:10]))
    rows = (
        q.order_by(func.coalesce(PageSpeedFinding.savings_ms, 0).desc())
        .limit(limit)
        .all()
    )
    if not rows and urls:
        rows = (
            db.query(PageSpeedFinding)
            .filter(PageSpeedFinding.client_id == client_id)
            .order_by(func.coalesce(PageSpeedFinding.savings_ms, 0).desc())
            .limit(limit)
            .all()
        )
    lines: list[str] = []
    for f in rows:
        savings_bits = []
        if f.savings_ms:
            savings_bits.append(f"~{f.savings_ms:.0f}ms")
        if f.savings_bytes:
            kb = f.savings_bytes / 1024.0
            savings_bits.append(f"~{kb:.0f}KB" if kb < 1024 else f"~{kb / 1024:.1f}MB")
        savings = " / ".join(savings_bits) if savings_bits else "see PSI"
        try:
            offenders = json.loads(f.top_offenders_json or "[]")
        except (json.JSONDecodeError, TypeError):
            offenders = []
        offender_urls = []
        for o in offenders[:2]:
            if isinstance(o, dict) and o.get("url"):
                offender_urls.append(str(o["url"]))
        offender_bit = f": `{offender_urls[0]}`" if offender_urls else ""
        lines.append(
            f"{f.title or f.audit_id} ({savings}){offender_bit}"
        )
    return lines


def _rewrite_copy_from_page(
    *,
    query: str,
    brand: str,
    templates: list[str],
    snap,
) -> Optional[list[str]]:
    """LLM-finished title/meta/H1 suggestions grounded in live page + query."""
    try:
        from app.ai_client import ai_configured, complete, parse_json_payload
    except Exception:
        return None
    if not ai_configured() or not snap:
        return None
    page_block = "\n".join(format_page_snapshot(snap))
    system = (
        "You rewrite SEO title/meta/H1 copy for a live page. "
        "Output JSON: {\"suggestions\": [\"...\", ...]} — 3 to 6 finished lines "
        "(title, meta description, H1). No placeholders like {Query} or {Brand}. "
        "Ground suggestions in the current page state and target query."
    )
    user = (
        f"Target query: {query}\nBrand: {brand}\n\n"
        f"{page_block}\n"
        f"Template hints (rewrite into finished copy):\n"
        + "\n".join(f"- {t}" for t in templates)
    )
    try:
        raw = complete(
            system=system,
            user=user,
            max_tokens=1024,
            json_mode=True,
            temperature=0.3,
            purpose="copy_rewrite",
        )
        if not raw:
            return None
        data = parse_json_payload(raw, expect=dict)
        if isinstance(data, dict):
            suggestions = data.get("suggestions") or data.get("copy") or []
        elif isinstance(data, list):
            suggestions = data
        else:
            return None
        out = [str(s).strip() for s in suggestions if str(s).strip()]
        return out[:8] if out else None
    except Exception:
        return None


