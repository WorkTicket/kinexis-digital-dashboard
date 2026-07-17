"""Portfolio today queue, benchmarking, health, AI value, known events."""
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client, Task, Insight, DataSource, ActionPlan
from app.impact_tracker import tasks_due_for_recheck, portfolio_impact_wins
from app.insight_scoring import score_insight, why_it_matters, effort_label
from app.portfolio_scoring import REVENUE_INSIGHT_TYPES, build_portfolio_benchmark
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["actions"])

# ── Portfolio Today queue ─────────────────────────────────────

@router.get("/today")
def portfolio_today(
    owner: Optional[str] = None,
    assignee: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Ranked cross-client next actions for the agency command center."""
    items: list[dict] = []
    today = date.today()
    stale_cutoff = utcnow() - timedelta(days=3)
    owner_q = (owner or "").strip().lower()
    assignee_q = (assignee or "").strip().lower()
    clients = {
        c.id: c
        for c in db.query(Client).filter((Client.archived == False) | (Client.archived.is_(None))).all()  # noqa: E712
    }
    if owner_q:
        clients = {
            cid: c
            for cid, c in clients.items()
            if ((c.owner or "").strip().lower() == owner_q)
            or (owner_q == "unassigned" and not (c.owner or "").strip())
        }
    seen_clients: set[int] = set()

    def client_name(cid: int) -> str:
        c = clients.get(cid)
        return c.name if c else f"Client {cid}"

    # 0) Success contracts behind target — highest commercial urgency
    from app.success_contract import evaluate_success_contract, parse_success_contract

    for client in clients.values():
        if not parse_success_contract(client):
            continue
        try:
            contract_eval = evaluate_success_contract(db, client)
        except Exception:
            continue
        if contract_eval.get("status") != "behind":
            continue
        prog = contract_eval.get("progress") or {}
        label = prog.get("label") or "KPI"
        ch = prog.get("change_pct")
        tgt = prog.get("target_delta_pct")
        detail = (
            f"{label} at {ch:+.0f}% vs +{tgt:.0f}% target"
            if ch is not None and tgt is not None
            else f"{label} is behind the success contract"
        )
        items.append({
            "id": f"contract-{client.id}",
            "kind": "contract_behind",
            "priority": 130,
            "client_id": client.id,
            "client_name": client.name,
            "title": f"Off contract: {label}",
            "detail": detail,
            "cta": "Open Detect",
            "cta_tab": "detect",
            "effort": "high",
        })
        seen_clients.add(client.id)

    # 1) Must-fix problems only (revenue leaks boosted) — opportunities stay off Today
    candidate_insights = (
        db.query(Insight)
        .filter(
            Insight.resolved == False,  # noqa: E712
            Insight.kind == "problem",
        )
        .order_by(Insight.priority_score.desc(), Insight.created_at.desc())
        .limit(80)
        .all()
    )
    for ins in candidate_insights:
        if ins.client_id not in clients:
            continue
        score = float(ins.priority_score if ins.priority_score is not None else score_insight(ins.severity, ins.type))
        if ins.severity != "high" and score < 70 and ins.type not in REVENUE_INSIGHT_TYPES:
            continue
        if ins.type in REVENUE_INSIGHT_TYPES:
            score += 20
        # Prefer one primary insight action per client in the focus queue
        if ins.client_id in seen_clients and ins.severity != "high":
            continue
        items.append({
            "id": f"insight-{ins.id}",
            "kind": "critical_insight" if ins.severity == "high" else "priority_insight",
            "priority": 100 + score,
            "client_id": ins.client_id,
            "client_name": client_name(ins.client_id),
            "title": why_it_matters(ins.type),
            "detail": (ins.message or "")[:200],
            "cta": "Open fix",
            "cta_tab": "prescribe",
            "insight_id": ins.id,
            "effort": effort_label(ins.type),
        })
        seen_clients.add(ins.client_id)

    # 2) Stuck / overdue tasks
    open_tasks = (
        db.query(Task)
        .filter(Task.status.in_(["open", "in_progress"]))
        .all()
    )
    for task in open_tasks:
        if task.client_id not in clients:
            continue
        if assignee_q:
            assigned = (task.assigned_to or "").strip().lower()
            if assignee_q == "unassigned":
                if assigned:
                    continue
            elif assigned != assignee_q:
                continue
        overdue = bool(task.due_date and task.due_date < today)
        stuck = (utcnow() - (task.created_at or utcnow())).days >= 7
        if not overdue and not stuck and task.status != "in_progress":
            continue
        pri = 90 if overdue else 70 if stuck else 60
        items.append({
            "id": f"task-{task.id}",
            "kind": "stuck_task",
            "priority": pri,
            "client_id": task.client_id,
            "client_name": client_name(task.client_id),
            "title": "Overdue work" if overdue else ("Stuck task" if stuck else "In-progress work"),
            "detail": (task.result_notes or f"Task #{task.id}")[:200],
            "cta": "Open work",
            "cta_tab": "execute",
            "task_id": task.id,
            "assigned_to": task.assigned_to or "",
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "effort": "medium",
        })

    # 3) Impact rechecks ready + pending-proof nags (done but never rechecked)
    window = 14
    try:
        from app.impact_tracker import get_impact_window_days
        window = get_impact_window_days(db)
    except Exception:
        pass
    due_ids = tasks_due_for_recheck(window)[:20]
    if due_ids:
        due_tasks = {
            t.id: t
            for t in db.query(Task).filter(Task.id.in_(due_ids)).all()
        }
        for task_id in due_ids:
            task = due_tasks.get(task_id)
            if not task:
                continue
            items.append({
                "id": f"recheck-{task_id}",
                "kind": "impact_recheck",
                "priority": 80,
                "client_id": task.client_id,
                "client_name": client_name(task.client_id),
                "title": "Impact recheck ready",
                "detail": (task.result_notes or f"Task #{task_id}")[:200],
                "cta": "Recheck impact",
                "cta_tab": "prove",
                "task_id": task_id,
                "effort": "low",
            })

    try:
        from app.proof_nag import find_pending_proof_tasks, find_stuck_proving_levers

        for pend in find_pending_proof_tasks(db)[:15]:
            if pend["client_id"] not in clients:
                continue
            items.append({
                "id": f"pending-proof-{pend['task_id']}",
                "kind": "pending_proof",
                "priority": 95,
                "client_id": pend["client_id"],
                "client_name": client_name(pend["client_id"]),
                "title": "Prove overdue — run recheck",
                "detail": (
                    f"Waiting {pend.get('days_waiting', 0)}d since baseline. "
                    f"{(pend.get('notes') or '')[:120]}"
                ),
                "cta": "Open Prove",
                "cta_tab": "prove",
                "task_id": pend["task_id"],
                "effort": "low",
            })
        for stuck in find_stuck_proving_levers(db)[:8]:
            if stuck["client_id"] not in clients:
                continue
            items.append({
                "id": f"stuck-lever-{stuck['lever_id']}",
                "kind": "pending_proof",
                "priority": 88,
                "client_id": stuck["client_id"],
                "client_name": stuck.get("client_name") or client_name(stuck["client_id"]),
                "title": "Lever stuck in proving",
                "detail": f"{stuck.get('title', 'Lever')} · {stuck.get('days_stuck', 0)}d",
                "cta": "Open Prove",
                "cta_tab": "prove",
                "effort": "medium",
            })
    except Exception as e:
        logger.warning("proof_nag today wiring failed: %s", e)

    # 3b) Capacity overload — owners with too much open/overdue work
    OWNER_OPEN_WARN = 8
    OWNER_OVERDUE_WARN = 2
    owner_load: dict[str, dict[str, int]] = {}
    for task in open_tasks:
        if task.client_id not in clients:
            continue
        owner = (clients[task.client_id].owner or "").strip() or "Unassigned"
        bucket = owner_load.setdefault(owner, {"open": 0, "overdue": 0})
        bucket["open"] += 1
        if task.due_date and task.due_date < today:
            bucket["overdue"] += 1
    for owner, load in owner_load.items():
        if load["open"] < OWNER_OPEN_WARN and load["overdue"] < OWNER_OVERDUE_WARN:
            continue
        # Attach to first client owned by this person for navigation
        owned = next(
            (
                c
                for c in clients.values()
                if ((c.owner or "").strip() or "Unassigned") == owner
            ),
            None,
        )
        if not owned:
            continue
        items.append({
            "id": f"capacity-{owner}",
            "kind": "capacity_overload",
            "priority": 85,
            "client_id": owned.id,
            "client_name": owned.name,
            "title": f"Capacity overload: {owner}",
            "detail": (
                f"{load['open']} open / {load['overdue']} overdue "
                f"(warn at {OWNER_OPEN_WARN} open or {OWNER_OVERDUE_WARN} overdue)"
            ),
            "cta": "Review Execute",
            "cta_tab": "execute",
            "effort": "high",
        })

    # 4) Stale syncs — one grouped query instead of per-client max()
    sync_by_client = {
        cid: ts
        for cid, ts in (
            db.query(DataSource.client_id, func.max(DataSource.last_synced_at))
            .filter(DataSource.client_id.in_(list(clients.keys())))
            .group_by(DataSource.client_id)
            .all()
        )
    } if clients else {}
    for client in clients.values():
        last_sync = sync_by_client.get(client.id)
        if last_sync is None or last_sync < stale_cutoff:
            items.append({
                "id": f"sync-{client.id}",
                "kind": "stale_sync",
                "priority": 50 if last_sync else 55,
                "client_id": client.id,
                "client_name": client.name,
                "title": "Data sync needed",
                "detail": (
                    "Never synced"
                    if not last_sync
                    else f"Last sync {last_sync.date().isoformat()}"
                ),
                "cta": "Sync",
                "cta_tab": "detect",
                "effort": "low",
            })

    items.sort(key=lambda x: -x["priority"])
    return {"generated_at": utcnow().isoformat(), "items": items[:40]}


# ── Benchmarking / Portfolio ──────────────────────────────────

@router.get("/benchmark")
def benchmark_clients(db: Session = Depends(get_db)):
    return build_portfolio_benchmark(db)


@router.get("/health/{client_id}")
def client_health_detail(client_id: int, db: Session = Depends(get_db)):
    """Return the authoritative health score for a single client (7d portfolio formula)."""
    from app.portfolio_scoring import build_client_health_detail

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    row = build_client_health_detail(db, client_id)
    if row:
        return row
    return {
        "client_id": client_id,
        "name": client.name,
        "health_score": None,
        "risk": "no_data",
        "risk_reasons": ["No data yet — sync connected sources to score health"],
        "pillars": None,
        "top_action": None,
    }


@router.get("/fix-effectiveness")
def fix_effectiveness(db: Session = Depends(get_db)):
    """Cross-client proven fix win rates by insight/playbook type (for ROI badges)."""
    from app.portfolio_scoring import cross_client_fix_effectiveness

    raw = cross_client_fix_effectiveness(db) or {}
    out = []
    for fix_type, stats in raw.items():
        total = int(stats.get("total") or 0)
        wins = int(stats.get("wins") or 0)
        out.append(
            {
                "fix_type": fix_type,
                "wins": wins,
                "total": total,
                "win_rate": round(wins / total, 3) if total else None,
                "median_lift_pct": stats.get("median_lift_pct"),
                "client_count": int(stats.get("client_count") or 0),
                "measured": total >= 3,
            }
        )
    out.sort(key=lambda r: (-(r["total"] or 0), -(r["win_rate"] or 0)))
    return {"fixes": out}


@router.get("/ai-value")
def ai_value_portfolio(db: Session = Depends(get_db)):
    """Cross-client ranking of AI recommendation value (adoption + attributed lift)."""
    from app.lever_service import portfolio_report_ready

    clients = db.query(Client).all()
    ready = portfolio_report_ready(db)
    try:
        wins = portfolio_impact_wins(days=30) or []
    except Exception:
        wins = []
    lift_by_client: dict[int, list[float]] = {}
    for w in wins or []:
        cid = w.get("client_id")
        if cid is None:
            continue
        lift_by_client.setdefault(cid, []).append(float(w.get("avg_primary_change") or 0))

    plan_counts = {}
    for row in db.query(ActionPlan.client_id, func.count(ActionPlan.id)).group_by(ActionPlan.client_id).all():
        plan_counts[row[0]] = row[1]

    task_from_plan = {}
    for row in (
        db.query(Task.client_id, func.count(Task.id))
        .filter(Task.action_plan_id.isnot(None))
        .group_by(Task.client_id)
        .all()
    ):
        task_from_plan[row[0]] = row[1]

    out = []
    for c in clients:
        if getattr(c, "archived", False):
            continue
        lifts = lift_by_client.get(c.id) or []
        avg_lift = sum(lifts) / len(lifts) if lifts else 0.0
        plans = int(plan_counts.get(c.id, 0) or 0)
        adopted = int(task_from_plan.get(c.id, 0) or 0)
        proven = int(ready.get(c.id, 0) or 0)
        score = round(plans * 8 + adopted * 15 + proven * 25 + max(avg_lift, 0) * 2, 1)
        out.append(
            {
                "client_id": c.id,
                "client_name": c.name,
                "plans_adopted": adopted,
                "plans_generated": plans,
                "attributed_lift_avg": round(avg_lift, 1),
                "proven_levers": proven,
                "ai_value_score": score,
            }
        )
    out.sort(key=lambda x: -x["ai_value_score"])
    return {"clients": out}


@router.post("/start-top-action/{client_id}")
def start_top_action(client_id: int, db: Session = Depends(get_db)):
    """One-click: Top Action → task + baseline + Cursor handoff payload.

    Creates/reactivates work from the client's current top_action, moves it to
    in_progress (captures Prove baseline), assigns Cursor, and resolves the insight.
    """
    from datetime import timedelta

    from app.impact_tracker import snapshot_task_metrics
    from app.portfolio_scoring import build_client_health_detail
    from app.routers.tasks import (
        _compute_fingerprint,
        _find_existing_task,
        _normalize_playbook_pattern,
        _resolve_playbook_from_insight_type,
    )

    client = (
        db.query(Client)
        .filter(Client.id == client_id, (Client.archived == False) | (Client.archived.is_(None)))  # noqa: E712
        .first()
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Stale sync gate — same rule as frontend assign
    last_sync = (
        db.query(func.max(DataSource.last_synced_at))
        .filter(DataSource.client_id == client_id)
        .scalar()
    )
    if last_sync and (utcnow() - last_sync).days >= 3:
        raise HTTPException(
            status_code=400,
            detail=f"Sync required before start — data is {(utcnow() - last_sync).days}d stale",
        )

    row = build_client_health_detail(db, client_id)
    top = (row or {}).get("top_action") or {}
    if not top:
        raise HTTPException(status_code=404, detail="No top action for this client")

    insight_id = top.get("insight_id")
    task_id = top.get("task_id")
    insight = None
    task = None

    if task_id:
        task = db.query(Task).filter(Task.id == task_id, Task.client_id == client_id).first()
    if not task and insight_id:
        insight = db.query(Insight).filter(Insight.id == insight_id, Insight.client_id == client_id).first()
        if insight:
            pattern = _normalize_playbook_pattern(
                _resolve_playbook_from_insight_type(insight.type or "")
            )
            fingerprint = _compute_fingerprint(
                client_id,
                pattern,
                insight.target_query,
                insight.target_url,
                insight.id,
            )
            task = _find_existing_task(db, client_id, fingerprint)
            if not task:
                notes = [
                    insight.recommended_action or (insight.message or "")[:200],
                    f"Severity: {insight.severity}",
                    "Prove: Success Contract KPI is primary when configured",
                ]
                task = Task(
                    client_id=client_id,
                    insight_id=insight.id,
                    assigned_to="Cursor",
                    result_notes="\n".join(notes),
                    playbook_pattern=pattern,
                    target_query=(insight.target_query or "")[:500] or None,
                    target_url=(insight.target_url or "")[:2000] or None,
                    fingerprint=fingerprint,
                    status="open",
                    due_date=date.today() + timedelta(days=7),
                )
                db.add(task)
                db.flush()

    if not task:
        # Score-driven play without insight — create a growth task
        playbook = top.get("playbook") or "growth_play"
        pattern = _normalize_playbook_pattern(str(playbook))
        fingerprint = _compute_fingerprint(client_id, pattern, None, None, None)
        task = _find_existing_task(db, client_id, fingerprint)
        if not task:
            task = Task(
                client_id=client_id,
                assigned_to="Cursor",
                result_notes=f"{top.get('title') or 'Growth play'}\n{top.get('detail') or ''}",
                playbook_pattern=pattern,
                fingerprint=fingerprint,
                status="open",
                due_date=date.today() + timedelta(days=7),
            )
            db.add(task)
            db.flush()

    prev_status = task.status
    task.assigned_to = task.assigned_to or "Cursor"
    if not (task.assigned_to or "").strip():
        task.assigned_to = "Cursor"
    if task.assigned_to == "Unassigned":
        task.assigned_to = "Cursor"
    task.status = "in_progress"
    if not task.due_date:
        task.due_date = date.today() + timedelta(days=7)

    if task.insight_id:
        insight = insight or db.query(Insight).filter(Insight.id == task.insight_id).first()
        if insight:
            insight.resolved = True

    try:
        from app import recommendation_service

        recommendation_service.accept_for_task(db, task)
    except Exception as e:
        logger.warning("recommendation accept failed on start-top-action: %s", e)

    db.commit()
    db.refresh(task)

    if prev_status != "in_progress":
        try:
            snapshot_task_metrics(task.id)
        except Exception as e:
            logger.warning("baseline snapshot failed for task %s: %s", task.id, e)

    return {
        "ok": True,
        "task_id": task.id,
        "client_id": client_id,
        "insight_id": task.insight_id,
        "assigned_to": task.assigned_to,
        "status": task.status,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "cta_tab": "execute",
        "title": top.get("title") or (task.result_notes or "")[:120],
        "detail": top.get("detail") or "",
        "open_cursor": True,
        "result_notes": task.result_notes,
        "target_query": task.target_query,
        "target_url": task.target_url,
        "playbook_pattern": task.playbook_pattern,
    }


@router.get("/known-events/{client_id}")
def known_events(client_id: int, db: Session = Depends(get_db)):
    """Return known events (core updates, seasonal) overlapping the client's data range."""
    from app.known_events import events_touching
    from app.models import MetricDaily

    last_date = (
        db.query(func.max(MetricDaily.date))
        .filter(MetricDaily.client_id == client_id)
        .scalar()
    )
    first_date = (
        db.query(func.min(MetricDaily.date))
        .filter(MetricDaily.client_id == client_id)
        .scalar()
    )

    if not first_date or not last_date:
        return {"client_id": client_id, "events": []}

    if isinstance(first_date, str):
        first_date = date.fromisoformat(first_date)
    if isinstance(last_date, str):
        last_date = date.fromisoformat(last_date)

    touching = events_touching(first_date, last_date)
    events_out = []
    for e in touching:
        start = e.get("start")
        end = e.get("end")
        events_out.append({
            "name": e.get("name", ""),
            "start": start.isoformat() if isinstance(start, date) else (str(start) if start else None),
            "end": end.isoformat() if isinstance(end, date) else (str(end) if end else None),
            "type": e.get("type", "unknown"),
        })
    return {"client_id": client_id, "events": events_out}

