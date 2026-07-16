"""
Fetch and parse live page HTML for AI prompts.

Primary path: static fetch (httpx + selectolax) — fast, works for SSR/WordPress.
Playwright JS-render fallback: activated when PAGE_CONTENT_RENDER_JS=true and the
static fetch yields an empty shell (SPA without SSR).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser
from sqlalchemy.orm import Session

import app.config as cfg
from app.models import PageSnapshot
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Heuristic: SPA shell / blocked bot / nearly empty document
_EMPTY_SHELL_WORD_THRESHOLD = 40


def _render_with_playwright(url: str, timeout_ms: int = 15000) -> str | None:
    """Render a page with headless Chromium via Playwright.

    Used as a fallback when static fetch yields an empty shell.
    Returns the rendered HTML string or None on failure.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed — cannot render JS pages")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                html = page.content()
                return html
            finally:
                browser.close()
    except Exception as e:
        logger.warning("Playwright render failed for %s: %s", url, e)
        return None


def looks_like_empty_shell(fields: dict[str, Any]) -> bool:
    """True when extracted fields look like a JS shell or empty page."""
    word_count = int(fields.get("word_count") or 0)
    title = (fields.get("title") or "").strip()
    h1 = (fields.get("h1") or "").strip()
    if word_count < _EMPTY_SHELL_WORD_THRESHOLD and not h1:
        return True
    if word_count == 0 and not title:
        return True
    return False


def extract_page_fields(html: str, base_url: str = "") -> dict[str, Any]:
    """Pure HTML extraction — used by fetch and unit tests."""
    tree = HTMLParser(html or "")

    title_node = tree.css_first("title")
    title = (title_node.text(strip=True) if title_node else "") or ""

    meta = tree.css_first('meta[name="description"]')
    meta_desc = ""
    if meta and meta.attributes:
        meta_desc = (meta.attributes.get("content") or "").strip()

    h1_node = tree.css_first("h1")
    h1 = h1_node.text(strip=True) if h1_node else ""

    headings: list[str] = []
    for n in tree.css("h2, h3"):
        text = n.text(strip=True)
        if text:
            headings.append(f"{n.tag.upper()}: {text}")
        if len(headings) >= 30:
            break

    body = tree.css_first("body")
    body_text = body.text(separator=" ", strip=True) if body else ""
    word_count = len([w for w in body_text.split() if w])

    schema_types: list[str] = []
    for node in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(node.text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        _collect_schema_types(data, schema_types)

    links: list[dict[str, str]] = []
    base_host = urlparse(base_url).netloc.lower() if base_url else ""
    for a in tree.css("a[href]"):
        href = (a.attributes or {}).get("href") or ""
        anchor = a.text(strip=True)
        if not href or not anchor:
            continue
        abs_href = urljoin(base_url, href) if base_url else href
        # Prefer same-host / relative as "internal"
        host = urlparse(abs_href).netloc.lower()
        if base_host and host and host != base_host:
            continue
        links.append({"href": abs_href, "anchor_text": anchor[:120]})
        if len(links) >= 40:
            break

    canonical = tree.css_first('link[rel="canonical"]')
    canonical_url = ""
    if canonical and canonical.attributes:
        canonical_url = (canonical.attributes.get("href") or "").strip()

    content_hash = hashlib.sha256(body_text.encode("utf-8", errors="ignore")).hexdigest()

    return {
        "title": title[:500],
        "meta_description": meta_desc[:500],
        "h1": h1[:500],
        "headings": headings,
        "word_count": word_count,
        "schema_types": list(dict.fromkeys(schema_types))[:20],
        "internal_links": links,
        "canonical_url": canonical_url[:1000] if canonical_url else "",
        "content_hash": content_hash,
        "body_text_preview": body_text[:500],
    }


def _collect_schema_types(data: Any, out: list[str]) -> None:
    if isinstance(data, list):
        for item in data:
            _collect_schema_types(item, out)
        return
    if not isinstance(data, dict):
        return
    t = data.get("@type")
    if isinstance(t, str) and t:
        out.append(t)
    elif isinstance(t, list):
        for item in t:
            if isinstance(item, str) and item:
                out.append(item)
    graph = data.get("@graph")
    if graph is not None:
        _collect_schema_types(graph, out)


def extract_urls_from_text(text: str) -> list[str]:
    found: list[str] = []
    for m in URL_RE.findall(text or ""):
        cleaned = m.rstrip(".,;:)")
        if cleaned not in found:
            found.append(cleaned)
    return found


def get_cached_snapshot(
    db: Session, client_id: int, url: str, *, max_age_hours: Optional[int] = None
) -> Optional[PageSnapshot]:
    hours = max_age_hours if max_age_hours is not None else cfg.PAGE_CONTENT_CACHE_HOURS
    cutoff = utcnow() - timedelta(hours=max(1, hours))
    return (
        db.query(PageSnapshot)
        .filter(
            PageSnapshot.client_id == client_id,
            PageSnapshot.url == url,
            PageSnapshot.fetched_at >= cutoff,
        )
        .order_by(PageSnapshot.fetched_at.desc())
        .first()
    )


def fetch_page_snapshot(
    db: Session,
    client_id: int,
    url: str,
    *,
    force_refresh: bool = False,
) -> Optional[PageSnapshot]:
    """Fetch+parse a URL, or return a recent cached snapshot. Soft-fails to None.

    Cache is TTL-based (PAGE_CONTENT_CACHE_HOURS). Pass force_refresh=True to
    bypass cache after a content deploy so briefs aren't grounded in stale copy.
    content_hash is stored for change detection / future invalidation.
    """
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return None

    from app.url_safety import assert_safe_fetch_url

    unsafe = assert_safe_fetch_url(url)
    if unsafe:
        logger.warning("Blocked unsafe page fetch (%s): %s", unsafe, url)
        return None

    if not force_refresh:
        cached = get_cached_snapshot(db, client_id, url)
        if cached:
            return cached

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=10.0,
            max_redirects=3,
            headers={"User-Agent": cfg.PAGE_CONTENT_USER_AGENT},
        ) as client:
            resp = client.get(url)
            # Re-check final URL after redirects
            final_err = assert_safe_fetch_url(str(resp.url))
            if final_err:
                logger.warning("Blocked redirected page fetch (%s): %s", final_err, resp.url)
                return None
    except Exception as e:
        logger.warning("Page fetch failed for %s: %s", url, e)
        return None

    try:
        fields = extract_page_fields(resp.text, base_url=str(resp.url))
    except Exception as e:
        logger.warning("Page parse failed for %s: %s", url, e)
        return None

    if looks_like_empty_shell(fields):
        logger.warning(
            "Page snapshot for %s looks like an empty/JS shell "
            "(word_count=%s, title=%r, h1=%r). Static fetch cannot execute JS — "
            "SSR/WordPress sites are supported; SPAs need a render fallback.",
            url,
            fields.get("word_count"),
            fields.get("title"),
            fields.get("h1"),
        )
        if getattr(cfg, "PAGE_CONTENT_RENDER_JS", False):
            logger.info(
                "PAGE_CONTENT_RENDER_JS enabled — retrying %s with Playwright",
                url,
            )
            js_html = _render_with_playwright(url)
            if js_html:
                try:
                    fields = extract_page_fields(js_html, base_url=str(resp.url))
                    logger.info(
                        "Playwright fallback succeeded for %s (word_count=%s, h1=%r)",
                        url,
                        fields.get("word_count"),
                        fields.get("h1"),
                    )
                except Exception as e:
                    logger.warning("Page parse failed after Playwright render for %s: %s", url, e)
            else:
                logger.warning("Playwright fallback returned empty content for %s", url)

    snap = PageSnapshot(
        client_id=client_id,
        url=url[:1000],
        title=fields["title"] or None,
        meta_description=fields["meta_description"] or None,
        h1=fields["h1"] or None,
        headings_json=json.dumps(fields["headings"]),
        word_count=fields["word_count"],
        schema_types=json.dumps(fields["schema_types"]),
        internal_links_json=json.dumps(fields["internal_links"]),
        canonical_url=fields["canonical_url"] or None,
        status_code=resp.status_code,
        content_hash=fields["content_hash"],
        fetched_at=utcnow(),
    )
    try:
        db.add(snap)
        db.commit()
        db.refresh(snap)
        return snap
    except Exception as e:
        db.rollback()
        logger.warning("Failed to persist page snapshot for %s: %s", url, e)
        return None
