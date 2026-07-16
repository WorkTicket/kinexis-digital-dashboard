"""
Content Brief Generator — AI-powered content briefs from insight data.
"""

import json
import logging
import re
from typing import Optional

from app.ai_client import ai_configured, complete, parse_json_payload
from app.ai_context import (
    ensure_page_snapshots_for_urls,
    format_client_profile,
    format_keyword_context,
    format_page_snapshot,
)
from app.ai_critique import critique_brief_dict
from app.connectors.page_content import extract_urls_from_text
from app.connectors.serp import (
    fetch_serp_snapshot,
    format_serp_snapshot,
    serp_enabled,
)
from app.funnel_analyzer import analyze_funnel
from app.marketing_knowledge import with_marketing_knowledge
from app.database import SessionLocal
from sqlalchemy.orm import Session
from app.models import Insight, ContentBrief, Client
from app.success_contract import parse_success_contract

logger = logging.getLogger(__name__)

BRIEF_PROMPT = """Generate a detailed, publish-ready content brief from SEO and insight data.
Apply the Kinexis playbook: content exists to move impressions → clicks → key_events — and ultimately the client's Success Contract primary KPI.
The brief must include a clear path from the article to a conversion CTA.

Output valid JSON with these fields:
  - "keyword": the primary target keyword (exact phrase)
  - "search_intent": one of [informational, commercial, transactional, navigational]
  - "success_metric": primary metric this content should move (prefer the Success Contract primary when set; otherwise gsc.impressions → gsc.clicks → ga4.key_events)
  - "title": array of 4-6 SEO-optimized, clickable title variations (different angles; CTR-focused)
  - "meta_description": one 150-160 character meta description draft (benefit + CTA hint)
  - "outline": array of H2 sections; each item is an object:
      {"h2": "...", "h3": ["...", "..."], "notes": "what this section must cover / proof points"}
  - "word_count": recommended total word count (number only, typically 1200-2500)
  - "related_keywords": array of 8-12 semantically related keywords / entities to include
  - "serp_notes": 3-5 observations about ranking opportunity — use LIVE SERP competitor
    titles/snippets when provided; otherwise use GSC position/CTR/impression data;
    note format gaps (listicles, guides, comparisons) you can exploit
  - "cta_suggestion": primary CTA plus where it should appear (how this drives key_events)
  - "internal_links": 2-4 suggested internal link targets (use real URLs from data when available)
  - "differentiation": 1-2 sentences on how this piece should beat what currently ranks

Output valid JSON only, no markdown wrapper, no explanation outside the JSON object."""


def _extract_keyword_hint(insight: Insight) -> str:
    """Best-effort keyword from insight message / recommended action."""
    text = f"{insight.message or ''} {insight.recommended_action or ''}"
    # Quoted phrases first
    quoted = re.findall(r'["\u201c\u201d]([^"\u201c\u201d]{2,80})["\u201c\u201d]', text)
    if quoted:
        return quoted[0].strip()
    # Common patterns: query "x", keyword x, for "x"
    m = re.search(
        r"(?:query|keyword|term|for|targeting)\s*[:\-]?\s*[\"']?([a-z0-9][\w\s\-]{1,60})",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip(" .,:;")
    # Fallback: first meaningful chunk of the message
    return (insight.message or "")[:80].strip()


def generate_content_brief(client_id: int, insight_id: int, db: Session | None = None) -> Optional[ContentBrief]:
    if not ai_configured():
        logger.warning("AI not configured — skipping content brief")
        return None

    close = False
    if db is None:
        db = SessionLocal()
        close = True
    try:
        client = db.query(Client).filter(Client.id == client_id).first()
        insight = db.query(Insight).filter(Insight.id == insight_id).first()
        if not client or not insight:
            return None

        keyword_hint = _extract_keyword_hint(insight)
        prompt_parts = [
            f"Client: {client.name} (Industry: {client.industry or 'Unknown'})",
            "",
        ]
        prompt_parts.extend(format_client_profile(client))
        contract = parse_success_contract(client)
        if contract:
            prompt_parts.append(
                f"Bind success_metric and CTA to the contract primary: "
                f"{contract.get('primary_metric')} ({contract.get('label')})."
            )
            prompt_parts.append("")

        try:
            funnel = analyze_funnel(client_id, days=30, db=db)
            lever = funnel.get("growth_lever") or {}
            leak = funnel.get("biggest_leak") or {}
            prompt_parts.append("=== FUNNEL CONTEXT (prioritize closing this leak) ===")
            if lever:
                prompt_parts.append(
                    f"  Growth lever: {lever.get('title') or lever.get('stage') or 'n/a'}"
                )
                if lever.get("cause"):
                    prompt_parts.append(f"  Cause: {lever.get('cause')}")
                if lever.get("fix"):
                    prompt_parts.append(f"  Fix direction: {lever.get('fix')}")
            if leak:
                prompt_parts.append(
                    f"  Biggest leak: {leak.get('stage')} "
                    f"({leak.get('dropoff')}% drop-off)"
                )
            prompt_parts.append("")
        except Exception as e:
            logger.warning("Funnel context for brief failed: %s", e)

        prompt_parts.extend(format_keyword_context(db, client_id, keyword_hint))

        target_urls = extract_urls_from_text(
            f"{insight.message or ''} {insight.recommended_action or ''}"
        )
        snaps = ensure_page_snapshots_for_urls(db, client_id, target_urls, limit=2)
        for snap in snaps:
            prompt_parts.extend(format_page_snapshot(snap))

        if serp_enabled() and keyword_hint:
            try:
                from app.competitor_domains import parse_client_domains, parse_competitor_domains
                from app.models import Client as ClientModel

                client_row = db.query(ClientModel).filter(ClientModel.id == client_id).first()
                serp = fetch_serp_snapshot(db, client_id, keyword_hint)
                prompt_parts.extend(
                    format_serp_snapshot(
                        serp,
                        competitor_domains=parse_competitor_domains(client_row),
                        client_domains=parse_client_domains(client_row),
                    )
                )
            except Exception as e:
                logger.warning("SERP context for brief failed: %s", e)

        prompt_parts.append("=== INSIGHT THAT TRIGGERED THIS BRIEF ===")
        prompt_parts.append(f"  Type: {insight.type}")
        prompt_parts.append(f"  Severity: {insight.severity}")
        prompt_parts.append(f"  Message: {insight.message}")
        prompt_parts.append(f"  Recommended action: {insight.recommended_action or 'N/A'}")
        prompt_parts.append(f"  Keyword hint: {keyword_hint or 'infer from insight'}")
        prompt_parts.append("")
        prompt_parts.append(
            "Generate a complete, detailed content brief targeting the keyword/opportunity above. "
            "Use GSC numbers when present. Prefer the Success Contract primary metric and the "
            "biggest funnel leak when choosing success_metric and CTA. Make the outline specific "
            "enough that a writer could draft without further briefing."
        )

        raw = complete(
            system=with_marketing_knowledge(BRIEF_PROMPT),
            user="\n".join(prompt_parts),
            max_tokens=4096,
            json_mode=True,
            temperature=0.4,
            purpose="content_brief",
        )
        if not raw:
            return None

        try:
            brief_data = parse_json_payload(raw, expect=dict)
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(brief_data, dict):
            return None

        user_context = "\n".join(prompt_parts)
        brief_data = critique_brief_dict(user_context, brief_data)
        if brief_data is None:
            logger.warning(
                "Content brief rejected by critique for client %s insight %s",
                client_id,
                insight_id,
            )
            return None

        # Keep outline as an array for the UI; prepend rich brief notes as string rows.
        sections = brief_data.get("outline") or []
        if not isinstance(sections, list):
            sections = [sections]
        outline: list = []
        if brief_data.get("search_intent"):
            outline.append(f"Intent: {brief_data['search_intent']}")
        if brief_data.get("success_metric"):
            outline.append(f"Success metric: {brief_data['success_metric']}")
        if brief_data.get("meta_description"):
            outline.append(f"Meta: {brief_data['meta_description']}")
        serp = brief_data.get("serp_notes")
        if serp:
            if isinstance(serp, list):
                outline.append("SERP notes: " + "; ".join(str(s) for s in serp))
            else:
                outline.append(f"SERP notes: {serp}")
        if brief_data.get("differentiation"):
            outline.append(f"Differentiation: {brief_data['differentiation']}")
        if brief_data.get("cta_suggestion"):
            outline.append(f"CTA: {brief_data['cta_suggestion']}")
        links = brief_data.get("internal_links")
        if links:
            if isinstance(links, list):
                outline.append("Internal links: " + "; ".join(str(l) for l in links))
            else:
                outline.append(f"Internal links: {links}")
        outline.extend(sections)

        brief = ContentBrief(
            client_id=client_id,
            insight_id=insight_id,
            keyword=brief_data.get("keyword", "") or keyword_hint,
            title=json.dumps(brief_data.get("title", [])),
            outline=json.dumps(outline),
            word_count=int(brief_data.get("word_count", 0) or 0),
            related_keywords=json.dumps(brief_data.get("related_keywords", [])),
            status="draft",
        )

        db.add(brief)
        db.commit()
        db.refresh(brief)
        logger.info(f"Content brief generated for client {client_id}, insight {insight_id}")
        return brief

    except Exception as e:
        db.rollback()
        logger.error(f"Content brief generation failed: {e}")
        return None
    finally:
        if close:
            db.close()
