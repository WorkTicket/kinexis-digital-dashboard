"""
Google OAuth router — Sign in with Google for GSC + GA4.
"""

import html
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.google_oauth import (
    is_google_oauth_configured,
    create_oauth_state,
    verify_oauth_state,
    build_auth_url,
    exchange_code_for_tokens,
    fetch_google_email,
    store_global_credentials,
    import_google_datasources,
    get_google_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["google-auth"])

SUCCESS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Kinexis — Google connected</title>
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
    <h1>Google account connected</h1>
    <p>Search Console and Analytics have been linked to your domains.<br>You can return to Kinexis.</p>
  </div>
</body>
</html>
"""


def _error_html(message: str) -> str:
    return ERROR_HTML.replace("{message}", html.escape(message, quote=True))


ERROR_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Kinexis — Google sign-in failed</title>
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
    <h1>Google sign-in failed</h1>
    <p>{message}</p>
  </div>
</body>
</html>
"""


def _sync_linked_clients_bg(client_ids: list[int]) -> None:
    """Pull metrics after OAuth without blocking the browser callback."""
    if not client_ids:
        return
    from app.routers.metrics import run_sync_client

    db = SessionLocal()
    try:
        for client_id in client_ids:
            try:
                run_sync_client(client_id, db)
            except Exception as sync_exc:
                logger.warning(
                    "Post-OAuth metric sync failed for client %s: %s",
                    client_id,
                    sync_exc,
                )
    finally:
        db.close()


@router.get("/status")
def google_status(db: Session = Depends(get_db)):
    return get_google_status(db)


@router.get("/start")
def google_start(db: Session = Depends(get_db)):
    if not is_google_oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not available in this Kinexis build yet.",
        )
    state = create_oauth_state(db)
    return {"auth_url": build_auth_url(state)}


@router.get("/callback")
def google_callback(
    background_tasks: BackgroundTasks,
    code: str = "",
    state: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    if error:
        return HTMLResponse(_error_html(error), status_code=400)
    if not code or not verify_oauth_state(db, state):
        return HTMLResponse(_error_html("Invalid or expired sign-in session."), status_code=400)

    try:
        token_data = exchange_code_for_tokens(code)
        email = fetch_google_email(token_data.get("access_token", ""))
        store_global_credentials(db, token_data, email)
        summary = import_google_datasources(db, token_data)
        logger.info("Google OAuth complete for %s: %s", email, summary)

        linked_ids = summary.get("linked_client_ids") or []
        if linked_ids:
            background_tasks.add_task(_sync_linked_clients_bg, list(linked_ids))

        return HTMLResponse(SUCCESS_HTML)
    except Exception as exc:
        logger.exception("Google OAuth callback failed: %s", exc)
        return HTMLResponse(
            _error_html("Sign-in failed. Please close this window and try again."),
            status_code=500,
        )


@router.post("/resync")
def google_resync(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from app.google_oauth import get_stored_token_data

    token_data = get_stored_token_data(db)
    if not token_data:
        raise HTTPException(status_code=400, detail="Google account not connected")
    summary = import_google_datasources(db, token_data)

    linked_ids = summary.get("linked_client_ids") or []
    if linked_ids:
        # Link immediately; metric pull continues in the background so Continue isn't blocked.
        background_tasks.add_task(_sync_linked_clients_bg, list(linked_ids))

    return {"ok": True, **summary, "synced": "background"}
