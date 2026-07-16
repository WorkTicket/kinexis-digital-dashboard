"""
Cloudflare connector — single account-wide API token, all zones.

Auth: One API token in .env (CLOUDFLARE_API_TOKEN).
Per-client config: zone_ids stored in DataSource credentials (optional — if omitted, fetches all zones in the account).
"""

import logging
from datetime import datetime, timedelta, date
from typing import Optional

import httpx

from app.config import CLOUDFLARE_API_TOKEN
from app.ds_status import mark_active, mark_error, mark_reauth_required
from app.connectors.base import normalize_dimension, replace_metrics_window
from app.credentials import CredentialsDecryptError, decrypt_credentials
from app.models import DataSource
from app.database import SessionLocal

logger = logging.getLogger(__name__)

CF_BASE = "https://api.cloudflare.com/client/v4"
CF_GRAPHQL_URL = f"{CF_BASE}/graphql"

_ZONE_DAILY_ANALYTICS_QUERY = """
query ZoneDailyAnalytics($zoneTag: string, $start: Time, $end: Time) {
  viewer {
    zones(filter: { zoneTag: $zoneTag }) {
      httpRequests1dGroups(
        limit: 100
        orderBy: [date_ASC]
        filter: { date_geq: $start, date_leq: $end }
      ) {
        dimensions { date }
        sum { requests bytes threats pageViews }
        uniq { uniques }
      }
    }
  }
}
"""


def _get_token(ds: DataSource) -> Optional[str]:
    """Resolve auth: env token, OAuth session, then per-source stored token."""
    if CLOUDFLARE_API_TOKEN:
        return CLOUDFLARE_API_TOKEN

    from app.cloudflare_oauth import get_valid_access_token
    from app.database import SessionLocal

    oauth_errored = False
    db = SessionLocal()
    try:
        oauth_token = get_valid_access_token(db)
        if oauth_token:
            return oauth_token
    except CredentialsDecryptError:
        raise
    except Exception:
        oauth_errored = True
        logger.exception("OAuth token resolution failed for DataSource %s; falling back to per-DS credentials", ds.id)
    finally:
        db.close()

    if ds.credentials_encrypted:
        try:
            creds = decrypt_credentials(ds.credentials_encrypted)
        except CredentialsDecryptError:
            raise
        per_ds = creds.get("api_token") or creds.get("access_token")
        if per_ds:
            return per_ds

    if oauth_errored:
        raise RuntimeError("Cloudflare OAuth token refresh failed and no per-datasource API token configured")

    return None


def _list_all_zones(token: str) -> list[dict]:
    """Fetch all zones from the Cloudflare account."""
    zones = []
    page = 1
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=30) as client:
        while True:
            resp = client.get(
                f"{CF_BASE}/zones",
                headers=headers,
                params={"page": page, "per_page": 50},
            )
            if resp.status_code == 401 or resp.status_code == 403:
                raise httpx.HTTPStatusError(
                    "Cloudflare API authentication failed — OAuth token may have expired. "
                    "Reconnect Cloudflare in Settings, or verify CLOUDFLARE_API_TOKEN in .env.",
                    request=resp.request,
                    response=resp,
                )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                logger.error(f"Cloudflare list zones failed: {data.get('errors')}")
                break

            results = data.get("result", [])
            zones.extend(results)

            info = data.get("result_info", {})
            if page >= info.get("total_pages", 1):
                break
            page += 1

    logger.info(f"Cloudflare: found {len(zones)} zones in account")
    return zones


def _fetch_analytics(token: str, zone_id: str, start_date: date, end_date: date) -> Optional[list[dict]]:
    """Fetch daily zone analytics via Cloudflare GraphQL API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": _ZONE_DAILY_ANALYTICS_QUERY,
        "variables": {
            "zoneTag": zone_id,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(CF_GRAPHQL_URL, headers=headers, json=payload)
        if resp.status_code == 401 or resp.status_code == 403:
            raise httpx.HTTPStatusError(
                "Cloudflare API authentication failed — OAuth token may have expired. "
                "Reconnect Cloudflare in Settings, or verify CLOUDFLARE_API_TOKEN in .env.",
                request=resp.request,
                response=resp,
            )
        resp.raise_for_status()
        data = resp.json()

    if data.get("errors"):
        msg = data["errors"][0].get("message", "GraphQL error")
        logger.warning(f"Cloudflare analytics failed for zone {zone_id}: {msg}")
        return None

    zones = (data.get("data") or {}).get("viewer", {}).get("zones") or []
    if not zones:
        logger.warning(f"Cloudflare analytics returned no zones for {zone_id}")
        return None

    groups = zones[0].get("httpRequests1dGroups") or []
    points = []
    for group in groups:
        day = (group.get("dimensions") or {}).get("date")
        if not day:
            continue
        try:
            day_clean = str(day)[:10]
            datetime.strptime(day_clean, "%Y-%m-%d")
        except (ValueError, TypeError):
            logger.warning("Cloudflare analytics: malformed date %s — skipping", day)
            continue
        totals = group.get("sum") or {}
        uniques = (group.get("uniq") or {}).get("uniques") or 0
        points.append(
            {
                "date": day_clean,
                "requests": totals.get("requests") or 0,
                "bandwidth": totals.get("bytes") or 0,
                "threats": totals.get("threats") or 0,
                "pageviews": totals.get("pageViews") or 0,
                "uniques": uniques,
            }
        )

    return points or None


def _resolve_zone_ids(ds: DataSource, token: str) -> tuple[list[str], dict[str, str]]:
    """
    Resolve which Cloudflare zones belong to this client.

    Priority:
      1. Explicit zone_ids in credentials (manual override)
      2. Domain-based auto-matching from credentials.domains
      3. Skip — no silent "all zones" fallback (that cross-contaminates client data)

    Returns (zone_ids, zone_id_to_name_map).
    """
    if ds.credentials_encrypted:
        try:
            creds = decrypt_credentials(ds.credentials_encrypted)
        except CredentialsDecryptError:
            raise

        configured = creds.get("zone_ids", creds.get("zone_id"))
        if configured:
            if isinstance(configured, list):
                ids = configured
            else:
                ids = [configured]
            # fetch names for these explicit IDs
            all_zones = _list_all_zones(token)
            name_map = {z["id"]: z.get("name", z["id"]) for z in all_zones if z.get("id") in ids}
            logger.info(f"DataSource {ds.id}: Using {len(ids)} explicitly configured zone(s)")
            return ids, name_map

        domains = creds.get("domains", creds.get("domain"))
        if domains:
            if isinstance(domains, list):
                domain_list = domains
            else:
                domain_list = [domains]

            all_zones = _list_all_zones(token)
            matched = []
            name_map = {}
            for zone in all_zones:
                zone_name = zone.get("name", "")
                zone_id = zone.get("id", "")
                for domain in domain_list:
                    if zone_name == domain or zone_name.endswith("." + domain):
                        matched.append(zone_id)
                        name_map[zone_id] = zone_name
                        logger.info(
                            f"DataSource {ds.id}: Auto-matched zone \"{zone_name}\" "
                            f"→ domain \"{domain}\""
                        )
                        break

            if matched:
                logger.info(
                    f"DataSource {ds.id}: Domain auto-match found {len(matched)} zone(s) "
                    f"for domains {domain_list}"
                )
            else:
                logger.warning(
                    f"DataSource {ds.id}: No Cloudflare zones matched domains {domain_list}. "
                    f"Check that domain names match zone names exactly in Cloudflare."
                )
            return matched, name_map

    logger.warning(
        f"DataSource {ds.id}: No zone_ids or domains configured. "
        f"Cloudflare sync will be skipped — configure zone_ids or domains in the data source credentials. "
        f"Credentials format: {{\"zone_ids\": [\"abc123\"]}} or {{\"domains\": [\"clienta.com\"]}}"
    )
    return [], {}


def sync_cloudflare(ds: DataSource) -> bool:
    try:
        token = _get_token(ds)
    except CredentialsDecryptError as e:
        logger.error("DataSource %s: Cloudflare decrypt failed: %s", ds.id, e)
        mark_reauth_required(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False
    except RuntimeError as e:
        logger.error("DataSource %s: OAuth token resolution failed: %s", ds.id, e)
        mark_error(ds, f"Cloudflare OAuth token refresh failed — reconnect in Settings. {e}")
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    if not token:
        logger.error(
            f"DataSource {ds.id}: No Cloudflare API token set. "
            f"Add CLOUDFLARE_API_TOKEN to .env or store per-source in credentials."
        )
        mark_error(ds, "No Cloudflare API token configured — set CLOUDFLARE_API_TOKEN in .env or connect via OAuth in Settings")
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False

    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=90)

        zone_ids, zone_names = _resolve_zone_ids(ds, token)
        if not zone_ids:
            msg = (
                "No zone_ids or domains configured in datasource credentials. "
                "Add {\"zone_ids\": [\"abc123\"]} or {\"domains\": [\"example.com\"]} to sync Cloudflare analytics."
            )
            logger.warning(f"DataSource {ds.id}: {msg}")
            ds.status = "pending"
            ds.last_error = msg[:500]
            db = SessionLocal()
            try:
                db.merge(ds)
                db.commit()
            finally:
                db.close()
            return False

        total_points = 0
        metric_payloads: list[dict] = []

        for zone_id in zone_ids:
            zone_name = zone_names.get(zone_id, zone_id)
            timeseries = _fetch_analytics(token, zone_id, start_date, end_date)
            if not timeseries:
                continue

            for point in timeseries:
                ts_date_str = point.get("date", "")
                if not ts_date_str:
                    continue
                try:
                    ts_date = datetime.strptime(ts_date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue

                for metric_name in ("requests", "bandwidth", "threats", "pageviews", "uniques"):
                    val = point.get(metric_name, 0) or 0
                    metric_payloads.append(
                        {
                            "date": ts_date,
                            "metric_name": metric_name,
                            "value": float(val),
                            "dimension_type": "zone",
                            "dimension_value": zone_name,
                        }
                    )
                    total_points += 1

        db = SessionLocal()
        try:
            replace_metrics_window(
                db,
                client_id=ds.client_id,
                source="cloudflare",
                start=start_date,
                end=end_date,
                rows=metric_payloads,
            )

            mark_active(ds)
            db.merge(ds)
            db.commit()
            logger.info(
                f"Cloudflare sync complete for client {ds.client_id}: "
                f"{total_points} data points across {len(zone_ids)} zones"
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        return True

    except CredentialsDecryptError as e:
        logger.error("DataSource %s: Cloudflare decrypt failed in zone resolution: %s", ds.id, e)
        mark_reauth_required(ds, str(e))
        db2 = SessionLocal()
        try:
            db2.merge(ds)
            db2.commit()
        finally:
            db2.close()
        return False
    except httpx.HTTPStatusError as e:
        logger.error(f"Cloudflare HTTP error for DataSource {ds.id}: {e}")
        msg = str(e)
        # 401/403 / invalid access token → reconnect, not a permanent zone failure
        if getattr(e.response, "status_code", None) in (401, 403) or "authentication failed" in msg.lower() or "invalid access token" in msg.lower():
            mark_reauth_required(
                ds,
                "Cloudflare session expired — reconnect Cloudflare in Settings, then Sync again.",
            )
        else:
            mark_error(ds, msg)
        db2 = SessionLocal()
        try:
            db2.merge(ds)
            db2.commit()
        finally:
            db2.close()
        return False
    except Exception as e:
        logger.error(f"Cloudflare sync failed for DataSource {ds.id}: {e}")
        mark_error(ds, str(e))
        db2 = SessionLocal()
        try:
            db2.merge(ds)
            db2.commit()
        finally:
            db2.close()
        return False
