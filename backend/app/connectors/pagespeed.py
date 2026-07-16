import json
import logging
from datetime import datetime, date
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.credentials import CredentialsDecryptError, decrypt_credentials, encrypt_credentials
from app.ds_status import mark_active, mark_error, mark_reauth_required
from app.models import AppSetting, Client, DataSource, MetricDaily, PageSpeedFinding
from app.database import SessionLocal
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

PSI_BASE = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
PSI_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def _offender_from_item(item: Any) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    url = item.get("url") or item.get("source") or ""
    if isinstance(url, dict):
        url = url.get("url") or url.get("text") or ""
    if not url:
        return None
    out: dict[str, Any] = {"url": str(url)[:500]}
    if item.get("wastedBytes") is not None:
        out["wastedBytes"] = float(item["wastedBytes"])
    if item.get("wastedMs") is not None:
        out["wastedMs"] = float(item["wastedMs"])
    return out


def _persist_opportunity_findings(
    db: Session,
    *,
    client_id: int,
    url: str,
    strategy: str,
    audits: dict,
) -> None:
    """Store Lighthouse audits with details.items (score < 0.9). Replace prior rows for url+strategy."""
    db.query(PageSpeedFinding).filter(
        PageSpeedFinding.client_id == client_id,
        PageSpeedFinding.url == url,
        PageSpeedFinding.strategy == strategy,
    ).delete(synchronize_session=False)

    for audit_id, audit in (audits or {}).items():
        if not isinstance(audit, dict):
            continue
        score = audit.get("score")
        if score is None or score >= 0.9:
            continue
        details = audit.get("details") or {}
        items = details.get("items") if isinstance(details, dict) else None
        if not items or not isinstance(items, list):
            continue

        offenders: list[dict] = []
        for item in items:
            off = _offender_from_item(item)
            if off:
                offenders.append(off)
            if len(offenders) >= 3:
                break
        if not offenders:
            continue

        overall_ms = details.get("overallSavingsMs") if isinstance(details, dict) else None
        overall_bytes = details.get("overallSavingsBytes") if isinstance(details, dict) else None
        if overall_ms is None:
            overall_ms = sum(float(o.get("wastedMs") or 0) for o in offenders) or None
        if overall_bytes is None:
            overall_bytes = sum(float(o.get("wastedBytes") or 0) for o in offenders) or None

        db.add(
            PageSpeedFinding(
                client_id=client_id,
                url=url[:1000],
                strategy=strategy,
                audit_id=str(audit_id)[:100],
                title=(audit.get("title") or str(audit_id))[:255],
                savings_ms=float(overall_ms) if overall_ms is not None else None,
                savings_bytes=float(overall_bytes) if overall_bytes is not None else None,
                top_offenders_json=json.dumps(offenders),
                fetched_at=utcnow(),
            )
        )


def _settings_api_key(db: Session) -> str:
    from app.credentials import decrypt_secret

    row = db.query(AppSetting).filter(AppSetting.key == "pagespeed_api_key").first()
    raw = (row.value or "").strip() if row else ""
    return decrypt_secret(raw).strip() if raw else ""


def _normalize_site_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("sc-domain:"):
        raw = raw.replace("sc-domain:", "", 1)
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}/"


def _resolve_client_url(db: Session, client_id: int) -> str:
    """Best-effort homepage URL from GSC / existing PageSpeed / client name."""
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
            url = _normalize_site_url(str(creds.get(key) or ""))
            if url:
                return url
        urls = creds.get("urls") or []
        if isinstance(urls, list):
            for item in urls:
                url = _normalize_site_url(str(item or ""))
                if url:
                    return url

    client = db.query(Client).filter(Client.id == client_id).first()
    if client:
        return _normalize_site_url(client.name)
    return ""


def ensure_pagespeed_datasource(db: Session, client_id: int) -> Optional[DataSource]:
    """
    Wire Settings pagespeed_api_key into a per-client datasource.
    Creates one when missing; refreshes api_key/url on existing rows.
    """
    api_key = _settings_api_key(db)
    existing = (
        db.query(DataSource)
        .filter(DataSource.client_id == client_id, DataSource.type == "pagespeed")
        .first()
    )
    if not api_key:
        return existing

    site_url = _resolve_client_url(db, client_id)
    if existing:
        creds: dict = {}
        if existing.credentials_encrypted:
            try:
                creds = decrypt_credentials(existing.credentials_encrypted)
            except Exception:
                creds = {}
        changed = False
        if not creds.get("api_key"):
            creds["api_key"] = api_key
            changed = True
        if site_url and not (creds.get("site_url") or any(creds.get("urls") or [])):
            creds["site_url"] = site_url
            creds["urls"] = [site_url]
            changed = True
        elif site_url and not creds.get("urls"):
            creds["urls"] = [creds.get("site_url") or site_url]
            changed = True
        if changed:
            existing.credentials_encrypted = encrypt_credentials(creds)
            if existing.status == "error":
                existing.status = "pending"
            db.flush()
        return existing

    if not site_url:
        logger.info("PageSpeed: no URL for client %s — skip auto datasource", client_id)
        return None

    ds = DataSource(
        client_id=client_id,
        type="pagespeed",
        credentials_encrypted=encrypt_credentials(
            {"api_key": api_key, "site_url": site_url, "urls": [site_url]}
        ),
        status="pending",
    )
    db.add(ds)
    db.flush()
    logger.info("PageSpeed: auto-created datasource for client %s (%s)", client_id, site_url)
    return ds


def sync_pagespeed(ds: DataSource) -> bool:
    db_probe = SessionLocal()
    try:
        settings_key = _settings_api_key(db_probe)
    finally:
        db_probe.close()

    if not ds.credentials_encrypted and not settings_key:
        logger.error(f"DataSource {ds.id}: No credentials for PageSpeed sync")
        mark_error(ds, "Sync failed")
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    try:
        creds = decrypt_credentials(ds.credentials_encrypted) if ds.credentials_encrypted else {}
    except CredentialsDecryptError as e:
        logger.error("DataSource %s: PageSpeed decrypt failed: %s", ds.id, e)
        mark_reauth_required(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False
    api_key = (creds.get("api_key") or settings_key or "").strip()
    urls = creds.get("urls") or []
    if not urls:
        site = creds.get("site_url") or ""
        urls = [site] if site else []
    if (not urls or not any(urls)) and settings_key:
        # Last resort: derive from client name / GSC
        db_url = SessionLocal()
        try:
            derived = _resolve_client_url(db_url, ds.client_id)
            if derived:
                urls = [derived]
        finally:
            db_url.close()

    if not api_key:
        logger.error(f"DataSource {ds.id}: Missing api_key for PageSpeed")
        mark_error(ds, "Sync failed")
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    if not urls or not any(urls):
        logger.error(f"DataSource {ds.id}: No URLs configured for PageSpeed")
        mark_error(ds, "Sync failed")
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    try:
        db = SessionLocal()
        today = date.today()

        with httpx.Client(timeout=60) as client:
            for url in urls:
                if not url:
                    continue
                for strategy in ("mobile", "desktop"):
                    try:
                        resp = client.get(
                            PSI_BASE,
                            params={
                                "url": url,
                                "strategy": strategy,
                                "key": api_key,
                                "category": ["performance", "seo", "best-practices", "accessibility"],
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as e:
                        logger.warning(f"PageSpeed fetch failed for {url} ({strategy}): {e}")
                        continue

                    lighthouse = data.get("lighthouseResult", {})
                    categories = lighthouse.get("categories", {})
                    audits = lighthouse.get("audits", {})

                    score_map = {
                        "performance_score": categories.get("performance", {}).get("score", 0),
                        "seo_score": categories.get("seo", {}).get("score", 0),
                        "best_practices_score": categories.get("best-practices", {}).get("score", 0),
                        "accessibility_score": categories.get("accessibility", {}).get("score", 0),
                    }

                    for metric_name, score in score_map.items():
                        entry = MetricDaily(
                            client_id=ds.client_id,
                            source="pagespeed",
                            date=today,
                            metric_name=f"{metric_name}_{strategy}",
                            value=float(score * 100) if score else 0.0,
                            dimension_type="url",
                            dimension_value=url,
                        )
                        db.add(entry)

                    cwv_metrics = {
                        "largest_contentful_paint": "largest-contentful-paint",
                        "total_blocking_time": "total-blocking-time",
                        "cumulative_layout_shift": "cumulative-layout-shift",
                        "first_contentful_paint": "first-contentful-paint",
                        "speed_index": "speed-index",
                        "interactive": "interactive",
                    }

                    for metric_slug, audit_key in cwv_metrics.items():
                        audit = audits.get(audit_key, {})
                        numeric_value = audit.get("numericValue", 0)
                        if numeric_value:
                            entry = MetricDaily(
                                client_id=ds.client_id,
                                source="pagespeed",
                                date=today,
                                metric_name=f"{metric_slug}_{strategy}",
                                value=float(numeric_value),
                                dimension_type="url",
                                dimension_value=url,
                            )
                            db.add(entry)

                    try:
                        _persist_opportunity_findings(
                            db,
                            client_id=ds.client_id,
                            url=url,
                            strategy=strategy,
                            audits=audits,
                        )
                    except Exception as e:
                        logger.warning(
                            "PageSpeed findings persist failed for %s (%s): %s",
                            url,
                            strategy,
                            e,
                        )

        mark_active(ds)
        db.merge(ds)
        db.commit()
        logger.info(f"PageSpeed sync complete for client {ds.client_id}")
        return True

    except Exception as e:
        logger.error(f"PageSpeed sync failed for DataSource {ds.id}: {e}")
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
