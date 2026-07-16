"""Outcome memory — win/loss track record + lift magnitude per playbook pattern for a client.

Phase 4: Feeds action_planner so historically weak patterns are auto-downranked
and proven lift magnitude informs future prescriptions. The downrank_multiplier
is applied to priority_score in build_action_candidates so low-win-rate
playbooks fall below the cap and stop being prescribed.

Uses Task.impact_outcome when set (manual override); otherwise derives the same
auto win/loss/flat rule as impact_tracker from primary-metric rechecks.

Cross-client effectiveness from portfolio_scoring supplements per-client data
when this client hasn't yet tried a playbook — but with softer multipliers.
"""

from __future__ import annotations

import logging
import statistics
from typing import Optional

from sqlalchemy.orm import Session

from app.impact_math import auto_outcome_from_avg_change
from app.models import ImpactSnapshot, Insight, Task

logger = logging.getLogger(__name__)

WIN_RATE_SUPPRESS_THRESHOLD: float = 0.30
WIN_RATE_BOOST_THRESHOLD: float = 0.70
MIN_SAMPLES_FOR_DOWNRANK: int = 3


def _primary_keys_for_insight_type(insight_type: str | None) -> set[str] | None:
    """Lazy import to avoid circular imports with impact_tracker."""
    if not insight_type:
        return None
    from app.impact_tracker import DEFAULT_PRIMARY, PRIMARY_BY_INSIGHT

    pairs = PRIMARY_BY_INSIGHT.get(insight_type) or DEFAULT_PRIMARY
    return {f"{s}.{m}" for s, m in pairs}


def _auto_outcome_for_task(db: Session, task: Task, insight: Insight | None) -> str | None:
    """Derive win/loss/flat from latest rechecks, or None if not yet measured."""
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
    if not rechecks:
        return None

    latest: dict[str, ImpactSnapshot] = {}
    for r in rechecks:
        key = f"{r.source}.{r.metric_name}"
        if key not in latest:
            latest[key] = r

    insight_type = insight.type if insight is not None else None
    primary_keys = _primary_keys_for_insight_type(insight_type)
    primary = (
        [r for r in latest.values() if f"{r.source}.{r.metric_name}" in primary_keys]
        if primary_keys
        else []
    )
    use = primary or list(latest.values())
    with_pct = [r for r in use if r.change_pct is not None]
    if not with_pct:
        return None
    avg = sum(r.change_pct for r in with_pct) / len(with_pct)
    return auto_outcome_from_avg_change(avg)


def effective_task_outcome(db: Session, task: Task, insight: Insight | None = None) -> str | None:
    """Manual impact_outcome wins; else auto from rechecks; else None."""
    manual = (task.impact_outcome or "").strip().lower()
    if manual in ("win", "loss", "flat"):
        return manual
    return _auto_outcome_for_task(db, task, insight)


def _primary_lift_for_task(db: Session, task: Task, insight: Insight | None) -> float | None:
    """Return the primary-metric avg change_pct for a task, or None if unmeasured."""
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
    if not rechecks:
        return None

    latest: dict[str, ImpactSnapshot] = {}
    for r in rechecks:
        key = f"{r.source}.{r.metric_name}"
        if key not in latest:
            latest[key] = r

    insight_type = insight.type if insight is not None else None
    primary_keys = _primary_keys_for_insight_type(insight_type)
    primary = (
        [r for r in latest.values() if f"{r.source}.{r.metric_name}" in primary_keys]
        if primary_keys
        else []
    )
    use = primary or list(latest.values())
    with_pct = [r for r in use if r.change_pct is not None]
    if not with_pct:
        return None
    return sum(r.change_pct for r in with_pct) / len(with_pct)


def playbook_track_record(db: Session, client_id: int) -> dict[str, dict]:
    """
    Win rate and lift magnitude per playbook_pattern (or insight.type fallback)
    for this client. Includes auto-derived outcomes from rechecks.
    """
    rows = (
        db.query(Task, Insight)
        .outerjoin(Insight, Task.insight_id == Insight.id)
        .filter(Task.client_id == client_id, Task.status == "done")
        .all()
    )
    track: dict[str, dict] = {}
    for task, insight in rows:
        outcome = effective_task_outcome(db, task, insight)
        if not outcome:
            continue
        key = (getattr(task, "playbook_pattern", None) or "").strip()
        if not key and insight is not None:
            key = (insight.type or "unknown").strip()
        if not key:
            key = "unknown"
        bucket = track.setdefault(key, {
            "wins": 0, "losses": 0, "flat": 0, "total": 0,
            "lift_pcts": [],
        })
        if outcome == "win":
            bucket["wins"] += 1
        elif outcome == "loss":
            bucket["losses"] += 1
        else:
            bucket["flat"] += 1
        bucket["total"] += 1

        lift = _primary_lift_for_task(db, task, insight)
        if lift is not None:
            bucket["lift_pcts"].append(lift)

    # Compute median/mean lift per pattern
    for key, bucket in track.items():
        lifts = bucket.get("lift_pcts", [])
        if lifts:
            bucket["median_lift_pct"] = round(statistics.median(lifts), 1)
            bucket["mean_lift_pct"] = round(statistics.mean(lifts), 1)
            bucket["max_lift_pct"] = round(max(lifts), 1)
            bucket["min_lift_pct"] = round(min(lifts), 1)
        else:
            bucket["median_lift_pct"] = None
            bucket["mean_lift_pct"] = None
            bucket["max_lift_pct"] = None
            bucket["min_lift_pct"] = None
        # Clean up raw values before returning (not JSON-serializable needed here)
        if "lift_pcts" in bucket:
            del bucket["lift_pcts"]

    return track


def format_playbook_track_record(track: dict[str, dict], *, limit: int = 8) -> list[str]:
    """Prompt lines for action_planner — deprioritize historically weak patterns."""
    if not track:
        return []
    lines = [
        "=== PLAYBOOK TRACK RECORD (this client — Proven outcomes feed back into prescriptions) ===",
        f"Do NOT prescribe playbooks with <{int(WIN_RATE_SUPPRESS_THRESHOLD * 100)}% win rate when ≥{MIN_SAMPLES_FOR_DOWNRANK} past tries — they consistently lose.",
        f"PREFER playbooks with ≥{int(WIN_RATE_BOOST_THRESHOLD * 100)}% win rate and positive median lift — these are proven winners for this client.",
        "Prefer patterns with more wins than losses AND higher median lift.",
    ]
    ranked = sorted(
        track.items(),
        key=lambda kv: (
            -(kv[1].get("total") or 0),
            -(kv[1].get("wins") or 0),
            -(kv[1].get("median_lift_pct") or 0),
        ),
    )
    for pattern, stats in ranked[:limit]:
        w, l, f = stats.get("wins", 0), stats.get("losses", 0), stats.get("flat", 0)
        total = w + l + f
        med = stats.get("median_lift_pct")
        lift_str = (
            f", median +{med}% lift" if med is not None and med > 0
            else f", median {med}% change" if med is not None
            else ""
        )
        wr_pct = round((w / total) * 100) if total > 0 else 0
        flag = ""
        if total >= MIN_SAMPLES_FOR_DOWNRANK:
            if wr_pct < (WIN_RATE_SUPPRESS_THRESHOLD * 100):
                flag = " [AVOID — consistently loses]"
            elif wr_pct < 50:
                flag = " [WEAK — prefer alternatives]"
            elif wr_pct >= (WIN_RATE_BOOST_THRESHOLD * 100):
                flag = " [PREFER — proven winner]"
        lines.append(f"- {pattern}: {w} wins / {l} losses / {f} flat (n={total}, wr={wr_pct}%){lift_str}{flag}")
    return lines


def _downrank_multiplier(
    win_rate: float | None,
    total_samples: int,
    *,
    cross_client: bool = False,
) -> float:
    """Priority score multiplier based on historical win rate.

    - ≥MIN_SAMPLES_FOR_DOWNRANK, win_rate < WIN_RATE_SUPPRESS_THRESHOLD: heavy penalty
    - ≥MIN_SAMPLES_FOR_DOWNRANK, win_rate < 50%: moderate penalty
    - ≥MIN_SAMPLES_FOR_DOWNRANK, win_rate ≥ WIN_RATE_BOOST_THRESHOLD: boost
    - <MIN_SAMPLES_FOR_DOWNRANK or no data: 1.0 (neutral — maintain optionality)

    Cross-client data carries softer modifiers because client-specific
    outcomes are a stronger signal.
    """
    if total_samples < MIN_SAMPLES_FOR_DOWNRANK or win_rate is None:
        return 1.0

    if not cross_client:
        if win_rate < WIN_RATE_SUPPRESS_THRESHOLD:
            return 0.30
        if win_rate < 0.50:
            return 0.60
        if win_rate >= WIN_RATE_BOOST_THRESHOLD:
            return 1.20
    else:
        if win_rate < WIN_RATE_SUPPRESS_THRESHOLD:
            return 0.50
        if win_rate < 0.50:
            return 0.75
        if win_rate >= WIN_RATE_BOOST_THRESHOLD:
            return 1.10

    return 1.0


def playbook_win_rate(
    db: Session,
    client_id: int,
    *,
    cross_client_effectiveness: Optional[dict[str, dict]] = None,
) -> dict[str, dict]:
    """Per-playbook win rate + downrank factor for candidate scoring.

    Uses this client's track record first. Falls back to cross-client
    effectiveness data for playbooks this client hasn't yet tried.

    Returns {playbook_pattern: {win_rate, downrank_factor, wins, losses, flat, total,
                                median_lift_pct, cross_client (bool)}}
    """
    track = playbook_track_record(db, client_id)
    result: dict[str, dict] = {}

    for pattern, stats in track.items():
        total = stats.get("total", 0)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        wr = (wins / total) if total > 0 else None
        result[pattern] = {
            "wins": wins,
            "losses": losses,
            "flat": stats.get("flat", 0),
            "total": total,
            "median_lift_pct": stats.get("median_lift_pct"),
            "mean_lift_pct": stats.get("mean_lift_pct"),
            "win_rate": wr,
            "downrank_factor": _downrank_multiplier(wr, total),
            "cross_client": False,
        }

    if cross_client_effectiveness:
        for pattern, xstats in cross_client_effectiveness.items():
            if pattern in result:
                continue
            total = xstats.get("total", 0) or 0
            wins = xstats.get("wins", 0) or 0
            wr = (wins / total) if total > 0 else None
            result[pattern] = {
                "wins": wins,
                "losses": 0,
                "flat": 0,
                "total": total,
                "median_lift_pct": xstats.get("median_lift_pct"),
                "mean_lift_pct": xstats.get("mean_lift_pct"),
                "win_rate": wr,
                "downrank_factor": _downrank_multiplier(wr, total, cross_client=True),
                "cross_client": True,
            }

    return result


def apply_downrank_to_score(
    priority_score: float,
    playbook_pattern: str,
    win_rates: dict[str, dict],
) -> tuple[float, float]:
    """Apply win-rate-based multiplier to a candidate's priority_score.

    Returns (adjusted_score, factor_applied).
    """
    wr_data = win_rates.get(playbook_pattern)
    if not wr_data:
        return (priority_score, 1.0)
    factor = wr_data.get("downrank_factor", 1.0)
    adjusted = round(priority_score * factor, 1)
    if factor != 1.0:
        logger.info(
            "Playbook %s win_rate=%.1f%% (n=%s, cross_client=%s) → priority %s × %.2f = %s",
            playbook_pattern,
            (wr_data.get("win_rate") or 0) * 100,
            wr_data.get("total", 0),
            wr_data.get("cross_client", False),
            priority_score,
            factor,
            adjusted,
        )
    return (adjusted, factor)
