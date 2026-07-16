"""
Assignee routing — maps playbook patterns to the right executor.
    
    Cursor AI  → Title/meta/H1/body changes, speed fixes, content creation
    Human      → GMB, citations, reviews, GBP management
    Prove      → Auto-recheck is already scheduled by impact_tracker.tasks_due_for_recheck

The plan also strips wait/recheck steps from Cursor briefs since Prove handles measurement.
"""

import re

# Playbook patterns assignable to Cursor AI (code/content on a URL)
CURSOR_PLAYBOOKS = frozenset({
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
    "crawl_missing_title",
    "crawl_missing_h1",
    "crawl_missing_meta",
    "crawl_thin_content",
    "crawl_broken_pages",
    "organic_leads_leak",
    "ads_spend_low_leads",
    "bing_opportunity",
    "bing_underperform",
    "local_onsite",
})

# Playbook patterns that require human intervention (GMB, reviews, GBP, sales ops, security)
HUMAN_PLAYBOOKS = frozenset({
    "leads_revenue_leak",
    "error_spike_alert",
})

# Steps that should be stripped from Cursor briefs — Prove handles these
_RECHECK_PATTERNS = (
    r"(?i)(?:recheck|compare|remeasure|monitor|track)\s+(?:ctr|clicks|position|metrics?)\s+"
    r"(?:in\s+)?\d+\s*(?:–|-|to)?\s*\d*\s*(?:day|week)"
)


def assignee_for_playbook(playbook_pattern: str | None) -> str:
    """Return 'cursor', 'human', or empty string (auto/cursor)."""
    if not playbook_pattern:
        return ""
    p = playbook_pattern.strip().lower()
    if p in HUMAN_PLAYBOOKS:
        return "human"
    if p in CURSOR_PLAYBOOKS:
        return "cursor"
    return ""


def strip_recheck_steps(steps: list[str] | None) -> list[str]:
    """
    Remove Prove-owned recheck/remeasure steps from Cursor task steps.
    Prove's impact_tracker.tasks_due_for_recheck handles measurement automatically.
    """
    if not steps:
        return []
    kept = []
    for s in steps:
        if re.search(_RECHECK_PATTERNS, s):
            continue
        kept.append(s)
    return kept


def is_human_task(playbook_pattern: str | None, title: str = "") -> bool:
    """True if this task needs a human (GMB, GBP, reviews)."""
    if assignee_for_playbook(playbook_pattern) == "human":
        return True
    t = title.lower()
    if any(kw in t for kw in ("gmb", "gbp", "google business", "citations", "review")):
        return True
    return False
