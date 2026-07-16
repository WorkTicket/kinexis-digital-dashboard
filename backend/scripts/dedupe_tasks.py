"""One-shot: close duplicate open tasks across all clients, keeping lowest id per fingerprint.

Run: python -m scripts.dedupe_tasks
"""

import hashlib
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import Task
from app.action_candidates import compute_task_fingerprint

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = ("open", "in_progress")


def _fingerprint(t: Task) -> str:
    return compute_task_fingerprint(
        client_id=t.client_id,
        playbook_pattern=t.playbook_pattern or "",
        target_query=t.target_query,
        target_url=t.target_url,
        insight_id=t.insight_id,
    )


def dedupe_all():
    db = SessionLocal()
    try:
        tasks = (
            db.query(Task)
            .filter(Task.status.in_(_ACTIVE_STATUSES))
            .order_by(Task.client_id, Task.id)
            .all()
        )

        seen: dict[str, Task] = {}
        closed = 0

        for t in tasks:
            fp = _fingerprint(t)
            if not fp:
                continue
            existing = seen.get(fp)
            if existing and existing.client_id == t.client_id:
                # Keep lowest id, close the other
                if t.id < existing.id:
                    # Swap: current is the keeper, close the previously seen
                    existing.status = "skipped"
                    existing.result_notes = (existing.result_notes or "") + f"\n\nAuto-closed: duplicate of task {t.id}"
                    seen[fp] = t
                else:
                    t.status = "skipped"
                    t.result_notes = (t.result_notes or "") + f"\n\nAuto-closed: duplicate of task {existing.id}"
                closed += 1
                logger.info("Closed duplicate task %s (kept %s) fp=%s", t.id, existing.id, fp)
            else:
                seen[fp] = t

        db.commit()
        logger.info("Done: closed %s duplicate tasks across all clients", closed)
    finally:
        db.close()


if __name__ == "__main__":
    dedupe_all()
