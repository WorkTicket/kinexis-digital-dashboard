"""Microsoft Clarity connector — page-level UX metrics via Data Export API.

Uses the public Export API:
  GET https://www.clarity.ms/export-data/api/v1/project-live-insights
  Authorization: Bearer <project token>
  ?numOfDays=1|2|3&dimension1=URL

Lookback is 1–3 days (10 req/day). Daily sync accumulates history.
Bounce rate is derived from Traffic.PagesPerSessionPercentage (Clarity does
not export bounceRate): approx bounce = clamp(2 - pps, 0, 1).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.credentials import CredentialsDecryptError, decrypt_credentials, encrypt_credentials
from app.ds_status import mark_active, mark_error, mark_reauth_required
from app.models import AppSetting, DataSource, MetricDaily
from app.database import SessionLocal
from app.connectors.base import _sync_lock

logger = logging.getLogger(__name__)

CLARITY_EXPORT_URL = "https://www.clarity.ms/export-data/api/v1/project-live-insights"


def _settings_clarity_token(db: Session) -> str:
    from app.credentials import decrypt_secret

    row = db.query(AppSetting).filter(AppSetting.key == "clarity_api_token").first()
    raw = (row.value or "").strip() if row else ""
    return decrypt_secret(raw).strip() if raw else ""


def _normalize_page(value: str) -> str:
    """Normalize Clarity URL → path form so it joins GA4 landing_page dims."""
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return path
    if not raw.startswith("/"):
        return f"/{raw}"
    return raw


def _derive_bounce(pages_per_session: float) -> float:
    """Approximate bounce from pages/session (1.0 ≈ 100% bounce)."""
    try:
        pps = float(pages_per_session)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, 2.0 - pps))


def _parse_export_payload(data: Any) -> list[dict[str, Any]]:
    """Flatten Export API metric blocks into per-URL metric rows."""
    blocks = data if isinstance(data, list) else []
    by_url: dict[str, dict[str, float]] = {}

    for block in blocks:
        if not isinstance(block, dict):
            continue
        metric_name = (block.get("metricName") or "").strip()
        info = block.get("information") or []
        if not isinstance(info, list):
            continue
        for row in info:
            if not isinstance(row, dict):
                continue
            url_raw = row.get("URL") or row.get("Url") or row.get("url") or ""
            page = _normalize_page(str(url_raw))
            if not page:
                continue
            bucket = by_url.setdefault(page, {})

            if metric_name == "Traffic":
                sessions = float(row.get("totalSessionCount") or 0)
                bucket["sessions"] = sessions
                pps = row.get("PagesPerSessionPercentage")
                if pps is not None:
                    bucket["bounce_rate"] = _derive_bounce(float(pps))
                    bucket["pages_per_session"] = float(pps)
            elif metric_name == "Scroll Depth":
                # API may return average scroll depth 0–100 or 0–1
                depth = row.get("averageScrollDepth") or row.get("scrollDepth") or row.get("value")
                if depth is not None:
                    d = float(depth)
                    bucket["scroll_depth"] = d / 100.0 if d > 1.0 else d
            elif metric_name == "Rage Click Count":
                bucket["rage_click_count"] = float(
                    row.get("sessionsCount") or row.get("count") or row.get("value") or 0
                )
            elif metric_name == "Dead Click Count":
                bucket["dead_click_count"] = float(
                    row.get("sessionsCount") or row.get("count") or row.get("value") or 0
                )

    out: list[dict[str, Any]] = []
    for page, metrics in by_url.items():
        for metric_name, value in metrics.items():
            out.append({"page": page, "metric_name": metric_name, "value": float(value)})
    return out


def ensure_clarity_datasource(db: Session, client_id: int) -> Optional[DataSource]:
    """Wire Settings clarity_api_token into a per-client datasource when present."""
    token = _settings_clarity_token(db)
    existing = (
        db.query(DataSource)
        .filter(DataSource.client_id == client_id, DataSource.type == "clarity")
        .first()
    )
    if not token:
        return existing

    if existing:
        creds: dict = {}
        if existing.credentials_encrypted:
            try:
                creds = decrypt_credentials(existing.credentials_encrypted)
            except Exception:
                creds = {}
        if not creds.get("api_token"):
            creds["api_token"] = token
            existing.credentials_encrypted = encrypt_credentials(creds)
            if existing.status in ("pending", "error", "reauth_required"):
                existing.status = "pending"
            db.commit()
        return existing

    ds = DataSource(
        client_id=client_id,
        type="clarity",
        credentials_encrypted=encrypt_credentials({"api_token": token}),
        status="pending",
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


def sync_clarity(ds: DataSource) -> bool:
    """Pull last 1–3 days of URL-dimension Clarity insights into MetricDaily."""
    db = SessionLocal()
    try:
        fresh = db.query(DataSource).filter(DataSource.id == ds.id).first()
        if not fresh:
            return False

        api_token = ""
        if fresh.credentials_encrypted:
            try:
                creds = decrypt_credentials(fresh.credentials_encrypted)
                api_token = (creds.get("api_token") or creds.get("token") or "").strip()
            except CredentialsDecryptError as e:
                logger.error("DataSource %s: Clarity decrypt failed: %s", fresh.id, e)
                mark_reauth_required(fresh, str(e))
                db.commit()
                return False

        if not api_token:
            api_token = _settings_clarity_token(db)

        if not api_token:
            logger.error("DataSource %s: Missing Clarity API token", fresh.id)
            mark_error(fresh, "Missing Clarity API token")
            db.commit()
            return False

        # Prefer 3-day lookback; fall back to 1 if rate-limited or rejected.
        payload: Any = None
        last_error = ""
        with httpx.Client(timeout=45) as client:
            for days in (3, 1):
                resp = client.get(
                    CLARITY_EXPORT_URL,
                    headers={
                        "Authorization": f"Bearer {api_token}",
                        "Content-Type": "application/json",
                    },
                    params={"numOfDays": str(days), "dimension1": "URL"},
                )
                if resp.status_code == 429:
                    last_error = "Clarity daily rate limit exceeded (10/day)"
                    continue
                if resp.status_code in (401, 403):
                    mark_reauth_required(fresh, "Clarity token unauthorized — regenerate in Clarity Settings")
                    db.commit()
                    return False
                if resp.status_code >= 400:
                    last_error = f"Clarity API HTTP {resp.status_code}: {resp.text[:200]}"
                    continue
                payload = resp.json()
                break

        if payload is None:
            mark_error(fresh, last_error or "Clarity sync failed")
            db.commit()
            return False

        rows = _parse_export_payload(payload)
        if not rows:
            mark_error(fresh, "Clarity export returned 0 URL rows")
            db.commit()
            return False

        # Attribute the batch to "yesterday" (UTC lookback window midpoint).
        metric_date = date.today() - timedelta(days=1)
        window_start = metric_date - timedelta(days=2)

        with _sync_lock(fresh.client_id, "clarity"):
            db.query(MetricDaily).filter(
                MetricDaily.client_id == fresh.client_id,
                MetricDaily.source == "clarity",
                MetricDaily.date >= window_start,
                MetricDaily.date <= metric_date,
                MetricDaily.dimension_type == "page",
            ).delete(synchronize_session=False)

            for row in rows:
                db.add(
                    MetricDaily(
                        client_id=fresh.client_id,
                        source="clarity",
                        date=metric_date,
                        metric_name=row["metric_name"],
                        value=float(row["value"]),
                        dimension_type="page",
                        dimension_value=row["page"][:500],
                    )
                )

        mark_active(fresh)
        db.commit()
        logger.info(
            "Clarity sync complete for client %s: %s page-metric points",
            fresh.client_id,
            len(rows),
        )
        return True
    except Exception as e:
        db.rollback()
        logger.error("Clarity sync failed for DataSource %s: %s", ds.id, e)
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
