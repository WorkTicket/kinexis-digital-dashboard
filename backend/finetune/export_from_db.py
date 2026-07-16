"""
Optional: export real ActionPlan / WeeklySummary / ContentBrief rows from the
Kinexis SQLite DB into SFT JSONL (append to synthetic data).

Usage (from backend/, with app importable):
  py -3.12 -m finetune.export_from_db --out finetune/data/from_db.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python export_from_db.py` from finetune/ or `-m` from backend/
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.action_planner import SYSTEM_PROMPT as ACTION_SYSTEM  # noqa: E402
from app.ai_summarizer import SYSTEM_PROMPT as WEEKLY_SYSTEM  # noqa: E402
from app.content_brief import BRIEF_PROMPT  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.marketing_knowledge import with_marketing_knowledge  # noqa: E402
from app.models import ActionPlan, Client, ContentBrief, WeeklySummary  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "data" / "from_db.jsonl")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    db = SessionLocal()
    rows: list[dict] = []
    try:
        plans = db.query(ActionPlan).order_by(ActionPlan.id.desc()).limit(args.limit).all()
        for plan in plans:
            client = db.query(Client).filter(Client.id == plan.client_id).first()
            try:
                content = json.loads(plan.content or "[]")
            except json.JSONDecodeError:
                continue
            if not content:
                continue
            name = client.name if client else f"client-{plan.client_id}"
            rows.append(
                {
                    "task": "action_plan",
                    "pattern": "from_db",
                    "source_id": plan.id,
                    "messages": [
                        {"role": "system", "content": with_marketing_knowledge(ACTION_SYSTEM)},
                        {
                            "role": "user",
                            "content": (
                                f"Client: {name}\n"
                                f"Regenerate a prioritized action plan equivalent to the approved agency plan.\n"
                                f"Title: {plan.title}\n"
                                "Output the JSON action array only."
                            ),
                        },
                        {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)},
                    ],
                }
            )

        summaries = (
            db.query(WeeklySummary).order_by(WeeklySummary.id.desc()).limit(args.limit).all()
        )
        for s in summaries:
            client = db.query(Client).filter(Client.id == s.client_id).first()
            raw = (s.content or "").strip()
            if not raw.startswith("{"):
                continue
            name = client.name if client else f"client-{s.client_id}"
            rows.append(
                {
                    "task": "weekly_brief",
                    "pattern": "from_db",
                    "source_id": s.id,
                    "messages": [
                        {"role": "system", "content": with_marketing_knowledge(WEEKLY_SYSTEM)},
                        {
                            "role": "user",
                            "content": f"Write the weekly brief JSON for {name} based on approved agency output.",
                        },
                        {"role": "assistant", "content": raw},
                    ],
                }
            )

        briefs = db.query(ContentBrief).order_by(ContentBrief.id.desc()).limit(args.limit).all()
        for b in briefs:
            client = db.query(Client).filter(Client.id == b.client_id).first()
            # ContentBrief stores fields across columns; rebuild a JSON target if outline exists
            outline = b.outline
            try:
                outline_parsed = json.loads(outline) if outline and outline.strip().startswith("[") else outline
            except json.JSONDecodeError:
                outline_parsed = outline
            payload = {
                "keyword": b.keyword or b.title,
                "title": [b.title] if b.title else [],
                "outline": outline_parsed,
                "word_count": b.word_count,
                "related_keywords": b.related_keywords,
                "success_metric": "gsc.impressions",
            }
            name = client.name if client else f"client-{b.client_id}"
            rows.append(
                {
                    "task": "content_brief",
                    "pattern": "from_db",
                    "source_id": b.id,
                    "messages": [
                        {"role": "system", "content": with_marketing_knowledge(BRIEF_PROMPT)},
                        {
                            "role": "user",
                            "content": f"Generate content brief JSON for {name}: {b.title}",
                        },
                        {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                }
            )
    finally:
        db.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Exported {len(rows)} examples → {args.out}")


if __name__ == "__main__":
    main()
