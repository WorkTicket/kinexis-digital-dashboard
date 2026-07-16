from datetime import date, datetime, timedelta
from typing import Optional
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.database import get_db, SessionLocal
from app.models import MetricDaily, Client, DataSource
from app.connectors.gsc import sync_gsc
from app.connectors.ga4 import sync_ga4
from app.connectors.cloudflare import sync_cloudflare
from app.connectors.pagespeed import sync_pagespeed, ensure_pagespeed_datasource
from app.connectors.bing import sync_bing
from app.connectors.hubspot import sync_hubspot
from app.connectors.ads_csv import sync_ads_csv
from app.connectors.google_ads import sync_google_ads
from app.connectors.meta_ads import sync_meta_ads
from app.connectors.gbp import sync_gbp
from app.connectors.backlinks import sync_backlinks
from app.connectors.clarity import sync_clarity, ensure_clarity_datasource
from app.connectors.crux import sync_crux, ensure_crux_datasource, sync_crux_for_client
from app.insight_service import generate_insights_for_client
from app.opportunities import build_opportunities
from app.timeutil import utcnow
from app.dimensions import SITE_TOTAL_DIMENSION

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])

# Dashboard default lookback — KPIs use 14d; charts benefit from longer history.
_DEFAULT_METRICS_DAYS = 400

_SYNC_FNS = {
    "gsc": sync_gsc,
    "ga4": sync_ga4,
    "cloudflare": sync_cloudflare,
    "clarity": sync_clarity,
    "pagespeed": sync_pagespeed,
    "bing": sync_bing,
    "hubspot": sync_hubspot,
    "ads_csv": sync_ads_csv,
    "google_ads": sync_google_ads,
    "meta_ads": sync_meta_ads,
    "gbp": sync_gbp,
    "backlinks": sync_backlinks,
    "crux": sync_crux,
}


def _datasource_health(db: Session, client_id: int) -> list[dict]:
    rows = db.query(DataSource).filter(DataSource.client_id == client_id).all()
    return [
        {
            "id": ds.id,
            "type": ds.type,
            "status": ds.status or "pending",
            "last_synced_at": ds.last_synced_at.isoformat() if ds.last_synced_at else None,
            "last_error": getattr(ds, "last_error", None),
        }
        for ds in rows
    ]


def _dedupe_datasources(db: Session, client_id: int) -> list[DataSource]:
    """Keep one row per type (prefer synced/active, then newest id). Drop extras."""
    rows = (
        db.query(DataSource)
        .filter(DataSource.client_id == client_id)
        .order_by(DataSource.id.asc())
        .all()
    )
    keep: dict[str, DataSource] = {}
    drop: list[DataSource] = []

    def _rank(ds: DataSource) -> tuple:
        status = (ds.status or "").lower()
        # Prefer working sources over error stubs when collapsing duplicates
        if status in ("error", "failed"):
            status_score = 0
        elif status == "active" or ds.last_synced_at:
            status_score = 2
        else:
            status_score = 1
        ts = ds.last_synced_at.timestamp() if ds.last_synced_at else 0
        has_creds = 1 if ds.credentials_encrypted else 0
        return (status_score, has_creds, ts, ds.id)

    for ds in rows:
        key = (ds.type or "").lower()
        prev = keep.get(key)
        if prev is None:
            keep[key] = ds
            continue
        if _rank(ds) > _rank(prev):
            drop.append(prev)
            keep[key] = ds
        else:
            drop.append(ds)

    if drop:
        for ds in drop:
            logger.info(
                "Removing duplicate DataSource %s (%s) for client %s",
                ds.id,
                ds.type,
                client_id,
            )
            db.delete(ds)
        db.commit()

    return list(keep.values())


@router.get("/")
def get_metrics(
    client_id: int = Query(...),
    source: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    metric_name: Optional[str] = Query(None),
    site_totals_only: bool = Query(
        True,
        description="Return one dimension per multi-dim source (avoids 4× GSC/Bing rows).",
    ),
    days: Optional[int] = Query(
        None,
        ge=7,
        le=365,
        description="Lookback window ending today. Ignored when start_date is set.",
    ),
    db: Session = Depends(get_db),
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Default to a bounded window so dashboards never pull unbounded history.
    effective_start = start_date
    if effective_start is None:
        lookback = days if days is not None else _DEFAULT_METRICS_DAYS
        effective_start = date.today() - timedelta(days=lookback)

    filters = [MetricDaily.client_id == client_id, MetricDaily.date >= effective_start]
    if source:
        filters.append(MetricDaily.source == source)
    if end_date:
        filters.append(MetricDaily.date <= end_date)
    if metric_name:
        filters.append(MetricDaily.metric_name == metric_name)

    if site_totals_only:
        # Keep empty-string / NULL site totals, or the preferred dimension per source.
        # Writers normalize NULL → "" (connectors.base.normalize_dimension).
        empty_dim = or_(
            MetricDaily.dimension_type.is_(None),
            MetricDaily.dimension_type == "",
        )
        dim_clauses = [empty_dim]
        for src, dim in SITE_TOTAL_DIMENSION.items():
            if dim is None:
                dim_clauses.append(and_(MetricDaily.source == src, empty_dim))
            else:
                dim_clauses.append(
                    and_(
                        MetricDaily.source == src,
                        or_(MetricDaily.dimension_type == dim, empty_dim),
                    )
                )
        # Sources not in SITE_TOTAL_DIMENSION (e.g. hubspot) — include all dims
        multi_sources = list(SITE_TOTAL_DIMENSION.keys())
        dim_clauses.append(~MetricDaily.source.in_(multi_sources))
        filters.append(or_(*dim_clauses))

    metrics = (
        db.query(MetricDaily)
        .filter(and_(*filters))
        .order_by(MetricDaily.date.desc(), MetricDaily.metric_name)
        .limit(50_000)
        .all()
    )
    return metrics


@router.get("/health/{client_id}")
def get_connector_health(client_id: int, db: Session = Depends(get_db)):
    """Per-connector sync health for a client."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    sources = _datasource_health(db, client_id)
    errors = [s for s in sources if (s["status"] or "").lower() in ("error", "failed", "reauth_required")]
    latest = None
    for s in sources:
        if s["last_synced_at"] and (latest is None or s["last_synced_at"] > latest):
            latest = s["last_synced_at"]
    return {
        "client_id": client_id,
        "last_synced_at": latest,
        "has_errors": len(errors) > 0,
        "sources": sources,
    }


@router.post("/sync/{client_id}")
def sync_client_metrics(
    client_id: int,
    background_tasks: BackgroundTasks,
    background: bool = Query(False, description="If true, queue sync and return immediately"),
    db: Session = Depends(get_db),
):
    """Sync metrics for one client. Pass background=true to queue and return immediately."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if background:

        def _job(cid: int = client_id):
            session = SessionLocal()
            try:
                run_sync_client(cid, session)
            except Exception as e:
                logger.exception("Background sync failed for client %s: %s", cid, e)
            finally:
                session.close()

        background_tasks.add_task(_job)
        return {
            "client_id": client_id,
            "queued": True,
            "message": "Sync started in background",
        }

    return run_sync_client(client_id, db)


def run_sync_client(client_id: int, db: Session):
    try:
        ensure_pagespeed_datasource(db, client_id)
        ensure_clarity_datasource(db, client_id)
        from app.connectors.crux import _settings_api_key

        if _settings_api_key(db):
            ensure_crux_datasource(db, client_id)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("Datasource auto-wire failed for client %s: %s", client_id, e)

    datasources = _dedupe_datasources(db, client_id)
    if not datasources:
        logger.warning("No data sources configured for client %s", client_id)
        return {"client_id": client_id, "results": {}, "sources": [], "message": "No data sources configured"}

    results = {}
    any_ok = False
    for ds in datasources:
        sync_fn = _SYNC_FNS.get(ds.type)
        if not sync_fn:
            results[ds.type] = "skipped (unknown source type)"
            continue
        try:
            ok = sync_fn(ds)
        except Exception as e:
            from app.credentials import CredentialsDecryptError
            from app.ds_status import mark_reauth_required

            if isinstance(e, CredentialsDecryptError):
                logger.warning(
                    "Sync %s for client %s: credentials decrypt failed — reauth required",
                    ds.type,
                    client_id,
                )
                fresh = db.query(DataSource).filter(DataSource.id == ds.id).first()
                if fresh:
                    mark_reauth_required(fresh, str(e))
                    db.commit()
                ok = False
            else:
                logger.warning(
                    "Sync %s for client %s raised: %s", ds.type, client_id, e
                )
                ok = False
        results[ds.type] = "ok" if ok else "failed"
        if ok:
            any_ok = True

    insights_created = 0
    new_insights = []
    crawl_pages = 0
    if any_ok:
        try:
            from app.connectors.site_crawl import ensure_crawl_for_client

            crawl_result = ensure_crawl_for_client(db, client_id, max_pages=25)
            crawl_pages = int(crawl_result.get("crawled") or 0)
        except Exception as e:
            logger.warning("Site crawl after sync failed for client %s: %s", client_id, e)

        try:
            sync_crux_for_client(db, client_id)
        except Exception as e:
            logger.warning("CrUX sync after client sync failed for client %s: %s", client_id, e)

        created = generate_insights_for_client(db, client_id)
        insights_created = len(created)
        new_insights = [
            {"id": i.id, "type": i.type, "severity": i.severity, "message": i.message}
            for i in created
        ]

    serp_snaps = 0
    try:
        from app.connectors.serp import ensure_serp_for_flagged_queries, serp_enabled

        if serp_enabled():
            snaps = ensure_serp_for_flagged_queries(db, client_id)
            serp_snaps = len(snaps)
            from app.connectors.sov import write_sov_presence

            write_sov_presence(db, client_id)
    except Exception as e:
        logger.warning("SERP refresh after sync failed for client %s: %s", client_id, e)

    sources = _datasource_health(db, client_id)
    return {
        "client_id": client_id,
        "synced_at": utcnow().isoformat(),
        "results": results,
        "sources": sources,
        "insights_created": insights_created,
        "new_insights": new_insights,
        "serp_snapshots": serp_snaps,
        "crawl_pages": crawl_pages,
    }


@router.post("/sync-all")
def sync_all_client_metrics(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Queue sync for every non-archived client that has at least one datasource."""
    clients = (
        db.query(Client)
        .filter((Client.archived == False) | (Client.archived.is_(None)))  # noqa: E712
        .order_by(Client.name)
        .all()
    )
    ids = [c.id for c in clients]

    def _job(client_ids: list[int] = ids):
        for cid in client_ids:
            session = SessionLocal()
            try:
                run_sync_client(cid, session)
            except Exception as e:
                logger.warning("sync-all failed for client %s: %s", cid, e)
            finally:
                session.close()

    background_tasks.add_task(_job)
    return {
        "queued": True,
        "client_count": len(ids),
        "client_ids": ids,
        "message": f"Queued sync for {len(ids)} clients",
    }


@router.get("/opportunities/{client_id}")
def get_opportunities(
    client_id: int,
    days: int = Query(28, ge=7, le=90),
    db: Session = Depends(get_db),
):
    """Query/page opportunity tables for the data explorer."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return build_opportunities(db, client_id, days=days)
