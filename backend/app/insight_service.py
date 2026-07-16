"""Shared insight generation with deduplication and noise pruning."""

import hashlib
import json
import logging
import re
from datetime import date, timedelta
from sqlalchemy.orm import Session

from app.models import Insight, Client
from app.insights.rules import run_all_rules
from app.insight_scoring import (
    default_kind,
    score_with_impact,
    score_with_intent,
    score_with_proven_effectiveness,
    INTENT_WEIGHTS,
)
from app.insight_thresholds import thresholds_for_client
from app.query_intent import classify_query_intent, lead_intent_weight
from app.service_area import parse_service_area, ServiceArea

logger = logging.getLogger(__name__)


def insight_fingerprint(
    insight_type: str,
    *,
    target_url: str | None = None,
    target_query: str | None = None,
) -> str:
    """Stable identity: sha256(type | target_url | target_query)."""
    url = (target_url or "").strip()
    q = (target_query or "").strip()
    raw = f"{insight_type}|{url}|{q}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _targets_from_item(item: dict) -> tuple[str | None, str | None]:
    """Prefer explicit fields; fall back to quoted query / first URL in text."""
    tq = (item.get("target_query") or "").strip() or None
    tu = (item.get("target_url") or "").strip() or None
    if tq and tu:
        return tq[:500], tu[:1000]
    blob = f"{item.get('message', '')} {item.get('recommended_action', '')}"
    if not tq:
        m = _QUOTED_QUERY_RE.search(blob)
        if m:
            tq = m.group(1).strip()[:500] or None
    if not tu:
        url_m = re.search(r'https?://[^\s"\']+', blob)
        if url_m:
            tu = url_m.group(0).rstrip(".,;:!?)'\"")[:1000]
    return tq, tu


def _evidence_json_for_item(item: dict) -> str | None:
    evidence = item.get("evidence")
    if evidence is None and item.get("evidence_json"):
        return item.get("evidence_json")
    if evidence is None:
        return None
    if isinstance(evidence, str):
        try:
            json.loads(evidence)
            return evidence
        except (json.JSONDecodeError, TypeError):
            return json.dumps({"text": evidence})
    try:
        return json.dumps(evidence)
    except (TypeError, ValueError):
        return None

# High-volume SEO rules that can still spam even with floors
NOISY_TYPES = (
    "content_opportunity",
    "ctr_opportunity",
    "ctr_gap",
    "zero_click_alert",
    "cro_opportunity",
    "bounce_cro_alert",
)

_QUOTED_QUERY_RE = re.compile(r'"([^"]{2,120})"')

# Evidence-gated types: only emit when data meets threshold
_EVIDENCE_GATED_TYPES = frozenset({
    "pagespeed_urgent",
    "pagespeed_improve",
    "mobile_ctr_gap",
})


def _extract_queries(items: list[dict]) -> dict[str, list[dict]]:
    """Map quoted queries to their insight items for cross-type dedupe."""
    by_query: dict[str, list[dict]] = {}
    for item in items:
        blob = f"{item.get('message', '')} {item.get('recommended_action', '')}"
        for m in _QUOTED_QUERY_RE.finditer(blob):
            q = m.group(1).strip().lower()
            if q and len(q) > 2:
                by_query.setdefault(q, []).append(item)
    return by_query


def _suppress_zero_click_with_ctr(items: list[dict]) -> list[dict]:
    """If same query has both zero_click_alert and ctr_gap/ctr_opportunity,
    drop the zero_click_alert — CTR insight is more actionable.
    Also folds zero-click into CTR opportunity when position data exists."""
    by_query = _extract_queries(items)
    zero_click_fingerprints: set[int] = set()
    ctr_types = {"ctr_gap", "ctr_opportunity"}

    for query, query_items in by_query.items():
        has_ctr = any(i.get("type") in ctr_types for i in query_items)
        if not has_ctr:
            continue
        for item in query_items:
            if item.get("type") == "zero_click_alert":
                zero_click_fingerprints.add(id(item))

    kept = []
    for item in items:
        if id(item) in zero_click_fingerprints:
            logger.info(
                "Cross-type suppress: zero_click for query — ctr_gap covers it"
            )
            continue
        kept.append(item)
    return kept


def prune_noisy_insights(db: Session, client_id: int) -> int:
    """
    Keep only the top N open insights per kind (by priority_score).
    Also caps per noisy type so portfolio/Prescribe stay actionable.
    """
    thr = thresholds_for_client(db, client_id)
    keep_problems = int(thr.get("max_open_problems", 8))
    keep_opps = int(thr.get("max_open_opportunities", 10))
    keep_type = int(thr.get("max_open_noisy_insights", 10))
    if thr.get("thin_traffic"):
        keep_problems = min(keep_problems, 5)
        keep_opps = min(keep_opps, 6)
        keep_type = min(keep_type, 5)

    resolved = 0

    for kind, keep in (("problem", keep_problems), ("opportunity", keep_opps)):
        open_rows = (
            db.query(Insight)
            .filter(
                Insight.client_id == client_id,
                Insight.kind == kind,
                Insight.resolved == False,  # noqa: E712
            )
            .order_by(Insight.priority_score.desc(), Insight.id.desc())
            .all()
        )
        for ins in open_rows[keep:]:
            ins.resolved = True
            ins.resolve_reason = "pruned"
            resolved += 1

    for insight_type in NOISY_TYPES:
        open_rows = (
            db.query(Insight)
            .filter(
                Insight.client_id == client_id,
                Insight.type == insight_type,
                Insight.resolved == False,  # noqa: E712
            )
            .order_by(Insight.priority_score.desc(), Insight.id.desc())
            .all()
        )
        for ins in open_rows[keep_type:]:
            if not ins.resolved:
                ins.resolved = True
                ins.resolve_reason = "pruned"
                resolved += 1

    if resolved:
        db.commit()
        logger.info(
            "Pruned %s low-signal insights for client %s (problems≤%s, opps≤%s)",
            resolved,
            client_id,
            keep_problems,
            keep_opps,
        )
    return resolved


def resolve_stale_insights(db: Session, client_id: int, fresh_keys: set[str]) -> int:
    """
    Resolve open insights no longer emitted by current rules.
    Compares all rows by fingerprint: compute SHA256 for legacy rows on the fly.
    """
    open_rows = (
        db.query(Insight)
        .filter(
            Insight.client_id == client_id,
            Insight.resolved == False,  # noqa: E712
        )
        .all()
    )
    resolved = 0
    for ins in open_rows:
        if ins.fingerprint:
            key = ins.fingerprint
        else:
            key = insight_fingerprint(
                ins.type,
                target_url=ins.target_url,
                target_query=ins.target_query,
            )
        if key not in fresh_keys:
            ins.resolved = True
            ins.resolve_reason = "stale"
            resolved += 1
    if resolved:
        db.commit()
        logger.info(
            "Resolved %s stale insights for client %s (no longer meet rule floors)",
            resolved,
            client_id,
        )
    return resolved


def backfill_insight_kinds(db: Session, client_id: int | None = None) -> int:
    """Sync kind from type taxonomy (fixes SQLite DEFAULT 'opportunity' on new column)."""
    q = db.query(Insight)
    if client_id is not None:
        q = q.filter(Insight.client_id == client_id)
    updated = 0
    for ins in q.all():
        expected = default_kind(ins.type or "")
        current = (ins.kind or "").strip().lower()
        if current != expected:
            ins.kind = expected
            updated += 1
    if updated:
        db.commit()
    return updated


def _evidence_gate(item: dict) -> bool:
    """Return False if insight type requires specific evidence not present."""
    typ = item.get("type", "")
    message = item.get("message", "") or ""
    action = item.get("recommended_action", "") or ""
    blob = f"{message} {action}"

    if typ in ("pagespeed_urgent", "pagespeed_improve"):
        # Require URL + numeric score in the message
        has_url = bool(re.search(r'https?://[^\s"\']+', blob))
        has_score = bool(re.search(r'\b\d{2}\b', message))  # two-digit score
        if not (has_url and has_score):
            logger.info("Evidence gate: %s dropped — missing URL or score", typ)
            return False

    if typ == "mobile_ctr_gap":
        # Require mobile CTR + desktop CTR numbers
        has_mobile_ctr = bool(re.search(r'mobile.*ctr|mobile.*\d+\.?\d*%', blob, re.I))
        has_desktop_ctr = bool(re.search(r'desktop.*ctr|desktop.*\d+\.?\d*%', blob, re.I))
        if not (has_mobile_ctr and has_desktop_ctr):
            logger.info("Evidence gate: mobile_ctr_gap dropped — missing mobile/desktop CTR")
            return False

    return True


def generate_insights_for_client(db: Session, client_id: int) -> list[Insight]:
    """Run all rules and persist new unresolved insights (deduped by fingerprint)."""
    from app.page_targets import enrich_insight_item

    backfill_insight_kinds(db, client_id)
    results = run_all_rules(client_id, db)
    client = db.query(Client).filter(Client.id == client_id).first()
    brand = (client.name or "").split(".")[0] if client else ""
    results = [enrich_insight_item(db, client_id, item, brand=brand) for item in results]
    # Evidence gate: drop insights that lack required numeric evidence
    before = len(results)
    results = [r for r in results if _evidence_gate(r)]
    if len(results) < before:
        logger.info("Evidence gate dropped %s insight(s) for client %s", before - len(results), client_id)
    # Cross-type suppression: drop zero_click if same query has CTR insight
    results = _suppress_zero_click_with_ctr(results)
    # Intent + service-area rescoring (Phase 3.3): local_commercial gets priority boost;
    # out-of-area queries get suppressed; informational/guide gets deweighted.
    sa: ServiceArea | None = parse_service_area(client) if client else None
    from app.service_area import classify_query_geo

    for item in results:
        blob = f"{item.get('message', '')} {item.get('recommended_action', '')}"
        for m in _QUOTED_QUERY_RE.finditer(blob):
            q = m.group(1).strip()
            if q:
                intent = classify_query_intent(q, sa)
                weight = lead_intent_weight(intent)
                item["_lead_intent_weight"] = weight
                # Suppress OOA/excluded only; unknown stays eligible for non-local work
                # but is never treated as in-area for local_commercial (see query_intent).
                if sa and sa.configured:
                    geo = classify_query_geo(q, sa)
                    item["_in_service_area"] = geo not in ("out_of_area", "excluded")
                else:
                    item["_in_service_area"] = True
                break
        if "_lead_intent_weight" not in item:
            item["_lead_intent_weight"] = 1.0
            item["_in_service_area"] = True

    fresh_keys: set[str] = set()
    created: list[Insight] = []

    # Learning Loop → Prescribe: Recommendation verified stats first, levers fallback
    effectiveness: dict = {}
    try:
        from app.recommendation_service import effectiveness_by_fix_type
        from app.portfolio_scoring import cross_client_fix_effectiveness

        rec_rows = effectiveness_by_fix_type(db) or []
        for row in rec_rows:
            ft = row.get("fix_type") or "unknown"
            if (row.get("total") or 0) < 3:
                continue
            effectiveness[ft] = {
                "wins": row.get("wins") or 0,
                "total": row.get("total") or 0,
                "median_lift_pct": row.get("median_lift_pct"),
            }
        if not effectiveness:
            effectiveness = cross_client_fix_effectiveness(db) or {}
    except Exception as e:
        logger.warning("effectiveness lookup unavailable: %s", e)

    # Confidence computation helpers
    from app.evidence import confidence_tier as compute_confidence_tier
    from app.known_events import events_touching
    from datetime import timedelta

    def _confidence_for_item(item: dict) -> tuple[str | None, int | None, bool]:
        """Extract sample size from insight message and compute confidence tier."""
        blob = f"{item.get('message', '')} {item.get('recommended_action', '')}"
        # Extract impression/session counts from the message
        sample = None
        for m in re.finditer(r'([\d,.]+)\s*(?:impr|impressions|sessions)', blob, re.I):
            try:
                n = int(float(m.group(1).replace(",", "")))
                if sample is None or n > sample:
                    sample = n
            except ValueError:
                continue
        if sample is None:
            # Try positions like "impr/30d" patterns
            for m in re.finditer(r'([\d,.]+)\s*(?:/30d|impr)', blob, re.I):
                try:
                    n = int(float(m.group(1).replace(",", "")))
                    if sample is None or n > sample:
                        sample = n
                except ValueError:
                    continue
        tier = compute_confidence_tier(impressions=float(sample or 0), days=30) if sample else None
        # Check for Google core updates overlapping analysis window
        today = date.today()
        events = events_touching(today - timedelta(days=30), today)
        has_update_caveat = bool(events)
        return tier, sample, has_update_caveat

    for item in results:
        kind = item.get("kind") or default_kind(item["type"])
        tq, tu = _targets_from_item(item)
        fp = insight_fingerprint(item["type"], target_url=tu, target_query=tq)
        fresh_keys.add(fp)
        evidence_json = _evidence_json_for_item(item)

        existing = (
            db.query(Insight)
            .filter(
                Insight.client_id == client_id,
                Insight.fingerprint == fp,
                Insight.resolved == False,  # noqa: E712
            )
            .first()
        )
        if not existing:
            # Legacy fallback: type+message for rows without fingerprint yet
            existing = (
                db.query(Insight)
                .filter(
                    Insight.client_id == client_id,
                    Insight.type == item["type"],
                    Insight.message == item["message"],
                    Insight.resolved == False,  # noqa: E712
                    Insight.fingerprint.is_(None),
                )
                .first()
            )
        score = score_with_proven_effectiveness(
            item.get("severity", "medium"),
            item["type"],
            impact_weight=item.get("impact_weight"),
            lead_intent_weight=item.get("_lead_intent_weight", 1.0),
            in_service_area=item.get("_in_service_area", True),
            effectiveness=effectiveness,
        )
        confidence_tier_val, sample_size_val, caveat = _confidence_for_item(item)
        if existing:
            existing.priority_score = score
            existing.kind = kind
            existing.severity = item.get("severity", existing.severity)
            existing.recommended_action = item.get("recommended_action") or existing.recommended_action
            existing.message = item["message"]
            existing.fingerprint = fp
            existing.target_query = tq
            existing.target_url = tu
            existing.confidence_tier = confidence_tier_val
            existing.sample_size = sample_size_val
            existing.algorithmic_caveat = caveat
            if evidence_json is not None:
                existing.evidence_json = evidence_json
            continue
        insight = Insight(
            client_id=client_id,
            type=item["type"],
            message=item["message"],
            recommended_action=item.get("recommended_action"),
            severity=item.get("severity", "medium"),
            kind=kind,
            priority_score=score,
            fingerprint=fp,
            target_query=tq,
            target_url=tu,
            evidence_json=evidence_json,
            confidence_tier=confidence_tier_val,
            sample_size=sample_size_val,
            algorithmic_caveat=caveat,
        )
        db.add(insight)
        created.append(insight)
    db.commit()
    for ins in created:
        db.refresh(ins)

    # Start Recommendation lifecycle for every new insight (Learning Loop)
    if created:
        try:
            from app.recommendation_service import propose_from_insight

            for ins in created:
                propose_from_insight(db, ins)
            db.commit()
        except Exception as e:
            logger.warning("auto-propose recommendations failed: %s", e)

    # Anomaly-triggered push queue for critical new insights
    ANOMALY_TYPES = {
        "decline_alert",
        "error_spike_alert",
        "zero_click_alert",
        "pagespeed_urgent",
        "ads_spend_low_leads",
    }
    try:
        from app.models import AnomalyNotification

        client = db.query(Client).filter(Client.id == client_id).first()
        client_name = client.name if client else f"Client {client_id}"
        for ins in created:
            if ins.severity != "high" and ins.type not in ANOMALY_TYPES:
                continue
            note = AnomalyNotification(
                client_id=client_id,
                insight_id=ins.id,
                severity=ins.severity or "high",
                title=f"Kinexis · {client_name}",
                body=ins.message[:280],
            )
            db.add(note)
        db.commit()
    except Exception as e:
        logger.warning("Could not queue anomaly notifications: %s", e)

    stale = resolve_stale_insights(db, client_id, fresh_keys)
    pruned = prune_noisy_insights(db, client_id)
    logger.info(
        "Insights for client %s: %s found, %s new, %s stale-resolved, %s pruned",
        client_id,
        len(results),
        len(created),
        stale,
        pruned,
    )
    return created
