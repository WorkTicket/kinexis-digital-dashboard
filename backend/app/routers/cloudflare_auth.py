"""
Cloudflare OAuth router — Sign in with Cloudflare for zone discovery.
"""

import html
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.cloudflare_oauth import (
    is_cloudflare_oauth_configured,
    create_oauth_session,
    consume_oauth_session,
    build_auth_url,
    exchange_code_for_tokens,
    fetch_user_info,
    store_global_credentials,
    import_cloudflare_zones,
    get_cloudflare_status,
    get_valid_access_token,
    sync_all_cloudflare_metrics,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/cloudflare", tags=["cloudflare-auth"])

SUCCESS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Kinexis — Cloudflare connected</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #0F172A; color: #e2e8f0;
           display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
    .card { text-align: center; padding: 2rem; max-width: 420px; }
    h1 { color: #22c55e; font-size: 1.25rem; margin-bottom: 0.5rem; }
    p { color: #94a3b8; font-size: 0.9rem; line-height: 1.5; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Cloudflare account connected</h1>
    <p>Your zones have been imported as clients.<br>You can return to Kinexis.</p>
  </div>
</body>
</html>
"""

ERROR_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Kinexis — Cloudflare sign-in failed</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #0F172A; color: #e2e8f0;
           display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
    .card { text-align: center; padding: 2rem; max-width: 420px; }
    h1 { color: #f87171; font-size: 1.25rem; margin-bottom: 0.5rem; }
    p { color: #94a3b8; font-size: 0.9rem; line-height: 1.5; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Cloudflare sign-in failed</h1>
    <p>{message}<br>Close this tab and try again from Kinexis.</p>
  </div>
</body>
</html>
"""


def _error_html(message: str) -> str:
    return ERROR_HTML.replace("{message}", html.escape(message, quote=True))


def _sync_cloudflare_metrics_bg() -> None:
    db = SessionLocal()
    try:
        sync_all_cloudflare_metrics(db)
    except Exception:
        logger.exception("Background Cloudflare metric sync failed")
    finally:
        db.close()


def _link_google_after_cf_bg() -> None:
    from app.google_oauth import get_stored_token_data, import_google_datasources

    db = SessionLocal()
    try:
        google_token = get_stored_token_data(db)
        if google_token:
            import_google_datasources(db, google_token)
    except Exception as exc:
        logger.warning("Google auto-link after Cloudflare OAuth failed: %s", exc)
    finally:
        db.close()


@router.get("/status")
def cloudflare_status(db: Session = Depends(get_db)):
    return get_cloudflare_status(db)


@router.get("/start")
def cloudflare_start(db: Session = Depends(get_db)):
    if not is_cloudflare_oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Cloudflare sign-in is not available in this Kinexis build yet.",
        )
    state, challenge = create_oauth_session(db)
    return {"auth_url": build_auth_url(state, challenge)}


@router.get("/callback")
def cloudflare_callback(
    background_tasks: BackgroundTasks,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    db: Session = Depends(get_db),
):
    if error:
        detail = error_description.strip() or error
        return HTMLResponse(_error_html(detail), status_code=400)
    code_verifier = consume_oauth_session(db, state)
    if not code or not code_verifier:
        return HTMLResponse(_error_html("Invalid or expired sign-in session."), status_code=400)

    try:
        token_data = exchange_code_for_tokens(code, code_verifier)
        access_token = token_data.get("access_token", "")
        if not access_token:
            raise ValueError("Cloudflare did not return an access token.")

        user_info = fetch_user_info(access_token)
        email = user_info.get("email", "")
        account_name = user_info.get("name", "") or email
        store_global_credentials(db, token_data, email=email, account_name=account_name)

        try:
            summary = import_cloudflare_zones(db, access_token)
            account_name = summary.get("account_name") or account_name
            store_global_credentials(db, token_data, email=email, account_name=account_name)
        except Exception:
            logger.exception("Cloudflare zone import failed after sign-in")
            # Account is connected; user can resync zones from Kinexis.
            return HTMLResponse(SUCCESS_HTML)

        background_tasks.add_task(_sync_cloudflare_metrics_bg)
        background_tasks.add_task(_link_google_after_cf_bg)

        logger.info("Cloudflare OAuth complete for %s: %s", email, summary)
        return HTMLResponse(SUCCESS_HTML)
    except Exception as exc:
        logger.exception("Cloudflare OAuth callback failed")
        return HTMLResponse(
            _error_html("Sign-in failed. Please close this window and try again."),
            status_code=500,
        )


@router.post("/resync")
def cloudflare_resync(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    access_token = get_valid_access_token(db)
    if not access_token:
        raise HTTPException(status_code=400, detail="Cloudflare account not connected")
    summary = import_cloudflare_zones(db, access_token)

    from app.google_oauth import get_stored_token_data, import_google_datasources

    google_token = get_stored_token_data(db)
    if google_token:
        try:
            import_google_datasources(db, google_token)
        except Exception as exc:
            logger.warning("Google auto-link after Cloudflare resync failed: %s", exc)

    background_tasks.add_task(_sync_cloudflare_metrics_bg)
    return {"ok": True, **summary}
