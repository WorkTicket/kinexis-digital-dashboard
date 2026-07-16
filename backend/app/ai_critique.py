"""
Self-critique pass for AI-generated plans and briefs.

Phase 2: Extended policy engine rejects unknown playbook patterns,
missing insight_id, and FAQ/schema without evidence. The deterministic
policy check runs first, then an LLM call validates evidence grounding.

Phase 4: Rejection rate tracking with telemetry — logs overall critique
rejection rate and warns when >50% (indicating prompts/rules need tuning).

Apply the Kinexis playbook catalog from action_candidates to reject
any action whose playbook_pattern is not in the allowed list.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.ai_client import complete, parse_json_payload
from app.action_candidates import ALLOWED_PLAYBOOK_PATTERNS as _ALLOWED_PLAYBOOK_PATTERNS
from app.service_area import ServiceArea, classify_query_geo, parse_service_area

logger = logging.getLogger(__name__)

CRITIQUE_REJECTION_RATE_WARN_THRESHOLD: float = 50.0
CRITIQUE_REJECTION_RATE_LOG_INTERVAL: int = 10

import threading

_critique_stats_lock = threading.Lock()

_critique_stats: dict[str, Any] = {
    "total_actions": 0,
    "policy_rejected": 0,
    "llm_rejected": 0,
    "accepted": 0,
    "by_reason": {},
    "call_count": 0,
}

CRITIQUE_ACTIONS_PROMPT = """You are a strict editor. For each action below, check whether the
"evidence" field (and why_it_matters) cites a real number, URL, or query that actually
appears in the SOURCE CONTEXT provided. Also reject if the action is generic
("improve SEO", "check GSC", "research competitors") or missing a concrete target_url
when FIX TARGET / page URLs were provided in the context. If an action's evidence is
vague, invented, or unsupported by the context, mark it "reject": true with a one-line
"reason". Otherwise set "reject": false.

Output a JSON array with the same length and order as the input actions. Each item must
include at least: "title" (echo), "reject" (boolean), and optionally "reason".
Do not invent new actions. Output valid JSON only."""

CRITIQUE_BRIEF_PROMPT = """You are a strict editor. Check whether this content brief is grounded
in the SOURCE CONTEXT (GSC numbers, keyword, insight message, page state when present).
Reject if titles/meta/serp_notes invent specific metrics, URLs, or queries that do not
appear in the context and are not clearly inferred from it.

Output a JSON object: {"reject": true|false, "reason": "one line if reject"}.
Output valid JSON only."""

# Policy patterns that trigger automatic rejection
_REJECT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Meta-audits / bulk audits
    (re.compile(r"(?i)audit\s+all\s+\d+\s+zero.click"), "bulk zero-click audit"),
    (re.compile(r"(?i)comprehensive\s+(serp|seo|audit)"), "comprehensive audit without target"),
    (re.compile(r"(?i)audit\s+(all|every)\s+(query|page|keyword|url)"), "bulk audit"),
    # FAQ schema for snippet eligibility
    (re.compile(r"(?i)faq.?schema.*(?:snippet|featured|eligib)"), "FAQ schema for snippets"),
    (re.compile(r"(?i)featured.?snippet.*(?:faq|schema|eligib)"), "snippet schema"),
    (re.compile(r"(?i)(?:add|implement)\s+structured\s+data.*(?:snippet|featured|faq)"), "structured data for snippets"),
    # Generic unshiprable
    (re.compile(r"(?i)^(?:improve|optimize|enhance)\s+(?:seo|site|page)\s"), "generic optimization"),
    (re.compile(r"(?i)^(?:check|research|review|analyze)\s+(?:gsc|competitor|keyword|serp)"), "research-only"),
    (re.compile(r"(?i)^(?:optimize|improve)\s+serp\s+snippet\s+for"), "generic SERP snippet"),
    # Fleet actions
    (re.compile(r"(?i)fix\s+(?:all|every)\s+"), "fleet action"),
    (re.compile(r"(?i)schema.*(?:default|always|whenever)"), "blanket schema"),
    # Mobile/PageSpeed without evidence
    (re.compile(r"(?i)^(?:improve|optimize|fix|audit)\s+mobile"), "mobile without evidence"),
    (re.compile(r"(?i)mobile\s+(?:ux|usability|experience)\s+(?:audit|fix|improve)"), "mobile UX without evidence"),
    (re.compile(r"(?i)^(?:improve|fix|optimize)\s+(?:page\s*speed|pagespeed|site\s*speed)"), "page speed without evidence"),
    # Evidence that's just a template with no real numbers
    (re.compile(r"insight\s+#\d+:\s*$"), "evidence is empty after insight ref"),
    # Default step patterns that the LLM should override
    (re.compile(r"(?i)keep\s+H1\s+aligned\s+to"), "unimproved default step"),
    (re.compile(r"(?i)Change title FROM.*TO.*\u226460"), "default FROM-TO step unmodified"),
]

# Playbook patterns that require target_url
_TARGET_REQUIRED_PATTERNS = frozenset({
    "ctr_gap", "ctr_opportunity", "content_opportunity", "zero_click_alert",
    "cro_opportunity", "bounce_cro_alert", "pagespeed_urgent", "pagespeed_improve",
    "mobile_ctr_gap", "decline_alert", "organic_leads_leak", "ads_spend_low_leads",
    "crawl_missing_title", "crawl_missing_h1", "crawl_missing_meta",
    "crawl_thin_content", "crawl_broken_pages",
    "local_onsite",
})

# Playbook patterns that are human-only (don't require target_url for critique)
_HUMAN_ONLY_PATTERNS = frozenset({"leads_revenue_leak", "error_spike_alert"})

# Local SEO patterns — require explicit in_area geo when service area is configured
_LOCAL_SEO_PLAYBOOKS = frozenset({"local_onsite"})
_GEO_REASON_PREFIX = "geo:"


def _policy_check(action: dict, sa: Optional[ServiceArea] = None) -> Optional[str]:
    """Return rejection reason if action fails policy, else None."""
    title = str(action.get("title") or "")
    playbook = str(action.get("playbook_pattern") or "")
    category = str(action.get("category") or "")
    target_url = str(action.get("target_url") or "")
    evidence = str(action.get("evidence") or "")
    insight_id = action.get("insight_id")
    target_query = str(action.get("target_query") or "").strip()

    # Unknown playbook pattern (not in allowed catalog)
    if playbook and playbook not in _ALLOWED_PLAYBOOK_PATTERNS:
        return f"unknown playbook_pattern '{playbook}' — not in allowed catalog"

    # Missing insight_id (should always be set in Phase 2)
    if insight_id is None:
        return "missing insight_id — every action must link to an insight"

    # Missing target_url for fix patterns (except human-only)
    if playbook in _TARGET_REQUIRED_PATTERNS and playbook not in _HUMAN_ONLY_PATTERNS:
        if not target_url.startswith("http"):
            return f"missing target_url for playbook {playbook}"

    # Geo hard gate: OOA / excluded must stay dropped; local SEO needs explicit in_area
    if sa and sa.configured and target_query:
        geo = classify_query_geo(target_query, sa)
        is_local = playbook in _LOCAL_SEO_PLAYBOOKS or category == "local_seo"
        if geo in ("out_of_area", "excluded"):
            return f"{_GEO_REASON_PREFIX} query is {geo} — do not prescribe"
        if is_local and geo != "in_area":
            return f"{_GEO_REASON_PREFIX} local SEO requires in_area (got {geo})"

    # Pattern match against title + evidence + playbook
    for pat, reason in _REJECT_PATTERNS:
        blob = f"{title} {evidence} {playbook} {category}"
        if pat.search(blob):
            return reason

    return None


def filter_rejected_actions(actions: list[dict], reviewed: list) -> list[dict]:
    """Drop actions whose matching review entry has reject=true. Pure helper for tests."""
    if not isinstance(actions, list) or not actions:
        return []
    if not isinstance(reviewed, list) or len(reviewed) != len(actions):
        return actions
    kept = []
    for action, review in zip(actions, reviewed):
        if not isinstance(action, dict):
            continue
        reject = False
        if isinstance(review, dict):
            reject = bool(review.get("reject"))
        if not reject:
            kept.append(action)
    return kept


def critique_action_list(
    context: str,
    actions: list[dict],
    *,
    service_area: Optional[ServiceArea] = None,
    client: Any = None,
) -> list[dict]:
    """Run policy check + LLM critique on an action list; return filtered actions.

    Fail-soft restores policy-kept actions when LLM critique fails — but never
    re-introduces geo-rejected (OOA) local SEO actions.
    """
    if not actions:
        return actions

    sa = service_area
    if sa is None and client is not None:
        sa = parse_service_area(client)

    _critique_stats_lock.acquire(timeout=5)
    try:
        _critique_stats["call_count"] += 1
    finally:
        _critique_stats_lock.release()
    total_in = len(actions)

    # Deterministic policy pass first
    policy_kept: list[dict] = []
    geo_rejected: list[dict] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        reason = _policy_check(action, sa)
        if reason:
            logger.info("Policy rejected action %r: %s", action.get("title", "")[:80], reason)
            _critique_stats_lock.acquire()
            try:
                _critique_stats["policy_rejected"] += 1
                by_reason = _critique_stats["by_reason"]
                key = reason[:80]
                by_reason[key] = by_reason.get(key, 0) + 1
            finally:
                _critique_stats_lock.release()
            if reason.startswith(_GEO_REASON_PREFIX):
                geo_rejected.append(action)
            continue
        policy_kept.append(action)

    _critique_stats_lock.acquire()
    try:
        _critique_stats["total_actions"] += total_in
    finally:
        _critique_stats_lock.release()

    if not policy_kept:
        # Fail-soft: keep one non-geo action if any exist; never revive geo-rejected.
        rescue = [a for a in actions if isinstance(a, dict) and a not in geo_rejected]
        if rescue:
            logger.warning("All actions rejected by policy — keeping 1 non-geo action")
            policy_kept = [rescue[0]]
            _critique_stats_lock.acquire()
            try:
                _critique_stats["policy_rejected"] -= 1
            finally:
                _critique_stats_lock.release()
        else:
            logger.warning("All actions geo-rejected — returning empty (no fail-soft revive)")
            return []

    try:
        raw = complete(
            system=CRITIQUE_ACTIONS_PROMPT,
            user=f"SOURCE CONTEXT:\n{context}\n\nACTIONS:\n{json.dumps(policy_kept)}",
            max_tokens=4096,
            json_mode=True,
            temperature=0.0,
            purpose="critique_actions",
        )
        if not raw:
            logger.warning("Action critique returned empty — keeping policy-kept actions")
            _critique_stats_lock.acquire()
            try:
                _critique_stats["accepted"] += len(policy_kept)
            finally:
                _critique_stats_lock.release()
            return policy_kept
        reviewed = parse_json_payload(raw, expect=list)
        if isinstance(reviewed, dict) and isinstance(reviewed.get("actions"), list):
            reviewed = reviewed["actions"]
        if not isinstance(reviewed, list):
            logger.warning("Action critique parse was not a list — keeping policy-kept")
            _critique_stats_lock.acquire()
            try:
                _critique_stats["accepted"] += len(policy_kept)
            finally:
                _critique_stats_lock.release()
            return policy_kept
        kept = filter_rejected_actions(policy_kept, reviewed)
        accepted = len(kept)
        dropped = len(policy_kept) - accepted
        _critique_stats_lock.acquire()
        try:
            _critique_stats["llm_rejected"] += dropped
            _critique_stats["accepted"] += accepted
        finally:
            _critique_stats_lock.release()
        if dropped:
            logger.info("Action critique dropped %s unsupported action(s)", dropped)
        _log_critique_rejection_rate_if_due()
        # Fail-soft empty LLM result → policy_kept (already excludes geo-rejected)
        return kept if kept else policy_kept
    except Exception as e:
        logger.warning("Action critique failed — keeping policy-kept: %s", e)
        _critique_stats_lock.acquire()
        try:
            _critique_stats["accepted"] += len(policy_kept)
        finally:
            _critique_stats_lock.release()
        return policy_kept


def critique_brief_dict(context: str, brief_data: dict) -> Optional[dict]:
    """
    Critique a content brief object.
    Returns brief_data if accepted, None if explicitly rejected,
    or brief_data on critique failure (fail-soft).
    """
    if not isinstance(brief_data, dict):
        return brief_data
    try:
        raw = complete(
            system=CRITIQUE_BRIEF_PROMPT,
            user=f"SOURCE CONTEXT:\n{context}\n\nBRIEF:\n{json.dumps(brief_data)}",
            max_tokens=1024,
            json_mode=True,
            temperature=0.0,
            purpose="critique_brief",
        )
        if not raw:
            logger.warning("Brief critique returned empty — keeping original brief")
            return brief_data
        reviewed = parse_json_payload(raw, expect=dict)
        if not isinstance(reviewed, dict):
            return brief_data
        if reviewed.get("reject"):
            logger.info(
                "Brief critique rejected brief: %s",
                reviewed.get("reason") or "unsupported evidence",
            )
            return None
        return brief_data
    except Exception as e:
        logger.warning("Brief critique failed — keeping original: %s", e)
        return brief_data


def critique_rejection_rate() -> dict[str, Any]:
    _critique_stats_lock.acquire()
    try:
        stats = {
            "total_actions": _critique_stats["total_actions"],
            "policy_rejected": _critique_stats["policy_rejected"],
            "llm_rejected": _critique_stats["llm_rejected"],
            "accepted": _critique_stats["accepted"],
            "call_count": _critique_stats["call_count"],
            "rejection_rate_pct": 0.0,
            "top_reasons": sorted(
                _critique_stats["by_reason"].items(),
                key=lambda x: -x[1],
            )[:5],
        }
    finally:
        _critique_stats_lock.release()
    total = stats["total_actions"]
    if total > 0:
        rejected = stats["policy_rejected"] + stats["llm_rejected"]
        stats["rejection_rate_pct"] = round(rejected / total * 100, 1)
    return stats


def _log_critique_rejection_rate_if_due() -> None:
    _critique_stats_lock.acquire()
    try:
        due = _critique_stats["call_count"] % CRITIQUE_REJECTION_RATE_LOG_INTERVAL == 0
    finally:
        _critique_stats_lock.release()
    if not due:
        return
    rate = critique_rejection_rate()
    pct = rate["rejection_rate_pct"]
    logger.info(
        "Critique rejection rate: %.1f%% (%s policy + %s llm rejected / %s total, %s calls)",
        pct,
        rate["policy_rejected"],
        rate["llm_rejected"],
        rate["total_actions"],
        rate["call_count"],
    )
    if pct > CRITIQUE_REJECTION_RATE_WARN_THRESHOLD:
        top = rate.get("top_reasons") or []
        reason_str = ", ".join(f"{r}:{c}" for r, c in top[:3])
        logger.warning(
            "HIGH critique rejection rate (%.1f%% > %s%% threshold) — prompts/rules may still "
            "be generating bad actions. Top reasons: %s",
            pct,
            CRITIQUE_REJECTION_RATE_WARN_THRESHOLD,
            reason_str or "n/a",
        )


def reset_critique_stats() -> None:
    _critique_stats_lock.acquire()
    try:
        _critique_stats["total_actions"] = 0
        _critique_stats["policy_rejected"] = 0
        _critique_stats["llm_rejected"] = 0
        _critique_stats["accepted"] = 0
        _critique_stats["call_count"] = 0
        _critique_stats["by_reason"].clear()
    finally:
        _critique_stats_lock.release()
