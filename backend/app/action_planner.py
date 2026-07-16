"""
AI Action Planner — generates prioritized, measurable action plans.

Phase 2: Compiler, not brainstormer. The LLM receives deterministic
action candidates and only writes FROM→TO copy + steps. It never
invents new action types or playbook patterns.
"""

import json
import logging
from datetime import date
from typing import Any, Optional

from app.ai_client import ai_configured, complete, parse_json_payload
from app.ai_context import (
    build_client_ai_context,
)
from app.assignee_routing import strip_recheck_steps
from app.connectors.page_content import extract_urls_from_text
from app.connectors.serp import (
    ensure_serp_for_flagged_queries,
    format_serp_snapshot,
    serp_enabled,
)
from app.marketing_knowledge import with_marketing_knowledge
from app.outcome_memory import format_playbook_track_record, playbook_track_record
from app.portfolio_scoring import cross_client_fix_effectiveness, format_cross_client_patterns
from app.database import SessionLocal
from sqlalchemy.orm import Session
from app.models import ActionPlan, Client
from app.funnel_analyzer import analyze_funnel
from app.opportunities import build_opportunities
from app.action_candidates import build_action_candidates

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Kinexis action planner. Your job is narrow: receive CANDIDATE ACTIONS
with pre-filled data (target_url, current_state, insight_id, playbook pattern) and write only
the proposed_changes (exact FROM→TO copy) + execution steps for each candidate.

FEEDBACK LOOP ACTIVE — you will receive a PLAYBOOK TRACK RECORD section below with this client's
historical win/loss rates per playbook. Use it:
  - Playbooks marked [AVOID] consistently lose — do NOT prescribe them, mark them skip.
  - Playbooks marked [PREFER] are proven winners — prioritize them first.
  - Playbooks marked [WEAK] have poor win rates — only prescribe if no better alternative exists.

You MAY NOT:
- Invent new action types or playbook patterns
- Add FAQ schema, featured-snippet, or "audit all" patterns (they are banned)
- Create actions not in the CANDIDATES list you receive
- Suggest "wait and recheck" steps (Prove handles measurement)
- Add mobile or page-speed actions without specific PSI/CTR evidence
- Prescribe playbooks marked [AVOID] in the track record

For each CANDIDATE in the input, produce EXACTLY ONE output action with these fields:
  - "candidate_index": integer matching the input CANDIDATE index (0-based)
  - "insight_id": echo the candidate's insight_id
  - "proposed_changes": object with exact new copy to ship, e.g.
      { "title": "new title ≤60 chars", "meta": "new meta ≤155 chars", "h1": "optional new H1" }
      Every proposed_change MUST be a verbatim replacement string — not a description.
      For CTR-gap fixes: provide exact new title (≤60 chars) and meta (≤155 chars) TO ship.
      For content fixes: add a "body_section" key with the H2 heading + what to write.
  - "steps": array of 3-6 concrete ordered steps. EVERY step must start with "On {target_url}: …"
      or name the target_url. Include exact FROM → TO strings for title/meta/H1 when changing copy.
      Step 1 for CTR/title fixes MUST be:
        "On {target_url}: Change title FROM \"{current_title}\" TO \"{new_title}\" (≤60 chars)"
  - "estimated_impact": concrete estimate tied to success_metric, e.g.
      "+15-25% organic clicks on [page/query] in 30 days" or "+0.3-0.8pp conversion rate in 60 days"
  - "why_it_matters": 2-3 sentences in plain English. Cite real numbers from the evidence.

All other fields (category, target_url, playbook_pattern, assignee, etc.) are already set on
the candidates — do NOT repeat them. Output a JSON array with the same length as the CANDIDATES
input, preserving order. If a candidate has no viable fix, output {"candidate_index": N, "skip": true}.

Output valid JSON only, no markdown, no explanation outside the JSON array."""


def generate_action_plan(client_id: int, db: Session | None = None) -> Optional[ActionPlan]:
    if not ai_configured():
        logger.warning("AI not configured — skipping action plan generation")
        return None

    close = False
    if db is None:
        db = SessionLocal()
        close = True
    try:
        today = date.today()

        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return None

        context = build_client_ai_context(db, client, days=30, include_dimensions=True)

        # Phase 2: Generate deterministic candidates before LLM
        candidates = build_action_candidates(db, client_id, max_candidates=8)
        if not candidates:
            logger.info(
                "No action candidates for client %s (%s). "
                "Ensure insights exist and pass evidence gates.",
                client_id,
                client.name,
            )
            return None

        prompt_parts = [context, "=== CANDIDATE ACTIONS (write FROM→TO copy for these only) ==="]

        for i, cand in enumerate(candidates):
            target_url = cand.get("target_url") or "?"
            target_query = cand.get("target_query") or ""
            state = cand.get("current_state") or {}
            hint = cand.get("proposed_changes_hint") or {}
            prompt_parts.append(
                f"CANDIDATE {i}: insight_id={cand['insight_id']}, "
                f"playbook={cand['playbook_pattern']}, "
                f"target_url={target_url}"
            )
            prompt_parts.append(f"  Insight: {cand['why_it_matters']}")
            if target_query:
                prompt_parts.append(f"  Query: \"{target_query}\"")
            if state.get("title"):
                prompt_parts.append(f"  Current title: {state['title']}")
            if state.get("meta"):
                prompt_parts.append(f"  Current meta: {state['meta']}")
            if state.get("h1"):
                prompt_parts.append(f"  Current H1: {state['h1']}")
            if hint.get("title"):
                prompt_parts.append(f"  Hint title: {hint['title']}")
            if hint.get("meta"):
                prompt_parts.append(f"  Hint meta: {hint['meta']}")
            prompt_parts.append(f"  Priority score: {cand['priority_score']}")
            prompt_parts.append("")

        # Inject funnel leaks + top opportunities so plans prioritize conversion/sales lifts
        try:
            funnel = analyze_funnel(client_id, days=30, db=db)
            prompt_parts.append("")
            prompt_parts.append("=== CONVERSION FUNNEL (top leak only) ===")
            lever = funnel.get("growth_lever")
            if lever:
                prompt_parts.append(
                    f"Biggest lever: {lever.get('title') or lever.get('stage')} \u2014 "
                    f"{lever.get('cause') or ''}"
                )
                if lever.get("fix"):
                    prompt_parts.append(f"Fix: {lever['fix']}")
            # Only include the top 2 leaks (was 4)
            for leak in (funnel.get("leaks") or [])[:2]:
                prompt_parts.append(
                    f"- {leak.get('stage')}: {leak.get('leak_pct')}% lost. "
                    f"Cause: {leak.get('cause')}. Fix: {leak.get('fix')}"
                )
            rates = funnel.get("rates") or {}
            totals = funnel.get("totals") or {}
            prompt_parts.append(
                f"Rates: CTR {rates.get('impression_to_click_pct')}%, "
                f"CVR {rates.get('session_to_conversion_pct')}%, "
                f"leads={totals.get('leads')}, revenue={totals.get('revenue')}"
            )
        except Exception as e:
            logger.warning("Funnel context for action plan failed: %s", e)

        try:
            opps = build_opportunities(db, client_id, days=28, limit=5)
            prompt_parts.append("")
            prompt_parts.append("=== TOP OPPORTUNITIES (use as evidence) ===")
            page_urls: list[str] = []
            rising_queries: list[str] = []
            for r in (opps.get("rising_queries") or [])[:3]:
                rising_queries.append(str(r["query"]))
                prompt_parts.append(
                    f"Rising: \"{r['query']}\" +{r['growth_pct']}% impr, "
                    f"pos {r['position']}"
                )
            for r in (opps.get("ctr_underperformers") or [])[:3]:
                prompt_parts.append(
                    f"CTR gap: {r['page']} {r['gap_pct']}% below expected"
                )
                if r.get("page") and str(r["page"]).startswith("http"):
                    page_urls.append(str(r["page"]))

            # Collect fix targets from candidates only (skip expensive page snapshots)
            from app.page_targets import extract_quoted_queries, collect_fix_targets_for_plan, resolve_target_url

            for cand in candidates[:5]:
                msg = cand.get("why_it_matters") or ""
                q = cand.get("target_query") or ""
                if msg:
                    page_urls.extend(extract_urls_from_text(msg))
                    if q:
                        rising_queries.append(q)
                if cand.get("target_url") and str(cand["target_url"]).startswith("http"):
                    page_urls.append(str(cand["target_url"]))

            prompt_parts.append("")
            prompt_parts.extend(
                collect_fix_targets_for_plan(
                    db,
                    client_id,
                    queries=rising_queries,
                    page_urls=page_urls,
                    brand=(client.name or "").split(".")[0],
                    limit=4,
                )
            )
        except Exception as e:
            logger.warning("Opportunities context for action plan failed: %s", e)

        if serp_enabled():
            try:
                from app.competitor_domains import parse_client_domains, parse_competitor_domains
                from app.models import Client as ClientModel

                client_row = db.query(ClientModel).filter(ClientModel.id == client_id).first()
                comps = parse_competitor_domains(client_row)
                owns = parse_client_domains(client_row)
                # Cost-capped: only queries already flagged by insight rules
                for snap in ensure_serp_for_flagged_queries(db, client_id, limit=3):
                    prompt_parts.extend(
                        format_serp_snapshot(
                            snap, competitor_domains=comps, client_domains=owns
                        )
                    )
            except Exception as e:
                logger.warning("SERP context for action plan failed: %s", e)

        try:
            track = playbook_track_record(db, client_id)
            lines = format_playbook_track_record(track)
            if lines:
                prompt_parts.extend(lines)
                logger.info(
                    "Injected playbook track record for client %s: %s patterns with outcome data",
                    client_id, len(track),
                )
        except Exception as e:
            logger.warning("Playbook track record failed: %s", e)

        try:
            xclient = cross_client_fix_effectiveness(db)
            prompt_parts.extend(format_cross_client_patterns(xclient))
        except Exception as e:
            logger.warning("Cross-client patterns failed: %s", e)

        prompt_parts.append("")
        prompt_parts.append(
            f"Write proposed_changes + steps for each CANDIDATE above. "
            f"Output a JSON array matching the CANDIDATES count, in order. "
            f"Every step must start with \"On {{target_url}}:\" and include exact FROM→TO copy."
        )

        raw = complete(
            system=with_marketing_knowledge(SYSTEM_PROMPT),
            user="\n".join(prompt_parts),
            max_tokens=6144,
            json_mode=True,
            temperature=0.35,
            purpose="action_plan",
        )
        if not raw:
            logger.error(
                "Action plan AI returned empty for client %s (%s). "
                "Check that Ollama is running and the model is loaded. "
                "First request after idle can take 1-2 minutes for model warmup.",
                client_id,
                client.name,
            )
            return None

        try:
            llm_output = parse_json_payload(raw, expect=list)
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Failed to parse action plan JSON for client {client_id}: {e}")
            return None

        # Normalize dict/list wrappers
        if isinstance(llm_output, dict):
            for key in ("actions", "items", "plan", "recommendations"):
                if isinstance(llm_output.get(key), list):
                    llm_output = llm_output[key]
                    break

        if not isinstance(llm_output, list):
            logger.error("Action plan LLM output was not a list for client %s", client_id)
            return None

        # Merge LLM output back into candidates
        merged: list[dict[str, Any]] = []
        llm_by_index: dict[int, dict] = {}
        for item in llm_output:
            if isinstance(item, dict):
                idx = item.get("candidate_index")
                if isinstance(idx, int) and 0 <= idx < len(candidates):
                    llm_by_index[idx] = item

        for idx, cand in enumerate(candidates):
            llm_item = llm_by_index.get(idx, {})
            if llm_item.get("skip"):
                logger.info("Skipping candidate %s (LLM marked skip)", idx)
                continue

            action = {
                "title": cand["title"],
                "category": cand["category"],
                "priority_score": cand["priority_score"],
                "success_metric": cand["success_metric"],
                "target_url": cand["target_url"],
                "target_query": cand.get("target_query", ""),
                "current_state": cand.get("current_state", {}),
                "proposed_changes": llm_item.get("proposed_changes", {}),
                "why_it_matters": llm_item.get("why_it_matters") or cand.get("why_it_matters", ""),
                "estimated_impact": llm_item.get("estimated_impact") or cand.get("estimated_impact", ""),
                "effort": cand["effort"],
                "steps": llm_item.get("steps") or cand.get("steps", []),
                "metrics_to_watch": cand["metrics_to_watch"],
                "expected_timeline": cand["expected_timeline"],
                "evidence": cand.get("evidence", ""),
                "playbook_pattern": cand["playbook_pattern"],
                "assignee": cand["assignee"],
                "insight_id": cand["insight_id"],
            }
            merged.append(action)

        if not merged:
            logger.error("No merged actions after LLM merge for client %s", client_id)
            return None

        # Sort by priority and cap at 5
        merged.sort(key=lambda a: float(a.get("priority_score") or 0), reverse=True)
        merged = merged[:5]

        # Phase 4: Run critique self-check on final plan (rejection rate tracked here)
        from app.ai_critique import critique_action_list
        before_critique = len(merged)
        merged = critique_action_list(context, merged, client=client)
        if len(merged) < before_critique:
            logger.info(
                "Critique dropped %s action(s) from final plan for client %s",
                before_critique - len(merged), client_id,
            )

        for action in merged:
            if action.get("assignee") != "human":
                action["steps"] = strip_recheck_steps(action.get("steps"))
        logger.info(
            "Merged action plan: %s actions from %s candidates for client %s",
            len(merged), len(candidates), client_id,
        )

        first = merged[0] if merged else {}
        plan = ActionPlan(
            client_id=client_id,
            title=f"Action Plan — {today.isoformat()}",
            content=json.dumps(merged, indent=2),
            priority_score=int(first.get("priority_score") or 0) if isinstance(first, dict) else 0,
            estimated_impact=(first.get("estimated_impact") or "") if isinstance(first, dict) else "",
            status="active",
        )
        db.add(plan)
        db.flush()

        for old_plan in (
            db.query(ActionPlan)
            .filter(
                ActionPlan.client_id == client_id,
                ActionPlan.status == "active",
                ActionPlan.id != plan.id,
            )
            .all()
        ):
            old_plan.status = "archived"

        db.commit()
        db.refresh(plan)
        logger.info(f"Action plan generated for client {client_id}: {len(merged)} actions")
        return plan

    except Exception as e:
        if close:
            db.rollback()
        logger.error(f"Action plan generation failed for client {client_id}: {e}")
        return None
    finally:
        if close:
            db.close()
