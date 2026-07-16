"""
Google Ads connector — GAQL searchStream → MetricDaily (source=google_ads).

Credentials (per datasource):
  customer_id          — 10-digit Ads customer ID (dashes optional)
  developer_token      — optional if set in Settings / GOOGLE_ADS_DEVELOPER_TOKEN
  login_customer_id    — optional MCC ID
  refresh_token        — OAuth refresh token with ads scope
  access_token         — optional; refreshed when missing/expired
  client_id / client_secret — optional overrides (else GOOGLE_CLIENT_*)

Requires a Google Ads API developer token and an OAuth refresh token with
https://www.googleapis.com/auth/adwords scope.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

import httpx

import app.config as cfg
from app.connectors.ads_common import persist_campaign_metrics, persist_search_term_metrics
from app.credentials import CredentialsDecryptError, decrypt_credentials, encrypt_credentials
from app.database import SessionLocal
from app.ds_status import mark_error, mark_reauth_required
from app.models import AppSetting, DataSource
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

ADS_API_VERSION = "v17"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _digits(raw: str) -> str:
    return "".join(c for c in (raw or "") if c.isdigit())


def _developer_token(creds: dict) -> str:
    tok = (creds.get("developer_token") or "").strip()
    if tok:
        return tok
    env = (getattr(cfg, "GOOGLE_ADS_DEVELOPER_TOKEN", None) or "").strip()
    if env:
        return env
    db = SessionLocal()
    try:
        row = db.query(AppSetting).filter(AppSetting.key == "google_ads_developer_token").first()
        if row and row.value:
            from app.credentials import decrypt_secret

            try:
                return decrypt_secret(row.value)
            except Exception:
                return row.value
    finally:
        db.close()
    return ""


def _refresh_access_token(creds: dict) -> tuple[str, dict]:
    """Return (access_token, updated_creds). Raises on failure."""
    access = (creds.get("access_token") or "").strip()
    refresh = (creds.get("refresh_token") or "").strip()
    if access and not refresh:
        return access, creds
    if not refresh:
        if access:
            return access, creds
        raise ValueError("Missing Google Ads refresh_token (or access_token)")

    client_id = (
        (creds.get("client_id") or "").strip()
        or (getattr(cfg, "GOOGLE_CLIENT_ID", "") or "").strip()
    )
    client_secret = (
        (creds.get("client_secret") or "").strip()
        or (getattr(cfg, "GOOGLE_CLIENT_SECRET", "") or "").strip()
    )
    if not client_id or not client_secret:
        if access:
            return access, creds
        raise ValueError("GOOGLE_CLIENT_ID/SECRET required to refresh Ads token")

    with httpx.Client(timeout=30) as client:
        resp = client.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code != 200:
            raise ValueError(f"OAuth refresh failed ({resp.status_code}): {resp.text[:200]}")
        data = resp.json()
    new_access = data.get("access_token")
    if not new_access:
        raise ValueError("OAuth refresh returned no access_token")
    updated = dict(creds)
    updated["access_token"] = new_access
    if data.get("expires_in"):
        updated["expires_at"] = (
            utcnow() + timedelta(seconds=int(data["expires_in"]) - 60)
        ).isoformat()
    return new_access, updated


def _gaql_rows(access_token: str, developer_token: str, customer_id: str, login_customer_id: str, days: int = 30) -> list[dict]:
    query = (
        "SELECT campaign.name, segments.date, "
        "metrics.impressions, metrics.clicks, metrics.cost_micros, "
        "metrics.conversions, metrics.conversions_value "
        "FROM campaign "
        f"WHERE segments.date DURING LAST_{days}_DAYS "
        "AND campaign.status != 'REMOVED'"
    )
    url = (
        f"https://googleads.googleapis.com/{ADS_API_VERSION}/"
        f"customers/{customer_id}/googleAds:searchStream"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "developer-token": developer_token,
        "Content-Type": "application/json",
    }
    if login_customer_id:
        headers["login-customer-id"] = login_customer_id

    out: list[dict] = []
    with httpx.Client(timeout=90) as client:
        resp = client.post(url, headers=headers, json={"query": query})
        if resp.status_code != 200:
            raise ValueError(f"Google Ads API {resp.status_code}: {resp.text[:400]}")
        # searchStream returns line-delimited JSON (NDJSON)
        raw_text = resp.text.strip()
        if not raw_text:
            return out
        batches = []
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                batch = json.loads(line)
                if isinstance(batch, dict):
                    batches.append(batch)
            except json.JSONDecodeError:
                logger.warning("Google Ads searchStream: failed to parse line: %s", line[:100])
        for batch in batches:
            for row in batch.get("results") or []:
                if not isinstance(row, dict):
                    continue
                campaign = (row.get("campaign") or {}).get("name") or "Unknown"
                seg = row.get("segments") or {}
                metrics = row.get("metrics") or {}
                raw_date = seg.get("date") or ""
                try:
                    d = date.fromisoformat(str(raw_date)[:10])
                except ValueError:
                    continue
                cost_micros = float(metrics.get("costMicros") or metrics.get("cost_micros") or 0)
                out.append(
                    {
                        "date": d,
                        "campaign": campaign,
                        "impressions": float(metrics.get("impressions") or 0),
                        "clicks": float(metrics.get("clicks") or 0),
                        "cost": cost_micros / 1_000_000.0,
                        "conversions": float(metrics.get("conversions") or 0),
                        "conversion_value": float(
                            metrics.get("conversionsValue")
                            or metrics.get("conversions_value")
                            or 0
                        ),
                    }
                )
    return out


def _gaql_search_term_rows(
    access_token: str,
    developer_token: str,
    customer_id: str,
    login_customer_id: str,
    days: int = 30,
) -> list[dict]:
    """Zero-conversion search terms with spend — waste candidates."""
    query = (
        "SELECT search_term_view.search_term, segments.date, "
        "metrics.impressions, metrics.clicks, metrics.cost_micros, "
        "metrics.conversions, metrics.conversions_value "
        "FROM search_term_view "
        f"WHERE segments.date DURING LAST_{days}_DAYS "
        "AND metrics.cost_micros > 0 "
        "AND metrics.conversions = 0"
    )
    url = (
        f"https://googleads.googleapis.com/{ADS_API_VERSION}/"
        f"customers/{customer_id}/googleAds:searchStream"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "developer-token": developer_token,
        "Content-Type": "application/json",
    }
    if login_customer_id:
        headers["login-customer-id"] = login_customer_id

    out: list[dict] = []
    with httpx.Client(timeout=90) as client:
        resp = client.post(url, headers=headers, json={"query": query})
        if resp.status_code != 200:
            logger.warning(
                "Google Ads search_term_view %s: %s", resp.status_code, resp.text[:200]
            )
            return out
        for line in (resp.text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                batch = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(batch, dict):
                continue
            for row in batch.get("results") or []:
                if not isinstance(row, dict):
                    continue
                st = (row.get("searchTermView") or row.get("search_term_view") or {}).get(
                    "searchTerm"
                ) or (row.get("searchTermView") or {}).get("search_term")
                if not st:
                    continue
                seg = row.get("segments") or {}
                metrics = row.get("metrics") or {}
                raw_date = seg.get("date") or ""
                try:
                    d = date.fromisoformat(str(raw_date)[:10])
                except ValueError:
                    continue
                cost_micros = float(metrics.get("costMicros") or metrics.get("cost_micros") or 0)
                out.append(
                    {
                        "date": d,
                        "search_term": str(st)[:500],
                        "impressions": float(metrics.get("impressions") or 0),
                        "clicks": float(metrics.get("clicks") or 0),
                        "cost": cost_micros / 1_000_000.0,
                        "conversions": float(metrics.get("conversions") or 0),
                        "conversion_value": float(
                            metrics.get("conversionsValue")
                            or metrics.get("conversions_value")
                            or 0
                        ),
                    }
                )
    return out


def sync_google_ads(ds: DataSource, days: int = 30) -> bool:
    if not ds.credentials_encrypted:
        logger.error("DataSource %s: No credentials for google_ads", ds.id)
        _persist_error(ds, "Missing Google Ads credentials")
        return False

    try:
        creds = decrypt_credentials(ds.credentials_encrypted)
    except CredentialsDecryptError as e:
        logger.error("DataSource %s: google_ads decrypt failed: %s", ds.id, e)
        mark_reauth_required(ds, str(e))
        db = SessionLocal()
        try:
            db.merge(ds)
            db.commit()
        finally:
            db.close()
        return False
    customer_id = _digits(str(creds.get("customer_id") or creds.get("client_customer_id") or ""))
    if not customer_id:
        _persist_error(ds, "Missing customer_id")
        return False

    developer_token = _developer_token(creds)
    if not developer_token:
        _persist_error(
            ds,
            "Missing developer_token (set on datasource, Settings, or GOOGLE_ADS_DEVELOPER_TOKEN)",
        )
        return False

    login_customer_id = _digits(str(creds.get("login_customer_id") or creds.get("mcc_id") or ""))

    try:
        access_token, updated = _refresh_access_token(creds)
        if updated.get("access_token") != creds.get("access_token"):
            db = SessionLocal()
            try:
                ds.credentials_encrypted = encrypt_credentials(updated)
                db.merge(ds)
                db.commit()
            finally:
                db.close()
        rows = _gaql_rows(access_token, developer_token, customer_id, login_customer_id, days=days)
        try:
            term_rows = _gaql_search_term_rows(
                access_token, developer_token, customer_id, login_customer_id, days=days
            )
        except Exception as e:
            logger.warning("google_ads search terms optional fetch failed: %s", e)
            term_rows = []
    except Exception as e:
        logger.error("google_ads sync failed for DataSource %s: %s", ds.id, e)
        _persist_error(ds, str(e))
        return False

    if not rows:
        _persist_error(ds, f"Google Ads returned 0 campaign rows for LAST_{days}_DAYS")
        return False

    ok = persist_campaign_metrics(ds, "google_ads", rows)
    if ok and term_rows:
        n = persist_search_term_metrics(ds, "google_ads", term_rows)
        logger.info("google_ads search_term rows persisted: %s points", n)
    return ok


def _persist_error(ds: DataSource, message: str) -> None:
    mark_error(ds, message)
    db = SessionLocal()
    try:
        db.merge(ds)
        db.commit()
    finally:
        db.close()
