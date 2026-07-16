"""
Cloudflare account sign-in — sign in once, auto-import zones as clients.
"""

import base64
import hashlib
import logging
import os
import secrets
from typing import Optional
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config import (
    CLOUDFLARE_CLIENT_ID,
    CLOUDFLARE_CLIENT_SECRET,
    CLOUDFLARE_OAUTH_SCOPES,
    BACKEND_PORT,
    BACKEND_HOST,
)
from app.credentials import encrypt_credentials, decrypt_credentials
from app.models import Client, DataSource, AppSetting
from app.timeutil import utcnow

logger = logging.getLogger(__name__)

CF_BASE = "https://api.cloudflare.com/client/v4"
CF_AUTH_URL = "https://dash.cloudflare.com/oauth2/auth"
CF_TOKEN_URL = "https://dash.cloudflare.com/oauth2/token"
CF_USERINFO_URL = "https://dash.cloudflare.com/oauth2/userinfo"

# Must match scopes enabled on the Kinexis OAuth client in Cloudflare.
# Do not request openid/email/profile — Cloudflare manages those.
# offline_access is granted by Cloudflare when the client allows it; do not add it here.
DEFAULT_CLOUDFLARE_SCOPES = [
    "zone.read",
    "account-analytics.read",
    "analytics.read",
    "account-settings.read",
]

_REDIRECT_SCHEME = os.getenv("KINEAXIS_REDIRECT_SCHEME", "http")
REDIRECT_URI = f"{_REDIRECT_SCHEME}://{BACKEND_HOST}:{BACKEND_PORT}/auth/cloudflare/callback"

SETTINGS_KEY_CREDS = "cloudflare_oauth_credentials"
SETTINGS_KEY_EMAIL = "cloudflare_oauth_email"
SETTINGS_KEY_ACCOUNT = "cloudflare_oauth_account"
SETTINGS_KEY_STATE = "cloudflare_oauth_state"
SETTINGS_KEY_PKCE = "cloudflare_oauth_pkce"
SETTINGS_KEY_STATE_TS = "cloudflare_oauth_state_ts"
LEGACY_TOKEN_KEY = "cloudflare_api_token"
_OAUTH_STATE_TTL_SEC = 600


def is_cloudflare_oauth_configured() -> bool:
    return bool(CLOUDFLARE_CLIENT_ID)


def _generate_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


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


def _delete_setting(db: Session, key: str):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        db.delete(row)
        db.commit()


def is_cloudflare_connected(db: Session) -> bool:
    if _get_setting(db, SETTINGS_KEY_CREDS):
        return True
    from app.credentials import decrypt_secret

    legacy = _get_setting(db, LEGACY_TOKEN_KEY)
    if not legacy:
        return False
    return bool(decrypt_secret(legacy).strip())


def create_oauth_session(db: Session) -> tuple[str, str]:
    from datetime import datetime

    state = secrets.token_urlsafe(24)
    verifier, challenge = _generate_pkce()
    _set_setting(db, SETTINGS_KEY_STATE, state)
    _set_setting(db, SETTINGS_KEY_PKCE, verifier)
    _set_setting(db, SETTINGS_KEY_STATE_TS, str(int(utcnow().timestamp())))
    return state, challenge


def consume_oauth_session(db: Session, state: str) -> Optional[str]:
    from datetime import datetime

    expected = _get_setting(db, SETTINGS_KEY_STATE)
    verifier = _get_setting(db, SETTINGS_KEY_PKCE)
    ts_raw = _get_setting(db, SETTINGS_KEY_STATE_TS) or ""
    if not expected or not verifier or not state:
        return None
    try:
        created = int(ts_raw)
        if abs(int(utcnow().timestamp()) - created) > _OAUTH_STATE_TTL_SEC:
            _set_setting(db, SETTINGS_KEY_STATE, "")
            _set_setting(db, SETTINGS_KEY_PKCE, "")
            _set_setting(db, SETTINGS_KEY_STATE_TS, "")
            return None
    except ValueError:
        _set_setting(db, SETTINGS_KEY_STATE, "")
        _set_setting(db, SETTINGS_KEY_PKCE, "")
        _set_setting(db, SETTINGS_KEY_STATE_TS, "")
        return None
    if len(expected) != len(state):
        return None
    if not secrets.compare_digest(expected, state):
        return None
    _set_setting(db, SETTINGS_KEY_STATE, "")
    _set_setting(db, SETTINGS_KEY_PKCE, "")
    _set_setting(db, SETTINGS_KEY_STATE_TS, "")
    return verifier


def get_cloudflare_scopes() -> list[str]:
    scopes = CLOUDFLARE_OAUTH_SCOPES or DEFAULT_CLOUDFLARE_SCOPES
    return [s for s in scopes if s]


def build_auth_url(state: str, code_challenge: str) -> str:
    params = {
        "client_id": CLOUDFLARE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(get_cloudflare_scopes()),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{CF_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(code: str, code_verifier: str = "") -> dict:
    data = {
        "code": code,
        "client_id": CLOUDFLARE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    if code_verifier:
        data["code_verifier"] = code_verifier
    if CLOUDFLARE_CLIENT_SECRET:
        data["client_secret"] = CLOUDFLARE_CLIENT_SECRET

    with httpx.Client(timeout=30) as client:
        resp = client.post(CF_TOKEN_URL, data=data)
        if resp.status_code != 200:
            detail = resp.text.strip() or resp.reason_phrase
            raise ValueError(f"Cloudflare token exchange failed ({resp.status_code}): {detail}")
        payload = resp.json()
        if payload.get("error"):
            description = payload.get("error_description") or payload["error"]
            raise ValueError(f"Cloudflare token exchange failed: {description}")
        return payload


def refresh_access_token(token_data: dict) -> dict:
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return token_data

    data = {
        "client_id": CLOUDFLARE_CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if CLOUDFLARE_CLIENT_SECRET:
        data["client_secret"] = CLOUDFLARE_CLIENT_SECRET

    with httpx.Client(timeout=30) as client:
        resp = client.post(CF_TOKEN_URL, data=data)
        resp.raise_for_status()
        refreshed = resp.json()
        token_data = dict(token_data)
        token_data["access_token"] = refreshed.get("access_token", token_data.get("access_token"))
        if refreshed.get("refresh_token"):
            token_data["refresh_token"] = refreshed["refresh_token"]
        if refreshed.get("expires_in"):
            token_data["expires_in"] = refreshed["expires_in"]
        return token_data


def fetch_user_info(access_token: str) -> dict:
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            CF_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 200:
            return resp.json()
    return {}


def get_stored_token_data(db: Session) -> Optional[dict]:
    encrypted = _get_setting(db, SETTINGS_KEY_CREDS)
    if not encrypted:
        return None
    return decrypt_credentials(encrypted)


def get_valid_access_token(db: Session) -> Optional[str]:
    token_data = get_stored_token_data(db)
    if not token_data:
        from app.credentials import decrypt_secret

        legacy = _get_setting(db, LEGACY_TOKEN_KEY)
        if not legacy:
            return None
        plain = decrypt_secret(legacy).strip()
        return plain or None

    try:
        token_data = refresh_access_token(token_data)
        # Strip client_secret before re-persist
        clean = {k: v for k, v in token_data.items() if k != "client_secret"}
        _set_setting(db, SETTINGS_KEY_CREDS, encrypt_credentials(clean))
        return token_data.get("access_token")
    except Exception:
        # Never hand callers a known-stale access token after refresh fails —
        # that surfaces as 403 "Invalid access token" on every zone sync.
        logger.exception("Failed to refresh Cloudflare OAuth token — reconnect required")
        return None


def store_global_credentials(db: Session, token_data: dict, email: str = "", account_name: str = ""):
    payload = {k: v for k, v in dict(token_data).items() if k != "client_secret"}
    payload["client_id"] = CLOUDFLARE_CLIENT_ID
    # Keep client_secret only in env/oauth.json — not in DB
    _set_setting(db, SETTINGS_KEY_CREDS, encrypt_credentials(payload))
    if email:
        _set_setting(db, SETTINGS_KEY_EMAIL, email)
    if account_name:
        _set_setting(db, SETTINGS_KEY_ACCOUNT, account_name)


def get_cloudflare_status(db: Session) -> dict:
    email = _get_setting(db, SETTINGS_KEY_EMAIL) or ""
    account_name = _get_setting(db, SETTINGS_KEY_ACCOUNT) or ""
    connected = is_cloudflare_connected(db)
    zone_count = db.query(DataSource).filter(DataSource.type == "cloudflare").count()
    client_count = db.query(Client).count()
    return {
        "configured": is_cloudflare_oauth_configured(),
        "connected": connected,
        "email": email,
        "account_name": account_name,
        "zone_count": zone_count,
        "client_count": client_count,
    }


def _cf_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def _fetch_account_name(access_token: str) -> str:
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{CF_BASE}/accounts",
                headers=_cf_headers(access_token),
                params={"page": 1, "per_page": 1},
            )
            if resp.status_code == 200:
                accounts = resp.json().get("result", [])
                if accounts:
                    return accounts[0].get("name", "")
    except Exception:
        logger.exception("Failed to fetch Cloudflare account name")
    return ""


def _fetch_all_zones(access_token: str) -> list[dict]:
    zones = []
    page = 1
    headers = _cf_headers(access_token)

    with httpx.Client(timeout=30) as client:
        while True:
            resp = client.get(
                f"{CF_BASE}/zones",
                headers=headers,
                params={"page": page, "per_page": 50},
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data.get("success"):
                break
            zones.extend(data.get("result", []))
            info = data.get("result_info", {})
            if page >= info.get("total_pages", 1):
                break
            page += 1

    return zones


def import_cloudflare_zones(db: Session, access_token: str) -> dict:
    account_name = _fetch_account_name(access_token)
    zones = _fetch_all_zones(access_token)

    clients_by_name = {c.name.lower(): c for c in db.query(Client).order_by(Client.name).all()}
    clients_created = 0
    zones_linked = 0
    linked_client_ids: set[int] = set()

    for zone in zones:
        zone_name = zone.get("name", "")
        zone_id = zone.get("id", "")
        if not zone_name or not zone_id:
            continue

        client_obj = clients_by_name.get(zone_name.lower())
        if not client_obj:
            client_obj = Client(
                name=zone_name,
                industry="",
                brand_color="#3B82F6",
            )
            db.add(client_obj)
            db.flush()
            clients_by_name[zone_name.lower()] = client_obj
            clients_created += 1

        # Replace per-client so we never accumulate duplicate Cloudflare rows
        existing = (
            db.query(DataSource)
            .filter(DataSource.client_id == client_obj.id, DataSource.type == "cloudflare")
            .all()
        )
        for ds in existing:
            db.delete(ds)
        db.flush()

        creds = encrypt_credentials({"zone_ids": [zone_id]})
        db.add(
            DataSource(
                client_id=client_obj.id,
                type="cloudflare",
                credentials_encrypted=creds,
                status="pending",
            )
        )
        zones_linked += 1
        linked_client_ids.add(client_obj.id)

    # Drop orphan Cloudflare datasources for clients no longer in the zone list
    if linked_client_ids:
        orphans = (
            db.query(DataSource)
            .filter(
                DataSource.type == "cloudflare",
                ~DataSource.client_id.in_(linked_client_ids),
            )
            .all()
        )
        for ds in orphans:
            db.delete(ds)

    _delete_setting(db, LEGACY_TOKEN_KEY)
    db.commit()

    return {
        "account_name": account_name,
        "clients_created": clients_created,
        "zone_count": zones_linked,
    }


def sync_all_cloudflare_metrics(db: Session) -> dict[int, bool]:
    """Pull Cloudflare analytics for every linked zone after sign-in or resync."""
    from app.connectors.cloudflare import sync_cloudflare

    results: dict[int, bool] = {}
    sources = db.query(DataSource).filter(DataSource.type == "cloudflare").all()
    for ds in sources:
        try:
            results[ds.client_id] = sync_cloudflare(ds)
        except Exception:
            logger.exception("Cloudflare metric sync failed for DataSource %s", ds.id)
            results[ds.client_id] = False
    return results


def clear_cloudflare_auth(db: Session):
    for key in (
        SETTINGS_KEY_CREDS,
        SETTINGS_KEY_EMAIL,
        SETTINGS_KEY_ACCOUNT,
        SETTINGS_KEY_STATE,
        SETTINGS_KEY_PKCE,
        SETTINGS_KEY_STATE_TS,
        LEGACY_TOKEN_KEY,
    ):
        _delete_setting(db, key)

    existing_ds = db.query(DataSource).filter(DataSource.type == "cloudflare").all()
    for ds in existing_ds:
        db.delete(ds)
    db.commit()
