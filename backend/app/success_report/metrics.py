"""KPI aggregation, baselines, and period wins."""
from __future__ import annotations

import calendar
import json
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.models import (
    Client,
    MetricDaily,
    Insight,
    Task,
    ImpactSnapshot,
    ClientBaseline,
)
from app.impact_math import (
    auto_outcome_from_avg_change,
    confidence_from_values,
    evidence_label,
)
from app.impact_tracker import DEFAULT_PRIMARY, PRIMARY_BY_INSIGHT
from app.connectors.ads_common import sum_paid_metric
from app.success_report.branding import PLAIN_LABELS, plain_label
from app.timeutil import utcnow

from app.dimensions import SITE_TOTAL_DIMENSION as _SITE_TOTAL_DIMENSION

def _site_dimension(source: str) -> Optional[str]:
    return _SITE_TOTAL_DIMENSION.get(source)


def _sum_metric(db: Session, client_id: int, source: str, metric_name: str, start: date, end: date) -> float:
    filters = [
        MetricDaily.client_id == client_id,
        MetricDaily.source == source,
        MetricDaily.metric_name == metric_name,
        MetricDaily.date >= start,
        MetricDaily.date <= end,
    ]
    dim = _site_dimension(source)
    if dim is not None:
        filters.append(MetricDaily.dimension_type == dim)
    val = db.query(func.sum(MetricDaily.value)).filter(and_(*filters)).scalar()
    return float(val or 0)


def _avg_metric(db: Session, client_id: int, source: str, metric_name: str, start: date, end: date) -> float:
    filters = [
        MetricDaily.client_id == client_id,
        MetricDaily.source == source,
        MetricDaily.metric_name == metric_name,
        MetricDaily.date >= start,
        MetricDaily.date <= end,
    ]
    dim = _site_dimension(source)
    if dim is not None:
        filters.append(MetricDaily.dimension_type == dim)
    val = db.query(func.avg(MetricDaily.value)).filter(and_(*filters)).scalar()
    return float(val or 0)


def _ctr_metric(db: Session, client_id: int, source: str, start: date, end: date) -> float:
    """True CTR = clicks / impressions (not an average of per-device CTR rates)."""
    clicks = _sum_metric(db, client_id, source, "clicks", start, end)
    impressions = _sum_metric(db, client_id, source, "impressions", start, end)
    if impressions <= 0:
        return 0.0
    return clicks / impressions


def _has_meaningful_period_data(kpis: list[dict], work: dict, wins: list[dict]) -> bool:
    if wins:
        return True
    if (work.get("tasks_completed") or 0) > 0 or (work.get("insights_resolved") or 0) > 0:
        return True
    for k in kpis:
        if (k.get("current") or 0) != 0 or (k.get("previous") or 0) != 0:
            return True
        if k.get("change_pct") is not None:
            return True
    return False


# Rate / level metrics — do not scale when aligning unequal period lengths.
_RATE_METRIC_SUFFIXES = (
    ".ctr",
    ".position",
    ".cvr",
    ".bounce_rate",
    ".scroll_depth",
    ".avg_position",
)

# Lower (or spend) is better — green when change_pct is negative.
INVERSE_METRIC_KEYS = frozenset(
    {
        "gsc.position",
        "bing.position",
        "paid.cost",
        "ads_csv.cost",
        "google_ads.cost",
        "meta_ads.cost",
    }
)

# Bump when report math/shape changes so cached MonthlyReport rows rebuild.
REPORT_PAYLOAD_VERSION = 3


def inclusive_days(start: date, end: date) -> int:
    """Inclusive day count for [start, end]."""
    return max(1, (end - start).days + 1)


def window_start(end: date, days: int) -> date:
    """Start date for an inclusive N-day window ending on `end`."""
    return end - timedelta(days=max(1, days) - 1)


def is_rate_metric(key: str) -> bool:
    k = (key or "").lower()
    return any(k.endswith(suf) for suf in _RATE_METRIC_SUFFIXES)


def is_inverse_metric(key: str) -> bool:
    k = (key or "").lower()
    if k in INVERSE_METRIC_KEYS:
        return True
    return k.endswith(".position") or k.endswith(".cost") or k.endswith(".bounce_rate")


def scale_baseline_value(
    base_val: float,
    *,
    key: str,
    baseline_days: int,
    compare_days: int,
) -> float:
    """Align a frozen baseline total to the comparison window length.

    Sum metrics (clicks, sessions, leads) are scaled by day count.
    Rates/levels (CTR, position, CVR) are left as-is.
    """
    if is_rate_metric(key):
        return float(base_val)
    if baseline_days <= 0 or compare_days <= 0 or baseline_days == compare_days:
        return float(base_val)
    return float(base_val) * (compare_days / baseline_days)


def change_is_favorable(key: str, change_pct: Optional[float]) -> Optional[bool]:
    """True when the direction of change is good for this metric."""
    if change_pct is None:
        return None
    if change_pct == 0:
        return None
    if is_inverse_metric(key):
        return change_pct < 0
    return change_pct > 0


# Minimum n for count-based metrics before a percentage delta is statistically meaningful.
# Rate metrics (CTR, position, CVR) return 0 — always show their deltas.
_COUNT_METRIC_MIN_N: dict[str, int] = {
    "gsc": 30,
    "bing": 30,
    "ga4": 30,
    "hubspot": 30,
    "ads_csv": 30,
    "google_ads": 30,
    "meta_ads": 30,
    "paid": 30,
}
_IMPRESSION_MIN_N = 200


def _min_n_for_metric(key: str) -> int:
    k = (key or "").lower()
    if is_rate_metric(key):
        return 0
    if k.endswith(".impressions"):
        return _IMPRESSION_MIN_N
    source = k.split(".")[0] if "." in k else ""
    return _COUNT_METRIC_MIN_N.get(source, 30)


def _sample_confidence(key: str, current: float, previous: float) -> tuple[Optional[float], Optional[str]]:
    """Returns (change_pct or None, confidence_tier or None).

    When the smaller of current/previous is below the minimum n for this metric type,
    percentage change is suppressed and a low-confidence flag is attached instead.
    Zero-previous always returns None change_pct (no percentage can be computed)
    but does not emit a sample-size flag — the inability to compute a delta is
    intrinsic, not a sample-size concern.
    """
    if previous is None or previous <= 0:
        return None, None
    min_n = _min_n_for_metric(key)
    if min_n <= 0:
        return _pct_change(current, previous), None
    if min(current, previous) < min_n:
        if min(current, previous) < (min_n * 0.33):
            return None, "sample_too_small"
        return None, "directional"
    return _pct_change(current, previous), None


def _pct_change(current: float, previous: float) -> Optional[float]:
    """Percent change from previous → current. None when previous is zero/missing.

    Never invent +100% from a zero baseline — that contradicted real declines
    vs engagement start and made executive KPIs untrustworthy.
    """
    if previous is None or previous <= 0:
        return None
    return round(((current - previous) / previous) * 100, 1)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _kpi_block(
    db: Session,
    client_id: int,
    source: str,
    name: str,
    period_start: date,
    period_end: date,
    prev_start: date,
    prev_end: date,
    aggregate: str = "sum",
) -> dict:
    if aggregate == "avg":
        if name == "ctr":
            cur = _ctr_metric(db, client_id, source, period_start, period_end)
            prev = _ctr_metric(db, client_id, source, prev_start, prev_end)
        else:
            cur = _avg_metric(db, client_id, source, name, period_start, period_end)
            prev = _avg_metric(db, client_id, source, name, prev_start, prev_end)
    else:
        cur = _sum_metric(db, client_id, source, name, period_start, period_end)
        prev = _sum_metric(db, client_id, source, name, prev_start, prev_end)
    key = f"{source}.{name}"
    change_pct, confidence_tier = _sample_confidence(key, cur, prev)
    is_sum = aggregate == "sum" and name != "ctr"
    result = {
        "key": key,
        "label": plain_label(key, name.replace("_", " ").title()),
        "source": source,
        "current": round(cur, 2),
        "current_n": round(cur) if is_sum else None,
        "previous": round(prev, 2),
        "previous_n": round(prev) if is_sum else None,
        "change_pct": change_pct,
        "aggregation": aggregate,
        "unit": "total" if is_sum else "average",
    }
    if confidence_tier:
        result["low_confidence"] = True
        result["confidence_tier"] = confidence_tier
    return result


def _paid_kpi_block(
    db: Session,
    client_id: int,
    name: str,
    period_start: date,
    period_end: date,
    prev_start: date,
    prev_end: date,
) -> dict:
    """Rolled paid media KPI across ads_csv + google_ads + meta_ads."""
    cur = sum_paid_metric(db, client_id, name, period_start, period_end)
    prev = sum_paid_metric(db, client_id, name, prev_start, prev_end)
    key = f"paid.{name}"
    change_pct, confidence_tier = _sample_confidence(key, cur, prev)
    result = {
        "key": key,
        "label": plain_label(key, name.replace("_", " ").title()),
        "source": "paid",
        "current": round(cur, 2),
        "current_n": round(cur),
        "previous": round(prev, 2),
        "previous_n": round(prev),
        "change_pct": change_pct,
        "aggregation": "sum",
        "unit": "total" if name != "ctr" else "average",
    }
    if confidence_tier:
        result["low_confidence"] = True
        result["confidence_tier"] = confidence_tier
    return result


def capture_client_baseline(
    db: Session,
    client_id: int,
    days: int = 30,
    *,
    force: bool = False,
) -> Optional[ClientBaseline]:
    """Freeze last N days of KPIs as the engagement baseline.

    By default the first capture sticks — re-running without force=True does not
    overwrite, so \"Progress since engagement start\" stays honest.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return None

    existing = db.query(ClientBaseline).filter(ClientBaseline.client_id == client_id).first()
    if existing and not force:
        return existing

    today = date.today()
    days = max(1, int(days))
    period_start = window_start(today, days)
    kpis = {
        "gsc.clicks": round(_sum_metric(db, client_id, "gsc", "clicks", period_start, today), 2),
        "gsc.impressions": round(_sum_metric(db, client_id, "gsc", "impressions", period_start, today), 2),
        "gsc.ctr": round(_ctr_metric(db, client_id, "gsc", period_start, today), 4),
        "gsc.position": round(_avg_metric(db, client_id, "gsc", "position", period_start, today), 2),
        "ga4.sessions": round(_sum_metric(db, client_id, "ga4", "sessions", period_start, today), 2),
        "ga4.key_events": round(_sum_metric(db, client_id, "ga4", "key_events", period_start, today), 2),
        "hubspot.leads": round(_sum_metric(db, client_id, "hubspot", "leads", period_start, today), 2),
        "hubspot.opportunities": round(_sum_metric(db, client_id, "hubspot", "opportunities", period_start, today), 2),
        "hubspot.closed_won": round(_sum_metric(db, client_id, "hubspot", "closed_won", period_start, today), 2),
        "hubspot.revenue": round(_sum_metric(db, client_id, "hubspot", "revenue", period_start, today), 2),
        "paid.cost": round(sum_paid_metric(db, client_id, "cost", period_start, today), 2),
        "paid.clicks": round(sum_paid_metric(db, client_id, "clicks", period_start, today), 2),
        "paid.conversions": round(sum_paid_metric(db, client_id, "conversions", period_start, today), 2),
        "paid.conversion_value": round(
            sum_paid_metric(db, client_id, "conversion_value", period_start, today), 2
        ),
        # Legacy aliases — older contracts / UI may still key off ads_csv.*
        "ads_csv.cost": round(_sum_metric(db, client_id, "ads_csv", "cost", period_start, today), 2),
        "ads_csv.clicks": round(_sum_metric(db, client_id, "ads_csv", "clicks", period_start, today), 2),
        "ads_csv.conversions": round(_sum_metric(db, client_id, "ads_csv", "conversions", period_start, today), 2),
        "ads_csv.conversion_value": round(
            _sum_metric(db, client_id, "ads_csv", "conversion_value", period_start, today), 2
        ),
        "bing.clicks": round(_sum_metric(db, client_id, "bing", "clicks", period_start, today), 2),
    }
    sessions = kpis["ga4.sessions"]
    events = kpis["ga4.key_events"]
    kpis["ga4.cvr"] = round((events / sessions * 100) if sessions else 0, 2)

    if existing:
        existing.kpis_json = json.dumps(kpis)
        existing.period_start = period_start
        existing.period_end = today
        existing.period_days = days
        existing.captured_at = utcnow()
        baseline = existing
    else:
        baseline = ClientBaseline(
            client_id=client_id,
            kpis_json=json.dumps(kpis),
            period_start=period_start,
            period_end=today,
            period_days=days,
        )
        db.add(baseline)
    db.commit()
    db.refresh(baseline)
    return baseline


def _baseline_deltas(
    baseline: Optional[dict],
    kpis: list[dict],
    *,
    compare_days: Optional[int] = None,
) -> list[dict]:
    """Compare current period KPIs against engagement baseline values.

    Sum metrics are scaled so a calendar month (or N-day report window) is not
    compared raw against a differently-length frozen baseline snapshot.
    When windows differ by >10% in length, a window_mismatch flag is set and
    per-day-rate normalization is applied to avoid misleading deltas.
    """
    if not baseline or not baseline.get("kpis"):
        return []
    base_map = {b["key"]: b["value"] for b in baseline["kpis"]}
    baseline_days = int(baseline.get("period_days") or 0)
    if baseline_days <= 0:
        try:
            ps = date.fromisoformat(str(baseline.get("period_start") or "")[:10])
            pe = date.fromisoformat(str(baseline.get("period_end") or "")[:10])
            baseline_days = inclusive_days(ps, pe)
        except (TypeError, ValueError):
            baseline_days = 30
    target_days = int(compare_days or baseline_days or 30)
    window_mismatch = False
    if baseline_days > 0 and target_days > 0:
        ratio = max(baseline_days, target_days) / min(baseline_days, target_days)
        if ratio > 1.10:
            window_mismatch = True
    deltas = []
    for k in kpis:
        key = k["key"]
        if key not in base_map:
            continue
        raw_base = float(base_map[key] or 0)
        base_val = scale_baseline_value(
            raw_base,
            key=key,
            baseline_days=baseline_days,
            compare_days=target_days,
        )
        cur = float(k.get("current") or 0)
        ch, conf_tier = _sample_confidence(key, cur, base_val)
        delta = {
            "key": key,
            "label": k["label"],
            "baseline": round(base_val, 2),
            "baseline_raw": round(raw_base, 2),
            "current": round(cur, 2),
            "current_n": k.get("current_n"),
            "change_pct": ch,
            "favorable": change_is_favorable(key, ch) if ch is not None else None,
            "scaled": (not is_rate_metric(key)) and baseline_days != target_days,
            "baseline_days": baseline_days,
            "compare_days": target_days,
        }
        if conf_tier:
            delta["low_confidence"] = True
            delta["confidence_tier"] = conf_tier
        if conf_tier == "sample_too_small":
            delta["evidence_label"] = evidence_label("insufficient")
        elif conf_tier == "directional":
            delta["evidence_label"] = evidence_label("low")
        else:
            delta["evidence_label"] = evidence_label(confidence_from_values(base_val, cur))
        if window_mismatch and ch is not None:
            delta["window_mismatch"] = True
            delta["normalized"] = not is_rate_metric(key)
        deltas.append(delta)
    return deltas


def get_client_baseline(db: Session, client_id: int) -> Optional[dict]:
    row = db.query(ClientBaseline).filter(ClientBaseline.client_id == client_id).first()
    if not row:
        return None
    try:
        kpis = json.loads(row.kpis_json or "{}")
    except (json.JSONDecodeError, TypeError):
        kpis = {}
    period_days = None
    if row.period_start and row.period_end:
        period_days = inclusive_days(row.period_start, row.period_end)
    return {
        "client_id": client_id,
        "captured_at": row.captured_at.isoformat() if row.captured_at else None,
        "period_start": row.period_start.isoformat() if row.period_start else None,
        "period_end": row.period_end.isoformat() if row.period_end else None,
        "period_days": period_days,
        "kpis": [
            {
                "key": k,
                "label": plain_label(k),
                "value": v,
            }
            for k, v in kpis.items()
        ],
        "notes": row.notes,
    }


REPORT_PHASES = ("baseline", "active", "proven")


def compute_report_phase(
    completed_tasks: int,
    impact_wins: list,
    proven_lever_count: int,
) -> str:
    """Determine the report phase: baseline | active | proven.

    - baseline: no work has been executed (no completed tasks, no wins, no proven levers)
    - active: work has been done but impact not yet attributed as a win
    - proven: at least one attributed win or proven growth lever exists
    """
    if impact_wins or proven_lever_count > 0:
        return "proven"
    if completed_tasks > 0:
        return "active"
    return "baseline"


def _wins_in_period(db: Session, client_id: int, period_start: date, period_end: date) -> list[dict]:
    """Wins whose impact recheck fell in the period (not task created date)."""
    start_dt = datetime.combine(period_start, datetime.min.time())
    end_dt = datetime.combine(period_end, datetime.max.time())
    rechecks = (
        db.query(ImpactSnapshot)
        .filter(
            ImpactSnapshot.client_id == client_id,
            ImpactSnapshot.snapshot_type == "recheck",
            ImpactSnapshot.created_at >= start_dt,
            ImpactSnapshot.created_at <= end_dt,
        )
        .all()
    )
    task_ids = {r.task_id for r in rechecks}
    if not task_ids:
        return []

    # Prefetch tasks + insights once (avoid per-task SessionLocal in get_task_impact_summary)
    tasks_by_id = {
        t.id: t
        for t in db.query(Task).filter(Task.id.in_(task_ids), Task.client_id == client_id).all()
    }
    insight_ids = {t.insight_id for t in tasks_by_id.values() if t.insight_id}
    insights_by_id = {
        i.id: i
        for i in db.query(Insight).filter(Insight.id.in_(insight_ids)).all()
    } if insight_ids else {}

    rechecks_by_task: dict[int, list[ImpactSnapshot]] = {}
    for r in rechecks:
        rechecks_by_task.setdefault(r.task_id, []).append(r)

    wins = []
    for task_id, snaps in rechecks_by_task.items():
        task = tasks_by_id.get(task_id)
        if not task:
            continue
        latest: dict[str, ImpactSnapshot] = {}
        for r in sorted(snaps, key=lambda s: s.created_at or datetime.min, reverse=True):
            key = f"{r.source}.{r.metric_name}"
            if key not in latest:
                latest[key] = r
        recheck_list = list(latest.values())

        primary_keys: set[str] = {f"{s}.{m}" for s, m in DEFAULT_PRIMARY}
        if task.insight_id and task.insight_id in insights_by_id:
            insight = insights_by_id[task.insight_id]
            if insight.type in PRIMARY_BY_INSIGHT:
                primary_keys = {f"{s}.{m}" for s, m in PRIMARY_BY_INSIGHT[insight.type]}
        primary_rechecks = [
            r for r in recheck_list if f"{r.source}.{r.metric_name}" in primary_keys
        ] or recheck_list
        primary_with_pct = [r for r in primary_rechecks if r.change_pct is not None]
        if not primary_with_pct:
            continue
        avg_improvement = sum(r.change_pct for r in primary_with_pct) / len(primary_with_pct)
        manual = (getattr(task, "impact_outcome", None) or "").strip().lower()
        outcome = manual if manual in ("win", "loss", "flat") else auto_outcome_from_avg_change(avg_improvement)
        if outcome != "win":
            continue

        proof_parts = []
        for r in primary_with_pct[:3]:
            key = f"{r.source}.{r.metric_name}"
            label = PLAIN_LABELS.get(key, key)
            sign = "+" if (r.change_pct or 0) >= 0 else ""
            proof_parts.append(
                f"{label}: {r.before_value:,.1f} → {r.after_value:,.1f} ({sign}{r.change_pct}%)"
            )
        proof = (
            f"After completing this work, primary results moved {avg_improvement:+.1f}% on average. "
            + (" · ".join(proof_parts) if proof_parts else "")
        ).strip()
        for key, label in PLAIN_LABELS.items():
            proof = proof.replace(key, label)
        wins.append({
            "task_id": task.id,
            "label": (task.result_notes or f"Task #{task.id}")[:160],
            "avg_primary_metric_change": round(avg_improvement, 1),
            "proof_copy": proof,
        })
    wins.sort(key=lambda w: w.get("avg_primary_metric_change") or 0, reverse=True)
    return wins
