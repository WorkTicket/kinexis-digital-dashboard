"""Per-client seasonality baselines — rolling 52-week expected values per metric.

Replaces the hardcoded month-based `seasonality_caution()` with data-driven
seasonal adjustment. Decline alerts subtract the expected seasonal delta before
flagging a drop, so a roofer losing traffic in December vs January doesn't
trigger a false alarm while the same drop in July does.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import ClientSeasonality, MetricDaily

logger = logging.getLogger(__name__)


def compute_seasonality_baseline(
    db: Session,
    client_id: int,
    source: str,
    metric_name: str,
    *,
    years_back: int = 2,
    dimension_type: Optional[str] = None,
) -> int:
    """Build or rebuild the 52-week rolling baseline for one metric.

    Uses median across N years of weekly data. Stores one row per ISO week.
    Returns count of weeks stored.
    """
    # Delete existing baseline for this metric
    db.query(ClientSeasonality).filter(
        ClientSeasonality.client_id == client_id,
        ClientSeasonality.source == source,
        ClientSeasonality.metric_name == metric_name,
    ).delete()

    today = date.today()
    # Go back years_back × 52 weeks
    start = today - timedelta(weeks=52 * years_back)

    filters = [
        MetricDaily.client_id == client_id,
        MetricDaily.source == source,
        MetricDaily.metric_name == metric_name,
        MetricDaily.date >= start,
        MetricDaily.date <= today,
    ]
    if dimension_type:
        filters.append(MetricDaily.dimension_type == dimension_type)

    rows = (
        db.query(MetricDaily.date, func.sum(MetricDaily.value))
        .filter(and_(*filters))
        .group_by(MetricDaily.date)
        .order_by(MetricDaily.date.asc())
        .all()
    )

    # Group by ISO week
    by_week: dict[int, list[float]] = {}
    for d, val in rows:
        iso_week = d.isocalendar()[1]  # 1-53
        by_week.setdefault(iso_week, []).append(float(val or 0))

    stored = 0
    for iso_week, values in by_week.items():
        if len(values) < 2:
            continue
        values.sort()
        n = len(values)
        median = values[n // 2] if n % 2 == 1 else (values[n // 2 - 1] + values[n // 2]) / 2
        p25 = values[max(0, n // 4)]
        p75 = values[min(n - 1, (n * 3) // 4)]

        db.add(ClientSeasonality(
            client_id=client_id,
            source=source,
            metric_name=metric_name,
            iso_week=iso_week,
            median_value=round(median, 2),
            p25_value=round(p25, 2),
            p75_value=round(p75, 2),
            sample_years=len(values),
        ))
        stored += 1

    db.commit()
    return stored


def seasonal_adjust(
    db: Session,
    client_id: int,
    source: str,
    metric_name: str,
    current_value: float,
    *,
    weeks: int = 4,
) -> Optional[float]:
    """Return the seasonal adjustment delta for a metric value.

    Positive = current is above seasonal expectation. Negative = below.
    None = insufficient data to compute.
    """
    today = date.today()
    current_iso_week = today.isocalendar()[1]

    baselines = (
        db.query(ClientSeasonality)
        .filter(
            ClientSeasonality.client_id == client_id,
            ClientSeasonality.source == source,
            ClientSeasonality.metric_name == metric_name,
        )
        .all()
    )
    if len(baselines) < 26:  # need at least half the year
        return None

    # Look up the expected value for this ISO week
    week_row = next((b for b in baselines if b.iso_week == current_iso_week), None)
    if not week_row:
        # Try adjacent weeks
        for offset in [1, -1, 2, -2]:
            adj = current_iso_week + offset
            if adj < 1:
                adj = 52
            if adj > 53:
                adj = 1
            week_row = next((b for b in baselines if b.iso_week == adj), None)
            if week_row:
                break
    if not week_row:
        return None

    expected = week_row.median_value
    if expected <= 0:
        return None

    seasonal_delta = current_value - expected
    return round(seasonal_delta, 2)


def seasonality_caution_for_metric(
    db: Session,
    client_id: int,
    source: str,
    metric_name: str,
    current_value: float,
) -> Optional[str]:
    """Return a human-readable caution if current value is within seasonal range.

    Returns None when seasonality is not a concern, or a string like:
    "Traffic is in the expected range for mid-July (median 1,200 clicks this week)"
    """
    adj = seasonal_adjust(db, client_id, source, metric_name, current_value)
    if adj is None:
        return None

    today = date.today()
    current_iso_week = today.isocalendar()[1]

    baseline = (
        db.query(ClientSeasonality)
        .filter(
            ClientSeasonality.client_id == client_id,
            ClientSeasonality.source == source,
            ClientSeasonality.metric_name == metric_name,
            ClientSeasonality.iso_week == current_iso_week,
        )
        .first()
    )

    if not baseline:
        return None

    pct_from_median = abs(adj) / baseline.median_value if baseline.median_value > 0 else 0
    if pct_from_median < 0.25:
        return (
            f"Current {metric_name} ({current_value:,.0f}) is within expected seasonal range "
            f"(median {baseline.median_value:,.0f} for this week). "
            f"Declines may be seasonal, not site-related."
        )
    return None
