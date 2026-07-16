"""Impact tracking endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Task
from app.impact_tracker import (
    snapshot_task_metrics,
    recheck_task_impact,
    get_task_impact_summary,
    portfolio_impact_wins,
    set_task_impact_outcome,
)

router = APIRouter(tags=["actions"])


@router.post("/impact/snapshot/{task_id}")
def take_snapshot(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    snapshots = snapshot_task_metrics(task_id)
    return {"status": "captured", "metrics_snapped": len(snapshots)}


@router.post("/impact/recheck/{task_id}")
def run_recheck(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    results = recheck_task_impact(task_id)
    return {"status": "complete", "metrics": results}


class ImpactOutcomeBody(BaseModel):
    outcome: str  # win | loss | flat | auto


@router.post("/impact/outcome/{task_id}")
def set_impact_outcome(task_id: int, body: ImpactOutcomeBody, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    result = set_task_impact_outcome(task_id, body.outcome)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Invalid outcome"))
    return result


@router.get("/impact/wins/portfolio")
def get_portfolio_wins(days: int = Query(30, ge=7, le=180)):
    return {"days": days, "wins": portfolio_impact_wins(days)}


@router.get("/impact/batch")
def get_impact_batch(task_ids: str = Query(..., description="Comma-separated task IDs")):
    """Load impact summaries for many tasks in one request (Prove tab)."""
    ids: list[int] = []
    for part in task_ids.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    ids = ids[:50]
    db = SessionLocal()
    try:
        return {str(tid): get_task_impact_summary(tid, db=db) for tid in ids}
    finally:
        db.close()


@router.get("/impact/{task_id}")
def get_impact(task_id: int):
    return get_task_impact_summary(task_id)
