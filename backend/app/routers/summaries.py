from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from app.database import get_db
from app.models import WeeklySummary, Client, Insight
from app.ai_summarizer import generate_weekly_summary
from app.ai_client import ai_configured, diagnose_ai

router = APIRouter(prefix="/summaries", tags=["summaries"])


class SummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    week_start: date
    content: str
    reviewed: bool
    created_at: datetime


@router.get("/", response_model=list[SummaryResponse])
def list_summaries(
    client_id: Optional[int] = Query(None),
    reviewed: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(WeeklySummary).order_by(WeeklySummary.created_at.desc())
    if client_id is not None:
        q = q.filter(WeeklySummary.client_id == client_id)
    if reviewed is not None:
        q = q.filter(WeeklySummary.reviewed == reviewed)
    return q.limit(20).all()


@router.post("/generate/{client_id}")
def generate_summary(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    pre = diagnose_ai()
    if not pre.get("ok"):
        return {"status": "skipped", "message": pre.get("message") or "AI is not ready."}

    open_insights = (
        db.query(Insight)
        .filter(Insight.client_id == client_id, Insight.resolved == False)  # noqa: E712
        .count()
    )
    if open_insights == 0:
        return {
            "status": "skipped",
            "message": "No unresolved insights to summarize. Sync data or open Detect first.",
        }

    summary = generate_weekly_summary(client_id)
    if summary is None:
        return {
            "status": "skipped",
            "message": (
                "AI generation failed. Ensure Ollama is running with the configured model "
                "(first request after idle can take 1–2 minutes)."
                if ai_configured()
                else "AI is not configured."
            ),
        }

    return {
        "status": "generated",
        "summary_id": summary.id,
        "week_start": summary.week_start.isoformat(),
    }


@router.put("/{summary_id}/review")
def mark_reviewed(summary_id: int, db: Session = Depends(get_db)):
    summary = db.query(WeeklySummary).filter(WeeklySummary.id == summary_id).first()
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    summary.reviewed = True
    db.commit()
    return {"ok": True}
