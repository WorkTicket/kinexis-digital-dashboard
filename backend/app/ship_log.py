"""
Parse agent ship-log markdown (filled handoff YAML blocks) and close the
Detect → Execute → Prove loop: create/update tasks, capture baselines.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.impact_tracker import snapshot_task_metrics
from app.models import Insight, Task

# Match ```yaml ... ``` or bare YAML blocks that start with fix_id:
_FENCE_RE = re.compile(r"```(?:ya?ml)?\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
_FIX_ID_RE = re.compile(r"^fix_id:\s*(\d+)\s*$", re.MULTILINE)


def _parse_simple_yaml(block: str) -> dict[str, str]:
    """
    Minimal YAML-ish parser for handoff blocks.
    Supports key: value and key: | multiline literals.
    """
    out: dict[str, str] = {}
    lines = block.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2)
        if rest.strip() == "|":
            # Multiline block: indent deeper than key
            i += 1
            buf: list[str] = []
            while i < len(lines):
                nxt = lines[i]
                if nxt.startswith("  ") or nxt.startswith("\t") or nxt.strip() == "":
                    buf.append(nxt[2:] if nxt.startswith("  ") else nxt.lstrip("\t"))
                    i += 1
                    continue
                if re.match(r"^[A-Za-z0-9_]+:", nxt):
                    break
                buf.append(nxt)
                i += 1
            # Trim trailing empty
            while buf and not buf[-1].strip():
                buf.pop()
            out[key] = "\n".join(buf).strip()
            continue
        out[key] = rest.strip().strip("\"'")
        i += 1
    return out


def extract_handoff_blocks(markdown: str) -> list[dict[str, str]]:
    """Extract filled handoff dicts that include a fix_id."""
    text = markdown or ""
    blocks: list[str] = []
    for m in _FENCE_RE.finditer(text):
        body = m.group(1)
        if "fix_id:" in body:
            blocks.append(body)
    # Also accept unfenced sections between --- handoff markers
    if not blocks and "fix_id:" in text:
        # Split on fix_id occurrences
        parts = re.split(r"(?=^fix_id:\s*\d+)", text, flags=re.MULTILINE)
        for part in parts:
            if _FIX_ID_RE.search(part):
                # Cap each part to ~40 lines so we don't swallow the whole doc
                clipped = "\n".join(part.split("\n")[:40])
                blocks.append(clipped)

    parsed: list[dict[str, str]] = []
    for block in blocks:
        data = _parse_simple_yaml(block)
        if data.get("fix_id") and str(data["fix_id"]).isdigit():
            parsed.append(data)
    return parsed


def apply_ship_log(
    db: Session,
    client_id: int,
    markdown: str,
    *,
    mark_done: bool = True,
    assigned_to: Optional[str] = None,
) -> dict[str, Any]:
    """
    Apply a filled agent brief / ship-log:
    - Find insight by fix_id
    - Create or update linked Task
    - Set result_notes from changes_made + day0_baseline
    - Capture ImpactSnapshot baseline
    """
    blocks = extract_handoff_blocks(markdown)
    if not blocks:
        return {
            "status": "error",
            "message": "No handoff blocks with fix_id found. Paste the filled YAML handoff section(s).",
            "applied": [],
        }

    applied: list[dict[str, Any]] = []
    errors: list[str] = []

    for data in blocks:
        fix_id = int(data["fix_id"])
        insight = (
            db.query(Insight)
            .filter(Insight.id == fix_id, Insight.client_id == client_id)
            .first()
        )
        if not insight:
            errors.append(f"fix_id {fix_id}: insight not found for this client")
            continue

        changes = (data.get("changes_made") or "").strip()
        day0 = (data.get("day0_baseline") or "").strip()
        notes_parts = []
        if changes and changes.lower() not in ("", "(agent fills)", "tbd", "n/a"):
            notes_parts.append(f"Ship log — changes:\n{changes}")
        if day0 and day0.lower() not in ("", "(agent fills)", "tbd", "n/a"):
            notes_parts.append(f"Day-0 baseline notes:\n{day0}")
        if data.get("title"):
            notes_parts.insert(0, f"Fix: {data['title']}")
        if data.get("urls") or data.get("resolved_urls") or data.get("paths"):
            targets = data.get("resolved_urls") or data.get("urls") or data.get("paths")
            notes_parts.append(f"Targets: {targets}")
        result_notes = "\n\n".join(notes_parts).strip() or (
            f"Imported from agent ship-log for insight #{fix_id}"
        )

        task = (
            db.query(Task)
            .filter(Task.client_id == client_id, Task.insight_id == fix_id)
            .order_by(Task.id.desc())
            .first()
        )
        created = False
        if not task:
            from app.routers.tasks import _resolve_playbook_from_insight_type
            task = Task(
                client_id=client_id,
                insight_id=fix_id,
                status="open",
                assigned_to=assigned_to,
                playbook_pattern=_resolve_playbook_from_insight_type(insight.type or ""),
            )
            db.add(task)
            db.flush()
            created = True

        task.result_notes = result_notes
        if assigned_to and not task.assigned_to:
            task.assigned_to = assigned_to
        if not task.playbook_pattern:
            from app.routers.tasks import _resolve_playbook_from_insight_type
            task.playbook_pattern = _resolve_playbook_from_insight_type(insight.type or data.get("type", ""))
        # Due date from recheck_at if present (Day N)
        recheck = (data.get("recheck_at") or "").strip()
        day_m = re.search(r"(\d+)", recheck)
        if day_m and not task.due_date:
            try:
                task.due_date = date.today() + timedelta(days=int(day_m.group(1)))
            except ValueError:
                pass

        status_before = task.status
        if mark_done:
            task.status = "done"
        elif task.status == "open":
            task.status = "in_progress"

        # Resolve insight when shipping as done
        if mark_done and not insight.resolved:
            insight.resolved = True
            insight.resolve_reason = "shipped"

        db.commit()
        db.refresh(task)

        snaps = snapshot_task_metrics(task.id)

        applied.append({
            "fix_id": fix_id,
            "task_id": task.id,
            "created": created,
            "status_before": status_before,
            "status": task.status,
            "baselines_captured": len(snaps),
            "title": data.get("title") or insight.message[:80],
        })

    return {
        "status": "ok" if applied else "error",
        "message": (
            f"Applied {len(applied)} ship-log item(s)."
            if applied
            else "No ship-log items could be applied."
        ),
        "applied": applied,
        "errors": errors,
    }
