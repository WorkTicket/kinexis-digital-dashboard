"""Local desktop API authentication (Bearer / X-Kinexis-Token) + client portal gate."""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_HEADER = "x-kinexis-token"
_TOKEN_FILENAME = ".kinexis_api_token"

_API_PREFIXES = (
    "/clients",
    "/metrics",
    "/insights",
    "/tasks",
    "/summaries",
    "/actions",
    "/onboarding",
    "/auth",
    "/settings",
    "/rankings",
    "/levers",
    "/pulse",
    "/recommendations",
    "/experiments",
    "/portal",
)

# Public within API namespace (OAuth browser redirects + health/docs).
_PUBLIC_EXACT = frozenset({"/health", "/docs", "/redoc", "/openapi.json"})
_PUBLIC_PREFIXES = (
    "/auth/google/callback",
    "/auth/cloudflare/callback",
)


def _backend_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _token_file_path() -> Path:
    override = os.getenv("KINEAXIS_API_TOKEN_FILE", "").strip()
    if override:
        return Path(override)
    return _backend_dir() / _TOKEN_FILENAME


def resolve_api_token() -> str:
    """Load API token from env, else persist/load a local file (desktop)."""
    env = (os.getenv("KINEAXIS_API_TOKEN") or "").strip()
    if env:
        return env

    path = _token_file_path()
    try:
        if path.is_file():
            existing = path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
    except OSError as e:
        logger.warning("Could not read API token file %s: %s", path, e)

    token = secrets.token_urlsafe(32)
    try:
        path.write_text(token + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        logger.info("Generated local API token at %s", path)
    except OSError as e:
        logger.warning("Could not persist API token file (%s); using in-memory token", e)
    return token


API_TOKEN: str = resolve_api_token()


def auth_required() -> bool:
    """When false (tests), middleware is a no-op for tokens."""
    required = (os.getenv("KINEAXIS_REQUIRE_API_TOKEN", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    if not required:
        logging.getLogger(__name__).warning(
            "KINEAXIS_REQUIRE_API_TOKEN is set to 0 — ALL API ROUTES ARE PUBLIC. "
            "This should only be used for local tests."
        )
    return required


def extract_token(request: Request) -> Optional[str]:
    header = request.headers.get(_HEADER) or request.headers.get("X-Kinexis-Token")
    if header and header.strip():
        return header.strip()
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _is_public_share_get(path: str, method: str) -> bool:
    """Tokenized Pulse / Report portal reads are public; create/revoke stay authenticated."""
    if method.upper() not in ("GET", "HEAD", "OPTIONS"):
        return False
    # /pulse/{token} and /pulse/{token}/html
    if path.startswith("/pulse/"):
        rest = path[len("/pulse/") :].split("/")[0]
        if rest in ("share", ""):
            return False
        return True
    # /portal/report/{token} and /portal/report/{token}/html
    if path.startswith("/portal/report/"):
        rest = path[len("/portal/report/") :].split("/")[0]
        if not rest or rest in ("share", ""):
            return False
        return True
    return False


# Back-compat alias used by tests
_is_public_pulse_get = _is_public_share_get


def _is_api_path(path: str, method: str = "GET") -> bool:
    if path in _PUBLIC_EXACT:
        return False
    if _is_public_share_get(path, method):
        return False
    for prefix in _PUBLIC_PREFIXES:
        if path == prefix or path.startswith(prefix + "?"):
            return False
        if path.startswith(prefix):
            return False
    for prefix in _API_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _client_host(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return ""


def is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "::1", "localhost", "testclient")


def _allow_remote() -> bool:
    return (os.getenv("KINEAXIS_ALLOW_REMOTE", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


class LocalAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path or "/"
        host = _client_host(request)
        allow_remote = _allow_remote()
        public_share = _is_public_share_get(path, request.method)

        if not allow_remote and host and not is_loopback(host):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Remote access denied. Enable Client portal in Settings (or set KINEAXIS_ALLOW_REMOTE=1)."
                },
            )

        # Fail closed: remote bind without token auth is never allowed.
        if allow_remote and not auth_required():
            logger.error(
                "Refusing request: KINEAXIS_ALLOW_REMOTE=1 with KINEAXIS_REQUIRE_API_TOKEN=0"
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": (
                        "Misconfigured auth: remote access requires API token. "
                        "Set KINEAXIS_REQUIRE_API_TOKEN=1 or disable KINEAXIS_ALLOW_REMOTE."
                    )
                },
            )

        # Portal mode: remote hosts may only hit public share links + health.
        # Agency SPA / static UI stays loopback-only even when ALLOW_REMOTE=1.
        if allow_remote and host and not is_loopback(host):
            if public_share or path == "/health":
                return await call_next(request)
            if not _is_api_path(path, request.method):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": (
                            "Agency UI is available on this machine only. "
                            "Clients should use their Pulse or Report share link."
                        )
                    },
                )
            # Remote API without token → 401 below

        if request.method == "OPTIONS" or not _is_api_path(path, request.method):
            return await call_next(request)

        if not auth_required():
            return await call_next(request)

        provided = extract_token(request)
        if not provided or not _tokens_equal(provided, API_TOKEN):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

        return await call_next(request)


def _tokens_equal(provided: str, expected: str) -> bool:
    """Length-safe compare so unequal tokens return False instead of raising."""
    if not provided or not expected:
        return False
    a = provided.encode("utf-8")
    b = expected.encode("utf-8")
    if len(a) != len(b):
        return False
    return secrets.compare_digest(a, b)


def require_api_token(request: Request) -> None:
    """Dependency-style check for routes that must always be authenticated."""
    if not auth_required():
        return
    provided = extract_token(request)
    if not provided or not _tokens_equal(provided, API_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")
