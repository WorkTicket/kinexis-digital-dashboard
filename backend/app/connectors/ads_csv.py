"""
Ads CSV connector — paste/upload daily campaign metrics into MetricDaily.

Expected CSV columns (header row required):
  date,campaign,impressions,clicks,cost,conversions,conversion_value

Optional columns may be omitted; missing numeric values default to 0.
Credentials store: { "csv_text": "..." } and optional platform label.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
from typing import Optional

from app.credentials import CredentialsDecryptError, decrypt_credentials
from app.ds_status import mark_active, mark_error, mark_reauth_required
from app.database import SessionLocal
from app.models import DataSource, MetricDaily
from app.connectors.base import _sync_lock

logger = logging.getLogger(__name__)

METRIC_COLS = ("impressions", "clicks", "cost", "conversions", "conversion_value")


def _parse_date(raw: str) -> Optional[date]:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def _float(raw: str) -> float:
    if raw is None:
        return 0.0
    s = str(raw).strip().replace(",", "").replace("$", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def sync_ads_csv(ds: DataSource) -> bool:
    if not ds.credentials_encrypted:
        logger.error("DataSource %s: No credentials for ads_csv sync", ds.id)
        _persist_error(ds, "Missing ads CSV credentials")
        return False

    try:
        creds = decrypt_credentials(ds.credentials_encrypted)
    except CredentialsDecryptError as e:
        logger.error("DataSource %s: ads_csv decrypt failed: %s", ds.id, e)
        mark_reauth_required(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False
    csv_text = creds.get("csv_text") or creds.get("csv") or ""
    if not csv_text.strip():
        logger.error("DataSource %s: Empty csv_text for ads_csv", ds.id)
        _persist_error(ds, "Empty csv_text for ads_csv")
        return False

    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if not reader.fieldnames:
        logger.error("DataSource %s: ads_csv missing header row", ds.id)
        _persist_error(ds, "ads_csv missing header row")
        return False

    # Normalize headers
    field_map = {h.strip().lower().replace(" ", "_"): h for h in reader.fieldnames}
    if "date" not in field_map:
        logger.error("DataSource %s: ads_csv requires a date column", ds.id)
        _persist_error(ds, "ads_csv requires a date column")
        return False

    rows_out: list[MetricDaily] = []
    min_d: Optional[date] = None
    max_d: Optional[date] = None
    parsed = 0

    for row in reader:
        d = _parse_date(row.get(field_map["date"], ""))
        if not d:
            continue
        campaign = ""
        if "campaign" in field_map:
            campaign = (row.get(field_map["campaign"]) or "").strip() or "Unknown"
        else:
            campaign = "All campaigns"

        min_d = d if min_d is None else min(min_d, d)
        max_d = d if max_d is None else max(max_d, d)

        for metric in METRIC_COLS:
            if metric not in field_map:
                continue
            val = _float(row.get(field_map[metric], "0"))
            rows_out.append(
                MetricDaily(
                    client_id=ds.client_id,
                    source="ads_csv",
                    date=d,
                    metric_name=metric,
                    value=val,
                    dimension_type="campaign",
                    dimension_value=campaign,
                )
            )
        parsed += 1

    if not rows_out or min_d is None or max_d is None:
        logger.error("DataSource %s: ads_csv parsed 0 valid rows", ds.id)
        _persist_error(ds, "ads_csv parsed 0 valid rows")
        return False

    db = SessionLocal()
    try:
        with _sync_lock(ds.client_id, "ads_csv"):
            db.query(MetricDaily).filter(
            MetricDaily.client_id == ds.client_id,
            MetricDaily.source == "ads_csv",
            MetricDaily.date >= min_d,
            MetricDaily.date <= max_d,
        ).delete(synchronize_session=False)

        for entry in rows_out:
            db.add(entry)

        mark_active(ds)
        db.merge(ds)
        db.commit()
        logger.info(
            "ads_csv sync complete for client %s: %s rows → %s metric points",
            ds.client_id,
            parsed,
            len(rows_out),
        )
        return True
    except Exception as e:
        db.rollback()
        logger.error("ads_csv sync failed for DataSource %s: %s", ds.id, e)
        _persist_error(ds, str(e))
        return False
    finally:
        db.close()


def _persist_error(ds: DataSource, message: str) -> None:
    mark_error(ds, message)
    db = SessionLocal()
    try:
        db.merge(ds)
        db.commit()
    finally:
        db.close()
