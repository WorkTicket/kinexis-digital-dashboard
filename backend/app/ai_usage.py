"""AI usage / cost logging helpers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AiUsageLog, Client
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

# Rough public list prices (USD per 1M tokens) — transparency, not billing
ANTHROPIC_INPUT_PER_M = 3.0
ANTHROPIC_OUTPUT_PER_M = 15.0
OLLAMA_COST = 0.0


def estimate_cost(provider: str, input_tokens: int, output_tokens: int) -> float:
    if (provider or "").lower() == "ollama":
        return 0.0
    return round(
        (input_tokens / 1_000_000) * ANTHROPIC_INPUT_PER_M
        + (output_tokens / 1_000_000) * ANTHROPIC_OUTPUT_PER_M,
        6,
    )


def log_usage(
    *,
    provider: str,
    model: str,
    purpose: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    client_id: Optional[int] = None,
) -> None:
    try:
        db = SessionLocal()
        try:
            cost = estimate_cost(provider, input_tokens, output_tokens)
            row = AiUsageLog(
                client_id=client_id,
                provider=provider or "",
                model=model or "",
                purpose=purpose or "",
                input_tokens=input_tokens or 0,
                output_tokens=output_tokens or 0,
                estimated_cost_usd=cost,
                created_at=utcnow(),
            )
            db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.debug("AI usage log failed: %s", e)


def usage_summary(db: Session, days: int = 7) -> dict:
    since = utcnow() - timedelta(days=days)
    rows = db.query(AiUsageLog).filter(AiUsageLog.created_at >= since).all()
    week_calls = len(rows)
    week_cost = sum(r.estimated_cost_usd or 0 for r in rows)

    by_client: dict[Optional[int], dict] = {}
    for r in rows:
        key = r.client_id
        bucket = by_client.setdefault(
            key,
            {
                "client_id": key,
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_usd": 0.0,
            },
        )
        bucket["calls"] += 1
        bucket["input_tokens"] += r.input_tokens or 0
        bucket["output_tokens"] += r.output_tokens or 0
        bucket["estimated_cost_usd"] += r.estimated_cost_usd or 0

    client_ids = [cid for cid in by_client if cid is not None]
    names = {}
    if client_ids:
        for c in db.query(Client).filter(Client.id.in_(client_ids)).all():
            names[c.id] = c.name

    by_client_list = []
    for cid, bucket in by_client.items():
        by_client_list.append(
            {
                **bucket,
                "client_name": names.get(cid, "Unscoped") if cid else "Unscoped",
                "estimated_cost_usd": round(bucket["estimated_cost_usd"], 4),
            }
        )
    by_client_list.sort(key=lambda x: -x["estimated_cost_usd"])

    recent = (
        db.query(AiUsageLog)
        .order_by(AiUsageLog.created_at.desc())
        .limit(25)
        .all()
    )
    return {
        "week_total_calls": week_calls,
        "week_estimated_cost_usd": round(week_cost, 4),
        "by_client": by_client_list,
        "recent": [
            {
                "id": r.id,
                "client_id": r.client_id,
                "provider": r.provider,
                "model": r.model,
                "purpose": r.purpose,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "estimated_cost_usd": r.estimated_cost_usd,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent
        ],
    }
