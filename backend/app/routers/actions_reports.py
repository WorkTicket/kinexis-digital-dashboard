"""Success report HTML/PDF/library endpoints."""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client, MonthlyReport
from app.success_report import (
    build_success_report,
    render_success_report_html,
    persist_monthly_report,
    report_download_filename,
    get_report_library,
)
from app.pdf_export import html_to_pdf, playwright_available

logger = logging.getLogger(__name__)

router = APIRouter(tags=["actions"])

# ── Success Report ────────────────────────────────────────────

@router.get("/report/{client_id}")
def get_success_report(
    client_id: int,
    days: int = Query(30, ge=7, le=90),
    year: Optional[int] = Query(None, ge=2020, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        if year is not None and month is not None:
            report = build_success_report(db, client_id, year=year, month=month, refresh=refresh)
        else:
            report = build_success_report(db, client_id, days=days, refresh=refresh)
    except Exception as e:
        logger.error("Failed to build success report for client %s: %s", client_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to build report: {e}") from e
    if report.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Client not found")
    return report


@router.get("/report/{client_id}/html", response_class=HTMLResponse)
def get_success_report_html(
    client_id: int,
    days: int = Query(30, ge=7, le=90),
    year: Optional[int] = Query(None, ge=2020, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        if year is not None and month is not None:
            report = build_success_report(db, client_id, year=year, month=month, refresh=refresh)
        else:
            report = build_success_report(db, client_id, days=days, refresh=refresh)
    except Exception as e:
        logger.error("Failed to build success report HTML for client %s: %s", client_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to build report: {e}") from e
    if report.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Client not found")
    return HTMLResponse(content=render_success_report_html(report))


@router.get("/report/{client_id}/pdf")
def get_success_report_pdf(
    client_id: int,
    days: int = Query(30, ge=7, le=90),
    year: Optional[int] = Query(None, ge=2020, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Download a PDF success report (Playwright). Falls back with 503 if unavailable."""
    try:
        if year is not None and month is not None:
            report = build_success_report(db, client_id, year=year, month=month, refresh=refresh)
        else:
            report = build_success_report(db, client_id, days=days, refresh=refresh)
    except Exception as e:
        logger.error("Failed to build success report PDF for client %s: %s", client_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to build report: {e}") from e
    if report.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Client not found")

    html = render_success_report_html(report)
    agency = report.get("agency") or {}
    client = report.get("client") or {}
    period = report.get("period") or {}
    if period.get("mode") == "monthly":
        period_label = f"{period.get('month_name', '')} {period.get('year', '')}".strip()
    else:
        period_label = f"{period.get('start', '')} → {period.get('end', '')}"
    header_left = f"{client.get('name', '')} · {period_label}".strip(" ·")
    footer_left = f"{agency.get('name') or 'Kinexis'} · Confidential"
    pdf_bytes = html_to_pdf(html, header_left=header_left, footer_left=footer_left)
    if not pdf_bytes:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "pdf_unavailable",
                "message": (
                    "PDF engine not available. Install with: pip install playwright && "
                    "playwright install chromium — or use Print / Save PDF from the HTML report."
                ),
                "playwright_installed": playwright_available(),
            },
        )
    filename = report_download_filename(report)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/report/{client_id}/monthly")
def generate_monthly_report(
    client_id: int,
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
):
    try:
        report = persist_monthly_report(db, client_id, year, month)
    except Exception as e:
        logger.error("Failed to generate monthly report for client %s: %s", client_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate monthly report: {e}") from e
    if report.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Client not found")
    return report


@router.get("/report/{client_id}/library")
def report_library(client_id: int, db: Session = Depends(get_db)):
    """Saved months + readiness — does not build or call AI."""
    data = get_report_library(db, client_id)
    if data.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Client not found")
    return data


@router.delete("/report/{client_id}/monthly/{report_id}")
def delete_monthly_report(
    client_id: int,
    report_id: int,
    db: Session = Depends(get_db),
):
    try:
        from app.models import MonthlyReport

        report = (
            db.query(MonthlyReport)
            .filter(
                MonthlyReport.id == report_id,
                MonthlyReport.client_id == client_id,
            )
            .first()
        )
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        db.delete(report)
        db.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to delete monthly report %s for client %s: %s",
            report_id,
            client_id,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Failed to delete report: {e}") from e


@router.get("/report/{client_id}/monthly/list")
def list_monthly_reports(client_id: int, db: Session = Depends(get_db)):
    data = get_report_library(db, client_id)
    if data.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Client not found")
    return data.get("reports") or []



