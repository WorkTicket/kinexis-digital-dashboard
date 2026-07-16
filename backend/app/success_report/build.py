"""Assemble the client success report payload."""
from __future__ import annotations

import calendar
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Client,
    Insight,
    Task,
    ActionPlan,
    WeeklySummary,
    MonthlyReport,
    ContentBrief,
    GrowthLeverThread,
)
from app.funnel_analyzer import analyze_funnel
from app.opportunities import build_opportunities, campaign_performance
from app.success_report.branding import (
    GLOSSARY,
    agency_branding,
    attach_agency_branding,
    plain_label,
)
from app.success_report.metrics import (
    REPORT_PAYLOAD_VERSION,
    _baseline_deltas,
    _has_meaningful_period_data,
    _kpi_block,
    _month_bounds,
    _paid_kpi_block,
    _pct_change,
    _wins_in_period,
    compute_report_phase,
    get_client_baseline,
    inclusive_days,
    window_start,
)
from app.success_report.narrative import (
    _narrative_is_low_quality,
    generate_monthly_summary,
)
from app.impact_math import seasonality_caution, evidence_label

logger = logging.getLogger(__name__)

def build_success_report(
    db: Session,
    client_id: int,
    days: int = 30,
    year: Optional[int] = None,
    month: Optional[int] = None,
    *,
    refresh: bool = False,
) -> dict:
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return {"error": "not_found"}

    is_monthly = year is not None and month is not None

    # Prefer a previously saved monthly report unless explicitly refreshing
    if is_monthly and not refresh:
        existing = (
            db.query(MonthlyReport)
            .filter(
                MonthlyReport.client_id == client_id,
                MonthlyReport.year == year,
                MonthlyReport.month == month,
            )
            .first()
        )
        if existing and existing.payload_json:
            try:
                cached = json.loads(existing.payload_json)
                if isinstance(cached, dict) and cached.get("client"):
                    narrative = cached.get("narrative")
                    stale_math = cached.get("payload_version") != REPORT_PAYLOAD_VERSION
                    if stale_math:
                        logger.info(
                            "Rejecting cached monthly report (payload_version=%s want %s) for client %s %s-%02d",
                            cached.get("payload_version"),
                            REPORT_PAYLOAD_VERSION,
                            client_id,
                            year,
                            month,
                        )
                    elif narrative and _narrative_is_low_quality(str(narrative)):
                        # Stale/spam AI output — rebuild instead of serving garbage
                        logger.info(
                            "Rejecting cached monthly narrative for client %s %s-%02d",
                            client_id,
                            year,
                            month,
                        )
                    else:
                        cached["monthly_report_id"] = existing.id
                        cached["from_cache"] = True
                        return attach_agency_branding(db, cached)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "Corrupt MonthlyReport payload for client %s %s-%02d",
                    client_id,
                    year,
                    month,
                )

    if is_monthly:
        period_start, period_end = _month_bounds(year, month)
        if month == 1:
            prev_start, prev_end = _month_bounds(year - 1, 12)
        else:
            prev_start, prev_end = _month_bounds(year, month - 1)
        period_meta = {
            "mode": "monthly",
            "year": year,
            "month": month,
            "month_name": calendar.month_name[month],
            "days": (period_end - period_start).days + 1,
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        }
    else:
        today = date.today()
        period_end = today
        period_start = window_start(today, days)
        period_len = inclusive_days(period_start, period_end)
        prev_end = period_start - timedelta(days=1)
        prev_start = window_start(prev_end, period_len)
        period_meta = {
            "mode": "rolling",
            "days": period_len,
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        }

    kpis = [
        # Commercial Prove first — clients buy leads/revenue
        _kpi_block(db, client_id, "hubspot", "leads", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "hubspot", "opportunities", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "hubspot", "closed_won", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "hubspot", "revenue", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "ga4", "sessions", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "ga4", "key_events", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "gsc", "clicks", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "gsc", "impressions", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "gsc", "ctr", period_start, period_end, prev_start, prev_end, "avg"),
        _kpi_block(db, client_id, "gsc", "position", period_start, period_end, prev_start, prev_end, "avg"),
        _kpi_block(db, client_id, "bing", "clicks", period_start, period_end, prev_start, prev_end),
        # Rolled paid media (CSV + Google Ads + Meta)
        _paid_kpi_block(db, client_id, "cost", period_start, period_end, prev_start, prev_end),
        _paid_kpi_block(db, client_id, "clicks", period_start, period_end, prev_start, prev_end),
        _paid_kpi_block(db, client_id, "conversions", period_start, period_end, prev_start, prev_end),
        _paid_kpi_block(db, client_id, "conversion_value", period_start, period_end, prev_start, prev_end),
        # Per-channel detail
        _kpi_block(db, client_id, "ads_csv", "cost", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "ads_csv", "clicks", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "ads_csv", "conversions", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "ads_csv", "conversion_value", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "google_ads", "cost", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "google_ads", "clicks", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "google_ads", "conversions", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "google_ads", "conversion_value", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "meta_ads", "cost", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "meta_ads", "clicks", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "meta_ads", "conversions", period_start, period_end, prev_start, prev_end),
        _kpi_block(db, client_id, "meta_ads", "conversion_value", period_start, period_end, prev_start, prev_end),
    ]
    # Hide empty KPIs when those sources aren't connected / have no data
    kpis = [
        k for k in kpis
        if not (
            (k.get("current") or 0) == 0
            and (k.get("previous") or 0) == 0
        )
    ]

    sessions = next((k for k in kpis if k["key"] == "ga4.sessions"), None)
    conversions = next((k for k in kpis if k["key"] == "ga4.key_events"), None)
    if sessions and conversions:
        cvr = (conversions["current"] / sessions["current"] * 100) if sessions["current"] else 0
        prev_cvr = (conversions["previous"] / sessions["previous"] * 100) if sessions["previous"] else 0
        kpis.append({
            "key": "ga4.cvr",
            "label": plain_label("ga4.cvr"),
            "source": "ga4",
            "current": round(cvr, 2),
            "previous": round(prev_cvr, 2),
            "change_pct": _pct_change(cvr, prev_cvr),
        })

    funnel = analyze_funnel(
        client_id,
        period_start=period_start,
        period_end=period_end,
        db=db,
    )
    opps = build_opportunities(
        db,
        client_id,
        period_start=period_start,
        period_end=period_end,
        limit=10,
    )
    campaigns = campaign_performance(db, client_id, period_start, period_end, limit=12)

    start_dt = datetime.combine(period_start, datetime.min.time())
    end_dt = datetime.combine(period_end, datetime.max.time())

    resolved = (
        db.query(Insight)
        .filter(
            Insight.client_id == client_id,
            Insight.resolved == True,  # noqa: E712
            Insight.created_at >= start_dt,
            Insight.created_at <= end_dt,
        )
        .count()
    )
    open_insights = (
        db.query(Insight)
        .filter(Insight.client_id == client_id, Insight.resolved == False)  # noqa: E712
        .count()
    )
    completed_tasks = (
        db.query(Task)
        .filter(
            Task.client_id == client_id,
            Task.status == "done",
            Task.created_at >= start_dt,
            Task.created_at <= end_dt,
        )
        .all()
    )
    briefs_done = (
        db.query(ContentBrief)
        .filter(
            ContentBrief.client_id == client_id,
            ContentBrief.created_at >= start_dt,
            ContentBrief.created_at <= end_dt,
        )
        .count()
    )

    work = {
        "insights_resolved": resolved,
        "insights_open": open_insights,
        "tasks_completed": len(completed_tasks),
        "briefs_created": briefs_done,
        "completed_items": [
            {
                "task_id": t.id,
                "label": (t.result_notes or f"Task #{t.id}")[:160],
            }
            for t in completed_tasks[:20]
        ],
    }

    impact_wins = _wins_in_period(db, client_id, period_start, period_end)

    plan = (
        db.query(ActionPlan)
        .filter(ActionPlan.client_id == client_id, ActionPlan.status == "active")
        .order_by(ActionPlan.created_at.desc())
        .first()
    )
    next_actions = []
    if plan:
        try:
            actions = json.loads(plan.content)
            if isinstance(actions, list):
                next_actions = actions[:5]
        except (json.JSONDecodeError, TypeError):
            pass

    baseline = get_client_baseline(db, client_id)
    baseline_deltas = _baseline_deltas(
        baseline,
        kpis,
        compare_days=inclusive_days(period_start, period_end),
    )

    from app.success_contract import evaluate_success_contract
    from app.brand_queries import brand_split_totals

    contract_eval = evaluate_success_contract(db, client)
    # Prefer contract primary metric at the front of baseline deltas when present
    if contract_eval.get("configured") and baseline_deltas:
        primary = (contract_eval.get("contract") or {}).get("primary_metric")
        if primary:
            baseline_deltas = sorted(
                baseline_deltas,
                key=lambda d: 0 if d.get("key") == primary or d.get("metric") == primary else 1,
            )
    try:
        brand_split = brand_split_totals(db, client_id, days=min(days, 28) if not is_monthly else 28)
    except Exception:
        brand_split = None

    # Default spine: all proven levers unless explicitly excluded from report
    proven_lever_rows = (
        db.query(GrowthLeverThread)
        .filter(
            GrowthLeverThread.client_id == client_id,
            GrowthLeverThread.status == "proven",
            (GrowthLeverThread.include_in_report.is_(None))
            | (GrowthLeverThread.include_in_report.is_(True)),
        )
        .order_by(GrowthLeverThread.impact_score.desc())
        .limit(8)
        .all()
    )
    proven_lever_payload = []
    for t in proven_lever_rows:
        entry = {
            "title": t.title,
            "fix": t.fix,
            "impact_summary": t.impact_summary,
            "confidence_label": t.confidence_label,
        }
        if t.task_id:
            try:
                from app.impact_tracker import get_task_impact_summary as _task_summary

                task_summary = _task_summary(t.task_id)
                if task_summary.get("status") == "complete":
                    entry["evidence_label"] = task_summary.get("evidence_label")
                    entry["outcome"] = task_summary.get("outcome")
                    entry["avg_primary_metric_change"] = task_summary.get("avg_primary_metric_change")
                    entry["caution_notes"] = task_summary.get("caution_notes")
                    entry["proof_copy"] = task_summary.get("proof_copy")
                    entry["funnel_proof"] = task_summary.get("funnel_proof")
                    entry["revenue_story"] = task_summary.get("revenue_story")
            except Exception:
                pass
        proven_lever_payload.append(entry)
    funnel_stages = funnel.get("stages") or []
    totals = funnel.get("totals") or {}
    commercial_proof = {
        "story": "click → session → conversion → lead → revenue",
        "clicks": round(float(totals.get("clicks") or 0), 1),
        "sessions": round(float(totals.get("sessions") or 0), 1),
        "conversions": round(float(totals.get("conversions") or 0), 1),
        "leads": round(float(totals.get("leads") or 0), 1),
        "opportunities": round(float(totals.get("opportunities") or 0), 1),
        "closed_won": round(float(totals.get("closed_won") or 0), 1),
        "revenue": round(float(totals.get("revenue") or 0), 2),
        "has_crm": bool(funnel.get("has_crm")),
        "has_paid": bool(funnel.get("has_paid")),
        "biggest_leak": funnel.get("biggest_leak"),
        "primary_contract": (contract_eval.get("contract") or {}).get("primary_metric")
        if contract_eval.get("configured")
        else None,
    }

    if is_monthly:
        narrative = generate_monthly_summary(
            db,
            client_id,
            year,
            month,
            kpis,
            work,
            impact_wins,
            proven_levers=proven_lever_payload,
            funnel_stages=funnel_stages,
            baseline_deltas=baseline_deltas or [],
            next_actions=next_actions,
        )
    else:
        latest_summary = (
            db.query(WeeklySummary)
            .filter(WeeklySummary.client_id == client_id)
            .order_by(WeeklySummary.created_at.desc())
            .first()
        )
        narrative = latest_summary.content if latest_summary else None
        if narrative and _narrative_is_low_quality(narrative):
            narrative = None
        if not narrative:
            # Same no-data / soft template as monthly so the Report tab is never blank
            if not _has_meaningful_period_data(kpis, work, impact_wins):
                narrative = (
                    f"For the last {days} days, we do not yet have enough synced marketing data "
                    f"or completed work for {client.name} to summarize results. "
                    "Connect Cloudflare and Google, run Sync, then complete playbook tasks so "
                    "this report can show what changed, what we did, and what improved."
                )
            else:
                active = [
                    k for k in kpis
                    if (k.get("current") or 0) != 0
                    or (k.get("previous") or 0) != 0
                    or k.get("change_pct") is not None
                ]
                up = [k for k in active if (k.get("change_pct") or 0) > 0]
                down = [k for k in active if (k.get("change_pct") or 0) < 0]
                if not work.get("tasks_completed") and not impact_wins:
                    narrative = (
                        f"Diagnostic read for the last {days} days for {client.name}: "
                        "detections and prescriptions are available, but no work has been "
                        "executed and no wins are attributed yet. "
                    )
                    if down:
                        narrative += (
                            f"{down[0]['label']} is {down[0]['change_pct']:+.1f}% vs prior. "
                        )
                    elif baseline_deltas:
                        bd = next(
                            (d for d in baseline_deltas if d.get("change_pct") is not None),
                            None,
                        )
                        if bd:
                            narrative += (
                                f"{bd['label']} is {bd['change_pct']:+.1f}% vs engagement start. "
                            )
                    narrative += "Ship the top prescription, then regenerate this report."
                else:
                    narrative = (
                        f"Over the last {days} days we completed {work.get('tasks_completed', 0)} work items "
                        f"for {client.name} and resolved {work.get('insights_resolved', 0)} issues. "
                    )
                    if up:
                        narrative += f"Improvements included {up[0]['label']} ({up[0]['change_pct']:+.1f}%). "
                    if impact_wins:
                        narrative += (
                            f"We measured {len(impact_wins)} attributed "
                            f"win{'s' if len(impact_wins) != 1 else ''}. "
                        )
                    open_n = work.get("insights_open") or 0
                    if open_n:
                        narrative += f"{open_n} issue{'s' if open_n != 1 else ''} remain open. "
                    narrative += "Continue the highest-priority fixes from the current action plan."

    report_phase = compute_report_phase(
        completed_tasks=len(completed_tasks),
        impact_wins=impact_wins,
        proven_lever_count=len(proven_lever_payload),
    )

    report_month = period_meta.get("month") if is_monthly else period_end.month
    seasonality_note = seasonality_caution(report_month)

    return {
        "payload_version": REPORT_PAYLOAD_VERSION,
        "client": {
            "id": client.id,
            "name": client.name,
            "industry": client.industry,
            "brand_color": client.brand_color,
        },
        "agency": agency_branding(db, client),
        "period": period_meta,
        "report_phase": report_phase,
        "report_kind": "diagnostic" if report_phase == "baseline" else "success",
        "baseline": baseline,
        "baseline_deltas": baseline_deltas,
        "success_contract": contract_eval,
        "brand_split": brand_split,
        "kpis": kpis,
        "funnel": {
            "stages": funnel.get("stages") or [],
            "biggest_leak": funnel.get("biggest_leak"),
            "leaks": (funnel.get("leaks") or [])[:3],
            "growth_lever": funnel.get("growth_lever"),
            "totals": funnel.get("totals") or {},
            "rates": funnel.get("rates") or {},
        },
        "commercial_proof": commercial_proof,
        "opportunities": {
            "rising_queries": (opps.get("rising_queries") or [])[:8],
            "ctr_underperformers": (opps.get("ctr_underperformers") or [])[:8],
            "landing_pages": (opps.get("landing_pages") or [])[:8],
        },
        "campaigns": campaigns,
        "work": work,
        "impact_wins": impact_wins,
        # Top-level proven levers — lead client storytelling (not vanity SEO only)
        "proven_levers": proven_lever_payload,
        "next_actions": next_actions,
        "narrative": narrative,
        "glossary": [{"term": t, "definition": d} for t, d in GLOSSARY],
        "seasonality_caution": seasonality_note,
        "generated_at": date.today().isoformat(),
        "from_cache": False,
    }
