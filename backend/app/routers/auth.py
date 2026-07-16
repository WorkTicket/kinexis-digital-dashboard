"""
Combined auth router — status and sign-out for Cloudflare + Google.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppSetting, DataSource
from app.cloudflare_oauth import get_cloudflare_status, clear_cloudflare_auth
from app.google_oauth import get_google_status, SETTINGS_KEY_CREDS as GOOGLE_CREDS_KEY
from app.google_oauth import SETTINGS_KEY_EMAIL as GOOGLE_EMAIL_KEY
from app.google_oauth import SETTINGS_KEY_STATE as GOOGLE_STATE_KEY

router = APIRouter(prefix="/auth", tags=["auth"])


def _delete_setting(db: Session, key: str):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        db.delete(row)


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    cf = get_cloudflare_status(db)
    google = get_google_status(db)
    fully_connected = bool(cf.get("connected")) and bool(google.get("connected"))
    return {
        "cloudflare": cf,
        "google": google,
        "fully_connected": fully_connected,
    }


@router.post("/signout")
def sign_out(db: Session = Depends(get_db)):
    clear_cloudflare_auth(db)

    for key in (GOOGLE_CREDS_KEY, GOOGLE_EMAIL_KEY, GOOGLE_STATE_KEY):
        _delete_setting(db, key)

    done = db.query(AppSetting).filter(AppSetting.key == "onboarding_complete").first()
    if done:
        done.value = "false"

    db.commit()
    return {"ok": True}
