"""
Google OAuth helpers — sign in once, auto-link GSC + GA4 to imported clients.
"""

import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, BACKEND_PORT, BACKEND_HOST
from app.credentials import encrypt_credentials, decrypt_credentials
from app.models import Client, DataSource, AppSetting
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
    # Live Google Business Profile Performance API (optional — re-auth after upgrade)
    "https://www.googleapis.com/auth/business.manage",
    "openid",
    "email",
    "profile",
]

_REDIRECT_SCHEME = os.getenv("KINEAXIS_REDIRECT_SCHEME", "http")
REDIRECT_URI = f"{_REDIRECT_SCHEME}://{BACKEND_HOST}:{BACKEND_PORT}/auth/google/callback"

SETTINGS_KEY_CREDS = "google_oauth_credentials"
SETTINGS_KEY_EMAIL = "google_oauth_email"
SETTINGS_KEY_STATE = "google_oauth_state"


def is_google_oauth_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def _get_setting(db: Session, key: str) -> Optional[str]:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


def _set_setting(db: Session, key: str, value: str):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def normalize_domain(value: str) -> str:
    s = (value or "").lower().strip()
    if s.startswith("sc-domain:"):
        return s.replace("sc-domain:", "", 1)
    s = s.replace("https://", "").replace("http://", "")
    host = s.rstrip("/").split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def domains_compatible(a: str, b: str) -> bool:
    """Exact or parent/subdomain match (blog.example.com ↔ example.com)."""
    if not a or not b:
        return False
    if a == b:
        return True
    return a.endswith("." + b) or b.endswith("." + a)


def client_match_domains(client: Client) -> list[str]:
    """Client name plus optional profile aliases (domains / aliases / website)."""
    domains: list[str] = []
    seen: set[str] = set()

    def add(raw: str):
        d = normalize_domain(raw)
        if d and d not in seen:
            seen.add(d)
            domains.append(d)

    add(client.name or "")
    try:
        profile = json.loads(client.profile_json or "{}")
    except Exception:
        profile = {}
    if not isinstance(profile, dict):
        profile = {}

    for key in ("website", "primary_domain", "domain"):
        val = profile.get(key)
        if isinstance(val, str):
            add(val)

    for key in ("domains", "aliases"):
        val = profile.get(key)
        if isinstance(val, str):
            for part in val.replace(";", ",").split(","):
                add(part.strip())
        elif isinstance(val, list):
            for part in val:
                if isinstance(part, str):
                    add(part)

    return domains


def _lookup_by_domain(by_domain: dict[str, str], client_domain: str) -> Optional[str]:
    if not client_domain:
        return None
    if client_domain in by_domain:
        return by_domain[client_domain]
    # Prefer longest matching domain (most specific)
    matches = [
        (domain, value)
        for domain, value in by_domain.items()
        if domains_compatible(client_domain, domain)
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: len(item[0]), reverse=True)
    return matches[0][1]


def _lookup_for_client(by_domain: dict[str, str], client: Client) -> Optional[str]:
    for domain in client_match_domains(client):
        hit = _lookup_by_domain(by_domain, domain)
        if hit:
            return hit
    return None


SETTINGS_KEY_STATE_TS = "google_oauth_state_ts"
_OAUTH_STATE_TTL_SEC = 600


def create_oauth_state(db: Session) -> str:
    state = secrets.token_urlsafe(24)
    _set_setting(db, SETTINGS_KEY_STATE, state)
    _set_setting(db, SETTINGS_KEY_STATE_TS, str(int(utcnow().timestamp())))
    return state


def verify_oauth_state(db: Session, state: str) -> bool:
    expected = _get_setting(db, SETTINGS_KEY_STATE)
    ts_raw = _get_setting(db, SETTINGS_KEY_STATE_TS) or ""
    _set_setting(db, SETTINGS_KEY_STATE, "")
    _set_setting(db, SETTINGS_KEY_STATE_TS, "")
    if not expected or not state:
        return False
    try:
        created = int(ts_raw)
        if abs(int(utcnow().timestamp()) - created) > _OAUTH_STATE_TTL_SEC:
            return False
    except ValueError:
        return False
    if len(expected) != len(state):
        return False
    return secrets.compare_digest(expected, state)


def build_auth_url(state: str) -> str:
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


def exchange_code_for_tokens(code: str) -> dict:
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


def fetch_google_email(access_token: str) -> str:
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            return resp.json().get("email", "")
    return ""


def _parse_expiry(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is None else value.replace(tzinfo=None)
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo is None else parsed.replace(tzinfo=None)
    except ValueError:
        return None


def credentials_from_token_data(
    token_data: dict,
    scopes: Optional[list[str]] = None,
) -> Credentials:
    return Credentials(
        token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token_data.get("client_id") or GOOGLE_CLIENT_ID,
        client_secret=token_data.get("client_secret") or GOOGLE_CLIENT_SECRET,
        scopes=scopes or GOOGLE_SCOPES,
        expiry=_parse_expiry(token_data.get("expiry")),
    )


def ensure_fresh_credentials(
    token_data: dict,
    scopes: Optional[list[str]] = None,
    *,
    force: bool = False,
) -> tuple[Credentials, dict, bool]:
    """
    Build Google user credentials and refresh when the access token is missing,
    expired, or has no expiry metadata (common after OAuth link — without expiry,
    google-auth treats a stale token as still valid, which breaks GA4 gRPC).
    Returns (credentials, updated_token_data, did_refresh).
    """
    creds = credentials_from_token_data(token_data, scopes=scopes)
    needs_refresh = bool(
        creds.refresh_token
        and (
            force
            or not creds.token
            or creds.expired
            or creds.expiry is None
        )
    )
    if needs_refresh:
        creds.refresh(Request())
        token_data = dict(token_data)
        token_data["access_token"] = creds.token
        if creds.expiry:
            token_data["expiry"] = creds.expiry.isoformat()
        if not token_data.get("client_id"):
            token_data["client_id"] = GOOGLE_CLIENT_ID
        # Never persist client_secret into stored token blobs
        token_data.pop("client_secret", None)
        return creds, token_data, True
    token_data = dict(token_data)
    token_data.pop("client_secret", None)
    return creds, token_data, False


def persist_datasource_token_update(ds: DataSource, token_data: dict) -> None:
    """Write refreshed OAuth fields back onto a datasource credential blob."""
    ds.credentials_encrypted = encrypt_credentials(token_data)


def get_stored_token_data(db: Session) -> Optional[dict]:
    encrypted = _get_setting(db, SETTINGS_KEY_CREDS)
    if not encrypted:
        return None
    return decrypt_credentials(encrypted)


def get_global_credentials(db: Session) -> Optional[Credentials]:
    token_data = get_stored_token_data(db)
    if not token_data:
        return None
    try:
        creds, updated, did_refresh = ensure_fresh_credentials(token_data)
        if did_refresh:
            _set_setting(db, SETTINGS_KEY_CREDS, encrypt_credentials(updated))
        return creds
    except Exception:
        logger.exception("Failed to load global Google credentials")
        return None


def store_global_credentials(db: Session, token_data: dict, email: str = ""):
    safe = {k: v for k, v in token_data.items() if k != "client_secret"}
    _set_setting(db, SETTINGS_KEY_CREDS, encrypt_credentials(safe))
    if email:
        _set_setting(db, SETTINGS_KEY_EMAIL, email)


def get_google_status(db: Session) -> dict:
    email = _get_setting(db, SETTINGS_KEY_EMAIL) or ""
    connected = bool(_get_setting(db, SETTINGS_KEY_CREDS))
    gsc_count = db.query(DataSource).filter(DataSource.type == "gsc").count()
    ga4_count = db.query(DataSource).filter(DataSource.type == "ga4").count()
    return {
        "configured": is_google_oauth_configured(),
        "connected": connected,
        "email": email,
        "gsc_linked": gsc_count,
        "ga4_linked": ga4_count,
    }


def _credential_payload(token_data: dict, **extra) -> dict:
    # Do not persist GOOGLE_CLIENT_SECRET into per-datasource Fernet blobs —
    # inject from config at refresh time via credentials_from_token_data.
    payload = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "client_id": GOOGLE_CLIENT_ID,
    }
    if token_data.get("expiry"):
        payload["expiry"] = token_data["expiry"]
    elif token_data.get("expires_in"):
        try:
            payload["expiry"] = (
                utcnow() + timedelta(seconds=int(token_data["expires_in"]))
            ).isoformat()
        except (TypeError, ValueError):
            pass
    payload.update(extra)
    return payload


def _list_gsc_sites(credentials: Credentials) -> list[dict]:
    service = build("searchconsole", "v1", credentials=credentials)
    response = service.sites().list().execute()
    return response.get("siteEntry", [])


def _list_ga4_properties(credentials: Credentials) -> list[dict]:
    try:
        from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
    except ImportError:
        logger.warning("google-analytics-admin not installed; GA4 auto-link skipped")
        return []

    client = AnalyticsAdminServiceClient(credentials=credentials)
    properties = []
    for account in client.list_account_summaries():
        for prop in account.property_summaries:
            property_name = prop.property
            property_id = property_name.split("/")[-1]
            domain = ""
            try:
                streams = client.list_data_streams(parent=property_name)
                for stream in streams:
                    web = stream.web_stream_data
                    if web and web.default_uri:
                        domain = normalize_domain(web.default_uri)
                        break
            except Exception:
                pass
            if not domain:
                domain = normalize_domain(prop.display_name)
            properties.append(
                {
                    "property_id": property_id,
                    "display_name": prop.display_name,
                    "domain": domain,
                }
            )
    return properties


def _replace_datasource(db: Session, client_id: int, ds_type: str, creds: dict):
    # Bulk delete avoids StaleDataError when the session still holds old rows
    db.query(DataSource).filter(
        DataSource.client_id == client_id,
        DataSource.type == ds_type,
    ).delete(synchronize_session="fetch")
    db.flush()

    db.add(
        DataSource(
            client_id=client_id,
            type=ds_type,
            credentials_encrypted=encrypt_credentials(creds),
            status="pending",
        )
    )


def import_google_datasources(db: Session, token_data: dict) -> dict:
    credentials = credentials_from_token_data(token_data)
    clients = db.query(Client).order_by(Client.name).all()
    gsc_sites = _list_gsc_sites(credentials)
    ga4_props = _list_ga4_properties(credentials)

    gsc_by_domain: dict[str, str] = {}
    for site in gsc_sites:
        if site.get("permissionLevel") in (None, "siteUnverifiedUser"):
            continue
        site_url = site.get("siteUrl", "")
        domain = normalize_domain(site_url)
        if domain:
            gsc_by_domain[domain] = site_url

    ga4_by_domain: dict[str, str] = {}
    for prop in ga4_props:
        domain = prop.get("domain", "")
        if domain:
            ga4_by_domain[domain] = prop["property_id"]

    gsc_linked = 0
    ga4_linked = 0
    linked_client_ids: set[int] = set()

    for client in clients:
        if not client_match_domains(client):
            continue

        site_url = _lookup_for_client(gsc_by_domain, client)
        if site_url:
            _replace_datasource(
                db,
                client.id,
                "gsc",
                _credential_payload(token_data, site_url=site_url),
            )
            gsc_linked += 1
            linked_client_ids.add(client.id)

        property_id = _lookup_for_client(ga4_by_domain, client)
        if property_id:
            _replace_datasource(
                db,
                client.id,
                "ga4",
                _credential_payload(token_data, property_id=property_id),
            )
            ga4_linked += 1
            linked_client_ids.add(client.id)

    db.commit()
    # Fresh identities before any follow-up sync in the same request
    db.expire_all()
    return {
        "gsc_linked": gsc_linked,
        "ga4_linked": ga4_linked,
        "gsc_available": len(gsc_by_domain),
        "ga4_available": len(ga4_by_domain),
        "clients_scanned": len(clients),
        "linked_client_ids": sorted(linked_client_ids),
        "gsc_domains": sorted(gsc_by_domain.keys()),
        "ga4_domains": sorted(ga4_by_domain.keys()),
    }
