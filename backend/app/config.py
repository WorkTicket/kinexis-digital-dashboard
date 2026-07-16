import json
import os
import sys
from dotenv import load_dotenv

def _load_env():
    search_paths = [os.getcwd()]
    if getattr(sys, 'frozen', False):
        search_paths.insert(0, os.path.dirname(sys.executable))
        if hasattr(sys, '_MEIPASS'):
            search_paths.insert(0, sys._MEIPASS)
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    search_paths.append(backend_dir)
    for d in search_paths:
        p = os.path.join(d, '.env')
        if os.path.isfile(p):
            load_dotenv(p, override=False)
            break

_load_env()

def _load_oauth_defaults() -> dict:
    """Optional bundled sign-in app credentials (set once when building Kinexis)."""
    search_paths = [os.getcwd()]
    if getattr(sys, 'frozen', False):
        search_paths.insert(0, os.path.dirname(sys.executable))
        if hasattr(sys, '_MEIPASS'):
            search_paths.insert(0, sys._MEIPASS)
    search_paths.append(os.path.dirname(os.path.dirname(__file__)))
    for d in search_paths:
        p = os.path.join(d, "oauth.json")
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
    return {}

_oauth_defaults = _load_oauth_defaults()
_google_defaults = _oauth_defaults.get("google", {})
_cloudflare_defaults = _oauth_defaults.get("cloudflare", {})

FERNET_KEY = os.getenv("FERNET_KEY")
if not FERNET_KEY:
    # Dev / first-run: generate a machine-local key next to the DB so we never
    # ship one shared installer secret. Electron injects FERNET_KEY from userData.
    _fernet_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".kinexis_fernet_key")
    _env_fernet_file = os.getenv("FERNET_KEY_FILE", "").strip()
    if _env_fernet_file:
        _fernet_path = _env_fernet_file
    if os.path.isfile(_fernet_path):
        with open(_fernet_path, encoding="utf-8") as _fk:
            FERNET_KEY = _fk.read().strip()
    if not FERNET_KEY:
        try:
            from cryptography.fernet import Fernet as _Fernet
            FERNET_KEY = _Fernet.generate_key().decode()
        except Exception as e:
            raise RuntimeError(
                "FERNET_KEY not set and cryptography library unavailable. "
                f"Ensure 'cryptography' is installed. ({e})"
            ) from e
        try:
            with open(_fernet_path, "w", encoding="utf-8") as _fk:
                _fk.write(FERNET_KEY + "\n")
            try:
                os.chmod(_fernet_path, 0o600)
            except OSError:
                pass
        except OSError as e:
            raise RuntimeError(
                "FERNET_KEY not set and could not persist a local key. "
                "Set FERNET_KEY in .env or FERNET_KEY_FILE."
            ) from e

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID") or _google_defaults.get("client_id", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET") or _google_defaults.get("client_secret", "")
CLOUDFLARE_CLIENT_ID = os.getenv("CLOUDFLARE_CLIENT_ID") or _cloudflare_defaults.get("client_id", "")
CLOUDFLARE_CLIENT_SECRET = os.getenv("CLOUDFLARE_CLIENT_SECRET") or _cloudflare_defaults.get("client_secret", "")
_cf_scopes_env = os.getenv("CLOUDFLARE_OAUTH_SCOPES", "").strip()
CLOUDFLARE_OAUTH_SCOPES = (
    [s.strip() for s in _cf_scopes_env.split() if s.strip()]
    if _cf_scopes_env
    else _cloudflare_defaults.get("scopes")
)
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514").strip()
def _safe_int(key: str, default: int, min_val: int | None = None, max_val: int | None = None) -> int:
    try:
        v = int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        v = default
    if min_val is not None:
        v = max(min_val, v)
    if max_val is not None:
        v = min(max_val, v)
    return v


def _safe_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default

AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").strip().lower() or "ollama"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "kinexis-marketing")
# If primary returns empty/invalid JSON, retry with this model.
OLLAMA_FALLBACK_MODEL = os.getenv("OLLAMA_FALLBACK_MODEL", "qwen3:14b").strip()
# Larger context + lower temp = more detailed, grounded JSON from local models.
# Cap hard: values like 65536 (often set in the user env) thrash VRAM and make
# every completion hit OLLAMA_TIMEOUT, which looks like "AI is broken".
_OLLAMA_NUM_CTX_RAW = _safe_int("OLLAMA_NUM_CTX", 16384)
OLLAMA_NUM_CTX = max(2048, min(_OLLAMA_NUM_CTX_RAW, 16384))
if OLLAMA_NUM_CTX != _OLLAMA_NUM_CTX_RAW:
    import logging as _logging

    _logging.getLogger(__name__).warning(
        "OLLAMA_NUM_CTX=%s clamped to %s (max 16384) to keep local generation reliable",
        _OLLAMA_NUM_CTX_RAW,
        OLLAMA_NUM_CTX,
    )
OLLAMA_TEMPERATURE = _safe_float("OLLAMA_TEMPERATURE", 0.35)
OLLAMA_TIMEOUT = _safe_float("OLLAMA_TIMEOUT", 300.0)
BACKEND_PORT = _safe_int("BACKEND_PORT", 8000)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'kinexis.db')}")

BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")

# Live page HTML snapshots for AI briefs/plans (static fetch; no JS render yet)
PAGE_CONTENT_USER_AGENT = os.getenv(
    "PAGE_CONTENT_USER_AGENT",
    "KinexisAuditBot/1.0 (+https://kinexisdigital.com/bot)",
)
PAGE_CONTENT_CACHE_HOURS = _safe_int("PAGE_CONTENT_CACHE_HOURS", 24)
PAGE_CONTENT_RENDER_JS = os.getenv("PAGE_CONTENT_RENDER_JS", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)

# Licensed SERP API (empty provider = disabled). Never scrape google.com.
SERP_PROVIDER = os.getenv("SERP_PROVIDER", "").strip().lower()  # serpapi | dataforseo | google_cse
SERP_API_KEY = os.getenv("SERP_API_KEY", "").strip()
SERP_GOOGLE_CSE_ID = os.getenv("SERP_GOOGLE_CSE_ID", "").strip()
SERP_MAX_QUERIES_PER_SYNC = _safe_int("SERP_MAX_QUERIES_PER_SYNC", 10)
SERP_CACHE_HOURS = _safe_int("SERP_CACHE_HOURS", 72)

# Google Ads API developer token (can also be set per-datasource or in Settings)
GOOGLE_ADS_DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip()

# Config namespace: modules that import `cfg` get the module itself, so
# runtime mutations from settings.py (setattr) are visible to all callers
# that use `import app.config as cfg` or `from app.config import cfg`.
# Modules using `from app.config import X` get a copy at import time and
# will NOT see runtime updates — only import the config keys you know are
# never changed at runtime.
import sys as _sys
cfg = _sys.modules[__name__]
