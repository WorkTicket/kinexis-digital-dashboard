"""Chrome UX Report (CrUX) connector — real-user Core Web Vitals field data.

Google ranks on field data (28-day rolling window from actual Chrome users),
not lab scores from PageSpeed Insights. This connector fetches URL-level
CrUX data via the PageSpeed Insights API (loadingExperience) and stores
per-URL CruxSnapshot rows + MetricDaily rollups.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional
from urllib.parse import urlparse

import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AppSetting, Client, CruxSnapshot, DataSource, MetricDaily
from app.ds_status import mark_active, mark_error
from app.connectors.base import _sync_lock
from app.credentials import decrypt_credentials

logger = logging.getLogger(__name__)

PSI_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def _settings_api_key(db: Session) -> str:
    from app.credentials import decrypt_secret
    import os

    row = db.query(AppSetting).filter(AppSetting.key == "pagespeed_api_key").first()
    raw = (row.value or "").strip() if row else ""
    if raw:
        return decrypt_secret(raw).strip()
    return (os.getenv("PAGESPEED_API_KEY") or "").strip()


def fetch_crux_for_url(
    url: str, strategy: str = "MOBILE", api_key: str = ""
) -> Optional[dict]:
    """Fetch CrUX field data for a URL via PageSpeed Insights API."""
    params = {
        "url": url,
        "strategy": strategy,
        "category": "PERFORMANCE",
    }
    if api_key:
        params["key"] = api_key
    try:
        resp = requests.get(PSI_API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("CrUX fetch failed for %s: %s", url, e)
        return None

    loading = data.get("loadingExperience", {})
    if not loading or str(loading.get("id", "")).startswith("LAB_"):
        return None

    metrics = loading.get("metrics", {})
    if not metrics:
        return None

    # Persist form_factor as PHONE|DESKTOP to match CruxSnapshot convention.
    form = "PHONE" if strategy.upper() == "MOBILE" else "DESKTOP"
    result = {
        "form_factor": form,
        "lcp_p75": _extract_p75(metrics, "LARGEST_CONTENTFUL_PAINT_MS"),
        "inp_p75": _extract_p75(metrics, "INTERACTION_TO_NEXT_PAINT"),
        "cls_p75": _extract_p75(metrics, "CUMULATIVE_LAYOUT_SHIFT_SCORE"),
        "ttfb_p75": _extract_p75(metrics, "EXPERIMENTAL_TIME_TO_FIRST_BYTE"),
    }

    for metric_key, prefix in [
        ("LARGEST_CONTENTFUL_PAINT_MS", "lcp"),
        ("INTERACTION_TO_NEXT_PAINT", "inp"),
        ("CUMULATIVE_LAYOUT_SHIFT_SCORE", "cls"),
    ]:
        m = metrics.get(metric_key, {})
        dist = m.get("distributions", [])
        if not dist:
            continue
        # First bucket is typically "GOOD"
        good = dist[0] if dist else None
        if good and good.get("proportion") is not None:
            result[f"{prefix}_good_pct"] = round(float(good["proportion"]) * 100, 1)

    return result


def _extract_p75(metrics: dict, key: str) -> Optional[float]:
    m = metrics.get(key, {})
    return m.get("percentile") if m else None


def top_urls_for_crux(db: Session, client_id: int, limit: int = 5) -> list[str]:
    """Pick highest-click GSC pages + homepage for CrUX sampling."""
    today = date.today()
    start = today - timedelta(days=28)
    rows = (
        db.query(
            MetricDaily.dimension_value,
            func.sum(MetricDaily.value).label("clicks"),
        )
        .filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == "gsc",
            MetricDaily.metric_name == "clicks",
            MetricDaily.dimension_type == "page",
            MetricDaily.date >= start,
            MetricDaily.dimension_value.isnot(None),
            MetricDaily.dimension_value != "",
        )
        .group_by(MetricDaily.dimension_value)
        .order_by(func.sum(MetricDaily.value).desc())
        .limit(limit)
        .all()
    )

    urls: list[str] = []
    for row in rows:
        raw = (row.dimension_value or "").strip()
        if not raw:
            continue
        if raw.startswith(("http://", "https://")):
            urls.append(raw)
        else:
            # Prefer absolute when we can resolve origin from GSC site
            origin = _client_origin(db, client_id)
            if origin:
                path = raw if raw.startswith("/") else f"/{raw}"
                urls.append(f"{origin.rstrip('/')}{path}")
            else:
                urls.append(raw if raw.startswith("http") else f"https://{raw.lstrip('/')}")

    if not urls:
        origin = _client_origin(db, client_id)
        if origin:
            urls.append(origin if origin.endswith("/") else f"{origin}/")
    return urls[:limit]


def _client_origin(db: Session, client_id: int) -> str:
    sources = (
        db.query(DataSource)
        .filter(DataSource.client_id == client_id, DataSource.type.in_(["gsc", "pagespeed", "cloudflare"]))
        .all()
    )
    for ds in sources:
        if not ds.credentials_encrypted:
            continue
        try:
            creds = decrypt_credentials(ds.credentials_encrypted)
        except Exception:
            continue
        for key in ("site_url", "url"):
            raw = str(creds.get(key) or "").strip()
            if raw.startswith("sc-domain:"):
                raw = f"https://{raw.replace('sc-domain:', '', 1)}"
            if not raw.startswith(("http://", "https://")):
                continue
            parsed = urlparse(raw)
            if parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
    client = db.query(Client).filter(Client.id == client_id).first()
    if client and "." in (client.name or ""):
        name = client.name.strip()
        if not name.startswith("http"):
            name = f"https://{name}"
        parsed = urlparse(name)
        if parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def sync_crux_for_client(
    db: Session, client_id: int, urls: list[str] | None = None, strategy: str = "MOBILE"
) -> int:
    """Fetch CrUX data for URLs and persist CruxSnapshot + MetricDaily rows."""
    api_key = _settings_api_key(db)
    if not api_key:
        logger.info("CrUX sync skipped for client %s — no PageSpeed API key", client_id)
        return 0

    if not urls:
        urls = top_urls_for_crux(db, client_id, limit=5)
    if not urls:
        return 0

    stored = 0
    for url in urls:
        data = fetch_crux_for_url(url, strategy, api_key=api_key)
        if not data:
            continue

        snapshot = CruxSnapshot(
            client_id=client_id,
            url=url[:1000],
            form_factor=data.get("form_factor") or "PHONE",
            lcp_p75=data.get("lcp_p75"),
            inp_p75=data.get("inp_p75"),
            cls_p75=data.get("cls_p75"),
            ttfb_p75=data.get("ttfb_p75"),
            lcp_good_pct=data.get("lcp_good_pct"),
            inp_good_pct=data.get("inp_good_pct"),
            cls_good_pct=data.get("cls_good_pct"),
        )
        db.add(snapshot)
        stored += 1

    if stored == 0:
        db.commit()
        return 0

    db.flush()
    latest = (
        db.query(CruxSnapshot)
        .filter(CruxSnapshot.client_id == client_id)
        .order_by(CruxSnapshot.fetched_at.desc())
        .first()
    )
    if latest:
        for metric, value in [
            ("crux_lcp_ms", latest.lcp_p75),
            ("crux_inp_ms", latest.inp_p75),
            ("crux_cls", latest.cls_p75),
        ]:
            if value is not None:
                _upsert_metric(db, client_id, "crux", metric, float(value))

    ds = ensure_crux_datasource(db, client_id)
    mark_active(ds)
    db.commit()
    logger.info("CrUX sync complete for client %s: %s URLs", client_id, stored)
    return stored


def sync_crux(ds: DataSource) -> bool:
    """Datasource sync entrypoint for CrUX (uses PageSpeed API key from Settings)."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        fresh = db.query(DataSource).filter(DataSource.id == ds.id).first()
        if not fresh:
            return False

        api_key = _settings_api_key(db)
        if not api_key:
            # Not an auth failure — agent hasn't configured the key yet.
            fresh.status = "pending"
            fresh.last_error = (
                "Add a PageSpeed Insights API key in Settings → API keys, then Sync. "
                "CrUX uses the same key as PageSpeed."
            )[:500]
            db.commit()
            return False

        n = sync_crux_for_client(db, fresh.client_id)
        if n <= 0:
            # Key present but Google has no field data (common on low-traffic sites).
            fresh.status = "partial"
            fresh.last_error = (
                "PageSpeed key works, but Chrome UX Report has no field data yet for this site "
                "(needs enough real Chrome users). Lab PageSpeed can still sync separately."
            )[:500]
            db.commit()
            return False
        return True
    except Exception as e:
        db.rollback()
        logger.error("CrUX sync failed for DataSource %s: %s", ds.id, e)
        try:
            fresh = db.query(DataSource).filter(DataSource.id == ds.id).first()
            if fresh:
                mark_error(fresh, str(e))
                db.commit()
        except Exception:
            db.rollback()
        return False
    finally:
        db.close()


def _upsert_metric(db, client_id: int, source: str, metric_name: str, value: float):
    today = date.today()
    with _sync_lock(client_id, source):
        db.query(MetricDaily).filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == source,
            MetricDaily.metric_name == metric_name,
            MetricDaily.date == today,
        ).delete(synchronize_session=False)
        db.add(
            MetricDaily(
                client_id=client_id,
                source=source,
                date=today,
                metric_name=metric_name,
                value=value,
                dimension_type="",
                dimension_value="",
            )
        )


def ensure_crux_datasource(db: Session, client_id: int) -> DataSource:
    ds = (
        db.query(DataSource)
        .filter(DataSource.client_id == client_id, DataSource.type == "crux")
        .first()
    )
    if not ds:
        ds = DataSource(client_id=client_id, type="crux", status="pending")
        db.add(ds)
        db.flush()
    return ds
