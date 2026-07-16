import logging
from datetime import datetime, timedelta, date
from typing import Optional

import httpx
from sqlalchemy import and_

from app.credentials import CredentialsDecryptError, decrypt_credentials
from app.ds_status import mark_active, mark_error, mark_reauth_required
from app.models import DataSource, MetricDaily
from app.database import SessionLocal
from app.connectors.base import _sync_lock

logger = logging.getLogger(__name__)

BING_BASE = "https://ssl.bing.com/webmaster/api.svc/json"


def sync_bing(ds: DataSource) -> bool:
    if not ds.credentials_encrypted:
        logger.error(f"DataSource {ds.id}: No credentials for Bing sync")
        mark_error(ds, "Sync failed")
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    try:
        creds = decrypt_credentials(ds.credentials_encrypted)
    except CredentialsDecryptError as e:
        logger.error("DataSource %s: Bing decrypt failed: %s", ds.id, e)
        mark_reauth_required(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False
    api_key = creds.get("api_key")
    site_url = creds.get("site_url")

    if not api_key or not site_url:
        logger.error(f"DataSource {ds.id}: Missing api_key or site_url for Bing")
        mark_error(ds, "Sync failed")
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    try:
        today = date.today()
        lookback_start = today - timedelta(days=30)
        db = SessionLocal()
        with _sync_lock(ds.client_id, "bing"):
            # Deduplicate: delete existing Bing data for this client in the date window
            db.query(MetricDaily).filter(
            and_(
                MetricDaily.client_id == ds.client_id,
                MetricDaily.source == "bing",
                MetricDaily.date >= lookback_start,
                MetricDaily.date <= today,
            )
        ).delete(synchronize_session=False)

        headers = {"Content-Type": "application/json"}
        params = {"apikey": api_key}

        with httpx.Client(timeout=30) as client:
            # Query stats (clicks, impressions, CTR, position by query)
            try:
                q_resp = client.get(
                    f"{BING_BASE}/GetQueryStats",
                    headers=headers,
                    params={**params, "siteUrl": site_url, "dateRange": "lastMonth"},
                )
                if q_resp.status_code == 200:
                    data = q_resp.json()
                    query_stats = (
                        data.get("d", {}).get("results", [])
                        if "d" in data
                        else data.get("results", [])
                    )
                    for row in query_stats:
                        if isinstance(row, dict):
                            metrics = {
                                "clicks": row.get("Clicks", 0),
                                "impressions": row.get("Impressions", 0),
                                "ctr": row.get("CTR", 0),
                                "position": row.get("AveragePosition", 0),
                            }
                            query_text = row.get("Query", "")
                            for metric_name, value in metrics.items():
                                entry = MetricDaily(
                                    client_id=ds.client_id,
                                    source="bing",
                                    date=lookback_start,
                                    metric_name=metric_name,
                                    value=float(value) if value else 0.0,
                                    dimension_type="query",
                                    dimension_value=query_text,
                                )
                                db.add(entry)
                else:
                    logger.warning(
                        f"Bing GetQueryStats returned {q_resp.status_code} for DS {ds.id}"
                    )
            except Exception as e:
                logger.warning(f"Bing query stats fetch failed for DS {ds.id}: {e}")

            # Page stats
            try:
                p_resp = client.get(
                    f"{BING_BASE}/GetPageStats",
                    headers=headers,
                    params={**params, "siteUrl": site_url},
                )
                if p_resp.status_code == 200:
                    data = p_resp.json()
                    page_stats = (
                        data.get("d", {}).get("results", [])
                        if "d" in data
                        else data.get("results", [])
                    )
                    for row in page_stats:
                        if isinstance(row, dict):
                            page_url = row.get("Url", "")
                            metrics = {
                                "clicks": row.get("Clicks", 0),
                                "impressions": row.get("Impressions", 0),
                            }
                            for metric_name, value in metrics.items():
                                entry = MetricDaily(
                                    client_id=ds.client_id,
                                    source="bing",
                                    date=lookback_start,
                                    metric_name=metric_name,
                                    value=float(value) if value else 0.0,
                                    dimension_type="page",
                                    dimension_value=page_url,
                                )
                                db.add(entry)
            except Exception as e:
                logger.warning(f"Bing page stats fetch failed for DS {ds.id}: {e}")

            # Crawl info
            try:
                c_resp = client.get(
                    f"{BING_BASE}/GetCrawlStats",
                    headers=headers,
                    params={**params, "siteUrl": site_url},
                )
                if c_resp.status_code == 200:
                    data = c_resp.json()
                    crawl_data = data.get("d", data) if "d" in data else data
                    crawl_metrics = {
                        "crawl_pages_indexed": crawl_data.get("PagesIndexed", 0),
                        "crawl_pages_crawled": crawl_data.get("PagesCrawled", 0),
                        "crawl_errors": crawl_data.get("CrawlErrors", 0),
                    }
                    for metric_name, value in crawl_metrics.items():
                        entry = MetricDaily(
                            client_id=ds.client_id,
                            source="bing",
                            date=lookback_start,
                            metric_name=metric_name,
                            value=float(value) if value else 0.0,
                        )
                        db.add(entry)
            except Exception as e:
                logger.warning(f"Bing crawl stats fetch failed for DS {ds.id}: {e}")

        mark_active(ds)
        db.merge(ds)
        db.commit()
        logger.info(f"Bing sync complete for client {ds.client_id}")
        return True

    except Exception as e:
        logger.error(f"Bing sync failed for DataSource {ds.id}: {e}")
        mark_error(ds, str(e))
        db2 = SessionLocal()
        try:
            db2.merge(ds)
            db2.commit()
        finally:
            db2.close()
        return False
    finally:
        if 'db' in locals():
            db.close()
