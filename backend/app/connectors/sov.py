"""Share-of-voice MetricDaily writer from SerpSnapshot + competitor profile."""

from __future__ import annotations

import json
import logging
from datetime import date
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.competitor_domains import parse_client_domains, parse_competitor_domains
from app.connectors.base import _sync_lock
from app.models import Client, MetricDaily, SerpSnapshot

logger = logging.getLogger(__name__)


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def compute_sov_from_snaps(
    snaps: list[SerpSnapshot],
    *,
    comps: list[str],
    owns: list[str],
) -> tuple[float | None, int, int]:
    """Return (presence 0..1, wins, losses) from latest-per-query SERP snaps."""
    if not comps or not snaps:
        return None, 0, 0
    latest: dict[str, SerpSnapshot] = {}
    for s in snaps:
        q = (s.query or "").strip().lower()
        if q and q not in latest:
            latest[q] = s
    wins = losses = 0
    for snap in latest.values():
        try:
            results = json.loads(snap.results_json or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        client_pos = None
        comp_pos = None
        for row in results:
            if not isinstance(row, dict):
                continue
            host = _host(str(row.get("url") or ""))
            try:
                pos = int(row.get("position") or 0) or None
            except (TypeError, ValueError):
                pos = None
            if not host or not pos:
                continue
            if owns and any(host == d or host.endswith("." + d) for d in owns):
                if client_pos is None or pos < client_pos:
                    client_pos = pos
            if any(host == d or host.endswith("." + d) for d in comps):
                if comp_pos is None or pos < comp_pos:
                    comp_pos = pos
        if client_pos is None and comp_pos is None:
            continue
        if comp_pos is not None and (client_pos is None or comp_pos < client_pos):
            losses += 1
        elif client_pos is not None:
            wins += 1
    measured = wins + losses
    if measured <= 0:
        return None, wins, losses
    return wins / measured, wins, losses


def write_sov_presence(db: Session, client_id: int, on_date: date | None = None) -> dict:
    """Write MetricDaily source=serp metric_name=sov_presence (+ sov_loss_rate)."""
    client = db.query(Client).filter(Client.id == client_id).first()
    comps = parse_competitor_domains(client)
    owns = parse_client_domains(client)
    if not comps:
        return {"ok": False, "reason": "no_competitors"}

    snaps = (
        db.query(SerpSnapshot)
        .filter(SerpSnapshot.client_id == client_id)
        .order_by(SerpSnapshot.fetched_at.desc())
        .limit(80)
        .all()
    )
    presence, wins, losses = compute_sov_from_snaps(snaps, comps=comps, owns=owns)
    if presence is None:
        return {"ok": False, "reason": "no_measured_queries", "wins": wins, "losses": losses}

    day = on_date or date.today()
    loss_rate = losses / (wins + losses) if (wins + losses) else 0.0
    with _sync_lock(client_id, "serp"):
        db.query(MetricDaily).filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == "serp",
            MetricDaily.date == day,
            MetricDaily.metric_name.in_(["sov_presence", "sov_loss_rate"]),
        ).delete(synchronize_session=False)
        for name, value in (("sov_presence", presence), ("sov_loss_rate", loss_rate)):
            db.add(
                MetricDaily(
                    client_id=client_id,
                    source="serp",
                    date=day,
                    metric_name=name,
                    value=float(value),
                    dimension_type="",
                    dimension_value="",
                )
            )
        db.commit()
    logger.info(
        "SoV presence written client=%s day=%s presence=%.2f wins=%s losses=%s",
        client_id,
        day,
        presence,
        wins,
        losses,
    )
    return {
        "ok": True,
        "sov_presence": round(presence, 4),
        "sov_loss_rate": round(loss_rate, 4),
        "wins": wins,
        "losses": losses,
    }
