"""Formal experiment registry API — hypothesis → ship → Prove metric."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client, Experiment, Recommendation, Task
from app.timeutil import utcnow

router = APIRouter(prefix="/experiments", tags=["experiments"])

VALID_STATUSES = frozenset(
    {"draft", "running", "won", "lost", "inconclusive", "archived"}
)


class ExperimentCreate(BaseModel):
    client_id: int
    hypothesis: str = Field(..., min_length=3, max_length=4000)
    control: Optional[str] = None
    treatment: Optional[str] = None
    success_metric: Optional[str] = None
    task_id: Optional[int] = None
    recommendation_id: Optional[int] = None
    status: str = "draft"
    notes: Optional[str] = None


class ExperimentUpdate(BaseModel):
    hypothesis: Optional[str] = None
    control: Optional[str] = None
    treatment: Optional[str] = None
    success_metric: Optional[str] = None
    status: Optional[str] = None
    outcome_lift_pct: Optional[float] = None
    notes: Optional[str] = None
    task_id: Optional[int] = None
    recommendation_id: Optional[int] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None


def _serialize(exp: Experiment) -> dict:
    return {
        "id": exp.id,
        "client_id": exp.client_id,
        "task_id": exp.task_id,
        "recommendation_id": exp.recommendation_id,
        "hypothesis": exp.hypothesis,
        "control": exp.control,
        "treatment": exp.treatment,
        "success_metric": exp.success_metric,
        "status": exp.status,
        "start_at": exp.start_at.isoformat() if exp.start_at else None,
        "end_at": exp.end_at.isoformat() if exp.end_at else None,
        "outcome_lift_pct": exp.outcome_lift_pct,
        "notes": exp.notes,
        "created_at": exp.created_at.isoformat() if exp.created_at else None,
    }


@router.get("/")
def list_experiments(
    client_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(Experiment)
    if client_id is not None:
        q = q.filter(Experiment.client_id == client_id)
    if status:
        q = q.filter(Experiment.status == status)
    rows = q.order_by(Experiment.created_at.desc()).limit(limit).all()
    return [_serialize(r) for r in rows]


@router.post("/")
def create_experiment(body: ExperimentCreate, db: Session = Depends(get_db)):
    if not db.query(Client).filter(Client.id == body.client_id).first():
        raise HTTPException(status_code=404, detail="Client not found")
    status = (body.status or "draft").strip().lower()
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    if body.task_id and not db.query(Task).filter(Task.id == body.task_id).first():
        raise HTTPException(status_code=404, detail="Task not found")
    if body.recommendation_id and not (
        db.query(Recommendation).filter(Recommendation.id == body.recommendation_id).first()
    ):
        raise HTTPException(status_code=404, detail="Recommendation not found")

    exp = Experiment(
        client_id=body.client_id,
        hypothesis=body.hypothesis.strip(),
        control=(body.control or "").strip() or None,
        treatment=(body.treatment or "").strip() or None,
        success_metric=(body.success_metric or "").strip() or None,
        task_id=body.task_id,
        recommendation_id=body.recommendation_id,
        status=status,
        notes=body.notes,
        start_at=utcnow() if status == "running" else None,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return _serialize(exp)


@router.patch("/{experiment_id}")
def update_experiment(
    experiment_id: int, body: ExperimentUpdate, db: Session = Depends(get_db)
):
    exp = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] is not None:
        status = str(data["status"]).strip().lower()
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        data["status"] = status
        if status == "running" and not exp.start_at:
            data.setdefault("start_at", utcnow())
        if status in ("won", "lost", "inconclusive", "archived") and not exp.end_at:
            data.setdefault("end_at", utcnow())

    for key, val in data.items():
        setattr(exp, key, val)
    db.commit()
    db.refresh(exp)
    return _serialize(exp)


@router.delete("/{experiment_id}")
def delete_experiment(experiment_id: int, db: Session = Depends(get_db)):
    exp = db.query(Experiment).filter(Experiment.id == experiment_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    db.delete(exp)
    db.commit()
    return {"ok": True}
