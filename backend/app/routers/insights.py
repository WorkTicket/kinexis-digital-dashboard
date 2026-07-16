import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.orm import Session

from app.agent_fix_report import build_agent_fix_markdown
from app.database import get_db
from app.insight_service import generate_insights_for_client
from app.models import Client, Insight, AnomalyNotification
from app.ship_log import apply_ship_log

router = APIRouter(prefix="/insights", tags=["insights"])


class InsightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    type: str
    message: str
    recommended_action: Optional[str] = None
    severity: str
    kind: str = "opportunity"
    priority_score: Optional[float] = None
    created_at: datetime
    resolved: bool
    fingerprint: Optional[str] = None
    target_query: Optional[str] = None
    target_url: Optional[str] = None
    evidence: Optional[Any] = None
    resolve_reason: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _parse_evidence(cls, data: Any) -> Any:
        """Map evidence_json ORM column → evidence (parsed JSON when possible)."""
        if isinstance(data, Insight):
            raw = getattr(data, "evidence_json", None)
            evidence = None
            if raw:
                try:
                    evidence = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    evidence = raw
            return {
                "id": data.id,
                "client_id": data.client_id,
                "type": data.type,
                "message": data.message,
                "recommended_action": data.recommended_action,
                "severity": data.severity,
                "kind": data.kind or "opportunity",
                "priority_score": data.priority_score,
                "created_at": data.created_at,
                "resolved": bool(data.resolved),
                "fingerprint": data.fingerprint,
                "target_query": data.target_query,
                "target_url": data.target_url,
                "evidence": evidence,
                "resolve_reason": data.resolve_reason,
                "confidence_tier": getattr(data, "confidence_tier", None),
                "sample_size": getattr(data, "sample_size", None),
                "trend_cv": getattr(data, "trend_cv", None),
                "algorithmic_caveat": getattr(data, "algorithmic_caveat", False),
            }
        if isinstance(data, dict) and "evidence" not in data and data.get("evidence_json"):
            raw = data.get("evidence_json")
            try:
                data = {**data, "evidence": json.loads(raw)}
            except (json.JSONDecodeError, TypeError):
                data = {**data, "evidence": raw}
        return data



class DeliveredBody(BaseModel):
    ids: list[int]


class ShipLogBody(BaseModel):
    markdown: str
    mark_done: bool = True
    assigned_to: Optional[str] = None


@router.get("/", response_model=list[InsightResponse])
def list_insights(
    response: Response,
    client_id: Optional[int] = Query(None),
    resolved: Optional[bool] = Query(None),
    kind: Optional[str] = Query(
        None,
        description="Filter: problem | opportunity | all",
    ),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Insight).order_by(Insight.created_at.desc())
    if client_id is not None:
        q = q.filter(Insight.client_id == client_id)
    if resolved is not None:
        q = q.filter(Insight.resolved == resolved)
    kind_norm = (kind or "").strip().lower()
    if kind_norm and kind_norm not in ("", "all"):
        if kind_norm not in ("problem", "opportunity"):
            raise HTTPException(status_code=400, detail="kind must be problem, opportunity, or all")
        q = q.filter(Insight.kind == kind_norm)
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Has-More"] = "1" if offset + len(rows) < total else "0"
    return rows


@router.get("/agent-md/{client_id}")
def download_agent_fix_md(
    client_id: int,
    severity: Optional[str] = Query(
        None,
        description="Optional severity filter: high | medium | low",
    ),
    kind: Optional[str] = Query(
        None,
        description="Optional kind filter: problem | opportunity | all",
    ),
    include_resolved: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Download a coding-agent Markdown brief for the Fix queue."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    sev = (severity or "").strip().lower() or None
    if sev in ("", "all"):
        sev = None
    if sev and sev not in ("high", "medium", "low"):
        raise HTTPException(status_code=400, detail="severity must be high, medium, or low")

    kind_norm = (kind or "problem").strip().lower()
    if kind_norm in ("", "all"):
        kind_norm = None
    if kind_norm and kind_norm not in ("problem", "opportunity"):
        raise HTTPException(status_code=400, detail="kind must be problem, opportunity, or all")

    try:
        body, filename = build_agent_fix_markdown(
            db,
            client_id,
            severity=sev,
            kind=kind_norm,
            include_resolved=include_resolved,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(
        content=body.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/ship-log/{client_id}")
def import_ship_log(client_id: int, body: ShipLogBody, db: Session = Depends(get_db)):
    """Import a filled agent brief / ship-log to close tasks and capture Prove baselines."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if not (body.markdown or "").strip():
        raise HTTPException(status_code=400, detail="markdown is required")
    result = apply_ship_log(
        db,
        client_id,
        body.markdown,
        mark_done=body.mark_done,
        assigned_to=body.assigned_to,
    )
    if result.get("status") == "error" and not result.get("applied"):
        raise HTTPException(status_code=400, detail=result.get("message") or "Import failed")
    return result


@router.post("/generate/{client_id}")
def generate_insights(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    created = generate_insights_for_client(db, client_id)

    return {
        "client_id": client_id,
        "insights_generated": len(created),
        "insights": [
            {"id": i.id, "type": i.type, "kind": i.kind, "severity": i.severity, "message": i.message}
            for i in created
        ],
    }


@router.get("/notifications/pending")
def pending_notifications(db: Session = Depends(get_db)):
    rows = (
        db.query(AnomalyNotification)
        .filter(AnomalyNotification.delivered == False)  # noqa: E712
        .order_by(AnomalyNotification.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "client_id": r.client_id,
                "insight_id": r.insight_id,
                "severity": r.severity,
                "title": r.title,
                "body": r.body,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.post("/notifications/delivered")
def mark_notifications_delivered(body: DeliveredBody, db: Session = Depends(get_db)):
    if not body.ids:
        return {"ok": True}
    rows = db.query(AnomalyNotification).filter(AnomalyNotification.id.in_(body.ids)).all()
    for r in rows:
        r.delivered = True
    db.commit()
    return {"ok": True}


class ResolveBody(BaseModel):
    resolve_reason: Optional[str] = "user"  # shipped | wont_fix | user | duplicate


@router.put("/{insight_id}/resolve")
def resolve_insight(
    insight_id: int,
    body: Optional[ResolveBody] = Body(None),
    db: Session = Depends(get_db),
):
    """Resolve an insight. Prefer shipped (linked done task) or wont_fix."""
    from app.models import Task

    insight = db.query(Insight).filter(Insight.id == insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")

    reason = ((body.resolve_reason if body else None) or "user").strip().lower()
    if reason not in ("shipped", "wont_fix", "user", "duplicate"):
        reason = "user"

    done_task = (
        db.query(Task)
        .filter(Task.insight_id == insight_id, Task.status == "done")
        .first()
    )
    if not done_task and reason not in ("wont_fix", "duplicate"):
        # Soft ship-gate: allow with explicit wont_fix; otherwise require done work
        raise HTTPException(
            status_code=400,
            detail="Ship a linked task first, or resolve as won't-fix",
        )

    if done_task and reason == "user":
        reason = "shipped"

    insight.resolved = True
    insight.resolve_reason = reason
    db.commit()
    return {"ok": True, "resolve_reason": reason}


@router.put("/{insight_id}/unresolve")
def unresolve_insight(insight_id: int, db: Session = Depends(get_db)):
    insight = db.query(Insight).filter(Insight.id == insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    insight.resolved = False
    insight.resolve_reason = None
    db.commit()
    return {"ok": True}
