"""
Resolve concrete page targets for fixes — URL + live title/meta/H1.

Used by action planner and insight enrichment so recommendations say
"change X on https://…" instead of "open GSC and rewrite title".
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Client, MetricDaily, PageSnapshot

QUOTED_RE = re.compile(r'"([^"]{2,120})"')
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)

_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "for",
        "to",
        "of",
        "in",
        "on",
        "at",
        "near",
        "best",
        "top",
        "how",
        "what",
        "with",
        "from",
        "your",
        "our",
        "is",
        "are",
    }
)


def extract_quoted_queries(text: str) -> list[str]:
    return [m.strip() for m in QUOTED_RE.findall(text or "") if m.strip()]


def extract_urls(text: str) -> list[str]:
    out: list[str] = []
    for m in URL_RE.findall(text or ""):
        cleaned = m.rstrip(".,;:)")
        if cleaned not in out:
            out.append(cleaned)
    return out


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]{3,}", (text or "").lower())
    return {w for w in words if w not in _STOP}


def _score_page_for_query(query: str, url: str, title: str, h1: str, meta: str) -> float:
    q_toks = _tokens(query)
    if not q_toks:
        return 0.0
    blob = f"{url} {title} {h1} {meta}".lower()
    hit = sum(1 for t in q_toks if t in blob)
    overlap = hit / len(q_toks)
    bonus = 0.0
    q_low = query.lower()
    if q_low and q_low in blob:
        bonus += 0.35
    path = urlparse(url).path.lower()
    for t in q_toks:
        if t in path:
            bonus += 0.08
    return overlap + bonus


def _homepage_for_client(client: Optional[Client]) -> Optional[str]:
    if not client:
        return None
    try:
        profile = json.loads(client.profile_json or "{}")
    except (json.JSONDecodeError, TypeError):
        profile = {}
    for key in ("website", "primary_domain", "domain"):
        raw = profile.get(key)
        if isinstance(raw, str) and raw.strip():
            host = raw.strip().removeprefix("https://").removeprefix("http://").split("/")[0]
            if host:
                return f"https://{host}/"
    domains = profile.get("domains") or profile.get("aliases") or []
    if isinstance(domains, str):
        domains = [d.strip() for d in domains.replace(",", " ").split() if d.strip()]
    if isinstance(domains, list) and domains:
        host = str(domains[0]).strip().removeprefix("https://").removeprefix("http://").split("/")[0]
        if host:
            return f"https://{host}/"
    return None


def top_gsc_pages(db: Session, client_id: int, *, days: int = 28, limit: int = 15) -> list[str]:
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


def gsc_page_for_query(db: Session, client_id: int, query: str, *, days: int = 30) -> Optional[str]:
    """Return the top-ranking page URL for a query from GSC query+page data."""
    if not query:
        return None
    today = date.today()
    start = today - timedelta(days=days)
    prefix = f"{query}|||"
    escaped_prefix = prefix.replace("%", r"\%").replace("_", r"\_")
    rows = (
        db.query(MetricDaily.dimension_value, func.sum(MetricDaily.value).label("clicks"))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source == "gsc",
                MetricDaily.dimension_type == "query_page",
                MetricDaily.metric_name == "clicks",
                MetricDaily.date >= start,
                MetricDaily.dimension_value.like(f"{escaped_prefix}%"),
            )
        )
        .group_by(MetricDaily.dimension_value)
        .order_by(func.sum(MetricDaily.value).desc())
        .limit(1)
        .all()
    )
    if rows and rows[0].dimension_value:
        parts = rows[0].dimension_value.split("|||", 1)
        if len(parts) == 2 and parts[1].startswith("http"):
            return parts[1]
    return None


def latest_snapshot(db: Session, client_id: int, url: str) -> Optional[PageSnapshot]:
    if not url:
        return None
    return (
        db.query(PageSnapshot)
        .filter(PageSnapshot.client_id == client_id, PageSnapshot.url == url)
        .order_by(PageSnapshot.fetched_at.desc())
        .first()
    )


def resolve_target_url(
    db: Session,
    client_id: int,
    *,
    query: Optional[str] = None,
    hint_urls: Optional[list[str]] = None,
) -> Optional[str]:
    """
    Pick the best page to edit for this fix.
    Prefer explicit hint URLs, then GSC query→page mapping, then crawl/snapshot keyword match, then top GSC pages.
    """
    for u in hint_urls or []:
        if u and u.startswith("http"):
            return u

    if query:
        gsc_page = gsc_page_for_query(db, client_id, query)
        if gsc_page:
            return gsc_page

    client = db.query(Client).filter(Client.id == client_id).first()
    snaps = (
        db.query(PageSnapshot)
        .filter(PageSnapshot.client_id == client_id)
        .order_by(PageSnapshot.fetched_at.desc())
        .limit(80)
        .all()
    )
    # Dedupe by URL keeping newest
    by_url: dict[str, PageSnapshot] = {}
    for s in snaps:
        if s.url and s.url not in by_url:
            by_url[s.url] = s

    if query and by_url:
        scored: list[tuple[float, str]] = []
        for url, snap in by_url.items():
            score = _score_page_for_query(
                query, url, snap.title or "", snap.h1 or "", snap.meta_description or ""
            )
            if score >= 0.35:
                scored.append((score, url))
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            return scored[0][1]

    pages = top_gsc_pages(db, client_id, limit=5)
    if pages:
        # Prefer http(s) absolute URLs
        for p in pages:
            if str(p).startswith("http"):
                return str(p)
        home = _homepage_for_client(client)
        if home and pages[0].startswith("/"):
            return home.rstrip("/") + pages[0]
        return pages[0]

    return _homepage_for_client(client)


def snapshot_state(snap: Optional[PageSnapshot]) -> dict[str, str]:
    if not snap:
        return {}
    return {
        "url": snap.url or "",
        "title": (snap.title or "").strip(),
        "meta": (snap.meta_description or "").strip(),
        "h1": (snap.h1 or "").strip(),
        "word_count": str(snap.word_count) if snap.word_count is not None else "",
    }


def propose_serp_copy(query: str, brand: str, state: dict[str, str]) -> dict[str, str]:
    """Deterministic draft title/meta that improves on the current page state."""
    q = (query or "").strip()
    brand_bit = (brand or "").strip() or "Local Experts"
    current_title = (state.get("title") or "").strip()
    current_meta = (state.get("meta") or "").strip()

    proposed_title = ""
    proposed_meta = ""

    if q:
        # Build a specific, benefit-driven title
        lead_q = q[0].upper() + q[1:] if q else ""
        # Try enhanced format first; fall back to basic if it doesn't fit
        if "near me" in q.lower():
            enhanced = f"{lead_q} | Expert Service & Free Estimates | {brand_bit}"
            basic = f"{lead_q} | {brand_bit}"
            proposed_title = enhanced if len(enhanced) <= 60 else (basic if len(basic) <= 60 else basic[:57].rstrip() + "...")
        else:
            proposed_title = f"{lead_q} | {brand_bit}"
            if len(proposed_title) > 60:
                # Trim query portion to preserve brand
                max_query_len = 60 - len(f" | {brand_bit}") - 3  # 3 for "..."
                if max_query_len > 0:
                    proposed_title = f"{lead_q[:max_query_len]}... | {brand_bit}"
                else:
                    proposed_title = proposed_title[:57].rstrip() + "..."
    else:
        proposed_title = current_title or f"Professional Services | {brand_bit}"

    if q:
        lead_q = q[0].upper() + q[1:]
        proposed_meta = (
            f"Looking for {lead_q.lower()}? {brand_bit} delivers proven results with "
            f"transparent pricing and local expertise. Get a free estimate today."
        )
    else:
        proposed_meta = current_meta or (
            f"Proven results with transparent pricing and local expertise. "
            f"Get a free estimate from {brand_bit} today."
        )

    if len(proposed_meta) > 155:
        proposed_meta = proposed_meta[:152].rstrip() + "..."

    # If current title is already good (has brand and keyword), keep it as-is
    # so we don't propose a worse replacement
    if current_title and len(current_title) <= 60 and brand_bit.lower() in current_title.lower():
        proposed_title = current_title

    return {"title": proposed_title, "meta": proposed_meta}


def collapse_by_page(candidates: list[dict]) -> list[dict]:
    """
    Collapse multiple candidates sharing the same target_url into one task.
    Primary query = highest priority_score (proxy for impr × CTR_gap).
    Returns a deduplicated list with combined titles/messages.
    """
    if not candidates:
        return []

    by_url: dict[str, list[dict]] = {}
    for c in candidates:
        url = (c.get("target_url") or "").strip()
        if not url:
            continue
        by_url.setdefault(url, []).append(c)

    collapsed: list[dict] = []
    for url, group in by_url.items():
        if len(group) == 1:
            collapsed.append(group[0])
            continue
        # Sort by priority_score descending; first = primary
        group.sort(key=lambda x: float(x.get("priority_score") or 0), reverse=True)
        primary = group[0]
        # Combine queries
        all_queries: list[str] = []
        for c in group:
            q = (c.get("target_query") or "").strip()
            if q and q not in all_queries:
                all_queries.append(q)
        if len(all_queries) > 1:
            primary = dict(primary)  # shallow copy
            primary["target_query"] = all_queries[0]
            primary["title"] = _collapsed_title(primary.get("playbook_pattern", ""), all_queries, url)
            # Merge evidence snippets
            evidences: list[str] = []
            for c in group:
                ev = (c.get("evidence") or "").strip()
                if ev and ev not in evidences:
                    evidences.append(ev)
            if evidences:
                primary["evidence"] = "; ".join(evidences)
            # Mention collapsed queries in why_it_matters
            if len(all_queries) > 1:
                extra = f" (collapsed: {len(all_queries)} queries sharing {url})"
                base = (primary.get("why_it_matters") or "").rstrip()
                if not base.endswith(extra):
                    primary["why_it_matters"] = base + extra
        collapsed.append(primary)

    return collapsed


def _collapsed_title(playbook_pattern: str, queries: list[str], url: str) -> str:
    """Generate a consolidated title for multiple queries on one URL."""
    labels = {
        "ctr_gap": "CTR",
        "ctr_opportunity": "CTR",
        "zero_click_alert": "CTR",
        "content_opportunity": "Content",
        "cro_opportunity": "CRO",
        "bounce_cro_alert": "CRO",
        "pagespeed_urgent": "Speed",
        "pagespeed_improve": "Speed",
        "local_onsite": "Local SEO",
    }
    label = labels.get(playbook_pattern, "Fix")
    if not queries:
        return f"{label} — {url}"
    if len(queries) == 1:
        return f"{label} — {queries[0]}"
    q0 = queries[0][:40]
    rest = len(queries) - 1
    return f"{label} — {q0}… (+{rest} more)"


def format_target_block(
    *,
    url: str,
    query: Optional[str] = None,
    state: Optional[dict[str, str]] = None,
    proposed: Optional[dict[str, str]] = None,
) -> list[str]:
    lines = ["=== FIX TARGET (edit this page — do not give generic advice) ==="]
    if query:
        lines.append(f"  query: \"{query}\"")
    lines.append(f"  target_url: {url}")
    state = state or {}
    if state.get("title"):
        lines.append(f"  current_title: {state['title']}")
    if state.get("meta"):
        lines.append(f"  current_meta: {state['meta']}")
    if state.get("h1"):
        lines.append(f"  current_h1: {state['h1']}")
    if state.get("word_count"):
        lines.append(f"  word_count: {state['word_count']}")
    proposed = proposed or {}
    if proposed.get("title"):
        lines.append(f"  proposed_title: {proposed['title']}")
    if proposed.get("meta"):
        lines.append(f"  proposed_meta: {proposed['meta']}")
    lines.append(
        "  REQUIREMENT: Every action step must name this target_url and the exact "
        "string to change (FROM → TO) or the exact new copy to publish."
    )
    lines.append("")
    return lines


def build_concrete_recommended_action(
    *,
    kind: str,
    query: Optional[str],
    url: str,
    state: dict[str, str],
    proposed: dict[str, str],
) -> str:
    """Replace generic insight playbooks with page-specific instructions."""
    title_now = state.get("title") or "(missing title)"
    meta_now = state.get("meta") or "(missing meta)"
    h1_now = state.get("h1") or "(missing H1)"
    new_title = proposed.get("title") or ""
    new_meta = proposed.get("meta") or ""
    q = query or "the target query"
    words = state.get("word_count") or "?"

    if kind in ("ctr_gap", "ctr_opportunity", "zero_click_alert"):
        return (
            f"On {url}:\n"
            f'1) Change <title> FROM "{title_now}" TO "{new_title}".\n'
            f'2) Change meta description FROM "{meta_now}" TO "{new_meta}".\n'
            f'3) Keep H1 aligned to "{q}" (current H1: "{h1_now}").\n'
            f"4) Deploy, request indexing for this URL, recheck CTR/clicks in 7–14 days."
        )
    if kind == "content_opportunity":
        return (
            f"On {url} (best matching page for \"{q}\"):\n"
            f'1) Update <title> to include "{q}" — proposed: "{new_title}".\n'
            f'2) Add or expand an H2 section titled around "{q}" (400–800 words of unique local content).\n'
            f'3) Add 2 internal links to {url} with descriptive anchors that include "{q}".\n'
            f"4) Deploy + request indexing; recheck position/clicks in 14 days."
        )
    if kind in ("cro_opportunity", "bounce_cro_alert"):
        return (
            f"On {url}:\n"
            f"1) Put one primary CTA above the fold (phone/form) — remove competing CTAs.\n"
            f'2) Align hero headline to the landing intent (current H1: "{h1_now}").\n'
            f"3) Add trust near CTA (reviews, guarantee, service area).\n"
            f"4) Watch GA4 key_events / bounce on this exact URL for 14 days."
        )
    if kind in ("pagespeed_urgent", "pagespeed_improve"):
        return (
            f"On {url}:\n"
            f"1) Run PageSpeed Insights (mobile) and note the LCP element.\n"
            f"2) Compress/resize hero images (WebP/AVIF); preload LCP; set width/height.\n"
            f"3) Defer non-critical JS; trim unused CSS.\n"
            f"4) Retest until mobile score ≥70; recheck clicks/CVR in 14 days."
        )
    if kind == "mobile_ctr_gap":
        return (
            f"On {url} (highest-priority page for mobile CTR):\n"
            f'1) Shorten <title> if truncated on mobile — current: "{title_now}".\n'
            f'2) Tighten meta for mobile SERP — current: "{meta_now}".\n'
            f"3) Fix tap targets, font size, sticky header covering content on the live page.\n"
            f"4) Recheck GSC mobile CTR for this URL in 14 days."
        )
    if kind == "decline_alert":
        return (
            f"On {url} (top dropped / priority URL):\n"
            f"1) Confirm HTTP 200 — no accidental noindex; canonical not pointing away.\n"
            f'2) Current title/H1: "{title_now}" / "{h1_now}" — restore if content was thinned.\n'
            f"3) GSC URL Inspection → request indexing if excluded.\n"
            f"4) Fix related 404s; resubmit sitemap; remeasure clicks in 7 days."
        )
    if kind in ("organic_leads_leak", "ads_spend_low_leads"):
        return (
            f"On {url}:\n"
            f"1) Submit the form — confirm HubSpot contact + thank-you/key_event fire.\n"
            f'2) One primary CTA above the fold (current H1: "{h1_now}").\n'
            f"3) Align offer copy with the ad/search promise that sends traffic here.\n"
            f"4) Remeasure CRM leads vs traffic on this URL in 7–14 days."
        )
    if kind == "crawl_missing_title":
        if new_title:
            proposed_t = new_title
        elif q != "the target query":
            proposed_t = f"{q.title()} | Local Pros"
        else:
            proposed_t = "Primary Keyword | Brand"
        return (
            f"On {url}:\n"
            f'1) Add <title> FROM "{title_now}" TO "{proposed_t}" (≤60 chars).\n'
            f"2) Deploy + request indexing.\n"
            f"3) Verify title in live source and SERP."
        )
    if kind == "crawl_missing_h1":
        return (
            f"On {url}:\n"
            f'1) Add one H1 FROM "{h1_now}" TO a clear intent headline (match primary keyword).\n'
            f"2) Ensure only one H1; do not use logo text as H1.\n"
            f"3) Deploy and recheck rankings for this URL."
        )
    if kind == "crawl_missing_meta":
        return (
            f"On {url}:\n"
            f'1) Add meta description FROM "{meta_now}" TO "{new_meta or "Benefit + CTA ≤155 chars"}".\n'
            f"2) Deploy; monitor CTR on this URL in GSC."
        )
    if kind == "crawl_thin_content":
        return (
            f"On {url} (currently ~{words} words):\n"
            f'1) Expand unique content to fully answer the page intent (current H1: "{h1_now}").\n'
            f"2) Add FAQ / supporting H2 sections — no fluff padding.\n"
            f"3) Deploy + request indexing; recheck rankings in 14 days."
        )
    if kind == "crawl_broken_pages":
        return (
            f"On {url}:\n"
            f"1) Restore content or 301 to the closest relevant live URL (not homepage dump).\n"
            f"2) Remove dead links from nav/sitemap pointing here.\n"
            f"3) Request indexing on the final live URL; re-crawl in 7 days."
        )
    if kind == "local_onsite":
        return (
            f"On {url} (primary service page):\n"
            f"1) Verify NAP (name, address, phone) matches GBP exactly.\n"
            f"2) Add city + service keyword to <title> and H1.\n"
            f'3) Embed service-area content on the page (cities served, coverage map, local landmarks).\n'
            f"4) Add schema LocalBusiness with correct service area."
        )
    return (
        f"On {url}: implement the fix for \"{q}\" using the current page state "
        f'(title="{title_now}", H1="{h1_now}"), then remeasure in 14 days.'
    )


# Insight types that benefit from URL + FROM→TO enrichment
_ENRICHABLE_KINDS = frozenset(
    {
        "ctr_gap",
        "ctr_opportunity",
        "zero_click_alert",
        "content_opportunity",
        "cro_opportunity",
        "bounce_cro_alert",
        "pagespeed_urgent",
        "pagespeed_improve",
        "mobile_ctr_gap",
        "decline_alert",
        "organic_leads_leak",
        "ads_spend_low_leads",
        "crawl_missing_title",
        "crawl_missing_h1",
        "crawl_missing_meta",
        "crawl_thin_content",
        "crawl_broken_pages",
        "local_onsite",
    }
)


def enrich_insight_item(db: Session, client_id: int, item: dict, *, brand: str = "") -> dict:
    """Attach a concrete recommended_action with URL + FROM→TO copy when possible."""
    if not isinstance(item, dict):
        return item
    kind = item.get("type") or ""
    msg = item.get("message") or ""
    action = item.get("recommended_action") or ""
    blob = f"{msg} {action}"
    queries = extract_quoted_queries(blob)
    hint_urls = extract_urls(blob)
    # Paths that look like pages in messages: "/services/..."
    path_match = re.search(r'(["\'])(/[a-zA-Z0-9_\-./]+)\1', blob)
    if path_match and not hint_urls:
        hint_urls = [path_match.group(2)]

    query = queries[0] if queries else None
    # For CRO/bounce messages the "quoted" bit is often the URL/path itself
    if kind in ("cro_opportunity", "bounce_cro_alert") and query and (
        query.startswith("/") or query.startswith("http")
    ):
        hint_urls = [query] + hint_urls
        query = None

    # Prefer first URL already named in the message (dropped pages, crawl lists, PageSpeed)
    url = resolve_target_url(db, client_id, query=query, hint_urls=hint_urls)
    if not url:
        return item

    # Absolute-ize path-only URLs
    if url.startswith("/"):
        client = db.query(Client).filter(Client.id == client_id).first()
        home = _homepage_for_client(client)
        if home:
            url = home.rstrip("/") + url

    snap = latest_snapshot(db, client_id, url)
    if not snap and url.startswith("http"):
        try:
            from app.connectors.page_content import fetch_page_snapshot

            snap = fetch_page_snapshot(db, client_id, url)
        except Exception:
            snap = None

    state = snapshot_state(snap)
    proposed = propose_serp_copy(query or "", brand, state) if query else {}
    # For crawl missing title without a query, still propose from URL slug / brand
    if kind in ("crawl_missing_title", "crawl_missing_meta") and not proposed:
        slug_q = urlparse(url).path.strip("/").replace("-", " ").replace("/", " ")
        proposed = propose_serp_copy(slug_q, brand, state)

    if kind in _ENRICHABLE_KINDS:
        already_concrete = bool(
            re.search(r"(?im)^(?:\d+[).]\s*)?on\s+https?://", action)
        ) or ("FROM" in action and "TO" in action)
        # Keep rule-generated per-URL crawl playbooks (don't collapse to one URL)
        if kind.startswith("crawl_") and (
            already_concrete
            or action.lower().count("on http") >= 1
        ):
            item = dict(item)
            if url and url not in (item.get("message") or ""):
                item["message"] = f"{item.get('message', '').rstrip()} Priority page: {url}"
            return item

        item = dict(item)
        item["recommended_action"] = build_concrete_recommended_action(
            kind=kind,
            query=query,
            url=url,
            state=state,
            proposed=proposed,
        )
        if url and url not in (item.get("message") or ""):
            item["message"] = f"{item.get('message', '').rstrip()} Target page: {url}"
    return item


def collect_fix_targets_for_plan(
    db: Session,
    client_id: int,
    *,
    queries: list[str],
    page_urls: list[str],
    brand: str,
    limit: int = 6,
) -> list[str]:
    """Prompt lines for the action planner with concrete pages + proposed copy."""
    lines: list[str] = []
    seen: set[str] = set()
    from app.connectors.page_content import fetch_page_snapshot

    targets: list[tuple[Optional[str], str]] = []
    for u in page_urls:
        if u and u.startswith("http") and u not in seen:
            seen.add(u)
            targets.append((None, u))
    for q in queries:
        if not q:
            continue
        url = resolve_target_url(db, client_id, query=q)
        if url and url not in seen:
            seen.add(url)
            targets.append((q, url))
        elif url:
            targets.append((q, url))

    for query, url in targets[:limit]:
        snap = latest_snapshot(db, client_id, url)
        if not snap and url.startswith("http"):
            try:
                snap = fetch_page_snapshot(db, client_id, url)
            except Exception:
                snap = None
        state = snapshot_state(snap)
        proposed = propose_serp_copy(query or "", brand, state) if query else {}
        lines.extend(
            format_target_block(url=url, query=query, state=state, proposed=proposed)
        )
    return lines
