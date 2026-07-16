"""
Impact Tracker — measures the effect of completed tasks on client metrics.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_

from app.database import SessionLocal
from app.models import Task, ImpactSnapshot, MetricDaily, Insight, Client, AppSetting
from app.impact_math import (
    auto_outcome_from_avg_change,
    change_pct,
    confidence_from_variance,
    evidence_label,
    pre_trend_flag,
    seasonality_caution,
)
from app.timeutil import utcnow
from app.causal_inference import evaluate_causal_impact

logger = logging.getLogger(__name__)


def get_impact_window_days(db=None) -> int:
    """Configurable recheck window from Settings (7 / 14 / 28)."""
    close = False
    if db is None:
        db = SessionLocal()
        close = True
    try:
        row = db.query(AppSetting).filter(AppSetting.key == "impact_window_days").first()
        if row and row.value:
            days = int(row.value)
            if days in (7, 14, 28):
                return days
    except Exception:
        pass
    finally:
        if close:
            db.close()
    return 14


from app.dimensions import SITE_TOTAL_DIMENSION as _SITE_TOTAL_DIMENSION

RELEVANT_METRICS = [
    ("gsc", "clicks"),
    ("gsc", "impressions"),
    ("gsc", "ctr"),
    ("gsc", "position"),
    ("ga4", "sessions"),
    ("ga4", "key_events"),
    ("ga4", "screen_page_views"),
    ("cloudflare", "requests"),
    ("bing", "clicks"),
    ("bing", "impressions"),
    ("hubspot", "leads"),
    ("hubspot", "revenue"),
    ("hubspot", "closed_won"),
    ("paid", "cost"),
    ("paid", "conversions"),
    ("paid", "clicks"),
]

# Primary metric(s) by insight type — used for win/loss and proof copy
# Organic SEO plays always include hubspot.leads so Prove tells a revenue story.
PRIMARY_BY_INSIGHT: dict[str, list[tuple[str, str]]] = {
    "content_opportunity": [("gsc", "clicks"), ("hubspot", "leads"), ("gsc", "impressions")],
    "ctr_opportunity": [("gsc", "ctr"), ("gsc", "clicks"), ("hubspot", "leads")],
    "ctr_gap": [("gsc", "ctr"), ("gsc", "clicks"), ("hubspot", "leads")],
    "zero_click_alert": [("gsc", "ctr"), ("gsc", "clicks"), ("hubspot", "leads")],
    "mobile_ctr_gap": [("gsc", "ctr"), ("gsc", "clicks"), ("hubspot", "leads")],
    "decline_alert": [("gsc", "clicks"), ("hubspot", "leads"), ("gsc", "impressions")],
    "cro_opportunity": [("ga4", "key_events"), ("hubspot", "leads"), ("ga4", "sessions")],
    "bounce_cro_alert": [("ga4", "key_events"), ("hubspot", "leads"), ("ga4", "sessions")],
    "error_spike_alert": [("ga4", "sessions"), ("cloudflare", "requests")],
    "pagespeed_urgent": [("gsc", "clicks"), ("ga4", "sessions"), ("hubspot", "leads")],
    "pagespeed_improve": [("gsc", "clicks"), ("ga4", "sessions"), ("hubspot", "leads")],
    "bing_opportunity": [("bing", "clicks"), ("bing", "impressions")],
    "bing_underperform": [("bing", "clicks"), ("gsc", "clicks")],
    "ads_spend_low_leads": [("hubspot", "leads"), ("paid", "cost"), ("paid", "conversions")],
    "pause_weak_campaign": [("paid", "conversions"), ("paid", "cost"), ("hubspot", "leads")],
    "ads_search_term_waste": [("paid", "cost"), ("paid", "conversions"), ("hubspot", "leads")],
    "sov_loss": [("gsc", "clicks"), ("hubspot", "leads"), ("gsc", "impressions")],
    "leads_revenue_leak": [("hubspot", "revenue"), ("hubspot", "closed_won"), ("hubspot", "leads")],
    "organic_leads_leak": [("hubspot", "leads"), ("gsc", "clicks"), ("hubspot", "revenue")],
    "crawl_broken_pages": [("gsc", "clicks"), ("gsc", "impressions"), ("ga4", "sessions")],
    "crawl_missing_title": [("gsc", "ctr"), ("gsc", "clicks"), ("gsc", "impressions")],
    "crawl_missing_h1": [("gsc", "ctr"), ("gsc", "clicks"), ("gsc", "impressions")],
    "crawl_missing_meta": [("gsc", "ctr"), ("gsc", "clicks"), ("gsc", "impressions")],
    "crawl_thin_content": [("gsc", "clicks"), ("gsc", "impressions"), ("hubspot", "leads")],
}

DEFAULT_PRIMARY = [
    ("gsc", "clicks"),
    ("ga4", "sessions"),
    ("ga4", "key_events"),
    ("hubspot", "leads"),
    ("hubspot", "revenue"),
]

# Ordered funnel for organic → revenue Prove strip
FUNNEL_PROOF_METRICS = [
    ("gsc", "clicks"),
    ("ga4", "sessions"),
    ("ga4", "key_events"),
    ("hubspot", "leads"),
    ("hubspot", "opportunities"),
    ("hubspot", "revenue"),
]

AVG_METRICS = {"ctr", "position", "bounce_rate", "scroll_depth"}


def _contract_primary_tuple(db, task: Task) -> tuple[str, str] | None:
    """Success Contract primary KPI as (source, metric) when configured."""
    try:
        from app.success_contract import CONTRACT_METRICS, parse_success_contract

        client = db.query(Client).filter(Client.id == task.client_id).first()
        if not client:
            return None
        contract = parse_success_contract(client)
        if not contract:
            return None
        key = contract.get("primary_metric") or ""
        meta = CONTRACT_METRICS.get(key)
        if not meta:
            return None
        return (meta["source"], meta["metric"])
    except Exception:
        return None


def _ordered_primary_for_task(db, task: Task) -> list[tuple[str, str]]:
    """Insight primaries with Success Contract KPI forced first when set.

    Clients buy the contract metric (leads/revenue/…). Intermediate SEO metrics
    stay in the set for evidence but must not outrank the commercial north star.
    """
    base: list[tuple[str, str]] = list(DEFAULT_PRIMARY)
    if task.insight_id:
        insight = db.query(Insight).filter(Insight.id == task.insight_id).first()
        if insight and insight.type in PRIMARY_BY_INSIGHT:
            base = list(PRIMARY_BY_INSIGHT[insight.type])
    contract = _contract_primary_tuple(db, task)
    if not contract:
        return base
    ordered = [contract] + [m for m in base if m != contract]
    return ordered


def _metrics_for_task(db, task: Task) -> list[tuple[str, str]]:
    primary = _ordered_primary_for_task(db, task)
    seen = set(primary)
    rest = [m for m in RELEVANT_METRICS if m not in seen]
    return primary + rest


def _primary_keys_for_task(db, task: Task) -> set[str]:
    return {f"{s}.{m}" for s, m in _ordered_primary_for_task(db, task)}


def _contract_outcome_gate(db, task: Task, recheck_list: list) -> tuple[float | None, str | None]:
    """When contract KPI has a recheck, win/loss is decided on that metric alone."""
    contract = _contract_primary_tuple(db, task)
    if not contract:
        return None, None
    key = f"{contract[0]}.{contract[1]}"
    for r in recheck_list:
        if f"{r.source}.{r.metric_name}" == key and r.change_pct is not None:
            return float(r.change_pct), key
    return None, key


def _aggregate_metric(db, client_id: int, source: str, metric_name: str, start: date, end: date) -> float | None:
    if source == "paid":
        from app.connectors.ads_common import sum_paid_metric

        return sum_paid_metric(db, client_id, metric_name, start, end)
    if metric_name == "ctr":
        clicks = _aggregate_metric(db, client_id, source, "clicks", start, end)
        impressions = _aggregate_metric(db, client_id, source, "impressions", start, end)
        if clicks is None or impressions is None:
            return None
        return (clicks / impressions) if impressions > 0 else 0.0
    filters = [
        MetricDaily.client_id == client_id,
        MetricDaily.source == source,
        MetricDaily.metric_name == metric_name,
        MetricDaily.date >= start,
        MetricDaily.date <= end,
    ]
    dim = _SITE_TOTAL_DIMENSION.get(source)
    if dim is not None:
        filters.append(MetricDaily.dimension_type == dim)
    rows = db.query(MetricDaily).filter(and_(*filters)).all()
    if not rows:
        return None
    if metric_name in AVG_METRICS:
        vals = [r.value for r in rows if r.value is not None]
        return float(sum(vals) / len(vals)) if vals else None
    vals = [r.value for r in rows if r.value is not None]
    return float(sum(vals)) if vals else None


def _daily_series(
    db,
    client_id: int,
    source: str,
    metric_name: str,
    start: date,
    end: date,
) -> list[float]:
    """Per-day totals for variance-based confidence (60–90d pre-baseline history)."""
    if source == "paid":
        from app.connectors.ads_common import paid_daily_series

        return paid_daily_series(db, client_id, metric_name, start, end)
    if metric_name == "ctr":
        imps_by_day = _daily_series_by_date(db, client_id, source, "impressions", start, end)
        clicks_by_day = _daily_series_by_date(db, client_id, source, "clicks", start, end)
        days = sorted(set(clicks_by_day) | set(imps_by_day))
        return [
            (clicks_by_day.get(d, 0.0) / d_imps)
            if (d_imps := imps_by_day.get(d, 0.0)) > 0
            else 0.0
            for d in days
        ]
    return list(_daily_series_by_date(db, client_id, source, metric_name, start, end).values())


def _daily_series_by_date(
    db,
    client_id: int,
    source: str,
    metric_name: str,
    start: date,
    end: date,
) -> dict[date, float]:
    filters = [
        MetricDaily.client_id == client_id,
        MetricDaily.source == source,
        MetricDaily.metric_name == metric_name,
        MetricDaily.date >= start,
        MetricDaily.date <= end,
    ]
    dim = _SITE_TOTAL_DIMENSION.get(source)
    if dim is not None:
        filters.append(MetricDaily.dimension_type == dim)
    rows = (
        db.query(MetricDaily.date, MetricDaily.value)
        .filter(and_(*filters))
        .order_by(MetricDaily.date.asc())
        .all()
    )
    by_day: dict[date, list[float]] = {}
    for d, v in rows:
        by_day.setdefault(d, []).append(float(v or 0))
    out: dict[date, float] = {}
    for d in sorted(by_day.keys()):
        vals = by_day[d]
        if metric_name in AVG_METRICS:
            out[d] = sum(vals) / len(vals)
        else:
            out[d] = sum(vals)
    return out


def snapshot_task_metrics(task_id: int) -> list[ImpactSnapshot]:
    """Take a baseline snapshot when work starts (in_progress), or on done as fallback.

    Existing baselines are never overwritten — so an in_progress snapshot sticks
    even if snapshot_task_metrics is called again when the task is marked done.
    """
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return []

        today = date.today()
        start_date = today - timedelta(days=30)
        metrics = _metrics_for_task(db, task)
        snapshots = []

        for source, metric_name in metrics:
            total = _aggregate_metric(db, task.client_id, source, metric_name, start_date, today)
            existing = (
                db.query(ImpactSnapshot)
                .filter(
                    ImpactSnapshot.task_id == task_id,
                    ImpactSnapshot.metric_name == metric_name,
                    ImpactSnapshot.source == source,
                    ImpactSnapshot.snapshot_type == "baseline",
                )
                .first()
            )
            if not existing:
                snap = ImpactSnapshot(
                    task_id=task_id,
                    client_id=task.client_id,
                    metric_name=metric_name,
                    source=source,
                    before_value=float(total) if total is not None else 0.0,
                    snapshot_type="baseline",
                )
                db.add(snap)
                snapshots.append(snap)

        db.commit()
        return snapshots

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to snapshot metrics for task {task_id}: {e}")
        return []
    finally:
        db.close()


def recheck_task_impact(task_id: int) -> list[dict]:
    """Capture after-values and calculate impact % for each metric."""
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            db.close()
            return []

        baselines = (
            db.query(ImpactSnapshot)
            .filter(ImpactSnapshot.task_id == task_id, ImpactSnapshot.snapshot_type == "baseline")
            .all()
        )

        if not baselines:
            snapshot_task_metrics(task_id)
            baselines = (
                db.query(ImpactSnapshot)
                .filter(ImpactSnapshot.task_id == task_id, ImpactSnapshot.snapshot_type == "baseline")
                .all()
            )
            if not baselines:
                return []

        today = date.today()
        primary_keys = _primary_keys_for_task(db, task)

        results = []
        for baseline in baselines:
            # After-window must not overlap the baseline's last-30-days window.
            # Prefer up to 30 days starting the day after the baseline was taken.
            if baseline.created_at:
                baseline_day = baseline.created_at.date() if baseline.created_at is not None else today
            else:
                baseline_day = today
            after_start = baseline_day + timedelta(days=1)
            after_end = today
            if after_end < after_start:
                current_total = baseline.before_value if baseline.before_value is not None else 0.0
            else:
                if (after_end - after_start).days > 29:
                    after_start = max(after_start, after_end - timedelta(days=29))
                current_total = _aggregate_metric(
                    db,
                    task.client_id,
                    baseline.source or "",
                    baseline.metric_name,
                    after_start,
                    after_end,
                )
            after_val = current_total if current_total is not None else 0.0
            pct = change_pct(baseline.before_value, float(after_val))
            # Replace prior recheck for this metric
            (
                db.query(ImpactSnapshot)
                .filter(
                    ImpactSnapshot.task_id == task_id,
                    ImpactSnapshot.metric_name == baseline.metric_name,
                    ImpactSnapshot.source == baseline.source,
                    ImpactSnapshot.snapshot_type == "recheck",
                )
                .delete(synchronize_session=False)
            )

            recheck = ImpactSnapshot(
                task_id=task_id,
                client_id=task.client_id,
                metric_name=baseline.metric_name,
                source=baseline.source,
                before_value=baseline.before_value,
                after_value=float(current_total),
                change_pct=round(pct, 1) if pct is not None else None,
                snapshot_type="recheck",
            )
            db.add(recheck)

            key = f"{baseline.source}.{baseline.metric_name}"
            results.append({
                "metric": key,
                "before": baseline.before_value,
                "after": float(current_total),
                "change_pct": round(pct, 1) if pct is not None else None,
                "direction": (
                    "up" if pct is not None and pct > 0
                    else "down" if pct is not None and pct < 0
                    else "flat"
                ),
                "is_primary": key in primary_keys,
            })

        db.commit()
        logger.info(f"Impact recheck complete for task {task_id}: {len(results)} metrics")
        db.close()
        return results

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        db.close()
        logger.error(f"Failed to recheck impact for task {task_id}: {e}")
        return []


def get_task_impact_summary(task_id: int, db=None) -> dict:
    """Get a human-readable impact summary for a task.

    Pass an existing Session via ``db`` to reuse it (e.g. impact batch).
    """
    close = False
    if db is None:
        db = SessionLocal()
        close = True
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        rechecks = (
            db.query(ImpactSnapshot)
            .filter(ImpactSnapshot.task_id == task_id, ImpactSnapshot.snapshot_type == "recheck")
            .order_by(ImpactSnapshot.created_at.desc())
            .all()
        )

        if not rechecks:
            prove_primary = None
            if task:
                ordered = _ordered_primary_for_task(db, task)
                if ordered:
                    prove_primary = f"{ordered[0][0]}.{ordered[0][1]}"
            baselines = (
                db.query(ImpactSnapshot)
                .filter(ImpactSnapshot.task_id == task_id, ImpactSnapshot.snapshot_type == "baseline")
                .order_by(ImpactSnapshot.created_at.desc())
                .all()
            )
            if baselines:
                baseline_at = baselines[0].created_at
                days_since = (utcnow() - baseline_at).days if baseline_at else 0
                window = get_impact_window_days(db)
                remaining = max(0, window - days_since)
                if remaining > 0:
                    return {
                        "status": "waiting",
                        "message": (
                            f"Baseline captured {days_since} day{'s' if days_since != 1 else ''} ago. "
                            f"Recheck in ~{remaining} more day{'s' if remaining != 1 else ''} "
                            f"(or run Recheck now if you have enough post-work data)."
                        ),
                        "outcome": None,
                        "confidence": "pending",
                        "window_days": window,
                        "primary_metric": prove_primary,
                    }
                return {
                    "status": "ready",
                    "message": f"{window}+ days since baseline — run Recheck to measure lift.",
                    "outcome": None,
                    "confidence": "pending",
                    "window_days": window,
                    "primary_metric": prove_primary,
                }
            return {
                "status": "no_data",
                "message": "No baseline yet. Move the task to In Progress (or complete it) to capture a baseline.",
                "confidence": "none",
            }

        # Deduplicate to latest per metric
        latest: dict[str, ImpactSnapshot] = {}
        for r in rechecks:
            key = f"{r.source}.{r.metric_name}"
            if key not in latest:
                latest[key] = r
        recheck_list = list(latest.values())

        primary_keys = _primary_keys_for_task(db, task) if task else set()
        primary_rechecks = [
            r for r in recheck_list if f"{r.source}.{r.metric_name}" in primary_keys
        ] or recheck_list

        improvements = [r for r in recheck_list if r.change_pct and r.change_pct > 0]
        declines = [r for r in recheck_list if r.change_pct and r.change_pct < 0]
        primary_with_pct = [r for r in primary_rechecks if r.change_pct is not None]

        # Contract KPI is the Prove north star when present — do not average with CTR.
        contract_change, contract_key = (
            _contract_outcome_gate(db, task, recheck_list) if task else (None, None)
        )
        if contract_change is not None:
            avg_improvement = contract_change
            primary_with_pct = [
                r
                for r in primary_with_pct
                if f"{r.source}.{r.metric_name}" == contract_key
            ] or primary_with_pct
        else:
            avg_improvement = (
                sum(r.change_pct for r in primary_with_pct) / len(primary_with_pct)
                if primary_with_pct
                else 0
            )

        # Prefer contract metric row as displayed primary_lift
        primary_lift = None
        if contract_key:
            for r in primary_with_pct:
                if f"{r.source}.{r.metric_name}" == contract_key:
                    primary_lift = r
                    break
        if primary_lift is None:
            primary_lift = primary_with_pct[0] if primary_with_pct else None
        auto_outcome = auto_outcome_from_avg_change(avg_improvement)
        # When HubSpot/contract is configured but contract metric has no recheck yet,
        # do not auto-declare a win from intermediate SEO averages alone.
        if (
            task
            and contract_key
            and contract_change is None
            and auto_outcome == "win"
            and not (getattr(task, "impact_outcome", None) or "").strip()
        ):
            auto_outcome = "flat"
        manual = (getattr(task, "impact_outcome", None) or "").strip().lower() if task else ""
        outcome = manual if manual in ("win", "loss", "flat") else auto_outcome
        n_primary = len(primary_with_pct)
        mag = abs(avg_improvement)
        sample_conf = "medium"
        pre_trend_caution: Optional[str] = None
        baseline_row = None
        if primary_lift and primary_lift.before_value is not None and primary_lift.after_value is not None:
            # Noise window: ~90 days ending just before the 30d baseline window
            # (anchored to baseline capture date, not "today", so late rechecks stay honest)
            baseline_row = (
                db.query(ImpactSnapshot)
                .filter(
                    ImpactSnapshot.task_id == task_id,
                    ImpactSnapshot.metric_name == primary_lift.metric_name,
                    ImpactSnapshot.source == primary_lift.source,
                    ImpactSnapshot.snapshot_type == "baseline",
                )
                .order_by(ImpactSnapshot.created_at.asc())
                .first()
            )
            if baseline_row and baseline_row.created_at:
                hist_end = baseline_row.created_at.date() - timedelta(days=30)
            else:
                hist_end = date.today() - timedelta(days=30)
            hist_start = hist_end - timedelta(days=90)
            history = _daily_series(
                db,
                task.client_id if task else primary_lift.client_id,
                primary_lift.source or "gsc",
                primary_lift.metric_name,
                hist_start,
                hist_end,
            )
            sample_conf = confidence_from_variance(
                primary_lift.before_value,
                primary_lift.after_value,
                history,
            )
            # Pre-trend check: was the metric already moving in the win/loss direction before the fix?
            if baseline_row and baseline_row.created_at:
                _baseline_day = baseline_row.created_at.date()
            else:
                _baseline_day = date.today()
            _baseline_window_start = _baseline_day - timedelta(days=30)
            _before_series = _daily_series(
                db,
                task.client_id if task else primary_lift.client_id,
                primary_lift.source or "gsc",
                primary_lift.metric_name,
                _baseline_window_start,
                _baseline_day,
            )
            pre_trend_caution = pre_trend_flag(_before_series, avg_improvement)
        if sample_conf == "low" or n_primary < 1 or mag < 1:
            confidence = "insufficient" if sample_conf == "low" or n_primary < 1 else "low"
        elif n_primary >= 2 and mag >= 5 and sample_conf == "high":
            confidence = "high"
        elif n_primary >= 1 and mag >= 2 and sample_conf != "low":
            confidence = "medium"
        else:
            confidence = "low"

        # Multi-metric agreement + ship notes raise evidence without claiming causality
        improving_primaries = sum(1 for r in primary_with_pct if (r.change_pct or 0) > 0)
        if (
            confidence in ("medium", "high")
            and improving_primaries >= 2
            and (task.result_notes or "").strip()
        ):
            if confidence == "medium" and mag >= 3:
                confidence = "high"
            evidence_boost = True
        else:
            evidence_boost = False

        PLAIN = {
            "gsc.clicks": "People who found you on Google",
            "gsc.impressions": "Times you showed up in search",
            "gsc.ctr": "How often they chose you",
            "ga4.sessions": "Website visits",
            "ga4.key_events": "Important actions on your site",
            "hubspot.leads": "Leads",
            "hubspot.opportunities": "Pipeline opportunities",
            "hubspot.closed_won": "Deals won",
            "hubspot.revenue": "Revenue",
            "paid.clicks": "Paid clicks",
            "paid.conversions": "Paid conversions",
            "paid.cost": "Paid spend",
        }

        FUNNEL_PLAIN = {
            "gsc.clicks": "Organic clicks",
            "ga4.sessions": "Sessions",
            "ga4.key_events": "Conversions",
            "hubspot.leads": "Leads",
            "hubspot.opportunities": "Opportunities",
            "hubspot.revenue": "Revenue",
        }

        proof_lines = []
        for r in primary_with_pct[:3]:
            key = f"{r.source}.{r.metric_name}"
            label = PLAIN.get(key, key)
            sign = "+" if (r.change_pct or 0) >= 0 else ""
            proof_lines.append(
                f"{label}: {r.before_value:,.1f} → {r.after_value:,.1f} ({sign}{r.change_pct}%)"
            )

        # Organic → revenue funnel strip (site-level before/after, not multi-touch attribution)
        by_key = {f"{r.source}.{r.metric_name}": r for r in recheck_list}
        funnel_proof: list[dict] = []
        for src, name in FUNNEL_PROOF_METRICS:
            key = f"{src}.{name}"
            row = by_key.get(key)
            if not row or (row.before_value == 0 and (row.after_value or 0) == 0):
                continue
            funnel_proof.append({
                "metric": key,
                "label": FUNNEL_PLAIN.get(key, key),
                "before": row.before_value,
                "after": row.after_value,
                "change_pct": row.change_pct,
            })
        clicks_row = by_key.get("gsc.clicks")
        leads_row = by_key.get("hubspot.leads")
        revenue_story = None
        if clicks_row and leads_row and clicks_row.change_pct is not None and leads_row.change_pct is not None:
            revenue_story = (
                f"Organic→leads: clicks {clicks_row.change_pct:+.1f}% · "
                f"leads {leads_row.change_pct:+.1f}%"
            )
            rev = by_key.get("hubspot.revenue")
            if rev and rev.change_pct is not None:
                revenue_story += f" · revenue {rev.change_pct:+.1f}%"

        evidence = evidence_label(confidence)
        if evidence_boost and confidence == "high":
            evidence = "strong multi-signal evidence (ship notes + aligned KPIs)"
        caution_notes: list[str] = []
        checked_at = recheck_list[0].created_at if recheck_list else None
        month = checked_at.month if checked_at else None
        seasonal = seasonality_caution(month)
        if seasonal:
            caution_notes.append(seasonal)
        if pre_trend_caution:
            caution_notes.append(pre_trend_caution)
        if confidence in ("low", "insufficient"):
            caution_notes.append(
                "Sample size or magnitude is too small to claim this fix caused the change."
            )
        if funnel_proof:
            caution_notes.append(
                "Funnel strip is site-level before/after — not channel-attributed CRM."
            )
        proof_copy = (
            f"After completing this work, primary results moved {avg_improvement:+.1f}% on average "
            f"({evidence}). "
            + (" · ".join(proof_lines) if proof_lines else "")
        )
        if revenue_story:
            proof_copy += f" {revenue_story}."
        if caution_notes:
            proof_copy += " Note: " + " ".join(caution_notes)

        # Causal inference: matched-control + bootstrap CI for the primary metric
        causal_verdict: dict | None = None
        if primary_lift and primary_lift.change_pct is not None:
            try:
                _treated_value = None
                # Prefer Task.target_url over scraping URLs from message text
                if task and getattr(task, "target_url", None):
                    tu = (task.target_url or "").strip()
                    if tu.startswith("http://") or tu.startswith("https://") or tu.startswith("/"):
                        _treated_value = tu
                if not _treated_value and task and task.insight_id:
                    insight = db.query(Insight).filter(Insight.id == task.insight_id).first()
                    if insight and getattr(insight, "target_url", None):
                        iu = (insight.target_url or "").strip()
                        if iu.startswith("http://") or iu.startswith("https://") or iu.startswith("/"):
                            _treated_value = iu
                    if not _treated_value and insight:
                        msg = (insight.message or "") + " " + (insight.recommended_action or "")
                        for word in msg.split():
                            if word.startswith("http://") or word.startswith("https://"):
                                _treated_value = word.rstrip(".,;:!?)'\"")
                                break
                if not _treated_value and task and task.result_notes:
                    for word in (task.result_notes or "").split():
                        if word.startswith("http://") or word.startswith("https://"):
                            _treated_value = word.rstrip(".,;:!?)'\"")
                            break
                _src = primary_lift.source or "gsc"
                _metric = primary_lift.metric_name
                _baseline_day = (
                    baseline_row.created_at.date()
                    if baseline_row and baseline_row.created_at
                    else date.today()
                )
                _before_end = _baseline_day
                _before_start = _before_end - timedelta(days=30)
                _after_start = _before_end + timedelta(days=1)
                _after_end = date.today()
                causal_verdict = evaluate_causal_impact(
                    db,
                    client_id=task.client_id if task else primary_lift.client_id,
                    source=_src,
                    metric_name=_metric,
                    before_start=_before_start,
                    before_end=_before_end,
                    after_start=_after_start,
                    after_end=_after_end,
                    treated_value=_treated_value,
                    dimension_type="page",
                )
            except Exception as e:
                logger.warning("Causal inference failed for task %s: %s", task_id, e)

        summary = {
            "status": "complete",
            "outcome": outcome,
            "auto_outcome": auto_outcome,
            "outcome_manual": bool(manual in ("win", "loss", "flat")),
            "confidence": confidence,
            "evidence_label": evidence,
            "confidence_note": (
                "Evidence strength from sample size, lift magnitude, trailing variance, "
                "and multi-metric alignment — correlational, not causal proof. "
                "Ship-log / lever completion strengthens the story when present."
            ),
            "caution_notes": caution_notes,
            "checked_at": checked_at.isoformat() if checked_at else None,
            "metrics_improved": len(improvements),
            "metrics_declined": len(declines),
            "avg_primary_metric_change": round(avg_improvement, 1),
            "primary_metric": (
                f"{primary_lift.source}.{primary_lift.metric_name}" if primary_lift else None
            ),
            "proof_copy": proof_copy.strip(),
            "funnel_proof": funnel_proof,
            "revenue_story": revenue_story,
            "causal_verdict": causal_verdict,
            "window_days": get_impact_window_days(db),
            "details": [
                {
                    "metric": f"{r.source}.{r.metric_name}",
                    "before": r.before_value,
                    "after": r.after_value,
                    "change_pct": r.change_pct,
                    "is_primary": f"{r.source}.{r.metric_name}" in primary_keys,
                }
                for r in recheck_list
            ],
        }
        # Auto-advance proving → proven when recheck shows a win
        if task and outcome == "win":
            try:
                from app.lever_service import maybe_mark_proven_from_task

                maybe_mark_proven_from_task(
                    db,
                    task,
                    impact_summary=summary.get("proof_copy"),
                    confidence_label=confidence,
                )
            except Exception as e:
                logger.warning("Could not auto-advance lever to proven for task %s: %s", task_id, e)
        return summary
    finally:
        if close:
            db.close()


def set_task_impact_outcome(task_id: int, outcome: str | None) -> dict:
    """Manually mark a task as win / loss / flat, or clear override (None)."""
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"status": "error", "message": "Task not found"}
        if outcome is None or outcome == "" or outcome == "auto":
            task.impact_outcome = None
        elif outcome.lower() in ("win", "loss", "flat"):
            task.impact_outcome = outcome.lower()
        else:
            return {"status": "error", "message": "outcome must be win, loss, flat, or auto"}
        if task.impact_outcome in ("win", "loss", "flat"):
            try:
                from app import recommendation_service

                recommendation_service.verify_from_impact(db, task_id, task.impact_outcome)
            except Exception as e:
                logger.warning("Could not verify recommendation for task %s: %s", task_id, e)
        db.commit()
        if (task.impact_outcome or "") == "win":
            try:
                from app.lever_service import maybe_mark_proven_from_task

                maybe_mark_proven_from_task(db, task, confidence_label="manual")
            except Exception as e:
                logger.warning("Could not auto-advance lever on manual win for task %s: %s", task_id, e)
        return get_task_impact_summary(task_id)
    finally:
        db.close()


def tasks_due_for_recheck(min_days: int = 14) -> list[int]:
    """Return done task IDs that have a baseline older than min_days and no recent recheck."""
    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(days=min_days)
        done = db.query(Task).filter(Task.status == "done").all()
        due = []
        for task in done:
            baseline = (
                db.query(ImpactSnapshot)
                .filter(
                    ImpactSnapshot.task_id == task.id,
                    ImpactSnapshot.snapshot_type == "baseline",
                )
                .order_by(ImpactSnapshot.created_at.asc())
                .first()
            )
            if not baseline or baseline.created_at > cutoff:
                continue
            recheck = (
                db.query(ImpactSnapshot)
                .filter(
                    ImpactSnapshot.task_id == task.id,
                    ImpactSnapshot.snapshot_type == "recheck",
                )
                .order_by(ImpactSnapshot.created_at.desc())
                .first()
            )
            if recheck and recheck.created_at >= baseline.created_at + timedelta(days=min_days):
                # Already rechecked after the window; skip unless never rechecked after latest baseline
                if recheck.created_at >= cutoff:
                    continue
            due.append(task.id)
        return due
    finally:
        db.close()


def run_due_impact_rechecks() -> dict:
    """Scheduled job: recheck all tasks past the configured baseline window."""
    window = get_impact_window_days()
    due = tasks_due_for_recheck(window)
    wins = losses = 0
    for task_id in due:
        results = recheck_task_impact(task_id)
        summary = get_task_impact_summary(task_id)
        outcome = (summary.get("outcome") or "").strip().lower()
        if outcome == "win":
            wins += 1
        elif outcome == "loss":
            losses += 1
        if outcome in ("win", "loss", "flat"):
            try:
                from app import recommendation_service

                db = SessionLocal()
                try:
                    recommendation_service.verify_from_impact(
                        db,
                        task_id,
                        outcome,
                        lift_pct=summary.get("avg_primary_metric_change"),
                    )
                    db.commit()
                finally:
                    db.close()
            except Exception as e:
                logger.warning("Could not verify recommendation on recheck for task %s: %s", task_id, e)
        logger.info(f"Auto-recheck task {task_id}: {len(results)} metrics, outcome={summary.get('outcome')}")
    return {"checked": len(due), "wins": wins, "losses": losses}


def portfolio_impact_wins(days: int = 30) -> list[dict]:
    """Portfolio-level wins: tasks with positive primary lift in the last N days."""
    db = SessionLocal()
    try:
        since = utcnow() - timedelta(days=days)
        rechecks = (
            db.query(ImpactSnapshot)
            .filter(
                ImpactSnapshot.snapshot_type == "recheck",
                ImpactSnapshot.created_at >= since,
                ImpactSnapshot.change_pct.isnot(None),
            )
            .all()
        )
        by_task: dict[int, list[ImpactSnapshot]] = {}
        for r in rechecks:
            by_task.setdefault(r.task_id, []).append(r)

        wins = []
        for task_id, snaps in by_task.items():
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                continue
            primary_keys = _primary_keys_for_task(db, task)
            primary = [s for s in snaps if f"{s.source}.{s.metric_name}" in primary_keys]
            use = primary or snaps
            with_pct = [s for s in use if s.change_pct is not None]
            if not with_pct:
                continue
            avg = sum(s.change_pct for s in with_pct) / len(with_pct)
            manual = (getattr(task, "impact_outcome", None) or "").strip().lower()
            if manual == "loss" or manual == "flat":
                continue
            if avg <= 2 and manual != "win":
                continue
            insight = None
            if task.insight_id:
                insight = db.query(Insight).filter(Insight.id == task.insight_id).first()
            client = db.query(Client).filter(Client.id == task.client_id).first()
            wins.append({
                "task_id": task_id,
                "client_id": task.client_id,
                "client_name": client.name if client else f"Client {task.client_id}",
                "avg_primary_change": round(avg, 1),
                "insight_type": insight.type if insight else None,
                "outcome": "win",
                "label": (task.result_notes or (insight.message if insight else f"Task #{task_id}"))[:120],
            })
        wins.sort(key=lambda w: w["avg_primary_change"], reverse=True)
        return wins
    finally:
        db.close()
