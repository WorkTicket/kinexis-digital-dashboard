"""Persist monthly reports and list the report library."""
from __future__ import annotations

import calendar
import json
import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Client,
    Insight,
    Task,
    ClientBaseline,
    MonthlyReport,
    DataSource,
    GrowthLeverThread,
)
from app.success_report.narrative import _narrative_is_low_quality
from app.timeutil import utcnow

logger = logging.getLogger(__name__)


def persist_monthly_report(db: Session, client_id: int, year: int, month: int) -> dict:
    # Resolve via package so patches of app.success_report.build_success_report apply
    from app import success_report as _success_report

    report = _success_report.build_success_report(db, client_id, year=year, month=month, refresh=True)
    if report.get("error"):
        return report
    existing = (
        db.query(MonthlyReport)
        .filter(
            MonthlyReport.client_id == client_id,
            MonthlyReport.year == year,
            MonthlyReport.month == month,
        )
        .first()
    )
    # Don't persist cache metadata / live white-label into the stored payload
    to_store = {
        k: v
        for k, v in report.items()
        if k not in ("from_cache", "monthly_report_id", "agency", "readiness", "stale")
    }
    payload = json.dumps(to_store)
    if existing:
        existing.payload_json = payload
        existing.generated_at = utcnow()
        row = existing
    else:
        row = MonthlyReport(
            client_id=client_id,
            year=year,
            month=month,
            payload_json=payload,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    report["monthly_report_id"] = row.id
    report["from_cache"] = False
    return report

def get_report_library(db: Session, client_id: int) -> dict:
    """Cheap library payload — no build_success_report / AI."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return {"error": "not_found"}

    rows = (
        db.query(MonthlyReport)
        .filter(MonthlyReport.client_id == client_id)
        .order_by(MonthlyReport.year.desc(), MonthlyReport.month.desc())
        .all()
    )

    last_metric_sync: Optional[datetime] = None
    for ds in db.query(DataSource).filter(DataSource.client_id == client_id).all():
        if ds.last_synced_at and (last_metric_sync is None or ds.last_synced_at > last_metric_sync):
            last_metric_sync = ds.last_synced_at

    proven_count = (
        db.query(func.count(GrowthLeverThread.id))
        .filter(
            GrowthLeverThread.client_id == client_id,
            GrowthLeverThread.status == "proven",
            GrowthLeverThread.include_in_report.is_(True),
        )
        .scalar()
        or 0
    )
    tasks_done = (
        db.query(func.count(Task.id))
        .filter(Task.client_id == client_id, Task.status == "done")
        .scalar()
        or 0
    )
    insights_open = (
        db.query(func.count(Insight.id))
        .filter(
            Insight.client_id == client_id,
            Insight.resolved == False,  # noqa: E712
        )
        .scalar()
        or 0
    )
    baseline = db.query(ClientBaseline).filter(ClientBaseline.client_id == client_id).first()

    reports = []
    for r in rows:
        narrative_ready = False
        stale = False
        try:
            payload = json.loads(r.payload_json or "{}")
            narrative = payload.get("narrative") if isinstance(payload, dict) else None
            narrative_ready = bool(narrative) and not _narrative_is_low_quality(str(narrative))
        except (json.JSONDecodeError, TypeError):
            payload = {}
        if last_metric_sync and r.generated_at and last_metric_sync > r.generated_at:
            stale = True
        reports.append(
            {
                "id": r.id,
                "year": r.year,
                "month": r.month,
                "month_name": calendar.month_name[r.month],
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
                "narrative_ready": narrative_ready,
                "stale": stale,
            }
        )

    has_saved = len(reports) > 0
    last_saved_at = reports[0]["generated_at"] if has_saved else None
    data_synced = last_metric_sync is not None
    has_work_or_proof = proven_count > 0 or tasks_done > 0
    checklist = {
        "data_synced": data_synced,
        "baseline_set": baseline is not None,
        "work_or_proof": has_work_or_proof,
        "has_saved_report": has_saved,
        "narrative_ready": any(r["narrative_ready"] for r in reports),
    }
    ready_score = sum(1 for v in checklist.values() if v)
    status = "ready" if ready_score >= 3 and has_saved else ("ready" if ready_score >= 3 else "draft")
    if has_saved and any(r["stale"] for r in reports[:1]):
        status = "stale"
    elif not has_saved and ready_score >= 2:
        status = "unsaved"

    return {
        "client_id": client_id,
        "client_name": client.name,
        "status": status,
        "has_saved": has_saved,
        "last_saved_at": last_saved_at,
        "data_freshness": last_metric_sync.isoformat() if last_metric_sync else None,
        "proven_lever_count": int(proven_count),
        "tasks_completed": int(tasks_done),
        "insights_open": int(insights_open),
        "baseline_set": baseline is not None,
        "checklist": checklist,
        "reports": reports,
    }


def run_monthly_reports_for_all_clients() -> dict:
    """Generate previous calendar month reports for every client."""
    from app.database import SessionLocal

    today = date.today()
    if today.month == 1:
        year, month = today.year - 1, 12
    else:
        year, month = today.year, today.month - 1

    db = SessionLocal()
    generated = 0
    errors = 0
    try:
        clients = db.query(Client).all()
        for client in clients:
            try:
                persist_monthly_report(db, client.id, year, month)
                generated += 1
            except Exception as e:
                errors += 1
                logger.error("Monthly report failed for client %s: %s", client.id, e)
    finally:
        db.close()
    return {"year": year, "month": month, "generated": generated, "errors": errors}
