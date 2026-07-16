"""Unified MetricsService — single aggregation façade for MetricDaily."""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import MetricDaily


def sum_metric(
    db: Session,
    client_id: int,
    source: str,
    metric_name: str,
    start: date,
    end: date,
    dimension_type: Optional[str] = None,
) -> float:
    """Sum a MetricDaily series. Use source='paid' for cross-ads rollup."""
    if source == "paid":
        from app.connectors.ads_common import sum_paid_metric

        return sum_paid_metric(db, client_id, metric_name, start, end)
    filters = [
        MetricDaily.client_id == client_id,
        MetricDaily.source == source,
        MetricDaily.metric_name == metric_name,
        MetricDaily.date >= start,
        MetricDaily.date <= end,
    ]
    if dimension_type is not None:
        filters.append(MetricDaily.dimension_type == dimension_type)
    val = db.query(func.sum(MetricDaily.value)).filter(and_(*filters)).scalar()
    return float(val or 0)


def batch_metric_sums(
    db: Session,
    client_ids: list[int],
    specs: list[tuple[str, str, Optional[str]]],
    start: date,
    end: date,
) -> dict[tuple[int, str, str], float]:
    """One query per (source, metric, dim) across all clients."""
    out: dict[tuple[int, str, str], float] = {}
    if not client_ids:
        return out
    for source, metric_name, dim in specs:
        filters = [
            MetricDaily.client_id.in_(client_ids),
            MetricDaily.source == source,
            MetricDaily.metric_name == metric_name,
            MetricDaily.date >= start,
            MetricDaily.date <= end,
        ]
        if dim is not None:
            filters.append(MetricDaily.dimension_type == dim)
        rows = (
            db.query(MetricDaily.client_id, func.sum(MetricDaily.value))
            .filter(and_(*filters))
            .group_by(MetricDaily.client_id)
            .all()
        )
        for cid, total in rows:
            out[(cid, source, metric_name)] = float(total or 0)
    return out


def pct_change(cur: float, prev: float) -> Optional[float]:
    if prev is None or prev <= 0:
        return None
    return round(((cur - prev) / prev) * 100, 1)


def paid_series(
    db: Session,
    client_id: int,
    metric_name: str,
    start: date,
    end: date,
) -> list[float]:
    from app.connectors.ads_common import paid_daily_series

    return paid_daily_series(db, client_id, metric_name, start, end)


class MetricsService:
    sum = staticmethod(sum_metric)
    batch_sums = staticmethod(batch_metric_sums)
    pct_change = staticmethod(pct_change)
    paid_series = staticmethod(paid_series)
