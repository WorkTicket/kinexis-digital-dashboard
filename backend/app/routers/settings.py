"""App settings — AI provider and optional connector keys stored in AppSetting."""

from typing import Optional
import shutil
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, engine
from app.models import AppSetting
from app.config import (
    AI_PROVIDER,
    ANTHROPIC_API_KEY,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_FALLBACK_MODEL,
    DATABASE_URL,
)
from app.ai_client import ai_configured, complete, diagnose_ai, ollama_status
from app.credentials import (
    decrypt_secret,
    encrypt_secret,
    is_masked_placeholder,
    mask_secret,
)
from app.local_auth import require_api_token
from app.public_urls import portal_ready, sync_portal_flag_file
from app.timeutil import utcnow

router = APIRouter(prefix="/settings", tags=["settings"])


def _portal_status(db: Session) -> dict:
    return portal_ready(db)

_config_lock = threading.Lock()

SECRET_KEYS = frozenset({
    "pagespeed_api_key",
    "bing_api_key",
    "clarity_api_token",
    "google_ads_developer_token",
})


def sync_ai_settings_from_db(db: Session) -> None:
    """Apply persisted AI settings onto runtime config (env + module vars)."""
    import os
    import app.config as cfg

    settings_to_apply = {}
    provider = _get(db, "ai_provider", "")
    if provider:
        settings_to_apply["AI_PROVIDER"] = provider.strip().lower()
    base = _get(db, "ollama_base_url", "")
    if base:
        settings_to_apply["OLLAMA_BASE_URL"] = base
    model = _get(db, "ollama_model", "")
    if model:
        settings_to_apply["OLLAMA_MODEL"] = model
    fallback = _get(db, "ollama_fallback_model", "")
    if fallback is not None and fallback != "":
        settings_to_apply["OLLAMA_FALLBACK_MODEL"] = fallback

    with _config_lock:
        for key, value in settings_to_apply.items():
            os.environ[key] = value
            setattr(cfg, key, value)


SETTING_KEYS = [
    "ai_provider",
    "ollama_base_url",
    "ollama_model",
    "ollama_fallback_model",
    "pagespeed_api_key",
    "bing_api_key",
    "clarity_api_token",
    "google_ads_developer_token",
    "cloudflare_api_token",
    "assignee_presets",
    "my_agent_name",
    "impact_window_days",
    "agency_name",
    "agency_accent",
    "agency_logo_url",
    "portal_enabled",
    "public_base_url",
]


def _get_raw(db: Session, key: str, default: str = "") -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row and row.value is not None else default


def _get(db: Session, key: str, default: str = "") -> str:
    raw = _get_raw(db, key, default)
    if key in SECRET_KEYS or key == "cloudflare_api_token":
        return decrypt_secret(raw) if raw else default
    return raw


def get_secret_setting(db: Session, key: str, default: str = "") -> str:
    """Decrypt a secret setting for connector use."""
    return _get(db, key, default)


def _set(db: Session, key: str, value: Optional[str]):
    if key in SECRET_KEYS or key == "cloudflare_api_token":
        if value is None or value == "":
            stored = ""
        else:
            stored = encrypt_secret(str(value))
    else:
        stored = value
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = stored
    else:
        db.add(AppSetting(key=key, value=stored))


def _sqlite_path() -> Optional[Path]:
    url = DATABASE_URL or ""
    if url.startswith("sqlite:///"):
        raw = url.replace("sqlite:///", "", 1)
        return Path(raw)
    return None


def _validate_ollama_base_url(value: str) -> str:
    """Restrict Ollama base URL to loopback hosts."""
    raw = (value or "").strip()
    if not raw:
        return "http://127.0.0.1:11434"
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = (parsed.hostname or "").lower()
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise HTTPException(
            status_code=400,
            detail="ollama_base_url must point to localhost / 127.0.0.1 / ::1",
        )
    scheme = parsed.scheme or "http"
    if scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="ollama_base_url must be http(s)")
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path if parsed.path and parsed.path != "/" else ""
    host_out = "127.0.0.1" if host in ("localhost", "127.0.0.1") else host
    if host == "::1":
        host_out = "[::1]"
    return f"{scheme}://{host_out}{port}{path}"


class SettingsUpdate(BaseModel):
    ai_provider: Optional[str] = None
    ollama_base_url: Optional[str] = None
    ollama_model: Optional[str] = None
    ollama_fallback_model: Optional[str] = None
    pagespeed_api_key: Optional[str] = None
    bing_api_key: Optional[str] = None
    clarity_api_token: Optional[str] = None
    google_ads_developer_token: Optional[str] = None
    cloudflare_api_token: Optional[str] = None
    assignee_presets: Optional[str] = None
    my_agent_name: Optional[str] = None
    impact_window_days: Optional[int] = None
    agency_name: Optional[str] = None
    agency_accent: Optional[str] = None
    agency_logo_url: Optional[str] = None
    portal_enabled: Optional[bool] = None
    public_base_url: Optional[str] = None


@router.get("/")
def get_settings(db: Session = Depends(get_db)):
    provider = _get(db, "ai_provider", AI_PROVIDER)
    window_raw = _get(db, "impact_window_days", "14")
    try:
        impact_window_days = int(window_raw or 14)
    except ValueError:
        impact_window_days = 14
    db_path = _sqlite_path()
    ready = False
    if provider == "ollama" and ai_configured():
        status = ollama_status()
        ready = bool(status.get("reachable") and status.get("primary_present"))
    elif provider == "anthropic":
        key = ANTHROPIC_API_KEY or ""
        ready = bool(key) and key.startswith("sk-ant-")

    ps = _get(db, "pagespeed_api_key", "")
    bing = _get(db, "bing_api_key", "")
    clarity = _get(db, "clarity_api_token", "")
    import app.config as cfg

    ads_dev = _get(db, "google_ads_developer_token", "") or (
        getattr(cfg, "GOOGLE_ADS_DEVELOPER_TOKEN", "") or ""
    )

    return {
        "ai_provider": provider,
        "ollama_base_url": _get(db, "ollama_base_url", OLLAMA_BASE_URL),
        "ollama_model": _get(db, "ollama_model", OLLAMA_MODEL),
        "ollama_fallback_model": _get(db, "ollama_fallback_model", OLLAMA_FALLBACK_MODEL),
        "anthropic_configured": bool(ANTHROPIC_API_KEY),
        "ai_ready": ready,
        "pagespeed_api_key": mask_secret(ps),
        "pagespeed_api_key_configured": bool(ps),
        "bing_api_key": mask_secret(bing),
        "bing_api_key_configured": bool(bing),
        "clarity_api_token": mask_secret(clarity),
        "clarity_api_token_configured": bool(clarity),
        "google_ads_developer_token": mask_secret(ads_dev),
        "google_ads_developer_token_configured": bool(ads_dev),
        "cloudflare_api_token": mask_secret(_get(db, "cloudflare_api_token", "")),
        "cloudflare_api_token_configured": bool(_get(db, "cloudflare_api_token", "")),
        "assignee_presets": _get(db, "assignee_presets", "Cursor"),
        "my_agent_name": _get(db, "my_agent_name", ""),
        "impact_window_days": impact_window_days,
        "agency_name": _get(db, "agency_name", ""),
        "agency_accent": _get(db, "agency_accent", ""),
        "agency_logo_url": _get(db, "agency_logo_url", ""),
        "portal_enabled": (_get(db, "portal_enabled", "0") or "0").strip().lower()
        in ("1", "true", "yes", "on"),
        "public_base_url": _get(db, "public_base_url", ""),
        "portal": _portal_status(db),
        "database_path": str(db_path) if db_path else None,
    }


@router.put("/")
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "impact_window_days":
            days = int(value) if value is not None else 14
            if days not in (7, 14, 28):
                days = 14
            _set(db, key, str(days))
            continue
        if key == "portal_enabled":
            _set(db, key, "1" if value else "0")
            continue
        if key == "public_base_url" and value is not None:
            from app.public_urls import normalize_public_base

            value = normalize_public_base(str(value))
        if key in SECRET_KEYS and is_masked_placeholder(str(value) if value is not None else ""):
            continue
        if key == "ollama_base_url" and value is not None:
            value = _validate_ollama_base_url(str(value))
        if key in SETTING_KEYS:
            _set(db, key, value if value is None else str(value))
            if key in ("ai_provider", "ollama_base_url", "ollama_model", "ollama_fallback_model") and value:
                import os
                import app.config as cfg

                with _config_lock:
                    if key == "ai_provider":
                        os.environ["AI_PROVIDER"] = value
                        cfg.AI_PROVIDER = value
                    elif key == "ollama_base_url":
                        os.environ["OLLAMA_BASE_URL"] = value
                        cfg.OLLAMA_BASE_URL = value
                    elif key == "ollama_model":
                        os.environ["OLLAMA_MODEL"] = value
                        cfg.OLLAMA_MODEL = value
                    elif key == "ollama_fallback_model":
                        os.environ["OLLAMA_FALLBACK_MODEL"] = value
                        cfg.OLLAMA_FALLBACK_MODEL = value
    db.commit()
    enabled = (_get(db, "portal_enabled", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    sync_portal_flag_file(
        enabled=enabled,
        public_base_url=_get(db, "public_base_url", ""),
        database_url=DATABASE_URL,
    )
    return get_settings(db)


@router.post("/backup")
def backup_database(request: Request):
    """Copy the SQLite database to a timestamped backup next to it."""
    require_api_token(request)
    src = _sqlite_path()
    if not src or not src.exists():
        raise HTTPException(status_code=400, detail="SQLite database path not found")
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass
    stamp = utcnow().strftime("%Y%m%d-%H%M%S")
    backup_dir = src.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"{src.stem}-{stamp}{src.suffix}"
    shutil.copy2(src, dest)
    return {
        "ok": True,
        "filename": dest.name,
        "message": f"Backup saved as {dest.name}",
    }


@router.post("/test-ai")
def test_ai():
    """Quick connectivity check for the configured AI provider."""
    pre = diagnose_ai()
    if not pre.get("ok"):
        return {"ok": False, "message": pre.get("message") or "AI is not ready."}
    text = complete(
        system="You are a connectivity probe. Reply with exactly: OK",
        user="Reply with exactly: OK",
        max_tokens=8,
        temperature=0.0,
    )
    if not text:
        return {
            "ok": False,
            "message": (
                "AI request failed after connecting. Check the model is loaded in Ollama "
                "(first run can take a minute) or that your Anthropic key is valid."
            ),
        }
    sample = " ".join(text.strip().split())[:80]
    return {"ok": True, "message": "AI connection works", "sample": sample}


@router.get("/ai-usage")
def ai_usage(db: Session = Depends(get_db)):
    from app.ai_usage import usage_summary

    return usage_summary(db, days=7)


@router.post("/reset-all")
def reset_all_data(request: Request, db: Session = Depends(get_db)):
    """Drop all data and reset to fresh state. Destructive — cannot be undone."""
    require_api_token(request)
    from app.models import Base
    from app.database import engine

    try:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}")

    return {"ok": True, "message": "All data reset. Please reconnect Cloudflare."}
