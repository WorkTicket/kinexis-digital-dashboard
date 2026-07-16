"""
Insight priority scoring: expected impact × inverse effort.
Used to rank the Prescribe fix queue and Portfolio Today items.
"""

from typing import Optional

# Base impact by severity
SEVERITY_IMPACT = {"high": 85, "medium": 55, "low": 30}

# Default kind when a rule does not emit one
PROBLEM_TYPES = {
    "decline_alert",
    "zero_click_alert",
    "error_spike_alert",
    "pagespeed_urgent",
    "cro_opportunity",
    "bounce_cro_alert",
    "ads_spend_low_leads",
    "pause_weak_campaign",
    "ads_search_term_waste",
    "meta_placement_waste",
    "meta_creative_fatigue",
    "sov_loss",
    "leads_revenue_leak",
    "organic_leads_leak",
    "mobile_ctr_gap",
    "ctr_gap",
    "gbp_low_engagement",
    "gbp_discovery_decline",
    "verify_tracking",
    "crux_lcp_failing",
    "crux_cls_failing",
    "crux_inp_failing",
}

OPPORTUNITY_TYPES = {
    "content_opportunity",
    "ctr_opportunity",
    "pagespeed_improve",
    "bing_opportunity",
    "bing_underperform",
    "local_onsite",
}

# Effort weight by insight type (lower effort → higher score multiplier)
# effort_factor: 1.0 = low effort, 0.7 = medium, 0.45 = high
TYPE_EFFORT = {
    "content_opportunity": 0.7,
    "ctr_opportunity": 1.0,
    "ctr_gap": 1.0,
    "decline_alert": 0.7,
    "zero_click_alert": 0.85,
    "cro_opportunity": 0.55,
    "error_spike_alert": 0.85,
    "pagespeed_urgent": 0.45,
    "pagespeed_improve": 0.7,
    "mobile_ctr_gap": 0.7,
    "bing_opportunity": 1.0,
    "bing_underperform": 0.85,
    "bounce_cro_alert": 0.55,
    "local_onsite": 0.85,
    "gbp_low_engagement": 0.7,
    "gbp_discovery_decline": 0.7,
    "ads_spend_low_leads": 0.7,
    "pause_weak_campaign": 1.0,
    "ads_search_term_waste": 1.0,
    "meta_placement_waste": 1.0,
    "meta_creative_fatigue": 0.85,
    "sov_loss": 0.7,
    "leads_revenue_leak": 0.45,
    "organic_leads_leak": 0.7,
    "verify_tracking": 1.0,
    "crux_lcp_failing": 0.45,
    "crux_cls_failing": 0.7,
    "crux_inp_failing": 0.7,
}

TYPE_WHY = {
    "content_opportunity": "Rising search demand you can capture with better content.",
    "ctr_opportunity": "People see you in search but choose someone else — fix titles/metas.",
    "ctr_gap": "High-volume query CTR is far below expected — titles/metas are leaking clicks.",
    "decline_alert": "Traffic is dropping week-over-week; stop the bleed first.",
    "zero_click_alert": "High visibility with almost no clicks — wasted opportunity.",
    "cro_opportunity": "Plenty of visitors, few conversions — money left on the table.",
    "error_spike_alert": "Bad traffic or attacks may be hurting real users.",
    "pagespeed_urgent": "Slow mobile pages hurt rankings and conversions now.",
    "pagespeed_improve": "Faster pages improve experience and search performance.",
    "mobile_ctr_gap": "Mobile searchers click less than desktop — fix the mobile SERP/UX.",
    "bing_opportunity": "Bing is an untapped channel for incremental traffic.",
    "bing_underperform": "Bing share is weak vs Google — easy incremental wins.",
    "bounce_cro_alert": "Visitors leave quickly and rarely convert — fix the landing experience.",
    "ads_spend_low_leads": "Ad spend is not producing CRM leads — fix tracking or cut waste.",
    "pause_weak_campaign": "A campaign is spending with zero conversions — pause or rebuild.",
    "ads_search_term_waste": "Search terms are burning budget with zero conversions — negative them.",
    "meta_placement_waste": "A Meta placement is spending with zero conversions — exclude or reallocate.",
    "meta_creative_fatigue": "Ad frequency is high and CTR is collapsing — refresh creative.",
    "sov_loss": "Competitors outrank you on tracked SERPs — reclaim title/meta and page proof.",
    "crux_lcp_failing": "Real users experience slow LCP — field data, not lab scores.",
    "crux_cls_failing": "Real users experience layout shift — stabilize the page.",
    "crux_inp_failing": "Real users experience slow interactions — fix main-thread work.",
    "local_onsite": "On-site NAP, keywords, and location pages improve local pack visibility.",
    "gbp_low_engagement": "GBP engagement (clicks, calls, direction requests) is below expected — optimize the listing.",
    "gbp_discovery_decline": "People are finding GBP less often — update categories, posts, and review responses.",
    "leads_revenue_leak": "Leads are up but closed revenue is flat — sales handoff is leaking.",
    "organic_leads_leak": "Organic traffic is up but CRM leads are flat — offer or tracking leak.",
    "verify_tracking": "No conversions have ever been recorded — tracking may be broken, not the page.",
}


def default_kind(insight_type: str) -> str:
    if insight_type in PROBLEM_TYPES:
        return "problem"
    if insight_type in OPPORTUNITY_TYPES:
        return "opportunity"
    return "opportunity"


INTENT_WEIGHTS = {
    "local_commercial": 1.0,
    "informational": 0.4,
    "navigational": 0.1,
    "other": 0.2,
}


def score_insight(severity: str, insight_type: str) -> float:
    impact = SEVERITY_IMPACT.get((severity or "medium").lower(), 55)
    effort = TYPE_EFFORT.get(insight_type, 0.7)
    return round(min(100.0, impact * effort * 1.15), 1)


def score_with_impact(
    severity: str,
    insight_type: str,
    impact_weight: float | None = None,
) -> float:
    """
    Rank by expected impact. impact_weight is 0–100 from rule evidence
    (e.g. impressions × CTR gap normalized).
    """
    base = score_insight(severity, insight_type)
    if impact_weight is None:
        return base
    w = max(0.0, min(100.0, float(impact_weight)))
    # Blend: 60% base score, 40% evidence weight
    return round(min(100.0, base * 0.6 + w * 0.4), 1)


def score_with_intent(
    severity: str,
    insight_type: str,
    impact_weight: float | None = None,
    lead_intent_weight: float = 1.0,
    in_service_area: bool = True,
) -> float:
    """
    Priority ≈ f(impr × CTR_gap × lead_intent_weight × in_service_area).
    
    - lead_intent_weight: 1.0 for local_commercial, 0.4 for informational, etc.
    - in_service_area: False when query is out-of-area (suppress to ~0).
    
    Blend: 60% base score (severity × effort) + 40% evidence weight,
    then multiply by intent weight. Out-of-area queries are floored to ~10.
    """
    if not in_service_area:
        return 10.0  # suppress but don't fully hide
    base = score_with_impact(severity, insight_type, impact_weight)
    w = max(0.1, min(1.0, float(lead_intent_weight)))
    return round(min(100.0, base * w), 1)


def why_it_matters(insight_type: str, message: Optional[str] = None) -> str:
    base = TYPE_WHY.get(insight_type, "This issue is holding back growth metrics.")
    if message and len(message) < 120:
        return f"{base} ({message})"
    return base


def effort_label(insight_type: str) -> str:
    f = TYPE_EFFORT.get(insight_type, 0.7)
    if f >= 0.9:
        return "low"
    if f >= 0.6:
        return "medium"
    return "high"


def score_with_proven_effectiveness(
    severity: str,
    insight_type: str,
    *,
    impact_weight: float | None = None,
    lead_intent_weight: float = 1.0,
    in_service_area: bool = True,
    effectiveness: dict[str, dict] | None = None,
) -> float:
    """Score insight boosted by cross-client proven win rates.

    When the agency has proven a fix type multiple times with real measured
    lift, that insight type gets a priority boost. Reinforces what works.
    """
    base = score_with_intent(
        severity, insight_type,
        impact_weight=impact_weight,
        lead_intent_weight=lead_intent_weight,
        in_service_area=in_service_area,
    )
    if not effectiveness or insight_type not in effectiveness:
        return base
    stats = effectiveness[insight_type]
    total = stats.get("total", 0)
    if total < 3:
        return base
    win_rate = (stats.get("wins", 0) / total) if total > 0 else 0
    median_lift = stats.get("median_lift_pct") or 0
    # Boost: up to 15% for win rate, up to 10% for median lift
    boost = 1.0 + win_rate * 0.15 + min(0.10, max(0, median_lift) / 200)
    return round(min(100.0, base * boost), 1)
