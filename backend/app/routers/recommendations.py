"""Recommendation lifecycle API — propose/accept/verify + cross-client learning."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Insight, Recommendation, Task
from app import recommendation_service as recs

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    insight_id: Optional[int] = None
    task_id: Optional[int] = None
    status: str
    fix_type: Optional[str] = None
    title: str
    expected_lift_pct: Optional[float] = None
    expected_metric: Optional[str] = None
    actual_lift_pct: Optional[float] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    verified_at: Optional[str] = None


def _serialize(rec: Recommendation) -> dict:
    return {
        "id": rec.id,
        "client_id": rec.client_id,
        "insight_id": rec.insight_id,
        "task_id": rec.task_id,
        "status": rec.status,
        "fix_type": rec.fix_type,
        "title": rec.title,
        "expected_lift_pct": rec.expected_lift_pct,
        "expected_metric": rec.expected_metric,
        "actual_lift_pct": rec.actual_lift_pct,
        "outcome": rec.outcome,
        "notes": rec.notes,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "completed_at": rec.completed_at.isoformat() if rec.completed_at else None,
        "verified_at": rec.verified_at.isoformat() if rec.verified_at else None,
    }


class ProposeBody(BaseModel):
    insight_id: int
    expected_lift_pct: Optional[float] = None
    expected_metric: Optional[str] = None


class StatusBody(BaseModel):
    status: str = Field(..., description="proposed|accepted|scheduled|in_progress|completed|verified|archived")
    notes: Optional[str] = None


@router.get("/")
def list_recs(
    client_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = recs.list_recommendations(db, client_id=client_id, status=status, limit=limit)
    return [_serialize(r) for r in rows]


@router.get("/effectiveness")
def recommendation_effectiveness(db: Session = Depends(get_db)):
    return {"fixes": recs.effectiveness_by_fix_type(db)}


@router.post("/propose")
def propose(body: ProposeBody, db: Session = Depends(get_db)):
    insight = db.query(Insight).filter(Insight.id == body.insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    rec = recs.propose_from_insight(
        db,
        insight,
        expected_lift_pct=body.expected_lift_pct,
        expected_metric=body.expected_metric,
    )
    db.commit()
    db.refresh(rec)
    return _serialize(rec)


@router.post("/from-task/{task_id}")
def accept_from_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    rec = recs.accept_for_task(db, task)
    db.commit()
    if not rec:
        raise HTTPException(status_code=400, detail="Could not create recommendation")
    db.refresh(rec)
    return _serialize(rec)


@router.put("/{rec_id}/status")
def update_status(rec_id: int, body: StatusBody, db: Session = Depends(get_db)):
    rec = db.query(Recommendation).filter(Recommendation.id == rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    status = (body.status or "").strip().lower()
    if status not in recs.VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(recs.VALID_STATUSES)}")
    rec.status = status
    if body.notes is not None:
        rec.notes = body.notes
    db.commit()
    db.refresh(rec)
    return _serialize(rec)
