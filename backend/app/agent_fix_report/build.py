"""Build agent-facing markdown fix reports from the Fix queue."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.ai_context import format_metric_totals_with_wow
from app.connectors.page_content import fetch_page_snapshot
from app.connectors.pagespeed import _resolve_client_url
from app.insight_scoring import TYPE_WHY, effort_label, why_it_matters
from app.models import Client, Insight, Task
from app.opportunities import build_opportunities

from .helpers import (
    _bullet_list,
    _connected_sources,
    _estimate_click_opportunity,
    _extract_targets,
    _fmt_num,
    _md_escape,
    _page_metrics,
    _parse_finding_numbers,
    _parse_profile,
    _query_metrics,
    _rewrite_copy_from_page,
    _site_kpi_snapshot,
    _slug,
    _top_pages_for_query,
    _top_pagespeed_finding_lines,
)
from .playbooks import PLAYBOOKS, SEVERITY_ORDER
from app.timeutil import utcnow

def build_agent_fix_markdown(
    db: Session,
    client_id: int,
    *,
    severity: Optional[str] = None,
    kind: Optional[str] = None,
    include_resolved: bool = False,
) -> tuple[str, str]:
    """Returns (markdown_body, suggested_filename)."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise ValueError("Client not found")

    q = db.query(Insight).filter(Insight.client_id == client_id)
    if not include_resolved:
        q = q.filter(Insight.resolved == False)  # noqa: E712
    if severity and severity != "all":
        q = q.filter(Insight.severity == severity)
    if kind and kind != "all":
        q = q.filter(Insight.kind == kind)

    insights = q.all()
    insights.sort(
        key=lambda i: (
            -(i.priority_score or 0),
            SEVERITY_ORDER.get((i.severity or "").lower(), 9),
            i.id or 0,
        )
    )

    site_url = _resolve_client_url(db, client_id)
    profile = _parse_profile(client)
    sources = _connected_sources(db, client_id)
    open_tasks = (
        db.query(Task)
        .filter(Task.client_id == client_id, Task.status.in_(["open", "in_progress"]))
        .all()
    )
    tasks_by_insight = {t.insight_id: t for t in open_tasks if t.insight_id}

    generated_at = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    filename = f"kinexis-agent-fix-brief-{_slug(client.name)}-{date.today().isoformat()}.md"

    # Precompute opportunities + KPI context
    try:
        opps = build_opportunities(db, client_id, days=28, limit=8)
    except Exception:
        opps = {"rising_queries": [], "ctr_underperformers": [], "landing_pages": []}

    kpi = _site_kpi_snapshot(db, client_id, days=28)
    metric_lines = format_metric_totals_with_wow(db, client_id, days=30)

    lines: list[str] = []
    lines.append(f"# Coding Agent Success Fix Brief — {client.name}")
    lines.append("")
    lines.append(
        "> **Mission:** Fully remediate each Fix-queue item so client success metrics move — "
        "especially **more Google clicks**, higher **CTR**, healthier **sessions**, and more "
        "**conversions/leads**. Do not stop at partial edits; meet every success contract."
    )
    lines.append("")
    lines.append(f"**Generated:** {generated_at}  ")
    lines.append(f"**Client ID:** {client.id}  ")
    lines.append(f"**Industry:** {client.industry or '—'}  ")
    lines.append(f"**Site URL:** {site_url or '_unknown — resolve from GSC/PageSpeed credentials_'}  ")
    lines.append(f"**Open fixes in this brief:** {len(insights)}  ")
    if severity and severity != "all":
        lines.append(f"**Severity filter:** {severity}  ")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Operating system for the agent")
    lines.append("")
    lines.append("You are a **senior implementation agent** (SEO + CRO + web performance).")
    lines.append("")
    lines.append("### Non-negotiables")
    lines.append("")
    lines.append("1. Work **strict priority order** (highest `priority_score` first).")
    lines.append("2. For each fix: read Finding → Targets → Success contract → Technical spec → ship → verify.")
    lines.append("3. **Optimize for outcomes**, not activity: clicks, CTR, conversions, leads.")
    lines.append("4. Only edit URLs/paths in **Target assets** (or pages you verify rank for the query).")
    lines.append("5. Respect **Agency constraints** (do-not-touch, brand voice, goals).")
    lines.append("6. One fix = one deployable unit with before/after notes in the handoff block.")
    lines.append("7. After each fix, leave a **measurement plan** (Day 0 / 7 / 14 / 28).")
    lines.append("8. Prefer high-leverage SERP/copy/CWV/CTA changes that unlock clicks and conversions.")
    lines.append("")

    from app.success_contract import parse_success_contract, evaluate_success_contract

    contract = parse_success_contract(client)
    contract_eval = evaluate_success_contract(db, client)
    if contract:
        lines.append("### Client Success Contract (BINDING — optimize for this first)")
        lines.append("")
        lines.append(
            f"1. **Primary KPI:** `{contract['primary_metric']}` ({contract['label']}) "
            f"— target **+{contract['target_delta_pct']}%** over **{contract['window_days']} days**"
        )
        if contract.get("secondary_metrics"):
            lines.append(
                f"2. **Secondary:** {', '.join(f'`{m}`' for m in contract['secondary_metrics'])}"
            )
        prog = (contract_eval.get("progress") or {}) if contract_eval.get("configured") else {}
        if prog.get("change_pct") is not None:
            lines.append(
                f"3. **Current progress:** {prog['change_pct']:+.1f}% "
                f"(status: **{contract_eval.get('status')}**)"
            )
        if contract.get("notes"):
            lines.append(f"4. **Notes:** {_md_escape(str(contract['notes']))}")
        lines.append("")
        lines.append(
            "Clicks/CTR/position still matter as leading indicators — but the Success Contract "
            "is the definition of client success for this engagement."
        )
        lines.append("")
    else:
        lines.append("### Success hierarchy (what “good” means)")
        lines.append("")
        lines.append("1. **Clicks** (GSC / Bing) — primary growth lever for organic")
        lines.append("2. **CTR** — yield on existing impressions (fastest wins)")
        lines.append("3. **Position** — durable click growth")
        lines.append("4. **Sessions that don’t bounce**")
        lines.append("5. **Key events / leads / revenue** — business outcome")
        lines.append("")
        lines.append(
            "_No Success Contract set — ask the agency to set primary KPI + target in client profile._"
        )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Agency constraints & profile")
    lines.append("")
    constraint_keys = (
        ("goals", "Goals"),
        ("do_not_touch", "Do not touch"),
        ("brand_voice", "Brand voice"),
        ("primary_location", "Primary location"),
        ("service_areas", "Service areas"),
        ("exclude_areas", "Out of area (never target)"),
        ("target_audience", "Target audience"),
        ("competitors", "Competitors"),
        ("brand_terms", "Brand search terms"),
        ("notes", "Notes"),
        ("website", "Website (profile)"),
        ("primary_domain", "Primary domain"),
        ("domain", "Domain"),
    )
    any_profile = False
    for key, label in constraint_keys:
        val = profile.get(key)
        if val:
            any_profile = True
            lines.append(f"- **{label}:** {_md_escape(str(val))}")
    if not any_profile:
        lines.append("_No agency profile memory set — default to clear, benefit-led, local-trust copy._")
    lines.append("")
    lines.append(f"**Connected data sources:** {', '.join(sources) if sources else 'none'}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Client success scoreboard (last ~28–30 days)")
    lines.append("")
    lines.append("Use this as the **before** baseline. Your work should move these numbers.")
    lines.append("")
    if metric_lines:
        for ml in metric_lines:
            if ml.startswith("==="):
                lines.append(f"**{ml.strip('= ').strip()}**")
            elif ml.strip():
                lines.append(f"- `{ml.strip()}`")
    if kpi:
        lines.append("")
        lines.append("**Raw summed series (may include dimensional rows — directional):**")
        for k, v in sorted(kpi.items()):
            lines.append(f"- `{k}`: {_fmt_num(v)}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Opportunity radar (synced data)")
    lines.append("")
    rising = opps.get("rising_queries") or []
    ctr_u = opps.get("ctr_underperformers") or []
    landing = opps.get("landing_pages") or []
    if rising:
        lines.append("### Rising queries (demand to capture → clicks)")
        lines.append("")
        lines.append("| Query | Impr | Growth | Clicks | Pos | CTR |")
        lines.append("|-------|-----:|-------:|-------:|----:|----:|")
        for r in rising[:8]:
            lines.append(
                f"| `{r['query']}` | {r['impressions']} | {r['growth_pct']}% | "
                f"{r['clicks']} | {r['position']} | {r['ctr']} |"
            )
        lines.append("")
    if ctr_u:
        lines.append("### CTR underperformer pages (impressions not becoming clicks)")
        lines.append("")
        lines.append("| Page | Impr | Clicks | CTR | Expected | Gap | Pos |")
        lines.append("|------|-----:|-------:|----:|---------:|----:|----:|")
        for r in ctr_u[:8]:
            page = str(r["page"]).replace("|", "\\|")
            lines.append(
                f"| `{page}` | {r['impressions']} | {r['clicks']} | {r['ctr']} | "
                f"{r['expected_ctr']} | {r['gap_pct']}% | {r['position']} |"
            )
        lines.append("")
    if landing:
        lines.append("### Top landing pages (convert the clicks you already have)")
        lines.append("")
        lines.append("| Page | Sessions | Conversions | CVR | vs avg |")
        lines.append("|------|---------:|------------:|----:|-------:|")
        for r in landing[:8]:
            page = str(r["page"]).replace("|", "\\|")
            lines.append(
                f"| `{page}` | {r['sessions']} | {r['conversions']} | {r['cvr']}% | {r['vs_avg']} |"
            )
        lines.append("")
    if not rising and not ctr_u and not landing:
        lines.append("_No opportunity tables available yet — rely on Fix queue evidence below._")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Fix queue summary (execute in this order)")
    lines.append("")
    if not insights:
        lines.append("_No open fixes in the queue for this filter._")
        lines.append("")
        return "\n".join(lines), filename

    # Pre-extract for summary + impact rollup
    prepped: list[dict[str, Any]] = []
    total_potential_clicks = 0.0
    for insight in insights:
        pb = PLAYBOOKS.get(insight.type, {})
        targets = _extract_targets(
            f"{insight.message or ''} {insight.recommended_action or ''}",
            site_url,
        )
        qm = None
        if targets["queries"]:
            qm = _query_metrics(db, client_id, targets["queries"][0])
        uplift = _estimate_click_opportunity(insight.type, insight.message or "", qm)
        if uplift and uplift.get("potential_extra_clicks_28d"):
            total_potential_clicks += float(uplift["potential_extra_clicks_28d"])
        prepped.append(
            {
                "insight": insight,
                "pb": pb,
                "targets": targets,
                "qm": qm,
                "uplift": uplift,
            }
        )

    lines.append(
        f"**Illustrative click opportunity across queue:** ~{_fmt_num(total_potential_clicks)} "
        f"additional clicks over a ~28-day window if CTR/content gaps are closed "
        f"(directional model — not a guarantee)."
    )
    lines.append("")
    lines.append("| # | Score | Sev | Type | North-star | Est. click unlock | Targets |")
    lines.append("|---|------:|-----|------|------------|------------------:|---------|")
    for idx, row in enumerate(prepped, start=1):
        insight = row["insight"]
        pb = row["pb"]
        targets = row["targets"]
        uplift = row["uplift"] or {}
        target_bits = []
        target_bits.extend(targets["urls"][:1])
        target_bits.extend(targets["resolved_urls"][:1])
        target_bits.extend([f'`"{q}"`' for q in targets["queries"][:2]])
        target_bits.extend(targets["paths"][:1])
        target_cell = ", ".join(target_bits) if target_bits else "—"
        target_cell = target_cell.replace("|", "\\|")
        north = (pb.get("north_star") or pb.get("metric") or "—").replace("|", "\\|")
        est = uplift.get("potential_extra_clicks_28d")
        est_s = f"~{_fmt_num(est)}" if est is not None else "—"
        lines.append(
            f"| {idx} | {insight.priority_score or 0:.0f} | {insight.severity} | "
            f"`{insight.type}` | {north} | {est_s} | {target_cell} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")

    for idx, row in enumerate(prepped, start=1):
        insight: Insight = row["insight"]
        pb: dict = row["pb"]
        targets: dict = row["targets"]
        qm = row["qm"]
        uplift = row["uplift"]
        title = pb.get("title") or insight.type.replace("_", " ").title()
        why = why_it_matters(insight.type, insight.message)
        effort = pb.get("effort") or effort_label(insight.type)
        task = tasks_by_insight.get(insight.id)
        parsed = _parse_finding_numbers(insight.message or "")

        lines.append(f"## Fix {idx:02d} — {title}")
        lines.append("")
        lines.append("### Identity")
        lines.append("")
        lines.append(f"- **insight_id:** `{insight.id}`")
        lines.append(f"- **type:** `{insight.type}`")
        lines.append(f"- **severity:** `{insight.severity}`")
        lines.append(f"- **priority_score:** `{insight.priority_score or 0}`")
        lines.append(f"- **effort:** {effort}")
        lines.append(f"- **north-star metric:** {pb.get('north_star') or pb.get('metric') or '—'}")
        lines.append(f"- **created_at:** {insight.created_at.isoformat() if insight.created_at else '—'}")
        if task:
            lines.append(
                f"- **linked_task:** id=`{task.id}` status=`{task.status}` "
                f"assignee=`{task.assigned_to or '—'}` due=`{task.due_date or '—'}`"
            )
        lines.append("")
        lines.append("### Why this grows client success")
        lines.append("")
        lines.append(_md_escape(why or TYPE_WHY.get(insight.type, "")))
        lines.append("")
        if pb.get("success_formula"):
            lines.append(f"**Success formula:** {pb['success_formula']}")
            lines.append("")
        if pb.get("impact_model"):
            lines.append(f"**Impact model:** {pb['impact_model']}")
            lines.append("")

        lines.append("### Finding (evidence)")
        lines.append("")
        lines.append(_md_escape(insight.message or "_No message._"))
        lines.append("")
        if parsed:
            lines.append("**Parsed signals from finding:**")
            lines.append("")
            for k, v in parsed.items():
                lines.append(f"- `{k}`: {v}")
            lines.append("")

        lines.append("### Recommended action (from rules engine)")
        lines.append("")
        lines.append(_md_escape(insight.recommended_action or "_No recommended action stored._"))
        lines.append("")

        lines.append("### Target assets (only touch these)")
        lines.append("")
        lines.append("**URLs**")
        lines.append("")
        lines.append(_bullet_list(targets["urls"]))
        lines.append("")
        lines.append("**Paths**")
        lines.append("")
        lines.append(_bullet_list(targets["paths"]))
        lines.append("")
        if site_url and targets["paths"]:
            lines.append("**Resolved absolute URLs**")
            lines.append("")
            lines.append(_bullet_list(targets["resolved_urls"]))
            lines.append("")
        lines.append("**Queries / keywords**")
        lines.append("")
        lines.append(_bullet_list([f'`"{q}"`' for q in targets["queries"]]))
        lines.append("")

        # Live metrics + uplift
        lines.append("### Baseline metrics & click opportunity")
        lines.append("")
        enrich_lines: list[str] = []
        for qname in targets["queries"][:5]:
            qmetrics = qm if (
                targets["queries"] and qname == targets["queries"][0] and qm is not None
            ) else _query_metrics(db, client_id, qname)
            if qmetrics:
                bits = ", ".join(
                    f"{k}={_fmt_num(v * 100, pct=True) if k == 'ctr' and v <= 1 else _fmt_num(v)}"
                    for k, v in qmetrics.items()
                )
                enrich_lines.append(f'Query `"{qname}"` (~28d): {bits}')
        for url in (targets["urls"] + targets["resolved_urls"] + targets["paths"])[:5]:
            pm = _page_metrics(db, client_id, url)
            if pm:
                bits = ", ".join(
                    f"{k}={_fmt_num(v * 100, pct=True) if k in ('ctr', 'cvr', 'bounce_rate') and v <= 1 else _fmt_num(v)}"
                    for k, v in pm.items()
                )
                enrich_lines.append(f"Page `{url}`: {bits}")

        if targets["queries"] and not enrich_lines:
            top_pages = _top_pages_for_query(db, client_id)
            if top_pages:
                enrich_lines.append(
                    "Top site pages by GSC clicks (locate likely ranking URL for the query):"
                )
                for p in top_pages[:6]:
                    enrich_lines.append(
                        f"  - `{p['page']}` — clicks={_fmt_num(p['clicks'])}, "
                        f"impressions={_fmt_num(p['impressions'])}"
                    )

        if enrich_lines:
            for el in enrich_lines:
                if el.startswith("  -"):
                    lines.append(el)
                else:
                    lines.append(f"- {el}")
        else:
            lines.append("- _No dimensional metrics matched — use finding text and GSC UI._")
        lines.append("")

        if uplift and uplift.get("narrative"):
            lines.append(f"**Click unlock estimate:** {uplift['narrative']}")
            lines.append("")
            if uplift.get("potential_extra_clicks_28d") is not None:
                lines.append(
                    f"- **Modeled extra clicks (~28d):** ~{_fmt_num(uplift['potential_extra_clicks_28d'])}"
                )
                lines.append("")

        # Success contract
        lines.append("### Success contract (definition of done)")
        lines.append("")
        lines.append(
            "Ship is not done until **implementation acceptance** is checked **and** "
            "the measurement plan is set. Business done when the north-star moves."
        )
        lines.append("")
        for item in pb.get("acceptance") or [
            "Recommended action completed on the correct URL/query",
            "North-star metric has a Day-0 baseline and Day-14 recheck plan",
        ]:
            lines.append(f"- [ ] {item}")
        lines.append("")

        lines.append("### Deliverables")
        lines.append("")
        lines.append(_bullet_list(pb.get("deliverables") or ["Completed recommended action"]))
        lines.append("")

        lines.append("### Technical specification (do this)")
        lines.append("")
        spec = list(pb.get("technical_spec") or pb.get("agent_notes") or [])
        target_page_urls = list(
            dict.fromkeys(
                (targets.get("urls") or [])
                + (targets.get("resolved_urls") or [])
            )
        )
        if insight.type in ("pagespeed_urgent", "pagespeed_improve"):
            finding_lines = _top_pagespeed_finding_lines(
                db, client_id, target_page_urls, limit=5
            )
            if finding_lines:
                lines.append("**Lighthouse opportunities (concrete offenders):**")
                lines.append("")
                for fl in finding_lines:
                    lines.append(f"- {fl}")
                lines.append("")
                # Prepend as numbered steps so agents act on real assets first
                spec = [
                    f"Address PSI finding: {fl}" for fl in finding_lines
                ] + spec
        if spec:
            for i, note in enumerate(spec, start=1):
                lines.append(f"{i}. {note}")
        else:
            lines.append("1. Implement the recommended action on the target assets.")
        if site_url:
            lines.append(f"{len(spec) + 1}. Site base URL: `{site_url}`")

        # Page-grounded copy (LLM) when we have a live snapshot; else template fill-in
        page_snap = None
        for u in target_page_urls[:3]:
            if u.startswith("http"):
                page_snap = fetch_page_snapshot(db, client_id, u)
                if page_snap:
                    break
        if not page_snap and site_url:
            page_snap = fetch_page_snapshot(db, client_id, site_url)

        if targets["queries"] and pb.get("copy_templates"):
            q0 = targets["queries"][0]
            brand = client.name.split(".")[0].title() if client.name else "Brand"
            rewritten = _rewrite_copy_from_page(
                query=q0,
                brand=brand,
                templates=list(pb["copy_templates"]),
                snap=page_snap,
            )
            lines.append("")
            if rewritten:
                lines.append(f"**Finished copy for query** `\"{q0}\"` (grounded in live page):")
                lines.append("")
                for line in rewritten:
                    lines.append(f"- {line}")
                if page_snap and (page_snap.title or page_snap.meta_description):
                    lines.append("")
                    lines.append(
                        f"_Current title:_ {page_snap.title or '—'}  \n"
                        f"_Current meta:_ {page_snap.meta_description or '—'}"
                    )
            else:
                lines.append(f"**Fill-in copy for query** `\"{q0}\"`:")
                lines.append("")
                for tmpl in pb["copy_templates"]:
                    filled = tmpl.replace("{Query}", q0).replace("{query}", q0)
                    filled = filled.replace("{Brand}", brand)
                    lines.append(f"- {filled}")
        elif pb.get("copy_templates"):
            lines.append("")
            lines.append("**Copy templates:**")
            lines.append("")
            for tmpl in pb["copy_templates"]:
                lines.append(f"- {tmpl}")
        lines.append("")

        lines.append("### Implementation checklist")
        lines.append("")
        steps = list(pb.get("steps") or [])
        if insight.type in ("pagespeed_urgent", "pagespeed_improve"):
            finding_lines = _top_pagespeed_finding_lines(
                db, client_id, target_page_urls, limit=5
            )
            for fl in finding_lines:
                steps.insert(0, f"Fix: {fl}")
        if steps:
            for step in steps:
                lines.append(f"- [ ] {step}")
        else:
            lines.append("- [ ] Complete recommended action")
            lines.append("- [ ] Verify production")
            lines.append("- [ ] Schedule metric recheck")
        lines.append("")

        if pb.get("anti_patterns"):
            lines.append("### Anti-patterns (do not do)")
            lines.append("")
            lines.append(_bullet_list(pb["anti_patterns"]))
            lines.append("")

        lines.append("### Measurement plan")
        lines.append("")
        ver = pb.get("verification") or [
            "Day 0: snapshot north-star metrics",
            "Day 14: confirm directional improvement",
            "Day 28: confirm sustained lift or iterate",
        ]
        for v in ver:
            lines.append(f"- [ ] {v}")
        lines.append("")
        lines.append("**Metrics to recheck:**")
        lines.append("")
        lines.append(
            _bullet_list(
                [f"`{m}`" for m in (pb.get("metrics_to_watch") or [])],
                empty="- Recheck the metric named in the finding",
            )
        )
        lines.append("")

        lines.append("### Agent handoff block (paste into PR / chat)")
        lines.append("")
        lines.append("```yaml")
        lines.append(f"fix_id: {insight.id}")
        lines.append(f"type: {insight.type}")
        lines.append(f"severity: {insight.severity}")
        lines.append(f"priority_score: {insight.priority_score or 0}")
        lines.append(f"title: {title}")
        lines.append(f"north_star: {pb.get('north_star') or pb.get('metric') or ''}")
        if uplift and uplift.get("potential_extra_clicks_28d") is not None:
            lines.append(
                f"estimated_extra_clicks_28d: {round(float(uplift['potential_extra_clicks_28d']), 1)}"
            )
        if targets["urls"]:
            lines.append("urls:")
            for u in targets["urls"]:
                lines.append(f"  - {u}")
        if targets["resolved_urls"]:
            lines.append("resolved_urls:")
            for u in targets["resolved_urls"]:
                lines.append(f"  - {u}")
        if targets["paths"]:
            lines.append("paths:")
            for p in targets["paths"]:
                lines.append(f"  - {p}")
        if targets["queries"]:
            lines.append("queries:")
            for qn in targets["queries"]:
                lines.append(f'  - "{qn}"')
        lines.append("finding: |")
        for fl in (insight.message or "").splitlines() or [""]:
            lines.append(f"  {fl}")
        lines.append("action: |")
        for fl in (insight.recommended_action or "").splitlines() or [""]:
            lines.append(f"  {fl}")
        lines.append("changes_made: |")
        lines.append("  # agent: list files/URLs changed")
        lines.append("day0_baseline: |")
        lines.append("  # agent: record clicks/CTR/CVR before")
        lines.append("recheck_at: Day 14")
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Execution wrap-up")
    lines.append("")
    lines.append(
        f"Processed **{len(insights)}** fix(es) for **{client.name}**. "
        f"Combined illustrative click unlock ≈ **{_fmt_num(total_potential_clicks)}** "
        "over ~28 days if gaps are closed."
    )
    lines.append("")
    lines.append("### Final agent checklist")
    lines.append("")
    lines.append("- [ ] Every fix shipped in priority order (or explicitly deferred with reason)")
    lines.append("- [ ] Each success contract implementation boxes checked")
    lines.append("- [ ] Day-0 baselines recorded for north-star metrics")
    lines.append("- [ ] Indexing requested for changed URLs")
    lines.append("- [ ] No do-not-touch violations")
    lines.append("- [ ] Calendar/reminder set for Day 7 / 14 / 28 rechecks")
    lines.append("- [ ] Client success scoreboard expected to move: **clicks → CTR → conversions/leads**")
    lines.append("")
    lines.append(
        "_End of Kinexis Coding Agent Success Fix Brief. "
        "Optimize relentlessly for more qualified clicks and the conversions that follow._"
    )
    lines.append("")

    return "\n".join(lines), filename
