"""
HubSpot CRM connector — private app token → daily leads / opportunities / closed_won / revenue.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.credentials import CredentialsDecryptError, decrypt_credentials
from app.ds_status import mark_active, mark_error, mark_reauth_required
from app.database import SessionLocal
from app.models import DataSource, MetricDaily
from app.connectors.base import _sync_lock

logger = logging.getLogger(__name__)

HUBSPOT_BASE = "https://api.hubapi.com"


def _ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day).timestamp() * 1000)


def _search_objects(
    client: httpx.Client,
    token: str,
    object_type: str,
    properties: list[str],
    start: date,
    date_property: str = "createdate",
) -> list[dict[str, Any]]:
    """Paginated CRM search for objects created/closed since start."""
    results: list[dict[str, Any]] = []
    after: str | None = None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body: dict[str, Any] = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": date_property,
                        "operator": "GTE",
                        "value": str(_ms(start)),
                    }
                ]
            }
        ],
        "properties": properties,
        "limit": 100,
    }
    for _ in range(20):
        if after:
            body["after"] = after
        resp = client.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/{object_type}/search",
            headers=headers,
            json=body,
            timeout=45,
        )
        if resp.status_code != 200:
            logger.warning(
                "HubSpot %s search returned %s: %s",
                object_type,
                resp.status_code,
                resp.text[:300],
            )
            break
        data = resp.json()
        results.extend(data.get("results") or [])
        after = (data.get("paging") or {}).get("next", {}).get("after")
        if not after:
            break
    return results


def _day_from_ms(value: Any) -> date | None:
    if value is None or value == "":
        return None
    try:
        ms = int(value)
        return datetime.utcfromtimestamp(ms / 1000.0).date()
    except (TypeError, ValueError, OSError):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except ValueError:
            return None


def sync_hubspot(ds: DataSource, days: int = 30) -> bool:
    if not ds.credentials_encrypted:
        logger.error("DataSource %s: No credentials for HubSpot sync", ds.id)
        _persist_error(ds, "Missing HubSpot credentials")
        return False

    try:
        creds = decrypt_credentials(ds.credentials_encrypted)
    except CredentialsDecryptError as e:
        logger.error("DataSource %s: HubSpot decrypt failed: %s", ds.id, e)
        mark_reauth_required(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False
    token = creds.get("access_token") or creds.get("api_token") or creds.get("api_key")
    if not token:
        logger.error("DataSource %s: Missing HubSpot access token", ds.id)
        _persist_error(ds, "Missing HubSpot access token")
        return False

    end = date.today()
    start = end - timedelta(days=days)

    try:
        with httpx.Client(timeout=45) as client:
            contacts = _search_objects(
                client,
                token,
                "contacts",
                ["createdate"],
                start,
                "createdate",
            )
            deals = _search_objects(
                client,
                token,
                "deals",
                ["createdate", "closedate", "dealstage", "hs_is_closed_won", "amount"],
                start,
                "createdate",
            )
            # Also pull recently closed deals (may have older createdate)
            closed_deals = _search_objects(
                client,
                token,
                "deals",
                ["createdate", "closedate", "dealstage", "hs_is_closed_won", "amount"],
                start,
                "closedate",
            )

        leads_by_day: dict[date, float] = defaultdict(float)
        for c in contacts:
            props = c.get("properties") or {}
            d = _day_from_ms(props.get("createdate"))
            if d and start <= d <= end:
                leads_by_day[d] += 1

        opps_by_day: dict[date, float] = defaultdict(float)
        for deal in deals:
            props = deal.get("properties") or {}
            d = _day_from_ms(props.get("createdate"))
            if d and start <= d <= end:
                opps_by_day[d] += 1

        won_by_day: dict[date, float] = defaultdict(float)
        revenue_by_day: dict[date, float] = defaultdict(float)
        seen_deal_ids: set[str] = set()
        for deal in closed_deals + deals:
            deal_id = str(deal.get("id") or "")
            if deal_id in seen_deal_ids:
                continue
            seen_deal_ids.add(deal_id)
            props = deal.get("properties") or {}
            is_won = str(props.get("hs_is_closed_won") or "").lower() in ("true", "1")
            stage = (props.get("dealstage") or "").lower()
            if not is_won and "closedwon" not in stage and stage != "closed won":
                continue
            d = _day_from_ms(props.get("closedate")) or _day_from_ms(props.get("createdate"))
            if not d or d < start or d > end:
                continue
            won_by_day[d] += 1
            try:
                revenue_by_day[d] += float(props.get("amount") or 0)
            except (TypeError, ValueError):
                pass

        db = SessionLocal()
        try:
            with _sync_lock(ds.client_id, "hubspot"):
                db.query(MetricDaily).filter(
                    MetricDaily.client_id == ds.client_id,
                    MetricDaily.source == "hubspot",
                    MetricDaily.date >= start,
                    MetricDaily.date <= end,
                ).delete(synchronize_session=False)

                for d, val in leads_by_day.items():
                    db.add(
                        MetricDaily(
                            client_id=ds.client_id,
                            source="hubspot",
                            date=d,
                            metric_name="leads",
                            value=float(val),
                        )
                    )
                for d, val in opps_by_day.items():
                    db.add(
                        MetricDaily(
                            client_id=ds.client_id,
                            source="hubspot",
                            date=d,
                            metric_name="opportunities",
                            value=float(val),
                        )
                    )
                for d, val in won_by_day.items():
                    db.add(
                        MetricDaily(
                            client_id=ds.client_id,
                            source="hubspot",
                            date=d,
                            metric_name="closed_won",
                            value=float(val),
                        )
                    )
                for d, val in revenue_by_day.items():
                    db.add(
                        MetricDaily(
                            client_id=ds.client_id,
                            source="hubspot",
                            date=d,
                            metric_name="revenue",
                            value=float(val),
                        )
                    )

                mark_active(ds)
                db.merge(ds)
                db.commit()
            logger.info(
                "HubSpot sync complete for client %s: %s leads days, %s revenue days",
                ds.client_id,
                len(leads_by_day),
                len(revenue_by_day),
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return True
    except Exception as e:
        logger.error("HubSpot sync failed for DataSource %s: %s", ds.id, e)
        _persist_error(ds, str(e))
        return False


def _persist_error(ds: DataSource, message: str) -> None:
    mark_error(ds, message)
    db = SessionLocal()
    try:
        db.merge(ds)
        db.commit()
    finally:
        db.close()
