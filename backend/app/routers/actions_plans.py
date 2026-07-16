"""Action plans + content briefs."""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client, ActionPlan, ContentBrief, DataSource, Insight
from app.action_planner import generate_action_plan
from app.ai_client import diagnose_ai
from app.content_brief import generate_content_brief

router = APIRouter(tags=["actions"])

# ── Action Plans ──────────────────────────────────────────────

@router.post("/plans/generate/{client_id}")
def create_action_plan(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    pre = diagnose_ai()
    if not pre.get("ok"):
        return {"status": "skipped", "message": pre.get("message") or "AI is not ready."}

    from app.models import Insight

    synced = (
        db.query(DataSource)
        .filter(DataSource.client_id == client_id, DataSource.status == "active")
        .count()
    )
    insights_count = (
        db.query(Insight)
        .filter(Insight.client_id == client_id, Insight.resolved == False)  # noqa: E712
        .count()
    )

    if synced == 0:
        return {
            "status": "skipped",
            "message": (
                "No data sources have synced successfully yet. "
                "Run a sync first from the Detect tab, then retry."
            ),
        }

    if insights_count == 0:
        return {
            "status": "skipped",
            "message": (
                f"Sync completed but no insights were detected. "
                f"Ensure clients have recent analytics data (GSC/GA4) and retry sync."
            ),
        }

    plan = generate_action_plan(client_id, db)
    if not plan:
        return {
            "status": "skipped",
            "message": (
                "Playbook generation failed. Ensure Ollama is running with the configured model "
                "(first request after idle can take 1–2 minutes), and that this client has "
                "insights or metrics to analyze."
            ),
        }

    try:
        actions = json.loads(plan.content) if plan.content else []
        action_count = len(actions) if isinstance(actions, list) else 0
    except (json.JSONDecodeError, TypeError):
        action_count = 0

    return {
        "status": "generated",
        "plan_id": plan.id,
        "title": plan.title,
        "action_count": action_count,
        "top_priority_score": plan.priority_score,
    }


@router.get("/plans/{client_id}")
def list_action_plans(client_id: int, status: Optional[str] = None, db: Session = Depends(get_db)):
    q = (
        db.query(ActionPlan)
        .filter(ActionPlan.client_id == client_id)
        .order_by(ActionPlan.created_at.desc())
    )
    if status:
        q = q.filter(ActionPlan.status == status)
    return q.all()


@router.get("/plans/{client_id}/latest")
def get_latest_plan(client_id: int, db: Session = Depends(get_db)):
    plan = (
        db.query(ActionPlan)
        .filter(ActionPlan.client_id == client_id, ActionPlan.status == "active")
        .order_by(ActionPlan.created_at.desc())
        .first()
    )
    if not plan:
        return {"status": "none", "message": "No active plan. Generate one first."}

    try:
        content = json.loads(plan.content) if plan.content else []
    except (json.JSONDecodeError, TypeError):
        content = []

    return {
        "id": plan.id,
        "title": plan.title,
        "content": content,
        "priority_score": plan.priority_score,
        "estimated_impact": plan.estimated_impact,
        "created_at": plan.created_at.isoformat(),
    }



# ── Content Briefs ────────────────────────────────────────────

class BriefStatusUpdate(BaseModel):
    status: str


def _safe_json_list(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


@router.post("/briefs/generate/{client_id}/{insight_id}")
def create_brief(client_id: int, insight_id: int, db: Session = Depends(get_db)):
    brief = generate_content_brief(client_id, insight_id, db)
    if not brief:
        return {"status": "skipped", "message": "AI not configured or generation failed."}
    return {
        "status": "generated",
        "brief_id": brief.id,
        "keyword": brief.keyword,
        "title_options": _safe_json_list(brief.title),
        "outline": _safe_json_list(brief.outline),
        "word_count": brief.word_count,
        "related_keywords": _safe_json_list(brief.related_keywords),
    }


@router.get("/briefs/{client_id}")
def list_briefs(client_id: int, db: Session = Depends(get_db)):
    briefs = (
        db.query(ContentBrief)
        .filter(ContentBrief.client_id == client_id)
        .order_by(ContentBrief.created_at.desc())
        .all()
    )
    out = []
    for b in briefs:
        out.append({
            "id": b.id,
            "client_id": b.client_id,
            "insight_id": b.insight_id,
            "keyword": b.keyword,
            "title": _safe_json_list(b.title),
            "outline": _safe_json_list(b.outline),
            "word_count": b.word_count,
            "related_keywords": _safe_json_list(b.related_keywords),
            "status": b.status,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })
    return out


@router.put("/briefs/{brief_id}/status")
def update_brief_status(brief_id: int, body: BriefStatusUpdate, db: Session = Depends(get_db)):
    brief = db.query(ContentBrief).filter(ContentBrief.id == brief_id).first()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    if body.status not in ("draft", "approved", "archived"):
        raise HTTPException(status_code=400, detail="Invalid status")
    brief.status = body.status
    db.commit()
    return {"ok": True, "id": brief.id, "status": brief.status}



