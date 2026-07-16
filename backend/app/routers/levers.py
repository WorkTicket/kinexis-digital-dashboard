"""Growth Lever Thread API."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app import lever_service

router = APIRouter(prefix="/levers", tags=["levers"])


class StatusUpdate(BaseModel):
    status: str
    task_id: Optional[int] = None
    brief_id: Optional[int] = None
    impact_summary: Optional[str] = None
    confidence_label: Optional[str] = None
    include_in_report: Optional[bool] = None


class LinkTaskBody(BaseModel):
    task_id: int


class LinkBriefBody(BaseModel):
    brief_id: int


@router.get("/client/{client_id}")
def list_client_levers(
    client_id: int,
    include_dismissed: bool = Query(False),
    synthesize: bool = Query(True),
    db: Session = Depends(get_db),
):
    if synthesize:
        try:
            return lever_service.synthesize_levers_for_client(db, client_id)
        except Exception as e:
            existing = lever_service.list_levers(db, client_id, include_dismissed=include_dismissed)
            if existing:
                return existing
            raise HTTPException(status_code=500, detail=str(e)) from e
    return lever_service.list_levers(db, client_id, include_dismissed=include_dismissed)


@router.post("/client/{client_id}/synthesize")
def synthesize(client_id: int, db: Session = Depends(get_db)):
    return lever_service.synthesize_levers_for_client(db, client_id)


@router.get("/report/{client_id}")
def report_levers(client_id: int, db: Session = Depends(get_db)):
    return {"levers": lever_service.proven_levers_for_report(db, client_id)}


@router.get("/portfolio/report-ready")
def portfolio_ready(db: Session = Depends(get_db)):
    return {"by_client": lever_service.portfolio_report_ready(db)}


@router.get("/{lever_id}")
def get_one(lever_id: int, db: Session = Depends(get_db)):
    row = lever_service.get_lever(db, lever_id)
    if not row:
        raise HTTPException(status_code=404, detail="Lever not found")
    return row


@router.post("/{lever_id}/status")
def set_status(lever_id: int, body: StatusUpdate, db: Session = Depends(get_db)):
    try:
        return lever_service.advance_status(
            db,
            lever_id,
            body.status,
            task_id=body.task_id,
            brief_id=body.brief_id,
            impact_summary=body.impact_summary,
            confidence_label=body.confidence_label,
            include_in_report=body.include_in_report,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Lever not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{lever_id}/link-task")
def link_task(lever_id: int, body: LinkTaskBody, db: Session = Depends(get_db)):
    try:
        return lever_service.link_task(db, lever_id, body.task_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{lever_id}/link-brief")
def link_brief(lever_id: int, body: LinkBriefBody, db: Session = Depends(get_db)):
    try:
        return lever_service.link_brief(db, lever_id, body.brief_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
