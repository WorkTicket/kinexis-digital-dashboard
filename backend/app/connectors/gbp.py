"""Google Business Profile (GBP) connector — local SEO metrics ingestion.

For the core ICP (roofers, plumbers, landscapers, contractors), GBP drives
40-60% of leads. This connector imports GBP Insights data and creates
insight rules for local performance gaps.

Uses the same Google OAuth credentials as GSC — GBP is part of the
My Business API within the same Google Cloud project.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from app.models import DataSource, MetricDaily, GbpSnapshot
from app.ds_status import mark_active, mark_error
from app.connectors.base import _sync_lock

logger = logging.getLogger(__name__)


def import_gbp_csv(db, client_id: int, csv_content: str) -> int:
    """Import GBP insights from a CSV export (Google Business Profile download).

    Supports Google's standard GBP Insights CSV format. Writes both GbpSnapshot
    rows and MetricDaily rows for portfolio charts and insight rules.

    Returns count of GBP snapshot rows stored.
    """
    import csv
    import io

    # Auto-detect period from filename or first row
    reader = csv.DictReader(io.StringIO(csv_content))
    if not reader.fieldnames:
        raise ValueError("Empty CSV")

    stored = 0
    today = date.today()
    # Default period: last 28 days
    period_end = today - timedelta(days=1)
    period_start = period_end - timedelta(days=27)

    totals = {
        "search_views": 0, "map_views": 0, "website_clicks": 0,
        "direction_requests": 0, "phone_calls": 0,
        "direct_searches": 0, "discovery_searches": 0,
    }

    for row in reader:
        # Detect column names (GBP export varies by language)
        col_map = _detect_gbp_columns(row)

        location_id = (row.get(col_map.get("location_id", "")) or row.get("Location ID") or "").strip()
        if not location_id:
            location_id = "primary"

        location_name = row.get(col_map.get("location_name", "")) or row.get("Business Name") or ""

        snapshot = GbpSnapshot(
            client_id=client_id,
            location_id=location_id,
            location_name=location_name,
            period_start=period_start,
            period_end=period_end,
            search_views=_int_val(row, col_map, "search_views"),
            map_views=_int_val(row, col_map, "map_views"),
            website_clicks=_int_val(row, col_map, "website_clicks"),
            direction_requests=_int_val(row, col_map, "direction_requests"),
            phone_calls=_int_val(row, col_map, "phone_calls"),
            direct_searches=_int_val(row, col_map, "direct_searches"),
            discovery_searches=_int_val(row, col_map, "discovery_searches"),
        )
        snapshot.total_actions = (
            snapshot.website_clicks + snapshot.direction_requests + snapshot.phone_calls
        )
        db.add(snapshot)
        stored += 1

        totals["search_views"] += snapshot.search_views
        totals["map_views"] += snapshot.map_views
        totals["website_clicks"] += snapshot.website_clicks
        totals["direction_requests"] += snapshot.direction_requests
        totals["phone_calls"] += snapshot.phone_calls
        totals["direct_searches"] += snapshot.direct_searches
        totals["discovery_searches"] += snapshot.discovery_searches

    # Write aggregated metrics to MetricDaily (per-source lock prevents concurrent writes)
    with _sync_lock(client_id, "gbp"):
        db.query(MetricDaily).filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == "gbp",
            MetricDaily.date == period_end,
        ).delete(synchronize_session=False)

        for metric_name in [
            "search_views", "map_views", "website_clicks",
            "direction_requests", "phone_calls", "direct_searches", "discovery_searches",
        ]:
            db.add(MetricDaily(
                client_id=client_id,
                source="gbp",
                date=period_end,
                metric_name=metric_name,
                value=float(totals.get(metric_name, 0)),
                dimension_type="",
                dimension_value="",
            ))

    db.commit()
    return stored


def _detect_gbp_columns(row: dict) -> dict[str, str]:
    """Detect GBP CSV column names by common patterns."""
    mapping = {}
    for key in row.keys():
        k = key.lower().strip()
        if "search" in k and "view" in k:
            mapping["search_views"] = key
        elif "map" in k and "view" in k:
            mapping["map_views"] = key
        elif "website" in k and "click" in k:
            mapping["website_clicks"] = key
        elif "direction" in k:
            mapping["direction_requests"] = key
        elif "phone" in k and ("call" in k or "number" in k):
            mapping["phone_calls"] = key
        elif "direct" in k and "search" in k:
            mapping["direct_searches"] = key
        elif "discovery" in k or "category" in k:
            mapping["discovery_searches"] = key
        elif "location" in k and "id" in k:
            mapping["location_id"] = key
        elif "name" in k or "business" in k:
            mapping["location_name"] = key
    return mapping


def _int_val(row: dict, mapping: dict, key: str) -> int:
    col = mapping.get(key)
    if not col:
        return 0
    try:
        return int(float(str(row.get(col, "0")).replace(",", "").strip()))
    except (ValueError, TypeError):
        return 0


def ensure_gbp_datasource(db, client_id: int) -> DataSource:
    ds = db.query(DataSource).filter(
        DataSource.client_id == client_id,
        DataSource.type == "gbp",
    ).first()
    if not ds:
        ds = DataSource(client_id=client_id, type="gbp", status="pending")
        db.add(ds)
        db.commit()
    return ds


def _store_gbp_totals(
    db,
    client_id: int,
    location_id: str,
    location_name: str,
    totals: dict[str, int],
    period_start: date,
    period_end: date,
) -> int:
    """Write one GbpSnapshot + MetricDaily rollup. Returns 1 on success."""
    snapshot = GbpSnapshot(
        client_id=client_id,
        location_id=location_id or "primary",
        location_name=location_name or "",
        period_start=period_start,
        period_end=period_end,
        search_views=int(totals.get("search_views") or 0),
        map_views=int(totals.get("map_views") or 0),
        website_clicks=int(totals.get("website_clicks") or 0),
        direction_requests=int(totals.get("direction_requests") or 0),
        phone_calls=int(totals.get("phone_calls") or 0),
        direct_searches=int(totals.get("direct_searches") or 0),
        discovery_searches=int(totals.get("discovery_searches") or 0),
    )
    snapshot.total_actions = (
        snapshot.website_clicks + snapshot.direction_requests + snapshot.phone_calls
    )
    db.add(snapshot)
    with _sync_lock(client_id, "gbp"):
        db.query(MetricDaily).filter(
            MetricDaily.client_id == client_id,
            MetricDaily.source == "gbp",
            MetricDaily.date == period_end,
        ).delete(synchronize_session=False)
        for metric_name in [
            "search_views",
            "map_views",
            "website_clicks",
            "direction_requests",
            "phone_calls",
            "direct_searches",
            "discovery_searches",
        ]:
            db.add(
                MetricDaily(
                    client_id=client_id,
                    source="gbp",
                    date=period_end,
                    metric_name=metric_name,
                    value=float(totals.get(metric_name, 0)),
                    dimension_type="",
                    dimension_value="",
                )
            )
    db.commit()
    return 1


def fetch_gbp_live_api(db, client_id: int, creds: dict) -> int:
    """Pull GBP Performance API daily metrics when location_id + OAuth token exist.

    Credentials keys:
      - location_id (required) — e.g. locations/123… or bare numeric id
      - location_name (optional)
      - access_token (optional) — else uses agency Google OAuth credentials
    Requires Google OAuth scope business.manage (re-auth after scope add).
    """
    import httpx

    location_id = (creds.get("location_id") or "").strip()
    if not location_id:
        return 0
    if not location_id.startswith("locations/"):
        location_id = f"locations/{location_id}"

    token = (creds.get("access_token") or creds.get("api_token") or "").strip()
    if not token:
        try:
            from app.google_oauth import get_global_credentials

            gcreds = get_global_credentials(db)
            if gcreds and getattr(gcreds, "token", None):
                token = gcreds.token
        except Exception as e:
            logger.warning("GBP live: no Google token (%s)", e)
            return 0
    if not token:
        return 0

    period_end = date.today() - timedelta(days=1)
    period_start = period_end - timedelta(days=27)
    # Business Profile Performance API — multi daily metrics
    url = (
        f"https://businessprofileperformance.googleapis.com/v1/{location_id}"
        f":fetchMultiDailyMetricsTimeSeries"
    )
    daily_metrics = [
        "WEBSITE_CLICKS",
        "CALL_CLICKS",
        "BUSINESS_DIRECTION_REQUESTS",
        "BUSINESS_IMPRESSIONS_DESKTOP_MAPS",
        "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH",
        "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
        "BUSINESS_IMPRESSIONS_MOBILE_SEARCH",
    ]
    params = [
        ("dailyMetrics", m) for m in daily_metrics
    ] + [
        ("dailyRange.start_date.year", str(period_start.year)),
        ("dailyRange.start_date.month", str(period_start.month)),
        ("dailyRange.start_date.day", str(period_start.day)),
        ("dailyRange.end_date.year", str(period_end.year)),
        ("dailyRange.end_date.month", str(period_end.month)),
        ("dailyRange.end_date.day", str(period_end.day)),
    ]
    try:
        resp = httpx.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0,
        )
        if resp.status_code == 401:
            raise PermissionError("GBP API unauthorized — re-auth Google with business.manage scope")
        if resp.status_code >= 400:
            logger.error("GBP API %s: %s", resp.status_code, resp.text[:300])
            return 0
        payload = resp.json()
    except PermissionError:
        raise
    except Exception as e:
        logger.error("GBP live fetch failed: %s", e)
        return 0

    totals = {
        "search_views": 0,
        "map_views": 0,
        "website_clicks": 0,
        "direction_requests": 0,
        "phone_calls": 0,
        "direct_searches": 0,
        "discovery_searches": 0,
    }
    series_list = payload.get("multiDailyMetricTimeSeries") or payload.get(
        "dailyMetricTimeSeries"
    ) or []
    # Normalize nested structure from fetchMultiDailyMetricsTimeSeries
    flat_series = []
    for block in series_list:
        for s in block.get("dailyMetricTimeSeries") or [block]:
            flat_series.append(s)
    if not flat_series and isinstance(payload.get("timeSeries"), dict):
        flat_series = [payload]

    for series in flat_series:
        metric = (series.get("dailyMetric") or series.get("metric") or "").upper()
        points = (
            (series.get("timeSeries") or {}).get("datedValues")
            or series.get("datedValues")
            or []
        )
        total = 0
        for p in points:
            try:
                total += int(float(p.get("value") or 0))
            except (TypeError, ValueError):
                continue
        if "WEBSITE_CLICKS" in metric:
            totals["website_clicks"] += total
        elif "CALL_CLICKS" in metric:
            totals["phone_calls"] += total
        elif "DIRECTION" in metric:
            totals["direction_requests"] += total
        elif "MAPS" in metric:
            totals["map_views"] += total
        elif "SEARCH" in metric:
            totals["search_views"] += total

    if sum(totals.values()) <= 0:
        logger.warning("GBP live API returned empty metrics for %s", location_id)
        return 0

    return _store_gbp_totals(
        db,
        client_id,
        location_id,
        (creds.get("location_name") or "").strip(),
        totals,
        period_start,
        period_end,
    )


def sync_gbp(ds: DataSource) -> bool:
    """Sync GBP Insights — live API when location_id set, else CSV fallback."""
    from app.credentials import CredentialsDecryptError, decrypt_credentials
    from app.database import SessionLocal
    from app.ds_status import mark_active, mark_error, mark_reauth_required

    if not ds.credentials_encrypted:
        logger.error("DataSource %s: No credentials for GBP sync", ds.id)
        _persist_gbp_error(ds, "Missing GBP credentials (location_id or CSV)")
        return False

    try:
        creds = decrypt_credentials(ds.credentials_encrypted)
    except CredentialsDecryptError as e:
        logger.error("DataSource %s: GBP decrypt failed: %s", ds.id, e)
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
        if (creds.get("location_id") or "").strip():
            try:
                stored = fetch_gbp_live_api(db, ds.client_id, creds)
            except PermissionError as e:
                mark_reauth_required(ds, str(e))
                db.merge(ds)
                db.commit()
                return False

        if stored <= 0:
            csv_text = (creds.get("csv_text") or creds.get("csv") or "").strip()
            if csv_text:
                stored = import_gbp_csv(db, ds.client_id, csv_text)

        if stored <= 0:
            mark_error(
                ds,
                "GBP sync produced 0 rows — set location_id for live API or paste Insights CSV",
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
        logger.info("GBP sync complete for client %s: %s snapshot rows", ds.client_id, stored)
        return True
    except Exception as e:
        db.rollback()
        logger.error("GBP sync failed for DataSource %s: %s", ds.id, e)
        _persist_gbp_error(ds, str(e))
        return False
    finally:
        db.close()


def _persist_gbp_error(ds: DataSource, message: str) -> None:
    from app.database import SessionLocal
    from app.ds_status import mark_error

    mark_error(ds, message)
    db = SessionLocal()
    try:
        db.merge(ds)
        db.commit()
    finally:
        db.close()
