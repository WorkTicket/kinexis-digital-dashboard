"""
Onboarding router — Cloudflare sign-in, auto-import, and guided setup.
"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal, engine, Base
from app.models import Client, DataSource, AppSetting
from app.credentials import encrypt_credentials, encrypt_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

CF_BASE = "https://api.cloudflare.com/client/v4"

# Ensure app_settings table exists
Base.metadata.create_all(bind=engine)


def _get_setting(db: Session, key: str) -> Optional[str]:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


def _set_setting(db: Session, key: str, value: str):
    if key == "cloudflare_api_token" and value:
        value = encrypt_secret(value)
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


class ConnectRequest(BaseModel):
    api_token: str = Field(..., min_length=10)


class ConnectResponse(BaseModel):
    success: bool
    account_name: str = ""
    clients_created: int = 0
    datasources_created: int = 0
    zone_count: int = 0
    errors: list[str] = []


class OnboardingStatus(BaseModel):
    cloudflare_connected: bool
    google_connected: bool
    hubspot_connected: bool = False
    fully_connected: bool
    onboarding_complete: bool
    client_count: int = 0


@router.get("/status", response_model=OnboardingStatus)
def get_onboarding_status(db: Session = Depends(get_db)):
    try:
        from app.cloudflare_oauth import is_cloudflare_connected
        from app.google_oauth import get_google_status

        done = _get_setting(db, "onboarding_complete")
        client_count = db.query(Client).count()
        cf_connected = is_cloudflare_connected(db)
        google_connected = get_google_status(db)["connected"]
        hubspot_ds = (
            db.query(DataSource)
            .filter(DataSource.type == "hubspot")
            .first()
        )
        hubspot_connected = False
        if hubspot_ds and hubspot_ds.credentials_encrypted:
            try:
                from app.credentials import decrypt_credentials

                creds = decrypt_credentials(hubspot_ds.credentials_encrypted)
                token = creds.get("access_token") or creds.get("api_token") or creds.get("api_key")
                if token:
                    resp = httpx.get(
                        "https://api.hubapi.com/crm/v3/objects/contacts?limit=1",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=10,
                    )
                    hubspot_connected = resp.status_code == 200
            except Exception:
                pass
        return OnboardingStatus(
            cloudflare_connected=cf_connected,
            google_connected=google_connected,
            hubspot_connected=hubspot_connected,
            fully_connected=cf_connected and google_connected,
            onboarding_complete=done == "true",
            client_count=client_count,
        )
    except Exception:
        logger.exception("Failed to read onboarding status")
        return OnboardingStatus(
            cloudflare_connected=False,
            google_connected=False,
            hubspot_connected=False,
            fully_connected=False,
            onboarding_complete=False,
            client_count=0,
        )


@router.post("/cloudflare/connect", response_model=ConnectResponse)
def connect_cloudflare(data: ConnectRequest, db: Session = Depends(get_db)):
    token = data.api_token.strip()
    result = ConnectResponse(success=False)

    if not token:
        result.errors.append("API token is required")
        return result

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Validate token
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{CF_BASE}/user/tokens/verify", headers=headers)
            if resp.status_code == 200:
                v = resp.json()
                if not v.get("success") or v.get("result", {}).get("status") != "active":
                    result.errors.append("Invalid or inactive API token")
                    return result
            else:
                result.errors.append(f"Token verification failed: HTTP {resp.status_code}")
                return result

            # Get account name
            try:
                acct = client.get(f"{CF_BASE}/accounts", headers=headers, params={"page": 1, "per_page": 1})
                if acct.status_code == 200:
                    data_acct = acct.json()
                    accounts = data_acct.get("result", [])
                    if accounts:
                        result.account_name = accounts[0].get("name", "")
            except Exception:
                pass

            # Fetch all zones
            zones = []
            page = 1
            while True:
                zr = client.get(f"{CF_BASE}/zones", headers=headers, params={"page": page, "per_page": 50})
                if zr.status_code != 200:
                    break
                zd = zr.json()
                if not zd.get("success"):
                    break
                zones.extend(zd.get("result", []))
                info = zd.get("result_info", {})
                if page >= info.get("total_pages", 1):
                    break
                page += 1

            result.zone_count = len(zones)

            # Delete existing Cloudflare datasources from a previous import
            clients_by_name = {c.name.lower(): c for c in db.query(Client).order_by(Client.name).all()}

            # Auto-create / reuse client + datasource for each zone
            linked_client_ids: set[int] = set()
            for zone in zones:
                zone_name = zone.get("name", "")
                zone_id = zone.get("id", "")
                if not zone_name or not zone_id:
                    continue

                try:
                    with db.begin_nested():
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
                            result.clients_created += 1

                        existing = (
                            db.query(DataSource)
                            .filter(
                                DataSource.client_id == client_obj.id,
                                DataSource.type == "cloudflare",
                            )
                            .all()
                        )
                        for ds in existing:
                            db.delete(ds)
                        db.flush()

                        creds = encrypt_credentials({"zone_ids": [zone_id], "api_token": token})
                        ds_obj = DataSource(
                            client_id=client_obj.id,
                            type="cloudflare",
                            credentials_encrypted=creds,
                            status="pending",
                        )
                        db.add(ds_obj)
                        result.datasources_created += 1
                        linked_client_ids.add(client_obj.id)
                except Exception as e:
                    result.errors.append(f"Failed for {zone_name}: {e}")

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

            # Save token
            _set_setting(db, "cloudflare_api_token", token)

            db.commit()
            result.success = True

            from app.google_oauth import get_stored_token_data, import_google_datasources

            token_data = get_stored_token_data(db)
            if token_data:
                try:
                    google_summary = import_google_datasources(db, token_data)
                    linked_ids = google_summary.get("linked_client_ids") or []
                    if linked_ids:
                        from app.routers.metrics import run_sync_client

                        for client_id in linked_ids:
                            try:
                                run_sync_client(client_id, db)
                            except Exception as sync_exc:
                                logger.warning(
                                    "Post-CF Google sync failed for client %s: %s",
                                    client_id,
                                    sync_exc,
                                )
                except Exception as e:
                    logger.warning("Google auto-link after Cloudflare import failed: %s", e)

    except httpx.TimeoutException:
        result.errors.append("Connection to Cloudflare timed out")
    except Exception as e:
        db.rollback()
        result.errors.append(str(e))

    return result


@router.post("/complete")
def complete_onboarding(db: Session = Depends(get_db)):
    _set_setting(db, "onboarding_complete", "true")
    return {"ok": True}


@router.get("/wizard/{client_id}")
def run_onboarding_wizard(client_id: int, db: Session = Depends(get_db)):
    """Auto-detect brand terms, service area, and suggested thresholds from GSC data.

    Eliminates 30+ minutes of manual profile_json editing. Returns a complete
    profile ready for review and confirmation by the agent.
    """
    from app.onboarding_wizard import run_onboarding_wizard as wizard
    try:
        result = wizard(db, client_id)
        return result
    except Exception as e:
        logger.exception("Onboarding wizard failed for client %s", client_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wizard/{client_id}/apply")
def apply_onboarding_wizard(client_id: int, db: Session = Depends(get_db)):
    """Apply the auto-detected profile to the client record."""
    from app.onboarding_wizard import run_onboarding_wizard as wizard
    try:
        result = wizard(db, client_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    import json
    profile_json = result.get("profile_json", "{}")
    client.profile_json = profile_json
    db.commit()
    return {"ok": True, "brand_terms": result.get("brand_terms", []), "primary_location": result.get("primary_location", "")}


@router.post("/reset")
def reset_onboarding(db: Session = Depends(get_db)):
    from app.routers.auth import sign_out

    sign_out(db)
    return {"ok": True}
