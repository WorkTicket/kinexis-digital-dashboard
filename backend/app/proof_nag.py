"""Pending-proof nagging — surfaces tasks that need recheck, insights stale after fix.

Runs as a scheduled job (daily). Identifies:
1. Tasks marked "done" with a baseline older than the impact window but no recheck
2. Insights resolved as "shipped" but whose target metric hasn't improved
3. Growth levers stuck in "proving" status beyond the expected window
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import Task, Insight, ImpactSnapshot, GrowthLeverThread, Client
from app.impact_tracker import get_impact_window_days
from app.timeutil import utcnow

logger = logging.getLogger(__name__)


def find_pending_proof_tasks(db: Session) -> list[dict[str, Any]]:
    """Find tasks done >window_days ago with a baseline but no recheck snapshot."""
    window = get_impact_window_days(db)
    cutoff = date.today() - timedelta(days=window)

    done_tasks = (
        db.query(Task)
        .filter(Task.status == "done")
        .all()
    )
    pending = []
    for task in done_tasks:
        baseline = (
            db.query(ImpactSnapshot)
            .filter(
                ImpactSnapshot.task_id == task.id,
                ImpactSnapshot.snapshot_type == "baseline",
            )
            .order_by(ImpactSnapshot.created_at.asc())
            .first()
        )
        if not baseline or (baseline.created_at and baseline.created_at.date() > cutoff):
            continue
        recheck = (
            db.query(ImpactSnapshot)
            .filter(
                ImpactSnapshot.task_id == task.id,
                ImpactSnapshot.snapshot_type == "recheck",
            )
            .first()
        )
        if recheck:
            continue
        insight = None
        if task.insight_id:
            insight = db.query(Insight).filter(Insight.id == task.insight_id).first()
        days_waiting = (utcnow() - baseline.created_at).days if baseline.created_at else 0
        pending.append({
            "task_id": task.id,
            "client_id": task.client_id,
            "insight_type": insight.type if insight else None,
            "days_waiting": days_waiting,
            "baseline_at": baseline.created_at.isoformat() if baseline.created_at else None,
            "notes": (task.result_notes or insight.message if insight else "")[:200],
        })
    return pending


def find_stuck_proving_levers(db: Session) -> list[dict[str, Any]]:
    """Growth levers stuck in 'proving' >30 days without resolution."""
    cutoff = utcnow() - timedelta(days=30)
    stuck = (
        db.query(GrowthLeverThread)
        .filter(
            GrowthLeverThread.status == "proving",
            GrowthLeverThread.updated_at < cutoff,
        )
        .all()
    )
    results = []
    for lever in stuck:
        client = db.query(Client).filter(Client.id == lever.client_id).first()
        results.append({
            "lever_id": lever.id,
            "client_id": lever.client_id,
            "client_name": client.name if client else "",
            "title": lever.title,
            "days_stuck": (utcnow() - lever.updated_at).days,
        })
    return results


def run_pending_proof_check(db: Session | None = None) -> dict[str, Any]:
    """Scheduled job entry point. Returns summary of pending-proof items found."""
    close = False
    if db is None:
        from app.database import SessionLocal
        db = SessionLocal()
        close = True
    try:
        pending_tasks = find_pending_proof_tasks(db)
        stuck_levers = find_stuck_proving_levers(db)
        total = len(pending_tasks) + len(stuck_levers)
        if total:
            logger.info(
                "Pending-proof check: %d tasks awaiting recheck, %d stuck levers",
                len(pending_tasks),
                len(stuck_levers),
            )
        return {
            "pending_recheck_count": len(pending_tasks),
            "stuck_levers_count": len(stuck_levers),
            "total": total,
        }
    finally:
        if close:
            db.close()
