"""Shared helpers for ads connectors → MetricDaily (campaign dimension)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.ds_status import mark_active, mark_error
from app.database import SessionLocal
from app.models import DataSource, MetricDaily
from app.connectors.base import _sync_lock

logger = logging.getLogger(__name__)

ADS_METRICS = ("impressions", "clicks", "cost", "conversions", "conversion_value")
PAID_SOURCES = ("ads_csv", "google_ads", "meta_ads")
PAID_ALIAS_SOURCE = "paid"


def sum_paid_metric(
    db: Session,
    client_id: int,
    metric_name: str,
    start: date,
    end: date,
) -> float:
    """Sum a campaign metric across ads_csv + google_ads + meta_ads."""
    if metric_name not in ADS_METRICS:
        return 0.0
    val = (
        db.query(func.sum(MetricDaily.value))
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source.in_(PAID_SOURCES),
                MetricDaily.metric_name == metric_name,
                MetricDaily.dimension_type == "campaign",
                MetricDaily.date >= start,
                MetricDaily.date <= end,
            )
        )
        .scalar()
    )
    return float(val or 0)


def paid_daily_series(
    db: Session,
    client_id: int,
    metric_name: str,
    start: date,
    end: date,
) -> list[float]:
    """Per-day paid totals (all PAID_SOURCES) for variance-based confidence."""
    if metric_name not in ADS_METRICS:
        return []
    rows = (
        db.query(MetricDaily.date, MetricDaily.value)
        .filter(
            and_(
                MetricDaily.client_id == client_id,
                MetricDaily.source.in_(PAID_SOURCES),
                MetricDaily.metric_name == metric_name,
                MetricDaily.dimension_type == "campaign",
                MetricDaily.date >= start,
                MetricDaily.date <= end,
            )
        )
        .order_by(MetricDaily.date.asc())
        .all()
    )
    by_day: dict[date, float] = {}
    for d, v in rows:
        by_day[d] = by_day.get(d, 0.0) + float(v or 0)
    return [by_day[d] for d in sorted(by_day.keys())]


def persist_campaign_metrics(
    ds: DataSource,
    source: str,
    rows: Iterable[dict],
) -> bool:
    """
    Persist daily campaign metrics.

    Each row: {date: date, campaign: str, impressions, clicks, cost, conversions, conversion_value}
    Replaces MetricDaily for this client+source over the min..max date range.
    """
    rows_out: list[MetricDaily] = []
    min_d: Optional[date] = None
    max_d: Optional[date] = None
    parsed = 0

    for row in rows:
        d = row.get("date")
        if not isinstance(d, date):
            continue
        campaign = (str(row.get("campaign") or "Unknown")).strip() or "Unknown"
        min_d = d if min_d is None else min(min_d, d)
        max_d = d if max_d is None else max(max_d, d)
        for metric in ADS_METRICS:
            try:
                val = float(row.get(metric) or 0)
            except (TypeError, ValueError):
                val = 0.0
            rows_out.append(
                MetricDaily(
                    client_id=ds.client_id,
                    source=source,
                    date=d,
                    metric_name=metric,
                    value=val,
                    dimension_type="campaign",
                    dimension_value=campaign[:500],
                )
            )
        parsed += 1

    if not rows_out or min_d is None or max_d is None:
        logger.error("DataSource %s (%s): no valid campaign rows", ds.id, source)
        _persist_error(ds, f"{source}: no valid campaign rows")
        return False

    db = SessionLocal()
    try:
        with _sync_lock(ds.client_id, source):
            # Only replace campaign rows — search_term / other dims persist separately
            db.query(MetricDaily).filter(
                MetricDaily.client_id == ds.client_id,
                MetricDaily.source == source,
                MetricDaily.dimension_type == "campaign",
                MetricDaily.date >= min_d,
                MetricDaily.date <= max_d,
            ).delete(synchronize_session=False)
            for entry in rows_out:
                db.add(entry)
            mark_active(ds)
            db.merge(ds)
            db.commit()
        logger.info(
            "%s sync complete for client %s: %s campaigns → %s metric points",
            source,
            ds.client_id,
            parsed,
            len(rows_out),
        )
        return True
    except Exception as e:
        db.rollback()
        logger.error("%s sync failed for DataSource %s: %s", source, ds.id, e)
        _persist_error(ds, str(e))
        return False
    finally:
        db.close()


def persist_dim_metrics(
    ds: DataSource,
    source: str,
    rows: Iterable[dict],
    *,
    dim_type: str,
    dim_key: str,
    extra_metrics: tuple[str, ...] = (),
) -> int:
    """Persist dimensioned ads metrics (search_term, placement, ad_creative, …)."""
    metric_names = tuple(dict.fromkeys((*ADS_METRICS, *extra_metrics)))
    rows_out: list[MetricDaily] = []
    min_d: Optional[date] = None
    max_d: Optional[date] = None
    for row in rows:
        d = row.get("date")
        if not isinstance(d, date):
            continue
        dim_val = (str(row.get(dim_key) or "")).strip()
        if not dim_val:
            continue
        min_d = d if min_d is None else min(min_d, d)
        max_d = d if max_d is None else max(max_d, d)
        for metric in metric_names:
            try:
                val = float(row.get(metric) or 0)
            except (TypeError, ValueError):
                val = 0.0
            rows_out.append(
                MetricDaily(
                    client_id=ds.client_id,
                    source=source,
                    date=d,
                    metric_name=metric,
                    value=val,
                    dimension_type=dim_type,
                    dimension_value=dim_val[:500],
                )
            )
    if not rows_out or min_d is None or max_d is None:
        return 0
    db = SessionLocal()
    try:
        with _sync_lock(ds.client_id, f"{source}:{dim_type}"):
            db.query(MetricDaily).filter(
                MetricDaily.client_id == ds.client_id,
                MetricDaily.source == source,
                MetricDaily.dimension_type == dim_type,
                MetricDaily.date >= min_d,
                MetricDaily.date <= max_d,
            ).delete(synchronize_session=False)
            for entry in rows_out:
                db.add(entry)
            db.commit()
        return len(rows_out)
    except Exception as e:
        db.rollback()
        logger.error("%s persist failed for DataSource %s: %s", dim_type, ds.id, e)
        return 0
    finally:
        db.close()


def persist_search_term_metrics(
    ds: DataSource,
    source: str,
    rows: Iterable[dict],
) -> int:
    """Persist search-term waste metrics (dimension_type=search_term)."""
    normalized = []
    for row in rows:
        r = dict(row)
        if not r.get("search_term"):
            r["search_term"] = r.get("term") or ""
        normalized.append(r)
    return persist_dim_metrics(
        ds, source, normalized, dim_type="search_term", dim_key="search_term"
    )


def _persist_error(ds: DataSource, message: str) -> None:
    mark_error(ds, message)
    db = SessionLocal()
    try:
        db.merge(ds)
        db.commit()
    finally:
        db.close()
