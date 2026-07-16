import hashlib
from datetime import date as date_type, datetime
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, field_validator

from app.database import get_db
from app.models import Task, Insight, Client
from app.impact_tracker import snapshot_task_metrics

router = APIRouter(prefix="/tasks", tags=["tasks"])

logger = logging.getLogger(__name__)

_TASK_STATUSES = frozenset({"open", "in_progress", "done", "skipped"})
TaskStatusFilter = Literal["open", "in_progress", "done", "skipped"]

_ACTIVE_STATUSES = frozenset({"open", "in_progress"})
_DEDUPE_STATUSES = frozenset({"open", "in_progress", "done"})


def _normalize_playbook_pattern(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()[:100]
    return cleaned or None


def _resolve_playbook_from_insight_type(insight_type: str) -> str:
    """Map insight type to canonical playbook pattern (consistent with action_candidates.ALLOWED_PLAYBOOKS).
    
    Without this, tasks created directly from insights use the raw insight type
    (e.g. 'zero_click_alert') while action plan tasks use the canonical pattern
    (e.g. 'ctr_gap'), producing mismatched fingerprints that break dedupe.
    """
    from app.action_candidates import ALLOWED_PLAYBOOKS
    mapping = ALLOWED_PLAYBOOKS.get(insight_type)
    if mapping:
        return mapping[0]  # (playbook_pattern, assignee, success_metric, metrics)
    return insight_type


def _compute_fingerprint(
    client_id: int,
    playbook_pattern: Optional[str],
    target_query: Optional[str] = None,
    target_url: Optional[str] = None,
    insight_id: Optional[int] = None,
) -> str:
    """Deterministic dedupe key — delegates to canonical implementation in action_candidates."""
    from app.action_candidates import compute_task_fingerprint

    return compute_task_fingerprint(
        client_id=client_id,
        playbook_pattern=playbook_pattern or "",
        target_query=target_query,
        target_url=target_url,
        insight_id=insight_id,
    )


def _find_existing_task(
    db: Session,
    client_id: int,
    fingerprint: str,
) -> Optional[Task]:
    return (
        db.query(Task)
        .filter(
            Task.client_id == client_id,
            Task.fingerprint == fingerprint,
            Task.status.in_(_DEDUPE_STATUSES),
        )
        .first()
    )


class TaskCreate(BaseModel):
    client_id: int
    insight_id: Optional[int] = None
    assigned_to: str = ""
    due_date: Optional[date_type] = None
    result_notes: Optional[str] = None
    brief_id: Optional[int] = None
    lever_id: Optional[int] = None
    playbook_pattern: Optional[str] = None
    action_plan_id: Optional[int] = None
    target_query: Optional[str] = None
    target_url: Optional[str] = None


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[date_type] = None
    result_notes: Optional[str] = None
    brief_id: Optional[int] = None
    lever_id: Optional[int] = None
    playbook_pattern: Optional[str] = None
    action_plan_id: Optional[int] = None
    target_query: Optional[str] = None
    target_url: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in _TASK_STATUSES:
            raise ValueError("status must be open, in_progress, done, or skipped")
        return v


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    insight_id: Optional[int] = None
    assigned_to: str
    status: str
    due_date: Optional[date_type] = None
    result_notes: Optional[str] = None
    impact_outcome: Optional[str] = None
    brief_id: Optional[int] = None
    lever_id: Optional[int] = None
    playbook_pattern: Optional[str] = None
    action_plan_id: Optional[int] = None
    target_query: Optional[str] = None
    target_url: Optional[str] = None
    fingerprint: Optional[str] = None
    created_at: datetime


@router.get("/", response_model=list[TaskResponse])
def list_tasks(
    response: Response,
    client_id: Optional[int] = Query(None),
    status: Optional[TaskStatusFilter] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Task).order_by(Task.created_at.desc())
    if client_id is not None:
        q = q.filter(Task.client_id == client_id)
    if status is not None:
        if status not in _TASK_STATUSES:
            raise HTTPException(
                status_code=400,
                detail="status must be open, in_progress, done, or skipped",
            )
        q = q.filter(Task.status == status)
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Has-More"] = "1" if offset + len(rows) < total else "0"
    return rows


@router.post("/", response_model=TaskResponse)
def create_task(data: TaskCreate, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == data.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    pattern = _normalize_playbook_pattern(data.playbook_pattern)
    if not pattern and data.insight_id:
        insight = db.query(Insight).filter(Insight.id == data.insight_id).first()
        if insight:
            pattern = _normalize_playbook_pattern(_resolve_playbook_from_insight_type(insight.type or ""))

    fingerprint = _compute_fingerprint(
        data.client_id, pattern, data.target_query, data.target_url, data.insight_id
    )

    existing = _find_existing_task(db, data.client_id, fingerprint)
    if existing:
        logger.info(
            "Dedupe hit: returning existing task %s for fingerprint %s",
            existing.id, fingerprint,
        )
        return existing

    task = Task(
        client_id=data.client_id,
        insight_id=data.insight_id,
        assigned_to=data.assigned_to,
        due_date=data.due_date,
        result_notes=data.result_notes,
        brief_id=data.brief_id,
        lever_id=data.lever_id,
        playbook_pattern=pattern,
        action_plan_id=data.action_plan_id,
        target_query=(data.target_query or "").strip()[:500] or None,
        target_url=(data.target_url or "").strip()[:2000] or None,
        fingerprint=fingerprint,
        status="open",
    )
    db.add(task)
    db.flush()
    if data.lever_id:
        try:
            from app import lever_service

            lever_service.link_task(db, data.lever_id, task.id)
        except Exception as e:
            logger.warning("lever_service.link_task failed for lever=%s task=%s: %s", data.lever_id, task.id, e)
    try:
        from app import recommendation_service

        recommendation_service.accept_for_task(db, task)
    except Exception as e:
        logger.warning("recommendation accept failed for task create: %s", e)
    db.commit()
    db.refresh(task)
    return task


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, data: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = data.model_dump(exclude_unset=True)
    prev_status = task.status
    if "playbook_pattern" in update_data:
        update_data["playbook_pattern"] = _normalize_playbook_pattern(
            update_data.get("playbook_pattern")
        )
    for key, val in update_data.items():
        if key in ("target_query", "target_url") and val is not None:
            val = str(val).strip()[:2000] or None
        setattr(task, key, val)

    # Backfill pattern from linked insight when still empty
    if not (task.playbook_pattern or "").strip() and task.insight_id:
        insight = db.query(Insight).filter(Insight.id == task.insight_id).first()
        if insight and insight.type:
            task.playbook_pattern = _normalize_playbook_pattern(_resolve_playbook_from_insight_type(insight.type))

    # Recompute fingerprint when key fields changed
    if "playbook_pattern" in update_data or "target_query" in update_data or "target_url" in update_data:
        task.fingerprint = _compute_fingerprint(
            task.client_id, task.playbook_pattern, task.target_query, task.target_url, task.insight_id
        )

    if update_data.get("status") == "done" and task.insight_id:
        insight = db.query(Insight).filter(Insight.id == task.insight_id).first()
        if insight:
            insight.resolved = True

    db.commit()
    db.refresh(task)

    new_status = update_data.get("status")
    if new_status == "in_progress" and prev_status != "in_progress":
        snapshot_task_metrics(task_id)
    elif new_status == "done":
        snapshot_task_metrics(task_id)

    if "status" in update_data:
        try:
            from app import lever_service

            lever_service.sync_from_task(db, task)
        except Exception as e:
            logger.warning("lever_service.sync_from_task failed for task=%s: %s", task_id, e)
        try:
            from app import recommendation_service

            recommendation_service.sync_from_task(db, task)
            db.commit()
        except Exception as e:
            logger.warning("recommendation sync_from_task failed for task=%s: %s", task_id, e)

    return task


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"ok": True}


@router.post("/dedupe-cleanup")
def dedupe_cleanup(client_id: int, db: Session = Depends(get_db)):
    """One-shot cleanup: close duplicate open tasks, keeping lowest id per fingerprint."""
    from sqlalchemy import func

    subq = (
        db.query(
            Task.fingerprint,
            func.min(Task.id).label("keep_id"),
        )
        .filter(
            Task.client_id == client_id,
            Task.fingerprint.isnot(None),
            Task.fingerprint != "",
            Task.status.in_(_ACTIVE_STATUSES),
        )
        .group_by(Task.fingerprint)
        .having(func.count(Task.id) > 1)
        .subquery()
    )
    dups = (
        db.query(Task)
        .filter(
            Task.client_id == client_id,
            Task.fingerprint.isnot(None),
            Task.fingerprint != "",
            Task.status.in_(_ACTIVE_STATUSES),
            Task.id.notin_(db.query(subq.c.keep_id)),
        )
        .all()
    )
    count = len(dups)
    for t in dups:
        t.status = "skipped"
        t.result_notes = (t.result_notes or "") + "\n\nAuto-closed: duplicate of fingerprint " + str(t.fingerprint)
    db.commit()
    return {"closed": count}
