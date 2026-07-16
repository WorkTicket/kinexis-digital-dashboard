"""Shared evidence helpers — single source of truth for metric computations.

Every module that computes CTR, confidence, or sample-size estimates must
use these functions. This prevents the class of bugs where different modules
compute the same metric differently (e.g. avg of daily ratios vs sum/sum).
"""

from __future__ import annotations

import statistics
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import MetricDaily


def weighted_ctr(
    *,
    clicks: float,
    impressions: float,
) -> Optional[float]:
    """SUM(clicks) / SUM(impressions) — the only correct way to compute CTR.

    Never average daily CTR ratios. See audit report Bug #1 for the full
    explanation of why avg(daily_ctr) is a statistical error.

    Returns None when impressions <= 0 (not 0.0 — caller decides what to do
    with missing data).
    """
    if impressions is None or impressions <= 0:
        return None
    return clicks / impressions


def weighted_ctr_pct(
    *,
    clicks: float,
    impressions: float,
) -> Optional[float]:
    """Same as weighted_ctr but returns percentage (0-100)."""
    ctr = weighted_ctr(clicks=clicks, impressions=impressions)
    return ctr * 100.0 if ctr is not None else None


def query_weighted_ctr(
    db: Session,
    client_id: int,
    source: str,
    *,
    dimension_type: str = "query",
    dimension_value: str,
    days: int = 30,
) -> tuple[float, float, float]:
    """Fetch clicks + impressions + compute correct CTR for one dimension value.

    Returns (clicks, impressions, ctr_ratio). CTR = SUM(clicks) / SUM(impressions).
    Impressions will be 0.0 if no data, ctr_ratio will be 0.0 in that case.
    """
    today = date.today()
    start = today - timedelta(days=days)

    def _sum_metric(metric_name: str) -> float:
        val = (
            db.query(func.sum(MetricDaily.value))
            .filter(
                and_(
                    MetricDaily.client_id == client_id,
                    MetricDaily.source == source,
                    MetricDaily.metric_name == metric_name,
                    MetricDaily.dimension_type == dimension_type,
                    MetricDaily.dimension_value == dimension_value,
                    MetricDaily.date >= start,
                )
            )
            .scalar()
        )
        return float(val or 0)

    clicks = _sum_metric("clicks")
    impressions = _sum_metric("impressions")
    ctr = (clicks / impressions) if impressions > 0 else 0.0
    return clicks, impressions, ctr


def confidence_tier(
    *,
    impressions: float,
    days: int,
) -> str:
    """Sample-size-based confidence tier for any impression-based insight.

    - high: >= 5000 total impressions (solid signal)
    - medium: >= 1000 total impressions (moderate signal)
    - low: anything below (small sample — caveat in UI)
    """
    daily_avg = impressions / max(1, days)
    if daily_avg >= 5000 / 30:
        return "high"
    if daily_avg >= 1000 / 30:
        return "medium"
    return "low"


def trend_stability(daily_values: list[float]) -> float:
    """Coefficient of variation for a metric's daily values.

    Lower = more stable. Use as a reliability signal on insights:
    a highly volatile metric with a small WoW change is likely noise.

    Returns CV as a ratio (0.0 = perfectly stable, 1.0 = highly variable).
    """
    if not daily_values or len(daily_values) < 2:
        return 0.0
    try:
        mean = statistics.mean(daily_values)
        if mean <= 0:
            return 0.0
        stdev = statistics.stdev(daily_values)
        return stdev / mean
    except statistics.StatisticsError:
        return 0.0
