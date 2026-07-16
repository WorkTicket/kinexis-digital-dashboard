"""Public base URL for client portal share links."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _strip_slash(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _valid_public_base(url: str) -> bool:
    raw = _strip_slash(url)
    if not raw:
        return False
    try:
        p = urlparse(raw if "://" in raw else f"https://{raw}")
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    if not host:
        return False
    return True


def normalize_public_base(url: str) -> str:
    raw = _strip_slash(url)
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    return _strip_slash(raw)


def portal_flag_path_from_db_url(database_url: str) -> Optional[Path]:
    url = database_url or ""
    if not url.startswith("sqlite:///"):
        return None
    raw = url.replace("sqlite:///", "", 1)
    return Path(raw).resolve().parent / "kinexis-portal.json"


def sync_portal_flag_file(
    *,
    enabled: bool,
    public_base_url: str = "",
    database_url: str = "",
) -> None:
    """Persist portal mode for Electron (reads this file before spawning backend)."""
    from app.config import DATABASE_URL

    path = portal_flag_path_from_db_url(database_url or DATABASE_URL)
    if path is None:
        return
    payload = {
        "enabled": bool(enabled),
        "public_base_url": normalize_public_base(public_base_url) if public_base_url else "",
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        logger.warning("Could not write portal flag file %s: %s", path, e)


def resolve_public_base_url(db: Optional[Session] = None) -> str:
    """Env PUBLIC_BASE_URL → AppSetting public_base_url → empty (caller falls back)."""
    env = normalize_public_base(os.getenv("PUBLIC_BASE_URL", "") or "")
    if env and _valid_public_base(env):
        return env
    if db is not None:
        try:
            from app.models import AppSetting

            row = db.query(AppSetting).filter(AppSetting.key == "public_base_url").first()
            if row and row.value:
                stored = normalize_public_base(str(row.value))
                if stored and _valid_public_base(stored):
                    return stored
        except Exception:
            pass
    return ""


def absolute_public_url(path: str, db: Optional[Session] = None) -> str:
    """Build absolute share URL. Falls back to loopback when portal URL unset."""
    from app.config import BACKEND_PORT

    base = resolve_public_base_url(db)
    if not base:
        base = f"http://127.0.0.1:{BACKEND_PORT}"
    p = path if path.startswith("/") else f"/{path}"
    return f"{base}{p}"


def portal_ready(db: Optional[Session] = None) -> dict:
    """Status blob for Settings UI."""
    base = resolve_public_base_url(db)
    enabled = False
    if db is not None:
        try:
            from app.models import AppSetting

            row = db.query(AppSetting).filter(AppSetting.key == "portal_enabled").first()
            enabled = (row.value or "").strip().lower() in ("1", "true", "yes", "on")
        except Exception:
            enabled = False
    env_portal = (os.getenv("KINEAXIS_PORTAL_MODE", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    allow_remote = (os.getenv("KINEAXIS_ALLOW_REMOTE", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    is_localhost = (not base) or any(
        h in base for h in ("127.0.0.1", "localhost", "[::1]")
    )
    return {
        "portal_enabled": enabled or env_portal,
        "public_base_url": base,
        "allow_remote": allow_remote,
        "share_links_reachable": bool(base) and not is_localhost,
        "needs_restart": enabled and not (env_portal or allow_remote),
        "hint": (
            "Paste your Cloudflare Tunnel or ngrok HTTPS URL, enable portal, then restart the app."
            if not base or is_localhost
            else "Share links use your public base URL. Agency API stays token-protected."
        ),
    }
