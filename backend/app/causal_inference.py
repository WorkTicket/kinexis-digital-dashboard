"""
Causal inference — matched-control comparison and bootstrap confidence intervals.

Replaces naive before/after with honest causal estimates.
Designed to work with the per-page/per-query time series already stored in MetricDaily.
"""

from __future__ import annotations

import random
import statistics
from datetime import date
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import MetricDaily, Task


# ---------------------------------------------------------------------------
# Matched-Control Comparison
# ---------------------------------------------------------------------------

def _page_metric_sum(
    db: Session,
    client_id: int,
    source: str,
    metric_name: str,
    page_value: str,
    start: date,
    end: date,
    *,
    dimension_type: str = "page",
) -> float:
    rows = (
        db.query(MetricDaily.value)
        .filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == source,
            MetricDaily.metric_name == metric_name,
            MetricDaily.dimension_type == dimension_type,
            MetricDaily.dimension_value == page_value,
            MetricDaily.date >= start,
            MetricDaily.date <= end,
        )
        .all()
    )
    return float(sum(r[0] for r in rows))


def _page_daily_series(
    db: Session,
    client_id: int,
    source: str,
    metric_name: str,
    page_value: str,
    start: date,
    end: date,
    *,
    dimension_type: str = "page",
) -> list[float]:
    rows = (
        db.query(MetricDaily.date, MetricDaily.value)
        .filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == source,
            MetricDaily.metric_name == metric_name,
            MetricDaily.dimension_type == dimension_type,
            MetricDaily.dimension_value == page_value,
            MetricDaily.date >= start,
            MetricDaily.date <= end,
        )
        .order_by(MetricDaily.date.asc())
        .all()
    )
    by_day: dict[date, list[float]] = {}
    for d, v in rows:
        by_day.setdefault(d, []).append(float(v or 0))
    return [sum(by_day[d]) for d in sorted(by_day)]


def _touched_pages(db: Session, client_id: int, before_end: date) -> set[str]:
    """Pages that were modified by any task completed before or during the period."""
    tasks = (
        db.query(Task)
        .filter(
            Task.client_id == client_id,
            Task.status == "done",
        )
        .all()
    )
    touched: set[str] = set()
    for task in tasks:
        notes = (task.result_notes or "").lower()
        if not notes:
            continue
        for line in notes.split("\n"):
            line = line.strip()
            for prefix in ("http://", "https://"):
                if prefix in line:
                    start = line.find(prefix)
                    end = line.find(" ", start) if " " in line[start:] else len(line)
                    url = line[start:end].rstrip(".,;:!?)'\"")
                    if url:
                        touched.add(url)
    return touched


def find_control_pages(
    db: Session,
    client_id: int,
    treated_value: str,
    source: str,
    metric_name: str,
    period_start: date,
    period_end: date,
    *,
    dimension_type: str = "page",
    min_control_pages: int = 3,
    max_control_pages: int = 20,
) -> list[str]:
    treated_volume = _page_metric_sum(
        db, client_id, source, metric_name, treated_value,
        period_start, period_end,
        dimension_type=dimension_type,
    )

    rows = (
        db.query(MetricDaily.dimension_value, MetricDaily.value)
        .filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == source,
            MetricDaily.metric_name == metric_name,
            MetricDaily.dimension_type == dimension_type,
            MetricDaily.date >= period_start,
            MetricDaily.date <= period_end,
        )
        .all()
    )

    by_page: dict[str, float] = {}
    for dv, val in rows:
        if not dv or dv == treated_value:
            continue
        by_page[dv] = by_page.get(dv, 0.0) + float(val or 0)

    touched = _touched_pages(db, client_id, period_end)
    candidates = {
        url: vol
        for url, vol in by_page.items()
        if url not in touched and vol > 0
    }

    if len(candidates) < min_control_pages:
        return []

    ranked = sorted(
        candidates.items(),
        key=lambda kv: abs(kv[1] - treated_volume),
    )[:max_control_pages]

    return [url for url, _ in ranked]


def matched_control_lift(
    db: Session,
    client_id: int,
    treated_value: str,
    source: str,
    metric_name: str,
    before_start: date,
    before_end: date,
    after_start: date,
    after_end: date,
    *,
    dimension_type: str = "page",
) -> dict | None:
    from app.impact_math import change_pct

    control_pages = find_control_pages(
        db, client_id, treated_value, source, metric_name,
        before_start, after_end,
        dimension_type=dimension_type,
        min_control_pages=3,
    )

    if len(control_pages) < 3:
        return None

    treated_before = _page_metric_sum(
        db, client_id, source, metric_name, treated_value,
        before_start, before_end, dimension_type=dimension_type,
    )
    treated_after = _page_metric_sum(
        db, client_id, source, metric_name, treated_value,
        after_start, after_end, dimension_type=dimension_type,
    )
    treated_pct = change_pct(treated_before, treated_after)

    control_changes: list[float] = []
    control_urls: list[str] = []
    for ctrl_url in control_pages:
        ctrl_before = _page_metric_sum(
            db, client_id, source, metric_name, ctrl_url,
            before_start, before_end, dimension_type=dimension_type,
        )
        ctrl_after = _page_metric_sum(
            db, client_id, source, metric_name, ctrl_url,
            after_start, after_end, dimension_type=dimension_type,
        )
        ctrl_pct = change_pct(ctrl_before, ctrl_after)
        if ctrl_pct is not None:
            control_changes.append(ctrl_pct)
            control_urls.append(ctrl_url)

    if len(control_changes) < 3:
        return None

    control_median = statistics.median(control_changes)
    adjusted_lift = (treated_pct or 0) - control_median
    n_controls = len(control_changes)
    control_spread = statistics.stdev(control_changes) if n_controls >= 2 else None

    if n_controls >= 8 and control_spread is not None and control_spread < abs(adjusted_lift):
        confidence = "high"
    elif n_controls >= 5:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "treated_change_pct": treated_pct,
        "control_median_change_pct": round(control_median, 1),
        "control_pages_count": n_controls,
        "control_pages": control_urls[:5],
        "adjusted_lift_pct": round(adjusted_lift, 1),
        "causal_claim": (
            adjusted_lift > 0
            and control_spread is not None
            and abs(adjusted_lift) > control_spread
        ),
        "confidence": confidence,
        "control_spread_stdev": round(control_spread, 2) if control_spread else None,
        "method": "matched_control",
    }


# ---------------------------------------------------------------------------
# Bootstrap Confidence Intervals
# ---------------------------------------------------------------------------

def bootstrap_confidence_interval(
    daily_treated: list[float],
    daily_control: list[float] | None = None,
    *,
    n_bootstrap: int = 2000,
    ci_level: float = 0.95,
) -> dict:
    if len(daily_treated) < 5:
        return _fallback_ci(daily_treated, daily_control, ci_level)

    estimates: list[float] = []
    n_t = len(daily_treated)
    n_c = len(daily_control) if daily_control else 0

    for _ in range(n_bootstrap):
        sample_t = [random.choice(daily_treated) for _ in range(n_t)]
        treated_est = statistics.mean(sample_t)

        if daily_control and n_c >= 3:
            sample_c = [random.choice(daily_control) for _ in range(n_c)]
            control_est = statistics.mean(sample_c)
            estimates.append(treated_est - control_est)
        else:
            estimates.append(treated_est)

    estimates.sort()
    alpha = (1 - ci_level) / 2
    lower_idx = max(0, int(alpha * len(estimates)))
    upper_idx = max(0, min(int((1 - alpha) * len(estimates)) - 1, len(estimates) - 1))

    ci_lower = estimates[lower_idx]
    ci_upper = estimates[upper_idx]
    median_effect = statistics.median(estimates)
    ci_excludes_zero = (ci_lower > 0) or (ci_upper < 0)

    return {
        "ci_lower": round(ci_lower, 2),
        "ci_upper": round(ci_upper, 2),
        "ci_level": ci_level,
        "ci_excludes_zero": ci_excludes_zero,
        "median_effect": round(median_effect, 2),
        "method": "bootstrap",
        "n_bootstrap": n_bootstrap,
        "n_observations": n_t,
        "n_control_observations": n_c if daily_control else 0,
    }


def _fallback_ci(
    daily_treated: list[float],
    daily_control: list[float] | None,
    ci_level: float,
) -> dict:
    return {
        "ci_lower": None,
        "ci_upper": None,
        "ci_level": ci_level,
        "ci_excludes_zero": None,
        "median_effect": None,
        "method": "fallback_insufficient_data",
        "n_bootstrap": 0,
        "n_observations": len(daily_treated),
        "n_control_observations": len(daily_control) if daily_control else 0,
        "note": f"Need >=5 daily observations for bootstrap CI (got {len(daily_treated)}).",
    }


def causal_confidence_label(ci: dict) -> str:
    if ci.get("ci_excludes_zero") is None:
        return "insufficient evidence"
    if ci["ci_excludes_zero"]:
        return "strong causal evidence (95% CI excludes zero)"
    ci_lower = ci.get("ci_lower")
    ci_upper = ci.get("ci_upper")
    if ci_lower is not None and ci_upper is not None:
        if ci_lower < 0 < ci_upper:
            return f"moderate evidence (95% CI [{ci_lower:+.1f}, {ci_upper:+.1f}] crosses zero)"
    return "limited evidence"


# ---------------------------------------------------------------------------
# Combined entry point — returns a unified causal verdict
# ---------------------------------------------------------------------------

def evaluate_causal_impact(
    db: Session,
    client_id: int,
    source: str,
    metric_name: str,
    before_start: date,
    before_end: date,
    after_start: date,
    after_end: date,
    *,
    treated_value: str | None = None,
    dimension_type: str = "page",
) -> dict:
    import logging
    _log = logging.getLogger(__name__)

    controlled: dict | None = None
    if treated_value:
        try:
            controlled = matched_control_lift(
                db, client_id, treated_value, source, metric_name,
                before_start, before_end, after_start, after_end,
                dimension_type=dimension_type,
            )
        except Exception as e:
            _log.warning("Causal inference matched_control_lift failed for client %s: %s", client_id, e)
            controlled = None

    daily_treated = _page_daily_series(
        db, client_id, source, metric_name,
        treated_value or "",
        before_start, after_end,
        dimension_type=dimension_type if treated_value else "page",
    ) if treated_value else []

    daily_control: list[float] | None = None
    if controlled and controlled.get("control_pages"):
        for ctrl_url in controlled["control_pages"][:5]:
            ctrl_series = _page_daily_series(
                db, client_id, source, metric_name,
                ctrl_url,
                before_start, after_end,
                dimension_type=dimension_type,
            )
            daily_control = (daily_control or []) + ctrl_series

    ci = bootstrap_confidence_interval(daily_treated, daily_control)

    return {
        "matched_control": controlled,
        "bootstrap_ci": ci,
        "causal_evidence_label": causal_confidence_label(ci),
        "verdict": (
            "causal_win" if ci.get("ci_excludes_zero") and (ci.get("median_effect") or 0) > 0
            else "causal_loss" if ci.get("ci_excludes_zero") and (ci.get("median_effect") or 0) < 0
            else "inconclusive"
        ),
    }
