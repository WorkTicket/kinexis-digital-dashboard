"""Growth Lever Thread — spine binding Detect → Prescribe → Execute → Prove → Report."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.funnel_analyzer import analyze_funnel
from app.models import GrowthLeverThread, Insight, Task, ContentBrief, Client
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

STATUSES = (
    "detected",
    "prescribed",
    "in_progress",
    "proving",
    "proven",
    "dismissed",
)

STATUS_ORDER = {s: i for i, s in enumerate(STATUSES)}


def _thread_to_dict(t: GrowthLeverThread) -> dict:
    insight_ids: list[int] = []
    if t.source_insight_ids:
        try:
            insight_ids = json.loads(t.source_insight_ids)
        except (json.JSONDecodeError, TypeError):
            insight_ids = []
    return {
        "id": t.id,
        "client_id": t.client_id,
        "status": t.status,
        "title": t.title,
        "stage": t.stage,
        "cause": t.cause,
        "fix": t.fix,
        "impact_score": t.impact_score,
        "source_insight_ids": insight_ids,
        "task_id": t.task_id,
        "brief_id": t.brief_id,
        "impact_summary": t.impact_summary,
        "confidence_label": t.confidence_label,
        "include_in_report": bool(t.include_in_report),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
    }


def list_levers(
    db: Session,
    client_id: int,
    *,
    include_dismissed: bool = False,
) -> list[dict]:
    q = db.query(GrowthLeverThread).filter(GrowthLeverThread.client_id == client_id)
    if not include_dismissed:
        q = q.filter(GrowthLeverThread.status != "dismissed")
    rows = q.order_by(GrowthLeverThread.impact_score.desc(), GrowthLeverThread.id.desc()).all()
    return [_thread_to_dict(t) for t in rows]


def get_lever(db: Session, lever_id: int) -> Optional[dict]:
    t = db.query(GrowthLeverThread).filter(GrowthLeverThread.id == lever_id).first()
    return _thread_to_dict(t) if t else None


def synthesize_levers_for_client(db: Session, client_id: int) -> list[dict]:
    """
    Create/update the primary growth lever from funnel analysis + top insights.
    Idempotent: refreshes the open 'detected'/'prescribed' primary thread.
    """
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return []

    funnel = analyze_funnel(client_id, db=db)
    growth = funnel.get("growth_lever") or {}
    biggest = funnel.get("biggest_leak") or {}

    title = (
        (growth.get("title") if isinstance(growth, dict) else None)
        or (f"Improve {biggest.get('stage')}" if biggest.get("stage") else None)
    )
    if not title:
        # Fall back to top open insight
        top = (
            db.query(Insight)
            .filter(Insight.client_id == client_id, Insight.resolved == False)  # noqa: E712
            .order_by(Insight.priority_score.desc())
            .first()
        )
        if not top:
            return list_levers(db, client_id)
        # Prefer concrete recommended_action first line as title when it names a page
        action = (top.recommended_action or "").strip()
        first_line = action.split("\n")[0].strip() if action else ""
        if first_line.lower().startswith("on http") or len(first_line) > 20:
            title = first_line[:240]
        else:
            title = (top.message or "Top opportunity")[:240]
        cause = top.message
        fix = top.recommended_action
        plain = None
        stage = top.type
        score = float(top.priority_score or 50)
        insight_ids = [top.id]
    else:
        cause = (growth.get("cause") if isinstance(growth, dict) else None) or (
            f"{biggest.get('dropoff')}% drop-off" if biggest.get("dropoff") is not None else None
        )
        fix = growth.get("fix") if isinstance(growth, dict) else None
        plain = growth.get("plain_english") if isinstance(growth, dict) else None
        stage = (growth.get("stage") if isinstance(growth, dict) else None) or biggest.get("stage")
        score = float(growth.get("leak_pct") or biggest.get("dropoff") or 50)
        top_insights = (
            db.query(Insight)
            .filter(Insight.client_id == client_id, Insight.resolved == False)  # noqa: E712
            .order_by(Insight.priority_score.desc())
            .limit(5)
            .all()
        )
        insight_ids = [i.id for i in top_insights]
        # Prefer a concrete insight title/fix when funnel leak is still generic
        if top_insights and (not fix or "Open Prescribe" in (fix or "")):
            ins = top_insights[0]
            if ins.recommended_action:
                fix = ins.recommended_action
            if ins.message and (not cause or "SERP/ad creative" in (cause or "")):
                cause = ins.message

    # Also create secondary threads from high-impact insights not already linked
    active = (
        db.query(GrowthLeverThread)
        .filter(
            GrowthLeverThread.client_id == client_id,
            GrowthLeverThread.status.notin_(["dismissed", "proven"]),
        )
        .all()
    )
    primary = next((t for t in active if t.stage == stage or t.title == title), None)
    if not primary and active:
        primary = active[0]

    now = utcnow()
    # Store plain-english + fix together so Execute shows how to act
    if plain and fix and plain not in (fix or ""):
        fix_blob = f"What this means: {plain}\n\nHow to fix:\n{fix}"
    elif plain and not fix:
        fix_blob = f"What this means: {plain}"
    else:
        fix_blob = fix

    if primary:
        primary.title = title[:500]
        primary.stage = (stage or primary.stage or "")[:100]
        primary.cause = cause
        primary.fix = fix_blob
        primary.impact_score = score
        primary.source_insight_ids = json.dumps(insight_ids)
        primary.updated_at = now
        if primary.status == "detected" and fix_blob:
            pass  # stay detected until prescribed
    else:
        primary = GrowthLeverThread(
            client_id=client_id,
            status="detected",
            title=title[:500],
            stage=(stage or "")[:100],
            cause=cause,
            fix=fix_blob,
            impact_score=score,
            source_insight_ids=json.dumps(insight_ids),
            created_at=now,
            updated_at=now,
        )
        db.add(primary)

    # Secondary narrative levers from top insights (cap 3 total open)
    closed = (
        db.query(GrowthLeverThread)
        .filter(
            GrowthLeverThread.client_id == client_id,
            GrowthLeverThread.status.in_(["dismissed", "proven"]),
        )
        .all()
    )
    existing_titles = {t.title for t in active}
    existing_titles.update(t.title for t in closed)
    existing_titles.add(primary.title)
    open_count = len([t for t in active if t.status not in ("dismissed", "proven")]) + (
        0 if primary in active else 1
    )
    top_extra = (
        db.query(Insight)
        .filter(Insight.client_id == client_id, Insight.resolved == False)  # noqa: E712
        .order_by(Insight.priority_score.desc())
        .limit(8)
        .all()
    )
    for ins in top_extra:
        if open_count >= 3:
            break
        action = (ins.recommended_action or "").strip()
        first_line = action.split("\n")[0].strip() if action else ""
        if first_line.lower().startswith("on http"):
            t_title = first_line[:500]
        elif action and "\n" in action:
            t_title = (ins.message or action)[:500]
        else:
            t_title = (ins.message or action or "Opportunity")[:500]
        if t_title in existing_titles:
            continue
        if ins.id in insight_ids and primary.title == title:
            continue
        thread = GrowthLeverThread(
            client_id=client_id,
            status="detected",
            title=t_title,
            stage=(ins.type or "")[:100],
            cause=ins.message,
            fix=ins.recommended_action,
            impact_score=float(ins.priority_score or 40),
            source_insight_ids=json.dumps([ins.id]),
            created_at=now,
            updated_at=now,
        )
        db.add(thread)
        existing_titles.add(t_title)
        open_count += 1

    db.commit()
    return list_levers(db, client_id)


def advance_status(
    db: Session,
    lever_id: int,
    status: str,
    *,
    task_id: Optional[int] = None,
    brief_id: Optional[int] = None,
    impact_summary: Optional[str] = None,
    confidence_label: Optional[str] = None,
    include_in_report: Optional[bool] = None,
) -> dict:
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")
    t = db.query(GrowthLeverThread).filter(GrowthLeverThread.id == lever_id).first()
    if not t:
        raise LookupError("Lever not found")
    t.status = status
    t.updated_at = utcnow()
    if task_id is not None:
        t.task_id = task_id
    if brief_id is not None:
        t.brief_id = brief_id
    if impact_summary is not None:
        t.impact_summary = impact_summary
    if confidence_label is not None:
        t.confidence_label = confidence_label
    if include_in_report is not None:
        t.include_in_report = include_in_report
    if status in ("proven", "dismissed"):
        t.resolved_at = utcnow()
        if status == "proven" and include_in_report is None:
            t.include_in_report = True
    db.commit()
    db.refresh(t)
    return _thread_to_dict(t)


def link_task(db: Session, lever_id: int, task_id: int) -> dict:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise LookupError("Task not found")
    t = db.query(GrowthLeverThread).filter(GrowthLeverThread.id == lever_id).first()
    if not t:
        raise LookupError("Lever not found")
    t.task_id = task_id
    if hasattr(task, "lever_id"):
        task.lever_id = lever_id
    status = "in_progress" if task.status in ("open", "in_progress") else "detected"
    if task.status == "skipped":
        status = "detected"
    if task.status == "done":
        status = "proving"
    return advance_status(db, lever_id, status, task_id=task_id)


def link_brief(db: Session, lever_id: int, brief_id: int) -> dict:
    brief = db.query(ContentBrief).filter(ContentBrief.id == brief_id).first()
    if not brief:
        raise LookupError("Brief not found")
    return advance_status(db, lever_id, "prescribed", brief_id=brief_id)


def sync_from_task(db: Session, task: Task) -> None:
    """When a task linked to a lever changes status, advance the thread."""
    lever_id = getattr(task, "lever_id", None)
    if not lever_id and task.id:
        linked = (
            db.query(GrowthLeverThread)
            .filter(GrowthLeverThread.task_id == task.id)
            .first()
        )
        if linked:
            lever_id = linked.id
    if not lever_id:
        return
    if task.status == "skipped":
        return
    if task.status == "done":
        advance_status(db, lever_id, "proving", task_id=task.id)
    elif task.status in ("open", "in_progress"):
        advance_status(db, lever_id, "in_progress", task_id=task.id)


def maybe_mark_proven_from_task(
    db: Session,
    task: Task,
    *,
    impact_summary: Optional[str] = None,
    confidence_label: Optional[str] = None,
) -> Optional[dict]:
    """Advance linked lever proving → proven after a successful win recheck."""
    lever = None
    lever_id = getattr(task, "lever_id", None)
    if lever_id:
        lever = db.query(GrowthLeverThread).filter(GrowthLeverThread.id == lever_id).first()
    if not lever and task.id:
        lever = (
            db.query(GrowthLeverThread)
            .filter(GrowthLeverThread.task_id == task.id)
            .first()
        )
    if not lever or lever.status != "proving":
        return None
    return advance_status(
        db,
        lever.id,
        "proven",
        task_id=task.id,
        impact_summary=impact_summary,
        confidence_label=confidence_label,
        include_in_report=True,
    )


def portfolio_report_ready(db: Session) -> dict[int, int]:
    """client_id → count of proven levers ready for report."""
    rows = (
        db.query(GrowthLeverThread)
        .filter(
            GrowthLeverThread.status == "proven",
            GrowthLeverThread.include_in_report == True,  # noqa: E712
        )
        .all()
    )
    counts: dict[int, int] = {}
    for r in rows:
        counts[r.client_id] = counts.get(r.client_id, 0) + 1
    return counts


def proven_levers_for_report(db: Session, client_id: int) -> list[dict]:
    rows = (
        db.query(GrowthLeverThread)
        .filter(
            GrowthLeverThread.client_id == client_id,
            GrowthLeverThread.status == "proven",
            GrowthLeverThread.include_in_report == True,  # noqa: E712
        )
        .order_by(GrowthLeverThread.resolved_at.desc())
        .all()
    )
    return [_thread_to_dict(t) for t in rows]
