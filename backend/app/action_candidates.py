"""
Deterministic action candidate generation for the action planner.

Maps insight types to allowed playbooks, enriches with page targets,
applies evidence gates, and dedupes against open tasks.
The action planner LLM receives these candidates and only writes
    FROM->TO copy — it never invents new action types.
"""

import hashlib
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Insight, Task

logger = logging.getLogger(__name__)

ALLOWED_PLAYBOOKS: dict[str, tuple[str, str, str, list[str]]] = {
    "ctr_gap": ("ctr_gap", "cursor", "gsc.ctr", ["gsc.ctr", "gsc.clicks"]),
    "ctr_opportunity": ("ctr_opportunity", "cursor", "gsc.ctr", ["gsc.ctr", "gsc.clicks"]),
    "zero_click_alert": ("ctr_gap", "cursor", "gsc.ctr", ["gsc.ctr", "gsc.clicks"]),
    "content_opportunity": ("content_opportunity", "cursor", "gsc.clicks", ["gsc.impressions", "gsc.clicks", "gsc.position"]),
    "cro_opportunity": ("cro_opportunity", "cursor", "ga4.key_events", ["ga4.key_events", "ga4.cvr"]),
    "bounce_cro_alert": ("cro_opportunity", "cursor", "ga4.key_events", ["ga4.key_events", "ga4.cvr"]),
    "pagespeed_urgent": ("pagespeed_urgent", "cursor", "pagespeed.score", ["pagespeed.score", "gsc.clicks"]),
    "pagespeed_improve": ("pagespeed_improve", "cursor", "pagespeed.score", ["pagespeed.score", "gsc.clicks"]),
    "mobile_ctr_gap": ("mobile_ctr_gap", "cursor", "gsc.ctr", ["gsc.ctr", "gsc.clicks"]),
    "decline_alert": ("decline_alert", "cursor", "gsc.impressions", ["gsc.impressions", "gsc.clicks"]),
    "crawl_missing_title": ("crawl_missing_title", "cursor", "gsc.impressions", ["gsc.impressions"]),
    "crawl_missing_h1": ("crawl_missing_h1", "cursor", "gsc.impressions", ["gsc.impressions"]),
    "crawl_missing_meta": ("crawl_missing_meta", "cursor", "gsc.ctr", ["gsc.ctr", "gsc.impressions"]),
    "crawl_thin_content": ("crawl_thin_content", "cursor", "gsc.clicks", ["gsc.clicks", "gsc.position"]),
    "crawl_broken_pages": ("crawl_broken_pages", "cursor", "gsc.impressions", ["gsc.impressions"]),
    "organic_leads_leak": ("organic_leads_leak", "cursor", "ga4.key_events", ["ga4.key_events", "ga4.cvr", "crm.leads"]),
    "ads_spend_low_leads": ("ads_spend_low_leads", "cursor", "crm.leads", ["crm.leads", "ga4.key_events"]),
    "pause_weak_campaign": ("pause_weak_campaign", "human", "paid.conversions", ["paid.conversions", "paid.cost"]),
    "verify_tracking": ("verify_tracking", "human", "ga4.key_events", ["ga4.key_events", "crm.leads"]),
    "crux_lcp_failing": ("crux_lcp_failing", "cursor", "crux.lcp", ["crux.lcp", "pagespeed.score"]),
    "crux_cls_failing": ("crux_cls_failing", "cursor", "crux.cls", ["crux.cls"]),
    "crux_inp_failing": ("crux_inp_failing", "cursor", "crux.inp", ["crux.inp"]),
    "bing_opportunity": ("bing_opportunity", "cursor", "gsc.clicks", ["gsc.clicks", "gsc.impressions"]),
    "bing_underperform": ("bing_underperform", "cursor", "gsc.clicks", ["gsc.clicks", "gsc.impressions"]),
    "local_onsite": ("local_onsite", "cursor", "gsc.clicks", ["gsc.clicks", "gsc.impressions"]),
    "gbp_low_engagement": ("gbp_low_engagement", "cursor", "gbp.total_actions", ["gbp.total_actions", "gbp.search_views", "gsc.clicks"]),
    "gbp_discovery_decline": ("gbp_discovery_decline", "cursor", "gbp.discovery_searches", ["gbp.discovery_searches", "gbp.search_views"]),
    "local_gbp": ("local_gbp", "cursor", "gsc.clicks", ["gsc.clicks", "gsc.impressions", "gbp.search_views"]),
    "leads_revenue_leak": ("leads_revenue_leak", "human", "hubspot.revenue", ["hubspot.revenue", "hubspot.closed_won"]),
    "error_spike_alert": ("error_spike_alert", "human", "cf.threats", ["cf.threats", "ga4.sessions"]),
}

ALLOWED_TYPES = frozenset(ALLOWED_PLAYBOOKS.keys())
ALLOWED_PLAYBOOK_PATTERNS = frozenset(v[0] for v in ALLOWED_PLAYBOOKS.values())

CATEGORY_MAP: dict[str, str] = {
    "ctr_gap": "content",
    "ctr_opportunity": "content",
    "zero_click_alert": "content",
    "content_opportunity": "content",
    "cro_opportunity": "cro",
    "bounce_cro_alert": "cro",
    "pagespeed_urgent": "speed",
    "pagespeed_improve": "speed",
    "mobile_ctr_gap": "ux",
    "decline_alert": "technical_seo",
    "crawl_missing_title": "technical_seo",
    "crawl_missing_h1": "technical_seo",
    "crawl_missing_meta": "technical_seo",
    "crawl_thin_content": "content",
    "crawl_broken_pages": "technical_seo",
    "organic_leads_leak": "cro",
    "ads_spend_low_leads": "analytics",
    "pause_weak_campaign": "paid",
    "verify_tracking": "analytics",
    "crux_lcp_failing": "speed",
    "crux_cls_failing": "speed",
    "crux_inp_failing": "speed",
    "bing_opportunity": "content",
    "bing_underperform": "technical_seo",
    "local_onsite": "local_seo",
    "gbp_low_engagement": "local_seo",
    "gbp_discovery_decline": "local_seo",
    "leads_revenue_leak": "analytics",
    "error_spike_alert": "analytics",
}

EFFORT_MAP: dict[str, str] = {
    "ctr_gap": "low",
    "ctr_opportunity": "low",
    "zero_click_alert": "low",
    "content_opportunity": "medium",
    "cro_opportunity": "medium",
    "bounce_cro_alert": "medium",
    "pagespeed_urgent": "high",
    "pagespeed_improve": "medium",
    "mobile_ctr_gap": "medium",
    "decline_alert": "medium",
    "crawl_missing_title": "low",
    "crawl_missing_h1": "low",
    "crawl_missing_meta": "low",
    "crawl_thin_content": "medium",
    "crawl_broken_pages": "medium",
    "organic_leads_leak": "medium",
    "ads_spend_low_leads": "medium",
    "pause_weak_campaign": "low",
    "verify_tracking": "medium",
    "crux_lcp_failing": "high",
    "crux_cls_failing": "medium",
    "crux_inp_failing": "medium",
    "bing_opportunity": "low",
    "bing_underperform": "medium",
    "local_onsite": "medium",
    "gbp_low_engagement": "medium",
    "gbp_discovery_decline": "medium",
    "leads_revenue_leak": "high",
    "error_spike_alert": "high",
}

# Moji-bake fix: use real en-dashes in remaining timeline strings
TIMELINE_MAP: dict[str, str] = {
    "ctr_gap": "2–4 weeks",
    "ctr_opportunity": "2–4 weeks",
    "zero_click_alert": "2–4 weeks",
    "content_opportunity": "4–8 weeks",
    "cro_opportunity": "4–6 weeks",
    "bounce_cro_alert": "4–6 weeks",
    "pagespeed_urgent": "2–4 weeks",
    "pagespeed_improve": "2–4 weeks",
    "mobile_ctr_gap": "3–6 weeks",
    "decline_alert": "1–3 weeks",
    "crawl_missing_title": "1–2 weeks",
    "crawl_missing_h1": "1–2 weeks",
    "crawl_missing_meta": "1–2 weeks",
    "crawl_thin_content": "2–4 weeks",
    "crawl_broken_pages": "1–3 weeks",
    "organic_leads_leak": "2–4 weeks",
    "ads_spend_low_leads": "2–4 weeks",
    "pause_weak_campaign": "1–2 weeks",
    "verify_tracking": "1–2 weeks",
    "crux_lcp_failing": "2–4 weeks",
    "crux_cls_failing": "2–4 weeks",
    "crux_inp_failing": "2–4 weeks",
    "bing_opportunity": "2–4 weeks",
    "bing_underperform": "2–4 weeks",
    "local_onsite": "2–4 weeks",
    "gbp_low_engagement": "2–4 weeks",
    "gbp_discovery_decline": "2–4 weeks",
    "leads_revenue_leak": "4–8 weeks",
    "error_spike_alert": "1–2 weeks",
}

_IN_ACTIVE_STATUSES = frozenset({"open", "in_progress"})


def compute_task_fingerprint(
    client_id: int,
    playbook_pattern: str,
    target_query: Optional[str],
    target_url: Optional[str],
    insight_id: Optional[int] = None,
) -> str:
    """Canonical deterministic dedupe key shared across action_candidates and tasks router.

    Uses playbook_pattern (not insight_type) so the match is exact with what
    routers/tasks.py computes when ActionBoard creates a Task from this action.
    """
    base = (
        (target_query or "").strip().lower()[:200]
        or (target_url or "").strip().lower()[:200]
        or f"insight:{insight_id}"
    )
    pattern = (playbook_pattern or "none").strip().lower()[:100]
    raw = f"{client_id}|{pattern}|{base}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def build_action_candidates(
    db: Session,
    client_id: int,
    *,
    max_candidates: int = 8,
) -> list[dict[str, Any]]:
    """
    Generate deterministic action candidates from top unresolved insights.

    Returns candidate dicts with all fields pre-filled except proposed_changes
    and steps (which the action planner LLM fills in). Each candidate carries
    insight_id so the resulting task links back to the insight.
    """
    from app.page_targets import (
        enrich_insight_item,
        resolve_target_url,
        latest_snapshot,
        snapshot_state,
        propose_serp_copy,
        extract_quoted_queries,
    )
    from app.models import Client

    client = db.query(Client).filter(Client.id == client_id).first()
    brand = (client.name or "").split(".")[0] if client else ""

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    unresolved = (
        db.query(Insight)
        .filter(Insight.client_id == client_id, Insight.resolved == False)  # noqa: E712
        .all()
    )
    if not unresolved:
        logger.info("No unresolved insights for client %s — no candidates", client_id)
        return []

    unresolved.sort(key=lambda i: (severity_rank.get(i.severity, 9), -(i.priority_score or 0)))

    candidates: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()

    for ins in unresolved:
        if len(candidates) >= max_candidates:
            break

        insight_type = (ins.type or "").strip()
        if insight_type not in ALLOWED_TYPES:
            logger.info("Skipping insight %s: type %s not in allowed playbook catalog", ins.id, insight_type)
            continue

        playbook_pattern, assignee, success_metric, metrics_to_watch = ALLOWED_PLAYBOOKS[insight_type]

        # Enrich insight item to get concrete URL + query
        raw_item = {
            "type": insight_type,
            "message": ins.message or "",
            "recommended_action": ins.recommended_action or "",
            "severity": ins.severity or "medium",
            "impact_weight": getattr(ins, "priority_score", None) or 50.0,
        }
        enriched = enrich_insight_item(db, client_id, raw_item, brand=brand)
        message = enriched.get("message") or ins.message or ""
        action_text = enriched.get("recommended_action") or ins.recommended_action or ""
        blob = f"{message} {action_text}"

        queries = extract_quoted_queries(blob)
        target_query = queries[0] if queries else None
        target_url = resolve_target_url(db, client_id, query=target_query)

        if not target_url:
            logger.info("Skipping insight %s: no target_url resolved", ins.id)
            continue

        # Dedupe against existing open tasks
        fp = compute_task_fingerprint(client_id, playbook_pattern, target_query, target_url)
        dup_task = (
            db.query(Task)
            .filter(
                Task.client_id == client_id,
                Task.fingerprint == fp,
                Task.status.in_(_IN_ACTIVE_STATUSES),
            )
            .first()
        )
        if dup_task:
            logger.info("Skipping candidate %s: open task %s already exists (fp=%s)", ins.id, dup_task.id, fp)
            continue

        # Dedupe against previously generated candidates in this batch
        if fp in seen_fingerprints:
            logger.info("Skipping candidate %s: duplicate fingerprint %s in current batch", ins.id, fp)
            continue
        seen_fingerprints.add(fp)

        # Get page state for FROM->TO copy
        snap = latest_snapshot(db, client_id, target_url)
        state = snapshot_state(snap)
        proposed = propose_serp_copy(target_query or "", brand, state) if target_query else {}

        # Build the candidate action dict
        candidate: dict[str, Any] = {
            "insight_id": ins.id,
            "title": _candidate_title(insight_type, target_query or target_url),
            "playbook_pattern": playbook_pattern,
            "category": CATEGORY_MAP.get(insight_type, "content"),
            "assignee": assignee,
            "success_metric": success_metric,
            "metrics_to_watch": metrics_to_watch,
            "target_url": target_url,
            "target_query": target_query or "",
            "priority_score": min(100.0, float(getattr(ins, "priority_score", 50) or 50)),
            "effort": EFFORT_MAP.get(insight_type, "medium"),
            "expected_timeline": TIMELINE_MAP.get(insight_type, "2–4 weeks"),
            "current_state": state,
            "proposed_changes_hint": proposed,
            "why_it_matters": ins.message or "",
            "evidence": f"{insight_type} insight #{ins.id}: {ins.message}",
            "estimated_impact": _estimate_impact(insight_type, state, proposed),
            "steps": _default_steps(insight_type, target_url, state, proposed, target_query),
            "fingerprint": fp,
        }
        candidates.append(candidate)

    # Phase 3.2: Collapse multiple queries sharing the same target URL into one task
    from app.page_targets import collapse_by_page
    before_collapse = len(candidates)
    candidates = collapse_by_page(candidates)
    if len(candidates) < before_collapse:
        logger.info(
            "Page-level collapse: %s -> %s candidates for client %s",
            before_collapse, len(candidates), client_id,
        )

    # Phase 4: Apply win-rate-based downranking from Prove outcome memory
    if candidates:
        candidates = _apply_win_rate_downranking(db, client_id, candidates, max_candidates)

    logger.info("Built %s action candidates for client %s", len(candidates), client_id)
    return candidates


def _apply_win_rate_downranking(
    db: Session,
    client_id: int,
    candidates: list[dict[str, Any]],
    max_candidates: int,
) -> list[dict[str, Any]]:
    """Fetch Prove outcome data and adjust priority scores by win rate.

    Playbooks with <30% win rate after >=3 tries get a heavy penalty (x0.3).
    Playbooks with >=70% win rate get a boost (x1.2).
    Ensures the feedback loop: losing patterns stop being prescribed.
    """
    try:
        from app.outcome_memory import playbook_win_rate, apply_downrank_to_score
        from app.portfolio_scoring import cross_client_fix_effectiveness

        xclient = cross_client_fix_effectiveness(db)
        win_rates = playbook_win_rate(db, client_id, cross_client_effectiveness=xclient)

        if not win_rates:
            return candidates

        downranked = 0
        boosted = 0
        for cand in candidates:
            pattern = cand.get("playbook_pattern") or ""
            if not pattern:
                continue
            old_score = float(cand.get("priority_score") or 50)
            new_score, factor = apply_downrank_to_score(old_score, pattern, win_rates)
            cand["priority_score"] = new_score
            if factor < 1.0:
                downranked += 1
            elif factor > 1.0:
                boosted += 1

        # Re-sort by adjusted priority score
        candidates.sort(key=lambda c: float(c.get("priority_score") or 0), reverse=True)
        capped = candidates[:max_candidates]

        if downranked or boosted:
            logger.info(
                "Win-rate downranking: %s downranked, %s boosted — %s -> %s candidates for client %s",
                downranked, boosted, len(candidates), len(capped), client_id,
            )
        return capped
    except Exception as e:
        logger.warning("Win-rate downranking skipped (non-fatal): %s", e)
        return candidates


def _candidate_title(insight_type: str, target_query_or_url: str) -> str:
    """Specific action-oriented title describing the actual fix."""
    snippet = (target_query_or_url or "").strip()
    # URL path extraction for cleaner titles
    if snippet.startswith("http"):
        try:
            path = snippet.split("/", 3)[-1] if len(snippet.split("/")) > 3 else snippet
            path = path.replace("-", " ").strip()[:40]
            snippet = path if path else "homepage"
        except Exception:
            snippet = snippet[:40]
    else:
        snippet = snippet[:60]

    templates = {
        "ctr_gap": f"Rewrite title & meta for '{snippet}'",
        "ctr_opportunity": f"Rewrite title & meta for '{snippet}'",
        "zero_click_alert": f"Fix zero-click SERP loss on '{snippet}'",
        "content_opportunity": f"Expand content targeting '{snippet}'",
        "cro_opportunity": f"Improve conversion rate on '{snippet}'",
        "bounce_cro_alert": f"Reduce bounce on '{snippet}'",
        "pagespeed_urgent": f"Fix critical page speed on '{snippet}'",
        "pagespeed_improve": f"Improve page speed on '{snippet}'",
        "mobile_ctr_gap": f"Fix mobile CTR for '{snippet}'",
        "decline_alert": f"Recover traffic decline on '{snippet}'",
        "crawl_missing_title": f"Add missing page title on '{snippet}'",
        "crawl_missing_h1": f"Add missing H1 heading on '{snippet}'",
        "crawl_missing_meta": f"Add missing meta description on '{snippet}'",
        "crawl_thin_content": f"Expand thin content on '{snippet}'",
        "crawl_broken_pages": f"Fix broken page '{snippet}'",
        "organic_leads_leak": f"Fix lead conversion leak on '{snippet}'",
        "ads_spend_low_leads": f"Improve ad-to-lead conversion on '{snippet}'",
        "pause_weak_campaign": f"Pause weak campaign '{snippet}'",
        "verify_tracking": f"Verify conversion tracking on '{snippet}'",
        "crux_lcp_failing": f"Fix real-user LCP on '{snippet}'",
        "crux_cls_failing": f"Fix real-user CLS on '{snippet}'",
        "crux_inp_failing": f"Fix real-user INP on '{snippet}'",
        "bing_opportunity": f"Capture Bing clicks for '{snippet}'",
        "bing_underperform": f"Fix Bing underperformance on '{snippet}'",
    "local_onsite": f"Optimize local SEO on '{snippet}'",
    "gbp_low_engagement": f"Boost GBP engagement on '{snippet}'",
    "gbp_discovery_decline": f"Recover GBP discovery searches on '{snippet}'",
    "leads_revenue_leak": f"Fix sales handoff leak for '{snippet}'",
        "error_spike_alert": f"Resolve security threat on '{snippet}'",
    }
    return templates.get(insight_type, f"Fix — {snippet}")


def _estimate_impact(insight_type: str, state: dict, proposed: dict) -> str:
    """Estimated impact tied to the specific insight type and target metric."""
    if insight_type in ("ctr_gap", "ctr_opportunity", "zero_click_alert"):
        return "+15-25% organic clicks in 30 days"
    if insight_type == "content_opportunity":
        return "+20-50% organic impressions in 30-60 days"
    if insight_type in ("cro_opportunity", "bounce_cro_alert"):
        return "+0.3-0.8pp conversion rate in 30 days"
    if insight_type in ("pagespeed_urgent", "pagespeed_improve"):
        return "+5-15% clicks/sessions after LCP improvement"
    if insight_type == "mobile_ctr_gap":
        return "+10-20% mobile clicks in 30 days"
    if insight_type == "decline_alert":
        return "Stop WoW decline, recover 50%+ of lost impressions"
    if insight_type in ("crawl_missing_title", "crawl_missing_meta"):
        return "+5-15% CTR improvement after adding metadata"
    if insight_type == "crawl_missing_h1":
        return "+5-10% impressions after adding H1"
    if insight_type == "crawl_thin_content":
        return "+10-25% organic impressions in 4-6 weeks"
    if insight_type == "crawl_broken_pages":
        return "Recover lost traffic from broken URL"
    if insight_type in ("organic_leads_leak", "ads_spend_low_leads"):
        return "+0.5-1.5pp lead conversion in 30 days"
    if insight_type == "pause_weak_campaign":
        return "Stop wasted ad spend within 7 days"
    if insight_type == "verify_tracking":
        return "Restore measurable conversions before optimizing spend"
    if insight_type.startswith("crux_"):
        return "Improve field CWV → rankings + conversion within 2–4 weeks"
    if insight_type in ("bing_opportunity", "bing_underperform"):
        return "+10-20% Bing clicks in 30 days"
    if insight_type == "local_onsite":
        return "+10-20% local organic clicks in 30 days"
    if insight_type == "gbp_low_engagement":
        return "+15-30% GBP total actions in 30 days"
    if insight_type == "gbp_discovery_decline":
        return "Recover GBP discovery search volume in 30 days"
    if insight_type == "leads_revenue_leak":
        return "+1-3 qualified leads in 14 days"
    if insight_type == "error_spike_alert":
        return "Reduce threat traffic, restore real user sessions"
    return "+measurable improvement on target metric"


def _default_steps(
    insight_type: str,
    target_url: str,
    state: dict,
    proposed: dict,
    target_query: Optional[str],
) -> list[str]:
    """Draft execution steps to seed the LLM with concrete instructions per playbook."""
    q = target_query or "the target query"
    title_now = (state.get("title") or "").strip()
    meta_now = (state.get("meta") or "").strip()
    h1_now = (state.get("h1") or "").strip()
    new_title = (proposed.get("title") or "").strip()
    new_meta = (proposed.get("meta") or "").strip()

    if insight_type in ("ctr_gap", "ctr_opportunity", "zero_click_alert"):
        steps = []
        if title_now and new_title:
            steps.append(
                f'On {target_url}: Change <title> FROM "{title_now}" TO "{new_title}" (max 60 chars)'
            )
        if meta_now and new_meta:
            steps.append(
                f'On {target_url}: Change meta description FROM "{meta_now}" TO "{new_meta}" (max 155 chars)'
            )
        if h1_now and q and q.lower() not in h1_now.lower():
            steps.append(f'On {target_url}: Update H1 to better match \'{q}\' (current: "{h1_now}")')
        steps.append(f"Request indexing for {target_url} via GSC URL Inspection")
        steps.append("Recheck GSC CTR and clicks on this query in 14 days")
        return steps

    if insight_type == "content_opportunity":
        return [
            f'On {target_url}: Expand content to 400-800 words of unique information targeting "{q}"',
            f'Add an H2 section titled around "{q}" covering what visitors want to know',
            f"Add 2-3 internal links to {target_url} with descriptive anchor text",
            f"Request indexing for {target_url}; recheck GSC position/clicks in 21 days",
        ]

    if insight_type in ("cro_opportunity", "bounce_cro_alert"):
        return [
            f"On {target_url}: Place one clear primary CTA above the fold (button or form)",
            f'On {target_url}: Align hero headline to the page\'s intent (current H1: "{h1_now}")',
            f"On {target_url}: Add trust elements near CTA (reviews, guarantee, service area badge)",
            f"Monitor GA4 key_events and conversion rate on {target_url} for 14 days",
        ]

    if insight_type in ("pagespeed_urgent", "pagespeed_improve"):
        return [
            f"Run PageSpeed Insights (mobile) on {target_url} -- identify the LCP element",
            f"Compress hero images to WebP/AVIF, preload the LCP image, set explicit width/height",
            f"Defer non-critical JS and trim unused CSS on {target_url}",
            f"Retest mobile PSI score on {target_url} until 70+; recheck clicks in 14 days",
        ]

    if insight_type == "local_onsite":
        return [
            f"On {target_url}: Verify business name, address, phone (NAP) matches GBP exactly",
            f"Add city + service keyword to <title> and H1 on {target_url}",
            f"Embed service-area specifics: cities served, coverage map, local landmarks",
            f"Add LocalBusiness schema with service area defined on {target_url}",
        ]

    if insight_type in ("gbp_low_engagement", "gbp_discovery_decline"):
        return [
            f"On GBP listing: Verify business hours, phone, services are accurate and complete",
            f"Add new GBP posts (offers, events, updates) to increase engagement signals",
            f"Respond to all Google reviews within 48 hours",
            f"Encourage 3-5 new Google reviews from recent customers this week",
            f"Recheck GBP insights in 14 days for engagement/reach improvement",
        ]

    if insight_type == "leads_revenue_leak":
        return [
            f"Review HubSpot pipeline: verify leads are being contacted within 5 minutes of submission",
            f"Check sales team follow-up rate on new leads — target 95% contact within 24 hours",
            f"Set up lead scoring to prioritize high-intent leads for immediate call-back",
            f"Monitor closed-won rate vs lead volume in 14 days",
        ]

    if insight_type == "error_spike_alert":
        return [
            "Cloudflare Security Events: identify bot/attack patterns hitting the site",
            "Tighten WAF rules and bot management for abusive paths",
            "Verify real user traffic is still passing through the funnel (GA4 sessions)",
            "Recheck GA4 sessions vs threat counts in 7 days",
        ]

    return [
        f'On {target_url}: Implement fix for "{q}"',
        f"Deploy changes and request indexing for {target_url}",
        "Recheck primary metric in 14 days",
    ]
