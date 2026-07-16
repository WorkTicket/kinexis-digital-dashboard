"""
Portfolio scoring — health, risk reasons, slipping detection, risk_rank, top actions.
Used by /actions/benchmark and informed by SEO + optional ads/CRM metrics.
"""

from __future__ import annotations

import math
import statistics
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.insight_scoring import effort_label, score_insight, why_it_matters
from app.models import Client, DataSource, Insight, MetricDaily, Task, GrowthLeverThread, ImpactSnapshot
from app.timeutil import utcnow
from app.dimensions import SITE_TOTAL_DIMENSION
from app.known_events import active_discontinuities, has_active_discontinuity, discontinuity_caveat

logger = logging.getLogger(__name__)

# Insight types that map to revenue / pipeline leaks — boost Today priority
REVENUE_INSIGHT_TYPES = {
    "ads_spend_low_leads",
    "leads_revenue_leak",
    "organic_leads_leak",
    "cro_opportunity",
    "bounce_cro_alert",
}


def metric_sum(
    db: Session,
    client_id: int,
    source: str,
    metric_name: str,
    start: date,
    end: date,
    dimension_type: Optional[str] = None,
) -> float:
    from app.metrics_service import sum_metric as _sum

    return _sum(db, client_id, source, metric_name, start, end, dimension_type)


def pct(cur: float, prev: float) -> Optional[float]:
    """Percent change. None when prior is zero — do not invent +100%."""
    from app.metrics_service import pct_change

    return pct_change(cur, prev)


def batch_metric_sums(
    db: Session,
    client_ids: list[int],
    specs: list[tuple[str, str, Optional[str]]],
    start: date,
    end: date,
) -> dict[tuple[int, str, str], float]:
    """
    One query per (source, metric, dim) across all clients.
    specs: list of (source, metric_name, dimension_type|None)
    Returns {(client_id, source, metric_name): sum} — dim is applied in filter only.
    """
    from app.metrics_service import batch_metric_sums as _batch

    return _batch(db, client_ids, specs, start, end)


def _sum_one_dimension(
    db: Session,
    client_id: int,
    source: str,
    metric_name: str,
    start: date,
    end: date,
    dimension_type: str,
) -> float:
    """Sum a single dimension type only — never across all dims (avoids N× inflation)."""
    filters = [
        MetricDaily.client_id == client_id,
        MetricDaily.source == source,
        MetricDaily.metric_name == metric_name,
        MetricDaily.date >= start,
        MetricDaily.date <= end,
    ]
    if dimension_type == "":
        filters.append(
            or_(MetricDaily.dimension_type == "", MetricDaily.dimension_type.is_(None))
        )
    else:
        filters.append(MetricDaily.dimension_type == dimension_type)
    val = db.query(func.sum(MetricDaily.value)).filter(and_(*filters)).scalar()
    return float(val or 0)


# When preferred dim is empty, try site total then one alternate at a time.
_GSC_FALLBACK_DIMS = ("", "query", "page")
_GA4_FALLBACK_DIMS = ("", "organic_channel")


def apply_gsc_ga4_sum_fallback(
    db: Session,
    client_ids: list[int],
    metric_map: dict[tuple[int, str, str], float],
    start: date,
    end: date,
) -> None:
    """Fill zero GSC/GA4 preferred-dimension sums from a single alternate dim.

    Order: site total (\"\") → one alternate dimension. Never SUM across all
    dimension types (that double-counts query+page+device+country).
    Mutates metric_map in place for this-week and prior-week windows.
    """
    for cid in client_ids:
        gsc_key = (cid, "gsc", "clicks")
        gsc_impr_key = (cid, "gsc", "impressions")
        if metric_map.get(gsc_key, 0) == 0 and metric_map.get(gsc_impr_key, 0) == 0:
            for dim in _GSC_FALLBACK_DIMS:
                clicks = _sum_one_dimension(db, cid, "gsc", "clicks", start, end, dim)
                impr = _sum_one_dimension(db, cid, "gsc", "impressions", start, end, dim)
                if clicks > 0 or impr > 0:
                    metric_map[gsc_key] = clicks
                    metric_map[gsc_impr_key] = impr
                    break
        ga4_sess_key = (cid, "ga4", "sessions")
        ga4_conv_key = (cid, "ga4", "key_events")
        if metric_map.get(ga4_sess_key, 0) == 0 and metric_map.get(ga4_conv_key, 0) == 0:
            for dim in _GA4_FALLBACK_DIMS:
                sessions = _sum_one_dimension(db, cid, "ga4", "sessions", start, end, dim)
                conversions = _sum_one_dimension(
                    db, cid, "ga4", "key_events", start, end, dim
                )
                if sessions > 0 or conversions > 0:
                    metric_map[ga4_sess_key] = sessions
                    metric_map[ga4_conv_key] = conversions
                    break


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.0f}%"


def _insight_kind(ins: Insight) -> str:
    k = (getattr(ins, "kind", None) or "").strip().lower()
    if k in ("problem", "opportunity"):
        return k
    from app.insight_scoring import default_kind

    return default_kind(ins.type or "")


def _problems_only(open_insights: list[Insight]) -> list[Insight]:
    return [i for i in open_insights if _insight_kind(i) == "problem"]


def _opportunities_only(open_insights: list[Insight]) -> list[Insight]:
    return [i for i in open_insights if _insight_kind(i) == "opportunity"]


def pick_score_driven_action(
    *,
    health_score: int,
    avg_ctr: float,
    gsc_clicks: float,
    gsc_impressions: float,
    ga4_sessions: float,
    conversion_rate: float,
    leads: float,
    revenue: float,
    ad_cost: float,
    stale_days: Optional[int],
) -> Optional[dict[str, Any]]:
    """Growth play from weak health pillars when no insight/task exists.

    Health can be low from volume/efficiency alone — without open insights —
    so agents still get a concrete next step to raise the score.
    """
    if health_score <= 0 or health_score >= 85:
        return None

    # Pillar points (same bands as compute_client_portfolio_row)
    ctr_pts = (
        15 if avg_ctr >= 5 else
        12 if avg_ctr >= 3.5 else
        8 if avg_ctr >= 2 else
        5 if avg_ctr >= 1 else
        2 if avg_ctr > 0 else 0
    )
    volume_pts = (
        10 if gsc_clicks >= 500 else
        7 if gsc_clicks >= 100 else
        4 if gsc_clicks >= 25 else
        2 if gsc_clicks > 0 else 0
    )
    search_visibility = ctr_pts + volume_pts

    cvr_pts = (
        15 if conversion_rate >= 8 else
        12 if conversion_rate >= 5 else
        9 if conversion_rate >= 3 else
        6 if conversion_rate >= 1.5 else
        3 if conversion_rate > 0 else 0
    )
    business_pts = (
        10 if revenue > 0 else
        8 if leads >= 5 else
        5 if leads >= 1 else
        3 if conversion_rate > 0 else 0
    )
    conversion_performance = cvr_pts + business_pts

    traffic_quality = (
        15 if ga4_sessions >= 1000 else
        11 if ga4_sessions >= 300 else
        7 if ga4_sessions >= 100 else
        4 if ga4_sessions >= 20 else
        2 if ga4_sessions > 0 else 0
    )

    if ad_cost > 0 and leads > 0:
        cpl = ad_cost / leads
        efficiency_pts = (
            20 if cpl <= 20 else
            16 if cpl <= 50 else
            11 if cpl <= 100 else
            6 if cpl <= 200 else 3
        )
    elif revenue > 0:
        efficiency_pts = 14
    elif ad_cost <= 0 and (gsc_clicks > 0 or ga4_sessions > 0):
        efficiency_pts = 11
    elif ad_cost > 0 and leads <= 0:
        efficiency_pts = 0
    else:
        efficiency_pts = 3

    # Normalized weakness (higher = worse relative to pillar max)
    pillars: list[tuple[str, float, dict[str, Any]]] = [
        (
            "visibility",
            1.0 - (search_visibility / 25.0),
            {
                "title": "Grow search visibility",
                "detail": (
                    f"Only {gsc_clicks:.0f} clicks / {gsc_impressions:.0f} impressions this week. "
                    "Publish topical content + fix titles on high-impression pages."
                    if gsc_impressions > 0
                    else "Connect GSC and ship content clusters around core service pages."
                ),
                "cta_tab": "prescribe",
                "effort": "high",
                "playbook": "grow_visibility",
            },
        ),
        (
            "engagement",
            (1.0 - (ctr_pts / 15.0)) if gsc_impressions > 0 else 0.0,
            {
                "title": "Lift CTR on high-impression queries",
                "detail": (
                    f"CTR at {avg_ctr:.1f}% — rewrite titles/metas on top impression pages "
                    "to win more of the traffic you already earn."
                ),
                "cta_tab": "prescribe",
                "effort": "low",
                "playbook": "lift_ctr",
            },
        ),
        (
            "conversion",
            1.0 - (conversion_performance / 25.0),
            {
                "title": "Turn traffic into leads",
                "detail": (
                    f"CVR {conversion_rate:.1f}% with {leads:.0f} leads. "
                    "Add above-fold CTAs and shorten forms on top landing pages."
                    if ga4_sessions > 0
                    else "Set up GA4 key events, then optimize landing-page CTAs."
                ),
                "cta_tab": "prescribe",
                "effort": "medium",
                "playbook": "raise_cvr",
            },
        ),
        (
            "traffic",
            1.0 - (traffic_quality / 15.0),
            {
                "title": "Build qualified traffic",
                "detail": (
                    f"Only {ga4_sessions:.0f} sessions this week. "
                    "Expand keyword coverage and internal links to grow engaged visits."
                ),
                "cta_tab": "prescribe",
                "effort": "high",
                "playbook": "grow_traffic",
            },
        ),
        (
            "efficiency",
            1.0 - (efficiency_pts / 20.0),
            {
                "title": (
                    "Stop wasted ad spend"
                    if ad_cost > 0 and leads <= 0
                    else "Improve lead efficiency"
                ),
                "detail": (
                    f"${ad_cost:.0f} ad spend with 0 leads — pause weak campaigns and "
                    "fix landing-page conversion before scaling spend."
                    if ad_cost > 0 and leads <= 0
                    else "Tighten targeting and landing-page match to lower cost per lead."
                ),
                "cta_tab": "prescribe",
                "effort": "medium",
                "playbook": "fix_efficiency",
            },
        ),
    ]

    if stale_days is not None and stale_days >= 3:
        pillars.append(
            (
                "sync",
                0.95,
                {
                    "title": "Refresh stale data",
                    "detail": f"Sources are {stale_days}d stale — sync so diagnosis and fixes stay accurate.",
                    "cta_tab": "detect",
                    "effort": "low",
                    "playbook": "sync_data",
                },
            )
        )

    # Prefer pillars that are meaningfully weak
    ranked = sorted(
        [(name, weakness, action) for name, weakness, action in pillars if weakness >= 0.25],
        key=lambda x: x[1],
        reverse=True,
    )
    if not ranked:
        return {
            "title": "Run the next growth experiment",
            "detail": "Health is improvable — open Prescribe for score-driven plays on the weakest pillars.",
            "insight_id": None,
            "task_id": None,
            "cta_tab": "prescribe",
            "effort": "medium",
            "playbook": "growth_experiment",
        }

    _, _, action = ranked[0]
    return {
        "title": action["title"],
        "detail": action["detail"][:160],
        "insight_id": None,
        "task_id": None,
        "cta_tab": action["cta_tab"],
        "effort": action["effort"],
        "playbook": action.get("playbook"),
    }


def pick_top_action(
    open_insights: list[Insight],
    open_tasks: list[Task],
    *,
    health_score: Optional[int] = None,
    avg_ctr: float = 0.0,
    gsc_clicks: float = 0.0,
    gsc_impressions: float = 0.0,
    ga4_sessions: float = 0.0,
    conversion_rate: float = 0.0,
    leads: float = 0.0,
    revenue: float = 0.0,
    ad_cost: float = 0.0,
    stale_days: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """Highest-value next action for a client row (problems preferred)."""
    best_ins: Optional[Insight] = None
    best_score = -1.0
    # Prefer must-fix problems; fall back to opportunities only if none
    candidates = _problems_only(open_insights) or open_insights
    for ins in candidates:
        s = float(ins.priority_score or score_insight(ins.severity, ins.type))
        if ins.type in REVENUE_INSIGHT_TYPES:
            s += 15
        if ins.severity == "high":
            s += 10
        if _insight_kind(ins) == "problem":
            s += 5
        if s > best_score:
            best_score = s
            best_ins = ins

    overdue_or_stuck = [
        t
        for t in open_tasks
        if t.status in ("open", "in_progress")
        and (
            (t.due_date and t.due_date < date.today())
            or t.status == "in_progress"
            or (t.created_at and (utcnow() - t.created_at).days >= 7)
        )
    ]
    if overdue_or_stuck and (not best_ins or best_score < 75):
        task = sorted(
            overdue_or_stuck,
            key=lambda t: (
                0 if (t.due_date and t.due_date < date.today()) else 1,
                t.due_date or date.max,
            ),
        )[0]
        overdue = bool(task.due_date and task.due_date < date.today())
        return {
            "title": "Overdue work" if overdue else "Active work needs attention",
            "detail": (task.result_notes or f"Task #{task.id}")[:160],
            "task_id": task.id,
            "insight_id": task.insight_id,
            "cta_tab": "execute",
            "effort": "medium",
        }

    if best_ins:
        return {
            "title": why_it_matters(best_ins.type),
            "detail": (best_ins.message or "")[:160],
            "insight_id": best_ins.id,
            "task_id": None,
            "cta_tab": "prescribe",
            "effort": effort_label(best_ins.type),
        }

    # No insights/tasks — still prescribe a score-raising play when health is weak
    if health_score is not None:
        return pick_score_driven_action(
            health_score=health_score,
            avg_ctr=avg_ctr,
            gsc_clicks=gsc_clicks,
            gsc_impressions=gsc_impressions,
            ga4_sessions=ga4_sessions,
            conversion_rate=conversion_rate,
            leads=leads,
            revenue=revenue,
            ad_cost=ad_cost,
            stale_days=stale_days,
        )
    return None


def compute_client_portfolio_row(
    client: Client,
    db: Session,
    *,
    gsc_clicks: float,
    gsc_clicks_prev: float,
    gsc_clicks_prev2: float,
    gsc_impressions: float,
    ga4_sessions: float,
    ga4_sessions_prev: float,
    ga4_conversions: float,
    ga4_conversions_prev: float,
    day_count: int,
    leads: float,
    leads_prev: float,
    revenue: float,
    revenue_prev: float,
    ad_cost: float,
    ad_cost_prev: float,
    open_insights: list[Insight],
    open_tasks: list[Task],
    last_sync: Optional[datetime],
    today: date,
) -> dict[str, Any]:
    problems = _problems_only(open_insights)
    opportunities = _opportunities_only(open_insights)
    high = sum(1 for i in problems if i.severity == "high")
    medium = sum(1 for i in problems if i.severity == "medium")
    open_task_count = sum(1 for t in open_tasks if t.status not in ("done", "skipped"))
    overdue_tasks = sum(
        1
        for t in open_tasks
        if t.status not in ("done", "skipped") and t.due_date and t.due_date < today
    )

    stale_days: Optional[int] = None
    if last_sync is None:
        stale_days = 999
    else:
        stale_days = max(0, (utcnow() - last_sync).days)

    # Unified discontinuity check — site relaunch, Google core updates,
    # and seasonal events all invalidate WoW trend comparisons.
    discontinuities = active_discontinuities(db, client.id, today)
    any_discontinuity = has_active_discontinuity(discontinuities)
    relaunch_discontinuity = next(
        (d for d in discontinuities if d["type"] == "site_relaunch"), None
    )
    days_since_relaunch = (
        relaunch_discontinuity["days_since"]
        if relaunch_discontinuity
        else None
    )

    wow = {
        "clicks": pct(gsc_clicks, gsc_clicks_prev),
        "sessions": pct(ga4_sessions, ga4_sessions_prev),
        "conversions": pct(ga4_conversions, ga4_conversions_prev),
        "leads": pct(leads, leads_prev) if (leads or leads_prev) else None,
        "revenue": pct(revenue, revenue_prev) if (revenue or revenue_prev) else None,
        "ad_cost": pct(ad_cost, ad_cost_prev) if (ad_cost or ad_cost_prev) else None,
    }

    # Multi-week slip: this week vs prev, and prev vs prev2
    clicks_wow = wow["clicks"]
    sessions_wow = wow["sessions"]
    prev_week_vs_prior = pct(gsc_clicks_prev, gsc_clicks_prev2)
    consecutive_click_decline = (
        clicks_wow is not None
        and clicks_wow < -5
        and prev_week_vs_prior is not None
        and prev_week_vs_prior < -5
        and gsc_clicks_prev >= 20
        and gsc_clicks_prev2 >= 20
    )
    thin_for_slip = gsc_clicks < 25 and ga4_sessions < 50 and leads <= 0 and ad_cost <= 0
    slipping = bool(
        not thin_for_slip
        and (
            (clicks_wow is not None and clicks_wow < -10 and sessions_wow is not None and sessions_wow < 0)
            or consecutive_click_decline
            or (wow["leads"] is not None and wow["leads"] < -15 and leads_prev > 0)
            or (
                wow["ad_cost"] is not None
                and wow["ad_cost"] > 20
                and wow["leads"] is not None
                and wow["leads"] <= 0
                and ad_cost > 0
            )
        )
    )

    raw_ctr = (gsc_clicks / gsc_impressions * 100) if gsc_impressions > 0 else 0.0
    raw_cvr = (ga4_conversions / ga4_sessions * 100) if ga4_sessions > 0 else 0.0

    # Industry-adjusted CTR/CVR (same bands as frontend health.ts)
    industry = (getattr(client, "industry", None) or "").lower()
    if any(x in industry for x in ("e-commerce", "retail")):
        ctr_mul, cvr_mul = 1.0, 0.8
    elif any(x in industry for x in ("finance", "insurance")):
        ctr_mul, cvr_mul = 0.8, 0.6
    elif "health" in industry:
        ctr_mul, cvr_mul = 1.1, 0.7
    elif "real estate" in industry:
        ctr_mul, cvr_mul = 0.9, 0.5
    elif "legal" in industry:
        ctr_mul, cvr_mul = 0.7, 0.4
    elif "education" in industry:
        ctr_mul, cvr_mul = 1.0, 0.7
    elif "manufacturing" in industry:
        ctr_mul, cvr_mul = 0.8, 0.5
    elif any(x in industry for x in ("technology", "saas")):
        ctr_mul, cvr_mul = 0.9, 0.6
    elif any(x in industry for x in ("hospitality", "travel")):
        ctr_mul, cvr_mul = 1.1, 0.7
    else:
        ctr_mul, cvr_mul = 1.0, 1.0

    avg_ctr = raw_ctr * ctr_mul
    conversion_rate = raw_cvr * cvr_mul

    thin_traffic = (
        gsc_clicks < 25
        and ga4_sessions < 50
        and leads <= 0
        and ad_cost <= 0
    )

    # ── Agency-standard health score ───────────────────────────────────
    # Weighted pillars (0–100). CTR/CVR use industry-adjusted rates.
    # Window is the trailing 7 days (caller supplies week vs prior week).

    has_any_metric = bool(gsc_clicks or gsc_impressions or ga4_sessions or leads or revenue or ad_cost)

    search_visibility = 0
    conversion_performance = 0
    traffic_quality = 0
    efficiency_pts = 0
    technical = 0

    if not has_any_metric and not problems:
        score = 0
    else:
        # ── 1. Search Visibility (25 pts) ── CTR against benchmarks + volume
        ctr_pts = (
            15 if avg_ctr >= 5 else
            12 if avg_ctr >= 3.5 else
            8 if avg_ctr >= 2 else
            5 if avg_ctr >= 1 else
            2 if avg_ctr > 0 else 0
        )
        volume_pts = (
            10 if gsc_clicks >= 500 else
            7 if gsc_clicks >= 100 else
            4 if gsc_clicks >= 25 else
            2 if gsc_clicks > 0 else 0
        )
        search_visibility = ctr_pts + volume_pts

        # ── 2. Conversion Performance (25 pts) ── CVR + business outcomes
        cvr_pts = (
            15 if conversion_rate >= 8 else
            12 if conversion_rate >= 5 else
            9 if conversion_rate >= 3 else
            6 if conversion_rate >= 1.5 else
            3 if conversion_rate > 0 else 0
        )
        business_pts = (
            10 if revenue > 0 else
            8 if leads >= 5 else
            5 if leads >= 1 else
            3 if ga4_conversions > 0 else 0
        )
        conversion_performance = cvr_pts + business_pts

        # ── 3. Traffic Quality (15 pts) ── Active site engagement
        traffic_quality = (
            15 if ga4_sessions >= 1000 else
            11 if ga4_sessions >= 300 else
            7 if ga4_sessions >= 100 else
            4 if ga4_sessions >= 20 else
            2 if ga4_sessions > 0 else 0
        )

        # ── 4. Efficiency (20 pts) ── Cost per lead / organic efficiency
        efficiency_pts = 0
        if ad_cost > 0 and leads > 0:
            cpl = ad_cost / leads
            efficiency_pts = (
                20 if cpl <= 20 else
                16 if cpl <= 50 else
                11 if cpl <= 100 else
                6 if cpl <= 200 else 3
            )
        elif revenue > 0:
            efficiency_pts = 14
        elif ad_cost <= 0 and (gsc_clicks > 0 or ga4_sessions > 0):
            efficiency_pts = 11
        elif ad_cost > 0 and leads <= 0:
            efficiency_pts = 0
        else:
            efficiency_pts = 3

        # ── 5. Technical & Foundation Health (10 pts) ── deduct red flags
        technical = 10

        # ── Pillar sum before momentum ─────────────────────────────────
        score = search_visibility + conversion_performance + traffic_quality + efficiency_pts + technical

        # ── Momentum bonus (WoW improvements) ─────────────────────────
        if not thin_traffic:
            if (clicks_wow or 0) > 10:
                score += 3
            if (sessions_wow or 0) > 10:
                score += 2
            if (wow["conversions"] or 0) > 10:
                score += 2
            if (wow["leads"] or 0) is not None and (wow["leads"] or 0) > 10:
                score += 2
            if (wow["revenue"] or 0) is not None and (wow["revenue"] or 0) > 10:
                score += 1
        else:
            if (clicks_wow or 0) > 50 and gsc_clicks >= 5:
                score += 2

        # ── WoW decline penalties (skipped during known discontinuities — site
        # relaunch, core updates, etc. — where trends are not comparable) ─
        if not any_discontinuity:
            if not thin_traffic:
                if (clicks_wow or 0) < -20:
                    score -= 5
                elif (clicks_wow or 0) < -10:
                    score -= 3
                if (sessions_wow or 0) < -20:
                    score -= 4
                elif (sessions_wow or 0) < -10:
                    score -= 2
                if (wow["conversions"] or 0) < -20:
                    score -= 4
                if (wow["leads"] or 0) is not None and (wow["leads"] or 0) < -20:
                    score -= 3
                if (wow["revenue"] or 0) is not None and (wow["revenue"] or 0) < -20:
                    score -= 2
            else:
                if (clicks_wow or 0) < -50 and gsc_clicks_prev >= 10:
                    score -= 3

            # Ad spend waste
            if (
                wow["ad_cost"] is not None
                and wow["ad_cost"] > 25
                and wow["leads"] is not None
                and wow["leads"] <= 0
            ):
                score -= 5

        # Issue penalty (capped at 40, 12 for thin traffic)
        weighted = high * 3 + medium
        if weighted > 0:
            ip = weighted if weighted <= 20 else min(40, 20 + round(math.log2(1 + weighted - 20) * 4))
            if thin_traffic:
                ip = min(ip, 12)
            score -= ip

        # Overdue tasks
        if overdue_tasks:
            score -= min(15, overdue_tasks * 3)

        # Stale sync (skipped during known discontinuities)
        if stale_days is not None and stale_days >= 3 and not any_discontinuity:
            score -= min(12, stale_days)

    score = max(0, min(100, score))

    # "0" has special meaning (no_data). When ANY metric data or problems
    # exist, floor to 1 so the UI distinguishes "building baseline" from
    # "never connected." Prevents the misleading "0 SCORE" next to real traffic.
    if score == 0 and (has_any_metric or problems):
        score = 1

    # Client priority weight (1=normal, 2=high, 3=vip)
    client_priority = int(getattr(client, "priority", None) or 1)
    client_priority = max(1, min(3, client_priority))

    # Opportunities never drive critical risk — only must-fix problems.
    medium_for_risk = 0 if thin_traffic else medium
    CRISIS_TYPES = {
        "decline_alert",
        "error_spike_alert",
        "ads_spend_low_leads",
        "leads_revenue_leak",
        "organic_leads_leak",
        "ctr_gap",
    }
    crisis_high = sum(
        1
        for i in problems
        if i.severity == "high" and (i.type or "") in CRISIS_TYPES
    )
    meaningful_decline = (
        not thin_traffic
        and not any_discontinuity
        and (
            (clicks_wow is not None and clicks_wow < -20 and gsc_clicks_prev >= 20)
            or (sessions_wow is not None and sessions_wow < -20 and ga4_sessions_prev >= 50)
        )
    )

    if relaunch_discontinuity:
        risk = "stabilizing"
    elif score == 0 and not problems:
        risk = "no_data"
    elif score == 1 and has_any_metric and not problems:
        # Has real data but pillars are thin — watch, never "no_data" (0 SCORE trust tax)
        risk = "watch"
    elif (
        crisis_high > 0
        or overdue_tasks >= 3
        or (high > 0 and not thin_traffic)
        or (score < 40 and not thin_traffic)
        or meaningful_decline
    ):
        risk = "critical"
    elif thin_traffic and (score < 55 or high > 0):
        risk = "watch"
    elif score < 55 or medium_for_risk > 2 or slipping or overdue_tasks > 0:
        risk = "watch"
    else:
        risk = "healthy"

    risk_reasons: list[str] = []
    has_traffic = gsc_clicks > 0 or gsc_impressions > 0 or ga4_sessions > 0
    if thin_traffic and has_traffic:
        risk_reasons.append("Low traffic sample — treat swings cautiously")
    if clicks_wow is not None and clicks_wow < -5 and not thin_traffic:
        risk_reasons.append(f"Clicks {_fmt_pct(clicks_wow)} WoW")
    if sessions_wow is not None and sessions_wow < -5 and not thin_traffic:
        risk_reasons.append(f"Sessions {_fmt_pct(sessions_wow)} WoW")
    if wow["conversions"] is not None and wow["conversions"] < -10 and not thin_traffic:
        risk_reasons.append(f"Conversions {_fmt_pct(wow['conversions'])} WoW")
    if wow["leads"] is not None and wow["leads"] < -10:
        risk_reasons.append(f"Leads {_fmt_pct(wow['leads'])} WoW")
    if wow["revenue"] is not None and wow["revenue"] < -10:
        risk_reasons.append(f"Revenue {_fmt_pct(wow['revenue'])} WoW")
    if (
        wow["ad_cost"] is not None
        and wow["ad_cost"] > 15
        and (wow["leads"] is None or wow["leads"] <= 0)
        and ad_cost > 0
    ):
        risk_reasons.append(f"Spend {_fmt_pct(wow['ad_cost'])}, leads flat")
    if high > 0:
        top_high = sorted(
            [i for i in problems if (i.severity or "").lower() == "high"],
            key=lambda i: float(i.priority_score or 0),
            reverse=True,
        )
        if top_high and top_high[0].message:
            snippet = (top_high[0].message or "").strip()
            if len(snippet) > 90:
                snippet = snippet[:87].rstrip() + "…"
            risk_reasons.append(
                f"{high} high-severity problem{'s' if high != 1 else ''}: {snippet}"
            )
        else:
            risk_reasons.append(f"{high} high-severity problem{'s' if high != 1 else ''}")
    elif medium_for_risk > 2:
        top_med = sorted(
            problems,
            key=lambda i: float(i.priority_score or 0),
            reverse=True,
        )
        if top_med and top_med[0].message:
            snippet = (top_med[0].message or "").strip()
            if len(snippet) > 90:
                snippet = snippet[:87].rstrip() + "…"
            risk_reasons.append(f"{medium} open medium problems — e.g. {snippet}")
        else:
            risk_reasons.append(f"{medium} open medium problems")
    if overdue_tasks:
        risk_reasons.append(f"{overdue_tasks} overdue task{'s' if overdue_tasks != 1 else ''}")
    if stale_days is not None and stale_days >= 3:
        if stale_days >= 999:
            risk_reasons.append("Never synced")
        else:
            risk_reasons.append(f"Sync stale {stale_days}d")
    if consecutive_click_decline and not thin_traffic:
        risk_reasons.append("Clicks down 2 weeks in a row")
    if slipping and not thin_traffic and not any("slip" in r.lower() or "down 2" in r.lower() for r in risk_reasons):
        risk_reasons.append("Slipping vs prior weeks")
    # Discontinuity caveat — single sentence at top of risk reasons
    if any_discontinuity:
        caveat = discontinuity_caveat(discontinuities)
        if caveat and caveat not in risk_reasons:
            risk_reasons.insert(0, caveat)
    if not risk_reasons and risk == "healthy":
        risk_reasons.append("On track")
    if not risk_reasons and risk == "no_data":
        risk_reasons.append("No traffic data yet")
    if not risk_reasons and risk == "watch" and thin_traffic:
        risk_reasons.append("Building baseline — limited data")

    # Continuous risk_rank: lower = more urgent (for sorting)
    risk_bucket = {"critical": 0, "stabilizing": 1, "watch": 1, "healthy": 2, "no_data": 3}[risk]
    risk_rank = (
        risk_bucket * 1000
        + score
        - high * 40
        - overdue_tasks * 25
        - (20 if slipping else 0)
        - (min(30, stale_days) if stale_days is not None and stale_days < 999 else (40 if stale_days == 999 else 0))
        - client_priority * 15
        - (10 if (wow["leads"] is not None and wow["leads"] < -10) else 0)
    )

    top_action = pick_top_action(
        open_insights,
        open_tasks,
        health_score=int(score),
        avg_ctr=avg_ctr,
        gsc_clicks=gsc_clicks,
        gsc_impressions=gsc_impressions,
        ga4_sessions=ga4_sessions,
        conversion_rate=conversion_rate,
        leads=leads,
        revenue=revenue,
        ad_cost=ad_cost,
        stale_days=None if stale_days == 999 and last_sync is None else stale_days,
    )

    # Pillar breakdown so UI can show what to raise (not only a single number)
    pillars = {
        "search_visibility": round(search_visibility, 1),
        "conversion_performance": round(conversion_performance, 1),
        "traffic_quality": round(traffic_quality, 1),
        "efficiency": round(efficiency_pts, 1),
        "technical": round(technical, 1),
    }

    return {
        "client_id": client.id,
        "name": client.name,
        "industry": client.industry,
        "brand_color": client.brand_color,
        "owner": getattr(client, "owner", None) or "",
        "priority": client_priority,
        "health_score": score,
        "risk": risk,
        "risk_reasons": risk_reasons[:6],
        "slipping": slipping,
        "stale_days": None if stale_days == 999 and last_sync is None else (stale_days if last_sync else None),
        "overdue_tasks": overdue_tasks,
        "risk_rank": round(risk_rank, 1),
        "top_action": top_action,
        "pillars": pillars,
        "open_insights": len(problems),
        "open_insights_high": high,
        "open_opportunities": len(opportunities),
        "open_tasks": open_task_count,
        "last_synced_at": last_sync.isoformat() if last_sync else None,
        "site_relaunched_at": client.site_relaunched_at.isoformat() if client.site_relaunched_at else None,
        "days_since_relaunch": days_since_relaunch,
        "wow": wow,
        "metrics": {
            "gsc_clicks": round(gsc_clicks, 1),
            "gsc_impressions": round(gsc_impressions, 1),
            "ga4_sessions": round(ga4_sessions, 1),
            "ga4_conversions": round(ga4_conversions, 1),
            # Raw rates for display; scoring used industry-adjusted values above
            "ctr": round(raw_ctr, 4) if raw_ctr <= 1 else round(raw_ctr, 2),
            "conversion_rate": round(raw_cvr, 2),
            "leads": round(leads, 1),
            "revenue": round(revenue, 2),
            "ad_cost": round(ad_cost, 2),
        },
        "rankings": {},
        "success_contract": None,
    }


def build_client_health_detail(db: Session, client_id: int) -> Optional[dict[str, Any]]:
    """Authoritative health for one client (7d window) — does not scan the full portfolio."""
    client = (
        db.query(Client)
        .filter(Client.id == client_id)
        .first()
    )
    if not client:
        return None

    today = date.today()
    this_start = today - timedelta(days=6)
    prev_start = today - timedelta(days=13)
    prev_end = today - timedelta(days=7)
    prev2_start = today - timedelta(days=20)
    prev2_end = today - timedelta(days=14)
    day_count = max(1, (today - this_start).days + 1)
    cid = client.id

    gsc_dim = SITE_TOTAL_DIMENSION.get("gsc")
    ga4_dim = SITE_TOTAL_DIMENSION.get("ga4")

    def _sum(source: str, metric: str, start: date, end: date, dim: Optional[str] = None) -> float:
        return metric_sum(db, cid, source, metric, start, end, dim)

    gsc_clicks = _sum("gsc", "clicks", this_start, today, gsc_dim)
    gsc_impr = _sum("gsc", "impressions", this_start, today, gsc_dim)
    if gsc_clicks == 0 and gsc_impr == 0:
        gsc_clicks = _sum("gsc", "clicks", this_start, today, None)
        gsc_impr = _sum("gsc", "impressions", this_start, today, None)

    ga4_sessions = _sum("ga4", "sessions", this_start, today, ga4_dim)
    ga4_conversions = _sum("ga4", "key_events", this_start, today, ga4_dim)
    if ga4_sessions == 0 and ga4_conversions == 0:
        ga4_sessions = _sum("ga4", "sessions", this_start, today, None)
        ga4_conversions = _sum("ga4", "key_events", this_start, today, None)

    leads = _sum("hubspot", "leads", this_start, today, None)
    revenue = _sum("hubspot", "revenue", this_start, today, None)
    ad_cost = (
        _sum("ads_csv", "cost", this_start, today, SITE_TOTAL_DIMENSION.get("ads_csv"))
        + _sum("google_ads", "cost", this_start, today, SITE_TOTAL_DIMENSION.get("google_ads"))
        + _sum("meta_ads", "cost", this_start, today, SITE_TOTAL_DIMENSION.get("meta_ads"))
    )

    open_insights = (
        db.query(Insight)
        .filter(Insight.client_id == cid, Insight.resolved == False)  # noqa: E712
        .all()
    )
    open_tasks = (
        db.query(Task)
        .filter(Task.client_id == cid, Task.status.notin_(["done", "skipped"]))
        .all()
    )
    last_sync = (
        db.query(func.max(DataSource.last_synced_at))
        .filter(DataSource.client_id == cid)
        .scalar()
    )

    row = compute_client_portfolio_row(
        client,
        db,
        gsc_clicks=gsc_clicks,
        gsc_clicks_prev=_sum("gsc", "clicks", prev_start, prev_end, gsc_dim) or _sum("gsc", "clicks", prev_start, prev_end, None),
        gsc_clicks_prev2=_sum("gsc", "clicks", prev2_start, prev2_end, gsc_dim) or _sum("gsc", "clicks", prev2_start, prev2_end, None),
        gsc_impressions=gsc_impr,
        ga4_sessions=ga4_sessions,
        ga4_sessions_prev=_sum("ga4", "sessions", prev_start, prev_end, ga4_dim) or _sum("ga4", "sessions", prev_start, prev_end, None),
        ga4_conversions=ga4_conversions,
        ga4_conversions_prev=_sum("ga4", "key_events", prev_start, prev_end, ga4_dim) or _sum("ga4", "key_events", prev_start, prev_end, None),
        day_count=day_count,
        leads=leads,
        leads_prev=_sum("hubspot", "leads", prev_start, prev_end, None),
        revenue=revenue,
        revenue_prev=_sum("hubspot", "revenue", prev_start, prev_end, None),
        ad_cost=ad_cost,
        ad_cost_prev=(
            _sum("ads_csv", "cost", prev_start, prev_end, SITE_TOTAL_DIMENSION.get("ads_csv"))
            + _sum("google_ads", "cost", prev_start, prev_end, SITE_TOTAL_DIMENSION.get("google_ads"))
            + _sum("meta_ads", "cost", prev_start, prev_end, SITE_TOTAL_DIMENSION.get("meta_ads"))
        ),
        open_insights=open_insights,
        open_tasks=open_tasks,
        last_sync=last_sync,
        today=today,
    )

    # Attach success contract (same as portfolio path)
    from app.success_contract import evaluate_success_contract, parse_success_contract

    contract_eval = {
        "configured": False,
        "status": "unset",
        "contract": None,
        "progress": None,
    }
    parsed_contract = parse_success_contract(client)
    if parsed_contract:
        try:
            contract_eval = evaluate_success_contract(db, client)
        except Exception:
            logger.error(
                "Failed to evaluate success contract for client %s (id=%s)",
                client.name,
                client.id,
                exc_info=True,
            )
            contract_eval = {
                "configured": True,
                "status": "no_data",
                "contract": parsed_contract,
                "progress": None,
            }
    row["success_contract"] = contract_eval
    if contract_eval.get("configured") and contract_eval.get("status") == "behind":
        prog = contract_eval.get("progress") or {}
        label = prog.get("label") or "KPI"
        ch = prog.get("change_pct")
        tgt = prog.get("target_delta_pct")
        reason = (
            f"Off contract: {label} {ch:+.0f}% vs +{tgt:.0f}% target"
            if ch is not None and tgt is not None
            else f"Off contract: {label}"
        )
        reasons = list(row.get("risk_reasons") or [])
        if reason not in reasons:
            reasons.insert(0, reason)
            row["risk_reasons"] = reasons[:6]
        if row.get("risk") == "healthy":
            row["risk"] = "watch"
        detail = reason
        if prog.get("change_pct") is not None:
            detail = (
                f"{label} at {prog.get('change_pct'):+.0f}% "
                f"(target +{prog.get('target_delta_pct', 0):.0f}%)"
            )
        row["top_action"] = {
            "title": f"Off contract: {label}",
            "detail": detail,
            "insight_id": None,
            "task_id": None,
            "cta_tab": "prescribe",
            "effort": "high",
        }
    return row


def build_portfolio_benchmark(db: Session) -> dict[str, Any]:
    """Batched portfolio benchmark for all clients."""
    today = date.today()
    this_start = today - timedelta(days=6)
    prev_start = today - timedelta(days=13)
    prev_end = today - timedelta(days=7)
    prev2_start = today - timedelta(days=20)
    prev2_end = today - timedelta(days=14)
    month_start = today - timedelta(days=30)
    day_count = max(1, (today - this_start).days + 1)

    clients = (
        db.query(Client)
        .filter((Client.archived == False) | (Client.archived.is_(None)))  # noqa: E712
        .all()
    )
    if not clients:
        return {"clients": [], "success_board": _build_success_board([])}

    client_ids = [c.id for c in clients]
    client_by_id = {c.id: c for c in clients}

    # Metric specs built from shared dimension map
    this_specs = [
        ("gsc", "clicks", SITE_TOTAL_DIMENSION.get("gsc")),
        ("gsc", "impressions", SITE_TOTAL_DIMENSION.get("gsc")),
        ("ga4", "sessions", SITE_TOTAL_DIMENSION.get("ga4")),
        ("ga4", "key_events", SITE_TOTAL_DIMENSION.get("ga4")),
        ("hubspot", "leads", None),
        ("hubspot", "revenue", None),
        ("ads_csv", "cost", SITE_TOTAL_DIMENSION.get("ads_csv")),
        ("google_ads", "cost", SITE_TOTAL_DIMENSION.get("google_ads")),
        ("meta_ads", "cost", SITE_TOTAL_DIMENSION.get("meta_ads")),
    ]

    this_m = batch_metric_sums(db, client_ids, this_specs, this_start, today)
    prev_m = batch_metric_sums(db, client_ids, this_specs, prev_start, prev_end)
    prev2_m = batch_metric_sums(
        db, client_ids, [("gsc", "clicks", SITE_TOTAL_DIMENSION.get("gsc"))], prev2_start, prev2_end
    )
    apply_gsc_ga4_sum_fallback(db, client_ids, this_m, this_start, today)
    apply_gsc_ga4_sum_fallback(db, client_ids, prev_m, prev_start, prev_end)
    apply_gsc_ga4_sum_fallback(db, client_ids, prev2_m, prev2_start, prev2_end)

    month_m = batch_metric_sums(
        db, client_ids, [("gsc", "clicks", SITE_TOTAL_DIMENSION.get("gsc"))], month_start, today
    )

    # Insights / tasks / sync in bulk
    all_insights = (
        db.query(Insight)
        .filter(Insight.client_id.in_(client_ids), Insight.resolved == False)  # noqa: E712
        .all()
    )
    insights_by: dict[int, list[Insight]] = {cid: [] for cid in client_ids}
    for ins in all_insights:
        insights_by.setdefault(ins.client_id, []).append(ins)

    all_tasks = (
        db.query(Task)
        .filter(Task.client_id.in_(client_ids), Task.status.notin_(["done", "skipped"]))
        .all()
    )
    tasks_by: dict[int, list[Task]] = {cid: [] for cid in client_ids}
    for t in all_tasks:
        tasks_by.setdefault(t.client_id, []).append(t)

    sync_rows = (
        db.query(DataSource.client_id, func.max(DataSource.last_synced_at))
        .filter(DataSource.client_id.in_(client_ids))
        .group_by(DataSource.client_id)
        .all()
    )
    sync_by = {cid: ts for cid, ts in sync_rows}

    # Ship cadence: distinct tasks with baseline in last 7 days (work started/measured)
    from app.models import ImpactSnapshot
    from app.timeutil import utcnow as _utcnow

    since_7d = _utcnow() - timedelta(days=7)
    ship_rows = (
        db.query(ImpactSnapshot.client_id, ImpactSnapshot.task_id)
        .filter(
            ImpactSnapshot.client_id.in_(client_ids),
            ImpactSnapshot.snapshot_type == "baseline",
            ImpactSnapshot.created_at >= since_7d,
        )
        .distinct()
        .all()
    )
    shipped_by: dict[int, int] = {cid: 0 for cid in client_ids}
    for cid, _tid in ship_rows:
        shipped_by[cid] = shipped_by.get(cid, 0) + 1

    def get_m(store: dict, cid: int, source: str, metric: str) -> float:
        return store.get((cid, source, metric), 0.0)

    def ad_cost_for(store: dict, cid: int) -> float:
        return (
            get_m(store, cid, "ads_csv", "cost")
            + get_m(store, cid, "google_ads", "cost")
            + get_m(store, cid, "meta_ads", "cost")
        )

    # Success contracts: evaluate_success_contract hits MetricDaily 2× + baseline per
    # client (windows/metrics vary, so full batching is not shared). Skip unset
    # contracts; catch failures so one bad profile cannot fail the portfolio.
    from app.success_contract import evaluate_success_contract, parse_success_contract

    results = []
    for cid in client_ids:
        client = client_by_id[cid]
        row = compute_client_portfolio_row(
            client,
            db,
            gsc_clicks=get_m(this_m, cid, "gsc", "clicks"),
            gsc_clicks_prev=get_m(prev_m, cid, "gsc", "clicks"),
            gsc_clicks_prev2=get_m(prev2_m, cid, "gsc", "clicks"),
            gsc_impressions=get_m(this_m, cid, "gsc", "impressions"),
            ga4_sessions=get_m(this_m, cid, "ga4", "sessions"),
            ga4_sessions_prev=get_m(prev_m, cid, "ga4", "sessions"),
            ga4_conversions=get_m(this_m, cid, "ga4", "key_events"),
            ga4_conversions_prev=get_m(prev_m, cid, "ga4", "key_events"),
            day_count=day_count,
            leads=get_m(this_m, cid, "hubspot", "leads"),
            leads_prev=get_m(prev_m, cid, "hubspot", "leads"),
            revenue=get_m(this_m, cid, "hubspot", "revenue"),
            revenue_prev=get_m(prev_m, cid, "hubspot", "revenue"),
            ad_cost=ad_cost_for(this_m, cid),
            ad_cost_prev=ad_cost_for(prev_m, cid),
            open_insights=insights_by.get(cid, []),
            open_tasks=tasks_by.get(cid, []),
            last_sync=sync_by.get(cid),
            today=today,
        )
        row["metrics"]["month_clicks"] = round(get_m(month_m, cid, "gsc", "clicks"), 1)
        shipped = int(shipped_by.get(cid, 0))
        row["shipped_7d"] = shipped
        row["ship_cadence"] = {
            "fixes_done_7d": shipped,
            "target_min": 3,
            "target_max": 5,
            "on_pace": shipped >= 3,
        }
        contract_eval = {
            "configured": False,
            "status": "unset",
            "contract": None,
            "progress": None,
        }
        parsed_contract = parse_success_contract(client)
        if parsed_contract:
            try:
                contract_eval = evaluate_success_contract(db, client)
            except Exception:
                logger.error(
                    "Failed to evaluate success contract for client %s (id=%s)",
                    client.name,
                    client.id,
                    exc_info=True,
                )
                contract_eval = {
                    "configured": True,
                    "status": "no_data",
                    "contract": parsed_contract,
                    "progress": None,
                }
        row["success_contract"] = contract_eval
        if contract_eval.get("configured") and contract_eval.get("status") == "behind":
            prog = contract_eval.get("progress") or {}
            label = prog.get("label") or "KPI"
            ch = prog.get("change_pct")
            tgt = prog.get("target_delta_pct")
            reason = f"Off contract: {label} {ch:+.0f}% vs +{tgt:.0f}% target" if ch is not None and tgt is not None else f"Off contract: {label}"
            reasons = list(row.get("risk_reasons") or [])
            if reason not in reasons:
                reasons.insert(0, reason)
                row["risk_reasons"] = reasons[:6]
            if row.get("risk") == "healthy":
                row["risk"] = "watch"
            # Boost urgency in sort
            row["risk_rank"] = round(float(row.get("risk_rank") or 0) - 35, 1)
            # Contract CTA becomes the top action when behind target
            detail = reason
            if prog.get("change_pct") is not None:
                detail = (
                    f"{label} at {prog.get('change_pct'):+.0f}% "
                    f"(target +{prog.get('target_delta_pct', 0):.0f}%)"
                )
            row["top_action"] = {
                "title": f"Off contract: {label}",
                "detail": detail,
                "insight_id": None,
                "task_id": None,
                "cta_tab": "prescribe",
                "effort": "high",
            }
        results.append(row)

    if len(results) > 1:
        for metric_key in [
            "gsc_clicks",
            "gsc_impressions",
            "ga4_sessions",
            "ga4_conversions",
            "ctr",
            "conversion_rate",
            "leads",
            "revenue",
        ]:
            sorted_clients = sorted(
                results, key=lambda r: r["metrics"].get(metric_key, 0), reverse=True
            )
            for rank, c in enumerate(sorted_clients, 1):
                for r in results:
                    if r["client_id"] == c["client_id"]:
                        r["rankings"][metric_key] = rank

    results.sort(key=lambda r: (r["risk_rank"], r["health_score"], -r["open_insights_high"]))

    try:
        from app.lever_service import portfolio_report_ready
        from app.models import ActionPlan

        ready = portfolio_report_ready(db)
        # AI value: plans + attributed wins proxy
        plan_counts = dict(
            db.query(ActionPlan.client_id, func.count(ActionPlan.id))
            .group_by(ActionPlan.client_id)
            .all()
        )
        for r in results:
            cid = r["client_id"]
            count = int(ready.get(cid, 0) or 0)
            r["report_ready_count"] = count
            r["report_ready"] = count > 0 or (
                r.get("open_tasks", 0) == 0 and r.get("risk") == "healthy" and r.get("open_insights", 0) == 0
            )
            plans = int(plan_counts.get(cid, 0) or 0)
            # Simple AI value score: plans * 10 + report-ready levers * 25 + inverse risk
            risk_bonus = {"healthy": 20, "watch": 10, "critical": 0, "no_data": 0}.get(r.get("risk"), 0)
            r["ai_value_score"] = round(plans * 10 + count * 25 + risk_bonus, 1)
    except Exception as e:
        logger.error("Failed to compute report-ready / AI-value scores: %s", e)
        for r in results:
            r.setdefault("report_ready", False)
            r.setdefault("report_ready_count", 0)
            r.setdefault("ai_value_score", None)

    success_board = _build_success_board(results)
    return {"clients": results, "success_board": success_board}


def cross_client_fix_effectiveness(db: Session) -> dict[str, dict]:
    """Aggregate proven GrowthLeverThread outcomes by fix type across all clients.

    Returns {fix_type: {wins, total, median_lift_pct, mean_lift_pct, client_count}}
    for every insight type that has been proven at least once.
    """
    proven = (
        db.query(GrowthLeverThread)
        .filter(GrowthLeverThread.status == "proven")
        .all()
    )

    by_type: dict[str, list[tuple[int, float | None]]] = {}
    for lever in proven:
        task = None
        if lever.task_id:
            task = db.query(Task).filter(Task.id == lever.task_id).first()
        if not task:
            continue

        insight = None
        if task.insight_id:
            insight = db.query(Insight).filter(Insight.id == task.insight_id).first()
        fix_type = insight.type if insight else (lever.stage or "unknown")

        rechecks = (
            db.query(ImpactSnapshot)
            .filter(
                ImpactSnapshot.task_id == task.id,
                ImpactSnapshot.snapshot_type == "recheck",
                ImpactSnapshot.change_pct.isnot(None),
            )
            .order_by(ImpactSnapshot.created_at.desc())
            .all()
        )
        latest: dict[str, ImpactSnapshot] = {}
        for r in rechecks:
            key = f"{r.source}.{r.metric_name}"
            if key not in latest:
                latest[key] = r

        from app.impact_tracker import _ordered_primary_for_task

        ordered = _ordered_primary_for_task(db, task)
        primary_keys = {f"{s}.{m}" for s, m in ordered}
        primary = [r for r in latest.values() if f"{r.source}.{r.metric_name}" in primary_keys]
        # Prefer contract/first ordered metric for lift (matches Prove north star)
        pct = None
        for src, met in ordered:
            key = f"{src}.{met}"
            if key in latest and latest[key].change_pct is not None:
                pct = latest[key].change_pct
                break
        if pct is None and primary and primary[0].change_pct is not None:
            pct = primary[0].change_pct

        if fix_type not in by_type:
            by_type[fix_type] = []
        by_type[fix_type].append((task.client_id, pct))

    result: dict[str, dict] = {}
    for fix_type, entries in by_type.items():
        pcts = [p for _, p in entries if p is not None]
        wins = sum(1 for _, p in entries if p is not None and p > 0)
        unique_clients = len({cid for cid, _ in entries}) if entries else 0
        median_lift = round(float(statistics.median(pcts)), 1) if pcts else None
        mean_lift = round(float(statistics.mean(pcts)), 1) if pcts else None
        result[fix_type] = {
            "wins": wins,
            "total": len(entries),
            "median_lift_pct": median_lift,
            "mean_lift_pct": mean_lift,
            "client_count": unique_clients,
        }

    return result


def format_cross_client_patterns(effectiveness: dict[str, dict], *, limit: int = 12) -> list[str]:
    """Format cross-client fix effectiveness for AI prompt injection."""
    if not effectiveness:
        return []
    lines = [
        "=== CROSS-CLIENT FIX EFFECTIVENESS (your agency's own proven history) ===",
        "Use this proprietary data: prefer fix types with high win rates and strong median lift.",
    ]
    ranked = sorted(
        effectiveness.items(),
        key=lambda kv: (
            -(kv[1].get("wins") or 0),
            -(kv[1].get("median_lift_pct") or 0),
        ),
    )
    for fix_type, stats in ranked[:limit]:
        w, t = stats.get("wins", 0), stats.get("total", 0)
        med = stats.get("median_lift_pct")
        clients = stats.get("client_count", 0)
        lift_str = f", median +{med}% lift" if med is not None and med > 0 else (
            f", median {med}% change" if med is not None else ""
        )
        lines.append(
            f"- {fix_type}: {w}/{t} wins across {clients} client{'s' if clients != 1 else ''}{lift_str}"
        )
    if not ranked:
        lines.append("(No proven fix outcomes yet — this data builds with every shipped and measured fix.)")
    return lines


def _build_success_board(results: list[dict]) -> dict[str, Any]:
    """Book-of-business aggregate for Portfolio morning strip."""
    counts = {"ahead": 0, "on_track": 0, "behind": 0, "unset": 0, "no_data": 0}
    overdue_execute = 0
    report_ready = 0
    shipped_7d = 0
    behind_pace = 0
    for r in results:
        sc = r.get("success_contract") or {}
        status = str(sc.get("status") or "unset")
        if status in counts:
            counts[status] += 1
        else:
            counts["unset"] += 1
        overdue_execute += int(r.get("overdue_tasks") or 0)
        if r.get("report_ready"):
            report_ready += 1
        shipped = int(r.get("shipped_7d") or (r.get("ship_cadence") or {}).get("fixes_done_7d") or 0)
        shipped_7d += shipped
        if shipped < 3 and (r.get("open_insights") or 0) > 0:
            behind_pace += 1
    return {
        **counts,
        "overdue_execute": overdue_execute,
        "report_ready": report_ready,
        "client_count": len(results),
        "shipped_7d": shipped_7d,
        "ship_target_min": 3,
        "ship_target_max": 5,
        "clients_behind_pace": behind_pace,
    }
