"""Recommendation lifecycle — propose → accept → execute → verify → learn.

Bridges insights/tasks/impact into a durable cross-client learning loop.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Insight, Recommendation, Task
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

VALID_STATUSES = frozenset({
    "proposed",
    "accepted",
    "scheduled",
    "in_progress",
    "completed",
    "verified",
    "archived",
})
VALID_OUTCOMES = frozenset({"win", "loss", "flat"})


def propose_from_insight(
    db: Session,
    insight: Insight,
    *,
    expected_lift_pct: Optional[float] = None,
    expected_metric: Optional[str] = None,
) -> Recommendation:
    """Create or refresh a proposed recommendation for an insight."""
    existing = (
        db.query(Recommendation)
        .filter(
            Recommendation.insight_id == insight.id,
            Recommendation.status.in_(["proposed", "accepted", "scheduled", "in_progress"]),
        )
        .order_by(Recommendation.id.desc())
        .first()
    )
    title = (insight.recommended_action or insight.message or insight.type or "Fix")[:500]
    if existing:
        existing.title = title
        existing.fix_type = insight.type
        if expected_lift_pct is not None:
            existing.expected_lift_pct = expected_lift_pct
        if expected_metric is not None:
            existing.expected_metric = expected_metric
        return existing

    rec = Recommendation(
        client_id=insight.client_id,
        insight_id=insight.id,
        status="proposed",
        fix_type=insight.type,
        title=title,
        expected_lift_pct=expected_lift_pct,
        expected_metric=expected_metric,
    )
    db.add(rec)
    db.flush()
    return rec


def accept_for_task(db: Session, task: Task) -> Optional[Recommendation]:
    """Link/create a recommendation when a task is assigned from an insight."""
    insight = None
    if task.insight_id:
        insight = db.query(Insight).filter(Insight.id == task.insight_id).first()

    if insight:
        rec = propose_from_insight(db, insight)
    else:
        title = (task.result_notes or task.playbook_pattern or "Work item")[:500]
        rec = Recommendation(
            client_id=task.client_id,
            insight_id=None,
            status="proposed",
            fix_type=task.playbook_pattern,
            title=title.split("\n", 1)[0][:500],
        )
        db.add(rec)
        db.flush()

    rec.task_id = task.id
    rec.status = "accepted"
    if task.status == "in_progress":
        rec.status = "in_progress"
    elif task.status == "done":
        rec.status = "completed"
        rec.completed_at = utcnow()
    db.flush()
    return rec


def sync_from_task(db: Session, task: Task) -> Optional[Recommendation]:
    """Mirror task status into the linked recommendation."""
    rec = (
        db.query(Recommendation)
        .filter(Recommendation.task_id == task.id)
        .order_by(Recommendation.id.desc())
        .first()
    )
    if not rec and task.insight_id:
        return accept_for_task(db, task)
    if not rec:
        return None

    status = (task.status or "").lower()
    if status == "open" and rec.status in ("proposed",):
        rec.status = "accepted"
    elif status == "in_progress":
        rec.status = "in_progress"
    elif status == "done":
        rec.status = "completed"
        if not rec.completed_at:
            rec.completed_at = utcnow()
    elif status == "skipped":
        rec.status = "archived"
        rec.notes = ((rec.notes or "") + "\nSkipped via task").strip()
    db.flush()
    return rec


def verify_from_impact(
    db: Session,
    task_id: int,
    outcome: str,
    lift_pct: Optional[float] = None,
) -> Optional[Recommendation]:
    """Close the loop when Prove measures win/loss/flat."""
    outcome_norm = (outcome or "").strip().lower()
    if outcome_norm not in VALID_OUTCOMES:
        return None

    rec = (
        db.query(Recommendation)
        .filter(Recommendation.task_id == task_id)
        .order_by(Recommendation.id.desc())
        .first()
    )
    if not rec:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return None
        rec = accept_for_task(db, task)
        if not rec:
            return None

    rec.status = "verified"
    rec.outcome = outcome_norm
    if lift_pct is not None:
        rec.actual_lift_pct = float(lift_pct)
    rec.verified_at = utcnow()
    if not rec.completed_at:
        rec.completed_at = utcnow()
    db.flush()
    return rec


def effectiveness_by_fix_type(db: Session) -> list[dict]:
    """Cross-client win rates from verified recommendations."""
    rows = (
        db.query(Recommendation)
        .filter(Recommendation.status == "verified", Recommendation.outcome.isnot(None))
        .all()
    )
    by: dict[str, dict] = {}
    for rec in rows:
        key = (rec.fix_type or "unknown").strip() or "unknown"
        bucket = by.setdefault(
            key,
            {"fix_type": key, "wins": 0, "losses": 0, "flat": 0, "total": 0, "lifts": []},
        )
        bucket["total"] += 1
        if rec.outcome == "win":
            bucket["wins"] += 1
        elif rec.outcome == "loss":
            bucket["losses"] += 1
        else:
            bucket["flat"] += 1
        if rec.actual_lift_pct is not None:
            bucket["lifts"].append(float(rec.actual_lift_pct))

    out = []
    for key, b in sorted(by.items(), key=lambda kv: (-kv[1]["wins"], kv[0])):
        lifts = sorted(b["lifts"])
        median = lifts[len(lifts) // 2] if lifts else None
        win_rate = (b["wins"] / b["total"]) if b["total"] else None
        out.append(
            {
                "fix_type": key,
                "wins": b["wins"],
                "losses": b["losses"],
                "flat": b["flat"],
                "total": b["total"],
                "win_rate": round(win_rate, 3) if win_rate is not None else None,
                "median_lift_pct": round(median, 1) if median is not None else None,
                "measured": True,
            }
        )
    return out


def list_recommendations(
    db: Session,
    *,
    client_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> list[Recommendation]:
    q = db.query(Recommendation)
    if client_id is not None:
        q = q.filter(Recommendation.client_id == client_id)
    if status:
        q = q.filter(Recommendation.status == status)
    return q.order_by(Recommendation.created_at.desc()).limit(limit).all()
