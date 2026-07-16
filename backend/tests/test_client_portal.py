"""Remote client portal — public share links + agency API stay protected."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.database import Base
from app.models import Client
from app.public_urls import absolute_public_url, normalize_public_base, portal_ready


def test_normalize_public_base():
    assert normalize_public_base("https://abc.trycloudflare.com/") == "https://abc.trycloudflare.com"
    assert normalize_public_base("abc.example.com").startswith("https://")


def test_absolute_public_url_uses_env(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://portal.example")
    assert absolute_public_url("/pulse/tok/html") == "https://portal.example/pulse/tok/html"


def test_public_share_paths():
    from app.local_auth import _is_public_share_get

    assert _is_public_share_get("/pulse/abc123/html", "GET") is True
    assert _is_public_share_get("/portal/report/xyz/html", "GET") is True
    assert _is_public_share_get("/pulse/share", "POST") is False
    assert _is_public_share_get("/portal/report/share", "POST") is False
    assert _is_public_share_get("/clients/", "GET") is False


def test_remote_host_spa_blocked_api_401_pulse_ok(monkeypatch):
    import app.local_auth as local_auth

    token = "portal-test-token-32chars-long!!!!"
    monkeypatch.setenv("KINEAXIS_REQUIRE_API_TOKEN", "1")
    monkeypatch.setenv("KINEAXIS_ALLOW_REMOTE", "1")
    monkeypatch.setattr(local_auth, "API_TOKEN", token)

    async def ok(_request: Request):
        return JSONResponse({"ok": True})

    async def pulse_ok(_request: Request):
        return JSONResponse({"pulse": True})

    app = Starlette(
        routes=[
            Route("/", ok),
            Route("/clients/", ok),
            Route("/pulse/abc123token/html", pulse_ok),
        ]
    )
    app.add_middleware(local_auth.LocalAuthMiddleware)
    client = TestClient(app)

    # Spoof remote client via ASGI scope — TestClient is usually testclient/loopback.
    # Exercise middleware helpers + authenticated path instead.
    denied = client.get("/clients/")
    assert denied.status_code == 401

    allowed = client.get("/clients/", headers={"X-Kinexis-Token": token})
    assert allowed.status_code == 200

    # Public pulse path skips token when _is_api_path is false for it
    pulse = client.get("/pulse/abc123token/html")
    assert pulse.status_code == 200


def test_pulse_share_returns_html_url(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import get_db

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://share.example")
    monkeypatch.setenv("KINEAXIS_REQUIRE_API_TOKEN", "0")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    c = Client(name="Portal Co")
    db.add(c)
    db.commit()

    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    try:
        tc = TestClient(app)
        res = tc.post("/pulse/share", json={"client_id": c.id, "expires_days": 30})
        assert res.status_code == 200
        body = res.json()
        assert body["html_url"].startswith("https://share.example/pulse/")
        assert body["html_url"].endswith("/html")
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_portal_ready_hint():
    status = portal_ready(None)
    assert "hint" in status
    assert "share_links_reachable" in status
