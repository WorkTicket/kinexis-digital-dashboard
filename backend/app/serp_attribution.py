"""SERP feature attribution for CTR gap insights.

When a query has a CTR lower than expected for its position, the cause might
not be weak titles/metas — it might be SERP feature changes (featured snippets,
People Also Ask, local packs, knowledge panels, etc.) pushing organic results
further down the page or reducing click-through.

This module enriches CTR gap insights with SERP feature data so the agent
can distinguish "bad snippet" from "Google changed the SERP layout."
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import SerpSnapshot, MetricDaily


def serp_features_for_query(db: Session, client_id: int, query: str) -> dict | None:
    """Return SERP feature data for a query if a recent snapshot exists.

    Returns None if no SERP data is available or SERP connector is disabled.
    """
    today = date.today()
    cutoff = today - timedelta(days=90)

    snap = (
        db.query(SerpSnapshot)
        .filter(
            SerpSnapshot.client_id == client_id,
            SerpSnapshot.query == query,
            SerpSnapshot.fetched_at >= cutoff,
        )
        .order_by(SerpSnapshot.fetched_at.desc())
        .first()
    )

    if not snap or not snap.results_json:
        return None

    import json
    try:
        results = json.loads(snap.results_json)
    except (json.JSONDecodeError, TypeError):
        return None

    features = _classify_serp_features(results)
    return {
        "query": query,
        "fetched_at": snap.fetched_at.isoformat() if snap.fetched_at else None,
        "features": features,
        "organic_count": sum(1 for r in results if r.get("position") and _is_organic(r)),
        "feature_blocking_pct": _estimate_click_displacement(features, results),
    }


def _classify_serp_features(results: list[dict]) -> dict[str, int]:
    """Count SERP feature types present in the results."""
    counts: dict[str, int] = {}
    for r in results:
        snippet = (r.get("snippet") or "").lower()
        title = (r.get("title") or "").lower()

        if r.get("position") == 1 and ("featured" in snippet or "snippet" in snippet):
            counts["featured_snippet"] = counts.get("featured_snippet", 0) + 1
        elif "people also ask" in title or "related questions" in snippet:
            counts["people_also_ask"] = counts.get("people_also_ask", 0) + 1
        elif "map" in snippet.lower() or "directions" in snippet.lower() or "local" in title:
            counts["local_pack"] = counts.get("local_pack", 0) + 1
        elif "knowledge" in snippet.lower() or "wikipedia" in snippet.lower():
            counts["knowledge_panel"] = counts.get("knowledge_panel", 0) + 1
        elif "video" in snippet.lower() or "youtube" in snippet.lower():
            counts["video_carousel"] = counts.get("video_carousel", 0) + 1
        elif "image" in snippet.lower() or "images" in title:
            counts["image_pack"] = counts.get("image_pack", 0) + 1
        elif "ad" in snippet.lower() and "sponsored" in snippet.lower():
            counts["ads_top"] = counts.get("ads_top", 0) + 1
    return counts


def _is_organic(result: dict) -> bool:
    """Check if a SERP result is an organic listing (not a feature block)."""
    title = (result.get("title") or "").lower()
    snippet = (result.get("snippet") or "").lower()
    # Exclude known feature blocks
    if "featured" in snippet and "snippet" in snippet:
        return False
    if "people also ask" in title:
        return False
    return True


def _estimate_click_displacement(features: dict, results: list[dict]) -> float:
    """Estimate what percentage of clicks are displaced by SERP features.

    Returns 0.0-1.0 where 0.35 means ~35% of potential clicks are being
    absorbed by SERP features above the organic results.
    """
    displacement = 0.0
    if features.get("featured_snippet"):
        displacement += 0.20  # Featured snippet captures ~20% of clicks
    if features.get("people_also_ask"):
        displacement += 0.08  # PAA blocks absorb ~8%
    if features.get("local_pack"):
        displacement += 0.25  # Local pack captures ~25% for local queries
    if features.get("knowledge_panel"):
        displacement += 0.10
    if features.get("ads_top"):
        displacement += 0.15  # Top ads push everything down
    return min(1.0, displacement)


def enrich_ctr_insight_with_serp(
    db: Session,
    client_id: int,
    insight: dict,
) -> dict:
    """Take a CTR gap insight and enrich it with SERP feature context.

    Modifies the message to distinguish "bad title/meta" from "SERP feature
    is absorbing clicks" — the latter needs a different playbook.
    """
    blob = f"{insight.get('message', '')} {insight.get('recommended_action', '')}"
    import re
    quoted = re.findall(r'"([^"]{2,120})"', blob)
    query = quoted[0] if quoted else None
    if not query:
        return insight

    serp = serp_features_for_query(db, client_id, query)
    if not serp or not serp.get("features"):
        return insight

    features = serp["features"]
    feature_names = [k.replace("_", " ") for k in features.keys()]
    displacement = serp.get("feature_blocking_pct", 0)

    if displacement >= 0.25:
        # SERP features are the dominant cause — switch the playbook
        insight["message"] = (
            insight["message"] + (
                f" Note: SERP analysis shows {', '.join(feature_names)} on this query "
                f"(~{displacement:.0%} of clicks absorbed by SERP features). "
                f"The CTR gap may be structural (Google layout), not a snippet issue."
            )
        )
        insight["recommended_action"] = (
            f"SERP feature strategy for '{query}':\n"
            f"1) Check if you can claim the existing featured snippet (add concise answer).\n"
            f"2) Optimize for local pack visibility (GBP profile, NAP consistency).\n"
            f"3) Target People Also Ask by answering common questions directly on your page.\n"
            f"4) Only rewrite title/meta after exhausting SERP feature plays."
        )

    return insight
