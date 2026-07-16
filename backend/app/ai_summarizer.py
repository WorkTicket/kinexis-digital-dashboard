"""
Weekly AI summary using configured AI provider (Anthropic or Ollama).
Produces structured JSON priorities for clean client-ready reports.
"""

import json
import logging
import re
from datetime import date, timedelta
from typing import Any, Optional

from app.ai_client import ai_configured, complete, parse_json_payload
from app.ai_context import build_client_ai_context
from app.marketing_knowledge import with_marketing_knowledge
from app.database import SessionLocal
from app.models import Insight, Client, WeeklySummary
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

_MD_HEADING = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_MD_HR = re.compile(r"^[-*_]{3,}\s*$", re.MULTILINE)
_MD_BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)

SYSTEM_PROMPT = (
    "You write client-ready weekly briefs. Apply the Kinexis playbook: "
    "each priority must target a success metric (clicks, CTR, key_events, cvr, etc.) "
    "and prescribe the matching tactic. Ground every claim in the provided metrics and insights. "
    "When a metric has declined, state the WoW delta and provide a hypothesis for why "
    "(cite specific data when available — e.g. 'clicks dropped 22% WoW on /service-page: "
    "the page lost rankings for [query]' or 'no known algorithmic cause — possible seasonal'). "
    "Respond with valid JSON only. No markdown fences or commentary."
)


def strip_markdown(text: str) -> str:
    """Flatten common markdown so legacy narratives read as plain prose."""
    if not text:
        return ""
    out = text.replace("\r\n", "\n")
    out = _MD_HR.sub("", out)
    out = _MD_HEADING.sub("", out)
    out = _MD_BOLD.sub(r"\1", out)
    out = _MD_ITALIC.sub(r"\1", out)
    out = _MD_BULLET.sub("• ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def parse_narrative(raw: Optional[str]) -> dict[str, Any]:
    """
    Normalize stored narrative into:
      { headline, priorities: [{priority, title, severity, issue, actions, measure}] }
    Falls back to plain text in `body` for legacy markdown dumps.
    """
    if not raw or not raw.strip():
        return {"headline": "", "priorities": [], "body": ""}

    text = raw.strip()
    try:
        data = parse_json_payload(text, expect=dict)
        if isinstance(data, dict) and (
            "priorities" in data or "headline" in data or "summary" in data
        ):
            priorities = data.get("priorities") or data.get("recommendations") or []
            cleaned = []
            for i, p in enumerate(priorities):
                if not isinstance(p, dict):
                    continue
                actions = p.get("actions") or p.get("steps") or []
                if isinstance(actions, str):
                    actions = [actions]
                cleaned.append(
                    {
                        "priority": int(p.get("priority") or i + 1),
                        "title": str(p.get("title") or p.get("name") or f"Priority {i + 1}"),
                        "severity": str(p.get("severity") or "medium").lower(),
                        "success_metric": str(
                            p.get("success_metric") or p.get("metric") or ""
                        ).strip(),
                        "issue": str(p.get("issue") or p.get("why") or "").strip(),
                        "hypothesis": str(p.get("hypothesis") or "").strip(),
                        "actions": [str(a).strip() for a in actions if str(a).strip()],
                        "measure": str(p.get("measure") or p.get("success_metric_note") or "").strip(),
                    }
                )
            return {
                "headline": str(data.get("headline") or data.get("summary") or "").strip(),
                "priorities": cleaned,
                "body": "",
            }
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    return {"headline": "", "priorities": [], "body": strip_markdown(text)}


def generate_weekly_summary(client_id: int) -> Optional[WeeklySummary]:
    if not ai_configured():
        logger.warning("AI not configured — skipping AI summary")
        return None

    db = SessionLocal()
    try:
        today = date.today()
        week_start = today - timedelta(days=7)

        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return None

        unresolved = (
            db.query(Insight)
            .filter(
                Insight.client_id == client_id,
                Insight.resolved == False,  # noqa: E712
            )
            .all()
        )

        if not unresolved:
            logger.info(f"No unresolved insights for client {client_id}, skipping summary")
            return None

        severity_rank = {"high": 0, "medium": 1, "low": 2}
        unresolved.sort(key=lambda i: (severity_rank.get(i.severity, 9), -(i.id or 0)))
        unresolved = unresolved[:30]

        context = build_client_ai_context(db, client, days=14, include_dimensions=True)

        prompt_parts = [
            "You are writing a client-ready weekly analyst brief for an agency account manager.",
            "Use ONLY the insights and metrics below. Do not invent tools, dashboards, or data.",
            "Cite real numbers, queries, and URLs when explaining issues.",
            "",
            context,
            "=== ACTIVE INSIGHTS ===",
        ]

        for i, insight in enumerate(unresolved, 1):
            prompt_parts.append(
                f"{i}. [{insight.severity.upper()}] {insight.type}: {insight.message}"
            )
            if insight.recommended_action:
                prompt_parts.append(f"   Recommended: {insight.recommended_action}")

        prompt_parts.append(
            """
Return JSON only with this exact shape:
{
  "headline": "One plain sentence on the week's status with a key number if available (no markdown)",
  "priorities": [
    {
      "priority": 1,
      "title": "Short action title (max 10 words)",
      "severity": "high|medium|low",
      "success_metric": "e.g. gsc.clicks | gsc.ctr | ga4.key_events | ga4.cvr",
      "issue": "2-3 sentences: what is wrong, which success metric is hurt, cite real numbers/queries/URLs",
      "hypothesis": "1 sentence on likely cause with confidence caveat (e.g. 'Likely seasonal — low confidence' or 'Correlated with title change on /page — medium confidence')",
      "actions": [
        "Concrete step the team can do this week (name the page/query/edit)",
        "Second concrete step",
        "Third concrete step if needed"
      ],
      "measure": "How we know it worked in 7-14 days (specific success metric + expected direction)"
    }
  ]
}

Rules:
- Exactly 4–5 priorities, ordered by business impact (highest first).
- Each priority maps to one playbook pattern (low CTR, striking distance, CRO leak, content gap, etc.).
- Prefer zero-click waste, traffic/impression drops, rising content opportunities, and CRO leaks when present.
- actions: 2-4 items each, specific (pages, queries, edits) — not vague advice.
- No markdown, no headings, no bold, no horizontal rules, no emoji.
- Do NOT tell the reader to "check GSC" or open external tools as the main action — prescribe the fix itself.
"""
        )

        raw = complete(
            system=with_marketing_knowledge(SYSTEM_PROMPT),
            user="\n".join(prompt_parts),
            max_tokens=3072,
            json_mode=True,
            temperature=0.35,
        )
        if not raw:
            return None

        try:
            parsed = parse_json_payload(raw, expect=dict)
            if not isinstance(parsed, dict):
                raise TypeError("expected object")
            # Re-serialize cleanly so the UI always gets consistent JSON
            normalized = parse_narrative(json.dumps(parsed))
            if not normalized["priorities"] and not normalized["headline"]:
                raise ValueError("empty narrative")
            content = json.dumps(
                {
                    "headline": normalized["headline"],
                    "priorities": normalized["priorities"],
                },
                ensure_ascii=False,
            )
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning(f"Narrative JSON parse failed, storing cleaned prose: {e}")
            content = strip_markdown(raw)

        existing = (
            db.query(WeeklySummary)
            .filter(
                WeeklySummary.client_id == client_id,
                WeeklySummary.week_start == week_start,
            )
            .first()
        )
        if existing:
            existing.content = content
            existing.reviewed = False
            existing.created_at = utcnow()
            db.commit()
            db.refresh(existing)
            logger.info(f"Weekly summary updated for client {client_id} (id={existing.id})")
            return existing

        summary = WeeklySummary(
            client_id=client_id,
            week_start=week_start,
            content=content,
            reviewed=False,
        )
        db.add(summary)
        db.commit()
        db.refresh(summary)

        logger.info(f"Weekly summary generated for client {client_id} (id={summary.id})")
        return summary

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to generate weekly summary for client {client_id}: {e}")
        return None
    finally:
        db.close()
