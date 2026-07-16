"""New insight rules for backlinks, GBP, and CrUX — the 3 missing SEO pillars.

These rules run after each daily sync alongside the existing 14 rules.
"""

import logging
from datetime import date, timedelta

from sqlalchemy import func, and_

logger = logging.getLogger(__name__)


# ── Backlink Rules ─────────────────────────────────────────────────────

def backlink_drop_alert(client_id: int, db, thr=None) -> list[dict]:
    """Lost referring domains or toxic link spike — diagnostic for ranking drops."""
    from app.models import BacklinkSnapshot

    today = date.today()
    cutoff = today - timedelta(days=30)

    latest = (
        db.query(BacklinkSnapshot)
        .filter(
            BacklinkSnapshot.client_id == client_id,
            BacklinkSnapshot.fetched_at >= cutoff,
        )
        .order_by(BacklinkSnapshot.fetched_at.desc())
        .first()
    )
    if not latest:
        return []

    prev = (
        db.query(BacklinkSnapshot)
        .filter(
            BacklinkSnapshot.client_id == client_id,
            BacklinkSnapshot.fetched_at < cutoff,
        )
        .order_by(BacklinkSnapshot.fetched_at.desc())
        .first()
    )

    insights = []

    # Lost links alert
    if latest.lost_links_30d and latest.lost_links_30d >= 5:
        insights.append({
            "type": "backlink_drop",
            "kind": "problem",
            "message": (
                f"Lost {latest.lost_links_30d} referring domains in the last 30 days. "
                f"Domain rating: {latest.domain_rating or 'N/A'}. "
                f"Backlink erosion may explain ranking declines — prioritize link reclamation."
            ),
            "recommended_action": (
                "1) Export lost backlinks from Ahrefs/SEMrush — identify top-value lost domains.\n"
                "2) Reach out to high-DR lost domains for reclamation (updated content, broken link fix).\n"
                "3) Build 3-5 new relevant backlinks to offset the loss.\n"
                "4) Monitor referring domains count in 30 days."
            ),
            "severity": "high" if latest.lost_links_30d >= 15 else "medium",
            "impact_weight": min(100.0, latest.lost_links_30d * 5 + 20),
            "metrics_to_watch": ["gsc.clicks", "gsc.impressions"],
        })

    # Toxic link alert
    if latest.toxic_score and latest.toxic_score >= 50:
        insights.append({
            "type": "toxic_backlinks",
            "kind": "problem",
            "message": (
                f"Backlink profile shows high toxicity score ({latest.toxic_score}/100). "
                f"Toxic backlinks may trigger Google penalties or suppress rankings."
            ),
            "recommended_action": (
                "1) Identify toxic domains in backlink audit tool.\n"
                "2) Disavow at the domain level in Google Search Console.\n"
                "3) Focus link-building efforts on high-quality, relevant domains.\n"
                "4) Recheck toxicity score and rankings in 30 days."
            ),
            "severity": "high" if latest.toxic_score >= 70 else "medium",
            "impact_weight": min(100.0, latest.toxic_score),
            "metrics_to_watch": ["gsc.clicks", "gsc.impressions"],
        })

    return insights


# ── GBP (Google Business Profile) Rules ────────────────────────────────

def gbp_underperforming(client_id: int, db, thr=None) -> list[dict]:
    """GBP profile has high search views but low actions — optimize the listing."""
    from app.models import GbpSnapshot

    today = date.today()
    cutoff = today - timedelta(days=30)

    recent = (
        db.query(GbpSnapshot)
        .filter(
            GbpSnapshot.client_id == client_id,
            GbpSnapshot.fetched_at >= cutoff,
        )
        .order_by(GbpSnapshot.fetched_at.desc())
        .first()
    )
    if not recent:
        return []

    insights = []

    # High impressions, low actions
    if recent.search_views >= 500:
        total_actions = recent.total_actions or 0
        if total_actions > 0:
            action_rate = total_actions / recent.search_views
            if action_rate < 0.03:  # Below 3% action rate
                insights.append({
                    "type": "gbp_low_engagement",
                    "kind": "problem",
                    "message": (
                        f"GBP profile has {recent.search_views:,} search views but only "
                        f"{total_actions} actions (calls/directions/clicks) — "
                        f"{action_rate:.1%} engagement rate. Listing optimization needed."
                    ),
                    "recommended_action": (
                        "1) Update GBP profile: add services/products, Q&A, posts weekly.\n"
                        "2) Upload 5+ new photos (interior, exterior, team, work examples).\n"
                        "3) Respond to all reviews (positive + negative) — improves visibility.\n"
                        "4) Verify NAP consistency with website and citations.\n"
                        "5) Recheck GBP actions in 14 days."
                    ),
                    "severity": "high" if action_rate < 0.01 else "medium",
                    "impact_weight": min(100.0, recent.search_views / 20),
                    "metrics_to_watch": ["gbp.website_clicks", "gbp.phone_calls"],
                })

    # Discovery searches declining
    if recent.discovery_searches > 0:
        prev = (
            db.query(GbpSnapshot)
            .filter(
                GbpSnapshot.client_id == client_id,
                GbpSnapshot.fetched_at < cutoff,
            )
            .order_by(GbpSnapshot.fetched_at.desc())
            .first()
        )
        if prev and prev.discovery_searches > 0:
            change = (recent.discovery_searches - prev.discovery_searches) / prev.discovery_searches
            if change < -0.15:
                insights.append({
                    "type": "gbp_discovery_decline",
                    "kind": "problem",
                    "message": (
                        f"GBP discovery (non-brand) searches dropped {abs(change):.0%}: "
                        f"{prev.discovery_searches:,} → {recent.discovery_searches:,}. "
                        f"Local pack visibility may be declining."
                    ),
                    "recommended_action": (
                        "1) Check GBP for policy violations or suspended listings.\n"
                        "2) Add/update services with relevant categories.\n"
                        "3) Build local citations on directories (Yelp, BBB, industry sites).\n"
                        "4) Post weekly updates to signal activity.\n"
                        "5) Recheck discovery searches in 14 days."
                    ),
                    "severity": "high" if change < -0.30 else "medium",
                    "impact_weight": min(100.0, abs(change) * 80 + 20),
                    "metrics_to_watch": ["gbp.discovery_searches", "gbp.map_views"],
                })

    return insights


# ── CrUX (Core Web Vitals Field Data) Rules ────────────────────────────

def crux_cwv_gap(client_id: int, db, thr=None) -> list[dict]:
    """Real-user Core Web Vitals failing while lab scores pass — silent ranking killer."""
    from app.models import CruxSnapshot

    today = date.today()
    cutoff = today - timedelta(days=14)

    recent = (
        db.query(CruxSnapshot)
        .filter(
            CruxSnapshot.client_id == client_id,
            CruxSnapshot.fetched_at >= cutoff,
        )
        .order_by(CruxSnapshot.fetched_at.desc())
        .first()
    )
    if not recent:
        return []

    insights = []

    # LCP failing
    if recent.lcp_p75 is not None and recent.lcp_p75 > 2500:
        good_pct = recent.lcp_good_pct or 0
        insights.append({
            "type": "crux_lcp_failing",
            "kind": "problem",
            "message": (
                f"CrUX field data: 75th percentile LCP is {recent.lcp_p75:.0f}ms "
                f"(Google threshold: <2,500ms). Only {good_pct:.0f}% of users have "
                f"good LCP. Real users experience the page as slow — Core Web Vitals "
                f"penalty may apply."
            ),
            "recommended_action": (
                "1) Identify the LCP element (hero image, heading, background) — optimize it.\n"
                "2) Preload the LCP image; use srcset for responsive loading.\n"
                "3) Reduce server response time (TTFB) — enable CDN, optimize backend.\n"
                "4) Defer non-critical third-party scripts.\n"
                "5) Recheck CrUX in 28 days (field data updates monthly)."
            ),
            "severity": "high" if recent.lcp_p75 > 4000 else "medium",
            "impact_weight": min(100.0, recent.lcp_p75 / 40),
            "metrics_to_watch": ["gsc.clicks", "ga4.sessions"],
        })

    # CLS failing
    if recent.cls_p75 is not None and recent.cls_p75 > 0.25:
        good_pct = recent.cls_good_pct or 0
        insights.append({
            "type": "crux_cls_failing",
            "kind": "problem",
            "message": (
                f"CrUX field data: 75th percentile CLS is {recent.cls_p75:.3f} "
                f"(Google threshold: <0.1). Only {good_pct:.0f}% of users have "
                f"good layout stability. Visual jank is hurting UX and rankings."
            ),
            "recommended_action": (
                "1) Add explicit width/height to all images, videos, and embeds.\n"
                "2) Reserve space for dynamic content (ads, banners) with min-height.\n"
                "3) Avoid injecting content above existing content (no late-loading banners).\n"
                "4) Recheck CrUX in 28 days."
            ),
            "severity": "high" if recent.cls_p75 > 0.5 else "medium",
            "impact_weight": min(100.0, recent.cls_p75 * 80 + 20),
            "metrics_to_watch": ["ga4.sessions", "ga4.key_events"],
        })

    # INP failing
    if recent.inp_p75 is not None and recent.inp_p75 > 200:
        good_pct = recent.inp_good_pct or 0
        insights.append({
            "type": "crux_inp_failing",
            "kind": "problem",
            "message": (
                f"CrUX field data: 75th percentile INP is {recent.inp_p75:.0f}ms "
                f"(Google threshold: <200ms). Only {good_pct:.0f}% have good "
                f"interaction responsiveness. Heavy JS is blocking user input."
            ),
            "recommended_action": (
                "1) Audit JavaScript bundle size — split into smaller chunks.\n"
                "2) Use requestIdleCallback / setTimeout to defer non-critical handlers.\n"
                "3) Avoid long synchronous tasks (>50ms) in event handlers.\n"
                "4) Profile with Chrome DevTools Performance tab.\n"
                "5) Recheck CrUX in 28 days."
            ),
            "severity": "high" if recent.inp_p75 > 500 else "medium",
            "impact_weight": min(100.0, recent.inp_p75 / 5),
            "metrics_to_watch": ["ga4.sessions", "ga4.key_events"],
        })

    return insights
