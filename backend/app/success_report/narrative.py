"""Narrative quality checks and monthly AI summary generation."""
from __future__ import annotations

import calendar
import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Client
from app.ai_summarizer import parse_narrative, strip_markdown
from app.ai_client import ai_configured, complete
from app.marketing_knowledge import with_marketing_knowledge
from app.success_report.branding import _esc
from app.success_report.metrics import _has_meaningful_period_data

logger = logging.getLogger(__name__)

def _render_narrative_html(raw: Optional[str], heading: str = "Executive summary") -> str:
    if not raw:
        return ""
    parsed = parse_narrative(raw)
    if parsed.get("priorities"):
        cards = []
        for p in parsed["priorities"]:
            actions = "".join(f"<li>{_esc(a)}</li>" for a in p.get("actions") or [])
            measure = (
                f"<p class='measure'><strong>How we'll know it worked:</strong> {_esc(p.get('measure'))}</p>"
                if p.get("measure")
                else ""
            )
            issue = f"<p class='issue'>{_esc(p.get('issue'))}</p>" if p.get("issue") else ""
            cards.append(
                "<div class='priority'>"
                f"<div class='priority-head'><span class='num'>#{_esc(p.get('priority'))}</span>"
                f"<strong>{_esc(p.get('title'))}</strong>"
                f"<span class='sev'>{_esc(p.get('severity'))}</span></div>"
                f"{issue}"
                f"<ul>{actions}</ul>"
                f"{measure}"
                "</div>"
            )
        headline = (
            f"<p class='headline'>{_esc(parsed['headline'])}</p>" if parsed.get("headline") else ""
        )
        return f"<h2>{_esc(heading)}</h2>{headline}{''.join(cards)}"

    body = strip_markdown(raw)
    return f"<h2>{_esc(heading)}</h2><div class='narrative'>{_esc(body)}</div>"

def _narrative_is_low_quality(text: str) -> bool:
    """Reject repetitive / scorecard-spam model output."""
    cleaned = (text or "").strip()
    if len(cleaned) < 40:
        return True
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    if len(lines) >= 6:
        unique_ratio = len(set(lines)) / len(lines)
        if unique_ratio < 0.45:
            return True
    na_hits = sum(1 for ln in lines if "n/a vs prior" in ln.lower())
    if na_hits >= 3:
        return True
    # Fake scorecard loops like "Overall: 0.0 (n/a vs prior month)"
    score_labels = ("overall:", "people:", "tasks:", "issues:", "risk:", "next:")
    score_hits = sum(1 for ln in lines if ln.lower().startswith(score_labels))
    if score_hits >= 4:
        return True
    # Same line repeated many times in a single blob
    for ln in set(lines):
        if len(ln) > 12 and cleaned.count(ln) >= 4:
            return True
    return False

def generate_monthly_summary(
    db: Session,
    client_id: int,
    year: int,
    month: int,
    kpis: list[dict],
    work: dict,
    wins: list[dict],
    *,
    proven_levers: Optional[list[dict]] = None,
    funnel_stages: Optional[list[dict]] = None,
    baseline_deltas: Optional[list[dict]] = None,
    next_actions: Optional[list[dict]] = None,
) -> Optional[str]:
    """Period-scoped executive pack: headline + what changed / did / proved / next."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return None

    month_name = calendar.month_name[month]
    meaningful = _has_meaningful_period_data(kpis, work, wins)
    active_kpis = [
        k for k in kpis
        if (k.get("current") or 0) != 0
        or (k.get("previous") or 0) != 0
        or k.get("change_pct") is not None
    ]
    up = [k for k in active_kpis if (k.get("change_pct") or 0) > 0]
    down = [k for k in active_kpis if (k.get("change_pct") or 0) < 0]
    proven_levers = proven_levers or []
    funnel_stages = funnel_stages or []
    baseline_deltas = baseline_deltas or []
    next_actions = next_actions or []

    def _structured_template() -> str:
        if not meaningful:
            return (
                f"Headline: {client.name} does not yet have enough synced data or completed work "
                f"for {month_name} {year} to report results.\n\n"
                "What changed: Connect data sources and sync so people who found you, visits, "
                "and important actions can be measured.\n\n"
                "What we did: No completed playbook work in this period yet.\n\n"
                "What we proved: No attributed wins yet.\n\n"
                "What's next: Sync connectors, complete at least one fix, then regenerate this month."
            )
        headline_bits = []
        if wins:
            headline_bits.append(
                f"we proved {len(wins)} attributed win{'s' if len(wins) != 1 else ''}"
            )
        # Prefer real prior-period moves; ignore missing priors (no fake +100%)
        if up:
            headline_bits.append(
                f"{up[0]['label']} moved {up[0]['change_pct']:+.1f}% vs prior"
            )
        elif baseline_deltas:
            bd = next(
                (d for d in baseline_deltas if d.get("change_pct") is not None),
                None,
            )
            if bd:
                headline_bits.append(
                    f"{bd['label']} is {bd['change_pct']:+.1f}% vs engagement start"
                )
        if work.get("tasks_completed"):
            headline_bits.append(
                f"we shipped {work.get('tasks_completed')} work item"
                f"{'s' if work.get('tasks_completed') != 1 else ''}"
            )
        diagnostic = (
            not wins
            and not work.get("tasks_completed")
            and not proven_levers
        )
        if diagnostic:
            headline = (
                f"{month_name} {year} is a diagnostic / kickoff read for {client.name} — "
                "issues and prescriptions are identified, but nothing has been executed or proven yet."
            )
        else:
            headline = (
                f"In {month_name} {year}, "
                + ("; ".join(headline_bits) if headline_bits else "we made steady progress")
                + f" for {client.name}."
            )
        changed = []
        for k in up[:2]:
            changed.append(f"{k['label']} {k['change_pct']:+.1f}% vs prior")
        for k in down[:1]:
            changed.append(f"{k['label']} {k['change_pct']:+.1f}% vs prior (watching)")
        for d in baseline_deltas[:3]:
            if d.get("change_pct") is not None:
                changed.append(f"{d['label']} {d['change_pct']:+.1f}% vs engagement start")
        drop = next(
            (
                s
                for s in funnel_stages
                if not s.get("unreliable")
                and s.get("dropoff") is not None
                and (s.get("dropoff") or 0) >= 20
            ),
            None,
        )
        if drop:
            changed.append(f"funnel drop-off at {drop.get('stage')} ({drop.get('dropoff')}%)")
        unreliable = next((s for s in funnel_stages if s.get("unreliable")), None)
        if unreliable:
            changed.append(
                f"{unreliable.get('stage')} cannot be scored as a conversion rate "
                "(search/ad clicks vs all-channel sessions)"
            )
        did = [
            f"{work.get('tasks_completed', 0)} tasks completed",
            f"{work.get('insights_resolved', 0)} issues resolved",
        ]
        for lev in proven_levers[:3]:
            title = lev.get("title") or "Growth lever"
            did.append(f"pulled lever: {title}")
        proved = []
        for w in wins[:3]:
            proved.append(f"+{w.get('avg_primary_metric_change')}% — {w.get('label')}")
        if not proved:
            proved.append("No attributed wins measured in this period yet.")
        nxt = []
        for a in next_actions[:3]:
            nxt.append(a.get("title") or a.get("why_it_matters") or "Continue priority plan")
        open_n = work.get("insights_open") or 0
        if open_n and not nxt:
            nxt.append(f"Close {open_n} remaining open issue{'s' if open_n != 1 else ''}")
        if not nxt:
            nxt.append("Continue the highest-priority fixes from the active plan.")
        return (
            f"Headline: {headline}\n\n"
            f"What changed: {'; '.join(changed) if changed else 'Mixed or flat movement across tracked metrics.'}\n\n"
            f"What we did: {'; '.join(did)}.\n\n"
            f"What we proved: {'; '.join(proved)}\n\n"
            f"What's next: {'; '.join(nxt)}"
        )

    template = _structured_template()

    if not meaningful or not ai_configured():
        return template

    lines = [
        f"Write a client success executive pack for {client.name} covering {month_name} {year}.",
        "Audience: business owner, not a marketer. No jargon (avoid CTR, GSC, CVR, SERP).",
        "Output EXACTLY these five labeled sections, each 1–3 sentences, plain prose (no bullets):",
        "Headline:",
        "What changed:",
        "What we did:",
        "What we proved:",
        "What's next:",
        "Use only numbers from the data. Do not invent wins. Do not invent +100% growth when prior is n/a. "
        "If tasks completed and wins are both zero, frame this as a diagnostic/kickoff report — not a success story. "
        "Do not output scorecards or markdown.",
        "",
        "KPI changes (non-zero only):",
    ]
    if active_kpis:
        for k in active_kpis:
            ch = k.get("change_pct")
            ch_s = f"{ch:+.1f}%" if ch is not None else "n/a"
            lines.append(f"- {k['label']}: {k['current']} ({ch_s} vs prior month)")
    else:
        lines.append("- (no KPI movement this month)")
    lines.append(
        f"Work: {work.get('tasks_completed', 0)} tasks done, "
        f"{work.get('insights_resolved', 0)} issues resolved, "
        f"{work.get('insights_open', 0)} still open."
    )
    if wins:
        lines.append("Wins:")
        for w in wins[:5]:
            lines.append(f"- +{w.get('avg_primary_metric_change')}% — {w.get('label')}")
    else:
        lines.append("Wins: none attributed this month.")
    if proven_levers:
        lines.append("Proven levers:")
        for lev in proven_levers[:5]:
            lines.append(f"- {lev.get('title')}: {lev.get('impact_summary') or lev.get('fix') or ''}")
    if funnel_stages:
        lines.append("Funnel stages:")
        for s in funnel_stages[:6]:
            if s.get("unreliable"):
                lines.append(
                    f"- {s.get('stage')}: unreliable cross-source ratio "
                    f"({s.get('entered')} → {s.get('exited')}) — not a conversion rate"
                )
            else:
                lines.append(
                    f"- {s.get('stage')}: drop {s.get('dropoff')}%, "
                    f"conversion {s.get('conversion_rate')}%"
                )
    if baseline_deltas:
        lines.append("Vs engagement baseline:")
        for d in baseline_deltas[:5]:
            ch = d.get("change_pct")
            ch_s = f"{ch:+.1f}%" if ch is not None else "n/a"
            lines.append(f"- {d.get('label')}: {ch_s}")
    if next_actions:
        lines.append("Next actions from plan:")
        for a in next_actions[:5]:
            lines.append(f"- {a.get('title') or a.get('why_it_matters') or 'Action'}")

    profile_bits = ""
    try:
        profile = json.loads(client.profile_json or "{}")
        if profile.get("goals"):
            profile_bits = f" Client goals: {profile['goals']}."
        if profile.get("brand_voice"):
            profile_bits += f" Voice: {profile['brand_voice']}."
        sc = profile.get("success_contract") if isinstance(profile.get("success_contract"), dict) else None
        if sc and sc.get("primary_metric"):
            profile_bits += (
                f" Success contract: grow {sc.get('primary_metric')} by "
                f"+{sc.get('target_delta_pct', '?')}% over {sc.get('window_days', '?')} days."
            )
    except (json.JSONDecodeError, TypeError):
        pass

    try:
        raw = complete(
            system=with_marketing_knowledge(
                "You write structured monthly digital marketing success reports for business owners. "
                "Always output the five labeled sections: Headline, What changed, What we did, "
                "What we proved, What's next. Plain prose under each label. Concrete numbers only. "
                "No bullet lists, no markdown, no scorecards, no repeated lines."
                + profile_bits
            ),
            user="\n".join(lines),
            max_tokens=700,
            json_mode=False,
            temperature=0.3,
        )
        if raw and raw.strip():
            cleaned = strip_markdown(raw.strip())
            if not _narrative_is_low_quality(cleaned) and _narrative_has_structure(cleaned):
                return cleaned
            if not _narrative_is_low_quality(cleaned):
                # Accept prose without labels if quality passes
                return cleaned
            logger.warning(
                "Monthly summary AI output rejected as low quality for client %s (%s-%02d)",
                client_id,
                year,
                month,
            )
    except Exception as e:
        logger.warning("Monthly summary AI failed: %s", e)
    return template


def _narrative_has_structure(text: str) -> bool:
    lower = (text or "").lower()
    markers = ("headline", "what changed", "what we did", "what we proved", "what's next", "whats next")
    return sum(1 for m in markers if m in lower) >= 3
