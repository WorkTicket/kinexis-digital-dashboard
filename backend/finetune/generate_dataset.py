"""
Generate a labeled SFT dataset for Kinexis marketing fine-tuning.

Produces ShareGPT / chat JSONL matching the live action-plan, weekly-brief,
and content-brief schemas — grounded in the same playbook patterns as
marketing_knowledge.py.

Usage:
  py -3.12 generate_dataset.py
  py -3.12 generate_dataset.py --n-per-pattern 12 --out data/train.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

# Keep system prompts aligned with production (without the long playbook —
# weights should learn the behavior; runtime can still inject the playbook).
ACTION_SYSTEM = """You create detailed, data-driven optimization plans for client websites.
Apply the Kinexis playbook: diagnose which success metric is broken, then prescribe the matching tactic.

For each client situation, output a JSON array of 5–8 recommended actions. Each action must have:
  - "title", "category", "priority_score", "success_metric", "why_it_matters",
  - "estimated_impact", "effort", "steps", "metrics_to_watch", "expected_timeline",
  - "evidence", "playbook_pattern"
Output valid JSON only, no markdown."""

WEEKLY_SYSTEM = (
    "You write client-ready weekly briefs. Apply the Kinexis playbook: "
    "each priority must target a success metric and prescribe the matching tactic. "
    "Respond with valid JSON only."
)

BRIEF_SYSTEM = """Generate a detailed, publish-ready content brief from SEO and insight data.
Apply the Kinexis playbook: content exists to move impressions → clicks → key_events.
Output valid JSON only with keyword, search_intent, success_metric, title, meta_description,
outline, word_count, related_keywords, serp_notes, cta_suggestion, internal_links, differentiation."""

INDUSTRIES = [
    ("Summit Dental Group", "dental", "summitdental.example"),
    ("Northline HVAC", "home services", "northlinehvac.example"),
    ("BrightPath Legal", "law firm", "brightpathlegal.example"),
    ("Harbor Pet Clinic", "veterinary", "harborpet.example"),
    ("Apex Roofing Co", "roofing", "apexroofing.example"),
    ("Lumen Eye Care", "optometry", "lumeneeye.example"),
    ("Cascade Plumbing", "plumbing", "cascadeplumb.example"),
    ("Verde Landscaping", "landscaping", "verdeland.example"),
    ("Pulse Fitness Studio", "fitness", "pulsefit.example"),
    ("Oak & Stone Interiors", "interior design", "oakstone.example"),
    ("ClearWater Pools", "pool service", "clearwaterpools.example"),
    ("Metro Auto Care", "auto repair", "metroautocare.example"),
]

PATTERNS = [
    "low_ctr",
    "striking_distance",
    "zero_click_waste",
    "impression_drop",
    "cro_leak",
    "engagement_gap",
    "mobile_gap",
    "speed",
    "local_seo",
    "content_gap",
]


def _url(domain: str, path: str) -> str:
    return f"https://www.{domain}/{path.strip('/')}/"


def _ctx_header(name: str, industry: str, domain: str) -> str:
    return (
        f"Client: {name}\n"
        f"Industry: {industry}\n"
        f"Website: https://www.{domain}/\n"
        f"Goals: increase qualified leads and organic clicks\n"
        f"Brand voice: clear, trustworthy, local expertise\n"
        f"Do not touch: /privacy/, /careers/\n"
    )


def _metric_block(clicks: int, impr: int, ctr: float, pos: float, sessions: int, events: int) -> str:
    cvr = (events / sessions * 100) if sessions else 0
    return (
        "=== METRIC TOTALS (last 28 days) ===\n"
        f"gsc.clicks={clicks}  gsc.impressions={impr}  gsc.ctr={ctr:.2f}%  gsc.position={pos:.1f}\n"
        f"ga4.sessions={sessions}  ga4.key_events={events}  ga4.cvr={cvr:.2f}%\n"
    )


def scenario_for(pattern: str, name: str, industry: str, domain: str, rng: random.Random) -> dict:
    """Build user context + gold assistant JSON for one playbook pattern."""
    path_map = {
        "low_ctr": "services/consultation",
        "striking_distance": f"blog/{industry.replace(' ', '-')}-guide",
        "zero_click_waste": "services/pricing",
        "impression_drop": f"services/{industry.split()[0].lower()}",
        "cro_leak": "contact",
        "engagement_gap": f"resources/{industry.replace(' ', '-')}-tips",
        "mobile_gap": "book-online",
        "speed": "services",
        "local_seo": f"locations/{domain.split('.')[0]}-near-me",
        "content_gap": f"blog/how-to-choose-{industry.replace(' ', '-')}",
    }
    page = _url(domain, path_map[pattern])
    q_base = {
        "low_ctr": f"best {industry} near me",
        "striking_distance": f"how to choose a {industry} company",
        "zero_click_waste": f"{industry} cost",
        "impression_drop": f"{industry} services",
        "cro_leak": f"{industry} consultation",
        "engagement_gap": f"{industry} tips",
        "mobile_gap": f"book {industry} appointment",
        "speed": f"{industry} company",
        "local_seo": f"{industry} in austin",
        "content_gap": f"{industry} checklist 2026",
    }[pattern]

    clicks = rng.randint(180, 900)
    impr = rng.randint(8000, 45000)
    pos = round(rng.uniform(4.5, 18.0), 1)
    ctr = round(clicks / impr * 100, 2) if impr else 1.0
    sessions = rng.randint(1200, 8000)
    events = rng.randint(20, 180)

    if pattern == "low_ctr":
        pos, ctr, clicks, impr = 5.2, 1.1, 140, 12700
        insights = [
            f"[HIGH] low_ctr: {page} ranks ~pos {pos} for \"{q_base}\" with CTR {ctr}% "
            f"({clicks} clicks / {impr} impressions) — well below niche ~3–5% CTR.",
        ]
        metrics = _metric_block(clicks, impr, ctr, pos, sessions, events)
        actions = [
            {
                "title": f"Rewrite title/meta on {path_map[pattern]} for CTR",
                "category": "content",
                "priority_score": 92,
                "success_metric": "gsc.ctr",
                "why_it_matters": (
                    f"\"{q_base}\" already earns ~{impr} impressions at position {pos}, but CTR is only "
                    f"{ctr}%. Closing even half the gap to a 3% CTR unlocks meaningful clicks without new rankings."
                ),
                "estimated_impact": f"+40–80% CTR on \"{q_base}\" / {page} in 21–28 days",
                "effort": "low",
                "steps": [
                    f"Audit current title/meta on {page} for truncation and benefit clarity",
                    f"Draft 3 title variants with year, number, and primary benefit for \"{q_base}\"",
                    "Ship winning title + meta; request indexing for the URL",
                    "Add FAQ schema if SERP shows PAA for this query cluster",
                ],
                "metrics_to_watch": [f"gsc.ctr:{q_base}", f"gsc.clicks:{page}"],
                "expected_timeline": "2–4 weeks to see CTR movement",
                "evidence": f"GSC: pos {pos}, CTR {ctr}%, {impr} impressions on \"{q_base}\"",
                "playbook_pattern": "low_ctr",
            },
            {
                "title": f"A/B SERP titles on top impression URLs",
                "category": "content",
                "priority_score": 78,
                "success_metric": "gsc.clicks",
                "why_it_matters": (
                    f"Same CTR leak pattern likely affects sibling service pages. Fixing the cluster compounds click growth."
                ),
                "estimated_impact": f"+12–20% clicks on service cluster in 30 days",
                "effort": "medium",
                "steps": [
                    "Export top 10 URLs by impressions with CTR below niche median",
                    "Rewrite titles to match SERP format (how-to / list / price)",
                    "Track CTR WoW per URL in GSC",
                ],
                "metrics_to_watch": ["gsc.ctr:service_cluster", "gsc.clicks"],
                "expected_timeline": "3–5 weeks",
                "evidence": f"Primary leak on {page}; cluster likely under-clicking",
                "playbook_pattern": "low_ctr",
            },
        ]
    elif pattern == "striking_distance":
        pos, impr, clicks, ctr = 14.2, 9200, 210, 2.28
        insights = [
            f"[HIGH] striking_distance: \"{q_base}\" at position {pos} with {impr} impressions — "
            f"content depth and internal links can push into top 8.",
        ]
        metrics = _metric_block(clicks, impr, ctr, pos, sessions, events)
        actions = [
            {
                "title": f"Expand {path_map[pattern]} for striking-distance query",
                "category": "content",
                "priority_score": 90,
                "success_metric": "gsc.position",
                "why_it_matters": (
                    f"\"{q_base}\" sits at ~pos {pos} with {impr} impressions. Moving into top 8 typically "
                    f"unlocks a step-change in clicks for informational commercial queries."
                ),
                "estimated_impact": f"Move \"{q_base}\" from ~pos {pos} → top 8; +80–150 clicks/mo",
                "effort": "medium",
                "steps": [
                    f"Map related queries ranking on {page}; list missing subtopics",
                    f"Add 400–700 words covering gaps with examples for {industry}",
                    f"Add 3 internal links from high-authority pages with descriptive anchors to {page}",
                    "Add author bio + updated date for E-E-A-T",
                    "Format one section as featured-snippet / PAA answer",
                ],
                "metrics_to_watch": [f"gsc.position:{q_base}", f"gsc.clicks:{q_base}"],
                "expected_timeline": "3–6 weeks for position movement",
                "evidence": f"Position {pos}, {impr} impressions, only {clicks} clicks",
                "playbook_pattern": "striking_distance",
            },
        ]
    elif pattern == "cro_leak":
        sessions, events, clicks, impr = 6400, 38, 520, 18000
        cvr = events / sessions * 100
        insights = [
            f"[HIGH] cro_leak: Sessions up on {page} but key_events flat ({events} events / "
            f"{sessions} sessions = {cvr:.2f}% CVR). Traffic is not converting.",
        ]
        metrics = _metric_block(clicks, impr, 2.9, 7.1, sessions, events)
        actions = [
            {
                "title": f"Fix above-fold CTA and form friction on {path_map[pattern]}",
                "category": "cro",
                "priority_score": 94,
                "success_metric": "ga4.key_events",
                "why_it_matters": (
                    f"{page} receives high sessions ({sessions}) but only {events} key events "
                    f"({cvr:.2f}% CVR). This is a conversion leak, not a traffic problem."
                ),
                "estimated_impact": f"+0.4–0.9pp CVR on {page} in 30–45 days",
                "effort": "medium",
                "steps": [
                    f"Place primary CTA above the fold on {page}; match query/ad intent in H1",
                    "Cut form to essential fields only; add trust (reviews, guarantee)",
                    "Add sticky mobile CTA; remove competing nav distractions",
                    "Verify key_event fires on submit in GA4 debug",
                ],
                "metrics_to_watch": [f"ga4.cvr:{page}", f"ga4.key_events:{page}"],
                "expected_timeline": "2–4 weeks after ship",
                "evidence": f"{sessions} sessions → {events} key_events on {page}",
                "playbook_pattern": "cro_leak",
            },
        ]
    elif pattern == "mobile_gap":
        insights = [
            f"[HIGH] mobile_gap: Mobile CTR 1.2% vs desktop 3.8% on {page}; mobile key_events lag.",
        ]
        metrics = (
            _metric_block(410, 22000, 1.86, 6.4, 5100, 55)
            + "Device split: mobile CTR 1.2% / desktop CTR 3.8%; mobile CVR ~40% of desktop.\n"
        )
        actions = [
            {
                "title": f"Close mobile CTR/CVR gap on {path_map[pattern]}",
                "category": "ux",
                "priority_score": 88,
                "success_metric": "gsc.ctr",
                "why_it_matters": (
                    f"Mobile drives most impressions but CTR is 1.2% vs 3.8% desktop on {page}. "
                    f"Title length and tap/form UX are suppressing mobile clicks and events."
                ),
                "estimated_impact": "+30–60% mobile CTR and +20–40% mobile key_events in 30 days",
                "effort": "medium",
                "steps": [
                    "Shorten title for mobile SERP truncation; front-load benefit",
                    f"Increase tap targets and simplify form on {page}",
                    "Prioritize mobile LCP on this money URL",
                    "Remove intrusive interstitials on entry",
                ],
                "metrics_to_watch": ["gsc.ctr:mobile", f"ga4.key_events:mobile:{page}"],
                "expected_timeline": "2–4 weeks",
                "evidence": "Mobile CTR 1.2% vs desktop 3.8%",
                "playbook_pattern": "mobile_gap",
            },
        ]
    elif pattern == "speed":
        insights = [
            f"[MEDIUM] speed: {page} performance_score ~42; LCP > 4s on mobile — hurting CTR and CVR.",
        ]
        metrics = _metric_block(360, 15000, 2.4, 8.0, 4200, 48)
        actions = [
            {
                "title": f"Fix LCP/CWV on money URL {path_map[pattern]}",
                "category": "speed",
                "priority_score": 85,
                "success_metric": "ga4.cvr",
                "why_it_matters": (
                    f"Poor LCP on {page} suppresses both engagement and conversion. Fix money URLs first."
                ),
                "estimated_impact": "LCP <2.5s; +10–20% CVR on this URL in 30 days",
                "effort": "medium",
                "steps": [
                    f"Compress/lazy-load hero image on {page}; preload LCP element",
                    "Defer non-critical JS; subset fonts",
                    "Fix CLS from late-loading banners",
                    "Re-test PageSpeed mobile; confirm key_events stable",
                ],
                "metrics_to_watch": ["pagespeed:mobile", f"ga4.cvr:{page}"],
                "expected_timeline": "1–3 weeks",
                "evidence": "performance_score ~42, LCP >4s mobile",
                "playbook_pattern": "speed",
            },
        ]
    elif pattern == "content_gap":
        insights = [
            f"[MEDIUM] content_gap: Rising query \"{q_base}\" has impressions but no dedicated intent-matched page.",
        ]
        metrics = _metric_block(95, 6100, 1.56, 22.0, 2800, 40)
        actions = [
            {
                "title": f"Publish intent-matched page for \"{q_base}\"",
                "category": "content",
                "priority_score": 82,
                "success_metric": "gsc.impressions",
                "why_it_matters": (
                    f"\"{q_base}\" is rising with demand but no strong landing asset. Capturing impressions "
                    f"now sets up clicks and later key_events."
                ),
                "estimated_impact": "New impressions in 14d; clicks in 28d; assisted key_events in 45–60d",
                "effort": "high",
                "steps": [
                    f"Brief and publish page targeting \"{q_base}\" + cluster",
                    f"Internal link from hub pages to {_url(domain, path_map[pattern])}",
                    "Include CTA path to contact/booking conversion page",
                    "Submit URL for indexing; track impressions weekly",
                ],
                "metrics_to_watch": [f"gsc.impressions:{q_base}", f"gsc.clicks:{q_base}"],
                "expected_timeline": "4–8 weeks for traction",
                "evidence": f"Rising impressions on \"{q_base}\" without dedicated page",
                "playbook_pattern": "content_gap",
            },
        ]
    elif pattern == "impression_drop":
        insights = [
            f"[HIGH] impression_drop: Impressions for \"{q_base}\" down 28% WoW; possible cannibalization "
            f"between {page} and a blog URL.",
        ]
        metrics = _metric_block(300, 11000, 2.7, 11.5, 3500, 42)
        actions = [
            {
                "title": f"Resolve cannibalization for \"{q_base}\"",
                "category": "technical_seo",
                "priority_score": 87,
                "success_metric": "gsc.impressions",
                "why_it_matters": (
                    f"Impression decline on \"{q_base}\" often means split equity across URLs. "
                    f"Consolidating restores visibility."
                ),
                "estimated_impact": "+15–30% impressions recovery on query cluster in 21–35 days",
                "effort": "medium",
                "steps": [
                    "List all URLs ranking for the query; pick one canonical money page",
                    "301 or consolidate thin duplicates; differentiate remaining pages",
                    f"Refresh {page} content and internal links to the winner",
                    "Monitor coverage/indexation for the canonical URL",
                ],
                "metrics_to_watch": [f"gsc.impressions:{q_base}", f"gsc.position:{q_base}"],
                "expected_timeline": "3–5 weeks",
                "evidence": "Impressions −28% WoW with multi-URL ranking",
                "playbook_pattern": "impression_drop",
            },
        ]
    elif pattern == "engagement_gap":
        insights = [
            f"[MEDIUM] engagement_gap: High sessions on {page} with elevated bounce and low engagement time.",
        ]
        metrics = _metric_block(440, 16000, 2.75, 7.8, 5800, 36)
        actions = [
            {
                "title": f"Fix intent mismatch and intro clarity on {path_map[pattern]}",
                "category": "ux",
                "priority_score": 80,
                "success_metric": "ga4.key_events",
                "why_it_matters": (
                    f"Traffic arrives but does not engage on {page}. Improving fit and next-step links "
                    f"recovers assisted conversions."
                ),
                "estimated_impact": "Lower bounce; +15–25% assisted key_events in 30 days",
                "effort": "medium",
                "steps": [
                    f"Rewrite intro on {page} to match top landing queries",
                    "Add internal links to next-step conversion content",
                    "Improve mobile layout and load speed of above-fold content",
                    "Prune or noindex thin pages attracting wrong queries",
                ],
                "metrics_to_watch": ["bounce_rate", f"ga4.key_events:{page}"],
                "expected_timeline": "2–4 weeks",
                "evidence": "High sessions + high bounce on landing URL",
                "playbook_pattern": "engagement_gap",
            },
        ]
    elif pattern == "local_seo":
        insights = [
            f"[HIGH] local_seo: Local queries like \"{q_base}\" under-click; GBP and location page gaps.",
        ]
        metrics = _metric_block(260, 14000, 1.86, 9.5, 3100, 70)
        actions = [
            {
                "title": f"Strengthen GBP + location page for \"{q_base}\"",
                "category": "local_seo",
                "priority_score": 89,
                "success_metric": "gsc.clicks",
                "why_it_matters": (
                    f"Local pack and \"{q_base}\" visibility drive calls/forms for {industry}. "
                    f"GBP completeness and unique location content move local clicks and key_events."
                ),
                "estimated_impact": "+20–40% local query clicks and +10–20 calls/forms in 30 days",
                "effort": "medium",
                "steps": [
                    "Complete GBP categories, services, photos, and weekly posts",
                    f"Expand {_url(domain, path_map[pattern])} with unique NAP-consistent content",
                    "Build service+city section only with unique proof (not doorway spam)",
                    "Request reviews; track call/form key_events",
                ],
                "metrics_to_watch": [f"gsc.clicks:{q_base}", "ga4.key_events:calls"],
                "expected_timeline": "3–5 weeks",
                "evidence": f"Local query \"{q_base}\" under-performing vs impression volume",
                "playbook_pattern": "local_seo",
            },
        ]
    else:  # zero_click_waste
        insights = [
            f"[HIGH] zero_click: {impr} impressions on \"{q_base}\" but only {clicks} clicks — weak SERP appeal "
            f"or intent mismatch on {page}.",
        ]
        metrics = _metric_block(120, 24000, 0.5, 4.8, 4000, 45)
        actions = [
            {
                "title": f"Fix SERP appeal + intent match for \"{q_base}\"",
                "category": "content",
                "priority_score": 91,
                "success_metric": "gsc.clicks",
                "why_it_matters": (
                    f"Huge impression volume with ~0.5% CTR means wasted visibility. Title/meta and intent "
                    f"alignment on {page} should convert impressions to clicks."
                ),
                "estimated_impact": f"+100–250 clicks/mo on \"{q_base}\" cluster in 30 days",
                "effort": "low",
                "steps": [
                    "Compare page intent vs query intent (info vs transactional)",
                    "Rewrite title/meta for benefit + specificity; match SERP format",
                    "If mismatch is structural, create intent-matched page and retarget internal links",
                    "Measure clicks uplift on the query cluster",
                ],
                "metrics_to_watch": [f"gsc.clicks:{q_base}", f"gsc.ctr:{q_base}"],
                "expected_timeline": "2–4 weeks",
                "evidence": f"{impr} impressions → {clicks} clicks on \"{q_base}\"",
                "playbook_pattern": "zero_click_waste",
            },
        ]

    # Pad to 5–6 actions with secondary supporting moves (still metric-tied)
    while len(actions) < 5:
        actions.append(
            {
                "title": f"Internal link boost to {path_map[pattern]}",
                "category": "link_building",
                "priority_score": 70 - len(actions),
                "success_metric": "gsc.position",
                "why_it_matters": (
                    f"Supporting internal links help the primary fix on {page} compound faster."
                ),
                "estimated_impact": f"+1–3 position lift assist on \"{q_base}\" in 30–45 days",
                "effort": "low",
                "steps": [
                    f"Find 3 relevant high-traffic pages on {domain}",
                    f"Add descriptive anchors pointing to {page}",
                    "Avoid exact-match spam; keep anchors natural",
                ],
                "metrics_to_watch": [f"gsc.position:{q_base}"],
                "expected_timeline": "3–5 weeks",
                "evidence": f"Primary opportunity on {page} needs link equity support",
                "playbook_pattern": pattern,
            }
        )

    user = (
        _ctx_header(name, industry, domain)
        + "\n"
        + metrics
        + "\n=== UNRESOLVED INSIGHTS (highest priority first) ===\n"
        + "\n".join(f"{i+1}. {t}" for i, t in enumerate(insights))
        + f"\n\nBased on the above, generate a detailed prioritized action plan for {name}. "
        "Include only actions that will meaningfully improve clicks, impressions, "
        "conversions, or revenue. Every action must cite evidence from the data."
    )

    return {
        "task": "action_plan",
        "pattern": pattern,
        "messages": [
            {"role": "system", "content": ACTION_SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": json.dumps(actions, ensure_ascii=False)},
        ],
    }


def weekly_example(pattern: str, name: str, industry: str, domain: str, rng: random.Random) -> dict:
    page = _url(domain, "services")
    q = f"best {industry} near me"
    plan = scenario_for(pattern, name, industry, domain, rng)
    # Reuse first action as weekly priority seed
    primary = json.loads(plan["messages"][2]["content"])[0]
    payload = {
        "headline": (
            f"{name}: prioritize {primary['success_metric']} — "
            f"{primary['playbook_pattern'].replace('_', ' ')} on key URLs this week."
        ),
        "priorities": [
            {
                "priority": 1,
                "title": primary["title"][:60],
                "severity": "high",
                "success_metric": primary["success_metric"],
                "issue": primary["why_it_matters"],
                "actions": primary["steps"][:3],
                "measure": primary["estimated_impact"],
            },
            {
                "priority": 2,
                "title": f"Track {primary['success_metric']} on {page}",
                "severity": "medium",
                "success_metric": primary["success_metric"],
                "issue": f"Need a clean baseline so we can attribute movement after the fix ships.",
                "actions": [
                    f"Snapshot current {primary['success_metric']} for the target URL/query",
                    "Note ship date of the primary fix",
                    "Compare 7–14 day post-ship delta",
                ],
                "measure": f"{primary['success_metric']} improves vs pre-ship baseline in 7–14 days",
            },
            {
                "priority": 3,
                "title": f"Support fix with internal links to money page",
                "severity": "medium",
                "success_metric": "gsc.position",
                "issue": "Primary metric fix compounds faster with internal equity.",
                "actions": [
                    f"Add 2–3 contextual links to {page}",
                    "Use descriptive anchors tied to the target query",
                ],
                "measure": "Position assist on target query within 21–35 days",
            },
            {
                "priority": 4,
                "title": "Protect conversion path while SEO ships",
                "severity": "low",
                "success_metric": "ga4.key_events",
                "issue": "SEO changes should not regress lead volume.",
                "actions": [
                    "Confirm key_event tagging still fires on contact/book flows",
                    "Watch CVR on the edited landing page after publish",
                ],
                "measure": "ga4.key_events stable or up WoW after changes",
            },
        ],
    }
    user = (
        f"You are writing a client-ready weekly analyst brief for {name} ({industry}).\n"
        + plan["messages"][1]["content"].split("Based on the above")[0]
        + "\nReturn JSON with headline + 4–5 priorities (success_metric, issue, actions, measure)."
    )
    return {
        "task": "weekly_brief",
        "pattern": pattern,
        "messages": [
            {"role": "system", "content": WEEKLY_SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }


def brief_example(name: str, industry: str, domain: str, rng: random.Random) -> dict:
    kw = f"{industry} checklist 2026"
    page = _url(domain, f"blog/{industry.replace(' ', '-')}-checklist")
    payload = {
        "keyword": kw,
        "search_intent": "informational",
        "success_metric": "gsc.impressions",
        "title": [
            f"{industry.title()} Checklist 2026: What to Verify Before You Hire",
            f"The Complete {industry.title()} Checklist (Free Download)",
            f"How to Choose {industry.title()}: 12-Point Checklist",
            f"{industry.title()} Buying Guide & Checklist for 2026",
            f"Avoid Costly Mistakes: {industry.title()} Checklist",
        ],
        "meta_description": (
            f"Use this {industry} checklist to compare providers, avoid surprises, and book with confidence. "
            f"Get the steps + CTA to schedule."
        )[:160],
        "outline": [
            {
                "h2": f"Why a {industry} checklist matters in 2026",
                "h3": ["Common costly mistakes", "What good looks like"],
                "notes": "Cite local proof; set up CTA later",
            },
            {
                "h2": "The 12-point checklist",
                "h3": ["Credentials", "Pricing transparency", "Reviews & guarantees"],
                "notes": "Scannable list for featured snippet",
            },
            {
                "h2": f"How to apply this checklist with {name}",
                "h3": ["What to prepare", "What happens next"],
                "notes": "Bridge to conversion CTA",
            },
        ],
        "word_count": 1600,
        "related_keywords": [
            f"best {industry}",
            f"{industry} cost",
            f"how to choose {industry}",
            f"{industry} near me",
            f"{industry} questions to ask",
            f"{industry} red flags",
            f"{industry} reviews",
            f"{industry} pricing",
            f"hire {industry}",
            f"{industry} guide",
        ],
        "serp_notes": [
            f"Target query \"{kw}\" shows listicle/checklist formats dominating",
            "Opportunity to win PAA with concise checklist answers",
            "Add year in title for CTR vs evergreen competitors",
        ],
        "cta_suggestion": f"Mid-article + end CTA to book consultation on {_url(domain, 'contact')} (drives ga4.key_events)",
        "internal_links": [_url(domain, "services"), _url(domain, "contact"), page],
        "differentiation": (
            f"Lead with practical local proof and a downloadable checklist; competitors stay generic. "
            f"Tie every section to a next step with {name}."
        ),
    }
    user = (
        f"Client: {name} (Industry: {industry})\n"
        f"=== INSIGHT THAT TRIGGERED THIS BRIEF ===\n"
        f"  Type: content_gap\n  Severity: medium\n"
        f"  Message: Rising query \"{kw}\" with impressions but no dedicated page.\n"
        f"  Keyword hint: {kw}\n\n"
        "Generate a complete, detailed content brief targeting the keyword/opportunity above."
    )
    return {
        "task": "content_brief",
        "pattern": "content_gap",
        "messages": [
            {"role": "system", "content": BRIEF_SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }


def build_dataset(n_per_pattern: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    for pattern in PATTERNS:
        for i in range(n_per_pattern):
            name, industry, domain = INDUSTRIES[(i + PATTERNS.index(pattern)) % len(INDUSTRIES)]
            # slight domain uniquifier so examples aren't identical
            domain_i = domain.replace(".example", f"{i}.example")
            rows.append(scenario_for(pattern, name, industry, domain_i, rng))
            if i % 2 == 0:
                rows.append(weekly_example(pattern, name, industry, domain_i, rng))
    for i in range(n_per_pattern * 2):
        name, industry, domain = INDUSTRIES[i % len(INDUSTRIES)]
        rows.append(brief_example(name, industry, domain.replace(".example", f"b{i}.example"), rng))
    rng.shuffle(rows)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate Kinexis SFT JSONL")
    ap.add_argument("--n-per-pattern", type=int, default=10, help="Action-plan examples per playbook pattern")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "data" / "train.jsonl")
    ap.add_argument("--val-ratio", type=float, default=0.1)
    args = ap.parse_args()

    rows = build_dataset(args.n_per_pattern, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    val_path = args.out.with_name("val.jsonl")

    n_val = max(1, int(len(rows) * args.val_ratio))
    val_rows = rows[:n_val]
    train_rows = rows[n_val:]

    def write_jsonl(path: Path, data: list[dict]) -> None:
        with path.open("w", encoding="utf-8") as f:
            for row in data:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    write_jsonl(args.out, train_rows)
    write_jsonl(val_path, val_rows)
    by_task: dict[str, int] = {}
    by_pat: dict[str, int] = {}
    for r in rows:
        by_task[r["task"]] = by_task.get(r["task"], 0) + 1
        by_pat[r["pattern"]] = by_pat.get(r["pattern"], 0) + 1
    print(f"Wrote {len(train_rows)} train -> {args.out}")
    print(f"Wrote {len(val_rows)} val   -> {val_path}")
    print(f"By task: {by_task}")
    print(f"By pattern: {by_pat}")


if __name__ == "__main__":
    main()
