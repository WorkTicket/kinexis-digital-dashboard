"""Backlink profile importer — ingests CSV/JSON exports from Ahrefs, SEMrush, or Moz.

Stores referring domain counts, domain rating, toxic scores, and link velocity
so the insight engine can correlate backlink changes with ranking movements.

Usage: User uploads a backlink CSV through the UI. The connector normalizes fields
and stores snapshots keyed by domain + fetch date.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import BacklinkSnapshot, MetricDaily, DataSource
from app.ds_status import mark_active, mark_error
from app.connectors.base import _sync_lock

logger = logging.getLogger(__name__)

CSV_COLUMN_MAP = {
    # Ahrefs export columns
    "Referring Domains": "referring_domains",
    "Total Backlinks": "total_backlinks",
    "Domain Rating": "domain_rating",
    "DR": "domain_rating",
    "New Links (30d)": "new_links_30d",
    "Lost Links (30d)": "lost_links_30d",
    "Dofollow %": "dofollow_ratio",
    "Top Anchor": "top_anchor_text",
    "Toxic Score": "toxic_score",
    # SEMrush columns
    "Referring Domains": "referring_domains",
    "Backlinks": "total_backlinks",
    "Authority Score": "domain_rating",
    "New": "new_links_30d",
    "Lost": "lost_links_30d",
    "Follow %": "dofollow_ratio",
}


def import_backlinks_csv(db: Session, client_id: int, csv_content: str) -> int:
    """Parse a backlink CSV export and store snapshot rows. Returns count stored."""
    reader = csv.DictReader(io.StringIO(csv_content))
    if not reader.fieldnames:
        raise ValueError("CSV file is empty or has no headers")

    field_map = _build_field_map(reader.fieldnames)
    # Full-profile replace: a CSV export is the current book of domains.
    db.query(BacklinkSnapshot).filter(BacklinkSnapshot.client_id == client_id).delete(
        synchronize_session=False
    )
    stored = 0
    for row in reader:
        if not row.get("Domain") and not row.get("URL") and not row.get("Target"):
            continue
        domain = (row.get("Domain") or row.get("URL") or row.get("Target") or "").strip()
        if not domain:
            continue

        snapshot = BacklinkSnapshot(
            client_id=client_id,
            domain=domain,
            referring_domains=_int_or(row, field_map, "referring_domains", 0),
            total_backlinks=_int_or(row, field_map, "total_backlinks", 0),
            domain_rating=_float_or(row, field_map, "domain_rating"),
            toxic_score=_int_or(row, field_map, "toxic_score", 0),
            new_links_30d=_int_or(row, field_map, "new_links_30d", 0),
            lost_links_30d=_int_or(row, field_map, "lost_links_30d", 0),
            dofollow_ratio=_float_or(row, field_map, "dofollow_ratio"),
            top_anchor_text=row.get("Anchor") or row.get("Top Anchor") or "",
        )
        db.add(snapshot)
        stored += 1

    # Write aggregated metrics to MetricDaily for charting
    today = date.today()
    db.flush()
    _write_backlink_metrics(db, client_id, today)
    db.commit()
    return stored


def _build_field_map(headers: list[str]) -> dict[str, str]:
    """Map CSV column names to our internal field names."""
    fm: dict[str, str] = {}
    for h in headers:
        cleaned = h.strip()
        if cleaned in CSV_COLUMN_MAP:
            fm[CSV_COLUMN_MAP[cleaned]] = cleaned
        # Also try case-insensitive
        for k, v in CSV_COLUMN_MAP.items():
            if k.lower() == cleaned.lower():
                fm[v] = cleaned
                break
    return fm


def _int_or(row: dict, field_map: dict, key: str, default: int) -> int:
    col = field_map.get(key)
    if not col:
        return default
    try:
        val = row.get(col, "").replace(",", "").replace("%", "").strip()
        return int(float(val)) if val else default
    except (ValueError, TypeError):
        return default


def _float_or(row: dict, field_map: dict, key: str) -> Optional[float]:
    col = field_map.get(key)
    if not col:
        return None
    try:
        val = row.get(col, "").replace(",", "").replace("%", "").strip()
        return float(val) if val else None
    except (ValueError, TypeError):
        return None


def _write_backlink_metrics(db: Session, client_id: int, today: date):
    """Aggregate current backlink profile into MetricDaily for portfolio charts."""
    db.flush()
    snaps = (
        db.query(BacklinkSnapshot)
        .filter(BacklinkSnapshot.client_id == client_id)
        .all()
    )
    if not snaps:
        return

    # Batch by calendar day of the newest fetch — avoids dropping same-import
    # rows that differ only by microsecond timestamps.
    dated = [s for s in snaps if s.fetched_at is not None]
    if dated:
        latest_day = max(s.fetched_at for s in dated).date()
        batch = [s for s in dated if s.fetched_at.date() == latest_day]
    else:
        batch = snaps

    metrics = {
        "referring_domains": float(sum(s.referring_domains or 0 for s in batch)),
        "toxic_backlinks": float(
            sum(s.total_backlinks or 0 for s in batch if (s.toxic_score or 0) >= 30)
        ),
        "new_links_30d": float(sum(s.new_links_30d or 0 for s in batch)),
        "lost_links_30d": float(sum(s.lost_links_30d or 0 for s in batch)),
    }

    # Delete existing backlinks metrics for today, then insert (avoids race)
    with _sync_lock(client_id, "backlinks"):
        db.query(MetricDaily).filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == "backlinks",
            MetricDaily.date == today,
        ).delete(synchronize_session=False)

        for metric_name, value in metrics.items():
            db.add(
                MetricDaily(
                    client_id=client_id,
                    source="backlinks",
                    date=today,
                    metric_name=metric_name,
                    value=value,
                    dimension_type="",
                    dimension_value="",
                )
            )


def ensure_backlinks_datasource(db: Session, client_id: int) -> DataSource:
    ds = db.query(DataSource).filter(
        DataSource.client_id == client_id,
        DataSource.type == "backlinks",
    ).first()
    if not ds:
        ds = DataSource(client_id=client_id, type="backlinks", status="pending")
        db.add(ds)
        db.commit()
    return ds


def fetch_backlinks_live_api(db: Session, client_id: int, creds: dict) -> int:
    """Live backlink overview via Ahrefs or SEMrush when API key + domain set.

    Credentials:
      - provider: ahrefs | semrush (default ahrefs if api_key looks like token)
      - api_key / access_token
      - domain / target (required)
    CSV remains the fallback when API is unset or fails.
    """
    import httpx

    api_key = (creds.get("api_key") or creds.get("access_token") or "").strip()
    domain = (creds.get("domain") or creds.get("target") or "").strip().lower()
    domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    if not api_key or not domain:
        return 0

    provider = (creds.get("provider") or "ahrefs").strip().lower()
    today = date.today()
    referring_domains = 0
    total_backlinks = 0
    domain_rating = None
    new_links = 0
    lost_links = 0

    try:
        if provider == "semrush":
            url = "https://api.semrush.com/"
            params = {
                "type": "backlinks_overview",
                "key": api_key,
                "target": domain,
                "target_type": "root_domain",
                "export_columns": "total,domains_num,follows_num,nofollows_num,score",
            }
            resp = httpx.get(url, params=params, timeout=60.0)
            if resp.status_code >= 400:
                logger.error("SEMrush backlinks %s: %s", resp.status_code, resp.text[:200])
                return 0
            lines = [ln for ln in resp.text.strip().splitlines() if ln.strip()]
            if len(lines) < 2:
                return 0
            # header;row
            cols = lines[0].split(";")
            vals = lines[1].split(";")
            row = dict(zip(cols, vals))
            total_backlinks = int(float(row.get("total") or row.get("ascore") or 0))
            referring_domains = int(float(row.get("domains_num") or 0))
            try:
                domain_rating = float(row.get("score") or 0)
            except (TypeError, ValueError):
                domain_rating = None
        else:
            # Ahrefs Site Explorer metrics (v3)
            url = "https://api.ahrefs.com/v3/site-explorer/domain-rating"
            resp = httpx.get(
                url,
                params={"target": domain, "date": today.isoformat()},
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                timeout=60.0,
            )
            if resp.status_code >= 400:
                logger.error("Ahrefs DR %s: %s", resp.status_code, resp.text[:200])
                return 0
            dr_body = resp.json() or {}
            domain_rating = float(
                ((dr_body.get("domain_rating") or {}) if isinstance(dr_body.get("domain_rating"), dict) else {}).get(
                    "domain_rating"
                )
                or dr_body.get("domain_rating")
                or 0
            )
            url2 = "https://api.ahrefs.com/v3/site-explorer/backlinks-stats"
            resp2 = httpx.get(
                url2,
                params={"target": domain, "date": today.isoformat()},
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                timeout=60.0,
            )
            if resp2.status_code < 400:
                stats = resp2.json() or {}
                metrics = stats.get("metrics") or stats
                referring_domains = int(
                    float(metrics.get("live_refdomains") or metrics.get("refdomains") or 0)
                )
                total_backlinks = int(
                    float(metrics.get("live") or metrics.get("backlinks") or 0)
                )
                new_links = int(float(metrics.get("live_refdomains") or 0))  # best-effort
    except Exception as e:
        logger.error("Backlinks live fetch failed (%s): %s", provider, e)
        return 0

    if referring_domains <= 0 and total_backlinks <= 0:
        return 0

    db.query(BacklinkSnapshot).filter(BacklinkSnapshot.client_id == client_id).delete(
        synchronize_session=False
    )
    snap = BacklinkSnapshot(
        client_id=client_id,
        domain=domain,
        referring_domains=referring_domains,
        total_backlinks=total_backlinks,
        domain_rating=domain_rating,
        toxic_score=0,
        new_links_30d=new_links,
        lost_links_30d=lost_links,
    )
    db.add(snap)
    db.flush()
    _write_backlink_metrics(db, client_id, today)
    db.commit()
    return 1


def sync_backlinks(ds: DataSource) -> bool:
    """Sync backlinks — live Ahrefs/SEMrush when api_key+domain set, else CSV."""
    from app.credentials import CredentialsDecryptError, decrypt_credentials
    from app.database import SessionLocal
    from app.ds_status import mark_active, mark_error, mark_reauth_required

    if not ds.credentials_encrypted:
        logger.error("DataSource %s: No credentials for backlinks sync", ds.id)
        _persist_backlinks_error(ds, "Missing backlinks credentials (API key+domain or CSV)")
        return False

    try:
        creds = decrypt_credentials(ds.credentials_encrypted)
    except CredentialsDecryptError as e:
        logger.error("DataSource %s: backlinks decrypt failed: %s", ds.id, e)
        mark_reauth_required(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    db = SessionLocal()
    try:
        stored = 0
        if (creds.get("api_key") or creds.get("access_token")) and (
            creds.get("domain") or creds.get("target")
        ):
            stored = fetch_backlinks_live_api(db, ds.client_id, creds)

        if stored <= 0:
            csv_text = (creds.get("csv_text") or creds.get("csv") or "").strip()
            if csv_text:
                stored = import_backlinks_csv(db, ds.client_id, csv_text)

        if stored <= 0:
            mark_error(
                ds,
                "Backlinks sync produced 0 rows — set api_key+domain or paste CSV export",
            )
            db.merge(ds)
            db.commit()
            return False
        row = db.query(DataSource).filter(DataSource.id == ds.id).first()
        if row:
            mark_active(row)
        else:
            mark_active(ds)
            db.merge(ds)
        db.commit()
        logger.info(
            "Backlinks sync complete for client %s: %s snapshot rows", ds.client_id, stored
        )
        return True
    except Exception as e:
        db.rollback()
        logger.error("Backlinks sync failed for DataSource %s: %s", ds.id, e)
        _persist_backlinks_error(ds, str(e))
        return False
    finally:
        db.close()


def _persist_backlinks_error(ds: DataSource, message: str) -> None:
    from app.database import SessionLocal
    from app.ds_status import mark_error

    mark_error(ds, message)
    db = SessionLocal()
    try:
        db.merge(ds)
        db.commit()
    finally:
        db.close()
