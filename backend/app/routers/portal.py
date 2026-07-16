"""Remote client portal — tokenized success report HTML for external stakeholders."""

from __future__ import annotations

import json
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client, MonthlyReport, ReportShareToken
from app.public_urls import absolute_public_url
from app.timeutil import utcnow

router = APIRouter(prefix="/portal", tags=["portal"])


class ReportShareBody(BaseModel):
    client_id: int
    report_id: Optional[int] = None
    expires_days: int = Field(90, ge=7, le=365)


def _load_report_payload(db: Session, row: ReportShareToken) -> dict:
    if row.report_id:
        mr = db.query(MonthlyReport).filter(MonthlyReport.id == row.report_id).first()
        if not mr:
            raise HTTPException(status_code=404, detail="Report not found")
        try:
            return json.loads(mr.payload_json or "{}")
        except (json.JSONDecodeError, TypeError) as e:
            raise HTTPException(status_code=500, detail=f"Corrupt report payload: {e}") from e

    # Live rolling report when no cached monthly row
    from app.success_report import build_success_report
    from app.success_report.branding import attach_agency_branding

    report = build_success_report(db, row.client_id, days=30)
    if not report or report.get("error"):
        raise HTTPException(status_code=404, detail="Could not build report for share link")
    return attach_agency_branding(db, report)


@router.post("/report/share")
def create_report_share(body: ReportShareBody, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == body.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    report_id = body.report_id
    period_start = period_end = None
    if report_id is not None:
        mr = (
            db.query(MonthlyReport)
            .filter(MonthlyReport.id == report_id, MonthlyReport.client_id == body.client_id)
            .first()
        )
        if not mr:
            raise HTTPException(status_code=404, detail="Report not found for client")
        try:
            payload = json.loads(mr.payload_json or "{}")
            period = payload.get("period") or {}
            period_start = period.get("start")
            period_end = period.get("end")
        except (json.JSONDecodeError, TypeError):
            pass

    token = secrets.token_urlsafe(24)
    row = ReportShareToken(
        client_id=body.client_id,
        report_id=report_id,
        token=token,
        period_start=period_start,
        period_end=period_end,
        expires_at=utcnow() + timedelta(days=int(body.expires_days or 90)),
        revoked=False,
    )
    db.add(row)
    db.commit()
    path = f"/portal/report/{token}/html"
    return {
        "token": token,
        "client_id": body.client_id,
        "report_id": report_id,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "path": path,
        "api_path": path,
        "html_url": absolute_public_url(path, db),
        "url": absolute_public_url(path, db),
    }


@router.get("/report/{token}")
def get_report_share(token: str, db: Session = Depends(get_db)):
    row = (
        db.query(ReportShareToken)
        .filter(ReportShareToken.token == token, ReportShareToken.revoked == False)  # noqa: E712
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Report link not found")
    if row.expires_at and row.expires_at < utcnow():
        raise HTTPException(status_code=410, detail="Report link expired")
    payload = _load_report_payload(db, row)
    return {
        "client_id": row.client_id,
        "report_id": row.report_id,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "report": payload,
    }


@router.get("/report/{token}/html", response_class=HTMLResponse)
def get_report_share_html(token: str, db: Session = Depends(get_db)):
    data = get_report_share(token, db)
    from app.success_report.html import render_success_report_html
    from app.success_report.branding import attach_agency_branding

    report = attach_agency_branding(db, data["report"])
    return render_success_report_html(report)


@router.post("/report/{token}/revoke")
def revoke_report_share(token: str, db: Session = Depends(get_db)):
    row = db.query(ReportShareToken).filter(ReportShareToken.token == token).first()
    if not row:
        raise HTTPException(status_code=404, detail="Report link not found")
    row.revoked = True
    db.commit()
    return {"ok": True}
