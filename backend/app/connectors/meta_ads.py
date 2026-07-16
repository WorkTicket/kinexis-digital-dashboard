"""
Meta (Facebook) Ads connector — Insights API → MetricDaily (source=meta_ads).

Credentials (per datasource):
  access_token   — user or system user token with ads_read
  ad_account_id  — act_XXXXXXXX or numeric ID

Syncs:
  - campaign daily (primary)
  - placement breakdown (publisher_platform)
  - ad creative (level=ad) with frequency for fatigue rules
"""

from __future__ import annotations

import logging
import os
import json
from datetime import date, timedelta
from typing import Any

import httpx

from app.connectors.ads_common import persist_campaign_metrics, persist_dim_metrics
from app.credentials import CredentialsDecryptError, decrypt_credentials
from app.database import SessionLocal
from app.ds_status import mark_error, mark_reauth_required
from app.models import DataSource

logger = logging.getLogger(__name__)

GRAPH_VERSION = os.getenv("META_ADS_API_VERSION", "v21.0")
_CONV_ACTION_TYPES = frozenset(
    {
        "purchase",
        "omni_purchase",
        "offsite_conversion.fb_pixel_purchase",
        "lead",
        "onsite_conversion.lead",
        "complete_registration",
        "submit_application",
        "contact",
    }
)
_VALUE_ACTION_TYPES = frozenset(
    {
        "purchase",
        "omni_purchase",
        "offsite_conversion.fb_pixel_purchase",
    }
)


def _normalize_account_id(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if s.startswith("act_"):
        return s
    digits = "".join(c for c in s if c.isdigit())
    return f"act_{digits}" if digits else ""


def _sum_actions(actions: list[dict] | None, allowed: frozenset[str]) -> float:
    total = 0.0
    for row in actions or []:
        if not isinstance(row, dict):
            continue
        if (row.get("action_type") or "") in allowed:
            try:
                total += float(row.get("value") or 0)
            except (TypeError, ValueError):
                pass
    return total


def _parse_insight_row(row: dict, *, dim_label: str) -> dict | None:
    raw_date = (row.get("date_start") or "")[:10]
    try:
        d = date.fromisoformat(raw_date)
    except ValueError:
        return None
    label = (dim_label or "Unknown").strip() or "Unknown"
    conversions = _sum_actions(row.get("actions"), _CONV_ACTION_TYPES)
    conversion_value = _sum_actions(row.get("action_values"), _VALUE_ACTION_TYPES)
    out: dict[str, Any] = {
        "date": d,
        "impressions": float(row.get("impressions") or 0),
        "clicks": float(row.get("clicks") or 0),
        "cost": float(row.get("spend") or 0),
        "conversions": conversions,
        "conversion_value": conversion_value,
    }
    try:
        out["frequency"] = float(row.get("frequency") or 0)
    except (TypeError, ValueError):
        out["frequency"] = 0.0
    try:
        # Meta CTR is percent (e.g. 1.2); store as ratio for AVG charts
        ctr_raw = float(row.get("ctr") or 0)
        out["ctr"] = ctr_raw / 100.0 if ctr_raw > 1 else ctr_raw
    except (TypeError, ValueError):
        out["ctr"] = 0.0
    return out


def _fetch_insights_pages(
    access_token: str,
    ad_account_id: str,
    *,
    days: int,
    level: str,
    fields: str,
    breakdowns: str | None = None,
) -> list[dict]:
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{ad_account_id}/insights"
    end = date.today()
    start = end - timedelta(days=days)
    params: dict[str, Any] = {
        "level": level,
        "fields": fields,
        "time_increment": 1,
        "time_range": json.dumps({"since": start.isoformat(), "until": end.isoformat()}),
        "limit": 500,
    }
    if breakdowns:
        params["breakdowns"] = breakdowns
    headers = {"Authorization": f"Bearer {access_token}"}
    out: list[dict] = []
    with httpx.Client(timeout=60) as client:
        next_url: str | None = url
        next_params: dict[str, Any] | None = params
        pages = 0
        while next_url and pages < 20:
            pages += 1
            resp = client.get(next_url, params=next_params, headers=headers)
            if resp.status_code != 200:
                raise ValueError(f"Meta Ads API {resp.status_code}: {resp.text[:400]}")
            data = resp.json()
            for row in data.get("data") or []:
                if isinstance(row, dict):
                    out.append(row)
            paging = data.get("paging") or {}
            next_url = paging.get("next")
            next_params = None
    return out


def _fetch_campaign_rows(access_token: str, ad_account_id: str, days: int = 30) -> list[dict]:
    raw = _fetch_insights_pages(
        access_token,
        ad_account_id,
        days=days,
        level="campaign",
        fields="campaign_name,impressions,clicks,spend,actions,action_values",
    )
    out: list[dict] = []
    for row in raw:
        label = (str(row.get("campaign_name") or "Unknown")).strip() or "Unknown"
        parsed = _parse_insight_row(row, dim_label=label)
        if parsed:
            parsed["campaign"] = label
            out.append(parsed)
    return out


def _fetch_placement_rows(access_token: str, ad_account_id: str, days: int = 30) -> list[dict]:
    raw = _fetch_insights_pages(
        access_token,
        ad_account_id,
        days=days,
        level="campaign",
        fields="impressions,clicks,spend,actions,action_values",
        breakdowns="publisher_platform",
    )
    out: list[dict] = []
    for row in raw:
        platform = (
            str(row.get("publisher_platform") or row.get("impression_device") or "unknown")
            .strip()
            .lower()
            or "unknown"
        )
        parsed = _parse_insight_row(row, dim_label=platform)
        if parsed:
            parsed["placement"] = platform
            out.append(parsed)
    return out


def _fetch_ad_creative_rows(access_token: str, ad_account_id: str, days: int = 30) -> list[dict]:
    raw = _fetch_insights_pages(
        access_token,
        ad_account_id,
        days=days,
        level="ad",
        fields="ad_name,ad_id,impressions,clicks,spend,actions,action_values,frequency,ctr",
    )
    out: list[dict] = []
    for row in raw:
        ad_name = (str(row.get("ad_name") or "").strip() or str(row.get("ad_id") or "Unknown"))
        parsed = _parse_insight_row(row, dim_label=ad_name)
        if parsed:
            parsed["ad_creative"] = ad_name[:500]
            out.append(parsed)
    return out


def sync_meta_ads(ds: DataSource, days: int = 30) -> bool:
    if not ds.credentials_encrypted:
        logger.error("DataSource %s: No credentials for meta_ads", ds.id)
        _persist_error(ds, "Missing Meta Ads credentials")
        return False

    try:
        creds = decrypt_credentials(ds.credentials_encrypted)
    except CredentialsDecryptError as e:
        logger.error("DataSource %s: meta_ads decrypt failed: %s", ds.id, e)
        mark_reauth_required(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False
    token = (
        creds.get("access_token")
        or creds.get("api_token")
        or creds.get("api_key")
        or ""
    ).strip()
    account = _normalize_account_id(
        str(creds.get("ad_account_id") or creds.get("account_id") or "")
    )
    if not token:
        _persist_error(ds, "Missing Meta access_token")
        return False
    if not account:
        _persist_error(ds, "Missing ad_account_id")
        return False

    try:
        rows = _fetch_campaign_rows(token, account, days=days)
    except Exception as e:
        logger.error("meta_ads sync failed for DataSource %s: %s", ds.id, e)
        _persist_error(ds, str(e))
        return False

    if not rows:
        _persist_error(ds, "Meta Ads returned 0 campaign insight rows")
        return False

    ok = persist_campaign_metrics(ds, "meta_ads", rows)

    # Best-effort placement + creative dims (do not fail campaign sync)
    try:
        placement_rows = _fetch_placement_rows(token, account, days=days)
        if placement_rows:
            n = persist_dim_metrics(
                ds, "meta_ads", placement_rows, dim_type="placement", dim_key="placement"
            )
            logger.info("meta_ads placement rows persisted: %s", n)
    except Exception as e:
        logger.warning("meta_ads placement sync skipped for DataSource %s: %s", ds.id, e)

    try:
        creative_rows = _fetch_ad_creative_rows(token, account, days=days)
        if creative_rows:
            n = persist_dim_metrics(
                ds,
                "meta_ads",
                creative_rows,
                dim_type="ad_creative",
                dim_key="ad_creative",
                extra_metrics=("frequency", "ctr"),
            )
            logger.info("meta_ads ad_creative rows persisted: %s", n)
    except Exception as e:
        logger.warning("meta_ads creative sync skipped for DataSource %s: %s", ds.id, e)

    return ok


def _persist_error(ds: DataSource, message: str) -> None:
    mark_error(ds, message)
    db = SessionLocal()
    try:
        db.merge(ds)
        db.commit()
    finally:
        db.close()
